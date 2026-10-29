#!/usr/bin/env python3
"""Lint the data-load-impact deterministic layer and any part-two playbook files present."""

from __future__ import annotations

import ast
import csv
import json
import re
import sys
from itertools import product
from pathlib import Path
from urllib.parse import unquote


DATA_FILES = {
    "re-enable-sequence.csv", "bypass-mechanisms.csv",
    "ruling-rules.csv", "dispositions.csv", "api-thresholds.csv",
    "lock-mitigation-ladder.csv", "tool-matrix.csv", "load-sequencing.csv", "rollback-rules.csv",
    "thresholds.csv", "blocked-reasons.csv",
    "uncatalogued-lock-rows.csv", "incident-classes.csv",
}
RETIRED_TOOL_NAMES = (
    "query_metadata", "get_metadata_node", "get_node_change_history",
    "explain_metadata_item", "code_search", "metadata_search", "get_active_space",
)
EXPECTED_BUNDLE_HEADERS = {
    "fire-chain-digest.csv": ["target", "branch", "minDepth", "entityApiName", "entityNodeId", "alternativesTotal", "alternativesUnresolvedTotal", "targetsAreAlternatives", "runtimeTargetCardinalityMin", "runtimeTargetCardinalityMax", "mechanism", "firingAutomation", "firingAutomationNodeId", "relationshipField", "relationshipFieldNodeId", "lockConsequence", "valueChange", "operation", "operationSource", "phaseBucket", "recursiveSave", "ruleIds", "variantsReturned", "variantsTotal", "representativePath", "digestRowId"],
    "alternatives.csv": ["target", "branch", "minDepth", "alternativesTotal", "targetsAreAlternatives", "runtimeTargetCardinalityMin", "runtimeTargetCardinalityMax", "alternativeTargetApiName", "alternativeTargetNodeId", "digestRowId"],
    "automations.csv": ["target", "kind", "type", "apiName", "name", "nodeId", "active", "mechanismFamily", "branch", "triggerEvents", "matchedFields", "partialReadsAssumed", "referencedWrittenFields"],
    "lock-rows.csv": ["target", "rowId", "table", "group", "ruleId", "column", "branch", "consequence", "label", "parentObjects", "rollupFields"],
    "fan-in.csv": ["target", "column", "parentObjects", "maxRowsPerParent", "skew"],
    "receipts.csv": ["scope", "target", "code", "classification", "ruleId", "detail"],
}
INCIDENT_CLASSES = {
    "unexpected_email", "lock_contention", "duplicate_records", "owner_overwritten",
    "bad_data_while_validation_off", "parent_grandparent_cascade", "governor_limit_failure",
    "unpredicted_automation", "evidence_lost", "accidental_re_fire", "unrecoverable_rollback",
}
UNCATALOGUED_ROWS = {"3", "4", "10", "14", "15", "16", "17", "32"}
DISPOSITIONS = {
    "deactivate",
    "bypass",
    "leave-on",
    "review: runs only when invoked (trigger, flow, batch schedule or UI)",
}
REFERENCE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?"
    r"(?:(?:steps|data|references|templates|agents|scripts|skills|work|report|stories)/"
    r"[A-Za-z0-9_./<>-]*|execution-state\.json)"
)
# Input domains transcribed from the named CSVs. Keep them fixed so a deleted row is visible.
# The one-condition ruling domains are deliberately narrow: those rules apply only when true
# (or, for validation replacement, when the disposition is deactivate).
MATRIX_SPECS = {
    "blocked-reasons.csv": [({"reason": ("MISSING_PRIMITIVE", "SYNC_INCOMPLETE")}, ("owner", "recovery_outcome"))],
    "incident-classes.csv": [({"incident_class": tuple(sorted(INCIDENT_CLASSES))}, ("plain_wording", "control", "control_reference"))],
    "tool-matrix.csv": [({"tool": (
        "Data Loader", "Bulk API 1.0", "Bulk API 2.0", "sf CLI",
        "Salesforce Inspector Reloaded", "Workbench", "dataloader.io",
    )}, ("api", "batch_control", "serial_mode", "automation_bypass", "verification"))],
    "ruling-rules.csv": [
        ({"rule": ("automation-disposition",), "input": ("bypass_verdict",),
          "condition": ("present", "absent", "unknown")}, ("output", "required_detail")),
        ({"rule": ("validation-replacement",), "input": ("disposition",),
          "condition": ("deactivate",)}, ("output", "required_detail")),
        ({"rule": ("email-safety",), "input": ("email_sender",),
          "condition": ("true",)}, ("output", "required_detail")),
        ({"rule": ("assignment-rule",), "input": ("api_load",),
          "condition": ("true",)}, ("output", "required_detail")),
        ({"rule": ("duplicate-rule",), "input": ("action",),
          "condition": ("block", "allow-with-alert", "allow-without-alert")}, ("output", "required_detail")),
        ({"rule": ("serial-mode",), "input": ("condition",),
          "condition": ("default", "named-operation", "persistent-lock")}, ("output", "required_detail")),
    ],
}
KEYED_LOOKUP_SPECS = {
    # checklist.py builds these dictionaries by key; rehearsal_reconcile.py also reads thresholds.
    "api-thresholds.csv": ("key", ("value",)),
    "thresholds.csv": ("key", ("value",)),
    "dispositions.csv": ("disposition", ("meaning", "blast_radius", "applies_to")),
    "uncatalogued-lock-rows.csv": (
        "cheat_sheet_row", ("trigger_condition", "consequence", "action", "rule_id")
    ),
}


