"""Turn the saved reads of a process map into the shared model and an inventory.

    python3 read_process_map.py build ENG

Reads ENG/levels/outline.json (the get_process_map_outline answer) and one
ENG/levels/<levelNumber>.json per level (the get_diagram answer with include
["all", "layout"]). Writes:

- ENG/model.json and ENG/process-model.json: meta, roles, activities (with
  parent, roles, diagramRef) and flows of every level, in the plugin's shared
  model (process-model.json stays as read; design.py merge rebuilds model.json
  from it);
- ENG/inventory.json: per level, every activity with its verb, resources,
  metadata attachments and the labels of its lines; across the map, every
  resource by type with the steps that use it.

Refuses (exit 1) when a level of the outline has no saved read, so a map read
in part is never taken for the whole map. Exit 2 is a setup problem.
"""

import re
import sys
from collections import OrderedDict

from common import (END, START, SetupError, eng_path, first_word, level_files, load_json, model_id, norm,
                    write_json)

ROLE_TYPES = {"Human": "human", "System": "system", "Platform / Capability": "system"}
AI_NAME = re.compile(r"\b(ai|agentforce|agent|bot|copilot|assistant|claude|gpt|einstein)\b", re.I)


from mcp_result import require_complete

def activity_id(level, key):
    return model_id("a", level, key)


def end_kind(end):
    """'activity' for an activity end; 'outside' for a terminator, an off-page link or a free end."""
    if isinstance(end, dict) and "activity" in end:
        return "activity"
    return "outside"


def describe_end(end):
    if end is None:
        return "free end"
    if "activity" in end:
        return f"activity {end['activity']}"
    if end.get("terminator"):
        return "terminator"
    if "offPage" in end:
        return "off-page link"
    return "free end"


