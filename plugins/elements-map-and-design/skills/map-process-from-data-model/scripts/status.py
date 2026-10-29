#!/usr/bin/env python3
"""Say which stage of a map-process-from-data-model run is done and which comes next.

    python3 status.py WORK [--json]

The answer is worked out from the files in the work folder (references/data-contracts.md), never
from memory, so a run resumed days later in a fresh session continues at the right stage and no
stage is skipped. The stages, in order:

  1 kickoff       scope.json holds the confirmed system, route and mode
  2 inventory     inventory.json holds the objects
  3 capabilities  every capability in inventory.json is confirmed
  4 top           levels/top.json, and levels/<area>.json for every area
  5 children      levels/<capability>.json for every capability with steps of its own
  6 model         model.json and coverage.json
  7 draw          draw-process-map has finished: <drawing>/layout-check.json, <drawing>/review/top.json and
                  the diagram-reviewer's verdict <drawing>/review.json, where <drawing> is scope.json drawing.dir
                  (by default WORK/drawing)
  8 status-automations
                  WORK/status-automations/done.json, or scope.json statusAutomations false; applies only
                  on route metadata when the model has value boxes, otherwise it is reported not applicable

The run is complete when every applicable stage is DONE; NEXT then says "Run complete". The DONE line
of stage 5 names the levels the fallback writers wrote instead of Elements' org-to-process, and the
DONE line of stage 8 the levels done.json lists as skipped (skippedLevels).
It records the last finished stage in scope.json's `stage` field (kickoff, inventory, capabilities,
top, areas, children, model, draw, status-automations), and changes nothing else. Exit code 0, or 2
when the work folder cannot be read. Standard library only; Python 3.8 or later.
"""

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import common  # noqa: E402  (this skill's helpers: the lifecycle plan)
import process_levels  # noqa: E402  (the shared core of level-by-level process readers)
import validate  # noqa: E402  (the plugin's model validator)

read = process_levels.read_or_none
record = process_levels.record_stage

# the instruction printed after NEXT for each stage
NEXT = {
    "kickoff": "Stage 1, kickoff: confirm the system, route, scope and mode with the person (on route metadata, also "
               "whether to expose the automations behind each status), then write scope.json.",
    "inventory": "Stage 2, inventory: read every object in scope ({route} route) and build inventory.json.",
    "capabilities": "Stage 3, capabilities: cluster the objects, run the capability-grouper, and apply its proposal with "
                    "inventory.py set-capabilities --confirmed{checkpoint} (one-object scope: inventory.py focus, then set-capabilities).",
    "top": "Stage 4, top level: write levels/top.json{areas}{checkpoint}.",
    "children": "Stage 5, child levels: run prepare_briefs.py children (or top, with a focus object) and send one process-level-writer per detail or lifecycle brief.",
    "model": "Stage 6, build and check: build_model.py, validate.py --for process, check_coverage.py.",
    "draw": "Stage 7, draw: draw {model} with draw-process-map, with {drawing} as its work folder. The drawing is a "
            "step of this run: when draw-process-map has reported, run status.py again.",
    "status-automations": "Stage 8, status automations: run the show-status-automations skill with {automations} as "
                          "its work folder, starting with: {command} Follow that skill until its next prints done "
                          "or skipped, then run status.py again.",
    "complete": "Run complete: every applicable stage is done. Give the person the final answer "
                "(SKILL.md, What to tell the person).",
}
AUTOMATIONS = "status-automations"  # stage 8's folder in the work folder, and its stage name
NO_VALUE_BOXES = "no box sets a lifecycle value"


def drawing_dir(work, scope):
    """The drawing's work folder: scope.json drawing.dir (relative to the work folder), by default WORK/drawing."""
    given = (scope.get("drawing") or {}).get("dir") if isinstance(scope.get("drawing"), dict) else None
    path = Path(given).expanduser() if given else Path(work) / "drawing"
    return path if path.is_absolute() else Path(work) / path


