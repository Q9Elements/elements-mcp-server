"""Create a deterministic story set before the card writes story prose."""

import json
import re
from collections import defaultdict
from pathlib import Path
from delta_keys import MIGRATION_KEYS


def _identity(element):
    return element.get("nodeId") or element.get("apiName") or element.get("name")


def _migration(delta):
    return any(delta.get(key) for key in MIGRATION_KEYS)


def _migration_criterion(name, delta):
    causes = []
    type_change = delta.get("type") or delta.get("data_type")
    if type_change:
        causes.append("changing the field type")
    if delta.get("values_removed"):
        causes.append("removing values")
    if delta.get("field_required"):
        causes.append("making the field required")
    if delta.get("restricted"):
        causes.append("restricting the allowed values")
    if len(causes) == 1 and type_change and str(type_change).lower() == "picklist":
        return f"Map every existing {name} value to a picklist value before the type change."
    if len(causes) == 1 and delta.get("field_required"):
        return f"Backfill blank {name} values before making the field required."
    if len(causes) == 1 and delta.get("restricted"):
        return f"Map existing unlisted {name} values to allowed values before restricting the picklist."
    if len(causes) > 2:
        cause_text = ", ".join(causes[:-1]) + ", and " + causes[-1]
    else:
        cause_text = " and ".join(causes)
    return f"Map existing {name} values before {cause_text}."


def _is_bare_confirmation(text):
    return bool(re.fullmatch(r"\s*(?:confirmed|yes(?:,? that(?:'|’)s right)?|that's right)[.!\s]*", text, re.IGNORECASE))


def _is_active(element):
    return str(element.get("active", "true")).lower() not in {"false", "inactive", "0"}


def _needs_late_deploy(delta):
    return any(delta.get(key) for key in ("restricted", *MIGRATION_KEYS))


def _type_source(unit, type_ids):
    source = unit.get("inputNodeId")
    if source is None and len(type_ids) == 1:
        return next(iter(type_ids))
    return source if source in type_ids else None


def _blocking_flag(element, findings):
    names = [element.get(key) for key in ("nodeId", "id", "name", "apiName") if element.get(key)]
    notes = []
    for finding in findings:
        if not isinstance(finding, dict) or not finding.get("blocking") or not finding.get("text"):
            continue
        text = finding["text"].casefold().replace("\\", "/")
        if finding.get("element") in names or any(re.search(r"(?<!\w)" + re.escape(name.casefold().replace("\\", "/")) + r"(?!\w)", text)
               for name in names):
            notes.append(finding["text"])
    return " ".join(notes)


def _story_units(units):
    """Keep recent reports named and group older report work by relation and outcome."""
    grouped = defaultdict(list)
    result = []
    for unit in units:
        if (unit.get("sfType") or unit.get("type")) != "Report" or unit.get("disposition") == "NOT_IMPACTED":
            result.append(unit)
            continue
        for member in unit.get("members", [unit]):
            member = {**member, "sfType": "Report", "disposition": unit["disposition"]}
            if member.get("recent") is True:
                result.append(member)
            else:
                grouped[(unit.get("relation_kind") or "other", unit["disposition"])].append(member)
    result.extend({"sfType": "Report", "relation_kind": relation, "disposition": disposition,
                   "count": len(members), "members": members}
                  for (relation, disposition), members in grouped.items())
    return result


