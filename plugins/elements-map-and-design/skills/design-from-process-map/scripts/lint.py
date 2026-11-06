"""Check the design-from-process-map package itself.

    python3 lint.py

Checks: every dispatch target exists and its card's State header matches; every
state a card writes is in the dispatch table; every card's Outcomes end with a
default ("Otherwise") outcome; every transition id is on exactly one card;
every relative link and every skill path a shipped file names resolves; every
agent a card names exists in the plugin's agents/; every script a card runs
exists; the data files are well formed; both plugin manifests agree on name,
version and description; and the Codex manifest's licence matches LICENSE.
Prints one line per finding and exits 1, or prints LINT CLEAN and exits 0.
Build material (_workspace/ and .playbook-build) is never read.
"""

import csv
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
AGENTS = ["process-quality-assessor", "data-model-deriver", "integration-deriver", "access-deriver",
          "solution-overview-writer"]


def dispatch_table(text):
    rows = {}
    for state, target in re.findall(r"^\| `([a-z-]+)` \| (.+?) \|$", text, re.M):
        link = re.search(r"\]\((steps/[^)]+)\)", target)
        rows[state] = link.group(1) if link else None
    return rows


def main():
    findings = []
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    table = dispatch_table(skill_md)
    if not table:
        findings.append("SKILL.md: no dispatch table found")
    terminal = [s for s, t in table.items() if t is None]
    if len(terminal) != 1:
        findings.append(f"SKILL.md: the dispatch table needs exactly one terminal row, has {len(terminal)}")
    transitions = {}
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
        for written in re.findall(r'"current_state": "([a-z-]+)"', text):
            if written not in table:
                findings.append(f"{target}: writes current_state '{written}', which is not in the dispatch table")
        for step in re.findall(r'"current_step": "(steps/[^"]+)"', text):
            if not (SKILL / step).exists():
                findings.append(f"{target}: names current_step {step}, which does not exist")
        for agent in re.findall(r"`([a-z]+(?:-[a-z]+)+)` agent", text):
            if not (PLUGIN / "agents" / f"{agent}.md").exists():
                findings.append(f"{target}: names agent {agent}, which is not in agents/")
        for script in re.findall(r'\$SKILL/scripts/([a-z_]+\.py)', text):
            if not (SKILL / "scripts" / script).exists():
                findings.append(f"{target}: runs scripts/{script}, which does not exist")
    for tr, cards in transitions.items():
        if len(cards) > 1:
            findings.append(f"{tr} appears on {len(cards)} cards: {', '.join(cards)}")
    shipped = [p for p in SKILL.rglob("*.md")] + [PLUGIN / "agents" / f"{a}.md" for a in AGENTS]
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
            base = PLUGIN if "<pluginRoot>/" + ref in text else SKILL
            if not (base / ref).exists() and not (PLUGIN / ref).exists() and not (SKILL / ref).exists():
                findings.append(f"{rel}: path {ref} does not exist")
        for ref in re.findall(r"`((?:steps|data|schemas|references|templates|scripts|assets)/[A-Za-z0-9_.-]+\.[a-z]+)`", text):
            if path.is_relative_to(SKILL) if hasattr(path, "is_relative_to") else str(path).startswith(str(SKILL)):
                if not (SKILL / ref).exists() and not (PLUGIN / ref).exists():
                    findings.append(f"{rel}: names {ref}, which does not exist")
    for name, columns in (("derivability-rubric.csv", ["rule_id", "checked_by", "applies_to", "weight", "threshold", "rule"]),
                          ("crud-verbs.csv", ["verb", "crud", "notes"]),
                          ("integration-evidence-types.csv", ["metadata_type", "shows", "direction"]),
                          ("solution-overview-sections.csv", ["order", "section_id", "title", "on", "content"])):
        with open(SKILL / "data" / name, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            rows = list(reader)
        if missing:
            findings.append(f"data/{name}: missing column(s) {', '.join(missing)}")
            continue
        key = columns[0]
        keys = [r[key] for r in rows]
        if len(keys) != len(set(keys)):
            findings.append(f"data/{name}: duplicate {key} values")
    rubric = list(csv.DictReader(open(SKILL / "data" / "derivability-rubric.csv", newline="", encoding="utf-8")))
    if sum(1 for r in rubric if r["checked_by"] == "score") != 1:
        findings.append("data/derivability-rubric.csv: needs exactly one pass mark row (checked_by score)")
    for r in csv.DictReader(open(SKILL / "data" / "crud-verbs.csv", newline="", encoding="utf-8")):
        if not re.fullmatch(r"C?R?U?D?", r["crud"]) or not r["crud"]:
            findings.append(f"data/crud-verbs.csv: '{r['verb']}' has crud '{r['crud']}'")
    for r in csv.DictReader(open(SKILL / "data" / "solution-overview-sections.csv", newline="", encoding="utf-8")):
        if r["on"] not in ("yes", "no"):
            findings.append(f"data/solution-overview-sections.csv: '{r['section_id']}' has on '{r['on']}'; use yes or no")
    claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    for field in ("name", "version", "description"):
        if claude.get(field) != codex.get(field):
            findings.append(f"manifests disagree on {field}")
    licence = (PLUGIN / "LICENSE").read_text(encoding="utf-8")[:200]
    if "Apache License" in licence and codex.get("license") != "Apache-2.0":
        findings.append(f"the Codex manifest's license is {codex.get('license')}, LICENSE is Apache-2.0")
    for line in findings:
        print(line)
    if findings:
        return 1
    print("LINT CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
