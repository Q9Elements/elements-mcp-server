#!/usr/bin/env python3
"""Select dependency-complete Apex packages until a capacity target is covered."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from apex_common import (
    ContractError,
    attached_tests,
    cli_guard,
    default_data_dir,
    parse_bool,
    parse_int,
    outside_apex_callers,
    is_self_match,
    outside_string_holders,
    qualified_name,
    read_csv,
    read_json_array,
    read_json_object,
    type_key,
    write_csv,
    write_json,
)


def required_characters(
    kind: str,
    value: int | float,
    allocation: int,
    characters_used: int | None,
) -> int:
    """Normalize a customer capacity target to an integer reclaim requirement."""
    try:
        exact_value = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ContractError("capacity target value must be a finite number") from None
    if kind == "free_percent":
        scaled = allocation * exact_value
        reclaim = -(-scaled.numerator // (scaled.denominator * 100))
    elif kind == "target_percent":
        if characters_used is None:
            raise ContractError(
                "a target usage percentage requires the exact current character count"
            )
        scaled = allocation * exact_value
        reclaim = characters_used - scaled.numerator // (scaled.denominator * 100)
    elif kind == "characters":
        reclaim = -(-exact_value.numerator // exact_value.denominator)
    else:
        raise ContractError(f"unknown capacity target kind: {kind}")
    return max(0, reclaim)


def normalize_target(
    target: dict[str, object],
    *,
    allocation: int,
    characters_used: int | None,
) -> dict[str, object]:
    """Return the persisted capacity target shape used by the engagement state."""
    for field in ("wording", "kind", "value"):
        if field not in target:
            raise ContractError(f"capacity target is missing {field}")
    kind = str(target["kind"])
    value = target["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("capacity target value must be a number")
    required = required_characters(kind, value, allocation, characters_used)
    return {
        "wording": str(target["wording"]),
        "kind": kind,
        "value": value,
        "requiredCharacters": required,
        "alreadyAtTarget": required == 0,
    }


def selection_outcome(
    *,
    required: int,
    reclaimed: int,
) -> str:
    """Classify selection after every eligible package has been considered."""
    if reclaimed >= required:
        return "target_covered"
    return "candidates_exhausted"




def is_test_only(row: dict[str, str]) -> bool:
    """Return whether the candidate is called only by one or more test classes."""
    name = row.get("qualifiedName", "candidate")
    return (
        not parse_bool(row.get("isTestClass", ""), field=f"{name} isTestClass")
        and (parse_int(row.get("incomingFromTest", ""), field=f"{name} incomingFromTest") or 0) >= 1
        and all(
            (parse_int(row.get(field, ""), field=f"{name} {field}") or 0) == 0
            for field in ("incomingFromP", "incomingFromCandidates", "incomingFromOther")
        )
    )


ENTRY_POINT_INTERFACE_CHANNELS = ("Invocable", "Batchable", "Queueable", "Schedulable")
ENTRY_POINT_CHANNELS = ("scheduled", "REST", "SOAP", *ENTRY_POINT_INTERFACE_CHANNELS)
# Each text channel is signalled when any of its patterns matches the class's name or summary.
ENTRY_POINT_TEXT_SIGNALS = {
    "REST": (
        re.compile(r"\bREST\b", re.IGNORECASE),
        re.compile(r"(?:Rest|REST)(?=[A-Z_]|$)"),
    ),
    "SOAP": (
        re.compile(r"\bSOAP\b", re.IGNORECASE),
        re.compile(r"(?:Soap|SOAP)(?=[A-Z_]|$)"),
    ),
    **{
        channel: (re.compile(channel, re.IGNORECASE),)
        for channel in ENTRY_POINT_INTERFACE_CHANNELS
    },
}


def entry_point_channels(
    row: dict[str, str], schedule_liveness_names: set[str]
) -> list[str]:
    """Return the externally initiated entry-point channels the bundle signals for a class."""
    channels = []
    if (
        row.get("scheduledJobNames", "").strip()
        or row.get("qualifiedName", "") in schedule_liveness_names
        or parse_bool(
            row.get("scheduleLive", ""), allow_empty=True,
            field=f"{row.get('qualifiedName', 'candidate')} scheduleLive",
        )
    ):
        channels.append("scheduled")
    text = " ".join((row.get("qualifiedName", ""), row.get("name", ""), row.get("automationSummary", "")))
    channels.extend(
        channel for channel, patterns in ENTRY_POINT_TEXT_SIGNALS.items()
        if any(pattern.search(text) is not None for pattern in patterns)
    )
    return channels


def has_entry_point_signal(
    row: dict[str, str], schedule_liveness_names: set[str]
) -> bool:
    """Return whether the bundle signals an externally initiated Apex entry point."""
    return bool(entry_point_channels(row, schedule_liveness_names))


def test_only_reviewer_text(
    row: dict[str, str], *, effective_days: int, entry_point_signal: bool
) -> str:
    """Return the settled reviewer wording for one test-only candidate."""
    if entry_point_signal:
        return "We haven't seen this run. You should consider this for deletion."
    characters = parse_int(
        row.get("countedCharacters", ""), allow_empty=True,
        field=f"{row.get('qualifiedName', 'candidate')} countedCharacters",
    )
    character_text = (
        "characters stop counting (Elements holds no length for this class)"
        if characters is None else f"{characters} characters stop counting"
    )
    return (
        "Only test classes call this, and it has not run in production in the last "
        f"{effective_days} days. If it is a test factory, mark it `@isTest`: its "
        f"{character_text} and nothing is deleted. Otherwise, "
        "consider it for deletion."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engagement", required=True, type=Path,
        help="engagement directory containing execution-state.json and work/bundle",
    )
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(__file__))
    return parser


def _apex_name(row: dict[str, str], prefix: str = "") -> str:
    return qualified_name(
        row[f"{prefix}MetadataComponentNamespace"],
        row[f"{prefix}MetadataComponentName"],
    )


def triage(engagement: Path, data_dir: Path) -> dict[str, object]:
    state = read_json_object(engagement / "execution-state.json", "execution state")
    capacity = state.get("capacity")
    if not isinstance(capacity, dict):
        raise ContractError("execution state is missing capacity")
    stored_target = capacity.get("target")
    if not isinstance(stored_target, dict):
        raise ContractError("execution state is missing capacity.target")
    allocation = capacity.get("allocation")
    characters_used = capacity.get("charactersUsed")
    if isinstance(allocation, bool) or not isinstance(allocation, int):
        raise ContractError("capacity.allocation must be an integer")
    if characters_used is not None and (
        isinstance(characters_used, bool) or not isinstance(characters_used, int)
    ):
        raise ContractError("capacity.charactersUsed must be an integer when present")

    target = normalize_target(
        stored_target,
        allocation=allocation,
        characters_used=characters_used,
    )
    if "requiredCharacters" in stored_target and stored_target["requiredCharacters"] != target["requiredCharacters"]:
        raise ContractError("capacity.target.requiredCharacters disagrees with the banner arithmetic")

    bundle = engagement / "work" / "bundle"
    candidate_fields, candidates = read_csv(
        bundle / "candidates.csv",
        required=[
            "qualifiedName", "countedCharacters", "componentLabel", "isTestClass",
            "incomingFromP", "incomingFromCandidates", "incomingFromTest",
            "incomingFromOther", "scheduledJobNames", "scheduleLive",
            "automationSummary",
        ],
    )
    _, catalog = read_csv(
        bundle / "catalog.csv",
        required=[
            "qualifiedName", "kind", "isTestClass",
        ],
    )
    edge_fields, edges = read_csv(
        bundle / "edges.csv",
        required=[
            "MetadataComponentName", "MetadataComponentType",
            "MetadataComponentNamespace", "RefMetadataComponentName",
            "RefMetadataComponentType", "RefMetadataComponentNamespace",
        ],
    )
    components = read_json_array(bundle / "components.json", "components bundle")
    ledger = read_json_object(bundle / "telemetry-ledger.json", "telemetry ledger")
    effective_days = ledger.get("effectiveDays")
    if isinstance(effective_days, bool) or not isinstance(effective_days, int):
        raise ContractError("telemetry ledger effectiveDays must be an integer")

    schedule_liveness_names: set[str] = set()
    schedule_path = bundle / "schedule-liveness.csv"
    if schedule_path.is_file():
        _, schedule_rows = read_csv(schedule_path, required=["qualifiedName"])
        schedule_liveness_names = {
            row["qualifiedName"] for row in schedule_rows if row["qualifiedName"]
        }

    by_name = {row["qualifiedName"]: row for row in candidates}
    if len(by_name) != len(candidates):
        raise ContractError("candidates.csv contains duplicate qualifiedName values")
    catalog_by_name = {row["qualifiedName"]: row for row in catalog}
    catalog_kinds = {name: row["kind"] for name, row in catalog_by_name.items()}
    catalog_names = set(catalog_by_name)
    test_names = {
        name for name, row in catalog_by_name.items()
        if parse_bool(row["isTestClass"], field=f"{name} isTestClass")
    }
    component_by_label = {
        str(component["label"]): component
        for component in components
        if isinstance(component, dict) and "label" in component
    }

    def component_context(label: str, package_members: set[str]) -> dict[str, object]:
        component = component_by_label.get(label, {})
        raw_members = component.get("members", [])
        member_names = [
            str(member.get("qualifiedName", "")) if isinstance(member, dict) else str(member)
            for member in raw_members
        ]
        minute_counts: dict[str, int] = defaultdict(int)
        for name in member_names:
            modified = by_name.get(name, {}).get("lastModifiedDate", "")
            if modified:
                minute_counts[modified[:16]] += 1
        return {
            "label": label,
            "size": int(component.get("size", len(member_names))),
            "countedCharacters": component.get("countedCharacters"),
            "externalInboundEdges": component.get("externalInboundEdges"),
            "anyDeclaredRoot": component.get("anyDeclaredRoot"),
            "members": [{
                "qualifiedName": name,
                "lastModifiedDate": by_name.get(name, {}).get("lastModifiedDate", ""),
                "sameMinuteClusterCount": minute_counts.get(
                    by_name.get(name, {}).get("lastModifiedDate", "")[:16], 0
                ) if by_name.get(name, {}).get("lastModifiedDate", "") else 0,
            } for name in sorted(package_members)],
        }

    graph: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    source_types: dict[str, str] = {}
    flow_blockers: dict[str, list[str]] = defaultdict(list)
    trigger_column = "MetadataComponentTriggerType" in edge_fields
    for row in edges:
        parent_type = row["MetadataComponentType"]
        child_type = row["RefMetadataComponentType"]
        parent = _apex_name(row)
        child = _apex_name(row, "Ref")
        source_types[parent] = parent_type
        if type_key(parent_type) in {"apexclass", "apextrigger"} and type_key(child_type) in {"apexclass", "apextrigger"}:
            graph[parent].add(child)
            incoming[child].add(parent)
        parent_type_key = type_key(parent_type)
        own_node = child in by_name and type_key(child_type) == type_key(
            "Apex " + (by_name[child].get("kind") or catalog_by_name.get(child, {}).get("kind", ""))
        )
        if parent_type_key in {
            "processbuilderworkflow", "workflowrule",
        } and own_node:
            flow_blockers[child].append(
                f"referenced by the {parent_type} {parent}, whose use Elements cannot see yet"
            )
        if parent_type_key == "flow" and own_node:
            if not trigger_column:
                flow_blockers[child].append(
                    f"referenced by the Flow {parent}, whose use Elements cannot see yet"
                )
            else:
                raw = row.get("MetadataComponentTriggerType", "")
                if raw == "Scheduled" or raw.startswith("Record") or raw == "PlatformEvent":
                    flow_blockers[child].append(
                        f"referenced by the Flow {parent}, whose use Elements cannot see yet"
                    )

    dispositions_path = engagement / "work" / "review" / "dispositions.csv"
    dispositions_by_name: dict[str, str] = {}
    if dispositions_path.is_file():
        _, dispositions = read_csv(dispositions_path, required=["qualifiedName", "disposition"])
        dispositions_by_name = {
            row["qualifiedName"]: row["disposition"] for row in dispositions
        }
    ruled_keep = {
        name for name, disposition in dispositions_by_name.items()
        if disposition == "keep"
    }
    ruled_remove = {
        name for name, disposition in dispositions_by_name.items()
        if disposition == "remove"
    }
    ruled_annotate = {
        name for name, disposition in dispositions_by_name.items()
        if disposition == "annotate"
    }
    invalid_annotations = sorted(
        name for name in ruled_annotate
        if name not in by_name or not is_test_only(by_name[name])
        or has_entry_point_signal(by_name[name], schedule_liveness_names)
    )
    if invalid_annotations:
        raise ContractError(
            "annotate is allowed only for test-only candidates without an entry-point signal: "
            + ", ".join(invalid_annotations)
        )
    excluded_by_ruling = ruled_keep | ruled_remove | ruled_annotate

    holders: dict[str, list[dict[str, str]]] = defaultdict(list)
    holders_path = engagement / "work" / "triage" / "string-holders.csv"
    string_status_path = engagement / "work" / "triage" / "string-search-status.json"
    if string_status_path.is_file():
        string_status = read_json_object(string_status_path, "string search status").get("status")
        if string_status not in {"available", "unavailable"}:
            raise ContractError(
                "string-search-status.json status must be available or unavailable"
            )
        if not holders_path.is_file():
            raise ContractError(
                "string-search-status.json requires work/triage/string-holders.csv"
            )
    else:
        string_status = "available" if holders_path.is_file() else "not_run"
    if string_status == "available":
        _, holder_rows = read_csv(
            holders_path,
            required=[
                "qualifiedName", "holderName", "holderType", "holderIsTest",
                "holderInSelectedSet",
            ],
        )
        for row in holder_rows:
            holders[row["qualifiedName"]].append(row)

    inventory = {}
    for name, row in by_name.items():
        test_only = is_test_only(row)
        entry_point = test_only and has_entry_point_signal(row, schedule_liveness_names)
        inventory[name] = {
            "qualifiedName": name,
            "countedCharacters": row["countedCharacters"],
            "componentLabel": row["componentLabel"],
            "status": "deferred",
            "packageId": "",
            "reason": "capacity priority",
            "testOnly": str(test_only).lower(),
            "entryPointSignal": str(entry_point).lower(),
            "entryPointChannels": ";".join(
                entry_point_channels(row, schedule_liveness_names)
            ),
            "reviewerText": (
                test_only_reviewer_text(
                    row, effective_days=effective_days, entry_point_signal=entry_point
                ) if test_only else ""
            ),
        }
    known: dict[str, int] = {}
    unknown_names: set[str] = set()
    for name, row in by_name.items():
        value = parse_int(
            row["countedCharacters"], allow_empty=True,
            field=f"{name} countedCharacters",
        )
        if value is None:
            unknown_names.add(name)
            inventory[name].update(status="unknown-length", reason="counted character length is unknown")
        else:
            known[name] = value
    for name in ruled_keep & set(inventory):
        inventory[name].update(status="ruled", reason="ruled keep")
    for name in ruled_remove & set(inventory):
        inventory[name].update(status="ruled", reason="ruled remove")
    for name in ruled_annotate & set(inventory):
        inventory[name].update(status="ruled", reason="ruled annotate")

    ranked = sorted(known, key=lambda name: (-known[name], name.casefold(), name))
    standalone_names = {
        name
        for name, row in by_name.items()
        if is_test_only(row)
        and not has_entry_point_signal(row, schedule_liveness_names)
        and (parse_int(
            row["incomingFromTest"], field=f"{name} incomingFromTest"
        ) or 0) >= 3
    }
    assigned: set[str] = set()
    selected: set[str] = set()
    selected_packages = 0
    selected_characters = 0
    confirmed_characters = sum(
        known.get(name, 0) for name in ruled_remove | ruled_annotate
    )
    packages: list[dict[str, object]] = []
    package_sequence = 0

    def assess_unit(
        unit_seed: str,
        members: set[str],
        confirmed: set[str],
    ) -> dict[str, object]:
        in_use_because: list[str] = []
        kept_because: list[str] = []
        for member in sorted(members):
            for caller in outside_apex_callers(
                member,
                incoming=incoming,
                endpoint_types=source_types,
                catalog_by_name=catalog_by_name,
                confirmed=confirmed,
            ):
                in_use_because.append(
                    f"{member} is referenced by {caller}, which is in use"
                )
            kept_because.extend(flow_blockers.get(member, []))
            outside_holders = outside_string_holders(
                holders.get(member, []), confirmed, kinds=catalog_kinds,
            )
            for holder_row in holders.get(member, []):
                holder = holder_row["holderName"]
                if holder not in outside_holders or is_self_match(holder_row, catalog_kinds):
                    continue
                if type_key(holder_row["holderType"]) in {
                    "apexclass", "apextrigger", "class", "trigger",
                }:
                    in_use_because.append(
                        f"{member} is referenced by {holder}, which is in use"
                    )
                else:
                    kept_because.append(
                        "referenced by the "
                        f"{holder_row['holderType']} {holder}, "
                        "whose use Elements cannot see yet"
                    )

        unit_test_only = is_test_only(by_name[unit_seed])
        unit_entry_point = unit_test_only and has_entry_point_signal(
            by_name[unit_seed], schedule_liveness_names
        )
        tests = [] if unit_seed in standalone_names else attached_tests(
            members,
            graph=graph,
            test_names=test_names,
            catalog_names=catalog_names,
        )
        return {
            "seed": unit_seed,
            "members": members,
            "tests": tests,
            "countedCharacters": sum(known.get(name, 0) for name in members),
            "testOnly": unit_test_only,
            "entryPointSignal": unit_entry_point,
            "reviewerText": (
                test_only_reviewer_text(
                    by_name[unit_seed], effective_days=effective_days,
                    entry_point_signal=unit_entry_point,
                ) if unit_test_only else ""
            ),
            "inUseBecause": sorted(set(in_use_because)),
            "keptBecause": sorted(set(kept_because)),
            "status": "unknown-length" if members & unknown_names else (
                "in-use" if in_use_because else (
                    "kept-use-unknown" if kept_because else "selected"
                )
            ),
        }

    if target["alreadyAtTarget"]:
        outcome = "already_at_target"
    elif confirmed_characters >= int(target["requiredCharacters"]):
        outcome = "target_covered"
    else:
        for seed in ranked:
            if seed in assigned or seed in excluded_by_ruling:
                continue
            if confirmed_characters + selected_characters >= int(target["requiredCharacters"]):
                break
            package_members: set[str] = set()
            companion_names: set[str] = set()
            visited_tests: set[str] = set()
            pending = [seed]
            while pending:
                member = pending.pop()
                if member in package_members or member in selected:
                    continue
                package_members.add(member)
                for caller in incoming.get(member, set()):
                    if caller in by_name and caller not in excluded_by_ruling and caller not in assigned:
                        if caller in standalone_names and caller != seed:
                            companion_names.add(caller)
                            continue
                        pending.append(caller)
                for holder_row in holders.get(member, []):
                    holder = holder_row["holderName"]
                    if (
                        parse_bool(
                            holder_row["holderIsTest"], field="holderIsTest"
                        )
                        or type_key(holder_row["holderType"])
                        not in {"apexclass", "apextrigger", "class", "trigger"}
                        or holder not in by_name
                        or holder in excluded_by_ruling
                        or holder in assigned
                    ):
                        continue
                    if holder in standalone_names and holder != seed:
                        companion_names.add(holder)
                        continue
                    pending.append(holder)
                if seed not in standalone_names:
                    for test in incoming.get(member, set()) & test_names - visited_tests:
                        visited_tests.add(test)
                        for target_name in graph.get(test, set()):
                            if (
                                target_name not in by_name
                                or target_name in excluded_by_ruling
                                or target_name in assigned
                            ):
                                continue
                            if target_name in standalone_names and target_name != seed:
                                continue
                            pending.append(target_name)

            companion_assessments = [
                assess_unit(
                    companion,
                    {companion},
                    {companion} | selected | ruled_remove,
                )
                for companion in sorted(
                    companion_names,
                    key=lambda name: (-known.get(name, -1), name.casefold(), name),
                )
            ]
            selected_companions = {
                str(assessment["seed"])
                for assessment in companion_assessments
                if assessment["status"] == "selected"
            }
            main_assessment = assess_unit(
                seed,
                package_members,
                package_members | selected | ruled_remove | selected_companions,
            )

            for assessment in [main_assessment, *companion_assessments]:
                unit_seed = str(assessment["seed"])
                members = set(assessment["members"])
                in_use_because = list(assessment["inUseBecause"])
                kept_because = list(assessment["keptBecause"])
                status = str(assessment["status"])
                package_characters = int(assessment["countedCharacters"])
                package_sequence += 1
                package_id = f"PKG-{package_sequence:04d}"
                if status == "selected":
                    selected.update(members)
                    selected_characters += package_characters
                    selected_packages += 1
                for name in members:
                    assigned.add(name)
                    inventory[name].update(
                        status="unknown-length" if name in unknown_names else status,
                        packageId=package_id,
                        reason="; ".join(in_use_because or kept_because)
                        or (
                            "counted character length is unknown"
                            if status == "unknown-length"
                            else "selected by capacity priority"
                        ),
                    )
                packages.append({
                    "packageId": package_id,
                    "selectionOrder": package_sequence,
                    "status": status,
                    "seed": unit_seed,
                    "componentLabel": by_name[unit_seed]["componentLabel"],
                    "componentContext": component_context(
                        by_name[unit_seed]["componentLabel"], members
                    ),
                    "members": sorted(members),
                    "tests": assessment["tests"],
                    "countedCharacters": package_characters,
                    "runningCharacters": selected_characters,
                    "testOnly": assessment["testOnly"],
                    "entryPointSignal": assessment["entryPointSignal"],
                    "reviewerText": assessment["reviewerText"],
                    "inUseBecause": in_use_because,
                    "keptBecause": kept_because,
                })
        eligible_deferred = sum(
            row["status"] == "deferred" for row in inventory.values()
        )
        outcome = selection_outcome(
            required=int(target["requiredCharacters"]),
            reclaimed=confirmed_characters + selected_characters,
        )

    inventory_rows = [inventory[row["qualifiedName"]] for row in candidates]
    counts = {
        "selected": sum(row["status"] == "selected" for row in inventory_rows),
        "deferred": sum(row["status"] == "deferred" for row in inventory_rows),
        "inUse": sum(row["status"] == "in-use" for row in inventory_rows),
        "keptUseUnknown": sum(
            row["status"] == "kept-use-unknown" for row in inventory_rows
        ),
        "unknown-length": sum(
            row["status"] == "unknown-length" for row in inventory_rows
        ),
        "ruled": sum(row["status"] == "ruled" for row in inventory_rows),
    }
    required = int(target["requiredCharacters"])
    summary = {
        "target": target,
        "requiredCharacters": required,
        "confirmedCharacters": confirmed_characters,
        "selectedCharacters": selected_characters,
        "shortfall": max(0, required - confirmed_characters - selected_characters),
        "counts": counts,
        "unknownLengthCandidates": counts["unknown-length"],
        "eligibleDeferred": counts["deferred"],
        "selectedPackages": selected_packages,
        "outcome": outcome,
        "blindSpots": (
            {"stringSearchUnavailable": True}
            if string_status == "unavailable" else {}
        ),
        "stringSearch": string_status,
    }
    triage_dir = engagement / "work" / "triage"
    write_json(triage_dir / "summary.json", summary)
    write_json(triage_dir / "packages.json", packages)
    fields = [
        "qualifiedName", "countedCharacters", "componentLabel", "status",
        "packageId", "reason", "testOnly", "entryPointSignal", "entryPointChannels",
        "reviewerText",
    ]
    write_csv(triage_dir / "candidates.csv", fields, inventory_rows)
    write_csv(
        triage_dir / "deferred.csv", fields,
        [row for row in inventory_rows if row["status"] in {"deferred", "unknown-length"}],
    )
    return summary


def run(args: argparse.Namespace) -> None:
    summary = triage(args.engagement, args.data_dir)
    print(
        f"triage {summary['outcome']}: {summary['selectedCharacters']} selected characters; "
        f"{summary['shortfall']} shortfall"
    )


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
