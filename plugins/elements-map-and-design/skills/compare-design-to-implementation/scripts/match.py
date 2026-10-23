"""Propose metadata links for the boxes that have none, take the analyst's corrections, and plan the writes.

    python3 match.py terms ENG                  # the searches of this round -> match/round-N/searches.json
    python3 match.py objects ENG                # objects among the hits -> match/round-N/objects.json
    python3 match.py briefs ENG                 # one matcher brief per level -> match/round-N/briefs/<level>.json
    python3 match.py check ENG FILE             # check one metadata-matcher answer
    python3 match.py next-round ENG             # whether the matchers asked for another round
    python3 match.py table ENG                  # the proposal -> links/proposed.json, printed as a table
    python3 match.py confirm ENG                # the analyst's corrections -> links/approved.json
    python3 match.py resolve ENG                # links that need their object's API name -> links/resolve.json
    python3 match.py plan ENG                   # manage_diagram changes per level -> links/plan/<level>.json
    python3 match.py drop-failed ENG LEVEL FILE [--batch N] # drop refusals from batch N (default 1)

N is match.round in ENG/execution-state.json. Search answers are saved as match/round-N/<search id>.json (the
search_metadata answer, whole); the where-used answer as the pull named in objects.json; each matcher answer as
match/round-N/found/<level>.json. Exit 0 done, 1 refused (the lines say why), 2 setup problem.
"""

import re
import sys
from pathlib import Path

import common
from common import Failed, SetupError, level_sort_key, load_json, norm, write_json

STOP = set("""
a an the and or of to for in on at by with from into onto via as is are be been being it its this that these those
their his her our your my we they he she you i who whom which what when where why how all any each every some more
most other than then so not no nor only own same too very can will just should would could may might must shall
new next set get use using up down out over under again further once both few such per if else also e g eg etc
step steps process task tasks activity activities box record records data information details detail system
was were has have had right left them him make made way ways like well able about after before during while
""".split())

VERB_HINTS = set("""
create update capture assign qualify convert review approve reject send receive submit check verify validate
manage handle record log notify call contact schedule close open complete generate calculate track monitor report
agree negotiate sign renew cancel escalate route resolve register enter add remove change set define design launch
""".split())


def round_dir(eng, rnd):
    return Path(eng) / "match" / f"round-{rnd}"


def current_round(eng):
    return int(((common.load_state(eng).get("match") or {}).get("round")) or 1)


def variants(term):
    words = term.split()
    out = [term]
    if len(words) > 1:
        out += ["".join(words), "_".join(words), "".join(w.capitalize() for w in words)]
    return list(dict.fromkeys(out))


def words_of(text):
    return [w for w in re.split(r"[^A-Za-z0-9]+", (text or "").casefold()) if w]


def box_terms(box, limit):
    """Search terms for one box: the objects and systems it names, then its nouns, then its verbs. Single words: the
    search matches the start of a name's words, so a phrase finds only names that hold it whole."""
    terms = []
    for res in box["resources"]:
        if res.get("type") in ("Object", "System", "Flow", "Platform / Capability") and res.get("name"):
            terms.append(norm(res["name"]))
    content = [w for w in words_of(box["text"]) if len(w) >= 2 and w not in STOP]
    nouns = [w for w in content if w not in VERB_HINTS]
    verbs = [w for w in content if w in VERB_HINTS]  # automations are often named by what they do: "Lead Assignment"
    terms += nouns + verbs
    out = []
    for t in terms:
        if t and t not in out:
            out.append(t)
    return out[:limit]


