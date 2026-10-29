"""Shortlist existing automations and verify purpose judgements against write edges."""

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from tool_reply import unwrap_reply
from automation_state import active_state
from cli_common import SingleLineParser, _edges, normalize_type, field_object
from normalize_reads import dependency_operation

AUTOMATIONS = {"Flow", "Process Builder Workflow", "Apex Trigger", "Apex Class", "Workflow Rule"}
OBJECTS = {"Object", "Standard Object", "Custom Object"}


def _kind(row):
    return normalize_type(row)


def _true(value):
    return str(value).lower() in {"true", "1"}


def _object(row):
    return field_object(row)


def _field(row):
    name = row.get("apiName") or ""
    return name if "." in name else f"{_object(row)}.{name}" if _object(row) and name else None


def _change_objects(change_set, rows):
    objects = set()
    ids = set()
    for change in change_set.get("elements", []):
        element = change.get("element") or {}
        delta = change.get("delta") or {}
        ids.add(element.get("nodeId"))
        for source in (element, delta):
            name = _object(source) or source.get("trigger_object") or source.get("triggerObject")
            if name:
                objects.add(name)
            objects.update(source.get("created_objects") or [])
            for key in ("written_fields", "writtenFields", "entry_fields", "read_fields"):
                fields = source.get(key) or []
                for field in [fields] if isinstance(fields, str) else fields:
                    name = field.get("apiName", "") if isinstance(field, dict) else field
                    if isinstance(field, dict) and field.get("object"):
                        objects.add(field["object"])
                    if "." in name:
                        objects.add(name.split(".", 1)[0])
    for row in rows:
        if row.get("direction") == "outgoing" and row.get("inputNodeId") in ids:
            name = row.get("apiName") if _kind(row) in OBJECTS else _object(row)
            if name:
                objects.add(name)
    return objects


def _packaged(row):
    # Normalized reads preserve managedPackage and namespacePrefix. Older folders
    # use the namespace prefix in the automation's API (application programming interface) name.
    if any(row.get(key) not in (None, "", False, "null", "None", "false", "{}")
           for key in ("managedPackage", "namespacePrefix", "namespace")):
        return True
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*__.+", (row.get("apiName") or "").rsplit(".", 1)[-1]))


def _inactive_definitions(folders):
    inactive = set()
    for folder in folders:
        root = Path(folder)
        with (root / "index.csv").open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                if active_state(row) is False:
                    inactive.add(row["nodeId"])
                if row.get("xmlFile"):
                    try:
                        definition = ET.parse(root / row["xmlFile"])
                    except ET.ParseError as error:
                        raise ValueError(f"invalid definition for {row['nodeId']}: {error}") from error
                    if any(element.tag.rsplit("}", 1)[-1] == "status"
                           and active_state({"status": (element.text or "").strip()}) is False
                           for element in definition.iter()):
                        inactive.add(row["nodeId"])
    return inactive


