#!/usr/bin/env python3
"""Merge card 03 reasoner returns into ``work/reasoned-candidates.csv``.

The grouping mechanism is an explicit ``--grouping <csv>`` argument. The CSV must contain exactly one
``qualifiedName,groupLabel,groupOrder,groupNote`` row for every selected candidate. Reasoner payloads and returns are
read from ``work/reasoning/payload-*.json`` and ``work/reasoning/return-*.json`` in the engagement. A return is
either one unit's ``return-<unit>.json`` or a ``return-batch-NN.json`` whose ``units`` array holds one per-unit return
for every unit its manifest batch lists; each per-unit return is checked against ``payload-<unit>.json``, including
``<packageId>-fragment-N`` units.
The payload/return unit sets must match exactly, and a fragmented component must contain every index from 1
through its shared ``of`` value without a non-fragment unit for that package.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from apex_common import (
    REASONED_CANDIDATE_COLUMNS,
    ContractError,
    cli_guard,
    default_data_dir,
    parse_bool,
    qualified_name,
    read_csv,
    read_json_array,
    read_json_object,
    read_table,
    type_key,
    write_csv,
)


GROUPING_COLUMNS = ["qualifiedName", "groupLabel", "groupOrder", "groupNote"]
REASONING_COLUMNS = REASONED_CANDIDATE_COLUMNS
MEMBER_FIELDS = ("verdict", "confidence", "bucket", "reasons", "quotes")
QUOTED_REASONS = {
    "declared_schedule", "recently_modified", "cadence_language", "dynamic_dispatch_residue",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement", required=True, type=Path,
                        help="engagement directory containing work/bundle and work/reasoning")
    parser.add_argument("--grouping", required=True, type=Path,
                        help="grouping CSV with qualifiedName,groupLabel,groupOrder,groupNote")
    return parser


def _load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"missing required input file: {path}") from None
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from None
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def _safe_unknown(name: str) -> dict[str, object]:
    return {
        "qualifiedName": name,
        "verdict": "unknown",
        "confidence": "high",
        "bucket": "review-first",
        "reasons": ["could_not_assess"],
        "quotes": [],
        "cadenceSignalAvailable": False,
    }


def _merge_fragment_members(existing: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    verdicts = {str(existing["verdict"]), str(incoming["verdict"])}
    structural = verdicts - {"unknown"}
    if len(structural) > 1:
        raise ContractError(
            f"{existing['qualifiedName']}: fragment returns have incompatible verdicts {sorted(verdicts)}"
        )
    verdict = "unknown" if "unknown" in verdicts else next(iter(structural))

    def union(left: object, right: object) -> list[str]:
        values = []
        for value in [*left, *right]:
            if value not in values:
                values.append(value)
        return values

    reasons = union(existing["reasons"], incoming["reasons"])
    quotes = union(existing["quotes"], incoming["quotes"])
    return {
        **existing,
        "verdict": verdict,
        "confidence": "high" if verdict == "unknown" else (
            "medium" if "medium" in {existing["confidence"], incoming["confidence"]}
            else existing["confidence"]
        ),
        "bucket": "review-first" if (
            existing["bucket"] == "review-first" or incoming["bucket"] == "review-first"
        ) else "confident",
        "reasons": reasons,
        "quotes": quotes,
    }


def _entry_unit(entry: object, batch_id: str) -> str:
    if not isinstance(entry, dict) or not isinstance(entry.get("packageId"), str) or not entry["packageId"]:
        raise ContractError(f"{batch_id}: every units entry must be an object with a packageId")
    fragment = entry.get("fragment")
    if isinstance(fragment, dict) and type(fragment.get("index")) is int:
        return f"{entry['packageId']}-fragment-{fragment['index']}"
    return entry["packageId"]


def _manifest_batches(manifest: dict, manifest_units: set[str]) -> dict[str, list[str]]:
    raw = manifest.get("batches", [])
    if not isinstance(raw, list) or not all(
        isinstance(batch, dict) and isinstance(batch.get("batch"), str)
        and isinstance(batch.get("units"), list) and set(batch["units"]) <= manifest_units
        for batch in raw
    ):
        raise ContractError("reasoning manifest batches must name manifest units")
    return {batch["batch"]: [str(unit) for unit in batch["units"]] for batch in raw}


def _load_returns(
    reasoning_dir: Path, manifest_units: set[str], batches: dict[str, list[str]],
) -> list[tuple[str, dict, str | None]]:
    """Return ``(unit, per-unit return, batch id or None)`` from unit and batch return files, sorted by unit."""
    returns = [
        (unit, _load_object(reasoning_dir / f"return-{unit}.json"), None)
        for unit in manifest_units if (reasoning_dir / f"return-{unit}.json").is_file()
    ]
    seen = {unit for unit, _, _ in returns}
    for batch_id, listed in batches.items():
        path = reasoning_dir / f"return-{batch_id}.json"
        if not path.is_file():
            continue
        document = _load_object(path)
        if document.get("batch") != batch_id:
            raise ContractError(f"{path.name}: batch must be {batch_id!r}, got {document.get('batch')!r}")
        entries = document.get("units")
        if not isinstance(entries, list):
            raise ContractError(f"{batch_id}: units must be an array of per-unit returns")
        given = [_entry_unit(entry, batch_id) for entry in entries]
        missing = [unit for unit in listed if unit not in given]
        extra = [unit for unit in given if unit not in listed]
        twice = sorted({unit for unit in given if given.count(unit) > 1})
        if missing or extra or twice:
            raise ContractError(
                f"{batch_id}: batch return units must match the manifest batch; "
                f"missing={missing!r}; not listed={extra!r}; listed more than once={twice!r}"
            )
        for unit, entry in zip(given, entries):
            if unit in seen:
                raise ContractError(f"{batch_id}: {unit} also has a per-unit return file")
            seen.add(unit)
            returns.append((unit, entry, batch_id))
    return sorted(returns, key=lambda item: item[0])


def merge_engagement(engagement: Path, grouping_path: Path) -> str:
    """Validate every return, write the reasoned CSV, and return the one-line summary."""
    work = engagement / "work"
    reasoning_dir = work / "reasoning"
    candidates_path = work / "bundle" / "candidates.csv"
    candidate_fields, candidates = read_csv(
        candidates_path,
        required=["qualifiedName", "incomingReading", "set", "componentLabel"],
    )
    if not candidates:
        raise ContractError(f"{candidates_path} has no rows")
    by_name = {candidate["qualifiedName"]: candidate for candidate in candidates}
    if len(by_name) != len(candidates):
        raise ContractError(f"{candidates_path} contains duplicate qualifiedName values")

    _, grouping_rows = read_csv(grouping_path, required=GROUPING_COLUMNS)
    grouping_names = [row["qualifiedName"] for row in grouping_rows]
    if len(grouping_names) != len(set(grouping_names)) or not set(grouping_names) <= set(by_name):
        raise ContractError(
            f"grouping names must be unique selected candidates; grouping names={sorted(grouping_names)!r}, "
            f"candidate names={sorted(by_name)!r}"
        )
    grouping = {row["qualifiedName"]: row for row in grouping_rows}
    selected_names = set(grouping)
    packages_path = work / "triage" / "packages.json"
    raw_packages = read_json_array(packages_path, "triage packages")
    if not all(isinstance(package, dict) for package in raw_packages):
        raise ContractError(f"{packages_path} must contain package objects")
    package_members = {
        str(package.get("packageId")): {
            str(member) for member in package.get("members", [])
        }
        for package in raw_packages
        if package.get("status") == "selected"
    }

    data_dir = default_data_dir(__file__)
    verdicts = {row["verdict"] for row in read_table(data_dir, "verdicts.csv", ["verdict"])}
    valid_reasons = {
        row["reason"] for row in read_table(data_dir, "review-first-reasons.csv", ["reason"])
    }
    manifest = read_json_object(reasoning_dir / "manifest.json", "reasoning manifest")
    units = manifest.get("units")
    if not isinstance(units, list) or not all(isinstance(unit, str) and unit for unit in units):
        raise ContractError("reasoning manifest units must be an array of unit names")
    if len(units) != len(set(units)):
        raise ContractError("reasoning manifest units must be unique")
    manifest_units = set(units)
    batches = _manifest_batches(manifest, manifest_units)
    for path in [*reasoning_dir.glob("payload-*.json"), *reasoning_dir.glob("return-*.json")]:
        unit = path.stem.removeprefix("payload-").removeprefix("return-")
        if unit not in manifest_units and not (path.name.startswith("return-") and unit in batches):
            raise ContractError(f"{path.name} is not listed in manifest")
    payload_paths = sorted(reasoning_dir / f"payload-{unit}.json" for unit in manifest_units
                           if (reasoning_dir / f"payload-{unit}.json").is_file())
    returns = _load_returns(reasoning_dir, manifest_units, batches)
    payload_units = {path.stem.removeprefix("payload-") for path in payload_paths}
    return_units = {unit for unit, _, _ in returns}
    if payload_units != return_units:
        raise ContractError(
            "payload/return unit basenames differ: "
            f"payload only={sorted(payload_units - return_units)!r}; "
            f"return only={sorted(return_units - payload_units)!r}"
        )
    if not returns:
        raise ContractError(f"no reasoner returns found under {reasoning_dir}")

    problems: list[str] = []
    merged: dict[str, dict[str, object]] = {}
    notes: dict[str, list[str]] = {}
    member_sources: dict[str, list[tuple[str, bool]]] = {}
    package_unit_modes: dict[str, set[bool]] = {}
    package_fragments: dict[str, list[tuple[int, int, int]]] = {}
    package_assignments: dict[str, set[str]] = {}
    member_packages: dict[str, str] = {}
    package_batches: dict[str, set[str]] = {}
    for unit_name, document, batch_id in returns:
        first_problem = len(problems)
        unit = f"{batch_id}: {unit_name}" if batch_id else unit_name
        package_id = document.get("packageId")
        component = document.get("componentLabel")
        fragment_match = re.fullmatch(r"(.+)-fragment-([1-9]\d*)", unit_name)
        is_fragment = fragment_match is not None
        unit_package = fragment_match.group(1) if fragment_match else unit_name
        payload = _load_object(reasoning_dir / f"payload-{unit_name}.json")
        payload_package = payload.get("packageId")
        payload_component = payload.get("componentLabel")
        component_context = payload.get("component")
        context_label = (
            component_context.get("label")
            if isinstance(component_context, dict) else None
        )
        if unit_package != package_id or unit_package != payload_package:
            raise ContractError(
                f"{unit}: unit name package prefix {unit_package!r} must match "
                f"return and payload packageId"
            )
        if package_id not in package_members:
            raise ContractError(f"{unit}: packageId is not a selected triage package")
        if not isinstance(component, str) or not component or (
            component != payload_component or component != context_label
        ):
            raise ContractError(
                f"{unit}: return and payload componentLabel must match component context"
            )
        document_fragment = document.get("fragment")
        payload_fragment = payload.get("fragment")
        package_unit_modes.setdefault(package_id, set()).add(is_fragment)
        if batch_id:
            package_batches.setdefault(package_id, set()).add(batch_id)
        if is_fragment:
            filename_index = int(fragment_match.group(2))
            for source, metadata in (("return", document_fragment), ("payload", payload_fragment)):
                if not isinstance(metadata, dict) or type(metadata.get("index")) is not int or (
                    metadata["index"] != filename_index
                ):
                    raise ContractError(
                        f"{unit}: {source} fragment metadata must match filename index {filename_index}"
                    )
                if type(metadata.get("of")) is not int or metadata["of"] < 1:
                    raise ContractError(f"{unit}: {source} fragment metadata needs a positive integer of value")
            package_fragments.setdefault(package_id, []).append(
                (filename_index, document_fragment["of"], payload_fragment["of"])
            )
        elif "fragment" not in document or "fragment" not in payload or (
            document_fragment is not None or payload_fragment is not None
        ):
            raise ContractError(f"{unit}: non-fragment unit must carry null fragment metadata")
        if "assignedMembers" not in payload:
            raise ContractError(f"{unit}: assignedMembers is required")
        assigned = payload["assignedMembers"]
        if not isinstance(assigned, list) or not all(isinstance(member, dict) for member in assigned):
            raise ContractError(f"{unit}: assignedMembers must be an array of candidate rows")
        given = [member["qualifiedName"] for member in assigned]
        payload_rows = payload.get("rows")
        if not isinstance(payload_rows, list) or not all(
            isinstance(member, dict) for member in payload_rows
        ):
            raise ContractError(f"{unit}: rows must be an array of assigned candidate rows")
        row_names = [member.get("qualifiedName") for member in payload_rows]
        if len(given) != len(set(given)) or row_names != given:
            raise ContractError(
                f"{unit}: rows must contain exactly the assignedMembers in assignment order"
            )
        prior_assignments = package_assignments.setdefault(package_id, set())
        overlap = prior_assignments & set(given)
        if is_fragment and overlap:
            problems.append(
                f"{package_id}: fragment assignments overlap at {sorted(overlap)}"
            )
        prior_assignments.update(given)
        returned_members = document.get("members", [])
        could_not_assess = document.get("couldNotAssess", [])
        if not all(
            isinstance(entries, list) and all(
                isinstance(member, dict) and isinstance(member.get("qualifiedName"), str)
                for member in entries
            )
            for entries in (returned_members, could_not_assess)
        ):
            raise ContractError(
                f"{unit}: members and couldNotAssess must be arrays of objects with a qualifiedName"
            )
        returned_members = list(returned_members)
        seen = ([member["qualifiedName"] for member in returned_members]
                + [member["qualifiedName"] for member in could_not_assess])
        if len(seen) != len(set(seen)) or sorted(seen) != sorted(given):
            problems.append(f"{package_id}: members accounted {sorted(seen)} != given {sorted(given)}")

        for unavailable in could_not_assess:
            returned_members.append(_safe_unknown(unavailable["qualifiedName"]))

        for member in returned_members:
            name = member["qualifiedName"]
            row = by_name.get(name)
            if row is None:
                problems.append(f"{name}: not present in candidates.csv")
                continue
            if name not in selected_names:
                problems.append(f"{name}: returned but not present in selected grouping")
                continue
            absent = [field for field in MEMBER_FIELDS if field not in member]
            if absent:
                problems.append(f"{unit_name}: {name}: missing field(s) {absent}")
                continue
            if not isinstance(member["reasons"], list) or not isinstance(member["quotes"], list):
                problems.append(f"{unit_name}: {name}: reasons and quotes must be arrays")
                continue
            verdict = member["verdict"]
            confidence = member["confidence"]
            reasons = member["reasons"]
            bucket = member["bucket"]
            quotes = member["quotes"]
            if verdict not in verdicts:
                problems.append(f"{name}: verdict {verdict!r} not in verdicts.csv")
            if confidence not in ("high", "medium"):
                problems.append(f"{name}: confidence {confidence!r} must be 'high' or 'medium'")
            bad_reasons = set(reasons) - valid_reasons
            if bad_reasons:
                problems.append(f"{name}: reasons {sorted(bad_reasons)} not in review-first-reasons.csv")
            if bucket not in ("confident", "review-first"):
                problems.append(f"{name}: bucket {bucket!r}")
            if bucket == "review-first" and not reasons:
                problems.append(f"{name}: review-first with no reason")
            if bucket == "confident" and reasons:
                problems.append(f"{name}: confident but carries reasons {reasons}")
            if set(reasons) & QUOTED_REASONS and not quotes:
                problems.append(f"{name}: rescue reason without a quote")
            if row["incomingReading"] == "alarming" and bucket == "confident":
                problems.append(f"{name}: alarming row returned confident")
            expected_verdict = "test_only_reachable" if row["set"] == "T" else "dormant_candidate"
            if verdict not in (expected_verdict, "unknown"):
                problems.append(f"{name}: verdict {verdict} but set={row['set']} expects {expected_verdict}")
            if name in merged:
                sources = member_sources[name]
                if not is_fragment or any(not prior_fragment or prior_package != package_id
                                          for prior_package, prior_fragment in sources):
                    problems.append(f"{name}: returned by more than one unrelated reasoning unit")
                    continue
                try:
                    merged[name] = _merge_fragment_members(merged[name], member)
                except ContractError as exc:
                    problems.append(str(exc))
                    continue
            else:
                merged[name] = member
                member_sources[name] = []
            member_sources[name].append((package_id, is_fragment))
            member_packages[name] = package_id
        note = document.get("componentNote", "").strip()
        component_notes = notes.setdefault(package_id, [])
        if note and note not in component_notes:
            component_notes.append(note)
        if batch_id:
            problems[first_problem:] = [f"{batch_id}: {problem}" for problem in problems[first_problem:]]

    def where(package: str) -> str:
        """Name the package, prefixed by the batches that carried its units."""
        carried = sorted(package_batches.get(package, ()))
        return f"{', '.join(carried)}: {package}" if carried else package

    for component, modes in package_unit_modes.items():
        if len(modes) > 1:
            problems.append(f"{where(component)}: cannot mix fragment and non-fragment units")
    for component, fragments in package_fragments.items():
        of_values = {value for _, return_of, payload_of in fragments for value in (return_of, payload_of)}
        if len(of_values) != 1:
            problems.append(
                f"{where(component)}: fragment units must use the same of value, got {sorted(of_values)}"
            )
            continue
        total = next(iter(of_values))
        indices = [index for index, _, _ in fragments]
        if len(indices) != len(set(indices)) or set(indices) != set(range(1, total + 1)):
            problems.append(
                f"{where(component)}: fragment indices must be exactly 1..{total}, got {sorted(indices)}"
            )
    for package_id, assigned_names in package_assignments.items():
        expected_names = package_members[package_id]
        if assigned_names != expected_names:
            problems.append(
                f"{where(package_id)}: assigned member union {sorted(assigned_names)} "
                f"does not match package {sorted(expected_names)}"
            )

    missing = selected_names - set(merged)
    if missing:
        problems.append(f"no verdict for {sorted(missing)}")
    if problems:
        raise ContractError("INVARIANTS FAILED:\n  - " + "\n  - ".join(problems))

    ledger = read_json_object(work / "bundle" / "telemetry-ledger.json", "telemetry ledger")
    try:
        window_start = date.fromisoformat(str(ledger["windowStart"])[:10])
        window_end = date.fromisoformat(str(ledger["windowEnd"])[:10])
    except (KeyError, TypeError, ValueError):
        raise ContractError("telemetry ledger must include valid windowStart and windowEnd dates") from None

    event_types = ledger.get("eventTypes")
    absent_types = ledger.get("typesAbsent")
    effective_days = ledger.get("effectiveDays")
    if not isinstance(event_types, dict) or not isinstance(absent_types, list) or (
        type(effective_days) is not int or effective_days < 0
    ):
        raise ContractError("telemetry ledger needs eventTypes, typesAbsent, and effectiveDays")
    if not all(isinstance(value, str) for value in absent_types):
        raise ContractError("telemetry ledger typesAbsent must contain event type names")
    present_missing: dict[str, int] = {}
    present_spans: dict[str, int] = {}
    present_bounds: dict[str, tuple[date, date]] = {}
    for event_type, coverage in event_types.items():
        if not isinstance(event_type, str) or not isinstance(coverage, dict) or (
            type(coverage.get("missingDays")) is not int or type(coverage.get("spanDays")) is not int
        ):
            raise ContractError(f"telemetry ledger has invalid coverage for {event_type!r}")
        missing_days = coverage["missingDays"]
        span_days = coverage["spanDays"]
        if not 0 <= missing_days <= span_days:
            raise ContractError(f"telemetry ledger has invalid missingDays for {event_type!r}")
        try:
            first_day = date.fromisoformat(str(coverage["firstDay"])[:10])
            last_day = date.fromisoformat(str(coverage["lastDay"])[:10])
        except (KeyError, TypeError, ValueError):
            raise ContractError(f"telemetry ledger has invalid date bounds for {event_type!r}") from None
        if first_day > last_day:
            raise ContractError(f"telemetry ledger has invalid date bounds for {event_type!r}")
        present_missing[event_type] = missing_days
        present_spans[event_type] = span_days
        present_bounds[event_type] = (first_day, last_day)
    if set(present_missing) & set(absent_types):
        raise ContractError("telemetry ledger eventTypes and typesAbsent overlap")
    # A present type can cap another type only when its span covers that type's full span.
    true_gap = {}
    for event_type, missing_days in present_missing.items():
        first_day, last_day = present_bounds[event_type]
        covering_missing = [
            other_missing for other_type, other_missing in present_missing.items()
            if other_type != event_type
            and present_bounds[other_type][0] <= first_day
            and present_bounds[other_type][1] >= last_day
        ]
        true_gap[event_type] = min([missing_days, *covering_missing])
    source_event_types = {
        row["source"]: [name.strip() for name in row["eventTypes"].split(";") if name.strip()]
        for row in read_table(data_dir, "telemetry-gap-mapping.csv", ["source", "eventTypes"])
    }
    _, triage_rows = read_csv(
        work / "triage" / "candidates.csv", required=["qualifiedName", "entryPointChannels"],
    )
    triage_channels = {row["qualifiedName"]: row["entryPointChannels"] for row in triage_rows}
    if len(triage_channels) != len(triage_rows) or not selected_names <= set(triage_channels):
        raise ContractError("triage candidates must have one entryPointChannels row per selected candidate")

    for name in selected_names:
        candidate = by_name[name]
        sources = [source.strip() for source in candidate["incomingOtherTypes"].split(";")
                   if source.strip()]
        sources.extend(f"entry:{channel.strip()}" for channel in triage_channels[name].split(";")
                       if channel.strip())
        member = merged[name]
        for source in dict.fromkeys(sources):
            mapped_types = source_event_types.get(source, [])
            if not any(event_type in present_missing for event_type in mapped_types):
                continue
            counts = [
                (true_gap[event_type], present_spans[event_type], event_type)
                if event_type in present_missing else (effective_days, effective_days, event_type)
                for event_type in mapped_types
                if event_type in present_missing or event_type in absent_types
            ]
            gap_days, span_days, event_type = min(counts, key=lambda item: item[0])
            if gap_days == 0:
                continue
            member["bucket"] = "review-first"
            if "telemetry_gap" not in member["reasons"]:
                member["reasons"].append("telemetry_gap")
            quote = f"{source}: {event_type} true gap {gap_days} of {span_days} days"
            if quote not in member["quotes"]:
                member["quotes"].append(quote)

    def executed_in_window(row: dict[str, str]) -> bool:
        raw_date = row["lastExecutedDate"].strip()
        if not raw_date:
            return False
        try:
            executed_date = date.fromisoformat(raw_date[:10])
        except ValueError:
            return False
        return window_start <= executed_date <= window_end

    def has_execution_signal(row: dict[str, str]) -> bool:
        return (
            parse_bool(row["lastExecutedDirect"], allow_empty=True,
                       field=f"{row['qualifiedName']} lastExecutedDirect")
            or bool(row["lastExecutedVia"].strip())
        )

    _, catalog = read_csv(
        work / "bundle" / "catalog.csv",
        required=["qualifiedName", "kind", "isTestClass", "lastExecutedDate", "lastExecutedDirect", "lastExecutedVia", "executionCount"],
    )
    catalog_by_name = {row["qualifiedName"]: row for row in catalog}
    executed_classes = {
        name for name, row in catalog_by_name.items()
        if name not in by_name and row["kind"] == "class"
        and executed_in_window(row)
        and has_execution_signal(row)
    }
    _, edges = read_csv(
        work / "bundle" / "edges.csv",
        required=[
            "MetadataComponentName", "MetadataComponentType", "MetadataComponentNamespace",
            "RefMetadataComponentName", "RefMetadataComponentType", "RefMetadataComponentNamespace",
        ],
    )
    callers: dict[str, set[str]] = {name: set() for name in executed_classes}
    for edge in edges:
        if type_key(edge["MetadataComponentType"]) not in {"apexclass", "apextrigger"} or (
            type_key(edge["RefMetadataComponentType"]) != "apexclass"
        ):
            continue
        target = qualified_name(edge["RefMetadataComponentNamespace"], edge["RefMetadataComponentName"])
        if target not in callers:
            continue
        source = qualified_name(edge["MetadataComponentNamespace"], edge["MetadataComponentName"])
        source_row = catalog_by_name.get(source)
        if source_row and parse_bool(source_row["isTestClass"], field=f"{source} isTestClass"):
            continue
        callers[target].add(source)
    for target, sources in callers.items():
        if len(sources) != 1:
            continue
        source = next(iter(sources))
        if source not in merged:
            continue
        target_row = catalog_by_name[target]
        via = target_row["lastExecutedVia"].strip()
        direct = parse_bool(
            target_row["lastExecutedDirect"], allow_empty=True,
            field=f"{target} lastExecutedDirect",
        )
        if not direct and (not via or via == source):
            continue
        member = merged[source]
        member["bucket"] = "review-first"
        if "sole_caller_of_executed_class" not in member["reasons"]:
            member["reasons"].append("sole_caller_of_executed_class")
        count = target_row["executionCount"].strip()
        evidence = f"Only non-test Apex caller of executed {target}"
        if count:
            evidence += f" ({count} executions in the window)"
        if evidence not in member["quotes"]:
            member["quotes"].append(evidence)

    merged_notes = {package: " ".join(package_notes) for package, package_notes in notes.items()}

    output = work / "reasoned-candidates.csv"
    output_rows = []
    for candidate in candidates:
        name = candidate["qualifiedName"]
        if name not in selected_names:
            continue
        member = merged[name]
        group = grouping[name]
        output_rows.append({
            **candidate,
            "verdict": member["verdict"],
            "confidence": member["confidence"],
            "bucket": member["bucket"],
            "reasons": ";".join(member["reasons"]),
            "quotes": " | ".join(member["quotes"]),
            "cadenceSignalAvailable": member.get("cadenceSignalAvailable", False),
            "componentNote": merged_notes.get(member_packages.get(name, ""), ""),
            "groupLabel": group["groupLabel"],
            "groupOrder": group["groupOrder"],
            "groupNote": group["groupNote"],
        })
    write_csv(output, [*candidate_fields, *REASONING_COLUMNS], output_rows)

    bucket_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for member in merged.values():
        bucket = str(member["bucket"])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        for reason in member["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return (f"invariants OK; wrote {output} ({len(merged)} rows); buckets {bucket_counts}; "
            f"reasons {reason_counts}")


def run(args: argparse.Namespace) -> None:
    print(merge_engagement(args.engagement, args.grouping))


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
