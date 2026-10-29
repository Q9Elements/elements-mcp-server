#!/usr/bin/env python3
"""Lay out a business-architecture model as an Elements system architecture diagram (a system landscape or a
solution architecture), write it with manage_diagram, amend an existing one in place, and check the result.

Usage:
  python3 layout_architecture.py plan MODEL.json --workdir DIR [--name TEXT] [--no-key] [--no-headings]
                                 [--drop-icons NAMES] [--skip KINDS] [--create-resources]
  python3 layout_architecture.py from-diagram TOP_READ.json [CHILD_READ.json ...] --out MODEL.json
  python3 layout_architecture.py amend MODEL.json --read TOP_READ.json --workdir DIR [--allow-remove] [--relayout]
                                 [--drop-icons NAMES] [--skip KINDS] [--create-resources]
  python3 layout_architecture.py next DIR
  python3 layout_architecture.py check DIR

plan          Works out every card and line. Each level puts its hub (the system the diagram is about) in the
              centre and the other systems in four zones around it, from their kind and the direction their data
              moves (data/architecture-zones.csv): sources left, destinations right, engagement above, ingestion
              below. A system's zone can be pinned in the model. A group (a system others name as their parent)
              is one card listing its members, with a drill-down level that shows each member as a card and the
              group's lines in and out continued to the member they really join. Every line is an integration:
              an arrow where the data arrives (both ends when two-way), labelled with its label, technology or
              pattern and its timing word. A Key card explains arrows, timing words and colours; text boxes name
              the zones. Writes DIR/plan.json and DIR/preview.svg and prints a summary with any warnings.
from-diagram  Turns get_diagram reads of an existing system architecture (the top level, then any group
              drill-down levels) into a model file: cards become systems, lines become integrations with their
              direction, label and timing. Edit that file and pass it to amend.
amend         Compares a model with the read of an existing diagram's top level and plans the manage_diagram
              changes that make it match: new cards placed in their zone, attributes, footers, icons and colours
              updated, new lines added, labels and arrows corrected. A new group card gets its drill-down level.
              Removals are listed but only planned with --allow-remove. --relayout also moves every card to a
              fresh layout and re-routes every line. Writes DIR/map.json and DIR/plan.json.
next          Prints, as JSON, the one thing to do next (create the map, preflight, a batch, a read, the review
              reads, or done). Run it again after saving each result where it says.
check         Checks the review reads in DIR/review/ against the plan and the rubric rows checked by layout-check
              for system architecture (R48-R50) and writes DIR/layout-check.json.

Why manage_diagram only: it is the write path that also amends a diagram later, and it never replaces a level
whole. It makes every card 200 px wide (wider only with more than three footer icons), sizes its height from
its attributes and footer, joins lines at the middle of a side, and accepts positions only inside the canvas,
which grows as cards are written; the plan splits the cards into as many writes as the canvas needs.

Exit 0: done. Exit 1: the model, the plan or a saved file has a problem the output describes.
Exit 2: setup problem (a data file or the command line). Standard library only; Python 3.8 or later.
"""

from mcp_result import map_name

import argparse
import csv
import html
import itertools
import json
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attachment_scope import scope_model
import validate  # noqa: E402  (the drawing gate: no plan from a model that fails validation)
import layout_engine as engine  # noqa: E402  (the shared layout engine: write loop, geometry, data files, checks)

PLUGIN = engine.PLUGIN
DATA = PLUGIN / "data"
STYLE_PATH = DATA / "style-architecture.csv"
KINDS_PATH = DATA / "system-kinds.csv"
ZONES_PATH = DATA / "architecture-zones.csv"
HEADINGS_PATH = DATA / "architecture-zone-headings.csv"
ICONS_PATH = DATA / "system-icons.csv"
TIMING_PATH = DATA / "integration-timing.csv"
PATTERNS_PATH = DATA / "integration-patterns.csv"
AUTOMATION_TYPES_PATH = DATA / "automation-types.csv"
ENTITY_KINDS_PATH = DATA / "entity-kinds.csv"
RUBRIC_PATH = DATA / "readability-rubric.csv"
DIAGRAM_TYPE = "system-architecture"
MAP_TYPE = "system_architecture"
SUBTYPE = "system_architecture"
TOP = engine.TOP
TOLERANCE = 2
KEY_NAME = "Key"
KEY_FILL, KEY_BORDER = "#ffffff", "#c9c9c9"
ZONES = ("top", "left", "right", "bottom")
MAIN_FLOW = {"left": "source", "right": "target", "top": "target", "bottom": "source"}
HUB_SIDE = {"left": "left", "right": "right", "top": "top", "bottom": "bottom"}
CARD_SIDE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
INFERRED = " (inferred)"
SetupError, PlanError = engine.SetupError, engine.PlanError
norm, squash, cut = engine.norm, engine.squash, engine.cut
ATTACHMENT_KINDS = engine.ATTACHMENT_KINDS
PREFLIGHT_BOX_ICONS = 8   # preflight icons are footer icons here, and footer icons widen a card (38 + 54 px each)


# ---------------------------------------------------------------- data files

def number(value):
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def load_style():
    style = {row["setting"]: number(row["value"]) for row in engine.read_csv(STYLE_PATH)}
    needed = ["card_width", "card_height_min", "card_height_base", "attribute_row_height", "footer_text_height",
              "footer_icons_height", "footer_both_height", "footer_icon_width", "max_footer_icons", "max_attributes",
              "attribute_max_chars", "footer_max_chars", "footer_max_words", "editor_growth_allowance", "hub_gap_x", "hub_gap_y", "hub_stack_gap",
              "zone_col_gap", "zone_stack_gap", "zone_row_gap", "zone_row_stack_gap", "max_zone_stack", "max_zone_row",
              "max_cards_per_level", "group_stack_gap", "group_free_end_clearance", "child_label_max_chars", "label_max_chars",
              "label_separator", "start_shape", "end_shape", "two_way_start_shape", "key", "key_gap", "zone_headings",
              "heading_gap", "text_box_width", "text_box_height", "canvas_blank_width", "canvas_blank_height", "canvas_margin_factor",
              "middleware_fold_threshold", "via_label_format", "chain_col_gap", "chain_stack_gap", "chain_reads_label",
              "chain_writes_label", "chain_triggers_label"]
    missing = [n for n in needed if n not in style]
    if missing:
        raise SetupError(f"{STYLE_PATH.name}: no value for {', '.join(missing)}")
    with open(STYLE_PATH, encoding="utf-8") as handle:   # keep the separator's spaces, which the CSV reader keeps too
        for row in csv.DictReader(handle):
            if row["setting"] == "label_separator":
                style["label_separator"] = row["value"]
    # names the data model helpers (free_spot) read
    style["col_gap"], style["row_gap"] = style["zone_row_gap"], style["zone_stack_gap"]
    return style


def load_kinds():
    kinds = {row["kind"]: row for row in engine.read_csv(KINDS_PATH)}
    if not kinds:
        raise SetupError(f"{KINDS_PATH.name} is empty")
    return kinds


def load_zones():
    zones = {(row["kind"], row["flow"]): row["zone"] for row in engine.read_csv(ZONES_PATH)}
    for (kind, flow), zone in zones.items():
        if zone not in ZONES:
            raise SetupError(f"{ZONES_PATH.name}: {kind}/{flow} has zone '{zone}'; use {', '.join(ZONES)}")
    return zones


def load_headings():
    return {row["zone"]: row for row in engine.read_csv(HEADINGS_PATH)}


def load_icons():
    rows = []
    for row in engine.read_csv(ICONS_PATH):
        try:
            row["regex"] = re.compile(row["match"], re.IGNORECASE)
        except re.error as exc:
            raise SetupError(f"{ICONS_PATH.name}: bad match '{row['match']}': {exc}")
        row["kind_list"] = [k for k in row.get("kinds", "").split("|") if k]
        rows.append(row)
    return rows


def load_timing():
    return {row["timing"]: row for row in engine.read_csv(TIMING_PATH)}


def load_patterns():
    return {row["pattern_id"]: row for row in engine.read_csv(PATTERNS_PATH)}


def yes(value):
    return str(value).strip().lower() in ("yes", "true", "1")


class Data:
    def __init__(self):
        self.style = load_style()
        self.kinds = load_kinds()
        self.zones = load_zones()
        self.headings = load_headings()
        self.icons = load_icons()
        self.timing = load_timing()
        self.patterns = load_patterns()
        self.icon_type = {norm(r["icon"]): r["type"] for r in self.icons}
        self.automation_types = {row["type"]: row for row in engine.read_csv(AUTOMATION_TYPES_PATH)}
        self.entity_kinds = {row["kind"]: row for row in engine.read_csv(ENTITY_KINDS_PATH)}


# ---------------------------------------------------------------- cards

def icon_for(system, data):
    """The header icon of a system: its own, or the first row of data/system-icons.csv that matches its name and kind."""
    if system.get("icon"):
        return system["icon"]
    for row in data.icons:
        if row["kind_list"] and system.get("kind") not in row["kind_list"]:
            continue
        if row["regex"].search(system.get("name", "")):
            return row["icon"]
    return None


def resource(name, data, role):
    return {"name": name, "type": data.icon_type.get(norm(name), "System"), "role": role}


def card_height(n_attributes, footer, n_icons, style):
    height = style["card_height_base"] + style["attribute_row_height"] * n_attributes
    if footer and n_icons:
        height += style["footer_both_height"]
    elif footer:
        height += style["footer_text_height"]
    elif n_icons:
        height += style["footer_icons_height"]
    return max(style["card_height_min"], height)


def card_width(n_icons, style):
    return max(style["card_width"], 38 + style["footer_icon_width"] * n_icons)


def attribute_list(items, style):
    out = []
    limit = int(style["attribute_max_chars"])
    for item in items:
        title = " ".join(item["title"].split())
        description = item.get("description", "")
        if len(title) > limit:
            description = title + (". " + description if description else "")
            title = title[:limit - 1].rstrip() + "…"
        entry = {"title": title}
        if description:
            entry["description"] = description[:400]
        out.append(entry)
    most = int(style["max_attributes"])
    if len(out) > most:
        rest = out[most - 1:]
        out = out[:most - 1] + [{"title": f"+{len(rest)} more", "description": "; ".join(a["title"] for a in rest)[:400]}]
    return out


def word_cut(text, limit):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    if " " in head:
        head = head[:head.rfind(" ")]
    return head.rstrip(",;:") + "…"


def footer_text(text, style):
    """A card's footer: at most footer_max_words words and footer_max_chars characters, cut with an ellipsis, so a
    long description does not stretch the card."""
    words = " ".join((text or "").split()).split(" ")
    most = int(style["footer_max_words"])
    short = " ".join(words[:most]).rstrip(",;:.") + "…" if len(words) > most else " ".join(words)
    return word_cut(short, int(style["footer_max_chars"]))


def build_card(system, members, data, drop_icons, warnings):
    style = data.style
    header = icon_for(system, data)
    if header and norm(header) in drop_icons:
        header = None
    attributes = system.get("attributes")
    if attributes is None and members:
        attributes = [{"title": m["name"]} for m in members]
    attributes = attribute_list(attributes or [], style)
    footer = footer_text(system.get("footer", ""), style)
    icons = list(system.get("footerIcons", []))
    if not icons and members:
        for m in members:
            icon = icon_for(m, data)
            if icon and norm(icon) not in {norm(i) for i in icons} and (not header or norm(icon) != norm(header)):
                icons.append(icon)
    icons = [i for i in icons if norm(i) not in drop_icons]
    most = int(style["max_footer_icons"])
    if len(icons) > most:
        warnings.append(f"'{system['name']}' has {len(icons)} footer icons; only the first {most} are drawn so the card stays {style['card_width']} px wide")
        icons = icons[:most]
    kind = data.kinds.get(system.get("kind"), {"fill": "", "border": "", "colour": "", "legend": ""})
    if len(system["name"]) > 50:
        warnings.append(f"'{system['name']}' is a long name; it wraps and the editor may make the card taller")
    resources = ([resource(header, data, "header")] if header else []) + [resource(i, data, "footer") for i in icons]
    return {"id": system["id"], "name": system["name"], "kind": system.get("kind", ""), "header": header, "icons": icons,
            "resources": resources, "attributes": attributes, "footer": footer,
            "fill": kind.get("fill") or None, "border": kind.get("border") or None,
            "w": card_width(len(icons), style), "h": card_height(len(attributes), footer, len(icons), style)}


# ---------------------------------------------------------------- lines

def label_of(integration, data):
    style = data.style
    base = integration.get("label") or integration.get("technology") or ""
    if not base and integration.get("pattern") in data.patterns:
        base = data.patterns[integration["pattern"]].get("short_label") or data.patterns[integration["pattern"]]["name"]
    base = " ".join(base.split())
    word = data.timing.get(integration.get("timing"), {}).get("word", "")
    text = f"{base}{style['label_separator']}{word}" if base and word else (base or word)
    if integration.get("step"):
        text = f"{integration['step']}. {text}".strip()
    if integration.get("inferred"):
        text = (text + INFERRED).strip()
    return text


def shapes(two_way, style):
    return (style["two_way_start_shape"] if two_way else style["start_shape"]), style["end_shape"]


