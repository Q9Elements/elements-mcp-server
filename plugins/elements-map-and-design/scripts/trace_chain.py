#!/usr/bin/env python3
"""Walk an automation chain through the Elements dependency graph, one tool call at a time, then assemble it.

Usage:
  python3 trace_chain.py init DIR --ref-model ID --root NODE_ID --root-name NAME --root-type SFTYPE
                         [--root-api API_NAME] [--question TEXT] [--keywords WORD,WORD,...]
                         [--down N] [--up N] [--max-automations N] [--max-fanout N]
  python3 trace_chain.py next DIR
  python3 trace_chain.py candidates DIR [--json]
  python3 trace_chain.py decide DIR [--include NODE_ID,...] [--exclude NODE_ID,...] [--confirm]
  python3 trace_chain.py assemble DIR --out CHAIN.json --links LINKS.json [--title TITLE]
  python3 trace_chain.py bundle DIR --chain CHAIN.json [--links LINKS.json] --automation MODEL_ID --out-dir FOLDER

Why a script: automations rarely call each other. Mostly they chain through data: one saves a record and
that fires the record-triggered automations on its object, or one publishes a platform event and its
subscribers run. So the walk goes automation -> object or event -> automation, reading what each element
does from the dependency graph's relation descriptions ("Start", "Update Record 'X'", "Record Lookup 'Y'",
see data/chain-relations.csv). Doing that by hand is slow and easy to get wrong; this script decides every
step, keeps the state in DIR/trace.json, stops at the limits in data/trace-limits.csv, and records why.

init        Starts a walk from the root automation (the one the person confirmed).
next        Applies every saved result, then prints the one thing to do next, as JSON:
              get-dependencies  call get_dependencies with 'arguments', save the whole result at 'saveTo'
              describe          call get_metadata_component with 'arguments', save the whole result at 'saveTo'
              checkpoint        the walk is complete: show the person 'candidates', then 'decide'
              done              confirmed: run 'assemble'
            A saved result that holds file.url (delivery "file") is downloaded by this script. If that
            download fails, next says so and asks for the same call again: with delivery "file" once when the
            link had run out (follow its expiresInSeconds), with fresh part links, or stop with an explicit download gap.
candidates  The automations found, in scope and not, with how each joins the chain and why it was or was
            not followed: the table to show the person at the checkpoint.
decide      The person's choices: --include a candidate (it is followed from where it joins), --exclude
            one in scope (automations it alone called go back to candidates), --confirm when the chain is right.
assemble    Writes the chain level as a model (automations, the hub objects and events, the interactions
            numbered in order, START and END, gaps) and LINKS (for build_interaction_model.py merge).
bundle      Writes one automation's evidence for the automation-logic-reader agent: context.json (the
            chain lines in and out, with ids and what each is about; the elements the graph names),
            using.json and component.json.

Exit 0: done. Exit 1: a problem the output describes. Exit 2: setup or command line problem.
Standard library only; Python 3.8 or later.
"""

import argparse
import csv
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from mcp_result import hydrate, acquire_native, native_errors, AcquisitionError

PLUGIN = Path(__file__).resolve().parents[1]
TYPES_PATH = PLUGIN / "data" / "automation-types.csv"
RELATIONS_PATH = PLUGIN / "data" / "chain-relations.csv"
LIMITS_PATH = PLUGIN / "data" / "trace-limits.csv"
STYLE_PATH = PLUGIN / "data" / "style-interaction.csv"
OBJECT_TYPES = {"custom object", "standard object", "external object", "big object"}
EVENT_TYPES = {"platform event"}
ENTRY_TYPES = {"buttons & links", "button or link", "lightning page", "lightning pages", "global action", "global actions",
               "quick action", "quick actions", "custom button", "weblink"}
VERBS = {"create": "Creates", "update": "Updates", "delete": "Deletes", "touch": "Changes"}
ID_SAFE = re.compile(r"[^a-z0-9_.-]+")


class SetupError(Exception):
    pass


class TraceError(Exception):
    pass


# ---------------------------------------------------------------- data files

def read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                    for row in csv.DictReader(handle) if any((v or "").strip() for v in row.values())]
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def tables():
    sf_to_type = {}
    for row in read_csv(TYPES_PATH):
        for sf in row.get("sf_types", "").split("|"):
            if sf.strip():
                sf_to_type[sf.strip().casefold()] = row["type"]
    relations = [(re.compile(row["pattern"]), row["relation"]) for row in read_csv(RELATIONS_PATH)]
    limits = {}
    for row in read_csv(LIMITS_PATH):
        try:
            limits[row["setting"]] = int(row["value"])
        except ValueError:
            raise SetupError(f"{LIMITS_PATH.name}: {row['setting']} needs a whole number")
    footer = 250
    for row in read_csv(STYLE_PATH):
        if row.get("setting") == "footer_max_chars":
            footer = int(row["value"])
    needed = ["down_depth", "up_depth", "max_automations", "max_fanout", "hub_writers", "hub_triggered", "describe_batch"]
    missing = [n for n in needed if n not in limits]
    if missing:
        raise SetupError(f"{LIMITS_PATH.name}: no value for {', '.join(missing)}")
    return sf_to_type, relations, limits, footer


# ---------------------------------------------------------------- reading results

def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def saved(path):
    """True when a result is saved at path (a failed download leaves a marker, which does not count)."""
    if not Path(path).exists():
        return False
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return False
    return not (isinstance(data, dict) and data.get("downloadFailed"))


def materialise(path):
    """A saved tool result, with its file.url downloaded when delivery 'file' put the rows in a file."""
    try:
        return hydrate(read_json(path))
    except (OSError, ValueError) as exc:
        raise DownloadError(str(exc))


VERB_3RD = {"create": "creates", "update": "updates", "delete": "deletes", "touch": "saves", "read": "reads", "call": "calls"}


class DownloadError(Exception):
    def __init__(self, message, expired=False, lasts=None):
        super().__init__(message)
        self.expired = expired
        self.lasts = lasts


def download_failed(trace, path, exc):
    """Record a download gap and reacquire fresh links with identical arguments."""
    state = trace.state
    write_json(path, {"downloadFailed": exc.args[0]})
    state["expiredLinks"] = state.get("expiredLinks", 0) + (1 if exc.expired else 0)
    if exc.expired and state["expiredLinks"] < 2:
        trace.save()
        lasts = f"{exc.lasts} seconds" if exc.lasts else "a short time"
        return {"action": "download-failed", "error": exc.args[0],
                "how": f"The result's file link had run out (it lasts {lasts}). Run next again: it asks for the same call. "
                       "Save the result and run next straight after, with nothing in between."}
    trace.save()
    return {"action": "download-failed", "error": exc.args[0],
            "how": "Repeat the identical request for fresh links; acquire every native part or report the download gap."}


