"""Colour the design by verdict, record what was written, and plan the reset.

    python3 colour.py plan ENG          # fills, sticky notes and a legend per level -> colour/plan/<level>.json
    python3 colour.py record ENG        # after the writes and fresh reads: check them, keep the note keys
    python3 colour.py reset-plan ENG    # the writes that put the design back -> colour/reset/<level>.json
    python3 colour.py reset-verify ENG  # after the reset writes and fresh reads: check nothing of the playbook's is left

Every command reads ENG/design.json, so rebuild it from fresh level reads (read_design.py build) first. plan saves
each box's fill and border in colour/originals.json before it plans any change, and never overwrites a saved one:
the reset puts back what the author had. Only fills change (Elements gives a box a border when its fill is set, so
the original border is saved too). Each sticky note starts with "Design check:" and the legend with "Design check
legend:", so a reset without this run's files still finds them; it then clears only boxes filled with this
playbook's colours. Exit 0 done, 1 refused (the lines say why), 2 setup problem.
"""

import sys
from pathlib import Path

import common
from common import Failed, level_sort_key, load_json, write_json


def overlaps(a, b, pad=4):
    return not (a[0] + a[2] + pad <= b[0] or b[0] + b[2] + pad <= a[0] or a[1] + a[3] + pad <= b[1] or b[1] + b[3] + pad <= a[1])


def inside(rect, canvas):
    if not canvas:
        return True
    return (rect[0] >= canvas["x"] and rect[1] >= canvas["y"] and rect[0] + rect[2] <= canvas["x"] + canvas["w"]
            and rect[1] + rect[3] <= canvas["y"] + canvas["h"])


def rect_of(item):
    if item.get("x") is None or item.get("y") is None:
        return None
    return (item["x"], item["y"], item.get("w") or 0, item.get("h") or 0)


def place(box_rect, size, gap, obstacles, canvas):
    """Above the box first (the owner's 'on top of the box'), then below, right and left; above when all collide."""
    x, y, w, h = box_rect
    options = [(x, y - size - gap), (x, y + h + gap), (x + w + gap, y), (x - size - gap, y)]
    for ox, oy in options:
        rect = (ox, oy, size, size)
        if inside(rect, canvas) and not any(overlaps(rect, o) for o in obstacles):
            return (ox, oy), False
    ox, oy = options[0]
    if canvas:
        ox = max(canvas["x"], min(ox, canvas["x"] + canvas["w"] - size))
        oy = max(canvas["y"], min(oy, canvas["y"] + canvas["h"] - size))
    return (ox, oy), True


def place_legend(min_x, min_y, size, gap, obstacles, canvas):
    """Left of the top-left box, then above-left, then above everything; the first that is clear."""
    far = 3 * gap
    options = [(min_x - size - far, min_y), (min_x - size - far, min_y - size - far), (min_x, min_y - 2 * size - far)]
    for ox, oy in options:
        rect = (ox, oy, size, size)
        if inside(rect, canvas) and not any(overlaps(rect, o) for o in obstacles):
            return ox, oy
    return options[0]


def legend_text(present, rows):
    lines = [f"{common.LEGEND_MARKER} how far the org supports each step."]
    lines += [rows[v]["legend"] + "." for v in common.VERDICTS if v in present]
    lines.append("Ask to reset the colours to remove the colours and these notes.")
    return " ".join(lines)


