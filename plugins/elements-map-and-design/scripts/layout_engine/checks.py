"""The layout check: compares saved review reads with the plan against the layout rubric rows.

Part of the shared layout engine (see __init__.py). Standard library only; Python 3.8 or later.
"""

import json
from collections import defaultdict
from pathlib import Path

from .base import RUBRIC_PATH, load_style, read_csv, read_json, squash
from .geometry import route, route_crossings
from .reads import refuse, review_refusals
from .write_loop import level_diagram_ids, unlinkable


ALLOWED = {
    ("same", "right"): {("right", "left")},
    ("same", "left"): {("top", "top")},
    ("same", "same"): {("top", "top")},
    ("above", "right"): {("top", "left"), ("right", "bottom")},
    ("above", "left"): {("top", "top")},
    ("above", "same"): {("top", "top")},
    ("below", "right"): {("bottom", "left"), ("right", "top"), ("right", "left")},
    ("below", "left"): {("right", "left"), ("top", "top")},
    ("below", "same"): {("top", "top")},
}


def relation(a, b):
    acy, bcy = a["y"] + a["h"] / 2, b["y"] + b["h"] / 2
    vertical = "same" if abs(acy - bcy) < min(a["h"], b["h"]) / 2 else ("above" if bcy < acy else "below")
    horizontal = "same" if abs(a["x"] - b["x"]) < 30 else ("right" if b["x"] > a["x"] else "left")
    return vertical, horizontal


def layout_rules():
    rules = {}
    for row in read_csv(RUBRIC_PATH):
        if row.get("checked_by") == "layout-check":
            rules[row["rule_id"]] = row
    return rules


def refuse_partial_reads(workdir, the_plan=None):
    """Raise TrimmedReads, naming each file, when a review read the plan needs is missing or is not the whole
    get_diagram answer (reads.py), so no layout-check.json is written from it."""
    workdir = Path(workdir)
    ids, skip = {}, set()
    if the_plan and the_plan.get("levels"):
        ids = level_diagram_ids(workdir, the_plan)
        if the_plan.get("preflight"):
            skip = unlinkable(workdir, the_plan)
    refusals = review_refusals(workdir, the_plan, ids, skip)
    if refusals:
        refuse(workdir, refusals)


