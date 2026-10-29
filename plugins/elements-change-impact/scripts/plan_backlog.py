"""Create a deterministic story set before the card writes story prose."""

import json
import re
from collections import defaultdict
from pathlib import Path
from delta_keys import MIGRATION_KEYS, writes_added_value
from cli_common import normalize_type, field_object
from dependents_digest import combine_effects


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


def _card_judged(unit):
    kind = normalize_type(unit)
    return (unit.get("decided_by") == "card" or unit.get("reason") == "definition judgement"
            or kind in {"Flow", "Process Builder Workflow", "Apex Class", "Apex Trigger",
                        "Workflow Rule", "Validation Rule", "Formula Field"}
            or (kind == "Field" and (unit.get("relation_kind") == "formula"
                                    or "formula" in unit.get("relationDescription", "").lower())))


def _story_units(units):
    """Keep judged defects separate and group script decisions by type and relation."""
    judged = combine_effects([unit for unit in units if _card_judged(unit)])
    judged_by_id = {_identity(unit): unit for unit in judged}
    seen = set()
    grouped = defaultdict(list)
    result = []
    for unit in units:
        if _card_judged(unit):
            identity = _identity(unit)
            if identity in seen:
                continue
            seen.add(identity)
            unit = judged_by_id[identity]
        if unit.get("disposition") == "NOT_IMPACTED":
            continue
        if _card_judged(unit) and unit.get("disposition") in {"UPDATE", "DELETE", "DELETE_CANDIDATE"}:
            result.append(unit)
            continue
        kind = normalize_type(unit) or "Component"
        family = "Reports and Dashboards" if kind in {"Report", "Dashboard"} else kind
        relation = unit.get("relation_kind") or "other"
        key = (family, "any" if kind in {"Report", "Dashboard", "List View"} else relation)
        for member in unit.get("members", [unit]):
            facts = {key: value for key, value in unit.items() if key not in {"members", "count"}}
            grouped[key].append({**facts, **member, "sfType": normalize_type(member) or kind})
    for (kind, relation), members in grouped.items():
        members.sort(key=lambda member: (member.get("lastUsed") or member.get("last_used") or ""), reverse=True)
        members.sort(key=lambda member: member.get("recent") is not True)
        unique = {}
        for member in members:
            key = (member.get("nodeId") or member.get("apiName") or member.get("name"), member.get("sfType"))
            unique.setdefault(key, member)
        result.append({"sfType": kind, "relation_kind": relation, "disposition": "UPDATE", "review": True,
                       "count": len(unique), "members": list(unique.values()),
                       "flag_note": " ".join(dict.fromkeys(f"impact not confirmed: {member.get('reason', 'facts not returned')}"
                                                            for member in members if member.get("disposition") in {"UNKNOWN", "REVIEW"})),
                       "input_ids": list(dict.fromkeys(member.get("inputNodeId") for member in members if member.get("inputNodeId"))),
                       "filter_review": any(member.get("relation_kind") == "filter_or_bucket_or_cross_filter"
                                            for member in members)})
    return result


def _review_criteria(unit, elements):
    relevant = [row for row in elements if not unit.get("input_ids") or _identity(row.get("element") or {}) in unit["input_ids"]]
    fields = ", ".join(dict.fromkeys((row.get("element") or {}).get("apiName") or
                                    (row.get("element") or {}).get("name") or "the changed field" for row in relevant)) or "the changed field"
    added = [value for row in relevant for value in (row.get("delta") or {}).get("values_added", [])]
    values = ", ".join(map(str, dict.fromkeys(added)))
    if unit.get("filter_review") and values:
        return [f"Each component's owner records whether it should count {values} records in the members file.",
                f"Where the owner says yes, every {fields} filter meant to count these records includes {values}.",
                f"For a sample period after the first {values} record exists, each component's total equals a direct count of records whose {fields} is any value its updated filter includes; a component that excludes {values} is lower by exactly the count of {values} records."]
    return [f"Each listed component is checked for its use of {fields} and updated or marked no change in the members file."]


