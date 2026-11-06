"""Check the compare-design-to-implementation package itself.

    python3 lint.py

Checks: every dispatch target exists and its card's State header matches; every state a card writes is in the
dispatch table; every card's Outcomes end with a default ("Otherwise") outcome; every transition id is on exactly one
card; every relative link and every package path a shipped file names resolves; every agent a card names exists in
the plugin's agents/; every script a card runs exists; the data files load and hold no duplicate keys; the
execution-state template holds every field the cards write; both plugin manifests agree on name, version and
description; and the Codex manifest's licence matches LICENSE. Prints one line per finding and exits 1, or prints
LINT CLEAN and exits 0. Build material (_workspace/ and .playbook-build) is never read.
"""

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
AGENTS = ["metadata-matcher", "implementation-assessor"]
sys.path.insert(0, str(SKILL / "scripts"))


def dispatch_table(text):
    rows = {}
    for state, target in re.findall(r"^\| `([a-z-]+)` \| (.+?) \|$", text, re.M):
        link = re.search(r"\]\((steps/[^)]+)\)", target)
        rows[state] = link.group(1) if link else None
    return rows


def check_cards(findings):
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    table = dispatch_table(skill_md)
    if not table:
        findings.append("SKILL.md: no dispatch table found")
    terminal = [s for s, t in table.items() if t is None]
    if len(terminal) != 1:
        findings.append(f"SKILL.md: the dispatch table needs exactly one terminal row, has {len(terminal)}")
    transitions, written = {}, set()
    for state, target in table.items():
        if target is None:
            continue
        card = SKILL / target
        if not card.exists():
            findings.append(f"SKILL.md: dispatch target {target} does not exist")
            continue
        text = card.read_text(encoding="utf-8")
        header = re.search(r"^State: `([a-z-]+)`", text, re.M)
        if not header or header.group(1) != state:
            findings.append(f"{target}: State header is {header.group(1) if header else 'missing'}, the table says {state}")
        outcomes = re.search(r"^## Outcomes.*?$(.*?)^## ", text, re.M | re.S)
        if not outcomes:
            findings.append(f"{target}: no Outcomes section")
        else:
            bullets = re.findall(r"^- \*\*(TR-\d+) — (.+?)\*\*", outcomes.group(1), re.M)
            if not bullets:
                findings.append(f"{target}: Outcomes has no transitions")
            elif not bullets[-1][1].startswith("Otherwise"):
                findings.append(f"{target}: the last outcome ({bullets[-1][0]}) is not the default 'Otherwise'")
            for tr, _ in bullets:
                transitions.setdefault(tr, []).append(target)
        if not re.search(r"^## Failure", text, re.M):
            findings.append(f"{target}: no Failure section")
        for value in re.findall(r'"current_state": "([a-z-]+)"', text):
            written.add(value)
            if value not in table:
                findings.append(f"{target}: writes current_state '{value}', which is not in the dispatch table")
        for step in re.findall(r'"current_step": "(steps/[^"]+)"', text):
            if not (SKILL / step).exists():
                findings.append(f"{target}: names current_step {step}, which does not exist")
        for agent in re.findall(r"`([a-z]+(?:-[a-z]+)+)` agent", text):
            if not (PLUGIN / "agents" / f"{agent}.md").exists():
                findings.append(f"{target}: names agent {agent}, which is not in agents/")
        for script in re.findall(r'\$SKILL/scripts/([a-z_]+\.py)', text):
            if not (SKILL / "scripts" / script).exists():
                findings.append(f"{target}: runs scripts/{script}, which does not exist")
        for script in re.findall(r'\$PLUGIN/scripts/([a-z_]+\.py)', text):
            if not (PLUGIN / "scripts" / script).exists():
                findings.append(f"{target}: runs the plugin's scripts/{script}, which does not exist")
    for state in table:
        if state not in written and state != "not-started":
            findings.append(f"SKILL.md: no card writes the state '{state}'")
    for tr, cards in transitions.items():
        if len(cards) > 1:
            findings.append(f"{tr} appears on {len(cards)} cards: {', '.join(cards)}")
    return table


def check_links(findings):
    shipped = list(SKILL.rglob("*.md")) + [PLUGIN / "agents" / f"{a}.md" for a in AGENTS]
    for path in shipped:
        if not path.exists():
            findings.append(f"agents/{path.name} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(PLUGIN)
        for link in re.findall(r"\]\(([^)#\s]+)\)", text):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / link).resolve().exists():
                findings.append(f"{rel}: link {link} does not resolve")
        for ref in re.findall(r"<(?:pluginRoot|skill)>/([A-Za-z0-9_./-]+)", text):
            if not (PLUGIN / ref).exists() and not (SKILL / ref).exists():
                findings.append(f"{rel}: path {ref} does not exist")
        if str(path).startswith(str(SKILL)):
            for ref in re.findall(r"`((?:steps|data|schemas|references|templates|scripts)/[A-Za-z0-9_.-]+\.[a-z]+)`", text):
                if not (SKILL / ref).exists() and not (PLUGIN / ref).exists():
                    findings.append(f"{rel}: names {ref}, which does not exist")


def check_data(findings):
    import common
    try:
        common.load_verdicts()
        common.load_rollup()
        common.load_link_types()
        common.load_limits()
    except common.SetupError as exc:
        findings.append(f"data: {exc}")
        return
    for name in ("matches.schema.json", "assessment.schema.json"):
        try:
            schema = common.load_json(SKILL / "schemas" / name)
            common.validate.check_schema_keywords(schema, "#")
        except common.SetupError as exc:
            findings.append(f"schemas/{name}: {exc}")


def check_template(findings):
    template = json.loads((SKILL / "templates" / "execution-state.json").read_text(encoding="utf-8"))
    for card in sorted((SKILL / "steps").glob("*.md")):
        text = card.read_text(encoding="utf-8")
        for dotted in set(re.findall(r"`((?:slots|match|checks|deliverables|blocked|engagement)\.(?!py\b)[a-z_]+)`", text)):
            node = template
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    findings.append(f"steps/{card.name}: names {dotted}, which templates/execution-state.json does not hold")
                    break
                node = node[part]


def check_manifests(findings):
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    for field in ("name", "version", "description"):
        if claude.get(field) != codex.get(field):
            findings.append(f"manifests disagree on {field}")
    licence = (PLUGIN / "LICENSE").read_text(encoding="utf-8")[:200]
    if "Apache License" in licence and codex.get("license") != "Apache-2.0":
        findings.append(f"the Codex manifest's license is {codex.get('license')}, LICENSE is Apache-2.0")


def main():
    findings = []
    check_cards(findings)
    check_links(findings)
    check_data(findings)
    check_template(findings)
    check_manifests(findings)
    for line in findings:
        print(line)
    if findings:
        return 1
    print("LINT CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
