#!/usr/bin/env python3
"""Lay out a business-architecture model as an Elements capability map, step through writing it with
manage_diagram, and check the drawn result.

Usage:
  python3 layout_capability.py plan MODEL.json --workdir DIR [--scale NAME] [--children-as boxes|list]
                                [--no-drivers] [--no-legend] [--skip KINDS] [--name TEXT]
  python3 layout_capability.py next DIR
  python3 layout_capability.py check DIR

plan   Works out every card and heading: a row of driver cards under a section heading, a grid of columns
       each under the heading of a top-level capability (a text box), sub-capabilities as cards stacked
       beneath, a capability that groups cards of its own as a sub-heading with its cards under it, band
       rows below the grid, and a rating legend on the left. A capability whose sub-capabilities are list
       lines, or that has none, is a card. Sizes and gaps come from data/style-capability.csv, rating colours
       from data/capability-ratings.csv. Writes DIR/plan.json and DIR/preview.svg (the planned layout, to look
       at before anything is written) and prints a summary with any warnings and gaps. Refuses a model that
       fails validate.py for its diagram type.
       --scale picks the rating scale (default: assessment). --children-as list draws every lowest level
       of sub-capabilities as list lines on its parent's card instead of as cards, unless the model says
       otherwise for a capability. --skip metadata,story,link,note leaves those attachment kinds out;
       note also leaves out the Inferred and Description notes.
next   Prints, as JSON, the one thing to do next: create the map, dry-run a batch of changes, send it,
       read the level back, read it for review, or nothing (done). Batches add the cards that fit the
       level's canvas; once every card is on the level, a read-back compares each card with the layout
       and moves any that are out of place. Run it again after saving each result where it says.
check  Checks DIR/review/top.json against the plan and the rubric rows checked by layout-check for
       capability maps (R26-R28) and writes DIR/layout-check.json in the diagram-reviewer's finding format.

Why headings rather than boxes: manage_diagram makes every card on a capability map 200 px wide and sizes
its height from its footer and list lines; it cannot resize a card, so a parent cannot be drawn as a box
around its children. A capability that groups others is drawn as a heading instead: a text box (always
120 x 80 px, its text centred near the top) over the column of cards it groups. Every card in a column shares
one left edge, so the map reads as a clean grid.

Files in DIR: plan.json, preview.svg, map.json, batches/<n>.json and <n>.final.json (what each batch
sends), results/<n>.dry.json and <n>.json (the dry run and the real call), reads/<n>.json (the level after
batch n), review/top.json, layout-check.json.

Exit 0: done. Exit 1: the model, the plan or a saved file has a problem the output describes.
Exit 2: setup problem (a data file or the command line).

Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name, hydrate, bind_step, write_complete, write_recovery

import argparse
import csv
import html
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attachment_scope import scope_model, unscoped_attachment_stop
import validate  # noqa: E402  (the drawing gate: no plan from a model that fails validation)
from layout_engine.reads import REVIEW_INCLUDE, TrimmedReads, refuse, reread, saved_read_problems  # noqa: E402  (the whole-read rule)

PLUGIN = Path(__file__).resolve().parents[1]
STYLE_PATH = PLUGIN / "data" / "style-capability.csv"
RATINGS_PATH = PLUGIN / "data" / "capability-ratings.csv"
RUBRIC_PATH = PLUGIN / "data" / "readability-rubric.csv"

MAX_CHANGES = 100
MAX_DEPTH = 4              # three levels of cards and a fourth as list lines
MOVE_ROUNDS = 3            # read-back-and-move passes before the run stops and asks

# Errors that clear up on their own: the dry run is sent again after the user leaves edit mode or after a wait,
# instead of stopping the run (the drawing protocol, section 4). Code -> what to do before sending it again.
TRANSIENT = {
    "lock_held": "someone, maybe the user, has the level open in edit mode: ask them to leave edit mode",
    "being_edited": "someone, maybe the user, has the level open in edit mode: ask them to leave edit mode",
    "rate_limited": "wait a minute (or retryAfter seconds)",
    "server_busy": "wait a minute (or retryAfter seconds)",
}
BLANK_CANVAS = {"x": 0, "y": 0, "w": 2000, "h": 1200}   # a blank level, as get_diagram reports it
ATTACHMENT_KINDS = ("metadata", "story", "link", "note")


class SetupError(Exception):
    pass


class PlanError(Exception):
    pass


# ---------------------------------------------------------------- data files

def read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                    for row in csv.DictReader(handle) if any((v or "").strip() for v in row.values())]
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


NEEDED = ["card_width", "card_height", "list_base", "footer_height", "list_line_height", "text_width",
          "text_height", "column_gap", "max_columns", "max_stack", "sibling_gap", "group_gap", "row_gap",
          "label_gap", "legend_gap", "heading_case_top", "heading_max_word", "heading_max_word_upper", "header_border", "header_fill", "rated_border",
          "drivers_title", "box_text_max_chars", "heading_max_chars", "footer_max_chars", "list_max_items"]


def load_style():
    style = {}
    for row in read_csv(STYLE_PATH):
        value = row["value"]
        try:
            style[row["setting"]] = float(value) if re.fullmatch(r"-?\d+\.\d+", value) else int(value)
        except ValueError:
            style[row["setting"]] = value
    missing = [n for n in NEEDED if n not in style]
    if missing:
        raise SetupError(f"{STYLE_PATH.name} lacks {', '.join(missing)}")
    style["pitch"] = style["card_width"] + style["column_gap"]
    style["heading_dx"] = (style["card_width"] - style["text_width"]) // 2   # centres a heading over a column
    return style


def load_scale(name):
    rows = read_csv(RATINGS_PATH)
    mine = sorted((r for r in rows if r["scale"] == name), key=lambda r: int(r["order"]))
    if not mine:
        raise SetupError(f"{RATINGS_PATH.name} has no scale '{name}'; it has {', '.join(sorted({r['scale'] for r in rows}))}")
    return {"name": name, "title": mine[0]["title"],
            "values": [{"value": r["value"], "label": r["label"], "fill": r["fill"], "border": r["border"]} for r in mine]}


def layout_rules():
    return {row["rule_id"]: row for row in read_csv(RUBRIC_PATH)
            if row["checked_by"] == "layout-check" and "capability" in row["applies_to"].split("|")}


# ---------------------------------------------------------------- sizes

def card_size(box, style):
    """The size manage_diagram gives a card: fixed width; height from its footer and list lines."""
    if box["kind"] == "label":
        return style["text_width"], style["text_height"]
    lines = len(box.get("attributes", []))
    if box.get("footer"):
        height = style["footer_height"] + style["list_line_height"] * lines
    else:
        height = max(style["card_height"], style["list_base"] + style["list_line_height"] * lines)
    return style["card_width"], height


# ---------------------------------------------------------------- the boxes

class Builder:
    def __init__(self, model, scale, children_as, style, skip):
        self.model, self.scale, self.children_as, self.style, self.skip = model, scale, children_as, style, skip
        self.boxes, self.warnings, self.gaps = [], [], []
        self.values = {v["value"].casefold(): v for v in scale["values"]}
        self.used_ratings = set()
        self.lost = defaultdict(list)     # what a heading cannot show -> the headings that have it
        caps = model.get("capabilities", [])
        self.by_id = {c["id"]: c for c in caps}
        self.kids = defaultdict(list)
        self.tops = []
        for cap in caps:
            if cap.get("parent") in self.by_id:
                self.kids[cap["parent"]].append(cap)
            else:
                self.tops.append(cap)

    def warn(self, text):
        self.warnings.append(text)

    def add(self, kind, text, **extra):
        box = {"ref": f"{'t' if kind == 'label' else 'b'}{len(self.boxes) + 1}", "kind": kind, "text": text,
               "parent": None, "attributes": []}
        box.update({k: v for k, v in extra.items() if v not in (None, [], "")})
        box["w"], box["h"] = card_size(box, self.style)
        self.boxes.append(box)
        return box

    def heading_text(self, text, top):
        """A heading's text: in capitals at the top level when every word still fits the text box's width."""
        words = text.split()
        too_long = [w for w in words if len(w) > self.style["heading_max_word"]]
        if too_long:
            self.warn(f"the heading '{text}' has a word too long for its 120 px text box ({', '.join(too_long)}); "
                      "the text box will cut it. Use a shorter word or a hyphen")
        if top and self.style["heading_case_top"] == "upper":
            if all(len(w) <= self.style["heading_max_word_upper"] for w in words):
                return text.upper()
        return text

    def rating(self, cap, as_line):
        raw = cap.get("rating")
        if raw is None:
            return None
        found = self.values.get(str(raw).casefold())
        if not found:
            self.warn(f"capabilities[{cap['id']}] has rating '{raw}', which scale '{self.scale['name']}' does not have "
                      f"({', '.join(v['value'] for v in self.scale['values'])}); it is drawn without a colour")
            return None
        if as_line:
            self.warn(f"capabilities[{cap['id']}] has a rating but is drawn as a list line, which cannot take a colour; "
                      "draw its parent's sub-capabilities as cards to show it")
            return None
        self.used_ratings.add(found["value"])
        return found

    def list_mode(self, cap, level):
        """True when this capability's sub-capabilities are list lines on its card."""
        children = self.kids.get(cap["id"], [])
        if not children:
            return False
        own = cap.get("childrenAs")
        grand = any(self.kids.get(c["id"]) for c in children)
        if level >= MAX_DEPTH - 1:
            if own == "boxes":
                self.warn(f"capabilities[{cap['id']}] is at level {level}; its sub-capabilities are drawn as list lines, "
                          "because headings group two levels at most")
            return True
        if own:
            return own == "list"
        return self.children_as == "list" and not grand

    def node(self, cap, level, parent, band=False):
        """One capability: a heading (text box) when its sub-capabilities are cards, otherwise a card.
        Returns (box, the sub-capabilities to draw as cards under it)."""
        if level > 1 and cap.get("placement"):
            self.warn(f"capabilities[{cap['id']}] has placement '{cap['placement']}', which only top-level capabilities take; ignored")
        if cap.get("bandRow") is not None and not (band and level == 1):
            self.warn(f"capabilities[{cap['id']}] has bandRow but is not a band; ignored")
        children = self.kids.get(cap["id"], [])
        if children and not self.list_mode(cap, level):
            if cap.get("rating") is not None:
                self.rating(cap, False)
                self.lost["a rating colour"].append(cap["name"])
            for key, what in (("icon", "an icon"), ("description", "a description"), ("attachments", "attachments"),
                              ("inferred", "an Inferred note")):
                if cap.get(key):
                    self.lost[what].append(cap["name"])
            box = self.add("label", self.heading_text(cap["name"], level == 1), modelId=cap["id"], role="heading",
                           level=level, parent=parent)
            return box, children
        found = self.rating(cap, False)
        top = level == 1
        if top:
            fill, border = (found["fill"] if found else self.style["header_fill"]), self.style["header_border"]
        elif found:
            fill, border = found["fill"], self.style["rated_border"]
        else:
            fill = border = None
        attributes, list_ids, list_inferred = [], [], []
        for child in children:
            self.rating(child, True)
            attributes.append(child["name"])
            list_ids.append(child["id"])
            if child.get("inferred"):
                list_inferred.append(child["name"])
            if self.kids.get(child["id"]):
                names = ", ".join(c["name"] for c in self.kids[child["id"]][:3])
                self.gaps.append({"about": child["id"], "note": f"'{child['name']}' is drawn as a list line on "
                                  f"'{cap['name']}', so its {len(self.kids[child['id']])} sub-capabilities ({names}...) are not drawn"})
        if len(children) > self.style["list_max_items"]:
            self.warn(f"capabilities[{cap['id']}] lists {len(children)} sub-capabilities as lines; more than "
                      f"{self.style['list_max_items']} makes a long card. Consider cards or grouping them")
        if list_inferred:
            self.warn(f"capabilities[{cap['id']}] has inferred sub-capabilities drawn as list lines; the Inferred note goes on its card")
        box = self.add("capability", cap["name"], modelId=cap["id"], role="header" if top else "card", level=level,
                       parent=parent, footer=cap.get("description") if top else None, attributes=attributes,
                       listIds=list_ids, listInferred=list_inferred, fill=fill, border=border,
                       rating=found["value"] if found else None, icon=cap.get("icon"),
                       inferred=bool(cap.get("inferred")) or None, evidence=list(cap.get("evidence", [])),
                       description=None if top else cap.get("description"),
                       attachments=list(cap.get("attachments", [])))
        return box, []


