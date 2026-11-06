#!/usr/bin/env python3
"""Lay out a business-architecture model as an Elements process map or customer journey,
then step through writing it with manage_diagram, and check the drawn result.

Usage:
  python3 layout_process.py plan MODEL.json --type process|journey --workdir DIR [--skip KINDS] [--no-uses] [--create-resources]
                            [--apply-renames] [--accept-type-clashes]
  python3 layout_process.py next DIR
  python3 layout_process.py check DIR

plan   Works out every level: which boxes go where, which side each line leaves and enters
       (data/line-sides.csv), and the manage_diagram change batches that draw it, in the order to
       send them. Writes DIR/plan.json and prints a summary with any warnings. Refuses a model that fails validate.py for its diagram type.
       --skip metadata,story,link,note leaves those attachment kinds out. --no-uses leaves out the
       Object and System resources an activity's 'uses' would add. --create-resources lets the writes
       add resources the space library lacks; use it only once the user has agreed.
       --apply-renames applies the renames a fix-preflight step listed (from the plan and preflight saved in DIR) to a
       copy of the model, MODEL.renamed.json beside it, and plans from that copy; MODEL is left as it is. The renames
       are kept in DIR/renames.json, and the done step lists them (renamed) for the report.
       --accept-type-clashes draws objects the space library holds under another type (fix-preflight typeClashes) as
       the library holds them; use it only once the user has agreed.
next   Prints, as JSON, the one thing to do next: create the map, dry-run the preflight (every resource
       and library attachment once, before anything is written), read a level, send a batch (its
       changes already resolved to the keys earlier results returned), read every level for review,
       or nothing (done). Run it again after saving each result where it says.
check  Checks the saved review reads (DIR/review/*.json) against the rubric rows checked by
       layout-check and writes DIR/layout-check.json in the diagram-reviewer's finding format. A review read
       that is missing or not the whole get_diagram answer is refused: an ERROR line per file, exit 1, and no
       layout-check.json.

Files in DIR: plan.json, map.json, preflight/<n>.json, preflight/matches-<n>.json, renames.json,
results/<level>/<batch>.json, reads/<level>.json, review/<level>.json, layout-check.json. <level> is "top" or the id of the activity a child level
drills down from.

Exit 0: done. Exit 1: the model, the plan or a saved file has a problem the output describes.
Exit 2: setup problem (a data file or the command line).

Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attachment_scope import scope_model
import validate  # noqa: E402  (the drawing gate: no plan from a model that fails validation)
from layout_engine import next_step as engine_next_step  # noqa: E402
from layout_engine import (  # noqa: E402  (the shared layout engine)
    ATTACHMENT_KINDS, END, Level, PLUGIN, PlanError, START,
    NOTE_SIZE, SetupError, attachment_changes, canvas_after, check, chunk, inside, level_note_spot, line_paths,
    load_style, map_type, norm, preflight_batches, preflight_renames, prepare_workdir, read_json,
)

SIDES_PATH = PLUGIN / "data" / "line-sides.csv"


# ---------------------------------------------------------------- plan: batches


NOTE_TEXT_FIT = 400   # characters a 150 x 150 px level note shows before its text runs past the note


def note_text(note):
    """The drawn text of a level note: its title as the first sentence, then its text. A level note loses its line
    breaks, so the two are joined as sentences."""
    title = note["title"].strip()
    return f"{title}{'' if title[-1:] in '.:!?' else '.'} {note['text'].strip()}".strip()


def place_level_notes(level, model, style, skip, passes, canvases, warnings):
    """The model's levelNotes for this level, each placed beside its box (level_note_spot): {pass index: [change]}.
    A note goes into the write that places its box, inside that write's canvas; when it fits only once every box is
    written, it goes into the last write. level["notes"] records where each one went."""
    level["notes"] = []
    if "note" in skip:
        return {}
    mine = [n for n in model.get("levelNotes", []) if n.get("parent") == level["parent"]]
    if not mine:
        return {}
    boxes = {b["id"]: b for b in level["boxes"]}
    paths = line_paths(boxes, level["lines"], style)
    first = next((ln["to"] for ln in level["lines"] if ln["from"] == START and ln["to"] in boxes), level["boxes"][0]["id"])
    where = "top level" if level["parent"] is None else f"level under '{level['parent']}'"
    by_pass = defaultdict(list)
    for note in mine:
        anchor = boxes.get(note.get("near") or first)
        if anchor is None:
            warnings.append(f"{where}: the note '{note['title']}' is beside '{note.get('near')}', which is not a box on this level; left out")
            continue
        text = note_text(note)
        at = next(i for i, group in enumerate(passes) if anchor in group)
        spot = level_note_spot(anchor, list(boxes.values()), paths, canvases[at])
        if spot is None and at != len(passes) - 1:
            at = len(passes) - 1
            spot = level_note_spot(anchor, list(boxes.values()), paths, canvas_after(level["boxes"], style))
        if spot is None:
            warnings.append(f"{where}: no free place beside '{anchor['name']}' for the note '{note['title']}'; left out, so add it by hand")
            continue
        if len(text) > NOTE_TEXT_FIT:
            warnings.append(f"{where}: the note '{note['title']}' has {len(text)} characters; a note is drawn 150 x 150 px, so about {NOTE_TEXT_FIT} show without scrolling")
        by_pass[at].append({"op": "add", "kind": "note", "text": text, "position": {"x": spot[0], "y": spot[1]}})
        level["notes"].append({"near": anchor["id"], "x": spot[0], "y": spot[1], "w": NOTE_SIZE[0], "h": NOTE_SIZE[1],
                               "title": note["title"], **({"purpose": note["purpose"]} if note.get("purpose") else {})})
    return by_pass


def level_batches(level, model, style, skip, warnings=None):
    acts = {a["id"]: a for a in model["activities"]}
    pending = list(level["boxes"])
    canvas = (0, 0, style["canvas_blank_width"], style["canvas_blank_height"])
    placed, passes, canvases = [], [], []
    while pending:
        fits = [b for b in pending if inside(b, canvas)]
        if not fits:
            raise PlanError(f"{level['slug']}: boxes do not fit the canvas even after {len(passes)} write(s)")
        passes.append(fits)
        canvases.append(canvas)
        placed += fits
        pending = [b for b in pending if b not in fits]
        canvas = canvas_after(placed, style)
    notes = place_level_notes(level, model, style, skip, passes, canvases, warnings if warnings is not None else [])
    batches = []
    for at, group_boxes in enumerate(passes):
        groups = []
        for box in group_boxes:
            changes = [{"op": "add", "kind": "activity", "ref": box["ref"], "text": box["name"], "position": {"x": box["x"], "y": box["y"]}}]
            for res in box["resources"]:
                change = {"op": "add", "kind": "resource", "activity": box["ref"], "name": res["name"], "type": res["type"]}
                if res.get("rasci"):
                    change["rasci"] = res["rasci"]
                changes.append(change)
            changes += attachment_changes(acts[box["id"]], box["ref"], skip)
            groups.append(changes)
        groups += [[change] for change in notes.get(at, [])]
        for changes in chunk(groups):
            batches.append({"kind": "boxes", "changes": changes})
    ref_of = {b["id"]: b["ref"] for b in level["boxes"]}
    line_changes = []
    for line in level["lines"]:
        change = {"op": "add", "kind": "line", "ref": line["ref"], "label": line["label"],
                  "from": {"terminator": True} if line["from"] == START else {"activity": ref_of[line["from"]]},
                  "to": {"terminator": True} if line["to"] == END else {"activity": ref_of[line["to"]]}}
        if "fromSide" in line:
            change["fromSide"] = line["fromSide"]
        if "toSide" in line:
            change["toSide"] = line["toSide"]
        if "boundary" in line:
            # The line add child seeded for this parent line is replaced, not connected: an update keeps the
            # seeded free end where add child put it (a short stub at the left), so the line would bend or run
            # backwards. A new line preserves parentLine and requests the planned free end; the server chooses its clear route.
            free = "from" if line["from"] == START else "to"
            change[free] = None
            change["parentLine"] = {"$parentLine": line["boundary"]}
            line_changes.append([{"op": "remove", "kind": "line", "key": {"$boundary": line["boundary"]}}, change])
        else:
            line_changes.append([change])
    for changes in chunk(line_changes):
        batch = {"kind": "lines", "changes": changes}
        if any(c["op"] == "remove" for c in changes):
            batch["confirm"] = True  # removes only the seeded lines this batch replaces; a small level trips the 30 % guard
        batches.append(batch)
    parents = [b for b in level["boxes"] if any(a.get("parent") == b["id"] for a in model["activities"])]
    if parents:
        batches.append({"kind": "children", "changes": [{"op": "add", "kind": "child", "activity": b["ref"]} for b in parents]})
    return batches, len(passes)


def plan(model, diagram_type, skip, use_uses, create_resources=False, create_objects=True, accept_type_clashes=False):
    style = load_style(diagram_type)
    warnings = []
    levels = []

    def visit(parent, boundary):
        level = Level(model, parent, diagram_type, style, skip, use_uses, warnings).build(boundary)
        if level is None:
            return
        level["batches"], level["writes"] = level_batches(level, model, style, skip, warnings)
        levels.append(level)
        for box in level["boxes"]:
            if any(a.get("parent") == box["id"] for a in model["activities"]):
                inputs = [ln for ln in level["lines"] if ln["to"] == box["id"]]
                outputs = [ln for ln in level["lines"] if ln["from"] == box["id"]]
                visit(box["id"], {"inputs": [{"ref": ln["ref"], "label": model["flows"][ln["flowIndex"]].get("label", "")} for ln in inputs],
                                  "outputs": [{"ref": ln["ref"], "label": model["flows"][ln["flowIndex"]].get("label", "")} for ln in outputs]})

    visit(None, None)
    result = {
        "planVersion": 1, "diagramType": diagram_type, "mapType": map_type(diagram_type),
        "mapName": map_name(model["meta"]["title"]), "mapDescription": model["meta"].get("description", ""),
        "createResources": create_resources, "createObjects": bool(create_objects and use_uses),
        "levels": levels, "preflight": preflight_batches(levels, model), "warnings": warnings, "gaps": model.get("gaps", []),
    }
    if accept_type_clashes:
        result["acceptTypeClashes"] = True
    result["planId"] = hashlib.sha1(json.dumps(result, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return result


# ---------------------------------------------------------------- renames


def renamed_path(model_path):
    """MODEL.renamed.json beside MODEL; a model that is already a renamed copy keeps its name."""
    path = Path(model_path)
    stem = path.stem[:-len(".renamed")] if path.stem.endswith(".renamed") else path.stem
    return path.with_name(f"{stem}.renamed{path.suffix or '.json'}")


def merge_renames(earlier, new):
    """The renames made so far, original name first: a rename of a name an earlier rename produced ("Contact" to
    "Contact (object)", then to "Contact (object, Contact)") extends that entry instead of adding one."""
    merged = [dict(r) for r in earlier]
    for rename in new:
        chain = next((r for r in merged if norm(r["libraryName"]) == norm(rename["name"])), None)
        if chain is None:
            merged.append(dict(rename))
        else:
            chain.update({k: v for k, v in rename.items() if k != "name"})
    return merged


def apply_renames(model_path, workdir):
    """Write the model with the entity renames the preflight saved in workdir asked for (fix-preflight renames)
    beside it, and return (that path, the renames made); the model file itself is not changed. None, after an
    ERROR line, when there is nothing to apply."""
    plan_path = Path(workdir) / "plan.json"
    if not plan_path.exists():
        print(f"ERROR {workdir} holds no plan: --apply-renames applies the renames the preflight of the plan in that folder found")
        return None
    renames = preflight_renames(Path(workdir), read_json(plan_path))
    if renames is None:
        print(f"ERROR the preflight in {workdir} is not finished: run next and send each preflight step first")
        return None
    if not renames:
        print(f"ERROR the preflight in {workdir} lists no renames; plan without --apply-renames")
        return None
    model = read_json(model_path)
    to = {norm(r["name"]): r["libraryName"] for r in renames}
    done = []
    for entity in model.get("entities", []):
        new = to.get(norm(entity.get("name", "")))
        if new and entity["name"] != new:
            done.append((entity["name"], new))
            entity["name"] = new
    if not done:
        print(f"ERROR no entity in {model_path} is named as the renames list says ({', '.join(r['name'] for r in renames)}); "
              "give the model the plan in the folder was made from")
        return None
    out = renamed_path(model_path)
    out.write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    renamed = {norm(old) for old, _ in done}
    reasons = {norm(r["name"]): r.get("reason") for r in renames}
    for old, new in done:
        print(f"RENAMED {old} -> {new}" + (f" ({reasons[norm(old)]})" if reasons.get(norm(old)) else ""))
    for r in renames:
        if norm(r["name"]) not in renamed:
            print(f"WARN no entity in {model_path} is named '{r['name']}'; nothing renamed to '{r['libraryName']}'")
    print(f"Wrote the renamed model to {out}; {model_path} is unchanged. Use {out} as the model from now on.")
    return out, [r for r in renames if norm(r["name"]) in renamed]


def record_renames(workdir, made):
    """Keep every rename made in this work folder in renames.json, which the done step hands back for the report."""
    record = Path(workdir) / "renames.json"
    earlier = read_json(record) if record.exists() else []
    record.write_text(json.dumps(merge_renames(earlier, made), indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- main

def print_plan_summary(result, workdir):
    print(f"Plan written to {Path(workdir) / 'plan.json'}: {len(result['levels'])} level(s).")
    for level in result["levels"]:
        rows = {(b["band"], b["row"]) for b in level["boxes"]}
        print(f"  {level['slug']}: {len(level['boxes'])} boxes in {len(rows)} row(s), {len(level['lines'])} lines, "
              f"{len(level['batches'])} batch(es), {level['writes']} box write(s)"
              + (f", {len(level['notes'])} note(s)" if level.get("notes") else ""))
    for warning in result["warnings"]:
        print(f"WARN {warning}")
    for gap in result["gaps"]:
        print(f"GAP {gap.get('about', 'model')}: {gap['note']}")


def next_step(workdir):
    """The engine's write loop, naming this script for the check that follows."""
    return engine_next_step(workdir, Path(__file__).name)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Lay out and write a process map or customer journey.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("model")
    p_plan.add_argument("--type", required=True, choices=["process", "journey"])
    p_plan.add_argument("--workdir", required=True)
    p_plan.add_argument("--skip", default="", help="attachment kinds to leave out, comma separated")
    p_plan.add_argument("--no-uses", action="store_true", help="leave out the Object and System resources of each step's uses (only when the user asks)")
    p_plan.add_argument("--create-resources", action="store_true", help="add every resource missing from the space library, people and systems too (only once the user has agreed)")
    p_plan.add_argument("--no-create-objects", action="store_true", help="do not add missing Object resources to the space library without asking")
    p_plan.add_argument("--apply-renames", action="store_true", help="apply the renames the preflight saved in --workdir listed to a copy of the model (MODEL.renamed.json) and plan from it")
    p_plan.add_argument("--accept-type-clashes", action="store_true", help="draw objects the space library holds under another type as the library holds them (only once the user has agreed)")
    p_next = sub.add_parser("next")
    p_next.add_argument("workdir")
    p_check = sub.add_parser("check")
    p_check.add_argument("workdir")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            skip = {s.strip() for s in args.skip.split(",") if s.strip()}
            unknown = skip - set(ATTACHMENT_KINDS)
            if unknown:
                print(f"SETUP --skip takes {', '.join(ATTACHMENT_KINDS)}; not {', '.join(sorted(unknown))}", file=sys.stderr)
                return 2
            model_path, made = args.model, []
            if args.apply_renames:
                applied = apply_renames(args.model, args.workdir)
                if applied is None:
                    return 1
                model_path, made = applied
            gate = validate.gate(model_path, args.type)
            if gate:
                return gate
            model = scope_model(read_json(model_path), model_path, args.workdir)
            if not any(a for a in model.get("activities", [])):
                print("ERROR the model has no activities to draw")
                return 1
            result = plan(model, args.type, skip, not args.no_uses, args.create_resources, not args.no_create_objects,
                          args.accept_type_clashes)
            workdir = Path(args.workdir)
            prepare_workdir(workdir, result)
            (workdir / "plan.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            if made:
                record_renames(workdir, made)
            print_plan_summary(result, workdir)
            return 0
        if args.command == "next":
            print(json.dumps(next_step(args.workdir), indent=2))
            return 0
        result = check(args.workdir)
        for f in result["findings"]:
            print(f"{f['severity'].upper()} {f['rule']} level {f['level']}: {f['issue']}")
        print(f"{len(result['findings'])} finding(s) on {len(result['checked'])} level(s); written to {Path(args.workdir) / 'layout-check.json'}")
        return 0
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except (PlanError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
