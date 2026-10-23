#!/usr/bin/env python3
"""Write the brief each process-level-writer agent works from.

Usage:
  prepare_briefs.py top --inventory inventory.json --out briefs/top.json --outline-path levels/top.json [--title TEXT]
  prepare_briefs.py children --inventory inventory.json --outline levels/top.json --out-dir briefs/ [--levels-dir levels/]

A capability whose main object has a lifecycle (common.lifecycle_plan) gets a lifecycle brief instead of a
detail brief: one step per status or stage value. With record types (route metadata), its level is a split
by record type, which this script writes itself (outline source "record-type-split"), and each record type
gets a lifecycle brief of its own (level "<capability>--<record type>").

top       one brief for the top level: one item per top-level capability (or area),
          with what each owns, the capabilities it depends on, and a suggested order.
children  one brief per box of a written level whose step stands for a capability:
          an overview brief when the capability is an area with capabilities under
          it, otherwise a detail brief listing every object the level must use, the
          relationships between them, a suggested order (records before the records
          that point at them), and the labels of the lines into and out of the parent
          box, which the child level copies exactly.

A brief holds data only; how to write a level is in references/articulation-rules.md
(its rulesPath). The writer checks its outline with the plugin's scripts/check_outline.py,
which reads the brief's cover and budget: every object used (or explained in a gap),
the parent's labels copied, one box per capability on overview levels.
Exit 0 on success, 1 when the outline or inventory has a problem the brief cannot
be written around, 2 on a setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import common
from common import SetupError

MAX_STEPS = 10  # boxes on one level (max_boxes_per_level in the plugin's data/style-process.csv)
RULES = common.SKILL / "references" / "articulation-rules.md"  # how the writer turns a brief into a level


def load_inventory(path):
    inv = common.load_json(path, "inventory")
    errors = common.shape_errors(inv, "inventory.schema.json")
    if errors:
        raise SetupError("the inventory does not match its schema; run inventory.py check first:\n  " + "\n  ".join(errors[:10]))
    if not inv.get("capabilities"):
        raise SetupError("the inventory has no capabilities yet; apply the grouping with inventory.py set-capabilities first")
    stop = common.usage_stop(inv)
    if stop:
        raise SetupError(stop)
    return inv


def index(inv):
    objects = {o["apiName"]: o for o in inv["objects"]}
    caps = {c["id"]: c for c in inv["capabilities"]}
    children = defaultdict(list)
    for cap in inv["capabilities"]:
        if cap.get("parent"):
            children[cap["parent"]].append(cap["id"])
    owner = {a: c["id"] for c in inv["capabilities"] for a in c["objects"]}
    rels = [r for r in inv.get("relationships", []) if not r.get("polymorphic")]
    return objects, caps, children, owner, rels, inv


def leaf_ids(cap_id, children):
    if not children.get(cap_id):
        return [cap_id]
    return [leaf for kid in children[cap_id] for leaf in leaf_ids(kid, children)]


def topo_order(items, depends, tiebreak):
    """Kahn's algorithm; depends[x] = {y: weight} means x comes after y. Cycles are broken
    by taking the item with the least unresolved weight."""
    remaining = list(items)
    placed, order = set(), []
    while remaining:
        ready = [x for x in remaining if all(y in placed or y not in items for y in depends.get(x, {}))]
        if not ready:
            ready = [min(remaining, key=lambda x: (sum(w for y, w in depends.get(x, {}).items() if y not in placed), tiebreak(x)))]
        pick = min(ready, key=tiebreak)
        order.append(pick)
        placed.add(pick)
        remaining.remove(pick)
    return order


def capability_item(cap, inv_index):
    objects, caps, children, owner, rels, _ = inv_index
    leaves = leaf_ids(cap["id"], children)
    owned = [a for leaf in leaves for a in caps[leaf]["objects"]]
    unused = set(common.unused_objects(inv_index[5], owned))
    owned_all, owned = owned, [a for a in owned if a not in unused]  # basis usage: objects holding no records are not offered
    inbound = Counter(r["to"] for r in rels if r["to"] in owned and r["from"] in owned)
    key = sorted(owned, key=lambda a: (-inbound[a], owned.index(a)))[:5]
    item = {"capability": cap["id"], "name": cap["name"], "origin": cap["origin"],
            "ownedObjects": len(owned), "keyObjects": [objects[a]["name"] for a in key if a in objects]}
    workflows = [f"{objects[a]['name']} {objects[a]['lifecycle']['label']}: " + ", ".join(v["value"] for v in objects[a]["lifecycle"]["values"])
                 for a in owned if a in objects and objects[a].get("lifecycle")]
    if workflows:
        item["lifecycles"] = workflows
    if unused:
        item["ownedObjects"] = len(owned_all)
        item["withoutRecords"] = [objects[a]["name"] for a in owned_all if a in unused]
    for field in ("description", "docUrl", "helpLinks", "supporting"):
        if cap.get(field):
            item[field] = cap[field]
    if children.get(cap["id"]):
        item["capabilities"] = [caps[k]["name"] for k in children[cap["id"]]]
    return item


def capability_dependencies(ids, inv_index):
    """depends[a][b] = number of reference fields from a's objects to b's objects."""
    objects, caps, children, owner, rels, _ = inv_index
    group = {}
    for cid in ids:
        for leaf in leaf_ids(cid, children):
            for api in caps[leaf]["objects"]:
                group[api] = cid
    depends = defaultdict(Counter)
    for rel in rels:
        a, b = group.get(rel["from"]), group.get(rel["to"])
        if a and b and a != b:
            depends[a][b] += 1
    return depends


def overview_brief(level, title, ids, inv, inv_index, outline_path, parent=None):
    objects, caps, children, owner, rels, _ = inv_index
    depends = capability_dependencies(ids, inv_index)
    position = {cid: i for i, cid in enumerate(ids)}
    order = topo_order(ids, depends, lambda c: (bool(caps[c].get("supporting")), position[c]))
    items = []
    for cid in ids:
        item = capability_item(caps[cid], inv_index)
        if depends.get(cid):
            item["dependsOn"] = [{"capability": b, "name": caps[b]["name"], "references": n}
                                 for b, n in depends[cid].most_common()]
        items.append(item)
    brief = {"level": level, "mode": "overview", "system": inv["system"], "route": inv["route"],
             "title": title, "outlinePath": str(outline_path), "rulesPath": str(RULES), "parent": parent,
             "items": items, "suggestedOrder": order,
             "cover": {"items": list(ids)},
             "budget": {"min": len(ids), "max": MAX_STEPS}}
    if inv.get("variant"):
        brief["variant"] = inv["variant"]
    return brief


def detail_brief(cap, inv, inv_index, outline_path, parent):
    objects, caps, children, owner, rels, _ = inv_index
    table, default = common.load_archetypes()
    owned = [a for a in cap["objects"] if a in objects]
    shared = common.shared_objects(inv, cap)
    # basis usage: an object that holds no records is not offered to the writer; the build names it in a note
    excluded = common.unused_objects(inv, owned + shared)
    owned = [a for a in owned if a not in excluded]
    shared = [a for a in shared if a not in excluded]
    owned_set = set(owned)
    scope = owned_set | set(shared)

    depends = defaultdict(Counter)
    detail_count = Counter()
    for rel in rels:
        if rel["from"] in owned_set and rel["to"] in owned_set and rel["from"] != rel["to"]:
            depends[rel["from"]][rel["to"]] += 1
            detail_count[rel["to"]] += 1
    arche = {a: common.archetype_of(objects[a]["name"], table, default) for a in owned}
    position = {a: i for i, a in enumerate(owned)}
    order = topo_order(owned, depends, lambda a: (arche[a]["position"], -detail_count[a], position[a]))

    def describe(api, full):
        obj = objects[api]
        row = {"apiName": api, "name": obj["name"]}
        if obj.get("description"):
            row["description"] = obj["description"][:600] if full else common.first_sentence(obj["description"])
        if obj.get("kind"):
            row["kind"] = obj["kind"]
        if full:
            row["archetype"] = arche[api]["archetype"]
            row["typicalVerbs"] = arche[api]["verbs"]
            for field in ("keyFields", "hasRecords", "docUrl", "lifecycle"):
                if field in obj:
                    row[field] = obj[field]
            if row.get("lifecycle", {}).get("recordTypes"):  # record type usage is for the build, not the writer
                row["lifecycle"] = dict(row["lifecycle"], recordTypes=[{k: v for k, v in rt.items() if k != "usage"}
                                                                       for rt in row["lifecycle"]["recordTypes"]])
        elif owner.get(api):
            row["ownedBy"] = caps[owner[api]]["name"]
        return row

    relationships = []
    for rel in rels:
        if rel["from"] in scope and rel["to"] in scope and (rel["from"] in owned_set or rel["to"] in owned_set):
            row = {"from": rel["from"], "to": rel["to"], "kind": rel.get("kind", "lookup")}
            if rel.get("field"):
                row["field"] = rel["field"]
            if rel.get("required"):
                row["required"] = True
            relationships.append(row)

    n = len(owned)
    capability = {"id": cap["id"], "name": cap["name"], "origin": cap["origin"]}
    for field in ("description", "docUrl", "helpLinks"):
        if cap.get(field):
            capability[field] = cap[field]
    brief = {"level": cap["id"], "mode": "detail", "system": inv["system"], "route": inv["route"],
             "capability": capability, "outlinePath": str(outline_path), "rulesPath": str(RULES), "parent": parent,
             "objects": [describe(a, True) for a in order],
             "sharedObjects": [describe(a, False) for a in shared],
             "relationships": relationships,
             "suggestedOrder": order,
             "cover": {"uses": order, "mayUse": shared},
             "budget": {"min": min(2, max(n, 1)), "max": MAX_STEPS, "objectsToCover": n,
                        "typicalSteps": [min(MAX_STEPS, max(2, math.ceil(n / 3))), min(MAX_STEPS, max(3, math.ceil(n * 0.75)))]}}
    if inv.get("variant"):
        brief["variant"] = inv["variant"]
    if excluded:
        brief["excludedByUsage"] = [{"apiName": a, "name": objects[a]["name"]} for a in excluded]
    unknown = common.unknown_usage(inv, owned + shared)
    if unknown:
        brief["usageUnknown"] = unknown
    return brief


def lifecycle_brief(cap, plan, rt, inv, inv_index, outline_path, parent, level):
    """A level built on one lifecycle: one step per value (articulation-rules.md section 4a). The capability's
    other objects are used on those steps; with a record type, only the values that record type uses."""
    brief = detail_brief(cap, inv, inv_index, outline_path, parent)
    objects = inv_index[0]
    cover = common.lifecycle_cover(plan, rt)
    brief.update({"level": level, "mode": "lifecycle", "lifecycle": cover,
                  "object": {"apiName": plan["object"], "name": plan["name"],
                             "description": objects[plan["object"]].get("description", "")[:600]}})
    brief["cover"]["lifecycle"] = cover
    n = len(cover["values"])
    brief["budget"] = {"min": n, "max": max(MAX_STEPS, n + 2), "objectsToCover": brief["budget"]["objectsToCover"], "typicalSteps": [n, n + 1]}
    if rt:
        brief["recordType"] = {"name": rt["name"], "label": rt["label"]}
        # the record types' levels share the capability's other objects: each level must show the lifecycle
        # object, and uses the others where its record type's work touches them (the coverage check, C02,
        # then sees that every owned object is used on some record type's level)
        others = [a for a in brief["cover"]["uses"] if a != plan["object"]]
        brief["cover"]["uses"] = [plan["object"]]
        brief["cover"]["mayUse"] = others + [a for a in brief["cover"]["mayUse"] if a not in others]
        brief["recordTypeLevels"] = len(plan["recordTypes"])
    return brief


def split_outline(cap, plan, parent, roles, level):
    """The record-type split, written here rather than by a writer: a first step that settles which kind of
    record is needed ("Decide which team member to capture"), then one step per record type ("Process Contractor
    team member", reached by "Contractor team member needed"), each drilling down to its own lifecycle level."""
    name = plan["name"]
    lower = " ".join(w if len(w) > 1 and w.isupper() else w.lower() for w in name.split())  # "team member", "CPQ quote"
    a_lower = ("an " if lower[:1] in "aeiou" else "a ") + lower  # "an opportunity", "a team member"
    roles = roles or [{"name": "Process owner"}]
    steps = [{"id": "choose", "name": f"Decide which {lower} to capture", "uses": [plan["object"]], "roles": roles,
              "what": f"Someone needs {a_lower} and decides which kind it is: each record type of {name} follows its own process.",
              "why": "The record type decides which statuses, fields and automation apply to the record.", "next": []}]
    taken = {"choose"}
    for rt in plan["recordTypes"]:
        base = sid = "rt-" + (common.slug(rt["name"], 34) or "type")
        n = 2
        while sid in taken:
            sid, n = f"{base[:36]}-{n}", n + 1
        taken.add(sid)
        # "Dealer claim", not "Dealer claim claim", when the label already names the object
        box = rt["label"] if common.norm(rt["label"]).endswith(common.norm(name)) else f"{rt['label']} {lower}"
        # short: the label is drawn again on the record type level's start line, which has room for 40 characters
        steps[0]["next"].append({"to": sid, "outcome": f"{box} needed"})
        steps.append({"id": sid, "name": f"Process {box}"[:100], "item": rt["level"], "uses": [plan["object"]],
                      "roles": roles, "what": f"{a_lower[:1].upper()}{a_lower[1:]} of record type {rt['label']} is created and taken through its {plan['fieldLabel'].lower()} values"
                                              + (f" (its process, {rt['process']})" if rt.get("process") else "") + ": "
                                              + ", ".join(v["value"] for v in rt["values"]) + ".",
                      "why": f"Records of type {rt['label']} follow their own lifecycle."})
    inputs = (parent or {}).get("inputs") or [f"New {lower} needed"]
    outputs = (parent or {}).get("outputs") or []
    outline = {"schemaVersion": "1.0", "level": level, "source": "record-type-split",
               "steps": steps, "starts": [{"to": "choose", "trigger": label} for label in inputs], "ends": []}
    for step, rt in zip(steps[1:], plan["recordTypes"]):
        box = rt["label"] if common.norm(rt["label"]).endswith(common.norm(name)) else f"{rt['label']} {lower}"
        for label in outputs or [f"{box} processed"]:
            outline["ends"].append({"from": step["id"], "outcome": label})
    return outline


def write_capability_level(cap, inv, inv_index, plans, parent, roles, level, levels_dir, out_dir, title=None):
    """Write what a capability's level needs: a lifecycle brief, a record-type split outline and one lifecycle
    brief per record type, or a detail brief. Returns [(id, mode, path)]."""
    written = []
    plan = plans.get(cap["id"])
    outline_path = levels_dir / f"{level}.json"
    if plan and plan["recordTypes"]:
        outline = split_outline(cap, plan, parent, roles, level)
        common.write_json(outline_path, outline)
        written.append((level, "split", outline_path))
        for step in outline["steps"][1:]:
            rt = next(r for r in plan["recordTypes"] if r["level"] == step["item"])
            inputs, outputs = common.outline_boundary(outline, step["id"])
            rt_parent = {"level": level, "stepId": step["id"], "name": step["name"], "inputs": inputs, "outputs": outputs}
            brief = lifecycle_brief(cap, plan, rt, inv, inv_index, levels_dir / f"{rt['level']}.json", rt_parent, rt["level"])
            out = Path(out_dir) / f"{rt['level']}.json"
            common.write_json(out, brief)
            written.append((rt["level"], "lifecycle", out))
        return written
    if plan:
        brief = lifecycle_brief(cap, plan, None, inv, inv_index, outline_path, parent, level)
    else:
        brief = detail_brief(cap, inv, inv_index, outline_path, parent)
        brief["level"] = level
    if title:
        brief["title"] = title[:80]
    out = Path(out_dir) / f"{level}.json"
    common.write_json(out, brief)
    written.append((level, brief["mode"], out))
    return written


def cmd_top(args):
    inv = load_inventory(args.inventory)
    inv_index = index(inv)
    top_ids = [c["id"] for c in inv["capabilities"] if not c.get("parent")]
    if inv.get("focus"):
        # One object's process: the top level is the capability's own steps (its lifecycle, or the split by
        # record type), not a box standing for it.
        if len(top_ids) != 1 or inv_index[2].get(top_ids[0]):
            raise SetupError("an inventory with a focus object has exactly one capability and no areas; run inventory.py focus")
        cap = inv_index[1][top_ids[0]]
        plans = common.lifecycle_plan(inv)
        written = write_capability_level(cap, inv, inv_index, plans, None, None, "top", Path(args.outline_path).parent,
                                         Path(args.out).parent, args.title or cap["name"])
        for level, mode, path in written:
            print(f"{mode:9} {level} -> {path}")
        print(f"Top level for {cap['name']} (focus {inv['focus']}): {len(written)} file(s).")
        return 0
    title = args.title or f"Business Process ({inv['system']})"
    brief = overview_brief("top", title[:80], top_ids, inv, inv_index, args.outline_path)
    common.write_json(args.out, brief)
    print(f"Top-level brief: {len(top_ids)} capabilit(ies); written to {args.out}.")
    return 0


def cmd_children(args):
    inv = load_inventory(args.inventory)
    inv_index = index(inv)
    objects, caps, children, owner, rels, _ = inv_index
    outline = common.load_json(args.outline, "outline")
    errors = common.process_levels.shape_errors(outline, common.OUTLINE_SCHEMA) or common.outline_errors(outline)
    if errors:
        for line in errors:
            print(f"ERROR {args.outline}: {line}")
        return 1
    levels_dir = Path(args.levels_dir) if args.levels_dir else Path(args.outline).parent
    plans = common.lifecycle_plan(inv)
    written, problems = [], []
    for step in outline["steps"]:
        cid = step.get("item")
        if not cid:
            continue
        cap = caps.get(cid)
        if cap is None:
            problems.append(f"step '{step['id']}' stands for capability '{cid}', which is not in the inventory")
            continue
        inputs, outputs = common.outline_boundary(outline, step["id"])
        parent = {"level": outline["level"], "stepId": step["id"], "name": step["name"],
                  "inputs": inputs, "outputs": outputs}
        outline_path = levels_dir / f"{cid}.json"
        if children.get(cid):
            brief = overview_brief(cid, step["name"], children[cid], inv, inv_index, outline_path, parent)
            out = Path(args.out_dir) / f"{cid}.json"
            common.write_json(out, brief)
            written.append((cid, brief["mode"], out))
        else:
            written += write_capability_level(cap, inv, inv_index, plans, parent, step.get("roles"), cid, levels_dir, args.out_dir)
    for line in problems:
        print(f"ERROR {line}")
    for cid, mode, out in written:
        print(f"{mode:9} {cid} -> {out}")
    print(f"{len(written)} brief(s) written, {len(problems)} problem(s).")
    return 1 if problems else 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Write the briefs for the process-level-writer agents.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("top")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--outline-path", type=Path, required=True, help="where the writer saves the top-level outline")
    p.add_argument("--title")
    p = sub.add_parser("children")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--outline", type=Path, required=True, help="a written level whose boxes stand for capabilities")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--levels-dir", type=Path, help="where child outlines go; the outline's folder when left out")
    args = parser.parse_args(argv)
    try:
        return {"top": cmd_top, "children": cmd_children}[args.command](args)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
