"""Call the fire chain once per target and digest its bundle files."""

import csv
import json
from collections import Counter
from pathlib import Path


def _events(value):
    text = " ".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value or "")
    text = text.lower()
    return {event for event in ("create", "update", "delete", "undelete") if event in text}


def _api_name(value):
    if isinstance(value, dict):
        value = value.get("apiName") or value.get("api_name")
    if value is not None and not isinstance(value, str):
        raise ValueError("field API name must be a string or an {apiName} object")
    return value or ""


def targets(change_set, write_edges, definitions=()):
    """Return added or moved active automation writes for impact calls."""
    result = []
    creates_by_id = {record.get("nodeId"): set(record.get("created_objects") or [])
                     for record in definitions if record.get("nodeId")}
    for row in change_set.get("elements", []):
        if row.get("action") not in {"create", "update", "delete"}:
            continue
        element = row.get("element") or {}
        delta = row.get("delta") or {}
        kind = element.get("sfType") or element.get("type")
        if kind == "Custom Value":
            object_name = element.get("parentObject") or element.get("parent_object")
            parent_field = (element.get("parentFieldApiName") or element.get("parent_field_api_name")
                            or element.get("parentField") or element.get("parent_field"))
            parent_field = _api_name(parent_field)
            if not object_name or not parent_field:
                raise ValueError("parent object and field required for Custom Value")
            result.append({"object": object_name, "writtenFields": [parent_field.rsplit(".", 1)[-1]], "operation": "update"})
            continue
        if row.get("action") == "delete":
            continue
        if kind == "Field":
            if row.get("action") == "create":
                continue
            api_name = _api_name(element.get("apiName"))
            identity_parts = (element.get("identity") or "").split(".")
            identity_object = (identity_parts[identity_parts.index("fields") - 1]
                               if "fields" in identity_parts and identity_parts.index("fields") > 0 else None)
            object_name = (element.get("parentObject") or element.get("parent_object")
                           or identity_object or (api_name.split(".", 1)[0] if "." in api_name else None))
            if not object_name:
                raise ValueError(f"parent object required for field {api_name or element.get('name') or 'unnamed'}")
            field_name = api_name.rsplit(".", 1)[-1]
            if field_name:
                result.append({"object": object_name, "writtenFields": [field_name], "operation": "update"})
            continue
        fields = delta.get("written_fields", delta.get("writtenFields", []))
        if isinstance(fields, str):
            fields = [fields]
        if not isinstance(fields, (list, tuple)):
            raise ValueError("written_fields must be API-name strings or {apiName} objects")
        fields = [field if isinstance(field, str) else
                  (f"{field['object']}.{field['apiName']}" if field.get("object") else field["apiName"])
                  if isinstance(field, dict) and isinstance(field.get("apiName"), str)
                  and (not field.get("object") or isinstance(field.get("object"), str)) else None for field in fields]
        if any(not field for field in fields):
            raise ValueError("written_fields must be API-name strings or {apiName} objects")
        if delta.get("phase") is not None and not isinstance(delta["phase"], str):
            raise ValueError("phase must be a string")
        object_name = (delta.get("trigger_object") or element.get("trigger_object") or element.get("triggerObject")
                       or element.get("parentObject") or element.get("parent_object") or element.get("object"))
        if any("." not in field for field in fields) and not object_name:
            raise ValueError("written fields require a trigger object")
        created_objects = (set(delta.get("created_objects") or []) if row.get("action") == "create"
                           else creates_by_id.get(element.get("nodeId"), set()))
        host_active = str(element.get("active", "true")).lower() in {"true", "1"}
        current = {(f"{edge.get('parentObject') or object_name}.{edge.get('apiName')}"
                    if "." not in str(edge.get("apiName") or "") else edge.get("apiName")) for edge in write_edges
                   if host_active and edge.get("inputNodeId") == element.get("nodeId")
                   and edge.get("sfType") == "Field"
                   and str(edge.get("write")).lower() in {"true", "1"}
                   and str(edge.get("active") or "true").lower() in {"true", "1"}}
        current_phase = element.get("phase") or element.get("triggerType")
        current_object = (element.get("trigger_object") or element.get("triggerObject") or element.get("parentObject")
                          or element.get("parent_object") or element.get("object"))
        current_events = element.get("events") or element.get("recordTriggerType")
        moved = (bool(current_phase and delta.get("phase") and delta["phase"] != current_phase)
                 or bool(current_object and delta.get("trigger_object") and delta["trigger_object"] != current_object)
                 or bool(current_events and delta.get("events") and _events(delta["events"]) != _events(current_events)))
        qualified = [field if "." in field else f"{object_name}.{field}" for field in fields]
        added = list(dict.fromkeys(fields if moved or row.get("action") == "create" else
                                   [field for field, full in zip(fields, qualified) if full not in current]))
        grouped = {}
        for field in added:
            target_object, separator, field_name = field.partition(".")
            target_object = target_object if separator else object_name
            field_name = field_name if separator else field
            operation = "insert" if target_object in created_objects else "update"
            names = grouped.setdefault((target_object, operation), [])
            if field_name not in names:
                names.append(field_name)
        for (target_object, operation), names in grouped.items():
            result.append({"object": target_object, "writtenFields": names, "operation": operation})
        if row.get("action") == "create":
            for created_object in sorted(created_objects - {key[0] for key in grouped if key[1] == "insert"}):
                result.append({"object": created_object, "writtenFields": [], "operation": "insert"})
    unique = {}
    for item in result:
        fields = unique.setdefault((item["object"], item["operation"]), [])
        fields.extend(field for field in item["writtenFields"] if field not in fields)
    return [{"object": object_name, "writtenFields": fields, "operation": operation, "estimatedVolume": 1000}
            for (object_name, operation), fields in unique.items()]


