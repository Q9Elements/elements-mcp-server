#!/usr/bin/env python3
"""Recompute one object's free-text ratio from local Field rows.

Usage: python3 free_text_ratio.py 'fields-*.ndjson' --fields-total 56 --server-ratio 0.571
Input: newline-delimited JavaScript Object Notation (NDJSON) files; repeats collapse by nodeId.
Output: one JavaScript Object Notation (JSON) object with field lists, ratios and coverage warnings.
Exit 0: save the output and run rank_stop.py. Exit 2: repair or download the named
inputs and rerun; if unavailable, retain the server ratio and report the unresolved evidence.
Field definitions and query instructions are in ../references/scoring.md.
"""

import argparse
import glob
import json
import sys

LONG_TEXT_MIN_LENGTH = 256  # Long Text Area starts above the short Text Area limit of 255.


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; run {self.prog} --help, fix arguments and rerun")


def read_rows(paths):
    rows = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"error: {path}:{lineno} is not JSON ({exc}); repair or download the part and rerun", file=sys.stderr)
                    sys.exit(2)
                if not isinstance(rec, dict) or not isinstance(rec.get("nodeId"), str) or not rec["nodeId"]:
                    print(f"error: {path}:{lineno} needs a field row with nodeId; repair the input and rerun; recompute unavailable", file=sys.stderr)
                    sys.exit(2)
                rows[rec["nodeId"]] = rec
    return list(rows.values())


def expand_part_files(patterns):
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if not matches:
            print(f"error: no part file exists for {pattern}; download every completed part and rerun; recompute unavailable", file=sys.stderr)
            sys.exit(2)
        paths.extend(matches)
    return paths


def main():
    ap = ActionParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="NDJSON part files or quoted patterns from list_metadata_by_criteria over Field")
    ap.add_argument("--fields-total", type=int, help="scan row schema.fieldsTotal (coverage comparison)")
    ap.add_argument("--server-ratio", type=float, help="scan row schema.unstructuredRatio, echoed for comparison")
    ap.add_argument("--include-short-text-area", action="store_true", help="count short Text Area fields as free text")
    args = ap.parse_args()

    rows = read_rows(expand_part_files(args.files))
    if not rows:
        print("error: no field rows read; recompute unavailable, keep the server ratio and flag it", file=sys.stderr)
        sys.exit(2)

    objects = {((r.get("sf") or {}).get("fullApiName") or "").rsplit("/", 1)[0] for r in rows}
    objects.discard("")
    if len(objects) > 1:
        print(f"error: rows span more than one object: {sorted(objects)}; separate their parts and rerun", file=sys.stderr)
        sys.exit(2)

    long_text, rich_text, short_text = [], [], []
    for r in rows:
        details = r.get("nodeDetails") or {}
        name = (r.get("sf") or {}).get("apiName") or "?"
        subtype = details.get("subtype")
        length = details.get("length")
        if subtype == "Rich text area":
            rich_text.append(name)
        elif subtype == "Text area":
            if isinstance(length, (int, float)) and length >= LONG_TEXT_MIN_LENGTH:
                long_text.append(name)
            else:
                short_text.append(name)

    free = len(long_text) + len(rich_text) + (len(short_text) if args.include_short_text_area else 0)
    warnings = []
    denominator, source = len(rows), "fieldRows"
    if args.fields_total is not None:
        if args.fields_total != len(rows):
            warnings.append(
                f"query returned {len(rows)} field rows but the scan reports fieldsTotal {args.fields_total}; "
                "use the completed query rows as the denominator and note the mismatch"
            )

    print(json.dumps({
        "object": next(iter(objects), None),
        "fieldRows": len(rows),
        "longTextArea": sorted(long_text),
        "richTextArea": sorted(rich_text),
        "shortTextArea": sorted(short_text),
        "includesShortTextArea": args.include_short_text_area,
        "freeTextCount": free,
        "denominator": denominator,
        "denominatorSource": source,
        "recomputedRatio": round(free / denominator, 3) if denominator else None,
        "serverRatio": args.server_ratio,
        "warnings": warnings,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"error: {exc}; repair the input paths or rows and rerun", file=sys.stderr)
        sys.exit(2)
