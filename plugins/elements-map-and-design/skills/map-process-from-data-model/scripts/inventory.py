#!/usr/bin/env python3
"""Build, merge, group and check the object inventory (schemas/inventory.schema.json).

Usage:
  inventory.py from-metadata --objects PART.ndjson [...] [--relationships PART.ndjson ...]
                             [--with-records PART.ndjson ... | --all-have-records] [--only API ...] [--basis usage|configuration]
                             --system NAME [--variant TEXT] --ref-model ID [--scope-note TEXT] --out inventory.json
  inventory.py merge PARTIAL.json [...] --out inventory.json
  inventory.py set-capabilities --inventory inventory.json --proposal capabilities.proposal.json
                                [--out inventory.json] [--confirmed] [--max-top 10] [--max-objects 15]
  inventory.py check inventory.json [--partial]
  inventory.py lifecycle-candidates --inventory inventory.json --fields PART.ndjson [...] [--choose Object.Field ...]
                                    [--out lifecycle-fields.json]
  inventory.py lifecycle --inventory inventory.json --fields FIELDS.json [...] --values VALUES.json [...]
                         [--record-types PART.ndjson ...] [--out inventory.json]
  inventory.py focus --inventory inventory.json --object API [--name TEXT] [--out capabilities.proposal.json]
  inventory.py usage --inventory inventory.json --results USAGE.json [...] [--basis usage|configuration | --scope scope.json]
                     [--read-at YYYY-MM-DD] [--out inventory.json]

from-metadata  turns the NDJSON part files of two Elements calls into an inventory:
               list_metadata_by_criteria (Standard Object / Custom Object rows) and
               get_dependencies (nodeIds, where_used, fieldTypes "relationship").
merge          joins the partial inventories the system-doc-reader agent writes.
set-capabilities applies the capability-grouper's proposal and checks that every
               object is placed exactly once.
check          checks an inventory's shape and rules; --partial checks a doc
               reader's partial inventory (shape and duplicates only).
lifecycle-candidates  (route metadata) picks each in-scope object's lifecycle field (its status or
               stage picklist) from list_metadata_by_criteria Field rows, and writes the nodeIds
               to read in full.
lifecycle      (route metadata) writes each object's lifecycle (values in the org's order, closed,
               won, default) from the saved get_metadata_component results of those fields and of
               their values, and counts active record types.
focus          (one-object scope) writes the capability proposal for the process of one object:
               one capability owning the object and the objects that belong to it.
usage          (route metadata) writes each object's usage (record counts, per record type, last
               created and modified, net change) from saved get_component_usage results, copies the
               run's basis (usage or configuration) into the inventory, and on basis usage names the
               objects that hold no records. With a focus object that holds none, it stops the run.

Every command marks each object's role from data/platform-objects.csv, marks an
object that eight or more others look up to (its own master-detail children
aside) as a hub, and flags polymorphic reference fields. Prints one line per finding and a summary line. Exit 0: no errors;
1: the inventory or proposal has errors; 2: setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import common
from common import SetupError, norm

SCHEMA = "inventory.schema.json"  # the shape every inventory and partial inventory must pass
POLYMORPHIC_MIN_TARGETS = 5   # a field pointing at more object types than this is polymorphic
HUB_MIN_REFERRERS = 8          # an object this many others look up to (master-detail aside) is a hub
HUB_MIN_CAPABILITIES = 3       # with capabilities: an object looked up to from this many other capabilities


class Report:
    def __init__(self):
        self.errors, self.warnings, self.notes = [], [], []

    def error(self, message):
        self.errors.append(f"ERROR {message}")

    def warn(self, message):
        self.warnings.append(f"WARN {message}")

    def note(self, message):
        self.notes.append(f"NOTE {message}")

    def finish(self, summary=""):
        for line in self.errors + self.warnings + self.notes:
            print(line)
        verdict = "FAIL" if self.errors else "PASS"
        print(f"{verdict}: {len(self.errors)} error(s), {len(self.warnings)} warning(s).{summary}")
        return 1 if self.errors else 0


# ---------------------------------------------------------------- roles

from mcp_result import owner_api, hydrate, require_complete

def assign_roles(inv, hub_min=HUB_MIN_REFERRERS):
    """Set object.role from the platform list and how widely the object is referenced.

    Without capabilities, an object that hub_min others look up to is a hub. With
    capabilities (the vendor's grouping), only references from other capabilities
    count: an inventory's own transactions all pointing at Product Item do not make
    it a hub, while Account referenced from every capability does."""
    rules = common.load_platform_rules()
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    caps_of, home = defaultdict(set), {}
    for cap in inv.get("capabilities", []):
        for api in cap.get("objects", []) + cap.get("sharedObjects", []):
            caps_of[api].add(cap["id"])
        for api in cap.get("objects", []):
            home.setdefault(api, cap["id"])  # the first capability listing an object, as ownership resolves it
    referrers, other_caps = defaultdict(set), defaultdict(set)
    for rel in inv.get("relationships", []):
        # A master's own detail objects are its family, not other capabilities using it,
        # so only lookups count towards making an object a hub. A referrer counts once, for
        # its home capability, so vendor guides that repeat each other do not inflate the count.
        if not rel.get("polymorphic") and rel["from"] != rel["to"] and rel.get("kind") != "master-detail":
            referrers[rel["to"]].add(rel["from"])
            if rel["from"] in home and home[rel["from"]] not in caps_of.get(rel["to"], set()):
                other_caps[rel["to"]].add(home[rel["from"]])
    for api, obj in objects.items():
        role = common.platform_role(api, rules)
        if role is None:
            if caps_of and len(other_caps.get(api, ())) >= HUB_MIN_CAPABILITIES:
                role = "hub"
            elif not caps_of and len(referrers.get(api, ())) >= hub_min:
                role = "hub"
        if role:
            obj["role"] = role
        else:
            obj.pop("role", None)


def mark_polymorphic(relationships, all_rows=None):
    """A field that points at many object types says nothing about where an object belongs."""
    targets = defaultdict(set)
    for rel in all_rows if all_rows is not None else relationships:
        targets[(rel["from"], rel.get("field") or "")].add(rel["to"])
    for rel in relationships:
        if len(targets[(rel["from"], rel.get("field") or "")]) > POLYMORPHIC_MIN_TARGETS:
            rel["polymorphic"] = True


def dedupe_relationships(relationships):
    seen, kept = set(), []
    for rel in relationships:
        key = (rel["from"], rel.get("field") or "", rel["to"])
        if key not in seen:
            seen.add(key)
            kept.append(rel)
    return kept


# ---------------------------------------------------------------- from-metadata

# Elements metadata type -> inventory kind; a Big Object is treated as a custom object
KIND_BY_TYPE = {"Standard Object": "standard", "Custom Object": "custom", "External Object": "external",
                "Big Object": "custom"}


def object_from_row(row):
    sf = row.get("sf") or {}
    api = sf.get("apiName")
    if not api:
        return None
    managed = bool((row.get("nodeDetails") or {}).get("isManaged"))
    obj = {"apiName": api, "name": (row.get("name") or api).strip() or api,
           "kind": "managed" if managed else KIND_BY_TYPE.get(sf.get("type"), "custom")}
    if (row.get("description") or "").strip():
        obj["description"] = row["description"].strip()[:2000]
    if row.get("nodeId"):
        obj["nodeId"] = str(row["nodeId"])
    if row.get("lastCreatedRecordDate"):
        obj["lastRecordCreated"] = str(row["lastCreatedRecordDate"])[:40]
    return obj


def relationship_from_row(row):
    node, related = row.get("node") or {}, row.get("related") or {}
    carrying = row.get("carryingObject") or {}
    source = carrying.get("apiName") or related.get("object")
    target, field = node.get("apiName"), related.get("apiName")
    if not (source and target):
        return None
    field_type = (related.get("fieldType") or "").casefold()
    rel = {"from": source, "to": target, "field": field or "",
           "kind": "master-detail" if "master" in field_type else "lookup"}
    if not rel["field"]:
        del rel["field"]
    pct = row.get("populationPercent")
    if isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 <= pct <= 100:
        rel["populationPercent"] = pct
    return rel


def cmd_from_metadata(args):
    report = Report()
    objects, order, record_counts = {}, [], {}
    only = {a.casefold(): a for a in args.only} if args.only else None
    for row in common.read_ndjson(args.objects):
        if row.get("status") == "deleted":
            continue
        obj = object_from_row(row)
        if obj is None:
            report.warn(f"skipped an object row with no API name: {str(row)[:120]}")
            continue
        if only is not None and obj["apiName"].casefold() not in only:
            continue
        if obj["apiName"] not in objects:
            order.append(obj["apiName"])
        objects[obj["apiName"]] = obj
        count = row.get("record_count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            record_counts[obj["apiName"]] = count

    with_records = None
    if args.with_records:
        with_records = {o["apiName"] for o in filter(None, map(object_from_row, common.read_ndjson(args.with_records)))}
    counted = [api for api in order if isinstance(record_counts.get(api), int)]
    for api in order:
        if args.all_have_records:
            objects[api]["hasRecords"] = True
            if record_counts.get(api) == 0:
                # the rows carry record_count: an object list said to be filtered to records holds an empty object
                objects[api]["hasRecords"] = False
                report.warn(f"--all-have-records was given, but the row of {api} has record_count 0; the object list was not "
                            "filtered on records, so it is marked as holding none (use inventory.py usage for the real counts)")
        elif with_records is not None:
            objects[api]["hasRecords"] = api in with_records
        elif api in counted:
            objects[api]["hasRecords"] = record_counts[api] > 0

    rules = common.load_platform_rules()
    all_rels = [r for r in map(relationship_from_row, common.read_ndjson(args.relationships or [])) if r]
    mark_polymorphic(all_rels)
    in_scope = []
    dropped_platform = 0
    for rel in all_rels:
        if rel["from"] not in objects or rel["to"] not in objects:
            continue
        if common.platform_role(rel["from"], rules) == "platform":
            dropped_platform += 1
            continue
        in_scope.append(rel)

    inv = {"schemaVersion": "1.0", "system": args.system, "route": "metadata",
           "sources": [{"kind": "metadata", "ref": args.ref_model}],
           "objects": [objects[a] for a in order],
           "relationships": dedupe_relationships(in_scope), "gaps": []}
    if args.variant:
        inv["variant"] = args.variant
    if args.scope_note:
        inv["sources"][0]["note"] = args.scope_note
    if not args.relationships:
        inv["gaps"].append({"note": "No relationship export was given, so objects are grouped by name and description only."})
    if only is not None:
        missing = sorted(only[k] for k in set(only) - {a.casefold() for a in order})
        for api in missing:
            report.warn(f"'{api}' was asked for but is not in the object export")
            inv["gaps"].append({"about": api, "note": "Named in the scope but not found among the org's objects."})
    if args.basis:
        inv["basis"] = args.basis
    if with_records is None and not args.all_have_records and len(counted) < len(order):
        inv["gaps"].append({"note": "Whether each object holds records is unknown: no record-count export was given."})
    assign_roles(inv, args.hub_min)
    if not inv["gaps"]:
        del inv["gaps"]

    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    if not report.errors:
        common.write_json(args.out, inv)
    roles = defaultdict(int)
    for obj in inv["objects"]:
        roles[obj.get("role", "business")] += 1
    report.note(f"{dropped_platform} relationship(s) from platform objects left out")
    summary = (f" {len(inv['objects'])} object(s): {roles['business']} business, {roles['hub']} hub, "
               f"{roles['platform']} platform; {len(inv['relationships'])} relationship(s)"
               f"{'' if report.errors else ' written to ' + str(args.out)}.")
    return report.finish(summary)


# ---------------------------------------------------------------- merge

def merge_lists(first, second, key):
    seen = {key(x) for x in first}
    return first + [x for x in second if key(x) not in seen and not seen.add(key(x))]


def cmd_merge(args):
    report = Report()
    partials = []
    for path in args.partials:
        doc = common.load_json(path, "partial inventory")
        for line in common.shape_errors(doc, SCHEMA):
            report.error(f"{path}: {line}")
        partials.append((path, doc))
    if report.errors:
        return report.finish(" Fix the partial inventories, then merge again.")

    base = partials[0][1]
    inv = {"schemaVersion": "1.0", "system": base["system"], "route": base["route"],
           "sources": [], "objects": [], "relationships": [], "capabilities": [], "gaps": []}
    if base.get("variant"):
        inv["variant"] = base["variant"]
    objects, caps = {}, {}
    for path, doc in partials:
        if doc["route"] != inv["route"]:
            report.error(f"{path}: route '{doc['route']}' differs from '{inv['route']}'")
        inv["sources"] = merge_lists(inv["sources"], doc["sources"], lambda s: (s["kind"], s["ref"]))
        for obj in doc.get("objects", []):
            current = objects.get(obj["apiName"])
            if current is None:
                objects[obj["apiName"]] = dict(obj)
                continue
            for field in ("kind", "docUrl", "nodeId", "lastRecordCreated", "lifecycle"):
                if field in obj and field not in current:
                    current[field] = obj[field]
            if obj.get("lifecycle") and len(obj["lifecycle"]["values"]) > len(current["lifecycle"]["values"]):
                current["lifecycle"] = obj["lifecycle"]
            # A partial that only knew the API name uses it as the name; a later partial that
            # read the object's page has its label, which is what the diagram should show.
            if current["name"] == current["apiName"] and obj["name"] != obj["apiName"]:
                current["name"] = obj["name"]
            if len(obj.get("description", "")) > len(current.get("description", "")):
                current["description"] = obj["description"]
            if "hasRecords" in obj:
                current["hasRecords"] = current.get("hasRecords", False) or obj["hasRecords"]
            current["keyFields"] = merge_lists(current.get("keyFields", []), obj.get("keyFields", []), lambda f: norm(f["name"]))
            current["evidence"] = merge_lists(current.get("evidence", []), obj.get("evidence", []), lambda e: e)
            for field in ("keyFields", "evidence"):
                if not current[field]:
                    del current[field]
        inv["relationships"].extend(doc.get("relationships", []))
        for cap in doc.get("capabilities", []):
            current = caps.get(cap["id"])
            if current is None:
                caps[cap["id"]] = dict(cap)
                continue
            for field in ("description", "docUrl", "parent", "supporting"):
                if field in cap and field not in current:
                    current[field] = cap[field]
            current["objects"] = merge_lists(current["objects"], cap["objects"], lambda a: a)
            for field, key in (("sharedObjects", lambda a: a), ("helpLinks", lambda l: l["url"]), ("evidence", lambda e: e)):
                merged = merge_lists(current.get(field, []), cap.get(field, []), key)
                if merged:
                    current[field] = merged
        inv["gaps"] = merge_lists(inv["gaps"], doc.get("gaps", []), lambda g: (g.get("about"), g["note"]))

    inv["objects"] = list(objects.values())
    inv["relationships"] = dedupe_relationships(inv["relationships"])
    for rel in inv["relationships"]:
        rel.pop("polymorphic", None)
    mark_polymorphic(inv["relationships"])
    for rel in inv["relationships"]:
        for end in ("from", "to"):
            if rel[end] not in objects:
                report.warn(f"relationship {rel['from']}.{rel.get('field', '?')} -> {rel['to']}: '{rel[end]}' is not in the object list; add it or the relationship is ignored")
    inv["capabilities"] = list(caps.values())
    assign_roles(inv, args.hub_min)
    resolve_source_ownership(inv, report)
    for section in ("relationships", "capabilities", "gaps"):
        if not inv[section]:
            del inv[section]

    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    if not report.errors:
        common.write_json(args.out, inv)
    listed = {a for c in inv.get("capabilities", []) for a in c["objects"] + c.get("sharedObjects", [])}
    orphans = [o["apiName"] for o in inv["objects"] if o.get("role") != "platform" and o["apiName"] not in listed]
    if inv.get("capabilities") and orphans:
        report.note(f"{len(orphans)} object(s) are in no source capability; the capability-grouper places them: {', '.join(orphans[:20])}{' ...' if len(orphans) > 20 else ''}")
    summary = (f" {len(inv['objects'])} object(s), {len(inv.get('relationships', []))} relationship(s), "
               f"{len(inv.get('capabilities', []))} source capabilit(ies) from {len(partials)} partial(s)"
               f"{'' if report.errors else ' written to ' + str(args.out)}.")
    return report.finish(summary)


def resolve_source_ownership(inv, report):
    """An object a source lists under several capabilities is owned by the first; hubs and
    platform objects are shared, never owned."""
    objects = {o["apiName"]: o for o in inv["objects"]}
    owner = {}
    for cap in inv.get("capabilities", []):
        owned, shared = [], list(cap.get("sharedObjects", []))
        for api in cap["objects"]:
            obj = objects.get(api)
            if obj is None:
                report.warn(f"capability '{cap['id']}' lists '{api}', which is not in the object list")
                owned.append(api)
            elif obj.get("role") in ("hub", "platform"):
                shared.append(api)
            elif api in owner:
                shared.append(api)
                report.note(f"'{api}' is listed by '{owner[api]}' and '{cap['id']}'; '{owner[api]}' owns it and '{cap['id']}' shares it")
            else:
                owner[api] = cap["id"]
                owned.append(api)
        cap["objects"] = owned
        shared = common.dedupe(shared)
        if shared:
            cap["sharedObjects"] = shared


# ---------------------------------------------------------------- capabilities

def check_capabilities(inv, report, max_top, max_objects, unassigned=()):
    objects = {o["apiName"]: o for o in inv["objects"]}
    caps = inv.get("capabilities", [])
    by_id = {}
    for cap in caps:
        if cap["id"] in by_id:
            report.error(f"capability id '{cap['id']}' is used twice")
        by_id[cap["id"]] = cap
    children = defaultdict(list)
    for cap in caps:
        if "parent" in cap:
            parent = by_id.get(cap["parent"])
            if parent is None:
                report.error(f"capability '{cap['id']}': parent '{cap['parent']}' is not a capability")
            elif "parent" in parent:
                report.error(f"capability '{cap['id']}': parent '{cap['parent']}' is itself under an area; use at most two levels (area, capability)")
            else:
                children[cap["parent"]].append(cap["id"])
    names = defaultdict(list)
    for cap in caps:
        names[(cap.get("parent"), norm(cap["name"]))].append(cap["id"])
    for (_, name), ids in names.items():
        if len(ids) > 1:
            report.error(f"capabilities {', '.join(ids)} share the name '{name}' at one level; give them different names")

    top = [c for c in caps if "parent" not in c]
    if len(top) > max_top:
        report.error(f"{len(top)} capabilities on the top level; at most {max_top} fit. Merge close ones or group them under areas (parent)")
    for area, kids in children.items():
        if len(kids) > max_top:
            report.error(f"area '{area}' has {len(kids)} capabilities; at most {max_top} fit on its level")

    owner = {}
    unassigned_apis = {u["apiName"] for u in unassigned}
    for cap in caps:
        is_area = cap["id"] in children
        if is_area and cap["objects"]:
            report.error(f"area '{cap['id']}' owns objects; areas group capabilities, so move {', '.join(cap['objects'][:5])} into one of its capabilities")
        if not is_area and not cap["objects"]:
            report.warn(f"capability '{cap['id']}' owns no objects; its child level can only use shared objects")
        if not is_area and len(cap["objects"]) > max_objects:
            report.warn(f"capability '{cap['id']}' owns {len(cap['objects'])} objects; above {max_objects} its level will not fit 10 steps, so consider splitting it")
        for api in cap["objects"]:
            obj = objects.get(api)
            if obj is None:
                report.error(f"capability '{cap['id']}' owns '{api}', which is not in the inventory")
                continue
            if api in owner:
                report.error(f"'{api}' is owned by both '{owner[api]}' and '{cap['id']}'; an object belongs to one capability (list it under sharedObjects of the other)")
            owner[api] = cap["id"]
            if obj.get("role") == "platform":
                report.warn(f"capability '{cap['id']}' owns '{api}', which data/platform-objects.csv marks as platform; keep it only if it is a business record here")
        for api in cap.get("sharedObjects", []):
            if api not in objects:
                report.error(f"capability '{cap['id']}' shares '{api}', which is not in the inventory")
    shared = {a for cap in inv.get("capabilities", []) for a in cap.get("sharedObjects", [])}
    for api, obj in objects.items():
        if obj.get("role") in ("platform", "hub") or api in owner:
            continue
        if inv.get("focus") and api in shared:
            continue  # one object's process: what it points at is read, not owned, and has no process of its own here
        if api not in unassigned_apis:
            report.error(f"'{api}' ({obj['name']}) is in no capability; give it an owner or list it under unassigned with the reason")
    return owner


def cmd_set_capabilities(args):
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    proposal = common.load_json(args.proposal, "proposal")
    if not isinstance(proposal, dict) or not isinstance(proposal.get("capabilities"), list):
        raise SetupError(f"{args.proposal} must be an object with a 'capabilities' list")
    unassigned = proposal.get("unassigned", [])
    for index, item in enumerate(unassigned):
        if not isinstance(item, dict) or not item.get("apiName") or not item.get("reason"):
            report.error(f"unassigned[{index}] needs apiName and reason")
    inv["capabilities"] = proposal["capabilities"]
    if args.confirmed:
        for cap in inv["capabilities"]:
            cap["confirmed"] = True
    gaps = [g for g in inv.get("gaps", []) if not g.get("note", "").startswith("Not placed in any capability")]
    gaps += [{"about": u["apiName"], "note": f"Not placed in any capability: {u['reason']}"} for u in unassigned if isinstance(u, dict) and u.get("apiName") and u.get("reason")]
    if gaps:
        inv["gaps"] = gaps
    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    if not report.errors:
        check_capabilities(inv, report, args.max_top, args.max_objects, unassigned)
    if not report.errors:
        common.write_json(args.out or args.inventory, inv)
    leaves = [c for c in inv["capabilities"] if not any(k.get("parent") == c["id"] for k in inv["capabilities"])]
    summary = (f" {len(inv['capabilities'])} capabilit(ies), {len(leaves)} with a child level of their own, "
               f"{len(unassigned)} object(s) left unassigned"
               f"{'' if report.errors else ' written to ' + str(args.out or args.inventory)}.")
    return report.finish(summary)


def cmd_check(args):
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    if report.errors:
        return report.finish("")
    apis = {o["apiName"] for o in inv["objects"]}
    seen = set()
    for obj in inv["objects"]:
        if obj["apiName"] in seen:
            report.error(f"object '{obj['apiName']}' is listed twice")
        seen.add(obj["apiName"])
    for rel in inv.get("relationships", []):
        for end in ("from", "to"):
            if rel[end] not in apis:
                report.warn(f"relationship {rel['from']} -> {rel['to']}: '{rel[end]}' is not in the object list")
    for obj in inv["objects"]:
        lifecycle_problems(obj, report)
    if inv.get("focus") and inv["focus"] not in apis:
        report.error(f"focus '{inv['focus']}' is not an object in the inventory")
    if inv.get("capabilities") and not args.partial:
        assign_roles(inv)
        unassigned = [{"apiName": g["about"]} for g in inv.get("gaps", []) if g.get("about") and g["note"].startswith("Not placed in any capability")]
        check_capabilities(inv, report, args.max_top, args.max_objects, unassigned)
    return report.finish(f" {len(inv['objects'])} object(s), {len(inv.get('relationships', []))} relationship(s), {len(inv.get('capabilities', []))} capabilit(ies).")


# ---------------------------------------------------------------- lifecycles

# Field names that carry a record's workflow, best first; a custom field matches by its ending.
LIFECYCLE_NAMES = ["StageName", "Status", "Stage", "State", "Phase"]
LIFECYCLE_ENDINGS = ["Stage__c", "Status__c", "State__c", "Phase__c"]


def lifecycle_problems(obj, report):
    lc = obj.get("lifecycle")
    if not lc:
        return
    seen = set()
    for v in lc["values"]:
        if v["value"] in seen:
            report.error(f"object '{obj['apiName']}': lifecycle value '{v['value']}' is listed twice")
        seen.add(v["value"])
        if v.get("won") and v.get("closed") is False:
            report.error(f"object '{obj['apiName']}': lifecycle value '{v['value']}' is won but not closed")
    process_object = obj["apiName"] in common.PROCESS_OBJECTS
    if process_object and not common.lifecycle_ready(obj["apiName"], lc):
        missing = [rt["name"] for rt in lc["recordTypes"] if not rt.get("process")]
        report.warn(f"object '{obj['apiName']}': record type(s) {', '.join(missing)} have no process values; read each record type's "
                    "Process and its Custom Values (source-routes step 7.4), or the object stays an ordinary object on the steps that use it")
    values = {v["value"] for v in lc["values"]}
    for rt in lc.get("recordTypes") or []:
        if process_object and not rt.get("process"):
            continue
        if "values" not in rt:
            report.warn(f"object '{obj['apiName']}': record type {rt['name']} has no value usage; its level shows every value of {lc['field']}")
        elif not rt["values"]:
            report.warn(f"object '{obj['apiName']}': record type {rt['name']} uses none of the active values of {lc['field']}")
        for v in rt.get("values") or []:
            if v not in values:
                report.error(f"object '{obj['apiName']}': record type {rt['name']} uses '{v}', which is not an active value")


def object_of(row):
    """The API name of the object a Field or Record Type row belongs to, from its parentPath
    ('Object.StandardObject.Case.fields' -> 'Case'), or its parentObject."""
    parts = (row.get("parentPath") or "").split(".")
    if len(parts) >= 2 and parts[-1].lower() in ("fields", "recordtypes", "recordtype"):
        return parts[-2]
    return row.get("parentObject")


def lifecycle_rank(api):
    """Lower is a better lifecycle field; None when the name does not look like one. A managed package's
    field (a namespace prefix, as in Gong__Flow_Status__c) comes after the org's own fields."""
    if api in LIFECYCLE_NAMES:
        return LIFECYCLE_NAMES.index(api)
    managed = 100 if api.count("__") > 1 else 0
    for i, ending in enumerate(LIFECYCLE_ENDINGS):
        if api.endswith(ending):
            return len(LIFECYCLE_NAMES) + i + managed
    return None


def cmd_lifecycle_candidates(args):
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    apis = {o["apiName"] for o in inv["objects"]}
    candidates = defaultdict(list)
    for row in common.read_ndjson(args.fields):
        api = (row.get("sf") or {}).get("apiName") or row.get("apiName")
        subtype = (row.get("nodeDetails") or {}).get("subtype") or row.get("subtype")
        obj = object_of(row)
        if obj not in apis or not api or row.get("status") == "deleted":
            continue
        if subtype and "picklist" not in subtype.lower():
            continue
        rank = lifecycle_rank(api)
        if rank is None:
            continue
        candidates[obj].append({"field": api, "nodeId": row.get("nodeId"), "rank": rank,
                                "label": row.get("name"), "percentFilled": row.get("percent_filled")})
    chosen = {}
    for choice in args.choose or []:
        obj, _, field = choice.partition(".")
        if not any(c["field"] == field for c in candidates.get(obj, [])):
            report.error(f"--choose {choice}: no picklist {field} on {obj} among the rows")
        chosen[obj] = field
    out = []
    for obj in sorted(candidates):
        rows = sorted(candidates[obj], key=lambda c: (c["rank"], c["field"]))
        pick = next((c for c in rows if c["field"] == chosen.get(obj)), rows[0])
        entry = {"object": obj, "field": pick["field"], "nodeId": pick["nodeId"], "label": pick["label"]}
        others = [c["field"] for c in rows if c is not pick]
        if others:
            entry["alternatives"] = others
            report.note(f"{obj}: chose {pick['field']} over {', '.join(others)}; pass --choose {obj}.<field> to change it")
        out.append(entry)
    if not report.errors:
        common.write_json(args.out, {"fields": out, "nodeIds": [e["nodeId"] for e in out if e["nodeId"]]})
    return report.finish(f" {len(out)} object(s) with a lifecycle field{'' if report.errors else ' written to ' + str(args.out)}."
                         " Read their nodeIds with get_metadata_component (detail full), then the value nodeIds each lists.")


def items_of(path):
    """The node documents in a saved get_metadata_component result: {items: [...]}, one document, or a list."""
    doc = require_complete(common.load_json(path, "saved get_metadata_component result"))
    if isinstance(doc, dict) and any(item.get("error") for item in doc.get("items", [])):
        raise SetupError(f"{path}: component item errors are explicit evidence gaps: {doc['items']}")
    if isinstance(doc, dict) and isinstance(doc.get("items"), list):
        return doc["items"]
    if isinstance(doc, list):
        return doc
    return [doc]


def summary_flags(summary):
    """Closed, Won, Default and Probability from a picklist value's summary ('Closed: true\nWon: false\n...')."""
    flags = {}
    for line in (summary or "").splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip().lower()
        if key in ("closed", "won", "default", "is default", "isdefault") and value in ("true", "false"):
            flags["default" if "default" in key else key] = value == "true"
        elif key == "probability":
            try:
                flags["probability"] = float(value)
            except ValueError:
                pass
    return flags


def cmd_lifecycle(args):
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    objects = {o["apiName"]: o for o in inv["objects"]}
    values = {}
    for path in args.values:
        for item in items_of(path):
            node = item.get("_id") or item.get("nodeId")
            if node:
                values[node] = item
    with_record_types = None
    if args.record_type_objects:
        # the org health tool's objects_by_record_type detail: the objects with custom record types
        with_record_types = {item.get("apiName") for path in args.record_type_objects for item in items_of(path)}
    record_types = defaultdict(list)
    for row in common.read_ndjson(args.record_types or []):
        active = row.get("active", (row.get("nodeDetails") or {}).get("active", True))
        name = (row.get("sf") or {}).get("apiName") or row.get("name")
        obj = object_of(row)
        # every object lists a "Master" record type; it is the absence of record types, not one of them
        if row.get("status") == "deleted" or active is False or (name or "").casefold() == "master" or (with_record_types is not None and obj not in with_record_types):
            continue
        record_types[obj].append({"name": name, "label": row.get("name") or name, "nodeId": row.get("nodeId")})
    # Lead, Opportunity and Case: get_dependencies using, sfType Process, on the record types (which sales,
    # support or lead process each record type uses), then using, sfType Custom Value, on those processes
    # (which stage or status values each process holds)
    rt_process = {}
    for row in common.read_ndjson(args.record_type_processes or []):
        related = row.get("related") or {}
        if related.get("type") == "Process" and related.get("active") is not False:
            rt_process[(row.get("node") or {}).get("nodeId")] = {"name": related.get("name") or related.get("apiName"),
                                                               "nodeId": related.get("nodeId")}
    process_values = defaultdict(set)
    for row in common.read_ndjson(args.process_values or []):
        related = row.get("related") or {}
        if related.get("type") == "Custom Value":
            process_values[(row.get("node") or {}).get("nodeId")].add(related.get("nodeId"))
    # get_dependencies where_used, sfType Record Type, on the value nodes: which record type uses which value
    usage = defaultdict(set)
    for row in common.read_ndjson(args.value_usage or []):
        related = row.get("related") or {}
        if related.get("type") == "Record Type":
            usage[related.get("nodeId")].add((row.get("node") or {}).get("nodeId"))
    done = set()
    for path in args.fields:
        for field in items_of(path):
            sf = field.get("sf") or {}
            obj = owner_api(field) or object_of(field)
            api = sf.get("apiName") or field.get("apiName")
            if obj not in objects:
                report.warn(f"{path}: field {obj}.{api} belongs to no object in the inventory; skipped")
                continue
            if obj in done:
                report.error(f"{obj} has two lifecycle fields in the results; keep one (lifecycle-candidates --choose)")
                continue
            rows = []
            for node in field.get("nodes", []):
                item = values.get(node)
                if item is None:
                    report.error(f"{obj}.{api}: value node {node} is not in the saved value results; read it with get_metadata_component")
                    continue
                details = item.get("nodeDetails") or {}
                if details.get("active") is False or item.get("status") == "deleted":
                    continue
                vsf = item.get("sf") or {}
                row = {"value": vsf.get("apiName") or item.get("name"), "nodeId": node}
                if item.get("name") and item["name"] != row["value"]:
                    row["label"] = item["name"]
                row.update(summary_flags(item.get("summary")))
                description = item.get("description")
                description = description.get("value") if isinstance(description, dict) else description
                if (description or "").strip().lower() == "default":  # how the dictionary marks a standard set's default value
                    row["default"] = True
                rows.append((details.get("order", 10 ** 6), row))
            if not rows:
                note = f"{obj}.{api}: no active values found; lifecycle field skipped"
                gap = {"about": f"{obj}.{api}", "note": note}
                if gap not in inv.setdefault("gaps", []):
                    inv["gaps"].append(gap)
                report.warn(note)
                continue
            rows.sort(key=lambda r: r[0])
            # a custom field's summary names its default value: "'Active' is the default value."
            match = re.search(r"'(.+?)' is the default value", field.get("summary") or "")
            if match:
                for _, row in rows:
                    if row["value"] == match.group(1) or row.get("label") == match.group(1):
                        row["default"] = True
            # the field says "Values are sorted alphabetically" when Salesforce sorts them; then the order is not the process's
            alphabetical = "sorted alphabetically" in (field.get("summary") or "").lower()
            lifecycle = {"field": api, "label": field.get("name") or api, "ordered": not alphabetical and all(o < 10 ** 6 for o, _ in rows),
                         "source": "metadata", "values": [r for _, r in rows]}
            if field.get("_id") or field.get("nodeId"):
                lifecycle["fieldNodeId"] = field.get("_id") or field.get("nodeId")
            help_text = (sf.get("helpText") or {}).get("value") if isinstance(sf.get("helpText"), dict) else sf.get("helpText")
            if help_text:
                lifecycle["helpText"] = help_text[:2000]
            if record_types.get(obj):
                lifecycle["recordTypes"] = []
                for rt in record_types[obj]:
                    entry = {k: v for k, v in rt.items() if v}
                    if obj in common.PROCESS_OBJECTS:
                        # the stage or status values come from the record type's process, not its picklist values
                        process = rt_process.get(rt["nodeId"])
                        if process and process["nodeId"] in process_values:
                            used = process_values[process["nodeId"]]
                            entry["process"] = process["name"]
                            entry["values"] = [r["value"] for _, r in rows if r["nodeId"] in used]
                    elif args.value_usage is not None:
                        used = usage.get(rt["nodeId"], set())
                        entry["values"] = [r["value"] for _, r in rows if r["nodeId"] in used]
                    lifecycle["recordTypes"].append(entry)
            objects[obj]["lifecycle"] = lifecycle
            done.add(obj)
            lifecycle_problems(objects[obj], report)
    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    if not report.errors:
        common.write_json(args.out or args.inventory, inv)
    return report.finish(f" {len(done)} lifecycle(s){'' if report.errors else ' written to ' + str(args.out or args.inventory)}.")


def cmd_focus(args):
    """One capability for the process of one object: the object, its master-detail children, and the
    objects that look up to it and to nothing else in scope; what it looks up to is shared."""
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    assign_roles(inv)
    objects = {o["apiName"]: o for o in inv["objects"]}
    focus = args.object
    if focus not in objects:
        raise SetupError(f"'{focus}' is not an object in the inventory")
    rels = [r for r in inv.get("relationships", []) if not r.get("polymorphic")]
    shared = common.dedupe([r["to"] for r in rels if r["from"] == focus and r["to"] != focus and r["to"] in objects
                            and objects[r["to"]].get("role") != "platform"])
    owned = [focus]
    for rel in rels:
        if rel["to"] != focus or rel["from"] == focus or rel["from"] not in objects:
            continue
        child = objects[rel["from"]]
        if child.get("role") in ("platform", "hub"):
            continue
        # a detail of the focus object, or a record that points only at it and at what it points at (a campaign member)
        others = [r["to"] for r in rels if r["from"] == rel["from"] and r["to"] not in (focus, rel["from"])]
        if rel.get("kind") == "master-detail" or all(o in shared or objects.get(o, {}).get("role") in ("platform", "hub") for o in others):
            owned.append(rel["from"])
    owned = common.dedupe(owned)
    shared = [a for a in common.dedupe(shared) if a not in owned]
    unassigned = [{"apiName": a, "reason": f"Not part of the {objects[focus]['name']} process"}
                  for a in objects if a not in owned and a not in shared and objects[a].get("role") not in ("platform", "hub")]
    stop = common.usage_stop(dict(inv, focus=focus))
    if stop:
        report.error(f"STOP {stop}")
        return report.finish(" Nothing written.")
    name = args.name or f"{objects[focus]['name']} process"
    proposal = {"capabilities": [{"id": common.slug(objects[focus]["name"]), "name": name, "origin": "inferred",
                                  "description": f"Everything done with {objects[focus]['name']} records, from creation to closure, and the objects that belong to them.",
                                  "objects": owned, "sharedObjects": shared,
                                  "evidence": [f"Focus object {focus}: the person asked for its process"]}],
                "unassigned": unassigned,
                "notes": f"One-object scope: {focus} with {len(owned) - 1} object(s) that belong to it; {len(shared)} shared."}
    inv["focus"] = focus
    common.write_json(args.inventory, inv)
    common.write_json(args.out, proposal)
    return report.finish(f" focus {focus}: {len(owned)} owned, {len(shared)} shared, {len(unassigned)} left out; proposal written to {args.out}.")


# ---------------------------------------------------------------- usage

def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def usage_block(usage, read_at):
    """The inventory's usage block (schemas/inventory.schema.json $defs/usage) from one get_component_usage
    item's usage. Telemetry that is missing stays null: it is never read as zero."""
    usage = usage or {}
    if usage.get("available") is False or usage.get("kind") not in (None, "object"):
        block = {"available": False, "total": None, "byRecordType": {}, "withoutRecordType": None, "lastCreated": None,
                 "lastModified": None, "net7": None, "net30": None, "windowDays": None, "trend": None, "readAt": read_at}
        reason = usage.get("reason") or (f"usage of kind {usage.get('kind')} has no record counts" if usage.get("kind") else "")
        if reason:
            block["reason"] = str(reason)[:500]
        return block
    records = usage.get("records") or {}
    total = _count(records.get("total"))
    by_rt = {}
    without = None
    for label, n in (records.get("byRecordType") or {}).items():
        if _count(n) is None:
            continue
        if label == common.WITHOUT_RECORD_TYPE:
            without = n
        else:
            by_rt[str(label)] = n
    velocity = usage.get("velocity") or {}
    live = velocity.get("dataAvailable") is True
    block = {"available": total is not None, "total": total, "byRecordType": by_rt, "withoutRecordType": without,
             "lastCreated": records.get("lastCreated") or None, "lastModified": records.get("lastModified") or None,
             "net7": _count(velocity.get("net7")) if live else None, "net30": _count(velocity.get("net30")) if live else None,
             "windowDays": _count(velocity.get("windowDays")) if live else None,
             "trend": (str(velocity.get("trend"))[:40] if velocity.get("trend") else None) if live else None,
             "readAt": read_at}
    if total is None:
        block["reason"] = "get_component_usage returned no record total"
    return block


def usage_items(path):
    """The items of a saved get_component_usage result: {items: [...]} (nodeIds), one {nodeId, usage}, or a list."""
    doc = common.load_json(path, "saved get_component_usage result")
    if isinstance(doc, dict) and isinstance(doc.get("items"), list):
        return doc["items"]
    if isinstance(doc, list):
        return doc
    return [doc]


def cmd_usage(args):
    report = Report()
    inv = common.load_json(args.inventory, "inventory")
    if args.basis:
        basis = args.basis
    elif args.scope:
        basis = common.scope_basis(common.load_json(args.scope, "scope"))
    elif inv.get("basis") in common.BASES:
        basis = inv["basis"]
    else:
        raise SetupError("say which basis the run uses: --basis usage|configuration, or --scope scope.json")
    read_at = args.read_at or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", read_at):
        raise SetupError(f"--read-at '{read_at}' is not a date (YYYY-MM-DD)")
    objects = {o["apiName"]: o for o in inv["objects"]}
    by_node = {o["nodeId"]: o for o in inv["objects"] if o.get("nodeId")}
    read = set()
    for path in args.results:
        for item in usage_items(path):
            if not isinstance(item, dict):
                continue
            usage = item.get("usage") or {}
            api = ((usage.get("object") or {}).get("apiName"))
            obj = by_node.get(str(item.get("nodeId"))) or objects.get(api)
            if obj is None:
                if item.get("error") or item.get("notFound"):
                    report.warn(f"{path}: {item.get('nodeId')} was not found: {item.get('error') or 'not found'}")
                continue  # a component that is not an inventory object (a record type read by mistake)
            obj["usage"] = usage_block(usage, read_at)
            if obj["usage"]["available"]:
                obj["hasRecords"] = obj["usage"]["total"] > 0
            read.add(obj["apiName"])
            lc = obj.get("lifecycle") or {}
            for rt in lc.get("recordTypes") or []:
                counts = obj["usage"]["byRecordType"]
                total = counts.get(rt.get("label")) if rt.get("label") in counts else counts.get(rt.get("name"))
                rt["usage"] = {"total": total if obj["usage"]["available"] else None}
                if obj["usage"]["available"] and total is None:
                    report.warn(f"{obj['apiName']}: record type {rt.get('label') or rt['name']} is not in the usage counts "
                                f"({', '.join(counts) or 'none'}); its records are unknown")
    missing = [a for a in objects if a not in read]
    for api in missing:
        report.warn(f"no usage was read for {api}; it counts as used. Read it with get_component_usage (nodeId "
                    f"{objects[api].get('nodeId') or 'unknown'}) and run this again")
    inv["basis"] = basis
    unavailable = [a for a in read if not objects[a]["usage"]["available"]]
    for api in unavailable:
        report.warn(f"usage of {api} is not available ({objects[api]['usage'].get('reason', 'no reason given')}); it counts as used")
    empty = [a for a in objects if a in read and objects[a]["usage"]["available"] and objects[a]["usage"]["total"] == 0]
    if basis == "usage" and empty:
        report.note(f"{common.NO_RECORDS_NOTE} (left off every box, named in notes): " + ", ".join(empty))
    for line in common.shape_errors(inv, SCHEMA):
        report.error(line)
    stop = common.usage_stop(inv)
    if not report.errors:
        common.write_json(args.out or args.inventory, inv)
    if stop:
        report.error(f"STOP {stop}")
    used = len(read) - len(empty) - len(unavailable)
    return report.finish(f" basis {basis}: usage read for {len(read)} of {len(objects)} object(s): {used} hold records, "
                         f"{len(empty)} hold none, {len(unavailable) + len(missing)} unknown;"
                         f"{'' if common.shape_errors(inv, SCHEMA) else ' written to ' + str(args.out or args.inventory)}.")


# ---------------------------------------------------------------- main

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Build, merge, group and check the object inventory.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("from-metadata", help="build an inventory from Elements NDJSON exports")
    p.add_argument("--objects", nargs="+", required=True, help="list_metadata_by_criteria part files")
    p.add_argument("--relationships", nargs="*", help="get_dependencies part files (where_used, relationship fields)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--with-records", nargs="*", help="part files of the same object list filtered to record_count > 0")
    group.add_argument("--all-have-records", action="store_true", help="the object list was already filtered to record_count > 0")
    p.add_argument("--only", nargs="+", help="keep only these API names (the person named the objects)")
    p.add_argument("--system", required=True)
    p.add_argument("--variant")
    p.add_argument("--ref-model", required=True)
    p.add_argument("--scope-note")
    p.add_argument("--hub-min", type=int, default=HUB_MIN_REFERRERS)
    p.add_argument("--basis", choices=common.BASES, help="the run's basis from scope.json (inventory.py usage sets it too)")
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("merge", help="merge partial inventories from the doc reader")
    p.add_argument("partials", nargs="+")
    p.add_argument("--hub-min", type=int, default=HUB_MIN_REFERRERS)
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("set-capabilities", help="apply a capability-grouper proposal")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--confirmed", action="store_true", help="mark every capability confirmed")
    p.add_argument("--max-top", type=int, default=10)
    p.add_argument("--max-objects", type=int, default=15)

    p = sub.add_parser("check", help="check an inventory")
    p.add_argument("inventory", type=Path)
    p.add_argument("--partial", action="store_true", help="a doc reader's partial inventory: skip the capability rules")
    p.add_argument("--max-top", type=int, default=10)
    p.add_argument("--max-objects", type=int, default=15)

    p = sub.add_parser("lifecycle-candidates", help="pick each object's status or stage picklist")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--fields", nargs="+", required=True, help="list_metadata_by_criteria Field part files")
    p.add_argument("--choose", nargs="*", help="Object.Field to use instead of the best-named candidate")
    p.add_argument("--out", type=Path, default=Path("metadata/lifecycle-fields.json"))

    p = sub.add_parser("lifecycle", help="write lifecycles from saved field and value results")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--fields", nargs="+", required=True, help="saved get_metadata_component results of the lifecycle fields (detail full)")
    p.add_argument("--values", nargs="+", required=True, help="saved get_metadata_component results of their value nodes (detail full)")
    p.add_argument("--record-types", nargs="*", help="list_metadata_by_criteria Record Type part files (active)")
    p.add_argument("--record-type-objects", nargs="*", help="saved get_org_health_detail results (objects_by_record_type): the objects with custom record types")
    p.add_argument("--value-usage", nargs="*", help="get_dependencies part files: where_used, sfType Record Type, on the value nodes")
    p.add_argument("--record-type-processes", nargs="*", help="Lead, Opportunity, Case: get_dependencies part files, using, sfType Process, on the record types")
    p.add_argument("--process-values", nargs="*", help="Lead, Opportunity, Case: get_dependencies part files, using, sfType Custom Value, on those processes")
    p.add_argument("--out", type=Path)

    p = sub.add_parser("focus", help="the capability proposal for one object's process")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--name")
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("usage", help="write each object's usage from saved get_component_usage results")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--results", nargs="+", required=True, help="saved get_component_usage results (nodeIds, 50 per call)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--basis", choices=common.BASES, help="the run's basis (overrides scope.json)")
    group.add_argument("--scope", type=Path, help="scope.json: its metadata.basis (or onlyWithRecords) gives the basis")
    p.add_argument("--read-at", help="the day usage was read (YYYY-MM-DD); today when left out")
    p.add_argument("--out", type=Path)

    args = parser.parse_args(argv)
    try:
        return {"from-metadata": cmd_from_metadata, "usage": cmd_usage, "merge": cmd_merge,
                "set-capabilities": cmd_set_capabilities, "check": cmd_check,
                "lifecycle-candidates": cmd_lifecycle_candidates, "lifecycle": cmd_lifecycle,
                "focus": cmd_focus}[args.command](args)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
