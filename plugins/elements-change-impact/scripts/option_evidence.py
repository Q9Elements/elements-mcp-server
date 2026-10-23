"""Add factual pre-pick evidence to card 02 options."""

from collections import Counter

from delta_keys import MIGRATION_KEYS
from plan_backlog import _migration
from population import population_value


def _kind(row):
    return row.get("sfType") or row.get("type") or "Unknown"


def _phase(value):
    return value if value and str(value).lower() not in {"unknown", "none"} else "phase unknown"


def _subtype(value):
    text = str(value or "unknown type").strip()
    return {"checkbox": "Boolean", "check box": "Boolean"}.get(text.lower(), text)


def option_evidence(options, candidates, dependents, *, kind, facts=(), dependents_gap=None, read_ids=()):
    """Preserve option order and attach counts from already held bundle rows."""
    if isinstance(options, dict):
        options = options.get("options")
    if not isinstance(options, list) or any(not isinstance(option, dict) for option in options):
        raise ValueError("options must be a list or an object with an options list")
    by_id = {row.get("nodeId"): row for row in candidates if row.get("nodeId")}
    fact_by_id = {row.get("inputNodeId") or row.get("nodeId") or (row.get("node") or {}).get("_id"): row for row in facts}
    read_ids = set(read_ids) | {row.get("inputNodeId") for row in dependents if row.get("inputNodeId")}
    if kind == "schema":
        counts = Counter(_subtype(row.get("subtype")) for row in candidates if _kind(row) == "Field")
    elif kind == "automation":
        seen = set()
        counts = Counter()
        for index, row in enumerate(candidates):
            if str(row.get("active")).lower() not in {"true", "1"}:
                continue
            row_kind = _kind(row)
            if row_kind in {"Process Builder Workflow", "Workflow Rule"}:
                if not (row.get("parentObject") or row.get("parent_object")):
                    continue
            elif row_kind not in {"Flow", "Apex Trigger"} or not row.get("triggerType"):
                continue
            identity = row.get("nodeId") or index
            if identity in seen:
                continue
            seen.add(identity)
            phase = _phase(row.get("triggerType") or row.get("recordTriggerType"))
            phases = ("RecordBeforeSave", "RecordAfterSave") if phase == "RecordBeforeAndAfterSave" else (phase,)
            for item in phases:
                counts[f"{row_kind} | {item}"] += 1
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
                migrations.append({"name": name, "type": element_type, "needed": existing_change and bool(_migration(delta)),
                                   "causes": [key for key in MIGRATION_KEYS if existing_change and delta.get(key)]})
                if not node_id or item.get("action") == "create":
                    value = "not applicable (new field)"
                else:
                    fact = fact_by_id.get(node_id, {})
                    node = fact.get("node") or fact
                    value = population_value(node.get("population") or candidate.get("population") or {},
                                             candidate.get("percent_filled"))
                population.append({"name": name, "type": element_type, "value": value})
            if kind == "schema" and element_type == "Field":
                subtype = _subtype((item.get("delta") or {}).get("type") or (item.get("delta") or {}).get("data_type") or candidate.get("subtype") or element.get("subtype"))
                own.append({"subtype": subtype, "count": counts[subtype], "total": sum(counts.values())})
            if kind == "automation" and element_type != "Field":
                phase = _phase((item.get("delta") or {}).get("phase") or element.get("triggerType") or candidate.get("triggerType") or candidate.get("recordTriggerType"))
                key = f"{element_type} | {phase}"
                own.append({"type": element_type, "phase": phase, "count": counts[key], "total": sum(counts.values())})
        evidence = {"blast_radius": f"not available, get_dependencies failed twice ({dependents_gap})" if dependents_gap else radius,
                    "migration": migrations, "population": population,
                    "pattern": {"counts": dict(counts), "option": own}}
        result.append({**option, "evidence": evidence})
    return result


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("option_evidence"))