def terms(eng):
    eng = Path(eng)
    limits = common.load_limits()
    rnd = current_round(eng)
    design = load_json(eng / "design.json", "the design file")
    searches, by_term, gaps = [], {}, []

    def add(term, bid):
        key = norm(term)
        queries = variants(key)
        if not queries or len(queries) > 20 or any(not 2 <= len(q.strip()) <= 256 for q in queries):
            gaps.append({"box": bid, "term": term, "note": "search query requires 2-256 trimmed characters and at most 20 variants"})
            return
        if key not in by_term:
            entry = {"id": f"s{len(searches) + 1}", "term": key, "queries": queries, "boxes": []}
            by_term[key] = entry
            searches.append(entry)
        if bid not in by_term[key]["boxes"]:
            by_term[key]["boxes"].append(bid)

    if rnd == 1:
        cov = load_json(eng / "coverage.json", "the coverage file")
        for bid in cov["unlinked"]:
            for term in box_terms(design["boxes"][bid], limits["terms_per_box"]):
                add(term, bid)
    else:
        done = set()
        for earlier in range(1, rnd):
            done |= {x["term"] for x in load_json(round_dir(eng, earlier) / "searches.json")["searches"]}
        prev = round_dir(eng, rnd - 1) / "found"
        for path in sorted(prev.glob("*.json")):
            for ask in load_json(path).get("moreTerms") or []:
                for query in (ask.get("queries") or [])[:limits["more_terms_per_box"]]:
                    if norm(query) not in done:
                        add(query.strip(), ask["box"])
    asked = []
    if rnd > 1:
        for path in sorted((round_dir(eng, rnd - 1) / "found").glob("*.json")):
            asked += [a["box"] for a in load_json(path).get("moreTerms") or []]
    if not searches and not asked and not gaps:
        raise Failed([f"round {rnd} has nothing to search"])
    write_json(round_dir(eng, rnd) / "searches.json", {"round": rnd, "limit": limits["hits_per_search"], "searches": searches,
                                                        "boxes": list(dict.fromkeys(asked)), "gaps": gaps})
    print(f"SEARCHES {len(searches)} for round {rnd}: call search_metadata once per search with its queries and "
          f"limit {limits['hits_per_search']}, saving each answer as match/round-{rnd}/<id>.json")
    for s in searches:
        print(f"  {s['id']}: {s['queries']}")
    return 0


def search_answers(eng, rnd):
    rd = round_dir(eng, rnd)
    plan = load_json(rd / "searches.json", "the searches of this round")
    answers, missing = {}, []
    for s in plan["searches"]:
        path = rd / f"{s['id']}.json"
        if not path.exists():
            missing.append(f"search {s['id']} ({s['term']}) is not saved as match/round-{rnd}/{s['id']}.json")
            continue
        answers[s["id"]] = load_json(path)
    if missing:
        raise Failed(missing)
    return plan, answers


def core_objects(design, plan, answers):
    """Objects whose name is one of the searched words: the records the boxes are about."""
    terms = {s["term"] for s in plan["searches"]}
    out = {}
    for answer in answers.values():
        for node in answer.get("nodes") or []:
            if not common.is_object_type(node.get("sfType")):
                continue
            if norm(node.get("name")) in terms or norm(node.get("apiName")) in terms:
                out.setdefault(node["nodeId"], {"nodeId": node["nodeId"], "name": node.get("name"),
                                                "apiName": node.get("apiName"), "sfType": node.get("sfType")})
    return out


def objects(eng):
    eng = Path(eng)
    rnd = current_round(eng)
    design = load_json(eng / "design.json", "the design file")
    plan, answers = search_answers(eng, rnd)
    core = core_objects(design, plan, answers)
    if rnd > 1:  # objects read in an earlier round are not read again
        for earlier in range(1, rnd):
            prev = round_dir(eng, earlier) / "objects.json"
            if prev.exists():
                for oid in load_json(prev)["nodeIds"]:
                    core.pop(oid, None)
    ids = list(core)
    pull = f"match-r{rnd}-where-used"
    fields = [{"nodeId": oid, "name": core[oid]["name"], "apiName": core[oid]["apiName"],
               "pull": f"match-r{rnd}-fields-{i + 1}"} for i, oid in enumerate(ids)]
    if len(ids) > 1000:
        raise Failed(["Object dependency scope exceeds 1000 node IDs; split the matching scope before pulling"])
    write_json(round_dir(eng, rnd) / "objects.json", {"pull": pull, "nodeIds": ids, "objects": list(core.values()),
                                                      "fieldPulls": fields})
    if ids:
        print(f"OBJECTS {len(ids)}: " + ", ".join(core[o]["name"] for o in ids))
        print(f"  get_dependencies lookingFor where_used, nodeIds from objects.json, attributes [\"description\", \"status\"] -> pull {pull}")
        for f in fields:
            print(f"  list_metadata_by_criteria metadataList [\"Field\"], filters [{{\"column\": \"parent_object\", \"operator\": "
                  f"\"eq\", \"value\": \"{f['apiName']}\"}}], columns [\"name\", \"api_name\", \"parent_object\", \"description\", \"status\"] -> pull {f['pull']}")
    else:
        print("NO OBJECTS named by the searched words: no further call this round")
    return 0


def where_used_by_object(eng, rnd, automation_types):
    obj = load_json(round_dir(eng, rnd) / "objects.json", "the objects of this round")
    if not obj["nodeIds"]:
        return {}
    errors = common.verify_pull(eng, obj["pull"])
    if errors:
        raise Failed(errors)
    out = {}
    for row in common.pull_rows(eng, obj["pull"]):
        related = row.get("related") or {}
        if norm(related.get("type")) not in automation_types:
            continue
        attrs = related.get("attributes") or {}
        out.setdefault((row.get("node") or {}).get("nodeId"), []).append({
            "nodeId": related.get("nodeId"), "name": related.get("name"), "apiName": related.get("apiName"),
            "sfType": related.get("type"), "active": related.get("active"),
            "description": (attrs.get("description") or "")[:400], "status": attrs.get("status") or related.get("status"),
        })
    return out


