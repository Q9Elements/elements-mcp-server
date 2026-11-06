"""Build the bypass audit set from bundle and order-of-execution evidence."""

from __future__ import annotations

import sys
import argparse
import re
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, managed_validation_rule, metadata_type, read_csv, read_json, resolve_metadata_type, source_types_by_node, write_json
except ImportError:
    from dli_common import ContractError, managed_validation_rule, metadata_type, read_csv, read_json, resolve_metadata_type, source_types_by_node, write_json


NARRATION_ORIGIN = "named in the order-of-execution explanation; not in the Elements load analysis"


def automation_key(row: dict) -> tuple[str, str, str]:
    """Identify one automation within its object and metadata type."""
    return (row.get("target", ""), metadata_type(row.get("type", "")), row.get("apiName", ""))


def _same_automation(automation: dict, row: dict) -> bool:
    if automation.get("target") != row.get("target") or metadata_type(automation["type"]) != metadata_type(row["type"]):
        return False
    if automation.get("apiName"):
        return automation["apiName"] == row["apiName"]
    return automation["name"] in {row["apiName"], row.get("name", "")}


def matching_verdicts(automation: dict, verdicts: list[dict]) -> list[dict]:
    """Match supplied identity fields, retaining legacy unambiguous name-only rows."""
    return [row for row in verdicts if row.get("apiName") == automation.get("apiName")
            and (not row.get("target") or row["target"] == automation.get("target", ""))
            and (not row.get("type") or metadata_type(row["type"]) == metadata_type(automation.get("type", "")))]


def normalize_audit_set(rows: list[dict], source_manifest: dict) -> list[dict]:
    """Reconcile resolved aliases and freeze source-confirmed auditor identities."""
    source_types = source_types_by_node(source_manifest)
    source_names = {row["nodeId"]: row["apiName"] for row in source_manifest.get("files", [])
                    if row.get("nodeId") and row.get("apiName")}
    source_components = {row["nodeId"]: row for row in source_manifest.get("files", []) if row.get("nodeId")}
    unique = {}
    # Prefer the bundle identity while preserving narration evidence on the survivor.
    for original in sorted(rows, key=lambda row: row.get("origin") != "bundle"):
        row = dict(original, type=resolve_metadata_type(original, source_types))
        if row.get("nodeId") in source_names:
            row["apiName"] = source_names[row["nodeId"]]
        component = source_components.get(row.get("nodeId"), {})
        row.update({field: component[field] for field in ("namespace", "isManaged") if field in component})
        if managed_validation_rule(row):
            row["isManaged"] = True
        key = (row.get("target"), row["nodeId"]) if row.get("nodeId") else automation_key(row)
        survivor = unique.setdefault(key, row)
        if row.get("isManaged"):
            survivor["isManaged"] = True
        if original.get("origin") == "narration-only":
            survivor["narrationNames"] = list(dict.fromkeys(
                survivor.get("narrationNames", []) + [original.get("name") or original["apiName"]]))
            survivor["narrationEvidence"] = original.get("originEvidence", NARRATION_ORIGIN)
            for field in ("active", "activeEvidence", "nonFiring", "nonFiringEvidence"):
                if field in original:
                    survivor[field] = original[field]
    result = list(unique.values())
    if len({automation_key(row) for row in result}) != len(result):
        raise ContractError("resolved nodes have conflicting audit identities")
    return sorted(result, key=automation_key)


def verdicts_for_automations(automations: list[dict], verdicts: list[dict]) -> list[dict]:
    """Select verdicts for a subset without borrowing from another object or type."""
    return [row for row in verdicts if any(matching_verdicts(automation, [row])
                                         for automation in automations)]


def validate_shared_source_verdicts(audit_set: list[dict], verdicts: list[dict]) -> None:
    """A shared component has one hook assessment, with target-specific firing facts."""
    by_node = {}
    for automation in audit_set:
        if not automation.get("nodeId"):
            continue
        for verdict in matching_verdicts(automation, verdicts):
            hook = tuple(verdict.get(field, "") for field in ("verdict", "scope", "switch", "evidence"))
            if by_node.setdefault(automation["nodeId"], hook) != hook:
                raise ContractError("shared source component has conflicting bypass assessments")