def balanced_split(items, parts, height):
    """Split items, in order, into `parts` runs with the tallest run as short as it can be."""
    parts = max(1, min(parts, len(items)))
    if parts == 1:
        return [items]
    sizes = [height(i) for i in items]
    n = len(items)
    prefix = [0]
    for s in sizes:
        prefix.append(prefix[-1] + s)
    memo = {}

    def solve(start, k):
        if (start, k) not in memo:
            if k == 1:
                memo[(start, k)] = (prefix[n] - prefix[start], [n])
            else:
                best = None
                for end in range(start + 1, n - k + 2):
                    rest, cuts = solve(end, k - 1)
                    cost = max(prefix[end] - prefix[start], rest)
                    if best is None or cost < best[0]:
                        best = (cost, [end] + cuts)
                memo[(start, k)] = best
        return memo[(start, k)]

    _, cuts = solve(0, parts)
    runs, start = [], 0
    for end in cuts:
        runs.append(items[start:end])
        start = end
    return runs


def plan(model, scale_name, children_as, show_drivers, show_legend, skip, name):
    style = load_style()
    scale = load_scale(scale_name)
    b = Builder(model, scale, children_as, style, skip)
    for item in model.get("gaps", []):
        b.gaps.append({"about": item.get("about"), "note": item["note"], "fromModel": True})
    for cap in model.get("capabilities", []):
        depth, node, seen = 1, cap, {cap["id"]}
        while node.get("parent") in b.by_id and node["parent"] not in seen:
            node = b.by_id[node["parent"]]
            seen.add(node["id"])
            depth += 1
        if depth == MAX_DEPTH + 1:
            b.gaps.append({"about": cap["id"], "note": f"'{cap['name']}' is at level {depth}; a capability map draws "
                           f"{MAX_DEPTH} levels, so it and the capabilities below it are not drawn"})
    columns = [c for c in b.tops if (c.get("placement") or "column") == "column"]
    bands = [c for c in b.tops if c.get("placement") == "band"]
    if not columns and not bands:
        raise PlanError("the model has no capabilities to draw")
    if not columns:
        b.warn("every top-level capability is a band; the map has no grid of columns")

    rows = []        # layout rows: {"kind", "label", "stacks": [{"col", "items": [{"ref"|"spacer", "gap", "dx"}]}]}
    centre = style["heading_dx"]
    sizes = lambda ref: next(x for x in b.boxes if x["ref"] == ref)["h"]

    # drivers: a section heading, then a row of cards
    drivers = model.get("drivers", []) if show_drivers else []
    if drivers:
        label = b.add("label", b.heading_text(style["drivers_title"], True), role="section")
        cards = [b.add("driver", d["name"], modelId=d["id"], footer=d.get("description"),
                       inferred=bool(d.get("inferred")) or None, evidence=list(d.get("evidence", [])),
                       attachments=list(d.get("attachments", []))) for d in drivers]
        for start in range(0, len(cards), style["max_columns"]):
            chunk = cards[start:start + style["max_columns"]]
            rows.append({"kind": "drivers", "label": label["ref"] if start == 0 else None,
                         "stacks": [{"col": i, "items": [{"ref": c["ref"], "gap": 0, "dx": 0}]} for i, c in enumerate(chunk)]})
    legend_at = len(rows)

    def entries_under(children, heading_box, level):
        """Stack entries for the sub-capabilities drawn as cards under a heading: each entry is a card, or a
        sub-heading followed by its cards."""
        entries, previous_group = [], False
        cards_first = sorted(children, key=lambda c: bool(b.kids.get(c["id"])) and not b.list_mode(c, level))
        for index, cap in enumerate(cards_first):
            box, grand = b.node(cap, level, heading_box["ref"])
            is_group = box["kind"] == "label"
            if index == 0:
                gap = style["label_gap"]
            elif is_group or previous_group:
                gap = style["group_gap"]
            else:
                gap = style["sibling_gap"]
            entry = [{"ref": box["ref"], "gap": gap, "dx": centre if is_group else 0}]
            for j, child in enumerate(grand):
                card, _ = b.node(child, level + 1, box["ref"])
                entry.append({"ref": card["ref"], "gap": style["label_gap"] if j == 0 else style["sibling_gap"], "dx": 0})
            entries.append(entry)
            previous_group = is_group
        return entries

    def entry_height(entry):
        return sum(it["gap"] + sizes(it["ref"]) for it in entry)

    column_blocks = []
    for cap in columns:
        box, children = b.node(cap, 1, None)
        if box["kind"] != "label":
            column_blocks.append([[{"ref": box["ref"], "gap": 0, "dx": 0}]])
            continue
        entries = entries_under(children, box, 2)
        direct = len(entries)
        span = max(1, min(style["max_columns"], math.ceil(direct / style["max_stack"])))
        if span > 1:
            b.warn(f"capabilities[{cap['id']}] has {direct} sub-capabilities; they continue into {span - 1} more "
                   f"column(s) so no stack is taller than {style['max_stack']} cards")
        stacks = []
        for k, run in enumerate(balanced_split(entries, span, entry_height)):
            items = [{"ref": box["ref"], "gap": 0, "dx": centre}] if k == 0 else [{"spacer": box["ref"], "gap": 0, "dx": 0}]
            for j, entry in enumerate(run):
                first = dict(entry[0])
                if j == 0:
                    first["gap"] = style["label_gap"]
                items += [first] + entry[1:]
            stacks.append(items)
        column_blocks.append(stacks)

    current, used = [], 0
    for stacks in column_blocks:
        if current and used + len(stacks) > style["max_columns"]:
            rows.append({"kind": "grid", "label": None, "stacks": current})
            current, used = [], 0
        for k, items in enumerate(stacks):
            current.append({"col": used + k, "items": items})
        used += len(stacks)
    if current:
        rows.append({"kind": "grid", "label": None, "stacks": current})

    # bands: a band that groups cards is a section heading over a row of them; a band that is a card shares a row
    # with the other card bands of its bandRow
    groups = []
    for index, cap in enumerate(bands):
        key = ("row", cap["bandRow"]) if cap.get("bandRow") is not None else ("own", index)
        for group in groups:
            if group[0] == key:
                group[1].append(cap)
                break
        else:
            groups.append((key, [cap]))
    for _, members in groups:
        card_stacks = []
        for cap in members:
            box, children = b.node(cap, 1, None, band=True)
            if box["kind"] != "label":
                card_stacks.append(box)
                continue
            entries = entries_under(children, box, 2)
            for start in range(0, len(entries), style["max_columns"]):
                chunk = entries[start:start + style["max_columns"]]
                stacks = []
                for col, entry in enumerate(chunk):
                    first = dict(entry[0], gap=0, dx=0 if entry[0]["dx"] == 0 else centre)
                    stacks.append({"col": col, "items": [first] + entry[1:]})
                rows.append({"kind": "band", "label": box["ref"] if start == 0 else None, "stacks": stacks})
        for start in range(0, len(card_stacks), style["max_columns"]):
            chunk = card_stacks[start:start + style["max_columns"]]
            rows.append({"kind": "band", "label": None,
                         "stacks": [{"col": i, "items": [{"ref": c["ref"], "gap": 0, "dx": 0}]} for i, c in enumerate(chunk)]})

    # legend, left of the first grid row
    legend = None
    if show_legend and b.used_ratings:
        title = b.add("label", b.heading_text(scale["title"], True), role="section")
        swatches = [b.add("swatch", v["label"], fill=v["fill"], border=v["border"], rating=v["value"]) for v in scale["values"]]
        legend = {"label": title["ref"], "items": [{"ref": s["ref"], "gap": 0 if i == 0 else style["sibling_gap"], "dx": 0}
                                                    for i, s in enumerate(swatches)],
                  "alignRow": next((i for i, r in enumerate(rows) if r["kind"] == "grid"), legend_at)}

    for what, names in b.lost.items():
        b.warn(f"{len(names)} heading(s) cannot show {what}, because a capability that groups others is a text box: "
               f"{', '.join(names)}")

    layout = {"rows": rows, "legend": legend, "x0": (style["card_width"] + style["legend_gap"]) if legend else 0}
    positions = place(layout, {bx["ref"]: (bx["w"], bx["h"]) for bx in b.boxes}, style)
    for bx in b.boxes:
        bx["x"], bx["y"] = positions[bx["ref"]]

    # creation order: reading order (top to bottom, then left to right), so batches fill the canvas from the top
    b.boxes.sort(key=lambda bx: (bx["y"], bx["x"]))
    for number, bx in enumerate(b.boxes, start=1):
        bx["order"] = number
        limit = style["heading_max_chars"] if bx["kind"] == "label" else style["box_text_max_chars"]
        if bx.get("modelId") and len(bx["text"]) > limit:
            what = "a heading's text box shows about" if bx["kind"] == "label" else "a card does not grow for its title, so over"
            b.warn(f"'{bx['text'][:40]}...' is {len(bx['text'])} characters; {what} {limit} characters")
        if bx.get("footer") and len(bx["footer"]) > style["footer_max_chars"]:
            b.warn(f"the footer of '{bx['text']}' is {len(bx['footer'])} characters; a card does not grow for its "
                   f"footer, so over {style['footer_max_chars']} it may be cut")
    for bx in b.boxes:
        bx["changes"] = box_changes(bx, skip)
        if not bx.get("inferred"):
            bx.pop("evidence", None)

    title = map_name(name if name is not None else model["meta"]["title"])
    return {"version": 3, "name": title, "description": (model["meta"].get("description") or "")[:5000],
            "scale": scale["name"], "skip": sorted(skip), "layout": layout, "boxes": b.boxes,
            "warnings": b.warnings, "gaps": b.gaps}