def dep_rows(result):
    """Related type and node evidence adapted from each canonical dependency row."""
    rows = []
    records = result if isinstance(result, list) else result.get("rows", [])
    for row in records:
        related = row.get("related") or {}
        dep = dict(related)
        dep["sfType"] = related.get("type")
        dep["description"] = (related.get("attributes") or {}).get("description") or ""
        dep["relationDescription"] = row.get("relationshipDescription") or ""
        dep.update({key: row.get(key) for key in ("read", "write", "triggerType", "triggerAction")})
        rows.append((related.get("type") or "", dep))
    return rows


def description_text(value):
    if isinstance(value, dict):
        return value.get("value") or ""
    return value or ""


def api_name(dep):
    sf = dep.get("sf") or {}
    return sf.get("apiName") or dep.get("apiName") or dep.get("name") or ""


def is_managed(dep):
    identity = dep.get("identity") or ""
    path = ((dep.get("sf") or {}).get("fullPath") or "")
    return bool(dep.get("managedPackage")) or identity.startswith("Namespace.") or path.startswith("Managed Packages")


def element_lines(description):
    lines = []
    for raw in (description or "").splitlines():
        raw = raw.strip()
        if raw.startswith("- "):
            lines.append(raw[2:].strip())
    return lines


# ---------------------------------------------------------------- the walk

