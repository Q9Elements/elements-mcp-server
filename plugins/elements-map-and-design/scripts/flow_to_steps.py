#!/usr/bin/env python3
"""Turn a Salesforce Flow or Process Builder definition into a logic fragment for an interaction flow.

Usage:
  python3 flow_to_steps.py FLOW.flow-meta.xml --automation-id ID [--api-name NAME] [--ref-model-id ID] [--out FRAGMENT.json]

A Flow's XML lists every element (Get Records, Decision, Loop, Update Records ...) and every connector
between them, so its logic can be read exactly instead of interpreted. This script writes one fragment
(the format scripts/build_interaction_model.py merges into a model):

  automation  the flow itself: name, type, API name, description, attributes for its chain card
  steps       one per element, plus a Start step; the element kind comes from the flow_xml column of
              data/automation-elements.csv; attributes list the object, conditions and fields
  connectors  the lines between steps on one level; START into the Start step; END where a path stops
  gaps        what could not be placed (elements not reachable from the start, jumps out of a loop)
  hints       what the flow reads, writes, publishes and calls, and which step does it, so a chain
              line can leave the step that causes it

A loop's body becomes a drill-down level under the Loop step: its steps get the loop as their parent.
The body's line in reads "For each item" and its lines back to the Loop card "Next item"; the Loop
card's own line on reads "After last item". The drawing links the body's lines to the Loop card's.

Exit 0: written. Exit 1: the file is not a flow, or cannot be read. Exit 2: setup or command line problem.
Standard library only; Python 3.8 or later.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
ELEMENTS_PATH = PLUGIN / "data" / "automation-elements.csv"
STYLE_PATH = PLUGIN / "data" / "style-interaction.csv"

START, END = "START", "END"
LOOP_EACH_LABEL = "For each item"  # a loop body's line in
LOOP_NEXT_LABEL = "Next item"      # a loop body's lines back to the Loop card
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
QUALIFIER = {"actionCalls": "actionType", "collectionProcessors": "elementSubtype"}
OPERATORS = {
    "EqualTo": "=", "NotEqualTo": "≠", "GreaterThan": ">", "LessThan": "<",
    "GreaterThanOrEqualTo": "≥", "LessThanOrEqualTo": "≤", "Contains": "contains",
    "StartsWith": "starts with", "EndsWith": "ends with", "In": "is one of", "NotIn": "is not one of",
}
TRUE_FALSE_OPERATORS = {
    "IsNull": ("is empty", "is not empty"), "IsBlank": ("is blank", "is not blank"),
    "IsChanged": ("is changed", "is not changed"), "WasSet": ("was set", "was not set"),
    "WasSelected": ("was selected", "was not selected"), "WasVisited": ("was visited", "was not visited"),
}
ACTION_TYPES = {
    "apex": "Apex action", "emailSimple": "Email", "emailAlert": "Email alert", "sendEmail": "Email",
    "chatterPost": "Chatter post", "quickAction": "Quick action", "submit": "Submit for approval",
    "generatePromptResponse": "Prompt template", "externalService": "External service", "flow": "Flow action",
    "component": "Lightning component", "createServiceReport": "Service report",
}
RECORD_EVENTS = {"Create": "created", "Update": "updated", "CreateAndUpdate": "created or updated", "Delete": "deleted"}
TIMING = {"RecordAfterSave": "after save", "RecordBeforeSave": "before save", "RecordBeforeDelete": "before delete"}
PB_TRIGGERS = {"onCreateOnly": "created", "onAllChanges": "created or updated"}


class SetupError(Exception):
    pass


class FlowError(Exception):
    pass


# ---------------------------------------------------------------- data files

def read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                    for row in csv.DictReader(handle) if any((v or "").strip() for v in row.values())]
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def tag_map():
    """(tag, qualifier) -> element, from the flow_xml column; a qualified entry wins over the bare tag."""
    mapping = {}
    for row in read_csv(ELEMENTS_PATH):
        cell = re.sub(r"\([^)]*\)", "", row.get("flow_xml", ""))
        for token in cell.split(","):
            token = token.strip()
            if not token or " " in token:
                continue
            tag, _, qualifier = token.partition(":")
            mapping[(tag, qualifier or None)] = row["element"]
    if not mapping:
        raise SetupError(f"{ELEMENTS_PATH.name}: no flow_xml entries")
    return mapping


def style():
    values = {}
    for row in read_csv(STYLE_PATH):
        try:
            values[row["setting"]] = int(row["value"])
        except ValueError:
            continue
    return {"max_attributes": values.get("max_attributes_shown", 6), "attribute_chars": values.get("attribute_max_chars", 60),
            "footer_chars": values.get("footer_max_chars", 250)}


# ---------------------------------------------------------------- XML helpers

def strip_ns(root):
    for node in root.iter():
        if isinstance(node.tag, str) and "}" in node.tag:
            node.tag = node.tag.split("}", 1)[1]
    return root


def text(node, path, default=""):
    found = node.find(path) if node is not None else None
    return (found.text or "").strip() if found is not None and found.text else default


def value_text(node):
    """A Flow <value> or <rightValue>: the literal or the reference it holds."""
    if node is None:
        return ""
    for child in node:
        raw = (child.text or "").strip()
        if child.tag == "numberValue":
            try:
                number = float(raw)
                return str(int(number)) if number.is_integer() else str(number)
            except ValueError:
                return raw
        if child.tag == "elementReference":
            return clean_ref(raw)
        return raw
    return ""


def clean_ref(ref):
    ref = ref.strip()
    for prefix in ("$Record.", "myVariable_current."):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    if ref.startswith("$Record__Prior."):
        return "prior " + ref[len("$Record__Prior."):]
    if ref.startswith("myVariable_old."):
        return "prior " + ref[len("myVariable_old."):]
    return ref


def condition(node, left_tag):
    left = clean_ref(text(node, left_tag))
    operator = text(node, "operator")
    value = value_text(node.find("rightValue") if node.find("rightValue") is not None else node.find("value"))
    if operator in TRUE_FALSE_OPERATORS:
        yes, no = TRUE_FALSE_OPERATORS[operator]
        return f"{left} {no if value.lower() == 'false' else yes}"
    return f"{left} {OPERATORS.get(operator, operator)} {value}".strip()


def logic_phrase(logic, count):
    logic = (logic or "and").strip().lower()
    if count < 2:
        return ""
    if logic == "and":
        return "all of"
    if logic == "or":
        return "any of"
    return f"conditions {logic.upper()}"


# ---------------------------------------------------------------- attributes

class Card:
    def __init__(self, limits):
        self.limits = limits
        self.items = []

    def add(self, title, description=""):
        title = " ".join((title or "").split())
        if not title:
            return
        limit = self.limits["attribute_chars"]
        if len(title) > limit:
            description = (title + (". " + description if description else ""))
            title = title[:limit - 1].rstrip() + "…"
        item = {"title": title}
        if description:
            item["description"] = description[:400]
        self.items.append(item)

    def done(self):
        limit = self.limits["max_attributes"]
        if len(self.items) <= limit:
            return self.items
        kept, rest = self.items[:limit - 1], self.items[limit - 1:]
        more = "; ".join(i["title"] for i in rest)
        return kept + [{"title": f"+{len(rest)} more", "description": more[:400]}]


def conditions_card(card, nodes, logic, left_tag, lead=None):
    conds = [condition(n, left_tag) for n in nodes]
    phrase = logic_phrase(logic, len(conds))
    if lead:
        card.add(f"{lead}: {phrase}" if phrase else lead)
    elif phrase and phrase != "all of":
        card.add(f"When {phrase}")
    for item in conds:
        card.add(item)


def assignments_card(card, node, tag="inputAssignments"):
    for item in node.findall(tag):
        field = text(item, "field") or text(item, "name")
        value = value_text(item.find("value"))
        card.add(f"{field} = {value}" if value else field)


def summary_of(description, limit):
    description = " ".join((description or "").split())
    if len(description) <= limit:
        return description
    cut = description[:limit]
    stop = max(cut.rfind(". "), cut.rfind("; "))
    if stop > limit // 2:
        return cut[:stop + 1]
    return cut[:cut.rfind(" ")].rstrip(",;:") + "…"


# ---------------------------------------------------------------- the flow

class Flow:
    def __init__(self, root, automation_id, api_name, limits, elements):
        self.root, self.aid, self.api_name, self.limits = root, automation_id, api_name, limits
        self.mapping = elements
        self.process_type = text(root, "processType")
        self.label = text(root, "label") or api_name
        self.start_node = root.find("start")
        self.meta = {text(m, "name"): value_text(m.find("value")) for m in root.findall("processMetadataValues")}
        self.variables = {text(v, "name"): text(v, "objectType") for v in root.findall("variables") if text(v, "objectType")}
        self.formulas = {text(f, "name"): " ".join(text(f, "expression").split()) for f in root.findall("formulas") if text(f, "name")}
        self.nodes = {}       # element API name -> (tag, node, element kind)
        self.order = []
        for child in root:
            qualifier = text(child, QUALIFIER[child.tag]) if child.tag in QUALIFIER else None
            kind = self.mapping.get((child.tag, qualifier)) or self.mapping.get((child.tag, None))
            name = text(child, "name")
            if kind and name:
                self.nodes[name] = (child.tag, child, kind)
                self.order.append(name)
        self.gaps = []
        self.hints = {"trigger": {}, "reads": [], "writes": [], "publishes": [], "calls": []}

    # ---- what kind of flow

    def subtype(self):
        trigger = text(self.start_node, "triggerType")
        if self.process_type == "Workflow":
            return "process-builder"
        if trigger in TIMING:
            return "record-triggered"
        if trigger == "PlatformEvent":
            return "platform-event"
        if trigger == "Scheduled":
            return "scheduled"
        if self.process_type == "Flow":
            return "screen"
        return "autolaunched"

    def trigger_object(self):
        return text(self.start_node, "object") or self.meta.get("ObjectType", "")

    def step_id(self, name):
        ident = f"{self.aid}.{name}"
        if ID_PATTERN.match(ident):
            return ident
        digest = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:8]
        short = re.sub(r"[^A-Za-z0-9_.-]", "_", ident)[:52]
        return f"{short}~{digest}".replace("~", "-")

    # ---- objects a step works on

    def object_of(self, node, tag):
        obj = text(node, "object")
        if obj:
            return obj
        ref = text(node, "inputReference") or text(node, "outputReference")
        if ref in ("$Record", "myVariable_current"):
            return self.trigger_object()
        base = ref.split(".")[0]
        if base in self.variables:
            return self.variables[base]
        if base in self.nodes:
            lookup = self.nodes[base]
            if lookup[0] == "recordLookups":
                return text(lookup[1], "object")
        return ""

    # ---- the Start step

    def start_step(self):
        sub = self.subtype()
        card = Card(self.limits)
        obj = self.trigger_object()
        start = self.start_node
        if sub == "record-triggered":
            event = RECORD_EVENTS.get(text(start, "recordTriggerType"), text(start, "recordTriggerType").lower() or "saved")
            card.add(f"{obj} {event.upper()}")
            card.add(f"Runs {TIMING.get(text(start, 'triggerType'), 'after save')}")
            name, label = "Record-triggered start", "Record-triggered"
            self.hints["trigger"] = {"object": obj, "event": event, "timing": TIMING.get(text(start, "triggerType"), "")}
        elif sub == "process-builder":
            event = PB_TRIGGERS.get(self.meta.get("TriggerType", ""), "created or updated")
            card.add(f"{obj} {event.upper()}")
            name, label = "Process Builder start", "Process Builder"
            self.hints["trigger"] = {"object": obj, "event": event, "timing": "after save"}
        elif sub == "platform-event":
            card.add(f"Platform event: {obj}")
            name, label = "Platform event start", "Platform event"
            self.hints["trigger"] = {"object": obj, "event": "published", "timing": ""}
        elif sub == "scheduled":
            schedule = start.find("schedule") if start is not None else None
            frequency = text(schedule, "frequency")
            when = " ".join(x for x in (frequency, text(schedule, "startDate"), text(schedule, "startTime")) if x)
            card.add(f"Schedule: {when}" if when else "Scheduled")
            if obj:
                card.add(f"For each {obj} record")
            name, label = "Scheduled start", "Scheduled"
            self.hints["trigger"] = {"object": obj, "event": "scheduled", "timing": frequency}
        elif sub == "screen":
            name, label = "Screen flow start", "Screen flow"
            card.add("Started by a user")
        else:
            name, label = "Autolaunched start", "Called by another automation"
            card.add("Called by another flow, Apex or an action")
        if start is not None:
            filters = start.findall("filters")
            logic = text(start, "filterLogic")
            if filters:
                conditions_card(card, filters, logic, "field")
            formula = text(start, "filterFormula")
            if formula:
                card.add("Entry formula", formula)
        if self.hints["trigger"]:
            self.hints["trigger"]["conditions"] = [a["title"] for a in card.items[1:]]
        return {"id": self.step_id("start"), "name": name, "automation": self.aid, "element": "start",
                "attributes": card.done(), "sourceRef": "start"}, label

    # ---- one element

    def element_step(self, name):
        tag, node, kind = self.nodes[name]
        card = Card(self.limits)
        step = {"id": self.step_id(name), "name": text(node, "label") or name, "automation": self.aid, "element": kind,
                "sourceRef": name}
        sid = step["id"]
        if tag == "recordLookups":
            obj = self.object_of(node, tag)
            card.add(obj)
            conditions_card(card, node.findall("filters"), text(node, "filterLogic"), "field")
            card.add("First record only" if text(node, "getFirstRecordOnly") == "true" else "All matching records")
            sort = text(node, "sortField")
            if sort:
                card.add(f"Sorted by {sort} {text(node, 'sortOrder').lower()}".strip())
            self.hints["reads"].append({"object": obj, "step": sid})
        elif tag in ("recordCreates", "recordUpdates", "recordDeletes"):
            obj = self.object_of(node, tag)
            ref = text(node, "inputReference")
            if text(node, "object"):
                card.add(obj)
            elif ref:
                card.add(f"{obj} records in {clean_ref(ref) or ref}" if obj else f"Records in {clean_ref(ref) or ref}")
            conditions_card(card, node.findall("filters"), text(node, "filterLogic"), "field")
            assignments_card(card, node)
            verb = {"recordCreates": "creates", "recordUpdates": "updates", "recordDeletes": "deletes"}[tag]
            if obj.endswith("__e") and tag == "recordCreates":
                self.hints["publishes"].append({"event": obj, "step": sid})
            elif obj:
                self.hints["writes"].append({"object": obj, "step": sid, "verb": verb})
        elif tag == "recordRollbacks":
            card.add("Undoes this transaction's record changes")
        elif tag in ("assignments",):
            for item in node.findall("assignmentItems"):
                target = clean_ref(text(item, "assignToReference"))
                operator = {"Assign": "=", "Add": "add", "Subtract": "subtract", "AddItem": "add",
                            "RemoveAll": "remove all", "RemoveFirst": "remove first", "AssignCount": "= count of"}.get(text(item, "operator"), text(item, "operator"))
                card.add(f"{target} {operator} {value_text(item.find('value'))}".strip())
        elif tag == "transforms":
            card.add(f"Into {text(node, 'dataType') or 'a variable'}")
        elif tag == "decisions":
            rules = node.findall("rules")
            if len(rules) == 1:
                rule = rules[0]
                conds = rule.findall("conditions")
                conditions_card(card, conds, text(rule, "conditionLogic"), "leftValueReference", lead=text(rule, "label") or text(rule, "name"))
            else:
                for rule in rules:
                    conds = [condition(c, "leftValueReference") for c in rule.findall("conditions")]
                    phrase = logic_phrase(text(rule, "conditionLogic"), len(conds))
                    shown = conds[0] if len(conds) == 1 else f"{phrase} {len(conds)} conditions"
                    card.add(f"{text(rule, 'label') or text(rule, 'name')}: {shown}", "; ".join(conds))
        elif tag == "waits":
            for event in node.findall("waitEvents"):
                conds = [condition(c, "leftValueReference") for c in event.findall("conditions")]
                card.add(text(event, "label") or text(event, "name"), "; ".join(conds))
        elif tag == "loops":
            card.add(f"For each item in {clean_ref(text(node, 'collectionReference'))}")
            if text(node, "iterationOrder") == "Desc":
                card.add("Last to first")
        elif tag == "collectionProcessors":
            card.add(f"Collection: {clean_ref(text(node, 'collectionReference'))}")
            conditions_card(card, node.findall("conditions"), text(node, "conditionLogic"), "leftValueReference")
            for option in node.findall("sortOptions"):
                card.add(f"Sort by {text(option, 'sortField')} {text(option, 'sortOrder').lower()}".strip())
        elif tag == "subflows":
            flow_name = text(node, "flowName")
            card.add(f"Flow: {flow_name}")
            for item in node.findall("inputAssignments")[:3]:
                card.add(f"{text(item, 'name')} = {value_text(item.find('value'))}")
            self.hints["calls"].append({"step": sid, "apiName": flow_name, "kind": "flow"})
            step["callsApiName"] = flow_name
        elif tag in ("actionCalls", "apexPluginCalls"):
            action_type = text(node, "actionType") or ("apex" if tag == "apexPluginCalls" else "")
            action_name = text(node, "actionName") or text(node, "apexClass")
            kind_label = ACTION_TYPES.get(action_type, action_type or "Action")
            card.add(kind_label if action_name in ("", action_type) else f"{kind_label}: {action_name}")
            for item in node.findall("inputParameters")[:3]:
                card.add(f"{text(item, 'name')} = {value_text(item.find('value'))}")
            if action_type == "apex" or tag == "apexPluginCalls":
                self.hints["calls"].append({"step": sid, "apiName": action_name.split(".")[0], "kind": "apex"})
                step["callsApiName"] = action_name.split(".")[0]
            elif action_type == "flow":
                self.hints["calls"].append({"step": sid, "apiName": action_name, "kind": "flow"})
                step["callsApiName"] = action_name
        elif tag == "customErrors":
            for message in node.findall("customErrorMessages"):
                card.add(text(message, "errorMessage"))
        elif tag == "screens":
            fields = node.findall("fields")
            for field in fields[:5]:
                card.add(text(field, "fieldText") or text(field, "name"))
        else:
            card.add(tag)
        description = text(node, "description")
        if description:
            step["summary"] = summary_of(description, self.limits["footer_chars"])
        self.explain_formulas(card)
        step["attributes"] = card.done()
        return step

    def explain_formulas(self, card):
        """An attribute that uses a formula gets the formula's expression as its description."""
        for item in card.items:
            used = [name for name in self.formulas if name and re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", item["title"])]
            if used:
                text_ = "; ".join(f"{name} = {self.formulas[name]}" for name in used)
                item["description"] = (item.get("description", "") + ("; " if item.get("description") else "") + text_)[:400]

    # ---- the lines out of one element

    def outgoing(self, name):
        """(target or None, label, kind) for every connector out of an element, expected outcome first."""
        tag, node, _ = self.nodes[name]
        out = []

        def target(conn):
            return text(conn, "targetReference") or None

        def goto(conn):
            return text(conn, "isGoTo") == "true"

        if tag == "decisions":
            for rule in node.findall("rules"):
                conn = rule.find("connector")
                out.append((target(conn) if conn is not None else None, text(rule, "label") or text(rule, "name"), "outcome", conn is not None and goto(conn)))
            conn = node.find("defaultConnector")
            out.append((target(conn) if conn is not None else None, text(node, "defaultConnectorLabel") or "Default outcome", "default", conn is not None and goto(conn)))
        elif tag == "waits":
            for event in node.findall("waitEvents"):
                conn = event.find("connector")
                out.append((target(conn) if conn is not None else None, text(event, "label") or text(event, "name"), "outcome", False))
            conn = node.find("defaultConnector")
            if conn is not None:
                out.append((target(conn), text(node, "defaultConnectorLabel") or "Default outcome", "default", goto(conn)))
        elif tag == "loops":
            conn = node.find("nextValueConnector")
            out.append((target(conn) if conn is not None else None, "For each item", "loop-each", False))
            conn = node.find("noMoreValuesConnector")
            out.append((target(conn) if conn is not None else None, "After last item", "loop-done", False))
        else:
            conn = node.find("connector")
            fault = node.find("faultConnector")
            if conn is not None:
                out.append((target(conn), "Success" if fault is not None else "", "next", goto(conn)))
            else:
                out.append((None, "Success" if fault is not None else "", "next", False))
            if fault is not None:
                out.append((target(fault), "Fault", "fault", goto(fault)))
        return out

    # ---- the whole flow

    def first_element(self):
        start = self.start_node
        conn = start.find("connector") if start is not None else None
        first = text(conn, "targetReference") if conn is not None else ""
        return first or text(self.root, "startElementReference") or None

    def build(self):
        if not self.nodes and self.start_node is None:
            raise FlowError("no flow elements and no start element: is this a .flow-meta.xml file?")
        start_step, start_label = self.start_step()
        steps = {start_step["id"]: start_step}
        by_name = {}
        for name in self.order:
            step = self.element_step(name)
            steps[step["id"]] = step
            by_name[name] = step["id"]
        edges = []  # (from step id, to step id or END, label, kind)
        first = self.first_element()
        if first in by_name:
            edges.append((start_step["id"], by_name[first], "", "next"))
        elif first:
            self.gaps.append({"about": start_step["id"], "note": f"The start points at '{first}', which is not an element this script reads."})
        else:
            edges.append((start_step["id"], END, "", "next"))
        start = self.start_node
        if start is not None:
            for path in start.findall("scheduledPaths"):
                conn = path.find("connector")
                dst = text(conn, "targetReference") if conn is not None else ""
                offset = " ".join(x for x in (text(path, "offsetNumber"), text(path, "offsetUnit"), text(path, "timeSource")) if x)
                label = f"Scheduled: {text(path, 'label') or offset}".strip()
                if dst in by_name:
                    edges.append((start_step["id"], by_name[dst], label, "scheduled"))
            if any(e[3] == "scheduled" for e in edges) and edges and edges[0][2] == "":
                edges[0] = (edges[0][0], edges[0][1], "Run immediately", edges[0][3])
        for name in self.order:
            for dst, label, kind, is_goto in self.outgoing(name):
                if dst is None:
                    edges.append((by_name[name], END, label, kind))
                elif dst in by_name:
                    if is_goto:
                        kind = "goto"
                        label = label or f"Go to {self.nodes[dst][1].findtext('label') or dst}"
                    edges.append((by_name[name], by_name[dst], label, kind))
                else:
                    self.gaps.append({"about": by_name[name], "note": f"A connector points at '{dst}', which is not an element this script reads; drawn as an end."})
                    edges.append((by_name[name], END, label, kind))
        loops = {by_name[n]: n for n in self.order if self.nodes[n][0] == "loops"}
        parents = self.loop_parents(edges, loops)
        for sid, parent in parents.items():
            steps[sid]["parent"] = parent
        connectors = self.level_connectors(edges, parents, loops, start_label, start_step["id"])
        reachable = self.reachable(edges, start_step["id"])
        for sid, step in steps.items():
            if sid not in reachable:
                self.gaps.append({"about": sid, "note": f"'{step['name']}' cannot be reached from the start of the flow."})
        self.unique_names(steps)
        return self.in_reading_order(steps, connectors)

    def in_reading_order(self, steps, connectors):
        """Steps and lines in the order a reader follows them: from the start, expected outcome first."""
        out = defaultdict(list)
        for index, conn in enumerate(connectors):
            out[conn["from"]].append(conn["to"])
        rank, stack = {}, list(reversed(out[START]))
        while stack:
            node = stack.pop()
            if node == END or node in rank:
                continue
            rank[node] = len(rank)
            stack.extend(reversed(out[node]))
        last = len(rank)
        ordered_steps = sorted(steps.values(), key=lambda s: rank.get(s["id"], last))
        position = {s["id"]: i for i, s in enumerate(ordered_steps)}
        ordered_connectors = sorted(enumerate(connectors), key=lambda ic: (
            -1 if ic[1]["from"] == START and ic[1].get("kind") != "loop-each"
            else position.get(ic[1]["to"], last) - 0.5 if ic[1]["from"] == START
            else position.get(ic[1]["from"], last),
            ic[0]))
        return ordered_steps, [c for _, c in ordered_connectors]

    def reachable(self, edges, root):
        nxt = defaultdict(list)
        for src, dst, *_ in edges:
            nxt[src].append(dst)
        seen, queue = {root}, deque([root])
        while queue:
            for dst in nxt[queue.popleft()]:
                if dst != END and dst not in seen:
                    seen.add(dst)
                    queue.append(dst)
        return seen

    def loop_parents(self, edges, loops):
        """Each step in a loop's body gets the innermost loop as its parent."""
        nxt = defaultdict(list)
        each = {}
        for src, dst, _, kind in edges:
            if kind == "loop-each" and src in loops:
                each[src] = dst
            else:
                nxt[src].append(dst)
        bodies = {}
        for loop, first in each.items():
            body, queue = set(), deque([first] if first != END else [])
            while queue:
                node = queue.popleft()
                if node in body or node == loop or node == END:
                    continue
                body.add(node)
                queue.extend(nxt[node])
                if node in each:
                    queue.append(each[node])
            bodies[loop] = body
        parents = {}
        for loop, body in sorted(bodies.items(), key=lambda kv: -len(kv[1])):
            for node in body:
                parents[node] = loop  # smaller (inner) bodies come later and win
        return parents

    def level_connectors(self, edges, parents, loops, start_label, start_id):
        level = lambda sid: parents.get(sid)
        out = [{"from": START, "to": start_id, "label": start_label, "kind": "next"}]
        for src, dst, label, kind in edges:
            if kind == "loop-each":
                # The body's line in: one item at a time. The drawing links it to the line into the Loop card.
                if dst == END:
                    continue
                out.append({"from": START, "to": dst, "label": LOOP_EACH_LABEL, "kind": "loop-each"})
                continue
            if dst == END:
                out.append({"from": src, "to": END, "label": label, "kind": kind})
                continue
            if level(src) == level(dst):
                out.append({"from": src, "to": dst, "label": label, "kind": kind})
            elif dst in loops and level(src) == dst:
                # Back to the Loop card: the next item. The drawing links it to the Loop card's line out.
                out.append({"from": src, "to": END, "label": LOOP_NEXT_LABEL, "kind": "loop-done"})
            else:
                self.gaps.append({"about": src, "note": f"A line leaves a loop body and jumps to '{dst}' on another level; drawn as an end of the body."})
                out.append({"from": src, "to": END, "label": label or "Leaves the loop", "kind": "goto"})
        seen, unique = set(), []
        for conn in out:
            key = (conn["from"], conn["to"], conn["label"])
            if key not in seen:
                seen.add(key)
                unique.append({k: v for k, v in conn.items() if v != "" or k in ("from", "to")})
        return unique

    def unique_names(self, steps):
        seen = defaultdict(int)
        for step in steps.values():
            key = (step.get("parent"), " ".join(step["name"].split()).casefold())
            seen[key] += 1
            if seen[key] > 1:
                step["name"] = f"{step['name']} ({seen[key]})"

    def automation(self, ref_model_id=None):
        sub = self.subtype()
        card = Card(self.limits)
        kind = {"record-triggered": "Record-triggered flow", "process-builder": "Process Builder", "platform-event": "Platform event-triggered flow",
                "scheduled": "Scheduled flow", "screen": "Screen flow", "autolaunched": "Autolaunched flow"}[sub]
        trigger = self.hints["trigger"]
        card.add(kind + (f": {trigger['timing']}" if trigger.get("timing") and sub in ("record-triggered",) else ""))
        if trigger.get("object"):
            card.add(f"{trigger['object']} {trigger.get('event', '')}".strip())
        status = text(self.root, "status")
        if status and status != "Active":
            card.add(f"Status: {status}")
        item = {"id": self.aid, "name": self.label, "type": "process-builder" if sub == "process-builder" else "flow",
                "apiName": self.api_name, "attributes": card.done(),
                "attachments": [{"type": "metadata", "apiName": self.api_name, "metadataType": "Flow",
                                 **({"refModelId": ref_model_id} if ref_model_id else {})}]}
        description = text(self.root, "description")
        if description:
            item["description"] = description[:5000]
            item["summary"] = summary_of(description, self.limits["footer_chars"])
        return item


def fragment_from(path, automation_id, api_name=None, ref_model_id=None):
    try:
        root = strip_ns(ET.parse(path).getroot())
    except (OSError, ET.ParseError) as exc:
        raise FlowError(f"cannot read {path}: {exc}")
    if root.tag != "Flow":
        raise FlowError(f"{path} holds a <{root.tag}>, not a <Flow>")
    if not ID_PATTERN.match(automation_id):
        raise FlowError(f"automation id '{automation_id}' is not a valid model id (letters, digits, _ . -; up to 64)")
    name = api_name or Path(path).name.split(".")[0]
    flow = Flow(root, automation_id, name, style(), tag_map())
    steps, connectors = flow.build()
    return {
        "fragmentVersion": 1,
        "source": {"kind": "flow-xml", "file": Path(path).name, "processType": flow.process_type, "subtype": flow.subtype()},
        "automation": flow.automation(ref_model_id),
        "steps": steps,
        "connectors": connectors,
        "gaps": flow.gaps,
        "hints": flow.hints,
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Turn a Flow definition into a logic fragment.")
    parser.add_argument("flow", help="the .flow-meta.xml file")
    parser.add_argument("--automation-id", required=True, help="the automation's id in the model")
    parser.add_argument("--api-name", help="the flow's API name (default: from the file name)")
    parser.add_argument("--ref-model-id", help="the run's selected reference model for the metadata link")
    parser.add_argument("--out", help="where to write the fragment (default: print it)")
    args = parser.parse_args(argv)
    try:
        fragment = fragment_from(args.flow, args.automation_id, args.api_name, args.ref_model_id)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except FlowError as exc:
        print(f"ERROR {exc}")
        return 1
    text_out = json.dumps(fragment, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text_out + "\n", encoding="utf-8")
        levels = {s.get("parent") for s in fragment["steps"]}
        print(f"Wrote {args.out}: {len(fragment['steps'])} steps on {len(levels)} level(s), {len(fragment['connectors'])} lines, {len(fragment['gaps'])} gap(s).")
    else:
        print(text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