def object_fields(eng, rnd):
    obj = load_json(round_dir(eng, rnd) / "objects.json", "the objects of this round")
    out, errors = {}, []
    pulls = common.load_pulls(eng)
    for f in obj.get("fieldPulls") or []:
        problems = common.verify_pull(eng, f["pull"], pulls)
        if problems:
            errors += problems
            continue
        out[f["nodeId"]] = [{"nodeId": r["nodeId"], "name": r.get("name"),
                             "apiName": (r.get("sf") or {}).get("apiName") or r.get("api_name"),
                             "description": (r.get("description") or "")[:200], "status": r.get("status")}
                            for r in common.pull_rows(eng, f["pull"], pulls)]
    if errors:
        raise Failed(errors)
    return out


def box_choices(brief, box):
    """Every component a matcher may link to this box: its candidates, and the objects it is about with their fields
    and the automations that use them."""
    out = {c["nodeId"]: c for c in box["candidates"]}
    for oid in box.get("objects") or []:
        obj = brief["objects"][oid]
        out.setdefault(oid, {"nodeId": oid, "name": obj["name"], "apiName": obj["apiName"], "sfType": obj["sfType"]})
        for f in obj["fields"]:
            out.setdefault(f["nodeId"], {"nodeId": f["nodeId"], "name": f["name"], "apiName": f["apiName"],
                                         "sfType": "Field", "path": [obj["name"], "Fields", f["name"]],
                                         "object": obj["apiName"]})
        for a in obj["automations"]:
            out.setdefault(a["nodeId"], a)
    by_label = {o["name"]: o["apiName"] for o in (brief.get("objects") or {}).values()}
    for oid, obj in (brief.get("objects") or {}).items():
        for f in obj["fields"]:
            if f["nodeId"] in out and not out[f["nodeId"]].get("object"):
                out[f["nodeId"]] = dict(out[f["nodeId"]], object=obj["apiName"])
    for cand in list(out.values()):  # a field the search found, on an object the brief knows: its object by label
        path = cand.get("path") or []
        if norm(cand.get("sfType")) == "field" and not cand.get("object") and len(path) >= 3 and path[-2] == "Fields":
            if path[-3] in by_label:
                out[cand["nodeId"]] = dict(cand, object=by_label[path[-3]])
    return out


