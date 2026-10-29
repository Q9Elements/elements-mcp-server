#!/usr/bin/env python3
"""Check the shipped change-impact playbook package."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


TOOL_CLASSES = {"transient", "external", "permanent"}
TR_ID = re.compile(r"\*\*(TR-[A-Z0-9]+)\s+—")
PATH_TOKEN = re.compile(
    r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?(?:\.\.?/)*(?:steps|data|references|templates|agents|scripts|skills)/[A-Za-z0-9_./-]+|execution-state\.json"
)
BUILD_PATHS = {"_workspace", ".playbook-build"}


def _read(path: Path, findings: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        findings.append(f"{path}: cannot read ({type(error).__name__})")
        return ""


def _dispatch(skill: Path, text: str, findings: list[str]) -> tuple[dict[str, str], set[str]]:
    rows: dict[str, str] = {}
    terminal: set[str] = set()
    in_dispatch = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if "| `current_state` | Card |" in line:
            in_dispatch = True
            continue
        if not in_dispatch:
            continue
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        match = re.match(r"\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|", line)
        if not match or match.group(1).strip("- ") == "":
            continue
        state, cell = match.groups()
        card_match = re.search(r"`([^`]+\.md)`", cell)
        if not card_match or "terminal" in cell.lower():
            terminal.add(state)
            continue
        card_path = card_match.group(1)
        rows[state] = card_path
        if not (skill / card_path).is_file():
            findings.append(f"SKILL.md:{line_number}: dispatch target {card_path} missing")
    return rows, terminal


def _state_writes(text: str) -> list[str]:
    states: list[str] = []
    for match in re.finditer(r"\{[^{}]*\}", text):
        try:
            value = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("current_state"), str):
            states.append(value["current_state"])
    return states


def _check_cards(skill: Path, dispatch: dict[str, str], terminal: set[str], findings: list[str]) -> list[Path]:
    card_paths = sorted((skill / "steps").glob("*.md"))
    path_states = {path: state for state, card in dispatch.items() for path in [skill / card]}
    seen_ids: dict[str, set[Path]] = defaultdict(set)
    id_counts: dict[str, int] = defaultdict(int)
    for card in card_paths:
        text = _read(card, findings)
        label = card.relative_to(skill.parent.parent)
        state_match = re.search(r"^State:\s*`([^`]+)`\s*$", text, re.MULTILINE)
        if not state_match:
            findings.append(f"{label}: missing State header")
        elif card not in path_states:
            findings.append(f"{label}: State header {state_match.group(1)} has no dispatch row")
        elif state_match.group(1) != path_states[card]:
            findings.append(f"{label}: State header {state_match.group(1)} does not match dispatch row {path_states[card]}")
        for state in _state_writes(text):
            if state not in dispatch and state not in terminal and state not in {"report-delivered", "<blocked.entered_from>"}:
                findings.append(f"{label}: state write {state} has no dispatch row")
        outcomes = re.search(r"^## Outcomes[^\n]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        if not outcomes:
            findings.append(f"{label}: missing Outcomes section and default outcome")
        else:
            bullets = [line.strip() for line in outcomes.group(1).splitlines() if re.match(r"^-\s+", line)]
            if not bullets or not re.search(r"\bOtherwise\b", bullets[-1], re.IGNORECASE):
                findings.append(f"{label}: Outcomes last bullet must be the default outcome")
        for match in TR_ID.finditer(text):
            seen_ids[match.group(1)].add(card)
            id_counts[match.group(1)] += 1
    for transition_id, cards in sorted(seen_ids.items()):
        if len(cards) != 1 or id_counts[transition_id] != 1:
            findings.append(f"{transition_id}: must appear exactly once on exactly one card")
    for state, card in dispatch.items():
        if not (skill / card).is_file():
            continue
        if skill / card not in card_paths:
            findings.append(f"SKILL.md: dispatch target {card} is not a card in steps/")
    return card_paths


def _agent_names_on_card(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"`([^`]+)`", text):
        tail = text[match.end():match.end() + 24]
        name = match.group(1)
        if re.match(r"\s+(?:evidence\s+)?agent\b", tail, re.IGNORECASE) and re.fullmatch(r"[a-z][a-z0-9-]*", name):
            names.add(name)
    return names


def _check_agents(root: Path, cards: list[Path], findings: list[str]) -> None:
    named: set[str] = set()
    for card in cards:
        text = _read(card, findings)
        named.update(_agent_names_on_card(text))
    agent_files = sorted((root / "agents").glob("*.md"))
    shipped: set[str] = set()
    for path in agent_files:
        text = _read(path, findings)
        frontmatter = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.DOTALL)
        if frontmatter and re.search(r"\bmcp__[A-Za-z0-9_]+", frontmatter.group(1)):
            findings.append(f"{path.relative_to(root)}: agent frontmatter names an mcp__ tool")
        match = re.search(r"^name:\s*([^\s]+)\s*$", text, re.MULTILINE)
        name = match.group(1) if match else path.stem
        shipped.add(name)
        if name not in named:
            findings.append(f"{path.relative_to(root)}: agent {name} is not named on a card")
    for name in sorted(named - shipped):
        findings.append(f"agent {name} named on a card is missing from agents/")


def _markdown_references(root: Path, skill: Path, cards: list[Path], findings: list[str], strict: bool) -> None:
    shipped_markdown = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in BUILD_PATHS and name != ".git"]
        shipped_markdown.extend(
            Path(directory) / name
            for name in filenames
            if name.endswith(".md") and name not in BUILD_PATHS
        )
    shipped_markdown.sort()
    for source in shipped_markdown:
        if not source.is_file():
            continue
        text = _read(source, findings)
        label = source.relative_to(root)
        base = skill if source.is_relative_to(root / "skills") else root
        for line_number, line in enumerate(text.splitlines(), 1):
            candidates = set(PATH_TOKEN.findall(line))
            for match in re.finditer(r"\[[^]]*\]\(([^)]*)\)", line):
                target = match.group(1).strip().strip("<>").split()[0] if match.group(1).strip() else ""
                if target and not re.match(r"(?:[a-z][a-z0-9+.-]*:|#)", target, re.IGNORECASE):
                    candidates.add(target.split("#", 1)[0])
            for raw in sorted(candidates):
                raw = raw.rstrip(".,;:)")
                if raw == "execution-state.json":
                    continue
                plugin_root = raw.startswith("${CLAUDE_PLUGIN_ROOT}/")
                target = raw.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
                if plugin_root:
                    resolve_from = root
                else:
                    resolve_from = base
                resolved = (resolve_from / target).resolve()
                if resolved.is_file():
                    continue
                if resolved.is_relative_to(skill) and (
                    resolved.relative_to(skill).parts[0] in {"report", "work", "stories"}
                    or resolved.relative_to(skill) == Path("execution-state.json")
                ):
                    continue
                if not strict and source in cards and "scripts/" in target:
                    continue
                if not resolved.is_relative_to(root):
                    findings.append(f"{label}:{line_number}: dangling relative path {raw} resolves outside the package")
                else:
                    findings.append(f"{label}:{line_number}: dangling relative path {raw}")


def _manifest(root: Path, relative: str, findings: list[str]) -> dict | None:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        findings.append(f"{relative}: missing or invalid JSON")
        return None
    if not isinstance(value, dict):
        findings.append(f"{relative}: expected JSON object")
        return None
    return value


def _check_manifests(root: Path, findings: list[str]) -> None:
    claude = _manifest(root, ".claude-plugin/plugin.json", findings)
    codex = _manifest(root, ".codex-plugin/plugin.json", findings)
    for field in ("name", "version", "description"):
        if claude is not None and codex is not None and claude.get(field) != codex.get(field):
            findings.append(f"plugin manifest {field} mismatch")
    if claude is not None and codex is not None:
        for label, manifest in ((".claude-plugin/plugin.json", claude), (".codex-plugin/plugin.json", codex)):
            for field in ("name", "version", "description"):
                if not manifest.get(field):
                    findings.append(f"{label}: missing {field}")
    license_text = _read(root / "LICENSE", findings)
    license_lines = license_text.splitlines()
    while license_lines and not license_lines[0].strip():
        license_lines.pop(0)
    if len(license_lines) >= 2 and license_lines[0].strip() == "Apache License" and license_lines[1].strip() == "Version 2.0, January 2004":
        expected = "Apache-2.0"
    else:
        match = re.search(r"^SPDX-License-Identifier:\s*(\S+)\s*$", "\n".join(license_lines), re.MULTILINE)
        expected = match.group(1) if match else None
    if expected is None:
        findings.append("LICENSE: cannot determine license identifier")
    elif codex is not None and codex.get("license") != expected:
        findings.append(f".codex-plugin/plugin.json: license mismatch; LICENSE is {expected}")


def _check_blocked_causes(skill: Path, findings: list[str]) -> None:
    path = skill / "data" / "blocked-causes.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        findings.append(f"data/blocked-causes.csv: cannot read ({type(error).__name__})")
        return
    if not {"cause", "signal", "class", "runner_text", "fix"}.issubset(headers):
        findings.append("data/blocked-causes.csv: header must include cause, signal, class, runner_text and fix")
        return
    for line_number, row in enumerate(rows, 2):
        value = (row.get("class") or "").strip()
        if value not in TOOL_CLASSES:
            findings.append(f"data/blocked-causes.csv:{line_number}: class {value or '(empty)'} is invalid")


def _check_matrices(skill: Path, findings: list[str]) -> None:
    matrices = {
        "ooe-rules.csv": ("condition",),
        "relation-kinds.csv": ("metadata_type", "relation_kind", "mode"),
    }
    for filename, inputs in matrices.items():
        path = skill / "data" / filename
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = set(reader.fieldnames or [])
                rows = list(reader)
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            findings.append(f"data/{filename}: cannot read ({type(error).__name__})")
            continue
        output = {"status", "reason_text"} if filename == "ooe-rules.csv" else {"decided_by", "story", "report_text"}
        if not set(inputs).issubset(headers) or not output.issubset(headers):
            findings.append(f"data/{filename}: missing input or output column")
            continue
        seen = set()
        for line_number, row in enumerate(rows, 2):
            key = tuple((row.get(column) or "").strip() for column in inputs)
            if key in seen:
                findings.append(f"data/{filename}:{line_number}: duplicate input {key}")
            seen.add(key)
            if not any((row.get(column) or "").strip() for column in output):
                findings.append(f"data/{filename}:{line_number}: no output")


def _check_required_tools(root: Path, skill_text: str, findings: list[str]) -> None:
    readme = _read(root / "README.md", findings)
    readme_section = re.search(r"^## Tools it uses\s*\n(.*?)(?=^## |\Z)", readme, re.MULTILINE | re.DOTALL)
    run_section = re.search(r"^## How this playbook runs\s*\n(.*?)(?=^## |\Z)", skill_text, re.MULTILINE | re.DOTALL)
    first_step = re.search(r"^1\. (.*?)(?=^2\. |\Z)", run_section.group(1), re.MULTILINE | re.DOTALL) if run_section else None
    readme_tools = re.findall(r"^\s*- (`[^\n]+)", readme_section.group(1), re.MULTILINE) if readme_section else []
    skill_tools = re.findall(r"^\s*- (`[^\n]+)", first_step.group(1), re.MULTILINE) if first_step else []
    if not readme_tools or readme_tools != skill_tools:
        findings.append("README.md and SKILL.md step 1: required tool lists must be present and identical")


def lint_package(root: Path, strict: bool = False) -> list[str]:
    """Return one line per package finding."""
    root = root.resolve()
    skill = root / "skills" / "analyze-change-impact"
    findings: list[str] = []
    skill_text = _read(skill / "SKILL.md", findings)
    dispatch, terminal = _dispatch(skill, skill_text, findings)
    cards = _check_cards(skill, dispatch, terminal, findings)
    _check_agents(root, cards, findings)
    _markdown_references(root, skill, cards, findings, strict)
    _check_manifests(root, findings)
    _check_blocked_causes(skill, findings)
    _check_matrices(skill, findings)
    _check_required_tools(root, skill_text, findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="check for scripts referenced by cards that are built in parallel")
    args = parser.parse_args(argv)
    findings = lint_package(args.package, strict=args.strict)
    if findings:
        print("\n".join(findings))
        return 1
    print(f"lint clean: {args.package}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
