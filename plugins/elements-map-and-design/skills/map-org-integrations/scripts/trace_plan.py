#!/usr/bin/env python3
"""Plan and join the trace of the confirmed systems' automations, one round at a time.

Usage:
  python3 trace_plan.py terms ENG         # the code searches to run this round
  python3 trace_plan.py hits ENG          # join the searches; the gateways to ask where-used of
  python3 trace_plan.py automations ENG   # join where-used; the automations to read and explain
  python3 trace_plan.py pack ENG          # one evidence pack per system for the integration-tracer

The round is trace.round in ENG/execution-state.json. It traces the confirmed systems of systems.json that no
round has packed yet (tracedRound null). Every list answer is recorded in ENG/evidence/pulls.json and its parts
saved as ENG/evidence/<pull>-<index>.ndjson, as for the inventory.

terms        Search terms per system: its searchTerms (known-systems.csv, the classifier or the architect), else its
             name and aliases; its package namespaces; callout:<API name> of each named credential in its evidence;
             the API names of its platform events. A term that holds another of the system's terms is left out (the search
             matches substrings, case ignored). Terms shorter than min_term_length, past max_terms_per_system,
             or past max_searches for the run (data/limits.csv) are recorded as gaps, not searched. A term two
             systems share is searched once. Writes trace/round-N/searches.json; pull names search-<term>.
hits         Checks every search pull and keeps, by data/hit-types.csv, automations (test classes skipped), key
             fields and gateways. A system's gateways are its evidence items of a gateway type and the Apex classes,
             platform events and custom metadata its searches hit. Writes trace/round-N/hits.json and
             trace/round-N/batches.json "whereUsed" (nodeId lists of at most dependency_batch); pull names
             gateways-rN-<k>.
automations  Checks the gateway pulls; adds every automation that uses a system's gateway (one step out) to that
             system. Writes trace/round-N/automations.json and batches.json "using" (pulls using-rN-<k>),
             "summary" (explain_metadata_components summary, explain_batch each, at most max_explained in the run)
             and "chain" (the middleware systems' automations, one batch).
pack         Checks the using pulls and that every explain batch's answer is saved as
             trace/round-N/explain-summary-<k>.json or explain-chain-<k>.json (failed items are gaps, never an
             error). Writes trace/packs/<system id>.json: the system and its evidence, every automation with its
             description, summary, chain, what found it, the objects it reads, writes and runs on, the fields it
             reads and writes, what it calls and publishes; the key fields; the gaps. Marks those systems traced
             in this round in systems.json. Ends PACKED.

Exit 0 with READY or PACKED. Exit 1 REFUSED: a pull or answer is missing or incomplete (ERROR lines).
Exit 2: setup problem.
"""

import sys
from collections import OrderedDict
from pathlib import Path

import common

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from metadata_narrative import narrative_text
from common import SetupError, norm

GATEWAY_EVIDENCE = ("Named Credential", "External Credential", "External Service", "Platform Event")  # proof whose users reach the system
OBJECT_TYPES = ("standard object", "custom object", "external object", "big object")  # dependency rows kept as objects
FIELD_LIST_LIMIT = 12   # fields listed per object in a pack: enough to name the keys, short enough to read


def round_of(eng):
    state = common.load_state(eng)
    value = (state.get("trace") or {}).get("round")
    if not isinstance(value, int) or value < 1:
        raise SetupError("execution-state.json trace.round must be 1 or more")
    return value


def round_dir(eng, n):
    return Path(eng) / "trace" / f"round-{n}"


def load_systems(eng):
    return common.load_json(Path(eng) / "systems.json", "systems.json")


def to_trace(systems):
    return [s for s in systems["systems"] if s.get("status") == "confirmed" and s.get("tracedRound") is None]


def refuse(errors):
    for line in errors:
        print(f"ERROR {line}")
    print("REFUSED")
    return 1


