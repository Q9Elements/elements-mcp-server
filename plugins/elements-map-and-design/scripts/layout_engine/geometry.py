"""Placement and line geometry: the left-to-right level layout (Level), the sides and routes lines take, canvas growth and the writes it allows, free spots and card sizing.

Part of the shared layout engine (see __init__.py). Standard library only; Python 3.8 or later.
"""

import copy
import json
from collections import defaultdict

from .base import END, PlanError, RESOURCE_TYPE, START, TOP, USES_TYPE, make_ref, norm


JETTY = 20


def side_point(box, side):
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return {"left": (x, y + h / 2), "right": (x + w, y + h / 2),
            "top": (x + w / 2, y), "bottom": (x + w / 2, y + h)}[side]


STEP = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def route(a, a_side, b, b_side):
    """An approximate orthogonal route between two box sides, like the editor's, as a list of points."""
    p0, p1 = side_point(a, a_side), side_point(b, b_side)
    d0, d1 = STEP[a_side], STEP[b_side]
    q0 = (p0[0] + d0[0] * JETTY, p0[1] + d0[1] * JETTY)
    q1 = (p1[0] + d1[0] * JETTY, p1[1] + d1[1] * JETTY)
    if a_side == "top" and b_side == "top":
        level = min(q0[1], q1[1])
        mid = [(q0[0], level), (q1[0], level)]
    elif a_side == "bottom" and b_side == "bottom":
        level = max(q0[1], q1[1])
        mid = [(q0[0], level), (q1[0], level)]
    elif a_side in ("left", "right") and b_side in ("left", "right"):
        if (a_side == "right" and q1[0] >= q0[0]) or (a_side == "left" and q1[0] <= q0[0]):
            mx = (q0[0] + q1[0]) / 2
            mid = [(mx, q0[1]), (mx, q1[1])]
        else:  # going back: through the gap between the two boxes' rows
            gap = (a["y"] + a["h"] + b["y"]) / 2 if b["y"] > a["y"] + a["h"] else (b["y"] + b["h"] + a["y"]) / 2 \
                if a["y"] > b["y"] + b["h"] else min(a["y"], b["y"]) - JETTY * 2
            mid = [(q0[0], gap), (q1[0], gap)]
    elif a_side in ("top", "bottom") and b_side in ("left", "right"):
        mid = [(q0[0], q1[1])]
    elif a_side in ("left", "right") and b_side in ("top", "bottom"):
        mid = [(q1[0], q0[1])]
    else:  # top/bottom to bottom/top
        my = (q0[1] + q1[1]) / 2
        mid = [(q0[0], my), (q1[0], my)]
    return [p0, q0] + mid + [q1, p1]


def segment_hits_box(p, q, box, margin=2):
    x0, x1 = sorted((p[0], q[0]))
    y0, y1 = sorted((p[1], q[1]))
    bx0, by0 = box["x"] + margin, box["y"] + margin
    bx1, by1 = box["x"] + box["w"] - margin, box["y"] + box["h"] - margin
    return x0 < bx1 and x1 > bx0 and y0 < by1 and y1 > by0


def route_crossings(points, boxes, skip):
    hits = []
    for box in boxes:
        if box["key"] in skip:
            continue
        if any(segment_hits_box(p, q, box) for p, q in zip(points, points[1:])):
            hits.append(box)
    return hits


USES_RESERVED = 2  # places on a full box kept for the objects and systems its step uses


