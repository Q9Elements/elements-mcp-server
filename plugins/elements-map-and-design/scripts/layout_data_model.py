#!/usr/bin/env python3
"""Lay out a business-architecture model as an Elements data model, write it with manage_diagram, amend
an existing data model in place, and check the drawn result.

Usage:
  python3 layout_data_model.py plan MODEL.json --workdir DIR [--max-fields N] [--no-api-names] [--no-legend]
                                [--label-fields] [--skip KINDS] [--name TEXT]
  python3 layout_data_model.py from-diagram READ.json --out MODEL.json
  python3 layout_data_model.py amend MODEL.json --read READ.json --workdir DIR [--allow-remove] [--relayout]
                                [--max-fields N] [--no-api-names] [--label-fields] [--skip KINDS]
  python3 layout_data_model.py next DIR
  python3 layout_data_model.py check DIR

plan          Works out every card and line of a new data model: one card per entity (its key fields as
              attributes, its API name as the footer, coloured by kind from data/entity-kinds.csv), one line
              per relationship drawn from the "one" end to the "many" end, with the line ends from
              data/relationship-ends.csv (or the relationship's own fromEnd and toEnd) as Elements shapes
              from data/er-line-ends.csv. Parents sit above their children; a card with many childless
              children stacks them in columns beside it. Writes DIR/plan.json with the manage_diagram batches
              and DIR/preview.svg, and prints a summary with any warnings. Refuses a model that fails validate.py for its diagram type.
from-diagram  Turns a get_diagram read of an existing data model into a model file: cards become entities,
              attributes become fields, lines become relationships with their line ends. Edit that file
              (add an entity, change a line end) and pass it to amend.
amend         Compares a model with the read of an existing data model and plans the manage_diagram
              changes that make the diagram match it: new cards placed next to the card they relate to,
              fields and line ends updated, new lines added. Removals (cards, lines, fields the model no
              longer has) are listed but only planned with --allow-remove. --relayout also moves every card
              to a fresh layout and re-routes every line. Writes DIR/map.json and DIR/plan.json.
next          Prints, as JSON, the one thing to do next: create the map (plan only), send a batch, read the
              level for review, or nothing (done). Run it again after saving each result where it says.
check         Checks DIR/review/top.json against the plan and the rubric rows checked by layout-check for
              data models (R32-R34) and writes DIR/layout-check.json in the diagram-reviewer's finding format.

Why manage_diagram only: it is the one write path that also amends a diagram later. It makes every card
200 px wide and sizes its height from the attributes and footer (data/style-data-model.csv), joins lines at
the middle of a side, and accepts positions only inside the canvas, which grows as cards are written; the
plan splits the cards into as many writes as the canvas needs.

Exit 0: done. Exit 1: the model, the plan or a saved file has a problem the output describes.
Exit 2: setup problem (a data file or the command line). Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name

import argparse
import hashlib
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attachment_scope import scope_model
import validate  # noqa: E402  (the drawing gate: no plan from a model that fails validation)
from layout_engine import (  # noqa: E402  (the shared layout engine)
    PLUGIN, PlanError, STEP, SetupError, TOP, attachment_changes,
    choose_sides, chunk, cut, dedupe, fit_blank, free_spot,
    guard_workdir, id_map, level_results, make_ref, moves_in_passes, next_step,
    norm, overlaps, parse_skip, plan_id, read_csv, read_json, refuse_partial_reads,
    route, route_crossings, side_point, simulate_attributes, slug, unwrap,
    write_passes,
)

STYLE_PATH = PLUGIN / "data" / "style-data-model.csv"
ENDS_PATH = PLUGIN / "data" / "er-line-ends.csv"
DEFAULTS_PATH = PLUGIN / "data" / "relationship-ends.csv"
KINDS_PATH = PLUGIN / "data" / "entity-kinds.csv"
RUBRIC_PATH = PLUGIN / "data" / "readability-rubric.csv"
DIAGRAM_TYPE = "data-model"
MAP_TYPE = "data_model"
SUBTYPE = "data_model"
TOLERANCE = 2
LEGEND_NAME = "Key"
LEGEND_FILL, LEGEND_BORDER = "#ffffff", "#c9c9c9"

SELF_LOOPS = [("top", "right"), ("bottom", "left"), ("left", "top"), ("right", "bottom")]  # one corner per loop
END_SYMBOL = {"zero-or-one": "o|", "exactly-one": "||", "one": "|", "zero-or-many": "o<",
              "one-or-many": "|<", "many": "<", "none": "-"}


# ---------------------------------------------------------------- data files

def number(value):
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def load_style():
    style = {row["setting"]: number(row["value"]) for row in read_csv(STYLE_PATH)}
    needed = ["card_width", "card_height_min", "card_height_base", "attribute_row_height", "footer_height",
              "editor_growth_allowance", "col_gap", "row_gap", "tree_gap", "comb_gap", "comb_stack_gap",
              "max_row_children", "max_comb_children", "max_width", "band_gap", "max_entities", "max_fields",
              "field_max_chars", "label_max_chars", "primary_marker", "show_api_names", "legend", "legend_gap",
              "canvas_blank_width", "canvas_blank_height", "canvas_margin_factor"]
    missing = [n for n in needed if n not in style]
    if missing:
        raise SetupError(f"{STYLE_PATH.name}: no value for {', '.join(missing)}")
    return style


def load_ends():
    ends = {row["end"]: row for row in read_csv(ENDS_PATH)}
    if not ends:
        raise SetupError(f"{ENDS_PATH.name} is empty")
    return ends


def load_defaults():
    table = {(row["cardinality"], row.get("kind", "")): row for row in read_csv(DEFAULTS_PATH)}
    if not table:
        raise SetupError(f"{DEFAULTS_PATH.name} is empty")
    return table


def default_ends(table, cardinality, kind):
    row = table.get((cardinality, kind or "")) or table.get((cardinality, ""))
    if not row:
        raise SetupError(f"{DEFAULTS_PATH.name}: no row for cardinality {cardinality}")
    return row["one_end"], row["other_end"]


def load_kinds():
    kinds = {row.get("kind", ""): row for row in read_csv(KINDS_PATH)}
    if "" not in kinds:
        raise SetupError(f"{KINDS_PATH.name}: no row with an empty kind (the colours for an entity with no kind)")
    return kinds


def yes(value):
    return str(value).strip().lower() in ("yes", "true", "1")


# ---------------------------------------------------------------- cards and lines from the model


def card_height(attributes, footer, style):
    height = style["card_height_base"] + style["attribute_row_height"] * len(attributes)
    if footer:
        height += style["footer_height"]
    return max(style["card_height_min"], height)


def field_rank(field):
    """The order fields are shown in: the identifier, required fields, relationship fields, the rest."""
    if field.get("key") == "primary":
        return 0
    if field.get("required") and field.get("key") != "foreign":
        return 1
    if field.get("key") == "foreign":
        return 2
    return 3


def attribute_of(field, style):
    marker = f"{style['primary_marker']} " if field.get("key") == "primary" else ""
    title = marker + " ".join(field["name"].split())
    parts = [p for p in (field.get("type"), "required" if field.get("required") else "",
                         "inferred" if field.get("inferred") else "") if p]
    description = ", ".join(parts)
    limit = int(style["field_max_chars"])
    if len(title) > limit:
        description = title + (". " + description if description else "")
        title = title[:limit - 1].rstrip() + "…"
    out = {"title": title}
    if description:
        out["description"] = description[:400]
    return out


def build_cards(model, style, kinds, max_fields, show_api, warnings):
    cards = {}
    for ent in model.get("entities", []):
        fields = sorted(enumerate(ent.get("fields", [])), key=lambda pair: (field_rank(pair[1]), pair[0]))
        shown = [f for _, f in fields[:max_fields]]
        hidden = [f for _, f in fields[max_fields:]]
        if hidden:
            warnings.append(f"'{ent['name']}' shows {len(shown)} of its {len(fields)} fields; not shown: "
                            + ", ".join(f["name"] for f in hidden))
        attributes = [attribute_of(f, style) for f in shown]
        footer = ""
        if show_api and ent.get("apiName") and norm(ent["apiName"]) != norm(ent["name"]):
            footer = ent["apiName"]
        colours = kinds.get(ent.get("kind", ""), kinds[""])
        if len(ent["name"]) > 60:
            warnings.append(f"'{ent['name']}' is a long name; it wraps onto several lines and the editor may make the card taller")
        cards[ent["id"]] = {"id": ent["id"], "name": ent["name"], "attributes": attributes, "footer": footer,
                            "fill": colours["fill"], "border": colours["border"], "kind": ent.get("kind", ""),
                            "w": style["card_width"], "h": card_height(attributes, footer, style)}
    return cards


def build_edges(model, ends, defaults, label_fields, style, warnings):
    """One line per relationship, drawn from the 'one' end (start) to the 'many' end (end)."""
    edges = []
    for index, rel in enumerate(model.get("relationships", [])):
        cardinality = rel["cardinality"]
        a, b, a_end, b_end = rel["from"], rel["to"], rel.get("fromEnd"), rel.get("toEnd")
        if cardinality == "many-to-one":
            a, b, a_end, b_end, cardinality = b, a, b_end, a_end, "one-to-many"
        one_end, other_end = default_ends(defaults, cardinality, rel.get("kind"))
        parent_end, child_end = a_end or one_end, b_end or other_end
        for end in (parent_end, child_end):
            if end not in ends:
                raise SetupError(f"{ENDS_PATH.name}: no row for the line end '{end}'")
        label = rel.get("label", "")
        if not label and label_fields and rel.get("field"):
            label = rel["field"].split(".")[-1]
        edges.append({"id": rel.get("id") or f"rel-{index + 1}", "index": index, "parent": a, "child": b,
                      "parentEnd": parent_end, "childEnd": child_end,
                      "startShape": ends[parent_end]["shape"], "endShape": ends[child_end]["shape"],
                      "kind": rel.get("kind", ""), "cardinality": cardinality, "label": label,
                      "field": rel.get("field", ""), "inferred": bool(rel.get("inferred"))})
    pairs = defaultdict(list)
    for edge in edges:
        pairs[frozenset((edge["parent"], edge["child"]))].append(edge)
    for group in pairs.values():
        if len(group) > 1:
            for edge in group:
                if not edge["label"] and edge["field"]:
                    edge["label"] = edge["field"].split(".")[-1]
            if any(not e["label"] for e in group):
                warnings.append(f"{len(group)} relationships join the same two entities ({', '.join(e['id'] for e in group)}) "
                                "and not all have a label or field; give each a label so readers can tell the lines apart")
    for edge in edges:
        label = cut(edge["label"], int(style["label_max_chars"]))
        if edge["inferred"]:
            label = (label + " (inferred)").strip()
        edge["label"] = label
    return edges


# ---------------------------------------------------------------- layout

class Layout:
    """Parents above children, a tree per group of related entities, groups side by side in bands.

    Every entity is placed under one parent: its master-detail parent when it has one, otherwise the parent
    nearest the top (the hub), so an entity related to a hub and to one of the hub's children sits next to
    that child, joined by a short line across, rather than a row further down. A card with more than max_row_children children keeps the ones with children of
    their own in a row under it and stacks the childless ones in columns beside it (right first, then left),
    joined to its side. Other relationships are drawn as lines between wherever the cards end up."""

    def __init__(self, order, sizes, edges, style, warnings, names=None):
        self.order = list(order)
        self.index = {e: i for i, e in enumerate(self.order)}
        self.sizes = sizes
        self.edges = [e for e in edges if e["parent"] in self.index and e["child"] in self.index]
        self.style = style
        self.warn = warnings
        self.w = style["card_width"]
        self.names = names or {}
        self.pull = {}

    # -- structure
    def structure(self):
        out = defaultdict(list)
        for edge in self.edges:
            if edge["parent"] != edge["child"]:
                out[edge["parent"]].append(edge)
        incoming = defaultdict(int)
        for edge in self.edges:
            if edge["parent"] != edge["child"]:
                incoming[edge["child"]] += 1
        state, back = {}, set()
        starts = [n for n in self.order if not incoming[n]] + [n for n in self.order if incoming[n]]
        for start in starts:
            if state.get(start):
                continue
            stack = [(start, iter(out[start]))]
            state[start] = 1
            while stack:
                node, it = stack[-1]
                edge = next(it, None)
                if edge is None:
                    state[node] = 2
                    stack.pop()
                    continue
                child = edge["child"]
                if state.get(child) == 1:
                    back.add(edge["index"])
                elif not state.get(child):
                    state[child] = 1
                    stack.append((child, iter(out[child])))
        dag = [e for e in self.edges if e["parent"] != e["child"] and e["index"] not in back]
        parents = defaultdict(list)
        for edge in dag:
            parents[edge["child"]].append(edge)
        rank = {}

        def rank_of(node, seen=()):
            if node in rank:
                return rank[node]
            value = 0
            for edge in parents[node]:
                value = max(value, rank_of(edge["parent"], seen + (node,)) + 1)
            rank[node] = value
            return value

        for node in self.order:
            rank_of(node)
        outdeg = defaultdict(int)
        for edge in dag:
            outdeg[edge["parent"]] += 1
        self.primary = {}
        for node in self.order:
            candidates = parents[node]
            if candidates:
                best = min(candidates, key=lambda e: (e["kind"] != "master-detail", rank[e["parent"]], -outdeg[e["parent"]], e["index"]))
                self.primary[node] = best
        self.kids = defaultdict(list)
        for node in self.order:
            if node in self.primary:
                self.kids[self.primary[node]["parent"]].append(node)
        for parent in self.kids:
            self.kids[parent].sort(key=lambda n: self.primary[n]["index"])
        self.roots = [n for n in self.order if n not in self.primary]

    def subtree(self, node):
        out, todo = [], [node]
        while todo:
            n = todo.pop()
            out.append(n)
            todo.extend(self.kids[n])
        return out

    # -- one tree
    def split(self, node):
        kids = self.kids[node]
        limit = int(self.style["max_row_children"])
        if len(kids) <= limit:
            return kids, [], []
        leaves = [k for k in kids if not self.kids[k]]
        branches = [k for k in kids if self.kids[k]]
        comb = int(self.style["max_comb_children"])
        if self.pull:
            leaves.sort(key=lambda k: self.pull.get(k, 0))
        count = min(comb, max(0, len(leaves) - comb))
        left = leaves[:count]
        right = leaves[count:count + comb]
        extra = leaves[count + comb:]
        if extra:
            self.warn.append(f"'{self.names.get(node, node)}' has {len(kids)} related entities under it; {len(extra)} of them go in a long row. "
                             "Consider a separate data model for that area")
        return branches + extra, right, left

    def measure(self, node):
        row, right, left = self.split(node)
        gap = self.style["col_gap"]
        offsets, x, centres = [], 0, []
        for kid in row:
            m = self.measure(kid)
            offsets.append(x)
            centres.append(x + m["centre"])
            x += m["width"] + gap
        row_w = x - gap if row else 0
        pc = (centres[0] + centres[-1]) / 2 if row else 0
        row_left, row_right = (-pc, row_w - pc) if row else (-self.w / 2, self.w / 2)
        comb = self.style["comb_gap"] + self.w
        top_left = -self.w / 2 - (comb if left else 0)
        top_right = self.w / 2 + (comb if right else 0)
        lo, hi = min(row_left, top_left), max(row_right, top_right)
        m = {"row": row, "right": right, "left": left, "offsets": offsets, "pc": pc,
             "width": hi - lo, "centre": -lo}
        self.m[node] = m
        return m

    def place(self, node, left):
        m = self.m[node]
        cx = left + m["centre"]
        self.pos[node] = {"x": cx - self.w / 2, "role": self.role.get(node, "root"), "depth": self.depth[node]}
        row_left = cx - m["pc"]
        for kid, off in zip(m["row"], m["offsets"]):
            self.role[kid] = "row"
            self.depth[kid] = self.depth[node] + 1
            self.place(kid, row_left + off)
        comb = self.style["comb_gap"] + self.w
        for side, kids in (("right", m["right"]), ("left", m["left"])):
            x = cx + self.w / 2 + self.style["comb_gap"] if side == "right" else cx - self.w / 2 - comb
            for kid in kids:
                self.role[kid] = f"comb-{side}"
                self.depth[kid] = self.depth[node]
                self.pos[kid] = {"x": x, "role": f"comb-{side}", "depth": self.depth[node], "anchor": node}

    def block_height(self, node):
        m = self.m.get(node, {"right": [], "left": []})
        gap = self.style["comb_stack_gap"]
        stacks = [sum(self.sizes[k]["h"] for k in kids) + gap * (len(kids) - 1) for kids in (m["right"], m["left"]) if kids]
        return max([self.sizes[node]["h"]] + stacks)

    # -- the whole diagram
    def run(self):
        self.structure()
        self.pull = {}
        boxes = self.arrange()
        # Second pass: order each card's children by where their other relationships lead, so those lines
        # cross less; then lay out again.
        centre = {n: b["x"] + b["w"] / 2 for n, b in boxes.items()}
        tree_of = {}
        for root in self.roots:
            for n in self.subtree(root):
                tree_of[n] = root
        primary_ids = {e["index"] for e in self.primary.values()}
        partners = defaultdict(list)
        for edge in self.edges:
            if edge["index"] in primary_ids or edge["parent"] == edge["child"]:
                continue
            partners[edge["parent"]].append(edge["child"])
            partners[edge["child"]].append(edge["parent"])
        for parent, kids in self.kids.items():
            for kid in kids:
                inside = set(self.subtree(kid))
                xs = [centre[p] for n in inside for p in partners[n] if p not in inside]
                self.pull[kid] = sum(xs) / len(xs) - centre[kid] if xs else 0
            kids.sort(key=lambda k: (centre[k] + self.pull[k], self.primary[k]["index"]))
            self.kids[parent] = self.keep_neighbours_together(kids, partners)
        return self.arrange()

    def keep_neighbours_together(self, kids, partners):
        """Children related to each other stay side by side, in a chain, in the order given."""
        members = set(kids)
        out = []

        def take(kid):
            out.append(kid)
            for other in kids:
                if other not in out and other in members and other in partners[kid]:
                    take(other)

        for kid in kids:
            if kid not in out:
                take(kid)
        return out

    def arrange(self):
        self.m, self.pos, self.role, self.depth = {}, {}, {}, {}
        trees = self.order_trees()
        bands, current, width = [], [], 0
        for root in trees:
            m = self.measure(root)
            add = m["width"] + (self.style["tree_gap"] if current else 0)
            if current and width + add > self.style["max_width"]:
                bands.append(current)
                current, width = [], 0
                add = m["width"]
            current.append(root)
            width += add
        if current:
            bands.append(current)
        boxes, top = {}, 0
        for band in bands:
            x = 0
            for root in band:
                self.depth[root] = 0
                self.place(root, x)
                x += self.m[root]["width"] + self.style["tree_gap"]
            members = [n for root in band for n in self.subtree(root)]
            depth_max = max(self.depth[n] for n in members)
            heights = [0] * (depth_max + 1)
            for n in members:
                if self.pos[n]["role"] in ("row", "root"):
                    heights[self.depth[n]] = max(heights[self.depth[n]], self.block_height(n))
            ys, y = [], top
            for h in heights:
                ys.append(y)
                y += h + self.style["row_gap"] + self.style["editor_growth_allowance"]
            for n in members:
                p = self.pos[n]
                if p["role"] in ("row", "root"):
                    boxes[n] = self.box(n, p["x"], ys[self.depth[n]])
            for n in members:
                if self.pos[n]["role"].startswith("comb"):
                    continue
                for side in ("right", "left"):
                    yy = boxes[n]["y"]
                    for kid in self.m[n][side]:
                        boxes[kid] = self.box(kid, self.pos[kid]["x"], yy)
                        yy += self.sizes[kid]["h"] + self.style["comb_stack_gap"]
            top = y - self.style["row_gap"] - self.style["editor_growth_allowance"] + self.style["band_gap"]
        return boxes

    def box(self, node, x, y):
        return {"id": node, "x": int(round(x)), "y": int(round(y)), "w": self.sizes[node]["w"], "h": self.sizes[node]["h"],
                "role": self.pos[node]["role"], "anchor": self.pos[node].get("anchor") or
                (self.primary[node]["parent"] if node in self.primary else None)}

    def order_trees(self):
        tree_of = {}
        for root in self.roots:
            for n in self.subtree(root):
                tree_of[n] = root
        links = defaultdict(int)
        for edge in self.edges:
            a, b = tree_of[edge["parent"]], tree_of[edge["child"]]
            if a != b:
                links[(a, b)] += 1
                links[(b, a)] += 1
        size = {r: len(self.subtree(r)) for r in self.roots}
        connected = {r for r in self.roots if size[r] > 1 or any(links[(r, o)] for o in self.roots)}
        pending = [r for r in self.roots if r in connected]
        lone = [r for r in self.roots if r not in connected]
        ordered = []
        while pending:
            if not ordered:
                pick = max(pending, key=lambda r: (size[r], -self.index[r]))
            else:
                pick = max(pending, key=lambda r: (sum(links[(r, o)] for o in ordered), size[r], -self.index[r]))
            ordered.append(pick)
            pending.remove(pick)
        return ordered + lone


# ---------------------------------------------------------------- line sides


def assign_sides(edges, boxes, role_of):
    """Sides for every line. Tree lines follow the layout: a row child joins its parent's bottom; a stacked
    child joins its parent's side. Every other line takes the sides choose_sides finds."""
    usage = defaultdict(int)
    keyed = [dict(b, key=b["id"]) for b in boxes.values()]
    sides, routes = {}, []
    loops = defaultdict(int)
    for edge in edges:
        p, c = edge["parent"], edge["child"]
        if p == c:
            sides[edge["index"]] = SELF_LOOPS[loops[p] % len(SELF_LOOPS)]
            loops[p] += 1
            for side in sides[edge["index"]]:
                usage[(p, side)] += 1
            continue
        role, anchor = role_of.get(c, (None, None))
        if anchor == p and edge.get("primary"):
            pair = {"row": ("bottom", "top"), "comb-right": ("right", "left"), "comb-left": ("left", "right")}.get(role)
            if pair:
                sides[edge["index"]] = pair
                usage[(p, pair[0])] += 1
                usage[(c, pair[1])] += 1
                routes.append(route(boxes[p], pair[0], boxes[c], pair[1]))
    for edge in edges:
        if edge["index"] in sides:
            continue
        a = dict(boxes[edge["parent"]], key=edge["parent"])
        b = dict(boxes[edge["child"]], key=edge["child"])
        pair = choose_sides(a, b, keyed, usage, {edge["parent"], edge["child"]}, routes)
        routes.append(route(a, pair[0], b, pair[1]))
        sides[edge["index"]] = pair
        usage[(edge["parent"], pair[0])] += 1
        usage[(edge["child"], pair[1])] += 1
    return sides


