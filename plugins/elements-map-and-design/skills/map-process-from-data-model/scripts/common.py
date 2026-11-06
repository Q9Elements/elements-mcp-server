"""Helpers shared by the map-process-from-data-model scripts.

What every level-by-level process reader shares (outline rules, the boundary
labels, ids, files) is in the plugin's scripts/process_levels.py and is
re-exported here; this file adds what is particular to data models.

Standard library only; Python 3.8 or later. The shape checks reuse the
plugin's own validator (scripts/validate.py) so every file in the plugin is
checked against its JSON Schema the same way.
"""

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import process_levels  # noqa: E402  (the shared core of level-by-level process readers)
import validate  # noqa: E402  (the plugin's model validator)
from process_levels import (  # noqa: E402,F401  (re-exported for this skill's scripts)
    END, MODEL_ID, OUTLINE_SCHEMA, START, Findings, SetupError, dedupe, first_sentence, label_limits,
    load_json, model_id, norm, outline_boundary, outline_errors, read_csv, slug, split_list, write_json)

SCHEMAS = SKILL / "schemas"
DATA = SKILL / "data"
PLATFORM_CSV = DATA / "platform-objects.csv"
ARCHETYPES_CSV = DATA / "object-archetypes.csv"



# ---------------------------------------------------------------- files

from mcp_result import verify_rows

def read_ndjson(paths):
    rows = []
    for path in paths:
        try:
            evidence = verify_rows(path)
        except (OSError, ValueError) as exc:
            raise SetupError(str(exc))
        if evidence.get("failed"):
            raise SetupError(f"{path}: native coverage gaps: {evidence['failed']}")
        try:
            with open(path, encoding="utf-8-sig") as handle:
                for number, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except ValueError as exc:
                        raise SetupError(f"{path} line {number} is not JSON: {exc}")
        except OSError as exc:
            raise SetupError(f"cannot read {path}: {exc}")
    return rows


def load_schema(name):
    schema = load_json(SCHEMAS / name, "schema")
    validate.check_schema_keywords(schema, "#")
    return schema


def shape_errors(document, schema_name):
    """Check a document against one of this skill's schemas; return error lines."""
    return process_levels.shape_errors(document, SCHEMAS / schema_name)


# ---------------------------------------------------------------- text and ids

def words(label):
    """Words of a label or an API name: 'SalesAgreementProduct' -> ['Sales', 'Agreement', 'Product']."""
    text = re.sub(r"__c$|__r$", "", label or "")
    text = re.sub(r"^[A-Za-z0-9]+__", "", text)  # namespace prefix
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return [w for w in text.split() if w]


# ---------------------------------------------------------------- data files

def load_platform_rules(path=PLATFORM_CSV):
    rows = read_csv(Path(path), ["pattern", "match", "role", "reason"])
    for row in rows:
        if row["match"] not in ("exact", "prefix", "suffix"):
            raise SetupError(f"{Path(path).name}: match must be exact, prefix or suffix, not '{row['match']}'")
        if row["role"] not in ("platform", "hub"):
            raise SetupError(f"{Path(path).name}: role must be platform or hub, not '{row['role']}'")
    return rows


def platform_role(api_name, rules):
    """The role data/platform-objects.csv gives an API name, or None."""
    for row in rules:
        pattern, match = row["pattern"], row["match"]
        if match == "exact" and api_name == pattern:
            return row["role"]
        if match == "suffix" and api_name.endswith(pattern) and api_name != pattern:
            return row["role"]
        if match == "prefix" and api_name.startswith(pattern) and api_name != pattern:
            return row["role"]
    return None


def load_archetypes(path=ARCHETYPES_CSV):
    rows = read_csv(Path(path), ["archetype", "position", "name_endings", "typical_verbs", "guidance"])
    table = []
    default = None
    for row in rows:
        try:
            position = int(row["position"])
        except ValueError:
            raise SetupError(f"{Path(path).name}: position '{row['position']}' is not a whole number")
        endings = [[w.casefold() for w in ending.split()] for ending in split_list(row["name_endings"])]
        entry = {"archetype": row["archetype"], "position": position, "endings": endings,
                 "verbs": split_list(row["typical_verbs"])}
        if not endings:
            default = entry
        table.append(entry)
    if default is None:
        raise SetupError(f"{Path(path).name}: one row must have no name_endings (the default archetype)")
    return table, default


