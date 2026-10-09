#!/usr/bin/env python3
"""Recompute one object's free-text ratio from its query_metadata Field rows.

Input: one or more ndjson files or quoted page patterns written from
  query_metadata(metadataList: ["Field"],
                 filters: [{column: "full_api_name", operator: "startswith", value: "<ObjectApiName>/"}],
                 columns: ["full_api_name", "subtype", "length"], format: "ndjson", limit: 200)
(one file per page). Each row carries nodeDetails.subtype and nodeDetails.length.

Free text is a Long Text Area (subtype "Text area" with length > 255) or a Rich Text Area
(subtype "Rich text area"). A short Text Area (subtype "Text area", length <= 255 or absent) counts
only with --include-short-text-area. String, Email, Phone, Url, Encrypted string and every other
subtype are structured.

The denominator is --fields-total (the scan row's schema.fieldsTotal) when given, else the number of
distinct field rows. Prints one JSON object; exits 2 when no field rows were read (recompute
unavailable), a page pattern matches no files, or the rows span more than one object.
"""

import argparse
import glob
import json
import sys

LONG_TEXT_MIN_LENGTH = 256


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
                    sys.exit(f"error: {path}:{lineno} is not JSON ({exc})")
                sf = rec.get("sf") or {}
                key = sf.get("fullApiName") or rec.get("_id") or sf.get("apiName")
                rows[key] = rec
    return list(rows.values())


def expand_page_files(patterns):
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if not matches:
            print(f"error: no page file exists for {pattern}; recompute unavailable", file=sys.stderr)
            sys.exit(2)
        paths.extend(matches)
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="ndjson page files or quoted patterns from query_metadata over Field")
    ap.add_argument("--fields-total", type=int, help="scan row schema.fieldsTotal (denominator)")
    ap.add_argument("--server-ratio", type=float, help="scan row schema.unstructuredRatio, echoed for comparison")
    ap.add_argument("--include-short-text-area", action="store_true", help="count short Text Area fields as free text")
    args = ap.parse_args()

    rows = read_rows(expand_page_files(args.files))
    if not rows:
        print("error: no field rows read; recompute unavailable, keep the server ratio and flag it", file=sys.stderr)
        sys.exit(2)

    objects = {((r.get("sf") or {}).get("fullApiName") or "").split("/", 1)[0] for r in rows}
    objects.discard("")
    if len(objects) > 1:
        print(f"error: rows span more than one object: {sorted(objects)}", file=sys.stderr)
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
    if args.fields_total:
        denominator, source = args.fields_total, "scan fieldsTotal"
        if args.fields_total != len(rows):
            warnings.append(
                f"query returned {len(rows)} field rows but the scan reports fieldsTotal {args.fields_total}; "
                "check for a missed page before trusting the ratio"
            )
    else:
        denominator, source = len(rows), "fieldRows"

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
    main()
