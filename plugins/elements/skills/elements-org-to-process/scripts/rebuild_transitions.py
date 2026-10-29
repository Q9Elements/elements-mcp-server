#!/usr/bin/env python3
"""Usage: python3 rebuild_transitions.py INPUT --expected N [--output transitions.json]

INPUT is a downloaded ZIP archive or its extracted 1.json level.
Exit 0: rebuilt; run the payload validator next.
Exit 1: count mismatch; recover the complete export and re-run.
Exit 2: invalid input or local file failure; correct the named input/path and re-run.
"""
import argparse
from html import unescape
import json
from pathlib import Path
import re
import sys
import zipfile


def clean_text(text):
    text = unescape(text or "")
    text = re.sub(r"<br\s*/?\s*>", " ", text, flags=re.I)
    text = re.sub(r"<div[^>]*>", " ", text)
    text = re.sub(r"</div>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^AND\s+", "", text, flags=re.I)
    text = re.sub(r'"([^"]*)"', r"'\1'", text)
    return text.strip()


class Parser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; use --help, correct the arguments and re-run.")


def main():
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path("transitions.json"))
    args = parser.parse_args()
    try:
        if zipfile.is_zipfile(args.input):
            with zipfile.ZipFile(args.input) as bundle:
                level = json.loads(bundle.read("1.json").decode("utf-8"))
        else:
            level = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(level["flowlines"], list) or not isinstance(level["activities"], list):
            raise ValueError("activities and flowlines must be arrays")
        activity_keys = {activity["mxKey"] for activity in level["activities"]}
        transitions = [{
            "id": "transition:" + line["mxKey"],
            "fromActivityId": "activity:" + line["srcId"] if line.get("srcId") in activity_keys else None,
            "toActivityId": "activity:" + line["tgtId"] if line.get("tgtId") in activity_keys else None,
            "label": clean_text(line.get("text")),
        } for line in level["flowlines"]]
        if len(transitions) != args.expected:
            print(f"rebuilt {len(transitions)}, expected {args.expected}; recover the complete export and re-run.", file=sys.stderr)
            return 1
        args.output.write_text(json.dumps(transitions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"Cannot rebuild: {error}; correct the input/export or output path and re-run.", file=sys.stderr)
        return 2
    print(f"Rebuilt {len(transitions)} transitions; run build_finder_payload.py --check next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
