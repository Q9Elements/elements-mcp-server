#!/usr/bin/env python3
"""Prepare aggregate-only input and a local rehearsal batch for a data load."""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path


SALESFORCE_ID = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")


def canonical_salesforce_id(value):
    """Return the case-sensitive Salesforce 15-character identity."""
    return value[:15]


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="adapter", required=True)

    count_parser = subparsers.add_parser("count")
    count_parser.add_argument("--file", required=True, type=Path)

    slice_parser = subparsers.add_parser("slice")
    slice_parser.add_argument("--file", required=True, type=Path)
    slice_parser.add_argument("--out", required=True, type=Path)
    slice_parser.add_argument("--rows", required=True, type=int)
    slice_parser.add_argument("--sort-by")

    csv_parser = subparsers.add_parser("csv")
    csv_parser.add_argument("--file", required=True, type=Path)
    csv_parser.add_argument("--object", required=True)
    csv_parser.add_argument("--operation", choices=("insert", "update", "upsert"))
    csv_parser.add_argument("--written-fields")
    csv_parser.add_argument("--answers", type=Path)
    csv_parser.add_argument("--org-context", type=Path)
    csv_parser.add_argument("--rules", required=True, type=Path)
    csv_parser.add_argument("--hash-ids", action="store_true")
    csv_parser.add_argument("--top-k", type=int, default=10)
    csv_parser.add_argument("--soql-result", action="append", default=[])
    csv_parser.add_argument("--soql-result-override", action="store_true")
    csv_parser.add_argument("--upsert-match-field")
    csv_parser.add_argument("--upsert-insert-share", type=float)
    csv_parser.add_argument("--out", required=True, type=Path)

    soql_parser = subparsers.add_parser("soql")
    soql_parser.add_argument("--query-file", required=True, type=Path)
    soql_parser.add_argument("--object")
    soql_parser.add_argument("--operation", choices=("insert", "update", "upsert"))
    soql_parser.add_argument("--written-fields")
    soql_parser.add_argument("--volume", "--estimated-volume", dest="volume", type=int)
    soql_parser.add_argument("--answers", type=Path)
    soql_parser.add_argument("--org-context", type=Path)
    soql_parser.add_argument("--rules", required=True, type=Path)
    soql_parser.add_argument("--hash-ids", action="store_true")
    soql_parser.add_argument("--top-k", type=int, default=10)
    soql_parser.add_argument("--soql-result", action="append", default=[])
    soql_parser.add_argument("--soql-result-override", action="store_true")
    soql_parser.add_argument("--upsert-match-field")
    soql_parser.add_argument("--upsert-insert-share", type=float)
    soql_parser.add_argument("--out", required=True, type=Path)
    return parser