class Level:

    mark_inferred_lines = True       # append " (inferred)" to the label of an inferred line
    pair_boundary_by_order = False   # pair parent lines left unmatched by label with free START/END lines, in order

    def __init__(self, model, parent, diagram_type, style, skip, use_uses, warnings):
        self.model, self.parent, self.type, self.style = model, parent, diagram_type, style
        self.skip, self.use_uses, self.warn = skip, use_uses, warnings
        self.slug = parent or TOP
        self.acts = [a for a in model.get("activities", []) if a.get("parent") == parent]
        self.ids = [a["id"] for a in self.acts]
        self.by_id = {a["id"]: a for a in self.acts}
        idset = set(self.ids)
        self.flows = []  # (index, flow)
        for index, flow in enumerate(model.get("flows", [])):
            src, dst = flow["from"], flow["to"]
            if (src in idset) or (src == START and dst in idset):
                self.flows.append((index, flow))
        self.out = defaultdict(list)
        self.into = defaultdict(list)
        for index, flow in self.flows:
            self.out[flow["from"]].append((index, flow))
            self.into[flow["to"]].append((index, flow))

    def where(self):
        return "top level" if self.parent is None else f"level under '{self.parent}'"

    # ---- sequence: main path and loops

    def main_path(self):
        starts = [f["to"] for _, f in self.out[START] if f["to"] in self.by_id]
        first = starts[0] if starts else (self.ids[0] if self.ids else None)
        path = []
        node = first
        while node is not None and node not in path:
            path.append(node)
            # The first-listed line out of a box is its expected outcome; a line back to a box already
            # on the path is a loop, not the way on. The path ends where the expected outcome is END.
            ahead = next((f["to"] for _, f in self.out[node] if f["to"] not in path), None)
            node = ahead if ahead in self.by_id else None
        return path

    def classify(self, path):
        """Mark loops (lines back to a box still being followed, in model order) and the main path."""
        main_edges = set()
        for a, b in zip(path, path[1:]):
            for index, flow in self.out[a]:
                if flow["to"] == b:
                    main_edges.add(index)
                    break
        ordered = {}
        for node in self.ids:
            flows = self.out[node]
            first = [x for x in flows if x[0] in main_edges]
            ordered[node] = first + [x for x in flows if x[0] not in main_edges]
        loops, colour = set(), {}
        roots = [f["to"] for _, f in self.out[START] if f["to"] in self.by_id] + self.ids
        for root in roots:
            if root in colour:
                continue
            stack = [(root, iter(ordered[root]))]
            colour[root] = 1
            while stack:
                node, it = stack[-1]
                step = next(it, None)
                if step is None:
                    colour[node] = 2
                    stack.pop()
                    continue
                index, flow = step
                dst = flow["to"]
                if dst not in self.by_id:
                    continue
                if colour.get(dst) == 1:
                    loops.add(index)
                elif dst not in colour:
                    colour[dst] = 1
                    stack.append((dst, iter(ordered[dst])))
        return main_edges, loops, ordered

    def outcome_sides(self, ordered, loops):
        """fromSide for every line out of a box: loops top; distinct outcomes right, top, bottom; then 'facing'."""
        sides, groups_of = {}, {}
        for node in self.ids:
            flows = ordered[node]
            has_loop = any(index in loops for index, _ in flows)
            free = ["right"] + ([] if has_loop else ["top"]) + ["bottom"]
            groups = []
            for index, flow in flows:
                if index in loops:
                    sides[index] = "top"
                    continue
                key = norm(flow.get("label"))
                group = next((g for g in groups if g["key"] == key and key), None)
                if group is None:
                    group = {"key": key, "flows": []}
                    groups.append(group)
                group["flows"].append(index)
            for position, group in enumerate(groups):
                side = free[position] if position < len(free) else "facing"
                for index in group["flows"]:
                    sides[index] = side
            groups_of[node] = groups
            limit = self.style["max_decision_outcomes"]
            if len(groups) + (1 if has_loop else 0) > limit:
                self.warn.append(f"{self.where()}: '{self.by_id[node]['name']}' has {len(groups) + (1 if has_loop else 0)} different outcomes; more than {limit} share a side, which UPN reads as parallel paths. Consider splitting the decision")
        return sides, groups_of

    # ---- resources and box size

    def resources(self, act):
        model = self.model
        roles = {r["id"]: r for r in model.get("roles", [])}
        out, seen = [], set()
        assignments = list(act.get("roles", []))
        if self.type == "journey":
            first = self.style.get("journey_first_resource", "Customer")
            assignments.sort(key=lambda a: 0 if norm(roles.get(a["role"], {}).get("name")) == norm(first) else 1)
            if not any(norm(roles.get(a["role"], {}).get("name")) == norm(first) for a in assignments):
                self.warn.append(f"{self.where()}: journey box '{act['name']}' has no '{first}' role; journey boxes list the customer first")
        for assignment in assignments:
            role = roles.get(assignment["role"])
            if not role or norm(role["name"]) in seen:
                continue
            seen.add(norm(role["name"]))
            item = {"name": role["name"], "type": RESOURCE_TYPE[role["kind"]]}
            if role["kind"] == "ai-agent":
                self.warn.append(f"{self.where()}: AI agent '{role['name']}' is drawn as a System resource; Elements has no AI agent resource type")
            if assignment.get("rasci") and role["kind"] == "human":
                item["rasci"] = assignment["rasci"]
            out.append(item)
        used = []
        if self.use_uses:
            pools = {section: {i["id"]: i for i in model.get(section, [])} for section in USES_TYPE}
            for ref in act.get("uses", []):
                for section, pool in pools.items():
                    if ref in pool and norm(pool[ref]["name"]) not in seen:
                        seen.add(norm(pool[ref]["name"]))
                        used.append({"name": pool[ref]["name"], "type": USES_TYPE[section]})
        limit = self.style["max_resources_shown"]
        if len(out) + len(used) > limit:
            # The objects a step uses show at first sight whether the step is right, so they keep up to
            # USES_RESERVED places; the people and systems doing it keep the rest, the first person always.
            keep_used = min(len(used), max(USES_RESERVED, limit - len(out)), limit - 1)
            keep_roles = limit - keep_used
            dropped = out[keep_roles:] + used[keep_used:]
            self.warn.append(f"{self.where()}: '{act['name']}' has {len(out) + len(used)} resources; showing {limit}, "
                             f"leaving out {', '.join(r['name'] for r in dropped)}")
            self.resource_overflow = getattr(self, "resource_overflow", {})
            self.resource_overflow[act["id"]] = [item["name"] for item in dropped]
            out, used = out[:keep_roles], used[:keep_used]
        return out + used

    def height(self, resources):
        return self.style["box_height_base"] + self.style["resource_row_height"] * len(resources)

    def box_height(self, act, resources):
        """The height the server gives this box; a subclass for other box kinds overrides it."""
        return self.height(resources)

    # ---- placement

    def layers(self, path):
        """Column of every box: the longest run of lines from the start, ignoring loops.

        A box therefore always sits right of every box that leads to it, so an alternative path
        that rejoins the main path meets it further right, and the main path leaves a gap for it."""
        layer = {}
        incoming = defaultdict(list)
        for index, flow in self.flows:
            if index in self._loops or flow["from"] not in self.by_id or flow["to"] not in self.by_id:
                continue
            incoming[flow["to"]].append(flow["from"])
        state = {}

        def depth(node):
            if node in layer:
                return layer[node]
            state[node] = 1
            best = 0
            for src in incoming[node]:
                if state.get(src) == 1:  # a cycle the loop marking missed; ignore that line
                    continue
                best = max(best, depth(src) + 1)
            state[node] = 2
            layer[node] = best
            return best

        for node in path + self.ids:
            depth(node)
        return layer

    def place(self, path, ordered, sides, groups_of):
        cols = self.style["max_columns"]
        layer = self.layers(path)
        cells, cell_of, reserved = {}, {}, {}

        def column(node):
            return layer[node] // cols, layer[node] % cols

        def reserve(node):
            band, row, col = cell_of[node]
            for index, _ in ordered[node]:
                side = sides.get(index)
                if side in ("top", "bottom") and index not in self._loops:
                    target = (band, row - 1 if side == "top" else row + 1, col)
                    reserved.setdefault(target, node)
                    if target in cells and cells[target] != node:
                        self.warn.append(f"{self.where()}: the line leaving '{self.by_id[node]['name']}' from its {side} runs through '{self.by_id[cells[target]]['name']}'")

        def put(node, cell):
            cells[cell] = node
            cell_of[node] = cell
            reserve(node)

        def free(cell):
            return cell not in cells and cell not in reserved

        def search(node, row, step):
            band, col = column(node)
            while not free((band, row, col)):
                row += step
            return (band, row, col)

        for node in path:
            band, col = column(node)
            put(node, (band, 0, col))
        queue = list(path)
        for _, flow in self.out[START]:
            node = flow["to"]
            if node in self.by_id and node not in cell_of:
                put(node, search(node, 1, 1))
                queue.append(node)
        position = 0
        while True:
            while position < len(queue):
                node = queue[position]
                position += 1
                row = cell_of[node][1]
                away = -1 if row < 0 else 1
                for group in groups_of[node]:
                    for rank, index in enumerate(group["flows"]):
                        dst = self.flow_by_index[index]["to"]
                        if dst not in self.by_id or dst in cell_of:
                            continue
                        side = sides[index]
                        if side == "top":
                            cell = search(dst, row - 1, -1)
                        elif side == "right" and not rank:
                            cell = search(dst, row, away)
                        else:  # bottom, a further parallel target, or a fourth outcome
                            cell = search(dst, row + 1, 1)
                        put(dst, cell)
                        queue.append(dst)
            leftover = [n for n in self.ids if n not in cell_of]
            if not leftover:
                break
            node = leftover[0]
            lowest = max((c[1] for c in cell_of.values()), default=0)
            self.warn.append(f"{self.where()}: '{self.by_id[node]['name']}' is not reached from the start of the level; placed below the rest")
            put(node, search(node, lowest + 1, 1))
            queue.append(node)
        return cell_of

    def coordinates(self, cell_of, heights):
        style = self.style
        pitch = style["box_width"] + style["col_gap"]
        rows_by_band = defaultdict(set)
        for band, row, _ in cell_of.values():
            rows_by_band[band].add(row)
        tallest = defaultdict(int)
        for node, (band, row, _) in cell_of.items():
            tallest[(band, row)] = max(tallest[(band, row)], heights[node])
        centre, y_cursor = {}, style["top_margin"]
        for band in sorted(rows_by_band):
            previous = None
            for row in sorted(rows_by_band[band]):
                h = tallest[(band, row)]
                if previous is None:
                    centre[(band, row)] = y_cursor + h / 2
                else:
                    centre[(band, row)] = centre[previous] + tallest[previous] / 2 + style["row_gap"] + h / 2
                previous = (band, row)
            y_cursor = centre[previous] + tallest[previous] / 2 + style["band_gap"]
        boxes = {}
        for node, (band, row, col) in cell_of.items():
            h = heights[node]
            boxes[node] = {"key": node, "x": int(style["free_end_clearance"] + col * pitch),
                           "y": int(round(centre[(band, row)] - h / 2)), "w": style["box_width"], "h": h,
                           "band": band, "row": row, "col": col}
        return boxes

    # ---- lines

    def entry_side(self, index, flow, from_side, boxes, main_edges):
        dst = flow["to"]
        if index in self._loops:
            return "top"
        if index in main_edges or self.by_id[dst].get("join") == "all":
            return "left"
        src = flow["from"]
        a, b = boxes[src], boxes[dst]
        if (a["band"], a["row"]) == (b["band"], b["row"]):
            return "left" if b["col"] > a["col"] else "top"
        if (b["band"], b["row"]) < (a["band"], a["row"]):  # target above: an outcome up, or a rejoin from below
            return "left" if from_side == "top" and b["col"] > a["col"] else "bottom"
        if from_side == "bottom" and b["col"] > a["col"]:  # an outcome down
            return "left"
        if from_side == "right" and self.is_parallel(src, index):  # stacked parallel targets
            return "left"
        return "top"  # a rejoin from above

    def is_parallel(self, src, index):
        return any(index in g["flows"] and len(g["flows"]) > 1 for g in self._groups.get(src, []))

    def facing(self, a, b):
        if b is None:
            return "bottom"
        if (a["band"], a["row"]) == (b["band"], b["row"]):
            return "right" if b["col"] > a["col"] else "top"
        return "top" if (b["band"], b["row"]) < (a["band"], a["row"]) else "bottom"

    # ---- the whole level

    def build(self, parent_boundary):
        if not self.acts:
            return None
        self.flow_by_index = {index: flow for index, flow in self.flows}
        path = self.main_path()
        main_edges, loops, ordered = self.classify(path)
        self._loops = loops
        sides, groups = self.outcome_sides(ordered, loops)
        self._groups = groups
        if len(self.acts) > self.style["max_boxes_per_level"]:
            self.warn.append(f"{self.where()}: {len(self.acts)} boxes; at most {self.style['max_boxes_per_level']} per level, so move some into a child level")
        if len(path) > self.style["max_columns"]:
            self.warn.append(f"{self.where()}: the main path has {len(path)} steps, so it wraps onto a second row after {self.style['max_columns']}")
        resources = {a["id"]: self.resources(a) for a in self.acts}
        heights = {a["id"]: self.box_height(a, resources[a["id"]]) for a in self.acts}
        cell_of = self.place(path, ordered, sides, groups)
        boxes = self.coordinates(cell_of, heights)

        refs = {a["id"]: make_ref("", a["id"]) for a in self.acts}
        lines = []
        # The parent's lines into and out of this level's box, by label. Two parent lines can share a label
        # (a parallel split), so each label holds a list and every seed is used once.
        seeded_in, seeded_out = defaultdict(list), defaultdict(list)
        for seed in (parent_boundary or {}).get("inputs", []):
            seeded_in[norm(seed["label"])].append(seed)
        for seed in (parent_boundary or {}).get("outputs", []):
            seeded_out[norm(seed["label"])].append(seed)
        used_seeds = set()

        def take(seeds):
            return next((seed for seed in seeds if seed["ref"] not in used_seeds), None)

        for index, flow in self.flows:
            src, dst = flow["from"], flow["to"]
            label = flow.get("label", "")
            if flow.get("inferred") and self.mark_inferred_lines:
                label = f"{label} (inferred)" if label else "(inferred)"
            line = {"ref": make_ref("~f", flow.get("id", str(index))), "flowIndex": index, "from": src, "to": dst, "label": label}
            if src == START:
                line["toSide"] = "left"
                line["rule"] = "L11"
                seed = take(seeded_in.get(norm(flow.get("label")), []))
                if seed:
                    line["boundary"] = seed["ref"]
                    used_seeds.add(seed["ref"])
            else:
                side = sides.get(index, "right")
                if side == "facing":
                    side = self.facing(boxes[src], boxes.get(dst))
                line["fromSide"] = side
                if dst == END:
                    seed = take(seeded_out.get(norm(flow.get("label")), []))
                    line["rule"] = "L12" if side == "right" else "L13"
                    if seed:
                        line["boundary"] = seed["ref"]
                        used_seeds.add(seed["ref"])
                else:
                    line["toSide"] = self.entry_side(index, flow, side, boxes, main_edges)
                    line["rule"] = self.rule_id(index, side, line["toSide"], main_edges)
            if len(label) > self.style["label_max_chars"]:
                self.warn.append(f"{self.where()}: the label {json.dumps(label)} is longer than {self.style['label_max_chars']} characters")
            elif (src == START or dst == END) and len(label) > self.style["end_label_max_chars"]:
                self.warn.append(f"{self.where()}: the start or end label {json.dumps(label)} is longer than {self.style['end_label_max_chars']} characters; check that its returned free-end route leaves enough room beside the box")
            if src == dst and src != START:
                self.warn.append(f"{self.where()}: '{self.by_id[src]['name']}' has a line to itself; the editor draws it as a short loop over the box")
            lines.append(line)
        # A parent line with no label names no particular way in or out: it continues as the first free one.
        # Levels that pair by position (pair_boundary_by_order) do the same for any parent line left unmatched.
        for seeds, end_of in ((seeded_in, lambda ln: ln["from"] == START), (seeded_out, lambda ln: ln["to"] == END)):
            for key, group in seeds.items():
                for seed in group:
                    if seed["ref"] in used_seeds or (key and not self.pair_boundary_by_order):
                        continue
                    free = next((ln for ln in lines if end_of(ln) and "boundary" not in ln), None)
                    if free:
                        free["boundary"] = seed["ref"]
                        used_seeds.add(seed["ref"])
        for seeds, end in ((seeded_in, START), (seeded_out, END)):
            for label, group in seeds.items():
                for seed in group:
                    if seed["ref"] in used_seeds:
                        continue
                    # More parent lines with this label than START or END lines on this level: the extra parent
                    # line continues as a copy of the level's last line with that label, drawn over it.
                    twin = next((ln for ln in reversed(lines) if "boundary" in ln and norm(ln["label"]) == label
                                 and (ln["from"] if end == START else ln["to"]) == end), None)
                    if twin is None:
                        self.warn.append(f"{self.where()}: the parent line {json.dumps(seed['label'])} has no START or END line with the same label on this level, so the line add child seeds for it stays unattached")
                        continue
                    copy = dict(twin, ref=make_ref("~p", seed["ref"]), boundary=seed["ref"])
                    lines.append(copy)
                    used_seeds.add(seed["ref"])
                    box = twin["to"] if end == START else twin["from"]
                    self.warn.append(f"{self.where()}: {len(group)} parent lines labelled {json.dumps(seed['label'])} continue from '{self.by_id[box]['name']}'; the extra one is drawn over the first")

        self.shared_points(lines, boxes)
        box_list = list(boxes.values())
        for line in lines:
            a, b = boxes.get(line["from"]), boxes.get(line["to"])
            if a and b and line["from"] != line["to"]:
                hits = route_crossings(route(a, line["fromSide"], b, line["toSide"]), box_list, {a["key"], b["key"]})
                for hit in hits:
                    self.warn.append(f"{self.where()}: the line {json.dumps(line['label'])} from '{self.by_id[a['key']]['name']}' to '{self.by_id[b['key']]['name']}' may run through '{self.by_id[hit['key']]['name']}'")

        return {
            "slug": self.slug, "parent": self.parent,
            "title": self.model["meta"]["title"] if self.parent is None else self.by_id_any(self.parent)["name"],
            "boxes": [dict(boxes[n], id=n, ref=refs[n], name=self.by_id[n]["name"], resources=resources[n], overflow=getattr(self, "resource_overflow", {}).get(n, [])) for n in self.ids],
            "lines": lines,
        }

    def shared_points(self, lines, boxes):
        """Warn where middle-of-side attachment makes lines overlap or read as 'all must arrive'."""
        use = defaultdict(lambda: {"in": [], "out": []})
        for line in lines:
            if line["from"] in boxes and line.get("fromSide"):
                use[(line["from"], line["fromSide"])]["out"].append(line)
            if line["to"] in boxes and line.get("toSide"):
                use[(line["to"], line["toSide"])]["in"].append(line)
        for (node, side), u in use.items():
            name = self.by_id[node]["name"]
            if u["in"] and u["out"] and not all(l["from"] == l["to"] for l in u["in"]):
                labels = ", ".join(json.dumps(l["label"]) for l in u["out"] + u["in"])
                self.warn.append(f"{self.where()}: lines leave and enter the {side} of '{name}' at the same point and overlap ({labels})")
            if len(u["in"]) > 1 and self.by_id[node].get("join") != "all":
                labels = ", ".join(json.dumps(l["label"]) for l in u["in"])
                self.warn.append(f"{self.where()}: {len(u['in'])} lines enter the {side} of '{name}' at one point, which UPN reads as 'all must arrive' ({labels})")
        for line in lines:
            if line.get("rule") != "L02" or line["from"] not in boxes or line["to"] not in boxes:
                continue
            a, b = boxes[line["from"]], boxes[line["to"]]
            low, high = sorted((a["x"], b["x"]))
            for node, box in boxes.items():
                if node in (line["from"], line["to"]) or (box["band"], box["row"]) != (a["band"], a["row"]) or not low < box["x"] < high:
                    continue
                if use.get((node, "top"), {}).get("out"):
                    self.warn.append(f"{self.where()}: the loop {json.dumps(line['label'])} runs over the top of '{self.by_id[node]['name']}' and crosses the line that leaves its top")

    def by_id_any(self, ident):
        return next(a for a in self.model["activities"] if a["id"] == ident)

    def rule_id(self, index, from_side, to_side, main_edges):
        if index in self._loops:
            return "L02"
        if index in main_edges:
            return "L01"
        if to_side == "bottom":
            return "L07"
        if to_side == "top":
            return "L08"
        src = self.flow_by_index[index]["from"]
        if self.is_parallel(src, index):
            return "L09"
        return {"right": "L03", "top": "L04", "bottom": "L05"}.get(from_side, "L06")