def _keyed_lookup_checks(tables: dict[str, list[dict[str, str]]], findings: list[str]) -> None:
    for filename, (key_column, outputs) in KEYED_LOOKUP_SPECS.items():
        seen = set()
        for line_number, row in enumerate(tables.get(filename, []), start=2):
            key = row.get(key_column, "").strip()
            if not key:
                findings.append(f"{filename}:{line_number}: empty key {key_column}; fill the lookup key")
            elif key in seen:
                findings.append(f"{filename}:{line_number}: duplicate key {key_column}={key}; keep one row")
            seen.add(key)
            for output in outputs:
                if not row.get(output, "").strip():
                    findings.append(f"{filename}:{line_number}: empty output {output}; fill the lookup value")


def _matrix_checks(tables: dict[str, list[dict[str, str]]], findings: list[str]) -> None:
    for filename, groups in MATRIX_SPECS.items():
        rows = tables.get(filename, [])
        for domains, outputs in groups:
            keys = tuple(domains)
            for combination in product(*(domains[key] for key in keys)):
                inputs = dict(zip(keys, combination))
                matching = [
                    row for row in rows
                    if all(row.get(key) == value for key, value in inputs.items())
                ]
                label = ", ".join(f"{key}={value}" for key, value in inputs.items())
                if not matching:
                    findings.append(f"{filename}: matrix combination {label} missing; add one output row")
                elif len(matching) > 1:
                    findings.append(f"{filename}: matrix combination {label} has multiple outputs; keep one row")
                elif any(not matching[0].get(output, "").strip() for output in outputs):
                    findings.append(f"{filename}: matrix combination {label} has undefined output; fill {', '.join(outputs)}")


def _reference_target(raw: str, source: Path, line_number: int, findings: list[str]) -> str | None:
    value = raw.strip()
    if value.startswith("<"):
        value = value[1:].split(">", 1)[0] if ">" in value else ""
    else:
        value = value.split()[0] if value.split() else ""
    if not value:
        findings.append(f"{source}:{line_number}: empty Markdown link destination; supply a path")
        return None
    target = unquote(value).split("#", 1)[0]
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
        return None
    return target