def csv_header(path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        header = next(reader, [])
    require_unique_csv_header(header)
    return header


def require_unique_csv_header(header):
    duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
    if duplicates:
        label = "header" if len(duplicates) == 1 else "headers"
        raise ValueError(f"duplicate CSV {label}: {', '.join(duplicates)}")


def has_written_fields(value):
    return isinstance(value, str) and any(
        field.strip() for field in value.split(",")
    )


def has_valid_upsert_share(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 1
    )


def common_missing_asks(arguments, adapter_asks):
    asks = []
    if arguments.operation not in ("insert", "update", "upsert"):
        asks.append(
            {
                "key": "operation",
                "question": "Which load operation will run: insert, update, or upsert?",
                "required": True,
            }
        )
    asks.extend(adapter_asks)
    if arguments.operation == "upsert" and not arguments.upsert_match_field:
        asks.append(
            {
                "key": "upsertMatchField",
                "question": "Which external-ID field will the upsert use for matching?",
                "required": True,
            }
        )
    if arguments.operation == "upsert" and not has_valid_upsert_share(
        arguments.upsert_insert_share
    ):
        asks.append(
            {
                "key": "upsertInsertShare",
                "question": "What share of rows is expected to insert (a number from 0 through 1)?",
                "required": True,
            }
        )
    return asks


def missing_csv_asks(arguments):
    adapter_asks = []
    if not has_written_fields(arguments.written_fields):
        candidates = ", ".join(csv_header(arguments.file))
        adapter_asks.append(
            {
                "key": "writtenFields",
                "question": (
                    "Which fields does the load WRITE? CSV header candidate fields "
                    f"(suggestion only; confirmation required): {candidates}"
                ),
                "required": True,
            }
        )
    return common_missing_asks(arguments, adapter_asks)


def apply_answers(arguments):
    if arguments.answers is None:
        return
    answers = read_json(arguments.answers)
    if not isinstance(answers, dict):
        raise ValueError("answers must be a JSON object")
    expected_types = {
        "operation": (
            lambda value: isinstance(value, str),
            "a JSON string",
        ),
        "writtenFields": (
            lambda value: isinstance(value, str)
            or (
                isinstance(value, list)
                and all(isinstance(field, str) for field in value)
            ),
            "a JSON string or an array of strings",
        ),
        "upsertMatchField": (
            lambda value: isinstance(value, str),
            "a JSON string",
        ),
        "upsertInsertShare": (
            has_valid_upsert_share,
            "a JSON number from 0 through 1",
        ),
        "estimatedVolume": (
            lambda value: isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0,
            "a non-negative JSON integer",
        ),
    }
    for key, (is_valid, expected) in expected_types.items():
        value = answers.get(key)
        if value is not None and not is_valid(value):
            raise ValueError(f"answers.{key} must be {expected}")
    if arguments.operation is None and answers.get("operation") is not None:
        arguments.operation = answers["operation"]
    if arguments.written_fields is None and answers.get("writtenFields") is not None:
        written_fields = answers["writtenFields"]
        if isinstance(written_fields, list):
            written_fields = ",".join(written_fields)
        arguments.written_fields = written_fields
    if arguments.upsert_match_field is None and answers.get("upsertMatchField") is not None:
        arguments.upsert_match_field = answers["upsertMatchField"]
    if arguments.upsert_insert_share is None and answers.get("upsertInsertShare") is not None:
        arguments.upsert_insert_share = answers["upsertInsertShare"]
    if hasattr(arguments, "volume") and arguments.volume is None:
        if answers.get("estimatedVolume") is not None:
            arguments.volume = answers["estimatedVolume"]


def read_json(path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


class _JsonObjectPairs(list):
    pass


def _convert_org_context_json(value, path=()):
    if isinstance(value, _JsonObjectPairs):
        converted = {}
        for key, nested_value in value:
            if path == ("keyPrefixes",) and key in converted:
                raise ValueError(
                    f"duplicate org-context keyPrefixes prefix: {key}"
                )
            converted[key] = _convert_org_context_json(
                nested_value,
                path + (key,),
            )
        return converted
    if isinstance(value, list):
        return [_convert_org_context_json(item, path) for item in value]
    return value


def read_org_context(path):
    with path.open("r", encoding="utf-8") as source:
        parsed = json.load(source, object_pairs_hook=_JsonObjectPairs)
    return _convert_org_context_json(parsed)


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        columns = next(reader, [])
        require_unique_csv_header(columns)
        rows = []
        for row_number, row in enumerate(reader, start=2):
            validate_csv_row(path, columns, row, row_number)
            rows.append(dict(zip(columns, row)))
        return rows, columns


def validate_csv_row(path, columns, row, row_number):
    if len(row) < len(columns):
        missing = columns[len(row):]
        label = "column" if len(missing) == 1 else "columns"
        raise ValueError(
            f"malformed CSV {path}: row {row_number} is missing {label} "
            + ", ".join(missing)
        )
    if len(row) > len(columns):
        raise ValueError(
            f"malformed CSV {path}: row {row_number} has {len(row) - len(columns)} extra value(s)"
        )


def count_csv_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        columns = next(reader, [])
        require_unique_csv_header(columns)
        count = 0
        for row_number, row in enumerate(reader, start=2):
            validate_csv_row(path, columns, row, row_number)
            count += 1
        return count


def slice_csv_rows(path, output, limit, sort_by=None):
    if limit < 1:
        raise ValueError("--rows must be at least 1")
    if path.resolve() == output.resolve():
        raise ValueError("--out must differ from --file")
    with path.open("rb") as source:
        first_line = source.readline()
    line_ending = "CRLF" if first_line.endswith(b"\r\n") else "LF"
    terminator = "\r\n" if line_ending == "CRLF" else "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, [])
            require_unique_csv_header(header)
            if not header:
                raise ValueError("CSV source has no header")
            if sort_by is not None and sort_by not in header:
                raise ValueError("--sort-by field is absent from CSV header")
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=output.parent,
                prefix=f".{output.name}.", delete=False,
            ) as destination:
                temporary = Path(destination.name)
                writer = csv.writer(destination, lineterminator=terminator)
                writer.writerow(header)
                count = 0
                selected = []
                for row_number, row in enumerate(reader, start=2):
                    validate_csv_row(path, header, row, row_number)
                    if sort_by is None:
                        writer.writerow(row)
                    else:
                        selected.append(row)
                    count += 1
                    if count == limit:
                        break
                if sort_by is not None:
                    index = header.index(sort_by)
                    for row in sorted(selected, key=lambda item: item[index]):
                        writer.writerow(row)
        if count == 0:
            raise ValueError("CSV source has no data rows")
        os.replace(temporary, output)
        return {"rows": count, "candidateWrittenFields": header, "lineEnding": line_ending}
    except csv.Error as error:
        raise ValueError("malformed CSV source: selected row has invalid quoting") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def relationship_inventory(object_name, rules, org_context):
    fields = {}
    if org_context:
        object_context = org_context.get("objects", {}).get(object_name, {})
        for field in object_context.get("relationshipFields", []):
            fields[field["apiName"]] = field
    rule = rules.get("objectSpecific", {}).get(object_name, {})
    for column in rule.get("relationshipColumns", []):
        include_targets = rule.get("columnTargets", {}).get(column, {}).get("include")
        polymorphic = None
        if isinstance(include_targets, list) and include_targets:
            polymorphic = len(include_targets) > 1
        fields.setdefault(
            column,
            {
                "apiName": column,
                "polymorphic": polymorphic,
            },
        )
    return fields


HISTOGRAM_BUCKETS = (
    ("1", 1, 1),
    ("2-10", 2, 10),
    ("11-100", 11, 100),
    ("101-1000", 101, 1000),
    ("1001-10000", 1001, 10000),
    (">10000", 10001, None),
)


def build_fan_in_counts(counts, top_k, hash_ids):
    histogram = []
    for label, minimum, maximum in HISTOGRAM_BUCKETS:
        parents = sum(
            1
            for count in counts.values()
            if count >= minimum and (maximum is None or count <= maximum)
        )
        histogram.append({"bucket": label, "parents": parents})
    top_parents = []
    for parent_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_k]:
        rendered_id = parent_id
        if hash_ids:
            rendered_id = hashlib.sha256(parent_id.encode("utf-8")).hexdigest()[:12]
        top_parents.append({"id": rendered_id, "rows": count})
    return {
        "distinctParents": len(counts),
        "maxRowsPerParent": max(counts.values(), default=0),
        "histogram": histogram,
        "topParents": top_parents,
        "idRepresentation": "sha256_12" if hash_ids else "raw",
    }


