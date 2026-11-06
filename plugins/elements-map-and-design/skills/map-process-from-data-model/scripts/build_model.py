#!/usr/bin/env python3
"""Turn the level outlines and the inventory into one business-architecture model.

Usage:
  build_model.py --inventory inventory.json --levels-dir levels/ --out model.json [--title TEXT] [--scope scope.json]

Starts from levels/top.json and follows every step that stands for a capability
to levels/<capability id>.json, so the model holds the whole hierarchy. It:
  - checks every outline against the plugin's schemas/level-outline.schema.json and its rules
    (the level walk itself is the plugin's scripts/process_levels.py);
  - checks each child level starts and ends with the labels of the lines into and
    out of its parent box (an extra start or end is a warning and a gap);
  - gives every step, role, object and capability a model id;
  - writes 'About this step' notes (what happens, why, the objects used), the
    capability's help links on its box, and on route metadata a metadata
    attachment per object, so the box links to the object in Elements;
  - adds the objects as entities with their relationships, and the capabilities
    with what realises them, so the same model can later be drawn as a data
    model or a capability map;
  - with --scope, adds a gap for each level meant to come from Elements' org-to-process
    that the stage-5 fallback (a process-level-writer) wrote instead, with the reason
    scope.json records (common.fallback_levels).

Run scripts/validate.py MODEL --for process and check_coverage.py next.
Exit 0: model written, no errors. 1: errors to fix (the model is written when
its shape is valid, so the findings can be inspected). 2: setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import common
import usage_notes
from common import SetupError, model_id, norm
MAIN_OBJECTS = 2       # records a box standing for a capability shows
MAIN_OBJECTS_AREA = 3  # records a box standing for an area shows
# inventory kind -> Elements metadata type of the attachment that links a box to its object (route metadata)
NODE_ID = re.compile(r"[a-f0-9]{24}")
METADATA_TYPE = {"standard": "Standard Object", "custom": "Custom Object", "managed": "Custom Object"}
# inventory kind -> entity kind in ba-model.schema.json, which has no separate managed kind
ENTITY_KIND = {"standard": "standard", "custom": "custom", "managed": "custom", "external": "external"}


class Builder(common.process_levels.LevelWalker):
    """The shared level walk (scripts/process_levels.py) plus what a data model adds: objects as
    Object resources and entities, capabilities with what realises them, metadata attachments."""

    def __init__(self, inv, levels_dir):
        super().__init__(levels_dir)
        self.inv = inv
        self.ref_model_id = next((source["ref"] for source in inv["sources"] if source["kind"] == "metadata"), None)
        self.objects = {o["apiName"]: o for o in inv["objects"]}
        self.caps = {c["id"]: c for c in inv.get("capabilities", [])}
        self.children = defaultdict(list)
        for cap in inv.get("capabilities", []):
            if cap.get("parent"):
                self.children[cap["parent"]].append(cap["id"])
        self.used_objects = []
        self.realised = defaultdict(list)
        self.focus = inv.get("focus")
        self.basis = common.inventory_basis(inv)
        self.unused = set(common.unused_objects(inv))  # basis usage: objects holding no records, left off every box
        self.noted_capabilities = set()
        self.plans = common.lifecycle_plan(inv)
        self.lifecycle_levels = common.lifecycle_levels(self.plans)
        self.record_type_levels = {rt["level"]: (plan, rt) for plan in self.plans.values() for rt in plan["recordTypes"]}
        self.split_levels = {plan["level"] for plan in self.plans.values() if plan["recordTypes"]}
        # basis usage: every level a lifecycle drives (object lifecycle, record-type split, record-type lifecycle)
        # gets a usage note beside step 1 (usage_notes.py); the level's list of objects holding no records moves
        # from its first box's note into that note
        self.usage_levels = (set(self.lifecycle_levels) | self.split_levels) if self.basis == "usage" else set()
        self.level_notes, self.level_parent = [], {}
        self.inbound = defaultdict(int)  # api -> references from other objects of the same capability
        owner = {a: c["id"] for c in inv.get("capabilities", []) for a in c.get("objects", [])}
        for rel in inv.get("relationships", []):
            if rel["from"] != rel["to"] and owner.get(rel["from"]) and owner.get(rel["from"]) == owner.get(rel["to"]):
                self.inbound[rel["to"]] += 1

    # ------------------------------------------------------------ hooks

    def walk(self, level, parent_activity=None, *args, **kwargs):
        self.level_parent.setdefault(level, parent_activity)  # the box a level drills down from, for its level notes
        return super().walk(level, parent_activity, *args, **kwargs)

    def overview(self, level):
        if self.focus:
            return False  # one object's process: the top level holds the capability's own steps
        return level == "top" or bool(self.children.get(level))

    def leaves(self, cid):
        kids = self.children.get(cid)
        return [leaf for k in kids for leaf in self.leaves(k)] if kids else [cid]

    def main_objects(self, cid):
        """The records a box standing for a capability (two) or an area (three) shows as resources:
        objects with a lifecycle first, then those the capability's other objects point at most."""
        owned = [a for leaf in self.leaves(cid) for a in self.caps[leaf].get("objects", []) if a in self.objects and a not in self.unused]
        ranked = sorted(owned, key=lambda a: (0 if self.objects[a].get("lifecycle") else 1, -self.inbound[a], owned.index(a)))
        return ranked[:MAIN_OBJECTS_AREA if self.children.get(cid) else MAIN_OBJECTS]

    def sets_entity(self, obj):
        if obj in {p["object"] for p in self.plans.values()}:
            self.ensure_object(obj)
            return model_id("obj", obj)
        return None

    def objects_set_by(self, step_id):
        """Objects whose lifecycle value a line out of (or a start into) this step sets: the step works on them."""
        outline = getattr(self, "outline", None) or {}
        found = [l["sets"]["object"] for s in outline.get("steps", []) if s["id"] == step_id for l in s.get("next", []) if l.get("sets")]
        found += [e["sets"]["object"] for e in outline.get("ends", []) if e["from"] == step_id and e.get("sets")]
        found += [t["sets"]["object"] for t in outline.get("starts", []) if t["to"] == step_id and t.get("sets")]
        return [a for a in found if a in self.objects]

    def expected_items(self, level):
        return [c["id"] for c in self.inv.get("capabilities", []) if (c.get("parent") or "top") == level]

    def child_level(self, level, outline, step):
        cid = step.get("item")
        if level in self.split_levels and cid in self.record_type_levels:
            return cid
        if self.overview(level) and cid in self.caps and cid in self.expected_items(level):
            return cid
        return None

    def decorate(self, level, step, activity, here, overview):
        objects = list(step.get("uses", []))
        if overview and objects:
            self.warn(here, "objects are listed on a box that stands for a capability; they belong on its child level, and the build shows the capability's main records instead")
        if overview:
            objects = self.main_objects(step["item"]) if step.get("item") in self.caps else []
        else:
            objects += [a for a in self.objects_set_by(step["id"]) if a not in objects]
        objects = [a for a in objects if a not in self.unused]  # basis usage: not shown; the level's note names them
        uses = []
        for api in objects:
            if api not in self.objects:
                self.error(here, f"uses '{api}', which is not an object in the inventory")
                continue
            uses.append(model_id("obj", api))
            if api not in self.used_objects:
                self.used_objects.append(api)
        if uses:
            activity["uses"] = common.dedupe(uses)
        if self.focus and not overview:
            for cap in self.inv.get("capabilities", []):
                if self.focus in cap.get("objects", []) and level == "top":
                    self.realised[cap["id"]].append(activity["id"])
        cid = step.get("item")
        if level in self.split_levels and cid in self.record_type_levels:
            plan, rt = self.record_type_levels[cid]
            if self.inv["route"] == "metadata":
                activity["attachments"].append({"type": "metadata", "apiName": rt["name"], "metadataType": "Record Type",
                                                **({"refModelId": self.ref_model_id} if self.ref_model_id else {}),
                                                "text": f"Record type {rt['label']} of {plan['name']}"})
            cid = None
        value_box = level in self.lifecycle_levels and bool(step.get("value"))
        if value_box:
            plan, _ = self.lifecycle_levels[level]
            if self.inv["route"] == "metadata":
                # a value box links its Custom Value and nothing else: the field and the objects are on every box
                # of the level, so linking them only repeats the same items on the documentation. The nodeId is
                # the value on the field (a standard value set holds a second value of the same name).
                row = next((v for v in plan["values"] if v["value"] == step["value"]), {})
                activity["attachments"].append({"type": "metadata", "apiName": step["value"], "metadataType": "Custom Value",
                                                **({"refModelId": self.ref_model_id} if self.ref_model_id else {}),
                                                **({"nodeId": row["nodeId"]} if NODE_ID.fullmatch(str(row.get("nodeId", ""))) else {}),
                                                "text": f"{plan['fieldLabel']} value this step puts the {plan['name']} in"})
        if cid:
            if not overview:
                self.warn(here, f"names capability '{cid}' on a detail level; ignored")
            elif cid not in self.caps:
                self.error(here, f"stands for capability '{cid}', which is not in the inventory")
            else:
                self.realised[cid].append(activity["id"])
                activity["attachments"] += [{"type": "link", "title": l["title"], "url": l["url"]} for l in self.caps[cid].get("helpLinks", [])]
        elif overview:
            self.error(here, "a box on this level stands for a capability, so give the step its capability id as item")
        if self.inv["route"] == "metadata" and not overview and not value_box:
            for api in objects:
                obj = self.objects.get(api)
                if obj and obj.get("kind") in METADATA_TYPE:
                    activity["attachments"].append({"type": "metadata", "apiName": api, "metadataType": METADATA_TYPE[obj["kind"]],
                                                    **({"refModelId": self.ref_model_id} if self.ref_model_id else {}),
                                                    "text": "Object this step creates, reads or updates"})

    def capability_of_level(self, level):
        """The leaf capability a non-overview level belongs to (its own level, a record type's level, or the
        focus object's top level), or None."""
        if level in self.caps and not self.children.get(level):
            return self.caps[level]
        if level in self.record_type_levels:
            return self.caps.get(self.record_type_levels[level][0]["capability"])
        if level == "top" and self.focus:
            return next((c for c in self.caps.values() if self.focus in c.get("objects", [])), None)
        return None

    def no_records_line(self, apis):
        line = common.no_records_line(self.inv, apis)
        return f"{line} (not shown as resources)" if line else None

    def note_lines(self, level, step):
        lines = []
        if self.overview(level):
            main = self.main_objects(step["item"]) if step.get("item") in self.caps else []
            if main:
                lines.append("Main records (each step behind this box shows the objects it uses): "
                             + ", ".join(self.objects[a]["name"] for a in main))
            if self.unused and step.get("item") in self.caps:
                line = self.no_records_line([a for leaf in self.leaves(step["item"]) for a in self.caps[leaf].get("objects", [])])
                if line:
                    lines.append(line)
            return lines
        if level in self.lifecycle_levels and step.get("value"):
            plan, _ = self.lifecycle_levels[level]
            lines.append(f"{plan['fieldLabel']} value: '{step['value']}' (the {plan['name']} is in this value once the step is done)")
        if level in self.split_levels and step.get("item") in self.record_type_levels:
            plan, rt = self.record_type_levels[step["item"]]
            via = f" (from its process, {rt['process']})" if rt.get("process") else ""
            lines.append(f"Record type: {rt['label']} ({rt['name']}); {plan['fieldLabel']} values it uses{via}: " + ", ".join(v["value"] for v in rt["values"]))
            if rt.get("noRecords"):
                read = (self.objects[plan["object"]].get("usage") or {}).get("readAt")
                lines.append(f"Holds no records: the org has no {plan['name']} records of this record type"
                             f"{' (read ' + read + ')' if read else ''}; it is shown because it is configured.")
        objects = [a for a in step.get("uses", []) if a in self.objects]
        objects += [a for a in self.objects_set_by(step["id"]) if a not in objects]
        hidden = [a for a in objects if a in self.unused]
        objects = [a for a in objects if a not in self.unused]
        cap = self.capability_of_level(level) if self.unused and level not in self.usage_levels else None  # usage note has it
        outline = getattr(self, "outline", None) or {}
        if cap is not None and outline.get("steps") and outline["steps"][0]["id"] == step["id"]:
            # the level's first box names every object of its capability that the basis leaves out
            hidden = cap.get("objects", []) + common.shared_objects(self.inv, cap) + hidden
            self.noted_capabilities.add(cap["id"])
        if hidden:
            line = self.no_records_line(hidden)
            if line:
                lines.append(line)
        if objects:
            lines.append("Objects used:")
            for api in objects:
                obj = self.objects[api]
                desc = common.first_sentence(obj.get("description", ""))
                lines.append(f"- {obj['name']}: {desc}" if desc else f"- {obj['name']}")
        return lines

    def gap_about(self, about):
        if about in self.objects:
            self.ensure_object(about)
            return model_id("obj", about)
        return None

    def usage_note(self, level, outline, ids):
        """Basis usage: the levelNotes entry for a level a lifecycle drives, beside step 1 (the box its first start
        enters). Its text is usage_notes.py's for the kind of level, then the level's objects holding no records."""
        if level in self.split_levels:
            plan = next(p for p in self.plans.values() if p["level"] == level)
            rt = None
        else:
            plan, rt = self.lifecycle_levels[level]
        obj = self.objects[plan["object"]]
        usage = obj.get("usage") or {"available": False, "total": None, "readAt": None,
                                     "reason": "usage was not read for this object"}
        if level in self.split_levels:
            inv_rts = {r["name"]: r for r in (obj.get("lifecycle") or {}).get("recordTypes") or []}
            counts = [(r["label"], usage_notes.record_type_count(usage, inv_rts.get(r["name"], r))) for r in plan["recordTypes"]]
            name, text = plan["name"], usage_notes.split_text(usage, counts)
        elif rt is not None:
            inv_rt = next((r for r in (obj.get("lifecycle") or {}).get("recordTypes") or [] if r["name"] == rt["name"]), rt)
            name = rt["label"]
            text = usage_notes.record_type_text(usage, rt["label"], usage_notes.record_type_count(usage, inv_rt), plan["name"])
        else:
            name, text = plan["name"], usage_notes.object_text(usage)
        # the objects related to the level's object (a direct Lookup or Master-Detail either way) that hold no records;
        # other empty objects stay in the coverage report (excludedByUsage) and the capability's gap
        empty = common.unused_objects(self.inv, usage_notes.related_objects(self.inv, plan["object"]))
        extra = usage_notes.no_records_sentence([self.objects[a]["name"] for a in empty])
        note = usage_notes.level_note(usage_notes.title(name, usage), text, extra)
        parent = self.level_parent.get(level)
        if parent:
            note["parent"] = parent
        first = (outline.get("starts") or [{}])[0].get("to") or outline["steps"][0]["id"]
        if first in ids:
            note["near"] = ids[first]
        self.level_notes.append({k: note[k] for k in ("parent", "near", "title", "text", "purpose") if k in note})

    def check_level(self, level, outline, ids, overview):
        if level in self.usage_levels:
            self.usage_note(level, outline, ids)
        if level in self.lifecycle_levels:
            plan, rt = self.lifecycle_levels[level]
            gapped = {g.get("about") for g in outline.get("gaps", [])}
            errors, warnings = common.process_levels.lifecycle_level_findings(outline, common.lifecycle_cover(plan, rt), gapped,
                                                                              getattr(self, "inherited", ()))
            for line in errors:
                self.error(f"{level}.json", line)
            for line in warnings:
                self.warn(f"{level}.json", line)
        if not overview:
            return
        expected = self.expected_items(level)
        named = [s.get("item") for s in outline["steps"] if s.get("item")]
        for cid in expected:
            if named.count(cid) == 0:
                self.error(f"{level}.json", f"capability '{cid}' ({self.caps[cid]['name']}) has no box on this level")
            elif named.count(cid) > 1:
                self.error(f"{level}.json", f"capability '{cid}' has {named.count(cid)} boxes; give it exactly one")
        for step in outline["steps"]:
            cid = step.get("item")
            if cid in self.caps and cid not in expected:
                self.error(f"{level}.json step '{step['id']}'", f"capability '{cid}' belongs on the level of '{self.caps[cid].get('parent') or 'top'}', not here")

    def ensure_object(self, api):
        if api in self.objects and api not in self.used_objects:
            self.used_objects.append(api)

    # ------------------------------------------------------------ model

    def entities(self):
        owned = [a for c in self.inv.get("capabilities", []) for a in c.get("objects", [])]
        included = common.dedupe(self.used_objects + [a for a in owned if a in self.objects])
        names, rows = {}, []
        counts = defaultdict(int)
        for api in included:
            counts[norm(self.objects[api]["name"])] += 1
        for api in included:
            obj = self.objects[api]
            name = obj["name"] if counts[norm(obj["name"])] == 1 else f"{obj['name']} ({api})"
            entity = {"id": model_id("obj", api), "name": name, "apiName": api}
            if api in {p["object"] for p in self.plans.values()}:  # only a lifecycle a level is built on
                entity["lifecycle"] = {k: v for k, v in obj["lifecycle"].items() if k != "evidence"}
                if entity["lifecycle"].get("recordTypes"):  # record type usage stays in the inventory (ba-model has no place for it)
                    entity["lifecycle"]["recordTypes"] = [{k: v for k, v in rt.items() if k != "usage"} for rt in entity["lifecycle"]["recordTypes"]]
            if obj.get("kind") in ENTITY_KIND:
                entity["kind"] = ENTITY_KIND[obj["kind"]]
            if obj.get("description"):
                entity["description"] = obj["description"][:5000]
            evidence = ([obj["docUrl"]] if obj.get("docUrl") else []) + obj.get("evidence", [])
            if evidence:
                entity["evidence"] = evidence[:20]
            rows.append(entity)
            names[api] = name
        return rows, set(included)

    def relationships(self, included):
        rows, seen = [], set()
        for rel in self.inv.get("relationships", []):
            if rel.get("polymorphic") or rel["from"] not in included or rel["to"] not in included:
                continue
            rid = model_id("rel", rel["from"], rel.get("field") or rel["to"])
            if rid in seen:
                continue
            seen.add(rid)
            row = {"id": rid, "from": model_id("obj", rel["to"]), "to": model_id("obj", rel["from"]),
                   "cardinality": "one-to-many"}
            if rel.get("kind"):
                row["kind"] = rel["kind"]
            if rel.get("field"):
                row["field"] = rel["field"]
            rows.append(row)
        return rows

    def capabilities(self, included):
        rows = []
        for cap in self.inv.get("capabilities", []):
            row = {"id": model_id("cap", cap["id"]), "name": cap["name"]}
            if cap.get("parent"):
                row["parent"] = model_id("cap", cap["parent"])
            realised = self.realised.get(cap["id"], []) + [model_id("obj", a) for a in cap["objects"] if a in included]
            if realised:
                row["realisedBy"] = common.dedupe(realised)
            if cap.get("description"):
                row["description"] = cap["description"]
            if cap["origin"] == "inferred":
                row["inferred"] = True
            evidence = ([cap["docUrl"]] if cap.get("docUrl") else []) + cap.get("evidence", [])
            if evidence:
                row["evidence"] = evidence[:20]
            if cap.get("helpLinks"):
                row["attachments"] = [{"type": "link", "title": l["title"], "url": l["url"]} for l in cap["helpLinks"]]
            rows.append(row)
        return rows

    def usage_gaps(self):
        """Basis usage: one gap per capability naming its objects that hold no records, so none is dropped silently."""
        rows = []
        for cap in self.inv.get("capabilities", []):
            if self.children.get(cap["id"]):
                continue
            line = common.no_records_line(self.inv, cap.get("objects", []) + common.shared_objects(self.inv, cap))
            if line:
                rows.append({"about": model_id("cap", cap["id"]),
                             "note": f"{cap['name']}: {line}. Basis usage leaves them off every box; run on basis configuration to show them."})
        unknown = common.unknown_usage(self.inv)
        if unknown:
            rows.append({"note": "Usage unknown (treated as used): " + ", ".join(self.objects[a]["name"] for a in unknown)})
        return rows

    def inventory_gaps(self, included):
        rows = []
        cap_ids = set(self.caps)
        for gap in self.inv.get("gaps", []):
            about = gap.get("about")
            entry = {"note": gap["note"]}
            if about in included:
                entry["about"] = model_id("obj", about)
            elif about in cap_ids:
                entry["about"] = model_id("cap", about)
            elif about:
                entry["note"] = f"{about}: {gap['note']}"
            rows.append(entry)
        return rows

    def model(self, title):
        entities, included = self.entities()
        sources = [{"kind": s["kind"], "ref": s["ref"][:500], **({"note": s["note"]} if s.get("note") else {})}
                   for s in self.inv["sources"]]
        variant = f" ({self.inv['variant']})" if self.inv.get("variant") else ""
        how = "its official documentation" if self.inv["route"] == "docs" else "the objects in the Elements Metadata Dictionary"
        model = {
            "schemaVersion": "1.0",
            "meta": {
                "title": title[:80],
                "description": (f"{'Process of the ' + self.objects[self.focus]['name'] + ' object in ' if self.focus in self.objects else 'Business process of '}"
                                f"{self.inv['system']}{variant}, inferred from {how} by the "
                                f"map-process-from-data-model skill on {date.today().isoformat()}. The steps, their order and the "
                                "roles are worked out from what the data model holds and how its objects relate; have someone "
                                "who runs the process confirm them."),
                "author": "map-process-from-data-model",
                "sources": sources,
            },
            "roles": self.roles,
            "activities": self.activities,
            "flows": self.flows,
            "entities": entities,
            "relationships": self.relationships(included),
            "capabilities": self.capabilities(included),
            "levelNotes": self.level_notes,
            "gaps": self.inventory_gaps(included) + self.gaps + self.usage_gaps(),
        }
        return {k: v for k, v in model.items() if v != []}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Build the business-architecture model from the level outlines.")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--levels-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", help="map name; the top outline's title, or 'Business Process (<system>)', when left out")
    parser.add_argument("--scope", type=Path, help="the run's scope.json: its generatorFallback reasons go into the gaps")
    args = parser.parse_args(argv)
    try:
        inv = common.load_json(args.inventory, "inventory")
        problems = common.shape_errors(inv, "inventory.schema.json")
        if problems:
            raise SetupError("the inventory does not match its schema; run inventory.py check first:\n  " + "\n  ".join(problems[:10]))
        stop = common.usage_stop(inv)
        if stop:
            raise SetupError(stop)
        builder = Builder(inv, args.levels_dir)
        builder.walk("top")
        if args.scope:
            scope = common.load_json(args.scope, "scope")
            for level, reason in common.fallback_levels(scope, inv, args.levels_dir):
                builder.gaps.append({"note": f"Level {level} was written from the data model by a process-level-writer, "
                                             f"not generated by Elements' org-to-process: {reason}. It has one box per "
                                             "status value rather than the steps of the org's automation."})
        top = builder.levels_dir / "top.json"
        title = args.title or (common.load_json(top, "outline").get("title") if top.exists() else None) or f"Business Process ({inv['system']})"
        model = builder.model(title)
        shape = builder.check_model_shape(model)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    for line in shape:
        builder.errors.append(f"ERROR model shape {line}")
    if not shape:
        common.write_json(args.out, model)
    for line in builder.errors + builder.warnings:
        print(line)
    levels = len({a.get("parent") for a in builder.activities})
    verdict = "FAIL" if builder.errors else "PASS"
    written = f" Written to {args.out}." if not shape else " Not written: the model's shape is invalid."
    print(f"{verdict}: {len(builder.errors)} error(s), {len(builder.warnings)} warning(s). "
          f"{len(builder.activities)} step(s) on {levels} level(s), {len(builder.flows)} line(s), "
          f"{len(builder.roles)} role(s), {len(model.get('entities', []))} object(s).{written}")
    return 1 if builder.errors else 0


if __name__ == "__main__":
    sys.exit(main())