def plan_backlog(change_set, units, *, delete_order=(), findings=(), answers=(), requested_stories=(), engagement=None):
    entries = []
    elements = change_set.get("elements") or []
    active = [row for row in elements if row.get("action") != "keep"]
    replacement_flows = {name for row in active if row.get("action") in {"create", "update"} and
                         row.get("element", {}).get("sfType") == "Flow"
                         for name in (_identity(row.get("element") or {}),
                                      (row.get("element") or {}).get("name"),
                                      (row.get("element") or {}).get("apiName")) if name}
    def has_replacement(row):
        marker = row.get("replacement") or (row.get("delta") or {}).get("replacement")
        if marker is True:
            return bool(replacement_flows)
        if isinstance(marker, str):
            return marker in replacement_flows
        if isinstance(marker, (list, tuple)):
            return any(name in replacement_flows for name in marker)
        return False
    if not active and elements:
        element = elements[0]["element"]
        entries.append({"kind": "adopt", "outcome": "update", "targets": [_identity(element)],
                        "summary": f"Adopt {element.get('name') or _identity(element)} as is", "fixed_criteria": ["Confirm the existing element meets the requested outcome."], "members": []})
    for row in active:
        element = row["element"]
        action = row["action"]
        name = element.get("name") or element.get("apiName") or "the element"
        criteria = []
        delta = row.get("delta") or {}
        if action == "delete":
            if _is_active(element) and (element.get("sfType") or element.get("type")) != "Field":
                criteria.append(f"Deactivate {name} before deletion.")
            if has_replacement(row) and _is_active(element):
                criteria.append("Confirm replacement flows are active and produce the same field results on a sample record before deletion.")
        if action == "update" and delta.get("length"):
            criteria.append(f"Export and resolve existing {name} values longer than {delta['length']} characters "
                            "before shortening the field.")
        if action == "update" and any(delta.get(key) for key in MIGRATION_KEYS if key != "length"):
            criteria.append(_migration_criterion(name, delta))
        entries.append({"kind": "change", "outcome": action, "targets": [_identity(element)],
                        "summary": f"{action.capitalize()} {name}", "fixed_criteria": criteria, "members": [],
                        "flag_note": _blocking_flag(element, findings),
                        "target_active": _is_active(element) if action == "delete" else None,
                        "deploy_after_dependents": action == "update" and _needs_late_deploy(delta)})
    for request in requested_stories:
        if not request.get("summary") or not request.get("request"):
            raise ValueError("requested story needs a summary and verbatim request")
        entries.append({"kind": "requested", "requested": True, "outcome": "requested", "targets": [],
                        "summary": request["summary"], "request": request["request"],
                        "fixed_criteria": [], "members": []})
    for unit in _story_units(units):
        disposition = unit.get("disposition")
        if disposition == "NOT_IMPACTED":
            continue
        if disposition not in {"UPDATE", "DELETE", "DELETE_CANDIDATE", "UNKNOWN", "REVIEW"}:
            raise ValueError(f"unsupported disposition: {disposition}")
        bucket = "count" in unit and "members" in unit
        if bucket:
            kind = unit.get("sfType") or "components"
            count = unit["count"]
            name = f"{count} {kind if count == 1 else kind + 's'}"
            target = f"bucket:{kind}:{unit.get('relation_kind') or ''}:{disposition}"
            members = [{**member, "api_name": member.get("name") or member.get("apiName") or member.get("api_name") or "",
                        "type": member.get("sfType") or member.get("type") or kind}
                       for member in unit["members"]]
        else:
            name = unit.get("name") or unit.get("apiName") or "the dependent"
            target = unit.get("nodeId") or name
            members = unit.get("members") or []
        criteria = []
        if disposition in {"DELETE", "DELETE_CANDIDATE"}:
            if (unit.get("sfType") or unit.get("type")) != "Field":
                criteria.append(f"Deactivate {name} before deletion.")
            if has_replacement(unit):
                criteria.append("Confirm replacement flows are active and produce the same field results on a sample record before deletion.")
            criteria.append("Confirm remaining dependents are removed or updated.")
        elif disposition in {"UNKNOWN", "REVIEW"}:
            criteria = ["Confirm the impact before changing this component."]
        deleting = disposition in {"DELETE", "DELETE_CANDIDATE"}
        entries.append({"kind": "dependent", "outcome": "delete" if deleting else "update",
                        "targets": [target], "summary": f"{'Remove' if deleting else 'Update'} {name}",
                        "sfType": unit.get("sfType") or unit.get("type"),
                        "fixed_criteria": criteria, "members": members,
                        "flag_note": f"impact not confirmed: {unit.get('reason', 'facts not returned')}" if disposition in {"UNKNOWN", "REVIEW"} else ""})
    older_reports = []
    for unit in units:
        if unit.get("sfType") != "Report" or unit.get("disposition") == "NOT_IMPACTED":
            continue
        for member in unit.get("members", [unit]):
            if member.get("recent") is True:
                continue
            older_reports.append({"api_name": member.get("name") or member.get("apiName") or "Report",
                                  "type": "Report", "elements_link": member.get("elements_link", "")})
    type_change_ids = {_identity(row.get("element", {})) for row in active
                       if row.get("action") == "update" and
                       ((row.get("delta") or {}).get("type") or (row.get("delta") or {}).get("data_type"))}
    def record_type_source(row):
        if (row.get("element") or {}).get("sfType") != "Record Type":
            return None
        delta = row.get("delta") or {}
        fields = {field for key in ("picklist_values_added", "picklist_values_removed")
                  for field in (delta.get(key) or {})}
        return next((item for item in active if _identity(item.get("element", {})) in type_change_ids and
                     (item.get("element") or {}).get("apiName") in fields), None)
    related_type_ids = {_type_source(unit, type_change_ids) for unit in units
                        if unit.get("disposition") == "UPDATE" and
                        (unit.get("sfType") or unit.get("type")) not in {"Report", "List View", "Record Type"}}
    rank = {(node.get("nodeId") if isinstance(node, dict) else node): index
            for index, node in enumerate(delete_order)}
    def phase(entry):
        if entry["kind"] == "requested":
            return -1
        if entry["outcome"] == "delete":
            return 3
        if entry["kind"] == "change" and entry["targets"][0] not in type_change_ids:
            row = next((item for item in active if _identity(item.get("element", {})) == entry["targets"][0]), {})
            if record_type_source(row):
                return 2
        if entry["kind"] == "dependent" and entry.get("sfType") in {"Report", "List View", "Record Type"}:
            return 2
        return 1 if entry.get("deploy_after_dependents") else 0
    entries.sort(key=lambda entry: (phase(entry), rank.get(entry["targets"][0], len(rank)) if entry["targets"] else len(rank)))
    late_entries = [entry for entry in entries if entry.get("deploy_after_dependents")]
    for entry in late_entries:
        if any(other["kind"] == "dependent" and other["outcome"] == "update" for other in entries):
            type_change = entry["targets"][0] in type_change_ids
            length_change = any(_identity(row.get("element", {})) == entry["targets"][0]
                                and (row.get("delta") or {}).get("length") for row in active)
            criterion = ("Shorten the field" if length_change else "Deploy the restriction" if any(_identity(row.get("element", {})) == entry["targets"][0]
                                                        and (row.get("delta") or {}).get("restricted") for row in active)
                         else "Deploy the type or value change")
            if type_change and entry["targets"][0] in related_type_ids:
                entry["fixed_criteria"].append("Deploy the type change with dependent updates in the same deployment.")
            elif not type_change:
                entry["fixed_criteria"].append(f"{criterion} after dependent fixes in earlier steps, or in the same release.")
    for index, entry in enumerate(entries, 1):
        entry.pop("deploy_after_dependents", None)
        entry["id"] = f"story-{index:03d}"
        entry["sequence"] = f"step {index} of {len(entries)}"
        entry["member_count"] = len(entry["members"])
        entry["members_file"] = f"members/{entry['id']}.csv" if entry["members"] else None
    type_steps = {entry["targets"][0]: index for index, entry in enumerate(entries, 1)
                  if entry["kind"] == "change" and entry["targets"][0] in type_change_ids}
    dependent_sources = {unit.get("nodeId"): _type_source(unit, type_change_ids) for unit in units
                         if unit.get("disposition") == "UPDATE" and
                         (unit.get("sfType") or unit.get("type")) not in {"Report", "List View", "Record Type"}}
    if type_steps:
        for entry in entries:
            if entry["kind"] == "dependent" and entry["outcome"] == "update" and entry["targets"][0] in dependent_sources:
                step = type_steps.get(dependent_sources[entry["targets"][0]])
                if step is not None:
                    entry["fixed_criteria"].append(f"Deploy in the same deployment as step {step}.")
    for entry in entries:
        if entry["kind"] != "dependent" or entry["outcome"] != "update" or entry.get("sfType") != "Record Type":
            continue
        source = next((unit.get("inputNodeId") for unit in units if unit.get("nodeId") == entry["targets"][0]), None)
        if source in type_steps:
            entry["fixed_criteria"].append(f"Deploy these available values with or after step {type_steps[source]}.")
    for entry in entries:
        if entry["kind"] != "change" or entry["targets"][0] in type_change_ids:
            continue
        row = next((item for item in active if _identity(item.get("element", {})) == entry["targets"][0]), {})
        source = record_type_source(row)
        if source:
            entry["fixed_criteria"].append(f"Deploy these available values with or after step {type_steps[_identity(source['element'])]}.")
    member_groups = ([{"name": "Older reports", "members_file": "members/older-reports.csv",
                       "member_count": len(older_reports), "members": older_reports}] if older_reports else [])
    plan = {"entries": entries, "member_groups": member_groups,
            "answers": [row["text"] for row in answers if row.get("kind") == "requirement"
                        and not _is_bare_confirmation(row["text"])]}
    if engagement is not None:
        root = Path(engagement)
        root.mkdir(parents=True, exist_ok=True)
        (root / "story-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("plan_backlog"))
