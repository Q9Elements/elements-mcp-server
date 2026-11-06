#!/usr/bin/env python3
"""Resolve the org's integration inventory into the outside systems it proves.

Usage:
  python3 resolve_systems.py propose ENG    # match inventory.json against the data files
  python3 resolve_systems.py build ENG [--check]   # add the classifier's calls; write systems.json
  python3 resolve_systems.py show ENG       # the system list for the architect, in their words
  python3 resolve_systems.py confirm ENG    # apply systems/corrections.json; every system confirmed

propose  Matches every inventory item and managed package, in this order: (1) data/not-external.csv rows on the
         item's domain, API name or name (Salesforce's own apps and domains, generated credentials); (2)
         data/known-systems.csv on domain, package namespace, and name or alias in the item's name or API name:
         one vendor matched is a match, two or more go to the classifier with both as candidates; (3)
         not-external namespace rows (in-org packages); (4) anything else goes to the classifier. Supporting items
         (permission sets) join a system only by its namespace or name, never on their own; package components
         (applications) join a system by namespace, for the card's links. Writes systems/proposal.json and, for the
         system-classifier agent, systems/unmatched.json. Ends CLASSIFY or NOTHING TO CLASSIFY.
build    Checks systems/classified.json (when there was anything to classify) against
         schemas/classified.schema.json and the unmatched items: every item classified once. Merges a system the
         classifier names that is already a known or matched vendor. Writes systems/proposed.json and
         systems.json. Ends PROPOSED; ERROR lines go back to the agent (exit 1). With --check it writes nothing
         and ends CLASSIFIED OK: the classifier's own check.
show     Prints the systems, how each was found and its evidence, then the calls the classifier made and the
         items set aside as not outside systems, counted by reason.
confirm  Rebuilds systems.json from systems/proposed.json and every round of systems/corrections.json, in order:
         {"rounds": [{"date", "by", "corrections": [op, ...], "applied"}]}, ops:
           {"op": "drop", "system": S, "reason": R}          {"op": "rename", "system": S, "to": NAME}
           {"op": "merge", "into": S, "systems": [S, ...]}   {"op": "kind", "system": S, "kind": K, "middleware": B}
           {"op": "add", "name": NAME, "kind": K, "middleware": B, "searchTerms": [...], "note": TEXT}
         S is a system id or name. Every system left is confirmed. Ends CONFIRMED; an op that does not apply, or a
         result with no system left, is an ERROR line (exit 1) and nothing is written.

Exit 2: setup problem.
"""

import sys
from collections import Counter, OrderedDict
from datetime import date
from pathlib import Path

import common
from common import SetupError, norm


# ---------------------------------------------------------------- matching

def vendor_candidates(item, vendors):
    """Vendors the item points at, each with how: domain, namespace, name."""
    found = OrderedDict()
    domain = item.get("domain") or ""
    for v in vendors:
        if domain and any(common.domain_matches(domain, d) for d in v["domains"]):
            found.setdefault(v["vendor"], set()).add("domain")
        if item.get("namespace") and item["namespace"].casefold() in v["namespaces"]:
            found.setdefault(v["vendor"], set()).add("namespace")
        for phrase in [v["vendor"]] + v["aliases"]:
            if common.phrase_in(phrase, item.get("name", "")) or common.phrase_in(phrase, item.get("apiName", "")):
                found.setdefault(v["vendor"], set()).add("name")
                break
    return found


def noise_reason(item, rows, kinds):
    for row in rows:
        if row["match_on"] not in kinds:
            continue
        if row["match_on"] == "domain" and item.get("domain") and row["regex"].search(item["domain"]):
            return row["reason"]
        if row["match_on"] == "api_name" and item.get("type") == "Named Credential" and row["regex"].search(item.get("apiName", "")):
            return row["reason"]
        if row["match_on"] == "name" and (row["regex"].search(item.get("name", "")) or row["regex"].search(item.get("apiName", ""))):
            return row["reason"]
        if row["match_on"] == "namespace" and item.get("namespace") and row["regex"].search(item["namespace"]):
            return row["reason"]
    return None


