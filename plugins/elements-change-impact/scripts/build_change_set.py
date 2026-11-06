"""Build the asserted change set from named targets or a picked option."""

from cli_common import field_object


def _id(element):
    return element.get("nodeId") or element.get("id") or element.get("apiName")


def _existing(element):
    return bool(element.get("nodeId") or element.get("id"))


def _with_parent(element, *sources):
    for source in (element, *sources):
        parent = field_object(source)
        if parent:
            if not (element.get("parentObject") or element.get("parent_object")):
                element["parent_object" if source.get("parent_object") else "parentObject"] = parent
            break
    return element


def _with_trigger_facts(element, *sources):
    for source in sources:
        for key in ("triggerType", "recordTriggerType", "phase", "triggerObject", "trigger_object"):
            if not element.get(key) and source.get(key):
                element[key] = source[key]
    return element


def build_change_set(targets, *, action=None, delta=None, option=None):
    targets_by_id = {_id(target): target for target in targets}
    if option is None:
        if action not in {"update", "delete"}:
            raise ValueError("named targets require update or delete")
        for target in targets:
            if not _existing(target):
                raise ValueError(f"named target {target.get('name') or target.get('apiName') or 'unnamed'} has no existing identifier; use decide for a new element")
        elements = [{"element": _with_trigger_facts(_with_parent(dict(target), target), target), "current_type": target.get("sfType") or target.get("type"),
                     "action": action, "mode": None, "delta": target.get("delta", delta) or {}}
                    for target in targets if _existing(target)]
    else:
        elements = []
        for row in option.get("elements", []):
            element = dict(row.get("element") or {})
            if row.get("action") != "create" and not _existing(element):
                continue
            source = targets_by_id.get(_id(element), {})
            _with_parent(element, row, row.get("candidate") or {}, source)
            _with_trigger_facts(element, row, row.get("candidate") or {}, source)
            if element.get("active") is None:
                if row.get("active") is not None:
                    element["active"] = row["active"]
                elif source.get("active") is not None:
                    element["active"] = source["active"]
            elements.append({"element": element, "current_type": row.get("current_type") or element.get("sfType") or element.get("type"),
                             "action": row.get("action"), "mode": row.get("mode") or option.get("mode"),
                             "delta": row.get("delta") or {}})
    if any(row["action"] not in {"create", "update", "delete", "keep"} for row in elements):
        raise ValueError("change set element has no valid action")
    if any(row["action"] == "keep" and row["delta"] for row in elements):
        raise ValueError("keep element must have an empty delta")
    ids = [_id(row["element"]) for row in elements]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate change set element")
    missing = [_id(target) for target in targets if _existing(target) and _id(target) not in ids]
    if missing:
        raise ValueError("named target missing an action: " + ", ".join(str(item) for item in missing))
    return {"elements": elements}


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("build_change_set"))
