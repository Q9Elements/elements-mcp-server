#!/usr/bin/env python3
"""Build a business-architecture data model from Salesforce objects in the Elements Metadata Dictionary.

Usage:
  python3 build_data_model.py build --objects OBJECTS.json --relationships REL.ndjson [REL.ndjson ...]
                                    --fields FIELDS.ndjson [FIELDS.ndjson ...] --out MODEL.json --title TEXT
                                    [--description TEXT] [--ref-model ID] [--fields-per-entity N]
  python3 build_data_model.py neighbours --objects OBJECTS.json --relationships REL.ndjson [...] [--top N]
  python3 build_data_model.py merge BASE.json ADDITION.json --out MODEL.json

Inputs, all saved by the draw-data-model skill from Elements tools:
  OBJECTS.json   the objects in scope, as search_metadata found them: [{"nodeId", "name", "apiName", "sfType"}]
  REL.ndjson     get_dependencies rows for those nodeIds (lookingFor where_used, fieldTypes relationship): one
                 row per Lookup, Master detail or Hierarchy field that points at an object in scope
  FIELDS.ndjson  list_metadata_by_criteria rows for metadataList ["Field"], filtered by full_api_name
                 starting "<ApiName>/" per object (or every field of the org): name, API name, subtype, required

build       Writes the model: one entity per object (standard or custom from its type), its key fields (the
            record name or number, required fields, relationship fields to other objects in scope, then the
            rest, up to --fields-per-entity, default 6, the same as the drawing shows), and one relationship
            per relationship field between two objects in scope: master-detail or lookup, a required lookup
            drawn with an exactly-one end at the parent, a role label when the field's label is not just the
            parent's name ("Partner Account"). System and audit fields (data/system-fields.csv) are left out.
neighbours  Lists objects outside the scope that hold relationship fields pointing at objects in scope, most
            connected first, so the person can choose to add some.
merge       Adds to BASE (usually the model read back from a drawn data model) the entities of ADDITION it does
            not have, matched by API name or else by name, and every relationship of ADDITION that touches an added
            entity. Used when amending: build ADDITION from the new objects together with the objects already on
            the map, so the relationships between old and new objects are found.

Exit 0: done. Exit 1: an input has a problem the output describes. Exit 2: setup problem.
Standard library only; Python 3.8 or later.
"""

from mcp_result import hydrate, require_complete, verify_rows

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SYSTEM_FIELDS_PATH = PLUGIN / "data" / "system-fields.csv"
KINDS = {"lookup": "lookup", "master detail": "master-detail", "master-detail": "master-detail", "hierarchy": "lookup"}
STATUS_WORDS = ("status", "stage", "type", "priority")


class InputError(Exception):
    pass


def norm(text):
    return " ".join((text or "").split()).casefold()


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return require_complete(hydrate(json.load(handle)))
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot read {path}: {exc}")


def read_ndjson(paths):
    rows = []
    for path in paths:
        try:
            evidence = verify_rows(path)
        except (OSError, ValueError) as exc:
            raise InputError(str(exc))
        if evidence.get("failed"):
            raise InputError(f"{path}: dependency/source coverage gaps: {evidence['failed']}")
        try:
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except ValueError as exc:
                            raise InputError(f"{path} line {number}: not JSON ({exc})")
        except OSError as exc:
            raise InputError(f"cannot read {path}: {exc}")
    return rows


def system_fields():
    try:
        with open(SYSTEM_FIELDS_PATH, newline="", encoding="utf-8-sig") as handle:
            return {row["api_name"].strip() for row in csv.DictReader(handle) if row.get("api_name")}
    except OSError as exc:
        print(f"SETUP cannot read {SYSTEM_FIELDS_PATH}: {exc}", file=sys.stderr)
        sys.exit(2)


def entity_id(api_name, used):
    base = re.sub(r"[^A-Za-z0-9]+", "-", api_name).strip("-").lower()[:60] or "object"
    ident, n = base, 2
    while ident in used:
        ident = f"{base}-{n}"
        n += 1
    used.add(ident)
    return ident


def load_objects(path):
    objects = read_json(path)
    if not isinstance(objects, list) or not objects:
        raise InputError(f"{path}: expected a non-empty list of objects")
    for item in objects:
        if not isinstance(item, dict) or not item.get("apiName") or not item.get("name"):
            raise InputError(f"{path}: every object needs name and apiName: {item}")
    return objects


def field_rows(rows):
    """Fields by object API name, from list_metadata_by_criteria rows (fullApiName 'Object/Field')."""
    out = defaultdict(list)
    for row in rows:
        sf = row.get("sf") or {}
        full = sf.get("fullApiName") or ""
        if "/" not in full:
            continue
        obj, api = full.split("/", 1)
        details = row.get("nodeDetails") or {}
        out[obj].append({"name": row.get("name") or api, "apiName": sf.get("apiName") or api,
                         "subtype": details.get("subtype") or "", "required": details.get("required") == "Applied"})
    return out


