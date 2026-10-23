#!/usr/bin/env python3
"""Lay out a business-architecture model as an Elements interaction flow, step through writing it with
manage_diagram, and check the drawn result.

Usage:
  python3 layout_interaction.py plan MODEL.json --workdir DIR [--skip KINDS] [--create-resources] [--allow-custom-icons]
                                [--drop-icons NAMES]
  python3 layout_interaction.py next DIR
  python3 layout_interaction.py check DIR

What is drawn where:
  - A model with one automation and no interactions draws that automation's logic on the top level:
    one card per step, the loop bodies and other drill-downs as child levels.
  - Otherwise the top level is the chain: one card per automation (header icon from
    data/automation-types.csv), plus the entities, systems and roles the interactions touch, joined by the
    interactions. Each automation with steps gets a child level with its logic. The chain lines into an
    automation's card come into its Start step; each chain line out leaves the step that causes it
    (the interaction's fromStep, or the top-level card whose drill-down holds it; else the last step of the main path).

plan   Places the cards with the process-map engine (scripts/layout_process.py: the same main path, the
       same line sides from data/line-sides.csv), sizes them as the server does (data/style-interaction.csv),
       and writes DIR/plan.json with the manage_diagram batches in the order to send them: cards with their
       header icon, attributes, footer and attachments; then the lines; then the child levels.
next   Prints the one thing to do next, exactly as layout_process.py next does (create the map, the preflight
       dry run, read a child level, send a batch, the review reads, done).
check  Checks the review reads against the layout rubric rows (R13-R17) and writes DIR/layout-check.json.

Exit 0: done. Exit 1: the model, the plan or a saved file has a problem the output describes.
Exit 2: setup problem (a data file or the command line). Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attachment_scope import scope_model
import validate  # noqa: E402  (the drawing gate: no plan from a model that fails validation)
import layout_engine as engine  # noqa: E402  (the shared layout engine: write loop, geometry, data files, checks)

PLUGIN = engine.PLUGIN
ELEMENTS_PATH = PLUGIN / "data" / "automation-elements.csv"
AUTOMATION_TYPES_PATH = PLUGIN / "data" / "automation-types.csv"
DIAGRAM_TYPE = "interaction-flow"
START, END, TOP = engine.START, engine.END, engine.TOP
GENERIC_END_LABELS = {"", "end", "done"}


# ---------------------------------------------------------------- cards

def load_tables():
    elements = {row["element"]: row for row in engine.read_csv(ELEMENTS_PATH)}
    types = {row["type"]: row for row in engine.read_csv(AUTOMATION_TYPES_PATH)}
    if not elements or not types:
        raise engine.SetupError("data/automation-elements.csv or data/automation-types.csv is empty")
    return elements, types


def cut(text, limit):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    stop = max(text.rfind(". ", 0, limit), text.rfind("; ", 0, limit))
    if stop > limit // 2:
        return text[:stop + 1]
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def card_attributes(items, style):
    limit, chars = style["max_attributes_shown"], style["attribute_max_chars"]
    out = []
    for item in items or []:
        title = " ".join(item.get("title", "").split())
        description = item.get("description", "")
        if len(title) > chars:
            description = (title + (". " + description if description else ""))
            title = title[:chars - 1].rstrip() + "…"
        entry = {"title": title}
        if description:
            entry["description"] = description[:400]
        out.append(entry)
    if len(out) > limit:
        rest = out[limit - 1:]
        out = out[:limit - 1] + [{"title": f"+{len(rest)} more", "description": "; ".join(i["title"] for i in rest)[:400]}]
    return out


def card_height(card, style):
    """The height the server gives a card: it counts attributes and a footer, not wrapped lines."""
    height = style["card_height_base"] + style["attribute_row_height"] * len(card["attributes"])
    if card.get("footer"):
        height += style["footer_height"]
    return max(style["card_height_min"], height)


# ---------------------------------------------------------------- the levels to draw

class CardLevel(engine.Level):
    """A level of cards: the process-map placement and line rules, with card headers and card heights."""

    def __init__(self, pseudo, parent, style, skip, warnings, cards):
        self.cards = cards
        super().__init__(pseudo, parent, DIAGRAM_TYPE, style, skip, False, warnings)

    # A loop body's line in reads "For each item" and its lines out "Next item": they pair with the Loop card's
    # lines by position, not by label.
    pair_boundary_by_order = True

    def build(self, parent_boundary):
        # When every line of the logic on a level is inferred (a logic rebuilt from Elements), " (inferred)" on
        # each label says nothing a single note does not: the level's first card carries that note instead.
        own = [f for _, f in self.flows if not f.get("chain")]  # chain lines continued here are the chain's, not the logic's
        self.all_inferred = bool(own) and all(f.get("inferred") for f in own)
        self.mark_inferred_lines = not self.all_inferred
        level = super().build(parent_boundary)
        if level is not None:
            level["linesInferred"] = self.all_inferred
        return level

    def where(self):
        if self.parent is None:
            return "top level"
        return f"level under '{self.by_id_any(self.parent)['name']}'"

    def resources(self, act):
        header = self.cards[act["id"]].get("header")
        return [dict(header, role="header")] if header else []

    def box_height(self, act, resources):
        return card_height(self.cards[act["id"]], self.style)

    def outcome_sides(self, ordered, loops):
        """As on process maps, except that a fault path leaves the bottom when it is free (the top is where a
        wrapped main path runs back, and a failure reads naturally below the step that failed), and so does any
        outcome of a card that a line loops back into, since that line enters the top."""
        sides, groups = super().outcome_sides(ordered, loops)
        # A line looping back enters its target's top, so the target's own outcomes keep off the top.
        loop_targets = {self.flow_by_index[i]["to"] for i in loops if i in self.flow_by_index}
        for node, node_groups in groups.items():
            used = {sides[i] for g in node_groups for i in g["flows"]}
            for group in node_groups:
                faults = all(self.flow_by_index[i].get("kind") == "fault" for i in group["flows"])
                if (faults or node in loop_targets) and sides[group["flows"][0]] == "top" and "bottom" not in used:
                    for index in group["flows"]:
                        sides[index] = "bottom"
                    used.discard("top")
                    used.add("bottom")
        return sides, groups

    def shared_points(self, lines, boxes):
        """The process-map warnings, less 'all must arrive': lines meeting at a card mean that in UPN, not here."""
        before = len(self.warn)
        super().shared_points(lines, boxes)
        self.warn[before:] = [w for w in self.warn[before:] if "all must arrive" not in w]


class Builder:
    """Turns the model into the pseudo model the layout engine reads (activities and flows) plus card specs."""

    def __init__(self, model, style, warnings, drop_icons=frozenset()):
        self.model, self.style, self.warn = model, style, warnings
        self.drop_icons, self.dropped = drop_icons, {}
        self.elements, self.types = load_tables()
        self.automations = {a["id"]: a for a in model.get("automations", [])}
        self.steps = {s["id"]: s for s in model.get("steps", [])}
        self.items = {}
        for section in ("entities", "systems", "roles"):
            for item in model.get(section, []):
                self.items[item["id"]] = (section, item)
        self.chain = bool(model.get("interactions")) or len(self.automations) > 1
        self.activities, self.flows, self.cards, self.sources = [], [], {}, {}

    # ---- cards

    def header(self, name, kind):
        """The card's header icon, or None when the user agreed to draw this run without it (--drop-icons)."""
        if not name:
            return None
        if engine.norm(name) in self.drop_icons:
            self.dropped[name] = self.dropped.get(name, 0) + 1
            return None
        return {"name": name, "type": kind}

    def automation_card(self, auto):
        row = self.types.get(auto.get("type"), self.types.get("other"))
        header = self.header(row.get("chain_resource"), row.get("chain_resource_type")) if row else None
        return {"header": header, "attributes": card_attributes(auto.get("attributes"), self.style),
                "footer": cut(auto.get("summary", ""), self.style["footer_max_chars"])}

    def step_card(self, step):
        row = self.elements.get(step["element"])
        header = self.header(row.get("resource"), row.get("resource_type")) if row else None
        return {"header": header, "attributes": card_attributes(step.get("attributes"), self.style),
                "footer": cut(step.get("summary", ""), self.style["footer_max_chars"])}

    def other_card(self, section, item):
        card = {"header": None, "attributes": [], "footer": cut(item.get("description", ""), self.style["footer_max_chars"])}
        if section == "entities":
            card["fill"], card["border"] = self.style["entity_fill"], self.style["entity_border"]
            what = "Platform event" if (item.get("apiName") or "").endswith("__e") else "Object"
            card["attributes"] = card_attributes([{"title": f"{what}: {item.get('apiName') or item['name']}"}], self.style)
        return card

    # ---- the pseudo model

    def add(self, ident, name, parent, card, source):
        activity = {"id": ident, "name": name}
        if parent is not None:
            activity["parent"] = parent
        self.activities.append(activity)
        self.cards[ident] = card
        self.sources[ident] = source

    def build(self):
        if self.chain:
            self.chain_level()
            for auto in self.automations.values():
                self.logic_levels(auto["id"], under=auto["id"])
        else:
            auto = next(iter(self.automations.values()), None)
            if auto is None:
                raise engine.PlanError("the model has no automation to draw")
            self.logic_levels(auto["id"], under=None)
            # With no chain card, the automation's own links (its metadata, above all) go on its Start card.
            start = next((s for s in self.model.get("steps", []) if s["automation"] == auto["id"] and s["element"] == "start" and "parent" not in s), None)
            if start is not None and auto.get("attachments"):
                source = dict(self.sources[start["id"]])
                source["attachments"] = list(auto["attachments"]) + list(start.get("attachments", []))
                self.sources[start["id"]] = source
        pseudo = {"meta": self.model["meta"], "activities": self.activities, "flows": self.flows}
        return pseudo

    def chain_level(self):
        order = []
        for item in self.model.get("interactions", []):
            for end in (item["from"], item["to"]):
                if end not in (START, END) and end not in order:
                    order.append(end)
        order += [a for a in self.automations if a not in order]
        for ident in order:
            if ident in self.automations:
                auto = self.automations[ident]
                self.add(ident, auto["name"], None, self.automation_card(auto), auto)
            elif ident in self.items:
                section, item = self.items[ident]
                self.add(ident, item["name"], None, self.other_card(section, item), item)
        for index, item in enumerate(self.model.get("interactions", [])):
            flow = {"id": item.get("id", f"i{index}"), "from": item["from"], "to": item["to"], "label": chain_label(item)}
            if item.get("inferred"):
                flow["inferred"] = True
            self.flows.append(flow)

    def logic_levels(self, automation_id, under):
        mine = [s for s in self.model.get("steps", []) if s["automation"] == automation_id]
        if not mine:
            return
        for step in mine:
            parent = step.get("parent", under)
            self.add(step["id"], step["name"], parent, self.step_card(step), step)
        level_of = {s["id"]: s.get("parent") for s in mine}
        own = [c for c in self.model.get("connectors", []) if level_of.get(c["from"], level_of.get(c["to"], "?")) is None
               and (c["from"] in level_of or c["to"] in level_of)]
        others = [c for c in self.model.get("connectors", []) if c not in own and (c["from"] in level_of or c["to"] in level_of)]
        if under is not None:
            own = self.wire_boundary(automation_id, own, mine)
            others = others + self.nested_outputs(automation_id, mine)
        for conn in own + others:
            flow = {"from": conn["from"], "to": conn["to"], "label": conn.get("label", ""), "kind": conn.get("kind", "next")}
            if conn.get("id"):
                flow["id"] = conn["id"]
            if conn.get("inferred"):
                flow["inferred"] = True
            if conn.get("chain"):
                flow["chain"] = True
            self.flows.append(flow)

    def wire_boundary(self, automation_id, own, mine):
        """The chain lines into and out of the automation's card continue on its logic level."""
        ins = [i for i in self.model.get("interactions", []) if i["to"] == automation_id]
        outs = [i for i in self.model.get("interactions", []) if i["from"] == automation_id]
        top_ids = {s["id"] for s in mine if "parent" not in s}
        if ins:
            starts = [c for c in own if c["from"] == START]
            first = starts[0]["to"] if starts else next((s["id"] for s in mine if s["element"] == "start" and s["id"] in top_ids), None)
            if first is None:
                first = next(iter(top_ids))
            own = [c for c in own if c["from"] != START]
            labels = []
            for item in ins:
                label = chain_label(item)
                if engine.norm(label) not in [engine.norm(x[0]) for x in labels]:
                    labels.append((label, item.get("inferred")))
            own = [dict({"from": START, "to": first, "label": label, "chain": True}, **({"inferred": True} if inferred else {})) for label, inferred in labels] + own
        if outs:
            last = self.last_step(own, top_ids)
            used = set()
            for item in outs:
                step = self.top_ancestor(item.get("fromStep"), top_ids)
                if step is None:
                    step = last
                    if item.get("fromStep"):
                        self.warn.append(f"chain line {json.dumps(chain_label(item))}: fromStep '{item['fromStep']}' is not a step of '{automation_id}'; it leaves '{self.steps[step]['name']}' instead")
                    else:
                        self.warn.append(f"chain line {json.dumps(chain_label(item))} out of '{self.automations[automation_id]['name']}' has no fromStep; it leaves the last step, '{self.steps[step]['name']}'")
                used.add(step)
                conn = {"from": step, "to": END, "label": chain_label(item), "chain": True}
                if item.get("inferred"):
                    conn["inferred"] = True
                own.append(conn)
            # A plain end from a step a chain line now leaves would be a second, unlabelled way out.
            own = [c for c in own if not (c["to"] == END and c["from"] in used and engine.norm(c.get("label")) in GENERIC_END_LABELS
                                          and not any(o.get("fromStep") == c["from"] and engine.norm(chain_label(o)) == engine.norm(c.get("label")) for o in outs))]
        return own

    def nested_outputs(self, automation_id, mine):
        """A chain line out of a step inside a drill-down leaves the top-level card that holds it; on each level
        below, it continues from the card holding the step (the step itself at the bottom) to an end line with the
        same label, so the drill-down shows where it really leaves."""
        top_ids = {s["id"] for s in mine if "parent" not in s}
        children = defaultdict(list)
        for s in mine:
            if s.get("parent"):
                children[s["parent"]].append(s["id"])
        connectors = self.model.get("connectors", [])
        extra = []
        for item in self.model.get("interactions", []):
            step = item.get("fromStep")
            if item["from"] != automation_id or step not in self.steps:
                continue
            # A line said to leave a card that has a drill-down leaves, inside it, its last step.
            while children.get(step):
                inner = set(children[step])
                step = self.last_step([c for c in connectors if c["from"] in inner or c["to"] in inner], inner)
                self.warn.append(f"chain line {json.dumps(chain_label(item))} leaves '{self.steps[item['fromStep']]['name']}', which has a drill-down; "
                                 f"inside it, it leaves the last step, '{self.steps[step]['name']}' (name the step itself as fromStep to change that)")
            if step in top_ids:
                continue
            seen = set()
            while step in self.steps and step not in top_ids and step not in seen:
                seen.add(step)
                conn = {"from": step, "to": END, "label": chain_label(item), "chain": True}
                if item.get("inferred"):
                    conn["inferred"] = True
                extra.append(conn)
                step = self.steps[step].get("parent")
        return extra

    def top_ancestor(self, step_id, top_ids):
        """The card on the top logic level a step sits under: itself, or the Loop card whose body holds it."""
        seen = set()
        while step_id in self.steps and step_id not in top_ids and step_id not in seen:
            seen.add(step_id)
            step_id = self.steps[step_id].get("parent")
        return step_id if step_id in top_ids else None

    def last_step(self, connectors, ids):
        out = defaultdict(list)
        for conn in connectors:
            out[conn["from"]].append(conn["to"])
        node = next((dst for dst in out[START] if dst in ids), None) or next(iter(ids))
        seen = []
        while node in ids and node not in seen:
            seen.append(node)
            node = next((dst for dst in out[node] if dst not in seen), END)
        return seen[-1]