def evidence_entry(item, matched_by):
    entry = {k: item[k] for k in ("nodeId", "type", "role", "name", "apiName", "namespace", "domain", "url",
                                  "description", "namedCredential") if item.get(k)}
    entry["matchedBy"] = matched_by
    return entry


def propose(eng):
    eng = Path(eng)
    inventory = common.load_json(eng / "inventory.json", "inventory.json (run inventory.py build first)")
    vendors = common.load_known_systems()
    by_vendor = {v["vendor"]: v for v in vendors}
    noise_rows = common.load_not_external()
    items = [dict(i) for i in inventory.get("items", [])]
    items += [{"nodeId": p.get("nodeId"), "type": "Managed Package", "role": "proof", "name": p["namespace"],
               "apiName": p["namespace"], "namespace": p["namespace"], "description": p.get("displayName") or ""}
              for p in inventory.get("packages", [])]
    matched, unmatched, noise, support, components = OrderedDict(), [], [], [], []
    for item in items:
        if item["role"] == "support":
            support.append(item)
            continue
        if item["role"] == "package-component":
            components.append(item)
            continue
        reason = noise_reason(item, noise_rows, ("domain", "api_name", "name"))
        if reason:
            noise.append(dict(evidence_entry(item, "not-external"), reason=reason))
            continue
        candidates = vendor_candidates(item, vendors)
        if len(candidates) == 1:
            vendor, how = next(iter(candidates.items()))
            matched.setdefault(vendor, []).append(evidence_entry(item, "+".join(sorted(how))))
            continue
        if not candidates:
            reason = noise_reason(item, noise_rows, ("namespace",))
            if reason:
                noise.append(dict(evidence_entry(item, "not-external"), reason=reason))
                continue
        unmatched.append(dict(evidence_entry(item, "none"), candidates=list(candidates)))
    # supporting items and package components join systems already proven, never on their own
    proven_ns = {}
    for vendor, evidence in matched.items():
        for e in evidence:
            # an in-org package's namespace (DevOps Center's credentials) proves no vendor's other components
            if e.get("namespace") and not noise_reason({"namespace": e["namespace"]}, noise_rows, ("namespace",)):
                proven_ns.setdefault(e["namespace"].casefold(), vendor)
        for ns in by_vendor[vendor]["namespaces"]:
            proven_ns.setdefault(ns, vendor)
    ignored = 0
    for item in support + components:
        vendor = proven_ns.get((item.get("namespace") or "").casefold())
        if vendor is None and item["role"] == "support":
            names = [v for v in matched if any(common.phrase_in(p, item.get("name", "")) or common.phrase_in(p, item.get("apiName", ""))
                                              for p in [v] + by_vendor[v]["aliases"])]
            vendor = names[0] if len(names) == 1 else None
        if vendor is None:
            ignored += 1
            continue
        matched[vendor].append(evidence_entry(item, "namespace" if item.get("namespace") else "name"))
    for n, item in enumerate(unmatched, start=1):
        item["id"] = f"u{n}"
    proposal = {"matched": [{"vendor": v, "evidence": e} for v, e in matched.items()], "unmatched": unmatched,
                "noise": noise, "supportIgnored": ignored, "packageComponents": [evidence_entry(c, "namespace") for c in components]}
    common.write_json(eng / "systems" / "proposal.json", proposal)
    common.write_json(eng / "systems" / "unmatched.json", {"items": unmatched, "knownSystems": [v["vendor"] for v in vendors]})
    print(f"MATCHED {len(matched)} system(s) from the known-systems list; {len(noise)} item(s) not outside systems; "
          f"{len(unmatched)} item(s) for the classifier")
    print("CLASSIFY" if unmatched else "NOTHING TO CLASSIFY")
    return 0


# ---------------------------------------------------------------- build

