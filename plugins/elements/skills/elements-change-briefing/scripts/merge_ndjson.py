#!/usr/bin/env python3
"""Merge verified newline-delimited JavaScript Object Notation (NDJSON) change parts.

list_metadata_changes supplies native row files. Save parsed, hydrated replies in
arrival order as a JavaScript Object Notation (JSON) array, and unchanged downloaded bytes in files named
changes-{resultId}-part-{index}.ndjson. The capture supplies identity, descriptors
and final totals; it contains no row data. Only the final computation is merged.

Usage:
  merge_ndjson.py <parts_dir_or_glob> <master_out> --capture <replies.json>
                  [--expected N] [--key FIELD]

--expected checks the manifest totalItems as well as final totalRows/totalItems.
--key reports distinct/duplicate values (use changeLogId, since nodeId repeats).
Checks cover completion, failures, indices, Secure Hash Algorithm 256-bit (SHA-256)
digests, bytes, rows, parsing and placeholder leakage. Hashes precede newline
repair. Exit 0: use the verified master. Exit 1: reacquire or reconcile the
capture and retry; any existing master is preserved. Exit 2: correct arguments
using --help.
The caller downloads parts immediately and discards held parts on identity change.
This script performs local verification only, with no network or polling calls.
"""
import argparse
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


PART_NAME = re.compile(r"changes-(.+)-part-(\d+)\.ndjson")


def nonnegative(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def capture_parts(path):
    """Accumulate descriptor segments, resetting held descriptors on identity change."""
    replies = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(replies, list) or not replies:
        raise ValueError("capture must be a nonempty array of hydrated native replies")
    result_id, parts = None, {}
    for reply in replies:
        identity = reply.get("resultId")
        if not isinstance(identity, str) or not identity:
            raise ValueError("capture reply is missing resultId")
        if identity != result_id:
            result_id, parts = identity, {}
        for part in reply.get("parts", []):
            index = nonnegative(part["index"], "part index")
            if part.get("format") != "ndjson":
                raise ValueError("merger requires NDJSON parts")
            nonnegative(part["rows"], "part rows")
            nonnegative(part["bytes"], "part bytes")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", part["sha256"]):
                raise ValueError(f"invalid sha256 for part {index}")
            # Refreshed signed links can change URL and expiry, but not held bytes.
            if index in parts and any(parts[index][key] != part[key]
                                      for key in ("format", "rows", "bytes", "sha256")):
                raise ValueError(f"conflicting descriptor for part {index}")
            parts[index] = part
    final = replies[-1]
    if final.get("status") != "complete":
        raise ValueError(f"capture is {final.get('status')!r}, not complete")
    if "nextPartsFrom" in final:
        raise ValueError("unconsumed descriptor segment: nextPartsFrom is present")
    if final.get("failed") or final.get("failedTotal") or final.get("failedFile"):
        raise ValueError("capture has unresolved component failures")
    count = nonnegative(final["partsTotal"], "partsTotal")
    if set(parts) != set(range(count)):
        raise ValueError(f"part indices must cover 0 through {count - 1} exactly")
    for key in ("totalRows", "totalItems"):
        nonnegative(final[key], key)
    return result_id, parts, final


def part_files(pattern, output, result_id, parts):
    """Select the final identity and reject multiple files for a single index."""
    files = {}
    for name in glob.glob(pattern):
        path = Path(name)
        if path.resolve() == output.resolve():
            continue
        match = PART_NAME.fullmatch(path.name)
        if not match:
            raise ValueError(f"invalid part filename: {path.name}")
        if match[1] != result_id:
            continue
        index = int(match[2])
        if index in files:
            raise ValueError(f"duplicate part index {index}")
        files[index] = path
    if set(files) != set(parts):
        raise ValueError("downloaded part indices do not match capture descriptors")
    return files


def merge(args):
    result_id, parts, final = capture_parts(args.capture)
    output = Path(args.master_out)
    pattern = (args.parts if any(c in args.parts for c in "*?[")
               else os.path.join(args.parts, "changes-*-part-*.ndjson"))
    files = part_files(pattern, output, result_id, parts)
    total, seen = 0, set()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as out:
            temp_path = Path(out.name)
            for index in sorted(files):
                data = files[index].read_bytes()
                part = parts[index]
                if hashlib.sha256(data).hexdigest() != part["sha256"].lower():
                    raise ValueError(f"sha256 mismatch for part {index}")
                if len(data) != part["bytes"]:
                    raise ValueError(f"byte count mismatch for part {index}")
                rows = 0
                for raw_line in data.split(b"\n"):
                    if raw_line.endswith(b"\r"):
                        raw_line = raw_line[:-1]
                    line = raw_line.decode("utf-8")
                    if not line.strip():
                        continue
                    if "$$__tp__" in line:
                        raise ValueError(f"$$__tp__ placeholder leakage in part {index}")
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError(f"part {index} contains a non-object row")
                    rows += 1
                    if args.key:
                        seen.add(json.dumps(record.get(args.key), sort_keys=True))
                if rows != part["rows"]:
                    raise ValueError(f"row count mismatch for part {index}: {rows} vs {part['rows']}")
                out.write(data)
                if data and not data.endswith(b"\n"):
                    out.write(b"\n")
                total += rows
        for label, expected in (("totalRows", final["totalRows"]),
                                ("totalItems", final["totalItems"]),
                                ("expected", args.expected)):
            if expected is not None and total != expected:
                raise ValueError(f"{total} vs {label} {expected}")
        temp_path.replace(output)
        print(f"merged {len(files)} part(s) for {result_id} -> {output} ({total} records)")
        if args.key:
            print(f"distinct {args.key}: {len(seen)} distinct, {total - len(seen)} duplicate(s)")
        print("VERDICT: PASS")
        return 0
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("parts", help="part directory or explicit part glob")
    ap.add_argument("master_out", help="output master.ndjson path")
    ap.add_argument("--capture", required=True, help="JSON array of hydrated native replies")
    ap.add_argument("--expected", type=int, help="expected record count from manifest totalItems")
    ap.add_argument("--key", help="field for informational distinct/duplicate counts")
    args = ap.parse_args()
    try:
        if args.expected is not None:
            nonnegative(args.expected, "expected")
        return merge(args)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"FAIL: {error}; reacquire or reconcile the capture, then retry.\nVERDICT: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