def place(layout, sizes, style):
    """Positions of every box from the layout and box sizes {ref: (w, h)}: rows top to bottom, stacks within."""
    pos = {}
    x0, pitch = layout["x0"], style["pitch"]
    cursor = 0
    row_tops = []
    for row in layout["rows"]:
        top = cursor
        if row.get("label"):
            pos[row["label"]] = (x0, top)
            top += sizes[row["label"]][1] + style["label_gap"]
        row_tops.append(top)
        bottom = top
        for stack in row["stacks"]:
            y = top
            x = x0 + stack["col"] * pitch
            for item in stack["items"]:
                y += item["gap"]
                if "spacer" in item:
                    y += sizes[item["spacer"]][1]
                    continue
                pos[item["ref"]] = (x + item["dx"], y)
                y += sizes[item["ref"]][1]
            bottom = max(bottom, y)
        cursor = bottom + style["row_gap"]
    legend = layout.get("legend")
    if legend:
        top = row_tops[legend["alignRow"]] if legend["alignRow"] < len(row_tops) else cursor
        pos[legend["label"]] = (style["heading_dx"], top)
        y = top + sizes[legend["label"]][1] + style["label_gap"]
        for item in legend["items"]:
            y += item["gap"]
            pos[item["ref"]] = (0, y)
            y += sizes[item["ref"]][1]
    return pos


