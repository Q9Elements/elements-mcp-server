"""Project profiler payloads into strict one-target tool calls and local residue."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, read_json, write_json
except ImportError:
    from dli_common import ContractError, read_json, write_json


class ProjectionError(ContractError):
    """A profiler payload cannot be projected without changing its meaning."""


OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")
HASHED_IDENTIFIER = re.compile(r"^[0-9a-f]{12}$")


def _positive_integer(value, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProjectionError(f"{label} must be a positive integer")
    return value


def _relationship(entry: dict) -> tuple[dict, dict]:
    projected = {"column": entry.get("column")}
    residue = {key: value for key, value in entry.items() if key not in {"column", "typeDistribution", "fanIn"}}
    distributions = entry.get("typeDistribution", [])
    resolved = []
    removed_distribution_fields = []
    unresolved = []
    for index, row in enumerate(distributions):
        if row.get("object"):
            resolved.append({"object": row["object"]})
            removed = {key: value for key, value in row.items() if key != "object"}
            if removed:
                removed_distribution_fields.append({"entryIndex": index, **removed})
        else:
            unresolved.append(row)
    if len(resolved) > 20:
        raise ProjectionError(f"{entry.get('column')}: typeDistribution exceeds 20 entries")
    if resolved:
        projected["typeDistribution"] = sorted(resolved, key=lambda row: row["object"])
    if removed_distribution_fields:
        residue["typeDistribution"] = removed_distribution_fields
    if unresolved:
        residue["unresolvedTypeDistribution"] = unresolved
    fan_in = entry.get("fanIn")
    if fan_in is not None:
        if fan_in.get("idRepresentation") != "sha256_12":
            raise ProjectionError(f"{entry.get('column')}: idRepresentation must be hashed")
        if any(
            not HASHED_IDENTIFIER.fullmatch(str(parent.get("id", "")))
            for parent in fan_in.get("topParents", [])
        ):
            raise ProjectionError(f"{entry.get('column')}: hashed parent identifier is invalid")
        maximum = fan_in.get("maxRowsPerParent")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            raise ProjectionError(f"{entry.get('column')}: maxRowsPerParent must be numeric")
        projected["fanIn"] = {"maxRowsPerParent": maximum}
        extra_fan_in = {key: value for key, value in fan_in.items() if key != "maxRowsPerParent"}
        if extra_fan_in:
            residue["fanIn"] = extra_fan_in
    return projected, residue


PREDICATE_FIELDS = {"ruleId", "fields", "evaluableRows", "matchingRows", "note"}


def _predicate_reason(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return "entry must be an object"
    missing = sorted(PREDICATE_FIELDS - set(entry))
    if missing:
        return f"missing field(s): {', '.join(missing)}"
    unknown = sorted(set(entry) - PREDICATE_FIELDS)
    if unknown:
        return f"unknown field(s): {', '.join(unknown)}"
    if not isinstance(entry["ruleId"], str) or not entry["ruleId"]:
        return "ruleId must be a non-empty string"
    fields = entry["fields"]
    if not isinstance(fields, list) or len(fields) > 500:
        return "fields must be an array with at most 500 entries"
    if any(not isinstance(field, str) or not field.strip() or len(field.strip()) > 128 for field in fields):
        return "fields entries must be non-empty strings of at most 128 characters"
    for name in ("evaluableRows", "matchingRows"):
        value = entry[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return f"{name} must be a non-negative integer"
    if not isinstance(entry["note"], str) or len(entry["note"]) > 4000:
        return "note must be a string of at most 4000 characters"
    return None


def _target(target: dict) -> tuple[dict, dict]:
    operation = target.get("operation")
    if operation not in {"insert", "update", "upsert", "delete"}:
        raise ProjectionError(f"unsupported operation: {operation}")
    fields = target.get("writtenFields")
    if not isinstance(fields, list) or any(not isinstance(field, str) or not field.strip() for field in fields):
        raise ProjectionError("writtenFields must be an array of non-empty strings")
    fields = sorted(set(field.strip() for field in fields))
    if len(fields) > 200:
        raise ProjectionError("writtenFields exceeds 200 entries")
    if operation in {"update", "upsert"} and not fields:
        raise ProjectionError("writtenFields must not be empty for update and upsert operations")
    projected = {
        "object": str(target.get("object", "")).strip(),
        "writtenFields": fields,
        "operation": operation,
        "estimatedVolume": _positive_integer(target.get("estimatedVolume"), "estimatedVolume"),
    }
    if not projected["object"]:
        raise ProjectionError("object must be a non-empty string")
    aggregates = target.get("aggregates") or {}
    relationship_rows = aggregates.get("relationshipColumns") or []
    if len(relationship_rows) > 50:
        raise ProjectionError("relationshipColumns exceeds 50 entries")
    projected_relationships = []
    relationship_residue = []
    for entry in sorted(relationship_rows, key=lambda row: row.get("column", "")):
        kept, dropped = _relationship(entry)
        projected_relationships.append(kept)
        if dropped:
            relationship_residue.append({"column": entry.get("column"), **dropped})
    predicate_stats = aggregates.get("predicateStats") or []
    valid_predicates = []
    rejected_predicates = []
    for index, entry in enumerate(predicate_stats):
        reason = _predicate_reason(entry)
        if reason is None and len(valid_predicates) >= 100:
            reason = "predicateStats exceeds 100 valid entries"
        if reason:
            rejected_predicates.append({"entryIndex": index, "reason": reason, "value": entry})
        else:
            valid_predicates.append(entry)
    if valid_predicates and target.get("volumeSource") != "row_count":
        raise ProjectionError("predicateStats require estimatedVolume from an exact row count")
    projected_aggregates = {}
    if projected_relationships:
        projected_aggregates["relationshipColumns"] = projected_relationships
    if valid_predicates:
        projected_aggregates["predicateStats"] = sorted(valid_predicates, key=lambda row: row["ruleId"])
    if projected_aggregates:
        projected["aggregates"] = projected_aggregates
    residue = {
        "object": projected["object"],
        "operation": operation,
        "sourceFields": {key: value for key, value in target.items()
                         if key not in {"object", "writtenFields", "operation", "estimatedVolume", "aggregates", "upsert"}},
        "upsert": target.get("upsert"),
        "relationshipColumns": relationship_residue,
        "unresolved": aggregates.get("unresolved") or [],
    }
    if rejected_predicates:
        residue["predicateStats"] = rejected_predicates
    return projected, residue


def project_payloads(payloads: list[dict], ref_model_id: str, depth_bound: int = 5,
                     team_id: str | None = None):
    if not OBJECT_ID.fullmatch(ref_model_id):
        raise ProjectionError("refModelId must be a 24-character hexadecimal identifier")
    if team_id is not None and not OBJECT_ID.fullmatch(team_id):
        raise ProjectionError("teamId must be a 24-character hexadecimal identifier")
    if not isinstance(depth_bound, int) or not 1 <= depth_bound <= 10:
        raise ProjectionError("depthBound must be an integer from 1 through 10")
    calls = []
    residue = {"payloads": [], "targets": []}
    seen_objects = set()
    for payload_index, payload in enumerate(payloads):
        targets = payload.get("targets")
        if not isinstance(targets, list) or not targets:
            raise ProjectionError(f"payload {payload_index + 1} has no targets")
        residue["payloads"].append({
            "payloadIndex": payload_index,
            "contractVersion": payload.get("contractVersion"),
            "generatedBy": payload.get("generatedBy"),
            "asks": payload.get("asks", []),
            "assumptions": payload.get("assumptions", []),
            "warnings": payload.get("warnings", []),
        })
        for source in targets:
            target, dropped = _target(source)
            key = (target["object"], target["operation"])
            if key in seen_objects:
                raise ProjectionError(f"duplicate target {target['object']} {target['operation']}")
            seen_objects.add(key)
            calls.append({
                "object": target["object"],
                "arguments": {"refModelId": ref_model_id, **({"teamId": team_id} if team_id else {}),
                              "targets": [target], "depthBound": depth_bound},
            })
            residue["targets"].append(dropped)
    calls.sort(key=lambda call: (call["object"], call["arguments"]["targets"][0]["operation"]))
    residue["targets"].sort(key=lambda row: (row["object"], row["operation"]))
    return calls, residue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payloads", nargs="+", type=Path)
    parser.add_argument("--ref-model-id", required=True)
    parser.add_argument("--team-id")
    parser.add_argument("--depth-bound", type=int, default=5)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--residue", required=True, type=Path)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        calls, residue = project_payloads(
            [read_json(path) for path in arguments.payloads], arguments.ref_model_id,
            arguments.depth_bound, arguments.team_id
        )
        write_json(arguments.out, {"calls": calls})
        write_json(arguments.residue, residue)
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"projected {len(calls)} one-target call(s); residue targets: {len(residue['targets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
