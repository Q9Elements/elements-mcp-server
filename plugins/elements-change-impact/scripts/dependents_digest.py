"""Classify complete dependent rows with the shipped relation table."""

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from delta_keys import REPORT_CHANGE_KEYS, VALUE_ADDED_KEYS, VALUE_REMOVED_KEYS, field_name, written_fields
from automation_state import is_automation, active_state
from cli_common import normalize_type


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "skills/analyze-change-impact/data/relation-kinds.csv"


def _true(value):
    return str(value).lower() in {"true", "1", "yes"}


def _relation_kind(kind, description):
    text = description.lower()
    if kind in {"Report", "Dashboard", "List View"}:
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
        "Flow", "Process Builder Workflow", "Workflow Rule", "Apex Class", "Apex Trigger", "Validation Rule"} else (
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


def combine_effects(rows):
    """Keep one component with its strongest effect and every source relation."""
    components = {}
    strength = {"NOT_IMPACTED": 0, "UNKNOWN": 1, "REVIEW": 2, "UPDATE": 3,
                "DELETE_CANDIDATE": 4, "DELETE": 5}
    for row in rows:
        identity = row.get("nodeId") or (normalize_type(row), row.get("apiName") or row.get("name"))
        components.setdefault(identity, []).append(row)
    result = []
    for sources in components.values():
        if len(sources) == 1:
            result.append(sources[0])
            continue
        strongest = max(sources, key=lambda item: strength.get(item.get("disposition"), 6))
        result.append({**strongest, "sources": sources,
                       "input_ids": list(dict.fromkeys(node_id for source in sources
                                                        for node_id in [*source.get("input_ids", []), source.get("inputNodeId")]
                                                        if node_id))})
    return result


def digest(rows, *, mode, change_set=None, change_set_ids=(), input_node_id=None, formula_input_ids=(), rules_path=None, now=None):
    with (Path(rules_path) if rules_path else DEFAULT_RULES).open(encoding="utf-8", newline="") as handle:
        rules = list(csv.DictReader(handle))
    output = {"judgement": [], "units": [], "groups": [], "outgoing": []}
    groups = defaultdict(list)
    now = now or datetime.now(timezone.utc)
    changed = [item for item in (change_set or {}).get("elements", []) if item.get("action") in {"update", "delete"}]
    if input_node_id is not None:
        changed = [item for item in changed if (item.get("element") or {}).get("nodeId") == input_node_id]
    changed_by_id = {item.get("element", {}).get("nodeId"): item for item in changed if item.get("element", {}).get("nodeId")}
    formula_input_ids = set(formula_input_ids)
    if formula_input_ids:
        if len(changed) != 1:
            raise ValueError("formula_input_ids require one changed element")
        root_id = changed[0]["element"]["nodeId"]
        rows = [{**row, "inputNodeId": root_id, "viaFormulaNodeId": row["inputNodeId"]}
                if row.get("inputNodeId") in formula_input_ids and row.get("direction") in (None, "", "incoming")
                else row for row in rows]
        rows.sort(key=lambda row: bool(row.get("viaFormulaNodeId")))
    for item in changed:
        element = item.get("element") or {}
        if normalize_type(element) != "Custom Value":
            continue
        parent_id = (element.get("parentFieldNodeId") or element.get("parent_field_node_id")
                     or element.get("parent_field_id") or element.get("parentNodeId") or element.get("parent_node_id"))
        if parent_id:
            changed_by_id[parent_id] = item
    value_ids = {item.get("element", {}).get("nodeId") for item in changed
                 if normalize_type(item.get("element", {})) == "Custom Value"}
    value_ids.discard(None)
    value_rows = sorted(rows, key=lambda row: row.get("inputNodeId") not in value_ids) if value_ids else rows
    for row in value_rows:
        if input_node_id is not None and row.get("inputNodeId") not in changed_by_id:
            continue
        if row.get("nodeId") in change_set_ids:
            continue
        if change_set is not None and not changed:
            continue
        if changed_by_id and row.get("inputNodeId") and row["inputNodeId"] not in changed_by_id:
            continue
        if row.get("direction") == "outgoing":
            output["outgoing"].append(row)
            continue
        kind = normalize_type(row) or "Unknown"
        row = {**row, "sfType": kind}
        if is_automation(row):
            state = active_state(row)
            row = {**row, "automation_status": "active" if state is True else "inactive" if state is False else "unknown"}
        field_only_value_change = bool(value_ids and row.get("inputNodeId") not in value_ids
                                       and row.get("inputNodeId") in changed_by_id)
        relation = row.get("relationDescription") or ""
        relation_kind = _relation_kind(kind, relation)
        change = changed_by_id.get(row.get("inputNodeId")) or (changed[0] if len(changed) == 1 else None)
        rule_mode = _mode_for_delta(mode, change) if kind in {"Report", "Dashboard", "List View", "Page Layout"} else mode
        if (kind in {"Report", "Dashboard", "List View"} and change
                and (change.get("delta") or {}).get("values_added") and rule_mode == mode
                and any(other is not change and other.get("action") in {"create", "update"}
                        and field_name(change.get("element") or {}) in written_fields(other)
                        for other in (change_set or {}).get("elements", []))):
            rule_mode = "value_add_written"
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
                    "decided_by": rule.get("decided_by", "script"), "relation_kind": relation_kind,
                    "report_text": (rule.get("report_text") or "").replace("{component_type}", kind.lower())}
            if (kind == "Report" and relation_kind == "column_or_plain_grouping"
                    and (mode == "length_update" or (change or {}).get("delta", {}).get("length"))):
                unit["report_text"] = "The report needs no change."
        if row.get("lastUsed"):
            try:
                used = datetime.fromisoformat(row["lastUsed"].replace("Z", "+00:00"))
                unit["recent"] = now - timedelta(days=90) <= used <= now
            except ValueError:
                unit["recent"] = None
        output["units"].append(unit)
    if value_ids or formula_input_ids:
        combined = combine_effects([*output["judgement"], *output["units"]])
        output["judgement"] = [row for row in combined if "disposition" not in row]
        output["units"] = [row for row in combined if "disposition" in row]
    for unit in output["units"]:
        groups[(unit["sfType"], unit["relation_kind"] if "relation_kind" in unit else
                _relation_kind(unit["sfType"], unit.get("relationDescription", "")), unit["disposition"])].append(unit)
    output["groups"] = [{"sfType": kind, "relation_kind": relation_kind, "disposition": disposition,
                          "count": len(members), "members": members,
                          "report_text": members[0].get("report_text", "")}
                         for (kind, relation_kind, disposition), members in groups.items()]
    return output


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("dependents_digest"))