def build_type_distribution_counts(prefix_counts, org_context):
    key_prefixes = org_context.get("keyPrefixes", {}) if org_context else {}
    distribution = []
    for prefix in sorted(prefix_counts):
        object_name = key_prefixes.get(prefix)
        entry = {
            "prefix": prefix,
            "object": object_name,
            "rows": prefix_counts[prefix],
        }
        if object_name is None:
            entry["flag"] = "unresolved_prefix"
        distribution.append(entry)
    return distribution


def read_soql_results(specifications):
    results = {}
    for specification in specifications:
        if "=" not in specification:
            raise ValueError("--soql-result must be COLUMN=FILE.csv")
        column, filename = specification.split("=", 1)
        column = column.strip()
        counts = Counter()
        null_rows = 0
        non_id_rows = 0
        result_path = Path(filename)
        with result_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if column not in (reader.fieldnames or []):
                raise ValueError(
                    f"SOQL result for {column} must contain the {column} column"
                )
            grouped = "c" in (reader.fieldnames or [])
            for row_number, row in enumerate(reader, start=2):
                raw_count = row.get("c") if grouped else "1"
                try:
                    count = int(raw_count)
                except (TypeError, ValueError):
                    count = -1
                if count < 0:
                    raise ValueError(
                        f"invalid SOQL result {result_path}: row {row_number} column c "
                        "must be a non-negative integer"
                    )
                parent_value = row.get(column)
                if parent_value is None:
                    raise ValueError(
                        f"invalid SOQL result {result_path}: row {row_number} is missing column {column}"
                    )
                parent_id = parent_value.strip()
                if parent_id:
                    if SALESFORCE_ID.fullmatch(parent_id):
                        counts[canonical_salesforce_id(parent_id)] += count
                    else:
                        non_id_rows += count
                else:
                    null_rows += count
        results[column] = (counts, null_rows, non_id_rows)
    return results


def soql_result_columns(specifications):
    columns = []
    for specification in specifications:
        if "=" not in specification:
            raise ValueError("--soql-result must be COLUMN=FILE.csv")
        column = specification.split("=", 1)[0].strip()
        if not column:
            raise ValueError("--soql-result must be COLUMN=FILE.csv")
        columns.append(column)
    return columns


def validate_soql_result_columns(inventory, result_columns):
    duplicates = sorted(
        column
        for column, count in Counter(result_columns).items()
        if count > 1
    )
    if duplicates:
        raise ValueError(
            f"--soql-result column {duplicates[0]} was provided more than once"
        )
    unknown = sorted(set(result_columns) - set(inventory))
    if unknown:
        raise ValueError(
            f"--soql-result column {unknown[0]} is not in the relationship inventory"
        )


def relationship_from_counts(
    column,
    field,
    counts,
    null_rows,
    non_id_rows,
    org_context,
    top_k,
    hash_ids,
):
    prefix_counts = Counter()
    for parent_id, count in counts.items():
        prefix_counts[parent_id[:3]] += count
    relationship = {
        "column": column,
        "polymorphic": field.get("polymorphic"),
        "populatedRows": sum(counts.values()),
        "nullRows": null_rows,
        "nonIdRows": non_id_rows,
        "typeDistribution": build_type_distribution_counts(prefix_counts, org_context),
        "fanIn": build_fan_in_counts(counts, top_k, hash_ids),
    }
    if non_id_rows:
        relationship["flag"] = "non_id_values"
    return relationship


def unresolved_relationship(
    column,
    object_name,
    reason,
    operation,
    volume,
    upsert_insert_share,
):
    entry = {
        "column": column,
        "reason": reason,
        "resolution": "generated_soql",
        "soql": (
            f"SELECT {column}, COUNT(Id) c FROM {object_name} "
            "WHERE Id IN (...loaded set...) "
            f"GROUP BY {column} ORDER BY COUNT(Id) DESC"
        ),
    }
    if operation == "upsert":
        update_share = 1 - upsert_insert_share
        estimated_volume = volume * update_share
        if estimated_volume.is_integer():
            estimated_volume = int(estimated_volume)
        entry.update(
            {
                "branch": "update",
                "volumeShare": update_share,
                "estimatedVolume": estimated_volume,
            }
        )
    return entry


