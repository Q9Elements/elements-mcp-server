#!/usr/bin/env python3
"""Say which stage of a map-agent-as-process run is done and which comes next.

    python3 status.py WORK [--json]

Worked out from the files in the work folder, never from memory, so a resumed run
continues at the right stage. The stages, in order:

  1 kickoff     scope.json holds the package, the diagrams, the depth and the view
  2 inventory   inventory.json holds the stages (or a plugin's candidates: choose one),
                then the scope check: the person has confirmed the scope (scope.json confirmed)
  3 top         levels/top.json
  4 children    levels/<stage>.json for every stage on the top level that has a level of its own
  5 model       model.json and coverage.json
  6 hand-off    tell the person and draw the model

It records the last finished stage in scope.json's `stage` field and changes nothing
else. Exit 0, or 2 when the work folder cannot be read. Standard library only.
"""

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import process_levels  # noqa: E402  (the shared core of level-by-level process readers)
import validate  # noqa: E402

read = process_levels.read_or_none

NEXT = {
    "kickoff": "Stage 1, kickoff: settle the package, the diagrams, the depth and the view with the person, then write scope.json.",
    "inventory": "Stage 2, inventory: run inventory_package.py on the package{entry}.",
    "confirm": "Stage 2, scope check: tell the person what the inventory found and the scope (diagrams, depth, view), ask them to confirm or correct it, and stop for the answer; then write their answer to scope.json and set confirmed to true.",
    "top": "Stage 3, top level: prepare_briefs.py top, then one process-level-writer for levels/top.json.",
    "children": "Stage 4, stage levels: prepare_briefs.py children, then one process-level-writer per brief, in parallel.",
    "model": "Stage 5, build and check: build_model.py, then validate.py --for process{flow}.",
    "hand-off": "Stage 6, hand-off: tell the person what the map shows and draw it with draw-process-map{flow_draw}.",
}


def status(work):
    work = Path(work)
    scope = read(work / "scope.json") or {}
    inv = read(work / "inventory.json") or {}
    done, missing = [], []
    flow = "interaction-flow" in (scope.get("diagrams") or [])

    def result(stage):
        text = NEXT[stage].format(entry=" again with --entry naming the package to draw" if inv.get("candidates") else "",
                                  flow=" and --for interaction-flow" if flow else "",
                                  flow_draw=", then the interaction flow with draw-interaction-flow" if flow else "")
        return {"workdir": str(work), "done": done, "next": stage, "do": text, "missing": missing}

    if not (scope.get("package") and scope.get("diagrams") and scope.get("depth") in ("top", "children")
            and scope.get("view") in ("business", "technical")):
        missing.append("scope.json with package, diagrams, depth (top or children) and view (business or technical)")
        return result("kickoff")
    done.append("kickoff")

    if not inv.get("stages"):
        missing.append("inventory.json with stages" + (" (it lists a plugin's packages: choose one)" if inv.get("candidates") else ""))
        return result("inventory")
    if scope.get("confirmed") is not True:
        missing.append("scope.json confirmed: true (the person has seen the inventory and the scope)")
        return result("confirm")
    done.append("inventory")

    top = read(work / "levels" / "top.json")
    if not top:
        missing.append("levels/top.json")
        return result("top")
    done.append("top")

    drill = {s["id"] for s in inv["stages"] if s.get("drillDown")}
    boxed = [s.get("item") for s in top.get("steps", []) if s.get("item") in drill]
    absent = [f"levels/{sid}.json" for sid in boxed if not (work / "levels" / f"{sid}.json").exists()]
    if absent:
        missing.extend(absent)
        return result("children")
    done.append("children")

    if not (work / "model.json").exists() or not (work / "coverage.json").exists():
        missing.extend(n for n in ("model.json", "coverage.json") if not (work / n).exists())
        return result("model")
    done.append("model")
    out = result("hand-off")
    code, lines = validate.run_checks(str(work / "model.json"), "process")
    out["validation"] = lines[-1] if lines else ""
    out["coverageErrors"] = len((read(work / "coverage.json") or {}).get("errors") or [])
    return out


def main(argv=None):
    return process_levels.status_main(status, "Which stage of a map-agent-as-process run comes next.", argv)


if __name__ == "__main__":
    sys.exit(main())
