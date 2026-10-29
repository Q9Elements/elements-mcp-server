#!/usr/bin/env python3
"""Check a business-architecture model file before anything is drawn from it.

Usage:
  python3 validate.py MODEL.json [--for DIAGRAM_TYPE]

Checks, in order:
  1. Shape: the file matches schemas/ba-model.schema.json.
  2. Model rules the schema cannot express: ids are unique and every id a field
     points at exists and is the right kind of item; drill-down levels and
     capability trees have no loops; every line joins two activities on the
     same level and appears once; steps belong to an automation and their
     connectors stay on one logic level; names are unique where boxes are
     matched by name; RASCI is only given to human roles; integration patterns
     and step elements are ones data/integration-patterns.csv and
     data/automation-elements.csv list; the model is not empty.
  3. Diagram fit (with --for): the model has the section that diagram type
     needs, as data/diagram-types.csv lists.
  4. Readability: the validator rows of data/readability-rubric.csv, reported
     at the row's severity. Deleting a row switches its check off.

Prints one line per finding, then a summary line with the counts. Exit 0: no
errors (warnings may remain). Exit 1: the model has errors. Exit 2: setup
problem: the model file, the schema or a data file could not be read or does
not fit this script, or the command line was wrong.

Standard library only; Python 3.8 or later.
"""

import argparse
import csv
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PLUGIN / "schemas" / "ba-model.schema.json"
TYPES_PATH = PLUGIN / "data" / "diagram-types.csv"
RUBRIC_PATH = PLUGIN / "data" / "readability-rubric.csv"
PATTERNS_PATH = PLUGIN / "data" / "integration-patterns.csv"
ELEMENTS_PATH = PLUGIN / "data" / "automation-elements.csv"
MECHANISMS_PATH = PLUGIN / "data" / "integration-mechanisms.csv"
TIMING_PATH = PLUGIN / "data" / "integration-timing.csv"

START, END = "START", "END"

# JSON Schema keywords this script enforces, and keywords it may ignore.
# A schema edit that uses any other keyword stops the script, so the schema
# can never ask for a check that silently does not run.
SUPPORTED_KEYWORDS = {
    "$ref", "type", "required", "properties", "additionalProperties", "enum",
    "const", "pattern", "minLength", "maxLength", "minimum", "maximum",
    "items", "minItems", "oneOf",
}
ANNOTATION_KEYWORDS = {
    "$schema", "$id", "$defs", "$comment", "title", "description", "examples",
    "default",
}
TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}
CHECKERS = {"validator", "reviewer", "layout-check"}
SEVERITIES = {"warn", "error"}
API_NAME = re.compile(
    r"__(c|e|r|mdt|x|b)\b"                          # custom suffixes: Order_Requested__e
    r"|^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$"  # Object.Field
    r"|^[A-Za-z0-9]+(_[A-Za-z0-9]+)+$"               # Lead_Assignment
)
PLAIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


class SetupError(Exception):
    """The schema or a data file is unreadable or does not fit this script."""


class Findings:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.notes = []

    def error(self, where, message, rule=""):
        self.errors.append(f"ERROR {rule + ' ' if rule else ''}{where}: {message}")

    def warn(self, where, message, rule=""):
        self.warnings.append(f"WARN {rule + ' ' if rule else ''}{where}: {message}")


# ---------------------------------------------------------------- loading

def load_json_strict(path):
    """Load JSON, refusing duplicate keys (a later key would silently win)."""

    def no_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"key {json.dumps(key)} appears twice in one object")
            seen[key] = value
        return seen

    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=no_duplicates)


def read_csv(path, columns):
    """Read a data CSV as stripped rows, skipping blank rows; tolerate Excel's BOM."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = [h.strip() for h in (reader.fieldnames or [])]
            missing = [c for c in columns if c not in header]
            if missing:
                raise SetupError(f"{path.name}: missing column(s) {', '.join(missing)}")
            rows = []
            for raw in reader:
                row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None}
                if any(row.values()):
                    rows.append(row)
            return rows
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def split_list(cell):
    return [part.strip() for part in cell.split("|") if part.strip()]


def content_sections(schema):
    """Top-level arrays whose items are objects with an id hold the model's items."""
    sections = []
    for name, spec in schema["properties"].items():
        if spec.get("type") != "array" or "items" not in spec:
            continue
        items = spec["items"]
        while "$ref" in items:
            items = resolve_ref(schema, items["$ref"])
        if items.get("type") == "object" and "id" in items.get("properties", {}):
            sections.append(name)
    return sections


def load_schema():
    try:
        schema = load_json_strict(SCHEMA_PATH)
    except (OSError, ValueError) as exc:
        raise SetupError(f"cannot read {SCHEMA_PATH}: {exc}")
    check_schema_keywords(schema, "#")
    return schema


def check_schema_keywords(node, where):
    if not isinstance(node, dict):
        raise SetupError(f"schema {where}: expected an object")
    for key, value in node.items():
        if key not in SUPPORTED_KEYWORDS and key not in ANNOTATION_KEYWORDS:
            raise SetupError(f"schema {where}: keyword '{key}' is not supported by validate.py")
        if key == "additionalProperties" and not isinstance(value, bool):
            raise SetupError(f"schema {where}: additionalProperties must be true or false")
        if key == "type":
            for name in value if isinstance(value, list) else [value]:
                if name not in TYPE_CHECKS:
                    raise SetupError(f"schema {where}: unknown type '{name}'")
        if key in ("properties", "$defs"):
            for name, sub in value.items():
                check_schema_keywords(sub, f"{where}/{key}/{name}")
        elif key == "items":
            check_schema_keywords(value, f"{where}/items")
        elif key == "oneOf":
            for index, sub in enumerate(value):
                check_schema_keywords(sub, f"{where}/oneOf/{index}")