def note_text(evidence):
    if evidence:
        return "Worked out rather than stated. Evidence: " + "; ".join(evidence)
    return "Worked out rather than stated by the source."


def box_changes(bx, skip):
    """The manage_diagram changes that add one box, its list lines, icon and attachments."""
    ref = bx["ref"]
    if bx["kind"] == "label":
        return [{"op": "add", "kind": "text", "ref": ref, "text": bx["text"], "position": {"x": bx["x"], "y": bx["y"]}}]
    add = {"op": "add", "kind": "activity", "ref": ref, "text": bx["text"], "position": {"x": bx["x"], "y": bx["y"]}}
    if bx.get("fill"):
        add["fill"] = bx["fill"]
        add["border"] = bx.get("border")
    if bx.get("footer"):
        add["footerText"] = bx["footer"]
    changes = [add]
    changes += [{"op": "add", "kind": "attribute", "activity": ref, "title": t} for t in bx.get("attributes", [])]
    if bx.get("icon"):
        changes.append({"op": "add", "kind": "resource", "activity": ref, "name": bx["icon"], "role": "header"})
    if "note" not in skip:
        if bx.get("inferred"):
            changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note", "title": "Inferred",
                            "text": note_text(bx.get("evidence"))})
        elif bx.get("listInferred"):
            changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note", "title": "Inferred",
                            "text": "These list lines are worked out rather than stated: " + "; ".join(bx["listInferred"])})
        if bx.get("description"):
            changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note", "title": "Description",
                            "text": bx["description"]})
    for att in bx.get("attachments", []):
        kind = att.get("type")
        if kind in skip or kind not in ATTACHMENT_KINDS:
            continue
        change = {"op": "add", "kind": "attachment", "activity": ref, "type": kind}
        if kind == "metadata":
            change["apiName"] = att["apiName"]
            for key in ("metadataType", "description", "refModelId"):
                if att.get(key):
                    change[key] = att[key]
        elif kind == "story":
            change["storyId"] = att["storyId"]
        elif kind == "link":
            change.update(title=att["title"], url=att["url"])
        else:
            change.update(title=att["title"], text=att["text"])
        changes.append(change)
    if len(changes) > MAX_CHANGES:
        raise PlanError(f"'{bx['text']}' needs {len(changes)} changes; one manage_diagram call takes {MAX_CHANGES}")
    return changes