INFERRED_LEVEL_NOTE = ("Every line between the cards on this level is inferred: the order and the branches were worked out "
                       "from what Elements' dependency graph names, not read from the automation's definition. Each "
                       "card's own Inferred note gives its evidence.")


def chain_label(item):
    label = item.get("label", "")
    if item.get("order"):
        return f"{item['order']}. {label}".strip() if label else f"{item['order']}."
    return label


# ---------------------------------------------------------------- plan

def centre(level, style):
    """Move a level's cards so their middle is the middle of a blank canvas.

    manage_diagram accepts positions only inside the canvas: 2000 x 1200 px from (0, 0) on a blank level, then the
    content's bounding box plus half its size on each side. A layout anchored at the top left can end up with a
    tall card just past the bottom edge that no later write ever brings inside; centred, the canvas grows evenly
    around the cards already written, so every card fits in one or two writes."""
    boxes = level["boxes"]
    if not boxes:
        return
    left = min(b["x"] for b in boxes)
    right = max(b["x"] + b["w"] for b in boxes)
    top = min(b["y"] for b in boxes)
    bottom = max(b["y"] + b["h"] for b in boxes)
    dx = int(round(style["canvas_blank_width"] / 2 - (left + right) / 2))
    dy = int(round(style["canvas_blank_height"] / 2 - (top + bottom) / 2))
    for box in boxes:
        box["x"] += dx
        box["y"] += dy