def canvas_after(boxes, style):
    xs = [b["x"] for b in boxes] + [b["x"] + b["w"] for b in boxes]
    ys = [b["y"] for b in boxes] + [b["y"] + b["h"] for b in boxes]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    factor = 1 + 2 * style["canvas_margin_factor"]
    w = max((max(xs) - min(xs)) * factor, style["canvas_blank_width"])
    h = max((max(ys) - min(ys)) * factor, style["canvas_blank_height"])
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def inside(box, canvas):
    return box["x"] >= canvas[0] and box["y"] >= canvas[1] and box["x"] + box["w"] <= canvas[2] and box["y"] + box["h"] <= canvas[3]


SIDE_REUSE = 400   # cost of joining a side another line already uses: ends drawn on one point are hard to read


SIDE_PAIRS = [("bottom", "top"), ("top", "bottom"), ("right", "left"), ("left", "right"),
              ("bottom", "left"), ("bottom", "right"), ("top", "left"), ("top", "right"),
              ("right", "top"), ("left", "top"), ("right", "bottom"), ("left", "bottom"), ("bottom", "bottom"), ("top", "top")]


def route_length(points):
    return sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(points, points[1:]))


def plausible(a, b, pair, margin=20):
    sa, sb = pair
    acx, acy = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bcx, bcy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    below = b["y"] >= a["y"] + a["h"] + margin
    above = b["y"] + b["h"] <= a["y"] - margin
    right = b["x"] >= a["x"] + a["w"] + margin
    left = b["x"] + b["w"] <= a["x"] - margin
    return {
        ("bottom", "top"): below, ("top", "bottom"): above,
        ("right", "left"): right, ("left", "right"): left,
        ("bottom", "left"): b["x"] >= acx + margin and bcy >= a["y"] + a["h"] + margin,
        ("bottom", "right"): b["x"] + b["w"] <= acx - margin and bcy >= a["y"] + a["h"] + margin,
        ("top", "left"): b["x"] >= acx + margin and bcy <= a["y"] - margin,
        ("top", "right"): b["x"] + b["w"] <= acx - margin and bcy <= a["y"] - margin,
        ("right", "top"): b["y"] >= acy + margin and bcx >= a["x"] + a["w"] + margin,
        ("left", "top"): b["y"] >= acy + margin and bcx <= a["x"] - margin,
        ("right", "bottom"): b["y"] + b["h"] <= acy - margin and bcx >= a["x"] + a["w"] + margin,
        ("left", "bottom"): b["y"] + b["h"] <= acy - margin and bcx <= a["x"] - margin,
        ("bottom", "bottom"): abs(a["y"] - b["y"]) < 40 and (right or left),
        ("top", "top"): abs(a["y"] - b["y"]) < 40 and (right or left),
    }[pair]


