#!/usr/bin/env python3
"""Render card 02's deterministic candidate report from an engagement bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apex_common import (
    BLIND_SPOT_DISPLAY_NAMES,
    ContractError,
    cli_guard,
    parse_int,
    read_csv,
    read_json_array,
    read_json_object,
)


DEFAULT_REPORT = Path("report/02-candidates.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engagement",
        required=True,
        type=Path,
        help="engagement directory containing work/bundle and report",
    )
    return parser


def read_components(path: Path) -> list[dict[str, object]]:
    value = read_json_array(path, "components bundle")
    if not all(isinstance(item, dict) for item in value):
        raise ContractError(
            f"{path} must contain a JSON array of component objects"
        )
    return value


def integer(row: dict[str, str], field: str) -> int:
    return parse_int(row[field], allow_empty=True, field=field) or 0


def characters_text(known: int, unknown: int, size: int) -> str:
    if not unknown:
        return f"{known:,}"
    if unknown >= size and not known:
        return "unknown"
    return f"{known:,} plus {unknown:,} of unknown length"


def component_characters(item: dict[str, object]) -> str:
    unknown = item.get("unknownLengthMembers") or 0
    unknown_count = len(unknown) if isinstance(unknown, list) else int(unknown)
    size = item.get("members", item.get("size", 0)) or 0
    size = len(size) if isinstance(size, list) else int(size)
    return characters_text(int(item.get("countedCharacters") or 0), unknown_count, size)


def rows_characters(rows: list[dict[str, str]]) -> str:
    return characters_text(
        sum(integer(row, "countedCharacters") for row in rows),
        sum(not row["countedCharacters"].strip() for row in rows),
        len(rows),
    )


def event_day_count(facts: dict[str, object], event_type: str, field: str) -> int:
    value = facts.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"telemetry event type {event_type} {field} must be an integer")
    if value < 0:
        raise ContractError(f"telemetry event type {event_type} {field} must not be negative")
    return value


def blind_spot_detail(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    if isinstance(value, dict):
        return "; ".join(
            f"{name}: {nested}" for name, nested in sorted(value.items())
        ) or "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def render_report(engagement: Path) -> Path:
    bundle = engagement / "work" / "bundle"
    ledger = read_json_object(bundle / "telemetry-ledger.json", "telemetry ledger")
    summary = read_json_object(bundle / "catalog-summary.json", "catalog summary")
    blind_spots = read_json_object(bundle / "blind-spots.json", "blind spots")
    blind_spots = {
        name: value for name, value in blind_spots.items()
        if "coverage" not in name.casefold()
    }

    event_types = ledger.get("eventTypes")
    if not isinstance(event_types, dict):
        raise ContractError("telemetry ledger is missing eventTypes object")
    event_lines = []
    for name, facts in sorted(event_types.items()):
        if not isinstance(facts, dict):
            raise ContractError(f"telemetry event type {name} must be an object")
        days_processed = event_day_count(facts, name, "daysProcessed")
        span_days = event_day_count(facts, name, "spanDays")
        if days_processed > span_days:
            raise ContractError(
                f"telemetry event type {name} daysProcessed must not exceed spanDays"
            )
        event_lines.append(
            f"| {name} | {days_processed} | {span_days} | "
            f"{span_days - days_processed} |"
        )
    absent = ledger.get("typesAbsent", [])
    if not isinstance(absent, list):
        raise ContractError("telemetry ledger typesAbsent must be an array")
    event_lines.extend(f"| {name} | absent | absent | unknown |" for name in sorted(absent))

    candidate_capacity = summary.get("candidateCapacity")
    triage_path = engagement / "work" / "triage" / "summary.json"
    if isinstance(candidate_capacity, dict) and triage_path.is_file():
        triage = read_json_object(triage_path, "triage summary")
        envelope = read_json_object(bundle / "envelope.json", "candidate-tool envelope")
        envelope_summary = envelope.get("summary")
        candidate_summary = (
            envelope_summary.get("candidates")
            if isinstance(envelope_summary, dict) else None
        )
        candidate_total = (
            candidate_summary.get("total")
            if isinstance(candidate_summary, dict) else None
        )
        if isinstance(candidate_total, bool) or not isinstance(candidate_total, int):
            raise ContractError("candidate-tool envelope summary.candidates.total must be an integer")
        largest = candidate_capacity.get("largestComponents", [])
        if not isinstance(largest, list) or not all(isinstance(item, dict) for item in largest):
            raise ContractError("catalog summary candidateCapacity.largestComponents must be an array of objects")
        component_lines = [
            f"| {item.get('label', '')} | {int(item.get('members', item.get('size', 0))):,} | "
            f"{component_characters(item)} |"
            for item in largest[:10]
        ]
        counts = triage.get("counts", {})
        if not isinstance(counts, dict):
            raise ContractError("triage summary counts must be an object")
        packages_path = engagement / "work" / "triage" / "packages.json"
        packages = (
            read_json_array(packages_path, "triage packages")
            if packages_path.is_file() else []
        )
        if not all(isinstance(package, dict) for package in packages):
            raise ContractError("triage packages must contain package objects")

        def outcome_lines(status: str, reason_field: str) -> str:
            lines: list[str] = []
            for package in packages:
                if package.get("status") != status:
                    continue
                reasons = package.get(reason_field, [])
                if not isinstance(reasons, list):
                    raise ContractError(
                        f"triage package {reason_field} must be an array"
                    )
                lines.extend([
                    f"### {package.get('seed', '')}",
                    "",
                    *[f"- {reason}" for reason in reasons],
                    "",
                ])
            return "\n".join(lines).rstrip() or "None."

        in_use_lines = outcome_lines("in-use", "inUseBecause")
        kept_use_unknown_lines = outcome_lines(
            "kept-use-unknown", "keptBecause"
        )
        string_search = triage.get("stringSearch", "not_run")
        if string_search not in {"not_run", "available", "unavailable"}:
            raise ContractError("triage summary stringSearch has an invalid value")
        if string_search == "unavailable":
            blind_spots = {
                **blind_spots,
                "stringSearchUnavailable": "unavailable",
            }
        selected_packages = triage.get("selectedPackages", counts.get("selected", 0))
        string_search_text = (
            string_search if string_search != "not_run" else
            "not run (no package selected)" if int(selected_packages or 0) == 0 else "pending"
        )
        blind_spot_lines = [
            f"| {BLIND_SPOT_DISPLAY_NAMES.get(name, name)} | {blind_spot_detail(value)} |"
            for name, value in sorted(blind_spots.items())
        ]
        report = f"""# Candidate report