def new_system(name, kind, middleware, how, **extra):
    entry = {"id": common.system_id(name), "name": name, "kind": kind, "middleware": bool(middleware), "how": how,
             "reasons": [], "description": "", "searchTerms": [], "icon": "", "evidence": [], "status": "proposed",
             "origin": "inventory", "via": None, "tracedRound": None}
    entry.update(extra)
    return entry


def build(eng, check_only=False):
    eng = Path(eng)
    proposal = common.load_json(eng / "systems" / "proposal.json", "systems/proposal.json (run propose first)")
    vendors = {v["vendor"]: v for v in common.load_known_systems()}
    alias_of = {}
    for v in vendors.values():
        for phrase in [v["vendor"]] + v["aliases"]:
            alias_of[norm(phrase)] = v["vendor"]
    systems = OrderedDict()
    for entry in proposal["matched"]:
        v = vendors[entry["vendor"]]
        systems[v["vendor"]] = new_system(v["vendor"], v["kind"], v["middleware"], "known", searchTerms=list(v["searchTerms"]),
                                          icon=v["icon"], evidence=list(entry["evidence"]))
    classified_calls = []
    unmatched = proposal["unmatched"]
    if unmatched:
        path = eng / "systems" / "classified.json"
        if not path.exists():
            print("ERROR systems/classified.json is missing: run the system-classifier agent on systems/unmatched.json")
            print("REFUSED")
            return 1
        classified = common.load_json(path, "systems/classified.json")
        errors = common.shape_errors(classified, "classified.schema.json")
        by_item = {}
        for n, call in enumerate(classified.get("items", []) if isinstance(classified, dict) else []):
            if not isinstance(call, dict):
                continue
            if call.get("item") in by_item:
                errors.append(f"items[{n}]: item {call.get('item')} is classified twice")
            by_item[call.get("item")] = call
        ids = {u["id"] for u in unmatched}
        for missing in sorted(ids - set(by_item), key=lambda i: int(i[1:])):
            errors.append(f"item {missing} is not classified; classify every item in systems/unmatched.json")
        for extra in sorted(set(by_item) - ids):
            errors.append(f"item {extra} is not in systems/unmatched.json")
        terms = {}
        for n, s in enumerate(classified.get("systems", []) if isinstance(classified, dict) else []):
            if isinstance(s, dict):
                terms[norm(s.get("name"))] = s
        for call in by_item.values():
            if call.get("verdict") == "system" and norm(call.get("system")) not in terms and norm(call.get("system")) not in alias_of:
                errors.append(f"item {call.get('item')}: system '{call.get('system')}' has no entry in 'systems' with its search terms")
        if errors:
            for line in errors:
                print(f"ERROR {line}")
            print("REFUSED")
            return 1
        items = {u["id"]: u for u in unmatched}
        for item_id, call in sorted(by_item.items(), key=lambda kv: int(kv[0][1:])):
            item = {k: v for k, v in items[item_id].items() if k not in ("id", "candidates", "matchedBy")}
            if call["verdict"] == "noise":
                proposal_noise = dict(item, matchedBy="classifier", reason=call["reason"])
                proposal["noise"].append(proposal_noise)
                classified_calls.append({"item": item["name"], "type": item["type"], "verdict": "not an outside system",
                                         "reason": call["reason"], "confidence": call.get("confidence", "")})
                continue
            name = alias_of.get(norm(call["system"]), call["system"])
            if name not in systems:
                detail = terms.get(norm(call["system"]), {})
                known = vendors.get(name)
                systems[name] = new_system(name, known["kind"] if known else call["kind"],
                                           known["middleware"] if known else call.get("middleware", False),
                                           "known" if known else "classifier",
                                           searchTerms=list(known["searchTerms"]) if known else list(detail.get("searchTerms", [])),
                                           icon=known["icon"] if known else "", description=detail.get("description", ""))
            systems[name]["evidence"].append(dict(item, matchedBy="classifier"))
            systems[name]["reasons"].append(f"{item['type']} {item['name']}: {call['reason']}")
            classified_calls.append({"item": item["name"], "type": item["type"], "verdict": name,
                                     "reason": call["reason"], "confidence": call.get("confidence", "")})
    # package components and permission sets of a namespace the classifier proved
    by_ns = {}
    noise_rows = common.load_not_external()
    for name, s in systems.items():
        for e in s["evidence"]:
            if e.get("namespace") and e["role"] == "proof" and not noise_reason({"namespace": e["namespace"]}, noise_rows, ("namespace",)):
                by_ns.setdefault(e["namespace"].casefold(), name)
    for comp in proposal.get("packageComponents", []):
        owner = by_ns.get((comp.get("namespace") or "").casefold())
        if owner and not any(e.get("nodeId") == comp.get("nodeId") for e in systems[owner]["evidence"]):
            systems[owner]["evidence"].append(comp)
    result = {"systems": list(systems.values()), "noise": proposal["noise"], "classifierCalls": classified_calls,
              "dropped": [], "supportIgnored": proposal.get("supportIgnored", 0)}
    for s in result["systems"]:
        s["evidence"].sort(key=lambda e: (e["role"] != "proof", e["type"], e["name"]))
    if check_only:
        print(f"{len(result['systems'])} system(s) would be proposed")
        print("CLASSIFIED OK")
        return 0
    common.write_json(eng / "systems" / "proposed.json", result)
    common.write_json(eng / "systems.json", result)
    print(f"{len(result['systems'])} system(s) proposed; {len(result['noise'])} item(s) set aside as not outside systems")
    print("PROPOSED")
    return 0