class Trace:
    def __init__(self, workdir):
        self.dir = Path(workdir)
        self.sf_to_type, self.relations, self.limits, self.footer = tables()
        path = self.dir / "trace.json"
        if not path.exists():
            raise TraceError(f"{path} does not exist; run init first")
        self.state = read_json(path)
        self.nodes = self.state["nodes"]

    def save(self):
        write_json(self.dir / "trace.json", self.state)

    # ---- kinds and relevance

    def kind_of(self, sf_type, api):
        key = (sf_type or "").casefold()
        if key in EVENT_TYPES or api.endswith("__e"):
            return "event"
        if key in self.sf_to_type:
            return "automation"
        if key in OBJECT_TYPES:
            return "object"
        if key in ENTRY_TYPES:
            return "entry"
        return "other"

    def relevant(self, node):
        words = [w.casefold() for w in self.state.get("keywords", []) if w.strip()]
        if not words:
            return True
        hay = " ".join([node.get("name", ""), node.get("apiName", ""), node.get("description", "")]).casefold()
        return any(w in hay for w in words)

    def in_scope_count(self):
        return sum(1 for n in self.nodes.values() if n["kind"] == "automation" and n["status"] in ("root", "in-scope"))

    def node(self, dep, sf_type):
        ident = dep.get("_id") or dep.get("nodeId")
        api = api_name(dep)
        if ident not in self.nodes:
            self.nodes[ident] = {
                "nodeId": ident, "name": dep.get("name") or api, "apiName": api, "sfType": dep.get("sfType") or sf_type,
                "kind": self.kind_of(dep.get("sfType") or sf_type, api), "description": description_text(dep.get("description")),
                "managed": is_managed(dep), "details": {"active": dep.get("active")} if "active" in dep else {}, "status": "found", "reason": "", "depth": {}, "expand": [], "entry": [], "launchedFrom": [],
            }
        return self.nodes[ident]

    def link(self, src, dst, kind, elements=(), inferred=False):
        for item in self.state["links"]:
            if item["from"] == src and item["to"] == dst and item["kind"] == kind:
                for element in elements:
                    if element not in item["elements"]:
                        item["elements"].append(element)
                if not inferred:
                    item.pop("inferred", None)
                return item
        item = {"from": src, "to": dst, "kind": kind, "elements": list(elements)}
        if inferred:
            item["inferred"] = True
        self.state["links"].append(item)
        return item

    def admit(self, node, direction, depth, via):
        """Bring an automation into scope (and follow it), or leave it as a candidate with the reason."""
        if node["status"] in ("root", "in-scope", "excluded"):
            return
        if (node.get("details") or {}).get("active") is False:
            node["status"], node["reason"] = "candidate", "inactive in the org"
            return
        limit = self.limits["down_depth"] if direction == "down" else self.limits["up_depth"]
        node.setdefault("joins", {"direction": direction, "via": via, "depth": depth})
        if depth > limit:
            node["status"], node["reason"] = "candidate", f"beyond the {direction}stream depth limit ({limit})"
            return
        explicit = via.startswith("called")
        if not explicit and not self.relevant(node):
            node["status"], node["reason"] = "candidate", "its name and description match none of the keywords"
            return
        if node["managed"]:
            node["status"], node["reason"] = "in-scope", f"{via}; managed package: drawn as one card, not followed"
            node["depth"][direction] = depth
            return
        if self.in_scope_count() >= self.limits["max_automations"]:
            node["status"], node["reason"] = "candidate", f"the chain already has {self.limits['max_automations']} automations"
            return
        node["status"], node["reason"] = "in-scope", via
        self.expand(node, direction, depth)

    def expand(self, node, direction, depth):
        node["depth"][direction] = min(depth, node["depth"].get(direction, depth))
        limit = self.limits["down_depth"] if direction == "down" else self.limits["up_depth"]
        if node["kind"] == "automation" and node["managed"]:
            return
        if node["kind"] == "automation" and depth >= limit and node["status"] != "root":
            node["stop"] = f"{direction}stream depth limit ({limit}) reached; not followed further"
            return
        if node["kind"] != "automation" and depth + 1 > limit:
            return  # nothing that starts on it or saves it could join within the limit
        if direction in node["expand"]:
            return
        node["expand"].append(direction)
        if node["kind"] == "automation":
            self.ask(node, "using")
            if direction == "up":
                self.ask(node, "where_used")
        else:
            self.ask(node, "where_used")

    def ask(self, node, looking, sf_type=None):
        key = f"{node['nodeId']}-{looking}" + (f"-{re.sub(r'[^A-Za-z0-9]+', '_', sf_type)}" if sf_type else "")
        stem = f"{node['nodeId']}-{looking}"
        existing = [item for item in self.state["lookups"] if item["key"] == key]
        if existing:
            # Reapply the acquired collection when the same node is followed in another direction.
            for item in self.state["lookups"]:
                if item["key"].startswith(stem) and item["status"] == "done":
                    item["status"] = "pending"
            return
        self.state["lookups"].append({"key": key, "nodeId": node["nodeId"], "lookingFor": looking, "sfType": sf_type, "status": "pending"})

    # ---- applying one result

    def apply(self, lookup, result):
        node = self.nodes[lookup["nodeId"]]
        rows = dep_rows(result)
        if any("Start" in dep.get("relationDescription", "") for _, dep in rows):
            gap = f"Entry conditions for {node['name']} require component or source evidence; dependency rows do not provide identity paths"
            if gap not in self.state["notChecked"]:
                self.state["notChecked"].append(gap)
        for failure in result.get("failed") or []:
            note = f"Dependency gap for {failure.get('nodeId')}: {failure.get('error') or failure.get('reason')}"
            if note not in self.state["notChecked"]:
                self.state["notChecked"].append(note)
        if node["kind"] == "automation":
            if lookup["lookingFor"] == "using":
                self.apply_using(node, rows)
            else:
                self.apply_callers(node, rows)
        else:
            self.apply_object(node, rows)

    def relation(self, line):
        for pattern, relation in self.relations:
            if pattern.search(line):
                return relation
        return "reference"

    def relations_of(self, dep):
        lines = element_lines(dep.get("relationDescription"))
        rels = [(self.relation(line), line) for line in lines] if lines else [("unstated", "")]
        if dep.get("write") is True and not any(r in ("create", "update", "delete") for r, _ in rels):
            rels.append(("touch", "Dependency write flag is true"))
        return rels

    def apply_using(self, node, rows):
        down = "down" in node["expand"]
        up = "up" in node["expand"] or node["status"] == "root"
        apex = node["sfType"].casefold().startswith("apex")
        for group, dep in rows:
            other = self.node(dep, group)
            if other["nodeId"] == node["nodeId"]:
                continue
            rels = self.relations_of(dep)
            if other["kind"] == "automation":
                self.link(node["nodeId"], other["nodeId"], "calls", [l for _, l in rels if l])
                if down:
                    self.admit(other, "down", node["depth"].get("down", 0) + 1, f"called by {node['name']}")
            elif other["kind"] in ("object", "event"):
                kinds = {r for r, _ in rels}
                lines = [l for _, l in rels if l]
                writes = kinds & {"create", "update", "delete", "touch"}
                if "trigger" in kinds or (other["kind"] == "event" and "unstated" in kinds and not apex):
                    self.link(other["nodeId"], node["nodeId"], "triggers", [l for r, l in rels if r == "trigger"], inferred="trigger" not in kinds)
                    if up:
                        other["status"] = "hop"
                        self.expand(other, "up", node["depth"].get("up", 0))
                if apex and "unstated" in kinds:
                    stem = re.sub(r"(__c|__e)$", "", other["apiName"]).replace("_", "").casefold()
                    if node["sfType"].casefold() == "apex trigger" and stem and stem in node["apiName"].replace("_", "").casefold():
                        self.link(other["nodeId"], node["nodeId"], "triggers", [], inferred=True)
                        if up:
                            other["status"] = "hop"
                            self.expand(other, "up", node["depth"].get("up", 0))
                for verb in sorted(writes):
                    self.link(node["nodeId"], other["nodeId"], "publishes" if other["kind"] == "event" else verb,
                              [l for r, l in rels if r == verb])
                if writes and down:
                    other["status"] = "hop"
                    self.expand(other, "down", node["depth"].get("down", 0))
                if not writes and "trigger" not in kinds:
                    self.link(node["nodeId"], other["nodeId"], "reads", lines,
                              inferred=apex and "unstated" in kinds and dep.get("read") is not True)
            else:
                starts = [l for r, l in rels if r == "trigger"]
                if starts:
                    entry = entry_hint(dep)
                    if entry and entry not in node["entry"]:
                        node["entry"].append(entry)

    def apply_callers(self, node, rows):
        for group, dep in rows:
            other = self.node(dep, group)
            if other["nodeId"] == node["nodeId"]:
                continue
            if other["kind"] == "automation":
                self.link(other["nodeId"], node["nodeId"], "calls", [l for _, l in self.relations_of(dep) if l])
                self.admit(other, "up", node["depth"].get("up", 0) + 1, f"calls {node['name']}")
            elif other["kind"] == "entry":
                where = f"{other['sfType']}: {other['name']}"
                if where not in node["launchedFrom"]:
                    node["launchedFrom"].append(where)

    def apply_object(self, obj, rows):
        down = "down" in obj["expand"]
        up = "up" in obj["expand"]
        triggered, writers = [], []
        for group, dep in rows:
            other = self.node(dep, group)
            if other["kind"] != "automation":
                continue
            rels = self.relations_of(dep)
            kinds = {r for r, _ in rels}
            apex = other["sfType"].casefold().startswith("apex")
            if "trigger" in kinds or (obj["kind"] == "event" and "unstated" in kinds and not apex):
                self.link(obj["nodeId"], other["nodeId"], "triggers", [l for r, l in rels if r == "trigger"], inferred="trigger" not in kinds)
                triggered.append(other)
            writes = kinds & {"create", "update", "delete", "touch"}
            if apex and "unstated" in kinds:
                stem = re.sub(r"(__c|__e)$", "", obj["apiName"]).replace("_", "").casefold()
                if other["sfType"].casefold() == "apex trigger" and stem and stem in other["apiName"].replace("_", "").casefold():
                    self.link(obj["nodeId"], other["nodeId"], "triggers", [], inferred=True)
                    triggered.append(other)
            for verb in sorted(writes):
                self.link(other["nodeId"], obj["nodeId"], "publishes" if obj["kind"] == "event" else verb,
                          [l for r, l in rels if r == verb])
            if writes:
                writers.append(other)
            if not writes and "trigger" not in kinds and not (obj["kind"] == "event" and "unstated" in kinds):
                self.link(other["nodeId"], obj["nodeId"], "reads", [l for _, l in rels if l],
                          inferred=apex and "unstated" in kinds and dep.get("read") is not True)
        if down:
            self.admit_many(triggered, "down", obj["depth"].get("down", 0) + 1, f"runs when {obj['name']} is {'published' if obj['kind'] == 'event' else 'saved'}")
        if up:
            self.admit_many(writers, "up", obj["depth"].get("up", 0) + 1, f"{'publishes' if obj['kind'] == 'event' else 'writes'} {obj['name']}")

    def admit_many(self, nodes, direction, depth, via):
        fresh = [n for n in dict((n["nodeId"], n) for n in nodes).values() if n["status"] in ("found", "candidate")]
        relevant = [n for n in fresh if self.relevant(n)]
        if len(relevant) > self.limits["max_fanout"]:
            for extra in relevant[self.limits["max_fanout"]:]:
                extra.setdefault("joins", {"direction": direction, "via": via, "depth": depth})
                extra["status"], extra["reason"] = "candidate", f"more than {self.limits['max_fanout']} automations join here"
            fresh = [n for n in fresh if n not in relevant[self.limits["max_fanout"]:]]
        for node in fresh:
            self.admit(node, direction, depth, via)

    # ---- describe results

    def apply_describe(self, result):
        for item in (result.get("items") or []) if isinstance(result, dict) else []:
            ident = item.get("nodeId") or item.get("_id")
            node = self.nodes.get(ident)
            if node is None:
                continue
            details = item.get("nodeDetails") or {}
            if item.get("error"):
                self.state["notChecked"].append(f"Component gap for {ident}: {item['error']}")
            node["described"] = True
            node["details"] = {k: details.get(k) for k in ("active", "subtype", "triggerType", "isManaged", "frequency", "startDate") if k in details}
            if not node["description"]:
                node["description"] = description_text(item.get("description"))
            if details.get("isManaged"):
                node["managed"] = True
            if details.get("active") is False and node["status"] == "in-scope":
                node["status"], node["reason"] = "candidate", "inactive in the org"