def batches_of(ids, size):
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def write_batches(eng, n, **lists):
    path = round_dir(eng, n) / "batches.json"
    data = common.load_json(path) if path.exists() else {}
    data.update(lists)
    common.write_json(path, data)


# ---------------------------------------------------------------- terms

def terms(eng):
    eng = Path(eng)
    n = round_of(eng)
    limits = common.load_limits()
    systems = load_systems(eng)
    vendors = {v["vendor"]: v for v in common.load_known_systems()}
    pulls = common.load_pulls(eng)
    searched_before = {name for name in pulls if name.startswith("search-")}
    budget = limits["max_searches"] - len(searched_before)
    searches, plan, gaps = OrderedDict(), [], []
    for s in to_trace(systems):
        wanted = list(s.get("searchTerms") or [])
        if not wanted:
            wanted = [s["name"]] + (vendors[s["name"]]["aliases"] if s["name"] in vendors else [])
        for e in s.get("evidence", []):
            if e["type"] == "Managed Package" and e.get("namespace"):
                wanted.append(e["namespace"])
            if e["type"] == "Named Credential" and e.get("apiName"):
                wanted.append(f"callout:{e['apiName']}")
            if e["type"] == "Platform Event" and e.get("apiName"):
                wanted.append(e["apiName"])
        mine, seen = [], set()
        broad = [w.strip() for w in wanted if limits["min_term_length"] <= len(w.strip()) <= 512]
        for term in wanted:
            term = term.strip()
            if not 2 <= len(term) <= 512:
                gaps.append({"about": s["id"], "note": f"{term!r} was not searched for {s['name']}: query requires 2-512 trimmed characters"})
                continue
            if norm(term) in seen:
                continue
            seen.add(norm(term))
            # a term that holds another of the system's terms finds nothing that term does not (the search is a substring match)
            if any(norm(b) != norm(term) and norm(b) in norm(term) for b in broad):
                continue
            if len(term) < limits["min_term_length"]:
                gaps.append({"about": s["id"], "note": f"'{term}' was not searched for {s['name']}: shorter than {limits['min_term_length']} characters"})
                continue
            if len(mine) >= limits["max_terms_per_system"]:
                gaps.append({"about": s["id"], "note": f"'{term}' was not searched for {s['name']}: past {limits['max_terms_per_system']} terms per system"})
                continue
            key = norm(term)
            if key not in searches:
                if budget <= 0:
                    gaps.append({"about": s["id"], "note": f"'{term}' was not searched for {s['name']}: past {limits['max_searches']} searches per run"})
                    continue
                budget -= 1
                pull = "search-" + common.slug(term, 60)
                used = {v["pull"] for v in searches.values()}
                k = 2
                while pull in used:
                    pull = f"search-{common.slug(term, 56)}-{k}"
                    k += 1
                searches[key] = {"term": term, "pull": pull, "systems": []}
            searches[key]["systems"].append(s["id"])
            mine.append(term)
        gateways = [{"nodeId": e["nodeId"], "name": e.get("apiName") or e["name"], "type": e["type"]}
                    for e in s.get("evidence", []) if e["type"] in GATEWAY_EVIDENCE and e.get("nodeId")]
        plan.append({"id": s["id"], "name": s["name"], "terms": mine, "gateways": gateways})
    if not plan:
        print("NOTHING TO TRACE: every confirmed system has been traced")
    common.write_json(round_dir(eng, n) / "searches.json", {"round": n, "searches": list(searches.values()),
                                                         "systems": plan, "gaps": gaps})
    for item in searches.values():
        print(f"SEARCH {item['pull']} {item['term']!r}")
    for gap in gaps:
        print(f"GAP {gap['note']}")
    print(f"{len(searches)} search(es) for {len(plan)} system(s) in round {n}, written to trace/round-{n}/searches.json")
    print("READY")
    return 0


# ---------------------------------------------------------------- hits