def plan_backlog(change_set, units, *, delete_order=(), findings=(), answers=(), requested_stories=(), regression=(), assumptions=(), engagement=None):
    delete_order = delete_order or ()
    requested_stories = requested_stories or ()
    regression = regression or ()
    assumptions = assumptions or ()
    entries = []
    elements = change_set.get("elements") or []
    active = [row for row in elements if row.get("action") != "keep"]
    replacement_flows = {name for row in active if row.get("action") in {"create", "update"} and
                         normalize_type(row.get("element", {})) == "Flow"
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
        entries.append({"kind": "change", "outcome": "update", "targets": [_identity(element)],
                        "public_targets": [element.get("name") or element.get("apiName") or "the existing element"],
                        "summary": f"Adopt {element.get('name') or element.get('apiName') or 'the existing element'} as is", "fixed_criteria": ["Confirm the existing element meets the requested outcome."], "members": []})
    for row in active:
        element = row["element"]
        action = row["action"]
        name = element.get("name") or element.get("apiName") or "the element"
        criteria = []
        delta = row.get("delta") or {}
        if action == "delete":
            if _is_active(element) and normalize_type(element) != "Field":
                criteria.append(f"Deactivate {name} before deletion.")
            if has_replacement(row) and _is_active(element):
                criteria.append("Confirm replacement flows are active and produce the same field results on a sample record before deletion.")
        if action == "update" and delta.get("length"):
            criteria.append(f"Export and resolve existing {name} values longer than {delta['length']} characters "
                            "before shortening the field.")
        if action == "create" and normalize_type(element) == "Field" and delta.get("field_required"):
            criteria.append(_migration_criterion(name, {"field_required": True}))
        if action == "update" and any(delta.get(key) for key in MIGRATION_KEYS if key != "length"):
            criteria.append(_migration_criterion(name, delta))
        entries.append({"kind": "change", "outcome": action, "targets": [_identity(element)],
                        "public_targets": [element.get("name") or element.get("apiName") or "the element"],
                        "summary": f"{action.capitalize()} {name}", "fixed_criteria": criteria, "members": [],
                        "flag_note": _blocking_flag(element, findings),
                        "target_active": _is_active(element) if action == "delete" else None,
                        "deploy_after_dependents": (action == "update" and _needs_late_deploy(delta)) or writes_added_value(row, active)})
    for request in requested_stories:
        if not request.get("summary") or not request.get("request"):
            raise ValueError("requested story needs a summary and verbatim request")
        entries.append({"kind": "change", "requested": True, "outcome": "requested", "targets": [],
                        "summary": request["summary"], "request": request["request"],
                        "fixed_criteria": [], "members": []})
    story_units = _story_units(units)
    objects_by_name = defaultdict(set)
    for unit in story_units:
        name = unit.get("name") or unit.get("apiName") or "the dependent"
        object_name = field_object(unit)
        if object_name:
            objects_by_name[name].add(object_name)
    for unit in story_units:
        disposition = unit.get("disposition")
        if disposition == "NOT_IMPACTED":
            continue
        if disposition not in {"UPDATE", "DELETE", "DELETE_CANDIDATE", "UNKNOWN", "REVIEW"}:
            raise ValueError(f"unsupported disposition: {disposition}")
        bucket = "count" in unit and "members" in unit
        if bucket:
            kind = normalize_type(unit) or "components"
            count = unit["count"]
            name = f"{count} {kind if count == 1 or kind.endswith('s') else kind + 's'}"
            target = f"bucket:{kind}:{unit.get('relation_kind') or ''}:{disposition}"
            members = [{**member, "name": member.get("name") or member.get("apiName") or member.get("api_name") or "",
                        "api_name": member.get("apiName") or member.get("api_name") or "",
                        "type": normalize_type(member) or kind,
                        "last_used": member.get("lastUsed") or member.get("last_used") or ""}
                       for member in unit["members"]]
        else:
            name = unit.get("name") or unit.get("apiName") or "the dependent"
            objects = objects_by_name.get(name, set())
            object_name = field_object(unit)
            if len(objects) > 1 and object_name:
                name = f"{name} ({object_name})"
            target = unit.get("nodeId") or name
            members = unit.get("members") or []
        criteria = _review_criteria(unit, active) if unit.get("review") else []
        if disposition in {"DELETE", "DELETE_CANDIDATE"}:
            if normalize_type(unit) != "Field":
                criteria.append(f"Deactivate {name} before deletion.")
            if has_replacement(unit):
                criteria.append("Confirm replacement flows are active and produce the same field results on a sample record before deletion.")
            criteria.append("Confirm remaining dependents are removed or updated.")
        elif disposition in {"UNKNOWN", "REVIEW"}:
            criteria = ["Confirm the impact before changing this component."]
        deleting = disposition in {"DELETE", "DELETE_CANDIDATE"}
        entries.append({"kind": "review" if unit.get("review") else "defect", "outcome": "delete" if deleting else "update",
                        "targets": [target], "public_targets": [name], "summary": f"{'Review' if unit.get('review') else 'Remove' if deleting else 'Update'} {name}",
                        "sfType": normalize_type(unit),
                        "input_ids": unit.get("input_ids") or [unit.get("inputNodeId")],
                        "sources": unit.get("sources", [unit]),
                        "fixed_criteria": criteria, "members": members,
                        "flag_note": unit.get("flag_note") or (f"impact not confirmed: {unit.get('reason', 'facts not returned')}" if disposition in {"UNKNOWN", "REVIEW"} else "")})
    if regression:
        criteria = []
        for interaction in regression:
            if (not isinstance(interaction, dict) or interaction.get("kind") not in
                    {"duplicate_creators", "shared_parent_lock", "shared_write"}
                    or not isinstance(interaction.get("outcome"), str) or not interaction["outcome"].strip()):
                raise ValueError("regression interaction needs a supported kind and an end-to-end outcome")
            criteria.append(interaction["outcome"])
        entries.append({"kind": "regression", "outcome": "test", "targets": [],
                        "summary": "Verify cross-story outcomes", "fixed_criteria": criteria, "members": [],
                        "input_ids": list(dict.fromkeys(element for interaction in regression
                                                         for element in interaction.get("elements", [])))})
    type_change_ids = {_identity(row.get("element", {})) for row in active
                       if row.get("action") == "update" and
                       ((row.get("delta") or {}).get("type") or (row.get("delta") or {}).get("data_type"))}
    def record_type_source(row):
        if normalize_type(row.get("element") or {}) != "Record Type":
            return None
        delta = row.get("delta") or {}
        fields = {field for key in ("picklist_values_added", "picklist_values_removed")
                  for field in (delta.get(key) or {})}
        return next((item for item in active if _identity(item.get("element", {})) in type_change_ids and
                     (item.get("element") or {}).get("apiName") in fields), None)
    related_type_ids = {_type_source(unit, type_change_ids) for unit in units
                        if unit.get("disposition") == "UPDATE" and
                        normalize_type(unit) not in {"Report", "List View", "Record Type"}}
    rank = {(node.get("nodeId") if isinstance(node, dict) else node): index
            for index, node in enumerate(delete_order)}
    def phase(entry):
        if entry["kind"] == "regression":
            return 5
        if entry.get("requested"):
            return -1
        if entry["kind"] == "change":
            row = next((item for item in active if _identity(item.get("element", {})) == entry["targets"][0]), {})
            if writes_added_value(row, active):
                return 4.5
        if entry["kind"] == "review":
            return 4
        if entry["outcome"] == "delete":
            return 3
        if entry["kind"] == "change" and entry["targets"][0] not in type_change_ids:
            row = next((item for item in active if _identity(item.get("element", {})) == entry["targets"][0]), {})
            if record_type_source(row):
                return 2
        if entry["kind"] in {"defect", "review"} and entry.get("sfType") in {"Report", "List View", "Record Type"}:
            return 2
        if entry.get("deploy_after_dependents"):
            return 2
        return 1 if entry["kind"] == "defect" else 0
    entries.sort(key=lambda entry: (phase(entry), rank.get(entry["targets"][0], len(rank)) if entry["targets"] else len(rank)))
    late_entries = [entry for entry in entries if entry.get("deploy_after_dependents")]
    for entry in late_entries:
        if any(other["kind"] in {"defect", "review"} and other["outcome"] == "update" for other in entries):
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
                  if entry["kind"] == "change" and entry["targets"] and entry["targets"][0] in type_change_ids}
    type_names = {_identity(row["element"]): row["element"].get("apiName") or row["element"].get("name") or "the field"
                  for row in active if _identity(row["element"]) in type_steps}
    dependent_sources = {unit.get("nodeId"): _type_source(unit, type_change_ids) for unit in units
                         if unit.get("disposition") == "UPDATE" and
                         normalize_type(unit) not in {"Report", "List View", "Record Type"}}
    if type_steps:
        for entry in entries:
            if entry["kind"] in {"defect", "review"} and entry["outcome"] == "update" and entry["targets"][0] in dependent_sources:
                step = type_steps.get(dependent_sources[entry["targets"][0]])
                if step is not None:
                    entry["fixed_criteria"].append(f"Deploy in the same deployment as step {step}.")
    for entry in entries:
        if entry["kind"] not in {"defect", "review"} or entry["outcome"] != "update" or entry.get("sfType") != "Record Type":
            continue
        sources = [source for source in entry.get("input_ids", []) if source in type_steps]
        if len(sources) == 1:
            entry["fixed_criteria"].append(f"Deploy these available values with or after step {type_steps[sources[0]]}.")
        elif sources:
            deployments = "; ".join(f"{type_names[source]} with or after step {type_steps[source]}" for source in sources)
            entry["fixed_criteria"].append(f"Deploy these available values for each field: {deployments}.")
    for entry in entries:
        if entry["kind"] != "change" or not entry["targets"] or entry["targets"][0] in type_change_ids:
            continue
        row = next((item for item in active if _identity(item.get("element", {})) == entry["targets"][0]), {})
        source = record_type_source(row)
        if source:
            entry["fixed_criteria"].append(f"Deploy these available values with or after step {type_steps[_identity(source['element'])]}.")
    for entry in entries:
        entry["assumptions"] = []
        references = set(entry["targets"]) | set(entry.get("input_ids") or [])
        for row in elements:
            element = row.get("element") or {}
            aliases = {element.get(key) for key in ("nodeId", "name", "apiName") if element.get(key)}
            if references.intersection(aliases):
                references.update(aliases)
        for item in assumptions:
            if (not isinstance(item, dict) or not isinstance(item.get("question"), str)
                    or not isinstance(item.get("assumption"), str) or not item["assumption"].strip()
                    or not isinstance(item.get("elements", []), list)):
                raise ValueError("assumptions need question, assumption and elements")
            if (not item.get("elements") and entry["kind"] == "change") or references.intersection(item.get("elements") or []):
                entry["assumptions"].append(item["assumption"])
    member_groups = []
    plan = {"entries": entries, "member_groups": member_groups,
            "flags": [finding["text"] for finding in findings if isinstance(finding, dict) and finding.get("blocking") and finding.get("text")],
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
