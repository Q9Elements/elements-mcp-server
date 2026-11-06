#!/usr/bin/env python3
"""Check one level outline against the brief it was written from.

Usage:
  check_outline.py --brief BRIEF [--outline OUTLINE]

Every process reader that works one level at a time writes its briefs with the
same generic fields, and the process-level-writer agent runs this script on its
own level before handing it back:
  - the outline's shape (schemas/level-outline.schema.json) and the rules the
    schema cannot express, as relaxed by the brief's outlineRules;
  - cover.items: one box per item on an overview level;
  - cover.uses: every id used by some step, or explained in a gap;
  - parent: the parent box's input and output labels copied exactly;
  - budget.max boxes, label lengths, a line into and out of every step.

Exit 0 when the outline passes (warnings may remain), 1 when it has errors,
2 on a setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import sys
from pathlib import Path

import process_levels
from process_levels import SetupError


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Check a level outline against its brief.")
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--outline", type=Path, help="the outline to check; the brief's outlinePath when left out")
    args = parser.parse_args(argv)
    try:
        brief = process_levels.load_json(args.brief, "brief")
        path = Path(args.outline or brief.get("outlinePath", ""))
        outline = process_levels.load_json(path, "outline")
        errors, warnings = process_levels.check_outline(outline, brief)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    for line in errors:
        print(f"ERROR {line}")
    for line in warnings:
        print(f"WARN {line}")
    print(f"{'FAIL' if errors else 'PASS'}: {len(errors)} error(s), {len(warnings)} warning(s) in {path}.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