def load_diagram_types(sections):
    types = {}
    for row in read_csv(TYPES_PATH, ["diagram_type", "create_map_type", "needs", "also_uses"]):
        types[row["diagram_type"]] = {"needs": row["needs"], "also_uses": split_list(row["also_uses"])}
    for name, spec in types.items():
        for section in [spec["needs"]] + spec["also_uses"]:
            if section not in sections:
                raise SetupError(f"{TYPES_PATH.name}: '{name}' names unknown section '{section}'")
    return types


def load_patterns():
    return {row["pattern_id"] for row in read_csv(PATTERNS_PATH, ["pattern_id", "name"])}


def load_elements():
    return {row["element"] for row in read_csv(ELEMENTS_PATH, ["element", "resource", "resource_type"])}


def load_validator_rules(types):
    rules = []
    for row in read_csv(RUBRIC_PATH, ["rule_id", "applies_to", "checked_by", "severity", "threshold", "rule"]):
        rule_id = row["rule_id"]
        if row["checked_by"] not in CHECKERS:
            raise SetupError(f"{RUBRIC_PATH.name}: rule {rule_id} has checked_by '{row['checked_by']}'; use validator, reviewer or layout-check")
        if row["severity"] not in SEVERITIES:
            raise SetupError(f"{RUBRIC_PATH.name}: rule {rule_id} has severity '{row['severity']}'; use warn or error")
        applies = split_list(row["applies_to"])
        for name in applies:
            if name != "*" and name not in types:
                raise SetupError(f"{RUBRIC_PATH.name}: rule {rule_id} applies to unknown diagram type '{name}'")
        if row["checked_by"] != "validator":
            continue
        if rule_id not in RULE_CHECKS:
            raise SetupError(f"{RUBRIC_PATH.name}: rule {rule_id} says checked_by=validator but validate.py has no check for it")
        check, needs_threshold = RULE_CHECKS[rule_id]
        threshold = None
        if needs_threshold:
            try:
                threshold = int(row["threshold"])
            except ValueError:
                raise SetupError(f"{RUBRIC_PATH.name}: rule {rule_id} needs a whole-number threshold")
        rules.append((rule_id, applies, row["severity"], check, threshold))
    return rules


# ---------------------------------------------------------------- 1. shape

def item_label(path, index, item):
    if isinstance(item, dict) and isinstance(item.get("id"), str) and PLAIN_ID.match(item["id"]):
        return f"{path}[{item['id']}]"
    return f"{path}[{index}]"


def kind_of(value):
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if TYPE_CHECKS[name](value):
            return name
    return type(value).__name__


def resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise SetupError(f"schema: only local $ref values are supported, got '{ref}'")
    node = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SetupError(f"schema: $ref '{ref}' does not resolve")
        node = node[part]
    return node


def full_match(pattern, value):
    """JSON Schema patterns are searches; '$' must not accept a trailing newline."""
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.search(pattern, value) is not None


def check_one_of(value, branches, path, root, findings):
    results = []
    for branch in branches:
        trial = Findings()
        check_shape(value, branch, path, root, trial)
        results.append((branch, trial.errors))
    passing = [r for r in results if not r[1]]
    if len(passing) == 1:
        return
    if len(passing) > 1:
        findings.error(path, "matches more than one allowed form")
        return
    # No branch passed. Report the branch whose "type" constant the value names.
    named = None
    consts = []
    for branch, errors in results:
        target = branch
        while "$ref" in target:
            target = resolve_ref(root, target["$ref"])
        const = target.get("properties", {}).get("type", {}).get("const")
        if const is not None:
            consts.append(const)
            if isinstance(value, dict) and value.get("type") == const:
                named = errors
    if named is not None:
        findings.errors.extend(named)
    elif consts:
        findings.error(path, "type must be one of " + ", ".join(json.dumps(c) for c in consts))
    else:
        findings.error(path, "does not match any allowed form")