def briefs(eng):
    eng = Path(eng)
    limits = common.load_limits()
    linkable = common.load_link_types()
    autos = {k for k, v in linkable.items() if v["kind"] == "automation"}
    rnd = current_round(eng)
    final = rnd >= limits["matcher_rounds"]
    design = load_json(eng / "design.json", "the design file")
    plan, answers = search_answers(eng, rnd)
    using = where_used_by_object(eng, rnd, autos)
    fields = object_fields(eng, rnd)
    core = {o["nodeId"]: o for o in load_json(round_dir(eng, rnd) / "objects.json")["objects"]}
    known = {}
    for oid, obj in core.items():
        autos_of = using.get(oid, [])
        known[oid] = dict(obj, fields=fields.get(oid, []), automations=autos_of[:limits["automations_per_object"]],
                          automationsCut=max(0, len(autos_of) - limits["automations_per_object"]))
    for earlier in range(1, rnd):  # objects read in an earlier round
        for path in sorted((round_dir(eng, earlier) / "briefs").glob("*.json")):
            for oid, obj in (load_json(path).get("objects") or {}).items():
                known.setdefault(oid, obj)

    candidates, values, cut = {}, {}, {}
    for s in plan["searches"]:
        for node in (answers[s["id"]].get("nodes") or []):
            for bid in s["boxes"]:
                if norm(node.get("sfType")) == "custom value":
                    values.setdefault(bid, []).append({"name": node.get("name"), "path": node.get("path")})
                    continue
                if norm(node.get("sfType")) not in linkable:
                    continue
                cand = candidates.setdefault(bid, {}).setdefault(node["nodeId"], {
                    "nodeId": node["nodeId"], "name": node.get("name"), "apiName": node.get("apiName"),
                    "sfType": node.get("sfType"), "path": node.get("path"), "foundBy": []})
                cand["foundBy"].append(s["term"])
        if answers[s["id"]].get("hasMore"):
            for bid in s["boxes"]:
                cut.setdefault(bid, []).append(s["term"])
    if rnd == 1:
        in_play = load_json(eng / "coverage.json")["unlinked"]
    else:
        in_play = plan.get("boxes") or [b for s in plan["searches"] for b in s["boxes"]]
    in_play = list(dict.fromkeys(in_play))
    earlier_terms = {}
    if rnd > 1:  # a later round shows the earlier rounds' candidates too
        for earlier in range(1, rnd):
            for path in sorted((round_dir(eng, earlier) / "briefs").glob("*.json")):
                for box in load_json(path)["boxes"]:
                    if box["id"] in in_play:
                        earlier_terms.setdefault(box["id"], []).extend(box["searched"])
                        for cand in box["candidates"]:
                            candidates.setdefault(box["id"], {}).setdefault(cand["nodeId"], cand)
    by_level = {}
    for bid in in_play:
        by_level.setdefault(design["boxes"][bid]["level"], []).append(bid)
    levels = {l["levelNumber"]: l for l in design["levels"]}
    written = []
    for number, bids in sorted(by_level.items(), key=lambda kv: level_sort_key(kv[0])):
        level = levels[number]
        parent = design["boxes"].get(level["parentBox"]) if level["parentBox"] else None
        linked = [{"text": design["boxes"][b]["text"],
                   "links": [f"{l['name']} ({l['metadataType']})" for l in design["boxes"][b]["links"] if l["status"] == "ok"]}
                  for b in level["boxes"] if b not in bids and design["boxes"][b]["links"]]
        boxes, level_objects = [], {}
        for bid in bids:
            box = design["boxes"][bid]
            cands = sorted((candidates.get(bid) or {}).values(), key=lambda c: (-len(c["foundBy"]), c.get("name") or ""))
            about = {norm(r["name"]) for r in box["resources"] if r.get("type") == "Object" and r.get("name")}
            about |= {s["term"] for s in plan["searches"] if bid in s["boxes"]}
            if rnd > 1:
                about |= set(earlier_terms.get(bid, []))
            box_objects = [oid for oid, o in known.items() if norm(o["name"]) in about or norm(o["apiName"]) in about]
            for oid in box_objects:
                level_objects[oid] = known[oid]
            boxes.append({
                "id": bid, "text": box["text"], "resources": box["resources"], "attributes": box["attributes"],
                "notes": box["notes"], "inLines": box["inLines"], "outLines": box["outLines"],
                "searched": [s["term"] for s in plan["searches"] if bid in s["boxes"]],
                "searchesWithMoreHits": cut.get(bid, []),
                "candidates": cands[:limits["candidates_per_box"]],
                "candidatesCut": max(0, len(cands) - limits["candidates_per_box"]),
                "valueHits": (values.get(bid) or [])[:20],
                "objects": box_objects,
            })
        brief = {"round": rnd, "finalRound": final, "level": number, "levelTitle": level["title"],
                 "levelDescription": level["description"], "diagramType": level["subtype"],
                 "parentBox": parent["text"] if parent else None, "linkedOnLevel": linked,
                 "linkTypes": sorted({v["sf_type"] for v in linkable.values()}),
                 "noteMaxWords": limits["note_max_words"], "moreTermsPerBox": limits["more_terms_per_box"],
                 "objects": level_objects, "boxes": boxes,
                 "outputPath": f"match/round-{rnd}/found/{number}.json"}
        write_json(round_dir(eng, rnd) / "briefs" / f"{number}.json", brief)
        written.append(number)
    print(f"BRIEFS {len(written)} level(s) for round {rnd}{' (final round)' if final else ''}: " + ", ".join(written))
    print("Run one metadata-matcher agent per brief.")
    return 0