def plan(eng):
    eng = Path(eng)
    limits = common.load_limits()
    rows = common.load_verdicts()
    design = load_json(eng / "design.json", "the design file")
    results = load_json(eng / "results.json", "the results")["boxes"]
    size, gap = limits["note_size_px"], limits["note_gap_px"]
    orig_path = eng / "colour" / "originals.json"
    originals = load_json(orig_path)["levels"] if orig_path.exists() else {}
    for level in design["levels"]:
        saved = originals.setdefault(level["levelNumber"], {})
        for bid in level["boxes"]:
            box = design["boxes"][bid]
            if results.get(bid, {}).get("verdict") in common.COLOURED and str(box["key"]) not in saved:
                saved[str(box["key"])] = {"fill": box["layout"].get("fill"), "border": box["layout"].get("border")}
    write_json(orig_path, {"levels": originals})

    out_dir = eng / "colour" / "plan"
    for old in out_dir.glob("*.json") if out_dir.exists() else []:
        old.unlink()
    warnings, planned = [], 0
    for level in sorted(design["levels"], key=lambda l: level_sort_key(l["levelNumber"])):
        verdicts = {bid: results[bid]["verdict"] for bid in level["boxes"] if bid in results}
        coloured = [b for b, v in verdicts.items() if v in common.COLOURED]
        if not coloured:
            continue
        changes, notes = [], []
        obstacles = [r for r in (rect_of(design["boxes"][b]["layout"]) for b in level["boxes"]) if r]
        obstacles += [r for r in (rect_of(t) for t in level.get("texts") or []) if r]
        for n in level["freeNotes"]:
            if n["ours"]:
                changes.append({"op": "remove", "kind": "note", "key": n["key"]})
            elif rect_of(n):
                obstacles.append(rect_of(n))
        for bid in level["boxes"]:
            verdict = verdicts.get(bid)
            if verdict not in common.COLOURED:
                continue
            box = design["boxes"][bid]
            changes.append({"op": "update", "kind": "activity", "key": box["key"], "fill": rows[verdict]["fill"]})
            if verdict == "supported":
                continue
            note = (results[bid].get("note") or "").strip()
            if common.word_count(note) > limits["note_max_words"]:
                raise Failed([f"box {bid}: its note has more than {limits['note_max_words']} words"])
            rect = rect_of(box["layout"])
            if rect is None:
                raise Failed([f"box {bid} has no position: read level {level['levelNumber']} with include [\"layout\"]"])
            (x, y), crowded = place(rect, size, gap, obstacles, level.get("canvas"))
            if crowded:
                warnings.append(f"level {level['levelNumber']}: the note for '{box['text']}' overlaps something; move it by hand if it hides text")
            obstacles.append((x, y, size, size))
            ref = f"n{len(notes) + 1}"
            text = f"{common.NOTE_MARKER} {rows[verdict]['label']}. {note}" if note else f"{common.NOTE_MARKER} {rows[verdict]['label']}."
            changes.append({"op": "add", "kind": "note", "ref": ref, "text": text, "position": {"x": x, "y": y}})
            notes.append({"box": bid, "ref": ref})
        present = set(verdicts.values())
        rects = [rect_of(design["boxes"][b]["layout"]) for b in level["boxes"] if rect_of(design["boxes"][b]["layout"])]
        min_x, min_y = min(r[0] for r in rects), min(r[1] for r in rects)
        legend_at = place_legend(min_x, min_y, size, gap, obstacles, level.get("canvas"))
        changes.append({"op": "add", "kind": "note", "ref": "legend", "text": legend_text(present, rows),
                        "position": {"x": legend_at[0], "y": legend_at[1]}})
        removals = sum(1 for c in changes if c["op"] == "remove")
        write_json(out_dir / f"{level['levelNumber']}.json", {
            "diagramId": level["diagramId"], "baseVersion": level["version"], "changes": changes, "notes": notes,
            "confirm": removals > 0,  # Elements asks for confirm above 5 removals or 30% of a level; a plan removes only the playbook's own notes
            "fills": {str(design["boxes"][b]["key"]): rows[verdicts[b]]["fill"] for b in coloured}})
        planned += 1
        print(f"PLANNED level {level['levelNumber']}: {len(coloured)} box(es) coloured, {len(notes)} note(s), a legend")
    for line in warnings:
        print(f"WARNING {line}")
    if not planned:
        print("NOTHING TO COLOUR: no box in scope has a coloured verdict")
    return 0