class Model:
    """The model's systems by level, and its integrations lifted to the cards that show them."""

    def __init__(self, model, data, drop_icons, warnings):
        self.model = model
        self.data = data
        self.warn = warnings
        self.systems = {s["id"]: s for s in model.get("systems", [])}
        self.order = [s["id"] for s in model.get("systems", [])]
        self.parent = {s["id"]: s.get("parent") for s in model.get("systems", [])}
        self.members = defaultdict(list)
        for s in model.get("systems", []):
            if s.get("parent"):
                self.members[s["parent"]].append(s)
        self.groups = [i for i in self.order if self.members.get(i)]
        self.cards = {}
        for ident in self.order:
            self.cards[ident] = build_card(self.systems[ident], self.members.get(ident, []), data, drop_icons, warnings)
        self.integrations = []
        for index, item in enumerate(model.get("integrations", [])):
            label = label_of(item, data)
            if len(label) > data.style["label_max_chars"]:
                warnings.append(f"the label '{label}' is long; the server wraps labels at about 20 characters, so it takes "
                                f"{len(label) // 20 + 1} lines. Shorten the technology or label")
            self.integrations.append(dict(item, index=index, id=item.get("id") or f"int-{index + 1}", text=label,
                                          two_way=item.get("direction") == "two-way"))
        self.placement = self.middleware_placement()
        self.hidden = {mid for mid, where in self.placement.items() if where == "label"
                       and not any(mid in (i["from"], i["to"]) for i in self.integrations)}
        self.top_items = self.lift_via()
        self.chains = validate.chain_members({"systems": model.get("systems", []), "integrations": self.integrations})

    def middleware_placement(self):
        """card or label for every middleware an integration passes through: the model's placement, else label when it
        carries more systems than middleware_fold_threshold (systems other than hubs and Salesforce at either end)."""
        carried = defaultdict(set)
        for item in self.integrations:
            if item.get("via") in self.systems:
                for end in (item["from"], item["to"]):
                    s = self.systems.get(end, {})
                    if not s.get("hub") and s.get("kind") != "salesforce":
                        carried[item["via"]].add(end)
        threshold = self.data.style["middleware_fold_threshold"]
        out = {}
        for mid in {i["via"] for i in self.integrations if i.get("via") in self.systems}:
            out[mid] = self.systems[mid].get("placement") or ("label" if len(carried[mid]) > threshold else "card")
            if out[mid] == "label" and not self.systems[mid].get("placement"):
                self.warn.append(f"'{self.systems[mid]['name']}' carries {len(carried[mid])} systems, more than {threshold}: they join the "
                                 f"other end directly with 'via {self.systems[mid]['name']}' in their labels (set placement card to draw them through it)")
        return out

    def lift_via(self):
        """The integrations as top-level line items: a direct one as it is; one through a middleware drawn as a card as two
        items, the side away from the carried system labelled with the mechanism (merged into one line per direction), the
        side to it with the integration's label; one through a middleware drawn as a label as one item, 'via <middleware>'."""
        style = self.data.style
        out = []
        carded = {mid for mid, where in self.placement.items() if where == "card"}
        for item in self.integrations:
            via = item.get("via")
            if not via or via not in self.placement:
                if item["from"] in carded or item["to"] in carded:
                    other = item["to"] if item["from"] in carded else item["from"]
                    s = self.systems.get(other, {})
                    if s.get("hub") or s.get("kind") == "salesforce":
                        out.append(dict(item, hubSide=True))
                        continue
                out.append(item)
                continue
            if self.placement[via] == "label":
                text = style["via_label_format"].format(via=self.systems[via]["name"], label=item["text"]).strip()
                out.append(dict(item, text=text))
                continue
            first = dict(item, id=f"{item['id']}~1", to=via)
            second = dict(item, id=f"{item['id']}~2", **{"from": via})
            for seg, other in ((first, item["from"]), (second, item["to"])):
                s = self.systems.get(other, {})
                if s.get("hub") or s.get("kind") == "salesforce":
                    seg["hubSide"] = True
                    seg["text"] = " ".join((item.get("technology") or "").split())
            out.append(first)
            out.append(second)
        return out

    def visible(self, ident):
        return self.parent.get(ident) or ident

    def level_ids(self, parent):
        return [i for i in self.order if self.parent.get(i) == parent and not (parent is None and i in self.hidden)]

    def top_edges(self):
        """One line per integration between two top-level cards; integrations that lift onto the same two cards
        with the same label and direction share one line."""
        edges, by_key = [], {}
        for item in self.top_items:
            a, b = self.visible(item["from"]), self.visible(item["to"])
            if a == b:
                continue
            key = (a, b, item["two_way"], "\u00a7hub" if item.get("hubSide") else norm(item["text"]))
            if key in by_key:
                edge = by_key[key]
                edge["items"].append(item)
                if item.get("hubSide") and item["text"] and norm(item["text"]) not in norm(edge["label"]):
                    edge["label"] = ", ".join(x for x in (edge["label"], item["text"]) if x)
                continue
            edge = {"id": item["id"], "index": len(edges), "from": a, "to": b, "two_way": item["two_way"],
                    "label": item["text"], "items": [item]}
            by_key[key] = edge
            edges.append(edge)
        return edges

    def child_edges(self, group, top_edges):
        """The lines of a group's drill-down: integrations between its members, and each integration with one
        member end as a line from or to a free end, continuing the top-level line it lifted onto."""
        members = {m["id"] for m in self.members[group]}
        internal, boundary = [], []
        parent_of_item = {}
        for edge in top_edges:
            for item in edge["items"]:
                parent_of_item[item["id"]] = edge
        linked = set()
        for item in self.top_items:
            a, b = item["from"], item["to"]
            if a in members and b in members:
                internal.append({"id": item["id"], "index": len(internal), "from": a, "to": b, "two_way": item["two_way"],
                                 "label": item["text"]})
                continue
            if a not in members and b not in members:
                continue
            edge = parent_of_item.get(item["id"])
            if edge is None:
                continue
            outward = a in members
            member, other = (a, b) if outward else (b, a)
            limit = int(self.data.style["child_label_max_chars"])
            other_name = self.systems[other]["name"]
            label = f"{other_name}: {item['text']}"
            if len(label) > limit:   # the line is short: name the other system, the parent line carries the mechanism
                label = word_cut(other_name if item["two_way"] else f"{'To' if a in members else 'From'} {other_name}", limit)
            entry = {"id": item["id"], "member": member, "out": outward, "two_way": item["two_way"], "label": label,
                     "parentEdge": edge["id"]}
            key = (edge["id"], outward)
            if key not in linked:
                linked.add(key)
                entry["linked"] = True
            boundary.append(entry)
        return internal, boundary


# ---------------------------------------------------------------- zones and hubs

def degrees(ids, edges):
    count = Counter()
    for edge in edges:
        if edge["from"] in ids and edge["to"] in ids:
            count[edge["from"]] += 1
            count[edge["to"]] += 1
    return count


def choose_hubs(ids, systems, edges):
    hubs = [i for i in ids if systems[i].get("hub")]
    if hubs or not ids:
        return hubs
    count = degrees(set(ids), edges)
    central = [i for i in ids if systems[i].get("kind") in ("salesforce", "middleware")] or list(ids)
    return [max(central, key=lambda i: (count[i], -ids.index(i)))]


def assign_zones(ids, hubs, systems, edges, zone_table):
    """zone and flow of every non-hub card: pinned, else from its kind and the direction of its lines with the hubs;
    a card with no line to a hub joins the zone of the neighbours it has most lines with."""
    hub_set = set(hubs)
    flows, zones = {}, {}
    for ident in ids:
        if ident in hub_set:
            continue
        out = inn = False
        for edge in edges:
            if edge["two_way"] and hub_set.intersection((edge["from"], edge["to"])) and ident in (edge["from"], edge["to"]):
                out = inn = True
            elif edge["from"] == ident and edge["to"] in hub_set:
                out = True
            elif edge["to"] == ident and edge["from"] in hub_set:
                inn = True
        flows[ident] = "two-way" if out and inn else "source" if out else "target" if inn else "none"
        if systems[ident].get("zone"):
            zones[ident] = systems[ident]["zone"]
        elif flows[ident] != "none":
            zones[ident] = zone_table.get((systems[ident].get("kind"), flows[ident]), "right")
    for _ in range(len(ids)):
        changed = False
        for ident in ids:
            if ident in hub_set or ident in zones:
                continue
            near = Counter()
            for edge in edges:
                if ident in (edge["from"], edge["to"]):
                    other = edge["to"] if edge["from"] == ident else edge["from"]
                    if other in zones:
                        near[zones[other]] += 1
            if near:
                zones[ident] = near.most_common(1)[0][0]
                changed = True
        if not changed:
            break
    for ident in ids:
        if ident not in hub_set and ident not in zones:
            zones[ident] = zone_table.get((systems[ident].get("kind"), "none"), "right")
    return zones, flows


def keep_together(members, edges):
    """Members ordered so cards that share a line sit next to each other: each group of connected members is walked
    as a chain from its least connected member, always stepping to the least connected partner not yet placed, so a
    card joined to two others sits between them. Groups keep the model order of their first member."""
    partners = defaultdict(list)
    inside = set(members)
    for edge in edges:
        if edge["from"] in inside and edge["to"] in inside and edge["from"] != edge["to"]:
            if edge["to"] not in partners[edge["from"]]:
                partners[edge["from"]].append(edge["to"])
            if edge["from"] not in partners[edge["to"]]:
                partners[edge["to"]].append(edge["from"])
    order = {m: n for n, m in enumerate(members)}
    out, placed = [], set()
    for first in members:
        if first in placed:
            continue
        component, todo = [], [first]
        while todo:
            node = todo.pop()
            if node in component:
                continue
            component.append(node)
            todo.extend(partners[node])
        node = min(component, key=lambda m: (len(partners[m]), order[m]))
        while node is not None:
            out.append(node)
            placed.add(node)
            nxt = [p for p in partners[node] if p not in placed]
            if not nxt:
                rest = [m for m in component if m not in placed]
                nxt = rest
            node = min(nxt, key=lambda m: (len(partners[m]), order[m])) if nxt else None
    return out