# ---------------------------------------------------------------- show

def evidence_summary(system, limit=6):
    groups = OrderedDict()
    for e in system["evidence"]:
        label = "managed package" if e["type"] == "Managed Package" else e["type"].lower()
        if e["name"] not in groups.setdefault(label, []):
            groups[label].append(e["name"])
    parts = []
    for label, names in groups.items():
        shown = ", ".join(f"'{n}'" for n in names[:limit])
        more = f" and {len(names) - limit} more" if len(names) > limit else ""
        parts.append(f"{label} {shown}{more}" if len(names) == 1 else f"{label}s {shown}{more}")
    return "; ".join(parts)


def show(eng):
    data = common.load_json(Path(eng) / "systems.json", "systems.json")
    print("| System | Kind | Found by | Evidence |")
    print("|---|---|---|---|")
    for s in data["systems"]:
        kind = "middleware" if s.get("middleware") else s["kind"]
        found = {"known": "known vendor", "classifier": "classifier", "architect": "added by the architect",
                 "indirect": f"named behind {s.get('via') or 'a middleware'}"}.get(s["how"], s["how"])
        if s.get("status") == "confirmed" and s.get("origin") == "indirect":
            found = f"named behind {s.get('via')}"
        print(f"| {s['name']} | {kind} | {found} | {evidence_summary(s) or s.get('description', '')} |")
    calls = data.get("classifierCalls", [])
    if calls:
        print()
        print("Classifier calls:")
        for c in calls:
            print(f"- {c['type']} '{c['item']}': {c['verdict']} ({c.get('confidence') or 'no confidence given'}): {c['reason']}")
    counts = Counter(n["reason"] for n in data.get("noise", []))
    if counts:
        print()
        print("Set aside as not outside systems:")
        for reason, count in counts.most_common():
            examples = [n["name"] for n in data["noise"] if n["reason"] == reason][:4]
            print(f"- {count}: {reason} (for example {', '.join(examples)})")
    if data.get("dropped"):
        print()
        print("Dropped by the architect:")
        for d in data["dropped"]:
            print(f"- {d['name']}: {d.get('reason', '')}")
    return 0


# ---------------------------------------------------------------- confirm

def find_system(systems, ref):
    for s in systems:
        if s["id"] == ref or norm(s["name"]) == norm(ref):
            return s
    return None


