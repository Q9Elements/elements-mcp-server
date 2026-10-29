"""Screen active automation peers using the shipped order rules."""

import csv
import re
from pathlib import Path
from delta_keys import ENTRY_CONDITION_CHANGE_KEY
from automation_state import active_state
from cli_common import normalize_type, field_object


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "skills/analyze-change-impact/data/ooe-rules.csv"
CONDITIONS = {
    "same_phase_shared_write": "same phase and shared written field",
    "same_phase_write_read": "same phase and one writes a field the other reads",
    "same_phase_distinct_write": "same phase and both write triggering record on different fields",
    "different_phase": "different phases and both write triggering record",
    "different_phase_write_read": "different phases and one writes a field the other reads",
    "apex_peer": "two Apex triggers with overlapping events",
    "legacy_peer": "Workflow Rule or Process Builder peer",
    "unknown": "phase unknown or peer field facts unavailable",
    "no_shared_field": "known field facts share no written or read field",
}


def _phases(value):
    value = str(value or "").lower()
    if value == "processbuilder":
        return {"process_builder"}
    if "beforeandafter" in value:
        return {"before", "after"}
    return {phase for phase in ("before", "after") if phase in value}


def _phase(row):
    if normalize_type(row) == "Process Builder Workflow":
        return "ProcessBuilder"
    return row.get("phase") or row.get("triggerType") or row.get("recordTriggerType")


