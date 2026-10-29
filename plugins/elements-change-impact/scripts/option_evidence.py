"""Add factual pre-pick evidence to card 02 options."""

from collections import Counter

from delta_keys import MIGRATION_KEYS
from plan_backlog import _migration
from population import population_value
from cli_common import normalize_type, field_object
from ooe_screen import _phase as automation_phase


def _kind(row):
    return normalize_type(row) or "Unknown"


def _object(row):
    return (row.get("trigger_object") or row.get("triggerObject") or field_object(row) or row.get("inputObject")
            or (row.get("inputApiName") if normalize_type(row.get("inputSfType")) in
                {"Object", "Standard Object", "Custom Object"} else None))


def _inventory_object(row):
    if normalize_type(row.get("inputSfType")) in {"Object", "Standard Object", "Custom Object"}:
        return row.get("inputApiName") or row.get("inputObject")
    if row.get("inputNodeId") or row.get("inputSfType"):
        return None
    return _object(row)


def _phase(value):
    return value if value and str(value).lower() not in {"unknown", "none"} else "phase unknown"


def _subtype(value):
    text = str(value or "unknown type").strip()
    return {"checkbox": "Boolean", "check box": "Boolean"}.get(text.lower(), text)


def option_evidence(options, candidates, dependents, *, kind, facts=(), fields=(), dependents_gap=None, read_ids=(), inventory_objects=()):
    """Preserve option order and attach counts from already held bundle rows."""
    if isinstance(options, dict):
        options = options.get("options")
    if not isinstance(options, list) or any(not isinstance(option, dict) for option in options):
        raise ValueError("options must be a list or an object with an options list")
    for option in options:
        elements = option.get("elements", [])
        if not isinstance(elements, list) or any(not isinstance(item, dict) for item in elements):
            raise ValueError("option elements must be a list of objects")
        for item in elements:
            if any(item.get(key) is not None and not isinstance(item[key], dict) for key in ("element", "delta")):
                raise ValueError("option element and delta must be objects")
    for label, rows in (("candidate", candidates), ("dependents", dependents), ("target_facts", facts), ("fields", fields)):
        if not isinstance(rows, (list, tuple)) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"{label} must contain row objects")
    by_id = {row.get("nodeId"): row for row in candidates if row.get("nodeId")}
    fact_by_id = {row.get("inputNodeId") or row.get("nodeId") or (row.get("node") or {}).get("_id"): row for row in facts}
    field_by_id = {row["nodeId"]: row for row in fields if row.get("nodeId") and _kind(row) == "Field"}
    read_ids = set(read_ids) | {row.get("inputNodeId") for row in dependents if row.get("inputNodeId")}
    object_counts = {name: Counter() for name in inventory_objects}
    if kind == "schema":
        counts = Counter(_subtype(row.get("subtype")) for row in candidates if _kind(row) == "Field")
    elif kind == "automation":
        seen = set()
        counts = Counter()
        for index, row in enumerate(candidates):
            inventory_object = _inventory_object(row)
            if inventory_object and row.get("direction") in (None, "", "incoming"):
                object_counts.setdefault(inventory_object, Counter())
            if row.get("direction") not in (None, "", "incoming"):
                continue
            if row.get("inputNodeId") or row.get("inputSfType"):
                if not inventory_object or _object(row) != inventory_object:
                    continue
            if str(row.get("active")).lower() not in {"true", "1"}:
                continue
            row_kind = _kind(row)
            if row_kind in {"Process Builder Workflow", "Workflow Rule"}:
                if not _object(row):
                    continue
            elif row_kind not in {"Flow", "Apex Trigger"} or not row.get("triggerType"):
                continue
            identity = row.get("nodeId") or index
            if identity in seen:
                continue
            seen.add(identity)
            phase = _phase(automation_phase(row))
            phases = ("RecordBeforeSave", "RecordAfterSave") if phase == "RecordBeforeAndAfterSave" else (phase,)
            for item in phases:
                counts[f"{row_kind} | {item}"] += 1
                if inventory_object:
                    object_counts[inventory_object][f"{row_kind} | {item}"] += 1
    else:
        raise ValueError("kind must be schema or automation")
    result = []
    for option in options:
        radius, migrations, population, own = [], [], [], []
        for item in option.get("elements", []):
            element = item.get("element") or {}
            node_id = element.get("nodeId")
            if item.get("action") != "create" and not node_id:
                continue
            candidate = by_id.get(node_id, {})
            name = element.get("name") or candidate.get("name") or element.get("apiName") or "unnamed element"
            element_type = _kind(element) if _kind(element) != "Unknown" else _kind(candidate)
            if node_id and item.get("action") != "create" and not dependents_gap:
                totals = Counter(_kind(row) for row in dependents
                                 if row.get("inputNodeId") == node_id
                                 and row.get("direction") in (None, "", "incoming"))
                radius.append({"name": name, "type": element_type, "totals": dict(totals),
                               "summary": "dependents not read" if node_id not in read_ids else
                               ("nothing references it" if not totals else "")})
            if element_type == "Field":
                delta = item.get("delta") or {}
                existing_change = bool(node_id) and item.get("action") == "update"
                causes = [key for key in MIGRATION_KEYS if delta.get(key) and
                          (existing_change or (item.get("action") == "create" and key == "field_required"))]
                migrations.append({"name": name, "type": element_type, "needed": bool(causes),
                                   "causes": causes})
                if not node_id or item.get("action") == "create":
                    value = "not applicable (new field)"
                else:
                    fact = fact_by_id.get(node_id, {})
                    node = fact.get("node") or fact
                    value = "not known"
                    for source in (node, candidate, field_by_id.get(node_id, {})):
                        value = population_value(source.get("population") or {}, source.get("percent_filled"))
                        if value != "not known":
                            break
                population.append({"name": name, "type": element_type, "value": value})
            if kind == "schema" and element_type == "Field":
                subtype = _subtype((item.get("delta") or {}).get("type") or (item.get("delta") or {}).get("data_type") or candidate.get("subtype") or element.get("subtype"))
                own.append({"subtype": subtype, "count": counts[subtype], "total": sum(counts.values())})
            if kind == "automation" and element_type != "Field":
                delta = item.get("delta") or {}
                host = {**candidate, **element, "sfType": element_type}
                phase = _phase(automation_phase({**host, "phase": delta.get("phase") or automation_phase(host)}))
                key = f"{element_type} | {phase}"
                comparable = object_counts.get(_object(delta) or _object(host))
                own.append({"type": element_type, "phase": phase,
                            "count": comparable[key] if comparable is not None else "not known",
                            "total": sum(comparable.values()) if comparable is not None else "not known"})
        evidence = {"blast_radius": f"not available, get_dependencies failed twice ({dependents_gap})" if dependents_gap else radius,
                    "migration": migrations, "population": population,
                    "pattern": {"counts": dict(counts), "option": own}}
        result.append({**option, "evidence": evidence})
    return result


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("option_evidence"))