def check_shape(value, node, path, root, findings):
    if "$ref" in node:
        check_shape(value, resolve_ref(root, node["$ref"]), path, root, findings)
        node = {k: v for k, v in node.items() if k != "$ref"}
    if "oneOf" in node:
        check_one_of(value, node["oneOf"], path, root, findings)

    where = path or "model"
    if "type" in node:
        allowed = node["type"] if isinstance(node["type"], list) else [node["type"]]
        if not any(TYPE_CHECKS[t](value) for t in allowed):
            findings.error(where, f"should be {' or '.join(allowed)}, not {kind_of(value)}")
            return
    if "const" in node and value != node["const"]:
        findings.error(where, f"must be {json.dumps(node['const'])}")
        return
    if "enum" in node and value not in node["enum"]:
        options = ", ".join(json.dumps(o) for o in node["enum"])
        findings.error(where, f"{json.dumps(value)} is not one of {options}")
        return

    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            findings.error(where, "is empty" if node["minLength"] == 1 else f"is shorter than {node['minLength']} characters")
        if "maxLength" in node and len(value) > node["maxLength"]:
            findings.error(where, f"is longer than {node['maxLength']} characters")
        if "pattern" in node and not full_match(node["pattern"], value):
            findings.error(where, f"{json.dumps(value)} does not match the pattern {node['pattern']}")
    if TYPE_CHECKS["number"](value):
        if "minimum" in node and value < node["minimum"]:
            findings.error(where, f"must be at least {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            findings.error(where, f"must be at most {node['maximum']}")
    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            findings.error(where, f"needs at least {node['minItems']} item(s)")
        if "items" in node:
            for index, item in enumerate(value):
                check_shape(item, node["items"], item_label(path, index, item), root, findings)
    if isinstance(value, dict):
        for name in node.get("required", []):
            if name not in value:
                findings.error(where, f"is missing required field '{name}'")
        properties = node.get("properties", {})
        for name, sub in value.items():
            if name in properties:
                check_shape(sub, properties[name], f"{path}.{name}" if path else name, root, findings)
            elif node.get("additionalProperties", True) is False:
                close = difflib.get_close_matches(name, list(properties), n=1)
                hint = f"; did you mean '{close[0]}'?" if close else ""
                findings.error(where, f"unknown field {json.dumps(name)}{hint}")


# ---------------------------------------------------------------- 2. model rules

def by_id(model, section):
    return {item["id"]: item for item in model.get(section, []) if "id" in item}


def find_loops(parent_of):
    """Return each loop in a child -> parent map once, as a list of ids."""
    loops, settled = [], set()
    for start in parent_of:
        path, seen, node = [], {}, start
        while node in parent_of and node not in settled:
            if node in seen:
                loops.append(path[seen[node]:])
                break
            seen[node] = len(path)
            path.append(node)
            node = parent_of[node]
        settled.update(path)
    return loops


def level_name(parent):
    return f"the level under '{parent}'" if parent else "the top level"


def step_level(step):
    """The logic level a step is drawn on: its automation's own level, or the drill-down of its parent step."""
    return (step["automation"], step.get("parent"))


def step_level_name(level):
    automation, parent = level
    return f"the level under step '{parent}'" if parent else f"the logic level of '{automation}'"


def norm(text):
    return " ".join(text.split()).casefold()


def check_unique_names(groups, findings):
    """groups: lists of (section, items, group_of, place) whose boxes can share a diagram level."""
    for members in groups:
        seen = {}
        for section, items, group_of, place in members:
            for index, item in enumerate(items):
                key = (group_of(item), norm(item["name"]))
                where = item_label(section, index, item)
                if key in seen:
                    findings.error(where, f"has the same name as {seen[key]}{place(item)}; readers and the diagram reviewer tell boxes apart by name, so make it distinct, such as 'ERP Account'")
                else:
                    seen[key] = where


def check_model_rules(model, sections, patterns, findings, elements=None):
    owner = {}
    for section in sections:
        for index, item in enumerate(model.get(section, [])):
            if "id" not in item:
                continue
            where = item_label(section, index, item)
            if item["id"] in (START, END):
                findings.error(where, f"'{item['id']}' is reserved for flows; choose another id")
            elif item["id"] in owner:
                findings.error(where, f"id '{item['id']}' is already used in {owner[item['id']]}; ids must be unique across the model")
            else:
                owner[item["id"]] = section

    roles = by_id(model, "roles")
    activities = by_id(model, "activities")
    entities = by_id(model, "entities")
    systems = by_id(model, "systems")
    automations = by_id(model, "automations")
    capabilities = by_id(model, "capabilities")

    def must_be(where, ref, pool, what):
        if ref not in pool:
            findings.error(where, f"'{ref}' is not {what}")
            return False
        return True

    # Activities: roles, parent, what they use.
    usable = {**entities, **systems, **automations}
    for index, act in enumerate(model.get("activities", [])):
        where = item_label("activities", index, act)
        for j, assignment in enumerate(act.get("roles", [])):
            if must_be(f"{where}.roles[{j}].role", assignment["role"], roles, "a role id"):
                if assignment.get("rasci") and roles[assignment["role"]]["kind"] != "human":
                    findings.error(f"{where}.roles[{j}].rasci", f"RASCI applies to human roles only, and '{assignment['role']}' is a {roles[assignment['role']]['kind']} role")
        if "parent" in act:
            if act["parent"] == act["id"]:
                findings.error(f"{where}.parent", "an activity cannot be its own parent")
            else:
                must_be(f"{where}.parent", act["parent"], activities, "an activity id")
        for j, ref in enumerate(act.get("uses", [])):
            must_be(f"{where}.uses[{j}]", ref, usable, "an entity, system or automation id")
    parent_of = {a["id"]: a["parent"] for a in activities.values() if a.get("parent") in activities and a["parent"] != a["id"]}
    for loop in find_loops(parent_of):
        findings.error("activities", "drill-down levels loop: " + " -> ".join(loop + [loop[0]]))

    # Flows: ends exist, START/END the right way round, same level, no repeats.
    seen_flows = {}
    for index, flow in enumerate(model.get("flows", [])):
        where = item_label("flows", index, flow)
        src, dst = flow["from"], flow["to"]
        ok = True
        if src == END:
            findings.error(f"{where}.from", "END can only be a 'to'")
            ok = False
        elif src != START:
            ok = must_be(f"{where}.from", src, activities, "an activity id or START") and ok
        if dst == START:
            findings.error(f"{where}.to", "START can only be a 'from'")
            ok = False
        elif dst != END:
            ok = must_be(f"{where}.to", dst, activities, "an activity id or END") and ok
        if src == START and dst == END:
            findings.error(where, "joins START straight to END with no activity between")
            ok = False
        if ok and src in activities and dst in activities:
            a, b = activities[src].get("parent"), activities[dst].get("parent")
            if a != b:
                findings.error(where, f"joins '{src}' on {level_name(a)} to '{dst}' on {level_name(b)}; a line can only join activities on the same level")
        sets = flow.get("sets")
        if sets and must_be(f"{where}.sets.entity", sets["entity"], entities, "an entity id"):
            values = [v["value"] for v in entities[sets["entity"]].get("lifecycle", {}).get("values", [])]
            if not values:
                findings.error(f"{where}.sets", f"entity '{sets['entity']}' has no lifecycle, so no line can set its value")
            elif sets["value"] not in values:
                findings.error(f"{where}.sets.value", f"'{sets['value']}' is not one of the lifecycle values of '{sets['entity']}' ({', '.join(values)})")
        key = (src, dst, norm(flow.get("label", "")))
        if key in seen_flows:
            findings.error(where, f"repeats {seen_flows[key]}: same ends and label")
        else:
            seen_flows[key] = where

    # Data model, architecture, interaction lines.
    for section, pool, what in (
        ("relationships", entities, "an entity id"),
        ("integrations", systems, "a system id"),
    ):
        for index, item in enumerate(model.get(section, [])):
            where = item_label(section, index, item)
            must_be(f"{where}.from", item["from"], pool, what)
            must_be(f"{where}.to", item["to"], pool, what)
    for index, item in enumerate(model.get("integrations", [])):
        if "pattern" in item and item["pattern"] not in patterns:
            findings.error(f"{item_label('integrations', index, item)}.pattern", f"'{item['pattern']}' is not a pattern_id in {PATTERNS_PATH.name} ({', '.join(sorted(patterns))})")
    # The middleware an exchange passes through, and the automations and objects that carry it (a system's drill-down).
    for index, item in enumerate(model.get("integrations", [])):
        where = item_label("integrations", index, item)
        if "via" in item and must_be(f"{where}.via", item["via"], systems, "a system id"):
            if systems[item["via"]].get("kind") != "middleware":
                findings.error(f"{where}.via", f"'{item['via']}' is a {systems[item['via']].get('kind')} system; 'via' names a middleware system")
            if item["via"] in (item.get("from"), item.get("to")):
                findings.error(f"{where}.via", f"'{item['via']}' is also an end of the integration")
        for j, ref in enumerate(item.get("automations", [])):
            must_be(f"{where}.automations[{j}]", ref, automations, "an automation id")
        for j, ref in enumerate(item.get("objects", [])):
            must_be(f"{where}.objects[{j}]", ref, entities, "an entity id")
    for index, item in enumerate(model.get("systems", [])):
        if "placement" in item and item.get("kind") != "middleware":
            findings.error(f"{item_label('systems', index, item)}.placement", "placement applies to middleware systems only")
    # System architecture: groups are one level deep, and a line joins two different cards.
    system_parent = {}
    for index, item in enumerate(model.get("systems", [])):
        if "parent" in item:
            where = item_label("systems", index, item)
            if must_be(f"{where}.parent", item["parent"], systems, "a system id"):
                system_parent[item["id"]] = item["parent"]
    for loop in find_loops(system_parent):
        findings.error(f"systems[{loop[0]}].parent", "groups loop: " + " -> ".join(loop + [loop[0]]))
    for child, group in system_parent.items():
        if group in system_parent and group != child:
            findings.error(f"systems[{child}].parent", f"'{group}' is itself a member of '{system_parent[group]}'; groups are one level deep, so make '{child}' a member of '{system_parent[group]}' or of no group")
    for index, item in enumerate(model.get("integrations", [])):
        where = item_label("integrations", index, item)
        a, b = item.get("from"), item.get("to")
        if a == b:
            findings.error(where, "joins a system to itself; an integration joins two systems")
        elif system_parent.get(a) == b or system_parent.get(b) == a:
            findings.error(where, "joins a group to one of its own members; join the member to the other system it exchanges data with")
    touchable = {**automations, **entities, **systems, **roles}
    steps = by_id(model, "steps")
    seen_interactions = {}
    for index, item in enumerate(model.get("interactions", [])):
        where = item_label("interactions", index, item)
        src, dst = item["from"], item["to"]
        if src == END:
            findings.error(f"{where}.from", "END can only be a 'to'")
        elif src != START:
            must_be(f"{where}.from", src, touchable, "an automation, entity, system or role id, or START")
        if dst == START:
            findings.error(f"{where}.to", "START can only be a 'from'")
        elif dst != END:
            must_be(f"{where}.to", dst, touchable, "an automation, entity, system or role id, or END")
        if src == START and dst == END:
            findings.error(where, "joins START straight to END with nothing between")
        if "fromStep" in item:
            step = steps.get(item["fromStep"])
            if step is None:
                findings.error(f"{where}.fromStep", f"'{item['fromStep']}' is not a step id")
            elif step["automation"] != src:
                findings.error(f"{where}.fromStep", f"'{item['fromStep']}' is a step of '{step['automation']}', not of '{src}'")
        key = (src, dst, item["kind"], norm(item.get("label", "")))
        if key in seen_interactions:
            findings.error(where, f"repeats {seen_interactions[key]}: same ends, kind and label")
        else:
            seen_interactions[key] = where

    # Steps: the automation they belong to, their drill-down parent, their element, what they call.
    if elements is None:
        elements = load_elements()
    for index, step in enumerate(model.get("steps", [])):
        where = item_label("steps", index, step)
        must_be(f"{where}.automation", step["automation"], automations, "an automation id")
        if step["element"] not in elements:
            close = difflib.get_close_matches(step["element"], sorted(elements), n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            findings.error(f"{where}.element", f"'{step['element']}' is not an element in {ELEMENTS_PATH.name}{hint}")
        if "parent" in step:
            if step["parent"] == step["id"]:
                findings.error(f"{where}.parent", "a step cannot be its own parent")
            elif must_be(f"{where}.parent", step["parent"], steps, "a step id"):
                if steps[step["parent"]]["automation"] != step["automation"]:
                    findings.error(f"{where}.parent", f"'{step['parent']}' belongs to automation '{steps[step['parent']]['automation']}', not '{step['automation']}'")
        if "calls" in step:
            must_be(f"{where}.calls", step["calls"], automations, "an automation id")
    step_parent = {s["id"]: s["parent"] for s in steps.values() if s.get("parent") in steps and s["parent"] != s["id"]}
    for loop in find_loops(step_parent):
        findings.error("steps", "drill-down levels loop: " + " -> ".join(loop + [loop[0]]))

    # Connectors: ends exist, START/END the right way round, same logic level, no repeats.
    seen_connectors = {}
    for index, conn in enumerate(model.get("connectors", [])):
        where = item_label("connectors", index, conn)
        src, dst = conn["from"], conn["to"]
        ok = True
        if src == END:
            findings.error(f"{where}.from", "END can only be a 'to'")
            ok = False
        elif src != START:
            ok = must_be(f"{where}.from", src, steps, "a step id or START") and ok
        if dst == START:
            findings.error(f"{where}.to", "START can only be a 'from'")
            ok = False
        elif dst != END:
            ok = must_be(f"{where}.to", dst, steps, "a step id or END") and ok
        if src == START and dst == END:
            findings.error(where, "joins START straight to END with no step between")
            ok = False
        if ok and src in steps and dst in steps:
            a, b = step_level(steps[src]), step_level(steps[dst])
            if a != b:
                findings.error(where, f"joins '{src}' on {step_level_name(a)} to '{dst}' on {step_level_name(b)}; a line can only join steps on the same level")
        key = (src, dst, norm(conn.get("label", "")))
        if key in seen_connectors:
            findings.error(where, f"repeats {seen_connectors[key]}: same ends and label")
        else:
            seen_connectors[key] = where

    # Capabilities: parent, loops, what realises them.
    realisers = {**activities, **entities, **systems, **automations}
    for index, cap in enumerate(model.get("capabilities", [])):
        where = item_label("capabilities", index, cap)
        if "parent" in cap:
            if cap["parent"] == cap["id"]:
                findings.error(f"{where}.parent", "a capability cannot be its own parent")
            else:
                must_be(f"{where}.parent", cap["parent"], capabilities, "a capability id")
        for j, ref in enumerate(cap.get("realisedBy", [])):
            must_be(f"{where}.realisedBy[{j}]", ref, realisers, "an activity, entity, system or automation id")
    cap_parent = {c["id"]: c["parent"] for c in capabilities.values() if c.get("parent") in capabilities and c["parent"] != c["id"]}
    for loop in find_loops(cap_parent):
        findings.error("capabilities", "capability tree loops: " + " -> ".join(loop + [loop[0]]))

    # Level notes: the level they sit on (its parent activity) and the box they sit beside, on that level.
    for index, note in enumerate(model.get("levelNotes", [])):
        where = f"levelNotes[{index}]"
        parent = note.get("parent")
        if parent is not None and not must_be(f"{where}.parent", parent, activities, "an activity id"):
            continue
        if parent is not None and not any(a.get("parent") == parent for a in activities.values()):
            findings.error(f"{where}.parent", f"'{parent}' has no child level: no activity has it as parent")
        if "near" in note and must_be(f"{where}.near", note["near"], activities, "an activity id"):
            if activities[note["near"]].get("parent") != parent:
                findings.error(f"{where}.near", f"'{note['near']}' is not on {level_name(parent)}, where the note is")

    for index, gap in enumerate(model.get("gaps", [])):
        if "about" in gap:
            must_be(f"gaps[{index}].about", gap["about"], owner, "an id in this model")

    # Names: boxes are told apart by name, so names must differ where boxes share a level.
    whole = lambda _: None
    nowhere = lambda _: ""
    check_unique_names([
        [("activities", model.get("activities", []), lambda a: a.get("parent"), lambda a: f" on {level_name(a.get('parent'))}")],
        [("capabilities", model.get("capabilities", []), lambda c: c.get("parent"), lambda c: " under the same parent")],
        [("roles", model.get("roles", []), whole, nowhere)],
        [(section, model.get(section, []), whole, nowhere) for section in ("entities", "systems", "automations")],
        [("steps", model.get("steps", []), step_level, lambda s: f" on {step_level_name(step_level(s))}")],
    ], findings)

    refs = {}
    for index, act in enumerate(model.get("activities", [])):
        if "diagramRef" in act:
            key = (act["diagramRef"]["diagramId"], act["diagramRef"]["key"])
            where = item_label("activities", index, act)
            if key in refs:
                findings.error(f"{where}.diagramRef", f"points at the same box as {refs[key]}")
            else:
                refs[key] = where

    if not any(model.get(section) for section in sections) and not model.get("gaps"):
        findings.error("model", "has no content; add at least one item, or record in gaps why nothing was found")


# ---------------------------------------------------------------- 3. diagram fit

def check_fit(model, diagram_type, types, findings):
    needs = types[diagram_type]["needs"]
    if not model.get(needs):
        findings.error("model", f"a {diagram_type} diagram needs at least one item in '{needs}'")


# ---------------------------------------------------------------- 4. readability

def levels_of(model):
    levels = defaultdict(list)
    for act in model.get("activities", []):
        levels[act.get("parent")].append(act)
    return levels


def level_where(parent):
    return f"activities[{parent}] child level" if parent else "top level"


def rule_max_activities_per_level(model, threshold, report):
    for parent, acts in levels_of(model).items():
        if len(acts) > threshold:
            report(level_where(parent), f"has {len(acts)} activities; the rubric allows {threshold}. Move some into a child level")


def rule_activity_connected(model, threshold, report):
    touched = set()
    for flow in model.get("flows", []):
        touched.update((flow["from"], flow["to"]))
    for act in model.get("activities", []):
        if act["id"] not in touched:
            report(f"activities[{act['id']}]", "has no line in or out")


def rule_decisions_labelled(model, threshold, report):
    outgoing = defaultdict(list)
    for flow in model.get("flows", []):
        if flow["from"] != flow["to"]:
            outgoing[flow["from"]].append(flow)
    for source, flows in outgoing.items():
        if source == START or len(flows) < 2:
            continue
        unlabelled = [f for f in flows if not f.get("label", "").strip()]
        if unlabelled:
            report(f"activities[{source}]", f"has {len(flows)} outgoing lines and {len(unlabelled)} without a label; label each with its condition")


def rule_levels_start(model, threshold, report):
    activities = by_id(model, "activities")
    started = {activities[f["to"]].get("parent") for f in model.get("flows", [])
               if f["from"] == START and f["to"] in activities}
    for parent in levels_of(model):
        if parent not in started:
            report(level_where(parent), "has no line from START; add one to show what starts this level")


def rule_capability_depth(model, threshold, report):
    caps = by_id(model, "capabilities")
    for cap_id in caps:
        depth, node, seen = 1, cap_id, {cap_id}
        while caps[node].get("parent") in caps and caps[node]["parent"] not in seen:
            node = caps[node]["parent"]
            seen.add(node)
            depth += 1
        if depth == threshold + 1:
            report(f"capabilities[{cap_id}]", f"is at level {depth}; a capability map draws {threshold} levels, so it and anything below it will not be drawn. Fold it into its parent or draw that branch as a map of its own")


def rule_entity_related(model, threshold, report):
    entities = model.get("entities", [])
    if len(entities) < 2:
        return
    related = set()
    for rel in model.get("relationships", []):
        related.update((rel["from"], rel["to"]))
    for ent in entities:
        if ent["id"] not in related:
            report(f"entities[{ent['id']}]", "has no relationship to any other entity")


def rule_entity_count(model, threshold, report):
    count = len(model.get("entities", []))
    if count > threshold:
        report("entities", f"has {count} entities; the rubric allows {threshold} on one data model, so it will be hard to read. Split it into several maps by area, or leave out objects the reader does not need")


MANY_ENDS = {"zero-or-many", "one-or-many", "many"}
ONE_ENDS = {"zero-or-one", "exactly-one", "one"}


def rule_relationship_ends(model, threshold, report):
    for index, rel in enumerate(model.get("relationships", [])):
        where = f"relationships[{rel.get('id') or index}]"
        from_many, to_many = {"one-to-one": (False, False), "one-to-many": (False, True),
                              "many-to-one": (True, False), "many-to-many": (True, True)}[rel["cardinality"]]
        for end, many in (("fromEnd", from_many), ("toEnd", to_many)):
            value = rel.get(end)
            if value in MANY_ENDS and not many:
                report(where, f"{end} is {value} but the cardinality {rel['cardinality']} says one at that end; change one of them")
            elif value in ONE_ENDS and many:
                report(where, f"{end} is {value} but the cardinality {rel['cardinality']} says many at that end; change one of them")


def rule_role_used(model, threshold, report):
    used = {r["role"] for a in model.get("activities", []) for r in a.get("roles", [])}
    for item in model.get("interactions", []):
        used.update((item["from"], item["to"]))
    for role in model.get("roles", []):
        if role["id"] not in used:
            report(f"roles[{role['id']}]", "is not assigned to any activity or interaction")


def rule_business_names(model, threshold, report):
    for section in ("activities", "roles", "capabilities"):
        for item in model.get(section, []):
            if API_NAME.search(item["name"]):
                report(f"{section}[{item['id']}]", f"name {json.dumps(item['name'])} looks like an API name; use the business name readers know")


def logic_levels(model):
    levels = defaultdict(list)
    for step in model.get("steps", []):
        levels[step_level(step)].append(step)
    return levels


def logic_where(level):
    automation, parent = level
    return f"steps[{parent}] drill-down level" if parent else f"automations[{automation}] logic level"


def rule_max_steps_per_level(model, threshold, report):
    for level, steps in logic_levels(model).items():
        if len(steps) > threshold:
            report(logic_where(level), f"has {len(steps)} steps; the rubric allows {threshold}. Move a loop body or a long branch into a drill-down")


def rule_step_connected(model, threshold, report):
    touched = set()
    for conn in model.get("connectors", []):
        touched.update((conn["from"], conn["to"]))
    for step in model.get("steps", []):
        if step["id"] not in touched:
            report(f"steps[{step['id']}]", "has no line in or out")


def rule_step_outcomes_labelled(model, threshold, report):
    outgoing = defaultdict(list)
    for conn in model.get("connectors", []):
        if conn["from"] != conn["to"] and conn["from"] != START:
            outgoing[conn["from"]].append(conn)
    for source, conns in outgoing.items():
        if len(conns) < 2:
            continue
        unlabelled = [c for c in conns if not c.get("label", "").strip()]
        if unlabelled:
            report(f"steps[{source}]", f"has {len(conns)} outgoing lines and {len(unlabelled)} without a label; label each with its condition")


def rule_one_start_step(model, threshold, report):
    for level, steps in logic_levels(model).items():
        if level[1] is not None:
            continue
        starts = [s for s in steps if s["element"] == "start"]
        if len(starts) != 1:
            report(logic_where(level), f"has {len(starts)} Start steps; an automation's logic begins at exactly one")


def rule_step_business_names(model, threshold, report):
    for section in ("automations", "steps"):
        for item in model.get(section, []):
            if API_NAME.search(item["name"]):
                report(f"{section}[{item['id']}]", f"name {json.dumps(item['name'])} looks like an API name; use the label people see in Salesforce")


def rule_card_attributes(model, threshold, report):
    for section in ("automations", "steps"):
        for item in model.get(section, []):
            count = len(item.get("attributes", []))
            if count > threshold:
                report(f"{section}[{item['id']}]", f"has {count} attributes; the rubric allows {threshold}, so the card would be very tall. Keep the ones that explain the logic")


def rule_summary_length(model, threshold, report):
    for section in ("automations", "steps"):
        for item in model.get(section, []):
            if len(item.get("summary", "")) > threshold:
                report(f"{section}[{item['id']}]", f"summary is {len(item['summary'])} characters; the rubric allows {threshold} for a card footer")


def rule_automation_in_chain(model, threshold, report):
    automations = model.get("automations", [])
    if len(automations) < 2:
        return
    joined = set()
    for item in model.get("interactions", []):
        joined.update((item["from"], item["to"]))
    for automation in automations:
        if automation["id"] not in joined:
            report(f"automations[{automation['id']}]", "is not joined to any other item by an interaction, so it stands alone on the chain level")


# ---------------------------------------------------------------- system architecture rules

def arch_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def arch_levels(model):
    levels = defaultdict(list)
    for item in model.get("systems", []):
        levels[item.get("parent")].append(item)
    return levels


def arch_where(parent):
    return f"systems[{parent}] drill-down" if parent else "top level"


def rule_systems_per_level(model, threshold, report):
    for parent, items in arch_levels(model).items():
        if len(items) > threshold:
            report(arch_where(parent), f"shows {len(items)} systems; the rubric allows {threshold}. Put related systems in a group (a system others name as their parent), which draws as one card with a drill-down")


def chain_members(model):
    """The drill-down of each system whose integrations list automations or objects, column by column: the systems
    (column 1), the middleware (column 2), the automations and the objects, and the integrations drawn there. A
    middleware's drill-down shows the systems it carries and its own integrations' automations and objects; any other
    system's shows its integrations' middleware, automations and objects. Hubs, groups and group members have none."""
    systems = by_id(model, "systems")
    hubs = {i for i, s in systems.items() if s.get("hub")}
    grouped = {s.get("parent") for s in systems.values() if s.get("parent")} | {i for i, s in systems.items() if s.get("parent")}
    out = {}
    for sid, system in systems.items():
        if sid in hubs or sid in grouped:
            continue
        own = [i for i in model.get("integrations", []) if sid in (i.get("from"), i.get("to")) and (i.get("automations") or i.get("objects"))]
        carried = [i for i in model.get("integrations", []) if i.get("via") == sid]
        if not own and not carried:
            continue
        first, middle = [], []
        if system.get("kind") == "middleware":
            middle.append(sid)
            for i in carried + own:
                for end in (i.get("from"), i.get("to")):
                    if end != sid and end not in hubs and end in systems and end not in first:
                        first.append(end)
        else:
            first.append(sid)
            for i in own:
                for other in (i.get("via"), i.get("to") if i.get("from") == sid else i.get("from")):
                    if other and other != sid and other not in hubs and other in systems and other not in middle:
                        middle.append(other)
        autos, objects = [], []
        for i in own:
            autos += [a for a in i.get("automations", []) if a not in autos]
            objects += [o for o in i.get("objects", []) if o not in objects]
        out[sid] = {"systems": first, "middleware": middle, "automations": autos, "objects": objects,
                    "integrations": [i for i in own] + [i for i in carried if i not in own]}
    return out


def rule_drilldown_cards(model, threshold, report):
    for sid, chain in chain_members(model).items():
        count = len(chain["systems"]) + len(chain["middleware"]) + len(chain["automations"]) + len(chain["objects"])
        if count > threshold:
            report(f"systems[{sid}] drill-down", f"shows {count} cards (systems, middleware, automations and objects); the rubric allows {threshold}. "
                   "Keep the automations that carry the exchange and leave out the ones that only read configuration")


def rule_system_integrated(model, threshold, report):
    parent_of = {s["id"]: s.get("parent") for s in model.get("systems", [])}
    touched = set()
    for item in model.get("integrations", []):
        for end in (item["from"], item["to"], item.get("via")):   # a middleware the data passes through is joined too
            if end is None:
                continue
            touched.add(end)
            if parent_of.get(end):
                touched.add(parent_of[end])
    for parent, items in arch_levels(model).items():
        if len(items) < 2:
            continue
        for item in items:
            if item["id"] not in touched:
                report(f"systems[{item['id']}]", "has no integration, so its card stands alone; add how data reaches it or leaves it, or leave it out")


def rule_integration_labelled(model, threshold, report):
    for index, item in enumerate(model.get("integrations", [])):
        if not (item.get("label") or item.get("technology") or item.get("pattern")):
            report(item_label("integrations", index, item), "has no label, technology or pattern, so its line will say nothing about how the data moves")


def arch_kind_of(model):
    systems = {s["id"]: s for s in model.get("systems", [])}

    def kind(ident):
        item = systems.get(ident, {})
        own = item.get("kind")
        group = systems.get(item.get("parent"), {})
        return {own, group.get("kind")}
    return kind


def rule_pattern_direction(model, threshold, report):
    patterns = {row["pattern_id"]: row for row in arch_csv(PATTERNS_PATH)}
    kind = arch_kind_of(model)
    for index, item in enumerate(model.get("integrations", [])):
        row = patterns.get(item.get("pattern"))
        end = (row or {}).get("salesforce_end", "")
        if not end or item.get("direction") == "two-way":
            continue
        ident = item[end]
        if "salesforce" not in kind(ident):
            other = "to" if end == "from" else "from"
            if "salesforce" in kind(item[other]):
                report(item_label("integrations", index, item), f"follows {row['name']}, where Salesforce is the {'caller' if end == 'from' else 'receiver'}, but Salesforce is at the other end. Swap 'from' and 'to' if the data moves the other way, or choose the pattern that fits")
            else:
                report(item_label("integrations", index, item), f"follows {row['name']}, a pattern with Salesforce as the {'caller' if end == 'from' else 'receiver'}, but neither end is a Salesforce system")


def mechanism_for(pattern, technology, rows):
    """The data/integration-mechanisms.csv row of this pattern whose match covers most of the technology text."""
    best = None
    for row in rows:
        if row["pattern_id"] != pattern or not row.get("match"):
            continue
        found = re.search(row["match"], technology, re.IGNORECASE)
        if found:
            length = len(found.group(0))
            if best is None or length > best[0]:
                best = (length, row)
    return best[1] if best else None


def rule_mechanism_fit(model, threshold, report):
    rows = arch_csv(MECHANISMS_PATH)
    for index, item in enumerate(model.get("integrations", [])):
        if not item.get("pattern") or not item.get("technology"):
            continue
        row = mechanism_for(item["pattern"], item["technology"], rows)
        if row and row["fit"] == "suboptimal":
            better = [r["mechanism"] for r in rows if r["pattern_id"] == item["pattern"] and r["fit"] == "best"]
            report(item_label("integrations", index, item), f"uses {row['mechanism']}, which Well-Architected rates suboptimal for this pattern: {row['note']}. Recommended: {', '.join(better)}")


def rule_timing_pattern(model, threshold, report):
    patterns = {row["pattern_id"]: row for row in arch_csv(PATTERNS_PATH)}
    for index, item in enumerate(model.get("integrations", [])):
        row = patterns.get(item.get("pattern"))
        if not row or not item.get("timing") or not row.get("timing"):
            continue
        allowed = split_list(row["timing"])
        if item["timing"] not in allowed:
            report(item_label("integrations", index, item), f"is {item['timing']}, but {row['name']} is {' or '.join(allowed)}. Check the timing or the pattern")


def rule_footer_icons(model, threshold, report):
    for item in model.get("systems", []):
        count = len(item.get("footerIcons", []))
        if count > threshold:
            report(f"systems[{item['id']}]", f"has {count} footer icons; the rubric allows {threshold}, so only the first {threshold} are drawn")


def rule_system_attributes(model, threshold, report):
    for item in model.get("systems", []):
        count = len(item.get("attributes", []))
        if count > threshold:
            report(f"systems[{item['id']}]", f"has {count} attributes; the rubric allows {threshold}, so the card would be very tall. Keep the main components, or make the system a group")


RULE_CHECKS = {
    "R01": (rule_max_activities_per_level, True),
    "R02": (rule_activity_connected, False),
    "R03": (rule_decisions_labelled, False),
    "R04": (rule_levels_start, False),
    "R05": (rule_capability_depth, True),
    "R06": (rule_entity_related, False),
    "R07": (rule_role_used, False),
    "R08": (rule_business_names, False),
    "R18": (rule_max_steps_per_level, True),
    "R19": (rule_step_connected, False),
    "R20": (rule_step_outcomes_labelled, False),
    "R21": (rule_one_start_step, False),
    "R22": (rule_step_business_names, False),
    "R23": (rule_card_attributes, True),
    "R24": (rule_summary_length, True),
    "R25": (rule_automation_in_chain, False),
    "R30": (rule_entity_count, True),
    "R31": (rule_relationship_ends, False),
    "R40": (rule_systems_per_level, True),
    "R41": (rule_system_integrated, False),
    "R42": (rule_integration_labelled, False),
    "R43": (rule_pattern_direction, False),
    "R44": (rule_mechanism_fit, False),
    "R45": (rule_timing_pattern, False),
    "R46": (rule_footer_icons, True),
    "R47": (rule_system_attributes, True),
    "R51": (rule_drilldown_cards, True),
}


def check_readability(model, diagram_type, types, rules, findings):
    if diagram_type:
        active = {diagram_type}
    else:
        active = {name for name, spec in types.items() if model.get(spec["needs"])}
    for rule_id, applies, severity, check, threshold in rules:
        if "*" in applies or active.intersection(applies):
            sink = findings.error if severity == "error" else findings.warn
            check(model, threshold, lambda where, msg, r=rule_id, s=sink: s(where, msg, rule=r))


# ---------------------------------------------------------------- main

def summary_counts(model, sections):
    if not isinstance(model, dict):
        return ""
    inferred = 0
    for section in sections:
        items = model.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            inferred += item.get("inferred") is True
            for nested in ("fields", "roles"):
                children = item.get(nested)
                if isinstance(children, list):
                    inferred += sum(1 for c in children if isinstance(c, dict) and c.get("inferred") is True)
    gaps = model.get("gaps")
    gap_count = len(gaps) if isinstance(gaps, list) else 0
    return f" {inferred} item(s) marked inferred, {gap_count} gap(s) recorded."


def run_checks(model_path, diagram_type=None):
    """Run every check on one model file. Returns (exit_code, lines): 0 pass, 1 errors, 2 setup problem."""
    try:
        schema = load_schema()
        sections = content_sections(schema)
        types = load_diagram_types(sections)
        patterns = load_patterns()
        rules = load_validator_rules(types)
    except SetupError as exc:
        return 2, [f"SETUP {exc}"]
    if diagram_type is not None and diagram_type not in types:
        return 2, [f"SETUP unknown diagram type {diagram_type}; data/diagram-types.csv has {', '.join(sorted(types))}"]

    try:
        model = load_json_strict(model_path)
    except OSError as exc:
        return 2, [f"SETUP cannot read {model_path}: {exc}"]
    except (ValueError, RecursionError) as exc:
        return 2, [f"SETUP {model_path} is not valid JSON: {exc}"]

    findings = Findings()
    try:
        check_shape(model, schema, "", schema, findings)
        if findings.errors:
            findings.notes.append("NOTE the model rules and readability checks run once the errors above are fixed")
        else:
            check_model_rules(model, sections, patterns, findings)
            if diagram_type:
                check_fit(model, diagram_type, types, findings)
            if not findings.errors:
                check_readability(model, diagram_type, types, rules, findings)
    except SetupError as exc:
        return 2, [f"SETUP {exc}"]
    except RecursionError:
        return 2, [f"SETUP {model_path} is nested too deeply to check"]

    lines = findings.errors + findings.warnings + findings.notes
    errors, warnings = len(findings.errors), len(findings.warnings)
    verdict = "FAIL" if errors else "PASS"
    lines.append(f"{verdict}: {errors} error(s), {warnings} warning(s).{summary_counts(model, sections)}")
    return (1 if errors else 0), lines


def gate(model_path, diagram_type):
    """The drawing gate: layout scripts call this before planning, so nothing is drawn from a model that fails
    validation. Prints nothing and returns 0 when the model passes (warnings are the validator's own report);
    otherwise prints the validator's lines and a REFUSED line and returns the validator's exit code."""
    code, lines = run_checks(model_path, diagram_type)
    if code == 0:
        return 0
    stream = sys.stderr if code == 2 else sys.stdout
    for line in lines:
        print(line, file=stream)
    print(f"REFUSED the model fails validate.py --for {diagram_type}; fix the model (or send it back to whoever wrote it) "
          "and plan again", file=stream)
    return code


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
        sys.stderr.reconfigure(errors="backslashreplace")
    try:
        types = load_diagram_types(content_sections(load_schema()))
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="Check a business-architecture model file.")
    parser.add_argument("model", help="path to the model JSON file")
    parser.add_argument("--for", dest="diagram_type", choices=sorted(types), help="also check the model has what this diagram type needs")
    args = parser.parse_args(argv)

    code, lines = run_checks(args.model, args.diagram_type)
    for line in lines:
        print(line, file=sys.stderr if line.startswith("SETUP") else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
