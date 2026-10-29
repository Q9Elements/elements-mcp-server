"""Shared, standard-library helpers for data-load impact command-line tools."""

from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path


class ContractError(ValueError):
    """An input does not satisfy a documented script contract."""


METADATA_TYPE_ALIASES = {
    "Process Builder": "Process Builder Workflow",
    "Workflow": "Workflow Rule",
    "ApexClass": "Apex Class",
    "ApexTrigger": "Apex Trigger",
    "ValidationRule": "Validation Rule",
    "WorkflowRule": "Workflow Rule",
}


def metadata_type(value: str) -> str:
    """Use the synced Salesforce type name at script boundaries."""
    return METADATA_TYPE_ALIASES.get(value, value)


def source_types_by_node(manifest: dict | None) -> dict[str, str]:
    return {row["nodeId"]: metadata_type(row["type"])
            for row in (manifest or {}).get("files", [])
            if row.get("nodeId") and row.get("type")}


def resolve_metadata_type(row: dict, source_types: dict[str, str]) -> str:
    return source_types.get(row.get("nodeId")) or metadata_type(row.get("type", "Automation"))


def managed_validation_rule(row: dict) -> bool:
    """Recognize package ownership, including a qualified rule name from source."""
    if metadata_type(row.get("type") or row.get("automation_type", "")) != "Validation Rule":
        return False
    name = (row.get("apiName") or row.get("automation_api_name", "")).rsplit(".", 1)[-1]
    return bool(row.get("namespace") or str(row.get("isManaged", "")).lower() == "true"
                or "managed_component" in row.get("side_effect_flags", "").split(";")
                or re.match(r"^[A-Za-z][A-Za-z0-9_]*__", name))


def owner_coverage_statement(*, activation_unknown: bool, non_firing: bool, verdict: str) -> str:
    """Render coverage facts independently of internal evidence and tool failures."""
    activation = ("evidence shows it does not fire for this load" if non_firing else
                  "activation could not be verified" if activation_unknown else "activation verified")
    bypass = {"present": "an existing bypass covers this load", "absent": "no applicable bypass was found",
              "unknown": "bypass coverage is unknown"}[verdict]
    return f"Coverage: {activation}; {bypass}."


def validate_owner_steps(steps) -> None:
    """Require owner-authored criteria to name a core story and their ruling time."""
    if not isinstance(steps, list):
        raise ContractError("ownerSteps must be an array")
    stories = {"pre-load", "load", "export-and-reconcile", "re-enable", "rollback"}
    for index, entry in enumerate(steps, 1):
        if not isinstance(entry, dict):
            raise ContractError(f"ownerSteps entry {index} must be an object")
        if not isinstance(entry.get("story"), str) or entry["story"] not in stories:
            raise ContractError(f"ownerSteps entry {index} has invalid story")
        for field in ("step", "ruledOn"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ContractError(f"ownerSteps entry {index} needs {field}")


def fires_for_operation(automation: dict, operation: str) -> bool:
    """Whether bundle entry evidence permits this automation to fire for the load."""
    if automation.get("kind") != "directAutomation":
        return True
    branches = {"insert", "update"} if operation == "upsert" else {operation}
    if automation.get("branch") and automation["branch"] not in branches:
        return False
    if automation.get("branch"):
        branches = {automation["branch"]}
    if automation.get("type") in {"Flow", "Apex Trigger"}:
        events = set(automation.get("triggerEvents", "").replace(",", " ").lower().split())
        if not events:
            return True
        return bool(events & ({"create", "insert"} if "insert" in branches else set())
                    or events & ({"update"} if "update" in branches else set())
                    or events & ({"delete"} if "delete" in branches else set()))
    return True


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise ContractError(f"file not found: {error.filename}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON in {path}: line {error.lineno} column {error.colno}") from error


@contextmanager
def _atomic_text_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary as handle:
            yield handle
            handle.flush()
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json(path: Path, value) -> None:
    with _atomic_text_writer(path) as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            if not fields:
                raise ContractError(f"CSV has no header: {path}")
            return fields, list(reader)
    except FileNotFoundError as error:
        raise ContractError(f"file not found: {error.filename}") from error


def bundle_node_names(directories: list[Path]) -> dict[str, str]:
    """Resolve Elements node identifiers using names already present in tool bundles."""
    names = {}
    for directory in directories:
        for filename, pairs in (
            ("automations.csv", (("nodeId", "apiName"),)),
            ("fire-chain-digest.csv", (("entityNodeId", "entityApiName"),
                                       ("firingAutomationNodeId", "firingAutomation"),
                                       ("relationshipFieldNodeId", "relationshipField"))),
            ("alternatives.csv", (("alternativeTargetNodeId", "alternativeTargetApiName"),)),
        ):
            for row in read_csv(directory / filename)[1]:
                for id_key, name_key in pairs:
                    if row.get(id_key) and row.get(name_key):
                        names[row[id_key]] = row[name_key]
    return names


ELEMENTS_ID = re.compile(r"(?<![\w/.-])\b[0-9a-f]{24}\b(?![\w/-]|\.[A-Za-z0-9_-]+)")
METADATA_TYPE = re.compile(
    r"(?:Apex Class|Apex Trigger|Assignment Rule|Duplicate Rule|Validation Rule|Workflow Rule|"
    r"Flow|entity|object|field|metadata item)\s+$", re.I,
)


def render_element_ids(content: str, names_by_id: dict[str, str]) -> str:
    """Use known names in prose while leaving path and filename tokens intact."""
    def replacement(match: re.Match) -> str:
        name = names_by_id.get(match.group())
        if name:
            return name
        return "(name unavailable)" if METADATA_TYPE.search(content[:match.start()]) else "metadata item (name unavailable)"
    return ELEMENTS_ID.sub(replacement, content)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with _atomic_text_writer(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def require_fields(actual: list[str], expected: list[str], label: str) -> None:
    if actual != expected:
        raise ContractError(f"{label} header must be {','.join(expected)}")


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}