def entry_hint(dep):
    """A field or picklist value the Start element names: part of what makes the automation run."""
    identity = dep.get("identity") or ""
    if ".CustomValue." in identity:
        field = identity.split(".fields.")[-1].split(".CustomValue.")[0]
        return f"{field} = {dep.get('name')}"
    if ".fields." in identity:
        return identity.split(".fields.")[-1]
    return ""


# ---------------------------------------------------------------- commands

def cmd_init(args):
    workdir = Path(args.workdir)
    if (workdir / "trace.json").exists():
        print(f"ERROR {workdir / 'trace.json'} already exists; use a new folder or carry on with next")
        return 1
    sf_to_type, _, limits, _ = tables()
    if args.down is not None:
        limits["down_depth"] = args.down
    if args.up is not None:
        limits["up_depth"] = args.up
    if args.max_automations is not None:
        limits["max_automations"] = args.max_automations
    if args.max_fanout is not None:
        limits["max_fanout"] = args.max_fanout
    if args.root_type.casefold() not in sf_to_type:
        print(f"ERROR '{args.root_type}' is not an automation type in {TYPES_PATH.name}")
        return 1
    state = {"traceVersion": 2, "server": args.server, "teamId": args.team_id, "refModelId": args.ref_model, "question": args.question or "",
             "keywords": [k.strip() for k in (args.keywords or "").split(",") if k.strip()],
             "root": args.root, "delivery": "file", "confirmed": False, "nodes": {}, "links": [], "lookups": [],
             "describes": [], "notChecked": [], "decisions": [], "limitsOverride": limits}
    write_json(workdir / "trace.json", state)
    trace = Trace(workdir)
    trace.limits = limits
    root = trace.node({"_id": args.root, "name": args.root_name, "sfType": args.root_type, "sf": {"apiName": args.root_api or args.root_name}}, args.root_type)
    root["status"], root["reason"] = "root", "the automation the person chose"
    trace.expand(root, "down", 0)
    trace.expand(root, "up", 0)
    trace.save()
    print(f"Started a walk from '{args.root_name}' in {workdir}. Next: python3 {Path(__file__).name} next {workdir}")
    return 0


def load_trace(workdir):
    trace = Trace(workdir)
    trace.limits.update(trace.state.get("limitsOverride", {}))
    return trace


def next_step(workdir):
    trace = load_trace(workdir)
    state = trace.state
    for lookup in state["lookups"]:
        if lookup["status"] != "pending":
            continue
        path = trace.dir / "lookups" / f"{lookup['key']}.json"
        if not saved(path):
            continue
        try:
            result = materialise(path)
        except DownloadError as exc:
            return download_failed(trace, path, exc)
        try:
            result = acquire_native(result, lookup.get("acquired"))
        except (OSError, ValueError) as exc:
            return download_failed(trace, path, DownloadError(str(exc)))
        lookup["acquired"] = result
        lookup["partsFrom"] = result.get("nextPartsFrom")
        lookup["retryAfterSeconds"] = result.get("retryAfterSeconds", 0)
        path.unlink()
        if result.get("status") == "failed":
            lookup["status"] = "failed"
            state["notChecked"].append(f"Dependency job failed for {lookup['nodeId']}: {result.get('error')}")
            continue
        if native_errors(result):
            if result.get("status") == "complete" and result.get("nextPartsFrom") is None:
                trace.save()
                return {"action": "acquisition-gap", "errors": native_errors(result),
                        "how": "Acquire every part and all failure evidence for this resultId."}
            continue
        write_json(path, result)
        trace.apply(lookup, result)
        lookup["status"] = "done"
    for number, describe in enumerate(state["describes"]):
        if describe.get("status") == "done":
            continue
        path = trace.dir / "describe" / f"{number + 1}.json"
        if saved(path):
            try:
                result = materialise(path)
            except DownloadError as exc:
                return download_failed(trace, path, exc)
            items = {item.get("nodeId") or item.get("_id"): item for item in describe.get("items", [])}
            items.update({item.get("nodeId") or item.get("_id"): item for item in result.get("items", [])})
            describe["items"] = list(items.values())
            cursor = (result.get("_truncated") or {}).get("nextSkip")
            if cursor is not None:
                describe["skip"] = cursor
                path.unlink()
                continue
            missing = set(describe["nodeIds"]) - set(items)
            for node in missing:
                state["notChecked"].append(f"Component gap for {node}: requested node missing from complete reply")
                trace.nodes[node]["described"] = True
            result["items"] = list(items.values())
            write_json(path, result)
            trace.apply_describe(result)
            describe["status"] = "done"
    trace.save()
    pending = [item for item in state["lookups"] if item["status"] == "pending"]
    if pending:
        lookup = pending[0]
        node = trace.nodes[lookup["nodeId"]]
        arguments = {"refModelId": state["refModelId"], "nodeId": lookup["nodeId"], "lookingFor": lookup["lookingFor"],
                     "attributes": ["description", "status"], "delivery": "file"}
        if lookup.get("sfType"):
            arguments.update(sfType=lookup["sfType"])
        if lookup.get("partsFrom") is not None:
            arguments["partsFrom"] = lookup["partsFrom"]
        if state.get("teamId"):
            arguments["teamId"] = state["teamId"]
        what = "what it uses" if lookup["lookingFor"] == "using" else "what uses it"
        return {"action": "get-dependencies", "tool": "get_dependencies", "about": f"{node['name']} ({node['sfType']}): {what}",
                "remaining": len(pending), "waitSeconds": lookup.get("retryAfterSeconds", 0), "arguments": arguments,
                "saveTo": str(trace.dir / "lookups" / f"{lookup['key']}.json"), "save": "the whole result, as JSON"}
    wanted = [n["nodeId"] for n in trace.nodes.values()
              if n["kind"] == "automation" and n["status"] in ("root", "in-scope", "candidate") and not n.get("described")
              and not any(n["nodeId"] in d["nodeIds"] for d in state["describes"] if d.get("status") != "failed")]
    if wanted:
        batch = wanted[:trace.limits["describe_batch"]]
        state["describes"].append({"nodeIds": batch, "status": "pending"})
        trace.save()
    open_describe = next(((i, d) for i, d in enumerate(state["describes"]) if d.get("status") == "pending"), None)
    if open_describe:
        number, describe = open_describe
        return {"action": "describe", "tool": "get_metadata_component",
                "about": f"{len(describe['nodeIds'])} automation(s): active or not, trigger, managed package",
                "arguments": {**({"teamId": state["teamId"]} if state.get("teamId") else {}), "refModelId": state["refModelId"], "nodeIds": describe["nodeIds"], "detail": "full", "delivery": state["delivery"], **({"skip": describe["skip"]} if describe.get("skip") is not None else {})},
                "saveTo": str(trace.dir / "describe" / f"{number + 1}.json"), "save": "the whole result, as JSON"}
    if not state["confirmed"]:
        counts = defaultdict(int)
        for node in trace.nodes.values():
            if node["kind"] == "automation":
                counts[node["status"]] += 1
        return {"action": "checkpoint", "inScope": counts["root"] + counts["in-scope"], "candidates": counts["candidate"],
                "excluded": counts["excluded"],
                "then": f"python3 {Path(__file__).name} candidates {workdir}: show the table; apply the person's choices with decide (--include, --exclude, --confirm)"}
    return {"action": "done", "then": f"python3 {Path(__file__).name} assemble {workdir} --out <chain.json> --links <links.json>"}


