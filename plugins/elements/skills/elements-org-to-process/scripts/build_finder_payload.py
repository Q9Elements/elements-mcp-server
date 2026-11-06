#!/usr/bin/env python3
"""Usage: python3 build_finder_payload.py RESULT [--transitions FILE] [--check] [--output payload.json]

RESULT is a hydrated get_process_map JavaScript Object Notation (JSON) object.
Exit 0: counts checked or payload written; build the payload or apply the rubric next.
Exit 1: incomplete evidence; recover the named array and re-run.
Exit 2: invalid input or local file failure; correct the named input/path and re-run.
"""
import argparse
import json
from pathlib import Path
import sys


class Parser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; use --help, correct the arguments and re-run.")


def main():
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("result", type=Path)
    parser.add_argument("--transitions", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("payload.json"))
    args = parser.parse_args()
    try:
        result = json.loads(args.result.read_text(encoding="utf-8"))
        if args.transitions:
            result["transitions"] = json.loads(args.transitions.read_text(encoding="utf-8"))
        metadata = result["metadata"]
        for field, count in (("activities", "activityCount"), ("transitions", "transitionCount")):
            if type(metadata[count]) is not int or metadata[count] < 0:
                raise ValueError(f"metadata.{count} must be a nonnegative integer")
            rows = result.get(field)
            if not isinstance(rows, list) or len(rows) != metadata[count]:
                got = len(rows) if isinstance(rows, list) else "unavailable"
                print(f"{field}: recovered {got}, expected {metadata[count]}; recover the complete array and re-run.", file=sys.stderr)
                return 1
        if args.check:
            print("Counts match; build the rubric payload next.")
            return 0
        activities = []
        for activity in result["activities"]:
            row = {"id": activity["id"], "text": activity["text"],
                   "resources": [{key: resource[key] for key in ("name", "type") if key in resource}
                                 for resource in activity.get("resources", [])]}
            for target, endpoint in (("inputFlowlines", "toActivityId"), ("outputFlowlines", "fromActivityId")):
                row[target] = [{"id": line["id"], "text": line.get("label", "")}
                               for line in result["transitions"] if line[endpoint] == activity["id"]]
            activities.append(row)
        payload = {"processName": metadata.get("name", ""), "processDescription": metadata.get("description", ""),
                   "activities": activities}
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(f"Cannot build payload: {error}; correct the hydrated input or output path and re-run.", file=sys.stderr)
        return 2
    print("Payload written; apply the Agent Finder rubric next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
