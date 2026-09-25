#!/usr/bin/env python3
"""Diff two captured metadata snapshots (previous vs current), the change-briefing skill's
client-side equivalent of the Elements changelog dialog's side-by-side view.

The skill writes each version to its own file (via get_node_change_history with a changeLogId),
then runs this to surface only the delta; the raw snapshot stays on disk, never re-read into context.

Snapshot formats, detected from content (not file extension):
  XML   (classic Metadata API types)        -> pretty-printed with minidom
  JSON  (Data Cloud types, e.g. Data Transform) -> re-serialized with sorted keys, 2-space indent,
                                                so key-order noise does not show as a change;
                                                numbers keep their source text exactly
  other (e.g. XML followed by an Apex body)  -> diffed as raw text

Usage:
  diff_xml.py --current <file> [--previous <file>] [--out <file>] [--raw]

  --current FILE    the newer version's snapshot (required)
  --previous FILE   the older version's snapshot; omit/empty => node is new in range (all additions)
  --out FILE        write the unified diff here instead of stdout
  --raw             skip XML/JSON normalization (diff the bytes as stored)

Exit 0 always (a diff, even empty, is a valid result). Stdlib only.
"""
import argparse
import difflib
import json
import os
import sys
import xml.dom.minidom as minidom


def load(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


class RawNumber(str):
    """A JSON number kept as its source text, so float rounding never hides a change."""


def dump_json(value, indent=0):
    """Serialize like json.dumps(indent=2, sort_keys=True), writing numbers verbatim."""
    pad, inner = "  " * indent, "  " * (indent + 1)
    if isinstance(value, RawNumber):
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = (
            f"{inner}{json.dumps(key, ensure_ascii=False)}: {dump_json(value[key], indent + 1)}"
            for key in sorted(value)
        )
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = (f"{inner}{dump_json(item, indent + 1)}" for item in value)
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return json.dumps(value, ensure_ascii=False)


def normalize(text):
    """Normalize a snapshot to cut whitespace/ordering noise: JSON gets sorted keys and a fixed
    indent with every number written as its source text, XML is pretty-printed. Anything that parses as neither (e.g. an Apex body appended
    after the XML header) falls back to the raw text so the diff still runs."""
    if text is None:
        return None
    try:
        parsed = json.loads(text, parse_float=RawNumber, parse_int=RawNumber)
        return dump_json(parsed)
    except ValueError:
        pass
    try:
        pretty = minidom.parseString(text.encode("utf-8")).toprettyxml(indent="  ")
        # drop blank lines minidom sprinkles in
        return "\n".join(line for line in pretty.splitlines() if line.strip())
    except Exception:
        return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--previous", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()

    current = load(args.current)
    if current is None:
        print(f"FAIL: --current file not found or empty: {args.current}")
        return 1
    previous = load(args.previous)

    prep = (lambda t: t) if args.raw else normalize
    cur_lines = (prep(current) or "").splitlines()

    if previous is None or not previous.strip():
        out = (
            f"# No previous version for {os.path.basename(args.current)}; "
            f"node is new in range (all {len(cur_lines)} lines added).\n"
        )
    else:
        prev_lines = (prep(previous) or "").splitlines()
        diff = list(
            difflib.unified_diff(
                prev_lines,
                cur_lines,
                fromfile=os.path.basename(args.previous),
                tofile=os.path.basename(args.current),
                lineterm="",
            )
        )
        adds = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        dels = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        summary = (
            f"# {os.path.basename(args.previous)} -> {os.path.basename(args.current)}: "
            f"+{adds} / -{dels} lines"
            + ("  (identical after normalization)" if not diff else "")
        )
        out = summary + "\n" + ("\n".join(diff) + "\n" if diff else "")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"wrote diff -> {args.out}")
        print(out.splitlines()[0] if out else "")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