def value_boxes(model):
    """How many boxes of the model stand for a lifecycle value: a line out of them sets the value."""
    acts = {a.get("id") for a in (model or {}).get("activities") or []}
    return len({f.get("from") for f in (model or {}).get("flows") or [] if f.get("sets") and f.get("from") in acts})


def drawn_model(work):
    """The model the drawing drew: model.renamed.json, which layout_process.py plan --apply-renames writes beside
    model.json with the objects renamed as the space library holds them, when it exists and is not older than
    model.json; otherwise model.json."""
    model, renamed = Path(work) / "model.json", Path(work) / "model.renamed.json"
    if renamed.exists() and (not model.exists() or renamed.stat().st_mtime >= model.stat().st_mtime):
        return renamed
    return model


def automations_command(work, scope, drawing):
    """The show-status-automations command that starts stage 8, with this run's paths and ids."""
    meta = scope.get("metadata") if isinstance(scope.get("metadata"), dict) else {}
    work = Path(work).resolve()
    script = PLUGIN / "skills" / "show-status-automations" / "scripts" / "status_automations.py"
    team = f' --team-id {meta["teamId"]}' if meta.get("teamId") else ""
    return (f'python3 "{script}" boxes --model "{drawn_model(work)}" --inventory "{work / "inventory.json"}" '
            f'--scope "{work / "scope.json"}" --reads "{Path(drawing).resolve() / "review"}" '
            f'--ref-model-id {meta.get("refModelId") or "<refModelId>"}{team} '
            f'--out "{work / AUTOMATIONS / "boxes.json"}"')


