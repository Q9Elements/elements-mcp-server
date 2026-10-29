#!/usr/bin/env python3
"""Check a built model covers its data model, and optionally compare it with a golden model.

Usage:
  check_coverage.py model.json [--inventory inventory.json] [--golden examples/manufacturing-cloud.json] [--json report.json]

Checks (scripts/validate.py has already checked the model's shape and rules):
  C01 error  every capability has a box, and every capability that owns objects has a child level
  C02 error  every object a capability owns is used by a step on its child level, or a gap says why not
  C03 warn   a step uses an object owned by another capability that its capability does not list as shared
  C04 error  a child level starts and ends with the labels of the lines into and out of its box
  C05 error  two lines on one level carry the same outcome (one step's parallel lines aside)
  C06 warn   a step on a child level uses no object
  C07 error  a step has no human role
  C08 warn   an outcome label is longer than 100 characters, or than 40 on a line into or out of a
             box with a child level, or a start or end (limits from data/style-process.csv)
  C09 warn   an outcome label does not read as a completed, checkable state
  C10 warn   box text is longer than 8 words
  C11 warn   a box that stands for a capability (not an area) has no help or documentation link (route docs)
  C12 warn   more than 15 roles, and over a third of them on one box only: reuse a smaller set
  C13 error  a role has the name of an object in the model ("Supplier" the person and Supplier the
             record): the drawing shows both as resources, and the space library holds one name
             under one type only, so name the person ("Supplier contact")
  C14 error  an object a capability owns, with a lifecycle (a status or stage picklist), has a value no line sets, or a
             line sets a value from a step that does not show the object; warn when the line's
             label does not name the value it sets
  C15 warn   a box shows no object (every box on every level shows the records it works on)
  C16 warn   two role names are near duplicates ("Sales development representative" and "Business
             development representative"): writers working in parallel named one role twice; names
             each role's levels so their writers can be given the one name to use

Basis usage (the inventory's basis): an object that holds no records is left off every box on purpose. C02
reports it as INFO (excluded by usage), not as an error, and C06 and C15 report a box as INFO when it shows no
object because its objects hold none (its note names them). coverage.json lists them under excludedByUsage.

Without --inventory, C03 and C11 are skipped (they need the inventory's shared
objects and route); use that to check a hand-made model such as the golden one.

With --golden, also reports how well the model matches a hand-made reference
model: which reference capability each generated one matches (by the objects
they own), and how many of the reference's objects the generated steps use.

Exit 0: no errors. 1: errors. 2: setup problem.
Standard library only; Python 3.8 or later.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import common
from common import END, START, SetupError, norm

# C09: words that make a label read as a completed, checkable state (past participles, "is", "approved", ...)
STATE_WORDS = re.compile(
    r"\b(\w{3,}ed|\w{3,}en|set|sent|built|made|paid|held|met|done|kept|won|lost|known|shown|run|"
    r"sold|bought|found|brought|told|put|read|left|spent|begun|"
    r"is|are|was|were|has|have|exists?|ready|complete|available|active|approved|open|closed|due|"
    r"differs|exceeds|matches|in stock|in place|on record|up to date|agreed|accepted|rejected)\b", re.IGNORECASE)

# C16: role names at least this alike (difflib ratio, case and spacing ignored) are one role named twice:
# "Sales development representative" / "Business development representative" 0.90, "Renewals manager" / "Renewal
# manager" 0.97. Distinct roles that share words stay below it: "Account executive" / "Account manager" 0.56,
# "Service agent" / "Service manager" 0.79, "Customer representative" / "Customer service representative" 0.87.
ROLE_SIMILARITY = 0.88


class Report:
    def __init__(self):
        self.lines = []
        self.errors = self.warnings = 0

    def add(self, code, severity, where, message):
        tag = {"error": "ERROR", "info": "INFO"}.get(severity, "WARN")
        self.lines.append(f"{tag} {code} {where}: {message}")
        if severity == "error":
            self.errors += 1
        elif severity != "info":
            self.warnings += 1


def norm_name(text):
    return "".join(text.lower().split())


def descendants(acts_by_parent, root):
    out, stack = [], [root]
    while stack:
        current = stack.pop()
        for act in acts_by_parent.get(current, []):
            out.append(act)
            stack.append(act["id"])
    return out


def level_of(flow, acts):
    for end in (flow["from"], flow["to"]):
        if end not in (START, END) and end in acts:
            return acts[end].get("parent")
    return None


def check(model, inv, report):
    acts = {a["id"]: a for a in model.get("activities", [])}
    by_parent = defaultdict(list)
    for act in model.get("activities", []):
        by_parent[act.get("parent")].append(act)
    roles = {r["id"]: r for r in model.get("roles", [])}
    entities = {e["id"]: e for e in model.get("entities", [])}
    api_of = {e["id"]: e.get("apiName", e["name"]) for e in entities.values()}
    gaps_about = {g.get("about") for g in model.get("gaps", []) if g.get("about")}
    caps = {c["id"]: c for c in model.get("capabilities", [])}
    child_caps = defaultdict(list)
    for cap in caps.values():
        if cap.get("parent"):
            child_caps[cap["parent"]].append(cap["id"])
    inv_caps = {common.model_id("cap", c["id"]): c for c in inv.get("capabilities", [])}
    obj_owner = {common.model_id("obj", a): common.model_id("cap", c["id"]) for c in inv.get("capabilities", []) for a in c["objects"]}
    excluded = {common.model_id("obj", a) for a in common.unused_objects(inv)} if inv else set()

    cap_box = {}
    for cid, cap in caps.items():
        boxes = [r for r in cap.get("realisedBy", []) if r in acts]
        owned = [r for r in cap.get("realisedBy", []) if r in entities]
        name = cap["name"]
        if not boxes:
            report.add("C01", "error", name, "has no box on the map")
            continue
        box = boxes[0]
        cap_box[cid] = box
        if inv.get("focus") and all(acts[b].get("parent") is None for b in boxes):
            # one object's process: the top level holds the capability's own steps
            steps = [acts[b] for b in boxes] + [d for b in boxes for d in descendants(by_parent, b)]
        else:
            steps = descendants(by_parent, box)
        if child_caps.get(cid):
            continue
        if owned and not steps:
            report.add("C01", "error", name, f"owns {len(owned)} object(s) but its box '{acts[box]['name']}' has no child level")
            continue
        used = {u for s in steps for u in s.get("uses", [])}
        for ent in owned:
            if ent in excluded and ent not in used:
                report.add("C02", "info", name, f"object '{entities[ent]['name']}' ({api_of[ent]}) holds no records: excluded by basis usage, not drawn")
            elif ent not in used and ent not in gaps_about:
                report.add("C02", "error", name, f"object '{entities[ent]['name']}' ({api_of[ent]}) is used by no step on the child level; use it or record a gap about it")
        shared = {common.model_id("obj", a) for a in common.shared_objects(inv, inv_caps[cid])} if cid in inv_caps else set()
        for step in steps:
            for ent in step.get("uses", []):
                owner = obj_owner.get(ent)
                if owner and owner != cid and ent not in shared:
                    report.add("C03", "warn", f"{name} / {step['name']}", f"uses '{entities[ent]['name']}', which '{caps[owner]['name']}' owns; list it as shared or move the step")
            if not step.get("uses") and no_records_noted(step):
                report.add("C06", "info", f"{name} / {step['name']}", "uses no object: its objects hold no records (basis usage)")
            elif not step.get("uses"):
                report.add("C06", "warn", f"{name} / {step['name']}", "uses no object; check the step is needed, or mark it inferred")

    flows_into = defaultdict(list)
    flows_out = defaultdict(list)
    for flow in model.get("flows", []):
        if flow["to"] in acts:
            flows_into[flow["to"]].append(flow)
        if flow["from"] in acts:
            flows_out[flow["from"]].append(flow)
    for act in model.get("activities", []):
        kids = by_parent.get(act["id"])
        if not kids:
            continue
        kid_ids = {k["id"] for k in kids}
        child_starts = {norm(f.get("label", "")) for f in model.get("flows", []) if f["from"] == START and f["to"] in kid_ids}
        child_ends = {norm(f.get("label", "")) for f in model.get("flows", []) if f["to"] == END and f["from"] in kid_ids}
        for flow in flows_into[act["id"]]:
            if norm(flow.get("label", "")) not in child_starts:
                report.add("C04", "error", act["name"], f"the line in '{flow.get('label', '')}' has no matching start on the child level")
        for flow in flows_out[act["id"]]:
            if norm(flow.get("label", "")) not in child_ends:
                report.add("C04", "error", act["name"], f"the line out '{flow.get('label', '')}' has no matching end on the child level")

    longest, longest_end = common.label_limits()
    has_child = {a["parent"] for a in model.get("activities", []) if a.get("parent")}
    per_level = defaultdict(lambda: defaultdict(list))
    for flow in model.get("flows", []):
        label = flow.get("label", "")
        per_level[level_of(flow, acts)][norm(label)].append(flow)
        where = f"line {flow['from']} -> {flow['to']}"
        boundary = flow["from"] in has_child or flow["to"] in has_child
        on_child = level_of(flow, acts) is not None
        if len(label) > longest:
            report.add("C08", "warn", where, f"label is {len(label)} characters; keep it under {longest} so it fits between boxes")
        elif len(label) > longest_end and (boundary or (not on_child and START in (flow["from"], flow["to"])) or (not on_child and END in (flow["from"], flow["to"]))):
            report.add("C08", "warn", where, f"label is {len(label)} characters; it is drawn on a start or end line (here or on a child level), which has room for {longest_end}")
        if label and not STATE_WORDS.search(label):
            report.add("C09", "warn", where, f"'{label}' does not read as a completed state you could check; say what is now true, naming the record or status that proves it")
    for level, labels in per_level.items():
        for label, flows in labels.items():
            sources = {f["from"] for f in flows}
            parallel = len(sources) == 1 and START not in sources
            same_end = all(f["to"] == END for f in flows)  # alternative paths ending in one state
            if label and len(flows) > 1 and not parallel and not same_end:
                parent = acts[level]["name"] if level in acts else "the top level"
                report.add("C05", "error", parent, f"{len(flows)} lines carry the same outcome '{flows[0]['label']}'; each line on a level needs its own outcome")

    leaf_boxes = {r for cid, cap in caps.items() if not child_caps.get(cid) for r in cap.get("realisedBy", []) if r in acts}
    boxes_per_role = defaultdict(int)
    for act in model.get("activities", []):
        for assignment in act.get("roles", []):
            boxes_per_role[assignment["role"]] += 1
    once = [roles[r]["name"] for r, n in boxes_per_role.items() if n == 1 and r in roles]
    if len(roles) > 15 and len(once) * 3 > len(roles):
        report.add("C12", "warn", "roles", f"{len(roles)} roles, {len(once)} of them on one box only ({', '.join(once[:15])}{' ...' if len(once) > 15 else ''}); a system is run by a smaller set of roles, so reuse names across steps and levels")
    entity_names = {norm_name(e["name"]): e["name"] for e in model.get("entities", [])}
    entity_names.update({norm_name(e["apiName"]): e["name"] for e in model.get("entities", []) if e.get("apiName")})
    for role in roles.values():
        if norm_name(role["name"]) in entity_names:
            report.add("C13", "error", f"role '{role['name']}'", f"has the name of the object '{entity_names[norm_name(role['name'])]}'; name the person or team instead, such as '{role['name']} contact'")
    near_duplicate_roles(model, report)
    lifecycle_checks(model, acts, entities, gaps_about, report)
    for act in model.get("activities", []):
        if not [u for u in act.get("uses", []) if u in entities] and no_records_noted(act):
            report.add("C15", "info", act["name"], "shows no object: its objects hold no records (basis usage), as its note says")
        elif not [u for u in act.get("uses", []) if u in entities]:
            report.add("C15", "warn", act["name"], "shows no object; give the step the records it works on, or mark it inferred")
        humans = [a for a in act.get("roles", []) if roles.get(a["role"], {}).get("kind") == "human"]
        if not humans:
            report.add("C07", "error", act["name"], "has no person or team doing it; add the human role first")
        if len(act["name"].split()) > 8:
            report.add("C10", "warn", act["name"], f"box text has {len(act['name'].split())} words; keep it to a verb and its object")
        if act["id"] in leaf_boxes and inv.get("route") == "docs":
            if not any(att.get("type") == "link" for att in act.get("attachments", [])):
                report.add("C11", "warn", act["name"], "has no link to the vendor's help or documentation for this capability")
    return cap_box


def level_file(act):
    """The level file a box is on: levels/top.json, or levels/<level>.json for a child level, whose box ids are
    '<level>.<step id>' (level and step ids hold no dot, so the first part of the id is the level)."""
    return f"levels/{act['id'].split('.', 1)[0] if act.get('parent') else 'top'}.json"


def near_duplicate_roles(model, report):
    """C16: pairs of role names so alike that they are one role named twice, with the boxes and levels using each."""
    boxes, levels = defaultdict(int), defaultdict(list)
    for act in model.get("activities", []):
        for assignment in act.get("roles", []):
            boxes[assignment["role"]] += 1
            if level_file(act) not in levels[assignment["role"]]:
                levels[assignment["role"]].append(level_file(act))

    def used(role):
        count = boxes[role["id"]]
        return f"'{role['name']}' on {count} box{'' if count == 1 else 'es'} ({', '.join(levels[role['id']]) or 'no level'})"

    roles = model.get("roles", [])
    for i, first in enumerate(roles):
        for second in roles[i + 1:]:
            ratio = SequenceMatcher(None, norm(first["name"]), norm(second["name"])).ratio()
            if ratio >= ROLE_SIMILARITY:
                report.add("C16", "warn", f"roles '{first['name']}' and '{second['name']}'",
                           f"names {ratio:.0%} alike: {used(first)}; {used(second)}. If they are one role, "
                           "give the writers of those levels the one name to use")


def no_records_noted(act):
    """Whether a box's note names objects left off it because they hold no records (basis usage)."""
    return any(att.get("type") == "note" and common.NO_RECORDS_NOTE in (att.get("text") or "") for att in act.get("attachments", []))