# ---------------------------------------------------------------- preview

def preview_svg(the_plan):
    style = load_style()
    boxes = the_plan["boxes"]
    x1 = max(bx["x"] + bx["w"] for bx in boxes) + 20
    y1 = max(bx["y"] + bx["h"] for bx in boxes) + 20
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='-20 -20 {x1 + 20} {y1 + 20}' width='{x1 + 20}' "
           f"height='{y1 + 20}' font-family='Helvetica, Arial, sans-serif'>",
           f"<rect x='-20' y='-20' width='{x1 + 20}' height='{y1 + 20}' fill='#ffffff'/>"]
    for bx in boxes:
        x, y, w, h = bx["x"], bx["y"], bx["w"], bx["h"]
        if bx["kind"] == "label":
            lines = wrap(bx["text"], 11 if bx["text"].isupper() else 15)[:5]
            ty = y + h / 2 - len(lines) * 16.8 / 2 + 13
            for line in lines:
                out.append(f"<text x='{x + w / 2}' y='{ty:.0f}' font-size='14' text-anchor='middle' fill='#2f6fd6'>{html.escape(line)}</text>")
                ty += 16.8
            continue
        out.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='12' fill='{bx.get('fill') or '#ffffff'}' "
                   f"stroke='{bx.get('border') or '#9a9a9a'}' stroke-width='2'/>")
        ty = y + 24
        for line in wrap(bx["text"], 26)[:3]:
            out.append(f"<text x='{x + 12}' y='{ty}' font-size='12' font-weight='bold' fill='#222'>{html.escape(line)}</text>")
            ty += 16
        ay = y + 60
        for attr in bx.get("attributes", []):
            out.append(f"<text x='{x + 14}' y='{ay}' font-size='11' fill='#333'>{html.escape(attr[:32])}</text>")
            ay += style["list_line_height"]
        if bx.get("footer"):
            out.append(f"<rect x='{x + 2}' y='{y + h - 34}' width='{w - 4}' height='30' fill='#e8e8e8'/>")
            out.append(f"<text x='{x + w / 2}' y='{y + h - 15}' font-size='10' text-anchor='middle' fill='#555'>"
                       f"{html.escape(bx['footer'][:38] + ('...' if len(bx['footer']) > 38 else ''))}</text>")
        if bx.get("icon"):
            out.append(f"<circle cx='{x + w - 20}' cy='{y + 20}' r='10' fill='#cfe0f5'/>")
    out.append("</svg>")
    return "\n".join(out)


def wrap(text, per_line):
    lines, current = [], ""
    for word in str(text).split():
        if current and len(current) + 1 + len(word) > per_line:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return lines + ([current] if current else [])


# ---------------------------------------------------------------- stepping through the writes

def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return hydrate(json.load(handle))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def unwrap(result):
    """Saved tool results may hold the tool's whole answer or just its data."""
    if isinstance(result, dict) and isinstance(result.get("diagram"), dict):
        merged = dict(result)
        merged.update(result["diagram"])
        return merged
    return result


def elements_of(read):
    """{key: {x, y, w, h, kind}} for the activities and text boxes of a level read."""
    read = unwrap(read)
    found = {}
    for act in read.get("activities", []):
        found[act["key"]] = dict(act, kind="activity")
    for txt in read.get("texts", []):
        found[txt["key"]] = dict(txt, kind="text")
    return found


def fits(rect, canvas):
    return (rect[0] >= canvas["x"] and rect[1] >= canvas["y"] and rect[0] + rect[2] <= canvas["x"] + canvas["w"]
            and rect[1] + rect[3] <= canvas["y"] + canvas["h"])