def resolve_relationship_columns(
    columns,
    inventory,
    soql_results,
    adapter,
    operation,
    written_fields,
    object_name,
    volume,
    upsert_insert_share,
    org_context,
    top_k,
    hash_ids,
):
    relationships = []
    unresolved = []
    warnings = []
    for column in sorted(columns):
        if operation == "insert" and column not in written_fields:
            continue
        if column in soql_results:
            counts, null_rows, non_id_rows = soql_results[column]
            relationships.append(
                relationship_from_counts(
                    column,
                    inventory[column],
                    counts,
                    null_rows,
                    non_id_rows,
                    org_context,
                    top_k,
                    hash_ids,
                )
            )
            if non_id_rows:
                warnings.append(
                    f"Relationship column {column} has {non_id_rows} non-ID rows and may be mis-mapped."
                )
            continue
        if adapter == "csv" and operation == "insert":
            continue
        reason = (
            "soql_row_values_unavailable"
            if adapter == "soql" and operation == "insert"
            else "update_stored_values_unknown"
        )
        unresolved.append(
            unresolved_relationship(
                column,
                object_name,
                reason,
                operation,
                volume,
                upsert_insert_share,
            )
        )
    return relationships, unresolved, warnings


def condition_matches(row, condition):
    value = row.get(condition["field"], "")
    operator = condition.get("operator")
    if operator == "equals":
        return value == str(condition.get("value", ""))
    if operator == "not_null":
        return bool(value.strip())
    raise ValueError(f"unsupported predicate operator: {operator}")


def build_predicate_stats(rows, columns, object_rule, operation):
    stats = []
    warnings = []
    for predicate in sorted(object_rule.get("predicates", []), key=lambda item: item["ruleId"]):
        if predicate.get("scope") != "row":
            continue
        applies_to = predicate.get("appliesTo")
        if applies_to is not None and operation not in applies_to:
            continue
        fields = sorted(predicate.get("fields", []))
        missing = sorted(set(fields) - set(columns))
        if missing:
            warnings.append(
                f"Rule {predicate['ruleId']} not evaluated; missing CSV columns: {', '.join(missing)}"
            )
            continue
        condition_group = predicate.get("conditions")
        conditions = (
            condition_group.get("all")
            if isinstance(condition_group, dict)
            else None
        )
        if not isinstance(conditions, list) or not conditions:
            warnings.append(
                f"Rule {predicate['ruleId']} not evaluated; conditions.all must be non-empty"
            )
            continue
        try:
            matching = sum(
                all(condition_matches(row, condition) for condition in conditions)
                for row in rows
            )
        except ValueError as error:
            warnings.append(f"Rule {predicate['ruleId']} not evaluated; {error}")
            continue
        if "note" in predicate:
            note = predicate["note"]
        else:
            note = "Row predicate from rules data; human-readable note unavailable."
            warnings.append(
                f"Rule {predicate['ruleId']} has no predicate note; using a generic note."
            )
        stats.append(
            {
                "ruleId": predicate["ruleId"],
                "fields": fields,
                "evaluableRows": len(rows),
                "matchingRows": matching,
                "note": note,
            }
        )
    return stats, warnings


def answered_asks(arguments, include_volume=False):
    asks = [
        {
            "question": "Which load operation will run: insert, update, or upsert?",
            "answered": True,
        },
        {
            "question": "Which fields does the load WRITE?",
            "answered": True,
        },
    ]
    if include_volume:
        asks.append(
            {
                "question": "What is the data-load owner's approximate volume for this query-defined load?",
                "answered": True,
            }
        )
    if arguments.operation == "upsert":
        asks.extend(
            [
                {
                    "question": "Which external-ID field will the upsert use for matching?",
                    "answered": True,
                },
                {
                    "question": "What share of rows is expected to insert?",
                    "answered": True,
                },
            ]
        )
    return asks