def relationship_rows(rows, scope):
    """(child API, field API, field label, kind, parent API) for relationship fields between objects in scope."""
    out, seen = [], set()
    for row in rows:
        parent = (row.get("node") or {}).get("apiName")
        child = (row.get("carryingObject") or {}).get("apiName") or (row.get("related") or {}).get("object")
        related = row.get("related") or {}
        field = related.get("apiName")
        if not parent or not child or not field:
            continue
        key = (child, field, parent)
        if key in seen:
            continue
        seen.add(key)
        kind = KINDS.get(norm(related.get("fieldType")), "reference")
        out.append({"child": child, "field": field, "label": related.get("name") or field, "kind": kind,
                    "parent": parent, "inScope": parent in scope and child in scope})
    return out


def bare_label(label):
    """A relationship field's label without the ' Name' or ' ID' Salesforce adds ("Account Name" -> "Account")."""
    text = " ".join((label or "").split())
    return re.sub(r"\s+(Name|ID|Id)$", "", text)


def build(objects, relationships, fields, title, description, ref_model, per_entity):
    skip = system_fields()
    scope = {o["apiName"] for o in objects}
    used, ids = set(), {}
    for item in objects:
        ids[item["apiName"]] = entity_id(item["apiName"], used)
    names = {o["apiName"]: " ".join(o["name"].split()) for o in objects}
    rels = [r for r in relationship_rows(relationships, scope) if r["inScope"] and r["field"] not in skip]
    fk = defaultdict(dict)
    for rel in rels:
        fk[rel["child"]][rel["field"]] = rel["parent"]
    by_object = field_rows(fields)
    entities, gaps, required_fk = [], [], set()
    for item in objects:
        api = item["apiName"]
        rows, labels = [], set()
        for f in by_object.get(api, []):
            if f["apiName"] in skip or f["subtype"] == "Id" or norm(f["name"]) in labels:
                continue  # a second field with the same label (ForecastCategory, ForecastCategoryName) adds nothing on a card
            labels.add(norm(f["name"]))
            rows.append(f)
        if not rows:
            gaps.append({"about": ids[api], "note": f"No fields were found for {api}; its card shows none. Download its fields "
                                                    f"(full_api_name starts with '{api}/') and build again"})
        primary = next((f for f in rows if f["apiName"] == "Name"), None) or next(
            (f for f in rows if norm(f["subtype"]) == "auto number"), None)

        def rank(f):
            if f is primary:
                return 0
            if f["required"]:
                return 1
            if f["apiName"] in fk[api]:
                return 2
            if any(w in norm(f["name"]) for w in STATUS_WORDS) and norm(f["subtype"]) == "picklist":
                return 3
            return 4

        chosen = sorted(enumerate(rows), key=lambda pair: (rank(pair[1]), pair[0]))[:per_entity]
        out_fields = []
        for _, f in chosen:
            field = {"name": f["name"], "apiName": f["apiName"]}
            subtype = f["subtype"]
            if f["apiName"] in fk[api]:
                parent = fk[api][f["apiName"]]
                kind = "Master-Detail" if norm(subtype) == "master detail" else "Lookup"
                field["type"] = f"{kind}({names.get(parent, parent)})"
                field["key"] = "foreign"
                if f["required"]:
                    required_fk.add((api, f["apiName"]))
            elif subtype:
                field["type"] = subtype[:100]
            if f is primary:
                field["key"] = "primary"
            if f["required"] and f is not primary:
                field["required"] = True
            out_fields.append(field)
        for f in rows:
            if f["apiName"] in fk[api] and f["required"]:
                required_fk.add((api, f["apiName"]))
        entity = {"id": ids[api], "name": names[api], "apiName": api,
                  "kind": "custom" if "custom" in norm(item.get("sfType")) else "standard"}
        if out_fields:
            entity["fields"] = out_fields
        entities.append(entity)
    pair_count = Counter(frozenset((r["child"], r["parent"])) for r in rels)
    relationships_out = []
    for rel in rels:
        out = {"from": ids[rel["parent"]], "to": ids[rel["child"]], "cardinality": "one-to-many", "kind": rel["kind"],
               "field": f"{rel['child']}.{rel['field']}", "evidence": [f"{rel['child']}.{rel['field']}"]}
        label = bare_label(rel["label"])
        if rel["child"] == rel["parent"] or pair_count[frozenset((rel["child"], rel["parent"]))] > 1 \
                or norm(label) != norm(names[rel["parent"]]):
            out["label"] = label[:200]
        if rel["kind"] == "lookup" and (rel["child"], rel["field"]) in required_fk:
            out["fromEnd"] = "exactly-one"
        relationships_out.append(out)
    model = {"schemaVersion": "1.0",
             "meta": {"title": title[:80], "author": "draw-data-model (org route, build_data_model.py)",
                      "sources": [{"kind": "metadata", "ref": ref_model or "Elements Metadata Dictionary"}]},
             "entities": entities}
    if description:
        model["meta"]["description"] = description[:5000]
    if relationships_out:
        model["relationships"] = relationships_out
    if gaps:
        model["gaps"] = gaps
    return model


