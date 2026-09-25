#!/usr/bin/env python3
"""Write bounded reasoning payloads for the selected capacity packages."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import shutil
import sys
from pathlib import Path

from apex_common import (
    ContractError,
    cli_guard,
    default_data_dir,
    parse_float,
    parse_int,
    read_csv,
    read_json_array,
    read_json_object,
    read_table,
    safe_filename,
    write_json,
)


def build_package_payloads(
    package: dict[str, object],
    rows: list[dict[str, str]],
    *,
    fragment_size: int,
) -> list[tuple[str, dict[str, object]]]:
    """Return filename units and payloads containing only their assigned rows."""
    package_id = str(package.get("packageId", ""))
    component_label = str(package.get("componentLabel", ""))
    if not package_id or safe_filename(package_id) != package_id:
        raise ContractError(f"invalid packageId for reasoning payload: {package_id!r}")
    if not component_label:
        raise ContractError(f"{package_id}: componentLabel is required")
    if fragment_size < 1:
        raise ContractError("reasoning fragment size must be positive")
    expected = [str(name) for name in package.get("members", [])]
    by_name = {row["qualifiedName"]: row for row in rows}
    if len(by_name) != len(rows) or set(by_name) != set(expected):
        raise ContractError(
            f"{package_id}: candidate rows must match package members"
        )
    ordered_rows = [by_name[name] for name in expected]
    chunks = [
        ordered_rows[index:index + fragment_size]
        for index in range(0, len(ordered_rows), fragment_size)
    ]
    if not chunks:
        raise ContractError(f"{package_id}: selected package has no members")
    total = len(chunks)
    payloads = []
    for index, assigned in enumerate(chunks, start=1):
        fragment = {"index": index, "of": total} if total > 1 else None
        unit = f"{package_id}-fragment-{index}" if fragment else package_id
        payloads.append((unit, {
            "packageId": package_id,
            "componentLabel": component_label,
            "package": {
                key: package.get(key)
                for key in (
                    "packageId", "selectionOrder", "countedCharacters",
                    "runningCharacters", "inUseBecause", "keptBecause",
                    "tests", "testOnly",
                    "entryPointSignal", "reviewerText",
                )
            },
            "component": package.get("componentContext"),
            "fragment": fragment,
            "assignedMembers": assigned,
            "rows": assigned,
        }))
    return payloads


def pack_batches(
    units: list[tuple[str, int, bool]], *, batch_size: int,
) -> list[dict[str, object]]:
    """Group ``(unit, rows, isFragment)`` units, in order, into batches of at most ``batch_size`` rows.

    A fragment unit is always a batch on its own; a package unit joins the current batch while the batch's
    row total stays at or below ``batch_size``.
    """
    batches: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for unit, rows, is_fragment in units:
        if is_fragment or current is None or int(current["rows"]) + rows > batch_size:
            current = {"batch": f"batch-{len(batches) + 1:02d}", "units": [], "rows": 0}
            batches.append(current)
        current["units"].append(unit)
        current["rows"] = int(current["rows"]) + rows
        if is_fragment:
            current = None
    return batches


def _threshold(data_dir: Path, threshold_id: str) -> int:
    rows = read_table(
        data_dir, "thresholds.csv",
        ["id", "name", "value", "unit", "how_computed", "who_sets", "used_by"],
    )
    row = next((item for item in rows if item["id"] == threshold_id), None)
    if row is None:
        raise ContractError(f"missing threshold {threshold_id} in thresholds.csv")
    value = parse_float(row["value"], field=f"{threshold_id} value")
    if not value.is_integer():
        raise ContractError(f"{threshold_id} value must be an integer")
    return int(value)


def write_reasoning_payloads(engagement: Path, data_dir: Path) -> int:
    """Write one payload per package or fragment, batch them in the manifest, and return the file count."""
    work = engagement / "work"
    state = read_json_object(engagement / "execution-state.json", "execution state")
    packages = read_json_array(work / "triage" / "packages.json", "triage packages")
    _, candidates = read_csv(
        work / "bundle" / "candidates.csv",
        required=["qualifiedName", "componentLabel"],
    )
    by_name = {row["qualifiedName"]: row for row in candidates}
    reasoning = state.get("reasoning", {})
    configured_size = reasoning.get("fragmentSize") if isinstance(reasoning, dict) else None
    fragment_size = (
        parse_int(str(configured_size), field="reasoning.fragmentSize")
        if configured_size is not None else _threshold(data_dir, "T-3")
    )
    mass_cluster = _threshold(data_dir, "T-6")
    slots = state.get("slots", {})
    bundle_state = state.get("bundle", {})
    if not isinstance(slots, dict) or not isinstance(bundle_state, dict):
        raise ContractError("execution state slots and bundle must be objects")
    output_dir = work / "reasoning"
    previous_units = [
        *output_dir.glob("payload-*.json"),
        *output_dir.glob("return-*.json"),
    ] if output_dir.exists() else []
    if previous_units:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = output_dir / "previous" / timestamp
        archive.mkdir(parents=True)
        for path in previous_units:
            shutil.move(str(path), archive / path.name)
    count = 0
    units: list[str] = []
    sized_units: list[tuple[str, int, bool]] = []
    for raw_package in packages:
        if not isinstance(raw_package, dict) or raw_package.get("status") != "selected":
            continue
        names = [str(name) for name in raw_package.get("members", [])]
        try:
            rows = [by_name[name] for name in names]
        except KeyError as exc:
            raise ContractError(
                f"{raw_package.get('packageId')}: package member absent from candidates.csv: {exc.args[0]}"
            ) from None
        for unit, payload in build_package_payloads(
            raw_package, rows, fragment_size=fragment_size,
        ):
            payload.update({
                "refModelId": slots.get("model_id"),
                "teamId": slots.get("space_id"),
                "window": {
                    "start": bundle_state.get("windowStart"),
                    "end": bundle_state.get("windowEnd"),
                },
                "thresholds": {"massDeploymentCluster": mass_cluster},
                "vocab": {
                    "rescueSignals": "skills/remove-unused-apex/data/rescue-signals.csv",
                    "verdicts": "skills/remove-unused-apex/data/verdicts.csv",
                    "reviewFirstReasons": "skills/remove-unused-apex/data/review-first-reasons.csv",
                    "incomingEdgeReading": "skills/remove-unused-apex/data/incoming-edge-reading.csv",
                },
            })
            write_json(output_dir / f"payload-{unit}.json", payload)
            units.append(unit)
            sized_units.append((unit, len(payload["assignedMembers"]), payload["fragment"] is not None))
            count += 1
    write_json(output_dir / "manifest.json", {
        "units": units,
        "batches": pack_batches(sized_units, batch_size=fragment_size),
    })
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engagement", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(__file__))
    return parser


def run(args: argparse.Namespace) -> None:
    count = write_reasoning_payloads(args.engagement, args.data_dir)
    print(f"wrote {count} reasoning payloads")


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