def shared_run(p, q, r, t, min_run=20):
    """True when segment p-q runs along segment r-t (same line, overlapping by more than min_run px)."""
    if abs(p[0] - q[0]) < 1 and abs(r[0] - t[0]) < 1 and abs(p[0] - r[0]) < 6:
        lo, hi = max(min(p[1], q[1]), min(r[1], t[1])), min(max(p[1], q[1]), max(r[1], t[1]))
        return hi - lo > min_run
    if abs(p[1] - q[1]) < 1 and abs(r[1] - t[1]) < 1 and abs(p[1] - r[1]) < 6:
        lo, hi = max(min(p[0], q[0]), min(r[0], t[0])), min(max(p[0], q[0]), max(r[0], t[0]))
        return hi - lo > min_run
    return False


def crosses(p, q, r, t):
    """True when a vertical and a horizontal segment cross."""
    for (a, b), (c, d) in (((p, q), (r, t)), ((r, t), (p, q))):
        if abs(a[0] - b[0]) < 1 and abs(c[1] - d[1]) < 1:
            x, y = a[0], c[1]
            if min(c[0], d[0]) < x < max(c[0], d[0]) and min(a[1], b[1]) < y < max(a[1], b[1]):
                return True
    return False


def route_cost(points, routes):
    shared = crossing = 0
    for other in routes:
        for p, q in zip(points, points[1:]):
            for r, t in zip(other, other[1:]):
                if shared_run(p, q, r, t):
                    shared += 1
                elif crosses(p, q, r, t):
                    crossing += 1
    return shared * 3000 + crossing * 40


