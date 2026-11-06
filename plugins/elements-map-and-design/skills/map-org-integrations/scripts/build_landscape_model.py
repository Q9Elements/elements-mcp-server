#!/usr/bin/env python3
"""Join the integration-tracer files into the integration list, apply the architect's corrections, and build the
model the landscape is drawn from.

Usage:
  python3 build_landscape_model.py check-found ENG FILE   # one tracer file against its pack
  python3 build_landscape_model.py merge ENG              # every tracer file into integrations.json
  python3 build_landscape_model.py show ENG               # the integration list for the architect
  python3 build_landscape_model.py correct ENG            # apply integrations/corrections.json
  python3 build_landscape_model.py model ENG              # write drawing/model.json

check-found  Checks a tracer file (trace/found/<system id>.json) against schemas/found.schema.json and its pack
             (trace/packs/<system id>.json): every end is 'org', a system or a new system the file names; 'via' is
             a middleware; every automation is in the pack and every object is one the pack's automations touch; a
             pattern is a pattern_id of the plugin's data/integration-patterns.csv; no exchange is written twice.
             Ends FOUND OK; ERROR lines go back to the agent (exit 1).
merge        Checks every pack has a tracer file that passes, then joins them: systems named only behind a
             middleware are added to systems.json (status confirmed, origin indirect) when they are not there yet;
             the same exchange written by two tracers (same from, to and via) becomes one integration with the
             automations, objects and evidence of both, labelled by the tracer that listed more of its automations
             (on a tie, the tracer of one of its ends). Writes integrations/merged.json and, with the corrections
             of integrations/corrections.json applied, integrations.json. Ends NEW SYSTEMS (new systems to trace,
             while trace.round is below trace_rounds) or MERGED; no integration at all is an ERROR (exit 1).
show         Prints the integration list (from, to, via, what moves, how, automations, objects), where each
             middleware is drawn and why, the calls to rule on (inferred integrations and systems named only behind
             a middleware, with their evidence), the systems with no integration found, and the gaps.
correct      Rebuilds integrations.json from integrations/merged.json and every round of
             integrations/corrections.json ({"rounds": [{"date", "by", "corrections": [op, ...], "applied"}]}), ops:
               {"op": "drop-integration", "integration": ID, "reason": R}
               {"op": "edit-integration", "integration": ID, "set": {field: value, ...}}
               {"op": "add-integration", "from": S, "to": S, "via": S, "whatMoves": TEXT, "direction": D, ...}
               {"op": "drop-system", "system": S, "reason": R}   {"op": "rename-system", "system": S, "to": NAME}
               {"op": "merge-systems", "into": S, "systems": [S, ...]}
               {"op": "placement", "system": S, "placement": "card" | "label"}
             S is a system id or name ('org' for the Salesforce org). Ends CORRECTED; an op that does not apply, or a
             result with no integration left, is an ERROR line (exit 1) and nothing is written.
model        Writes drawing/model.json in the plugin's shared model: the org as the hub, every system with its
             evidence as metadata links (a system named only behind a middleware: the automations that carry its
             exchanges) and a short footer, every middleware's placement, the integrations with via, automations and objects, the
             automations and objects with their metadata links, and what each automation reads, writes or runs on.
             Validate it with the plugin's validate.py --for system-architecture before drawing.

Exit 2: setup problem.
"""

import copy
import csv
import re
import sys
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

import common
from common import SetupError, norm

ORG = "org"          # the Salesforce org's id in tracer files, integrations.json and the model
INDIRECT_LINKS = 5   # automations linked on the card of a system named only behind a middleware
PATTERNS_CSV = common.PLUGIN / "data" / "integration-patterns.csv"
STYLE_CSV = common.PLUGIN / "data" / "style-architecture.csv"
AUTOMATION_TYPES_CSV = common.PLUGIN / "data" / "automation-types.csv"


def refuse(errors):
    for line in errors:
        print(f"ERROR {line}")
    print("REFUSED")
    return 1


def pattern_ids():
    with open(PATTERNS_CSV, newline="", encoding="utf-8") as handle:
        return {row["pattern_id"] for row in csv.DictReader(handle)}