def record(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    levels = {l["levelNumber"]: l for l in design["levels"]}
    applied, errors = {}, []
    for path in sorted((eng / "colour" / "plan").glob("*.json")):
        number = path.stem
        planned = load_json(path)
        level = levels.get(number)
        if level is None:
            errors.append(f"level {number} is not in the design; rebuild it from fresh reads")
            continue
        by_key = {str(design["boxes"][b]["key"]): design["boxes"][b] for b in level["boxes"]}
        for key, fill in planned["fills"].items():
            have = (by_key.get(key, {}).get("layout") or {}).get("fill")
            if (have or "").upper() != fill.upper():
                errors.append(f"level {number}: box {key} has fill {have}, the plan wrote {fill}")
        ours = [n["key"] for n in level["freeNotes"] if n["ours"]]
        want = len(planned["notes"]) + 1
        if len(ours) != want:
            errors.append(f"level {number}: {len(ours)} of the playbook's notes are on the level, the plan wrote {want}")
        applied[number] = {"diagramId": level["diagramId"], "noteKeys": ours, "fills": planned["fills"]}
    if errors:
        raise Failed(errors)
    write_json(eng / "colour" / "applied.json", {"levels": applied})
    print(f"RECORDED {len(applied)} level(s) coloured: " + ", ".join(sorted(applied, key=level_sort_key)))
    return 0


def palette():
    return {r["fill"].upper() for v, r in common.load_verdicts().items() if r["fill"]}


def reset_plan(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    orig_path, applied_path = eng / "colour" / "originals.json", eng / "colour" / "applied.json"
    originals = load_json(orig_path)["levels"] if orig_path.exists() else None
    applied = load_json(applied_path)["levels"] if applied_path.exists() else {}
    ours_fills = palette()
    out_dir = eng / "colour" / "reset"
    for old in out_dir.glob("*.json") if out_dir.exists() else []:
        old.unlink()
    kept, planned = [], 0
    for level in sorted(design["levels"], key=lambda l: level_sort_key(l["levelNumber"])):
        number = level["levelNumber"]
        changes = [{"op": "remove", "kind": "note", "key": n["key"]} for n in level["freeNotes"] if n["ours"]]
        written = (applied.get(number) or {}).get("fills") or {}
        for bid in level["boxes"]:
            box = design["boxes"][bid]
            key = str(box["key"])
            fill = (box["layout"].get("fill") or "").upper()
            back = ((originals or {}).get(number) or {}).get(key)
            if back is not None and (back.get("fill") or "").upper() == fill and fill not in ours_fills:
                continue  # already put back (a reset resumed after this level was written)
            if written:
                ours = key in written and written[key].upper() == fill
            elif originals is not None:  # coloured but not recorded: the boxes whose colours were saved
                ours = back is not None and fill in ours_fills
            else:  # no run files: the playbook's colours
                ours = fill in ours_fills
            if not ours:
                if key in written:
                    kept.append(f"level {number}: '{box['text']}' was recoloured after the check; left as it is")
                continue
            if back is None:
                back = {"fill": None, "border": None}
            changes.append({"op": "update", "kind": "activity", "key": box["key"], "fill": back["fill"], "border": back["border"]})
        if changes:
            removals = sum(1 for c in changes if c["op"] == "remove")
            write_json(out_dir / f"{number}.json", {"diagramId": level["diagramId"], "baseVersion": level["version"],
                                                    "changes": changes, "confirm": removals > 0})
            planned += 1
            print(f"RESET level {number}: {sum(1 for c in changes if c['kind'] == 'activity')} box(es), "
                  f"{sum(1 for c in changes if c['kind'] == 'note')} note(s)")
    for line in kept:
        print(f"KEPT {line}")
    if originals is None:
        print("NOTE no saved originals: boxes in the playbook's colours go back to the theme colour")
    if not planned:
        print("NOTHING TO RESET: no colour or note of this playbook is on the design")
    return 0


def reset_verify(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    applied_path = eng / "colour" / "applied.json"
    applied = load_json(applied_path)["levels"] if applied_path.exists() else {}
    errors = []
    for level in design["levels"]:
        number = level["levelNumber"]
        left = [n["key"] for n in level["freeNotes"] if n["ours"]]
        if left:
            errors.append(f"level {number}: {len(left)} note(s) of the playbook are still there")
        written = (applied.get(number) or {}).get("fills") or {}
        for bid in level["boxes"]:
            box = design["boxes"][bid]
            key = str(box["key"])
            if key in written and (box["layout"].get("fill") or "").upper() == written[key].upper():
                errors.append(f"level {number}: '{box['text']}' still has the check's colour")
    if errors:
        raise Failed(errors)
    print("RESET OK: no colour or note of the check is left")
    return 0


def main():
    args = sys.argv[1:]
    commands = {"plan": plan, "record": record, "reset-plan": reset_plan, "reset-verify": reset_verify}
    if len(args) == 2 and args[0] in commands:
        return commands[args[0]](args[1])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    common.run(main)