def apply_ops(result, rounds):
    systems, errors = result["systems"], []
    for r_index, round_ in enumerate(rounds, start=1):
        by = round_.get("by") or "the architect"
        for c_index, op in enumerate(round_.get("corrections", []), start=1):
            where = f"round {r_index} correction {c_index}"
            kind = op.get("op")
            if kind == "drop":
                s = find_system(systems, op.get("system", ""))
                if not s:
                    errors.append(f"{where}: no system '{op.get('system')}' to drop")
                    continue
                systems.remove(s)
                result["dropped"].append({"name": s["name"], "reason": op.get("reason", ""), "by": by})
            elif kind == "rename":
                s = find_system(systems, op.get("system", ""))
                if not s or not op.get("to"):
                    errors.append(f"{where}: rename needs an existing system and 'to'")
                    continue
                s["name"] = op["to"]
                s["id"] = common.system_id(op["to"])
            elif kind == "merge":
                into = find_system(systems, op.get("into", ""))
                if not into:
                    errors.append(f"{where}: no system '{op.get('into')}' to merge into")
                    continue
                for ref in op.get("systems", []):
                    s = find_system(systems, ref)
                    if not s or s is into:
                        errors.append(f"{where}: no system '{ref}' to merge")
                        continue
                    into["evidence"] += s["evidence"]
                    into["searchTerms"] = list(dict.fromkeys(into["searchTerms"] + s["searchTerms"] + [s["name"]]))
                    into["reasons"] += s["reasons"]
                    systems.remove(s)
            elif kind == "kind":
                s = find_system(systems, op.get("system", ""))
                if not s or op.get("kind") not in common.SYSTEM_KINDS:
                    errors.append(f"{where}: kind needs an existing system and one of {', '.join(common.SYSTEM_KINDS)}")
                    continue
                s["kind"] = op["kind"]
                if "middleware" in op:
                    s["middleware"] = bool(op["middleware"])
                if s["middleware"]:
                    s["kind"] = "middleware"
            elif kind == "add":
                if not op.get("name") or op.get("kind") not in common.SYSTEM_KINDS:
                    errors.append(f"{where}: add needs a name and a kind ({', '.join(common.SYSTEM_KINDS)})")
                    continue
                if find_system(systems, op["name"]):
                    errors.append(f"{where}: '{op['name']}' is already in the list")
                    continue
                systems.append(new_system(op["name"], "middleware" if op.get("middleware") else op["kind"], op.get("middleware"),
                                          "architect", searchTerms=list(op.get("searchTerms") or [op["name"]]),
                                          description=op.get("note", ""), reasons=[f"added by {by}"]))
            else:
                errors.append(f"{where}: unknown op '{kind}'; use drop, rename, merge, kind or add")
    ids = Counter(s["id"] for s in systems)
    for ident, count in ids.items():
        if count > 1:
            errors.append(f"two systems share the id '{ident}'; rename or merge them")
    return errors


def confirm(eng):
    eng = Path(eng)
    result = common.load_json(eng / "systems" / "proposed.json", "systems/proposed.json (run build first)")
    path = eng / "systems" / "corrections.json"
    rounds = common.load_json(path, "systems/corrections.json").get("rounds", []) if path.exists() else []
    errors = apply_ops(result, rounds)
    if not errors and not result["systems"]:
        errors = ["no outside system is left: a landscape needs at least one. Show this to the architect: they can add a "
                  "system or end the run here"]
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED")
        return 1
    for s in result["systems"]:
        s["status"] = "confirmed"
        if s.get("middleware"):
            s["kind"] = "middleware"
    result["confirmedOn"] = date.today().isoformat()
    common.write_json(eng / "systems.json", result)
    print(f"{len(result['systems'])} system(s) confirmed; {len(result['dropped'])} dropped")
    print("CONFIRMED")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    commands = {"propose": propose, "build": build, "show": show, "confirm": confirm}
    check_only = argv[2:] == ["--check"] and argv[:1] == ["build"]
    if not (len(argv) == 2 or check_only) or argv[0] not in commands:
        print(__doc__.strip())
        return 2
    try:
        return build(argv[1], True) if check_only else commands[argv[0]](argv[1])
    except SetupError as exc:
        print(f"SETUP {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