def choose_sides(a, b, boxes, usage, skip_keys, routes=()):
    """The pair of sides (from a, into b) whose likely route crosses the fewest other cards, does not run along
    another line, crosses few lines and is short, preferring sides no other line uses yet."""
    best = None
    pairs = [p for p in SIDE_PAIRS if plausible(a, b, p)] or [("right", "left")]
    for pair in pairs:
        points = route(a, pair[0], b, pair[1])
        crossings = len(route_crossings(points, boxes, skip_keys))
        score = (crossings * 10000 + route_cost(points, routes) + route_length(points)
                 + SIDE_REUSE * (usage[(a["key"], pair[0])] + usage[(b["key"], pair[1])]))
        if best is None or score < best[0]:
            best = (score, pair, points)
    return best[1]


SAME_SIDE_PAIRS = [("bottom", "bottom"), ("top", "top"), ("right", "right"), ("left", "left")]


def parallel_sides(a, b, taken, boxes, skip_keys, routes=(), max_length=None, busy=()):
    """Sides for one more line between two cards that a line already joins, so the two do not share one path: a pair
    no line between them uses yet (taken, as (side of a, side of b)), the same side on both cards first (bottom to
    bottom, then top to top), whose likely route crosses no card and runs along as few lines as possible. With
    max_length, a route longer than that is not taken; busy, as (card key, side), names sides lines to other cards
    use, which are not taken either. None when no pair qualifies."""
    best = None
    candidates = SAME_SIDE_PAIRS + [p for p in SIDE_PAIRS if p not in SAME_SIDE_PAIRS]
    for rank, pair in enumerate(candidates):
        if pair in taken or (a["key"], pair[0]) in busy or (b["key"], pair[1]) in busy:
            continue
        points = route(a, pair[0], b, pair[1])
        if route_crossings(points, boxes, skip_keys) or route_crossings(points[1:-1], [a, b], ()):
            continue
        if max_length is not None and route_length(points) > max_length:
            continue
        score = (0 if pair in SAME_SIDE_PAIRS else 1, route_cost(points, routes) + route_length(points), rank)
        if best is None or score < best[0]:
            best = (score, pair)
    return best[1] if best else None


