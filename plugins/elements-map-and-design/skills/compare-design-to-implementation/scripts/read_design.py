"""Read a saved map into the design file, follow its links into the org being compared, and count which boxes are linked.

    python3 read_design.py build ENG
    python3 read_design.py org-plan ENG     # the lookups that find the design's links in the run's org
    python3 read_design.py org-map ENG      # read those lookups -> ENG/links/org-map.json
    python3 read_design.py coverage ENG

build reads ENG/levels/outline.json ({"items": [...]}, every page of get_process_map_outline joined) and one
ENG/levels/<levelNumber>.json per level in scope (the get_diagram answer with include ["layout", "metadata",
"notes"]). The scope is slots.scope of ENG/execution-state.json: "map" for every level, or a level number for that
level and every level beneath it, since a box is judged with the steps under it. Links approved in
ENG/links/approved.json that the read does not show are added as "approved-not-saved", so a map the analyst cannot
edit is still compared on them. Writes ENG/design.json. Refuses (exit 1) when a level in scope has no saved read, or
when the scope holds more boxes than limits.csv boxes_per_run allows.

A link on a box ties it to one component across every org the space syncs (production and each sandbox), but the
diagram names one org's copy of it. A link whose copy is in the run's reference model (slots.ref_model_id) is used as
it is. Any other link, made in another org or one Elements cannot resolve, is looked up in the run's org by its type
and API name: build prints TO RESOLVE; org-plan writes ENG/links/org-plan.json and prints one list_metadata_by_criteria
call per type (per object for fields), each saved as the pull it names; org-map reads the pulls into
ENG/links/org-map.json, and the next build follows each link to the run's org's copy, or marks it missing-in-org: the
design asks for a component this org does not have.

coverage writes ENG/coverage.json and prints ALL LINKED, or UNLINKED n OF m with the boxes by level. A box that has
a level beneath it is judged by what is under it, so only boxes without one are counted. A link followed to the run's
org counts, and so does one missing in it (the box is judged on what the org lacks); a link with no type or API name
to look up does not. Refuses while a link is still to be looked up.

Exit 0 done, 1 refused (the lines say why), 2 setup problem.
"""

import json
import sys
from pathlib import Path

import common
from common import Failed, SetupError, box_id, level_sort_key, load_json, norm, write_json

LOOKUP_CHUNK = 50  # API names per list_metadata_by_criteria call


from mcp_result import require_complete

def in_scope(level, scope):
    if scope in (None, "", "map"):
        return True
    return level == scope or level.startswith(scope + ".")


def read_link(att, ref_model_id):
    node = att.get("nodeId")
    link = {
        "nodeId": node,
        "apiName": att.get("apiName"),
        "metadataType": att.get("metadataType"),
        "name": att.get("name") or att.get("apiName"),
        "refModelId": att.get("refModelId"),
        "source": "diagram",
    }
    here = node and not att.get("unresolved") and not att.get("restricted")
    if here and (not ref_model_id or att.get("refModelId") == ref_model_id):
        link["status"] = "ok"
    elif ref_model_id and link["apiName"] and link["metadataType"]:
        link["status"] = "to-resolve"  # another org's copy, or none Elements resolves: look it up in the run's org
    else:
        link["status"] = "unresolved"
    return link


def link_key(metadata_type, api_name):
    return f"{norm(metadata_type)}|{(api_name or '').casefold()}"


def load_org_map(eng, ref_model, warnings):
    path = eng / "links" / "org-map.json"
    if not path.exists() or not ref_model:
        return None
    org = load_json(path, "the org lookups")
    if org.get("refModelId") != ref_model:
        warnings.append("links/org-map.json was looked up in another reference model; run org-plan and org-map again")
        return None
    return org