def _package_reference_checks(root: Path, skill: Path, paths: list[Path], findings: list[str]) -> None:
    for source in paths:
        if source.suffix not in {".md", ".py", ".csv"}:
            continue
        label = source.relative_to(root)
        relevant_lines = None
        if source.suffix == ".py":
            try:
                tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            except (OSError, UnicodeDecodeError, SyntaxError) as error:
                findings.append(f"{label}: cannot parse script references ({type(error).__name__}); correct the file")
                continue
            relevant_lines = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                        relevant_lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
                if isinstance(node, ast.keyword) and node.arg == "help" and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    relevant_lines.update(range(node.value.lineno, node.value.end_lineno + 1))
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            findings.append(f"{label}: cannot read references ({type(error).__name__}); correct the file")
            continue
        for line_number, line in enumerate(lines, 1):
            if relevant_lines is not None and line_number not in relevant_lines:
                continue
            candidates = []
            markdown_destinations = []
            if source.suffix in {".md", ".py"}:
                for match in re.finditer(r"\[[^]]*\]\(([^)]*)\)", line):
                    markdown_destinations.append(match.span(1))
                    target = _reference_target(match.group(1), label, line_number, findings)
                    if target:
                        candidates.append(target)
                definition = re.match(r"^\s{0,3}\[[^]]+\]:\s*(.*)$", line)
                if definition:
                    markdown_destinations.append(definition.span(1))
                    target = _reference_target(definition.group(1), label, line_number, findings)
                    if target:
                        candidates.append(target)
            if source.suffix == ".py":
                candidates.extend(
                    match.group().rstrip(".,;:") for match in REFERENCE_PATH.finditer(line)
                    if not any(start <= match.start() and match.end() <= end
                               for start, end in markdown_destinations)
                )
            else:
                for code in re.findall(r"`([^`]+)`", line):
                    candidates.extend(match.group() for match in REFERENCE_PATH.finditer(code))
            for raw in sorted(set(candidates)):
                if "<" in raw or ">" in raw:
                    continue  # A documented parameter, not a concrete package file.
                plugin_root = raw.startswith("${CLAUDE_PLUGIN_ROOT}/")
                target = raw.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
                if target.startswith(("agents/", "scripts/", "skills/")) or plugin_root:
                    base = root
                else:
                    base = skill
                resolved = (base / target).resolve()
                if resolved.is_relative_to(skill):
                    skill_relative = resolved.relative_to(skill)
                    if skill_relative.parts and skill_relative.parts[0] in {"work", "report", "stories"}:
                        continue
                    if skill_relative == Path("execution-state.json"):
                        continue
                if not resolved.is_relative_to(root) or not resolved.exists():
                    findings.append(
                        f"{label}:{line_number}: dangling package reference "
                        f"{raw}; correct the path or ship the referenced file"
                    )


def _manifest(path: Path, root: Path, findings: list[str]) -> dict | None:
    label = str(path.relative_to(root))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        findings.append(f"{label}: missing")
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        findings.append(f"{label}: invalid JSON")
        return None
    if not isinstance(value, dict):
        findings.append(f"{label}: expected JSON object")
        return None
    return value


def _plugin_metadata_checks(root: Path, findings: list[str]) -> None:
    claude = _manifest(root / ".claude-plugin" / "plugin.json", root, findings)
    codex = _manifest(root / ".codex-plugin" / "plugin.json", root, findings)
    for field in ("name", "version", "description"):
        if claude is not None and field not in claude:
            findings.append(f".claude-plugin/plugin.json: missing {field}")
        if codex is not None and field not in codex:
            findings.append(f".codex-plugin/plugin.json: missing {field}")
        if claude is not None and codex is not None and claude.get(field) != codex.get(field):
            findings.append(f"plugin manifest {field} mismatch")
    state = _manifest(root / "skills" / "data-load-impact" / "templates" / "execution-state.json", root, findings)
    if claude is not None and state is not None:
        if state.get("engagement", {}).get("playbook_version") != claude.get("version"):
            findings.append("execution-state.json: engagement.playbook_version must match the plugin manifest version")

    try:
        lines = (root / "LICENSE").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        findings.append("LICENSE: missing")
        return
    except (OSError, UnicodeDecodeError):
        findings.append("LICENSE: unreadable")
        return
    while lines and not lines[0].strip():
        lines.pop(0)
    if len(lines) >= 2 and lines[0].strip() == "Apache License" and lines[1].strip() == "Version 2.0, January 2004":
        expected_license = "Apache-2.0"
    else:
        first_line = lines[0].strip() if lines else ""
        match = re.fullmatch(r"(?:SPDX-License-Identifier:\s*)?([A-Za-z0-9][A-Za-z0-9.+-]*)", first_line)
        if not match:
            findings.append("LICENSE: unrecognised license text")
            return
        expected_license = match.group(1)
    if codex is not None and codex.get("license") != expected_license:
        findings.append(f".codex-plugin/plugin.json: license mismatch; LICENSE is {expected_license}")