def found_errors(eng, file, rnd):
    """Error lines for one matcher answer against its round's brief; empty when it passes."""
    eng = Path(eng)
    limits = common.load_limits()
    linkable = common.load_link_types()
    found = load_json(file, "the matcher answer")
    errors = common.shape_errors(found, "matches.schema.json")
    if errors:
        return errors, found, 0
    brief_path = round_dir(eng, rnd) / "briefs" / f"{found['level']}.json"
    if not brief_path.exists():
        return [f"no brief for level {found['level']} in round {rnd}"], found, 0
    brief = load_json(brief_path)
    want = {b["id"]: b for b in brief["boxes"]}
    seen = {}
    for entry in found["boxes"]:
        bid = entry["id"]
        if bid not in want:
            errors.append(f"box {bid} is not in the brief")
            continue
        if bid in seen:
            errors.append(f"box {bid} appears twice")
        seen[bid] = entry
        cands = box_choices(brief, want[bid])
        if entry["decision"] == "links":
            if not entry.get("links"):
                errors.append(f"box {bid}: decision links needs at least one link")
            for link in entry.get("links") or []:
                cand = cands.get(link["nodeId"])
                if cand is None:
                    errors.append(f"box {bid}: {link['nodeId']} is not one of the box's candidates, or a field or automation of "
                                  f"an object the box is about; never invent an id")
                    continue
                if norm(cand["sfType"]) not in linkable:
                    errors.append(f"box {bid}: {cand['name']} is a {cand['sfType']}, which is not a linkable type")
        else:
            if entry.get("links"):
                errors.append(f"box {bid}: decision {entry['decision']} takes no links")
            if not (entry.get("reason") or "").strip():
                errors.append(f"box {bid}: decision {entry['decision']} needs a reason")
        if entry["decision"] == "nothing-found":
            if not (entry.get("gapNote") or "").strip():
                errors.append(f"box {bid}: nothing-found needs a gapNote for the sticky note")
            elif common.word_count(entry["gapNote"]) > limits["note_max_words"]:
                errors.append(f"box {bid}: gapNote has {common.word_count(entry['gapNote'])} words; at most {limits['note_max_words']}")
    for bid in want:
        if bid not in seen:
            errors.append(f"box {bid} ({want[bid]['text']}) has no entry")
    asks = found.get("moreTerms") or []
    if asks and brief["finalRound"]:
        errors.append("this is the final round: moreTerms must be empty; decide each box from the candidates shown")
    for ask in asks:
        if ask["box"] not in want:
            errors.append(f"moreTerms names box {ask['box']}, which is not in the brief")
        if len(ask["queries"]) > limits["more_terms_per_box"]:
            errors.append(f"moreTerms for {ask['box']} has {len(ask['queries'])} queries; at most {limits['more_terms_per_box']}")
    return errors, found, len(asks)


def check_found(eng, file):
    errors, found, asks = found_errors(eng, file, current_round(Path(eng)))
    if errors:
        raise Failed(errors)
    seen = {e["id"]: e for e in found["boxes"]}
    print(f"FOUND OK level {found['level']}: {len(seen)} box(es), {sum(len(e.get('links') or []) for e in seen.values())} link(s), "
          f"{asks} box(es) asking for more searches")
    return 0


def latest_found(eng):
    """Per box, the entry of the latest round that decided it, with its round and its brief's candidates."""
    eng = Path(eng)
    rnd = current_round(eng)
    out, errors = {}, []
    for r in range(1, rnd + 1):
        for path in sorted((round_dir(eng, r) / "found").glob("*.json")):
            problems, found, _ = found_errors(eng, path, r)
            if problems:
                errors += [f"round {r} {path.name}: {p}" for p in problems]
                continue
            brief = load_json(round_dir(eng, r) / "briefs" / f"{found['level']}.json")
            cands = {b["id"]: box_choices(brief, b) for b in brief["boxes"]}
            for entry in found["boxes"]:
                out[entry["id"]] = (r, entry, cands.get(entry["id"], {}))
    if errors:
        raise Failed(errors + ["run the level's metadata-matcher again with these lines as findings"])
    return out


def next_round(eng):
    eng = Path(eng)
    limits = common.load_limits()
    rnd = current_round(eng)
    briefs_dir, found_dir = round_dir(eng, rnd) / "briefs", round_dir(eng, rnd) / "found"
    missing = [p.stem for p in briefs_dir.glob("*.json") if not (found_dir / p.name).exists()]
    if missing:
        raise Failed([f"level {m} has a brief but no matcher answer in round {rnd}" for m in sorted(missing, key=level_sort_key)])
    asks, errors = [], []
    for path in sorted(found_dir.glob("*.json")):
        problems, found, _ = found_errors(eng, path, rnd)
        errors += [f"{path.name}: {p}" for p in problems]
        asks += found.get("moreTerms") or []
    if errors:
        raise Failed(errors + ["run the level's metadata-matcher again with these lines as findings"])
    if asks and rnd < limits["matcher_rounds"]:
        print(f"ANOTHER ROUND: {len(asks)} box(es) asked for more searches; set match.round to {rnd + 1}")
    else:
        print("DONE: no further round")
    return 0


