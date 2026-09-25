#!/usr/bin/env python3
"""Build card 04's self-contained unused-Apex review page from an engagement."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from apex_common import (
    REASONED_CANDIDATE_COLUMNS,
    ContractError,
    cli_guard,
    default_data_dir,
    parse_bool,
    parse_float,
    parse_int,
    read_csv,
    read_json_array,
    read_table,
    require_file,
    qualified_name,
)
from capacity_triage import (
    has_entry_point_signal,
    is_test_only,
    test_only_reviewer_text,
)


DEFAULT_REPORT = Path("report/04-review-pack.html")
TEMPLATE_PATH = Path(__file__).with_name("review_page_template.html")
REQUIRED_REASONED_COLUMNS = [
    field for field in REASONED_CANDIDATE_COLUMNS
    if field != "cadenceSignalAvailable"
]
REQUIRED_CANDIDATE_COLUMNS = [
    "nodeId", "sfId", "qualifiedName", "name", "kind", "triggerObject", "apiVersion",
    "countedCharacters", "countedRule", "lastModifiedDate", "lastExecutedDate",
    "lastExecutedDirect", "lastExecutedVia", "executionCount", "executionRate",
    "scheduledJobNames", "scheduleLive", "set", "incomingFromP", "incomingFromCandidates",
    "incomingFromTest", "incomingFromOther", "incomingTotal", "incomingOtherTypes",
    "incomingReading", "componentLabel", "description", "automationSummary", "intentTags",
    "stringReferenceHits", "stringReferenceNodes", "stringReferenceOutsideCandidates",
]
REQUIRED_EDGE_COLUMNS = [
    "MetadataComponentName", "MetadataComponentType", "MetadataComponentNamespace",
    "RefMetadataComponentName", "RefMetadataComponentType", "RefMetadataComponentNamespace",
    "parentUsed", "parentNodeId", "childNodeId",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement", required=True, type=Path,
                        help="engagement directory containing work/ and report/")
    parser.add_argument("--out", type=Path,
                        help="output path (default: <engagement>/report/04-review-pack.html)")
    parser.add_argument("--org-name", required=True, help="customer org name displayed in the toolbar")
    parser.add_argument("--reviewer", default="",
                        help="reviewer name recorded by card 04 step 1; pre-fills the page's Reviewer box")
    parser.add_argument("--ref-model-id", help="Elements reference-model id for provenance")
    return parser


def _load_json(path: Path, label: str) -> dict:
    require_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from None
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def _elements_link_meta(engagement: Path, fallback_ref_model_id: str | None) -> tuple[str | None, str | None]:
    path = engagement / "execution-state.json"
    if not path.is_file():
        return fallback_ref_model_id, None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(state, dict):
        return None, None
    slots = state.get("slots")
    if not isinstance(slots, dict):
        return None, None
    ref_model_id = slots.get("model_id")
    if not isinstance(ref_model_id, str) or not ref_model_id.strip():
        return None, None
    base_url = slots.get("elements_base_url")
    if not isinstance(base_url, str):
        return ref_model_id, None
    base_url = base_url.lower()
    if not re.fullmatch(
        r"https://(?:[a-z0-9-]+\.)+(?:elements\.cloud|elements-eng\.cloud|q9elements\.com)",
        base_url,
    ):
        return ref_model_id, None
    return ref_model_id, base_url


def _number(value: str, *, integer: bool = False) -> int | float | None:
    if value.strip() == "":
        return None
    return parse_int(value) if integer else parse_float(value)


def _display_text(value: str) -> str:
    """Undo the server's one-character spreadsheet formula escape for display."""
    if len(value) >= 2 and value[0] == "'" and value[1] in "=+-@":
        return value[1:]
    return value


def _without_coverage(value: object) -> object:
    """Remove server fields that this customer-facing page does not use."""
    if isinstance(value, dict):
        return {
            key: _without_coverage(nested)
            for key, nested in value.items()
            if "coverage" not in key.casefold()
        }
    if isinstance(value, list):
        return [
            _without_coverage(item) for item in value
            if not (isinstance(item, str) and "coverage" in item.casefold())
        ]
    return value


