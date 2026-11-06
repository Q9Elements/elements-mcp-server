#!/usr/bin/env python3
"""Check the shipped quote line pricing playbook.

Run from the plugin directory: python3 scripts/lint.py
Exit 0 clean, exit 1 with one line per finding.
"""
from __future__ import annotations

import csv
import ast
import io
import json
import os
import re
import sys
import tokenize
from itertools import product
from pathlib import Path
from urllib.parse import unquote


OUTCOME = re.compile(r'^- \*\*(TR-\d{2,})(?::| ' + chr(0x2014) + r') (.*?)\.\*\*', re.M)
BUILD_PATHS = {'_workspace', '.playbook-build'}
GENERATED_PATHS = {'.git', '__pycache__', '.pytest_cache'}
REFERENCE_PATH = re.compile(
    r'(?<![A-Za-z0-9_./:-])(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?'
    r'(?:(?:\.\.?/)+(?:[A-Za-z0-9_.<>-]+/)*[A-Za-z0-9_.<>-]*'
    r'|(?:steps|data|references|templates|agents|scripts|skills|\.claude-plugin|\.codex-plugin)/'
    r'[A-Za-z0-9_./<>-]*|execution-state\.json|README\.md|LICENSE|NOTICE)'
)
# Fixed domains make deleted input rows detectable, as in the sibling lints.
MATRIX_SPECS = {
    'question-routing.csv': ({'topic': (
        'discount', 'pricing-method', 'bundle-and-options', 'price-rules', 'mdq', 'broad',
    )}, ('agent',)),
    'blocked-reasons.csv': ({'reason': (
        'ROUTE_UNAVAILABLE', 'PACKAGE_MISSING', 'ACCESS_GAP', 'NO_QLM_LOG', 'QUERY_FAILED',
    )}, ('meaning', 'owner_role', 'recovery_step')),
}
# Required fields follow direct script/card consumption. Empty values with defined
# fallback behavior stay optional, including routing gates and warning message IDs.
CSV_SPECS = {
    'blocked-reasons.csv': (('reason', 'meaning', 'owner_role', 'recovery_step'), {}),
    'canned-messages.csv': (('id', 'when', 'text'), {'id': (
        'FALLBACK', 'OUT-OF-SCOPE', 'QUOTE-NOT-LINE', 'LINE-NOT-FOUND', 'STALE-LOG',
        'SCOPE-CALC-RULES', 'HISTORY-PER-SYNC', 'CONTRACTED-NOT-READABLE',
        'CALCULATION-PASSES-AMBIGUOUS', 'HISTORY-UNAVAILABLE',
    )}),
    'field-stage-map.csv': (('target_object', 'field_api_name', 'waterfall_stage'), {}),
    'price-action-field-labels.csv': (('label', 'field_api_name'), {}),
    'question-routing.csv': (('topic', 'example_phrases', 'agent'), {}),
    'report-sections.csv': (('order', 'section'), {'order': (
        '1', '2', '3.1', '3.2', '3.3', '3.4', '4', '5',
    )}),
    'required-access.csv': (('object', 'query_id', 'required'), {}),
    'routing-flags.csv': (('flag', 'json_path', 'rule'), {'flag': (
        'isDiscounted', 'hasBundleContext', 'isMdq',
    )}),
    'warning-codes.csv': (('code', 'severity', 'meaning'), {'code': (
        'STALE_LOG', 'BLOCK_BASIS_NOT_QUANTITY', 'POT_UNPRORATE_FAILED',
        'POT_SIBLINGS_TRUNCATED', 'TIER_VALUE_NULL', 'ACTION_FIELD_UNMAPPED',
        'HISTORY_UNAVAILABLE', 'CALCULATION_PASSES_AMBIGUOUS',
    )}),
    'waterfall-stages.csv': (('order', 'stage', 'label', 'sf_field', 'owner_agent'), {'stage': (
        'original', 'list', 'special', 'prorated', 'regular', 'customer', 'partner', 'net',
    )}),
}


