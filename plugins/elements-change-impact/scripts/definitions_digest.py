"""Extract target references and decision lines from definition bundle files."""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from automation_state import is_automation, active_state
from cli_common import normalize_type


SIGNAL_TAGS = {"entryCriteria", "filterLogic", "formula", "errorConditionFormula", "field", "fieldReference", "inputReference",
               "outputReference", "operation", "operationType", "object", "recordCreates", "recordUpdates",
               "recordDeletes", "triggerType", "value", "fullName", "leftValueReference",
               "elementReference", "expression", "operator", "booleanValue", "stringValue",
               "numberValue", "dateValue", "literalValue", "conditionLogic"}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _safe_file(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("definition path outside bundle")
    return path


def _xml_nodes(root, row):
    native = {"Workflow Rule": "WorkflowRule", "Record Type": "RecordType"}.get(normalize_type(row))
    if native and _local(root.tag) == native:
        return [root]
    if normalize_type(row) in {"Field Update", "Workflow Field Update", "Workflow Rule", "Record Type"}:
        wanted = (row.get("apiName") or "").rsplit(".", 1)[-1]
        block = {"Workflow Rule": "rules", "Record Type": "recordTypes"}.get(normalize_type(row), "fieldUpdates")
        nodes = [node for node in root.iter() if _local(node.tag) == block
                 and any(_local(child.tag) == "fullName" and (child.text or "").strip() == wanted
                         for child in node)]
    elif row.get("xmlScope") == "object":
        fields = [node for node in root.iter() if _local(node.tag) == "fields"]
        selected = []
        for field in fields:
            if any(_local(child.tag) == "fullName" and (child.text or "").strip() == row.get("apiName") for child in field):
                selected.append(field)
        nodes = selected
    else:
        nodes = [root]
    return nodes


def _xml_lines(content, row, terms):
    nodes = _xml_nodes(ET.fromstring(content), row)
    lines = []
    for node in nodes:
        for child in node.iter():
            if _local(child.tag) == "inputAssignments":
                field = next(((part.text or "").strip() for part in child if _local(part.tag) == "field"), "")
                values = [part for part in child if _local(part.tag) == "value"]
                literal = next(((part.text or "").strip() for value in values for part in value.iter()
                                if _local(part.tag) in {"stringValue", "booleanValue", "numberValue", "dateValue"}
                                and (part.text or "").strip()), "")
                if field and literal:
                    lines.append(f"inputAssignment: {field} = {literal}")
            value = (child.text or "").strip()
            if _local(child.tag) in {"recordCreates", "recordUpdates", "recordDeletes"}:
                lines.append(f"{_local(child.tag)}: record operation")
            if value and (_local(child.tag) in SIGNAL_TAGS or any(term.lower() in value.lower() for term in terms)):
                lines.append(f"{_local(child.tag)}: {value}")
    return list(dict.fromkeys(lines))


def _created_objects(content):
    root = ET.fromstring(content)
    variables = {}
    for variable in root.iter():
        if _local(variable.tag) != "variables":
            continue
        parts = {_local(child.tag): (child.text or "").strip() for child in variable}
        if parts.get("name") and parts.get("objectType"):
            variables[parts["name"]] = parts["objectType"]
    created = []
    for operation in root.iter():
        if _local(operation.tag) != "recordCreates":
            continue
        parts = {_local(child.tag): (child.text or "").strip() for child in operation}
        object_name = parts.get("object") or variables.get(parts.get("inputReference"))
        if object_name:
            created.append(object_name)
    return list(dict.fromkeys(created))


def digest(index, bundle, *, targets=()):
    """Return one compact evidence record for each definitions index row."""
    root = Path(bundle)
    if isinstance(index, (str, Path)):
        with Path(index).open(encoding="utf-8", newline="") as handle:
            index = list(csv.DictReader(handle))
    output = []
    for row in index:
        record = {"nodeId": row.get("nodeId"), "apiName": row.get("apiName"),
                  "sfType": normalize_type(row), "lines": [], "created_objects": []}
        if is_automation(record):
            record["active"] = active_state(row)
        if row.get("status") != "ok":
            record["lines"] = [f"not available ({(row.get('reason') or 'unknown reason').replace('_', ' ')})"]
            output.append(record)
            continue
        terms = [str(term) for term in targets] + [row.get("apiName") or ""]
        for key in ("xmlFile", "bodyFile"):
            name = row.get(key)
            if not name:
                continue
            path = _safe_file(root, name)
            if not path.is_file():
                record["lines"].append(f"not available ({name} missing)")
                continue
            content = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".xml":
                if record["sfType"] in {"Flow", "Process Builder Workflow"}:
                    definition = ET.fromstring(content)
                    status = next(((child.text or "").strip() for child in definition
                                   if _local(child.tag) == "status"), None)
                    if status:
                        record["automation_status"] = status
                        record["active"] = active_state({"automation_status": status})
                if record["sfType"] in {"Validation Rule", "Workflow Rule", "Record Type"}:
                    states = [child for node in _xml_nodes(ET.fromstring(content), row) for child in node
                              if _local(child.tag) == "active"]
                    if states:
                        record["active"] = active_state({"active": (states[0].text or "").strip()})
                record["lines"].extend(_xml_lines(content, row, terms))
                record["created_objects"].extend(_created_objects(content))
            else:
                for line in content.splitlines():
                    if any(term.lower() in line.lower() for term in terms if term) or any(signal in line for signal in ("entryCriteria", "recordUpdates", "recordCreates", "recordDeletes")):
                        record["lines"].append(line.strip())
        if not record["lines"]:
            record["lines"] = ["no target reference or operation found in stored definition"]
        if is_automation(record):
            state = "active" if record["active"] is True else "inactive" if record["active"] is False else None
            status = f" ({record['automation_status']})" if record.get("automation_status") else ""
            record["lines"].insert(0, f"Automation: {state}{status}." if state else "Automation: active state not available.")
        output.append(record)
    return output


if __name__ == "__main__":
    from cli_common import main
    raise SystemExit(main("definitions_digest"))
