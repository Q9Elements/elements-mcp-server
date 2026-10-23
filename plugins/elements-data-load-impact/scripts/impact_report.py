"""Render a customer-facing impact report from complete tool bundles and local residue."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, bundle_node_names, fires_for_operation, read_csv, read_json, render_element_ids
except ImportError:
    from dli_common import ContractError, bundle_node_names, fires_for_operation, read_csv, read_json, render_element_ids


BUNDLE_FILES = {
    "fire-chain-digest.csv", "alternatives.csv", "automations.csv", "lock-rows.csv",
    "fan-in.csv", "receipts.csv", "targets.json", "coverage.json", "rule-catalog.json",
    "rules-data.json", "response.json",
}


def _narrative_lines(content: str | dict) -> list[str]:
    if not isinstance(content, dict):
        return [content, ""]
    lines = []
    for fact in content.get("toolFacts", []):
        fact = " ".join(fact.split())
        if re.match(r"source\s*:", fact, re.I):
            continue
        phase = re.match(r"(beforeSave|afterSave|risks|dataMigration)(\.\w+)*\s*:\s*(.*)", fact)
        value = phase[3] if phase else fact
        if not value or value.casefold().rstrip(".") == "not found":
            continue
        if phase:
            label = {"beforeSave": "Before save", "afterSave": "After save",
                     "risks": "Risks", "dataMigration": "Data migration"}[phase[1]]
            if phase[2]:
                detail = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", phase[2][1:]).lower()
                detail = re.sub(r"\bui\b", "user interface", detail)
                detail = re.sub(r"\bapex\b", "Apex", detail)
                label += f", {detail}"
            fact = f"{label}: {value}"
        lines.append(f"- {fact}")
    explanation = content.get("explanation", "")
    if explanation:
        if lines:
            lines.append("")
        lines.append(explanation)
    return [*lines, ""]


def _require_bundle(directory: Path) -> None:
    missing = sorted(name for name in BUNDLE_FILES if not (directory / name).is_file())
    if missing:
        raise ContractError(f"bundle {directory} is missing: {', '.join(missing)}")


def _branch_status(target: dict, branch: str) -> str:
    match = next((item for item in target.get("fireChain", []) if item.get("branch") == branch), None)
    return "complete" if match and match.get("coverage", {}).get("absenceIsEvidence") is True else "incomplete"


def _rule_display(rule_id: str, catalog: dict[str, dict]) -> str:
    if rule_id not in catalog:
        return rule_id
    explicit = catalog[rule_id].get("displayLabel")
    if explicit:
        return explicit
    words = re.sub(r"^SF_LOCK_|_V\d+$", "", rule_id).lower().split("_")
    label = " ".join(words).replace("rollup", "roll-up")
    return f"{label.capitalize()} lock"


def _lock_phrase(consequence: str, entity: str) -> str:
    if consequence == "locked":
        return f"locks `{entity}`"
    if consequence == "conditional":
        return f"may lock `{entity}`"
    if consequence == "not_locked":
        return f"does not lock `{entity}`"
    return f"has an unknown lock effect on `{entity}`"


def _digest_line(row: dict[str, str], catalog: dict[str, dict]) -> str:
    consequence = _lock_phrase(row.get("lockConsequence", ""), row.get("entityApiName", ""))
    automation = row.get("firingAutomation", "")
    if automation:
        return (
            f"`{automation}` reaches `{row.get('entityApiName', '')}` at depth {row.get('minDepth', '')} "
            f"and {consequence}."
        )
    mechanism = row.get("mechanism", "unknown").replace("_", " ").replace("rollup", "roll-up").capitalize()
    relationship = row.get("relationshipField") or "unknown relationship"
    rule_labels = [
        _rule_display(rule_id, catalog)
        for rule_id in row.get("ruleIds", "").split()
    ]
    rules = f" ({'; '.join(rule_labels)})" if rule_labels else ""
    return f"{mechanism} through `{relationship}` {consequence}{rules}."


def _counted_lines(lines: list[str]) -> list[str]:
    counts = Counter(lines)
    result = []
    for line in dict.fromkeys(lines):
        if counts[line] > 1:
            line = f"{line[:-1]} ({counts[line]} occurrences)."
        result.append(f"- {line}")
    return result


def render_report(
    bundle_directories: list[Path], residue: dict | None = None,
    unpredicted_automations: list[dict] | None = None,
    duplicate_rules: dict[str, list[str]] | None = None,
    managed_packages: dict | None = None,
    narrations: list[dict] | None = None,
    non_firing_automations: set[str] | None = None,
) -> str:
    if duplicate_rules is not None and (
        not isinstance(duplicate_rules, dict)
        or any(not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names)
               for names in duplicate_rules.values())
    ):
        raise ContractError("duplicate rules must map objects to rule-name arrays")
    residue_by_target = {
        (row.get("object"), row.get("operation")): row
        for row in (residue or {}).get("targets", [])
    }
    if managed_packages is not None and not isinstance(managed_packages, dict):
        raise ContractError("managed packages must be grouped by target object")
    narration_by_object = {}
    for row in narrations or []:
        narration_by_object.setdefault(row["object"], []).append(row)
    rendered_objects = set()
    names_by_id = bundle_node_names(bundle_directories)
    lines = [
        "# Data-load impact report",
        "",
        "This report covers the planned Application Programming Interface (API) load using org metadata and local aggregate evidence.",
        "",
    ]
    if unpredicted_automations:
        lines.extend(["## Rehearsal coverage residue", ""])
        for automation in sorted(
            unpredicted_automations, key=lambda row: (row.get("name", ""), row.get("type", ""))
        ):
            name = automation.get("name")
            if not name:
                raise ContractError("unpredicted rehearsal automation is missing a name")
            automation_type = automation.get("type") or "unknown type"
            lines.append(
                f"- `{name}` ({automation_type}) was observed in rehearsal, not in the fire chain."
            )
        lines.append("")
    for directory in bundle_directories:
        _require_bundle(directory)
        response = read_json(directory / "response.json")
        coverage = read_json(directory / "coverage.json")
        rule_catalog = {
            row["id"]: row for row in read_json(directory / "rule-catalog.json")
        }
        _, digest = read_csv(directory / "fire-chain-digest.csv")
        _, locks = read_csv(directory / "lock-rows.csv")
        _, automations = read_csv(directory / "automations.csv")
        _, receipts = read_csv(directory / "receipts.csv")
        for target in response.get("targets", []):
            object_name = target["object"]
            rendered_objects.add(object_name)
            local = residue_by_target.get((object_name, target.get("operation")), {})
            lines.extend([f"## {object_name}", ""])
            lines.append(f"Operation: {target['operation']}; estimated rows: {target['estimatedVolume']:,}.")
            upsert = local.get("upsert")
            if upsert:
                insert_percent = round(upsert["insertShare"] * 100)
                lines.append(
                    f"Local upsert estimate: {insert_percent}% insert and {100 - insert_percent}% update, matched by `{upsert['matchField']}`."
                )
            threshold = response.get("skewThreshold", {})
            source = threshold.get("source", "unknown")
            source_text = "server default" if source == "default" else "server-provided value"
            lines.append(f"Skew threshold: {source_text} of {threshold.get('value', 10000):,} rows per parent.")
            lines.extend(["", "### Coverage", ""])
            branches = target.get("fireChain", [])
            for branch in ("insert", "update", "delete"):
                if any(item.get("branch") == branch for item in branches):
                    lines.append(f"- {branch.title()} branch: {_branch_status(target, branch)}")
            unresolved = local.get("unresolved", [])
            unresolved_types = [
                row
                for row in local.get("relationshipColumns", [])
                if row.get("unresolvedTypeDistribution")
            ]
            server_complete = coverage.get("absenceIsEvidence") is True
            lines.append(f"- Server bundle absence is evidence: {'yes' if server_complete else 'no'}")
            local_complete = not unresolved and not unresolved_types
            lines.append(f"- Overall absence is evidence: {'yes' if server_complete and local_complete else 'no'}")
            if duplicate_rules is not None:
                lines.extend(["", "### Active duplicate rules", ""])
                names = duplicate_rules.get(object_name, [])
                lines.extend(f"- `{name}`" for name in names)
                if not names:
                    lines.append("- None listed for this target object.")
            if managed_packages is not None:
                lines.extend(["", "### Managed packages on the target", ""])
                packages = managed_packages.get(object_name, [])
                for package in packages:
                    triggers = ", ".join(f"`{name}`" for name in package["triggers"])
                    lines.append(f"- `{package['namespace']}`: {triggers}.")
                if not packages:
                    lines.append("- None found in the metadata lookup.")
            firing = [row for row in automations if row.get("target") == object_name
                      and row.get("apiName") not in (non_firing_automations or set())
                      and fires_for_operation(row, target["operation"])]
            if firing:
                lines.extend(["", "### Automations that fire", ""])
                for row in firing:
                    unknown = "; trigger events unknown" if row.get("kind") == "directAutomation" and not row.get("triggerEvents") else ""
                    lines.append(f"- `{row['apiName']}` ({row['type']}; {row['kind']}{unknown}).")
            unnamed_managed = []
            for receipt in receipts:
                if receipt.get("target") != object_name or receipt.get("code") != "automation_managed_excluded":
                    continue
                try:
                    detail = json.loads(receipt.get("detail") or "{}")
                except ValueError:
                    detail = {}
                qualified = detail.get("apiName") or detail.get("name") or ""
                if not (detail.get("namespace") or "." in qualified):
                    unnamed_managed.append(receipt)
            if unnamed_managed and not managed_packages:
                lines.append("- Managed code has no package namespace in the bundle. The rehearsal tracks managed packages from debug-log namespace entries and flags any unplanned package for review.")
            lines.extend(["", "### Fire chain and lock effects", ""])
            target_digest = [row for row in digest if row.get("target") == object_name]
            if target_digest:
                lines.extend(_counted_lines([
                    _digest_line(row, rule_catalog) for row in target_digest
                ]))
            else:
                lines.append("- No fire-chain rows were returned.")
            for row in locks:
                if row.get("target") == object_name:
                    lines.append(
                        f"- `{row['column']}` carries {row['consequence']} lock evidence under rule `{row['ruleId']}`."
                    )
            load_risk = target.get("loadRisk", {})
            risk_lines = []
            parents = load_risk.get("volume", {}).get("parents", [])
            for parent in parents:
                fact = parent.get("recordCount", {})
                value = f"{fact.get('value'):,} records" if fact.get("status") == "available" else "count unavailable"
                risk_lines.append(f"- Parent volume, {parent['object']}: {value}.")
            for sender in load_risk.get("emailSenders", []):
                risk_lines.append(f"- Email sender: `{sender['apiName']}` ({sender['sfType']}).")
            for gated in load_risk.get("gatedColumns", []):
                risk_lines.append(
                    f"- Gated relationship column: `{gated['column']}` on the {gated['branch']} branch ({gated['reason']})."
                )
            if risk_lines:
                lines.extend(["", "### Response-only risk evidence", "", *risk_lines])
            if narration_by_object.get(object_name):
                lines.extend(["", "### Order of execution", ""])
                for narration in narration_by_object[object_name]:
                    lines.extend(_narrative_lines(narration.get("narrative", "")))
            if unresolved or unresolved_types:
                lines.extend(["", "### Local coverage residue", ""])
                for row in unresolved:
                    lines.append(f"- Coverage is incomplete for `{row['column']}` ({row['reason']}).")
                    lines.extend(["", "```sql", row["soql"], "```"])
                for row in unresolved_types:
                    lines.append(f"- Coverage is incomplete for `{row['column']}` (unresolved type prefix).")
            lines.append("")
    for object_name, object_narrations in sorted(narration_by_object.items()):
        if object_name in rendered_objects:
            continue
        lines.extend([f"## Related object: {object_name}", "", "### Order of execution", ""])
        for narration in object_narrations:
            lines.extend(_narrative_lines(narration.get("narrative", "")))
        lines.append("")
    rendered = "\n".join(lines).rstrip() + "\n"
    rendered = re.sub(r"[ \t]*" + chr(0x2014) + r"[ \t]*", ", ", rendered)
    return render_element_ids(rendered, names_by_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--residue", type=Path)
    parser.add_argument("--unpredicted-automations", type=Path)
    parser.add_argument("--duplicate-rules", type=Path)
    parser.add_argument("--managed-packages", type=Path)
    parser.add_argument("--narration", nargs="+", action="extend", type=Path)
    parser.add_argument("--bypass-verdicts", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        report = render_report(
            arguments.bundles,
            read_json(arguments.residue) if arguments.residue else None,
            read_json(arguments.unpredicted_automations)
            if arguments.unpredicted_automations else None,
            read_json(arguments.duplicate_rules) if arguments.duplicate_rules else None,
            read_json(arguments.managed_packages) if arguments.managed_packages else None,
            [read_json(path) for path in arguments.narration] if arguments.narration else None,
            {row["apiName"] for row in read_csv(arguments.bypass_verdicts)[1]
             if row.get("nonFiring", "").strip().lower() == "true"} if arguments.bypass_verdicts else None,
        )
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(report, encoding="utf-8")
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"wrote impact report for {len(arguments.bundles)} bundle(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