def table(eng):
    eng = Path(eng)
    design = load_json(eng / "design.json", "the design file")
    cov = load_json(eng / "coverage.json", "the coverage file")
    latest = latest_found(eng)
    missing = [b for b in cov["unlinked"] if b not in latest]
    if missing:
        raise Failed([f"box {b} ({design['boxes'][b]['text']}) has no matcher answer" for b in missing])
    proposed = {}
    for bid in cov["unlinked"]:
        rnd, entry, cands = latest[bid]
        if entry["decision"] == "links" and not entry.get("links"):
            raise Failed([f"box {bid}: the round {rnd} answer has decision links but none"])
        links = []
        for link in entry.get("links") or []:
            cand = cands[link["nodeId"]]
            links.append({"nodeId": link["nodeId"], "name": cand.get("name"), "apiName": cand.get("apiName"),
                          "sfType": cand.get("sfType"), "path": cand.get("path"), "object": cand.get("object"),
                          "why": link["why"], "confidence": link["confidence"]})
        box = design["boxes"][bid]
        proposed[bid] = {"level": box["level"], "text": box["text"], "decision": entry["decision"], "links": links,
                         "reason": entry.get("reason", ""), "gapNote": entry.get("gapNote", "")}
    write_json(eng / "links" / "proposed.json", {"boxes": proposed})
    print("| Level | Step | Proposed link | Type | Why | Confidence |")
    print("|---|---|---|---|---|---|")
    for bid, p in sorted(proposed.items(), key=lambda kv: (level_sort_key(kv[1]["level"]), design["boxes"][kv[0]]["number"] or 0)):
        if p["decision"] == "links":
            for link in p["links"]:
                print(f"| {p['level']} | {p['text']} | {link['name']} | {link['sfType']} | {link['why']} | {link['confidence']} |")
        elif p["decision"] == "no-org-support":
            print(f"| {p['level']} | {p['text']} | (none: needs no org support) | | {p['reason']} | |")
        else:
            print(f"| {p['level']} | {p['text']} | (nothing found in the org) | | {p['reason']} | |")
    n_links = sum(len(p["links"]) for p in proposed.values())
    print(f"PROPOSED {n_links} link(s) on {sum(1 for p in proposed.values() if p['links'])} box(es); "
          f"{sum(1 for p in proposed.values() if p['decision'] == 'no-org-support')} needing no org support; "
          f"{sum(1 for p in proposed.values() if p['decision'] == 'nothing-found')} with nothing found")
    return 0


OPS = {
    "drop": ("box", "nodeId"),
    "drop-box": ("box",),
    "add": ("box", "nodeId", "apiName", "sfType", "name", "why"),
    "no-org-support": ("box", "reason"),
    "nothing-found": ("box", "gapNote"),
}


def confirm(eng):
    eng = Path(eng)
    limits = common.load_limits()
    linkable = common.load_link_types()
    proposed = load_json(eng / "links" / "proposed.json", "the proposal")["boxes"]
    boxes = {bid: {"decision": p["decision"], "links": [dict(l) for l in p["links"]], "reason": p["reason"],
                   "gapNote": p["gapNote"]} for bid, p in proposed.items()}
    corr_path = eng / "links" / "corrections.json"
    rounds = load_json(corr_path)["rounds"] if corr_path.exists() else []
    errors = []
    for number, rnd in enumerate(rounds, 1):
        for op in rnd.get("corrections") or []:
            kind = op.get("op")
            if kind not in OPS:
                errors.append(f"round {number}: unknown op {kind}; the ops are {', '.join(OPS)}")
                continue
            lacking = [k for k in OPS[kind] if not op.get(k)]
            if lacking:
                errors.append(f"round {number}: op {kind} needs {', '.join(lacking)}")
                continue
            box = boxes.get(op["box"])
            if box is None:
                errors.append(f"round {number}: box {op['box']} is not in the proposal")
                continue
            if kind == "drop":
                before = len(box["links"])
                box["links"] = [l for l in box["links"] if l["nodeId"] != op["nodeId"]]
                if len(box["links"]) == before:
                    errors.append(f"round {number}: box {op['box']} has no proposed link {op['nodeId']}")
                if not box["links"] and box["decision"] == "links":
                    box["decision"] = "dropped"
            elif kind == "drop-box":
                box.update({"decision": "dropped", "links": [], "reason": "", "gapNote": ""})
            elif kind == "add":
                if norm(op["sfType"]) not in linkable:
                    errors.append(f"round {number}: {op['name']} is a {op['sfType']}, which is not a linkable type")
                    continue
                if not re.match(r"^[0-9a-fA-F]{24}$", op["nodeId"]):
                    errors.append(f"round {number}: {op['nodeId']} is not a node id; copy it from search_metadata")
                    continue
                if all(l["nodeId"] != op["nodeId"] for l in box["links"]):
                    box["links"].append({"nodeId": op["nodeId"], "name": op["name"], "apiName": op["apiName"],
                                         "sfType": op["sfType"], "path": op.get("path"), "object": op.get("object"),
                                         "why": op["why"], "confidence": "analyst"})
                box.update({"decision": "links", "reason": "", "gapNote": ""})
            elif kind == "no-org-support":
                box.update({"decision": "no-org-support", "links": [], "reason": op["reason"], "gapNote": ""})
            elif kind == "nothing-found":
                if common.word_count(op["gapNote"]) > limits["note_max_words"]:
                    errors.append(f"round {number}: the note for {op['box']} has more than {limits['note_max_words']} words")
                    continue
                box.update({"decision": "nothing-found", "links": [], "gapNote": op["gapNote"],
                            "reason": op.get("reason") or op["gapNote"]})
    if errors:
        raise Failed(errors)
    kept = {bid: b for bid, b in boxes.items() if b["decision"] != "dropped"}
    counts = {"links": sum(len(b["links"]) for b in kept.values()),
              "boxesWithLinks": sum(1 for b in kept.values() if b["links"]),
              "noOrgSupport": sum(1 for b in kept.values() if b["decision"] == "no-org-support"),
              "nothingFound": sum(1 for b in kept.values() if b["decision"] == "nothing-found"),
              "dropped": sum(1 for b in boxes.values() if b["decision"] == "dropped")}
    write_json(eng / "links" / "approved.json", {"boxes": kept, "counts": counts})
    texts = load_json(eng / "design.json", "the design file")["boxes"]
    print("| Step | Link | Type | Why |")
    print("|---|---|---|---|")
    for bid, b in kept.items():
        text = texts[bid]["text"] if bid in texts else bid
        if b["links"]:
            for link in b["links"]:
                print(f"| {text} | {link['name']} | {link['sfType']} | {link['why']} |")
        elif b["decision"] == "no-org-support":
            print(f"| {text} | (none: needs no org support) | | {b['reason']} |")
        else:
            print(f"| {text} | (nothing found in the org) | | {b['gapNote']} |")
    for bid, b in boxes.items():
        if b["decision"] == "dropped":
            print(f"| {texts[bid]['text'] if bid in texts else bid} | (left unlinked: not compared) | | |")
    print(f"CONFIRMED {counts['links']} link(s) on {counts['boxesWithLinks']} box(es); {counts['noOrgSupport']} needing no "
          f"org support; {counts['nothingFound']} with nothing found; {counts['dropped']} left unlinked")
    return 0