def write_passes(boxes, style):
    """The cards each write can place, as the canvas grows around what is written; None when some never fit."""
    pending = list(boxes)
    canvas = (0, 0, style["canvas_blank_width"], style["canvas_blank_height"])
    placed, passes = [], []
    while pending:
        fits = [b for b in pending if engine.inside(b, canvas)]
        if not fits:
            return None
        passes.append(fits)
        placed += fits
        pending = [b for b in pending if b not in fits]
        canvas = engine.canvas_after(placed, style)
    return passes


def fit(level, style):
    """Place a level on the blank canvas so every card can be written: centred first; a level taller or wider
    than the blank canvas may need one edge anchored instead, so the first write spans most of it and the
    canvas then grows over the rest. Picks the placement that needs the fewest writes."""
    boxes = level["boxes"]
    if not boxes:
        return
    centre(level, style)
    left = min(b["x"] for b in boxes)
    right = max(b["x"] + b["w"] for b in boxes)
    top = min(b["y"] for b in boxes)
    bottom = max(b["y"] + b["h"] for b in boxes)
    margin = 40
    width, height = style["canvas_blank_width"], style["canvas_blank_height"]
    xs = [0, margin - left, width - margin - right]
    ys = [0, margin - top, height - margin - bottom]
    best = None
    for dy in ys:
        for dx in xs:
            moved = [dict(b, x=b["x"] + dx, y=b["y"] + dy) for b in boxes]
            passes = write_passes(moved, style)
            if passes is not None and (best is None or len(passes) < best[0]):
                best = (len(passes), dx, dy)
    if best is None:
        raise engine.PlanError(f"{level['slug']}: the cards cannot be placed so that every one fits the canvas; split the level")
    for box in boxes:
        box["x"] += best[1]
        box["y"] += best[2]