def write_passes(boxes, style, canvas=None, placed=()):
    """The boxes each write can place, as the canvas grows around what is written; None when some never fit."""
    pending = list(boxes)
    canvas = canvas or (0, 0, style["canvas_blank_width"], style["canvas_blank_height"])
    placed, passes = list(placed), []
    while pending:
        fits = [b for b in pending if inside(b, canvas)]
        if not fits:
            return None
        passes.append(fits)
        placed += fits
        pending = [b for b in pending if b not in fits]
        canvas = canvas_after(placed, style)
    return passes


def fit_blank(boxes, style):
    """Move the layout onto a blank canvas so every card can be written in the fewest writes: centred, or with
    one edge anchored when the layout is bigger than the blank canvas."""
    if not boxes:
        return
    left = min(b["x"] for b in boxes)
    right = max(b["x"] + b["w"] for b in boxes)
    top = min(b["y"] for b in boxes)
    bottom = max(b["y"] + b["h"] for b in boxes)
    width, height = style["canvas_blank_width"], style["canvas_blank_height"]
    margin = 40
    xs = [int(round(width / 2 - (left + right) / 2)), margin - left, int(width - margin - right)]
    ys = [int(round(height / 2 - (top + bottom) / 2)), margin - top, int(height - margin - bottom)]
    best = None
    for dy in ys:
        for dx in xs:
            moved = [dict(b, x=b["x"] + dx, y=b["y"] + dy) for b in boxes]
            passes = write_passes(moved, style)
            if passes is not None and (best is None or len(passes) < best[0]):
                best = (len(passes), dx, dy)
    if best is None:
        raise PlanError("the cards cannot be placed so that every one fits the canvas; split the data model")
    for box in boxes:
        box["x"] += best[1]
        box["y"] += best[2]