def candidates(workdir):
    trace = load_trace(workdir)
    rows = []
    names = {k: n["name"] for k, n in trace.nodes.items()}
    for node in trace.nodes.values():
        if node["kind"] != "automation" or node["status"] == "found":
            continue
        joins = []
        for item in trace.state["links"]:
            if item["kind"] == "reads":
                continue
            if item["to"] == node["nodeId"] and item["from"] in names:
                joins.append(f"{names[item['from']]} {item['kind']} it")
            elif item["from"] == node["nodeId"] and item["to"] in names and trace.nodes[item["to"]]["kind"] != "automation":
                verb = VERB_3RD.get(item["kind"], item["kind"])
                joins.append(f"it {verb} {names[item['to']]}")
        rows.append({"nodeId": node["nodeId"], "name": node["name"], "type": node["sfType"], "status": node["status"],
                     "why": (node.get("stop") if node["status"] in ("root", "in-scope") else "") or node.get("reason", ""), "joins": joins[:4],
                     "active": (node.get("details") or {}).get("active"), "description": node.get("description", "")[:160]})
    order = {"root": 0, "in-scope": 1, "candidate": 2, "excluded": 3}
    rows.sort(key=lambda r: (order.get(r["status"], 4), r["name"].casefold()))
    return rows, trace.state["notChecked"]


def cmd_candidates(args):
    rows, not_checked = candidates(args.workdir)
    if args.json:
        print(json.dumps({"automations": rows, "notChecked": not_checked}, indent=2, ensure_ascii=False))
        return 0
    print("| Status | Automation | Type | How it joins | Why |")
    print("|---|---|---|---|---|")
    for row in rows:
        active = "" if row["active"] is not False else " (inactive)"
        print(f"| {row['status']} | {row['name']}{active} | {row['type']} | {'; '.join(row['joins']) or '-'} | {row['why']} |")
    for note in not_checked:
        print(f"NOTE {note}")
    print(f"node ids: " + ", ".join(f"{r['name']}={r['nodeId']}" for r in rows))
    return 0


def release_orphans(trace):
    """Automations in scope only as the subflow of an automation now out of the chain go back to candidates."""
    released, again = [], True
    while again:
        again = False
        for node in trace.nodes.values():
            if node["kind"] != "automation" or node["status"] != "in-scope" or not (node.get("reason") or "").startswith("called by"):
                continue
            callers = [trace.nodes[item["from"]] for item in trace.state["links"]
                       if item["to"] == node["nodeId"] and item["kind"] == "calls" and item["from"] in trace.nodes]
            if any(c["status"] in ("root", "in-scope") for c in callers):
                continue
            node["status"] = "candidate"
            node["reason"] = "only called by " + ", ".join(sorted(c["name"] for c in callers)) + ", out of the chain"
            released.append(node["name"])
            again = True
    return released


def cmd_decide(args):
    trace = load_trace(args.workdir)
    changed = []
    for ident in [i.strip() for i in (args.include or "").split(",") if i.strip()]:
        node = trace.nodes.get(ident)
        if node is None or node["kind"] != "automation":
            print(f"ERROR '{ident}' is not an automation the walk found")
            return 1
        joins = node.get("joins") or {"direction": "down", "via": "included by the person", "depth": 1}
        node["status"], node["reason"] = "in-scope", "included by the person"
        trace.expand(node, joins["direction"], joins["depth"])
        changed.append(f"included {node['name']}")
    for ident in [i.strip() for i in (args.exclude or "").split(",") if i.strip()]:
        node = trace.nodes.get(ident)
        if node is None or node["kind"] != "automation" or node["status"] == "root":
            print(f"ERROR '{ident}' is not an automation in scope that can be excluded")
            return 1
        node["status"], node["reason"] = "excluded", "excluded by the person"
        changed.append(f"excluded {node['name']}")
    changed += [f"left out {name}: it was only called by automations now out of the chain" for name in release_orphans(trace)]
    if args.confirm:
        trace.state["confirmed"] = True
        changed.append("confirmed the chain")
    trace.state["decisions"].extend(changed)
    trace.save()
    print("; ".join(changed) if changed else "nothing changed")
    return 0


# ---------------------------------------------------------------- assemble

def slug(text, taken):
    base = ID_SAFE.sub("-", (text or "item").casefold()).strip("-.") or "item"
    if not base[0].isalnum():
        base = "a" + base
    base = base[:60]
    ident, n = base, 2
    while ident in taken:
        ident = f"{base[:56]}-{n}"
        n += 1
    taken.add(ident)
    return ident


def cut(text, limit):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    sentence, clause = text.rfind(". ", 0, limit), text.rfind("; ", 0, limit - 1)
    if sentence > limit // 2 and sentence >= clause:
        return text[:sentence + 1]
    if clause > limit // 2:
        return text[:clause] + "…"
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def kind_label(node):
    details = node.get("details") or {}
    subtype = details.get("subtype") or ""
    subtype = {"no trigger": "Autolaunched"}.get(subtype.casefold(), subtype)  # Elements' name for an autolaunched flow
    timing = {"RecordAfterSave": "after save", "RecordBeforeSave": "before save", "RecordBeforeDelete": "before delete"}.get(details.get("triggerType") or "", "")
    if node["sfType"] == "Flow":
        label = f"{subtype} flow" if subtype and "flow" not in subtype.casefold() else (subtype or "Flow")
        return f"{label}: {timing}" if timing else label
    return node["sfType"]