def follow(link, org, ref_model):
    """Point a to-resolve link at the run's org's copy, or mark it missing there."""
    if link.get("status") != "to-resolve" or org is None:
        return
    key = link_key(link["metadataType"], link["apiName"])
    found = (org.get("found") or {}).get(key)
    if found:
        link.update({"linkedNodeId": link["nodeId"], "linkedRefModelId": link["refModelId"], "nodeId": found["nodeId"],
                     "refModelId": ref_model, "status": "ok", "followed": True})
    elif key in (org.get("missing") or []):
        link["status"] = "missing-in-org"
    elif key in (org.get("ambiguous") or []):
        link["status"] = "unresolved"
        link["why"] = "several components in the run's org have this type and API name"


def build(eng):
    eng = Path(eng)
    state = common.load_state(eng)
    slots = state.get("slots") or {}
    scope = slots.get("scope") or "map"
    ref_model = slots.get("ref_model_id")
    limits = common.load_limits()
    outline = require_complete(load_json(eng / "levels" / "outline.json", "the saved outline"))
    items = outline.get("items") or []
    if not items:
        raise Failed(["levels/outline.json lists no levels; save every page of get_process_map_outline as {\"items\": [...]}"])
    by_diagram = {i["diagramId"]: i for i in items}
    wanted = [i for i in items if in_scope(str(i["levelNumber"]), scope)]
    if not wanted:
        raise Failed([f"no level of the map matches the scope {scope}"])
    missing = [i["levelNumber"] for i in wanted if not (eng / "levels" / f"{i['levelNumber']}.json").exists()]
    if missing:
        raise Failed([f"level {n} is in scope but levels/{n}.json is not saved; read it with get_diagram "
                      f"include [\"layout\", \"metadata\", \"notes\"]" for n in sorted(missing, key=level_sort_key)])

    levels, boxes, warnings = [], {}, []
    parent_of_level = {}
    for item in sorted(wanted, key=lambda i: level_sort_key(i["levelNumber"])):
        number = str(item["levelNumber"])
        read = require_complete(load_json(eng / "levels" / f"{number}.json", f"the read of level {number}"))
        diagram = read.get("diagram") or {}
        if read.get("diagramId") and read["diagramId"] != item["diagramId"]:
            raise Failed([f"levels/{number}.json is the read of diagram {read['diagramId']}, the outline says {item['diagramId']}"])
        ids = []
        lines = diagram.get("lines") or []
        acts = diagram.get("activities") or []
        texts = {a["key"]: a.get("text", "") for a in acts}
        for act in acts:
            bid = box_id(number, act["key"])
            notes = [{"title": a.get("title", ""), "text": a.get("text", "")}
                     for a in act.get("attachments") or [] if a.get("type") == "note"]
            links = [read_link(a, ref_model) for a in act.get("attachments") or [] if a.get("type") == "metadata"]
            in_lines = [{"label": l.get("label", ""), "from": texts.get((l.get("from") or {}).get("activity"), "outside")}
                        for l in lines if (l.get("to") or {}).get("activity") == act["key"]]
            out_lines = [{"label": l.get("label", ""), "to": texts.get((l.get("to") or {}).get("activity"), "outside")}
                         for l in lines if (l.get("from") or {}).get("activity") == act["key"]]
            child = None
            if act.get("drilldown"):
                target = by_diagram.get(act["drilldown"])
                if target is None:
                    warnings.append(f"box {bid} drills down to diagram {act['drilldown']}, which the outline does not list")
                elif in_scope(str(target["levelNumber"]), scope):
                    child = str(target["levelNumber"])
                    parent_of_level[child] = bid
            boxes[bid] = {
                "id": bid, "level": number, "key": act["key"], "number": act.get("number"),
                "text": act.get("text", ""), "diagramId": item["diagramId"],
                "resources": [{"type": r.get("type"), "name": r.get("name")} for r in act.get("resources") or []],
                "attributes": [{"title": a.get("title", ""), "description": a.get("description", "")}
                               for a in act.get("attributes") or []],
                "footer": act.get("footerText", ""),
                "notes": notes, "links": links, "inLines": in_lines, "outLines": out_lines,
                "parent": None, "childLevel": child, "children": [], "decision": None,
                "layout": {k: act.get(k) for k in ("x", "y", "w", "h", "fill", "border")},
            }
            ids.append(bid)
        free_notes = [{"key": n["key"], "x": n.get("x"), "y": n.get("y"), "w": n.get("w"), "h": n.get("h"),
                       "text": n.get("text", ""), "ours": (n.get("text") or "").lstrip().startswith(common.NOTE_MARKER)
                       or (n.get("text") or "").lstrip().startswith(common.LEGEND_MARKER)}
                      for n in diagram.get("notes") or []]
        levels.append({
            "levelNumber": number, "diagramId": item["diagramId"], "title": read.get("title") or item.get("title"),
            "description": read.get("description", ""), "subtype": read.get("subtype"), "version": read.get("version"),
            "canvas": diagram.get("canvas"), "lock": item.get("lock"), "parentBox": None, "boxes": ids,
            "freeNotes": free_notes,
            "texts": [{"key": t["key"], "x": t.get("x"), "y": t.get("y"), "w": t.get("w"), "h": t.get("h")}
                      for t in diagram.get("texts") or []],
        })
    for level in levels:
        parent = parent_of_level.get(level["levelNumber"])
        level["parentBox"] = parent
        if parent:
            for bid in level["boxes"]:
                boxes[bid]["parent"] = parent
            boxes[parent]["children"] = list(level["boxes"])

    org = load_org_map(eng, ref_model, warnings)
    for box in boxes.values():
        for link in box["links"]:
            follow(link, org, ref_model)

    approved_path = eng / "links" / "approved.json"
    if approved_path.exists():
        approved = load_json(approved_path, "the approved links")
        for bid, entry in (approved.get("boxes") or {}).items():
            box = boxes.get(bid)
            if box is None:
                warnings.append(f"links/approved.json names box {bid}, which is not in scope")
                continue
            have = {l["nodeId"] for l in box["links"] if l.get("nodeId")}
            for link in entry.get("links") or []:
                if link["nodeId"] not in have:
                    box["links"].append({"nodeId": link["nodeId"], "apiName": link.get("apiName"),
                                         "metadataType": link.get("sfType"), "name": link.get("name"),
                                         "refModelId": ref_model, "source": "approved-not-saved", "status": "ok"})
            if entry.get("decision") in ("no-org-support", "nothing-found"):
                box["decision"] = {"kind": entry["decision"], "reason": entry.get("reason", ""),
                                   "gapNote": entry.get("gapNote", "")}

    if len(boxes) > limits["boxes_per_run"]:
        raise Failed([f"the scope holds {len(boxes)} boxes; one run compares at most {limits['boxes_per_run']} "
                      f"(limits.csv boxes_per_run): narrow the scope to a level"])
    design = {"mapId": outline.get("mapId"), "mapName": outline.get("name"), "scope": scope,
              "refModelId": ref_model, "levels": levels, "boxes": boxes, "warnings": warnings}
    write_json(eng / "design.json", design)
    for line in warnings:
        print(f"WARNING {line}")
    linked = sum(1 for b in boxes.values() if usable_links(b))
    print(f"BUILT {len(levels)} level(s), {len(boxes)} box(es), {linked} with links")
    pending = to_resolve(design)
    if pending:
        print(f"TO RESOLVE {len(pending)} link(s) name a copy in another org, or one Elements cannot resolve: run "
              f"read_design.py org-plan to look them up in the run's org")
    return 0