def overlaps(a, b, margin=0):
    return (a["x"] < b["x"] + b["w"] + margin and b["x"] < a["x"] + a["w"] + margin
            and a["y"] < b["y"] + b["h"] + margin and b["y"] < a["y"] + a["h"] + margin)


def free_spot(anchor, size, occupied, canvas, style):
    """A position for a new card next to anchor (a box) that overlaps nothing and lies inside the canvas."""
    w, h = size
    gap, row_gap = style["col_gap"], style["row_gap"]
    margin = gap / 2
    candidates = []
    if anchor:
        ax, ay, aw, ah = anchor["x"], anchor["y"], anchor["w"], anchor["h"]
        for k in (0, 1, -1, 2, -2, 3, -3, 4, -4):
            candidates.append((ax + k * (w + gap), ay + ah + row_gap))
        for k in range(0, 6):
            candidates.append((ax + aw + gap + k * (w + gap), ay))
            candidates.append((ax - gap - w - k * (w + gap), ay))
        candidates.append((ax, ay - row_gap - h))
    cx = (canvas[0] + canvas[2]) / 2 if not anchor else anchor["x"]
    cy = (canvas[1] + canvas[3]) / 2 if not anchor else anchor["y"]
    grid = [(x, y) for x in range(int(canvas[0]) + 20, int(canvas[2] - w), 40) for y in range(int(canvas[1]) + 20, int(canvas[3] - h), 40)]
    grid.sort(key=lambda p: abs(p[0] - cx) + abs(p[1] - cy))
    for x, y in candidates + grid:
        box = {"x": int(x), "y": int(y), "w": w, "h": h}
        if inside(box, canvas) and not any(overlaps(box, o, margin) for o in occupied):
            return box["x"], box["y"]
    raise PlanError("no free space on the canvas for a new card; amend with --relayout")