def lifecycle_checks(model, acts, entities, gaps_about, report):
    """C14: every value of every lifecycle in the model is set by a line, from a step that shows the object."""
    set_by = defaultdict(lambda: defaultdict(list))
    for flow in model.get("flows", []):
        sets = flow.get("sets")
        if not sets or sets["entity"] not in entities:
            continue
        ent = entities[sets["entity"]]
        set_by[ent["id"]][sets["value"]].append(flow)
        step = flow["from"] if flow["from"] in acts else flow["to"]
        where = f"line {flow['from']} -> {flow['to']}"
        if step in acts and ent["id"] not in acts[step].get("uses", []):
            report.add("C14", "error", where, f"sets {ent['name']} to '{sets['value']}' but '{acts[step]['name']}' does not show {ent['name']}; add it to the step's uses")
        names = [sets["value"]] + [v["label"] for v in ent["lifecycle"]["values"] if v["value"] == sets["value"] and v.get("label")]
        parent = acts.get(step, {}).get("parent")
        inherited = {norm(f.get("label", "")) for f in model.get("flows", []) if parent and parent in (f["from"], f["to"])}
        if norm(flow.get("label", "")) not in inherited and not any(norm(n) in norm(flow.get("label", "")) for n in names):
            report.add("C14", "warn", where, f"'{flow.get('label', '')}' does not name the value it sets ('{sets['value']}')")
    owned = {r for cap in model.get("capabilities", []) for r in cap.get("realisedBy", [])}
    for ent in entities.values():
        lc = ent.get("lifecycle")
        # only the workflow of an object a capability owns drives a level; a shared object's is another process's
        if not lc or ent["id"] not in owned or ent["id"] not in {u for a in acts.values() for u in a.get("uses", [])}:
            continue
        expected = [v["value"] for v in lc["values"]]
        if lc.get("recordTypes"):  # split by record type: the values some record type uses
            used = {v for rt in lc["recordTypes"] for v in (rt.get("values") or expected)}
            expected = [v for v in expected if v in used]
        missing = [v for v in expected if v not in set_by[ent["id"]]]
        if missing:
            severity = "warn" if ent["id"] in gaps_about else "error"
            report.add("C14", severity, ent["name"], f"{lc.get('label', lc['field'])} values no line sets: {', '.join(missing)}; "
                       "each value is the outcome of the step that moves the record there")


