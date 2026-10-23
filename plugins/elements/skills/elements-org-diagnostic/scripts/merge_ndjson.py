#!/usr/bin/env python3
"""Merge local newline-delimited JavaScript Object Notation (JSON) object pages.

Usage: merge_ndjson.py PAGES_OR_GLOB MASTER_OUT [--expected N] [--key FIELD]
Input: one area's or slice's page/part files; required row field and expected count.
Exit 0: checks pass; aggregate rows and reconcile reported duplicate keys.
Exit 1: input/check/output failure; repair or reacquire pages and re-run.
Exit 2: invalid arguments; run --help and correct the command.
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


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}. Run --help and correct the command.")


def main():
    ap = ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", help="pages directory or glob")
    ap.add_argument("master_out", help="output master.ndjson path")
    ap.add_argument("--expected", type=int, default=None, help="expected count (summary pagination.totalItems or drill totalItems)")
    ap.add_argument("--key", default=None, help="required row field for distinct/duplicate counts")
    args = ap.parse_args()

    # Accept locally serialized pages and downloaded parts; exclude the merged output.
    patterns = ([args.pages] if any(c in args.pages for c in "*?[") else
                [os.path.join(args.pages, "*page*.ndjson"), os.path.join(args.pages, "*part*.ndjson")])
    out_abs = os.path.abspath(args.master_out)
    matches = {f for pattern in patterns for f in glob.glob(pattern)}
    files = [f for f in sorted(matches, key=lambda f: (page_num(f), f)) if os.path.abspath(f) != out_abs]
    if not files:
        print(f"FAIL: no page or part files matched {patterns}. Acquire page files, then re-run.")
        return 1

    records, bad_lines, bad_rows, tp_hits = [], 0, 0, 0
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
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                if not isinstance(row, dict):
                    bad_rows += 1
                    continue
                records.append(row)

    total = len(records)
    checks = [("all lines parse", bad_lines == 0, f"{bad_lines} unparseable line(s)")]
    checks.append(("all rows are objects", bad_rows == 0, f"{bad_rows} non-object row(s)"))
    if args.expected is not None:
        checks.append(("count == expected", total == args.expected, f"{total} vs expected {args.expected}"))
    checks.append(("no $$__tp__ leakage", tp_hits == 0, f"{tp_hits} line(s) contain $$__tp__"))
    if args.key:
        missing = sum(r.get(args.key) is None for r in records)
        checks.append((f"all rows have {args.key}", missing == 0, f"{missing} missing/null key(s)"))
        seen = [json.dumps(r.get(args.key), sort_keys=True) for r in records]
        distinct = len(set(seen))
        # distinct count is informational (some duplicates are legitimate org data), not a hard fail
        checks.append((f"distinct {args.key}", True, f"{distinct} distinct, {total - distinct} duplicate(s)"))

    ok = all(passed for _, passed, _ in checks)
    print(f"merged {len(files)} page/part file(s) -> {args.master_out}  ({total} records)")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print("VERDICT:", "PASS: Aggregate validated rows; resolve duplicates before claiming coverage."
          if ok else "FAIL: Reacquire or repair the input pages or expected count, then re-run.")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError) as error:
        print(f"FAIL: {error}. Check input readability and output path, then re-run.")
        sys.exit(1)