class Run:
    def __init__(self, workdir):
        self.dir = Path(workdir)
        self.plan = read_json(self.dir / "plan.json")
        self.style = load_style()
        self.boxes = {bx["ref"]: bx for bx in self.plan["boxes"]}

    def path(self, *parts):
        return self.dir.joinpath(*parts)

    def batch_numbers(self):
        numbers = []
        n = 1
        while self.path("batches", f"{n}.json").exists():
            numbers.append(n)
            n += 1
        return numbers

    def keys(self):
        """ref -> key, from every saved real call."""
        found = {}
        for n in self.batch_numbers():
            result = self.path("results", f"{n}.json")
            if result.exists():
                found.update(unwrap(read_json(result)).get("idMap") or {})
        return found

    def written(self):
        refs = set()
        for n in self.batch_numbers():
            final = self.path("batches", f"{n}.final.json")
            result = self.path("results", f"{n}.json")
            if final.exists() and result.exists() and write_complete(unwrap(read_json(result))):
                refs.update(read_json(final).get("refs", []))
        return refs

    def dropped_icons(self):
        dropped = []
        for n in self.batch_numbers():
            final = self.path("batches", f"{n}.final.json")
            if final.exists():
                dropped += read_json(final).get("droppedIcons", [])
        return dropped

    def targets(self, read):
        """Where every box belongs, given the sizes Elements reports for the boxes already on the level."""
        keys = self.keys()
        elements = elements_of(read)
        sizes = {}
        for ref, bx in self.boxes.items():
            el = elements.get(keys.get(ref))
            sizes[ref] = (el["w"], el["h"]) if el and el.get("w") else (bx["w"], bx["h"])
        return place(self.plan["layout"], sizes, self.style), sizes


@bind_step
def next_step(workdir):
    run = Run(workdir)
    the_plan = run.plan
    stop = unscoped_attachment_stop(the_plan)
    if stop:
        return stop
    if sum(box.get("kind") != "label" for box in the_plan["boxes"]) > 150:
        raise PlanError("level exceeds 150 activities; split the capability map before creating it")
    if not run.path("map.json").exists():
        args = {"name": map_name(the_plan["name"]), "type": "capability_map"}
        if the_plan["description"]:
            args["description"] = the_plan["description"]
        return {"action": "create-map", "tool": "create_map", "arguments": args,
                "saveTo": str(run.path("map.json")), "save": "{\"mapId\", \"diagramId\", \"version\"} from the result"}
    the_map = read_json(run.path("map.json"))
    diagram = the_map["diagramId"]
    numbers = run.batch_numbers()

    # finish the batch in hand
    if numbers:
        n = numbers[-1]
        batch = read_json(run.path("batches", f"{n}.json"))
        dry, real, after = run.path("results", f"{n}.dry.json"), run.path("results", f"{n}.json"), run.path("reads", f"{n}.json")
        stop = unscoped_attachment_stop(batch)
        if stop:
            return stop
        if not dry.exists():
            return {"action": "dry-run", "tool": "manage_diagram", "batch": n, "kind": batch["kind"],
                    "arguments": {"diagramId": diagram, "baseVersion": batch["baseVersion"], "dryRun": True,
                                  "changes": batch["changes"]},
                    "saveTo": str(dry), "save": "{\"issues\"} from the dry run, keeping each issue's path"}
        final_path = run.path("batches", f"{n}.final.json")
        if not final_path.exists():
            waiting = [i for i in unwrap(read_json(dry)).get("issues", []) if i.get("code") in TRANSIENT]
            if waiting:
                code = waiting[0]["code"]
                return {"action": "retry-dry-run", "tool": "manage_diagram", "batch": n, "code": code,
                        "before": TRANSIENT[code], "retryAfter": waiting[0].get("retryAfter"),
                        "arguments": {"diagramId": diagram, "baseVersion": batch["baseVersion"], "dryRun": True,
                                      "changes": batch["changes"]},
                        "saveTo": str(dry),
                        "save": "{\"issues\"} from the new dry run, keeping each issue's path, in place of the saved one"}
            final, stop = finalise(batch, unwrap(read_json(dry)))
            if stop:
                return {"action": "stop", "reason": stop}
            write_json(final_path, final)
        final = read_json(final_path)
        stop = unscoped_attachment_stop(final)
        if stop:
            return stop
        if not real.exists():
            if not final["changes"]:
                write_json(real, {"saved": False, "skipped": True, "version": batch["baseVersion"], "idMap": {}, "issues": []})
            else:
                return {"action": "write", "tool": "manage_diagram", "batch": n, "kind": batch["kind"],
                        "arguments": {"diagramId": diagram, "baseVersion": batch["baseVersion"], "changes": final["changes"]},
                        "saveTo": str(real), "save": "{\"saved\", \"version\", \"idMap\", \"children\", \"diff\", \"issues\"} from the call"}
        outcome = unwrap(read_json(real))
        if write_recovery(outcome):
            return write_recovery(outcome)
        if not outcome.get("skipped") and not write_complete(outcome):
            return {"action": "reconcile-write", "diagramId": diagram,
                    "how": "Read the level and outline; reconcile side effects and recover genuine saved refs before replay."}
        if not after.exists():
            return {"action": "read-level", "tool": "get_diagram", "arguments": {"diagramId": diagram, "include": ["layout"], "delivery": "file"},
                    "saveTo": str(after), "save": "the whole result"}

    # plan the next batch from the latest read
    if numbers:
        read = unwrap(read_json(run.path("reads", f"{numbers[-1]}.json")))
        canvas, version = read.get("canvas") or BLANK_CANVAS, read.get("version")
    else:
        read, canvas, version = {"activities": [], "texts": []}, BLANK_CANVAS, the_map.get("version", 0)
    written = run.written()
    remaining = [bx for bx in the_plan["boxes"] if bx["ref"] not in written]
    n = (numbers[-1] if numbers else 0) + 1
    if remaining:
        targets, sizes = run.targets(read)
        changes, refs = [], []
        for bx in remaining:
            x, y = targets[bx["ref"]]
            if not fits((x, y, bx["w"], bx["h"]), canvas):
                continue
            box_changes_now = [dict(c, position={"x": x, "y": y}) if c["op"] == "add" and "position" in c else c
                               for c in bx["changes"]]
            if len(changes) + len(box_changes_now) > MAX_CHANGES:
                break
            changes += box_changes_now
            refs.append(bx["ref"])
        if not refs:
            return {"action": "stop", "reason": f"none of the {len(remaining)} cards still to draw fits the level's canvas "
                    f"({canvas}); open the map in Elements to see what is there"}
        write_json(run.path("batches", f"{n}.json"), {"kind": "add", "baseVersion": version, "changes": changes, "refs": refs})
        return next_step(workdir)

    # every box is on the level: move any that are not where the layout puts them
    targets, _ = run.targets(read)
    keys = run.keys()
    elements = elements_of(read)
    moves, late = [], 0
    for ref, (x, y) in targets.items():
        el = elements.get(keys.get(ref))
        if not el or (el.get("x"), el.get("y")) == (x, y):
            continue
        if not fits((x, y, el["w"], el["h"]), canvas):
            late += 1
            continue
        moves.append({"op": "update", "kind": "activity" if el["kind"] == "activity" else "text",
                      "key": el["key"], "position": {"x": x, "y": y}})
    if moves or late:
        rounds = sum(1 for m in numbers if read_json(run.path("batches", f"{m}.json"))["kind"] == "move")
        if rounds >= MOVE_ROUNDS or not moves:
            return {"action": "stop", "reason": f"after {rounds} read-backs {len(moves) + late} card(s) are still not where "
                    "the layout puts them; run check to see which, and tell the user"}
        write_json(run.path("batches", f"{n}.json"), {"kind": "move", "baseVersion": version, "changes": moves[:MAX_CHANGES], "refs": []})
        return next_step(workdir)

    review = run.path("review", "top.json")
    problems = saved_read_problems(review, False, REVIEW_INCLUDE, None, diagram) if review.exists() else None
    if problems is None or problems:
        step = {"action": "review-read", "tool": "get_diagram",
                "arguments": {"diagramId": diagram, "include": list(REVIEW_INCLUDE), "delivery": "file"},
                "saveTo": str(review), "save": "the whole result, exactly as get_diagram returns it: never trimmed or summarised"}
        if problems:
            step["refused"] = "the saved read is not the whole get_diagram answer: " + "; ".join(problems)
        return step
    return {"action": "done", "mapId": the_map["mapId"], "diagramId": diagram, "droppedIcons": run.dropped_icons()}