def usable_links(box):
    return [l for l in box["links"] if l.get("status") in ("ok", "missing-in-org")]


def to_resolve(design):
    """The distinct links still to look up in the run's org, by key."""
    out = {}
    for box in design["boxes"].values():
        for link in box["links"]:
            if link.get("status") == "to-resolve":
                out.setdefault(link_key(link["metadataType"], link["apiName"]),
                               {"metadataType": link["metadataType"], "apiName": link["apiName"]})
    return out


def org_plan(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    ref_model = design.get("refModelId")
    if not ref_model:
        raise Failed(["the run has no reference model (slots.ref_model_id): links are only looked up for a comparison"])
    pending = to_resolve(design)
    qualified = {k for k, v in common.load_link_types().items() if v["qualify"] == "object"}
    simple, by_object, keys = {}, {}, {}
    for key, link in sorted(pending.items()):
        mtype, api = link["metadataType"], link["apiName"]
        if norm(mtype) in qualified:
            if "." not in api:
                keys[key] = {"metadataType": mtype, "apiName": api, "pull": None}  # cannot be looked up: missing
                continue
            obj, child = api.split(".", 1)
            by_object.setdefault((mtype, obj), []).append((key, child))
        else:
            simple.setdefault(mtype, []).append((key, api))
    calls = []

    def add(mtype, obj, names):
        pull = f"org-{len(calls) + 1}"
        filters = ([{"column": "parent_object", "operator": "eq", "value": obj}] if obj else []) + \
                  [{"column": "api_name", "operator": "eq", "value": n} for _, n in names]
        columns = ["name", "api_name"] + (["parent_object"] if obj else []) + ["status"]
        calls.append({"pull": pull, "metadataList": [mtype], "filters": filters, "columns": columns, "object": obj})
        for key, n in names:
            keys[key] = {"metadataType": mtype, "apiName": f"{obj}.{n}" if obj else n, "pull": pull}

    for mtype, names in simple.items():
        for i in range(0, len(names), LOOKUP_CHUNK):
            add(mtype, None, names[i:i + LOOKUP_CHUNK])
    for (mtype, obj), names in by_object.items():
        for i in range(0, len(names), LOOKUP_CHUNK):
            add(mtype, obj, names[i:i + LOOKUP_CHUNK])
    write_json(eng / "links" / "org-plan.json", {"refModelId": ref_model, "calls": calls, "keys": keys})
    if not calls and not keys:
        print("NOTHING TO RESOLVE: every link is in the run's org")
        return 0
    print(f"LOOKUPS {len(calls)} for {len(keys)} link(s). Call list_metadata_by_criteria with refModelId {ref_model}, "
          f"teamId, and these arguments, saving each answer's parts as the pull named (a list with no rows too):")
    for c in calls:
        args = {"metadataList": c["metadataList"], "filters": c["filters"], "columns": c["columns"]}
        print(f"  pull {c['pull']}: {json.dumps(args)}")
    return 0


def org_map(eng):
    eng = Path(eng)
    plan_doc = load_json(eng / "links" / "org-plan.json", "the org lookups plan")
    pulls = common.load_pulls(eng)
    errors = []
    for c in plan_doc["calls"]:
        errors += common.verify_pull(eng, c["pull"], pulls)
    if errors:
        raise Failed(errors)
    rows_by_key = {}
    for c in plan_doc["calls"]:
        mtype = c["metadataList"][0]
        for row in common.pull_rows(eng, c["pull"], pulls):
            api = (row.get("sf") or {}).get("apiName") or row.get("apiName") or ""
            if c["object"]:
                obj = row.get("parentObject") or c["object"]
                api = f"{obj}.{api}"
            rows_by_key.setdefault(link_key(mtype, api), []).append(row)
    found, missing, ambiguous = {}, [], []
    for key, entry in plan_doc["keys"].items():
        rows = [r for r in rows_by_key.get(key, []) if norm(r.get("status")) != "deleted"]
        if len(rows) == 1:
            found[key] = {"nodeId": rows[0]["nodeId"], "name": rows[0].get("name"), "status": rows[0].get("status")}
        elif len(rows) > 1:
            ambiguous.append(key)
        else:
            missing.append(key)
    map_path = eng / "links" / "org-map.json"
    earlier = load_json(map_path) if map_path.exists() else {}
    if earlier.get("refModelId") == plan_doc["refModelId"]:  # keep the lookups of earlier rounds
        for key, value in (earlier.get("found") or {}).items():
            found.setdefault(key, value)
        settled = set(found) | set(missing) | set(ambiguous)
        missing += [k for k in earlier.get("missing") or [] if k not in settled]
        ambiguous += [k for k in earlier.get("ambiguous") or [] if k not in settled and k not in missing]
    write_json(map_path, {"refModelId": plan_doc["refModelId"], "found": found, "missing": missing, "ambiguous": ambiguous})
    print(f"FOUND {len(found)} link(s) in the run's org; MISSING {len(missing)}; AMBIGUOUS {len(ambiguous)}")
    for key in [k for k in ambiguous if k in plan_doc["keys"]]:
        entry = plan_doc["keys"][key]
        print(f"  AMBIGUOUS {entry['metadataType']} {entry['apiName']}: several components in the run's org have this "
              f"name; the link is left out")
    for key in [k for k in missing if k in plan_doc["keys"]]:
        entry = plan_doc["keys"][key]
        print(f"  NOT IN ORG {entry['metadataType']} {entry['apiName']}")
    print("Run read_design.py build again to follow them")
    return 0


def coverage(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    pending = to_resolve(design)
    if pending:
        raise Failed([f"{len(pending)} link(s) are not yet looked up in the run's org: run read_design.py org-plan, "
                      f"make its calls, run org-map, then build again"])
    boxes = design["boxes"]
    by_level, unlinked = {}, []
    followed, absent, unresolved = [], [], []
    for level in design["levels"]:
        counts = {"boxes": 0, "linked": 0, "unlinked": 0, "parents": 0}
        for bid in level["boxes"]:
            box = boxes[bid]
            counts["boxes"] += 1
            for link in box["links"]:
                if link.get("followed"):
                    followed.append(f"{bid} {link.get('name')}")
                if link["status"] == "missing-in-org":
                    absent.append(f"{bid} {link.get('name')} ({link.get('metadataType')})")
                elif link["status"] == "unresolved":
                    unresolved.append(f"{bid} {link.get('name')}")
            if box["childLevel"]:
                counts["parents"] += 1
                continue
            if usable_links(box) or box.get("decision"):
                counts["linked"] += 1
            else:
                counts["unlinked"] += 1
                unlinked.append(bid)
        by_level[level["levelNumber"]] = counts
    leaves = sum(c["boxes"] - c["parents"] for c in by_level.values())
    result = {"leafBoxes": leaves, "unlinked": unlinked, "byLevel": by_level,
              "followedLinks": followed, "missingInOrg": absent, "unresolvedLinks": unresolved}
    write_json(eng / "coverage.json", result)
    if followed:
        print(f"FOLLOWED {len(followed)} link(s) made in another org to the same component in the run's org")
    for line in absent:
        print(f"NOT IN ORG {line}: the design links it, the run's org does not have it; the box is judged without it")
    for line in unresolved:
        print(f"UNRESOLVED {line}: nothing to look it up by, or several components in the run's org match it; not used")
    if not unlinked:
        print(f"ALL LINKED {leaves} box(es) without a level beneath")
    else:
        print(f"UNLINKED {len(unlinked)} OF {leaves}")
        for number, counts in sorted(by_level.items(), key=lambda kv: level_sort_key(kv[0])):
            if counts["unlinked"]:
                names = [boxes[b]["text"] for b in unlinked if boxes[b]["level"] == number]
                print(f"  level {number}: {counts['unlinked']} of {counts['boxes'] - counts['parents']}: " + "; ".join(names))
    return 0


def main():
    commands = {"build": build, "org-plan": org_plan, "org-map": org_map, "coverage": coverage}
    if len(sys.argv) != 3 or sys.argv[1] not in commands:
        print(__doc__.strip())
        return 2
    return commands[sys.argv[1]](sys.argv[2])


if __name__ == "__main__":
    common.run(main)