def simulate_attributes(current, desired, allow_remove):
    """The attribute changes that turn current into desired, applied in order, and the titles that result."""
    ops, kept = [], []
    wanted = {norm(d["title"]) for d in desired}
    sim = []
    for attribute in current:
        if norm(attribute["title"]) in wanted:
            sim.append(attribute)
        elif allow_remove:
            ops.append({"op": "remove", "key": attribute["key"], "title": attribute["title"]})
        else:
            kept.append(attribute["title"])
            sim.append(attribute)
    for position, item in enumerate(desired, start=1):
        titles = [norm(a["title"]) for a in sim]
        if norm(item["title"]) not in titles:
            ops.append({"op": "add", "title": item["title"], "description": item.get("description", ""), "position": min(position, len(sim) + 1)})
            sim.insert(min(position, len(sim) + 1) - 1, {"title": item["title"]})
            continue
        index = titles.index(norm(item["title"]))
        current_item = sim[index]
        update = {}
        if item.get("description") and (current_item.get("description") or "") != item["description"]:
            update["description"] = item["description"]
        if index != position - 1 and index > position - 1:
            update["position"] = position
            sim.insert(position - 1, sim.pop(index))
        if update and "key" in current_item:
            ops.append(dict({"op": "update", "key": current_item["key"], "title": item["title"]}, **update))
    return ops, kept, [a["title"] for a in sim]


def moves_in_passes(state, moves, canvas, style):
    """Split moves (id -> target box) into writes: each write moves the cards whose target lies inside the
    canvas as it is after the writes before it."""
    state = {k: dict(v) for k, v in state.items()}
    pending = dict(moves)
    passes = []
    while pending:
        fits = [k for k, box in pending.items() if inside(box, canvas)]
        if not fits:
            raise PlanError("some cards cannot be moved inside the canvas; amend again without --relayout")
        passes.append(fits)
        for k in fits:
            state[k] = dict(pending.pop(k))
        canvas = canvas_after(list(state.values()), style)
    return passes


# ---- level notes (a sticky note beside one box of a level, such as the usage note by step 1)

NOTE_SIZE = (150, 150)   # the server draws every note 150 x 150 px, whatever its text
NOTE_GAP = 30            # space between the note and the box it sits beside
NOTE_CLEARANCE = 12      # space kept between the note and any line
LABEL_BOX = (130, 70)    # room a free-end label takes around its line: about 20 characters a line, up to five lines


def line_paths(boxes, lines, style):
    """The ground each line of a level covers, for keeping a note off it: a list of (points, label_rect or None).

    boxes: {id: box with x, y, w, h}. lines: dicts with from and to (an id, or START / END for a free end) and the
    sides fromSide / toSide. A box-to-box line follows route(); a free start or end runs free_end_length out from its
    side (free_end_length_vertical from a top or bottom side), with its label centred on it."""
    paths = []
    for line in lines:
        src, dst = line.get("from"), line.get("to")
        a, b = boxes.get(src), boxes.get(dst)
        if a is not None and b is not None and src != dst:
            paths.append((route(a, line.get("fromSide") or "right", b, line.get("toSide") or "left"), None))
            continue
        box, side = (b, line.get("toSide") or "left") if a is None else (a, line.get("fromSide") or "right")
        if box is None:
            continue
        p = side_point(box, side)
        length = style["free_end_length"] if side in ("left", "right") else style["free_end_length_vertical"]
        d = STEP[side]
        q = (p[0] + d[0] * length, p[1] + d[1] * length)
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        lw, lh = LABEL_BOX
        label = {"x": mx - lw / 2, "y": my - lh / 2, "w": lw, "h": lh} if line.get("label") else None
        paths.append(([p, q], label))
    return paths


def level_note_spot(anchor, boxes, paths, canvas, size=NOTE_SIZE, gap=NOTE_GAP):
    """Where a level note goes beside anchor (the box it belongs to): (x, y) of its top-left corner, or None.

    Tried in this order, the first that is inside the canvas (x0, y0, x1, y1), overlaps no box (with gap to spare)
    and keeps NOTE_CLEARANCE off every line and free-end label: above-left of the box, directly above it, below-left,
    directly below, then further out to the left. A note above-left sits over the level's start line and left of
    any line into the box's top, so it reads as belonging to step 1 without covering anything."""
    w, h = size
    ax, ay, aw, ah = anchor["x"], anchor["y"], anchor["w"], anchor["h"]
    candidates = [(ax - gap - w, ay - gap - h), (ax, ay - gap - h), (ax - gap - w, ay + ah + gap), (ax, ay + ah + gap),
                  (ax - 2 * (gap + w), ay - gap - h), (ax - 2 * (gap + w), ay + ah + gap)]
    others = [b for b in boxes if b is not anchor]
    for x, y in candidates:
        note = {"x": int(round(x)), "y": int(round(y)), "w": w, "h": h}
        if not inside(note, canvas):
            continue
        if overlaps(note, anchor) or any(overlaps(note, b, gap) for b in others):
            continue
        if any(segment_hits_box(p, q, note, -NOTE_CLEARANCE) for points, _ in paths for p, q in zip(points, points[1:])):
            continue
        if any(label and overlaps(note, label) for _, label in paths):
            continue
        return note["x"], note["y"]
    return None
