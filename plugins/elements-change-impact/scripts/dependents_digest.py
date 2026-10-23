"""Classify complete dependent rows with the shipped relation table."""

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from delta_keys import REPORT_CHANGE_KEYS, VALUE_ADDED_KEYS, VALUE_REMOVED_KEYS
from automation_state import AUTOMATION_TYPES, active_state


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "skills/analyze-change-impact/data/relation-kinds.csv"


def _true(value):
    return str(value).lower() in {"true", "1", "yes"}


def _relation_kind(kind, description):
    text = description.lower()
    if kind in {"Report", "List View"}:
        if any(word in text for word in ("filter", "bucket")):
            return "filter_or_bucket_or_cross_filter"
        if kind == "Report" and any(word in text for word in ("column", "group")):
            return "column_or_plain_grouping"
        if kind == "List View" and "column" in text:
            return "column"
    if kind == "Report Type":
        return "layout"
    if kind == "Page Layout":
        return "placement_or_required"
    if kind == "Record Type":
        return "restriction_or_values"
    if kind in {"Field", "Formula Field"}:
        if "formula" in text or kind == "Formula Field":
            return "formula"
        if "dependent" in text and "picklist" in text:
            return "dependent_picklist_mapping"
    if kind == "Path":
        return "value_mapping"
    return "other"


def _rule(rules, kind, relation, mode):
    table_kind = "Field" if kind == "Formula Field" else kind
    definition_modes = {"value_update", "type_update", "length_update", "label_rename", "api_name_rename", "deactivate", "value_delete"}
    table_mode = "value_or_type_update" if mode in definition_modes and kind in {
        "Flow", "Process Builder Workflow", "Apex Class", "Apex Trigger", "Validation Rule"} else (
            "value_or_type_update" if mode in {"value_update", "type_update", "length_update"} else mode)
    matches = [rule for rule in rules
               if rule["metadata_type"] in {table_kind, "*"}
               and rule["relation_kind"] in {relation, "any", "other"}
               and rule["mode"] in {table_mode, "any"}]
    return max(matches, key=lambda rule: (
        rule["metadata_type"] == table_kind,
        rule["relation_kind"] == relation,
        rule["mode"] == table_mode,
    ), default=None)


def _mode_for_delta(mode, change):
    if mode in {"label_rename", "api_name_rename", "deactivate", "value_delete"}:
        return "report_change"
    if mode in {"required_update", "placement_update"}:
        return "placement_or_required_update"
    if not change:
        return mode
    if change.get("action") == "delete":
        return "delete"
    delta = change.get("delta") or {}
    if any(delta.get(key) for key in REPORT_CHANGE_KEYS) or delta.get("active") is False:
        return "report_change"
    element = change.get("element") or {}
    if any(key in delta and delta[key] is not None
           and (delta[key] != element[key] if key in element else bool(delta[key]))
           for key in ("placement", "layout_placement", "required", "field_required")):
        return "placement_or_required_update"
    return mode


def digest(rows, *, mode, change_set=None, change_set_ids=(), rules_path=None, now=None):
    with (Path(rules_path) if rules_path else DEFAULT_RULES).open(encoding="utf-8", newline="") as handle:
        rules = list(csv.DictReader(handle))
    output = {"judgement": [], "units": [], "groups": [], "outgoing": []}
    groups = defaultdict(list)
    now = now or datetime.now(timezone.utc)
    changed = [item for item in (change_set or {}).get("elements", []) if item.get("action") in {"update", "delete"}]
    changed_by_id = {item.get("element", {}).get("nodeId"): item for item in changed if item.get("element", {}).get("nodeId")}
    for item in changed:
        element = item.get("element") or {}
        if (element.get("sfType") or element.get("type")) != "Custom Value":
            continue
        parent_id = (element.get("parentFieldNodeId") or element.get("parent_field_node_id")
                     or element.get("parent_field_id") or element.get("parentNodeId") or element.get("parent_node_id"))
        if parent_id:
            changed_by_id[parent_id] = item
    value_ids = {item.get("element", {}).get("nodeId") for item in changed
                 if (item.get("element", {}).get("sfType") or item.get("element", {}).get("type")) == "Custom Value"}
    value_ids.discard(None)
    value_rows = sorted(rows, key=lambda row: row.get("inputNodeId") not in value_ids) if value_ids else rows
    seen_dependents = set()
    for row in value_rows:
        if row.get("nodeId") in change_set_ids:
            continue
        if change_set is not None and not changed:
            continue
        if changed_by_id and row.get("inputNodeId") and row["inputNodeId"] not in changed_by_id:
            continue
        if row.get("direction") == "outgoing":
            output["outgoing"].append(row)
            continue
        kind = row.get("sfType") or row.get("type") or "Unknown"
        if kind in AUTOMATION_TYPES:
            state = active_state(row)
            row = {**row, "automation_status": "active" if state is True else "inactive" if state is False else "unknown"}
        identity = row.get("nodeId") or (kind, row.get("apiName") or row.get("name"))
        if value_ids and identity in seen_dependents:
            continue
        if value_ids:
            seen_dependents.add(identity)
        field_only_value_change = bool(value_ids and row.get("inputNodeId") not in value_ids
                                       and row.get("inputNodeId") in changed_by_id)
        relation = row.get("relationDescription") or ""
        relation_kind = _relation_kind(kind, relation)
        change = changed_by_id.get(row.get("inputNodeId")) or (changed[0] if len(changed) == 1 else None)
        rule_mode = _mode_for_delta(mode, change) if kind in {"Report", "List View", "Page Layout"} else mode
        rule = _rule(rules, kind, relation_kind, rule_mode)
        if field_only_value_change and rule and rule.get("decided_by") != "card":
            rule = {"relation_kind": relation_kind, "story": "no",
                    "report_text": "This reference does not identify the changed value."}
        if kind == "Record Type" and rule and (change or mode in {"label_rename", "api_name_rename"}):
            delta = (change or {}).get("delta") or {}
            if not any(delta.get(key) for key in (*VALUE_ADDED_KEYS, *VALUE_REMOVED_KEYS)):
                rule = {**rule, "story": "no", "report_text": "The available values follow the change automatically"}
        if rule and rule.get("decided_by") == "card":
            output["judgement"].append(row)
            continue
        if rule is None:
            unit = {**row, "disposition": "UNKNOWN", "reason": "relation rule not available"}
        else:
            story = _true(rule.get("story"))
            unit = {**row, "disposition": "UPDATE" if story else "NOT_IMPACTED",
                    "report_text": (rule.get("report_text") or "").replace("{component_type}", kind.lower())}
            if (kind == "Report" and relation_kind == "column_or_plain_grouping"
                    and (mode == "length_update" or (change or {}).get("delta", {}).get("length"))):
                unit["report_text"] = "The report needs no change."
        if kind == "Report" and row.get("lastUsed"):
            try:
                used = datetime.fromisoformat(row["lastUsed"].replace("Z", "+00:00"))
                unit["recent"] = now - timedelta(days=90) <= used <= now
            except ValueError:
                unit["recent"] = None
        output["units"].append(unit)
        groups[(kind, rule["relation_kind"] if rule else relation_kind, unit["disposition"])].append(unit)
    output["groups"] = [{"sfType": kind, "relation_kind": relation_kind, "disposition": disposition,
                          "count": len(members), "members": members,
                          "report_text": members[0].get("report_text", "")}
                         for (kind, relation_kind, disposition), members in groups.items()]
    return output


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("dependents_digest"))