def finalise(batch, dry):
    """The changes to send for real, after the dry run: icons the library lacks are left out; boxes the canvas
    refused wait for a later batch. Returns (final, stop reason)."""
    issues = [i for i in dry.get("issues", []) if i.get("severity") == "error"]
    if not issues:
        return dict(batch), None
    changes = batch["changes"]
    owner = {}
    current = None
    for index, change in enumerate(changes):
        if change["op"] == "add" and change["kind"] in ("activity", "text"):
            current = change["ref"]
        owner[index] = current
    drop_changes, drop_boxes, dropped_icons = set(), set(), []
    for issue in issues:
        match = re.match(r"changes\[(\d+)\]", str(issue.get("path", "")))
        if not match or int(match.group(1)) >= len(changes):
            return None, f"the dry run of batch reported an error not tied to one change: {issue}"
        index = int(match.group(1))
        change = changes[index]
        if issue.get("code") == "resource_not_found" and change["kind"] == "resource":
            drop_changes.add(index)
            dropped_icons.append({"ref": change["activity"], "icon": change["name"], "message": issue.get("message")})
        elif issue.get("code") == "position_out_of_bounds" and batch["kind"] == "add":
            drop_boxes.add(owner[index])
        elif issue.get("code") == "position_out_of_bounds":
            drop_changes.add(index)
        else:
            return None, f"the dry run reported {issue.get('code')}: {issue.get('message')} (at {issue.get('path')})"
    kept = [c for i, c in enumerate(changes) if i not in drop_changes and owner.get(i) not in drop_boxes]
    refs = [r for r in batch.get("refs", []) if r not in drop_boxes]
    if batch["kind"] == "add" and not refs:
        return None, "the dry run refused the position of every card in the batch; open the map in Elements to see what is there"
    return dict(batch, changes=kept, refs=refs, droppedIcons=dropped_icons, deferred=sorted(drop_boxes)), None


# ---------------------------------------------------------------- check

