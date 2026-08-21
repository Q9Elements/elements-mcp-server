#!/usr/bin/env python3
"""Merge + verify NDJSON page files from an MCP Tier-2 fan-out.

NOTE: identical copies of this script ship in elements-org-diagnostic and
elements-change-briefing (skills are self-contained); edit both together.

Per-page subagents each write one NDJSON page (the `data` string from a tool call with
format:"ndjson"). This concatenates those pages into one master file in NUMERIC page order
and VERIFIES the merge, so silent corruption (e.g. a missing trailing newline joining the
last record of one page to the first of the next) is caught instead of trusted.

Usage:
  merge_ndjson.py <pages_dir_or_glob> <master_out> [--expected N] [--key FIELD]

  <pages_dir_or_glob>  a directory of *.ndjson pages, or a glob like 'dir/page-*.ndjson'
  <master_out>         path to write the merged master.ndjson
  --expected N         expected record count (the manifest totalItems / totalObjects)
  --key FIELD          field to report distinct/duplicate counts on (e.g. _id, name)

Exit 0 = all checks pass, 1 = a check failed. Aggregate the master with jq/python afterward;
do not read the whole master back into the agent's context.
"""
import argparse
import glob
import json
import os
import re
import sys


def page_num(path):
    nums = re.findall(r"(\d+)", os.path.basename(path))
    return int(nums[-1]) if nums else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", help="pages directory or glob")
    ap.add_argument("master_out", help="output master.ndjson path")
    ap.add_argument("--expected", type=int, default=None, help="expected record count (manifest total)")
    ap.add_argument("--key", default=None, help="field to report distinct/duplicate counts on")
    args = ap.parse_args()

    # Default to *page*.ndjson (not *.ndjson) so the master we write (or any other ndjson in the dir)
    # is not re-ingested on a re-run; also explicitly exclude the output path.
    pattern = args.pages if any(c in args.pages for c in "*?[") else os.path.join(args.pages, "*page*.ndjson")
    out_abs = os.path.abspath(args.master_out)
    files = [f for f in sorted(glob.glob(pattern), key=page_num) if os.path.abspath(f) != out_abs]
    if not files:
        print(f"FAIL: no page files matched {pattern}")
        return 1

    records, bad_lines, tp_hits = [], 0, 0
    with open(args.master_out, "w") as out:
        for f in files:
            text = open(f).read()
            if text and not text.endswith("\n"):
                text += "\n"  # defensive: keep pages cat-safe even if a page lacks the trailing newline
            out.write(text)
            for line in text.splitlines():
                if not line.strip():
                    continue
                if "$$__tp__" in line:
                    tp_hits += 1
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    bad_lines += 1

    total = len(records)
    checks = [("all lines parse", bad_lines == 0, f"{bad_lines} unparseable line(s)")]
    if args.expected is not None:
        checks.append(("count == expected", total == args.expected, f"{total} vs expected {args.expected}"))
    checks.append(("no $$__tp__ leakage", tp_hits == 0, f"{tp_hits} line(s) contain $$__tp__"))
    if args.key:
        seen = [json.dumps(r.get(args.key), sort_keys=True) for r in records]
        distinct = len(set(seen))
        # distinct count is informational (some duplicates are legitimate org data), not a hard fail
        checks.append((f"distinct {args.key}", True, f"{distinct} distinct, {total - distinct} duplicate(s)"))

    ok = all(passed for _, passed, _ in checks)
    print(f"merged {len(files)} page(s) -> {args.master_out}  ({total} records)")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