def hits(eng):
    eng = Path(eng)
    n = round_of(eng)
    limits = common.load_limits()
    hit_types = common.load_hit_types()
    plan = common.load_json(round_dir(eng, n) / "searches.json", f"trace/round-{n}/searches.json (run terms first)")
    pulls = common.load_pulls(eng)
    errors = []
    for item in plan["searches"]:
        errors += common.verify_pull(eng, item["pull"], pulls)
    if errors:
        return refuse(errors)
    per = {s["id"]: {"id": s["id"], "name": s["name"], "automations": OrderedDict(), "keyFields": [], "gateways": list(s["gateways"])}
           for s in plan["systems"]}
    for item in plan["searches"]:
        for row in common.pull_rows(eng, item["pull"], pulls):
            spec = hit_types.get(norm(row.get("type")))
            if spec is None or not row.get("nodeId"):
                continue
            if spec["skip"] and spec["skip"].search(row.get("name") or ""):
                continue
            for sid in item["systems"]:
                target = per[sid]
                if spec["role"] == "automation":
                    auto = target["automations"].setdefault(row["nodeId"], {"nodeId": row["nodeId"], "name": row.get("name"),
                                                                            "sfType": row.get("type"), "foundBy": []})
                    auto["foundBy"].append(f"search '{item['term']}'")
                    if norm(row.get("type")) == "apex class" and all(g["nodeId"] != row["nodeId"] for g in target["gateways"]):
                        target["gateways"].append({"nodeId": row["nodeId"], "name": row.get("name"), "type": row.get("type")})
                elif spec["role"] == "key-field":
                    if all(f["nodeId"] != row["nodeId"] for f in target["keyFields"]):
                        target["keyFields"].append({"nodeId": row["nodeId"], "name": row.get("name"), "term": item["term"]})
                elif all(g["nodeId"] != row["nodeId"] for g in target["gateways"]):
                    target["gateways"].append({"nodeId": row["nodeId"], "name": row.get("name"), "type": row.get("type")})
    systems = [dict(s, automations=list(s["automations"].values())) for s in per.values()]
    common.write_json(round_dir(eng, n) / "hits.json", {"round": n, "systems": systems})
    ids = list(dict.fromkeys(g["nodeId"] for s in systems for g in s["gateways"]))
    batches = batches_of(ids, limits["dependency_batch"])
    write_batches(eng, n, whereUsed=[{"pull": f"gateways-r{n}-{k}", "nodeIds": b} for k, b in enumerate(batches, start=1)])
    for s in systems:
        print(f"{s['name']}: {len(s['automations'])} automation(s), {len(s['keyFields'])} key field(s), {len(s['gateways'])} gateway(s)")
    print(f"WHERE-USED {len(batches)} batch(es) of gateways, in trace/round-{n}/batches.json")
    print("READY")
    return 0


# ---------------------------------------------------------------- automations