def archetype_of(name, table, default):
    """Match the longest name ending; an ending only applies when the name has words before it."""
    tokens = [w.casefold() for w in words(name)]
    best, best_len = default, 0
    for entry in table:
        for ending in entry["endings"]:
            n = len(ending)
            if n > best_len and len(tokens) > n and tokens[-n:] == ending:
                best, best_len = entry, n
    return best


# ---------------------------------------------------------------- capabilities

def shared_objects(inv, cap):
    """Objects a capability's steps may use without owning them: the ones it lists as shared,
    then every object its owned objects point at that is not platform. prepare_briefs.py offers
    these to the writer and check_coverage.py accepts them, so both use this one function."""
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    owned = set(cap.get("objects", []))
    shared = list(cap.get("sharedObjects", []))
    for rel in inv.get("relationships", []):
        if rel.get("polymorphic"):
            continue
        if rel["from"] in owned and rel["to"] not in owned and rel["to"] in objects:
            if objects[rel["to"]].get("role") != "platform":
                shared.append(rel["to"])
    return [a for a in dedupe(shared) if a in objects and a not in owned]


# ---------------------------------------------------------------- usage basis

# What decides which objects a run draws (scope.json metadata.basis, copied into the inventory as `basis`):
#   configuration  every object in scope, whether or not the org holds records of it (the only choice in a
#                  sandbox other than a full copy, whose records are test data or none);
#   usage          only objects that hold records: an object with none is left off every box and named in a
#                  note instead. Offered only for production or a full sandbox.
BASES = ("usage", "configuration")
WITHOUT_RECORD_TYPE = "*Without Record Type*"  # get_component_usage's bucket for records of the Master record type
NO_RECORDS_NOTE = "Configured but holding no records"  # the line that names objects left off a box under basis usage


def scope_basis(scope):
    """The basis a scope.json asks for. metadata.basis when set; otherwise derived from the older
    metadata.onlyWithRecords (true: usage; false or null: configuration)."""
    meta = (scope or {}).get("metadata") or {}
    if meta.get("basis") in BASES:
        return meta["basis"]
    return "usage" if meta.get("onlyWithRecords") is True else "configuration"


# scope.json metadata.orgType: what the person said the org is. Only production and a full sandbox (a full copy
# of production, records included) hold records worth reading; any other sandbox runs on configuration.
ORG_TYPES = ("production", "full-sandbox", "other-sandbox")
USAGE_ORG_TYPES = ("production", "full-sandbox")


def basis_problem(scope):
    """Why a scope's basis cannot be used, or None: usage needs a production org or a full sandbox."""
    meta = (scope or {}).get("metadata") or {}
    if (scope or {}).get("route") != "metadata" or scope_basis(scope) != "usage":
        return None
    if meta.get("orgType") not in USAGE_ORG_TYPES:
        return (f"basis usage needs a production org or a full sandbox, but metadata.orgType is "
                f"'{meta.get('orgType')}'; set the basis to configuration, and tell the person why")
    return None


def inventory_basis(inv):
    """The basis an inventory was built for; configuration when it does not say (every inventory before usage)."""
    return inv.get("basis") if inv.get("basis") in BASES else "configuration"


def object_used(obj, basis):
    """Whether an object counts as used for this basis: True, False, or None when its usage is unknown.

    Under configuration every object counts (True). Under usage, an object counts when its usage block
    (inventory.py usage, from get_component_usage) has a record total above zero; None when there is no
    usage block, the telemetry was unavailable or the total is missing. None is treated as used by every
    script, with a warning: missing telemetry is never read as zero records."""
    if basis != "usage":
        return True
    usage = (obj or {}).get("usage") or {}
    total = usage.get("total")
    if not usage.get("available") or not isinstance(total, int) or isinstance(total, bool):
        return None
    return total > 0


def record_type_used(rt, basis):
    """Like object_used for one record type of a lifecycle: False only under usage with a known total of 0."""
    if basis != "usage":
        return True
    total = ((rt or {}).get("usage") or {}).get("total")
    if not isinstance(total, int) or isinstance(total, bool):
        return None
    return total > 0