<!-- prose: headline -->

## Capacity target and selection

| Fact | Value |
| --- | ---: |
| Required characters | {int(triage.get('requiredCharacters', 0)):,} |
| Confirmed characters | {int(triage.get('confirmedCharacters', 0)):,} |
| Selected characters | {int(triage.get('selectedCharacters', 0)):,} |
| Shortfall | {int(triage.get('shortfall', 0)):,} |
| Outcome | {triage.get('outcome', 'unknown')} |
| Candidates | {candidate_total:,} |
| Selected candidates | {int(counts.get('selected', 0)):,} |
| Deferred candidates | {int(counts.get('deferred', 0)):,} |
| Found in use candidates | {int(counts.get('inUse', 0)):,} |
| Kept: use unknown candidates | {int(counts.get('keptUseUnknown', 0)):,} |
| Unknown-length candidates | {int(candidate_capacity.get('unknownLengthCandidates', 0)):,} |
| Selected-class string search | {string_search_text} |

## Found in use

{in_use_lines}

## Kept: use unknown

{kept_use_unknown_lines}

## Telemetry window

<!-- prose: window -->

| Fact | Value |
| --- | --- |
| Requested days | {ledger.get('requestedDays', 'unknown')} |
| Effective days | {ledger.get('effectiveDays', 'unknown')} |
| Window start | {ledger.get('windowStart', 'unknown')} |
| Window end | {ledger.get('windowEnd', 'unknown')} |

| Event type | Days processed | Span days | Missing days |
| --- | ---: | ---: | ---: |
{chr(10).join(event_lines)}

## Ten largest candidate components by characters

| Component | Members | Counted characters |
| --- | ---: | ---: |
{chr(10).join(component_lines) if component_lines else '| none | 0 | 0 |'}

## Blind spots

<!-- prose: blind-spots -->