def neighbours(objects, relationships, top):
    """Objects outside the scope with relationship fields into it. A field that points at three or more objects
    in scope (WhatId, ParentId, TargetId) is polymorphic: listed, but not counted, so activity and system objects
    that can point at anything do not crowd out the objects that belong to the model."""
    scope = {o["apiName"] for o in objects}
    rels = [r for r in relationship_rows(relationships, scope) if r["parent"] in scope and r["child"] not in scope]
    targets = Counter((r["child"], r["field"]) for r in rels)
    links = defaultdict(list)
    score = Counter()
    for rel in rels:
        polymorphic = targets[(rel["child"], rel["field"])] >= 3
        links[rel["child"]].append(f"{rel['field']} -> {rel['parent']}" + (" (polymorphic)" if polymorphic else ""))
        if not polymorphic:
            score[rel["child"]] += 1
    ranked = sorted(links, key=lambda api: (-score[api], -len(links[api]), api))[:top]
    return [{"apiName": api, "links": score[api], "fields": links[api]} for api in ranked]


def merge(base, addition):
    """BASE plus the entities of ADDITION it lacks and the relationships of ADDITION that touch them."""
    out = json.loads(json.dumps(base))
    out.setdefault("entities", [])
    by_api = {norm(e.get("apiName")): e["id"] for e in out["entities"] if e.get("apiName")}
    by_name = {norm(e["name"]): e["id"] for e in out["entities"]}
    used = {e["id"] for e in out["entities"]} | {r.get("id") for r in out.get("relationships", []) if r.get("id")}
    id_of, added = {}, []
    for entity in addition.get("entities", []):
        found = by_api.get(norm(entity.get("apiName"))) if entity.get("apiName") else None
        found = found or by_name.get(norm(entity["name"]))
        if found:
            id_of[entity["id"]] = found
            continue
        new_id = entity["id"] if entity["id"] not in used else entity_id(entity["id"], used)
        used.add(new_id)
        id_of[entity["id"]] = new_id
        out["entities"].append(dict(entity, id=new_id))
        added.append(new_id)
    count = 0
    for rel in addition.get("relationships", []):
        a, b = id_of.get(rel["from"]), id_of.get(rel["to"])
        if a is None or b is None or (a not in added and b not in added):
            continue
        item = dict(rel, **{"from": a, "to": b})
        if item.get("id") in used:
            item.pop("id")
        out.setdefault("relationships", []).append(item)
        count += 1
    sources = out.setdefault("meta", {}).setdefault("sources", [])
    for source in addition.get("meta", {}).get("sources", []):
        if source not in sources:
            sources.append(source)
    return out, added, count


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a data model from Salesforce objects in Elements.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    p.add_argument("--objects", required=True)
    p.add_argument("--relationships", nargs="+", required=True)
    p.add_argument("--fields", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--ref-model", default="")
    p.add_argument("--fields-per-entity", type=int, default=6)
    p = sub.add_parser("neighbours")
    p.add_argument("--objects", required=True)
    p.add_argument("--relationships", nargs="+", required=True)
    p.add_argument("--top", type=int, default=15)
    p = sub.add_parser("merge")
    p.add_argument("base")
    p.add_argument("addition")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "merge":
            model, added, count = merge(read_json(args.base), read_json(args.addition))
            Path(args.out).write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"WROTE {args.out}: added {len(added)} entities ({', '.join(added) or 'none'}) and {count} relationships")
            return 0
        objects = load_objects(args.objects)
        relationships = read_ndjson(args.relationships)
        if args.command == "build":
            if len(args.title) < 2:
                raise InputError("--title needs at least 2 characters")
            model = build(objects, relationships, read_ndjson(args.fields), args.title, args.description,
                          args.ref_model, max(0, args.fields_per_entity))
            Path(args.out).write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"WROTE {args.out}: {len(model['entities'])} entities, {len(model.get('relationships', []))} relationships")
            for gap in model.get("gaps", []):
                print(f"GAP {gap['note']}")
            return 0
        for item in neighbours(objects, relationships, args.top):
            print(f"{item['apiName']}: {item['links']} direct link(s): {', '.join(item['fields'])}")
        return 0
    except InputError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