def shortlist(change_set, rows, target_objects=(), definitions=()):
    """Select active unpackaged peers that read or write a changed object."""
    changes = change_set.get("elements", [])
    deleted = [{"nodeId": item["element"]["nodeId"],
                "name": item["element"].get("name") or item["element"].get("apiName"),
                "type": _kind(item["element"])} for item in changes
               if item.get("action") == "delete" and _kind(item.get("element") or {}) in AUTOMATIONS]
    has_deletes = any(item.get("action") == "delete" for item in changes)
    direction = "both" if has_deletes and any(item.get("action") != "delete" for item in changes) else "delete" if has_deletes else "new"
    changed_ids = {item.get("element", {}).get("nodeId") for item in changes
                   if item.get("action") in {"create", "update", "delete"}}
    changed_names = {(item.get("element", {}).get("apiName") or item.get("element", {}).get("name"),
                      _kind(item.get("element") or {})) for item in changes
                     if item.get("action") in {"create", "update", "delete"}}
    objects = _change_objects(change_set, rows) | set(target_objects)
    facts, touched, excluded = {}, {}, _inactive_definitions(definitions)
    for row in rows:
        if row.get("direction") != "incoming" or _kind(row) not in AUTOMATIONS or not row.get("nodeId"):
            continue
        node_id = row["nodeId"]
        facts[node_id] = row
        if active_state(row) is False or _packaged(row):
            excluded.add(node_id)
        if _true(row.get("read")) or _true(row.get("write")):
            name = (row.get("inputApiName") if normalize_type(row.get("inputSfType")) in OBJECTS else row.get("inputObject")) or _object(row)
            if name:
                touched.setdefault(node_id, set()).add(name)
    for row in rows:
        if row.get("direction") == "outgoing" and (_true(row.get("read")) or _true(row.get("write"))):
            name = row.get("apiName") if _kind(row) in OBJECTS else _object(row)
            if name:
                touched.setdefault(row.get("inputNodeId"), set()).add(name)
    candidates = []
    for node_id, row in facts.items():
        if (node_id in changed_ids or node_id in excluded
                or (row.get("apiName") or row.get("name"), _kind(row)) in changed_names
                or not (touched.get(node_id, set()) & objects)):
            continue
        candidates.append({"nodeId": node_id, "name": row.get("name") or row.get("apiName"),
                           "type": _kind(row), "objects": sorted(touched[node_id])})
    return {"direction": direction, "deleted": deleted, "candidates": candidates,
            "summary_ids": list(dict.fromkeys(row["nodeId"] for row in deleted + candidates if row["type"] != "Workflow Rule"))}


def _summaries(paths):
    summaries = {}
    for path in paths:
        reply = json.loads(Path(path).read_text(encoding="utf-8"))
        reply = unwrap_reply(reply)
        for item in reply.get("items", [reply]):
            if item.get("status") != "complete":
                raise ValueError(f"summary {item.get('nodeId') or 'reply'} status: {item.get('status')}")
            if item.get("aspect") != "summary":
                raise ValueError(f"summary {item.get('nodeId')}: aspect must be summary")
            narrative = item.get("narrative")
            if isinstance(narrative, dict):
                text = narrative.get("text")
                narrative = text if isinstance(text, str) and text.strip() else narrative.get("purpose")
            if not isinstance(narrative, str) or not narrative.strip():
                raise ValueError(f"summary {item.get('nodeId')}: narrative required")
            summaries[item["nodeId"]] = narrative
    return summaries


def _write_match(node_id, fields, creates, rows):
    for row in rows:
        if row.get("inputNodeId") != node_id or row.get("direction") != "outgoing" or not _true(row.get("write")):
            continue
        if _kind(row) == "Field" and _field(row) in fields:
            return _field(row)
        if (_kind(row) in OBJECTS and creates and row.get("apiName") == creates
                and dependency_operation(row) in {"insert", "create"}):
            return creates
    return None