| Blind spot | Detail |
| --- | --- |
{chr(10).join(blind_spot_lines)}
"""
        out = engagement / DEFAULT_REPORT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        return out

    components = read_components(bundle / "components.json")
    _, candidates = read_csv(
        bundle / "candidates.csv",
        required=["qualifiedName", "set", "countedCharacters"],
    )
    _, catalog = read_csv(
        bundle / "catalog.csv",
        required=[
            "qualifiedName", "kind", "countedCharacters", "lastExecutedDate",
            "lastExecutedDirect",
        ],
    )

    kind_counts = {
        kind: sum(row["kind"] == kind for row in catalog)
        for kind in ("class", "trigger")
    }
    by_rule = summary.get("byRule")
    if not isinstance(by_rule, dict):
        raise ContractError("catalog summary is missing byRule object")
    counted = by_rule.get("COUNTED", {})
    managed = by_rule.get("EXEMPT_MANAGED_PACKAGE", {})
    tests = by_rule.get("EXEMPT_TEST", {})

    window_start = ledger.get("windowStart")
    if not isinstance(window_start, str) or not window_start:
        raise ContractError("telemetry ledger windowStart must be a non-empty string")

    def executed_in_window(row: dict[str, str]) -> bool:
        return bool(row["lastExecutedDate"] and row["lastExecutedDate"] >= window_start)

    direct = [
        row for row in catalog if row["countedRule"] == "COUNTED"
        and executed_in_window(row) and row["lastExecutedDirect"] == "true"
    ]
    reachable = [
        row for row in catalog if row["countedRule"] == "COUNTED"
        and executed_in_window(row) and row["lastExecutedDirect"] == "false"
    ]
    test_only = [
        row for row in candidates
        if row["countedRule"] == "COUNTED" and row["set"] == "T"
    ]
    no_evidence = [
        row for row in candidates
        if row["countedRule"] == "COUNTED" and row["set"] == "U"
    ]
    buckets = [
        ("Observed running", direct),
        ("Reachable from observed code", reachable),
        ("Reachable only from tests", test_only),
        ("No evidence of use", no_evidence),
    ]
    bucket_lines = [
        f"| {label} | {len(rows):,} | {rows_characters(rows)} |"
        for label, rows in buckets
    ]

    sorted_components = sorted(
        components,
        key=lambda item: (
            -int(item.get("size", 0)),
            -int(item.get("countedCharacters", 0)),
            str(item.get("label", "")).casefold(),
        ),
    )
    component_lines = [
        f"| {item.get('label', '')} | {int(item.get('size', 0)):,} | "
        f"{component_characters(item)} |"
        for item in sorted_components
    ]
    blind_spot_lines = [
        f"| {BLIND_SPOT_DISPLAY_NAMES.get(name, name)} | {blind_spot_detail(value)} |"
        for name, value in sorted(blind_spots.items())
    ]

    reconciled = summary.get("reconciled")
    report = f"""# Candidate report

<!-- prose: headline -->

## Telemetry window

<!-- prose: window -->

| Fact | Value |
| --- | --- |
| Requested days | {ledger.get('requestedDays', 'unknown')} |
| Effective days | {ledger.get('effectiveDays', 'unknown')} |
| Window start | {ledger.get('windowStart', 'unknown')} |
| Window end | {ledger.get('windowEnd', 'unknown')} |
| File interval | {ledger.get('interval', 'unknown')} |

| Event type | Days processed | Span days | Missing days |
| --- | ---: | ---: | ---: |
{chr(10).join(event_lines)}

## Estate

<!-- prose: estate -->

| Fact | Value |
| --- | ---: |
| Components in catalog | {int(summary.get('rows', len(catalog))):,} |
| Classes | {kind_counts['class']:,} |
| Triggers | {kind_counts['trigger']:,} |
| Counted components | {int(counted.get('count', 0)):,} |
| Counted characters | {int(summary.get('countedCharactersTotal', 0)):,} |
| Managed-package exemptions | {int(managed.get('count', 0)):,} |
| Test-class exemptions | {int(tests.get('count', 0)):,} |
| Capacity reconciled | {'yes' if reconciled is True else 'no'} |

## Evidence buckets

<!-- prose: candidates -->

| Bucket | Classes / triggers | Counted characters |
| --- | ---: | ---: |
{chr(10).join(bucket_lines)}

## Candidate components

| Component | Members | Counted characters |
| --- | ---: | ---: |
{chr(10).join(component_lines)}

## Blind spots

<!-- prose: blind-spots -->

| Blind spot | Detail |
| --- | --- |
{chr(10).join(blind_spot_lines)}
"""
    out = engagement / DEFAULT_REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    return out


def run(args: argparse.Namespace) -> None:
    print(f"wrote {render_report(args.engagement)}")


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