def automations(eng):
    eng = Path(eng)
    n = round_of(eng)
    limits = common.load_limits()
    hit_types = common.load_hit_types()
    found = common.load_json(round_dir(eng, n) / "hits.json", f"trace/round-{n}/hits.json (run hits first)")
    batches = common.load_json(round_dir(eng, n) / "batches.json")
    pulls = common.load_pulls(eng)
    errors = []
    for b in batches.get("whereUsed", []):
        errors += common.verify_pull(eng, b["pull"], pulls)
    if errors:
        return refuse(errors)
    users = {}
    for b in batches.get("whereUsed", []):
        for row in common.pull_rows(eng, b["pull"], pulls):
            node, related = row.get("node") or {}, row.get("related") or {}
            spec = hit_types.get(norm(related.get("type")))
            if not spec or spec["role"] != "automation" or not related.get("nodeId"):
                continue
            if spec["skip"] and spec["skip"].search(related.get("name") or ""):
                continue
            users.setdefault(node.get("nodeId"), []).append((related, node))
    systems_doc = load_systems(eng)
    middleware = {s["id"] for s in systems_doc["systems"] if s.get("middleware")}
    every = OrderedDict()
    for s in found["systems"]:
        autos = OrderedDict((a["nodeId"], a) for a in s["automations"])
        for gateway in s["gateways"]:
            for related, node in users.get(gateway["nodeId"], []):
                auto = autos.setdefault(related["nodeId"], {"nodeId": related["nodeId"], "name": related.get("name"),
                                                            "sfType": related.get("type"), "foundBy": []})
                auto["foundBy"].append(f"uses {node.get('type')} {node.get('name')}")
        s["automations"] = list(autos.values())
        for a in s["automations"]:
            every.setdefault(a["nodeId"], a)
    common.write_json(round_dir(eng, n) / "automations.json", {"round": n, "systems": found["systems"]})
    ids = list(every)
    explained_before = 0
    for k in range(1, n):
        earlier = round_dir(eng, k) / "batches.json"
        if earlier.exists():
            explained_before += sum(len(b["nodeIds"]) for b in common.load_json(earlier).get("summary", []))
    allowed = max(0, limits["max_explained"] - explained_before)
    summary_ids, left_out = ids[:allowed], ids[allowed:]
    chain_ids = list(dict.fromkeys(a["nodeId"] for s in found["systems"] if s["id"] in middleware for a in s["automations"]
                                   if norm(a["sfType"]) in ("flow", "apex trigger", "apex class")))[:limits["explain_batch"]]
    write_batches(eng, n,
                  using=[{"pull": f"using-r{n}-{k}", "nodeIds": b} for k, b in enumerate(batches_of(ids, limits["dependency_batch"]), start=1)],
                  summary=[{"file": f"explain-summary-{k}.json", "nodeIds": b} for k, b in enumerate(batches_of(summary_ids, limits["explain_batch"]), start=1)],
                  chain=[{"file": "explain-chain-1.json", "nodeIds": chain_ids}] if chain_ids else [],
                  notExplained=left_out)
    for s in found["systems"]:
        print(f"{s['name']}: {len(s['automations'])} automation(s)")
    if left_out:
        print(f"GAP {len(left_out)} automation(s) past max_explained are not explained")
    print(f"{len(ids)} automation(s) to read; batches in trace/round-{n}/batches.json")
    print("READY")
    return 0


# ---------------------------------------------------------------- pack

def explain_results(eng, n, batches):
    """nodeId -> {aspect: narrative}; and the gaps of failed or missing explanations."""
    out, gaps, errors = {}, [], []
    for aspect in ("summary", "chain"):
        for b in batches.get(aspect, []):
            path = round_dir(eng, n) / b["file"]
            if not path.exists():
                errors.append(f"trace/round-{n}/{b['file']} is missing: save the whole explain_metadata_components answer ({aspect}) for its batch, failed items and all")
                continue
            answer = common.load_json(path)
            if isinstance(answer, dict) and answer.get("_truncated"):
                errors.append(f"trace/round-{n}/{b['file']} is a trimmed answer (_truncated): call again with the same arguments "
                              f"and skip set to _truncated.nextSkip until an answer has no _truncated, and save the items of "
                              f"every answer joined in this file, without _truncated")
                continue
            items = answer.get("items") if isinstance(answer.get("items"), list) else [answer]
            got = {}
            for item in items:
                if isinstance(item, dict) and item.get("nodeId"):
                    got[item["nodeId"]] = item
            for node_id in b["nodeIds"]:
                item = got.get(node_id)
                if item and item.get("status") == "complete" and item.get("narrative"):
                    out.setdefault(node_id, {})[aspect] = " ".join(narrative_text(item["narrative"]).split())[:1500]
                else:
                    reason = (item or {}).get("error") or (item or {}).get("status") or "no answer"
                    gaps.append((node_id, aspect, reason))
    return out, gaps, errors