def assemble(workdir, title=None):
    trace = load_trace(workdir)
    nodes, links, limits = trace.nodes, trace.state["links"], trace.limits
    scope = {k for k, n in nodes.items() if n["kind"] == "automation" and n["status"] in ("root", "in-scope")}
    root = trace.state["root"]
    # Keep what joins the root through the scope (calls, or a write and a trigger through one object or event).
    adjacency = defaultdict(set)
    writes = defaultdict(lambda: defaultdict(set))   # object -> writer -> verbs
    triggers = defaultdict(set)                      # object -> automations it starts
    for item in links:
        src, dst, kind = item["from"], item["to"], item["kind"]
        if kind == "calls" and src in scope and dst in scope:
            adjacency[src].add(dst)
            adjacency[dst].add(src)
        elif kind in ("create", "update", "delete", "touch", "publishes") and src in scope and not item.get("inferred"):
            writes[dst][src].add(kind)
        elif kind == "triggers" and dst in scope:
            triggers[src].add(dst)
    for obj in set(writes) | set(triggers):
        for writer in writes[obj]:
            for target in triggers[obj]:
                if writer != target:
                    adjacency[writer].add(target)
                    adjacency[target].add(writer)
    connected, queue = {root}, deque([root])
    while queue:
        for nxt in adjacency[queue.popleft()]:
            if nxt not in connected:
                connected.add(nxt)
                queue.append(nxt)
    dropped = sorted(nodes[k]["name"] for k in scope - connected)
    scope &= connected
    taken = set()
    ids = {}
    for key in sorted(scope, key=lambda k: (k != root, nodes[k]["name"].casefold())):
        ids[key] = slug(nodes[key]["apiName"] or nodes[key]["name"], taken)
    automations = []
    for key in sorted(scope, key=lambda k: (k != root, nodes[k]["name"].casefold())):
        node = nodes[key]
        attributes = [{"title": kind_label(node)}]
        trig = [nodes[o]["name"] for o, targets in triggers.items() if key in targets and o in nodes]
        if trig:
            attributes.append({"title": cut(f"On: {', '.join(trig)}", 60)})
        entry = entry_parts(node["entry"])
        if entry:
            attributes.append({"title": cut("Entry: " + "; ".join(entry[:3]), 60), "description": "; ".join(entry)[:400]})
        if (node.get("details") or {}).get("active") is False:
            attributes.append({"title": "Inactive"})
        if node["managed"]:
            attributes.append({"title": "Managed package"})
        item = {"id": ids[key], "name": node["name"], "type": trace.sf_to_type.get(node["sfType"].casefold(), "other"),
                "apiName": node["apiName"], "attributes": attributes,
                "attachments": [{"type": "metadata", "apiName": node["apiName"], "metadataType": node["sfType"], "refModelId": trace.state["refModelId"]}]}
        if node.get("description"):
            item["description"] = node["description"][:5000]
            item["summary"] = cut(node["description"], trace.footer)
        automations.append(item)
    # Objects and events: a card at a hub, otherwise folded into the line label.
    entities, interactions, link_info = [], [], {}
    pairs = []
    for obj in sorted(set(writes) | set(triggers), key=lambda o: nodes[o]["name"].casefold() if o in nodes else o):
        writers = [w for w in writes[obj] if w in scope]
        targets = [t for t in triggers[obj] if t in scope]
        if not writers or not targets or obj not in nodes:
            continue
        o = nodes[obj]
        hub = len(writers) >= limits["hub_writers"] and len(targets) >= limits["hub_triggered"]
        if hub:
            ident = slug(o["apiName"] or o["name"], taken)
            entity = {"id": ident, "name": o["name"], "apiName": o["apiName"],
                      "kind": "custom" if o["apiName"].endswith(("__c", "__e")) else "standard",
                      "attachments": [{"type": "metadata", "apiName": o["apiName"], "metadataType": o["sfType"], "refModelId": trace.state["refModelId"]}]}
            if o.get("description"):
                entity["description"] = o["description"][:5000]
            entities.append(entity)
            for writer in writers:
                if writer in targets:
                    continue  # it runs on this record and saves it again: recursion, recorded as a gap below
                verbs = writes[obj][writer]
                pairs.append((ids[writer], ident, "publishes" if o["kind"] == "event" else "writes", verb_label(verbs, o), obj,
                              False, None))
            for target in targets:
                pairs.append((ident, ids[target], "triggers", hub_label(o, nodes[target]), obj, False, None))
        else:
            for writer in writers:
                for target in targets:
                    if writer == target:
                        continue
                    verbs = writes[obj][writer]
                    pairs.append((ids[writer], ids[target], "publishes" if o["kind"] == "event" else "triggers",
                                  verb_label(verbs, o), obj, False, None))
    for item in links:
        if item["kind"] == "calls" and item["from"] in scope and item["to"] in scope:
            pairs.append((ids[item["from"]], ids[item["to"]], "calls", "Runs it as a subflow" if nodes[item["to"]]["sfType"] == "Flow" else "Calls it", None, item.get("inferred"), item["to"]))
    gaps = []
    uncertain = set()
    for item in links:
        pair = (item["from"], item["to"])
        if item["kind"] in ("reads", "create", "update", "delete", "touch", "publishes") and \
                item.get("inferred") and item["from"] in scope and pair not in uncertain and \
                item["from"] not in writes[item["to"]]:
            uncertain.add(pair)
            gaps.append({"about": ids[item["from"]],
                         "note": f"'{nodes[item['from']]['name']}' references {nodes[item['to']]['name']}; "
                                 "whether it writes records is unconfirmed (inferred reference); no write is drawn."})
    for obj in sorted(set(writes) & set(triggers)):
        for writer in writes[obj]:
            if writer in scope and writer in triggers[obj]:
                gaps.append({"about": ids[writer], "note": f"'{nodes[writer]['name']}' runs when {nodes[obj]['name']} is saved and also changes it, so it can run again (recursion); the drawing shows no line back to itself."})
    has_in = {p[1] for p in pairs}
    onward = {p[0] for p in pairs if p[2] != "calls"}
    by_id = {ids[k]: k for k in scope}
    hub_of = {e["apiName"]: e["id"] for e in entities}
    starts, ends = [], []
    for item in automations:
        key = by_id[item["id"]]
        if item["id"] not in has_in:
            starts.append(("START", item["id"], "triggers", start_label(nodes[key], [nodes[o] for o, t in triggers.items() if key in t and o in nodes]), None, False, None))
        if item["id"] not in onward:
            terminal = [(o, v) for o, ws in writes.items() for w, v in ws.items()
                        if w == key and o in nodes and not (triggers[o] & scope)]
            # What it creates says most about what it leaves behind; then what it publishes, updates, deletes.
            terminal.sort(key=lambda item: min((END_ORDER.get(verb, 9) for verb in item[1]), default=9))
            ends.append((item["id"], "END", "writes", end_label(nodes[key], [(nodes[o], v) for o, v in terminal]),
                         terminal[0][0] if terminal else None, False, None))
    for entity in entities:
        if entity["id"] not in has_in:
            starts.append(("START", entity["id"], "triggers", f"{entity['name']} saved", None, False, None))
    # A loop through data (an automation that saves the record it runs on) can leave the chain with no way in:
    # start it where the root starts.
    reached = reachable(starts + pairs)
    candidates_in = [ids[root]] + [a["id"] for a in automations if a["id"] != ids[root]]
    for ident in candidates_in:
        if ident in reached:
            continue
        key = by_id[ident]
        objects = [nodes[o] for o, t in triggers.items() if key in t and o in nodes]
        target = next((hub_of[o["apiName"]] for o in objects if o["apiName"] in hub_of), ident)
        label = trigger_label(objects[0], nodes[key]) if objects else start_label(nodes[key], [])
        if target != ident:
            label = f"{objects[0]['name']} saved"
        starts.append(("START", target, "triggers", label, None, False, None))
        reached = reachable(starts + pairs)
    ordered = order_pairs(starts + pairs + ends)
    for number, (src, dst, kind, label, obj, inferred, callee) in enumerate(ordered, start=1):
        ident = f"i{number}"
        item = {"id": ident, "from": src, "to": dst, "kind": kind, "order": number, "label": label[:200]}
        if inferred:
            item["inferred"] = True
            item["evidence"] = ["Apex: the dependency graph names the object but not what the code does with it"]
        interactions.append(item)
        info = {"kind": "writes" if kind in ("writes", "triggers") and obj else kind}
        if obj:
            info["object"] = nodes[obj]["apiName"]
        if callee:
            info["calls"] = ids[callee]
        link_info[ident] = info
    for key in scope:
        node = nodes[key]
        if node.get("stop"):
            gaps.append({"about": ids[key], "note": f"Stopped after '{node['name']}': {node['stop']}."})
        if node["managed"]:
            gaps.append({"about": ids[key], "note": f"'{node['name']}' is in a managed package: its logic is not traced or drawn."})
    left = [n for n in nodes.values() if n["kind"] == "automation" and n["status"] in ("candidate", "excluded")]
    for node in sorted(left, key=lambda n: (n["name"].casefold(), n["nodeId"])):
        gaps.append({"note": f"'{node['name']}' was left out: {node['reason']}."})
    if dropped:
        gaps.append({"note": "Left out because they do not join the root through the chain: " + ", ".join(dropped)})
    gaps += not_checked_gaps(trace, scope)
    root_node = nodes[root]
    model = {
        "schemaVersion": "1.0",
        "meta": {"title": (title or f"{root_node['name']}: automation chain")[:80],
                 "description": cut((trace.state.get("question").rstrip() + ("" if trace.state.get("question").rstrip()[-1:] in ".?!" else ".") + " " if trace.state.get("question") else "")
                                    + f"Traced from '{root_node['name']}' through the Elements dependency graph: what calls what, and which saves and events start which automation.", 5000),
                 "author": "trace-automation-chain",
                 "sources": [{"kind": "metadata", "ref": trace.state["refModelId"]}]},
        "automations": automations,
    }
    if entities:
        model["entities"] = entities
    if interactions:
        model["interactions"] = interactions
    if gaps:
        model["gaps"] = gaps
    links_out = {"interactions": link_info, "automations": {ids[k]: k for k in scope}, "entities": {e["id"]: e["apiName"] for e in entities}}
    trace.state["assembled"] = {"ids": {k: ids[k] for k in scope}}
    trace.save()
    return model, links_out


