"""Merge the derived design into the model, and slice it into one model per diagram.

    python3 design.py check-section ENG data-model     # check derive/data-model.json
    python3 design.py check-section ENG integrations   # check derive/integrations.json
    python3 design.py merge ENG                        # both sections into model.json
    python3 design.py slice ENG --project NAME [--lower-confidence]
    python3 design.py stale ENG                        # corrections newer than the access matrix?

check-section checks one deriver's file against its schema and against the
process (every step it names exists) and prints SECTION OK (exit 0) or ERROR
lines for the deriver to fix (exit 1). merge rebuilds ENG/model.json from
ENG/process-model.json (the process as read) and both sections: entities, relationships, systems and
integrations in the shared model's own shape, each activity's 'uses' from the
sections' steps; it runs the plugin's validator for the data model and the
system architecture, printing its lines prefixed data-model: or
system-architecture:, and replaces model.json only when both pass (MERGED,
exit 0). Section ERROR lines or a failing validator end in REFUSED (exit 1,
or 2 for a setup problem). slice writes ENG/drawing/models/data-model[-<area>].json and architecture.json, each with
the source map's link in its description, proposed integrations labelled
'(proposed)' and proposed systems footed 'Proposed'. stale prints STALE when
ENG/derive/corrections.json is newer than ENG/access-matrix.csv (corrections
applied, access not yet derived again), otherwise FRESH.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from common import SetupError, eng_path, load_json, shape_errors, write_json, validate

ENTITY_KEYS = ("id", "name", "apiName", "kind", "description", "fields", "inferred", "evidence", "attachments")
RELATIONSHIP_KEYS = ("id", "from", "to", "cardinality", "kind", "fromEnd", "toEnd", "field", "label", "inferred", "evidence")
SYSTEM_KEYS = ("id", "name", "kind", "description", "inferred", "evidence", "attachments", "hub", "zone", "parent", "icon",
               "attributes", "footer", "footerIcons")
INTEGRATION_KEYS = ("id", "from", "to", "pattern", "direction", "technology", "label", "inferred", "evidence", "timing", "step")
SECTIONS = {"data-model": ("data-model.json", "data-model-section.schema.json"),
            "integrations": ("integrations.json", "integrations-section.schema.json")}


def base_model(eng):
    return load_json(eng_path(eng, "process-model.json"), "process-model.json (written by read_process_map.py)")


def section_errors(eng, which, base):
    name, schema = SECTIONS[which]
    doc = load_json(eng_path(eng, "derive", name), f"derive/{name}")
    errors = [f"derive/{name} {e}" for e in shape_errors(doc, schema)]
    if errors:
        return doc, errors
    steps = {a["id"] for a in base.get("activities", [])}
    if which == "data-model":
        ids = {e["id"] for e in doc["entities"]}
        for e in doc["entities"]:
            errors += [f"entity '{e['id']}' names step '{s}', which is not an activity of the process" for s in e["steps"] if s not in steps]
            if e.get("nodeId") and e["kind"] == "proposed":
                errors.append(f"entity '{e['id']}' is proposed but has an org nodeId; a proposed entity does not exist yet")
        for r in doc["relationships"]:
            errors += [f"relationship {r.get('id', '')} {r['from']}->{r['to']}: '{x}' is not an entity" for x in (r["from"], r["to"]) if x not in ids]
            errors += [f"relationship {r['from']}->{r['to']} names step '{s}', which is not an activity" for s in r.get("steps", []) if s not in steps]
        placed = [x for a in doc.get("areas", []) for x in a["entities"]]
        if doc.get("areas"):
            errors += [f"area lists '{x}', which is not an entity" for x in placed if x not in ids]
            errors += [f"entity '{x}' is in no area" for x in ids if x not in placed]
            errors += [f"entity '{x}' is in more than one area" for x in set(placed) if placed.count(x) > 1]
    else:
        ids = {s["id"] for s in doc["systems"]}
        for s in doc["systems"]:
            errors += [f"system '{s['id']}' names step '{x}', which is not an activity" for x in s["steps"] if x not in steps]
        for i in doc["integrations"]:
            errors += [f"integration '{i['id']}': '{x}' is not a system" for x in (i["from"], i["to"]) if x not in ids]
            errors += [f"integration '{i['id']}' names step '{x}', which is not an activity" for x in i["steps"] if x not in steps]
        for h in doc["manualHandoffs"]:
            if h["step"] not in steps:
                errors.append(f"manual handoff names step '{h['step']}', which is not an activity")
        if not any(s.get("hub") for s in doc["systems"]):
            errors.append("no system is marked hub: true; mark the target system")
    return doc, errors


def check_section(eng, which):
    base = base_model(eng)
    _, errors = section_errors(eng, which, base)
    for line in errors:
        print(f"ERROR {line}")
    if errors:
        print(f"REFUSED fix derive/{SECTIONS[which][0]} and check again")
        return 1
    print(f"SECTION OK derive/{SECTIONS[which][0]}")
    return 0


def merged_model(eng):
    ref_model_id = (load_json(eng_path(eng, "execution-state.json")).get("slots") or {}).get("ref_model_id")
    base = base_model(eng)
    dm, e1 = section_errors(eng, "data-model", base)
    it, e2 = section_errors(eng, "integrations", base)
    if e1 or e2:
        return None, e1 + e2
    model = {k: v for k, v in base.items() if k not in ("entities", "relationships", "systems", "integrations")}
    model["activities"] = [dict(a) for a in base.get("activities", [])]
    uses = {}
    entities = []
    for e in dm["entities"]:
        item = {k: e[k] for k in ENTITY_KEYS if k in e}
        if e.get("apiName") and e["kind"] in ("standard", "custom") and e.get("nodeId"):
            item.setdefault("attachments", []).append({"type": "metadata", "apiName": e["apiName"],
                                                        "metadataType": {"standard": "Standard Object", "custom": "Custom Object"}[e["kind"]],
                                                        **({"refModelId": ref_model_id} if ref_model_id else {})})
        entities.append(item)
        for s in e["steps"]:
            uses.setdefault(s, []).append(e["id"])
    systems = []
    for s in it["systems"]:
        systems.append({k: s[k] for k in SYSTEM_KEYS if k in s})
        for step in s["steps"]:
            uses.setdefault(step, []).append(s["id"])
    integrations = []
    for i in it["integrations"]:
        item = {k: i[k] for k in INTEGRATION_KEYS if k in i}
        if not item.get("label") and not item.get("technology"):
            item["label"] = i["data"][:200]
        integrations.append(item)
    for act in model["activities"]:
        act.pop("uses", None)
        if act["id"] in uses:
            act["uses"] = list(dict.fromkeys(uses[act["id"]]))
    model["entities"] = entities
    model["relationships"] = [{k: r[k] for k in RELATIONSHIP_KEYS if k in r} for r in dm["relationships"]]
    model["systems"] = systems
    model["integrations"] = integrations
    model["gaps"] = list(base.get("gaps", [])) + list(dm.get("gaps", [])) + list(it.get("gaps", []))
    if not model["gaps"]:
        model.pop("gaps")
    return model, []


def merge(eng):
    model, errors = merged_model(eng)
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED fix the derivers' files (check-section names which) and merge again")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "model.json"
        write_json(candidate, model)
        worst = 0
        for diagram_type in ("data-model", "system-architecture"):
            code, lines = validate.run_checks(candidate, diagram_type)
            for line in lines:
                print(f"{diagram_type}: {line}")
            worst = max(worst, code)
    if worst:
        print("REFUSED the merged model fails the validator; send each error to the deriver of its section")
        return worst
    write_json(eng_path(eng, "model.json"), model)
    print(f"MERGED model.json: {len(model['entities'])} entities, {len(model['relationships'])} relationships, "
          f"{len(model['systems'])} systems, {len(model['integrations'])} integrations")
    return 0


def data_model_part(model, keep, meta):
    """The entities in keep and the relationships between them, as a data model to draw or picture."""
    return {"schemaVersion": "1.0", "meta": meta,
            "entities": [e for e in model["entities"] if e["id"] in keep],
            "relationships": [r for r in model["relationships"] if r["from"] in keep and r["to"] in keep]}


def architecture_model(model, it, meta, only=None):
    """The systems and integrations (only those whose ids are in only, when given), proposed ones marked as such."""
    status = {i["id"]: i["status"] for i in it["integrations"]}
    sys_status = {s["id"]: s["status"] for s in it["systems"]}
    chosen = [i for i in model["integrations"] if only is None or i["id"] in only]
    ends = {e for i in chosen for e in (i["from"], i["to"])}
    systems = []
    for s in model["systems"]:
        if only is not None and s["id"] not in ends:
            continue
        s = dict(s)
        if sys_status.get(s["id"]) == "proposed" and not s.get("footer"):
            s["footer"] = "Proposed"
        systems.append(s)
    integrations = []
    for i in chosen:
        i = dict(i)
        if status.get(i["id"]) == "proposed":
            base = i.get("label") or ""
            i["label"] = (base + " (proposed)").strip()[:200]
        integrations.append(i)
    return {"schemaVersion": "1.0", "meta": meta, "systems": systems, "integrations": integrations}


def slice_models(eng, project, lower):
    model = load_json(eng_path(eng, "model.json"), "model.json")
    dm = load_json(eng_path(eng, "derive", "data-model.json"), "derive/data-model.json")
    it = load_json(eng_path(eng, "derive", "integrations.json"), "derive/integrations.json")
    src = model["meta"]["sources"]
    link = src[0]["ref"] if src else ""
    note = f"Derived by process-led design from the process map {link}."
    if lower:
        note += " The map did not pass the derivability check, so treat this design as lower confidence."
    written = []

    def meta(title):
        return {"title": title[:80], "description": note, "author": "design-from-process-map design.py", "sources": src}

    areas = dm.get("areas") or [{"id": "", "name": "", "entities": [e["id"] for e in model["entities"]]}]
    for area in areas:
        keep = set(area["entities"])
        part = data_model_part(model, keep, meta(f"{project} data model" + (f": {area['name']}" if area["name"] else "")))
        dropped = [r for r in model["relationships"] if (r["from"] in keep) != (r["to"] in keep)]
        if dropped:
            part["gaps"] = [{"note": f"{len(dropped)} relationship(s) join this area to another area and are drawn on neither: "
                                     + "; ".join(f"{r['from']} to {r['to']}" for r in dropped[:10])}]
        name = "data-model" + (f"-{area['id']}" if area["id"] else "")
        write_json(eng_path(eng, "drawing", "models", f"{name}.json"), part)
        written.append(name)
    write_json(eng_path(eng, "drawing", "models", "architecture.json"),
               architecture_model(model, it, meta(f"{project} system architecture")))
    written.append("architecture")
    for name in written:
        print(f"SLICED drawing/models/{name}.json")
    return 0


def stale(eng):
    corrections = eng_path(eng, "derive", "corrections.json")
    matrix = eng_path(eng, "access-matrix.csv")
    if corrections.exists() and (not matrix.exists() or corrections.stat().st_mtime > matrix.stat().st_mtime):
        print("STALE corrections were applied after the access matrix was derived")
    else:
        print("FRESH the access matrix follows the latest corrections")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check-section")
    p.add_argument("eng")
    p.add_argument("which", choices=sorted(SECTIONS))
    p = sub.add_parser("merge")
    p.add_argument("eng")
    p = sub.add_parser("slice")
    p.add_argument("eng")
    p.add_argument("--project", required=True)
    p.add_argument("--lower-confidence", action="store_true")
    p = sub.add_parser("stale")
    p.add_argument("eng")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "check-section":
            return check_section(args.eng, args.which)
        if args.cmd == "merge":
            return merge(args.eng)
        if args.cmd == "stale":
            return stale(args.eng)
        return slice_models(args.eng, args.project, args.lower_confidence)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