def unused_objects(inv, apis=None):
    """API names (in the order given, or the inventory's order) of objects the inventory's basis leaves out:
    usage basis and a known record total of 0. Empty under configuration."""
    basis = inventory_basis(inv)
    if basis != "usage":
        return []
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    names = list(apis) if apis is not None else list(objects)
    return [a for a in names if a in objects and object_used(objects[a], basis) is False]


def unknown_usage(inv, apis=None):
    """API names whose usage is unknown under basis usage (treated as used; say so)."""
    if inventory_basis(inv) != "usage":
        return []
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    names = list(apis) if apis is not None else list(objects)
    return [a for a in names if a in objects and object_used(objects[a], "usage") is None]


def usage_stop(inv):
    """The message to stop a run with, or None: under basis usage, a focus object (the object whose process
    was asked for) that holds no records would give an empty process."""
    focus = inv.get("focus")
    if inventory_basis(inv) != "usage" or not focus:
        return None
    obj = next((o for o in inv.get("objects", []) if o["apiName"] == focus), None)
    if obj is None or object_used(obj, "usage") is not False:
        return None
    read = (obj.get("usage") or {}).get("readAt")
    return (f"{obj['name']} ({focus}) holds no records in this org{' (read ' + read + ')' if read else ''}, so a process "
            f"based on usage would be empty. Run it on basis configuration instead (scope.json metadata.basis "
            f"\"configuration\", then inventory.py usage --basis configuration), or on an org that holds {obj['name']} records.")


def no_records_line(inv, apis):
    """'Configured but holding no records: X, Y' for the objects among apis that the basis leaves out, or None."""
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    left = unused_objects(inv, dedupe([a for a in apis if a in objects]))
    if not left:
        return None
    return f"{NO_RECORDS_NOTE}: " + ", ".join(objects[a]["name"] for a in left)


# ---------------------------------------------------------------- lifecycles

# Salesforce objects whose stage or status values are set per record type by a Process (sales process for
# Opportunity, support process for Case, lead process for Lead), not by the record type's picklist values.
PROCESS_OBJECTS = {"Lead", "Opportunity", "Case"}


def lifecycle_ready(api, lc):
    """Whether a level can be built on this lifecycle. An object in PROCESS_OBJECTS with custom record types
    needs each record type's process values (inventory.py lifecycle --record-type-processes --process-values);
    without them it stays an ordinary object on the steps that use it."""
    if api not in PROCESS_OBJECTS:
        return True
    return all(rt.get("process") for rt in lc.get("recordTypes") or [])


def lifecycle_plan(inv):
    """Which levels a lifecycle drives, worked out from the inventory alone, so prepare_briefs.py,
    build_model.py and status.py agree. Returns {capability id: plan}:

      {"capability", "object", "name", "field", "fieldLabel", "ordered", "values": [value rows],
       "level": the capability's level id ("top" with a focus object),
       "recordTypes": [{"name", "label", "level", "values": [value rows]}]}   (empty: no split level)

    A leaf capability is driven by its main lifecycle object: the owned object with a lifecycle (not in
    a Lead, Opportunity or Case whose record types have no process values) that the capability's other
    objects point at most; with a focus object, that object.
    With record types, the capability's level is a record-type split and each record type has a
    lifecycle level of its own, holding the values that record type uses."""
    objects = {o["apiName"]: o for o in inv.get("objects", [])}
    caps = inv.get("capabilities", [])
    parents = {c.get("parent") for c in caps if c.get("parent")}
    focus = inv.get("focus")
    basis = inventory_basis(inv)
    plans = {}
    for cap in caps:
        if cap["id"] in parents:
            continue
        owned = [a for a in cap.get("objects", []) if a in objects]
        inbound = {a: 0 for a in owned}
        for rel in inv.get("relationships", []):
            if rel["to"] in inbound and rel["from"] in inbound and rel["from"] != rel["to"]:
                inbound[rel["to"]] += 1
        candidates = [a for a in owned if objects[a].get("lifecycle") and lifecycle_ready(a, objects[a]["lifecycle"])
                      and object_used(objects[a], basis) is not False]  # basis usage: a lifecycle with no records drives no level
        if focus in owned:
            candidates = [focus] if focus in candidates else []
        if not candidates:
            continue
        api = sorted(candidates, key=lambda a: (-inbound[a], owned.index(a)))[0]
        lc = objects[api]["lifecycle"]
        level = "top" if focus else cap["id"]
        plan = {"capability": cap["id"], "object": api, "name": objects[api]["name"], "field": lc["field"],
                "fieldLabel": lc.get("label") or lc["field"], "ordered": bool(lc.get("ordered")),
                "values": lc["values"], "level": level, "recordTypes": []}
        used_levels = set()
        for rt in lc.get("recordTypes") or []:
            keep = set(rt.get("values") or [v["value"] for v in lc["values"]])
            rt_level = f"{cap['id']}--{slug(rt['name'], 40 - min(len(cap['id']), 30))}"[:48].rstrip("-")
            while rt_level in used_levels:
                rt_level = rt_level[:45] + f"-{len(used_levels)}"
            used_levels.add(rt_level)
            plan["recordTypes"].append({"name": rt["name"], "label": rt.get("label") or rt["name"], "level": rt_level,
                                        "values": [v for v in lc["values"] if v["value"] in keep]})
            if rt.get("process"):
                plan["recordTypes"][-1]["process"] = rt["process"]
            if record_type_used(rt, basis) is False:
                plan["recordTypes"][-1]["noRecords"] = True  # basis usage: still drawn (it is configuration), noted as empty
        plans[cap["id"]] = plan
    return plans


