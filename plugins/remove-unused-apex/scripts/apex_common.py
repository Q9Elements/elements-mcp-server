"""Shared, standard-library helpers for the remove-unused-apex CLIs."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class ContractError(Exception):
    """An input does not have the shape promised by data-contracts.md."""


REASONED_CANDIDATE_COLUMNS = [
    "verdict", "confidence", "bucket", "reasons", "quotes", "cadenceSignalAvailable",
    "componentNote",
    "groupLabel", "groupOrder", "groupNote",
]

BLIND_SPOT_DISPLAY_NAMES = {
    "incomingFromPAnomalies": "incoming edges from observed code",
    "managedOpaque": "opaque managed components",
    "nameHeldInData": "class names held in data",
    "nonTraversedEdgeSources": "edge sources the graph does not traverse",
    "packagePlatformDispatch": "package or platform dispatch by configured name",
    "rulesNotEvaluated": "rules not evaluated",
    "stringSearchUnavailable": "selected-class string search",
}

JSON_NAME = "JavaScript Object Notation (JSON)"


def default_data_dir(script_file: str) -> Path:
    return Path(script_file).resolve().parent.parent / "skills" / "remove-unused-apex" / "data"


def require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise ContractError(f"missing required {label} directory: {path}")


def require_file(path: Path, label: str | None = None) -> None:
    if not path.is_file():
        raise ContractError(f"missing required {label or 'input'} file: {path}")


def read_csv(path: Path, required: Sequence[str] = ()) -> tuple[list[str], list[dict[str, str]]]:
    require_file(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if reader.fieldnames is None:
                raise ContractError(f"missing header row in {path}")
            fields = [field.strip() for field in reader.fieldnames]
            missing = [field for field in required if field not in fields]
            if missing:
                raise ContractError(f"missing required column(s) in {path}: {', '.join(missing)}")
            rows = []
            for row in reader:
                if None in row:
                    raise ContractError(f"row has more values than columns in {path}")
                rows.append({(key or "").strip(): value or "" for key, value in row.items()})
            return fields, rows
    except UnicodeError as exc:
        raise ContractError(f"invalid UTF-8 CSV {path}: {exc}") from None
    except csv.Error as exc:
        raise ContractError(f"invalid CSV {path}: {exc}") from None


def read_table(data_dir: Path, name: str, required: Sequence[str]) -> list[dict[str, str]]:
    _, rows = read_csv(data_dir / name, required)
    return rows


def classify_quiddity(
        legend: dict[str, dict[str, str]], code: object) -> dict[str, object]:
    """Return the normalized legend row, using UD for every unknown code."""
    default = legend.get("UD")
    if default is None:
        raise ContractError("quiddity-codes.csv is missing the UD default")
    normal = str(code or "").strip().upper()
    classified: dict[str, object] = dict(legend.get(normal, default))
    classified["protects"] = parse_bool(str(classified.get("protects", "")), field="protects")
    return classified


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in fields})


def csv_value(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json_object(path: Path, label: str | None = None) -> dict[str, object]:
    """Read a JSON object with the same one-line contract errors as the CLIs."""
    require_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid {JSON_NAME} in {path}: {exc}"
        ) from None
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a {JSON_NAME} object")
    return value


def read_json_array(path: Path, label: str | None = None) -> list[object]:
    """Read an array with the same one-line contract errors as the CLIs."""
    require_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"invalid {JSON_NAME} in {path}: {exc}"
        ) from None
    if not isinstance(value, list):
        raise ContractError(f"{path} must contain a {JSON_NAME} array")
    return value


def parse_bool(value: str, *, allow_empty: bool = False, field: str = "boolean") -> bool | None:
    normal = value.strip().lower()
    if normal == "true":
        return True
    if normal == "false":
        return False
    if allow_empty and normal == "":
        return None
    raise ContractError(f"invalid {field}: expected true or false, got {value!r}")


def parse_int(value: str, *, allow_empty: bool = False, field: str = "integer") -> int | None:
    if allow_empty and value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise ContractError(f"invalid {field}: expected integer, got {value!r}") from None


def parse_float(value: str, *, allow_empty: bool = False, field: str = "number") -> float | None:
    if allow_empty and value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        raise ContractError(f"invalid {field}: expected number, got {value!r}") from None


def id_key(value: str) -> str:
    """Salesforce 15- and 18-character IDs identify the same row."""
    value = value.strip()
    return value[:15] if len(value) >= 15 else value


def qualified_name(namespace: str, name: str) -> str:
    namespace, name = namespace.strip(), name.strip()
    return f"{namespace}.{name}" if namespace else name


def cli_guard(function) -> int:
    try:
        function()
        return 0
    except ContractError as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"input/output error: {str(exc).replace(chr(10), ' ')}", file=sys.stderr)
        return 2


def mask_comments_and_strings(source: str, *, preserve_strings: bool = False) -> str:
    """Blank comments and, optionally, quoted strings while preserving positions/newlines."""
    chars = list(source)
    i = 0
    state = "code"
    quote = ""
    while i < len(chars):
        current = chars[i]
        following = chars[i + 1] if i + 1 < len(chars) else ""
        if state == "code":
            if current == "/" and following == "/":
                chars[i] = chars[i + 1] = " "
                state = "line"
                i += 2
                continue
            if current == "/" and following == "*":
                chars[i] = chars[i + 1] = " "
                state = "block"
                i += 2
                continue
            if current in ("'", '"'):
                quote = current
                if not preserve_strings:
                    chars[i] = " "
                state = "string"
        elif state == "line":
            if current == "\n":
                state = "code"
            else:
                chars[i] = " "
        elif state == "block":
            if current == "*" and following == "/":
                chars[i] = chars[i + 1] = " "
                state = "code"
                i += 2
                continue
            if current != "\n":
                chars[i] = " "
        else:
            if current == "\\" and following:
                if not preserve_strings:
                    chars[i] = chars[i + 1] = " "
                i += 2
                continue
            if current == quote:
                if not preserve_strings:
                    chars[i] = " "
                state = "code"
            elif not preserve_strings and current != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "unit"


# Bundle contract shapes (references/data-contracts.md). These columns describe the files
# get_unused_apex_candidates returns; the planner validates its inputs against them.
CATALOG_COLUMNS = [
    "nodeId", "sfId", "qualifiedName", "name", "namespacePrefix", "kind",
    "triggerObject", "isManagedPackage", "isTestClass", "apiVersion",
    "lengthWithoutComments", "countedRule", "countedCharacters", "coverageFraction",
    "linesCovered", "linesUncovered", "coverageStamp", "lastModifiedDate",
    "lastExecutedDate", "lastExecutedDirect", "lastExecutedVia", "executionCount",
    "executionRate", "scheduledJobNames", "scheduleLive",
]

CANDIDATE_EXTRA_COLUMNS = [
    "set", "incomingFromP", "incomingFromCandidates", "incomingFromTest",
    "incomingFromOther", "incomingOtherTypes", "incomingTotal", "incomingReading",
    "componentLabel", "outgoingWithinCandidates", "description", "automationSummary",
    "intentTags", "automationContextAvailable", "stringReferenceHits",
    "stringReferenceNodes", "stringReferenceOutsideCandidates",
]

EDGE_COLUMNS = [
    "MetadataComponentId", "MetadataComponentName", "MetadataComponentType", "MetadataComponentNamespace",
    "RefMetadataComponentId", "RefMetadataComponentName", "RefMetadataComponentType", "RefMetadataComponentNamespace",
    "parentUsed", "parentNodeId", "childNodeId",
]


def type_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def tarjan(nodes: set[str], graph: Mapping[str, set[str]]) -> list[set[str]]:
    """Return strongly connected components without using Python recursion."""
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    component_stack: list[str] = []
    on_stack: set[str] = set()
    result: list[set[str]] = []

    for start in sorted(nodes):
        if start in indices:
            continue
        frames: list[tuple[str, list[str], int, str | None]] = [
            (start, sorted(graph.get(start, set()) & nodes), 0, None)
        ]
        while frames:
            node, targets, position, parent = frames[-1]
            if node not in indices:
                indices[node] = low[node] = index
                index += 1
                component_stack.append(node)
                on_stack.add(node)
            if position < len(targets):
                target = targets[position]
                frames[-1] = (node, targets, position + 1, parent)
                if target not in indices:
                    frames.append(
                        (target, sorted(graph.get(target, set()) & nodes), 0, node)
                    )
                elif target in on_stack:
                    low[node] = min(low[node], indices[target])
                continue

            frames.pop()
            if parent is not None:
                low[parent] = min(low[parent], low[node])
            if low[node] == indices[node]:
                component: set[str] = set()
                while True:
                    member = component_stack.pop()
                    on_stack.remove(member)
                    component.add(member)
                    if member == node:
                        break
                result.append(component)
    return result


def attached_tests(
    members: set[str],
    *,
    graph: Mapping[str, set[str]],
    test_names: set[str],
    catalog_names: set[str],
) -> list[str]:
    """Apply the planner's complete-target test attachment rule."""
    possible = {
        test for test in test_names
        if graph.get(test, set()) & members
        and all(
            target in members or target in test_names
            for target in graph.get(test, set())
            if target in catalog_names
        )
    }
    changed = True
    while changed:
        changed = False
        for test in test_names - possible:
            targets = {
                target for target in graph.get(test, set())
                if target in catalog_names
            }
            if targets & possible and targets <= members | possible | test_names:
                possible.add(test)
                changed = True
    return sorted({
        test for test in possible
        if all(
            target in members or target in possible
            for target in graph.get(test, set())
            if target in catalog_names
        )
    })