# ---------------------------------------------------------------- the key card

def legend_attributes(cards, edges, kinds, ends, style):
    attributes = []
    seen = []
    for card in cards.values():
        if card["kind"] not in seen:
            seen.append(card["kind"])
    for kind in seen:
        row = kinds.get(kind, kinds[""])
        attributes.append({"title": f"{row['colour']}: {row['legend']}"})
    used = []
    for edge in edges:
        for end in (edge["parentEnd"], edge["childEnd"]):
            if end not in used and end != "none":
                used.append(end)
    order = list(ends)
    for end in sorted(used, key=order.index):
        attributes.append({"title": f"{END_SYMBOL.get(end, end)} {end.replace('-', ' ')}", "description": ends[end]["meaning"]})
    if any(a["title"].startswith(f"{style['primary_marker']} ") for c in cards.values() for a in c["attributes"]):
        attributes.append({"title": f"{style['primary_marker']} identifies the record"})
    if any(c["footer"] for c in cards.values()):
        attributes.append({"title": "Footer: API name"})
    return attributes


def legend_card(cards, edges, kinds, ends, style):
    attributes = legend_attributes(cards, edges, kinds, ends, style)
    return {"id": LEGEND_NAME, "name": LEGEND_NAME, "attributes": attributes, "footer": "", "fill": LEGEND_FILL,
            "border": LEGEND_BORDER, "kind": "legend", "w": style["card_width"], "h": card_height(attributes, "", style)}