def card_batches(level, builder, style, skip):
    passes = write_passes(level["boxes"], style)
    if passes is None:
        raise engine.PlanError(f"{level['slug']}: cards do not fit the canvas")
    batches = []
    for group_boxes in passes:
        groups = []
        for box in group_boxes:
            card = builder.cards[box["id"]]
            change = {"op": "add", "kind": "activity", "ref": box["ref"], "text": box["name"], "position": {"x": box["x"], "y": box["y"]}}
            if card.get("footer"):
                change["footerText"] = card["footer"]
            for key in ("fill", "border"):
                if card.get(key):
                    change[key] = card[key]
            changes = [change]
            for res in box["resources"]:
                changes.append({"op": "add", "kind": "resource", "activity": box["ref"], "name": res["name"], "type": res["type"], "role": "header"})
            for attribute in card["attributes"]:
                item = {"op": "add", "kind": "attribute", "activity": box["ref"], "title": attribute["title"]}
                if attribute.get("description"):
                    item["description"] = attribute["description"]
                changes.append(item)
            changes += engine.attachment_changes(builder.sources[box["id"]], box["ref"], skip)
            groups.append(changes)
        for changes in engine.chunk(groups):
            batches.append({"kind": "boxes", "changes": changes})
    ref_of = {b["id"]: b["ref"] for b in level["boxes"]}
    line_changes = []
    for line in level["lines"]:
        change = {"op": "add", "kind": "line", "ref": line["ref"], "label": line["label"],
                  "from": {"terminator": True} if line["from"] == START else {"activity": ref_of[line["from"]]},
                  "to": {"terminator": True} if line["to"] == END else {"activity": ref_of[line["to"]]}}
        for key in ("fromSide", "toSide"):
            if key in line:
                change[key] = line[key]
        if "boundary" in line:
            free = "from" if line["from"] == START else "to"
            change[free] = None
            change["parentLine"] = {"$parentLine": line["boundary"]}
            line_changes.append([{"op": "remove", "kind": "line", "key": {"$boundary": line["boundary"]}}, change])
        else:
            line_changes.append([change])
    for changes in engine.chunk(line_changes):
        batch = {"kind": "lines", "changes": changes}
        if any(c["op"] == "remove" for c in changes):
            batch["confirm"] = True
        batches.append(batch)
    parents = [b for b in level["boxes"] if any(a.get("parent") == b["id"] for a in builder.activities)]
    if parents:
        batches.append({"kind": "children", "changes": [{"op": "add", "kind": "child", "activity": b["ref"]} for b in parents]})
    return batches, len(passes)