def _edge_identity(name: str, namespace: str, component_type: str) -> str:
    if component_type in {"Apex Class", "Apex Trigger"}:
        return qualified_name(namespace, name)
    return name


def _group_contract(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    definitions: dict[int, tuple[str, str]] = {}
    for row in rows:
        order = parse_int(row["groupOrder"], field=f"groupOrder of {row['qualifiedName']}")
        label, note = row["groupLabel"].strip(), row["groupNote"].strip()
        if not label or not note:
            raise ContractError(f"{row['qualifiedName']}: groupLabel and groupNote must be non-empty")
        existing = definitions.get(order)
        if existing is not None and existing != (label, note):
            raise ContractError(f"groupOrder {order} has inconsistent label or note")
        if any(other_order != order and other[0] == label for other_order, other in definitions.items()):
            raise ContractError(f"groupLabel {label!r} has more than one groupOrder")
        definitions[order] = (label, note)

    groups = []
    for order in sorted(definitions):
        label, note = definitions[order]
        members = [row for row in rows if parse_int(row["groupOrder"]) == order]
        groups.append({
            "order": order,
            "label": label,
            "note": note,
            "rows": len(members),
            "components": len({row["componentLabel"] for row in members}),
            "chars": sum(parse_int(row["countedCharacters"], allow_empty=True) or 0 for row in members),
            "unknownLengthRows": sum(not row["countedCharacters"].strip() for row in members),
        })
    return groups


def build_state(
    engagement: Path,
    org_name: str,
    ref_model_id: str | None,
    reviewer: str = "",
) -> tuple[dict, int]:
    """Read the card 04 inputs and return the page state plus the edge count."""
    ref_model_id, elements_base_url = _elements_link_meta(engagement, ref_model_id)
    work = engagement / "work"
    bundle = work / "bundle"
    reasoned_path = work / "reasoned-candidates.csv"
    _, all_reasoned = read_csv(
        reasoned_path,
        required=[*REQUIRED_CANDIDATE_COLUMNS, *REQUIRED_REASONED_COLUMNS],
    )
    if not all_reasoned:
        raise ContractError(f"{reasoned_path} has no rows")
    packages_path = work / "triage" / "packages.json"
    triage_summary: dict[str, object] | None = None
    capacity_packages: list[dict[str, object]] = []
    inventory_names: set[str] = set()
    if packages_path.is_file():
        raw_packages = read_json_array(packages_path, "triage packages")
        if not all(isinstance(package, dict) for package in raw_packages):
            raise ContractError(f"{packages_path} must contain package objects")
        capacity_packages = sorted(
            [package for package in raw_packages if package.get("status") == "selected"],
            key=lambda package: int(package.get("selectionOrder", 0)),
        )
        triage_summary = _load_json(work / "triage" / "summary.json", "triage summary")
        _, triage_inventory = read_csv(
            work / "triage" / "candidates.csv",
            required=[
                "qualifiedName", "countedCharacters", "componentLabel", "status",
                "packageId", "reason",
            ],
        )
        selected_names = {
            str(member)
            for package in capacity_packages
            for member in package.get("members", [])
        }
        candidates = [
            candidate for candidate in all_reasoned
            if candidate["qualifiedName"] in selected_names
        ]
        if {candidate["qualifiedName"] for candidate in candidates} != selected_names:
            raise ContractError(
                "reasoned-candidates.csv does not cover every selected package member"
            )
        inventory_names = {
            str(row["qualifiedName"]) for row in triage_inventory
        }
    else:
        candidates = all_reasoned
        inventory_names = {row["qualifiedName"] for row in all_reasoned}

    _, edges = read_csv(bundle / "edges.csv", required=REQUIRED_EDGE_COLUMNS)
    ledger = _without_coverage(
        _load_json(bundle / "telemetry-ledger.json", "telemetry ledger")
    )
    blind_spots = _without_coverage(
        _load_json(bundle / "blind-spots.json", "blind spots")
    )
    if not isinstance(ledger, dict) or not isinstance(blind_spots, dict):
        raise ContractError("review evidence must be JSON objects")
    envelope = _load_json(
        bundle / "envelope.json", "candidate-tool envelope written by card 02"
    )
    capacity_source = _load_json(
        bundle / "catalog-summary.with-capacity.json", "capacity summary written by card 02"
    )
    candidate_by_name = {row["qualifiedName"]: row for row in all_reasoned}
    candidate_names = {row["qualifiedName"] for row in candidates}
    schedule_liveness_names: set[str] = set()
    schedule_path = bundle / "schedule-liveness.csv"
    if schedule_path.is_file():
        _, schedule_rows = read_csv(schedule_path, required=["qualifiedName"])
        schedule_liveness_names = {
            row["qualifiedName"] for row in schedule_rows if row["qualifiedName"]
        }
    dispositions_path = work / "review" / "dispositions.csv"
    prior_rulings: dict[str, dict[str, object]] = {}
    if dispositions_path.is_file():
        _, prior_rows = read_csv(
            dispositions_path,
            required=[
                "qualifiedName", "disposition", "decidedBy", "decidedOn", "note",
            ],
        )
        for row in prior_rows:
            name = row["qualifiedName"]
            if name not in inventory_names:
                raise ContractError(
                    f"{dispositions_path} names non-candidate {name}"
                )
            if row["disposition"] not in {"remove", "keep", "decide-later", "annotate"}:
                raise ContractError(
                    f"{dispositions_path} has invalid disposition {row['disposition']!r} for {name}"
                )
            candidate = candidate_by_name.get(name)
            annotatable = bool(
                candidate
                and is_test_only(candidate)
                and not has_entry_point_signal(candidate, schedule_liveness_names)
            )
            if row["disposition"] == "annotate" and not annotatable:
                raise ContractError(
                    "annotate is allowed only for test-only candidates without an entry-point signal: "
                    + name
                )
            if name in candidate_names:
                prior_rulings[name] = {
                    "disposition": row["disposition"],
                    "decidedBy": row["decidedBy"],
                    "decidedOn": row["decidedOn"],
                    "note": row["note"],
                    "alreadyRuled": row["disposition"] != "decide-later",
                }

    data_dir = default_data_dir(__file__)
    reason_text = {
        row["reason"]: row["meaning"]
        for row in read_table(data_dir, "review-first-reasons.csv", ["reason", "meaning"])
    }
    dispositions = read_table(data_dir, "dispositions.csv", ["disposition", "meaning", "planned"])
    looks_dead = read_table(
        data_dir,
        "looks-dead-but-is-not.csv",
        ["id", "pattern", "why_it_looks_dead", "check"],
    )

    candidate_node_ids = {row["nodeId"] for row in candidates}
    inbound: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    outbound: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for edge in edges:
        child_node, parent_node = edge["childNodeId"], edge["parentNodeId"]
        child_type, parent_type = edge["RefMetadataComponentType"], edge["MetadataComponentType"]
        child = _edge_identity(
            edge["RefMetadataComponentName"], edge["RefMetadataComponentNamespace"], child_type,
        )
        parent = _edge_identity(
            edge["MetadataComponentName"], edge["MetadataComponentNamespace"], parent_type,
        )
        inbound[child_node].setdefault(parent_node, {
            "name": parent,
            "type": parent_type,
            "used": parse_bool(edge["parentUsed"], field="parentUsed"),
            "inCandidates": parent_node in candidate_node_ids,
            "nodeId": parent_node,
        })
        outbound[parent_node].setdefault(child_node, {
            "name": child,
            "type": child_type,
            "inCandidates": child_node in candidate_node_ids,
        })

    component_sizes: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        component_sizes[candidate["componentLabel"]] += 1

    package_for = {
        str(member): package
        for package in capacity_packages
        for member in package.get("members", [])
    }
    package_rank = {
        str(package["packageId"]): order
        for order, package in enumerate(capacity_packages, start=1)
    }
    package_label: dict[str, str] = {}
    package_note: dict[str, str] = {}
    for candidate in candidates:
        package = package_for.get(candidate["qualifiedName"])
        if package:
            package_id = str(package["packageId"])
            if candidate["groupLabel"].strip():
                package_label.setdefault(package_id, candidate["groupLabel"].strip())
            if candidate["groupNote"].strip():
                package_note.setdefault(package_id, candidate["groupNote"].strip())
    state_rows = []
    for candidate in candidates:
        qualified_name = candidate["qualifiedName"]
        package = package_for.get(qualified_name)
        incoming = list(inbound.get(candidate["nodeId"], {}).values())
        test_referrers = [
            ref for ref in incoming
            if ref["type"] == "Apex Class" and str(ref["name"]).lower().endswith("test")
        ]
        non_apex = [ref for ref in incoming if ref["type"] not in {"Apex Class", "Apex Trigger"}]
        reason_codes = [code for code in candidate["reasons"].split(";") if code]
        reasons = [{"code": code, "text": reason_text.get(code, code), "weak": False}
                   for code in reason_codes]
        quotes = [quote.strip() for quote in candidate["quotes"].split(" | ") if quote.strip()]
        test_only = is_test_only(candidate)
        entry_point = test_only and has_entry_point_signal(
            candidate, schedule_liveness_names
        )
        reviewer_text = (
            test_only_reviewer_text(
                candidate,
                effective_days=int(ledger.get("effectiveDays", 0)),
                entry_point_signal=entry_point,
            ) if test_only else ""
        )
        state_rows.append({
            "qualifiedName": qualified_name,
            "name": candidate["name"],
            "kind": candidate["kind"],
            "nodeId": candidate["nodeId"],
            "sfId": candidate["sfId"],
            "triggerObject": candidate["triggerObject"],
            "apiVersion": candidate["apiVersion"],
            "chars": parse_int(candidate["countedCharacters"], allow_empty=True),
            "countedRule": candidate["countedRule"],
            "lastModified": candidate["lastModifiedDate"][:10],
            "lastExecuted": candidate["lastExecutedDate"] or None,
            "lastExecutedDirect": candidate["lastExecutedDirect"],
            "lastExecutedVia": candidate["lastExecutedVia"],
            "executionCount": _number(candidate["executionCount"], integer=True),
            "executionRate": _number(candidate["executionRate"]),
            "scheduledJobNames": _display_text(candidate["scheduledJobNames"]),
            "scheduleLive": parse_bool(candidate["scheduleLive"], field="scheduleLive"),
            "set": candidate["set"],
            "incomingReading": candidate["incomingReading"],
            "incomingFromP": parse_int(candidate["incomingFromP"]),
            "incomingFromCandidates": parse_int(candidate["incomingFromCandidates"]),
            "incomingFromTest": parse_int(candidate["incomingFromTest"]),
            "incomingFromOther": parse_int(candidate["incomingFromOther"]),
            "incomingTotal": parse_int(candidate["incomingTotal"]),
            "incomingOtherTypes": candidate["incomingOtherTypes"],
            "component": candidate["componentLabel"],
            "description": _display_text(candidate["description"]),
            "automationSummary": _display_text(candidate["automationSummary"]),
            "intentTags": _display_text(candidate["intentTags"]),
            "stringHits": parse_int(candidate["stringReferenceHits"], allow_empty=True) or 0,
            "stringNodes": candidate["stringReferenceNodes"],
            # Decision 42 is implemented by the producing tool. The page consumes, and never re-derives, this flag.
            "stringOutside": (
                parse_bool(
                    candidate["stringReferenceOutsideCandidates"],
                    allow_empty=True,
                    field="stringReferenceOutsideCandidates",
                ) or any(reason["code"] == "dynamic_dispatch_residue" for reason in reasons)
            ),
            "verdict": candidate["verdict"],
            "confidence": candidate["confidence"],
            "bucket": candidate["bucket"],
            "reasons": reasons,
            "quotes": [_display_text(quote) for quote in quotes],
            "componentNote": _display_text(candidate["componentNote"]) if component_sizes[candidate["componentLabel"]] > 1 else "",
            "inbound": incoming,
            "outbound": list(outbound.get(candidate["nodeId"], {}).values()),
            "nonApexReferrers": non_apex,
            "testReferrers": test_referrers,
            "packageId": str(package["packageId"]) if package else "",
            "groupLabel": package_label.get(str(package["packageId"]), str(package["packageId"])) if package else candidate["groupLabel"],
            "groupOrder": package_rank[str(package["packageId"])] if package else parse_int(candidate["groupOrder"], field=f"groupOrder of {qualified_name}"),
            "testOnly": test_only,
            "entryPointSignal": entry_point,
            "annotatable": test_only and not entry_point,
            "reviewerText": reviewer_text,
        })

    state_rows.sort(key=lambda row: (
        row["groupOrder"],
        0 if row["bucket"] == "review-first" else 1,
        -(row["chars"] or 0),
        row["qualifiedName"],
    ))
    if capacity_packages:
        groups = [{
            "order": package_rank[str(package["packageId"])],
            "label": str(package.get("seed") or package_label.get(str(package["packageId"]), package["packageId"])),
            "note": package_note.get(str(package["packageId"]), "Dependency-complete removal package."),
            "rows": len(package.get("members", [])),
            "components": 1,
            "chars": int(package.get("countedCharacters", 0)),
            "unknownLengthRows": sum(
                row["chars"] is None for row in state_rows
                if row["groupOrder"] == package_rank[str(package["packageId"])]
            ),
            "packageId": package["packageId"],
            "tests": package.get("tests", []),
            "runningCharacters": package.get("runningCharacters", 0),
            "requiredCharacters": triage_summary.get("requiredCharacters", 0) if triage_summary else 0,
        } for package in capacity_packages]
    else:
        groups = _group_contract(candidates)
    component_members: dict[str, list[str]] = defaultdict(list)
    for row in state_rows:
        component_members[row["component"]].append(row["qualifiedName"])

    state = {
        "meta": {
            "org": org_name,
            "refModelId": ref_model_id,
            "elementsBaseUrl": elements_base_url,
            "computedAt": envelope["computedAt"],
            "syncTimestamp": envelope["syncTimestamp"],
            "bundleSha256": envelope.get("bundleSha256"),
            "reasoned": True,
            "generatedBy": "scripts/review_page.py",
        },
        "ledger": ledger,
        "blindSpots": blind_spots,
        "summary": envelope["summary"],
        "capacity": {
            key: capacity_source.get(key)
            for key in ("charactersUsed", "allocation", "displayedPercent", "reconciled")
        },
        "groups": groups,
        "packages": capacity_packages,
        "triage": triage_summary,
        "rows": state_rows,
        "components": {
            component: sorted(members)
            for component, members in component_members.items()
            if len(members) > 1
        },
        "dispositions": dispositions,
        "looksDead": looks_dead,
        "review": {
            "reviewer": reviewer.strip(),
            "rulings": prior_rulings,
            "componentRulings": {},
            "finished": None,
            "savedAt": None,
        },
    }
    return state, len(edges)


def generate_review_page(
    engagement: Path,
    out: Path,
    org_name: str,
    ref_model_id: str | None,
    reviewer: str = "",
) -> str:
    """Generate one review-page file and return the CLI summary line."""
    require_file(TEMPLATE_PATH, "review-page template")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count("__STATE__") != 1:
        raise ContractError(f"{TEMPLATE_PATH} must contain __STATE__ exactly once")
    state, edge_count = build_state(engagement, org_name, ref_model_id, reviewer)
    state_json = json.dumps(state, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("__STATE__", state_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return (f"wrote {out} ({out.stat().st_size:,} bytes); rows={len(state['rows'])} "
            f"groups={len(state['groups'])} edges={edge_count}")


def run(args: argparse.Namespace) -> None:
    output = args.out if args.out is not None else args.engagement / DEFAULT_REPORT
    print(generate_review_page(args.engagement, output, args.org_name, args.ref_model_id, args.reviewer))


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