def style_value(setting):
    with open(STYLE_CSV, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["setting"] == setting:
                return int(row["value"])
    raise SetupError(f"the plugin's data/style-architecture.csv has no {setting} row")


def fold_threshold():
    return style_value("middleware_fold_threshold")


# ---------------------------------------------------------------- check-found

def pack_facts(pack):
    autos = {a["nodeId"]: a for a in pack.get("automations", [])}
    objects = {o["apiName"] for a in autos.values() for o in a.get("objects", [])}
    return autos, objects


def check_found(eng, path):
    eng, path = Path(eng), Path(path)
    found = common.load_json(path, "the tracer file")
    errors = common.shape_errors(found, "found.schema.json")
    if errors:
        return errors
    pack_path = eng / "trace" / "packs" / f"{found['system']}.json"
    if not pack_path.exists():
        return [f"system '{found['system']}' has no pack (trace/packs/{found['system']}.json); use the pack's system id"]
    if path.stem != found["system"]:
        errors.append(f"the file is {path.name} but names system '{found['system']}'; write it as trace/found/{found['system']}.json")
    pack = common.load_json(pack_path)
    autos, objects = pack_facts(pack)
    # The tracer knows the systems its pack lists; a system a merge added later is still new to it.
    systems = [pack["system"]] + pack.get("otherSystems", [])
    ids = {s["id"]: s for s in systems}
    new = {norm(n["name"]): n for n in found["newSystems"]}
    for name, n in new.items():
        if any(norm(s["name"]) == name for s in systems):
            errors.append(f"newSystems: '{n['name']}' is already a system ({next(s['id'] for s in systems if norm(s['name']) == name)}); use its id")
    middleware = {i for i, s in ids.items() if s.get("middleware")} | {k for k, n in new.items() if n.get("middleware") or n["kind"] == "middleware"}
    patterns = pattern_ids()
    me = found["system"]
    seen = set()
    for index, item in enumerate(found["integrations"]):
        where = f"integrations[{index}]"
        ends = []
        for end in ("from", "to"):
            value = item[end]
            if value != ORG and value not in ids and norm(value) not in new:
                errors.append(f"{where}.{end}: '{value}' is not 'org', a system id of the pack's otherSystems, or a name in newSystems")
            ends.append(value if value in ids or value == ORG else norm(value))
        if ends[0] == ends[1]:
            errors.append(f"{where}: from and to are the same system")
        via = item.get("via")
        if via is not None:
            key = via if via in ids else norm(via)
            if key not in middleware:
                errors.append(f"{where}.via: '{via}' is not a middleware system")
            if key in ends:
                errors.append(f"{where}.via: '{via}' is also an end of the exchange")
        if me not in ends and via != me:
            errors.append(f"{where}: neither end nor 'via' is this pack's system '{me}'; write only the exchanges this system takes part in")
        for node_id in item["automations"]:
            if node_id not in autos:
                errors.append(f"{where}.automations: {node_id} is not an automation in the pack")
        for api in item["objects"]:
            if api not in objects:
                errors.append(f"{where}.objects: '{api}' is not an object the pack's automations read, write or run on")
        if item.get("pattern") and item["pattern"] not in patterns:
            errors.append(f"{where}.pattern: '{item['pattern']}' is not one of {', '.join(sorted(patterns))}")
        key = (ends[0], ends[1], via)
        if key in seen:
            errors.append(f"{where}: the exchange {item['from']} -> {item['to']}{' via ' + via if via else ''} is written twice; merge them")
        seen.add(key)
    for n in found["newSystems"]:
        if n.get("via") and n["via"] not in middleware:
            errors.append(f"newSystems '{n['name']}': via '{n['via']}' is not a middleware system")
    return errors


def cmd_check_found(eng, path):
    errors = check_found(eng, path)
    if errors:
        return refuse(errors)
    print("FOUND OK")
    return 0


# ---------------------------------------------------------------- merge

def known_vendor(name):
    for v in common.load_known_systems():
        if norm(name) in [norm(v["vendor"])] + [norm(a) for a in v["aliases"]]:
            return v
    return None


def merge(eng):
    eng = Path(eng)
    state = common.load_state(eng)
    limits = common.load_limits()
    n = state.get("trace", {}).get("round") or 1
    packs = sorted((eng / "trace" / "packs").glob("*.json"))
    if not packs:
        return refuse(["no evidence packs in trace/packs; run trace_plan.py pack first"])
    errors = []
    found_docs = []
    for pack_path in packs:
        path = eng / "trace" / "found" / pack_path.name
        if not path.exists():
            errors.append(f"trace/found/{pack_path.name} is missing: run the integration-tracer for {pack_path.stem}")
            continue
        problems = check_found(eng, path)
        if problems:
            errors.append(f"trace/found/{pack_path.name} does not pass check-found ({len(problems)} problem(s)); run check-found and send them back")
            continue
        found_docs.append((common.load_json(pack_path), common.load_json(path)))
    if errors:
        return refuse(errors)
    systems_doc = common.load_json(eng / "systems.json")
    systems = systems_doc["systems"]
    by_name = {norm(s["name"]): s for s in systems}
    added = []
    for pack, found in found_docs:
        for ns in found["newSystems"]:
            vendor = known_vendor(ns["name"])
            name = vendor["vendor"] if vendor else ns["name"]
            if norm(name) in by_name:
                continue
            entry = {"id": common.system_id(name), "name": name,
                     "kind": "middleware" if (ns.get("middleware") or (vendor and vendor["middleware"])) else (vendor["kind"] if vendor else ns["kind"]),
                     "middleware": bool(ns.get("middleware") or (vendor and vendor["middleware"])), "how": "indirect",
                     "reasons": [f"named by the trace of {pack['system']['name']}"], "description": "",
                     "searchTerms": list(vendor["searchTerms"]) if vendor and vendor["searchTerms"] else list(ns["searchTerms"]),
                     "icon": vendor["icon"] if vendor else "", "evidence": [], "status": "confirmed", "origin": "indirect",
                     "via": ns.get("via") or pack["system"]["id"], "tracedRound": None, "namedBy": list(ns["evidence"])}
            systems.append(entry)
            by_name[norm(name)] = entry
            added.append(entry)
    common.write_json(eng / "systems.json", systems_doc)

    def resolve(value):
        if value == ORG or value is None:
            return value
        if any(s["id"] == value for s in systems):
            return value
        vendor = known_vendor(value)
        return by_name[norm(vendor["vendor"] if vendor else value)]["id"]

    automations, objects, touches = OrderedDict(), OrderedDict(), {}
    merged, label_rank = OrderedDict(), {}
    gaps = []
    for pack, found in found_docs:
        for a in pack["automations"]:
            automations.setdefault(a["nodeId"], {k: a.get(k) for k in ("nodeId", "name", "apiName", "sfType", "type", "active",
                                                                      "description", "summary") if a.get(k) not in (None, "")})
            for o in a.get("objects", []):
                objects.setdefault(o["apiName"], {"apiName": o["apiName"], "name": o.get("name") or o["apiName"], "kind": o.get("kind", "standard")})
                t = touches.setdefault((a["nodeId"], o["apiName"]), set())
                if o.get("read"):
                    t.add("reads")
                if o.get("write"):
                    t.add("writes")
                if o.get("trigger"):
                    t.add("triggers")
        gaps += [{"about": pack["system"]["id"], "note": g["note"]} for g in pack.get("gaps", [])]
        gaps += [{"about": pack["system"]["id"], "note": g["note"]} for g in found["gaps"]]
        for item in found["integrations"]:
            a, b, via = resolve(item["from"]), resolve(item["to"]), resolve(item.get("via"))
            key = (a, b, via)
            entry = merged.get(key)
            if entry is None:
                entry = {"from": a, "to": b, "whatMoves": item["whatMoves"], "direction": item["direction"],
                         "automations": [], "objects": [], "evidence": [], "inferred": item["inferred"], "by": []}
                if via:
                    entry["via"] = via
                for k in ("timing", "technology", "pattern"):
                    if item.get(k):
                        entry[k] = item[k]
                merged[key] = entry
                label_rank[key] = (len(item["automations"]), found["system"] in (a, b))
            else:
                # Two tracers wrote the same exchange: the label covering more automations goes on the line,
                # on a tie the one from the tracer of an end rather than of the middleware; the other is kept.
                rank = (len(item["automations"]), found["system"] in (a, b))
                if norm(item["whatMoves"]) != norm(entry["whatMoves"]):
                    if rank > label_rank[key]:
                        entry.setdefault("otherLabels", []).append(entry["whatMoves"])
                        entry["whatMoves"] = item["whatMoves"]
                        label_rank[key] = rank
                    else:
                        entry.setdefault("otherLabels", []).append(item["whatMoves"])
                entry["inferred"] = entry["inferred"] and item["inferred"]
                if item["direction"] == "two-way":
                    entry["direction"] = "two-way"
                for k in ("timing", "technology", "pattern"):
                    if item.get(k) and not entry.get(k):
                        entry[k] = item[k]
            entry["automations"] = list(dict.fromkeys(entry["automations"] + item["automations"]))
            entry["objects"] = list(dict.fromkeys(entry["objects"] + item["objects"]))
            entry["evidence"] = list(dict.fromkeys(entry["evidence"] + item["evidence"]))
            entry["by"] = list(dict.fromkeys(entry["by"] + [found["system"]]))
    integrations = list(merged.values())
    for i, item in enumerate(integrations, start=1):
        item["id"] = f"i{i}"
    interactions = []
    for item in integrations:
        for node_id in item["automations"]:
            for api in item["objects"]:
                for kind in sorted(touches.get((node_id, api), ())):
                    pair = {"automation": node_id, "object": api, "kind": kind}
                    if pair not in interactions:
                        interactions.append(pair)
    last_round = n >= limits["trace_rounds"]
    untraced = [s for s in systems if s.get("status") == "confirmed" and s.get("tracedRound") is None]
    if last_round:
        for s in untraced:
            gaps.append({"about": s["id"], "note": f"{s['name']} is named behind {s.get('via') or 'a middleware'} but was not searched itself: the search passes are bounded at {limits['trace_rounds']}"})
    doc = {"hub": {"id": ORG, "name": (state.get("slots") or {}).get("hub_name") or "Salesforce org"},
           "systems": [dict({k: s.get(k) for k in ("id", "name", "kind", "middleware", "origin", "via", "how", "description", "icon")},
                            evidence=s.get("evidence", []), namedBy=s.get("namedBy", []), traced=s.get("tracedRound") is not None)
                       for s in systems if s.get("status") == "confirmed"],
           "integrations": integrations, "automations": list(automations.values()), "objects": list(objects.values()),
           "interactions": interactions, "gaps": gaps, "dropped": [], "placement": {}}
    common.write_json(eng / "integrations" / "merged.json", doc)
    result = apply_corrections(eng, doc)
    if isinstance(result, list):
        return refuse(result)
    print(f"{len(integrations)} integration(s) between {len(doc['systems'])} system(s) and the org")
    if untraced and not last_round:
        print(f"NEW SYSTEMS {len(untraced)}: {', '.join(s['name'] for s in untraced)}")
        return 0
    if untraced:
        print(f"UNTRACED {len(untraced)}: {', '.join(s['name'] for s in untraced)} (recorded as gaps)")
    print("MERGED")
    return 0


# ---------------------------------------------------------------- corrections

def find_system(doc, ref):
    if ref == ORG:
        return doc["hub"]
    for s in doc["systems"]:
        if s["id"] == ref or norm(s["name"]) == norm(ref):
            return s
    return None


def apply_ops(doc, rounds):
    errors = []
    allowed = {"from", "to", "via", "whatMoves", "direction", "timing", "technology", "pattern"}
    for r_index, round_ in enumerate(rounds, start=1):
        by = round_.get("by") or "the architect"
        for c_index, op in enumerate(round_.get("corrections", []), start=1):
            where = f"round {r_index} correction {c_index}"
            kind = op.get("op")
            ints = {i["id"]: i for i in doc["integrations"]}
            if kind == "drop-integration":
                item = ints.get(op.get("integration"))
                if not item:
                    errors.append(f"{where}: no integration '{op.get('integration')}'")
                    continue
                doc["integrations"].remove(item)
                doc["dropped"].append({"integration": item["id"], "reason": op.get("reason", ""), "by": by})
            elif kind in ("edit-integration", "add-integration"):
                fields = op.get("set", {}) if kind == "edit-integration" else {k: v for k, v in op.items() if k != "op"}
                unknown = set(fields) - allowed
                if unknown:
                    errors.append(f"{where}: cannot set {', '.join(sorted(unknown))}; use {', '.join(sorted(allowed))}")
                    continue
                for end in ("from", "to", "via"):
                    if fields.get(end):
                        s = find_system(doc, fields[end])
                        if not s:
                            errors.append(f"{where}: no system '{fields[end]}'")
                            break
                        fields[end] = s["id"]
                else:
                    if kind == "edit-integration":
                        item = ints.get(op.get("integration"))
                        if not item:
                            errors.append(f"{where}: no integration '{op.get('integration')}'")
                            continue
                        item.update(fields)
                        item["inferred"] = False
                        item["evidence"] = list(item["evidence"]) + [f"Corrected by {by}"]
                    else:
                        if not (fields.get("from") and fields.get("to") and fields.get("whatMoves")):
                            errors.append(f"{where}: add-integration needs from, to and whatMoves")
                            continue
                        number = max([int(i["id"][1:]) for i in doc["integrations"]] + [0]) + 1
                        doc["integrations"].append(dict({"direction": "one-way"}, **fields, id=f"i{number}", automations=[], objects=[],
                                                        evidence=[f"Added by {by}"], inferred=False, by=["architect"]))
            elif kind == "drop-system":
                s = find_system(doc, op.get("system", ""))
                if not s or s is doc["hub"]:
                    errors.append(f"{where}: no system '{op.get('system')}' to drop")
                    continue
                doc["systems"].remove(s)
                doc["dropped"].append({"system": s["name"], "reason": op.get("reason", ""), "by": by})
                doc["gaps"] = [g for g in doc["gaps"] if g.get("about") != s["id"]]
                for item in list(doc["integrations"]):
                    if s["id"] in (item["from"], item["to"]):
                        doc["integrations"].remove(item)
                    elif item.get("via") == s["id"]:
                        item.pop("via")
            elif kind == "rename-system":
                s = find_system(doc, op.get("system", ""))
                if not s or not op.get("to"):
                    errors.append(f"{where}: rename-system needs an existing system and 'to'")
                    continue
                s["name"] = op["to"]
            elif kind == "merge-systems":
                into = find_system(doc, op.get("into", ""))
                if not into or into is doc["hub"]:
                    errors.append(f"{where}: no system '{op.get('into')}' to merge into")
                    continue
                for ref in op.get("systems", []):
                    s = find_system(doc, ref)
                    if not s or s is into or s is doc["hub"]:
                        errors.append(f"{where}: no system '{ref}' to merge")
                        continue
                    into["evidence"] = into.get("evidence", []) + s.get("evidence", [])
                    doc["systems"].remove(s)
                    for item in doc["integrations"]:
                        for end in ("from", "to", "via"):
                            if item.get(end) == s["id"]:
                                item[end] = into["id"]
                    doc["integrations"] = [i for i in doc["integrations"] if i["from"] != i["to"] and i.get("via") not in (i["from"], i["to"])]
            elif kind == "placement":
                s = find_system(doc, op.get("system", ""))
                if not s or not s.get("middleware") or op.get("placement") not in ("card", "label"):
                    errors.append(f"{where}: placement needs a middleware system and 'card' or 'label'")
                    continue
                doc["placement"][s["id"]] = op["placement"]
            else:
                errors.append(f"{where}: unknown op '{kind}'")
    return errors


def apply_corrections(eng, merged):
    path = Path(eng) / "integrations" / "corrections.json"
    rounds = common.load_json(path).get("rounds", []) if path.exists() else []
    doc = common.load_json(Path(eng) / "integrations" / "merged.json") if merged is None else merged
    doc = copy.deepcopy(doc)
    errors = apply_ops(doc, rounds)
    if errors:
        return errors
    if not doc["integrations"]:
        if rounds:
            return ["no integration is left after the architect's corrections: a landscape needs at least one. Show this to "
                    "the architect: they can put one back or add one, or end the run here"]
        return ["the tracers left every system without an integration, which their brief forbids: a fault in the playbook"]
    used = {a for i in doc["integrations"] for a in i["automations"]}
    objs = {o for i in doc["integrations"] for o in i["objects"]}
    doc["interactions"] = [x for x in doc["interactions"] if x["automation"] in used and x["object"] in objs]
    doc["correctedOn"] = date.today().isoformat() if rounds else None
    common.write_json(Path(eng) / "integrations.json", doc)
    return doc


def correct(eng):
    result = apply_corrections(eng, None)
    if isinstance(result, list):
        return refuse(result)
    print(f"{len(result['integrations'])} integration(s); {len(result['dropped'])} item(s) dropped")
    print("CORRECTED")
    return 0


# ---------------------------------------------------------------- show

def carried(doc, middleware_id):
    """The systems a middleware carries, counted as the drawing counts them: Salesforce's own products are not."""
    salesforce = {s["id"] for s in doc["systems"] if s.get("kind") == "salesforce"}
    return sorted({end for i in doc["integrations"] if i.get("via") == middleware_id
                   for end in (i["from"], i["to"]) if end != ORG and end not in salesforce})


def placements(doc):
    """Where each middleware is drawn, {id: (card | label, why)}: the architect's placement; else a label when it carries
    more systems than middleware_fold_threshold; else its own card. Then, while level 1 would have more cards than
    max_cards_per_level, a label on the card-placed middleware the architect did not place that carries the most
    systems (ties by name). Level 1 counts as the drawing counts it: the hub and every system with an integration,
    less a label middleware that is not an end of any integration."""
    threshold, limit = fold_threshold(), style_value("max_cards_per_level")
    chosen = doc.get("placement", {})
    mids = sorted((s for s in doc["systems"] if s.get("middleware")), key=lambda s: s["name"])
    out = {}
    for s in mids:
        out[s["id"]] = placement_of(doc, s, threshold)
    ends = {e for i in doc["integrations"] for e in (i["from"], i["to"])}
    shown = {e for i in doc["integrations"] for e in (i["from"], i["to"], i.get("via")) if e and e != ORG}

    def level_one():
        return 1 + len([x for x in shown if not (out.get(x, ("card",))[0] == "label" and x not in ends)])
    while level_one() > limit:
        free = [s for s in mids if out[s["id"]][0] == "card" and s["id"] not in chosen]
        if not free:
            break
        pick = sorted(free, key=lambda s: (-len(carried(doc, s["id"])), s["name"]))[0]
        out[pick["id"]] = ("label", f"level 1 would have {level_one()} cards, more than {limit}: the {len(carried(doc, pick['id']))} "
                                    f"systems behind it join the org directly, labelled 'via {pick['name']}'")
    return out


def placement_of(doc, s, threshold):
    count = len(carried(doc, s["id"]))
    if s["id"] in doc.get("placement", {}):
        return doc["placement"][s["id"]], f"set by the architect ({count} system(s) behind it)"
    if count > threshold:
        return "label", f"{count} systems behind it, more than {threshold}: they join the org directly, labelled 'via {s['name']}'"
    return "card", f"{count} system(s) behind it, {threshold} or fewer: its own card, with them joined to it"


def show(eng):
    doc = common.load_json(Path(eng) / "integrations.json", "integrations.json")
    names = {s["id"]: s["name"] for s in doc["systems"]}
    names[ORG] = doc["hub"]["name"]
    autos = {a["nodeId"]: a for a in doc["automations"]}
    objs = {o["apiName"]: o for o in doc["objects"]}
    print("| # | From | To | Via | What moves | How | Automations | Objects |")
    print("|---|---|---|---|---|---|---|---|")
    for i in doc["integrations"]:
        how = " · ".join(x for x in (i.get("technology"), (i.get("timing") or "").replace("-", " "),
                                     "both ways" if i["direction"] == "two-way" else "", "inferred" if i.get("inferred") else "") if x)
        a_names = [autos[a]["name"] for a in i["automations"] if a in autos]
        shown = ", ".join(a_names[:4]) + (f" and {len(a_names) - 4} more" if len(a_names) > 4 else "")
        o_names = [objs[o]["name"] for o in i["objects"] if o in objs]
        print(f"| {i['id']} | {names.get(i['from'], i['from'])} | {names.get(i['to'], i['to'])} | {names.get(i.get('via'), '')} | "
              f"{i['whatMoves']} | {how} | {shown or 'none found'} | {', '.join(o_names) or 'none found'} |")
    resolved = placements(doc)
    middleware = [s for s in doc["systems"] if s.get("middleware")]
    if middleware:
        print()
        print("Middleware:")
        for s in middleware:
            where, why = resolved[s["id"]]
            print(f"- {s['name']}: drawn as {'its own card' if where == 'card' else 'a label on the lines'}; {why}")
    calls = [(f"{i['id']} {names.get(i['from'], i['from'])} to {names.get(i['to'], i['to'])} ({i['whatMoves']})", i.get("evidence", []))
             for i in doc["integrations"] if i.get("inferred")]
    calls += [(f"{s['name']}, named only behind {names.get(s.get('via'), s.get('via') or 'a middleware')}", s.get("namedBy", []))
              for s in doc["systems"] if s.get("origin") == "indirect"]
    if calls:
        print()
        print("Calls to rule on (inferred integrations, and systems named only behind a middleware):")
        for what, evidence in calls:
            print(f"- {what}: {'; '.join(evidence[:3]) or 'no evidence recorded'}")
    touched = {e for i in doc["integrations"] for e in (i["from"], i["to"], i.get("via")) if e}
    lonely = [s["name"] for s in doc["systems"] if s["id"] not in touched]
    if lonely:
        print()
        print(f"No integration found for: {', '.join(lonely)}")
    if doc.get("gaps"):
        print()
        print("Gaps:")
        for g in doc["gaps"]:
            print(f"- {names.get(g.get('about'), g.get('about') or '')}: {g['note']}")
    if doc.get("dropped"):
        print()
        print("Dropped by the architect:")
        for d in doc["dropped"]:
            print(f"- {d.get('system') or d.get('integration')}: {d.get('reason', '')}")
    return 0


# ---------------------------------------------------------------- model

def model_id(prefix, text, used):
    base = prefix + re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-.")[:56] or prefix + "x"
    ident, k = base, 2
    while ident in used:
        ident = f"{base[:58]}-{k}"
        k += 1
    used.add(ident)
    return ident


def automation_labels():
    with open(AUTOMATION_TYPES_CSV, newline="", encoding="utf-8") as handle:
        return {row["type"]: row["label"] for row in csv.DictReader(handle)}


def footer_of(system):
    counts = Counter()
    packages = []
    for e in system.get("evidence", []):
        if e["role"] != "proof":
            continue
        if e["type"] == "Managed Package":
            packages.append(e["name"])
        else:
            counts[e["type"].lower()] += 1
    parts = [f"{n} {t}{'s' if n > 1 else ''}" if n > 1 else t for t, n in counts.items()]
    parts += [f"package {p}" for p in packages]
    if system.get("origin") == "indirect":
        return f"Named behind {system.get('via_name') or 'a middleware'}; found in automation descriptions"
    return ("Found by: " + ", ".join(parts))[:200] if parts else ""


def attachments_of(system, ref_model_id, carried_by=()):
    """A system's metadata links: the inventory items that prove it; for a system named only behind a middleware, which
    has none, the automations that carry its exchanges."""
    out, seen = [], set()
    linkable = {row["metadata_type"] for row in common.load_inventory_types()}   # every inventory type is metadata
    for a in carried_by:
        if a.get("apiName") and (a["apiName"], a.get("sfType")) not in seen:
            seen.add((a["apiName"], a.get("sfType")))
            out.append({"type": "metadata", "apiName": a["apiName"], "metadataType": a.get("sfType") or "Flow", "refModelId": ref_model_id,
                        "text": f"Carries an exchange with {system['name']}"})
    for e in system.get("evidence", []):
        if e["type"] not in linkable or not e.get("apiName"):
            continue
        key = (e["apiName"], e["type"])
        if key in seen:
            continue
        seen.add(key)
        # the API name exactly as the Metadata Dictionary lists it: a packaged remote site, credential or permission set
        # resolves by its name without the namespace prefix, a packaged application by its prefixed name
        api = e["apiName"]
        text = e.get("url") or e.get("description") or f"{e['type']} that shows {system['name']}"
        out.append({"type": "metadata", "apiName": api, "metadataType": e["type"], "refModelId": ref_model_id, "text": text[:2000]})
    for e in system.get("evidence", []):
        if e["type"] == "Managed Package":
            if not any(x.get("namespace") == e.get("namespace") and x["type"] == "Application" for x in system.get("evidence", [])):
                out.append({"type": "note", "title": f"Managed package {e['name']}"[:120],
                            "text": f"Installed managed package {e['name']} ({e.get('description') or 'namespace ' + e['name']}). A package cannot be linked; its components are linked where the space can resolve them."})
    return out


def build_model(eng):
    eng = Path(eng)
    state = common.load_state(eng)
    slots = state.get("slots") or {}
    doc = common.load_json(eng / "integrations.json", "integrations.json")
    labels = automation_labels()
    used = {ORG}
    sys_ids = {}
    names = set()

    def unique_name(name, suffix):
        if norm(name) in names:
            name = f"{name} ({suffix})"
        k = 2
        base = name
        while norm(name) in names:
            name = f"{base} {k}"
            k += 1
        names.add(norm(name))
        return name

    hub_name = unique_name(doc["hub"]["name"], "org")
    systems = [{"id": ORG, "name": hub_name, "kind": "salesforce", "hub": True, "icon": "Salesforce",
                "footer": f"Reference model {slots.get('ref_model_name') or slots.get('ref_model_id') or ''}".strip()}]
    by_id = {s["id"]: s for s in doc["systems"]}
    touched = {e for i in doc["integrations"] for e in (i["from"], i["to"], i.get("via")) if e}
    threshold, resolved = fold_threshold(), placements(doc)
    for s in doc["systems"]:
        if s["id"] not in touched:
            continue
        ident = model_id("", s["id"], used) if s["id"] != ORG else model_id("s-", s["id"], used)
        sys_ids[s["id"]] = ident
        entry = {"id": ident, "name": unique_name(s["name"], "system"), "kind": "middleware" if s.get("middleware") else s["kind"]}
        if s.get("icon"):
            entry["icon"] = s["icon"]
        via_name = by_id.get(s.get("via"), {}).get("name")
        footer = footer_of(dict(s, via_name=via_name))
        if footer:
            entry["footer"] = footer
        carried_by = []
        if s.get("origin") == "indirect":
            node_ids = [n for i in doc["integrations"] if s["id"] in (i["from"], i["to"]) for n in i["automations"]]
            by_node_id = {a["nodeId"]: a for a in doc["automations"]}
            carried_by = [by_node_id[n] for n in dict.fromkeys(node_ids) if n in by_node_id][:INDIRECT_LINKS]
        attachments = attachments_of(s, slots["ref_model_id"], carried_by)
        if attachments:
            entry["attachments"] = attachments
        if s.get("origin") == "indirect":
            entry["inferred"] = True
            entry["evidence"] = (s.get("namedBy") or [f"Named behind {via_name}"])[:10]
        if s.get("middleware") and s["id"] in resolved:
            entry["placement"] = resolved[s["id"]][0]
        systems.append(entry)
    sys_ids[ORG] = ORG
    autos, auto_ids = [], {}
    by_node = {a["nodeId"]: a for a in doc["automations"]}
    for i in doc["integrations"]:
        for node_id in i["automations"]:
            if node_id in auto_ids or node_id not in by_node:
                continue
            a = by_node[node_id]
            ident = model_id("a-", a.get("apiName") or a["name"], used)
            auto_ids[node_id] = ident
            entry = {"id": ident, "name": unique_name(a["name"], labels.get(a.get("type"), "automation")), "type": a.get("type") or "other"}
            if a.get("apiName"):
                entry["apiName"] = a["apiName"]
                entry["attachments"] = [{"type": "metadata", "apiName": a["apiName"], "metadataType": a.get("sfType") or "Flow", "refModelId": slots["ref_model_id"],
                                         "text": f"The {labels.get(a.get('type'), 'automation').lower()} that carries this exchange"}]
            text = a.get("summary") or a.get("description")
            if text:
                entry["summary"] = text[:250]
            entry["attributes"] = [{"title": labels.get(a.get("type"), "Automation") + ("" if a.get("active") is not False else " (inactive)")}]
            autos.append(entry)
    entities, entity_ids = [], {}
    by_api = {o["apiName"]: o for o in doc["objects"]}
    for i in doc["integrations"]:
        for api in i["objects"]:
            if api in entity_ids or api not in by_api:
                continue
            o = by_api[api]
            ident = model_id("o-", api, used)
            entity_ids[api] = ident
            entities.append({"id": ident, "name": unique_name(o.get("name") or api, "object"), "apiName": api, "kind": o.get("kind", "standard"),
                             "attachments": [{"type": "metadata", "apiName": api, "refModelId": slots["ref_model_id"],
                                              "metadataType": {"custom": "Custom Object", "external": "External Object"}.get(o.get("kind"), "Standard Object"),
                                              "text": "An object the exchange reads or writes"}]})
    integrations = []
    for i in doc["integrations"]:
        if i["from"] not in sys_ids or i["to"] not in sys_ids:
            continue
        entry = {"id": i["id"], "from": sys_ids[i["from"]], "to": sys_ids[i["to"]], "label": i["whatMoves"][:200],
                 "direction": i["direction"], "inferred": bool(i.get("inferred")), "evidence": [e[:1000] for e in i["evidence"][:20]]}
        if i.get("via") in sys_ids:
            entry["via"] = sys_ids[i["via"]]
        for k in ("timing", "technology", "pattern"):
            if i.get(k):
                entry[k] = i[k]
        entry["automations"] = [auto_ids[a] for a in i["automations"] if a in auto_ids]
        entry["objects"] = [entity_ids[o] for o in i["objects"] if o in entity_ids]
        integrations.append(entry)
    interactions = []
    for x in doc.get("interactions", []):
        a, o = auto_ids.get(x["automation"]), entity_ids.get(x["object"])
        if not a or not o:
            continue
        if x["kind"] == "triggers":
            interactions.append({"from": o, "to": a, "kind": "triggers"})
        else:
            interactions.append({"from": a, "to": o, "kind": x["kind"]})
    title = slots.get("map_name") or f"{hub_name} integration landscape"
    model = {"schemaVersion": "1.0",
             "meta": {"title": title[:80],
                      "description": (f"The outside systems {hub_name} exchanges data with and how, found from its metadata in Elements "
                                      f"(reference model {slots.get('ref_model_name') or slots.get('ref_model_id')}) on {date.today().isoformat()}. "
                                      f"{len(systems) - 1} systems, {len(integrations)} integrations. Each system's drill-down shows the "
                                      f"middleware, automations and objects that carry its exchanges; every card links to the metadata behind it."),
                      "author": "map-org-integrations",
                      "sources": [{"kind": "metadata", "ref": slots.get("ref_model_id") or "unknown", "note": slots.get("ref_model_name") or ""}]},
             "systems": systems, "integrations": integrations, "automations": autos, "entities": entities,
             "interactions": interactions,
             "gaps": [{"note": g["note"][:2000]} for g in doc.get("gaps", [])]}
    common.write_json(eng / "drawing" / "model.json", model)
    print(f"{len(systems)} system card(s), {len(integrations)} integration(s), {len(autos)} automation(s), {len(entities)} object(s); "
          f"middleware placement threshold {threshold}")
    print("MODEL drawing/model.json")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) == 3 and argv[0] == "check-found":
            return cmd_check_found(argv[1], argv[2])
        commands = {"merge": merge, "show": show, "correct": correct, "model": build_model}
        if len(argv) == 2 and argv[0] in commands:
            return commands[argv[0]](argv[1])
    except SetupError as exc:
        print(f"SETUP {exc}")
        return 2
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