def run_targets(targets, call):
    """Give each target an independent server budget and retain every result."""
    output = []
    for target in targets:
        request = {"targets": [{key: value for key, value in target.items() if value is not None}]}
        output.append(call(request))
    return output


def _rows(root, name):
    path = root / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(bundle, *, status="complete", touched_fields=(), change_set=None):
    roots = [Path(item) for item in bundle] if isinstance(bundle, (list, tuple)) else [Path(bundle)]
    partial = status == "partial"
    reasons = set()
    groups = {"field-matched": [], "Apex assumed": [], "fires on every save": [],
              "validation rule": [], "assignment rule": []}
    next_hops = Counter()
    trigger_checks = []
    locks = []
    changed = (change_set or {}).get("elements", [])
    deleted = [row.get("element") or {} for row in changed if row.get("action") == "delete"]
    deleted_ids = {row.get("nodeId") for row in deleted}
    deleted_names = {row[key] for row in deleted for key in ("name", "apiName") if row.get(key)}
    related_objects = set()
    for item in changed:
        if item.get("action") not in {"create", "update"}:
            continue
        delta = item.get("delta") or {}
        writes = delta.get("written_fields") or delta.get("writtenFields") or []
        if isinstance(writes, str):
            writes = [writes]
        related_objects.update(str(field).split(".", 1)[0] for field in writes if "." in str(field))
        if any(str(field).endswith(".WhatId") for field in writes):
            related_objects.add(delta.get("trigger_object") or delta.get("triggerObject"))
    related_objects.discard(None)
    for root in roots:
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        coverage_path = root / "coverage.json"
        coverage = (manifest.get("coverage") or {}) if manifest_path.exists() else (
            json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {})
        partial = partial or manifest.get("status") == "partial" or coverage.get("absenceIsEvidence") is not True
        reasons.update(reason for branch in coverage.get("incompleteBranches", []) for reason in branch.get("stopReasons", []))
        variant_fields = {}
        response_path = root / "response.json"
        if response_path.exists():
            response = json.loads(response_path.read_text(encoding="utf-8"))
            for target in response.get("targets", []):
                for chain in target.get("fireChain", []):
                    for digest_row in chain.get("digest", []):
                        entity = (digest_row.get("entity") or {}).get("apiName")
                        for variant in digest_row.get("variants", []):
                            automation = (variant.get("firingAutomation") or {}).get("apiName")
                            fields = [field.get("apiName") if isinstance(field, dict) else field
                                      for field in (variant.get("triggerFields") or [])]
                            variant_fields.setdefault((automation, entity), set()).update(field for field in fields if field)
            for (automation, entity), fields in variant_fields.items():
                if automation and automation not in deleted_names and fields & set(touched_fields):
                    trigger_checks.append(automation)
        for row in _rows(root, "automations.csv"):
            if str(row.get("active")).lower() not in ("true", "1"):
                continue
            if row.get("nodeId") in deleted_ids or row.get("name") in deleted_names or row.get("apiName") in deleted_names:
                continue
            kind = (row.get("kind") or row.get("type") or "").lower()
            if "validation" in kind:
                group = "validation rule"
            elif "assignment" in kind:
                group = "assignment rule"
            elif str(row.get("matchedFields") or "").strip():
                group = "field-matched"
            elif str(row.get("partialReadsAssumed") or "").lower() in ("true", "1"):
                group = "Apex assumed"
            else:
                group = "fires on every save"
            groups[group].append(row.get("name") or row.get("apiName") or "unnamed")
        for row in _rows(root, "fire-chain-digest.csv"):
            if row.get("firingAutomation") in deleted_names:
                continue
            if str(row.get("minDepth") or "") == "1" and row.get("entityApiName"):
                next_hops[row["entityApiName"]] += 1
        for row in _rows(root, "lock-rows.csv"):
            possible = (row.get("parentObjects") or "").split()
            selected = [name for name in possible if name in related_objects and name != row.get("target")]
            if not selected and len(possible) == 1:
                selected = possible
            remainder = len(possible) - len(selected)
            label = ", ".join(selected) if selected else "record"
            extra = f" ({remainder} other possible object{'s' if remainder != 1 else ''})" if remainder else ""
            locks.append(f"saving {row.get('target') or 'a record'} locks the related {label}{extra}")
    lines = ["partial: " + (", ".join(sorted(reasons)) or "coverage incomplete") if partial else "complete"]
    for group, names in groups.items():
        lines.append(f"{group}: {', '.join(names) if names else 'none'}")
    if next_hops:
        ranked = sorted(next_hops.items(), key=lambda item: (-item[1], item[0]))
        summary = [f"{name} ({count} {'path' if count == 1 else 'paths'})" for name, count in ranked[:5]]
        if len(ranked) > 5:
            summary.append(f"{len(ranked) - 5} more objects")
        lines.append("next hop: " + ", ".join(summary))
    else:
        lines.append("next hop: none reported")
    lines.append(f"trigger-field check: {len(set(trigger_checks))} downstream automation{'s' if len(set(trigger_checks)) != 1 else ''} read{'s' if len(set(trigger_checks)) == 1 else ''} changed fields: {', '.join(sorted(set(trigger_checks)))}"
                 if trigger_checks else "trigger-field check: no matching trigger fields reported")
    lines.extend(dict.fromkeys(locks))
    return lines


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("fire_chain"))