def build_csv_payload(arguments):
    rows, columns = read_csv(arguments.file)
    rules = read_json(arguments.rules)
    org_context = read_org_context(arguments.org_context) if arguments.org_context else None
    inventory = relationship_inventory(arguments.object, rules, org_context)
    result_columns = soql_result_columns(arguments.soql_result)
    validate_soql_result_columns(inventory, result_columns)
    conflicting_result_columns = sorted(set(result_columns) & set(columns))
    if conflicting_result_columns and not arguments.soql_result_override:
        raise ValueError(
            f"--soql-result column {conflicting_result_columns[0]} is already measured from the CSV; "
            "pass --soql-result-override to replace it"
        )
    soql_results = read_soql_results(arguments.soql_result)
    object_rule = rules.get("objectSpecific", {}).get(arguments.object, {})
    predicate_stats, warnings = build_predicate_stats(
        rows, columns, object_rule, arguments.operation
    )
    written_fields = sorted(set(
        field.strip()
        for field in arguments.written_fields.split(",")
        if field.strip()
    ))
    absent_written_fields = sorted(set(written_fields) - set(columns))
    if absent_written_fields:
        warnings.append(
            "Written fields absent from CSV header: "
            + ", ".join(absent_written_fields)
        )
    if org_context is None:
        warnings.insert(
            0,
            "Org context not supplied; key-prefix object resolution is unavailable.",
        )
    ignored_relationships = sorted(
        column
        for column in inventory
        if arguments.operation == "insert"
        and column in columns
        and column not in written_fields
    )
    if ignored_relationships:
        warnings.append(
            "Insert ignored present-but-unwritten relationship columns: "
            + ", ".join(ignored_relationships)
        )
    for column in conflicting_result_columns:
        warnings.append(
            f"SOQL result overrides CSV measurements for relationship column {column}."
        )
    relationship_columns = []
    unresolved = []
    measured_columns = []
    for column in sorted(inventory):
        if column not in columns:
            continue
        if arguments.operation == "insert" and column not in written_fields:
            continue
        if column in soql_results and arguments.soql_result_override:
            continue
        values = [row.get(column, "").strip() for row in rows]
        id_values = [
            canonical_salesforce_id(value)
            for value in values
            if SALESFORCE_ID.fullmatch(value)
        ]
        null_rows = sum(not value for value in values)
        non_id_rows = len(values) - len(id_values) - null_rows
        relationship_columns.append(
            relationship_from_counts(
                column,
                inventory[column],
                Counter(id_values),
                null_rows,
                non_id_rows,
                org_context,
                arguments.top_k,
                arguments.hash_ids,
            )
        )
        measured_columns.append(column)
        if non_id_rows:
            warnings.append(
                f"Relationship column {column} has {non_id_rows} non-ID rows and may be mis-mapped."
            )
        if arguments.operation == "upsert":
            unresolved.append(
                unresolved_relationship(
                    column,
                    arguments.object,
                    "update_stored_values_unknown",
                    arguments.operation,
                    len(rows),
                    arguments.upsert_insert_share,
                )
            )
    resolved, resolution_unresolved, resolution_warnings = resolve_relationship_columns(
        set(inventory) - set(measured_columns),
        inventory,
        soql_results,
        "csv",
        arguments.operation,
        written_fields,
        arguments.object,
        len(rows),
        arguments.upsert_insert_share,
        org_context,
        arguments.top_k,
        arguments.hash_ids,
    )
    relationship_columns.extend(resolved)
    relationship_columns.sort(key=lambda item: item["column"])
    unresolved.extend(resolution_unresolved)
    unresolved.sort(key=lambda item: item["column"])
    warnings.extend(resolution_warnings)
    return {
        "contractVersion": "1.0.0",
        "generatedBy": {
            "script": "load_input_prep.py",
            "adapter": "csv",
            "rulesVersion": rules["rulesVersion"],
        },
        "targets": [
            {
                "object": arguments.object,
                "operation": arguments.operation,
                "writtenFields": written_fields,
                "estimatedVolume": len(rows),
                "volumeSource": "row_count",
                "upsert": (
                    {
                        "matchField": arguments.upsert_match_field,
                        "insertShare": arguments.upsert_insert_share,
                        "shareSource": "user_supplied",
                    }
                    if arguments.operation == "upsert"
                    else None
                ),
                "aggregates": {
                    "relationshipColumns": relationship_columns,
                    "predicateStats": predicate_stats,
                    "unresolved": unresolved,
                },
            }
        ],
        "asks": answered_asks(arguments),
        "assumptions": [
            {
                "key": "skewThreshold",
                "value": 10000,
                "label": "community consensus, not officially documented",
            }
        ],
        "warnings": warnings,
    }


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _require_keys(value, required, optional, location):
    _require(isinstance(value, dict), f"{location} must be an object")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    _require(not missing, f"{location} missing fields: {', '.join(sorted(missing))}")
    _require(not unknown, f"{location} unknown fields: {', '.join(sorted(unknown))}")


def _require_array(value, location):
    _require(isinstance(value, list), f"{location} must be an array")