def check(workdir):
    run = Run(workdir)
    style, rules = run.style, layout_rules()
    review = run.path("review", "top.json")
    diagram = read_json(run.path("map.json")).get("diagramId") if run.path("map.json").exists() else None
    if not review.exists():
        refuse(run.dir, [reread(review, diagram)])
    problems = saved_read_problems(review, False, REVIEW_INCLUDE, None, diagram)
    if problems:   # a review read that is not the whole answer writes no layout-check.json
        refuse(run.dir, [reread(review, diagram, REVIEW_INCLUDE, problems)])
    read = unwrap(read_json(review))
    level = str(read.get("levelNumber", "1"))
    keys = run.keys()
    elements = elements_of(read)
    targets, sizes = run.targets(read)
    findings = []

    def find(rule, element, issue, fix):
        row = rules.get(rule, {})
        findings.append({"rule": rule, "severity": row.get("severity", "warn"), "level": level,
                         "element": element, "issue": issue, "fix": fix})

    threshold = int((rules.get("R28") or {}).get("threshold") or 2)
    drawn = {}
    for ref, bx in run.boxes.items():
        el = elements.get(keys.get(ref))
        name = f"'{bx['text']}'"
        if not el or el.get("x") is None:
            find("R28", name, f"The card {name} is not on the level.", "Draw the map again from a new plan.")
            continue
        drawn[ref] = el
        tx, ty = targets[ref]
        if abs(el["x"] - tx) > threshold or abs(el["y"] - ty) > threshold:
            find("R28", f"{name} (key {el['key']})", f"{name} is at {el['x']},{el['y']}; the layout puts it at {tx},{ty}.",
                 "Someone may have moved it in Elements; move it back or draw the map again.")
    # R26: every card or sub-heading sits below its heading, in that heading's column (or row of columns)
    pitch, dx = style["pitch"], style["heading_dx"]
    for ref, bx in run.boxes.items():
        parent = run.boxes.get(bx.get("parent"))
        if not parent or ref not in drawn or parent["ref"] not in drawn:
            continue
        c, p = drawn[ref], drawn[parent["ref"]]
        own = c["x"] + (0 if bx["kind"] == "label" else dx)          # where a heading over this card would sit
        aligned = _is_row_label(run, parent["ref"]) or (own - p["x"]) % pitch == 0
        if c["y"] < p["y"] + p["h"] or not aligned:
            find("R26", f"'{bx['text']}' (key {c['key']})",
                 f"'{bx['text']}' is not under the heading '{parent['text']}', in its column, so it does not read as part of it.",
                 f"Move it into the column under '{parent['text']}'.")
    # R27: nothing overlaps; stacked cards keep the sibling gap
    rects = [(ref, el) for ref, el in drawn.items()]
    for i, (ra, a) in enumerate(rects):
        for rb, b in rects[i + 1:]:
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox > 0 and oy > 0:
                find("R27", f"'{run.boxes[ra]['text']}' and '{run.boxes[rb]['text']}'", "These two overlap.",
                     "Move one of them clear; drawing the map again from a new plan places them apart.")
            elif ox > 0 and -style["sibling_gap"] + threshold < oy <= 0 and a["kind"] == b["kind"] == "activity":
                find("R27", f"'{run.boxes[ra]['text']}' and '{run.boxes[rb]['text']}'",
                     f"These two are {-oy} px apart; stacked cards keep at least {style['sibling_gap']} px.",
                     "Move the lower one down.")
    # R28: column headers in a row share their top
    for row in run.plan["layout"]["rows"]:
        tops = {drawn[s["items"][0]["ref"]]["y"] for s in row["stacks"]
                if s["items"] and "ref" in s["items"][0] and s["items"][0]["ref"] in drawn}
        if len(tops) > 1 and max(tops) - min(tops) > threshold:
            find("R28", f"row of {row['kind']}", "The cards heading this row do not share their top.", "Line them up.")
    extra = [el for key, el in elements.items() if key not in set(keys.get(r) for r in run.boxes)]
    for el in extra:
        find("R28", f"'{el.get('text')}' (key {el['key']})", f"'{el.get('text')}' is on the level but not in the plan.",
             "Someone added it after the drawing; check it belongs.")
    result = {"findings": findings, "checked": sorted(rules), "boxes": len(drawn), "droppedIcons": run.dropped_icons()}
    write_json(run.path("layout-check.json"), result)
    return result


def _is_row_label(run, ref):
    return any(row.get("label") == ref for row in run.plan["layout"]["rows"])


# ---------------------------------------------------------------- main

def print_summary(the_plan, workdir):
    boxes = the_plan["boxes"]
    caps = [bx for bx in boxes if bx["kind"] == "capability"]
    lines = sum(len(bx.get("attributes", [])) for bx in boxes)
    changes = sum(len(bx["changes"]) for bx in boxes)
    width = max(bx["x"] + bx["w"] for bx in boxes)
    height = max(bx["y"] + bx["h"] for bx in boxes)
    headings = sum(1 for bx in boxes if bx["kind"] == "label" and bx.get("modelId"))
    print(f"PLAN {len(caps)} capability cards, {headings} capability headings, {lines} list lines, "
          f"{sum(1 for bx in boxes if bx['kind'] == 'driver')} driver cards, {sum(1 for bx in boxes if bx['kind'] == 'swatch')} "
          f"legend swatches, {sum(1 for bx in boxes if bx.get('role') == 'section')} section headings; {changes} changes; "
          f"about {width} x {height} px")
    for warning in the_plan["warnings"]:
        print(f"WARN {warning}")
    for item in the_plan["gaps"]:
        print(f"{'GAP (model)' if item.get('fromModel') else 'GAP'} {item['note']}")
    print(f"WROTE {Path(workdir) / 'plan.json'} and {Path(workdir) / 'preview.svg'}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Lay out and draw a capability map.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("model")
    p_plan.add_argument("--workdir", required=True)
    p_plan.add_argument("--scale", default="assessment")
    p_plan.add_argument("--children-as", choices=["boxes", "list"], default="boxes")
    p_plan.add_argument("--no-drivers", action="store_true")
    p_plan.add_argument("--no-legend", action="store_true")
    p_plan.add_argument("--skip", default="")
    p_plan.add_argument("--name")
    sub.add_parser("next").add_argument("workdir")
    sub.add_parser("check").add_argument("workdir")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            skip = {s.strip() for s in args.skip.split(",") if s.strip()}
            unknown = skip - set(ATTACHMENT_KINDS)
            if unknown:
                raise SetupError(f"--skip takes {', '.join(ATTACHMENT_KINDS)}; not {', '.join(sorted(unknown))}")
            workdir = Path(args.workdir)
            if (workdir / "map.json").exists():
                raise PlanError(f"{workdir} already holds a map this run created; plan into a new folder")
            gate = validate.gate(args.model, "capability")
            if gate:
                return gate
            the_plan = plan(scope_model(read_json(args.model), args.model, args.workdir), args.scale, args.children_as, not args.no_drivers,
                            not args.no_legend, skip, args.name)
            the_plan["model"] = str(Path(args.model).resolve())
            write_json(workdir / "plan.json", the_plan)
            (workdir / "preview.svg").write_text(preview_svg(the_plan), encoding="utf-8")
            print_summary(the_plan, workdir)
            return 0
        if args.command == "next":
            print(json.dumps(next_step(args.workdir), indent=2, ensure_ascii=False))
            return 0
        result = check(args.workdir)
        for f in result["findings"]:
            print(f"{f['severity'].upper()} {f['rule']} {f['element']}: {f['issue']}")
        print(f"CHECKED {result['boxes']} boxes against {', '.join(result['checked'])}: {len(result['findings'])} finding(s)")
        return 0
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except TrimmedReads as exc:
        for line in exc.lines:
            print(f"ERROR {line}", file=sys.stderr)
        return 1
    except PlanError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