def verb_label(verbs, obj):
    if obj["kind"] == "event":
        return f"Publishes {obj['name']}"
    words = [VERBS[v] for v in ("create", "update", "delete", "touch") if v in verbs]
    if len(words) > 1:
        words = [words[0]] + [w.lower() for w in words[1:]]
    return f"{' and '.join(words)} {obj['name']}"


def trigger_label(obj, target):
    if obj["kind"] == "event":
        return f"{obj['name']} published"
    entry = entry_parts(target.get("entry") or [])
    return f"{obj['name']} saved" + (f" ({'; '.join(entry[:2])})" if entry else "")


def hub_label(obj, target):
    """A line out of a hub card: the card already names the object, so the line says only when it starts."""
    if obj["kind"] == "event":
        return "Published"
    entry = entry_parts(target.get("entry") or [])
    return f"When {entry[0]}" if entry else "Saved"


def entry_parts(hints):
    """Entry hints read as conditions: 'Stage__c = Approved or Paid', then fields the Start names with no value."""
    values, bare = {}, []
    for hint in hints:
        if " = " in hint:
            field, value = hint.split(" = ", 1)
            values.setdefault(field, [])
            if value not in values[field]:
                values[field].append(value)
        elif hint not in bare:
            bare.append(hint)
    return [f"{field} = {' or '.join(vals)}" for field, vals in values.items()] + [b for b in bare if b not in values]


def start_label(node, objects):
    if objects:
        obj = objects[0]
        return trigger_label(obj, node)
    subtype = ((node.get("details") or {}).get("subtype") or "").casefold()
    if node.get("launchedFrom"):
        return f"Launched from {node['launchedFrom'][0]}"
    if "screen" in subtype:
        return "A user runs it"
    if "schedul" in subtype:
        return "On its schedule"
    return "Called or started outside this chain"


END_ORDER = {"create": 0, "publishes": 1, "update": 2, "delete": 3, "touch": 4}
NOT_CHECKED = re.compile(r"^Elements did not check (?P<type>.+) for (?P<how>what uses|what is used by) '(?P<name>.+)'$")
LAUNCHERS = ("aura", "lightning web component", "visualforce")


def not_checked_gaps(trace, scope):
    """One gap per component type Elements did not check, for the chain's own automations and objects only,
    and only where that type could add to a chain: Apex anywhere, and components that can launch an automation."""
    nodes = trace.nodes
    in_chain = {nodes[k]["name"]: nodes[k] for k in scope}
    for item in trace.state["links"]:
        if item["kind"] == "reads":
            continue
        for end, other in ((item["from"], item["to"]), (item["to"], item["from"])):
            if other in scope and end in nodes and nodes[end]["kind"] != "automation":
                in_chain.setdefault(nodes[end]["name"], nodes[end])
    by_type = defaultdict(list)
    for note in trace.state["notChecked"]:
        match = NOT_CHECKED.match(note)
        if not match or match["name"] not in in_chain:
            continue
        kind = (match["type"] or "").casefold()
        node = in_chain[match["name"]]
        apex = kind.startswith("apex")
        launches = node["kind"] == "automation" and match["how"] == "what uses" and kind.startswith(LAUNCHERS)
        if apex or launches:
            entry = f"{'what uses' if match['how'] == 'what uses' else 'what is used by'} {match['name']}"
            if entry not in by_type[match["type"]]:
                by_type[match["type"]].append(entry)
    return [{"note": note} for note in trace.state["notChecked"] if note.startswith(("Dependency", "Entry conditions", "Component gap"))] + [{"note": f"Elements did not check {kind} for " + "; ".join(entries)[:1500]
                     + ". Anything of that kind that joins the chain there is missing from it."}
            for kind, entries in sorted(by_type.items())]


def end_label(node, written):
    """What the last automation leaves behind: its first write, and how many more (end lines stay short)."""
    names = [verb_label(verbs, obj) for obj, verbs in written if obj["kind"] in ("object", "event")]
    if not names:
        return "Ends"
    return names[0] + (f" (+{len(names) - 1})" if len(names) > 1 else "")