def status(work):
    work = Path(work)
    scope = read(work / "scope.json") or {}
    done, missing = [], []
    notes, not_applicable, extra = {}, [], {}
    route = scope.get("route") or "the chosen"
    mode = scope.get("mode")
    checkpoint = "; with checkpoints, the person confirms it before you go on" if mode == "checkpoints" else ""

    def result(next_stage, areas_note="", **fields):
        text = NEXT[next_stage].format(route=route, checkpoint=checkpoint, areas=areas_note, **fields)
        out = {"workdir": str(work), "done": done, "next": next_stage, "do": text, "missing": missing, **extra}
        if notes:
            out["doneNotes"] = notes
        if not_applicable:
            out["notApplicable"] = not_applicable
        return out

    if not (scope.get("system") and scope.get("route") in ("docs", "metadata") and mode in ("checkpoints", "autopilot")):
        missing.append("scope.json with system, route (docs or metadata) and mode (checkpoints or autopilot)")
        return result("kickoff")
    problem = common.basis_problem(scope)
    if problem:
        missing.append(f"scope.json metadata.basis: {problem}")
        return result("kickoff")
    done.append("kickoff")

    inventory = read(work / "inventory.json")
    if not inventory or not inventory.get("objects"):
        missing.append("inventory.json with objects")
        return result("inventory")
    done.append("inventory")
    stop = common.usage_stop(inventory)
    if stop:
        # basis usage and a focus object holding no records: the process would be empty
        missing.append(f"a basis the focus object supports: {stop}")
        out = result("kickoff")
        out["do"] = "Stage 1, kickoff: " + stop + " Ask the person, record the basis in scope.json, then run inventory.py usage again."
        return out

    caps = inventory.get("capabilities") or []
    unconfirmed = [c.get("id") for c in caps if not c.get("confirmed")]
    if not caps or unconfirmed:
        missing.append("capabilities in inventory.json" if not caps else "confirmation of " + ", ".join(unconfirmed))
        return result("capabilities")
    done.append("capabilities")

    by_id = {c["id"]: c for c in caps if "id" in c}
    children = {}
    for cap in caps:
        if cap.get("parent"):
            children.setdefault(cap["parent"], []).append(cap["id"])
    areas = sorted(children)
    levels = work / "levels"
    top = read(levels / "top.json")
    missing_levels = [] if top else ["levels/top.json"]
    missing_levels += [f"levels/{a}.json" for a in areas if not (levels / f"{a}.json").exists()]
    if missing_levels:
        missing.extend(missing_levels)
        note = ", then one overview level per area (" + ", ".join(areas) + ")" if areas else ""
        return result("top", areas_note=note)
    done.append("top")
    if areas:
        done.append("areas")

    plans = common.lifecycle_plan(inventory) if caps else {}
    if inventory.get("focus"):
        # one object's process: the top level holds the capability's own steps, or its split by record type,
        # whose record types each need a lifecycle level
        expected = []
        record_type_levels = [rt["level"] for plan in plans.values() for rt in plan["recordTypes"]]
    else:
        expected = []
        for outline in [top] + [read(levels / f"{a}.json") or {} for a in areas]:
            for step in outline.get("steps", []):
                cid = step.get("item")
                if cid and cid in by_id and cid not in children and cid not in expected:
                    expected.append(cid)
        if not expected:
            missing.append("a top-level step that stands for a capability")
            return result("children")
        record_type_levels = [rt["level"] for cid in expected if cid in plans for rt in plans[cid]["recordTypes"]]
    missing_children = [f"levels/{c}.json" for c in expected + record_type_levels if not (levels / f"{c}.json").exists()]
    if missing_children:
        missing.extend(missing_children)
        return result("children")
    done.append("children")
    fallback = common.fallback_levels(scope, inventory, levels)
    if fallback:
        # levels meant to come from Elements' org-to-process that process-level-writers wrote instead
        notes["children"] = "fallback writers, not Elements' org-to-process, wrote " + common.fallback_summary(fallback)
        extra["fallbackLevels"] = [{"level": level, "reason": reason} for level, reason in fallback]

    if not (work / "model.json").exists() or not (work / "coverage.json").exists():
        missing.extend(n for n in ("model.json", "coverage.json") if not (work / n).exists())
        return result("model")
    done.append("model")
    code, lines = validate.run_checks(str(work / "model.json"), "process")
    extra["validation"] = lines[-1] if lines else ""
    errors = (read(work / "coverage.json") or {}).get("errors")
    extra["coverageErrors"] = errors if isinstance(errors, int) else len(errors or [])  # check_coverage.py writes a count

    drawing = drawing_dir(work, scope)
    drawn = [drawing / "layout-check.json", drawing / "review" / "top.json", drawing / "review.json"]
    if not all(path.exists() for path in drawn):
        missing.extend(str(path) for path in drawn if not path.exists())
        return result("draw", model=work / "model.json", drawing=drawing)
    done.append("draw")

    if scope.get("route") != "metadata":
        not_applicable.append([AUTOMATIONS, "route docs: automations are read from a connected org"])
        return result("complete")
    if not value_boxes(read(work / "model.json")):
        not_applicable.append([AUTOMATIONS, NO_VALUE_BOXES])
        return result("complete")
    if scope.get("statusAutomations") is False:
        done.append(AUTOMATIONS)
        notes[AUTOMATIONS] = "the person chose not to expose them at kickoff"
        return result("complete")
    marker = work / AUTOMATIONS / "done.json"
    if marker.exists():
        done.append(AUTOMATIONS)
        skipped = (read(marker) or {}).get("skippedLevels")
        if isinstance(skipped, list) and skipped:
            # levels show-status-automations left alone (open in the editor, or edited by someone): the run is
            # complete, and the final answer names each one
            titles = ", ".join(str(s.get("title") or s.get("diagramId")) for s in skipped if isinstance(s, dict))
            notes[AUTOMATIONS] = (f"{len(skipped)} level{'' if len(skipped) == 1 else 's'} skipped ({titles}), open in the "
                                  "editor or edited by someone: the hand-off must name each with its reason")
            extra["skippedLevels"] = skipped
        return result("complete")
    missing.append(str(marker))
    if not (scope.get("metadata") or {}).get("refModelId"):
        missing.append("scope.json metadata.refModelId (the org's reference model, for the command below)")
    return result(AUTOMATIONS, automations=work / AUTOMATIONS, command=automations_command(work, scope, drawing))


def main(argv=None):
    return process_levels.status_main(status, "Which stage of a map-process-from-data-model run comes next.", argv)


if __name__ == "__main__":
    sys.exit(main())