def check(held, summaries, judgements, rows, change_set):
    """Keep a purpose fit only when its candidate has a corresponding write."""
    candidates = {row["nodeId"]: row for row in held["candidates"]}
    if not isinstance(judgements, dict) or not isinstance(judgements.get("items"), list):
        raise ValueError("invalid judgements: expected an items list")
    for item in judgements["items"]:
        if (not isinstance(item, dict) or item.get("direction") not in {"new", "delete"}
                or not isinstance(item.get("job"), str) or not item["job"].strip()
                or not isinstance(item.get("job_fields"), list)
                or any(not isinstance(field, str) or "." not in field for field in item["job_fields"])
                or item.get("verdict") not in {"fit", "partial", "none"}
                or not isinstance(item.get("reason"), str)
                or (item.get("creates_object") is not None and not isinstance(item["creates_object"], str))
                or (item.get("candidate") is not None and not isinstance(item["candidate"], str))):
            raise ValueError("invalid judgement: direction, job, job_fields, candidate, verdict, reason and creates_object must follow the contract")
    for node_id in held["summary_ids"]:
        if node_id not in summaries:
            raise ValueError(f"missing summary: {node_id}")
    output = {"new": {"fits": [], "partials": []},
              "delete": {"covered": [], "partly_covered": [], "lost": [], "ask": []}}
    if held["deleted"] and not any(item.get("direction") == "delete" for item in judgements["items"]):
        raise ValueError("delete job has no item; supply a none judgement with candidate null when no candidate fits")
    deleted_ids = {item["element"]["nodeId"] for item in change_set.get("elements", [])
                   if item.get("action") == "delete" and _kind(item.get("element") or {}) in AUTOMATIONS}
    described_fields = {field for item in judgements["items"] if item.get("direction") == "delete"
                        for field in item.get("job_fields") or []}
    for row in rows:
        if (row.get("inputNodeId") in deleted_ids and row.get("direction") == "outgoing"
                and _kind(row) == "Field" and _true(row.get("write"))
                and _field(row) and _field(row) not in described_fields):
            raise ValueError(f"delete job has no item for {_field(row)}")
    delete_jobs = {}
    for item in judgements["items"]:
        node_id = item.get("candidate")
        if node_id is not None and node_id not in candidates:
            raise ValueError(f"candidate not in shortlist: {node_id}")
        candidate = candidates.get(node_id, {})
        fields = item.get("job_fields") or []
        creates = item.get("creates_object")
        written = _write_match(node_id, fields, creates, rows) if node_id else None
        verdict, reason = item["verdict"], item["reason"]
        if verdict in {"fit", "partial"} and not written:
            verdict = "none"
            reason = "summary matches but it does not write " + (", ".join(fields) or str(creates or "a job field"))
        entry = {**item, "verdict": verdict, "reason": reason, "model_reason": item["reason"],
                 "name": candidate.get("name"), "type": candidate.get("type"),
                 "summary": summaries.get(node_id), "written_field": written}
        if item["direction"] == "new":
            if verdict != "none":
                output["new"]["fits" if verdict == "fit" else "partials"].append(entry)
        else:
            key = (item["job"], tuple(sorted(fields)), creates)
            delete_jobs.setdefault(key, []).append(entry)
    for entries in delete_jobs.values():
        best = max(entries, key=lambda item: {"fit": 2, "partial": 1, "none": 0}[item["verdict"]])
        result = {**best, "assessments": entries}
        if best["verdict"] == "partial":
            result["lost_part"] = {"job": best["job"], "reason": best["reason"]}
        category = {"fit": "covered", "partial": "partly_covered", "none": "lost"}[best["verdict"]]
        output["delete"][category].append(result)
        if category in {"lost", "partly_covered"}:
            output["delete"]["ask"].append(result)
    return output


def main(argv=None):
    parser = SingleLineParser(description=__doc__)
    parser.add_argument("command", choices=("shortlist", "check"))
    parser.add_argument("--change-set", required=True)
    parser.add_argument("--objects", nargs="+", action="extend", default=[])
    parser.add_argument("--definitions", nargs="+", action="extend", default=[])
    parser.add_argument("--dependents", nargs="+", action="extend", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shortlist")
    parser.add_argument("--summaries", nargs="+", action="extend")
    parser.add_argument("--judgements")
    args = parser.parse_args(argv)
    try:
        change_set = json.loads(Path(args.change_set).read_text(encoding="utf-8"))
        rows = _edges(args.dependents, Path.cwd())
        if args.command == "shortlist":
            output = shortlist(change_set, rows, args.objects, args.definitions)
        else:
            if not args.shortlist or not args.judgements:
                raise ValueError("check requires --shortlist and --judgements")
            output = check(json.loads(Path(args.shortlist).read_text(encoding="utf-8")),
                           _summaries(args.summaries or []), json.loads(Path(args.judgements).read_text(encoding="utf-8")),
                           rows, change_set)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count = len(output["candidates"]) if args.command == "shortlist" else sum(
            len(items) for direction in output.values() for key, items in direction.items() if key != "ask")
        print(f"{count} results: {destination}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        print("error: " + " ".join(str(error).splitlines()), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