def lifecycle_levels(plans):
    """{level id: (plan, record type or None)} for every level built on a lifecycle (one box per value)."""
    levels = {}
    for plan in plans.values():
        if plan["recordTypes"]:
            for rt in plan["recordTypes"]:
                levels[rt["level"]] = (plan, rt)
        else:
            levels[plan["level"]] = (plan, None)
    return levels


def lifecycle_cover(plan, rt=None):
    """The lifecycle a level must follow, in the form process_levels.lifecycle_level_findings checks."""
    values = rt["values"] if rt else plan["values"]
    return {"object": plan["object"], "name": plan["name"], "field": plan["field"], "fieldLabel": plan["fieldLabel"],
            "ordered": plan["ordered"], "recordType": rt["label"] if rt else None,
            "values": [{k: v for k, v in val.items() if k in ("value", "label", "closed", "won", "default")} for val in values]}


# ---------------------------------------------------------------- where each level came from

def generator_levels(inv):
    """The levels Elements' org-to-process is meant to write, in plan order (route metadata only): every record
    type's lifecycle level (generate_process_map, source org_object, comes first), and with a focus object every
    lifecycle level, since a one-object run on route metadata stands in for elements-org-to-process."""
    if inv.get("route") != "metadata":
        return []
    return [level for level, (_, rt) in lifecycle_levels(lifecycle_plan(inv)).items() if rt is not None or inv.get("focus")]


def fallback_levels(scope, inv, levels_dir):
    """The levels meant to come from Elements' org-to-process that the stage-5 fallback (a process-level-writer)
    wrote instead, as [(level id, reason)]. A level counts once its outline exists without "source": "org-to-process".
    The reason is scope.json generatorFallback.levels[<level>], else on a focus run generatorFallback.run (why
    elements-org-to-process did not draw the object), else 'reason not recorded'."""
    record = (scope or {}).get("generatorFallback")
    record = record if isinstance(record, dict) else {}
    reasons = record.get("levels") if isinstance(record.get("levels"), dict) else {}
    found = []
    for level in generator_levels(inv):
        outline = process_levels.read_or_none(Path(levels_dir) / f"{level}.json")
        if not isinstance(outline, dict) or outline.get("source") == "org-to-process":
            continue
        reason = reasons.get(level) or (record.get("run") if inv.get("focus") else None)
        found.append((level, reason or "reason not recorded in scope.json generatorFallback"))
    return found


def fallback_summary(found):
    """The fallback levels on one line, grouped by reason: "a, b (reason one); c (reason two)"."""
    by_reason = {}
    for level, reason in found:
        by_reason.setdefault(reason, []).append(level)
    return "; ".join(f"{', '.join(levels)} ({reason})" for reason, levels in by_reason.items())