# ---------------------------------------------------------------- changes

def card_changes(box, entity, skip, position=True):
    change = {"op": "add", "kind": "activity", "ref": box["ref"], "text": box["name"]}
    if position:
        change["position"] = {"x": box["x"], "y": box["y"]}
    if box.get("footer"):
        change["footerText"] = box["footer"]
    change["fill"], change["border"] = box["fill"], box["border"]
    changes = [change]
    for attribute in box["attributes"]:
        item = {"op": "add", "kind": "attribute", "activity": box["ref"], "title": attribute["title"]}
        if attribute.get("description"):
            item["description"] = attribute["description"]
        changes.append(item)
    if entity is not None:
        changes += attachment_changes(entity, box["ref"], skip)
    return changes


def line_change(line, ref_of):
    change = {"op": "add", "kind": "line", "ref": line["ref"],
              "from": {"activity": ref_of[line["from"]]}, "to": {"activity": ref_of[line["to"]]},
              "fromSide": line["fromSide"], "toSide": line["toSide"],
              "startShape": line["startShape"], "endShape": line["endShape"]}
    if line.get("label"):
        change["label"] = line["label"]
    return change


# ---------------------------------------------------------------- plan: a new data model

def prepare(model, max_fields, show_api, label_fields, warnings):
    style, ends, defaults, kinds = load_style(), load_ends(), load_defaults(), load_kinds()
    max_fields = int(style["max_fields"]) if max_fields is None else max_fields
    show_api = yes(style["show_api_names"]) if show_api is None else show_api
    cards = build_cards(model, style, kinds, max_fields, show_api, warnings)
    edges = build_edges(model, ends, defaults, label_fields, style, warnings)
    if len(cards) > style["max_entities"]:
        warnings.append(f"the model has {len(cards)} entities; above {style['max_entities']} a data model is hard to read. "
                        "Consider one map per area")
    return style, ends, kinds, cards, edges