def validate_verdicts(audit_set: list[dict], verdicts: list[dict]) -> None:
    """Require activation evidence before treating narration additions as firing."""
    expected = {automation_key(row) for row in audit_set}
    by_automation = {}
    for verdict in verdicts:
        matches = [row for row in audit_set if matching_verdicts(row, [verdict])]
        if len(matches) != 1 or automation_key(matches[0]) in by_automation:
            raise ContractError("audit set needs exactly one verdict per automation and no extra verdicts")
        by_automation[automation_key(matches[0])] = verdict
    if len(expected) != len(audit_set) or set(by_automation) != expected:
        raise ContractError("audit set needs exactly one verdict per automation and no extra verdicts")
    validate_shared_source_verdicts(audit_set, verdicts)
    for row in verdicts:
        if row.get("verdict") not in {"present", "absent", "unknown"} or not row.get("evidence", "").strip():
            raise ContractError("every bypass verdict needs a published value and evidence")
        if str(row.get("nonFiring", "")).lower() == "true" and not row.get("nonFiringEvidence", "").strip():
            raise ContractError("non-firing verdict needs evidence")
    for automation in audit_set:
        row = by_automation[automation_key(automation)]
        if automation.get("origin") == "bundle" and str(row.get("nonFiring", "")).lower() == "true":
            # Object declarations alone do not disprove a predicted cascade.
            evidence = unescape(row["nonFiringEvidence"]).strip().rstrip(".")
            object_only = re.fullmatch(
                r"(?:<object>\s*\w+\s*</object>\s+record-triggered start;\s*confirmed targets are [\w/,\s]+"
                r"|trigger\s+\w+\s+on\s+\w+\s*\([^)]*\)(?:;\s*targets are [\w/,\s]+)?)",
                evidence, re.I,
            )
            if object_only:
                raise ContractError("fire-chain non-firing needs source proof beyond a start-object or trigger-object declaration")
        if automation.get("origin") != "narration-only":
            continue
        active = str(row.get("active", "")).lower()
        non_firing = str(row.get("nonFiring", "")).lower()
        if active not in {"true", "false", "unknown"} or not row.get("activeEvidence", "").strip():
            raise ContractError("narration additions need an activation check with evidence")
        if active == "false" and (non_firing != "true" or not row.get("nonFiringEvidence", "").strip()):
            raise ContractError("inactive narration additions need non-firing evidence")
        if active == "unknown" and (row.get("verdict") != "unknown" or non_firing != ""):
            raise ContractError("unverified activation needs an unknown verdict and no firing claim")