def reachable(pairs):
    out = defaultdict(list)
    for pair in pairs:
        out[pair[0]].append(pair[1])
    seen, queue = set(), deque(["START"])
    while queue:
        for nxt in out[queue.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def order_pairs(pairs):
    """Number the lines in reading order: from START, breadth first, the main line before the others."""
    out = defaultdict(list)
    for index, pair in enumerate(pairs):
        out[pair[0]].append(index)
    seen, ordered, queue = set(), [], deque(["START"])
    visited = set()
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for index in out[node]:
            if index not in seen:
                seen.add(index)
                ordered.append(pairs[index])
                queue.append(pairs[index][1])
    ordered += [p for i, p in enumerate(pairs) if i not in seen]
    return ordered


# ---------------------------------------------------------------- bundle

def bundle(workdir, chain_path, automation_id, out_dir, links_path=None):
    trace = load_trace(workdir)
    chain = read_json(chain_path)
    ids = trace.state.get("assembled", {}).get("ids", {})
    node_id = next((k for k, v in ids.items() if v == automation_id), None)
    auto = next((a for a in chain.get("automations", []) if a["id"] == automation_id), None)
    if node_id is None or auto is None:
        raise TraceError(f"'{automation_id}' is not an automation of the assembled chain")
    node = trace.nodes[node_id]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    using = trace.dir / "lookups" / f"{node_id}-using.json"
    if using.exists():
        shutil.copyfile(using, out / "using.json")
    for number, describe in enumerate(trace.state["describes"]):
        path = trace.dir / "describe" / f"{number + 1}.json"
        if node_id in describe["nodeIds"] and path.exists():
            data = read_json(path)
            item = next((i for i in data.get("items", []) if (i.get("nodeId") or i.get("_id")) == node_id), None)
            if item:
                write_json(out / "component.json", item)
    elements = element_index(trace, node_id, using)
    links = {}
    links_path = Path(links_path) if links_path else Path(chain_path).with_name("links.json")
    if links_path.exists():
        links = read_json(links_path).get("interactions", {})
    incoming = [{"id": i["id"], "label": i.get("label", ""), "kind": i["kind"], "from": i["from"]}
                for i in chain.get("interactions", []) if i["to"] == automation_id]
    outgoing = []
    for i in chain.get("interactions", []):
        if i["from"] != automation_id:
            continue
        entry = {"id": i["id"], "label": i.get("label", ""), "kind": i["kind"], "to": i["to"]}
        info = links.get(i["id"], {})
        if info.get("object"):
            entry["object"] = info["object"]
            entry["elementsThatDoIt"] = [e["element"] for e in elements if info["object"] in e["items"] and e["relation"] in ("create", "update", "delete", "touch")]
        if info.get("calls"):
            entry["calls"] = info["calls"]
        outgoing.append(entry)
    context = {"automation": auto, "nodeId": node_id, "sfType": node["sfType"], "managed": node["managed"],
               "details": node.get("details", {}), "entry": node["entry"], "launchedFrom": node["launchedFrom"],
               "incoming": incoming, "outgoing": outgoing, "elements": elements,
               "files": {"using": "using.json" if using.exists() else None,
                         "component": "component.json" if (out / "component.json").exists() else None}}
    write_json(out / "context.json", context)
    return context


def element_index(trace, node_id, using_path):
    """Every element the dependency graph names for this automation, with what it does and the items it names.

    From the saved 'using' result when there is one (fields and picklist values included, which is where a
    Decision or an Assignment shows up), else from the walk's links."""
    index = {}

    def add(line, relation, item):
        entry = index.setdefault(line, {"element": line, "relation": relation, "items": []})
        if item and item not in entry["items"]:
            entry["items"].append(item)

    if Path(using_path).exists():
        for _, dep in dep_rows(read_json(using_path)):
            item = api_name(dep)
            identity = dep.get("identity") or ""
            if ".fields." in identity:
                item = identity.split(".fields.")[0].split(".")[-1] + "." + entry_hint(dep).replace(" = ", ":")
            for relation, line in trace.relations_of(dep):
                if line:
                    add(line, relation, item)
    for link in trace.state["links"]:
        if link["from"] == node_id and link["to"] in trace.nodes:
            for line in link["elements"]:
                add(line, link["kind"], trace.nodes[link["to"]]["apiName"])
        elif link["to"] == node_id and link["kind"] == "triggers":
            add("Start", "trigger", trace.nodes[link["from"]]["apiName"])
    return list(index.values())


# ---------------------------------------------------------------- main

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Walk an automation chain through the Elements dependency graph.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init")
    p.add_argument("workdir")
    p.add_argument("--ref-model", required=True)
    p.add_argument("--team-id")
    p.add_argument("--server")
    p.add_argument("--root", required=True)
    p.add_argument("--root-name", required=True)
    p.add_argument("--root-type", required=True)
    p.add_argument("--root-api")
    p.add_argument("--question")
    p.add_argument("--keywords")
    p.add_argument("--down", type=int)
    p.add_argument("--up", type=int)
    p.add_argument("--max-automations", type=int)
    p.add_argument("--max-fanout", type=int)
    p = sub.add_parser("next")
    p.add_argument("workdir")
    p = sub.add_parser("candidates")
    p.add_argument("workdir")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("decide")
    p.add_argument("workdir")
    p.add_argument("--include")
    p.add_argument("--exclude")
    p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("assemble")
    p.add_argument("workdir")
    p.add_argument("--out", required=True)
    p.add_argument("--links", required=True)
    p.add_argument("--title")
    p = sub.add_parser("bundle")
    p.add_argument("workdir")
    p.add_argument("--chain", required=True, help="the chain model assemble wrote")
    p.add_argument("--links", help="the links file assemble wrote (default: links.json beside the chain)")
    p.add_argument("--automation", required=True)
    p.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "next":
            print(json.dumps(next_step(args.workdir), indent=2, ensure_ascii=False))
            return 0
        if args.command == "candidates":
            return cmd_candidates(args)
        if args.command == "decide":
            return cmd_decide(args)
        if args.command == "assemble":
            model, links = assemble(args.workdir, args.title)
            write_json(args.out, model)
            write_json(args.links, links)
            print(f"Wrote {args.out}: {len(model['automations'])} automation(s), {len(model.get('entities', []))} hub(s), "
                  f"{len(model.get('interactions', []))} line(s), {len(model.get('gaps', []))} gap(s); and {args.links}.")
            return 0
        context = bundle(args.workdir, args.chain, args.automation, args.out_dir, args.links)
        print(f"Wrote {Path(args.out_dir) / 'context.json'}: {len(context['incoming'])} line(s) in, {len(context['outgoing'])} out, {len(context['elements'])} element(s) named.")
        return 0
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except (TraceError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