def zone_layout(ids, sizes, systems, edges, data, warnings):
    """Boxes for one level: hubs stacked in the centre, the other cards in columns left and right of them and rows
    above and below. Returns (boxes, hubs, zones, flows, slots); slots holds each zone's columns or rows, inner first."""
    style = data.style
    hubs = choose_hubs(ids, systems, edges)
    zones, flows = assign_zones(ids, hubs, systems, edges, data.zones)
    by_zone = {z: keep_together([i for i in ids if zones.get(i) == z], edges) for z in ZONES}
    boxes = {}
    # the hub column, centred on x = 0, from y = 0
    y = 0
    for ident in hubs:
        w, h = sizes[ident]["w"], sizes[ident]["h"]
        boxes[ident] = {"id": ident, "x": -w / 2, "y": y, "w": w, "h": h, "zone": "hub"}
        y += h + style["hub_stack_gap"] + style["editor_growth_allowance"]
    hub_h = (y - style["hub_stack_gap"] - style["editor_growth_allowance"]) if hubs else 0
    hub_left = min([b["x"] for b in boxes.values()] or [-style["card_width"] / 2])
    hub_right = max([b["x"] + b["w"] for b in boxes.values()] or [style["card_width"] / 2])
    slots = {}
    # left and right columns
    stack_gap = style["zone_stack_gap"] + style["editor_growth_allowance"]
    columns = {}
    for zone in ("left", "right"):
        members = by_zone[zone]
        n = int(style["max_zone_stack"])
        columns[zone] = [members[i:i + n] for i in range(0, len(members), n)]
    band_h = max([hub_h] + [sum(sizes[i]["h"] for i in col) + stack_gap * (len(col) - 1)
                            for zone in ("left", "right") for col in columns[zone]])
    centre_y = hub_h / 2 if hubs else band_h / 2
    for zone in ("left", "right"):
        slots[zone] = columns[zone]
        for k, col in enumerate(columns[zone]):
            width = max(sizes[i]["w"] for i in col)
            if zone == "left":
                x_right = hub_left - style["hub_gap_x"] - k * (width + style["zone_col_gap"])
            else:
                x_left = hub_right + style["hub_gap_x"] + k * (width + style["zone_col_gap"])
            total = sum(sizes[i]["h"] for i in col) + stack_gap * (len(col) - 1)
            yy = centre_y - total / 2
            # an outer column sits with its cards' middles in the gaps of the column inside it, so its lines to the hub
            # pass between those cards rather than through them
            inner = [boxes[i] for i in columns[zone][k - 1]] if k else []
            mids = [(a["y"] + a["h"] + b["y"]) / 2 for a, b in zip(inner, inner[1:])]
            if k and len(col) <= len(mids):
                first = (len(mids) - len(col)) // 2
                targets = mids[first:first + len(col)]
            else:
                targets = None
            floor = None
            for n, ident in enumerate(col):
                w, h = sizes[ident]["w"], sizes[ident]["h"]
                x = x_right - w if zone == "left" else x_left
                if targets:
                    yy = targets[n] - h / 2 if floor is None else max(floor, targets[n] - h / 2)
                    floor = yy + h + stack_gap
                boxes[ident] = {"id": ident, "x": x, "y": yy, "w": w, "h": h, "zone": zone, "slot": k, "pos": col.index(ident)}
                yy += h + stack_gap
    band_top = centre_y - band_h / 2
    band_bottom = centre_y + band_h / 2
    # top and bottom rows: above and below the band, kept between the left and right zones so the lines from a row
    # to the hub never run through a column; a zone with more cards than fit there takes a second row, staggered
    # by half a card so its lines pass between the cards of the first
    centre_x = (hub_left + hub_right) / 2
    margin = 20
    lo = hub_left - style["hub_gap_x"] + margin if columns["left"] else None
    hi = hub_right + style["hub_gap_x"] - margin if columns["right"] else None
    gap = style["zone_row_gap"]
    slot_w = style["card_width"] + gap
    for zone in ("top", "bottom"):
        members = by_zone[zone]
        cap = int(style["max_zone_row"])
        if lo is not None and hi is not None:
            cap = max(1, min(cap, int((hi - lo + gap) // slot_w)))
        rows = [members[i:i + cap] for i in range(0, len(members), cap)]
        slots[zone] = rows
        edge_y = band_top - style["hub_gap_y"] if zone == "top" else band_bottom + style["hub_gap_y"] + style["editor_growth_allowance"]
        for k, row in enumerate(rows):
            row_h = max(sizes[i]["h"] for i in row)
            total_w = sum(sizes[i]["w"] for i in row) + gap * (len(row) - 1)
            x = centre_x - total_w / 2 + (slot_w / 2 if k % 2 else 0)
            if lo is not None and x < lo:
                x = lo
            if hi is not None and x + total_w > hi:
                x = max(lo if lo is not None else hi - total_w, hi - total_w)
            top = edge_y - row_h if zone == "top" else edge_y
            for n, ident in enumerate(row):
                w, h = sizes[ident]["w"], sizes[ident]["h"]
                # top rows share their bottom edge (the side their lines leave), bottom rows their top edge
                yy = top + (row_h - h) if zone == "top" else top
                boxes[ident] = {"id": ident, "x": x, "y": yy, "w": w, "h": h, "zone": zone, "slot": k, "pos": n}
                x += w + gap
            step = row_h + style["zone_row_stack_gap"] + style["editor_growth_allowance"]
            edge_y = edge_y - step if zone == "top" else edge_y + step
    if len(ids) > style["max_cards_per_level"]:
        warnings.append(f"{len(ids)} cards on one level; above {style['max_cards_per_level']} a diagram is hard to read. "
                        "Group related systems (give them a parent) so they draw as one card with a drill-down")
    for box in boxes.values():
        box["x"], box["y"] = int(round(box["x"])), int(round(box["y"]))
    return boxes, hubs, zones, flows, slots


def column_layout(ids, sizes, edges, data):
    """A group's drill-down: its members stacked in one column, cards that share a line next to each other."""
    style = data.style
    order = keep_together(list(ids), edges)
    boxes, y = {}, 0
    for ident in order:
        w, h = sizes[ident]["w"], sizes[ident]["h"]
        boxes[ident] = {"id": ident, "x": int(round(-w / 2)), "y": int(round(y)), "w": w, "h": h, "zone": "column", "slot": 0,
                        "pos": len(boxes)}
        y += h + style["group_stack_gap"] + style["editor_growth_allowance"]
    return boxes, order


# ---------------------------------------------------------------- line sides

def hub_pair(edge, boxes, hubs):
    """Sides for a line between a hub and a card in a zone: the card's side facing the hub, the hub's side facing the card."""
    a, b = edge["from"], edge["to"]
    if a in hubs and b in hubs:
        return ("bottom", "top") if boxes[a]["y"] < boxes[b]["y"] else ("top", "bottom")
    if a in hubs:
        zone = boxes[b]["zone"]
        return HUB_SIDE[zone], CARD_SIDE[zone]
    if b in hubs:
        zone = boxes[a]["zone"]
        return CARD_SIDE[zone], HUB_SIDE[zone]
    return None


OUTWARD = {"top": ("top", "top"), "bottom": ("bottom", "bottom"), "left": ("left", "left"), "right": ("right", "right"),
           "column": ("left", "left")}


def neighbour_pair(a, b):
    """Sides for two cards in one column or row: facing sides when they are next to each other, else the side away
    from the hub on both, so the line goes round the cards between them."""
    same_slot = a.get("zone") == b.get("zone") and a.get("slot") == b.get("slot") and "pos" in a and "pos" in b
    if same_slot and abs(a["pos"] - b["pos"]) > 1:
        return OUTWARD.get(a["zone"])
    if same_slot:
        if abs(a["x"] - b["x"]) <= TOLERANCE:
            return ("bottom", "top") if a["y"] < b["y"] else ("top", "bottom")
        if abs((a["y"] + a["h"]) - (b["y"] + b["h"])) <= TOLERANCE or abs(a["y"] - b["y"]) <= TOLERANCE:
            return ("right", "left") if a["x"] < b["x"] else ("left", "right")
    return None


def assign_sides(edges, boxes, hubs):
    usage = defaultdict(int)
    keyed = [dict(b, key=b["id"]) for b in boxes.values()]
    sides, routes = {}, []
    for edge in edges:
        pair = hub_pair(edge, boxes, set(hubs))
        if pair:
            sides[edge["index"]] = pair
            usage[(edge["from"], pair[0])] += 1
            usage[(edge["to"], pair[1])] += 1
            routes.append(engine.route(boxes[edge["from"]], pair[0], boxes[edge["to"]], pair[1]))
    for edge in edges:
        if edge["index"] in sides:
            continue
        a, b = boxes[edge["from"]], boxes[edge["to"]]
        pair = neighbour_pair(a, b)
        if pair is None:
            pair = engine.choose_sides(dict(a, key=edge["from"]), dict(b, key=edge["to"]), keyed, usage, {edge["from"], edge["to"]}, routes)
        sides[edge["index"]] = pair
        usage[(edge["from"], pair[0])] += 1
        usage[(edge["to"], pair[1])] += 1
        routes.append(engine.route(a, pair[0], b, pair[1]))
    separate_parallel(edges, boxes, sides, local=True)
    return sides


def separate_parallel(edges, boxes, sides, local=False):
    """A second or third line between the same two cards takes other sides than the lines before it (bottom to
    bottom, then top to top, where the route crosses no card), so the lines and their labels do not share one path.
    With local (the top level, where most lines meet at the hub), a line moves only to sides no line to another card
    uses and onto a route at most a card's height or two longer than the first line's; otherwise it keeps its sides.
    edges: [{"index", "from", "to"}]; sides: {index: (from side, to side)}, changed in place."""
    keyed = [dict(b, key=i) for i, b in boxes.items()]
    routes = {e["index"]: engine.route(boxes[e["from"]], sides[e["index"]][0], boxes[e["to"]], sides[e["index"]][1])
              for e in edges if e["index"] in sides}
    busy_by = defaultdict(set)
    for e in edges:
        if e["index"] in sides:
            busy_by[frozenset((e["from"], e["to"]))] |= {(e["from"], sides[e["index"]][0]), (e["to"], sides[e["index"]][1])}
    seen = defaultdict(list)
    for edge in edges:
        if edge["index"] not in sides:
            continue
        group = seen[frozenset((edge["from"], edge["to"]))]
        if group:
            taken = set()
            for other in group:
                pair = sides[other["index"]]
                taken.add(pair if other["from"] == edge["from"] else (pair[1], pair[0]))
            if sides[edge["index"]] in taken:
                a, b = dict(boxes[edge["from"]], key=edge["from"]), dict(boxes[edge["to"]], key=edge["to"])
                others = [r for i, r in routes.items() if i != edge["index"]]
                limit = busy = None
                if local:
                    first = engine.route_length(routes[group[0]["index"]])
                    limit = first + 2 * max(a["h"], b["h"]) + 4 * engine.JETTY
                    here = frozenset((edge["from"], edge["to"]))
                    busy = set().union(*[v for k, v in busy_by.items() if k != here]) if len(busy_by) > 1 else set()
                pair = engine.parallel_sides(a, b, taken, keyed, {edge["from"], edge["to"]}, others,
                                             max_length=limit, busy=busy or ())
                if pair:
                    sides[edge["index"]] = pair
                    routes[edge["index"]] = engine.route(a, pair[0], b, pair[1])
        group.append(edge)


# ---------------------------------------------------------------- key card and headings

def key_attributes(cards, edges, integrations, data):
    attributes = [{"title": "→ Data flows in the arrow's direction", "description": "The arrow points at the system the data reaches"}]
    if any(e["two_way"] for e in edges):
        attributes.append({"title": "↔ Data flows both ways", "description": "The line starts at the system that starts the exchange"})
    used = []
    for item in integrations:
        if item.get("timing") and item["timing"] not in used:
            used.append(item["timing"])
    for timing in [t for t in data.timing if t in used]:
        row = data.timing[timing]
        attributes.append({"title": f"{row['word']}: {row['short']}", "description": row["meaning"]})
    colours = []
    for card in cards.values():
        row = data.kinds.get(card["kind"])
        if row and (row["colour"], row["legend"]) not in colours:
            colours.append((row["colour"], row["legend"]))
    grouped = defaultdict(list)
    grouped_titles = {row["colour"]: row.get("key_title", "") for row in data.kinds.values()}
    for colour, legend in colours:
        grouped[colour].append(legend)
    if len(grouped) > 1:
        for colour, legends in grouped.items():
            attributes.append({"title": f"{colour} card: {grouped_titles.get(colour) or legends[0]}", "description": "; ".join(legends)})
    if any(i.get("inferred") for i in integrations):
        attributes.append({"title": "(inferred): worked out, not stated by the source"})
    return attributes


def key_card(cards, edges, integrations, data):
    style = data.style
    attributes = key_attributes(cards, edges, integrations, data)
    return {"id": KEY_NAME, "name": KEY_NAME, "kind": "key", "header": None, "icons": [], "resources": [],
            "attributes": attributes, "footer": "", "fill": KEY_FILL, "border": KEY_BORDER,
            "w": style["card_width"], "h": card_height(len(attributes), "", 0, style)}


def heading_boxes(boxes, zones, flows, slots, data):
    style = data.style
    out = []
    tw, th = style["text_box_width"], style["text_box_height"]
    for zone in ZONES:
        groups = slots.get(zone) or []
        members = [i for g in groups for i in g]
        if not members:
            continue
        row = data.headings.get(zone, {})
        pure = all(flows.get(i) == MAIN_FLOW[zone] for i in members)
        text = row.get("heading") if pure else row.get("heading_mixed")
        if not text:
            continue
        outer = groups[-1]
        if zone in ("left", "right"):
            first = boxes[groups[0][0]]
            top = min(boxes[i]["y"] for g in groups for i in g)
            x = boxes[outer[0]]["x"] if zone == "left" else boxes[groups[0][0]]["x"]
            out.append({"id": f"heading-{zone}", "text": text, "x": int(x), "y": int(top - style["heading_gap"] - th), "w": tw, "h": th})
        elif zone == "top":
            top = min(boxes[i]["y"] for i in outer)
            x = min(boxes[i]["x"] for i in outer)
            out.append({"id": f"heading-{zone}", "text": text, "x": int(x), "y": int(top - style["heading_gap"] - th), "w": tw, "h": th})
        else:
            bottom = max(boxes[i]["y"] + boxes[i]["h"] for i in outer)
            x = min(boxes[i]["x"] for i in outer)
            out.append({"id": f"heading-{zone}", "text": text, "x": int(x), "y": int(bottom + style["heading_gap"]), "w": tw, "h": th})
    return out


# ---------------------------------------------------------------- changes

def card_changes(box, system, skip):
    change = {"op": "add", "kind": "activity", "ref": box["ref"], "text": box["name"], "position": {"x": box["x"], "y": box["y"]}}
    if box.get("footer"):
        change["footerText"] = box["footer"]
    if box.get("fill"):
        change["fill"] = box["fill"]
    if box.get("border"):
        change["border"] = box["border"]
    changes = [change]
    for res in box["resources"]:
        changes.append({"op": "add", "kind": "resource", "activity": box["ref"], "name": res["name"], "type": res["type"], "role": res["role"]})
    for attribute in box["attributes"]:
        item = {"op": "add", "kind": "attribute", "activity": box["ref"], "title": attribute["title"]}
        if attribute.get("description"):
            item["description"] = attribute["description"]
        changes.append(item)
    if system is not None:
        changes += engine.attachment_changes(system, box["ref"], skip)
    return changes


def text_change(text_box):
    return {"op": "add", "kind": "text", "ref": text_box["ref"], "text": text_box["text"],
            "position": {"x": text_box["x"], "y": text_box["y"]}}


def line_change(line, ref_of):
    change = {"op": "add", "kind": "line", "ref": line["ref"],
              "from": {"activity": ref_of[line["from"]]}, "to": {"activity": ref_of[line["to"]]},
              "fromSide": line["fromSide"], "toSide": line["toSide"],
              "startShape": line["startShape"], "endShape": line["endShape"]}
    if line.get("label"):
        change["label"] = line["label"]
    return change


def plan_box(card, box, ref, role="card"):
    return {"id": card["id"], "ref": ref, "name": card["name"], "x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"],
            "zone": box.get("zone", role), "role": role, "header": card["header"], "icons": card["icons"],
            "resources": card["resources"], "attributes": card["attributes"], "footer": card["footer"],
            "fill": card["fill"], "border": card["border"], "kind": card["kind"]}


def passes_for(items, style):
    passes = engine.write_passes(items, style)
    if passes is None:
        raise PlanError("the cards do not fit the canvas")
    return passes


def expect_of(boxes, lines, ref_of, names, texts=(), groups=(), boundary=()):
    return {"cards": [{"ref": b["ref"], "name": b["name"], "header": b["header"], "icons": b["icons"],
                       "attributes": [a["title"] for a in b["attributes"]], "footer": b["footer"],
                       "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "drilldown": b["id"] in groups} for b in boxes],
            "lines": [{"ref": ln["ref"], "from": ref_of[ln["from"]], "to": ref_of[ln["to"]], "startShape": ln["startShape"],
                       "endShape": ln["endShape"], "label": ln.get("label", ""), "names": [names[ln["from"]], names[ln["to"]]]}
                      for ln in lines],
            "boundary": list(boundary),
            "texts": [t["text"] for t in texts],
            "exclusive": True}


# ---------------------------------------------------------------- plan: a new diagram

def top_level(m, data, key, headings, skip, warnings):
    style = data.style
    ids = m.level_ids(None)
    edges = m.top_edges()
    sizes = {i: {"w": m.cards[i]["w"], "h": m.cards[i]["h"]} for i in ids}
    boxes, hubs, zones, flows, slots = zone_layout(ids, sizes, m.systems, edges, data, warnings)
    extra = []
    if key and ids:
        card = key_card({i: m.cards[i] for i in m.order}, edges, m.integrations, data)
        left = min(b["x"] for b in boxes.values())
        top = min(b["y"] for b in boxes.values())
        boxes[KEY_NAME] = {"id": KEY_NAME, "x": int(left - style["key_gap"] - card["w"]), "y": int(top), "w": card["w"], "h": card["h"], "zone": "key"}
        extra.append(card)
    texts = heading_boxes(boxes, zones, flows, slots, data) if headings else []
    everything = list(boxes.values()) + texts
    engine.fit_blank(everything, style)
    content = {i: b for i, b in boxes.items() if i != KEY_NAME}
    sides = assign_sides(edges, content, hubs)
    cards = dict(m.cards, **{c["id"]: c for c in extra})
    plan_boxes = []
    for ident, box in boxes.items():
        ref = "key-card" if ident == KEY_NAME else engine.make_ref("s-", ident)
        plan_boxes.append(plan_box(cards[ident], box, ref, "key" if ident == KEY_NAME else "card"))
    for n, t in enumerate(texts, start=1):
        t["ref"] = f"heading{n}"
    ref_of = {b["id"]: b["ref"] for b in plan_boxes}
    lines = []
    for edge in edges:
        start, end = shapes(edge["two_way"], style)
        side_from, side_to = sides[edge["index"]]
        lines.append({"ref": f"line{edge['index'] + 1}", "id": edge["id"], "from": edge["from"], "to": edge["to"],
                      "fromSide": side_from, "toSide": side_to, "startShape": start, "endShape": end, "label": edge["label"],
                      "twoWay": edge["two_way"], "items": [i["id"] for i in edge["items"]]})
    batches = []
    for group in passes_for(plan_boxes + texts, style):
        changes = []
        for item in group:
            if "text" in item and "name" not in item:
                changes.append([text_change(item)])
            else:
                changes.append(card_changes(item, m.systems.get(item["id"]), skip))
        for chunk in engine.chunk(changes):
            batches.append({"kind": "cards", "changes": chunk})
    for chunk in engine.chunk([[line_change(ln, ref_of)] for ln in lines]):
        batches.append({"kind": "lines", "changes": chunk})
    groups = [g for g in m.groups if g in ref_of]
    chains = [c for c in m.chains if c in ref_of and c not in hubs and c not in groups]
    if groups or chains:
        batches.append({"kind": "children", "changes": [{"op": "add", "kind": "child", "activity": ref_of[g]} for g in groups + chains]})
    names = {b["id"]: b["name"] for b in plan_boxes}
    level = {"slug": TOP, "parent": None, "boxes": plan_boxes, "texts": texts, "lines": lines, "batches": batches,
             "hubs": hubs, "zones": {i: b.get("zone") for i, b in boxes.items()},
             "expect": expect_of(plan_boxes, lines, ref_of, names, texts, set(groups) | set(chains)), "chains": chains}
    return level, edges


def child_level(m, group, top_edges, top_ref_of, data, skip, warnings):
    style = data.style
    ids = [s["id"] for s in m.members[group]]
    internal, boundary = m.child_edges(group, top_edges)
    sizes = {i: {"w": m.cards[i]["w"], "h": m.cards[i]["h"]} for i in ids}
    boxes, order = column_layout(ids, sizes, internal, data)
    clearance = style["group_free_end_clearance"]
    pads = []
    if boxes:
        left = min(b["x"] for b in boxes.values())
        right = max(b["x"] + b["w"] for b in boxes.values())
        top = min(b["y"] for b in boxes.values())
        pads = [{"id": "pad-left", "x": left - clearance, "y": top, "w": 1, "h": 1},
                {"id": "pad-right", "x": right + clearance, "y": top, "w": 1, "h": 1}]
    engine.fit_blank(list(boxes.values()) + pads, style)
    sides = assign_sides(internal, boxes, [])
    # a line between members that are not next to each other goes round the cards between them, on the side where
    # fewer lines come in or go out of the drill-down (lines in arrive on the left, lines out leave on the right)
    ins = Counter(b["member"] for b in boundary if not b["out"])
    outs = Counter(b["member"] for b in boundary if b["out"])
    for edge in internal:
        if sides[edge["index"]] == OUTWARD["column"]:
            ends = (edge["from"], edge["to"])
            if sum(outs[e] for e in ends) <= sum(ins[e] for e in ends):
                sides[edge["index"]] = ("right", "right")
    plan_boxes = [plan_box(m.cards[i], boxes[i], engine.make_ref("s-", i)) for i in order]
    ref_of = {b["id"]: b["ref"] for b in plan_boxes}
    lines = []
    for edge in internal:
        start, end = shapes(edge["two_way"], style)
        side_from, side_to = sides[edge["index"]]
        lines.append({"ref": f"line{edge['index'] + 1}", "id": edge["id"], "from": edge["from"], "to": edge["to"],
                      "fromSide": side_from, "toSide": side_to, "startShape": start, "endShape": end, "label": edge["label"],
                      "twoWay": edge["two_way"]})
    boundary_lines, line_groups = [], []
    top_line_ref = {ln_id: ref for ln_id, ref in top_ref_of.items()}
    for n, item in enumerate(boundary, start=1):
        start, end = shapes(item["two_way"], style)
        change = {"op": "add", "kind": "line", "ref": f"boundary{n}", "label": item["label"], "startShape": start, "endShape": end}
        if item["out"]:
            change.update({"from": {"activity": ref_of[item["member"]]}, "to": None, "fromSide": "right"})
        else:
            change.update({"from": None, "to": {"activity": ref_of[item["member"]]}, "toSide": "left"})
        parent_ref = top_line_ref[item["parentEdge"]]
        entry = {"ref": change["ref"], "member": item["member"], "out": item["out"], "label": item["label"],
                 "startShape": start, "endShape": end, "parentRef": parent_ref, "linked": bool(item.get("linked"))}
        if item.get("linked"):
            change["parentLine"] = {"$parentLine": parent_ref}
            entry["boundary"] = parent_ref
            line_groups.append([{"op": "remove", "kind": "line", "key": {"$boundary": parent_ref}}, change])
        else:
            line_groups.append([change])
        boundary_lines.append(entry)
    batches = []
    for group_boxes in passes_for(plan_boxes, style):
        for chunk in engine.chunk([card_changes(b, m.systems.get(b["id"]), skip) for b in group_boxes]):
            batches.append({"kind": "cards", "changes": chunk})
    line_groups = [[line_change(ln, ref_of)] for ln in lines] + line_groups
    for chunk in engine.chunk(line_groups):
        batch = {"kind": "lines", "changes": chunk}
        if any(c["op"] == "remove" for c in chunk):
            batch["confirm"] = True   # removes only the lines add child seeded, which this batch adds again attached
        batches.append(batch)
    linked_refs = {ln["boundary"] for ln in boundary_lines if "boundary" in ln}
    names = {b["id"]: b["name"] for b in plan_boxes}
    expect = expect_of(plan_boxes, lines, ref_of, names,
                       boundary=[{"ref": ln["ref"], "member": ref_of[ln["member"]], "out": ln["out"], "label": ln["label"],
                                  "startShape": ln["startShape"], "endShape": ln["endShape"],
                                  "parentRef": ln["parentRef"] if ln["linked"] else None,
                                  "name": names[ln["member"]]} for ln in boundary_lines])
    unlinked = [ref for ref in {top_line_ref[e["id"]] for e in top_edges if group in (e["from"], e["to"])} if ref not in linked_refs]
    if unlinked:
        warnings.append(f"the drill-down of '{m.systems[group]['name']}' keeps {len(unlinked)} seeded line(s) no member continues")
    level = {"slug": group, "parent": group, "boxes": plan_boxes, "texts": [], "lines": lines + boundary_lines,
             "batches": batches, "hubs": [], "zones": {}, "expect": expect}
    return level


# ---------------------------------------------------------------- plan: a system's drill-down (system, middleware, automations, objects)

def automation_card(item, data, drop_icons):
    style = data.style
    row = data.automation_types.get(item.get("type")) or data.automation_types.get("other") or {}
    header = row.get("chain_resource") or None
    if header and norm(header) in drop_icons:
        header = None
    attributes = attribute_list(item.get("attributes") or [{"title": row.get("label") or "Automation"}], style)
    footer = footer_text(item.get("summary", ""), style)
    resources = [{"name": header, "type": row.get("chain_resource_type") or "Flow", "role": "header"}] if header else []
    return {"id": item["id"], "name": item["name"], "kind": "automation", "header": header, "icons": [], "resources": resources,
            "attributes": attributes, "footer": footer, "fill": None, "border": None,
            "w": card_width(0, style), "h": card_height(len(attributes), footer, 0, style)}


def object_card(item, data):
    style = data.style
    attributes = [{"title": item["apiName"]}] if item.get("apiName") and norm(item["apiName"]) != norm(item["name"]) else []
    attributes = attribute_list(attributes, style)
    kind = data.entity_kinds.get(item.get("kind") or "") or data.entity_kinds.get("") or {}
    return {"id": item["id"], "name": item["name"], "kind": "object", "header": None, "icons": [], "resources": [],
            "attributes": attributes, "footer": "", "fill": kind.get("fill") or None, "border": kind.get("border") or None,
            "w": card_width(0, style), "h": card_height(len(attributes), "", 0, style)}


def chain_lines(m, sid, chain, data):
    """The drill-down's lines as {(left, right, way): {"fwd", "back", "labels"}}: left is the card in the earlier column.
    Data moving toward the system side (the integration's 'to' is a card here) points left. Exchanges moving opposite
    ways between the same two cards are two lines, each with its own label (way "fwd" or "back"; "two" for an exchange
    that is two-way itself); what one automation does to one object is one line (way "touch")."""
    style = data.style
    col_of = {}
    for k, column in enumerate((chain["systems"], chain["middleware"], chain["automations"], chain["objects"])):
        for ident in column:
            col_of.setdefault(ident, k)
    autos = {a["id"] for a in m.model.get("automations", [])}
    ents = {e["id"] for e in m.model.get("entities", [])}
    touch = defaultdict(set)
    for x in m.model.get("interactions", []):
        if x["from"] in autos and x["to"] in ents:
            touch[(x["from"], x["to"])].add(x["kind"])
        elif x["from"] in ents and x["to"] in autos:
            touch[(x["to"], x["from"])].add(x["kind"])
    pairs = OrderedDict()
    shown = {o for (a, o) in touch if a in chain["automations"]}

    def add(a, b, toward_a, two_way, label="", touch_line=False):
        if a not in col_of or b not in col_of or a == b:
            return
        if col_of[a] > col_of[b]:
            a, b, toward_a = b, a, not toward_a
        way = "touch" if touch_line else "two" if two_way else "back" if toward_a else "fwd"
        entry = pairs.setdefault((a, b, way), {"fwd": False, "back": False, "labels": []})
        if two_way:
            entry["fwd"] = entry["back"] = True
        elif toward_a:
            entry["back"] = True
        else:
            entry["fwd"] = True
        if label and label not in entry["labels"]:
            entry["labels"].append(label)

    middleware = sid in chain["middleware"]
    for item in chain["integrations"]:
        two = item["two_way"]
        toward_system = item["to"] in col_of
        if middleware and item.get("via") == sid and sid not in (item["from"], item["to"]):
            for end in (item["from"], item["to"]):
                if end in col_of and col_of[end] == 0:
                    add(end, sid, item["to"] == end, two, item["text"])
            continue
        other = item["to"] if item["from"] == sid else item["from"]
        path = [other, sid] if middleware and other in col_of else [sid]
        if not middleware:
            if item.get("via") in col_of:
                path.append(item["via"])
            if other in col_of and other not in path:
                path.append(other)
        for a, b in zip(path, path[1:]):
            add(a, b, toward_system, two, item["text"])
        anchor = path[-1]
        label = item["text"] if len(path) == 1 else ""
        for auto in item.get("automations", []):
            add(anchor, auto, toward_system, two, label)
            for obj in item.get("objects", []):
                kinds = touch.get((auto, obj))
                if not kinds:
                    continue
                words = [style[f"chain_{k}_label"] for k in ("triggers", "reads", "writes") if k in kinds]
                into_auto = bool(kinds & {"reads", "triggers"})
                add(auto, obj, into_auto and "writes" not in kinds, into_auto and "writes" in kinds, ", ".join(words), True)
        if not item.get("automations"):
            # an exchange no automation carries joins its objects directly, unless an automation on the level already
            # shows the object: that line would cross the automations column and say nothing new
            for obj in item.get("objects", []):
                if obj not in shown:
                    add(anchor, obj, toward_system, two, label)
    return pairs, col_of



SHARING_EXACT = 8   # automations in a lane up to which every drawing order is tried (8! orders, well under a second)


def sharing_order(items, objs_of, autos_on):
    """A lane's automations in drawing order: the order that keeps the automations of each object closest together
    (the least total spread, over the objects, from the first to the last automation using it), so an object sits
    beside or between the automations it joins; automations with no object come last. Every order is tried for up to
    SHARING_EXACT automations, beyond that the best single moves from the model order. Model order breaks ties."""
    order = {a: n for n, a in enumerate(items)}
    with_objects = [a for a in items if objs_of[a]]
    groups = [[a for a in autos_on[o] if a in order] for o in {o for a in with_objects for o in objs_of[a]}]
    groups = [g for g in groups if len(g) > 1]

    def cost(seq):
        where = {a: n for n, a in enumerate(seq)}
        return (sum(max(where[a] for a in g) - min(where[a] for a in g) for g in groups), [order[a] for a in seq])
    if len(with_objects) <= SHARING_EXACT:
        best = min(itertools.permutations(with_objects), key=cost) if with_objects else ()
    else:
        best, improved = list(with_objects), True
        while improved:
            improved = False
            for i in range(len(best)):
                for j in range(len(best)):
                    if i == j:
                        continue
                    trial = best[:i] + best[i + 1:]
                    trial.insert(j, best[i])
                    if cost(trial) < cost(best):
                        best, improved = trial, True
    return list(best) + [a for a in items if not objs_of[a]]


def spread(items, gap):
    """Tops for cards stacked in one column, in the order given: each as near its wanted top as the cards around it
    allow, with at least gap between cards (a run of cards that would overlap moves as one, centred on what its
    cards want). items: (id, wanted top, height)."""
    blocks = []
    for ident, top, h in items:
        block = {"members": [(ident, top, h)], "offsets": [0.0], "height": h}
        block["top"] = top
        while blocks and blocks[-1]["top"] + blocks[-1]["height"] + gap > block["top"]:
            prev = blocks.pop()
            offsets = prev["offsets"] + [prev["height"] + gap + off for off in block["offsets"]]
            members = prev["members"] + block["members"]
            block = {"members": members, "offsets": offsets, "height": prev["height"] + gap + block["height"]}
            block["top"] = sum(t - off for (_, t, _), off in zip(members, offsets)) / len(members)
        blocks.append(block)
    return {ident: block["top"] + off for block in blocks for (ident, _, _), off in zip(block["members"], block["offsets"])}


def chain_level(m, sid, top_edges, top_ref_of, data, skip, warnings, drop_icons):
    style = data.style
    chain = m.chains[sid]
    autos = {a["id"]: a for a in m.model.get("automations", [])}
    ents = {e["id"]: e for e in m.model.get("entities", [])}
    cards = {}
    for ident in chain["systems"] + chain["middleware"]:
        cards[ident] = m.cards[ident]
    for ident in chain["automations"]:
        cards[ident] = automation_card(autos[ident], data, drop_icons)
    for ident in chain["objects"]:
        cards[ident] = object_card(ents[ident], data)
    pairs, col_of = chain_lines(m, sid, chain, data)
    autos_here = set(chain["automations"])
    # an object only an exchange with no automation joins sits in the automations column, in line with what joins it
    lonely = [o for o in chain["objects"] if not any(b == o and a in autos_here for (a, b, _) in pairs)]
    mids = list(chain["middleware"])

    def lane(ident):
        """0 for what joins a system directly, 1 + n for what the n-th middleware joins: each middleware sits beside its
        own automations, so a system's direct lines never cross a middleware card."""
        return next((1 + mids.index(a) for (a, b, _) in pairs if b == ident and a in mids), 0)
    objects = [o for o in chain["objects"] if o not in lonely]
    autos_on, objs_of = defaultdict(list), defaultdict(list)
    for (a, b, _) in pairs:
        if a in autos_here and b in objects and a not in autos_on[b]:
            autos_on[b].append(a)
            objs_of[a].append(b)
    # each lane's automations ordered so that automations sharing an object sit next to each other
    middle = []
    for n in sorted({lane(i) for i in list(chain["automations"]) + lonely}):
        middle += sharing_order([i for i in list(chain["automations"]) + lonely if lane(i) == n], objs_of, autos_on)
    gap = style["chain_stack_gap"] + style["editor_growth_allowance"]

    def stacked(column, mid_y):
        total = sum(cards[i]["h"] for i in column) + gap * (len(column) - 1)
        y, out = mid_y - total / 2, {}
        for ident in column:
            out[ident] = y
            y += cards[ident]["h"] + gap
        return out
    # One sweep down both columns. Each automation sits as high as it can, but low enough that its objects fit
    # level with it: its own objects (no other automation uses them) stacked around it, or on the side away from an
    # object it shares (starting level with it and going down when the shared object is above, ending level with it
    # when it is below). An object two or more automations use is placed with the last of them, as near the middle of
    # their centres as the objects above it allow; when it is shared only with the automation just above, this
    # automation moves down so the object sits midway.
    index = {a: n for n, a in enumerate(middle)}
    last_of = {o: max(autos_on[o], key=index.get) for o in objects if autos_on[o]}

    def stack_height(items):
        return sum(cards[o]["h"] for o in items) + gap * (len(items) - 1) if items else 0.0
    ys, centre, column = {}, {}, []
    auto_floor = obj_floor = None
    for a in middle:
        shared_here = [o for o in objs_of[a] if len(autos_on[o]) > 1 and last_of.get(o) == a]
        own = [o for o in objs_of[a] if len(autos_on[o]) == 1]
        c = 0.0 if auto_floor is None else auto_floor + cards[a]["h"] / 2
        floor = obj_floor
        # the shared block's centre is the mean, over its objects, of the mean centre of each one's automations:
        # base + c * weight, where c is this automation's centre
        base = sum(sum(centre[b] for b in autos_on[o] if b != a) / len(autos_on[o]) for o in shared_here) / max(len(shared_here), 1)
        weight = sum(1 / len(autos_on[o]) for o in shared_here) / max(len(shared_here), 1)
        between = all(len(autos_on[o]) == 2 and index[a] - min(index[b] for b in autos_on[o]) == 1 for o in shared_here)
        if shared_here and floor is not None and between:
            # an object shared with the automation just above sits midway: this automation moves down to make room
            c = max(c, (floor + stack_height(shared_here) / 2 - base) / weight)
        if shared_here:
            mean = base + c * weight
            top = mean - stack_height(shared_here) / 2
            if floor is not None:
                top = max(top, floor)
            for o in shared_here:
                ys[o] = top
                column.append(o)
                top += cards[o]["h"] + gap
            floor = top
        if own:
            shares_below = any(index[last_of[o]] > index[a] for o in objs_of[a] if len(autos_on[o]) > 1)
            if shared_here:
                lead = cards[own[0]]["h"] / 2                          # level with it, going down
            elif shares_below:
                lead = stack_height(own) - cards[own[-1]]["h"] / 2     # level with it, going up
            else:
                lead = stack_height(own) / 2                           # centred on it
            if floor is not None:
                c = max(c, floor + lead)
            top = c - lead
            for o in own:
                ys[o] = top
                column.append(o)
                top += cards[o]["h"] + gap
            floor = top
        centre[a] = c
        ys[a] = c - cards[a]["h"] / 2
        auto_floor = c + cards[a]["h"] / 2 + gap
        obj_floor = floor
    column += [o for o in objects if o not in ys]
    for o in column:
        ys.setdefault(o, 0.0)
    shift = (min(ys[i] for i in middle + column) + max(ys[i] + cards[i]["h"] for i in middle + column)) / 2 if ys else 0
    ys = {i: y - shift for i, y in ys.items()}
    columns = [list(chain["systems"]), mids, middle, column]
    spans = defaultdict(list)
    for ident in middle:
        spans[lane(ident)] += [ys[ident], ys[ident] + cards[ident]["h"]]
    want = {}
    for n, mid in enumerate(mids):
        span = spans.get(1 + n)
        want[mid] = ((min(span) + max(span)) / 2 if span else 0) - cards[mid]["h"] / 2
    floor = None
    for mid in sorted(mids, key=lambda i: want[i]):
        y = want[mid] if floor is None else max(want[mid], floor)
        ys[mid] = y
        floor = y + cards[mid]["h"] + gap
    systems = columns[0]
    if len(systems) == 1:
        span = spans.get(0)
        if span:
            mid_y = (min(span) + max(span)) / 2
        elif mids:
            mid_y = sum(ys[i] + cards[i]["h"] / 2 for i in mids) / len(mids)
        else:
            mid_y = 0
        ys[systems[0]] = mid_y - cards[systems[0]]["h"] / 2
    elif systems:
        mid_y = sum(ys[i] + cards[i]["h"] / 2 for i in mids) / len(mids) if mids else 0
        ys.update(stacked(systems, mid_y))
    boxes, x = {}, 0
    for k, column in enumerate(columns):
        if not column:
            continue
        width = max(cards[i]["w"] for i in column)
        for n, ident in enumerate(column):
            boxes[ident] = {"id": ident, "x": int(round(x)), "y": int(round(ys[ident])), "w": cards[ident]["w"], "h": cards[ident]["h"],
                            "zone": f"col{k}", "slot": k, "pos": n}
        x += width + style["chain_col_gap"]
    count = len(boxes)
    if count > style["max_cards_per_level"]:
        warnings.append(f"the drill-down of '{m.systems[sid]['name']}' has {count} cards; above {style['max_cards_per_level']} it is hard to read")
    engine.fit_blank(list(boxes.values()), style)
    order = [i for column in columns for i in column]
    plan_boxes = [plan_box(cards[i], boxes[i], engine.make_ref("s-", i), "chain") for i in order]
    ref_of = {b["id"]: b["ref"] for b in plan_boxes}
    lines = []
    for n, ((a, b, way), entry) in enumerate(pairs.items(), start=1):
        two_way = entry["fwd"] and entry["back"]
        src, dst = (a, b) if (entry["fwd"] or two_way) else (b, a)
        start, end = shapes(two_way, style)
        sides = ("right", "left") if src == a else ("left", "right")
        label = "; ".join(entry["labels"][:2]) + ("…" if len(entry["labels"]) > 2 else "")
        lines.append({"ref": f"line{n}", "id": f"{a}>{b}" + ("" if way in ("fwd", "touch") else f":{way}"), "from": src, "to": dst, "fromSide": sides[0], "toSide": sides[1],
                      "startShape": start, "endShape": end, "label": label, "twoWay": two_way})
    line_sides = {n: (ln["fromSide"], ln["toSide"]) for n, ln in enumerate(lines)}
    separate_parallel([{"index": n, "from": ln["from"], "to": ln["to"]} for n, ln in enumerate(lines)], boxes, line_sides)
    for n, ln in enumerate(lines):
        ln["fromSide"], ln["toSide"] = line_sides[n]
    seeded = [top_ref_of[e["id"]] for e in top_edges if sid in (e["from"], e["to"]) and e["id"] in top_ref_of]
    item_of = {}
    for i in chain["systems"] + chain["middleware"]:
        item_of[i] = m.systems.get(i)
    for i in chain["automations"]:
        item_of[i] = autos[i]
    for i in chain["objects"]:
        item_of[i] = ents[i]
    batches = []
    for group_boxes in passes_for(plan_boxes, style):
        for chunk in engine.chunk([card_changes(b, item_of.get(b["id"]), skip) for b in group_boxes]):
            batches.append({"kind": "cards", "changes": chunk})
    removals = [[{"op": "remove", "kind": "line", "key": {"$seeded": ref}}] for ref in seeded]
    for k, chunk in enumerate(engine.chunk(removals + [[line_change(ln, ref_of)] for ln in lines])):
        batch = {"kind": "lines", "changes": chunk}
        if any(c["op"] == "remove" for c in chunk):
            batch["confirm"] = True   # removes only the free-ended copies add child seeded; the drill-down draws its own lines
        batches.append(batch)
    names = {b["id"]: b["name"] for b in plan_boxes}
    level = {"slug": sid, "parent": sid, "kind": "chain", "boxes": plan_boxes, "texts": [], "lines": lines, "batches": batches,
             "hubs": [], "zones": {}, "seeded": seeded, "expect": expect_of(plan_boxes, lines, ref_of, names)}
    return level


def preflight(levels, model):
    """engine.preflight_batches, with every icon added as a footer icon: a header would replace the one before it.
    Footer icons widen a card, so each throwaway card carries fewer of them than on a process map."""
    batches = engine.preflight_batches(levels, model, per_box=PREFLIGHT_BOX_ICONS)
    for batch in batches:
        for change in batch["changes"]:
            change.pop("role", None)
    return batches


def plan(model, key=None, headings=None, drop_icons=(), skip=frozenset(), create_resources=False, name=None, drop_unresolved=False):
    data = Data()
    warnings = []
    drop = {norm(n) for n in drop_icons}
    m = Model(model, data, drop, warnings)
    key = yes(data.style["key"]) if key is None else key
    headings = yes(data.style["zone_headings"]) if headings is None else headings
    top, edges = top_level(m, data, key, headings, skip, warnings)
    levels = [top]
    top_ref_of = {ln["id"]: ln["ref"] for ln in top["lines"]}
    for group in m.groups:
        if m.parent.get(group) is None:
            levels.append(child_level(m, group, edges, top_ref_of, data, skip, warnings))
    for sid in top.get("chains", []):
        levels.append(chain_level(m, sid, edges, top_ref_of, data, skip, warnings, drop))
    for level in levels:
        level["writes"] = sum(1 for b in level["batches"] if b["kind"] == "cards")
    meta = model.get("meta", {})
    result = {"planVersion": 1, "mode": "create", "diagramType": DIAGRAM_TYPE, "mapType": MAP_TYPE,
              "mapName": map_name(name if name is not None else meta.get("title") or "System architecture"),
              "mapDescription": meta.get("description", "")[:5000], "createResources": create_resources,
              "levels": levels, "preflight": preflight(levels, model),
              "warnings": engine.dedupe(warnings), "gaps": model.get("gaps", [])}
    if drop_unresolved:
        result["dropUnresolved"] = True
    result["planId"] = engine.plan_id(result)
    return result


# ---------------------------------------------------------------- preview

def preview_svg(level):
    boxes = level["boxes"]
    texts = level.get("texts", [])
    if not boxes:
        return "<svg xmlns='http://www.w3.org/2000/svg'/>"
    by_id = {b["id"]: b for b in boxes}
    every = boxes + texts
    x0 = min(b["x"] for b in every) - 140
    y0 = min(b["y"] for b in every) - 80
    x1 = max(b["x"] + b["w"] for b in every) + 140
    y1 = max(b["y"] + b["h"] for b in every) + 80
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{x0} {y0} {x1 - x0} {y1 - y0}' width='{x1 - x0}' height='{y1 - y0}' "
           "font-family='sans-serif'>", f"<rect x='{x0}' y='{y0}' width='{x1 - x0}' height='{y1 - y0}' fill='#ffffff'/>",
           "<defs><marker id='arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
           "<path d='M0,0 L10,5 L0,10 z' fill='#5a6b7b'/></marker></defs>"]
    for line in level["lines"]:
        if "member" in line:
            b = by_id.get(line["member"])
            if not b:
                continue
            p = engine.side_point(b, "right" if line["out"] else "left")
            q = (p[0] + (80 if line["out"] else -80), p[1])
            pts = [p, q] if line["out"] else [q, p]
        else:
            a, b = by_id.get(line["from"]), by_id.get(line["to"])
            if not a or not b:
                continue
            pts = engine.route(a, line["fromSide"], b, line["toSide"])
        start = " marker-start='url(#arrow)'" if line["startShape"] != "none" else ""
        out.append("<polyline fill='none' stroke='#5a6b7b' stroke-width='1.5' marker-end='url(#arrow)'" + start + " points='"
                   + " ".join(f"{px:.0f},{py:.0f}" for px, py in pts) + "'/>")
        if line.get("label"):
            mid = midpoint(pts)
            out.append(f"<text x='{mid[0]:.0f}' y='{mid[1] - 4:.0f}' font-size='10' fill='#333' text-anchor='middle'>"
                       f"{html.escape(line['label'][:40])}</text>")
    for b in boxes:
        fill, border = b.get("fill") or "#ffffff", b.get("border") or "#1b1b1b"
        out.append(f"<rect x='{b['x']}' y='{b['y']}' width='{b['w']}' height='{b['h']}' rx='10' fill='{fill}' stroke='{border}' stroke-width='2'/>")
        if b.get("header"):
            out.append(f"<circle cx='{b['x'] + 24}' cy='{b['y'] + 24}' r='14' fill='#032d60'/>")
        out.append(f"<text x='{b['x'] + (46 if b.get('header') else 12)}' y='{b['y'] + 29}' font-size='13' font-weight='bold'>"
                   f"{html.escape(b['name'][:24])}</text>")
        y = b["y"] + 62
        for a in b["attributes"]:
            out.append(f"<text x='{b['x'] + 14}' y='{y}' font-size='11'>{html.escape(a['title'][:30])}</text>")
            y += 26
        if b.get("footer") or b.get("icons"):
            fy = b["y"] + b["h"] - (65 if b.get("footer") and b.get("icons") else 40)
            out.append(f"<line x1='{b['x']}' y1='{fy}' x2='{b['x'] + b['w']}' y2='{fy}' stroke='#cccccc'/>")
            if b.get("footer"):
                out.append(f"<text x='{b['x'] + 10}' y='{fy + 22}' font-size='11' font-style='italic' fill='#555'>{html.escape(b['footer'][:30])}</text>")
            for k, _ in enumerate(b.get("icons", [])):
                out.append(f"<circle cx='{b['x'] + 20 + 30 * k}' cy='{b['y'] + b['h'] - 18}' r='10' fill='#7a8fa3'/>")
    for t in texts:
        out.append(f"<text x='{t['x']}' y='{t['y'] + 20}' font-size='14' font-weight='bold' fill='#032d60'>{html.escape(t['text'])}</text>")
    out.append("</svg>")
    return "\n".join(out)


def midpoint(points):
    lengths = [abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(points, points[1:])]
    half = sum(lengths) / 2
    for (p, q), length in zip(zip(points, points[1:]), lengths):
        if half <= length and length:
            t = half / length
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        half -= length
    return points[len(points) // 2]


# ---------------------------------------------------------------- reading a drawn diagram

def header_of(act):
    for res in act.get("resources", []):
        if res.get("role") == "header":
            return res.get("name")
    return None


def footer_icons_of(act):
    return [res.get("name") for res in act.get("resources", []) if res.get("role") == "footer"]


def parse_label(label, data):
    """step, text, timing and inferred from a drawn line label."""
    text = " ".join((label or "").split())
    out = {}
    if text.endswith("(inferred)"):
        out["inferred"] = True
        text = text[:-len("(inferred)")].rstrip()
    found = re.match(r"^(\d+)\.\s+(.*)$", text)
    if found:
        out["step"] = int(found.group(1))
        text = found.group(2)
    sep = data.style["label_separator"].strip()
    words = {squash(row["word"]): timing for timing, row in data.timing.items()}   # the server wraps "real- time"
    if sep and sep in text:
        head, tail = text.rsplit(sep, 1)
        if squash(tail) in words:
            out["timing"] = words[squash(tail)]
            text = head.strip()
    elif squash(text) in words:
        out["timing"] = words[squash(text)]
        text = ""
    if text:
        out["label"] = text[:200]
    return out


def kind_from_card(act, data):
    icon = header_of(act)
    for row in data.icons:
        if icon and norm(row["icon"]) == norm(icon) and row["kind_list"]:
            return row["kind_list"][0], False
    fill = (act.get("fill") or "").lower()
    for kind, row in data.kinds.items():
        if fill and (row.get("fill") or "").lower() == fill:
            return kind, True
    return ("salesforce" if re.search(r"salesforce|cloud|\borg\b", act.get("text") or "", re.IGNORECASE) else "channel"), True


def from_diagram(reads):
    """A model file from reads of an existing system architecture: the top level first, then any drill-down levels."""
    data = Data()
    reads = [engine.unwrap(r) for r in reads]
    top = reads[0]
    for read in reads:
        if read.get("subtype") not in (None, SUBTYPE, "systemArchitecture"):
            raise PlanError(f"the level '{read.get('title')}' is a {read.get('subtype')} diagram, not a system architecture")
    used, systems, id_of, gaps, integrations = set(), [], {}, [], []
    acts = [a for a in top.get("activities", []) if norm(a.get("text")) != norm(KEY_NAME)]
    count = Counter()
    for line in top.get("lines", []):
        for end in ("from", "to"):
            key = (line.get(end) or {}).get("activity")
            if key is not None:
                count[key] += 1
    # the hubs: the card with the most lines, and any card stacked in the same column with two or more lines
    hub_keys = set()
    if acts:
        first = max(acts, key=lambda a: count[a["key"]])
        hub_keys.add(first["key"])
        if "x" in first:
            centre = first["x"] + first.get("w", 0) / 2
            for act in acts:
                if "x" in act and abs(act["x"] + act.get("w", 0) / 2 - centre) <= 10 and count[act["key"]] >= 2:
                    hub_keys.add(act["key"])
    hub_boxes = [a for a in acts if a["key"] in hub_keys and "x" in a]

    def system_of(act, parent=None):
        text = " ".join((act.get("text") or "").split())
        if not text:
            gaps.append({"note": f"Card {act.get('key')} has no text, so it is not in the model"})
            return None
        ident = engine.slug(text, used)
        kind, guessed = kind_from_card(act, data)
        item = {"id": ident, "name": text[:200], "kind": kind}
        if guessed:
            gaps.append({"about": ident, "note": f"The kind of '{text}' ({kind}) was guessed from its colour; check it"})
        if parent:
            item["parent"] = parent
        if header_of(act):
            item["icon"] = header_of(act)
        attributes = [{k: v for k, v in (("title", " ".join((a.get("title") or "").split())[:200]),
                                         ("description", (a.get("description") or "")[:400])) if v}
                      for a in act.get("attributes", []) if (a.get("title") or "").strip()]
        if attributes:
            item["attributes"] = attributes
        if act.get("footerText"):
            item["footer"] = " ".join(act["footerText"].split())[:1000]
        icons = footer_icons_of(act)
        if icons:
            item["footerIcons"] = icons
        return item

    for act in acts:
        item = system_of(act)
        if not item:
            continue
        if act["key"] in hub_keys:
            item["hub"] = True
        elif hub_boxes and "x" in act:
            left = min(b["x"] for b in hub_boxes)
            right = max(b["x"] + b["w"] for b in hub_boxes)
            hub_top = min(b["y"] for b in hub_boxes)
            if act["x"] + act.get("w", 0) <= left:
                item["zone"] = "left"
            elif act["x"] >= right:
                item["zone"] = "right"
            else:
                item["zone"] = "top" if act["y"] < hub_top else "bottom"
        id_of[act["key"]] = item["id"]
        systems.append(item)

    def integration_of(line, a, b):
        start, end = line.get("startShape") or "none", line.get("endShape") or "none"
        if start != "none" and end != "none":
            item = {"from": a, "to": b, "direction": "two-way"}
        elif start != "none":
            item = {"from": b, "to": a}
        else:
            item = {"from": a, "to": b}
        item.update(parse_label(line.get("label"), data))
        return item

    top_lines = {}
    for line in top.get("lines", []):
        a = id_of.get((line.get("from") or {}).get("activity"))
        b = id_of.get((line.get("to") or {}).get("activity"))
        if not a or not b:
            gaps.append({"note": f"Line {line.get('key')} does not join two system cards, so it is not in the model"})
            continue
        top_lines[line["key"]] = integration_of(line, a, b)
    replaced = set()
    for read in reads[1:]:
        boundary = read.get("boundary") or {}
        parent_name = norm(((boundary.get("activity") or {}).get("text")) or read.get("title"))
        parent = next((s for s in systems if norm(s["name"]) == parent_name and not s.get("parent")), None)
        if parent is None:
            gaps.append({"note": f"The drill-down '{read.get('title')}' belongs to no card on the top level read; it is not in the model"})
            continue
        child_id = {}
        for act in read.get("activities", []):
            item = system_of(act, parent["id"])
            if item:
                child_id[act["key"]] = item["id"]
                systems.append(item)
        for line in read.get("lines", []):
            a = child_id.get((line.get("from") or {}).get("activity"))
            b = child_id.get((line.get("to") or {}).get("activity"))
            if a and b:
                integrations.append(integration_of(line, a, b))
                continue
            member = a or b
            if not member:
                continue
            parent_line = top_lines.get(line.get("parentLine"))
            if not parent_line:
                gaps.append({"note": f"Line {line.get('key')} on the drill-down of '{parent['name']}' continues no top-level line; it is not in the model"})
                continue
            moved = dict(parent_line)
            if moved["from"] == parent["id"]:
                moved["from"] = member
            elif moved["to"] == parent["id"]:
                moved["to"] = member
            integrations.append(moved)
            replaced.add(line["parentLine"])
    integrations = [item for key, item in top_lines.items() if key not in replaced] + integrations
    title = " ".join((top.get("title") or "").split())[:80]
    model = {"schemaVersion": "1.0",
             "meta": {"title": title if len(title) >= 2 else "System architecture", "author": "draw-system-architecture (from-diagram)",
                      "sources": [{"kind": "diagram", "ref": top.get("mapId") or top.get("diagramId") or "unknown"}]}}
    if top.get("description"):
        model["meta"]["description"] = top["description"][:5000]
    if systems:
        model["systems"] = systems
    if integrations:
        model["integrations"] = integrations
    if gaps or not systems:
        model["gaps"] = gaps or [{"note": "The diagram has no system cards"}]
    return model


# ---------------------------------------------------------------- amend: change an existing diagram's top level

def zone_spot(ident, zone, final, zones_now, hub_box, size, occupied, canvas, style):
    """A free place for a new card in its zone: after the last card already in that zone, else beside the hub."""
    w, h = size
    peers = [b for i, b in final.items() if zones_now.get(i) == zone]
    candidates = []
    if peers:
        if zone in ("left", "right"):
            last = max(peers, key=lambda b: b["y"] + b["h"])
            first = min(peers, key=lambda b: b["y"])
            x = last["x"] + last["w"] - w if zone == "left" else last["x"]
            candidates += [(x, last["y"] + last["h"] + style["zone_stack_gap"] + style["editor_growth_allowance"]),
                           (x, first["y"] - style["zone_stack_gap"] - style["editor_growth_allowance"] - h)]
        else:
            last = max(peers, key=lambda b: b["x"] + b["w"])
            first = min(peers, key=lambda b: b["x"])
            y = last["y"] + last["h"] - h if zone == "top" else last["y"]
            candidates += [(last["x"] + last["w"] + style["zone_row_gap"], y), (first["x"] - style["zone_row_gap"] - w, y)]
    if hub_box:
        hx, hy, hw, hh = hub_box["x"], hub_box["y"], hub_box["w"], hub_box["h"]
        candidates.append({"left": (hx - style["hub_gap_x"] - w, hy + hh / 2 - h / 2),
                           "right": (hx + hw + style["hub_gap_x"], hy + hh / 2 - h / 2),
                           "top": (hx + hw / 2 - w / 2, hy - style["hub_gap_y"] - h),
                           "bottom": (hx + hw / 2 - w / 2, hy + hh + style["hub_gap_y"])}[zone])
    margin = style["zone_stack_gap"] / 2
    for x, y in candidates:
        box = {"x": int(x), "y": int(y), "w": w, "h": h}
        if engine.inside(box, canvas) and not any(engine.overlaps(box, o, margin) for o in occupied):
            return box["x"], box["y"]
    return engine.free_spot(peers[-1] if peers else hub_box, size, occupied, canvas, style)


def amend(model, read, allow_remove=False, relayout=False, drop_icons=(), skip=frozenset(), create_resources=False):
    read = engine.unwrap(read)
    if read.get("subtype") not in (None, SUBTYPE, "systemArchitecture"):
        raise PlanError(f"the level is a {read.get('subtype')} diagram, not a system architecture")
    if read.get("boundary"):
        raise PlanError("the read is a drill-down level; amend works on the top level: read it by its mapId and levelNumber 1")
    data = Data()
    style = data.style
    warnings = []
    m = Model(model, data, {norm(n) for n in drop_icons}, warnings)
    ids = m.level_ids(None)
    cards = {i: m.cards[i] for i in ids}
    edges = m.top_edges()
    acts = list(read.get("activities", []))
    names = {norm(c["name"]) for c in cards.values()}
    key_act = next((a for a in acts if norm(a.get("text")) == norm(KEY_NAME) and norm(KEY_NAME) not in names), None)
    pool = [a for a in acts if a is not key_act]
    match = {}
    for ident in ids:
        act = next((a for a in pool if norm(a.get("text")) == norm(cards[ident]["name"])), None)
        if act is not None:
            match[ident] = act
            pool.remove(act)
    extra = pool
    new_ids = [i for i in ids if i not in match]
    canvas = tuple((read.get("canvas") or {}).get(k) for k in ("x", "y", "w", "h"))
    if None in canvas:
        raise PlanError("the read has no canvas; read the level with include [\"layout\"]")
    canvas = (canvas[0], canvas[1], canvas[0] + canvas[2], canvas[1] + canvas[3])
    summary = {k: [] for k in ("addCards", "updateCards", "removeCards", "keepCards", "addLines", "updateLines", "removeLines", "keepLines")}
    removals, updates, line_ops, key_ops = [], [], [], []
    removed_keys = set()
    if allow_remove:
        for act in extra:
            removals.append({"op": "remove", "kind": "activity", "key": act["key"]})
            removed_keys.add(act["key"])
            summary["removeCards"].append(act.get("text"))
    else:
        summary["keepCards"] = [a.get("text") for a in extra]
    final, expect_cards = {}, []
    for ident, act in match.items():
        card = cards[ident]
        changed = []
        ops, kept, titles = engine.simulate_attributes(act.get("attributes", []), card["attributes"], allow_remove)
        for op in ops:
            if op["op"] == "remove":
                updates.append({"op": "remove", "kind": "attribute", "activity": act["key"], "key": op["key"]})
                changed.append(f"remove attribute {op['title']}")
            elif op["op"] == "add":
                change = {"op": "add", "kind": "attribute", "activity": act["key"], "title": op["title"], "position": op["position"]}
                if op["description"]:
                    change["description"] = op["description"]
                updates.append(change)
                changed.append(f"add attribute {op['title']}")
            else:
                change = {"op": "update", "kind": "attribute", "activity": act["key"], "key": op["key"]}
                for k in ("description", "position"):
                    if k in op:
                        change[k] = op[k]
                updates.append(change)
                changed.append(f"update attribute {op['title']}")
        if kept:
            changed.append(f"keep attributes not in the model: {', '.join(kept)}")
        update = {"op": "update", "kind": "activity", "key": act["key"]}
        footer = act.get("footerText") or ""
        if norm(footer) != norm(card["footer"]) and (card["footer"] or allow_remove):
            update["footerText"] = card["footer"]
            footer = card["footer"]
            changed.append(f"footer {card['footer'] or '(cleared)'}")
        if (act.get("fill") or None) != (card["fill"] or None) or (act.get("border") or None) != (card["border"] or None):
            if (act.get("fill") or "").lower() != (card["fill"] or "").lower() or (act.get("border") or "").lower() != (card["border"] or "").lower():
                update["fill"], update["border"] = card["fill"], card["border"]
                changed.append(f"colour for {card['kind'] or 'its kind'}")
        if len(update) > 3:
            updates.append(update)
        header_now, icons_now = header_of(act), footer_icons_of(act)
        header = header_now
        if card["header"] and norm(card["header"]) != norm(header_now):
            updates.append({"op": "add", "kind": "resource", "activity": act["key"], "name": card["header"],
                            "type": data.icon_type.get(norm(card["header"]), "System"), "role": "header"})
            changed.append(f"header icon {card['header']}")
            if header_now:
                icons_now = icons_now + [header_now]   # the header before it becomes a footer icon
            header = card["header"]
        wanted = [norm(i) for i in card["icons"]]
        for icon in card["icons"]:
            if norm(icon) not in [norm(i) for i in icons_now] and norm(icon) != norm(header):
                updates.append({"op": "add", "kind": "resource", "activity": act["key"], "name": icon,
                                "type": data.icon_type.get(norm(icon), "System"), "role": "footer"})
                icons_now = icons_now + [icon]
                changed.append(f"footer icon {icon}")
        for icon in list(icons_now):
            if norm(icon) not in wanted and (allow_remove or (header_now and norm(icon) == norm(header_now) and card["header"])):
                updates.append({"op": "remove", "kind": "resource", "activity": act["key"], "name": icon})
                icons_now.remove(icon)
                changed.append(f"remove icon {icon}")
        if changed:
            summary["updateCards"].append(f"{card['name']}: " + "; ".join(changed))
        n_icons = len(icons_now)
        height = max(act.get("h") or 0, card_height(len(titles), footer, n_icons, style))
        final[ident] = {"id": ident, "key": act["key"], "x": act.get("x", 0), "y": act.get("y", 0),
                        "w": max(act.get("w") or style["card_width"], card_width(n_icons, style)), "h": height}
        expect_cards.append({"key": act["key"], "name": card["name"], "header": header, "icons": None,
                             "attributes": titles, "footer": footer})
        if act.get("h") and height > act["h"] + TOLERANCE:
            grown = dict(final[ident])
            hit = [a.get("text") for a in acts if a is not act and a.get("key") not in removed_keys and "x" in a and engine.overlaps(grown, a)]
            if hit:
                warnings.append(f"'{card['name']}' grows to {height} px and will overlap {', '.join(hit)}; amend with --relayout or move the cards in Elements")
    others = [dict(a) for a in extra if a["key"] not in removed_keys and "x" in a]
    if key_act is not None and "x" in key_act:
        others.append(dict(key_act))
    for item in read.get("notes", []) + read.get("texts", []):
        if "x" in item:
            others.append(dict(item))
    # where the new cards go
    sizes = {i: {"w": final[i]["w"], "h": final[i]["h"]} if i in final else {"w": cards[i]["w"], "h": cards[i]["h"]} for i in ids}
    boxes, hubs, zones, flows, _ = zone_layout(ids, sizes, m.systems, edges, data, warnings)
    refs = {i: engine.make_ref("s-", i) for i in new_ids}
    moves = {}
    if relayout:
        content = list(final.values()) or [{"x": canvas[0], "y": canvas[1], "w": 0, "h": 0}]
        ccx = (min(b["x"] for b in content) + max(b["x"] + b["w"] for b in content)) / 2
        ccy = (min(b["y"] for b in content) + max(b["y"] + b["h"] for b in content)) / 2
        nx0, nx1 = min(b["x"] for b in boxes.values()), max(b["x"] + b["w"] for b in boxes.values())
        ny0, ny1 = min(b["y"] for b in boxes.values()), max(b["y"] + b["h"] for b in boxes.values())
        dx, dy = int(round(ccx - (nx0 + nx1) / 2)), int(round(ccy - (ny0 + ny1) / 2))
        for ident, box in boxes.items():
            target = {"x": box["x"] + dx, "y": box["y"] + dy, "w": box["w"], "h": box["h"]}
            if ident in final:
                if abs(target["x"] - final[ident]["x"]) > TOLERANCE or abs(target["y"] - final[ident]["y"]) > TOLERANCE:
                    moves[ident] = target
                final[ident].update(x=target["x"], y=target["y"], zone=box["zone"], slot=box.get("slot"))
            else:
                final[ident] = dict(target, id=ident, ref=refs[ident], zone=box["zone"], slot=box.get("slot"))
                moves[ident] = target
        if key_act is not None and "x" in key_act:
            left = min(b["x"] for b in final.values())
            top = min(b["y"] for b in final.values())
            target = {"x": int(left - style["key_gap"] - key_act["w"]), "y": int(top), "w": key_act["w"], "h": key_act["h"]}
            moves[KEY_NAME] = target
            others = [o for o in others if o.get("key") != key_act["key"]] + [dict(key_act, **target)]
        summary["relayout"] = f"{sum(1 for k in moves if k in match)} card(s) move; zone headings stay where they are"
    else:
        for ident in final:
            final[ident]["zone"] = boxes[ident]["zone"]
        hub_box = next((final[h] for h in hubs if h in final), None)
        occupied = list(final.values()) + others
        for ident in sorted(new_ids, key=lambda i: (i not in hubs, ids.index(i))):
            card = cards[ident]
            zone = boxes[ident]["zone"]
            if zone == "hub" and hub_box is None:
                x, y = engine.free_spot(None, (card["w"], card["h"]), occupied, canvas, style)
            elif zone == "hub":
                x, y = zone_spot(ident, "bottom", final, {i: b.get("zone") for i, b in final.items()}, hub_box,
                                 (card["w"], card["h"]), occupied, canvas, style)
            else:
                x, y = zone_spot(ident, zone, final, {i: b.get("zone") for i, b in final.items()}, hub_box,
                                 (card["w"], card["h"]), occupied, canvas, style)
            final[ident] = {"id": ident, "ref": refs[ident], "x": x, "y": y, "w": card["w"], "h": card["h"], "zone": zone}
            if zone == "hub" and hub_box is None:
                hub_box = final[ident]
            occupied.append(final[ident])
            moves[ident] = {"x": x, "y": y, "w": card["w"], "h": card["h"]}
    for ident in new_ids:
        card = cards[ident]
        summary["addCards"].append(card["name"])
        expect_cards.append({"ref": refs[ident], "name": card["name"], "header": card["header"], "icons": card["icons"],
                             "attributes": [a["title"] for a in card["attributes"]], "footer": card["footer"],
                             "x": final[ident]["x"], "y": final[ident]["y"], "drilldown": ident in m.groups})
    for item in expect_cards:
        ident = next((i for i, f in final.items() if "key" in item and f.get("key") == item["key"]), None)
        if ident in moves:
            item["x"], item["y"] = moves[ident]["x"], moves[ident]["y"]
    state = {i: {"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for i, b in final.items() if i in match}
    for k, a in enumerate(others):
        state[f"other{k}"] = {"x": a["x"], "y": a["y"], "w": a.get("w", 0), "h": a.get("h", 0)}
    for i in match:
        if i in moves:
            act = match[i]
            state[i] = {"x": act["x"], "y": act["y"], "w": act["w"], "h": act["h"]}
    passes = engine.moves_in_passes(state, moves, canvas, style) if moves else []
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
    relayout_sides = assign_sides(edges, {i: dict(b, id=i) for i, b in final.items()}, hubs) if relayout else {}
    expect_lines, plan_lines = [], []
    for edge in edges:
        a_id, b_id = edge["from"], edge["to"]
        a_key, b_key = key_or_ref[a_id], key_or_ref[b_id]
        names_pair = [cards[a_id]["name"], cards[b_id]["name"]]
        start, end = shapes(edge["two_way"], style)
        found = None
        if a_id in match and b_id in match:
            candidates = [ln for ln in by_pair[frozenset((a_key, b_key))] if ln["key"] not in used_lines]
            same = [ln for ln in candidates if squash(ln.get("label")) == squash(edge["label"])]
            found = (same or candidates or [None])[0]
        if found:
            used_lines.add(found["key"])
            forward = found["from"]["activity"] == a_key
            want_start, want_end = (start, end) if forward else (end, start)
            change = {"op": "update", "kind": "line", "key": found["key"]}
            what = []
            if (found.get("startShape") or "none") != want_start or (found.get("endShape") or "none") != want_end:
                change["startShape"], change["endShape"] = want_start, want_end
                what.append("arrows " + ("both ways" if edge["two_way"] else f"towards {names_pair[1]}"))
            if squash(found.get("label")) != squash(edge["label"]):
                change["label"] = edge["label"]
                what.append(f"label {edge['label']}")
            if relayout:
                pair = relayout_sides[edge["index"]] if forward else tuple(reversed(relayout_sides[edge["index"]]))
                if found.get("fromSide") != pair[0] or found.get("toSide") != pair[1]:
                    change["fromSide"], change["toSide"] = pair
                    what.append("re-routed")
            if len(change) > 3:
                line_ops.append(change)
                summary["updateLines"].append(f"{names_pair[0]} - {names_pair[1]}: " + ", ".join(what))
            expect_lines.append({"key": found["key"], "from": found["from"]["activity"], "to": found["to"]["activity"],
                                 "startShape": want_start, "endShape": want_end, "label": edge["label"], "names": names_pair})
            plan_lines.append({"from": a_id if forward else b_id, "to": b_id if forward else a_id,
                               "fromSide": change.get("fromSide", found.get("fromSide") or "right"),
                               "toSide": change.get("toSide", found.get("toSide") or "left"),
                               "startShape": want_start, "endShape": want_end, "label": edge["label"]})
            continue
        if relayout:
            pair = relayout_sides[edge["index"]]
        else:
            pair = hub_pair(edge, {i: dict(b, zone=b.get("zone") or "right") for i, b in final.items()}, set(hubs))
            if pair is None:
                pair = engine.choose_sides(boxes_now[a_id], boxes_now[b_id], keyed, usage, {a_key, b_key})
        usage[(a_key, pair[0])] += 1
        usage[(b_key, pair[1])] += 1
        ref = f"line{edge['index'] + 1}"
        change = {"op": "add", "kind": "line", "ref": ref, "from": {"activity": a_key}, "to": {"activity": b_key},
                  "fromSide": pair[0], "toSide": pair[1], "startShape": start, "endShape": end}
        if edge["label"]:
            change["label"] = edge["label"]
        line_ops.append(change)
        summary["addLines"].append(f"{names_pair[0]} - {names_pair[1]}" + (f" ({edge['label']})" if edge["label"] else ""))
        expect_lines.append({"ref": ref, "from": a_key, "to": b_key, "startShape": start, "endShape": end,
                             "label": edge["label"], "names": names_pair})
        plan_lines.append({"from": a_id, "to": b_id, "fromSide": pair[0], "toSide": pair[1], "startShape": start,
                           "endShape": end, "label": edge["label"], "ref": ref, "id": edge["id"]})
    name_of_key = {a["key"]: a.get("text") for a in acts}
    for ln in current:
        if ln["key"] in used_lines:
            continue
        ends_keys = (ln["from"]["activity"], ln["to"]["activity"])
        if any(k in removed_keys for k in ends_keys) or (key_act is not None and key_act["key"] in ends_keys):
            continue
        described = f"{name_of_key.get(ends_keys[0])} - {name_of_key.get(ends_keys[1])}" + (f" ({ln['label']})" if ln.get("label") else "")
        if allow_remove:
            removals.append({"op": "remove", "kind": "line", "key": ln["key"]})
            summary["removeLines"].append(described)
        else:
            summary["keepLines"].append(described)
    if key_act is not None:
        want = key_attributes(cards, edges, m.integrations, data)
        have = key_act.get("attributes", [])
        if [norm(a["title"]) for a in have] != [norm(a["title"]) for a in want]:
            key_ops += [{"op": "remove", "kind": "attribute", "activity": key_act["key"], "key": a["key"]} for a in have]
            for item in want:
                change = {"op": "add", "kind": "attribute", "activity": key_act["key"], "title": item["title"]}
                if item.get("description"):
                    change["description"] = item["description"]
                key_ops.append(change)
            summary["updateCards"].append("Key: brought up to date")
    # groups: a new group card gets its drill-down; an existing one is left as it is
    for group in m.groups:
        if group in match:
            if match[group].get("drilldown"):
                warnings.append(f"the drill-down of '{cards[group]['name']}' is not amended; amend handles the top level. Check its members there")
            else:
                warnings.append(f"'{cards[group]['name']}' now has members but no drill-down; add one in Elements (Drilldown > New drilldown) or redraw the map")
    # batches
    batches = []
    if removals:
        lines_first = [r for r in removals if r["kind"] == "line"] + [r for r in removals if r["kind"] == "activity"]
        for chunk in engine.chunk([[r] for r in lines_first]):
            batches.append({"kind": "remove", "changes": chunk, "confirm": True})
    groups = [[u] for u in updates]
    first = True
    for fits in passes or [[]]:
        group_list = list(groups) if first else []
        first = False
        for ident in fits:
            if ident == KEY_NAME:
                group_list.append([{"op": "update", "kind": "activity", "key": key_act["key"],
                                    "position": {"x": moves[ident]["x"], "y": moves[ident]["y"]}}])
            elif ident in match:
                group_list.append([{"op": "update", "kind": "activity", "key": match[ident]["key"],
                                    "position": {"x": moves[ident]["x"], "y": moves[ident]["y"]}}])
            else:
                box = plan_box(cards[ident], final[ident], refs[ident])
                group_list.append(card_changes(box, m.systems.get(ident), skip))
        for chunk in engine.chunk(group_list):
            if chunk:
                batches.append({"kind": "cards", "changes": chunk})
    for chunk in engine.chunk([[op] for op in line_ops + key_ops]):
        batches.append({"kind": "lines", "changes": chunk})
    new_groups = [g for g in m.groups if g in new_ids]
    if new_groups:
        batches.append({"kind": "children", "changes": [{"op": "add", "kind": "child", "activity": refs[g]} for g in new_groups]})
    plan_boxes = []
    for ident, box in final.items():
        card = cards[ident]
        plan_boxes.append(dict(plan_box(card, box, box.get("ref") or box.get("key")), key=box.get("key")))
    level = {"slug": TOP, "parent": None, "boxes": plan_boxes, "texts": [], "lines": plan_lines, "batches": batches,
             "hubs": hubs, "zones": {i: b.get("zone") for i, b in final.items()},
             "expect": {"cards": expect_cards, "lines": expect_lines, "boundary": [], "texts": [], "exclusive": allow_remove},
             "writes": len(batches)}
    levels = [level]
    if new_groups:
        top_ref_of = {ln["id"]: ln["ref"] for ln in plan_lines if ln.get("ref")}
        for group in new_groups:
            child = child_level(m, group, [e for e in edges if e["id"] in top_ref_of], top_ref_of, data, skip, warnings)
            child["writes"] = sum(1 for b in child["batches"] if b["kind"] == "cards")
            levels.append(child)
    meta = model.get("meta", {})
    result = {"planVersion": 1, "mode": "amend", "diagramType": DIAGRAM_TYPE, "mapType": MAP_TYPE,
              "mapName": map_name((meta.get("title") or read.get("title") or "System architecture")), "mapDescription": "",
              "createResources": create_resources, "levels": levels, "preflight": preflight(levels, model),
              "summary": summary, "map": {"mapId": read.get("mapId"), "diagramId": read.get("diagramId"), "version": read.get("version", 0)},
              "warnings": engine.dedupe(warnings), "gaps": model.get("gaps", [])}
    result["planId"] = engine.plan_id(result)
    return result


# ---------------------------------------------------------------- next

def next_step(workdir):
    step = engine.next_step(workdir, Path(__file__).name)
    if "then" in step:
        step["then"] = f"python3 {Path(__file__).name} check {workdir}"
    if step.get("action") == "fix-preflight":
        missing = [i.get("message", "").split(" in this space")[0].replace("No resource named ", "")
                   for i in step.get("issues", []) if i.get("code") == "resource_not_found"]
        if missing:
            step["missingIcons"] = missing
            step["how"] = ("resource_not_found: these icons are not in the space's resource library. Ask the user, per icon, to use a close "
                           "match from the message (set the system's icon in the model), to draw those cards without it (plan again with "
                           "--drop-icons \"" + ",".join(missing) + "\"), or to add the names to the library as icons without a picture "
                           "(plan again with --create-resources). " + step["how"])
    return step


# ---------------------------------------------------------------- check: the drawn result

def layout_rules():
    return {row["rule_id"]: row for row in engine.read_csv(RUBRIC_PATH)
            if row.get("checked_by") == "layout-check" and DIAGRAM_TYPE in row.get("applies_to", "").split("|")}


def check(workdir):
    workdir = Path(workdir)
    the_plan = engine.read_json(workdir / "plan.json")
    engine.refuse_partial_reads(workdir, the_plan)   # a review read missing or not whole writes no layout-check.json
    rules = layout_rules()
    findings = []
    counted = {"cards": 0, "lines": 0}
    for level_plan in the_plan["levels"]:
        slug = level_plan["slug"]
        path = workdir / "review" / f"{slug}.json"
        read = engine.unwrap(engine.read_json(path))
        keys = engine.id_map(engine.level_results(workdir, slug))
        findings += check_level(read, level_plan, keys, rules)
        counted["cards"] += len(read.get("activities", []))
        counted["lines"] += len(read.get("lines", []))
    result = {"findings": findings, "checked": sorted(rules), "boxes": counted["cards"], "lines": counted["lines"]}
    (workdir / "layout-check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def check_level(read, level_plan, keys, rules):
    level = str(read.get("levelNumber", "1"))
    acts = read.get("activities", [])
    by_key = {a["key"]: a for a in acts}
    findings = []

    def find(rule, element, issue, fix):
        findings.append({"rule": rule, "severity": rules.get(rule, {}).get("severity", "warn"), "level": level,
                         "element": element, "issue": issue, "fix": fix})

    def resolve(value):
        return value if isinstance(value, int) else keys.get(value)

    expect = level_plan["expect"]
    seen = set()
    for card in expect["cards"]:
        act = by_key.get(card["key"]) if "key" in card else by_key.get(keys.get(card.get("ref")))
        if act is None:
            act = next((a for a in acts if norm(a.get("text")) == norm(card["name"]) and a["key"] not in seen), None)
        name = f"'{card['name']}'"
        if act is None:
            find("R49", name, f"The card {name} is not on the level.", "Send the batch that adds it, or plan and draw again.")
            continue
        seen.add(act["key"])
        element = f"{name} (key {act['key']})"
        if norm(act.get("text")) != norm(card["name"]):
            find("R49", element, f"The card reads '{act.get('text')}', not {name}.", "Rename the card or the system so they match.")
        if card.get("header") and norm(header_of(act)) != norm(card["header"]):
            find("R49", element, f"The header icon is '{header_of(act) or 'none'}'; the plan has '{card['header']}'.", "Amend the diagram from the model again.")
        if card.get("icons") is not None and [norm(i) for i in footer_icons_of(act)] != [norm(i) for i in card["icons"]]:
            find("R49", element, f"The footer icons are {footer_icons_of(act)}; the plan has {card['icons']}.", "Amend the diagram from the model again.")
        drawn = [norm(a.get("title")) for a in act.get("attributes", [])]
        if drawn != [norm(t) for t in card["attributes"]]:
            find("R49", element, f"The card lists {drawn}; the plan has {[norm(t) for t in card['attributes']]}.", "Amend the diagram from the model again.")
        if norm(act.get("footerText")) != norm(card.get("footer")):
            find("R49", element, f"The footer reads '{act.get('footerText') or ''}'; the plan has '{card.get('footer') or ''}'.", "Amend the diagram from the model again.")
        if card.get("drilldown") and not act.get("drilldown"):
            find("R49", element, f"{name} is a group but has no drill-down level.", "Send the children batch, or add a drill-down in Elements.")
        if card.get("x") is not None and "x" in act:
            if abs(act["x"] - card["x"]) > TOLERANCE or abs(act["y"] - card["y"]) > TOLERANCE:
                find("R48", element, f"{name} is at {act['x']},{act['y']}; the plan put it at {card['x']},{card['y']}.", "Someone may have moved it in Elements; move it back or plan again.")
            if card.get("h") and act.get("h") and act["h"] + TOLERANCE < card["h"]:
                find("R48", element, f"{name} is {act['h']} px tall; the plan expected {card['h']} px.", "Check its attributes and footer were all written.")
    placed = [a for a in acts if "x" in a]
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if engine.overlaps(a, b):
                find("R48", f"'{a.get('text')}' and '{b.get('text')}'", "These two cards overlap.", "Move one of them, or amend with --relayout.")
    if expect.get("exclusive"):
        for act in acts:
            if act["key"] not in seen:
                find("R49", f"'{act.get('text')}' (key {act['key']})", "This card is on the level but not in the plan.", "Someone added it after the drawing; check it belongs.")
    lines = read.get("lines", [])
    used = set()
    for item in expect["lines"]:
        a, b = resolve(item["from"]), resolve(item["to"])
        element = f"line {item['names'][0]} - {item['names'][1]}"
        exact = resolve(item["ref"]) if item.get("ref") else item.get("key")
        candidates = [ln for ln in lines if ln.get("key") not in used and (ln.get("from") or {}).get("activity") == a
                      and (ln.get("to") or {}).get("activity") == b]
        found = next((ln for ln in candidates if ln.get("key") == exact), None) if exact is not None else None
        if found is None and candidates:
            found = next((ln for ln in candidates if squash(ln.get("label")) == squash(item.get("label"))), candidates[0])
        if found is None:
            find("R49", element, "The integration is not drawn between these two cards.", "Send the line batch again, or plan again.")
            continue
        used.add(found["key"])
        if (found.get("startShape") or "none") != item["startShape"] or (found.get("endShape") or "none") != item["endShape"]:
            find("R49", f"{element} (key {found['key']})", f"The arrows are {found.get('startShape')} and {found.get('endShape')}; the plan has {item['startShape']} and {item['endShape']}.",
                 "Amend the diagram from the model again.")
        if squash(found.get("label")) != squash(item.get("label")):
            find("R49", f"{element} (key {found['key']})", f"The label reads '{found.get('label') or ''}'; the plan has '{item.get('label')}'.", "Amend the diagram from the model again.")
    for item in expect.get("boundary", []):
        member = resolve(item["member"])
        end = "from" if item["out"] else "to"
        free = "to" if item["out"] else "from"
        candidates = [ln for ln in lines if ln.get("key") not in used and (ln.get(end) or {}).get("activity") == member and not ln.get(free)]
        found = next((ln for ln in candidates if squash(ln.get("label")) == squash(item["label"])), candidates[0] if candidates else None)
        element = f"line {'out of' if item['out'] else 'into'} '{item['name']}'"
        if found is None:
            find("R49", element, f"The line '{item['label']}' is not drawn.", "Send the level's line batch again.")
            continue
        used.add(found["key"])
        if (found.get("startShape") or "none") != item["startShape"] or (found.get("endShape") or "none") != item["endShape"]:
            find("R49", f"{element} (key {found['key']})", f"The arrows are {found.get('startShape')} and {found.get('endShape')}; the plan has {item['startShape']} and {item['endShape']}.",
                 "Amend the drill-down in Elements, or plan and draw again.")
        side = found.get("fromSide") if item["out"] else found.get("toSide")
        if side and side != ("right" if item["out"] else "left"):
            find("R49", f"{element} (key {found['key']})", f"The line joins the card's {side} side; lines in join the left side and lines out the right.",
                 "Move the line's end in Elements.")
        if item.get("parentRef") and not found.get("parentLine"):
            find("R49", f"{element} (key {found['key']})", "The line is not linked to the line it continues on the level above.", "Plan the drawing again; the link is made when the line is added.")
    if expect.get("exclusive"):
        for ln in lines:
            if ln.get("key") in used:
                continue
            if ln.get("parentLine") and not (ln.get("from") or ln.get("to")):
                find("R49", f"line key {ln['key']}", f"The line '{ln.get('label') or ''}' was seeded by the drill-down and joins no card.", "Remove it in Elements, or check which member it should join.")
            elif (ln.get("from") or {}).get("activity") is not None or (ln.get("to") or {}).get("activity") is not None:
                find("R49", f"line key {ln['key']}", "This line is on the level but not in the plan.", "Someone added it after the drawing; check it belongs.")
    boxes = [dict(a, key=a["key"]) for a in placed]
    for ln in lines:
        a = by_key.get((ln.get("from") or {}).get("activity"))
        b = by_key.get((ln.get("to") or {}).get("activity"))
        if not a or not b or a is b or not ln.get("fromSide") or not ln.get("toSide") or "x" not in a or "x" not in b:
            continue
        hits = engine.route_crossings(engine.route(a, ln["fromSide"], b, ln["toSide"]), boxes, {a["key"], b["key"]})
        if hits:
            find("R50", f"line {a.get('text')} - {b.get('text')} (key {ln['key']})",
                 f"The line is likely to run through {', '.join(repr(h.get('text')) for h in hits)}.", "Move a card, or amend with --relayout.")
    return findings


# ---------------------------------------------------------------- main

def print_summary(the_plan, workdir):
    for level in the_plan["levels"]:
        cards = [b for b in level["boxes"] if b.get("role") != "key"]
        where = "top level" if level["slug"] == TOP else f"drill-down of '{level['slug']}'"
        hubs = ", ".join(next((b["name"] for b in level["boxes"] if b["id"] == h), h) for h in level.get("hubs", []))
        counts = Counter(level.get("zones", {}).get(b["id"]) for b in cards)
        zones = ", ".join(f"{z} {counts[z]}" for z in ZONES if counts.get(z))
        print(f"LEVEL {where}: {len(cards)} cards, {len(level['lines'])} lines, {len(level['batches'])} batch(es)"
              + (f"; hub {hubs}" if hubs else "") + (f"; zones {zones}" if zones else "")
              + ("; a key card" if any(b.get("role") == "key" for b in level["boxes"]) else "")
              + (f"; {len(level.get('texts', []))} zone heading(s)" if level.get("texts") else ""))
    if the_plan["mode"] == "amend":
        s = the_plan["summary"]
        for label, key in (("ADD card", "addCards"), ("UPDATE card", "updateCards"), ("REMOVE card", "removeCards"),
                           ("KEEP card (not in the model; --allow-remove removes it)", "keepCards"), ("ADD line", "addLines"),
                           ("UPDATE line", "updateLines"), ("REMOVE line", "removeLines"),
                           ("KEEP line (not in the model; --allow-remove removes it)", "keepLines")):
            for item in s.get(key, []):
                print(f"{label}: {item}")
        if s.get("relayout"):
            print(f"RELAYOUT {s['relayout']}")
        if not any(lv["batches"] for lv in the_plan["levels"]):
            print("NOTHING TO CHANGE: the diagram already matches the model")
    for warning in the_plan["warnings"]:
        print(f"WARN {warning}")
    for gap in the_plan.get("gaps", []):
        print(f"GAP {gap.get('note')}")
    print(f"WROTE {Path(workdir) / 'plan.json'} and {Path(workdir) / 'preview.svg'}")


def parse_names(text):
    return [s.strip() for s in (text or "").split(",") if s.strip()]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Lay out, write, amend and check an Elements system architecture diagram.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "amend"):
        p = sub.add_parser(name)
        p.add_argument("model")
        p.add_argument("--workdir", required=True)
        p.add_argument("--drop-icons", default="")
        p.add_argument("--skip", default="")
        p.add_argument("--create-resources", action="store_true")
        p.add_argument("--drop-unresolved", action="store_true")
        if name == "plan":
            p.add_argument("--name")
            p.add_argument("--no-key", action="store_true")
            p.add_argument("--no-headings", action="store_true")
        else:
            p.add_argument("--read", required=True)
            p.add_argument("--allow-remove", action="store_true")
            p.add_argument("--relayout", action="store_true")
    p = sub.add_parser("from-diagram")
    p.add_argument("reads", nargs="+")
    p.add_argument("--out", required=True)
    p = sub.add_parser("next")
    p.add_argument("workdir")
    p = sub.add_parser("check")
    p.add_argument("workdir")
    args = parser.parse_args(argv)
    try:
        if args.command in ("plan", "amend"):
            workdir = Path(args.workdir)
            gate = validate.gate(args.model, "system-architecture")
            if gate:
                return gate
            model = scope_model(engine.read_json(args.model), args.model, args.workdir)
            skip = engine.parse_skip(args.skip)
            if args.command == "plan":
                the_plan = plan(model, False if args.no_key else None, False if args.no_headings else None,
                                parse_names(args.drop_icons), skip, args.create_resources, args.name, args.drop_unresolved)
            else:
                the_plan = amend(model, engine.read_json(args.read), args.allow_remove, args.relayout, parse_names(args.drop_icons),
                                 skip, args.create_resources)
                if args.drop_unresolved:
                    the_plan["dropUnresolved"] = True
                    the_plan["planId"] = engine.plan_id(dict(the_plan, planId=None))
            the_plan["model"] = str(Path(args.model).resolve())
            engine.prepare_workdir(workdir, the_plan)
            (workdir / "plan.json").write_text(json.dumps(the_plan, indent=2, ensure_ascii=False), encoding="utf-8")
            (workdir / "preview.svg").write_text(preview_svg(the_plan["levels"][0]), encoding="utf-8")
            for level in the_plan["levels"][1:]:
                (workdir / f"preview-{level['slug']}.svg").write_text(preview_svg(level), encoding="utf-8")
            if args.command == "amend":
                (workdir / "map.json").write_text(json.dumps(the_plan["map"], indent=2), encoding="utf-8")
            print_summary(the_plan, workdir)
            return 0
        if args.command == "from-diagram":
            model = from_diagram([engine.read_json(p) for p in args.reads])
            Path(args.out).write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"WROTE {args.out}: {len(model.get('systems', []))} systems, {len(model.get('integrations', []))} integrations, "
                  f"{len(model.get('gaps', []))} gap(s)")
            for gap in model.get("gaps", []):
                print(f"GAP {gap['note']}")
            return 0
        if args.command == "next":
            print(json.dumps(next_step(args.workdir), indent=2, ensure_ascii=False))
            return 0
        if args.command == "check":
            result = check(args.workdir)
            for f in result["findings"]:
                print(f"{f['severity'].upper()} {f['rule']} level {f['level']} {f['element']}: {f['issue']}")
            print(f"CHECKED {result['boxes']} cards and {result['lines']} lines against {', '.join(result['checked'])}: "
                  f"{len(result['findings'])} finding(s)")
            return 0
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except engine.TrimmedReads as exc:
        for line in exc.lines:
            print(f"ERROR {line}", file=sys.stderr)
        return 1
    except PlanError as exc:
        print(f"PLAN ERROR {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