def object_kind(api_name, sf_type=""):
    if norm(sf_type) == "external object" or api_name.endswith("__x"):
        return "external"
    if norm(sf_type) == "custom object" or api_name.endswith("__c"):
        return "custom"
    return "standard"


def detail_of(rows):
    """What one automation touches, from its get_dependencies using rows."""
    objects, fields, calls, publishes, config = OrderedDict(), OrderedDict(), [], [], []
    for row in rows:
        related = row.get("related") or {}
        kind, api = norm(related.get("type")), related.get("apiName") or related.get("name") or ""
        if not api:
            continue
        read, write = bool(row.get("read")), bool(row.get("write"))
        trigger = row.get("triggerType")
        if kind in OBJECT_TYPES:
            if api.endswith("__mdt"):
                config.append(api)
                continue
            o = objects.setdefault(api, {"apiName": api, "name": related.get("name") or api,
                                         "kind": object_kind(api, related.get("type")), "read": False, "write": False})
            o["read"] |= read
            o["write"] |= write
            if trigger:
                o["trigger"] = " ".join(x for x in (trigger, row.get("triggerAction")) if x)
        elif kind == "field" and related.get("object"):
            obj = related["object"]
            if obj.endswith("__mdt"):
                continue
            o = objects.setdefault(obj, {"apiName": obj, "name": obj, "kind": object_kind(obj), "read": False, "write": False})
            o["read"] |= read
            o["write"] |= write
            f = fields.setdefault(obj, {"read": [], "write": []})
            for flag, bucket in ((read, "read"), (write, "write")):
                if flag and api not in f[bucket]:
                    f[bucket].append(api)
        elif kind == "platform event":
            (publishes if write else calls).append({"name": related.get("name"), "apiName": api, "type": related.get("type"),
                                                    "how": "publishes" if write else ("runs on" if trigger else "uses")})
        elif kind == "custom metadata":
            config.append(api)
        elif kind in ("flow", "apex class", "apex trigger", "external service", "named credential", "external credential",
                      "omniscript", "omni integration procedure"):
            calls.append({"name": related.get("name"), "apiName": api, "type": related.get("type")})
    for f in fields.values():
        for bucket in ("read", "write"):
            if len(f[bucket]) > FIELD_LIST_LIMIT:
                f[bucket] = f[bucket][:FIELD_LIST_LIMIT] + [f"+{len(f[bucket]) - FIELD_LIST_LIMIT} more"]
    return list(objects.values()), fields, calls, publishes, list(dict.fromkeys(config))


