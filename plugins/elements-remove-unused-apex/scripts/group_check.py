#!/usr/bin/env python3
"""Check that review grouping follows selected capacity packages."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from apex_common import (
    ContractError, cli_guard, parse_int, read_csv, read_json_array, write_json,
)


GROUP_COLUMNS = ["groupLabel", "groupOrder", "groupNote"]
REQUIRED = [
    "qualifiedName", "countedCharacters", "componentLabel", "bucket", "reasons",
    *GROUP_COLUMNS,
]
BARE_NOTES = {"misc", "miscellaneous", "other", "others", "everything else", "rest", "the rest"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reasoned", required=True, type=Path, help="work/reasoned-candidates.csv")
    parser.add_argument(
        "--packages", required=True, type=Path,
        help="required work/triage/packages.json",
    )
    parser.add_argument("--summary-out", type=Path, help="write the per-group summary as JSON")
    return parser


def check_groups(
    rows: list[dict[str, str]],
    *,
    packages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return the ordered group summary, or raise ContractError listing every violation."""
    problems: list[str] = []
    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    order_of: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        reasons = [
            reason.strip()
            for reason in row["reasons"].split(";")
            if reason.strip()
        ]
        if row["bucket"] == "confident" and reasons:
            problems.append(
                f"{row['qualifiedName']}: confident but carries reasons {row['reasons']}"
            )
        if row["bucket"] == "review-first" and not reasons:
            problems.append(f"{row['qualifiedName']}: review-first with no reason")
        label = row["groupLabel"].strip()
        if not label:
            problems.append(f"{row['qualifiedName']}: no groupLabel")
            continue
        order = parse_int(row["groupOrder"], field=f"groupOrder of {row['qualifiedName']}")
        by_label[label].append(row)
        order_of[label].add(order)

    for label, orders in order_of.items():
        if len(orders) != 1:
            problems.append(f"group {label!r} carries several groupOrder values {sorted(orders)}")
    labels_by_order: dict[int, set[str]] = defaultdict(set)
    for label, orders in order_of.items():
        for order in orders:
            labels_by_order[order].add(label)
    for order, labels in labels_by_order.items():
        if len(labels) != 1:
            problems.append(f"groupOrder {order} used by several groups {sorted(labels)}")

    count = len(by_label)
    if count < 1:
        problems.append("selected packages require at least one group")
    expected_orders = set(range(1, count + 1))
    actual_orders = {min(orders) for orders in order_of.values() if orders}
    if actual_orders != expected_orders:
        problems.append(f"groupOrder values {sorted(actual_orders)} are not 1..{count}")

    selected_packages = sorted(
        [package for package in packages if package.get("status") == "selected"],
        key=lambda package: int(package.get("selectionOrder", 0)),
    )
    package_members = [
        {str(member) for member in package.get("members", [])}
        for package in selected_packages
    ]
    expected_names = set().union(*package_members) if package_members else set()
    actual_names = {row["qualifiedName"] for row in rows}
    if actual_names != expected_names:
        problems.append(
            f"grouping rows {sorted(actual_names)} do not match selected package members "
            f"{sorted(expected_names)}"
        )
    row_by_name = {row["qualifiedName"]: row for row in rows}
    for package_order, (package, members) in enumerate(
        zip(selected_packages, package_members), start=1
    ):
        labels = {
            row_by_name[name]["groupLabel"]
            for name in members if name in row_by_name
        }
        orders = {
            parse_int(row_by_name[name]["groupOrder"], field="groupOrder")
            for name in members if name in row_by_name
        }
        if len(labels) != 1:
            problems.append(
                f"package {package.get('packageId')} is split across groups {sorted(labels)}"
            )
        if orders != {package_order}:
            problems.append(
                f"package {package.get('packageId')} must be groupOrder {package_order}, "
                f"got {sorted(orders)}"
            )

    def characters(row: dict[str, str]) -> int:
        return parse_int(row["countedCharacters"], allow_empty=True, field="countedCharacters") or 0

    summary = []
    for label, members in by_label.items():
        notes = {member["groupNote"].strip() for member in members}
        if len(notes) != 1:
            problems.append(f"group {label!r}: groupNote differs between rows")
        note = next(iter(notes))
        if not note:
            problems.append(f"group {label!r}: empty groupNote")
        elif "\n" in note or "\r" in note:
            problems.append(f"group {label!r}: groupNote spans several lines")
        elif note.rstrip(".").lower() in BARE_NOTES:
            problems.append(f"group {label!r}: groupNote {note!r} says nothing about its contents")
        summary.append({
            "groupOrder": min(order_of[label]) if order_of[label] else None,
            "groupLabel": label,
            "members": len(members),
            "rows": len(members),
            "components": len({member["componentLabel"] for member in members}),
            "countedCharacters": sum(characters(member) for member in members),
            "unknownLengthMembers": sum(not member["countedCharacters"].strip() for member in members),
            "groupNote": note,
        })

    summary.sort(key=lambda group: (group["groupOrder"] is None, group["groupOrder"]))
    if problems:
        raise ContractError(
            "grouping violates one group per selected package:\n  - "
            + "\n  - ".join(problems)
        )
    return summary


def characters_phrase(known: int, unknown: int, size: int) -> str:
    if not unknown:
        return f"{known:,} characters"
    if unknown >= size and not known:
        return "unknown characters"
    return f"{known:,} characters plus {unknown:,} of unknown length"


def run(args: argparse.Namespace) -> None:
    _, rows = read_csv(args.reasoned, required=REQUIRED)
    if not rows:
        raise ContractError(f"{args.reasoned} has no rows")
    raw_packages = read_json_array(args.packages, "triage packages")
    if not all(isinstance(package, dict) for package in raw_packages):
        raise ContractError(f"{args.packages} must contain package objects")
    summary = check_groups(rows, packages=raw_packages)
    total = sum(group["countedCharacters"] for group in summary)
    unknown_total = sum(group["unknownLengthMembers"] for group in summary)
    total_text = characters_phrase(total, unknown_total, len(rows))
    print(f"grouping OK: {len(summary)} groups, {len(rows)} rows, {total_text}")
    for group in summary:
        group_text = characters_phrase(
            group["countedCharacters"], group["unknownLengthMembers"], group["members"]
        )
        if not unknown_total:
            share = (group["countedCharacters"] / total) if total else 0
            group_text += f" ({share:.1%})"
        print(f"  {group['groupOrder']:>2}. {group['groupLabel']}: {group['members']} members, {group_text}")
    if args.summary_out:
        write_json(args.summary_out, summary)


def main() -> int:
    args = build_parser().parse_args()
    return cli_guard(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
