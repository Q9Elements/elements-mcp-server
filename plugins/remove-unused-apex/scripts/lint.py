#!/usr/bin/env python3
"""Pre-ship lint for the remove-unused-apex playbook.

Run after any edit to the package: python3 scripts/lint.py
Exit 0 clean, exit 1 with one line per finding.
"""
import csv
import json
import re
import sys
from pathlib import Path

from capacity_triage import ENTRY_POINT_CHANNELS

if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__)
    sys.exit(0)

PLUGIN = Path(__file__).resolve().parent.parent
SKILL = PLUGIN / "skills" / "remove-unused-apex"
TERMINAL = "removal-planned"
findings = []


def read(p):
    return p.read_text(encoding="utf-8")


def csv_rows(name):
    with open(SKILL / "data" / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# 1. Dispatch table: every target exists.
skill_md = read(SKILL / "SKILL.md")
dispatch = dict(re.findall(r"\| `([a-z-]+)` \| `(steps/[a-z0-9-]+\.md)` \|", skill_md))
for state, card in dispatch.items():
    if not (SKILL / card).is_file():
        findings.append(f"dispatch target missing: {state} -> {card}")
if TERMINAL not in skill_md:
    findings.append(f"terminal state {TERMINAL} not in SKILL.md")

# 2. Every card's State header owns exactly its dispatch row.
cards = sorted((SKILL / "steps").glob("*.md"))
for card_path in cards:
    text = read(card_path)
    m = re.search(r"^State: `([a-z-]+)`", text, re.M)
    if not m:
        findings.append(f"{card_path.name}: no 'State:' header")
        continue
    rel = f"steps/{card_path.name}"
    if dispatch.get(m.group(1)) != rel:
        findings.append(f"{card_path.name}: declares state {m.group(1)} but dispatch maps it to {dispatch.get(m.group(1))}")
    for section in ("## Purpose", "## Procedure", "## Outcomes", "## Failure"):
        if section not in text:
            findings.append(f"{card_path.name}: missing section {section}")

# 3. Every state a card writes is dispatchable or terminal; every write pairs state with step.
all_states = set(dispatch) | {TERMINAL}
for card_path in cards:
    text = read(card_path)
    for state, step in re.findall(r'\{"current_state": "([a-z-]+)", "current_step": (null|"steps/[a-z0-9-]+\.md")\}', text):
        if state not in all_states:
            findings.append(f"{card_path.name}: writes undispatchable state {state}")
        elif state == TERMINAL:
            if step != "null":
                findings.append(f"{card_path.name}: terminal write must set current_step null")
        elif dispatch[state] != step.strip('"'):
            findings.append(f"{card_path.name}: writes {state} with step {step}, dispatch says {dispatch[state]}")
    if re.search(r'"current_state": "[a-z-]+"\}', text):
        findings.append(f"{card_path.name}: current_state written without current_step")

# 4. No dangling relative reference in any shipped file; nothing escapes the plugin.
shipped = list(SKILL.rglob("*.md")) + list(SKILL.rglob("*.csv")) + list(SKILL.rglob("*.json")) + list((PLUGIN / "agents").glob("*.md"))
for f in shipped:
    text = read(f)
    for token in set(re.findall(r"(?<![A-Za-z0-9_/.-])(?:steps|data|references|templates)/[A-Za-z0-9._-]+\.(?:md|csv|json)", text)):
        if not (SKILL / token).is_file():
            findings.append(f"{f.relative_to(PLUGIN)}: dangling reference {token}")
    for token in set(re.findall(r"scripts/[A-Za-z0-9_]+\.py", text)):
        if not (PLUGIN / token).is_file():
            findings.append(f"{f.relative_to(PLUGIN)}: dangling script reference {token}")
    history_text = text
    if f == SKILL / "references" / "data-contracts.md":
        history_text = text.replace("HANDOFF decision 24", "").replace("HANDOFF decision 25", "")
    if re.search(r"\.\./_(notes|research|process)|_notes/|_research/|feature-gaps|HANDOFF|⟦GAP", history_text):
        findings.append(f"{f.relative_to(PLUGIN)}: reference outside the package or to build history")

# 5. Every transition id has exactly one owning card. Numeric gaps are intentional.
tr_owner = {}
for card_path in cards:
    for tr in re.findall(r"\*\*(TR-\d\d) ", read(card_path)):
        tr_owner.setdefault(tr, []).append(card_path.name)
for tr, owners in sorted(tr_owner.items()):
    if len(owners) != 1:
        findings.append(f"{tr}: on {len(owners)} cards ({owners})")

# 6. Agents: every agent named on at least one card; every card's bold agent name exists.
agents = {p.stem for p in (PLUGIN / "agents").glob("*.md")}
card_text = "\n".join(read(c) for c in cards)
for a in agents:
    if f"**{a}**" not in card_text:
        findings.append(f"agent {a} is named on no card")
for a in set(re.findall(r"\*\*([a-z]+(?:-[a-z]+)+)\*\* agent", card_text)):
    if a not in agents:
        findings.append(f"card names unknown agent {a}")
for a in agents:
    fm = read(PLUGIN / "agents" / f"{a}.md")
    if not re.search(r"^tools: ", fm, re.M):
        findings.append(f"agent {a}: no tools line")
    if "never write" not in fm:
        findings.append(f"agent {a}: missing the never-write contract line")

agent_tier_path = SKILL / "data" / "agent-tiers.csv"
with open(agent_tier_path, newline="", encoding="utf-8") as tier_handle:
    tier_reader = csv.DictReader(tier_handle)
    tier_fields = list(tier_reader.fieldnames or [])
    tier_rows = list(tier_reader)
expected_tier_fields = ["agent", "tier", "effort", "why"]
if tier_fields != expected_tier_fields:
    findings.append("agent-tiers.csv: header must be " + ",".join(expected_tier_fields))
tier_rows_by_agent = {}
for row in tier_rows:
    agent = row.get("agent", "")
    tier_rows_by_agent.setdefault(agent, []).append(row)
    if agent not in agents:
        findings.append(f"agent-tiers.csv: unknown agent {agent}")
    if row.get("tier") not in {"fast", "strong"}:
        findings.append(f"agent-tiers.csv: unknown tier {row.get('tier', '')}")
    if row.get("effort") not in {"medium", "high"}:
        findings.append(f"agent-tiers.csv: unknown effort {row.get('effort', '')}")
tier_model_values = {}
for agent in sorted(agents):
    rows = tier_rows_by_agent.get(agent, [])
    if not rows:
        findings.append(f"agent {agent} has no agent-tiers.csv row")
        continue
    if len(rows) != 1:
        findings.append(f"agent {agent} has {len(rows)} agent-tiers.csv rows")
        continue
    frontmatter = re.match(
        r"^---\n(.*?)\n---(?:\n|$)", read(PLUGIN / "agents" / f"{agent}.md"), re.S
    )
    model_values = re.findall(
        r"^model:\s*(\S+)\s*$", frontmatter.group(1) if frontmatter else "", re.M
    )
    if len(model_values) != 1:
        findings.append(f"agent {agent}: must carry exactly one model alias")
        continue
    tier_model_values.setdefault(rows[0]["tier"], []).append((agent, model_values[0]))
for tier, values in sorted(tier_model_values.items()):
    if len({value for _, value in values}) > 1:
        rendered_values = ", ".join(
            f"{agent}={value}" for agent, value in sorted(values)
        )
        findings.append(
            f"agent-tiers.csv: tier {tier} agents carry different model aliases "
            f"({rendered_values})"
        )
if {
    value for _, value in tier_model_values.get("fast", [])
} & {
    value for _, value in tier_model_values.get("strong", [])
}:
    findings.append("agent-tiers.csv: tiers fast and strong carry the same model alias")

# 7. State template: every dotted state field a card reads or writes exists in the template.
template = json.loads(read(SKILL / "templates" / "execution-state.json"))
def has_path(obj, path):
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return False
        obj = obj[part]
    return True
for required_path in (
    "capacity.target", "capacity.target.wording", "capacity.target.kind",
    "capacity.target.value", "capacity.target.requiredCharacters",
    "capacity.target.alreadyAtTarget",
):
    if not has_path(template, required_path):
        findings.append(f"execution-state.json: missing {required_path}")
if "charactersUsed" in template.get("capacity", {}):
    findings.append(
        "execution-state.json: optional capacity.charactersUsed must be omitted when unknown"
    )
blocks = [k for k, v in template.items() if isinstance(v, dict)]
optional_state_paths = {"capacity.charactersUsed"}
for card_path in cards:
    for ref in set(re.findall(r"`((?:%s)\.[A-Za-z_.]+)`" % "|".join(blocks), read(card_path))):
        if not has_path(template, ref) and ref not in optional_state_paths:
            findings.append(f"{card_path.name}: state field {ref} not in template")

# 8. Data matrices: closed vocabularies and complete coverage.
rules = csv_rows("counted-set-rules.csv")
orders = [int(r["order"]) for r in rules]
if orders != list(range(1, len(rules) + 1)):
    findings.append("counted-set-rules.csv: order column is not 1..N")
for r in rules:
    if r["result"] not in ("exempt", "counted"):
        findings.append(f"counted-set-rules.csv: unknown result {r['result']} on {r['rule']}")
    if r["result"] == "exempt" and r["counted_characters"] != "0":
        findings.append(f"counted-set-rules.csv: exempt rule {r['rule']} must count 0")

prec = csv_rows("event-resolution-precedence.csv")
if [int(r["order"]) for r in prec] != list(range(1, len(prec) + 1)):
    findings.append("event-resolution-precedence.csv: order is not 1..N")
if prec[-1]["method"] != "unmatched":
    findings.append("event-resolution-precedence.csv: last method must be unmatched")

verdict_path = SKILL / "data" / "verdicts.csv"
with open(verdict_path, newline="", encoding="utf-8") as verdict_handle:
    verdict_reader = csv.DictReader(verdict_handle)
    verdict_fields = list(verdict_reader.fieldnames or [])
    verdict_rows = list(verdict_reader)
expected_verdict_fields = [
    "order", "verdict", "rule", "confidence", "confidence_note", "removal_candidate",
]
if verdict_fields != expected_verdict_fields:
    findings.append(
        "verdicts.csv: header must be " + ",".join(expected_verdict_fields)
    )
for r in verdict_rows:
    if r.get("confidence") not in {"high", "medium"}:
        findings.append(
            "verdicts.csv: confidence must be high or medium on "
            + str(r.get("verdict", "<unknown>"))
        )
verdict_ids = {r["verdict"] for r in verdict_rows}
reason_ids = {r["reason"] for r in csv_rows("review-first-reasons.csv")}
for r in csv_rows("rescue-signals.csv"):
    if r["reason_written"] not in reason_ids:
        findings.append(f"rescue-signals.csv: writes unknown reason {r['reason_written']}")
for r in csv_rows("incoming-edge-reading.csv"):
    for reason in re.findall(r"reason ([a-z_]+)", r["routing"]):
        if reason not in reason_ids:
            findings.append(f"incoming-edge-reading.csv: unknown reason {reason}")
kinds = {r["kind"] for r in csv_rows("root-kinds.csv")}
for r in csv_rows("root-kinds.csv"):
    if not r["liveness_test"]:
        findings.append(f"root-kinds.csv: {r['kind']} has no liveness test")
    if r["externally_callable"] not in ("true", "false"):
        findings.append(f"root-kinds.csv: {r['kind']} externally_callable not boolean")
quiddity_rows = csv_rows("quiddity-codes.csv")
quiddity_methods = {r["method"] for r in prec} | {"anonymous_apex"}
for r in quiddity_rows:
    label = r["code"] or "<default>"
    if r["resolution_method"] not in quiddity_methods:
        findings.append(
            f"quiddity-codes.csv: {label} has unknown resolution_method {r['resolution_method']}"
        )
    if r["root_kind"] and r["root_kind"] not in kinds:
        findings.append(
            f"quiddity-codes.csv: {label} has unknown root_kind {r['root_kind']}"
        )
    if r["protects"] not in ("true", "false"):
        findings.append(f"quiddity-codes.csv: {label} protects not boolean")
contexts = {r["context"] for r in quiddity_rows}
if not contexts <= {"production", "test", "unknown"}:
    findings.append(f"quiddity-codes.csv: unknown context values {contexts}")
if not any(r["code"] == "" and r["context"] == "unknown" for r in quiddity_rows):
    findings.append("quiddity-codes.csv: no default row mapping unlisted codes to unknown")
blocked = csv_rows("blocked-reasons.csv")
recovery_card = read(SKILL / "steps" / Path(dispatch["blocked"]).name)
for r in blocked:
    if f"`{r['reason']}`" not in recovery_card:
        findings.append(f"blocked-reasons.csv: {r['reason']} has no recovery outcome on the blocked card")
for reason in set(re.findall(r'blocked\.reason: "([A-Z_]+)"', card_text)):
    if reason not in {r["reason"] for r in blocked}:
        findings.append(f"cards enter blocked with undefined reason {reason}")
caps = csv_rows("capabilities.csv")
for r in caps:
    if r["status"] not in ("shipped", "to be built", "partial"):
        findings.append(f"capabilities.csv: {r['id']} unknown status {r['status']}")
    if r["status"] != "shipped" and r["interim"].strip() in ("", "-"):
        findings.append(f"capabilities.csv: {r['id']} not shipped but no interim route")
for r in csv_rows("thresholds.csv"):
    if not (SKILL / r["used_by"]).is_file():
        findings.append(f"thresholds.csv: {r['id']} used_by {r['used_by']} missing")
    refs_text = "\n".join(read(x) for x in (SKILL / "references").glob("*.md"))
    if f"{r['id']}" not in card_text and r["id"] not in refs_text:
        findings.append(f"thresholds.csv: {r['id']} referenced by no card or reference")
thresholds_by_id = {r["id"]: r for r in csv_rows("thresholds.csv")}
if thresholds_by_id.get("T-13", {}).get("value") != "1":
    findings.append("thresholds.csv: T-13 must require one distinct daily log date")
for r in csv_rows("quarantine-rules.csv"):
    if r["story_kind"] not in ("needs-rewrite", "precursor-rewrite"):
        findings.append(f"quarantine-rules.csv: {r['rule']} unknown story_kind")

# 9. plugin.json version matches the template.
plugin = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json"))
if plugin["version"] != template["engagement"]["playbook_version"]:
    findings.append("plugin.json version differs from templates/execution-state.json playbook_version")

# 10. Every card states whether it stops or dispatches immediately.
for card_path in cards:
    if not re.search(r"\bstop rule\b", read(card_path), re.I):
        findings.append(f"{card_path.name}: stop rule is not stated")

# 11. Card 03 uses the shipped telemetry-gap mapping table.
reasoning_card = SKILL / "steps" / "03-reason-candidates.md"
mapping_reference = "data/telemetry-gap-mapping.csv"
if mapping_reference not in read(reasoning_card):
    findings.append(f"{reasoning_card.name}: does not reference {mapping_reference}")
with open(SKILL / mapping_reference, newline="", encoding="utf-8") as fh:
    mapping_reader = csv.DictReader(fh)
    mapping_rows = list(mapping_reader)
if mapping_reader.fieldnames != ["source", "eventTypes"]:
    findings.append("telemetry-gap-mapping.csv: header must be source,eventTypes")
else:
    server_event_types = {
        "ApexExecution", "QueuedExecution", "ApexRestApi", "ApexSoap", "InvocableAction",
        "ApexTrigger", "AuraRequest", "FlowExecution", "VisualforceRequest",
    }
    mapping_sources = set()
    for line_number, r in enumerate(mapping_rows, start=2):
        if None in r:
            findings.append(f"telemetry-gap-mapping.csv: row {line_number} has extra columns")
        if r["source"] is None or r["eventTypes"] is None:
            findings.append(f"telemetry-gap-mapping.csv: row {line_number} is missing a column")
            continue
        for event_type in r["eventTypes"].split(";"):
            if event_type not in server_event_types:
                findings.append(
                    f"telemetry-gap-mapping.csv: {r['source']} has unknown event type {event_type}"
                )
        if r["source"] in mapping_sources:
            findings.append(f"telemetry-gap-mapping.csv: {r['source']} is listed more than once")
        mapping_sources.add(r["source"])
    for channel in ENTRY_POINT_CHANNELS:
        if f"entry:{channel}" not in mapping_sources:
            findings.append(f"telemetry-gap-mapping.csv: entry:{channel} is missing")

# 12. Human-facing shipped text contains no em dash outside structural exemptions.
em_dash = chr(0x2014)
text_suffixes = {".csv", ".html", ".json", ".md", ".py"}
dash_files = [
    path
    for directory in (SKILL, PLUGIN / "agents")
    for path in directory.rglob("*")
    if path.is_file() and path.suffix in text_suffixes
]
dash_files += list((PLUGIN / "scripts").glob("*.py"))
dash_files += list((PLUGIN / "scripts").glob("*.html"))
for path in sorted(set(dash_files)):
    for line_number, line in enumerate(read(path).splitlines(), start=1):
        checked = line
        if re.search(r"\*\*TR-\d\d " + em_dash + r" ", checked):
            checked = re.sub(r"(\*\*TR-\d\d) " + em_dash, r"\1", checked)
        if path == PLUGIN / "scripts" / "review_page_template.html":
            checked = checked.replace(f"{em_dash} rule {em_dash}", "")
        if em_dash in checked:
            findings.append(f"{path.relative_to(PLUGIN)}:{line_number}: em dash is not allowed")

# 13. Host presentation tools do not appear in shipped playbook text.
presentation_files = [
    path
    for path in [*SKILL.rglob("*"), *(PLUGIN / "agents").rglob("*")]
    if path.is_file()
    and path != SKILL / "data" / "capabilities.csv"
]
for path in presentation_files:
    text = re.sub(r"\s+", " ", read(path).lower())
    if re.search(r"\btodowrite\b|\bartifact tool\b", text):
        findings.append(f"{path.relative_to(PLUGIN)}: names a host presentation tool")

# 14. Disposition notes contain only words supplied by the reviewer.
for path in [*cards, *(SKILL / "references").glob("*.md")]:
    if re.search(r"\bnote it in the disposition\b", read(path), re.I):
        findings.append(
            f"{path.relative_to(PLUGIN)}: disposition note must contain only "
            "the reviewer's text"
        )

# 15. The held-days rule is 29; stale comparison prose cannot ship.
for path in [*cards, *(SKILL / "references").glob("*.md"), *(PLUGIN / "agents").glob("*.md")]:
    if re.search(r"\b(?:fewer than 30|at least 30)\b", read(path), re.I):
        findings.append(
            f"{path.relative_to(PLUGIN)}: stale 30-day comparison wording"
        )

# 16. Customer-facing test-coverage language is confined to the two contract references.
coverage_allowed = {
    SKILL / "references" / "data-contracts.md",
    SKILL / "references" / "method-notes.md",
}
for path in [*SKILL.rglob("*"), *(PLUGIN / "agents").rglob("*")]:
    if (
        path.is_file()
        and path not in coverage_allowed
        and re.search(r"coverage", read(path), re.I)
    ):
        findings.append(
            f"{path.relative_to(PLUGIN)}: coverage wording is limited to "
            "references/data-contracts.md and references/method-notes.md"
        )

if findings:
    print("\n".join(findings))
    sys.exit(1)
print(
    f"lint clean: {len(dispatch)} dispatch rows, {len(tr_owner)} transitions, "
    f"{len(agents)} agents, {len(caps)} capabilities, "
    f"{len(quiddity_rows)} quiddity rows, {len(kinds)} root kinds"
)
