"""Reconcile controlled and allowed automation against local rehearsal observations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Resolve shipped sibling modules when invoked with python3 -I.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .dli_common import ContractError, read_csv, read_json, write_csv, write_json
except ImportError:
    from dli_common import ContractError, read_csv, read_json, write_csv, write_json


COLUMNS = ["name", "type", "expectation", "observed_count", "result"]
UNKNOWN_TYPES = {"", "Automation", "Unknown"}


def predictions_from_checklist(checklist: list[dict[str, str]]) -> dict:
    predicted = {"expectedSilent": [], "expectedMayFire": []}
    for row in checklist:
        ruling = row.get("owner_ruling", "").strip()
        if ruling in {"deactivate", "bypass"}:
            field = "expectedSilent"
        elif ruling == "leave-on" or (row.get("automation_type") == "Apex Class" and ruling.startswith("review: ")):
            field = "expectedMayFire"
        else:
            raise ContractError("finalized checklist has an invalid or missing owner ruling")
        predicted[field].append({"apiName": row.get("automation_api_name", ""), "name": row.get("automation_name", ""), "type": row.get("automation_type", "")})
    return predicted


def validate_observed(observed: dict) -> None:
    counts = observed.get("errorCounts")
    if not isinstance(counts, dict) or not isinstance(observed.get("errorRowsRead"), int):
        raise ContractError("observed input needs aggregate error counts and errorRowsRead")
    if any(not isinstance(counts.get(code), int) or counts[code] < 0 for code in ("DUPLICATES_DETECTED", "UNABLE_TO_LOCK_ROW")):
        raise ContractError("observed input has invalid aggregate error counts")


def reconcile(predicted: dict, observed: dict, accepted_lock_errors: int | None = None,
              incident_class_rulings: list[dict] | None = None, data_dir: Path | None = None):
    if not isinstance(predicted, dict):
        raise ContractError("predicted input must contain expectedSilent and expectedMayFire arrays")
    predicted_rows = []
    identities = {}
    for field, expectation in (
        ("expectedSilent", "expected_silent"),
        ("expectedMayFire", "expected_may_fire"),
    ):
        values = predicted.get(field)
        if not isinstance(values, list):
            raise ContractError(f"predicted input field {field} must be an array")
        for row in values:
            canonical = row.get("apiName") or row.get("name")
            if not canonical:
                raise ContractError("predicted automation is missing apiName and name")
            identity = (canonical, row.get("type", ""))
            if identity in identities:
                if row.get("type") in {"Managed Package", "Duplicate Rule"}:
                    if identities[identity]["expectation"] != expectation:
                        raise ContractError(f"Managed Package {canonical} has conflicting expectations")
                    if row.get("name"):
                        identities[identity]["aliases"].add(row["name"])
                    continue
                raise ContractError(f"predicted automation appears more than once: {canonical}")
            aliases = {canonical}
            if row.get("name"):
                aliases.add(row["name"])
            predicted_row = {
                "type": row.get("type", ""),
                "name": canonical,
                "aliases": aliases,
                "expectation": expectation,
                "observed": 0,
            }
            predicted_rows.append(predicted_row)
            identities[identity] = predicted_row
    unmatched_observed = []
    for observation in observed.get("automations", []):
        matches = [
            row for row in predicted_rows
            if (
                (row["type"] in UNKNOWN_TYPES or row["type"] == observation["type"])
                and observation["name"] in row["aliases"]
            )
        ]
        if len(matches) == 1:
            matches[0]["observed"] += observation.get("fireCount", 0)
        else:
            unmatched_observed.append(observation)
    rows = []
    for predicted_row in sorted(predicted_rows, key=lambda item: (item["name"], item["type"])):
        actual = predicted_row["observed"]
        if predicted_row["expectation"] == "expected_silent":
            result = "control_failure" if actual else "silent_as_controlled"
        else:
            result = "observed_as_allowed" if actual else "informational_not_observed"
        rows.append({
            "name": predicted_row["name"], "type": predicted_row["type"],
            "expectation": predicted_row["expectation"], "observed_count": actual,
            "result": result,
        })
    for observation in sorted(unmatched_observed, key=lambda item: (item["name"], item["type"])):
        rows.append({
            "name": observation["name"], "type": observation["type"], "expectation": "unpredicted",
            "observed_count": observation.get("fireCount", 0), "result": "unpredicted",
        })
    control_failures = sorted(row["name"] for row in rows if row["result"] == "control_failure")
    informational = sorted(
        row["name"] for row in rows if row["result"] == "informational_not_observed"
    )
    unpredicted = sorted(row["name"] for row in rows if row["result"] == "unpredicted")
    complete = observed.get("complete") is True
    blockers = []
    if not complete:
        blockers.append("observation_incomplete")
    if control_failures:
        blockers.append("control_failure")
    if unpredicted:
        blockers.append("unpredicted_automation")
    error_counts = observed.get("errorCounts", {})
    duplicates = error_counts.get("DUPLICATES_DETECTED", 0)
    lock_errors = error_counts.get("UNABLE_TO_LOCK_ROW", 0)
    if lock_errors > (accepted_lock_errors if accepted_lock_errors is not None else 0):
        blockers.append("lock_errors")
    data_dir = data_dir or Path(__file__).resolve().parent.parent / "skills" / "data-load-impact" / "data"
    thresholds = {row["key"]: row["value"] for row in read_csv(data_dir / "thresholds.csv")[1]}
    threshold = int(thresholds["governor_limit_rehearsal_percent"])
    measured = []
    for ruling in incident_class_rulings or []:
        if ruling.get("ruling") != "measured-in-rehearsal":
            continue
        incident_class = ruling.get("incidentClass")
        if incident_class == "unexpected_email":
            count = observed.get("queuedEmails")
            result = ("not measurable for unexpected email" if count is None else
                      "blocker" if count > 0 else "measured clean")
            measured.append({"incidentClass": incident_class, "result": result, "queuedEmails": count})
        elif incident_class == "lock_contention":
            measured.append({"incidentClass": incident_class,
                             "result": f"measured {lock_errors} lock errors",
                             "lockErrors": lock_errors})
        elif incident_class == "governor_limit_failure":
            limits = observed.get("governorLimits", {})
            observed_packages = {
                row["name"] for row in observed.get("automations", [])
                if row.get("type") == "Managed Package" and row.get("fireCount", 0) > 0
            }
            not_measurable = [f"not measurable for {name}" for name in sorted(
                observed_packages - set(limits) | {name for name, values in limits.items() if not values}
            )]
            known_labels = {label for namespace_limits in limits.values() for label in namespace_limits}
            for namespace, namespace_limits in sorted(limits.items()):
                if namespace_limits:
                    not_measurable.extend(
                        f"not measurable for {namespace}: {label}"
                        for label in sorted(known_labels - set(namespace_limits))
                    )
            if not limits:
                not_measurable.insert(0, "not measurable for governor limits")
            high = [
                {"namespace": namespace, "limit": label, **value}
                for namespace, rows_by_limit in sorted(limits.items())
                for label, value in sorted(rows_by_limit.items())
                if value["ceiling"] <= 0 or value["used"] * 100 >= value["ceiling"] * threshold
            ]
            result = "blocker" if high else "measured clean" if not not_measurable else not_measurable[0]
            measured.append({"incidentClass": incident_class, "result": result,
                             "governorLimits": limits, "atOrAboveThreshold": high,
                             "notMeasurable": not_measurable})
        else:
            measured.append({"incidentClass": incident_class,
                             "result": f"not measurable for {incident_class.replace('_', ' ')}",
                             "measurement": "no debug-log measure for this class"})
    if any(row["result"] == "blocker" for row in measured):
        blockers.append("measured_incident_class")
    summary = {
        "evidenceComplete": complete,
        "controlFailures": control_failures,
        "unpredicted": unpredicted,
        "informationalNotObserved": informational,
        "duplicatesDetected": duplicates,
        "queuedEmails": observed.get("queuedEmails"),
        "lockErrors": lock_errors,
        "lockErrorsAccepted": accepted_lock_errors,
        "measuredIncidentClasses": measured,
        "blockers": blockers,
        "rehearsalPassed": not blockers,
    }
    return rows, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path)
    parser.add_argument("--observed", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--accepted-lock-errors", type=int)
    parser.add_argument("--parameters", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "skills" / "data-load-impact" / "data")
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.accepted_lock_errors is not None and arguments.accepted_lock_errors < 0:
            raise ContractError("accepted lock errors must be non-negative")
        observed = read_json(arguments.observed)
        validate_observed(observed)
        parameters = read_json(arguments.parameters)
        rulings = parameters.get("incidentClassRulings")
        if not isinstance(rulings, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("incidentClass"), str)
            or row.get("ruling") not in {"not-applicable", "measured-in-rehearsal"}
            for row in rulings
        ):
            raise ContractError("parameters need valid incidentClassRulings")
        rows, summary = reconcile(
            predictions_from_checklist(read_csv(arguments.checklist)[1]), observed,
            arguments.accepted_lock_errors,
            rulings,
            arguments.data_dir,
        )
        write_csv(arguments.out, COLUMNS, rows)
        if arguments.summary_out:
            write_json(arguments.summary_out, summary)
    except (ContractError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"reconciled {len(rows)} automation name(s); control failures: {len(summary['controlFailures'])}; "
        f"unpredicted: {len(summary['unpredicted'])}; evidence complete: {'yes' if summary['evidenceComplete'] else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
