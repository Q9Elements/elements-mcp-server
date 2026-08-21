#!/usr/bin/env python3
"""Diff two captured metadata-XML snapshots (previous vs current), the change-briefing skill's
client-side equivalent of the Elements changelog dialog's side-by-side view.

The skill writes each version to its own file (via get_node_change_history with a changeLogId),
then runs this to surface only the delta; the raw XML stays on disk, never re-read into context.

Usage:
  diff_xml.py --current <file> [--previous <file>] [--out <file>] [--raw]

  --current FILE    the newer version's XML (required)
  --previous FILE   the older version's XML; omit/empty => node is new in range (all additions)
  --out FILE        write the unified diff here instead of stdout
  --raw             skip XML pretty-normalization (diff the bytes as stored)

Exit 0 always (a diff, even empty, is a valid result). Stdlib only.
"""
import argparse
import difflib
import os
import sys
import xml.dom.minidom as minidom


def load(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def normalize(text):
    """Pretty-print XML to cut whitespace/ordering noise. Tolerant: non-XML (e.g. an Apex body
    appended after the XML header) falls back to the raw text so the diff still runs."""
    if text is None:
        return None
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
