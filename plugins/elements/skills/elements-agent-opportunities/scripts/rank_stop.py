#!/usr/bin/env python3
"""Verify the shortlist against the entire local scan corpus.

Usage: python3 rank_stop.py scan-master.ndjson [ratio.json ...]
Each ratio file is free_text_ratio.py output; an unavailable attempt uses
{"object":"Object1__c","recomputedRatio":null,"reason":"returned refusal"}.
Exit 0: verified, build the report. Exit 3: recompute nextNodeIds and rerun.
Exit 2: unresolved, repair inputs or report the returned unavailable evidence.
Prints JavaScript Object Notation (JSON), including every ranked row and its source.
"""
import argparse
import json
import math
from pathlib import Path
import sys

FREE_TEXT_POINTS = 28  # The workflow replaces the free-text contribution with 0.28 * 100 * ratio.
FINALISTS = 3  # The report selects three finalists by default.


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(f"{message}; run {self.prog} --help, fix arguments and rerun")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Scores, contributions and ratios must be finite numbers")
    return value


def rank(args):
    rows = [json.loads(line) for line in args.master.read_text().split('\n') if line.strip()]
    if not rows:
        raise ValueError("Empty corpus: report no candidates rather than a verified top three")
    identifiers, names = set(), set()
    for row in rows:
        if not row["nodeId"] or row["nodeId"] in identifiers or row["apiName"] in names:
            raise ValueError("Duplicate or missing object identity: reacquire a unique scan corpus")
        identifiers.add(row["nodeId"])
        names.add(row["apiName"])
        number(row["score"])
        factors = [f for f in row["scoreFactors"] if f["factor"] == "unstructuredRatio"]
        if len(factors) != 1:
            raise ValueError("Read detail:full scan rows with one unstructuredRatio factor")
        number(factors[0]["contribution"])
    ratios = {}
    for path in args.ratios:
        data = json.loads(path.read_text())
        name = data["object"].rsplit("/", 1)[-1]
        if name not in names or name in ratios:
            raise ValueError(f"Unmatched or duplicate ratio object: {name}")
        ratio = data["recomputedRatio"]
        if ratio is not None and not 0 <= number(ratio) <= 1:
            raise ValueError(f"Ratio for {name} must be between 0 and 1")
        ratios[name] = data
    return rows, ratios


def main():
    parser = ActionParser(description=__doc__)
    parser.add_argument("master", type=Path)
    parser.add_argument("ratios", nargs="*", type=Path)
    args = parser.parse_args()
    rows, ratios = rank(args)
    for row in rows:
        ratio = ratios.get(row["apiName"])
        row["serverScore"] = row["score"]
        row["scoreSource"] = "server ratio"
        if ratio and ratio["recomputedRatio"] is not None:
            contribution = next(f["contribution"] for f in row["scoreFactors"]
                                if f["factor"] == "unstructuredRatio")
            row["score"] = round(row["score"] - contribution
                                 + FREE_TEXT_POINTS * ratio["recomputedRatio"], 2)
            row["scoreSource"] = "recomputed"
            row["recomputedRatio"] = ratio["recomputedRatio"]
        elif ratio:
            row["unavailableReason"] = ratio.get("reason", "Recompute unavailable")
    rows.sort(key=lambda row: (-row["score"], row["nodeId"]))
    top = rows[:FINALISTS]
    pending = [row["nodeId"] for row in rows
               if row["scoreSource"] != "recomputed" and row["score"] >= top[-1]["score"]]
    blocked = any("unavailableReason" in row for row in rows if row["nodeId"] in pending)
    code = 2 if blocked else 3 if pending else 0
    action = ("Repair unavailable recomputes or report this unresolved ranking." if blocked else
              "Recompute nextNodeIds with free_text_ratio.py and rerun rank_stop.py." if pending else
              "Build the report with these verified scores.")
    print(json.dumps({"status": "unresolved" if blocked else "recompute" if pending else "verified",
                      "top3": top, "ranking": rows, "nextNodeIds": pending,
                      "nextAction": action}, indent=2))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"status": "unresolved", "error": str(exc),
                          "nextAction": "Repair the scan or ratio inputs and rerun rank_stop.py."}))
        sys.exit(2)
