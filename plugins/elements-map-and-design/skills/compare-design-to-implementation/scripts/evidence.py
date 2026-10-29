"""Gather the evidence for every linked box, pack it per box, check each verdict, and roll the verdicts up.

    python3 evidence.py plan ENG         # the Elements calls to make -> evidence/plan.json
    python3 evidence.py related ENG      # automations that act on the linked objects and fields -> evidence/related.json
    python3 evidence.py pack ENG         # one evidence pack per box -> assess/packs/<box>.json, definitions in assess/defs/
    python3 evidence.py wave ENG         # the next boxes to assess (limits.csv assessor_wave at a time)
    python3 evidence.py check ENG FILE [--dry]   # check one implementation-assessor answer (assess/verdicts/<box>.json);
                                                 # --dry checks without recording the pass (the agent's own check)
    python3 evidence.py rollup ENG       # every box's verdict -> results.json and report.md

What is saved, all in ENG/evidence/ (plan names each file):
  component-<k>.json  get_metadata_component answer (nodeIds, summary) for batch k
  history-<k>.json    get_component_change_history answer (nodeIds, historyType change_logs) for batch k
  explain-<k>.json    explain_metadata_components answer (aspect summary) for batch k, failed items kept
  <pull>-<i>.ndjson   the parts of get_metadata_source and get_dependencies pulls, recorded in pulls.json
A box is assessed when it has metadata links in the run's reference model, or links to components that org lacks
(missing-in-org: packed as not found, so the verdict names what the org does not have). Exit 0 done, 1 refused
(the lines say why), 2 setup problem.
"""

import json
import subprocess
import sys
from pathlib import Path

import common

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from metadata_narrative import narrative_text
from common import Failed, SetupError, level_sort_key, load_json, norm, write_json

FIELD_LIKE = ("field", "record type", "process", "standard value set", "global value set")