def _packaged(row):
    return (any(row.get(key) not in (None, "", False, "null", "None", "false", "{}")
                for key in ("managedPackage", "namespacePrefix", "namespace"))
            or bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*__.+", row.get("apiName") or "")))


def _fields(row, key):
    value = row.get(key) or []
    if isinstance(value, str):
        value = [value]
    return set(value)


def _events(row):
    value = str(row.get("events") or row.get("recordTriggerType") or "").lower()
    return {event for event in ("create", "update", "delete", "undelete") if event in value}


def _field_names(row, key, object_name):
    return {field if "." in field or not object_name else f"{object_name}.{field}"
            for field in _fields(row, key)}


def _automation(peer):
    kind = normalize_type(peer)
    if kind == "Flow":
        return bool(_phases(peer.get("triggerType") or peer.get("phase")))
    return kind in {"Apex Trigger", "Process Builder Workflow", "Workflow Rule"}


def screen(change, peers, *, deleted_ids=(), rules_path=None, edges=(), _baseline=False):
    with (Path(rules_path) if rules_path else DEFAULT_RULES).open(encoding="utf-8", newline="") as handle:
        rules = {row["condition"]: row for row in csv.DictReader(handle)}
    output = []
    trigger_object = change.get("trigger_object") or change.get("triggerObject") or field_object(change)
    if not trigger_object:
        trigger_object = next((field.split(".", 1)[0] for key in ("entry_fields", "written_fields")
                               for field in _fields(change, key) if "." in field), None)
    host_writes = (_field_names(change, "written_fields", trigger_object)
                   | _field_names(change, "existing_written_fields", trigger_object))
    for edge in edges:
        if (change.get("nodeId") and edge.get("inputNodeId") == change["nodeId"]
                and edge.get("direction") == "outgoing" and str(edge.get("write")).lower() in ("true", "1")
                and normalize_type(edge) == "Field"
                and edge.get("apiName")):
            parent = field_object(edge) or trigger_object
            field = str(edge["apiName"])
            host_writes.add(field if "." in field or not parent else f"{parent}.{field}")
    for peer in peers:
        if (active_state(peer) is not True or not _automation(peer)
                or peer.get("nodeId") in deleted_ids
                or (peer.get("nodeId") and peer.get("nodeId") == change.get("nodeId"))):
            continue
        peer_object = (peer.get("trigger_object") or peer.get("triggerObject")
                       or field_object(peer))
        if trigger_object and peer_object and peer_object != trigger_object:
            continue
        peer = dict(peer)
        peer["phase"] = _phase(peer)
        peer_edges = [edge for edge in edges if edge.get("inputNodeId") == peer.get("nodeId") and edge.get("direction") == "outgoing"]
        field_facts = (any(normalize_type(edge) == "Field" for edge in peer_edges)
                       or any(key in peer for key in ("written_fields", "read_fields", "entry_fields")))
        for edge_key, field_key in (("write", "written_fields"), ("read", "read_fields")):
            fields = [f"{field_object(edge)}.{edge.get('apiName')}" if field_object(edge) and "." not in str(edge.get("apiName") or "") else edge.get("apiName")
                      for edge in peer_edges if normalize_type(edge) == "Field"
                      and str(edge.get(edge_key)).lower() in ("true", "1") and edge.get("apiName")]
            if fields:
                peer[field_key] = list(_fields(peer, field_key) | set(fields))
        shared_phases = _phases(_phase(change)) & _phases(peer.get("phase"))
        writes = {field for field in host_writes
                  if not trigger_object or field.startswith(trigger_object + ".")}
        peer_writes = {field for field in _field_names(peer, "written_fields", trigger_object)
                       if not trigger_object or field.startswith(trigger_object + ".")}
        reads = _field_names(change, "read_fields", trigger_object) | _field_names(change, "entry_fields", trigger_object)
        peer_reads = _field_names(peer, "read_fields", trigger_object) | _field_names(peer, "entry_fields", trigger_object)
        shared_write_read = (writes & peer_reads) | (peer_writes & reads)
        if not writes and not (peer_writes & reads):
            continue
        field = None
        if not field_facts:
            condition = "unknown"
        elif normalize_type(peer) == "Workflow Rule" and not _phases(peer.get("phase")):
            condition = "legacy_peer"
        elif not _phases(_phase(change)) or not _phases(peer.get("phase")):
            condition = "unknown"
        elif shared_phases and writes & peer_writes:
            condition, field = "same_phase_shared_write", sorted(writes & peer_writes)[0]
        elif shared_phases and ((writes & peer_reads) or (peer_writes & reads)):
            condition, field = "same_phase_write_read", sorted((writes & peer_reads) | (peer_writes & reads))[0]
        elif shared_write_read:
            condition, field = "different_phase_write_read", sorted(shared_write_read)[0]
        elif shared_phases and normalize_type(change) == "Apex Trigger" and normalize_type(peer) == "Apex Trigger" and _events(change) & _events(peer):
            condition = "apex_peer"
        elif shared_phases and normalize_type(peer) == "Workflow Rule":
            condition = "legacy_peer"
        elif not shared_write_read and (not writes or not peer_writes):
            condition = "no_shared_field"
        elif shared_phases:
            condition = "same_phase_distinct_write"
        else:
            condition = "different_phase"
        rule = rules[CONDITIONS[condition]]
        reason = rule["reason_text"]
        if field and field not in reason:
            reason = f"{reason} ({field})"
        output.append({"peer": peer.get("name") or peer.get("apiName"), "phase": peer.get("phase"),
                       "status": rule["status"], "reason": reason})
        if not field_facts and _packaged(peer):
            output[-1]["note"] = "managed package: source not visible"
    if not _baseline:
        baseline = {**change, "phase": change.get("existing_phase", change.get("phase")), "written_fields": [],
                    "read_fields": change.get("existing_read_fields", []),
                    "entry_fields": change.get("existing_entry_fields", [])}
        old_blocks = {row["peer"] for row in screen(baseline, peers, deleted_ids=deleted_ids,
                                                   rules_path=rules_path, edges=edges, _baseline=True)
                      if row["status"] == "blocking"}
        comparisons = {peer.get("name") or peer.get("apiName"): peer.get("condition_comparison") or {}
                       for peer in peers}
        for row in output:
            comparison = comparisons.get(row["peer"], {})
            if row["status"] == "blocking" and comparison.get("proposed_overlap") is False:
                row["status"] = "manageable"
            conditions_known = (comparison.get("current_overlap") is True
                                and comparison.get("proposed_overlap") is True)
            entry_changed = ENTRY_CONDITION_CHANGE_KEY in change.get("delta", {})
            row["pre_existing"] = (row["status"] == "blocking" and row["peer"] in old_blocks
                                   and (conditions_known or (not entry_changed and not comparison)))
            if comparison.get("analyst_note"):
                row["analyst_note"] = comparison["analyst_note"]
    return output


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("ooe_screen"))