def build_audit_set(bundle_directories: list[Path], narrations: list[dict], *,
                    managed_packages: dict | None = None, duplicate_rules: dict | None = None,
                    unpredicted_automations: list[dict] | None = None) -> list[dict]:
    rows = []
    for bundle in bundle_directories:
        automations = read_csv(bundle / "automations.csv")[1]
        response = read_json(bundle / "response.json")
        node_types = {
            node["nodeId"]: node["sfType"]
            for target in response.get("targets", [])
            for chain in target.get("fireChain", [])
            for entity in chain.get("digest", [])
            for variant in entity.get("variants", [])
            if (node := variant.get("firingAutomation")) and node.get("nodeId") and node.get("sfType")
        }
        automation_types_by_node = {row.get("nodeId"): row.get("type") for row in automations if row.get("nodeId")}
        automation_types_by_name = {row.get("apiName"): row.get("type") for row in automations if row.get("apiName")}
        email_by_node = {
            sender["nodeId"]: sender
            for target in response.get("targets", [])
            for sender in target.get("loadRisk", {}).get("emailSenders", [])
        }
        rows.extend(dict(row, origin="bundle", originEvidence="Elements load analysis")
                    for row in automations)
        for row in read_csv(bundle / "fire-chain-digest.csv")[1]:
            name = row.get("firingAutomation")
            if name and not any(item["apiName"] == name and item.get("target") == row["target"]
                                for item in rows):
                automation_type = (node_types.get(row.get("firingAutomationNodeId"))
                                   or automation_types_by_node.get(row.get("firingAutomationNodeId"))
                                   or automation_types_by_name.get(name)
                                   or email_by_node.get(row.get("firingAutomationNodeId"), {}).get("sfType", "Automation"))
                rows.append({"apiName": name, "name": name, "type": automation_type,
                             "target": row["target"], "nodeId": row.get("firingAutomationNodeId", ""),
                             "origin": "bundle", "originEvidence": "Elements load analysis"})
    for narration in narrations:
        if not isinstance(narration.get("automations"), list) or not narration.get("object"):
            raise ContractError("narration needs object and structured automations; regenerate with the narrator")
        for automation in narration["automations"]:
            if not isinstance(automation, dict) or any(
                not isinstance(automation.get(key), str) or not automation[key].strip()
                for key in ("name", "type")
            ):
                raise ContractError("narration automation needs a name and type")
            automation = {**automation, "target": narration["object"]}
            if any(_same_automation(automation, row) for row in rows):
                continue
            rows.append({**automation, "apiName": automation.get("apiName") or automation["name"],
                         "target": narration["object"], "origin": "narration-only",
                         "originEvidence": NARRATION_ORIGIN})
    for target, packages in (managed_packages or {}).items():
        for package in packages:
            rows.append({"target": target, "apiName": package["namespace"],
                         "name": package["namespace"], "type": "Managed Package",
                         "origin": "managed-package", "originEvidence": "Managed package lookup"})
    for target, names in (duplicate_rules or {}).items():
        rows.extend({"target": target, "apiName": name, "name": name, "type": "Duplicate Rule",
                     "origin": "duplicate-rule", "originEvidence": "Active duplicate rule lookup"}
                    for name in names)
    for observed in unpredicted_automations or []:
        rows.append({"target": "rehearsal", "apiName": observed["name"], "name": observed["name"],
                     "type": observed.get("type") or "Automation", "origin": "rehearsal",
                     "originEvidence": "Observed in rehearsal, not in the fire chain."})
    unique = {}
    for row in rows:
        row["type"] = metadata_type(row["type"])
        unique.setdefault(automation_key(row), row)
    return sorted(unique.values(), key=lambda row: (row["apiName"], row["type"], row["target"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="*", type=Path)
    parser.add_argument("--narration", nargs="+", action="extend", type=Path)
    parser.add_argument("--managed-packages", type=Path)
    parser.add_argument("--duplicate-rules", type=Path)
    parser.add_argument("--unpredicted-automations", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--audit-set", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--verdicts", type=Path)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.source_manifest:
            if not arguments.audit_set or not arguments.out or arguments.bundles or arguments.verdicts:
                raise ContractError("normalization requires --audit-set, --source-manifest and --out")
            rows = normalize_audit_set(read_json(arguments.audit_set), read_json(arguments.source_manifest))
            write_json(arguments.out, rows)
            print(f"normalized {len(rows)} audit automation(s)")
        elif arguments.audit_set or arguments.verdicts:
            if not arguments.audit_set or not arguments.verdicts or arguments.bundles:
                raise ContractError("validation requires --audit-set and --verdicts only")
            validate_verdicts(read_json(arguments.audit_set), read_csv(arguments.verdicts)[1])
            print("validated bypass verdict coverage and activation evidence")
        else:
            if not arguments.bundles or not arguments.narration or not arguments.out:
                raise ContractError("building requires bundles, --narration and --out")
            rows = build_audit_set(
                arguments.bundles, [read_json(path) for path in arguments.narration],
                managed_packages=read_json(arguments.managed_packages) if arguments.managed_packages else None,
                duplicate_rules=read_json(arguments.duplicate_rules) if arguments.duplicate_rules else None,
                unpredicted_automations=read_json(arguments.unpredicted_automations)
                if arguments.unpredicted_automations else None,
            )
            write_json(arguments.out, rows)
            print(f"wrote {len(rows)} audit automation(s); "
                  f"narration additions: {sum(row['origin'] == 'narration-only' for row in rows)}")
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        print("error: bypass audit inputs incomplete or invalid; check structured names and verdict evidence", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