def lay_out(model, cards, edges, style, warnings, extra_sizes=None):
    order = [e["id"] for e in model.get("entities", [])]
    sizes = {i: {"w": c["w"], "h": c["h"]} for i, c in cards.items()}
    if extra_sizes:
        sizes.update(extra_sizes)
    layout = Layout(order, sizes, edges, style, warnings, {i: c["name"] for i, c in cards.items()})
    boxes = layout.run()
    for edge in edges:
        edge["primary"] = layout.primary.get(edge["child"]) is edge
    role_of = {n: (b["role"], b["anchor"]) for n, b in boxes.items()}
    return boxes, role_of


def plan(model, max_fields=None, show_api=None, legend=None, label_fields=False, skip=frozenset(), name=None):
    warnings = []
    style, ends, kinds, cards, edges = prepare(model, max_fields, show_api, label_fields, warnings)
    legend = yes(style["legend"]) if legend is None else legend
    boxes, role_of = lay_out(model, cards, edges, style, warnings)
    entities = {e["id"]: e for e in model.get("entities", [])}
    if legend and cards:
        key = legend_card(cards, edges, kinds, ends, style)
        left = min(b["x"] for b in boxes.values())
        top = min(b["y"] for b in boxes.values())
        boxes[LEGEND_NAME] = {"id": LEGEND_NAME, "x": int(left - style["legend_gap"] - key["w"]), "y": int(top),
                              "w": key["w"], "h": key["h"], "role": "legend", "anchor": None}
        cards = dict(cards, **{LEGEND_NAME: key})
    placed = list(boxes.values())
    fit_blank(placed, style)
    content = {k: v for k, v in boxes.items() if k != LEGEND_NAME}
    sides = assign_sides(edges, content, role_of)
    plan_boxes = []
    for ident, box in boxes.items():
        card = cards[ident]
        plan_boxes.append({"id": ident, "ref": "key-card" if ident == LEGEND_NAME else make_ref("e-", ident),
                           "name": card["name"], "x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"],
                           "role": box["role"], "attributes": card["attributes"], "footer": card["footer"],
                           "fill": card["fill"], "border": card["border"], "kind": card["kind"]})
    ref_of = {b["id"]: b["ref"] for b in plan_boxes}
    lines = []
    for edge in edges:
        side_from, side_to = sides[edge["index"]]
        lines.append({"ref": f"line{edge['index'] + 1}", "id": edge["id"], "from": edge["parent"], "to": edge["child"],
                      "fromSide": side_from, "toSide": side_to, "startShape": edge["startShape"], "endShape": edge["endShape"],
                      "parentEnd": edge["parentEnd"], "childEnd": edge["childEnd"], "label": edge["label"]})
    passes = write_passes(plan_boxes, style)
    if passes is None:
        raise PlanError("the cards do not fit the canvas")
    batches = []
    for group_boxes in passes:
        groups = [card_changes(b, entities.get(b["id"]), skip) for b in group_boxes]
        for changes in chunk(groups):
            batches.append({"kind": "cards", "changes": changes})
    for changes in chunk([[line_change(ln, ref_of)] for ln in lines]):
        batches.append({"kind": "lines", "changes": changes})
    level = {"slug": TOP, "parent": None, "boxes": plan_boxes, "lines": lines, "batches": batches, "writes": len(passes)}
    expect = {"cards": [{"ref": b["ref"], "name": b["name"], "attributes": [a["title"] for a in b["attributes"]],
                         "descriptions": [a.get("description", "") for a in b["attributes"]], "fill": b["fill"],
                         "footer": b["footer"], "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for b in plan_boxes],
              "lines": [{"ref": ln["ref"], "from": ref_of[ln["from"]], "to": ref_of[ln["to"]], "startShape": ln["startShape"],
                         "endShape": ln["endShape"], "label": ln["label"],
                         "names": [cards[ln["from"]]["name"], cards[ln["to"]]["name"]]} for ln in lines],
              "exclusive": True}
    meta = model.get("meta", {})
    result = {"planVersion": 1, "mode": "create", "diagramType": DIAGRAM_TYPE, "mapType": MAP_TYPE,
              "mapName": map_name(name if name is not None else meta.get("title") or "Data model"), "mapDescription": meta.get("description", "")[:5000],
              "createResources": False, "levels": [level], "preflight": [], "expect": expect,
              "warnings": dedupe(warnings), "gaps": model.get("gaps", [])}
    result["planId"] = plan_id(result)
    return result


# ---------------------------------------------------------------- preview

def preview_svg(boxes, lines):
    """A picture of the planned layout: cards, likely line routes and their end symbols."""
    by_id = {b["id"]: b for b in boxes}
    if not boxes:
        return "<svg xmlns='http://www.w3.org/2000/svg'/>"
    x0 = min(b["x"] for b in boxes) - 60
    y0 = min(b["y"] for b in boxes) - 60
    x1 = max(b["x"] + b["w"] for b in boxes) + 60
    y1 = max(b["y"] + b["h"] for b in boxes) + 60
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{x0} {y0} {x1 - x0} {y1 - y0}' width='{x1 - x0}' height='{y1 - y0}' "
           "font-family='sans-serif'>", f"<rect x='{x0}' y='{y0}' width='{x1 - x0}' height='{y1 - y0}' fill='#ffffff'/>"]
    for line in lines:
        a, b = by_id.get(line["from"]), by_id.get(line["to"])
        if not a or not b:
            continue
        if a is b:
            p = side_point(a, line["fromSide"])
            q = side_point(a, line["toSide"])
            d0, d1 = STEP[line["fromSide"]], STEP[line["toSide"]]
            p1 = (p[0] + d0[0] * 30, p[1] + d0[1] * 30)
            q1 = (q[0] + d1[0] * 30, q[1] + d1[1] * 30)
            corner = (q1[0], p1[1]) if line["fromSide"] in ("top", "bottom") else (p1[0], q1[1])
            pts = [p, p1, corner, q1, q]
        else:
            pts = route(a, line["fromSide"], b, line["toSide"])
        out.append("<polyline fill='none' stroke='#5a6b7b' stroke-width='1.5' points='"
                   + " ".join(f"{px:.0f},{py:.0f}" for px, py in pts) + "'/>")
        for end, point, nxt in ((line["parentEnd"], pts[0], pts[1]), (line["childEnd"], pts[-1], pts[-2])):
            out.append(f"<text x='{(point[0] + nxt[0]) / 2:.0f}' y='{(point[1] + nxt[1]) / 2 - 3:.0f}' font-size='11' "
                       f"fill='#b03a2e' text-anchor='middle'>{html.escape(END_SYMBOL.get(end, ''))}</text>")
        if line.get("label"):
            mid = pts[len(pts) // 2]
            out.append(f"<text x='{mid[0]:.0f}' y='{mid[1] - 4:.0f}' font-size='10' fill='#333' text-anchor='middle'>"
                       f"{html.escape(line['label'])}</text>")
    for b in boxes:
        out.append(f"<rect x='{b['x']}' y='{b['y']}' width='{b['w']}' height='{b['h']}' rx='10' fill='{b['fill']}' "
                   f"stroke='{b['border']}' stroke-width='2'/>")
        out.append(f"<text x='{b['x'] + 10}' y='{b['y'] + 22}' font-size='13' font-weight='bold'>{html.escape(b['name'][:28])}</text>")
        y = b["y"] + 46
        for a in b["attributes"]:
            out.append(f"<text x='{b['x'] + 14}' y='{y}' font-size='11'>{html.escape(a['title'][:30])}</text>")
            y += 26
        if b.get("footer"):
            out.append(f"<line x1='{b['x']}' y1='{b['y'] + b['h'] - 40}' x2='{b['x'] + b['w']}' y2='{b['y'] + b['h'] - 40}' stroke='#cccccc'/>")
            out.append(f"<text x='{b['x'] + 10}' y='{b['y'] + b['h'] - 16}' font-size='11' font-style='italic' fill='#555'>"
                       f"{html.escape(b['footer'][:30])}</text>")
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- reading a drawn data model


def from_diagram(read):
    """A model file from a read of an existing data model level."""
    read = unwrap(read)
    if read.get("subtype") not in (None, SUBTYPE, "dataModel"):
        raise PlanError(f"the level is a {read.get('subtype')} diagram, not a data model")
    style, ends, kinds = load_style(), load_ends(), load_kinds()
    shape_end = {row["shape"]: end for end, row in ends.items()}
    marker = f"{style['primary_marker']} "
    colours = {((row["fill"] or "").lower(), (row["border"] or "").lower()): kind for kind, row in kinds.items() if kind}
    used, entities, id_of, gaps = set(), [], {}, []
    for act in read.get("activities", []):
        text = " ".join((act.get("text") or "").split())
        if norm(text) == norm(LEGEND_NAME):
            continue
        if not text:
            gaps.append({"note": f"Card {act.get('key')} has no text, so it is not in the model"})
            continue
        ident = slug(text, used)
        id_of[act["key"]] = ident
        entity = {"id": ident, "name": text[:200]}
        if act.get("footerText"):
            entity["apiName"] = " ".join(act["footerText"].split())[:255]
        kind = colours.get(((act.get("fill") or "").lower(), (act.get("border") or "").lower()))
        if kind:
            entity["kind"] = kind
        fields = []
        for attribute in act.get("attributes", []):
            title = " ".join((attribute.get("title") or "").split())
            field = {}
            if title.startswith(marker):
                field["key"] = "primary"
                title = title[len(marker):]
            field["name"] = title[:200] or "?"
            parts = [p.strip() for p in (attribute.get("description") or "").split(",") if p.strip()]
            if "required" in parts:
                field["required"] = True
                parts.remove("required")
            if "inferred" in parts:
                field["inferred"] = True
                parts.remove("inferred")
            if parts:
                field["type"] = ", ".join(parts)[:100]
            fields.append(field)
        if fields:
            entity["fields"] = fields
        entities.append(entity)
    relationships = []
    for line in read.get("lines", []):
        a = (line.get("from") or {}).get("activity")
        b = (line.get("to") or {}).get("activity")
        if a not in id_of or b not in id_of:
            gaps.append({"note": f"Line {line.get('key')} does not join two object cards, so it is not in the model"})
            continue
        s_end, e_end = shape_end.get(line.get("startShape")), shape_end.get(line.get("endShape"))
        for shape, end in ((line.get("startShape"), s_end), (line.get("endShape"), e_end)):
            if shape and end is None:
                gaps.append({"note": f"Line {line.get('key')} has the end shape {shape}, which a data model relationship cannot hold; "
                                     "amending this diagram leaves that end as it is"})
        s_many = bool(s_end) and ends[s_end]["many"] == "yes"
        e_many = bool(e_end) and ends[e_end]["many"] == "yes"
        if e_many and not s_many:
            rel = {"from": id_of[a], "to": id_of[b], "cardinality": "one-to-many", "fromEnd": s_end, "toEnd": e_end}
        elif s_many and not e_many:
            rel = {"from": id_of[b], "to": id_of[a], "cardinality": "one-to-many", "fromEnd": e_end, "toEnd": s_end}
        else:
            rel = {"from": id_of[a], "to": id_of[b], "cardinality": "many-to-many" if s_many else "one-to-one",
                   "fromEnd": s_end, "toEnd": e_end}
        rel = {k: v for k, v in rel.items() if v}
        if line.get("label"):
            rel["label"] = " ".join(line["label"].split())[:200]
        relationships.append(rel)
    title = " ".join((read.get("title") or "").split())[:80]
    model = {"schemaVersion": "1.0",
             "meta": {"title": title if len(title) >= 2 else "Data model", "author": "draw-data-model (from-diagram)",
                      "sources": [{"kind": "diagram", "ref": read.get("mapId") or read.get("diagramId") or "unknown"}]}}
    if read.get("description"):
        model["meta"]["description"] = read["description"][:5000]
    if entities:
        model["entities"] = entities
    if relationships:
        model["relationships"] = relationships
    if gaps or not entities:
        model["gaps"] = gaps or [{"note": "The diagram has no object cards"}]
    return model


# ---------------------------------------------------------------- amend: change an existing data model


def amend(model, read, allow_remove=False, relayout=False, max_fields=None, show_api=None, label_fields=False, skip=frozenset()):
    read = unwrap(read)
    if read.get("subtype") not in (None, SUBTYPE, "dataModel"):
        raise PlanError(f"the level is a {read.get('subtype')} diagram, not a data model")
    warnings = []
    style, ends, kinds, cards, edges = prepare(model, max_fields, show_api, label_fields, warnings)
    entities = {e["id"]: e for e in model.get("entities", [])}
    acts = list(read.get("activities", []))
    names = {norm(c["name"]) for c in cards.values()}
    legend_act = next((a for a in acts if norm(a.get("text")) == norm(LEGEND_NAME) and norm(LEGEND_NAME) not in names), None)
    pool = [a for a in acts if a is not legend_act]
    match = {}

    def take(test):
        for ident, card in cards.items():
            if ident in match:
                continue
            entity = entities[ident]
            for act in pool:
                if test(card, entity, act):
                    match[ident] = act
                    pool.remove(act)
                    break

    take(lambda c, e, a: norm(a.get("text")) == norm(c["name"]))
    take(lambda c, e, a: bool(e.get("apiName")) and norm(a.get("text")) == norm(e["apiName"]))
    take(lambda c, e, a: bool(e.get("apiName")) and norm(a.get("text")) == norm(f"{c['name']} {e['apiName']}"))
    take(lambda c, e, a: bool(e.get("apiName")) and norm(a.get("footerText")) == norm(e["apiName"]))
    extra = pool
    new_ids = [i for i in cards if i not in match]
    canvas = tuple((read.get("canvas") or {}).get(k) for k in ("x", "y", "w", "h"))
    if None in canvas:
        raise PlanError("the read has no canvas; read the level with include [\"layout\"]")
    canvas = (canvas[0], canvas[1], canvas[0] + canvas[2], canvas[1] + canvas[3])
    summary = {"addCards": [], "updateCards": [], "removeCards": [], "keepCards": [], "addLines": [], "updateLines": [],
               "removeLines": [], "keepLines": []}
    removals, updates, line_ops, legend_ops = [], [], [], []
    expect_cards, final = [], {}
    removed_keys = set()
    if allow_remove:
        for act in extra:
            removals.append({"op": "remove", "kind": "activity", "key": act["key"]})
            removed_keys.add(act["key"])
            summary["removeCards"].append(act.get("text"))
    else:
        summary["keepCards"] = [a.get("text") for a in extra]
    # existing cards: fields, footer, colours
    for ident, act in match.items():
        card = cards[ident]
        ops, kept, titles = simulate_attributes(act.get("attributes", []), card["attributes"], allow_remove)
        changed = []
        for op in ops:
            if op["op"] == "remove":
                updates.append({"op": "remove", "kind": "attribute", "activity": act["key"], "key": op["key"]})
                changed.append(f"remove field {op['title']}")
            elif op["op"] == "add":
                change = {"op": "add", "kind": "attribute", "activity": act["key"], "title": op["title"], "position": op["position"]}
                if op["description"]:
                    change["description"] = op["description"]
                updates.append(change)
                changed.append(f"add field {op['title']}")
            else:
                change = {"op": "update", "kind": "attribute", "activity": act["key"], "key": op["key"]}
                for k in ("description", "position"):
                    if k in op:
                        change[k] = op[k]
                updates.append(change)
                changed.append(f"update field {op['title']}")
        if kept:
            changed.append(f"keep fields not in the model: {', '.join(kept)}")
        footer = act.get("footerText") or ""
        update = {"op": "update", "kind": "activity", "key": act["key"]}
        if norm(footer) != norm(card["footer"]):
            if card["footer"] or allow_remove:
                update["footerText"] = card["footer"]
                changed.append(f"footer {card['footer'] or '(cleared)'}")
                footer = card["footer"]
        if entities[ident].get("kind") and ((act.get("fill") or "").lower() != card["fill"].lower()
                                            or (act.get("border") or "").lower() != card["border"].lower()):
            update["fill"], update["border"] = card["fill"], card["border"]
            changed.append(f"colour for {entities[ident]['kind']}")
        if len(update) > 3:
            updates.append(update)
        if changed:
            summary["updateCards"].append(f"{card['name']}: " + "; ".join(changed))
        height = max(act.get("h") or 0, card_height(titles, footer, style))
        final[ident] = {"id": ident, "key": act["key"], "x": act.get("x", 0), "y": act.get("y", 0), "w": act.get("w", style["card_width"]),
                        "h": height, "name": card["name"], "attributes": [{"title": t} for t in titles], "footer": footer,
                        "fill": card["fill"] if "fill" in update else (act.get("fill") or card["fill"]),
                        "border": card["border"] if "border" in update else (act.get("border") or card["border"])}
        expect_cards.append({"key": act["key"], "name": card["name"], "attributes": titles, "footer": footer})
        if act.get("h") and height > act["h"] + TOLERANCE:
            grown = dict(final[ident])
            hit = [a.get("text") for a in acts if a is not act and a.get("key") not in removed_keys and "x" in a and overlaps(grown, a)]
            if hit:
                warnings.append(f"'{card['name']}' grows to {height} px and will overlap {', '.join(hit)}; amend with --relayout or move the cards in Elements")
    others = [dict(a) for a in extra if a["key"] not in removed_keys and "x" in a]
    if legend_act is not None and "x" in legend_act:
        others.append(dict(legend_act))
    for item in read.get("notes", []) + read.get("texts", []):
        if "x" in item:
            others.append(dict(item))
    # new cards and, with --relayout, new places for every card
    refs = {i: make_ref("e-", i) for i in new_ids}
    moves = {}
    if relayout:
        sizes = {i: {"w": final[i]["w"], "h": final[i]["h"]} for i in match}
        boxes, role_of = lay_out(model, cards, edges, style, warnings, sizes)
        content = [b for b in final.values()] or [{"x": canvas[0], "y": canvas[1], "w": 0, "h": 0}]
        ccx = (min(b["x"] for b in content) + max(b["x"] + b["w"] for b in content)) / 2
        ccy = (min(b["y"] for b in content) + max(b["y"] + b["h"] for b in content)) / 2
        nx0 = min(b["x"] for b in boxes.values())
        nx1 = max(b["x"] + b["w"] for b in boxes.values())
        ny0 = min(b["y"] for b in boxes.values())
        ny1 = max(b["y"] + b["h"] for b in boxes.values())
        dx, dy = int(round(ccx - (nx0 + nx1) / 2)), int(round(ccy - (ny0 + ny1) / 2))
        for ident, box in boxes.items():
            target = {"x": box["x"] + dx, "y": box["y"] + dy, "w": box["w"], "h": box["h"]}
            if ident in final:
                if abs(target["x"] - final[ident]["x"]) > TOLERANCE or abs(target["y"] - final[ident]["y"]) > TOLERANCE:
                    moves[ident] = target
                final[ident].update(x=target["x"], y=target["y"])
            else:
                card = cards[ident]
                final[ident] = dict(target, id=ident, ref=refs[ident], name=card["name"], attributes=card["attributes"],
                                    footer=card["footer"], fill=card["fill"], border=card["border"])
                moves[ident] = target
        if legend_act is not None and "x" in legend_act:
            left = min(b["x"] for b in final.values())
            top = min(b["y"] for b in final.values())
            target = {"x": int(left - style["legend_gap"] - legend_act["w"]), "y": int(top), "w": legend_act["w"], "h": legend_act["h"]}
            moves[LEGEND_NAME] = target
            others = [o for o in others if o.get("key") != legend_act["key"]] + [dict(legend_act, **target)]
        summary["relayout"] = f"{sum(1 for k in moves if k in match)} card(s) move"
    else:
        placed_ids = set(match)
        occupied = list(final.values()) + others
        todo = list(new_ids)
        while todo:
            pick, anchor = None, None
            for ident in todo:
                for edge in edges:
                    if edge["child"] == ident and edge["parent"] in placed_ids and edge["parent"] != ident:
                        pick, anchor = ident, final[edge["parent"]]
                        break
                if pick:
                    break
            if not pick:
                for ident in todo:
                    for edge in edges:
                        if edge["parent"] == ident and edge["child"] in placed_ids:
                            pick, anchor = ident, final[edge["child"]]
                            break
                    if pick:
                        break
            if not pick:
                pick = todo[0]
                if final:
                    right = max(final.values(), key=lambda b: b["x"] + b["w"])
                    anchor = right
            card = cards[pick]
            x, y = free_spot(anchor, (card["w"], card["h"]), occupied, canvas, style)
            final[pick] = {"id": pick, "ref": refs[pick], "x": x, "y": y, "w": card["w"], "h": card["h"], "name": card["name"],
                           "attributes": card["attributes"], "footer": card["footer"], "fill": card["fill"], "border": card["border"]}
            occupied.append(final[pick])
            moves[pick] = {"x": x, "y": y, "w": card["w"], "h": card["h"]}
            placed_ids.add(pick)
            todo.remove(pick)
    for ident in new_ids:
        summary["addCards"].append(cards[ident]["name"])
        expect_cards.append({"ref": refs[ident], "name": cards[ident]["name"], "attributes": [a["title"] for a in cards[ident]["attributes"]],
                             "footer": cards[ident]["footer"], "x": final[ident]["x"], "y": final[ident]["y"]})
    for item in expect_cards:
        ident = next((i for i, f in final.items() if f.get("key") == item.get("key") and "key" in item), None)
        if ident in moves:
            item["x"], item["y"] = moves[ident]["x"], moves[ident]["y"]
    state = {i: {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for i, b in final.items() if i in match}
    for k, a in enumerate(others):
        state[f"other{k}"] = {"x": a["x"], "y": a["y"], "w": a.get("w", 0), "h": a.get("h", 0)}
    for i in match:
        if i in moves:
            act = match[i]
            state[i] = {"x": act["x"], "y": act["y"], "w": act["w"], "h": act["h"]}
    passes = moves_in_passes(state, moves, canvas, style) if moves else []
    # lines
    key_or_ref = {i: final[i].get("key", final[i].get("ref")) for i in final}
    current = [ln for ln in read.get("lines", []) if (ln.get("from") or {}).get("activity") is not None
               and (ln.get("to") or {}).get("activity") is not None]
    by_pair = defaultdict(list)
    for ln in current:
        by_pair[frozenset((ln["from"]["activity"], ln["to"]["activity"]))].append(ln)
    used_lines = set()
    usage = defaultdict(int)
    for ln in current:
        if ln.get("fromSide"):
            usage[(ln["from"]["activity"], ln["fromSide"])] += 1
        if ln.get("toSide"):
            usage[(ln["to"]["activity"], ln["toSide"])] += 1
    boxes_now = {i: dict(b, key=key_or_ref[i]) for i, b in final.items()}
    keyed = list(boxes_now.values()) + [dict(o, key=f"o{n}") for n, o in enumerate(others)]
    role_sides = {}
    if relayout:
        role_sides = assign_sides(edges, {i: dict(b, id=i) for i, b in final.items()}, role_of)
    expect_lines, plan_lines = [], []
    for edge in edges:
        p, c = edge["parent"], edge["child"]
        a_key, b_key = key_or_ref[p], key_or_ref[c]
        names_pair = [cards[p]["name"], cards[c]["name"]]
        found = None
        if p in match and c in match:
            candidates = [ln for ln in by_pair[frozenset((a_key, b_key))] if ln["key"] not in used_lines]
            same = [ln for ln in candidates if edge["label"] and norm(ln.get("label")) == norm(edge["label"])]
            found = (same or candidates or [None])[0]
        if found:
            used_lines.add(found["key"])
            forward = found["from"]["activity"] == a_key
            start, end = (edge["startShape"], edge["endShape"]) if forward else (edge["endShape"], edge["startShape"])
            change = {"op": "update", "kind": "line", "key": found["key"]}
            what = []
            shape_end = {row["shape"]: name for name, row in ends.items()}
            drawn_from = names_pair[0] if forward else names_pair[1]
            drawn_to = names_pair[1] if forward else names_pair[0]
            if found.get("startShape") != start:
                change["startShape"] = start
                what.append(f"end at {drawn_from} becomes {shape_end.get(start, start)}")
            if found.get("endShape") != end:
                change["endShape"] = end
                what.append(f"end at {drawn_to} becomes {shape_end.get(end, end)}")
            if edge["label"] and norm(found.get("label")) != norm(edge["label"]):
                change["label"] = edge["label"]
                what.append(f"label {edge['label']}")
            if relayout and p != c:
                pair = role_sides[edge["index"]] if forward else tuple(reversed(role_sides[edge["index"]]))
                if found.get("fromSide") != pair[0] or found.get("toSide") != pair[1]:
                    change["fromSide"], change["toSide"] = pair
                    what.append("re-routed")
            if len(change) > 3:
                line_ops.append(change)
                summary["updateLines"].append(f"{names_pair[0]} - {names_pair[1]}: " + ", ".join(what))
            expect_lines.append({"key": found["key"], "from": found["from"]["activity"], "to": found["to"]["activity"],
                                 "startShape": start, "endShape": end, "label": edge["label"] or found.get("label", ""), "names": names_pair})
            plan_lines.append({"from": p if forward else c, "to": c if forward else p,
                               "fromSide": change.get("fromSide", found.get("fromSide") or "bottom"),
                               "toSide": change.get("toSide", found.get("toSide") or "top"),
                               "parentEnd": edge["parentEnd"] if forward else edge["childEnd"],
                               "childEnd": edge["childEnd"] if forward else edge["parentEnd"], "label": edge["label"]})
            continue
        if p == c:
            taken = {(ln.get("fromSide"), ln.get("toSide")) for ln in by_pair[frozenset((a_key,))]}
            pair = next((loop for loop in SELF_LOOPS if loop not in taken), SELF_LOOPS[0])
        elif relayout:
            pair = role_sides[edge["index"]]
        else:
            pair = choose_sides(boxes_now[p], boxes_now[c], keyed, usage, {a_key, b_key})
        usage[(a_key, pair[0])] += 1
        usage[(b_key, pair[1])] += 1
        ref = f"line{edge['index'] + 1}"
        change = {"op": "add", "kind": "line", "ref": ref, "from": {"activity": a_key}, "to": {"activity": b_key},
                  "fromSide": pair[0], "toSide": pair[1], "startShape": edge["startShape"], "endShape": edge["endShape"]}
        if edge["label"]:
            change["label"] = edge["label"]
        line_ops.append(change)
        summary["addLines"].append(f"{names_pair[0]} - {names_pair[1]}" + (f" ({edge['label']})" if edge["label"] else ""))
        expect_lines.append({"ref": ref, "from": a_key, "to": b_key, "startShape": edge["startShape"], "endShape": edge["endShape"],
                             "label": edge["label"], "names": names_pair})
        plan_lines.append({"from": p, "to": c, "fromSide": pair[0], "toSide": pair[1], "parentEnd": edge["parentEnd"],
                           "childEnd": edge["childEnd"], "label": edge["label"]})
    name_of_key = {a["key"]: a.get("text") for a in acts}
    for ln in current:
        if ln["key"] in used_lines:
            continue
        ends_keys = (ln["from"]["activity"], ln["to"]["activity"])
        if any(k in removed_keys for k in ends_keys):
            continue
        if legend_act is not None and legend_act["key"] in ends_keys:
            continue
        described = f"{name_of_key.get(ends_keys[0])} - {name_of_key.get(ends_keys[1])}" + (f" ({ln['label']})" if ln.get("label") else "")
        if allow_remove:
            removals.append({"op": "remove", "kind": "line", "key": ln["key"]})
            summary["removeLines"].append(described)
        else:
            summary["keepLines"].append(described)
    # the key card
    if legend_act is not None:
        want = legend_attributes({i: dict(cards[i], kind=cards[i]["kind"]) for i in cards}, edges, kinds, ends, style)
        have = legend_act.get("attributes", [])
        if [norm(a["title"]) for a in have] != [norm(a["title"]) for a in want]:
            legend_ops += [{"op": "remove", "kind": "attribute", "activity": legend_act["key"], "key": a["key"]} for a in have]
            for item in want:
                change = {"op": "add", "kind": "attribute", "activity": legend_act["key"], "title": item["title"]}
                if item.get("description"):
                    change["description"] = item["description"]
                legend_ops.append(change)
    # batches
    batches = []
    if removals:
        lines_first = [r for r in removals if r["kind"] == "line"] + [r for r in removals if r["kind"] == "activity"]
        for changes in chunk([[r] for r in lines_first]):
            batches.append({"kind": "remove", "changes": changes, "confirm": True})
    groups = [[u] for u in updates]
    first = True
    for fits in passes or [[]]:
        group_list = list(groups) if first else []
        first = False
        for ident in fits:
            if ident == LEGEND_NAME:
                group_list.append([{"op": "update", "kind": "activity", "key": legend_act["key"],
                                    "position": {"x": moves[ident]["x"], "y": moves[ident]["y"]}}])
            elif ident in match:
                group_list.append([{"op": "update", "kind": "activity", "key": match[ident]["key"],
                                    "position": {"x": moves[ident]["x"], "y": moves[ident]["y"]}}])
            else:
                box = dict(final[ident], ref=refs[ident])
                group_list.append(card_changes(box, entities[ident], skip))
        for changes in chunk(group_list):
            batches.append({"kind": "cards", "changes": changes})
    for changes in chunk([[op] for op in line_ops + legend_ops]):
        batches.append({"kind": "lines", "changes": changes})
    level = {"slug": TOP, "parent": None, "boxes": [dict(b, ref=b.get("ref") or b.get("key"), role="card") for b in final.values()],
             "lines": plan_lines, "batches": batches, "writes": len(batches)}
    expect = {"cards": expect_cards, "lines": expect_lines, "exclusive": allow_remove}
    meta = model.get("meta", {})
    result = {"planVersion": 1, "mode": "amend", "diagramType": DIAGRAM_TYPE, "mapType": MAP_TYPE,
              "mapName": map_name((meta.get("title") or read.get("title") or "Data model")), "mapDescription": "",
              "createResources": False, "levels": [level], "preflight": [], "expect": expect, "summary": summary,
              "map": {"mapId": read.get("mapId"), "diagramId": read.get("diagramId"), "version": read.get("version", 0)},
              "warnings": dedupe(warnings), "gaps": model.get("gaps", [])}
    result["planId"] = plan_id(result)
    return result


# ---------------------------------------------------------------- check: the drawn result

def layout_rules():
    return {row["rule_id"]: row for row in read_csv(RUBRIC_PATH)
            if row.get("checked_by") == "layout-check" and DIAGRAM_TYPE in row.get("applies_to", "").split("|")}


def check(workdir):
    workdir = Path(workdir)
    the_plan = read_json(workdir / "plan.json")
    refuse_partial_reads(workdir, the_plan)   # a review read that is not the whole answer writes no layout-check.json
    read = unwrap(read_json(workdir / "review" / f"{TOP}.json"))
    keys = id_map(level_results(workdir, TOP))
    rules = layout_rules()
    level = str(read.get("levelNumber", "1"))
    acts = read.get("activities", [])
    by_key = {a["key"]: a for a in acts}
    findings = []

    def find(rule, element, issue, fix):
        row = rules.get(rule, {})
        findings.append({"rule": rule, "severity": row.get("severity", "warn"), "level": level,
                         "element": element, "issue": issue, "fix": fix})

    def key_of(item):
        if "key" in item and isinstance(item["key"], int):
            return item["key"]
        ref = item.get("ref")
        return ref if isinstance(ref, int) else keys.get(ref)

    def resolve(value):
        return value if isinstance(value, int) else keys.get(value)

    expect = the_plan["expect"]
    seen = set()
    for card in expect["cards"]:
        act = by_key.get(key_of(card))
        if act is None:
            act = next((a for a in acts if norm(a.get("text")) == norm(card["name"]) and a["key"] not in seen), None)
        name = f"'{card['name']}'"
        if act is None:
            find("R33", name, f"The card {name} is not on the level.", "Send the batch that adds it, or plan and draw again.")
            continue
        seen.add(act["key"])
        element = f"{name} (key {act['key']})"
        if norm(act.get("text")) != norm(card["name"]):
            find("R33", element, f"The card reads '{act.get('text')}', not {name}.", "Rename the card or the entity so they match.")
        drawn = [norm(a.get("title")) for a in act.get("attributes", [])]
        wanted = [norm(t) for t in card["attributes"]]
        if drawn != wanted:
            find("R33", element, f"The card shows the fields {drawn}; the plan has {wanted}.", "Amend the diagram from the model again.")
        if "descriptions" in card and drawn == wanted:
            have = [norm(a.get("description")) for a in act.get("attributes", [])]
            if have != [norm(d) for d in card["descriptions"]]:
                find("R33", element, "Some field descriptions differ from the plan.", "Amend the diagram from the model again.")
        if card.get("fill") and act.get("fill") and act["fill"].lower() != card["fill"].lower():
            find("R33", element, f"The card's colour is {act['fill']}; the plan has {card['fill']}.", "Amend the diagram from the model again.")
        if norm(act.get("footerText")) != norm(card.get("footer")):
            find("R33", element, f"The footer reads '{act.get('footerText') or ''}'; the plan has '{card.get('footer') or ''}'.",
                 "Amend the diagram from the model again.")
        if card.get("x") is not None and "x" in act:
            if abs(act["x"] - card["x"]) > TOLERANCE or abs(act["y"] - card["y"]) > TOLERANCE:
                find("R32", element, f"{name} is at {act['x']},{act['y']}; the plan put it at {card['x']},{card['y']}.",
                     "Someone may have moved it in Elements; move it back or plan again.")
            if card.get("h") and act.get("h") and act["h"] + TOLERANCE < card["h"]:
                find("R32", element, f"{name} is {act['h']} px tall; the plan expected {card['h']} px.", "Check its fields were all written.")
    placed = [a for a in acts if "x" in a]
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if overlaps(a, b):
                find("R32", f"'{a.get('text')}' and '{b.get('text')}'", "These two cards overlap.",
                     "Move one of them, or amend with --relayout.")
    if expect.get("exclusive"):
        for act in acts:
            if act["key"] not in seen:
                find("R33", f"'{act.get('text')}' (key {act['key']})", "This card is on the level but not in the plan.",
                     "Someone added it after the drawing; check it belongs.")
    lines = [ln for ln in read.get("lines", [])]
    used = set()
    for item in expect["lines"]:
        a, b = resolve(item["from"]), resolve(item["to"])
        element = f"line {item['names'][0]} - {item['names'][1]}"
        found = None
        exact = resolve(item["ref"]) if item.get("ref") else item.get("key")
        candidates = [ln for ln in lines if ln.get("key") not in used and (ln.get("from") or {}).get("activity") == a
                      and (ln.get("to") or {}).get("activity") == b]
        if exact is not None:
            found = next((ln for ln in candidates if ln.get("key") == exact), None)
        if found is None and candidates:
            found = next((ln for ln in candidates if norm(ln.get("label")) == norm(item.get("label"))), candidates[0])
        if found is None:
            find("R33", element, "The relationship is not drawn between these two cards.", "Send the line batch again, or plan again.")
            continue
        used.add(found["key"])
        if found.get("startShape") != item["startShape"] or found.get("endShape") != item["endShape"]:
            find("R33", f"{element} (key {found['key']})",
                 f"The line ends are {found.get('startShape')} and {found.get('endShape')}; the plan has {item['startShape']} and {item['endShape']}.",
                 "Amend the diagram from the model again.")
    if expect.get("exclusive"):
        for ln in lines:
            if ln.get("key") not in used and (ln.get("from") or {}).get("activity") is not None and (ln.get("to") or {}).get("activity") is not None:
                find("R33", f"line key {ln['key']}", "This line is on the level but not in the plan.", "Someone added it after the drawing; check it belongs.")
    boxes = [dict(a, key=a["key"]) for a in placed]
    for ln in lines:
        a = by_key.get((ln.get("from") or {}).get("activity"))
        b = by_key.get((ln.get("to") or {}).get("activity"))
        if not a or not b or a is b or not ln.get("fromSide") or not ln.get("toSide") or "x" not in a or "x" not in b:
            continue
        hits = route_crossings(route(a, ln["fromSide"], b, ln["toSide"]), boxes, {a["key"], b["key"]})
        if hits:
            find("R34", f"line {a.get('text')} - {b.get('text')} (key {ln['key']})",
                 f"The line is likely to run through {', '.join(repr(h.get('text')) for h in hits)}.",
                 "Move a card, or amend with --relayout.")
    result = {"findings": findings, "checked": sorted(rules), "boxes": len(acts), "lines": len(lines)}
    (workdir / "layout-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


# ---------------------------------------------------------------- main

def print_summary(the_plan, workdir):
    level = the_plan["levels"][0]
    batches = level["batches"]
    if the_plan["mode"] == "create":
        cards = [b for b in level["boxes"] if b["role"] != "legend"]
        print(f"PLAN {len(cards)} cards, {len(level['lines'])} lines"
              f"{', a key card' if len(cards) < len(level['boxes']) else ''}; {len(batches)} batch(es) in {level['writes']} canvas write(s)")
    else:
        s = the_plan["summary"]
        print(f"PLAN amend: {len(batches)} batch(es)")
        for label, key in (("ADD card", "addCards"), ("UPDATE card", "updateCards"), ("REMOVE card", "removeCards"),
                           ("KEEP card (not in the model; --allow-remove removes it)", "keepCards"), ("ADD line", "addLines"),
                           ("UPDATE line", "updateLines"), ("REMOVE line", "removeLines"),
                           ("KEEP line (not in the model; --allow-remove removes it)", "keepLines")):
            for item in s.get(key, []):
                print(f"{label}: {item}")
        if s.get("relayout"):
            print(f"RELAYOUT {s['relayout']}")
        if not batches:
            print("NOTHING TO CHANGE: the diagram already matches the model")
    for warning in the_plan["warnings"]:
        print(f"WARN {warning}")
    for gap in the_plan.get("gaps", []):
        print(f"GAP {gap.get('note')}")
    print(f"WROTE {Path(workdir) / 'plan.json'} and {Path(workdir) / 'preview.svg'}")


def preview_of(the_plan):
    level = the_plan["levels"][0]
    boxes = [b for b in level["boxes"]]
    lines = level["lines"]
    return preview_svg(boxes, lines)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Lay out, write, amend and check an Elements data model.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "amend"):
        p = sub.add_parser(name)
        p.add_argument("model")
        p.add_argument("--workdir", required=True)
        p.add_argument("--max-fields", type=int)
        p.add_argument("--no-api-names", action="store_true")
        p.add_argument("--label-fields", action="store_true")
        p.add_argument("--skip", default="")
        if name == "plan":
            p.add_argument("--no-legend", action="store_true")
            p.add_argument("--name")
        else:
            p.add_argument("--read", required=True)
            p.add_argument("--allow-remove", action="store_true")
            p.add_argument("--relayout", action="store_true")
    p = sub.add_parser("from-diagram")
    p.add_argument("read")
    p.add_argument("--out", required=True)
    p = sub.add_parser("next")
    p.add_argument("workdir")
    p = sub.add_parser("check")
    p.add_argument("workdir")
    args = parser.parse_args(argv)
    try:
        if args.command in ("plan", "amend"):
            workdir = Path(args.workdir)
            guard_workdir(workdir)
            gate = validate.gate(args.model, "data-model")
            if gate:
                return gate
            model = scope_model(read_json(args.model), args.model, args.workdir)
            show_api = False if args.no_api_names else None
            if args.command == "plan":
                the_plan = plan(model, args.max_fields, show_api, False if args.no_legend else None, args.label_fields,
                                parse_skip(args.skip), args.name)
            else:
                the_plan = amend(model, read_json(args.read), args.allow_remove, args.relayout, args.max_fields, show_api,
                                 args.label_fields, parse_skip(args.skip))
            the_plan["model"] = str(Path(args.model).resolve())
            workdir.mkdir(parents=True, exist_ok=True)
            (workdir / "plan.json").write_text(json.dumps(the_plan, indent=2, ensure_ascii=False), encoding="utf-8")
            (workdir / "preview.svg").write_text(preview_of(the_plan), encoding="utf-8")
            if args.command == "amend":
                (workdir / "map.json").write_text(json.dumps(the_plan["map"], indent=2), encoding="utf-8")
            print_summary(the_plan, workdir)
            return 0
        if args.command == "from-diagram":
            model = from_diagram(read_json(args.read))
            Path(args.out).write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"WROTE {args.out}: {len(model.get('entities', []))} entities, {len(model.get('relationships', []))} relationships, "
                  f"{len(model.get('gaps', []))} gap(s)")
            for gap in model.get("gaps", []):
                print(f"GAP {gap['note']}")
            return 0
        if args.command == "next":
            step = next_step(args.workdir, Path(__file__).name)
            if "then" in step:
                step["then"] = f"python3 {Path(__file__).name} check {args.workdir}"
            print(json.dumps(step, indent=2, ensure_ascii=False))
            return 0
        if args.command == "check":
            result = check(args.workdir)
            for f in result["findings"]:
                print(f"{f['severity'].upper()} {f['rule']} {f['element']}: {f['issue']}")
            print(f"CHECKED {result['boxes']} cards and {result['lines']} lines against {', '.join(result['checked'])}: "
                  f"{len(result['findings'])} finding(s)")
            return 0
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except PlanError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