def build(eng):
    outline, items = level_files(eng)
    reads = OrderedDict()
    missing = []
    for item in sorted(items, key=lambda i: [int(p) if p.isdigit() else p for p in str(i["levelNumber"]).split(".")]):
        path = eng_path(eng, "levels", f"{item['levelNumber']}.json")
        if not path.exists():
            missing.append(item["levelNumber"])
            continue
        read = require_complete(load_json(path, f"level {item['levelNumber']}"))
        if read.get("diagramId") != item["diagramId"]:
            raise SetupError(f"levels/{item['levelNumber']}.json is diagram {read.get('diagramId')}, but the outline gives "
                             f"{item['diagramId']} for level {item['levelNumber']}; save the right level")
        if "diagram" not in read:
            raise SetupError(f"levels/{item['levelNumber']}.json has no diagram; save the whole get_diagram answer")
        reads[item["levelNumber"]] = (item, read)
    if missing:
        print(f"REFUSED levels with no saved read: {', '.join(missing)}. Read each with get_diagram (include all and layout) "
              "into levels/<levelNumber>.json, then build again")
        return 1

    by_diagram = {item["diagramId"]: number for number, (item, _) in reads.items()}
    top = next(iter(reads.values()))[1]
    map_name = outline.get("name") or top.get("title") or "Process map"
    url = top.get("diagramUrl", "")

    roles = OrderedDict()           # (kind, norm name) -> role
    role_names = {}                 # norm name -> kind, to keep names unique across kinds
    activities, flows, gaps = [], [], []
    inventory = {"map": {"mapId": outline.get("mapId"), "name": map_name, "url": url}, "levels": [],
                 "resources": {}, "metadata": []}
    resources = OrderedDict()       # (type, norm name) -> {name, type, steps}
    metadata = OrderedDict()        # (metadataType, apiName) -> {...}

    def role_for(resource):
        kind = ROLE_TYPES.get(resource.get("type"))
        if not kind:
            return None
        name = resource["name"].strip()
        if kind == "system" and AI_NAME.search(name):
            kind = "ai-agent"
        key = (kind, norm(name))
        if key not in roles:
            shown = name
            if norm(name) in role_names and role_names[norm(name)] != kind:
                shown = f"{name} ({kind})"
            role_names.setdefault(norm(name), kind)
            roles[key] = {"id": model_id("r", name if shown == name else shown), "name": shown, "kind": kind}
            ids = [r["id"] for r in roles.values()]
            if ids.count(roles[key]["id"]) > 1:
                roles[key]["id"] = model_id("r", kind, name)
        return roles[key]

    for number, (item, read) in reads.items():
        diagram = read["diagram"]
        parent = None
        if item.get("parentActivity") and item.get("parentDiagramId") in by_diagram:
            parent = activity_id(by_diagram[item["parentDiagramId"]], item["parentActivity"]["key"])
        level_inv = {"levelNumber": number, "diagramId": item["diagramId"], "title": read.get("title") or item.get("title"),
                     "url": read.get("diagramUrl", ""), "parent": parent, "activities": [], "lines": []}
        ids_by_key, names_on_level = {}, {}
        for act in diagram.get("activities", []):
            aid = activity_id(number, act["key"])
            ids_by_key[act["key"]] = aid
            text = " ".join((act.get("text") or "").split()) or f"Unnamed step {act.get('number', act['key'])}"
            name = text[:200]
            count = names_on_level.get(norm(name), 0) + 1
            names_on_level[norm(name)] = count
            if count > 1:
                gaps.append({"about": aid, "note": f"Level {number} has {count} boxes named '{name}'; this one is "
                                                   f"'{name} ({count})' in the model."})
                name = f"{name[:194]} ({count})"
            model_act = {"id": aid, "name": name, "diagramRef": {"diagramId": item["diagramId"], "key": act["key"]}}
            if parent:
                model_act["parent"] = parent
            assigned, seen_roles = [], set()
            inv_resources = []
            for res in act.get("resources", []):
                if not res.get("name"):
                    continue
                inv_resources.append({k: res[k] for k in ("name", "type", "rasci") if k in res})
                rkey = (res.get("type") or "Other", norm(res["name"]))
                entry = resources.setdefault(rkey, {"name": res["name"].strip(), "type": res.get("type") or "Other", "steps": []})
                entry["steps"].append(aid)
                role = role_for(res)
                if role and role["id"] not in seen_roles:
                    seen_roles.add(role["id"])
                    assignment = {"role": role["id"]}
                    letters = "".join(ch for ch in (res.get("rasci") or "") if ch in "RASCI")
                    if letters and role["kind"] == "human":
                        assignment["rasci"] = letters
                    assigned.append(assignment)
            if assigned:
                model_act["roles"] = assigned
            inv_meta = []
            for att in (act.get("attachments") or []):
                if att.get("type") == "metadata" and att.get("apiName"):
                    m = {k: att[k] for k in ("apiName", "metadataType", "nodeId", "refModelId", "name") if k in att}
                    inv_meta.append(m)
                    mkey = (att.get("metadataType"), att["apiName"])
                    entry = metadata.setdefault(mkey, dict(m, steps=[]))
                    entry["steps"].append(aid)
            activities.append(model_act)
            level_inv["activities"].append({
                "id": aid, "key": act["key"], "number": act.get("number"), "text": text, "verb": first_word(text),
                "resources": inv_resources, "metadata": inv_meta,
                "notes": [a.get("title") for a in (act.get("attachments") or []) if a.get("type") == "note" and a.get("title")],
                "drilldown": act.get("drilldown"), "linesIn": [], "linesOut": []})
        acts_inv = {a["key"]: a for a in level_inv["activities"]}
        seen_flows = set()
        for line in diagram.get("lines", []):
            src, dst = line.get("from"), line.get("to")
            label = " ".join((line.get("label") or "").split())
            level_inv["lines"].append({"key": line["key"], "from": describe_end(src), "to": describe_end(dst), "label": label})
            if end_kind(src) == "activity" and src["activity"] in acts_inv:
                acts_inv[src["activity"]]["linesOut"].append(label)
            if end_kind(dst) == "activity" and dst["activity"] in acts_inv:
                acts_inv[dst["activity"]]["linesIn"].append(label)
            frm = ids_by_key.get(src["activity"]) if end_kind(src) == "activity" else START
            to = ids_by_key.get(dst["activity"]) if end_kind(dst) == "activity" else END
            if frm is None or to is None or (frm == START and to == END):
                continue
            key = (frm, to, norm(label))
            if key in seen_flows:
                continue
            seen_flows.add(key)
            flow = {"id": model_id("f", number, line["key"]), "from": frm, "to": to}
            if label:
                flow["label"] = label[:200]
            flows.append(flow)
        inventory["levels"].append(level_inv)

    inventory["resources"] = {}
    for entry in resources.values():
        inventory["resources"].setdefault(entry["type"], []).append(
            {"name": entry["name"], "steps": sorted(set(entry["steps"]), key=entry["steps"].index)})
    inventory["metadata"] = [dict(m, steps=sorted(set(m["steps"]), key=m["steps"].index)) for m in metadata.values()]

    model = {
        "schemaVersion": "1.0",
        "meta": {"title": map_name[:80] if len(map_name) >= 2 else "Process map",
                 "description": f"Derived from the process map '{map_name}': {url}"[:5000],
                 "author": "design-from-process-map read_process_map.py",
                 "sources": [{"kind": "diagram", "ref": url or str(outline.get("mapId"))}]},
        "roles": list(roles.values()),
        "activities": activities,
        "flows": flows,
    }
    if gaps:
        model["gaps"] = gaps
    write_json(eng_path(eng, "model.json"), model)
    write_json(eng_path(eng, "process-model.json"), model)
    write_json(eng_path(eng, "inventory.json"), inventory)
    print(f"BUILT model.json: {len(reads)} levels, {len(activities)} activities, {len(flows)} lines, {len(roles)} roles; "
          f"inventory.json: {sum(len(v) for v in inventory['resources'].values())} resources, {len(inventory['metadata'])} "
          "linked metadata items")
    for gap in gaps:
        print(f"GAP {gap['note']}")
    return 0


def main(argv):
    if len(argv) != 3 or argv[1] != "build":
        print(__doc__.strip())
        return 2
    try:
        return build(argv[2])
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