def validate_payload(payload):
    """Validate a payload against Object 1 contract version 1.0.0."""
    _require_keys(
        payload,
        {
            "contractVersion",
            "generatedBy",
            "targets",
            "asks",
            "assumptions",
            "warnings",
        },
        set(),
        "payload",
    )
    _require(payload["contractVersion"] == "1.0.0", "unsupported contractVersion")
    generated = payload["generatedBy"]
    _require_keys(
        generated,
        {"script", "adapter", "rulesVersion"},
        set(),
        "generatedBy",
    )
    _require(generated["script"] == "load_input_prep.py", "generatedBy.script is invalid")
    _require(generated["adapter"] in ("csv", "soql"), "generatedBy.adapter is invalid")
    _require(
        isinstance(generated["rulesVersion"], str)
        and re.fullmatch(r"\d+\.\d+\.\d+", generated["rulesVersion"]) is not None,
        "generatedBy.rulesVersion must be semantic version text",
    )
    _require(isinstance(payload["targets"], list) and payload["targets"], "targets must be non-empty")
    identifier = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
    for target_index, target in enumerate(payload["targets"]):
        location = f"targets[{target_index}]"
        _require_keys(
            target,
            {
                "object",
                "operation",
                "writtenFields",
                "estimatedVolume",
                "volumeSource",
                "upsert",
                "aggregates",
            },
            set(),
            location,
        )
        _require(
            isinstance(target["object"], str) and identifier.fullmatch(target["object"]),
            f"{location}.object must be an API name",
        )
        _require(
            target["operation"] in ("insert", "update", "upsert"),
            f"{location}.operation must be insert, update, or upsert",
        )
        fields = target["writtenFields"]
        _require(isinstance(fields, list), f"{location}.writtenFields must be an array")
        _require(
            all(isinstance(field, str) and identifier.fullmatch(field) for field in fields),
            f"{location}.writtenFields must contain API names",
        )
        _require(fields == sorted(set(fields)), f"{location}.writtenFields must be sorted and unique")
        _require(_is_count(target["estimatedVolume"]), f"{location}.estimatedVolume must be a non-negative integer")
        _require(
            target["volumeSource"]
            == ("row_count" if generated["adapter"] == "csv" else "user_supplied"),
            f"{location}.volumeSource is invalid for {generated['adapter']} adapter",
        )
        upsert = target["upsert"]
        if target["operation"] == "upsert":
            _require_keys(
                upsert,
                {"matchField", "insertShare", "shareSource"},
                set(),
                f"{location}.upsert",
            )
            _require(
                isinstance(upsert["matchField"], str)
                and identifier.fullmatch(upsert["matchField"]),
                f"{location}.upsert.matchField must be an API name",
            )
            _require(
                isinstance(upsert["insertShare"], (int, float))
                and not isinstance(upsert["insertShare"], bool)
                and 0 <= upsert["insertShare"] <= 1,
                f"{location}.upsert.insertShare must be between 0 and 1",
            )
            _require(upsert["shareSource"] == "user_supplied", f"{location}.upsert.shareSource is invalid")
        else:
            _require(upsert is None, f"{location}.upsert must be null for non-upsert operations")

        aggregates = target["aggregates"]
        _require_keys(
            aggregates,
            {"relationshipColumns", "predicateStats", "unresolved"},
            set(),
            f"{location}.aggregates",
        )
        _require_array(
            aggregates["relationshipColumns"],
            f"{location}.aggregates.relationshipColumns",
        )
        _require_array(
            aggregates["predicateStats"],
            f"{location}.aggregates.predicateStats",
        )
        _require_array(
            aggregates["unresolved"],
            f"{location}.aggregates.unresolved",
        )
        for relationship_index, relationship in enumerate(aggregates["relationshipColumns"]):
            rel_location = f"{location}.aggregates.relationshipColumns[{relationship_index}]"
            _require_keys(
                relationship,
                {"column", "polymorphic", "populatedRows", "nullRows", "nonIdRows", "typeDistribution", "fanIn"},
                {"flag"},
                rel_location,
            )
            _require(isinstance(relationship["column"], str) and identifier.fullmatch(relationship["column"]), f"{rel_location}.column is invalid")
            _require(
                relationship["polymorphic"] is None
                or isinstance(relationship["polymorphic"], bool),
                f"{rel_location}.polymorphic must be boolean or null",
            )
            _require(_is_count(relationship["populatedRows"]), f"{rel_location}.populatedRows is invalid")
            _require(_is_count(relationship["nullRows"]), f"{rel_location}.nullRows is invalid")
            _require(_is_count(relationship["nonIdRows"]), f"{rel_location}.nonIdRows is invalid")
            if "flag" in relationship:
                _require(relationship["flag"] == "non_id_values", f"{rel_location}.flag is invalid")
            _require(
                (relationship["nonIdRows"] > 0) == (relationship.get("flag") == "non_id_values"),
                f"{rel_location}.flag must identify non-ID rows",
            )
            if generated["adapter"] == "csv":
                _require(
                    relationship["populatedRows"]
                    + relationship["nullRows"]
                    + relationship["nonIdRows"]
                    == target["estimatedVolume"],
                    f"{rel_location} counts must equal the CSV row count",
                )
            type_distribution_location = f"{rel_location}.typeDistribution"
            _require_array(relationship["typeDistribution"], type_distribution_location)
            for distribution_index, distribution in enumerate(relationship["typeDistribution"]):
                distribution_location = (
                    f"{type_distribution_location}[{distribution_index}]"
                )
                _require_keys(
                    distribution,
                    {"prefix", "object", "rows"},
                    {"flag"},
                    distribution_location,
                )
                _require(isinstance(distribution["prefix"], str) and len(distribution["prefix"]) <= 3, f"{distribution_location}.prefix is invalid")
                _require(distribution["object"] is None or isinstance(distribution["object"], str), f"{distribution_location}.object is invalid")
                _require(_is_count(distribution["rows"]), f"{distribution_location}.rows is invalid")
                _require(
                    (distribution["object"] is None)
                    == (distribution.get("flag") == "unresolved_prefix"),
                    f"{distribution_location}.flag must identify an unresolved prefix",
                )
            fan_in = relationship["fanIn"]
            fan_in_location = f"{rel_location}.fanIn"
            _require_keys(fan_in, {"distinctParents", "maxRowsPerParent", "histogram", "topParents", "idRepresentation"}, set(), fan_in_location)
            _require(_is_count(fan_in["distinctParents"]), f"{rel_location}.fanIn.distinctParents is invalid")
            _require(_is_count(fan_in["maxRowsPerParent"]), f"{rel_location}.fanIn.maxRowsPerParent is invalid")
            _require(fan_in["idRepresentation"] in ("raw", "sha256_12"), f"{rel_location}.fanIn.idRepresentation is invalid")
            histogram_location = f"{fan_in_location}.histogram"
            _require_array(fan_in["histogram"], histogram_location)
            for bucket_index, bucket in enumerate(fan_in["histogram"]):
                bucket_location = f"{histogram_location}[{bucket_index}]"
                _require_keys(bucket, {"bucket", "parents"}, set(), bucket_location)
                _require(
                    _is_count(bucket["parents"]),
                    f"{bucket_location}.parents is invalid",
                )
            _require(
                [bucket["bucket"] for bucket in fan_in["histogram"]]
                == [bucket[0] for bucket in HISTOGRAM_BUCKETS],
                f"{rel_location}.fanIn.histogram buckets are invalid",
            )
            top_parents_location = f"{fan_in_location}.topParents"
            _require_array(fan_in["topParents"], top_parents_location)
            for parent_index, parent in enumerate(fan_in["topParents"]):
                parent_location = f"{top_parents_location}[{parent_index}]"
                _require_keys(parent, {"id", "rows"}, set(), parent_location)
                _require(isinstance(parent["id"], str), f"{parent_location}.id is invalid")
                _require(_is_count(parent["rows"]), f"{parent_location}.rows is invalid")
                if fan_in["idRepresentation"] == "sha256_12":
                    _require(re.fullmatch(r"[0-9a-f]{12}", parent["id"]) is not None, f"{parent_location}.id is not a valid hash")
                else:
                    _require(
                        len(parent["id"]) == 15
                        and SALESFORCE_ID.fullmatch(parent["id"]) is not None,
                        f"{parent_location}.id is not a canonical raw id",
                    )

        predicate_stats_location = f"{location}.aggregates.predicateStats"
        for predicate_index, predicate in enumerate(aggregates["predicateStats"]):
            predicate_location = f"{predicate_stats_location}[{predicate_index}]"
            _require_keys(predicate, {"ruleId", "fields", "evaluableRows", "matchingRows", "note"}, set(), predicate_location)
            _require(isinstance(predicate["ruleId"], str), f"{predicate_location}.ruleId is invalid")
            _require_array(predicate["fields"], f"{predicate_location}.fields")
            for field_index, field in enumerate(predicate["fields"]):
                _require(
                    isinstance(field, str) and identifier.fullmatch(field),
                    f"{predicate_location}.fields[{field_index}] must be an API name",
                )
            _require(
                predicate["fields"] == sorted(set(predicate["fields"])),
                f"{predicate_location}.fields must be sorted and unique",
            )
            _require(_is_count(predicate["evaluableRows"]), f"{predicate_location}.evaluableRows is invalid")
            _require(_is_count(predicate["matchingRows"]), f"{predicate_location}.matchingRows is invalid")
            _require(predicate["matchingRows"] <= predicate["evaluableRows"], f"{predicate_location}.matchingRows exceeds evaluableRows")
            _require(isinstance(predicate["note"], str), f"{predicate_location}.note is invalid")

        unresolved_location = f"{location}.aggregates.unresolved"
        for unresolved_index, unresolved in enumerate(aggregates["unresolved"]):
            unresolved_entry_location = (
                f"{unresolved_location}[{unresolved_index}]"
            )
            _require_keys(
                unresolved,
                {"column", "reason", "resolution", "soql"},
                {"branch", "volumeShare", "estimatedVolume"},
                unresolved_entry_location,
            )
            _require(isinstance(unresolved["column"], str) and identifier.fullmatch(unresolved["column"]), f"{unresolved_entry_location}.column is invalid")
            _require(unresolved["resolution"] == "generated_soql", f"{unresolved_entry_location}.resolution is invalid")
            _require(
                unresolved["reason"]
                in ("update_stored_values_unknown", "soql_row_values_unavailable"),
                f"{unresolved_entry_location}.reason is invalid",
            )
            _require(
                isinstance(unresolved["soql"], str)
                and unresolved["soql"].startswith("SELECT ")
                and " GROUP BY " in unresolved["soql"]
                and "...loaded set..." in unresolved["soql"],
                f"{unresolved_entry_location}.soql is invalid",
            )
            if "branch" in unresolved:
                _require(unresolved["branch"] == "update", f"{unresolved_entry_location}.branch is invalid")
                _require(isinstance(unresolved.get("volumeShare"), (int, float)), f"{unresolved_entry_location}.volumeShare is invalid")
                _require(isinstance(unresolved.get("estimatedVolume"), (int, float)), f"{unresolved_entry_location}.estimatedVolume is invalid")

    _require(isinstance(payload["asks"], list), "asks must be an array")
    for ask in payload["asks"]:
        _require_keys(ask, {"question", "answered"}, set(), "asks entry")
        _require(isinstance(ask["question"], str), "asks.question must be text")
        _require(ask["answered"] is True, "payload asks must be answered")
    _require(isinstance(payload["assumptions"], list), "assumptions must be an array")
    for assumption in payload["assumptions"]:
        _require_keys(
            assumption,
            {"key", "value", "label"},
            set(),
            "assumptions entry",
        )
        _require(isinstance(assumption["key"], str), "assumptions.key must be text")
        _require(
            assumption["value"] is None
            or isinstance(assumption["value"], (str, int, float, bool)),
            "assumptions.value must be a JSON scalar",
        )
        _require(isinstance(assumption["label"], str), "assumptions.label must be text")
    _require(
        isinstance(payload["warnings"], list)
        and all(isinstance(warning, str) for warning in payload["warnings"]),
        "warnings must be an array of strings",
    )
    return None