def compare(model, golden):
    """Match each golden capability to the generated one owning most of the same objects."""
    def owned(m):
        ents = {e["id"]: e.get("apiName", e["name"]) for e in m.get("entities", [])}
        return {c["name"]: {ents[r] for r in c.get("realisedBy", []) if r in ents} for c in m.get("capabilities", [])}

    def used(m):
        ents = {e["id"]: e.get("apiName", e["name"]) for e in m.get("entities", [])}
        return {ents[u] for a in m.get("activities", []) for u in a.get("uses", []) if u in ents}

    gen, ref = owned(model), owned(golden)
    rows = []
    for name, objs in ref.items():
        best, score = None, 0.0
        for gname, gobjs in gen.items():
            union = objs | gobjs
            jaccard = len(objs & gobjs) / len(union) if union else 0.0
            if jaccard > score:
                best, score = gname, jaccard
        rows.append({"reference": name, "generated": best, "overlap": round(score, 2), "referenceObjects": len(objs)})
    ref_used, gen_used = used(golden), used(model)
    levels = lambda m: sorted(len([a for a in m.get("activities", []) if a.get("parent") == p]) for p in {a.get("parent") for a in m.get("activities", [])})
    return {"capabilities": rows,
            "objectRecall": round(len(ref_used & gen_used) / len(ref_used), 2) if ref_used else None,
            "referenceObjectsMissing": sorted(ref_used - gen_used),
            "stepsPerLevel": {"reference": levels(golden), "generated": levels(model)}}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Check a built model covers its data model.")
    parser.add_argument("model", type=Path)
    parser.add_argument("--inventory", type=Path, help="the inventory the model was built from")
    parser.add_argument("--golden", type=Path, help="a reference model to compare with")
    parser.add_argument("--json", type=Path, help="also write the findings and comparison as JSON")
    args = parser.parse_args(argv)
    try:
        model = common.load_json(args.model, "model")
        inv = common.load_json(args.inventory, "inventory") if args.inventory else {}
        golden = common.load_json(args.golden, "golden model") if args.golden else None
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    report = Report()
    check(model, inv, report)
    for line in report.lines:
        print(line)
    result = {"errors": report.errors, "warnings": report.warnings, "findings": report.lines}
    if inv and common.inventory_basis(inv) == "usage":
        result["basis"] = "usage"
        unused = common.unused_objects(inv)
        if unused:
            result["excludedByUsage"] = unused
            print(f"INFO basis usage: {common.NO_RECORDS_NOTE.lower()}, left off every box: {', '.join(unused)}")
    if golden is not None:
        comparison = compare(model, golden)
        result["comparison"] = comparison
        print("COMPARE reference capability -> best generated match (object overlap)")
        for row in comparison["capabilities"]:
            print(f"COMPARE   {row['reference']} -> {row['generated'] or 'none'} ({row['overlap']:.0%} of {row['referenceObjects']} object(s))")
        if comparison["objectRecall"] is not None:
            print(f"COMPARE objects the reference uses that the model also uses: {comparison['objectRecall']:.0%}")
        print(f"COMPARE steps per level: reference {comparison['stepsPerLevel']['reference']}, generated {comparison['stepsPerLevel']['generated']}")
    if args.json:
        common.write_json(args.json, result)
    print(f"{'FAIL' if report.errors else 'PASS'}: {report.errors} error(s), {report.warnings} warning(s).")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