def outside_apex_callers(
    name: str,
    *,
    incoming: Mapping[str, set[str]],
    endpoint_types: Mapping[str, str],
    catalog_by_name: Mapping[str, Mapping[str, object]],
    confirmed: set[str],
) -> list[str]:
    """Return non-test class and trigger callers outside a removal set."""
    result = []
    for source in incoming.get(name, set()):
        source_row = catalog_by_name.get(source)
        source_type = type_key(endpoint_types.get(source, ""))
        apex_type = source_type in {
            "apex", "apexclass", "apextrigger", "class", "trigger",
        }
        unresolved_type = source_row is None and source_type in {
            "", "unknown", "unresolved",
        }
        if not apex_type and not unresolved_type:
            continue
        if source_row and parse_bool(
            str(source_row.get("isTestClass", "")), field=f"{source} isTestClass"
        ):
            continue
        if source not in confirmed:
            result.append(source)
    return sorted(set(result))

APEX_HOLDER_TYPE_KEYS = {
    "class": {"apexclass", "class"},
    "trigger": {"apextrigger", "trigger"},
}
APEX_HOLDER_TYPES = APEX_HOLDER_TYPE_KEYS["class"] | APEX_HOLDER_TYPE_KEYS["trigger"]


def is_self_match(
    row: Mapping[str, str], kinds: Mapping[str, str] | None = None,
) -> bool:
    name = row.get("qualifiedName", "").strip()
    if not name or row.get("holderName", "").strip().casefold() != name.casefold():
        return False
    kind = (kinds or {}).get(name, "").strip().casefold()
    return type_key(row.get("holderType", "")) in APEX_HOLDER_TYPE_KEYS.get(
        kind, APEX_HOLDER_TYPES
    )


def outside_string_holders(
    rows: Iterable[Mapping[str, str]],
    confirmed: set[str],
    *,
    honor_selected_flag: bool = False,
    kinds: Mapping[str, str] | None = None,
) -> list[str]:
    """Return non-test configured-name holders outside a removal set."""
    result = []
    confirmed_folded = {name.lower() for name in confirmed}
    for row in rows:
        holder = row.get("holderName", "").strip()
        if not holder or parse_bool(row.get("holderIsTest", ""), field="holderIsTest"):
            continue
        if is_self_match(row, kinds):
            continue
        holder_type = type_key(row.get("holderType", ""))
        if holder_type and holder_type not in APEX_HOLDER_TYPES:
            result.append(holder)
            continue
        declared_selected = honor_selected_flag and bool(
            parse_bool(row.get("holderInSelectedSet", ""), field="holderInSelectedSet")
        )
        if holder.lower() not in confirmed_folded and not declared_selected:
            result.append(holder)
    return sorted(set(result))
