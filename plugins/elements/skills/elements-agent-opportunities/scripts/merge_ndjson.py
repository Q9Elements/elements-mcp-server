#!/usr/bin/env python3
"""Merge local newline-delimited JavaScript Object Notation (NDJSON) pages or parts.

Usage: python3 merge_ndjson.py 'scan-page-*.ndjson' scan-master.ndjson --expected 40 --key nodeId
Input: a directory of *page*.ndjson / *part*.ndjson files, or a quoted pattern.
Output: merged rows in numeric order and validation messages.
Exit 0: aggregate the master with Python. Exit 1: repair or download inputs and rerun.
Exit 2: fix command arguments using --help and rerun.
Check producer completion and failures before merging; counts alone establish row integrity.
"""
import argparse
import glob
import json
import os
import re
import sys


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; run {self.prog} --help, fix arguments and rerun")


def page_num(path):
    nums = re.findall(r"(\d+)", os.path.basename(path))
    return int(nums[-1]) if nums else 0


def main():
    ap = ActionParser()
    ap.add_argument("pages", help="pages directory or glob")
    ap.add_argument("master_out", help="output master.ndjson path")
    ap.add_argument("--expected", type=int, default=None, help="expected record count (manifest total)")
    ap.add_argument("--key", default=None, help="field to report distinct/duplicate counts on")
    args = ap.parse_args()

    # Restrict directory inputs to page/part files and exclude the master on repeated runs.
    patterns = ([args.pages] if any(c in args.pages for c in "*?[") else
                [os.path.join(args.pages, "*page*.ndjson"), os.path.join(args.pages, "*part*.ndjson")])
    out_abs = os.path.abspath(args.master_out)
    matched = {path for pattern in patterns for path in glob.glob(pattern)}
    files = [f for f in sorted(matched, key=lambda path: (page_num(path), path))
             if os.path.abspath(f) != out_abs]
    if not files:
        print(f"FAIL: no page or part files matched {args.pages}; download completed parts and rerun")
        return 1

    records, bad_lines, tp_hits = [], 0, 0
    with open(args.master_out, "w", encoding="utf-8") as out:
        for f in files:
            with open(f, encoding="utf-8") as source:
                text = source.read()
            if text and not text.endswith("\n"):
                text += "\n"  # defensive: keep pages cat-safe even if a page lacks the trailing newline
            out.write(text)
            for line in text.split('\n'):
                if not line.strip():
                    continue
                if "$$__tp__" in line:
                    tp_hits += 1
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        bad_lines += 1
                    else:
                        records.append(row)
                except json.JSONDecodeError:
                    bad_lines += 1

    total = len(records)
    checks = [("all lines are JSON objects", bad_lines == 0, f"{bad_lines} invalid row(s)")]
    if args.expected is not None:
        checks.append(("count == expected", total == args.expected, f"{total} vs expected {args.expected}"))
    checks.append(("no $$__tp__ leakage", tp_hits == 0, f"{tp_hits} line(s) contain $$__tp__"))
    if args.key:
        missing = sum(r.get(args.key) is None or r.get(args.key) == "" for r in records)
        checks.append((f"all rows have {args.key}", missing == 0, f"{missing} missing key(s)"))
        seen = [json.dumps(r.get(args.key), sort_keys=True) for r in records]
        distinct = len(set(seen))
        # distinct count is informational (some duplicates are legitimate org data), not a hard fail
        checks.append((f"distinct {args.key}", True, f"{distinct} distinct, {total - distinct} duplicate(s)"))

    ok = all(passed for _, passed, _ in checks)
    print(f"merged {len(files)} page/part file(s) -> {args.master_out}  ({total} records)")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("VERDICT:", "PASS: aggregate the master with Python" if ok else "FAIL: repair or download the input rows and rerun")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAIL: {exc}; repair the input or output path and rerun", file=sys.stderr)
        sys.exit(1)