def resolve(eng):
    eng = Path(eng)
    linkable = common.load_link_types()
    approved = load_json(eng / "links" / "approved.json", "the approved links")
    need = []
    for entry in approved["boxes"].values():
        for link in entry["links"]:
            if (linkable.get(norm(link["sfType"]), {}).get("qualify") == "object" and not link.get("object")
                    and link["nodeId"] not in need):
                need.append(link["nodeId"])
    write_json(eng / "links" / "resolve.json", {"nodeIds": need})
    have = [n for n in need if (eng / "links" / "resolve" / f"{n}.json").exists()]
    todo = [n for n in need if n not in have]
    if todo:
        print(f"RESOLVE {len(todo)}: call get_metadata_component with each nodeId and detail \"full\", saving the answer "
              f"as links/resolve/<nodeId>.json")
        for n in todo:
            print(f"  {n}")
    else:
        print(f"RESOLVED {len(have)} link(s) with their object's API name")
    return 0


def qualified_name(eng, link, linkable):
    if linkable.get(norm(link["sfType"]), {}).get("qualify") != "object":
        return link["apiName"]
    if link.get("object"):
        return f"{link['object']}.{link['apiName']}"
    path = Path(eng) / "links" / "resolve" / f"{link['nodeId']}.json"
    if not path.exists():
        raise Failed([f"{link['name']} needs its object's API name: run match.py resolve and save links/resolve/{link['nodeId']}.json"])
    doc = load_json(path)
    obj = common.owner_api(doc)
    api = (doc.get("sf") or {}).get("apiName") or link["apiName"]
    if not obj:
        raise Failed([f"links/resolve/{link['nodeId']}.json has no canonical owner API name (sf.fullApiName or identity/parentPath)"])
    return f"{obj}.{api}"