def pack(eng):
    eng = Path(eng)
    n = round_of(eng)
    hit_types = common.load_hit_types()
    found = common.load_json(round_dir(eng, n) / "automations.json", f"trace/round-{n}/automations.json (run automations first)")
    batches = common.load_json(round_dir(eng, n) / "batches.json")
    pulls = common.load_pulls(eng)
    errors = []
    for b in batches.get("using", []):
        errors += common.verify_pull(eng, b["pull"], pulls)
    explained, explain_gaps, explain_errors = explain_results(eng, n, batches)
    errors += explain_errors
    if errors:
        return refuse(errors)
    rows_of, node_of = {}, {}
    for b in batches.get("using", []):
        for row in common.pull_rows(eng, b["pull"], pulls):
            node = row.get("node") or {}
            rows_of.setdefault(node.get("nodeId"), []).append(row)
            node_of.setdefault(node.get("nodeId"), node)
    systems_doc = load_systems(eng)
    by_id = {s["id"]: s for s in systems_doc["systems"]}
    state = common.load_state(eng)
    hub = (state.get("slots") or {}).get("hub_name") or "Salesforce org"
    gateway_names = {}
    for k in range(1, n + 1):
        earlier = round_dir(eng, k) / "hits.json"
        if earlier.exists():
            for s in common.load_json(earlier)["systems"]:
                gateway_names.setdefault(s["id"], [])
                for g in s["gateways"]:
                    label = f"{g.get('type')} {g.get('name')}"
                    if label not in gateway_names[s["id"]]:
                        gateway_names[s["id"]].append(label)
    others = [{"id": s["id"], "name": s["name"], "kind": s["kind"], "middleware": bool(s.get("middleware")),
               "gateways": gateway_names.get(s["id"], [])} for s in systems_doc["systems"]]
    searches = common.load_json(round_dir(eng, n) / "searches.json")
    search_gaps = searches.get("gaps", []) + [{"about": system["id"], "note": gap}
            for system in systems_doc["systems"] for gap in common.native_gaps(pulls)]
    not_explained = set(batches.get("notExplained", []))
    gap_lines = {}
    for node_id, aspect, reason in explain_gaps:
        gap_lines.setdefault(node_id, []).append(f"no {aspect} explanation ({reason})")
    packed = 0
    for s in found["systems"]:
        system = by_id.get(s["id"])
        if system is None:
            continue
        autos = []
        for a in s["automations"]:
            node = node_of.get(a["nodeId"], {})
            objects, fields, calls, publishes, config = detail_of(rows_of.get(a["nodeId"], []))
            spec = hit_types.get(norm(a.get("sfType"))) or {}
            attrs = node.get("attributes") or {}
            entry = {"nodeId": a["nodeId"], "name": a.get("name") or node.get("name"), "apiName": node.get("apiName") or "",
                     "sfType": a.get("sfType"), "type": spec.get("automation_type") or "other",
                     "active": node.get("active"), "description": " ".join((attrs.get("description") or "").split())[:1000],
                     "foundBy": a.get("foundBy", [])}
            entry.update({k: v for k, v in (explained.get(a["nodeId"]) or {}).items()})
            if a["nodeId"] in not_explained:
                gap_lines.setdefault(a["nodeId"], []).append("not explained: past max_explained")
            if gap_lines.get(a["nodeId"]):
                entry["gaps"] = gap_lines[a["nodeId"]]
            if a["nodeId"] not in rows_of:
                entry.setdefault("gaps", []).append("no dependency rows: what it reads and writes is unknown")
            entry.update(objects=objects, fields=fields, calls=calls, publishes=publishes, config=config)
            autos.append(entry)
        evidence = [{k: e[k] for k in ("type", "name", "apiName", "namespace", "domain", "url", "description", "namedCredential") if e.get(k)}
                    for e in system.get("evidence", [])]
        doc = {"round": n, "hub": {"id": "org", "name": hub},
               "system": {"id": system["id"], "name": system["name"], "kind": system["kind"],
                          "middleware": bool(system.get("middleware")), "origin": system.get("origin"),
                          "via": system.get("via"), "description": system.get("description", ""), "evidence": evidence,
                          "namedBy": system.get("namedBy", []), "gateways": gateway_names.get(system["id"], [])},
               "otherSystems": [o for o in others if o["id"] != system["id"]],
               "automations": autos, "keyFields": s.get("keyFields", []),
               "gaps": [g for g in search_gaps if g.get("about") == system["id"]]}
        common.write_json(eng / "trace" / "packs" / f"{system['id']}.json", doc)
        system["tracedRound"] = n
        packed += 1
        print(f"{system['name']}: {len(autos)} automation(s) packed")
    common.write_json(eng / "systems.json", systems_doc)
    if explain_gaps:
        print(f"GAP {len(explain_gaps)} explanation(s) failed or missing; the tracer works from names, descriptions and dependencies")
    print(f"PACKED {packed} system(s) in round {n}")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    commands = {"terms": terms, "hits": hits, "automations": automations, "pack": pack}
    if len(argv) != 2 or argv[0] not in commands:
        print(__doc__.strip())
        return 2
    try:
        return commands[argv[0]](argv[1])
    except SetupError as exc:
        print(f"SETUP {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