def _csv(path: Path, findings: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames or [], list(reader)
    except (OSError, UnicodeDecodeError, csv.Error):
        findings.append(f'{path.name}: missing or invalid CSV')
        return [], []
    for index, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            findings.append(f'{path.name}:{index}: row does not match CSV header')
    return fields, rows


def _check_matrices(skill: Path, findings: list[str]) -> None:
    for filename, (domains, outputs) in MATRIX_SPECS.items():
        fields, rows = _csv(skill / 'data' / filename, findings)
        if not set(domains).union(outputs).issubset(fields):
            findings.append(f'{filename}: missing input or output column')
            continue
        for row in rows:
            for key, values in domains.items():
                if row.get(key) not in values:
                    findings.append(f'{filename}: unknown matrix input {key}={row.get(key)}')
        for values in product(*domains.values()):
            inputs = dict(zip(domains, values))
            matching = [row for row in rows if all(row.get(k) == v for k, v in inputs.items())]
            label = ', '.join(f'{k}={v}' for k, v in inputs.items())
            if not matching:
                findings.append(f'{filename}: matrix combination {label} missing')
            elif len(matching) > 1:
                findings.append(f'{filename}: matrix combination {label} has multiple outputs')
            elif any(not (matching[0].get(key) or '').strip() for key in outputs):
                findings.append(f'{filename}: matrix combination {label} has undefined output')


def _check_data_tables(skill: Path, findings: list[str]) -> None:
    for filename, (required, keys) in CSV_SPECS.items():
        fields, rows = _csv(skill / 'data' / filename, findings)
        missing = set(required) - set(fields)
        if missing:
            findings.append(f'{filename}: missing required column(s) {", ".join(sorted(missing))}')
            continue
        for index, row in enumerate(rows, 2):
            for column in required:
                if not (row.get(column) or '').strip():
                    findings.append(f'{filename}: row {index}: empty required column {column}')
            if (filename == 'routing-flags.csv' and row.get('flag') in keys.get('flag', ())
                    and not (row.get('gates_agent') or '').strip()):
                findings.append(f'{filename}: row {index}: empty required column gates_agent')
        for column, expected in keys.items():
            present = {row.get(column) for row in rows}
            for key in expected:
                if key not in present:
                    findings.append(f'{filename}: missing required {column}={key}')


def _read(path: Path, findings: list[str]) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        findings.append(f'{path.name}: missing or unreadable file')
        return ''


def _dispatch(skill: Path, findings: list[str]) -> tuple[dict[str, str], set[str]]:
    text = _read(skill / 'SKILL.md', findings)
    section = re.search(r'^## State dispatch[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    dispatch, terminal = {}, set()
    for state, cell in re.findall(r'^\|\s*`([^`]+)`\s*\|\s*([^\n]+?)\s*\|\s*$',
                                  section.group(1) if section else '', re.M):
        if state in dispatch or state in terminal:
            findings.append(f'SKILL.md: duplicate dispatch state {state}')
        if cell.lower().startswith('terminal;'):
            terminal.add(state)
            continue
        target = cell.strip('`')
        dispatch[state] = target
        if not (skill / target).is_file():
            findings.append(f'dispatch target missing: {state} -> {target}')
    if not dispatch:
        findings.append('SKILL.md: missing dispatch table')
    if not terminal:
        findings.append('SKILL.md: missing terminal dispatch row')
    return dispatch, terminal


def _check_cards(skill: Path, dispatch: dict[str, str], terminal: set[str],
                 findings: list[str]) -> None:
    transition_owners: dict[str, list[str]] = {}
    for card in sorted((skill / 'steps').glob('*.md')):
        text = _read(card, findings)
        headers = re.findall(r'^State:\s*`([^`]+)`\s*$', text, re.M)
        owners = [state for state, target in dispatch.items()
                  if target == f'steps/{card.name}']
        if len(headers) != 1 or headers != owners:
            findings.append(f'{card.name}: State header does not match dispatch')
        for write in re.finditer(r'"current_state"\s*:\s*', text):
            try:
                state, _ = json.JSONDecoder().raw_decode(text[write.end():])
            except json.JSONDecodeError:
                findings.append(f'{card.name}: invalid current_state write')
                continue
            if not isinstance(state, str) or state not in dispatch and state not in terminal:
                findings.append(f'{card.name}: state write {state} has no dispatch row')
        outcomes = re.search(r'^## Outcomes[^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        bullets = re.findall(r'^- .+', outcomes.group(1), re.M) if outcomes else []
        last = OUTCOME.match(bullets[-1]) if bullets else None
        if not last or last.group(2).lower() != 'otherwise':
            findings.append(f'{card.name}: Outcomes must end with a default outcome')
        for outcome in OUTCOME.finditer(text):
            transition_owners.setdefault(outcome.group(1), []).append(card.name)
    for transition, owners in sorted(transition_owners.items()):
        if len(owners) != 1:
            findings.append(f'{transition}: must appear exactly once on exactly one card')


def _manifest(root: Path, relative: str, findings: list[str]) -> dict | None:
    try:
        value = json.loads((root / relative).read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        findings.append(f'{relative}: missing or invalid JSON')
        return None
    if not isinstance(value, dict):
        findings.append(f'{relative}: expected JSON object')
        return None
    return value


def _check_manifests(root: Path, findings: list[str]) -> None:
    claude = _manifest(root, '.claude-plugin/plugin.json', findings)
    codex = _manifest(root, '.codex-plugin/plugin.json', findings)
    for field in ('name', 'version', 'description'):
        for label, manifest in (('.claude-plugin/plugin.json', claude),
                                ('.codex-plugin/plugin.json', codex)):
            if manifest is not None and not manifest.get(field):
                findings.append(f'{label}: missing {field}')
        if claude is not None and codex is not None and claude.get(field) != codex.get(field):
            findings.append(f'plugin manifest {field} mismatch')
    license_text = _read(root / 'LICENSE', findings)
    lines = license_text.strip().splitlines()
    if (len(lines) >= 2 and lines[0].strip() == 'Apache License'
            and lines[1].strip() == 'Version 2.0, January 2004'):
        expected = 'Apache-2.0'
    else:
        match = re.search(r'^SPDX-License-Identifier:\s*(\S+)\s*$', license_text, re.M)
        expected = match.group(1) if match else None
    if expected is None:
        findings.append('LICENSE: cannot determine license identifier')
    elif codex is not None and codex.get('license') != expected:
        findings.append(f'.codex-plugin/plugin.json: license mismatch; LICENSE is {expected}')


def _check_access(root: Path, skill: Path, findings: list[str]) -> None:
    fields, rows = _csv(skill / 'data' / 'required-access.csv', findings)
    if not {'object', 'field'}.issubset(fields):
        findings.append('required-access.csv: missing object or field column')
        return
    expected_objects = {row['object'] for row in rows if row.get('object')}
    expected_fields = {f"{row['object']}.{row['field']}" for row in rows
                       if row.get('object') and row.get('field')}
    readme = _read(root / 'README.md', findings)
    block = re.search(r'copyable access list[^\n]*\n\s*```text\n(.*?)\n```', readme, re.S)
    if not block:
        findings.append('README.md: missing copyable access list')
        return
    actual_objects, actual_fields = set(), set()
    for line in block.group(1).splitlines():
        objects = re.fullmatch(r'(?:Required|Optional) objects: (.+)', line)
        field_list = re.fullmatch(r'(?:Required|Optional) (\w+) fields: (.+)', line)
        if objects:
            actual_objects.update(value.strip() for value in objects.group(1).split(','))
        elif field_list:
            obj, values = field_list.groups()
            actual_objects.add(obj)
            actual_fields.update(f'{obj}.{value.strip()}' for value in values.split(','))
        elif line.strip():
            findings.append('README.md: access list line must name objects or an object and its fields')
    for kind, expected, actual in (('object', expected_objects, actual_objects),
                                    ('field', expected_fields, actual_fields)):
        for value in sorted(expected - actual):
            findings.append(f'README.md: access list missing {kind} {value}')
        for value in sorted(actual - expected):
            findings.append(f'README.md: access list extra {kind} {value}')


def _shipped_text(root: Path, findings: list[str]) -> dict[Path, str]:
    texts = {}
    for directory, subdirs, filenames in os.walk(root):
        subdirs[:] = sorted(name for name in subdirs if name not in BUILD_PATHS | GENERATED_PATHS)
        for name in sorted(filenames):
            if name in BUILD_PATHS or name.endswith(('.pyc', '.pyo')):
                continue
            path = Path(directory) / name
            try:
                contents = path.read_bytes()
                if b'\x00' not in contents:
                    texts[path] = contents.decode('utf-8')
            except UnicodeDecodeError:
                continue  # Binary assets do not contain text references.
            except OSError:
                findings.append(f'{path.relative_to(root)}: unreadable file')
    return texts


def _reference_lines(source: Path, text: str, findings: list[str]) -> set[int] | None:
    if source.suffix != '.py':
        return None
    # Match the sibling lint's documentation/help seam for Python, plus comments.
    # Test inputs and runtime artifact strings are data, not package citations.
    try:
        tree = ast.parse(text)
        lines = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
            if (isinstance(node, ast.keyword) and node.arg == 'help'
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                lines.update(range(node.value.lineno, node.value.end_lineno + 1))
        lines.update(token.start[0] for token in tokenize.generate_tokens(io.StringIO(text).readline)
                     if token.type == tokenize.COMMENT)
        return lines
    except (SyntaxError, tokenize.TokenError):
        findings.append(f'{source.name}: cannot parse script references')
        return set()


def _link_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith('<'):
        value = value[1:].split('>', 1)[0]
    else:
        value = value.split()[0] if value else ''
    value = unquote(value).split('#', 1)[0]
    if re.match(r'^[a-z][a-z0-9+.-]*:', value, re.I):
        return ''
    return value


def _check_references(root: Path, skill: Path, texts: dict[Path, str],
                      findings: list[str]) -> None:
    for source, text in texts.items():
        relevant = _reference_lines(source, text, findings)
        for number, line in enumerate(text.splitlines(), 1):
            if relevant is not None and number not in relevant:
                continue
            candidates = set()
            # Mask link destinations so URL paths cannot become package paths.
            masked = line
            for match in reversed(list(re.finditer(r'\[[^]]*\]\(([^)]*)\)', line))):
                target = _link_target(match.group(1))
                if target:
                    candidates.add(target)
                masked = masked[:match.start()] + ' ' * (match.end() - match.start()) + masked[match.end():]
            definition = re.match(r'^\s{0,3}\[[^]]+\]:\s*(.*)$', line)
            if definition:
                target = _link_target(definition.group(1))
                if target:
                    candidates.add(target)
                masked = ''
            candidates.update(match.group().rstrip('.,;:') for match in REFERENCE_PATH.finditer(masked))
            for raw in sorted(candidates):
                if '<' in raw or '>' in raw:
                    continue  # A parameterized engagement path, not a concrete citation.
                if raw == 'execution-state.json':
                    continue  # The live engagement file is created from the template.
                plugin_root = raw.startswith('${CLAUDE_PLUGIN_ROOT}/')
                target = raw.removeprefix('${CLAUDE_PLUGIN_ROOT}/')
                if (plugin_root or target.startswith(('agents/', 'scripts/', 'skills/',
                                                      '.claude-plugin/', '.codex-plugin/'))
                        or target in {'LICENSE', 'NOTICE', 'README.md'}
                        or source.parent.name in {'.claude-plugin', '.codex-plugin'}):
                    base = root
                else:
                    base = skill
                resolved = (base / target).resolve()
                excluded = (not resolved.is_relative_to(root)
                            or bool(set(resolved.relative_to(root).parts) & (BUILD_PATHS | GENERATED_PATHS)))
                if excluded or not resolved.exists():
                    findings.append(f'{source.relative_to(root)}:{number}: dangling package reference {raw}')


def _check_punctuation(root: Path, skill: Path, texts: dict[Path, str],
                       findings: list[str]) -> None:
    dash = chr(0x2014)
    for source, text in texts.items():
        in_outcomes = False
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith('## '):
                in_outcomes = line.startswith('## Outcomes')
            checked = line
            if (source.parent == skill / 'steps' and in_outcomes and OUTCOME.match(line)):
                checked = re.sub(r'(^- \*\*TR-\d{2,}) ' + dash + ' ', r'\1: ', line, count=1)
            if dash in checked:
                findings.append(f'{source.relative_to(root)}:{number}: em dash is not allowed')


def lint_package(root: Path) -> list[str]:
    """Return one line per package finding."""
    root = root.resolve()
    skill = root / 'skills' / 'explain-quote-line-pricing'
    findings: list[str] = []
    dispatch, terminal = _dispatch(skill, findings)
    _check_cards(skill, dispatch, terminal, findings)
    _check_matrices(skill, findings)
    _check_data_tables(skill, findings)
    _check_manifests(root, findings)
    _check_access(root, skill, findings)
    texts = _shipped_text(root, findings)
    _check_references(root, skill, texts, findings)
    _check_punctuation(root, skill, texts, findings)
    return sorted(set(findings))


def main() -> int:
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        return 0
    findings = lint_package(Path(__file__).resolve().parents[1])
    if findings:
        print('\n'.join(findings))
        return 1
    print('lint clean: quote line pricing package')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