def standard_icons():
    """Every header icon in data/automation-elements.csv and data/automation-types.csv: standard Elements
    resources, which the drawing uses and never adds to the space library."""
    elements, types = load_tables()
    icons = {}
    for row in elements.values():
        icons.setdefault(row["resource"], row["resource_type"])
    for row in types.values():
        if row.get("chain_resource"):
            icons.setdefault(row["chain_resource"], row["chain_resource_type"])
    return [{"name": name, "type": icons[name]} for name in sorted(icons)]


def plan(model, skip=frozenset(), create_resources=False, allow_custom_icons=False, drop_icons=()):
    style = engine.load_style(DIAGRAM_TYPE)
    warnings = []
    drop = {engine.norm(n) for n in drop_icons}
    unknown_drops = sorted(n for n in drop_icons if engine.norm(n) not in {engine.norm(i["name"]) for i in standard_icons()})
    if unknown_drops:
        warnings.append(f"--drop-icons names no header icon in data/automation-elements.csv or data/automation-types.csv: {', '.join(unknown_drops)}")
    builder = Builder(model, style, warnings, drop)
    pseudo = builder.build()
    levels = []

    def visit(parent, boundary):
        level = CardLevel(pseudo, parent, style, skip, warnings, builder.cards).build(boundary)
        if level is None:
            return
        fit(level, style)
        if level.get("linesInferred"):
            first = next((ln["to"] for ln in level["lines"] if ln["from"] == START), level["boxes"][0]["id"])
            source = dict(builder.sources[first])
            source["attachments"] = list(source.get("attachments", [])) + [{"type": "note", "title": "Inferred", "text": INFERRED_LEVEL_NOTE}]
            builder.sources[first] = source
        for box in level["boxes"]:
            card = builder.cards[box["id"]]
            box["header"] = card["header"]["name"] if card.get("header") else None
            box["attributes"] = len(card["attributes"])
            box["footer"] = bool(card.get("footer"))
        level["batches"], level["writes"] = card_batches(level, builder, style, skip)
        levels.append(level)
        for box in level["boxes"]:
            if any(a.get("parent") == box["id"] for a in pseudo["activities"]):
                inputs = [ln for ln in level["lines"] if ln["to"] == box["id"]]
                outputs = [ln for ln in level["lines"] if ln["from"] == box["id"]]
                visit(box["id"], {"inputs": [{"ref": ln["ref"], "label": pseudo["flows"][ln["flowIndex"]].get("label", "")} for ln in inputs],
                                  "outputs": [{"ref": ln["ref"], "label": pseudo["flows"][ln["flowIndex"]].get("label", "")} for ln in outputs]})

    visit(None, None)
    unknown = sorted({s["element"] for s in model.get("steps", []) if s["element"] not in builder.elements})
    if unknown:
        warnings.append(f"no header icon for element(s) {', '.join(unknown)}: not in data/automation-elements.csv")
    tall = [b["name"] for lv in levels for b in lv["boxes"] if b["h"] > 260]
    if tall:
        warnings.append(f"{len(tall)} card(s) are over 260 px tall ({', '.join(tall[:3])}{'...' if len(tall) > 3 else ''}); fewer attributes or a shorter footer would keep rows compact")
    result = {
        "planVersion": 1, "diagramType": DIAGRAM_TYPE, "mapType": engine.map_type(DIAGRAM_TYPE),
        "mapName": map_name(model["meta"]["title"]), "mapDescription": model["meta"].get("description", ""),
        "createResources": create_resources, "mode": "chain" if builder.chain else "logic",
        "standardResources": standard_icons(), "allowCustomIcons": allow_custom_icons,
        "droppedIcons": [{"icon": name, "cards": count} for name, count in sorted(builder.dropped.items())],
        "levels": levels, "preflight": engine.preflight_batches(levels, model), "warnings": warnings, "gaps": model.get("gaps", []),
    }
    result["planId"] = hashlib.sha1(json.dumps(result, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return result


def print_plan_summary(result, workdir):
    names = {}
    for level in result["levels"]:
        for box in level["boxes"]:
            names[box["id"]] = box["name"]
    print(f"Plan written to {Path(workdir) / 'plan.json'}: {result['mode']} map, {len(result['levels'])} level(s).")
    for level in result["levels"]:
        rows = {(b["band"], b["row"]) for b in level["boxes"]}
        where = "top" if level["slug"] == TOP else f"under '{names.get(level['slug'], level['slug'])}'"
        print(f"  {where}: {len(level['boxes'])} cards in {len(rows)} row(s), {len(level['lines'])} lines, "
              f"{len(level['batches'])} batch(es), {level['writes']} card write(s)")
    for dropped in result.get("droppedIcons", []):
        print(f"DROPPED header icon {dropped['icon']} on {dropped['cards']} card(s): drawn without it, as the user agreed")
    for warning in result["warnings"]:
        print(f"WARN {warning}")
    for gap in result["gaps"]:
        print(f"GAP {gap.get('about', 'model')}: {gap['note']}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Lay out and write an interaction flow.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("model")
    p_plan.add_argument("--workdir", required=True)
    p_plan.add_argument("--skip", default="", help="attachment kinds to leave out, comma separated")
    p_plan.add_argument("--create-resources", action="store_true", help="add resources missing from the space library (only once the user has agreed); never the standard header icons")
    p_plan.add_argument("--drop-icons", default="", help="header icons to draw without, comma separated (only once the user has agreed to draw without a standard icon the space lacks)")
    p_plan.add_argument("--allow-custom-icons", action="store_true", help="draw even where the space library holds a custom resource named like a standard header icon (only once the user has agreed)")
    p_next = sub.add_parser("next")
    p_next.add_argument("workdir")
    p_check = sub.add_parser("check")
    p_check.add_argument("workdir")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            skip = {s.strip() for s in args.skip.split(",") if s.strip()}
            unknown = skip - set(engine.ATTACHMENT_KINDS)
            if unknown:
                print(f"SETUP --skip takes {', '.join(engine.ATTACHMENT_KINDS)}; not {', '.join(sorted(unknown))}", file=sys.stderr)
                return 2
            gate = validate.gate(args.model, "interaction-flow")
            if gate:
                return gate
            model = scope_model(engine.read_json(args.model), args.model, args.workdir)
            if not model.get("automations"):
                print("ERROR the model has no automations to draw")
                return 1
            drop = [n.strip() for n in args.drop_icons.split(",") if n.strip()]
            result = plan(model, skip, args.create_resources, args.allow_custom_icons, drop)
            workdir = Path(args.workdir)
            engine.prepare_workdir(workdir, result)
            (workdir / "plan.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print_plan_summary(result, workdir)
            return 0
        if args.command == "next":
            step = engine.next_step(args.workdir, Path(__file__).name)
            print(json.dumps(step, indent=2, ensure_ascii=False))
            return 0
        result = engine.check(args.workdir)
        for f in result["findings"]:
            print(f"{f['severity'].upper()} {f['rule']} level {f['level']}: {f['issue']}")
        print(f"{len(result['findings'])} finding(s) on {len(result['checked'])} level(s); written to {Path(args.workdir) / 'layout-check.json'}")
        return 0
    except engine.SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except (engine.PlanError, OSError, ValueError, KeyError, StopIteration) as exc:
        print(f"ERROR {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
