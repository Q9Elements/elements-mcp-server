"""Compact full inventory bundle rows for the options card."""

import json
from pathlib import Path
from cli_common import normalize_type, field_object
from population import population_text

SEPARATOR = "\x1f"


def _read_rows(source):
    if isinstance(source, (str, Path)):
        with Path(source).open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    return list(source)


def _named(row, targets):
    def kind(value):
        value = normalize_type(value)
        return "Object" if value in {"Object", "Standard Object", "Custom Object"} else value

    ids = {str(row[key]) for key in ("nodeId", "_id") if row.get(key)}
    names = {str(row[key]) for key in ("name", "apiName", "api_name") if row.get(key)}
    for target in targets:
        if not isinstance(target, dict):
            if str(target) in ids | names:
                return True
        elif target.get("nodeId") and str(target["nodeId"]) in ids:
            return True
        elif kind(target) and kind(target) == kind(row):
            parent = field_object(target)
            if parent and field_object(row) != parent:
                continue
            if names & {str(target[key]) for key in ("name", "apiName", "api_name") if target.get(key)}:
                return True
    return False


def candidate_digest(source, *, kind="schema", targets=(), object_name=None, facts=()):
    rows = _read_rows(source)
    seen = {row.get("nodeId") for row in rows if row.get("nodeId")}
    population_by_id = {}
    for fact in facts:
        node = fact.get("node") or fact
        node_id = node.get("nodeId") or node.get("_id") or fact.get("inputNodeId")
        population_by_id[node_id] = node.get("population") or {}
        sf = node.get("sf") or {}
        details = node.get("nodeDetails") or {}
        trigger = (node.get("automationExplainerDetails") or {}).get("triggerContext") or {}
        description = node.get("description") or ""
        held = {**node, "nodeId": node_id,
                     "sfType": node.get("sfType") or sf.get("type"),
                     "apiName": node.get("apiName") or sf.get("apiName"),
                     "subtype": node.get("subtype") or details.get("subtype"),
                     "active": details.get("active", node.get("active")),
                     "triggerType": details.get("triggerType", node.get("triggerType")),
                     "trigger_object": node.get("trigger_object") or node.get("triggerObject") or trigger.get("object"),
                     "events": node.get("events") or node.get("recordTriggerType") or trigger.get("events"),
                     "description": description.get("value", "") if isinstance(description, dict) else description}
        if not _named(held, targets):
            continue
        if node_id in seen:
            rows = [{**row, **{key: value for key, value in held.items() if value is not None}}
                    if row.get("nodeId") == node_id else row for row in rows]
        else:
            rows.append(held)
        seen.add(node_id)
    values = {}
    for row in rows:
        if normalize_type(row) == "Custom Value":
            values.setdefault(row.get("parentPath"), []).append(row)
    lines = []
    for row in rows:
        row_kind = normalize_type(row)
        named = _named(row, targets)
        if row_kind == "Custom Value" and not named:
            continue
        if kind == "schema" and targets and not named:
            continue
        if kind == "automation" and not named:
            active = str(row.get("active")).lower() in {"true", "1"}
            parent = field_object(row)
            edge_object = (row.get("trigger_object") or row.get("triggerObject")
                           or (row.get("inputApiName") if normalize_type(row.get("inputSfType")) in
                               {"Object", "Standard Object", "Custom Object"} else row.get("inputObject")))
            legacy = row_kind in {"Process Builder Workflow", "Workflow Rule"}
            on_object = not object_name or (parent == object_name if legacy else not edge_object or edge_object == object_name)
            automation = (legacy or (row_kind in {"Flow", "Apex Trigger"}
                                     and bool(str(row.get("triggerType") or "").strip())))
            if not (active and on_object and automation):
                continue
        name = row.get("name") or row.get("apiName") or "unnamed"
        api = row.get("api_name") or row.get("apiName") or name
        if row_kind == "Field":
            data_type = row.get("subtype") or "unknown type"
            field_values = values.get(row.get("identity"), [])
            if field_values:
                field_values.sort(key=lambda item: (item.get("active") is False, item.get("name") or ""))
                listed = [f"{item.get('name') or item.get('api_name')}{' (inactive)' if item.get('active') is False else ''}"
                          for item in field_values]
                data_type += ": " + ", ".join(listed)
            description = (row.get("description") or "").split(".", 1)[0].strip()
            active = "active" if str(row.get("active")).lower() in {"true", "1"} else "inactive" if row.get("active") not in (None, "") else "unknown"
            lines.append(SEPARATOR.join((str(row.get("nodeId") or ""), str(name), str(api), data_type, active,
                                         description + "." if description else "no description",
                                         population_text(population_by_id.get(row.get("nodeId")) or row.get("population") or {},
                                                         row.get("percent_filled")))))
        else:
            fields = row.get("written_fields") or row.get("writtenFields") or []
            if isinstance(fields, str):
                fields = [fields]
            events = row.get("events") or row.get("recordTriggerType") or ""
            if isinstance(events, (list, tuple)):
                events = ", ".join(map(str, events))
            lines.append(SEPARATOR.join(str(value) for value in (
                row.get("nodeId") or "", name, api, row_kind, "active" if str(row.get("active")).lower() in {"true", "1"} else "inactive" if row.get("active") not in (None, "") else "unknown",
                row.get("trigger_object") or row.get("triggerObject") or (row.get("parentPath") if row_kind == "Custom Value" else "") or "",
                row.get("phase") or row.get("triggerType") or "",
                events, ", ".join(fields))))
    return lines


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("candidate_digest"))