def chunks(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def usable(box):
    """The links whose component is in the run's org."""
    return [l for l in box["links"] if l.get("status") == "ok"]


def absent(box):
    """The links whose component the run's org does not have."""
    return [l for l in box["links"] if l.get("status") == "missing-in-org"]


def missing_id(link):
    return f"missing:{link.get('metadataType')}:{link.get('apiName')}"


def assess_set(design):
    return [bid for bid in sorted(design["boxes"], key=lambda b: (level_sort_key(design["boxes"][b]["level"]), design["boxes"][b]["number"] or 0))
            if usable(design["boxes"][bid]) or absent(design["boxes"][bid])]


def is_target(sf_type):
    """Objects and fields are where automations act; everything else is itself the implementation."""
    return common.is_object_type(sf_type) or norm(sf_type) in FIELD_LIKE


def plan(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    boxes = assess_set(design)
    if not boxes:
        write_json(eng / "evidence" / "plan.json", {"boxes": [], "nodeIds": []})
        decided = [b for b in design["boxes"].values() if b.get("decision")]
        if decided:
            print(f"DECISIONS ONLY: no box has a metadata link, but {len(decided)} carry the analyst's approved decisions "
                  f"(nothing found, or no org support needed); run evidence.py rollup")
        else:
            print("NOTHING LINKED: no box in scope has a metadata link, so nothing can be compared")
        return 0
    nodes, types = [], {}
    for bid in boxes:
        for link in usable(design["boxes"][bid]):
            if link["nodeId"] not in types:
                nodes.append(link["nodeId"])
                types[link["nodeId"]] = link.get("metadataType") or ""
    targets = [n for n in nodes if is_target(types[n])]
    field_objects = []  # objects of the linked fields: their picklist values are read once per object
    for bid in boxes:
        for link in usable(design["boxes"][bid]):
            api = link.get("apiName") or ""
            if norm(link.get("metadataType")) == "field" and "." in api and api.split(".")[0] not in field_objects:
                field_objects.append(api.split(".")[0])
    others = [n for n in nodes if not is_target(types[n])]
    doc = {
        "boxes": boxes, "nodeIds": nodes,
        "component": [{"file": f"component-{i + 1}.json", "nodeIds": c} for i, c in enumerate(chunks(nodes, 50))],
        "history": [{"file": f"history-{i + 1}.json", "nodeIds": c} for i, c in enumerate(chunks(nodes, 50))],
        "explain": [{"file": f"explain-{i + 1}.json", "nodeIds": c} for i, c in enumerate(chunks(nodes, 25))],
        "source": [{"pull": f"source-{i + 1}", "nodeIds": c} for i, c in enumerate(chunks(nodes, 5000))],
        "using": [{"pull": f"using-{i + 1}", "nodeIds": c} for i, c in enumerate(chunks(others, 1000))],
        "whereUsed": [{"pull": f"where-used-{i + 1}", "nodeIds": c} for i, c in enumerate(chunks(targets, 1000))],
        "values": [{"pull": f"values-{i + 1}", "object": o} for i, o in enumerate(field_objects)],
    }
    write_json(eng / "evidence" / "plan.json", doc)
    print(f"PLAN {len(boxes)} box(es), {len(nodes)} linked component(s). Calls, every one with refModelId and teamId:")
    for b in doc["component"]:
        print(f"  get_metadata_component nodeIds ({len(b['nodeIds'])}) -> evidence/{b['file']}")
    for b in doc["history"]:
        print(f"  get_component_change_history nodeIds ({len(b['nodeIds'])}) historyType change_logs -> evidence/{b['file']}")
    for b in doc["explain"]:
        print(f"  explain_metadata_components aspect summary nodeIds ({len(b['nodeIds'])}) -> evidence/{b['file']}")
    for b in doc["source"]:
        print(f"  get_metadata_source nodeIds ({len(b['nodeIds'])}) -> pull {b['pull']}")
    for b in doc["using"]:
        print(f"  get_dependencies lookingFor using attributes [description, status] nodeIds ({len(b['nodeIds'])}) -> pull {b['pull']}")
    for b in doc["whereUsed"]:
        print(f"  get_dependencies lookingFor where_used attributes [description, status] nodeIds ({len(b['nodeIds'])}) -> pull {b['pull']}")
    for b in doc["values"]:
        print(f"  list_metadata_by_criteria metadataList [\"Custom Value\"], filters [{{\"column\": \"parent_object\", \"operator\": "
              f"\"eq\", \"value\": \"{b['object']}\"}}], columns [\"name\", \"api_name\", \"active\", \"parent_object\"] -> pull {b['pull']}")
    return 0


def is_trimmed(path):
    """True when a saved answer still carries the server's _truncated marker (more items to fetch)."""
    try:
        data = load_json(path)
    except Exception:
        return False   # an unreadable file is reported by the step that reads it
    return isinstance(data, dict) and bool(data.get("_truncated"))


def verify_plan_files(eng, doc, with_related):
    errors = []
    for key in ("component", "history", "explain"):
        for b in doc.get(key) or []:
            if not (eng / "evidence" / b["file"]).exists():
                errors.append(f"evidence/{b['file']} is not saved")
            elif is_trimmed(eng / "evidence" / b["file"]):
                errors.append(f"evidence/{b['file']} is a trimmed answer (_truncated): call again with the same arguments "
                              f"and skip set to _truncated.nextSkip until an answer has no _truncated, and save the items "
                              f"of every answer joined in this file, without _truncated")
            elif key == "explain":
                unanswered = len(set(b["nodeIds"]) - set(items_by_node(eng, [b])))
                if unanswered:
                    errors.append(f"evidence/{b['file']} answers {len(b['nodeIds']) - unanswered} of its {len(b['nodeIds'])} "
                                  f"components (a retry saved over the batch): ask explain_metadata_components again for the "
                                  f"missing nodeIds and merge their items into this file")
    pulls = common.load_pulls(eng)
    for key in ("source", "using", "whereUsed", "values"):
        for b in doc.get(key) or []:
            errors += common.verify_pull(eng, b["pull"], pulls)
    if with_related:
        rel_path = eng / "evidence" / "related.json"
        if not rel_path.exists():
            errors.append("evidence/related.json is not written: run evidence.py related")
        else:
            rel = load_json(rel_path)
            if rel["nodeIds"]:
                errors += common.verify_pull(eng, rel["pull"], pulls)
    return errors


def rows_of(eng, doc, key):
    out = []
    for b in doc.get(key) or []:
        out += common.pull_rows(eng, b["pull"])
    return out


def related(eng):
    eng = Path(eng)
    limits = common.load_limits()
    autos = {k for k, v in common.load_link_types().items() if v["kind"] == "automation"}
    doc = load_json(eng / "evidence" / "plan.json", "the evidence plan")
    errors = []
    pulls = common.load_pulls(eng)
    for b in doc.get("whereUsed") or []:
        errors += common.verify_pull(eng, b["pull"], pulls)
    if errors:
        raise Failed(errors)
    linked = set(doc["nodeIds"])
    by_target = {}
    for row in rows_of(eng, doc, "whereUsed"):
        rel = row.get("related") or {}
        if norm(rel.get("type")) not in autos or rel.get("nodeId") in linked:
            continue
        by_target.setdefault((row.get("node") or {}).get("nodeId"), {})[rel["nodeId"]] = rel
    chosen = []
    for target, rels in by_target.items():
        ranked = sorted(rels.values(), key=lambda r: (r.get("active") is False, r.get("name") or ""))
        for rel in ranked[:limits["automations_per_object"]]:
            if rel["nodeId"] not in chosen:
                chosen.append(rel["nodeId"])
    if len(chosen) > 5000:
        raise Failed(["Related-source scope exceeds 5000 node IDs; split the evidence scope before pulling"])
    out = {"pull": "source-related", "nodeIds": chosen}
    write_json(eng / "evidence" / "related.json", out)
    if chosen:
        print(f"RELATED {len(chosen)} automation(s) act on the linked objects and fields: call get_metadata_source with "
              f"these nodeIds, saving the parts as pull source-related")
    else:
        print("NO RELATED automations: nothing more to read")
    return 0


def items_by_node(eng, files):
    out = {}
    for b in files:
        answer = load_json(eng / "evidence" / b["file"])
        items = answer.get("items")
        if items is None and answer.get("nodeId"):
            items = [answer]
        for item in items or []:
            if item.get("nodeId"):
                out[item["nodeId"]] = item
    return out


def save_definition(eng, row, limit):
    """Write one definition to assess/defs/; return (path relative to ENG, truncated, gap)."""
    node = row["nodeId"]
    if row.get("status") != "ok":
        return None, False, f"no definition: {row.get('reason') or row.get('status')}"
    defs = eng / "assess" / "defs"
    defs.mkdir(parents=True, exist_ok=True)
    parts = []
    if row.get("xml"):
        parts.append(row["xml"])
    if row.get("body"):
        parts.append(row["body"])
    text = "\n\n".join(parts)
    truncated = len(text) > limit
    ext = "cls" if row.get("body") else ("json" if row.get("xmlFormat") == "json" else "xml")
    path = defs / f"{node}.{ext}"
    path.write_text(text[:limit], encoding="utf-8")
    scope = " (the whole object's definition: find the field in it)" if row.get("xmlScope") == "object" else ""
    gaps = ([str(row["reason"])] if row.get("reason") else []) + ([f"definition cut at {limit} characters"] if truncated else [])
    if not text:
        gaps.append("no stored definition text")
    gap = "; ".join(gaps) or None
    return str(path.relative_to(eng)) + scope, truncated, gap


def flow_steps(eng, node, api_name, def_path, ref_model_id):
    out = eng / "assess" / "defs" / f"{node}.steps.json"
    script = common.PLUGIN / "scripts" / "flow_to_steps.py"
    result = subprocess.run([sys.executable, str(script), str(eng / def_path.split(" (")[0]), "--automation-id", node,
                             "--api-name", api_name or node, "--ref-model-id", ref_model_id, "--out", str(out)], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return str(out.relative_to(eng))


def describe_row(row):
    rel = row.get("related") or {}
    attrs = rel.get("attributes") or {}
    entry = {"nodeId": rel.get("nodeId"), "name": rel.get("name"), "apiName": rel.get("apiName"), "type": rel.get("type"),
             "object": rel.get("object"), "active": rel.get("active"), "status": attrs.get("status") or rel.get("status")}
    for key in ("read", "write", "triggerType", "triggerAction"):
        if row.get(key) is not None:
            entry[key] = row[key]
    if attrs.get("description"):
        entry["description"] = attrs["description"][:500]
    if row.get("relationshipDescription"):
        entry["how"] = row["relationshipDescription"][:300]
    return entry


def pack(eng):
    eng = Path(eng)
    pulls = common.load_pulls(eng)
    limits = common.load_limits()
    autos = {k for k, v in common.load_link_types().items() if v["kind"] == "automation"}
    design = load_json(eng / "design.json", "the design file")
    doc = load_json(eng / "evidence" / "plan.json", "the evidence plan")
    if not doc["boxes"]:
        raise Failed(["nothing is linked: no pack to build"])
    errors = verify_plan_files(eng, doc, with_related=bool(doc.get("whereUsed")))
    if errors:
        raise Failed(errors)
    components = items_by_node(eng, doc["component"])
    history = items_by_node(eng, doc["history"])
    explained = items_by_node(eng, doc["explain"])
    sources = {r["nodeId"]: r for r in rows_of(eng, doc, "source")}
    rel = load_json(eng / "evidence" / "related.json") if (eng / "evidence" / "related.json").exists() else {"nodeIds": []}
    if rel["nodeIds"]:
        sources.update({r["nodeId"]: r for r in common.pull_rows(eng, rel["pull"])})
    values = {}
    for row in rows_of(eng, doc, "values"):
        parent = row.get("parentPath") or ""
        if ".fields." in parent:
            obj = parent.split(".")[2] if parent.count(".") >= 3 else ""
            field = parent.split(".fields.")[-1].split(".")[0]
            values.setdefault(f"{obj}.{field}", []).append(
                {"value": row.get("name"), "active": (row.get("nodeDetails") or {}).get("active")})
    deps = {}
    for key, direction in (("using", "using"), ("whereUsed", "whereUsed")):
        for row in rows_of(eng, doc, key):
            node = (row.get("node") or {}).get("nodeId")
            deps.setdefault(node, {}).setdefault(direction, []).append(row)

    def_cache = {}

    def definition(node, api_name, sf_type):
        if node in def_cache:
            return def_cache[node]
        row = sources.get(node)
        if row is None:
            result = (None, False, "no definition returned for this component", None)
        else:
            path, truncated, gap = save_definition(eng, row, limits["definition_chars_per_component"])
            steps = flow_steps(eng, node, api_name, path, design["refModelId"]) if path and norm(sf_type) == "flow" and not truncated else None
            result = (path, truncated, gap, steps)
        def_cache[node] = result
        return result

    packs_dir = eng / "assess" / "packs"
    org_name = (common.load_state(eng).get("slots") or {}).get("ref_model_name") or "the org compared"
    levels = {l["levelNumber"]: l for l in design["levels"]}
    for bid in doc["boxes"]:
        box = design["boxes"][bid]
        level = levels[box["level"]]
        pack_doc = {"box": bid, "text": box["text"], "level": box["level"], "levelTitle": level["title"],
                    "levelDescription": level["description"], "diagramType": level["subtype"],
                    "resources": box["resources"], "attributes": box["attributes"], "footer": box["footer"],
                    "notes": box["notes"], "inLines": box["inLines"], "outLines": box["outLines"],
                    "parentBox": design["boxes"][box["parent"]]["text"] if box["parent"] else None,
                    "childSteps": [design["boxes"][c]["text"] for c in box["children"]],
                    "noteMaxWords": limits["note_max_words"], "org": org_name, "components": [], "gaps": common.native_gaps(pulls),
                    "truncated": False}

        for link in usable(box):
            node = link["nodeId"]
            comp = components.get(node) or {}
            desc = comp.get("description")
            entry = {"nodeId": node, "name": link.get("name"), "apiName": link.get("apiName"),
                     "type": link.get("metadataType"), "linkSource": link["source"],
                     "description": (desc.get("value") if isinstance(desc, dict) else desc) or ""}
            if not comp:
                pack_doc["gaps"].append(f"{link.get('name')}: get_metadata_component returned nothing (deleted or not readable)")
                entry["notFound"] = True
            exp = explained.get(node)
            if exp and exp.get("status") == "complete" and exp.get("narrative"):
                entry["explanation"] = narrative_text(exp["narrative"])[:3000]
            else:
                pack_doc["gaps"].append(f"{link.get('name')}: no explanation ({(exp or {}).get('error') or (exp or {}).get('status') or 'not asked'})")
            d = definition(node, link.get("apiName"), link.get("metadataType"))
            if d[0]:
                entry["definition"] = d[0]
                if len(d) > 3 and d[3]:
                    entry["flowSteps"] = d[3]
            if d[2]:
                pack_doc["gaps"].append(f"{link.get('name')}: {d[2]}")
            if d[1]:
                pack_doc["truncated"] = True
            if norm(link.get("metadataType")) == "field" and link.get("apiName") in values:
                entry["picklistValues"] = values[link["apiName"]][:100]
            hist = history.get(node) or {}
            logs = sorted(hist.get("changeLogs") or [], key=lambda c: c.get("lastModifiedDate") or "", reverse=True)
            entry["changes"] = [{"date": c.get("lastModifiedDate"), "by": c.get("lastModifiedBy"), "status": c.get("status")}
                                for c in logs[:limits["change_logs_per_component"]]]
            dep = deps.get(node) or {}
            for direction in ("using", "whereUsed"):
                rows = dep.get(direction) or []
                if direction == "whereUsed":
                    rows = [r for r in rows if norm((r.get("related") or {}).get("type")) in autos]
                kept = [describe_row(r) for r in rows[:limits["dependency_rows_per_component"]]]
                if kept:
                    entry[direction] = kept
                if len(rows) > len(kept):
                    pack_doc["truncated"] = True
                    pack_doc["gaps"].append(f"{link.get('name')}: {len(rows) - len(kept)} more {direction} rows not shown")
            if is_target(link.get("metadataType")):
                acting = []
                for row in (dep.get("whereUsed") or []):
                    r = row.get("related") or {}
                    if r.get("nodeId") in sources and norm(r.get("type")) in autos:
                        d2 = definition(r["nodeId"], r.get("apiName"), r.get("type"))
                        item = {"nodeId": r["nodeId"], "name": r.get("name"), "type": r.get("type"), "active": r.get("active")}
                        if d2[1]:
                            pack_doc["truncated"] = True
                        if d2[2]:
                            pack_doc["gaps"].append(f"{r.get('name')}: {d2[2]}")
                        if d2[0]:
                            item["definition"] = d2[0]
                            if len(d2) > 3 and d2[3]:
                                item["flowSteps"] = d2[3]
                        acting.append(item)
                if acting:
                    entry["automationsActingOnIt"] = acting
            pack_doc["components"].append(entry)
        for link in absent(box):
            pack_doc["components"].append({"nodeId": missing_id(link), "name": link.get("name"), "apiName": link.get("apiName"),
                                           "type": link.get("metadataType"), "linkSource": link["source"],
                                           "notFound": True, "missingInOrg": True, "description": ""})
        write_json(packs_dir / f"{bid}.json", pack_doc)
    print(f"PACKED {len(doc['boxes'])} box(es) in assess/packs/")
    return 0


def checked_path(eng):
    return Path(eng) / "assess" / "checked.json"


def wave(eng):
    eng = Path(eng)
    limits = common.load_limits()
    doc = load_json(eng / "evidence" / "plan.json", "the evidence plan")
    checked = load_json(checked_path(eng))["boxes"] if checked_path(eng).exists() else {}
    todo = [b for b in doc["boxes"] if b not in checked]
    if not todo:
        print(f"ALL ASSESSED {len(doc['boxes'])} box(es)")
        return 0
    batch = todo[:limits["assessor_wave"]]
    print(f"WAVE {len(batch)} of {len(todo)} left: run one implementation-assessor agent per box, pack "
          f"assess/packs/<box>.json, output assess/verdicts/<box>.json")
    for b in batch:
        print(f"  {b}")
    return 0


def check(eng, file, dry=False):
    eng = Path(eng)
    limits = common.load_limits()
    answer = load_json(file, "the assessor answer")
    errors = common.shape_errors(answer, "assessment.schema.json")
    if errors:
        raise Failed(errors)
    bid = answer["box"]
    pack_path = eng / "assess" / "packs" / f"{bid}.json"
    if not pack_path.exists():
        raise Failed([f"box {bid} has no pack"])
    pack_doc = load_json(pack_path)
    known = {c["nodeId"] for c in pack_doc["components"]}
    for c in pack_doc["components"]:
        for key in ("using", "whereUsed", "automationsActingOnIt"):
            known |= {r.get("nodeId") for r in c.get(key) or []}
    for ev in answer["evidence"]:
        if ev["nodeId"] not in known:
            errors.append(f"evidence {ev['nodeId']} is not in the box's pack; cite only components the pack lists")
    if answer["verdict"] in ("partial", "not-supported"):
        if not answer.get("missing"):
            errors.append(f"verdict {answer['verdict']} needs at least one line in missing")
        if not (answer.get("note") or "").strip():
            errors.append(f"verdict {answer['verdict']} needs a note for the sticky note")
    if answer["verdict"] == "supported" and answer.get("missing"):
        errors.append("verdict supported cannot list anything missing; use partial")
    if common.word_count(answer.get("note")) > limits["note_max_words"]:
        errors.append(f"note has {common.word_count(answer['note'])} words; at most {limits['note_max_words']}")
    if pack_doc["truncated"] and not answer.get("gaps"):
        errors.append("the pack was cut (see its gaps): say in gaps what the verdict could not see")
    if errors:
        raise Failed(errors)
    if dry:
        print(f"ASSESSED OK {bid}: {answer['verdict']} (not recorded: the orchestrator records it)")
        return 0
    checked = load_json(checked_path(eng))["boxes"] if checked_path(eng).exists() else {}
    checked[bid] = {"file": str(Path(file).resolve().relative_to(eng.resolve())) if str(Path(file).resolve()).startswith(str(eng.resolve())) else str(file),
                    "verdict": answer["verdict"]}
    write_json(checked_path(eng), {"boxes": checked})
    print(f"ASSESSED OK {bid}: {answer['verdict']}")
    return 0


def children_summary(verdicts):
    counted = [v for v in verdicts if v != "no-org-support"]
    if not counted:
        return "none"
    if all(v == "supported" for v in counted):
        return "all-supported"
    if all(v == "not-supported" for v in counted):
        return "all-not-supported"
    if all(v == "not-assessed" for v in counted):
        return "all-not-assessed"
    return "mixed"


def trim_words(text, limit):
    words = (text or "").split()
    return " ".join(words) if len(words) <= limit else " ".join(words[:limit - 1]) + " ..."


def rollup(eng):
    eng = Path(eng)
    limits = common.load_limits()
    matrix = common.load_rollup()
    verdict_rows = common.load_verdicts()
    design = load_json(eng / "design.json", "the design file")
    doc = load_json(eng / "evidence" / "plan.json", "the evidence plan")
    checked = load_json(checked_path(eng))["boxes"] if checked_path(eng).exists() else {}
    missing = [b for b in doc["boxes"] if b not in checked]
    if missing:
        raise Failed([f"box {b} ({design['boxes'][b]['text']}) has no checked verdict" for b in missing])
    answers = {b: load_json(eng / checked[b]["file"]) for b in doc["boxes"]}
    boxes = design["boxes"]
    results = {}

    def leaf(bid):
        box = boxes[bid]
        if bid in answers:
            a = answers[bid]
            return {"verdict": a["verdict"], "note": a.get("note", ""), "how": "assessed", "supported": a.get("supported", []),
                    "missing": a.get("missing", []), "evidence": a["evidence"], "confidence": a["confidence"],
                    "gaps": a.get("gaps", [])}
        dec = box.get("decision") or {}
        if dec.get("kind") == "nothing-found":
            return {"verdict": "not-supported", "note": dec.get("gapNote", ""), "how": "nothing found when matching",
                    "missing": [dec.get("reason", "")]}
        if dec.get("kind") == "no-org-support":
            return {"verdict": "no-org-support", "note": "", "how": "needs no org support", "missing": [], "reason": dec.get("reason", "")}
        return {"verdict": "not-assessed", "note": "", "how": "no metadata linked", "missing": []}

    order = sorted(boxes, key=lambda b: -len(boxes[b]["level"].split(".")))
    for bid in order:  # deepest levels first, so a parent sees its children's verdicts
        box = boxes[bid]
        own = leaf(bid)
        if not box["children"]:
            results[bid] = own
            continue
        kids = [results[c]["verdict"] for c in box["children"]]
        summary = children_summary(kids)
        own_key = own["verdict"] if own["how"] == "assessed" else "none"
        verdict = matrix[(own_key, summary)]
        not_full = [boxes[c]["text"] for c in box["children"] if results[c]["verdict"] in ("partial", "not-supported", "not-assessed")]
        note = own.get("note", "") if own_key in ("partial", "not-supported") else ""
        if verdict in ("partial", "not-supported") and not_full:
            lead = f"{len(not_full)} of {len([k for k in kids if k != 'no-org-support'])} steps beneath are not fully supported: "
            note = trim_words((note + " " if note else "") + lead + "; ".join(not_full), limits["note_max_words"])
        missing = list(own.get("missing") or []) if own_key != "none" else []
        missing += [f"beneath: {boxes[c]['text']} ({verdict_rows[results[c]['verdict']]['label'].lower()})" for c in box["children"]
                    if results[c]["verdict"] in ("partial", "not-supported", "not-assessed")]
        results[bid] = dict(own, verdict=verdict, note=note, missing=missing,
                            how=("rolled up" if own_key == "none" else "assessed and rolled up"), children=summary)
    counts = {v: sum(1 for r in results.values() if r["verdict"] == v) for v in common.VERDICTS}
    write_json(eng / "results.json", {"boxes": results, "counts": counts})

    lines = [f"# Design check: {design.get('mapName') or design.get('mapId')}", "",
             f"Scope: {'the whole map' if design['scope'] == 'map' else 'level ' + design['scope'] + ' and the levels beneath it'}, "
             f"against {(common.load_state(eng).get('slots') or {}).get('ref_model_name') or 'the reference model'} as Elements last synced it. "
             f"{len(results)} steps: " + ", ".join(f"{counts[v]} {verdict_rows[v]['label'].lower()}" for v in common.VERDICTS if counts[v]) + ".", ""]
    for level in design["levels"]:
        lines += [f"## Level {level['levelNumber']}: {level['title']}", "", "| Step | Verdict | What is missing | How |", "|---|---|---|---|"]
        for bid in level["boxes"]:
            r = results[bid]
            missing_text = "; ".join(m for m in r.get("missing") or [] if m) or (r.get("reason") or "")
            lines.append(f"| {boxes[bid]['text']} | {verdict_rows[r['verdict']]['label']} | {missing_text.replace('|', '/')} | {r['how']} |")
        lines.append("")
    not_saved = eng / "links" / "not-saved.json"
    org_name = (common.load_state(eng).get("slots") or {}).get("ref_model_name") or "the org compared"
    not_in_org = [(b, l) for b in boxes for l in boxes[b]["links"] if l.get("status") == "missing-in-org"]
    if not_in_org:
        lines += [f"## Linked on the design but not in {org_name}", ""]
        lines += [f"- {boxes[b]['text']}: {l.get('name')} ({l.get('metadataType')} {l.get('apiName')})" for b, l in not_in_org]
        lines.append("")
    followed = sum(1 for b in boxes for l in boxes[b]["links"] if l.get("followed"))
    if followed:
        lines += [f"{followed} link(s) on the design name another org's copy of a component; the check used {org_name}'s copy.", ""]
    approved_not_saved = [(b, l) for b in boxes for l in boxes[b]["links"] if l["source"] == "approved-not-saved"]
    if approved_not_saved:
        lines += ["## Links used but not saved on the map", ""]
        lines += [f"- {boxes[b]['text']}: {l.get('name')} ({l.get('metadataType')})" for b, l in approved_not_saved]
        lines.append("")
    if not_saved.exists():
        lines += ["## Links Elements refused", ""]
        lines += [f"- {boxes[n['box']]['text']}: {n['apiName']} ({n['reason']})" for n in load_json(not_saved)["links"]]
        lines.append("")
    (eng / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("ROLLED UP " + ", ".join(f"{v} {counts[v]}" for v in common.VERDICTS) + "; report.md written")
    return 0


def main():
    args = sys.argv[1:]
    commands = {"plan": plan, "related": related, "pack": pack, "wave": wave, "rollup": rollup}
    if len(args) == 2 and args[0] in commands:
        return commands[args[0]](args[1])
    if len(args) in (3, 4) and args[0] == "check" and (len(args) == 3 or args[3] == "--dry"):
        return check(args[1], args[2], dry=len(args) == 4)
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    common.run(main)