def write_payload(payload, path):
    validate_payload(payload)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_simple_soql(path):
    query = path.read_text(encoding="utf-8")
    match = re.search(
        r"\bSELECT\b\s+(.*?)\s+\bFROM\b\s+([A-Za-z_][A-Za-z0-9_]*)",
        query,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None, [], "Could not parse a simple SELECT ... FROM <object> SOQL statement."
    select_text, object_name = match.groups()
    fields = [field.strip() for field in select_text.split(",") if field.strip()]
    if not fields:
        return None, [], "Could not parse any fields from the SOQL SELECT list."
    if any(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", field) is None
        for field in fields
    ):
        return (
            None,
            [],
            "SOQL adapter accepts only a simple SELECT list of simple field names; provide a simplified query.",
        )
    return object_name, fields, None


def missing_soql_asks(arguments, select_fields, parse_error):
    if parse_error:
        return [{"key": "query", "question": parse_error, "required": True}]
    adapter_asks = []
    if not has_written_fields(arguments.written_fields):
        adapter_asks.append(
            {
                "key": "writtenFields",
                "question": (
                    "Which fields does the load WRITE? SOQL SELECT-list candidates "
                    "(suggestion only; confirmation required): "
                    + ", ".join(select_fields)
                ),
                "required": True,
            }
        )
    if not _is_count(arguments.volume):
        adapter_asks.append(
            {
                "key": "estimatedVolume",
                "question": "What is the data-load owner's approximate volume for this query-defined load?",
                "required": True,
            }
        )
    return common_missing_asks(arguments, adapter_asks)


def build_soql_payload(arguments, object_name):
    rules = read_json(arguments.rules)
    org_context = read_org_context(arguments.org_context) if arguments.org_context else None
    inventory = relationship_inventory(object_name, rules, org_context)
    result_columns = soql_result_columns(arguments.soql_result)
    validate_soql_result_columns(inventory, result_columns)
    soql_results = read_soql_results(arguments.soql_result)
    written_fields = sorted(set(
        field.strip()
        for field in arguments.written_fields.split(",")
        if field.strip()
    ))
    relationship_columns, unresolved, warnings = resolve_relationship_columns(
        inventory,
        inventory,
        soql_results,
        "soql",
        arguments.operation,
        written_fields,
        object_name,
        arguments.volume,
        arguments.upsert_insert_share,
        org_context,
        arguments.top_k,
        arguments.hash_ids,
    )
    if org_context is None:
        warnings.append(
            "Org context not supplied; key-prefix object resolution is unavailable."
        )
    return {
        "contractVersion": "1.0.0",
        "generatedBy": {
            "script": "load_input_prep.py",
            "adapter": "soql",
            "rulesVersion": rules["rulesVersion"],
        },
        "targets": [
            {
                "object": object_name,
                "operation": arguments.operation,
                "writtenFields": written_fields,
                "estimatedVolume": arguments.volume,
                "volumeSource": "user_supplied",
                "upsert": (
                    {
                        "matchField": arguments.upsert_match_field,
                        "insertShare": arguments.upsert_insert_share,
                        "shareSource": "user_supplied",
                    }
                    if arguments.operation == "upsert"
                    else None
                ),
                "aggregates": {
                    "relationshipColumns": relationship_columns,
                    "predicateStats": [],
                    "unresolved": unresolved,
                },
            }
        ],
        "asks": answered_asks(arguments, include_volume=True),
        "assumptions": [
            {
                "key": "skewThreshold",
                "value": 10000,
                "label": "community consensus, not officially documented",
            }
        ],
        "warnings": warnings,
    }


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.adapter == "count":
            print(json.dumps({"rows": count_csv_rows(arguments.file),
                              "candidateWrittenFields": csv_header(arguments.file)}))
            return 0
        if arguments.adapter == "slice":
            print(json.dumps(slice_csv_rows(arguments.file, arguments.out, arguments.rows, arguments.sort_by)))
            return 0
        if arguments.top_k < 1:
            raise ValueError("--top-k must be at least 1")
        if arguments.adapter == "csv":
            csv_header(arguments.file)
            apply_answers(arguments)
            asks = missing_csv_asks(arguments)
            if asks:
                print(json.dumps({"asks": asks}, sort_keys=True))
                return 2
            write_payload(build_csv_payload(arguments), arguments.out)
        elif arguments.adapter == "soql":
            apply_answers(arguments)
            parsed_object, select_fields, parse_error = parse_simple_soql(
                arguments.query_file
            )
            if arguments.object and parsed_object and arguments.object != parsed_object:
                parse_error = (
                    f"--object {arguments.object} does not match SOQL FROM object {parsed_object}."
                )
            asks = missing_soql_asks(arguments, select_fields, parse_error)
            if asks:
                print(json.dumps({"asks": asks}, sort_keys=True))
                return 2
            write_payload(build_soql_payload(arguments, parsed_object), arguments.out)
    except FileNotFoundError as error:
        print(f"error: file not found: {error.filename}", file=sys.stderr)
        return 1
    except OSError as error:
        filename = f" {error.filename}" if error.filename else ""
        print(f"error: cannot access file{filename}: {error.strerror}", file=sys.stderr)
        return 1
    except (ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