def _argparse_options(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    options = {"-h", "--help"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        options.update(
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant)
            and isinstance(argument.value, str)
            and argument.value.startswith("-")
        )
    return options


def _csv(path: Path, findings: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
    except FileNotFoundError:
        findings.append(f"missing data file: {path.name}")
        return [], []
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        findings.append(f"{path.name}: cannot read CSV ({type(error).__name__}); correct the file")
        return [], []
    for index, row in enumerate(rows, start=2):
        if None in row:
            findings.append(f"{path.name}:{index}: row has more values than its header")
            del row[None]
        for field in fields:
            if row.get(field) is None:
                findings.append(f"{path.name}:{index}: missing {field} cell; fill the value")
                row[field] = ""
    return fields, rows


def _state_writes(text: str) -> list[tuple[int, dict | None]]:
    writes = []
    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 0
        quoted = False
        escaped = False
        end = None
        for position in range(start, len(text)):
            character = text[position]
            if escaped:
                escaped = False
            elif quoted and character == "\\":
                escaped = True
            elif character == '"':
                quoted = not quoted
            elif not quoted and character == "{":
                depth += 1
            elif not quoted and character == "}":
                depth -= 1
                if depth == 0:
                    end = position + 1
                    break
        if end is None or '"current_state"' not in text[start:end]:
            continue
        try:
            value = json.loads(text[start:end])
        except json.JSONDecodeError:
            value = None
        if value is None or isinstance(value, dict) and "current_state" in value:
            writes.append((start, value))
    return writes


def _part_two_checks(root: Path, skill: Path, findings: list[str]) -> None:
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        return
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        findings.append("SKILL.md: unreadable; correct the file")
        return
    if "engagement directory is the working directory" not in text.lower():
        findings.append("SKILL.md: engagement directory must be the working directory")
    dispatch = dict(re.findall(r"\| `([a-z-]+)` \| `(steps/[a-z0-9-]+\.md)` \|", text))
    terminal = set(re.findall(r"\| `([a-z-]+)` \| terminal[^\n]*\|", text))
    dispatch_steps = {**dispatch, **{state: None for state in terminal}}
    for state, card in dispatch.items():
        if not (skill / card).is_file():
            findings.append(f"dispatch target missing: {state} -> {card}")
    cards = sorted((skill / "steps").glob("*.md"))
    transition_owners = {}
    card_texts = {}
    for card in cards:
        try:
            card_text = card.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(f"{card.name}: unreadable; correct the file")
            continue
        card_texts[card.name] = card_text
        outcomes = re.search(
            r"^## Outcomes(?:, in precedence order)?[ \t]*$([\s\S]*?)(?=^## |\Z)",
            card_text, re.M,
        )
        if outcomes:
            bullets = list(re.finditer(r"^- ", outcomes.group(1), re.M))
            last = outcomes.group(1)[bullets[-1].start():] if bullets else ""
            bullet_lines = []
            for index, line in enumerate(last.splitlines(keepends=True)):
                if index and line.strip() and not line[:1].isspace():
                    break
                bullet_lines.append(line)
            last = "".join(bullet_lines)
            default = re.match(r"- \*\*TR-\d\d " + chr(0x2014) + r" Otherwise\.\*\*", last)
            write = next((value for _, value in _state_writes(last) if isinstance(value, dict)), None)
            next_card = re.search(r"Next card: `([^`]+)`", last)
            if not (
                default and write and next_card and next_card.group(1) == write.get("current_step")
                and "Record the default call in `decisions_log` and tell the user." in last
            ):
                findings.append(
                    f"{card.name}: default outcome missing or malformed; end Outcomes with "
                    "**TR-NN " + chr(0x2014) + " Otherwise.**, a state write, the matching Next card, "
                    "and a recorded default call reported to the user"
                )
        else:
            findings.append(
                f"{card.name}: default outcome missing or malformed; add an Outcomes section "
                "with a final **TR-NN " + chr(0x2014) + " Otherwise.** bullet"
            )
        for offset, write in _state_writes(card_text):
            line_number = card_text.count("\n", 0, offset) + 1
            if not isinstance(write, dict):
                findings.append(f"{card.name}:{line_number}: invalid state write; use a JSON object")
                continue
            state_written = write.get("current_state")
            step_written = write.get("current_step")
            if not isinstance(state_written, str):
                findings.append(f"{card.name}:{line_number}: state write {state_written!r} has no dispatch row; add a card or terminal row to SKILL.md")
                continue
            if state_written not in dispatch_steps:
                findings.append(
                    f"{card.name}:{line_number}: state write {state_written} has no dispatch row; "
                    "add a card or terminal row to SKILL.md"
                )
            elif step_written != dispatch_steps[state_written]:
                findings.append(
                    f"{card.name}:{line_number}: state write {state_written} current_step "
                    f"{step_written!r} differs from dispatch {dispatch_steps[state_written]!r}; "
                    "write the mapped step (null for terminal states)"
                )
        if re.search(r"\b(?:report|tell|present|show)\b[^\n]{0,100}\b(?:script|playbook)[ -](?:issues?|errors?|defects?)\b[^\n]{0,100}\bowner\b", card_text, re.I):
            findings.append(f"{card.name}: script issue must stay in open_items, not go to owner")
        state = re.search(r"^State: `([a-z-]+)`", card_text, re.M)
        if not state:
            findings.append(f"{card.name}: no State header")
        elif dispatch.get(state.group(1)) != f"steps/{card.name}":
            findings.append(f"{card.name}: state does not match dispatch")
        for section in ("## Purpose", "## Procedure", "## Outcomes", "## Failure"):
            if section not in card_text:
                findings.append(f"{card.name}: missing section {section}")
        if not re.search(r"\bstop rule\b", card_text, re.I):
            findings.append(f"{card.name}: stop rule is not stated")
        for transition in re.findall(r"\*\*(TR-\d\d) ", card_text):
            transition_owners.setdefault(transition, []).append(card.name)
        for invocation in re.finditer(
            r"\bpython3 ((?:\"?\$\{CLAUDE_PLUGIN_ROOT\}/)?)(scripts/[A-Za-z0-9_-]+\.py)\"?\b([^`\n]*)",
            card_text,
        ):
            prefix = invocation.group(1)
            script_name = invocation.group(2)
            if "${CLAUDE_PLUGIN_ROOT}/" not in prefix:
                findings.append(
                    f"{card.name}: script invocation must use ${{CLAUDE_PLUGIN_ROOT}}"
                )
            if not (root / script_name).is_file():
                findings.append(f"{card.name}: missing script {script_name}")
                continue
            try:
                accepted = _argparse_options(root / script_name)
            except (OSError, UnicodeDecodeError, SyntaxError) as error:
                findings.append(f"{card.name}: cannot parse {script_name} options ({type(error).__name__}); correct the script")
                continue
            for option in re.findall(r"(?<!\w)--[a-z0-9-]+", invocation.group(3)):
                if option not in accepted:
                    findings.append(f"{card.name}: {script_name} does not accept {option}")
        for data_file in set(re.findall(r"\bdata/[A-Za-z0-9_.-]+\.csv\b", card_text)):
            if not (skill / data_file).is_file():
                findings.append(f"{card.name}: missing data file {data_file}")
    maximum = max((int(value[3:]) for value in transition_owners), default=0)
    for number in range(1, maximum + 1):
        transition = f"TR-{number:02d}"
        if len(transition_owners.get(transition, [])) != 1:
            findings.append(f"{transition}: must appear on exactly one card")
    skill_transitions = set(re.findall(r"\| `(TR-\d\d)` \|", text))
    for transition in sorted(skill_transitions):
        if len(transition_owners.get(transition, [])) != 1:
            findings.append(
                f"{transition}: SKILL.md transition must appear on exactly one card as an exit"
            )
    for transition in sorted(set(transition_owners) - skill_transitions):
        findings.append(f"{transition}: card exit is not declared in SKILL.md")

    card_text = card_texts
    if "such as Claude Code or the Claude app" not in card_text.get("01-check-prerequisites.md", ""):
        findings.append("01-check-prerequisites.md: host check must name a script-capable host")
    intake = card_text.get("02-intake-manifest.md", "")
    if "--hash-ids" not in intake:
        findings.append("02-intake-manifest.md: profiler invocation must pass --hash-ids")
    if "work/bundle-baseline/<object>-<operation>/" not in intake:
        findings.append("02-intake-manifest.md: baseline bundle path must include object and operation")
    analysis = card_text.get("03-analyze-impact.md", "")
    if "work/bundle/<object>-<operation>/" not in analysis:
        findings.append("03-analyze-impact.md: bundle path must include object and operation")
    audit = card_text.get("04-audit-bypass.md", "")
    if "Space identifier" not in audit:
        findings.append("04-audit-bypass.md: auditor input must include the Space identifier")
    package = card_text.get("05-ratify-safety-package.md", "")
    for required in ("--tool-targets", "--finalize", "work/bypass/verdicts.csv"):
        if required not in package:
            findings.append(f"05-ratify-safety-package.md: missing finalized-package contract {required}")
    rehearsal = card_text.get("06-rehearse.md", "")
    if "claude.ai" in rehearsal:
        findings.append("06-rehearse.md: chat-only execution path is unreachable")
    if "rehearsal_reconcile.py" not in rehearsal or "--checklist" not in rehearsal:
        findings.append("06-rehearse.md: reconciliation must read the finalized checklist")
    delivery = card_text.get("07-deliver-backlog.md", "")
    if "recommends adding hooks" not in delivery:
        findings.append("07-deliver-backlog.md: final report must recommend adding hooks")

    agents = root / "agents"
    inherited = {
        "org-context-exporter.md": {"get_metadata_component", "search_metadata"},
        "order-of-execution-narrator.md": {"explain_metadata_components"},
        "bypass-readiness-auditor.md": {"get_metadata_component"},
    }
    for name, tools in inherited.items():
        path = agents / name
        if not path.is_file():
            findings.append(f"agents/{name}: missing agent")
            continue
        try:
            agent_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(f"agents/{name}: unreadable; correct the file")
            continue
        frontmatter = agent_text.split("---", 2)[1] if agent_text.startswith("---") else ""
        if re.search(r"^tools:", frontmatter, re.M):
            findings.append(f"agents/{name}: Elements agent must inherit session tools")
        for tool in tools:
            if tool not in agent_text:
                findings.append(f"agents/{name}: body must name allowed tool {tool}")
    exporter = agents / "org-context-exporter.md"
    if exporter.is_file() and "model: haiku" not in exporter.read_text(encoding="utf-8"):
        findings.append("agents/org-context-exporter.md: model must be haiku")
    reviewer = agents / "safety-package-reviewer.md"
    if reviewer.is_file():
        try:
            reviewer_text = reviewer.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append("agents/safety-package-reviewer.md: unreadable; correct the file")
        else:
            if "tools: Read, Glob" not in reviewer_text:
                findings.append("agents/safety-package-reviewer.md: reviewer tools must be Read, Glob")

    state_path = skill / "templates" / "execution-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        package_state = state.get("package", {})
        rehearsal_state = state.get("rehearsal", {})
        for field in (
            "controlFailures", "unpredicted", "errorFiles", "duplicatesDetected", "lockErrors",
            "lockErrorsAccepted", "ladderChanges",
        ):
            if field not in rehearsal_state:
                findings.append(f"execution-state.json: rehearsal is missing {field}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
        findings.append("execution-state.json: invalid JSON")


def lint_package(root: Path) -> list[str]:
    root = root.resolve()
    skill = root / "skills" / "data-load-impact"
    data = skill / "data"
    findings = []
    rendered_fixtures = root / "scripts" / "tests" / "fixtures" / "rendered"
    for path in sorted(rendered_fixtures.glob("*.md")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"script-defect|Elements team|my brief|engineering", line, re.I):
                findings.append(f"{path.relative_to(root)}:{line_number}: rendered output contains internal marker")
    playbook_surfaces = [
        *sorted((skill / "steps").glob("*.md")),
        *sorted((root / "agents").glob("*.md")),
        skill / "SKILL.md",
        *sorted((skill / "references").glob("*.md")),
        root / "README.md",
    ]
    for path in playbook_surfaces:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, 1):
            for tool_name in RETIRED_TOOL_NAMES:
                if re.search(rf"\b{re.escape(tool_name)}\b", line):
                    findings.append(
                        f"{path.relative_to(root)}:{line_number}: retired tool name {tool_name}"
                    )
    _plugin_metadata_checks(root, findings)
    present = {path.name for path in data.glob("*.csv")}
    for name in sorted(DATA_FILES - present):
        findings.append(f"missing data file: {name}")
    for name in sorted(present - DATA_FILES):
        findings.append(f"unexpected data file: {name}")
    tables = {}
    for name in sorted(DATA_FILES & present):
        fields, rows = _csv(data / name, findings)
        tables[name] = rows
        if "source" not in fields:
            findings.append(f"{name}: no source column")
        for index, row in enumerate(rows, start=2):
            if not row.get("source", "").strip():
                findings.append(f"{name}:{index}: source is empty")
            if re.search(
                r"standing decision|build plan|process document|house playbook|published resolution|method decision",
                row.get("source", ""), re.I,
            ):
                findings.append(f"{name}:{index}: source contains build narrative")

    for condition in ("block", "allow-with-alert"):
        rule = next(
            (row for row in tables.get("ruling-rules.csv", [])
             if row.get("rule") == "duplicate-rule" and row.get("condition") == condition),
            {},
        )
        if "inferred for Bulk API and measured in rehearsal" not in rule.get("required_detail", ""):
            findings.append(f"ruling-rules.csv: {condition} duplicate rule needs the Bulk API measured-in-rehearsal marker")

    dispositions = tables.get("dispositions.csv", [])
    disposition_values = {row.get("disposition") for row in dispositions}
    for value in disposition_values - DISPOSITIONS:
        findings.append(f"dispositions.csv: unknown disposition {value}")
    if disposition_values != DISPOSITIONS:
        findings.append(
            "dispositions.csv: must define deactivate, bypass, leave-on, and Apex review"
        )

    _matrix_checks(tables, findings)
    _keyed_lookup_checks(tables, findings)

    for row in tables.get("blocked-reasons.csv", []):
        if not row.get("recovery_outcome", "").strip():
            findings.append(f"blocked-reasons.csv: {row.get('reason')} has no recovery outcome")

    part_two_present = (skill / "SKILL.md").is_file()
    for row in tables.get("thresholds.csv", []):
        used_by = row.get("used_by", "")
        destination = root / used_by if used_by.startswith("scripts/") else skill / used_by
        if used_by.startswith("steps/") and not part_two_present:
            continue
        if not destination.is_file():
            findings.append(f"thresholds.csv: {row.get('key')} used_by {used_by} missing")

    incident_values = {row.get("incident_class") for row in tables.get("incident-classes.csv", [])}
    if incident_values != INCIDENT_CLASSES:
        findings.append("incident-classes.csv: must define exactly the eleven standing incident classes")
    for row in tables.get("incident-classes.csv", []):
        if not row.get("plain_wording", "").strip():
            findings.append(f"incident-classes.csv: {row.get('incident_class')} has no plain_wording")
        if not row.get("control", "").strip() or not row.get("control_reference", "").strip():
            findings.append(f"incident-classes.csv: {row.get('incident_class')} has no control")

    uncatalogued = tables.get("uncatalogued-lock-rows.csv", [])
    if {row.get("cheat_sheet_row") for row in uncatalogued} != UNCATALOGUED_ROWS:
        findings.append("uncatalogued-lock-rows.csv: rows must be exactly 3, 4, 10, 14, 15, 16, 17, 32")
    catalog_ids = set()
    for catalog in root.rglob("rule-catalog.json"):
        if "_workspace" in catalog.relative_to(root).parts:
            continue
        try:
            value = json.loads(catalog.read_text(encoding="utf-8"))
            catalog_ids.update(row.get("id") for row in value if isinstance(row, dict))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            findings.append(f"{catalog.relative_to(root)}: invalid rule catalog")
    for row in uncatalogued:
        if row.get("rule_id") in catalog_ids:
            findings.append(f"uncatalogued-lock-rows.csv: row {row.get('cheat_sheet_row')} duplicates bundle rule {row.get('rule_id')}")

    bundle = root / "scripts" / "tests" / "fixtures" / "bundle"
    required_bundle = set(EXPECTED_BUNDLE_HEADERS) | {
        "targets.json", "coverage.json", "rule-catalog.json", "rules-data.json", "response.json", "envelope.json"
    }
    if bundle.is_dir():
        missing = required_bundle - {path.name for path in bundle.iterdir() if path.is_file()}
        if missing:
            findings.append(f"synthetic bundle missing files: {', '.join(sorted(missing))}")
        bundle_rows = {}
        for name, expected in EXPECTED_BUNDLE_HEADERS.items():
            fields, rows = _csv(bundle / name, findings)
            bundle_rows[name] = rows
            if fields != expected:
                findings.append(f"synthetic bundle {name}: header does not match server source")
        try:
            response = json.loads((bundle / "response.json").read_text(encoding="utf-8"))
            targets = response.get("targets", [])
            expected_counts = {
                "fire-chain-digest.csv": sum(
                    len(row.get("variants", []))
                    for target in targets
                    for chain in target.get("fireChain", [])
                    for row in chain.get("digest", [])
                ),
                "alternatives.csv": sum(
                    len(row.get("variants", [])) * len(row.get("targetAlternatives", []))
                    for target in targets
                    for chain in target.get("fireChain", [])
                    for row in chain.get("digest", [])
                ),
                "automations.csv": sum(
                    len(target.get("directAutomations", {}).get("matched", []))
                    + len(target.get("validationRules", {}).get("matched", []))
                    + len(target.get("assignmentRules", {}).get("matched", []))
                    for target in targets
                ),
                "lock-rows.csv": sum(
                    len(target.get("loadRisk", {}).get("lockRows", [])) for target in targets
                ),
                "fan-in.csv": sum(
                    len(target.get("loadRisk", {}).get("fanIn", [])) for target in targets
                ),
                "receipts.csv": len(response.get("receipts", [])) + sum(
                    len(target.get("receipts", []))
                    + len(target.get("loadRisk", {}).get("receipts", []))
                    + sum(len(chain.get("receipts", [])) for chain in target.get("fireChain", []))
                    for target in targets
                ),
            }
            for name, expected_count in expected_counts.items():
                actual_count = len(bundle_rows.get(name, []))
                if actual_count != expected_count:
                    findings.append(
                        f"synthetic bundle {name} row count {actual_count} differs from response {expected_count}"
                    )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, TypeError):
            findings.append("synthetic bundle response.json is invalid")

    for snapshot in skill.rglob("rules-data.json"):
        findings.append(f"{snapshot.relative_to(root)}: rules-data.json must come from a baseline bundle")

    em_dash = chr(0x2014)
    checked_paths = [path for path in skill.rglob("*") if path.is_file()]
    checked_paths.extend(path for path in (root / "agents").glob("*.md") if path.is_file())
    checked_paths.extend(path for path in (root / "scripts").glob("*.py") if path.is_file())
    checked_paths.extend(path for path in (root / "scripts").glob("*.md") if path.is_file())
    if (root / "README.md").is_file():
        checked_paths.append(root / "README.md")
    _package_reference_checks(root, skill, checked_paths, findings)
    readable_paths = {}
    for path in sorted(set(checked_paths)):
        try:
            readable_paths[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(f"{path.relative_to(root)}: unreadable; correct the file")
    for path, contents in readable_paths.items():
        for line_number, line in enumerate(contents.splitlines(), start=1):
            checked = re.sub(r"(\*\*TR-\d\d) " + em_dash, r"\1", line)
            if em_dash in checked:
                findings.append(f"{path.relative_to(root)}:{line_number}: em dash is not allowed")

    for path, contents in readable_paths.items():
        flattened = re.sub(r"\s+", " ", contents.lower())
        if re.search(r"\btodowrite\b|\bartifact tool\b", flattened):
            findings.append(f"{path.relative_to(root)}: names a host presentation tool")

    cli = root / "scripts" / "CLI.md"
    if cli in readable_paths and "## Changes" in readable_paths[cli]:
        findings.append("scripts/CLI.md: current interface must not contain a Changes section")
    fresh_reader_phrases = ("there is no sponsor role", "no waiver", "never invent a retrofit branch")
    for path, contents in readable_paths.items():
        if path.resolve() == Path(__file__).resolve():
            continue
        lowered = contents.lower()
        for phrase in fresh_reader_phrases:
            if phrase in lowered:
                findings.append(f"{path.relative_to(root)}: rewrite history or absence wording: {phrase}")

    _part_two_checks(root, skill, findings)
    return sorted(set(findings))


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    root = Path(__file__).resolve().parent.parent
    findings = lint_package(root)
    if findings:
        print("\n".join(findings))
        return 1
    print(
        f"lint clean: {len(DATA_FILES)} data files; decision matrices; state writes; "
        "default outcomes; package references; card script invocations; "
        "card data citations; transition exits; plugin manifests and license; "
        "playbook structure and punctuation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