def check(workdir):
    workdir = Path(workdir)
    has_plan = (workdir / "plan.json").exists()
    the_plan = read_json(workdir / "plan.json") if has_plan else {"diagramType": "process"}
    refuse_partial_reads(workdir, the_plan if has_plan else None)
    style = load_style(the_plan.get("diagramType", "process"))
    rules = layout_rules()
    findings, checked = [], []

    def add(rule, level, element, issue, fix):
        if rule in rules:
            findings.append({"rule": rule, "severity": rules[rule]["severity"], "level": level, "element": element, "issue": issue, "fix": fix})

    for path in sorted((workdir / "review").glob("*.json")):
        read = read_json(path)
        diagram = read.get("diagram", read)
        level = read.get("levelNumber", path.stem)
        checked.append(level)
        boxes = {a["key"]: a for a in diagram.get("activities", []) if all(k in a for k in ("x", "y", "w", "h"))}
        if not boxes:
            continue
        box_list = list(boxes.values())
        name = lambda key: f"'{boxes[key]['text']}' (key {key})" if key in boxes else f"key {key}"
        outgoing = defaultdict(list)
        for line in diagram.get("lines", []):
            src = (line.get("from") or {}).get("activity") if isinstance(line.get("from"), dict) else None
            dst = (line.get("to") or {}).get("activity") if isinstance(line.get("to"), dict) else None
            label = line.get("label", "")
            fs, ts = line.get("fromSide"), line.get("toSide")
            if src is not None:
                outgoing[src].append(line)
            element = f"line {json.dumps(label)} (key {line['key']})"
            if src is not None and fs is None:
                add("R13", level, element, f"The line leaves {name(src)} away from the middle of a side.", "Set fromSide on the line.")
            if dst is not None and ts is None:
                add("R13", level, element, f"The line enters {name(dst)} away from the middle of a side.", "Set toSide on the line.")
            if src in boxes and dst in boxes and fs and ts and src != dst:
                rel = relation(boxes[src], boxes[dst])
                if (fs, ts) not in ALLOWED.get(rel, set()):
                    options = " or ".join(f"{a} to {b}" for a, b in sorted(ALLOWED.get(rel, set())))
                    add("R13", level, element, f"The line goes {fs} to {ts}, but its target is {rel[0]} and to the {rel[1]} of its source.",
                        f"Use {options} (data/line-sides.csv)." if options else "Move the target box so the line follows data/line-sides.csv.")
                hits = route_crossings(route(boxes[src], fs, boxes[dst], ts), box_list, {src, dst})
                for hit in hits:
                    add("R16", level, element, f"The line from {name(src)} to {name(dst)} is likely to run through {name(hit['key'])}.",
                        "Move one of the boxes so the line has a clear path, or check it in the editor.")
            if src is None and dst in boxes and ts and ts != "left":
                add("R13", level, element, f"A start line enters {name(dst)} at its {ts} side.", "Start lines enter the left side.")
            if dst in boxes or src in boxes:
                anchor = boxes.get(dst) if src is None and dst in boxes else (boxes.get(src) if dst is None else None)
                side = "left" if src is None else fs
                if anchor and side:
                    region = clearance_region(anchor, side, style)
                    for other in box_list:
                        if other["key"] != anchor["key"] and region_overlaps(region, other):
                            add("R15", level, element, f"{name(other['key'])} sits in the space kept clear for the {'start' if src is None else 'end'} line of {name(anchor['key'])}.",
                                f"Move it at least {style['free_end_clearance'] if side in ('left', 'right') else style['free_end_length_vertical'] + 20} px away.")
        threshold = int(rules.get("R14", {}).get("threshold") or 2)
        for group in groups_by(box_list, lambda b: b["y"] + b["h"] / 2):
            centres = [b["y"] + b["h"] / 2 for b in group]
            if len(group) > 1 and max(centres) - min(centres) > threshold:
                add("R14", level, ", ".join(name(b["key"]) for b in group), "These boxes form a row but their middles are not level.", "Give them the same middle so the lines between them are straight.")
        for group in groups_by(box_list, lambda b: b["x"]):
            lefts = [b["x"] for b in group]
            if len(group) > 1 and max(lefts) - min(lefts) > threshold:
                add("R14", level, ", ".join(name(b["key"]) for b in group), "These boxes form a column but their left edges do not line up.", "Give them the same x.")
        limit = int(rules.get("R17", {}).get("threshold") or style["max_decision_outcomes"])
        for key, lines in outgoing.items():
            outcomes = {squash(ln.get("label")) for ln in lines}
            if key in boxes and len(outcomes) > limit:
                add("R17", level, name(key), f"The box has {len(outcomes)} different outcomes; past {limit} they share a side, which UPN reads as parallel paths.", "Split the decision into two boxes.")
    result = {"findings": findings, "checked": checked}
    (workdir / "layout-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def clearance_region(box, side, style):
    reach = style["free_end_clearance"] if side in ("left", "right") else style["free_end_length_vertical"] + 20
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    if side == "left":
        return (box["x"] - reach, cy - 20, box["x"], cy + 20)
    if side == "right":
        return (box["x"] + box["w"], cy - 20, box["x"] + box["w"] + reach, cy + 20)
    if side == "top":
        return (cx - 20, box["y"] - reach, cx + 20, box["y"])
    return (cx - 20, box["y"] + box["h"], cx + 20, box["y"] + box["h"] + reach)


def region_overlaps(region, box):
    return region[0] < box["x"] + box["w"] and region[2] > box["x"] and region[1] < box["y"] + box["h"] and region[3] > box["y"]


def groups_by(boxes, measure, tolerance=30):
    groups = []
    for box in sorted(boxes, key=measure):
        if groups and measure(box) - measure(groups[-1][-1]) <= tolerance:
            groups[-1].append(box)
        else:
            groups.append([box])
    return groups