def plan(eng):
    eng = Path(eng)
    linkable = common.load_link_types()
    design = load_json(eng / "design.json", "the design file")
    approved = load_json(eng / "links" / "approved.json", "the approved links")
    not_saved = load_json(eng / "links" / "not-saved.json")["links"] if (eng / "links" / "not-saved.json").exists() else []
    skip = {(n["box"], n["nodeId"]) for n in not_saved}
    levels = {l["levelNumber"]: l for l in design["levels"]}
    per_level = {}
    for bid, entry in approved["boxes"].items():
        box = design["boxes"][bid]
        have = {l["nodeId"] for l in box["links"] if l["source"] == "diagram"}
        for link in entry["links"]:
            if link["nodeId"] in have or (bid, link["nodeId"]) in skip:
                continue
            change = {"op": "add", "kind": "attachment", "activity": box["key"], "type": "metadata",
                      "apiName": qualified_name(eng, link, linkable), "metadataType": link["sfType"],
                      "refModelId": design["refModelId"], "description": link["why"][:2000]}
            per_level.setdefault(box["level"], []).append((change, {"box": bid, "nodeId": link["nodeId"]}))
    out_dir = eng / "links" / "plan"
    for old in out_dir.glob("*.json") if out_dir.exists() else []:
        if not old.name.endswith((".saved.json", ".dryrun.json", ".failed.json")):
            old.unlink()
    for number, pairs in sorted(per_level.items(), key=lambda kv: level_sort_key(kv[0])):
        level = levels[number]
        if (out_dir / f"{number}.saved.json").exists():
            saved_result = load_json(out_dir / f"{number}.saved.json")
            if not common.write_complete(saved_result):
                raise Failed([f"level {number}: saved write evidence is incomplete or pending; reconcile the genuine result before replay"])
            print(f"SAVED BEFORE level {number}: its links were written; read it again and rebuild the design")
            continue
        write_json(out_dir / f"{number}.json", {"diagramId": level["diagramId"], "baseVersion": level["version"],
                                                "changes": [c for c, _ in pairs], "refs": [r for _, r in pairs]})
        print(f"PLANNED level {number}: {len(pairs)} link(s); run manage_batches.py next on the plan until done")
    if not per_level:
        print("NOTHING TO WRITE: every approved link is on its box already, or was refused")
    return 0


def drop_failed(eng, number, file, batch=1):
    eng = Path(eng)
    path = eng / "links" / "plan" / f"{number}.json"
    plan_doc = load_json(path, "the level's link plan")
    answer = load_json(file, "the dry-run answer")
    bad = {}
    for issue in answer.get("issues") or []:
        if issue.get("severity") != "error":
            continue
        m = re.match(r"^changes\[(\d+)\]", issue.get("path") or "")
        if not m:
            raise Failed([f"a dry-run error is not about one change ({issue.get('code')}: {issue.get('message')}); "
                          f"it cannot be dropped, so the level is blocked"])
        bad[int(m.group(1))] = f"{issue.get('code')}: {issue.get('message')}"
    if not bad:
        print("NO ERRORS in the dry run")
        return 0
    ns_path = eng / "links" / "not-saved.json"
    not_saved = load_json(ns_path)["links"] if ns_path.exists() else []
    batches = plan_doc.get("batches") or [plan_doc["changes"]]
    if not 1 <= batch <= len(batches):
        raise Failed(["batch number is outside the link plan"])
    selected = batches[batch - 1]
    offset = sum(len(items) for items in batches[:batch - 1])
    if any(index >= len(selected) for index in bad):
        raise Failed(["dry-run change index is outside the selected batch"])
    keep, refs = [], []
    for i, (change, ref) in enumerate(zip(selected, plan_doc["refs"][offset:offset + len(selected)])):
        if i in bad:
            not_saved.append({"box": ref["box"], "nodeId": ref["nodeId"], "apiName": change["apiName"],
                              "reason": bad[i]})
        else:
            keep.append(change)
            refs.append(ref)
    plan_doc["changes"] = keep
    plan_doc["refs"] = plan_doc["refs"][:offset] + refs + plan_doc["refs"][offset + len(selected):]
    if "batches" in plan_doc:
        batches[batch - 1] = keep
        plan_doc["batches"] = [items for items in batches if items]
        plan_doc["changes"] = plan_doc["batches"][0] if plan_doc["batches"] else []
    write_json(path, plan_doc)
    write_json(ns_path, {"links": not_saved})
    print(f"DROPPED {len(bad)} change(s) the dry run refused; {len(keep)} left for level {number}")
    for i, why in sorted(bad.items()):
        print(f"  change {i}: {why}")
    return 0


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ("terms", "objects", "briefs", "next-round", "table", "confirm", "resolve", "plan"):
        return {"terms": terms, "objects": objects, "briefs": briefs, "next-round": next_round, "table": table,
                "confirm": confirm, "resolve": resolve, "plan": plan}[args[0]](args[1])
    if len(args) == 3 and args[0] == "check":
        return check_found(args[1], args[2])
    if len(args) == 4 and args[0] == "drop-failed":
        return drop_failed(args[1], args[2], args[3])
    if len(args) == 6 and args[0] == "drop-failed" and args[4] == "--batch":
        return drop_failed(args[1], args[2], args[3], int(args[5]))
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    common.run(main)
