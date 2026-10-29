#!/usr/bin/env python3
"""Automations that run when a record reaches a status, one status box at a time.

The show-status-automations skill runs this script; it never calls Elements itself. Each step
prints the next tool call (with where to save its result) or the next agent to send, and reads
what was saved to decide the step after. Everything lives in one work folder ($WORK):

  boxes.json                  the status boxes to work on (written by `boxes`, or by hand)
  metadata/manifest.json      get_dependencies where_used manifest over every value, field,
                              object and record type node of the boxes
  metadata/rows-<type>.ndjson where_used rows of one registry type over the nodes that have some
  explain/<n>.json            explain_metadata_components results, in the order they were called
  briefs/<nodeId>.json        what the automation-firing-reader agent reads for one automation
  facts/<nodeId>.json         what it wrote: when the automation fires, in plain language
  report.json, report.md      per box: the steps in placement order, conditions, dropped,
                              unverified, and the level each registry type was found at
  draw/                       the diagram calls and their saved results; draw/failed/ the writes that saved nothing
  done.json                   written when next reaches done: every child level and objects write is saved
  writes/                     what each placed automation writes: using rows, definitions, usage, writes.json

Commands:
  boxes   --model --inventory --reads DIR --ref-model-id ID [--team-id] [--scope] --out boxes.json
  next    WORK            print the next action (also written to WORK/_next.json)
  check-facts WORK        check every facts file against its brief
  report  WORK            write report.json and report.md
  layout  WORK            print the child-level changes of every box (dry check of the layout rules)

Standard library only; Python 3.8 or later.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL.parents[1] / "scripts"))   # the plugin's shared scripts: the drawing's naming rule
from metadata_narrative import narrative_text
from mcp_result import hydrate, native_errors, write_complete, verify_rows, require_complete
from manage_batches import split_changes, next_batch
from layout_engine.write_loop import OBJECT_SUFFIX, object_rename  # noqa: E402
REGISTRY_CSV = SKILL / "data" / "automation-registry.csv"
LEVELS = ("value", "field", "object")
EXPLAIN_BATCH = 10          # the explain service rate-limits at about ten generations at once
EXPLAIN_ATTEMPTS = 2        # a failed generation is started again once, then the automation is unclear
RETRYABLE = {"rate_limited"}
FALLBACK_TO_SUMMARY = {"missing_automation_summary"}   # chain needs the org's automation summary batch
FIRES = ("value", "transition", "create", "unclear")
TIMING = ("before_save", "after_save", "unclear")
EVENT = ("create", "update", "create_or_update", "unclear")
CONFIDENCE_LOW = {"low"}
TEXT_LIMITS = {"activity": 60, "input": 100, "outcome": 100}   # box text, line in, line out
# a chain left to right, six boxes a row (five on a canvas under 1900 px wide), placed from the child level's canvas,
# which does not always start at 0 (one ran x -665 to 1335); without a canvas read, 0,0 2000 x 1200 is assumed
MARGIN_X, MARGIN_Y, STEP_X, ROW_Y, BOX_W, WIDE = 175, 200, 300, 330, 150, 1900
DEFAULT_CANVAS = {"x": 0, "y": 0, "w": 2000, "h": 1200}
NO_ORDER_FLAG = ("no set order among the other automations of this save step: Salesforce runs them in no guaranteed "
                 "order, so this place is arbitrary")
ATTRIBUTE_TYPES = {   # stored facts read with list_metadata_by_criteria before anything is explained
    "Flow": ["name", "api_name", "active", "subtype", "trigger_type", "trigger_order", "async_run"],
    "Apex Trigger": ["name", "api_name", "active"],
    "Process Builder Workflow": ["name", "api_name", "active"],
}
RECORD_TRIGGERED = "Record-triggered"
SCHEDULED = "Schedule-triggered"


class SetupError(Exception):
    pass


# ----------------------------------------------------------------- files

def load(path, what="file"):
    path = Path(path)
    if not path.exists():
        raise SetupError(f"{what} not found: {path}")
    try:
        return hydrate(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise SetupError(f"{what} {path} is not JSON: {exc}")


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def ndjson(path):
    rows = []
    path = Path(path)
    if not path.exists():
        return rows
    if path.name != "attributes-none.ndjson":
        try:
            evidence = verify_rows(path)
        except ValueError as exc:
            raise SetupError(str(exc))
        if evidence.get("failed"):
            raise SetupError(f"{path}: native coverage gaps: {evidence['failed']}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def registry():
    with open(REGISTRY_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for row in rows:
        out[row["type"]] = {
            "type": row["type"], "aspect": row["aspect"], "hint": row["found_at_hint"], "kind": row["kind"],
            "firstStatusOnly": row["first_status_only"].strip().lower() == "true",
            "objects": [o for o in row["objects"].split(";") if o],
            "rungBefore": int(row["rung_before"]) if row["rung_before"] else None,
            "rungAfter": int(row["rung_after"]) if row["rung_after"] else None,
            "resourceType": row.get("resource_type") or "System", "notes": row["notes"]}
    return out


# ----------------------------------------------------------------- boxes (hook mode)

def parent_boundary(read, key):
    """The parent activity's incoming and outgoing lines, with their exact labels and keys."""
    lines = read["diagram"].get("lines", [])
    return {"inputs": [{"key": ln["key"], "label": ln.get("label") or ""} for ln in lines
                       if (ln.get("to") or {}).get("activity") == key],
            "outputs": [{"key": ln["key"], "label": ln.get("label") or ""} for ln in lines
                        if (ln.get("from") or {}).get("activity") == key]}


def cmd_boxes(args):
    """The value boxes of a model built by map-process-from-data-model, matched to their drawn boxes."""
    model = load(args.model, "model")
    inv = load(args.inventory, "inventory")
    paths = sorted(Path(args.reads).glob("*.json"))
    reads = [load(p, "diagram read") for p in paths]
    # a whole get_diagram read has diagram.boundary (null on the top level); a read saved without it was trimmed
    trimmed = [p.name for p, r in zip(paths, reads) if "boundary" not in (r.get("diagram") or {})]
    objects = {o["apiName"]: o for o in inv["objects"]}
    acts = {a["id"]: a for a in model["activities"]}
    entity_api = {e["id"]: e.get("apiName") for e in model.get("entities", [])}
    by_parent_text = defaultdict(list)
    for r in reads:
        b = r.get("diagram", {}).get("boundary") or {}
        by_parent_text[(b.get("activity") or {}).get("text")].append(r)
    boxes, problems, unmatched, value_boxes = [], [], [], 0
    for act in model["activities"]:
        sets = [f for f in model["flows"] if f.get("from") == act["id"] and f.get("sets")]
        if not sets:
            continue
        value_boxes += 1
        value = sets[0]["sets"]["value"]
        api = entity_api.get(sets[0]["sets"]["entity"]) or sets[0]["sets"]["entity"].split(".", 1)[-1]
        obj = objects.get(api)
        lc = (obj or {}).get("lifecycle") or {}
        row = next((v for v in lc.get("values", []) if v["value"] == value), None)
        if not obj or not row:
            problems.append(f"{act['name']}: no lifecycle value {api}.{value} in the inventory")
            continue
        parent = acts.get(act.get("parent")) or {}
        rt = None
        for att in parent.get("attachments", []):
            if att.get("type") == "metadata" and att.get("metadataType") == "Record Type":
                rt = next((x for x in lc.get("recordTypes", []) if x["name"] == att["apiName"]), None)
        drawn = [(r, a) for r in by_parent_text.get(parent.get("name"), []) for a in r["diagram"]["activities"]
                 if a["text"] == act["name"]]
        if len(drawn) != 1:
            unmatched.append(f"{act['name']}: {'no' if not drawn else 'several'} drawn boxes match; read the level it is on")
            continue
        read, box = drawn[0]
        label = sets[0].get("label") or ""
        outcome = label if value in label else f"{obj['name']} {lc.get('label', lc['field']).lower()} updated to '{value}'"
        boxes.append({
            "id": act["id"], "diagramId": read["diagramId"], "boxKey": box["key"], "boxText": act["name"],
            "object": api, "objectLabel": obj["name"], "field": lc["field"], "fieldLabel": lc.get("label", lc["field"]),
            "value": value, "valueNodeId": row.get("nodeId"), "fieldNodeId": lc.get("fieldNodeId"),
            "objectNodeId": obj.get("nodeId"),
            **({"recordType": {"name": rt["name"], "label": rt.get("label", rt["name"]), "nodeId": rt.get("nodeId")}} if rt else {}),
            "isFirstStatus": any(f.get("from") == "START" and f.get("to") == act["id"] for f in model["flows"]),
            "boundary": parent_boundary(read, box["key"]),
            "boxOutcome": outcome, "statuses": [v["value"] for v in lc.get("values", [])]})
    for b in boxes:
        for key in ("valueNodeId", "fieldNodeId", "objectNodeId"):
            if not b.get(key):
                problems.append(f"{b['boxText']}: {key} is unknown; add it to boxes.json by hand")
    entity_name = {e["id"]: e.get("name") for e in model.get("entities", [])}
    for b in boxes:
        b["objectsBefore"] = [entity_name[u] for u in acts[b["id"]].get("uses", []) if entity_name.get(u)]
    redo = "re-read them whole with get_diagram include layout and attachments"
    if value_boxes and not boxes:
        # nothing to work on: stop loudly instead of writing an empty boxes.json
        for p in problems + ([] if trimmed else unmatched):
            print("WARN", p)
        if not paths:
            print(f"ERROR no diagram reads (*.json) in {args.reads}: read every level of the map whole with get_diagram "
                  f"include layout and attachments, save them there and run boxes again")
        elif trimmed:
            print(f"ERROR reads in {args.reads} are trimmed; {redo} ({len(trimmed)} of {len(paths)} have no "
                  f"diagram.boundary: {', '.join(trimmed[:5])}{', ...' if len(trimmed) > 5 else ''})")
        else:
            print(f"ERROR none of the {value_boxes} value boxes in the model matches a drawn box in {args.reads}; "
                  f"nothing written")
        return 1
    problems = unmatched + problems
    if unmatched and trimmed:
        problems.append(f"{len(trimmed)} reads in {args.reads} are trimmed (no diagram.boundary: "
                        f"{', '.join(trimmed[:5])}{', ...' if len(trimmed) > 5 else ''}); {redo}")
    save(args.out, {"refModelId": args.ref_model_id, **({"teamId": args.team_id} if args.team_id else {}),
                    "inventory": str(Path(args.inventory).resolve()),
                    **({"scope": str(Path(args.scope).resolve())} if args.scope else {}), "boxes": boxes})
    for p in problems:
        print("WARN", p)
    print(f"{len(boxes)} status boxes written to {args.out}")
    return 0


# ----------------------------------------------------------------- state

class Work:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.reg = registry()
        doc = load(self.dir / "boxes.json", "boxes.json")
        self.ref = doc["refModelId"]
        self.team = doc.get("teamId")
        self.boxes = doc["boxes"]
        for b in self.boxes:
            b["refModelId"] = self.ref
            b.setdefault("statuses", [b["value"]])
        self.rt_labels = {b["recordType"]["nodeId"]: b["recordType"]["label"] for b in self.boxes
                          if (b.get("recordType") or {}).get("nodeId")}
        self.attrs = self.attributes()
        # the map-process-from-data-model run this work folder belongs to: its scope (the basis) and inventory (usage)
        self.scope = self.optional_json(doc.get("scope"), "../scope.json")
        self.inventory = self.optional_json(doc.get("inventory"), "../inventory.json")
        self.rollup = doc.get("objectsRollup", "written")
        if self.rollup not in ROLLUPS:
            raise SetupError(f"objectsRollup must be one of {', '.join(ROLLUPS)}")

    def optional_json(self, given, default):
        path = Path(given) if given else self.dir / default
        if not path.is_absolute():
            path = self.dir / path
        if not path.exists():
            if given:
                raise SetupError(f"{given} named in boxes.json not found")
            return None
        return load(path, path.name)

    def call_args(self, **kw):
        return {"refModelId": self.ref, **({"teamId": self.team} if self.team else {}), **kw}

    # nodes
    def level_node(self, box, level):
        return box[{"value": "valueNodeId", "field": "fieldNodeId", "object": "objectNodeId"}[level]]

    def all_nodes(self):
        seen = []
        for b in self.boxes:
            for n in [b["valueNodeId"], b["fieldNodeId"], b["objectNodeId"], (b.get("recordType") or {}).get("nodeId")]:
                if n and n not in seen:
                    seen.append(n)
        if len(seen) > 1000:
            raise SetupError("Dependency scope exceeds 1000 nodes; split the run before requesting its manifest")
        return seen

    # manifest
    def manifest(self):
        path = self.dir / "metadata" / "manifest.json"
        if not path.exists():
            return None
        doc = load(path, "manifest")
        if doc.get("status") in ("running", "failed") or doc.get("failed") or doc.get("failedTotal"):
            raise SetupError(f"manifest has pending/failed coverage: {doc.get('status')} {doc.get('failed')}")
        missing = set(self.all_nodes()) - {node.get("nodeId") for node in doc.get("nodes", [])}
        if missing:
            raise SetupError(f"manifest is missing requested node coverage: {sorted(missing)}")
        counts = {}
        for node in doc.get("nodes", []):
            counts[node["nodeId"]] = {t["type"]: t["count"] for t in node.get("byType", [])}
        return counts

    def attributes(self):
        """{nodeId: {"subtype", "triggerType", "triggerOrder", "asyncRun", "active"}} from metadata/attributes-*.ndjson."""
        out = {}
        for path in sorted((self.dir / "metadata").glob("attributes-*.ndjson")):
            for row in ndjson(path):
                details = row.get("nodeDetails") or {}
                out[row.get("nodeId")] = {"subtype": details.get("subtype"), "triggerType": details.get("triggerType"),
                                          "triggerOrder": details.get("triggerOrder"), "asyncRun": details.get("asyncRun"),
                                          "active": details.get("active"), "status": row.get("status")}
        return out

    def rows_path(self, type_):
        return self.dir / "metadata" / f"rows-{slug(type_)}.ndjson"

    def needed_row_types(self, counts):
        """Registry types with a count on any node, and the nodes that have it."""
        need = {}
        for t in self.reg:
            nodes = [n for n in self.all_nodes() if counts.get(n, {}).get(t)]
            if nodes:
                need[t] = nodes
        return need

    def rows(self):
        """{type: {nodeId: [related rows]}} from the saved row files."""
        out = {}
        for t in self.reg:
            by_node = defaultdict(list)
            for row in ndjson(self.rows_path(t)):
                rel = row.get("related") or {}
                if rel.get("type") != t:
                    continue
                by_node[(row.get("node") or {}).get("nodeId")].append(row)
            out[t] = by_node
        return out


def live(row):
    rel = row.get("related") or {}
    status = (rel.get("status") or (rel.get("attributes") or {}).get("status") or "").lower()
    return rel.get("active") is not False and status not in ("deleted", "proposed")


# ----------------------------------------------------------------- step 1 and 2: candidates

def candidates(work, counts, rows):
    """Per box: {type: {"level", "rows": [...]}} by the triple check, plus coverage per type."""
    per_box = {}
    for b in work.boxes:
        found = {}
        for t, spec in work.reg.items():
            if spec["objects"] and b["object"] not in spec["objects"]:
                found[t] = {"level": None, "rows": [], "note": f"applies to {', '.join(spec['objects'])} only"}
                continue
            hit = {"level": None, "rows": []}
            for level in LEVELS:
                node = work.level_node(b, level)
                if not counts.get(node, {}).get(t):
                    continue
                kept = [r for r in rows[t].get(node, []) if live(r)]
                if kept:
                    hit = {"level": level, "rows": kept}
                    break
            found[t] = hit
        per_box[b["id"]] = found
    return per_box


def record_type_links(work, rows):
    """{record type nodeId: set of automation nodeIds linked to it}."""
    links = defaultdict(set)
    rt_nodes = {(b.get("recordType") or {}).get("nodeId") for b in work.boxes} - {None}
    for t in work.reg:
        for node, rs in rows[t].items():
            if node in rt_nodes:
                links[node] |= {(r.get("related") or {}).get("nodeId") for r in rs}
    return links


def automations(per_box):
    """{nodeId: {name, apiName, type, rows}} over every box: each automation is explained once."""
    out = {}
    for found in per_box.values():
        for t, hit in found.items():
            for r in hit["rows"]:
                rel = r["related"]
                a = out.setdefault(rel["nodeId"], {"nodeId": rel["nodeId"], "name": rel.get("name"),
                                                   "apiName": rel.get("apiName"), "type": t, "rows": []})
                a["rows"].append(r)
    return out


# ----------------------------------------------------------------- step 3: explanations

def explain_state(work, autos):
    """{nodeId: {aspect: {"status", "error", "narrative", "confidence", "failures"}}} from explain/*.json, in call order."""
    state = defaultdict(dict)
    files = sorted((work.dir / "explain").glob("*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    for path in files:
        doc = load(path, "explain result")
        for item in doc.get("items") or [doc]:
            node = item.get("nodeId")
            if node not in autos:
                continue
            aspect = item.get("aspect") or doc.get("aspect")
            s = state[node].setdefault(aspect, {"failures": 0})
            if item.get("status") == "failed":
                s["failures"] += 1
            s.update(status=item.get("status"), error=item.get("error"), narrative=item.get("narrative"),
                     confidence=item.get("confidence"), retryAfterSeconds=item.get("retryAfterSeconds"))
    return state


def explanation(work, a, state):
    """The complete explanation of an automation, or None."""
    for aspect in aspects_for(work, a):
        s = state.get(a["nodeId"], {}).get(aspect)
        if s and s.get("status") == "complete":
            return {"aspect": aspect, "narrative": s.get("narrative"), "confidence": s.get("confidence")}
    return None


def aspects_for(work, a):
    preferred = work.reg[a["type"]]["aspect"]
    return [preferred] + (["summary"] if preferred != "summary" else [])


def explain_wanted(work, autos, state):
    """[(aspect, nodeId)] still to call, and {nodeId: reason} for automations that end without an explanation.
    The registry's aspect first; chain falls back to summary when the org has no automation summary or chain
    keeps failing; a failed generation is started again up to EXPLAIN_ATTEMPTS times."""
    wanted, given_up = [], {}
    autos = {n: a for n, a in autos.items() if not stored_block(a, work.attrs)}
    outcomes = [x for per in state.values() for x in per.values()]
    retry_pending = any(s.get("error") in RETRYABLE and s["failures"] < EXPLAIN_ATTEMPTS
                        for node in autos for aspect in aspects_for(work, autos[node])
                        for s in [state.get(node, {}).get(aspect, {})] if s)
    if not retry_pending and not any(x.get("status") == "complete" for x in outcomes) and \
            sum(x["failures"] for x in outcomes if x.get("error") not in FALLBACK_TO_SUMMARY) >= EXPLAIN_BATCH:
        # nothing has ever been explained and at least a batch of generations failed: the service is down for
        # this reference model, so asking again only spends the rate limit
        return [], {node: "no explanation could be generated (the explain service failed for every component tried)"
                    for node in autos}
    for node, a in autos.items():
        reason = None
        for aspect in aspects_for(work, a):
            s = state.get(node, {}).get(aspect)
            if s is None or s.get("status") == "running" or (s.get("error") in RETRYABLE and s["failures"] < EXPLAIN_ATTEMPTS):
                wanted.append((aspect, node))
                break
            if s.get("status") == "complete":
                break
            reason = f"{aspect}: {s.get('error') or 'failed'}"
            if s.get("error") in FALLBACK_TO_SUMMARY:
                continue
            if s["failures"] < EXPLAIN_ATTEMPTS:
                wanted.append((aspect, node))
                break
        else:
            given_up[node] = f"no explanation could be generated ({reason})"
    return wanted, given_up


# ----------------------------------------------------------------- step 4: facts

def descriptions(work):
    """{nodeId: description} from metadata/descriptions*.json (get_metadata_component summary results)."""
    out = {}
    for path in sorted((work.dir / "metadata").glob("descriptions*.json")):
        doc = load(path, "get_metadata_component result")
        for item in doc.get("items") or [doc]:
            d = item.get("description")
            d = d.get("value") if isinstance(d, dict) else d
            if item.get("nodeId") and (d or "").strip():
                out[item["nodeId"]] = d.strip()
    return out


DESCRIPTION_FLAG = "evidence is the component's description: no explanation could be generated"


def brief(work, a, expl, per_box):
    statuses = []
    for b in work.boxes:
        for v in b["statuses"]:
            if v not in statuses:
                statuses.append(v)
    hits = sorted({(b["value"], found[a["type"]]["level"]) for b in work.boxes
                   for found in [per_box[b["id"]]] if any(r["related"]["nodeId"] == a["nodeId"] for r in found[a["type"]]["rows"])})
    first = work.boxes[0]
    return {"nodeId": a["nodeId"], "name": a["name"], "apiName": a["apiName"], "type": a["type"],
            "object": first["object"], "field": first["field"], "fieldLabel": first["fieldLabel"],
            "statusValues": statuses,
            "recordTypes": sorted({b["recordType"]["label"] for b in work.boxes if b.get("recordType")}),
            "linkedAt": [{"status": v, "level": lvl} for v, lvl in hits],
            "explanation": expl,
            **({"evidenceSource": "description"} if expl and expl.get("aspect") == "description" else {}),
            "relationships": sorted({(r.get("relationshipDescription") or "").strip() for r in a["rows"]} - {""})}


def facts_problems(fact, brief_doc):
    """What is wrong with one facts file, as a list of sentences."""
    out = []
    narrative = re.sub(r"\s+", " ", narrative_text(brief_doc["explanation"].get("narrative")))
    statuses = set(brief_doc["statusValues"])
    if fact.get("nodeId") != brief_doc["nodeId"]:
        out.append("nodeId does not match the brief")
    if fact.get("fires") not in FIRES:
        out.append(f"fires must be one of {', '.join(FIRES)}")
    for key, allowed in (("timing", TIMING), ("event", EVENT)):
        if fact.get(key) not in allowed:
            out.append(f"{key} must be one of {', '.join(allowed)}")
    for key in ("statuses", "excludedStatuses"):
        bad = [v for v in fact.get(key, []) if v not in statuses]
        if bad:
            out.append(f"{key} names values the field does not have: {', '.join(bad)}")
    for t in fact.get("transitions", []):
        for end in ("from", "to"):
            if t.get(end) is not None and t.get(end) not in statuses:
                out.append(f"a transition {end} '{t.get(end)}' is not a value of the field")
    if fact.get("fires") == "transition" and not fact.get("transitions"):
        out.append("fires is transition, so list the transitions")
    if fact.get("fires") == "unclear" and not fact.get("unclearReason"):
        out.append("fires is unclear, so give unclearReason")
    for key in ("evidence", "timingEvidence", "recordTypesEvidence"):
        quote = re.sub(r"\s+", " ", (fact.get(key) or "")).strip()
        if quote and quote not in narrative:
            out.append(f"{key} is not a quotation from the narrative (copy the sentence exactly)")
    if fact.get("fires") in ("value", "transition", "create") and not fact.get("evidence"):
        out.append("give the evidence sentence the firing rule rests on")
    for x in fact.get("writes", []):
        if not (x.get("object") or "").strip():
            out.append("each writes entry needs the object it writes")
        bad = [o for o in x.get("operations", []) if o not in OPS]
        if bad:
            out.append(f"writes operations must be create, update or delete, not {', '.join(bad)}")
        quote = re.sub(r"\s+", " ", (x.get("evidence") or "")).strip()
        if not quote or quote not in narrative:
            out.append("each writes entry needs evidence quoted exactly from the narrative")
    if brief_doc["type"] == "Validation Rule":
        if fact.get("fires") != "unclear" and not fact.get("condition"):
            out.append("a validation rule needs condition: what must be true to save the record at those statuses")
    elif fact.get("fires") != "unclear":
        for key in ("activity", "outcome"):
            if not (fact.get(key) or "").strip():
                out.append(f"{key} is missing")
        for key, limit in TEXT_LIMITS.items():
            if len(fact.get(key) or "") > limit:
                out.append(f"{key} is {len(fact[key])} characters; keep it to {limit} (it is drawn as box or line text)")
        if brief_doc["type"] in ("Flow", "Apex Trigger") and not (fact.get("input") or "").strip():
            out.append("input is missing (one sentence on what starts it)")
    return out


# ----------------------------------------------------------------- step 4 per box, step 5

def stored_block(a, attrs):
    """Why the stored facts rule an automation out before anything is explained, or None.
    Schedule-triggered flows are not ruled out here: one tied to the status is listed beside the chain."""
    at = attrs.get(a["nodeId"]) or {}
    if at.get("active") is False or at.get("status") in ("deleted", "proposed"):
        return "inactive"
    if a["type"] == "Flow" and at.get("subtype") and at["subtype"] not in (RECORD_TRIGGERED, SCHEDULED):
        return f"not record-triggered ({at['subtype']}): it does not run when the record is saved"
    if a["type"] == "Flow" and "Delete" in (at.get("triggerType") or ""):
        return "runs when the record is deleted"
    return None


def rung(spec, fact, at=None):
    """The save-order rung: the stored trigger type first (a flow's RecordBeforeSave or RecordAfterSave), then
    the narrative's timing, then the type's only rung."""
    trigger = (at or {}).get("triggerType") or ""
    if "BeforeSave" in trigger and spec["rungBefore"]:
        return spec["rungBefore"]
    if "AfterSave" in trigger and spec["rungAfter"]:
        return spec["rungAfter"]
    if fact.get("timing") == "before_save" and spec["rungBefore"]:
        return spec["rungBefore"]
    if fact.get("timing") == "after_save" and spec["rungAfter"]:
        return spec["rungAfter"]
    if spec["rungBefore"] and spec["rungBefore"] == spec["rungAfter"]:
        return spec["rungBefore"]
    return None


def order_key(s):
    """Placement in the chain: the save-order rung, then within flows the trigger order (1-1000 run before the
    flows without one, 1001-2000 after), then the name, which stands for no real order: Salesforce runs the rest
    in no guaranteed order."""
    order = s.get("triggerOrder")
    group = 1 if order is None else (0 if order <= 1000 else 2)
    return (s["rung"] if s["rung"] is not None else 99, group, order or 0, (s["name"] or "").lower())


def decide(work, b, a, level, fact, rt_links):
    """(verdict, detail): verdict is place, scheduled, condition, dropped or unverified."""
    v = b["value"]
    spec = work.reg[a["type"]]
    at = work.attrs.get(a["nodeId"]) or {}
    blocked = stored_block(a, work.attrs)
    if blocked:
        return "dropped", blocked
    if fact is None:
        return "unverified", "no explanation could be generated"
    fires = fact["fires"]
    confidence = str(fact.get("confidence") or "").lower()
    named = v in fact.get("statuses", []) or any(v in (t.get("from"), t.get("to")) for t in fact.get("transitions", []))
    if fires == "unclear":
        return "unverified", fact.get("unclearReason") or "the explanation does not say when it fires"
    if confidence in CONFIDENCE_LOW and not named:
        return "unverified", "confidence is Low and nothing in the explanation names this status"
    rt = b.get("recordType")
    flags = []
    if rt:
        named = fact.get("recordTypes") or []
        if a["nodeId"] in rt_links.get(rt["nodeId"], set()):
            pass
        elif named and rt["label"] not in named and rt["name"] not in named:
            return "dropped", f"names only other record types ({', '.join(named)})"
        else:
            others = sorted(label for node, label in work.rt_labels.items()
                            if node != rt["nodeId"] and a["nodeId"] in rt_links.get(node, set()))
            if others:
                return "dropped", f"the dependency graph links it only to other record types ({', '.join(others)})"
            if not named:
                flags.append("record type not verified")
    if spec["firstStatusOnly"] and not b["isFirstStatus"]:
        return "dropped", "runs only when the record is created, and this is not the first status"
    if fact.get("_source") == "description":
        flags.append(DESCRIPTION_FLAG)
    detail = {"flags": flags}
    if v in fact.get("excludedStatuses", []):
        return "dropped", f"the explanation names '{v}' only as a status it does not run at"
    if fires == "create":
        if not b["isFirstStatus"]:
            return "dropped", "runs only on creation, and this is not the first status"
        detail["when"] = "create"
    elif fires == "transition":
        froms = [t for t in fact["transitions"] if t.get("from") == v]
        tos = [t for t in fact["transitions"] if t.get("to") == v]
        if froms:
            detail["when"] = "transition"
            detail["target"] = froms[0].get("to")
        elif tos:
            return "dropped", f"arrives from {tos[0].get('from') or 'another status'}"
        else:
            return "dropped", "runs on a change between other statuses"
    else:
        # placed at the status that triggers it, on every box whose status does
        if v in fact.get("statuses", []):
            detail["when"] = "value"
        elif fact.get("statuses"):
            return "dropped", f"triggered at {', '.join(repr(x) for x in fact['statuses'])}, not at this status"
        elif level == "value":
            detail["when"] = "value"
            flags.append("the explanation names no status; kept because the dependency graph links it to this value")
        else:
            return "dropped", "not tied to this status"
    if fact.get("event") == "create" and not b["isFirstStatus"]:
        return "dropped", "runs only on creation, and this is not the first status"
    if spec["kind"] == "condition":
        return "condition", detail
    if spec["kind"] == "report":
        return "unverified", "this type is specified but not built: reported, not placed"
    if a["type"] == "Flow" and at.get("subtype") == SCHEDULED:
        return "scheduled", detail
    detail["rung"] = rung(spec, fact, at)
    if detail["rung"] is None:
        flags.append("rung unknown")
    detail["triggerOrder"] = at.get("triggerOrder")
    if at.get("asyncRun"):
        flags.append("also has an asynchronous path, which runs after the save is committed")
    return "place", detail


def box_report(work, b, per_box, autos, facts, rt_links):
    found = per_box[b["id"]]
    steps, conditions, scheduled, dropped, unverified, coverage = [], [], [], [], [], {}
    for t, hit in found.items():
        coverage[t] = hit.get("note") or (hit["level"] or "none found")
        for r in hit["rows"]:
            a = autos[r["related"]["nodeId"]]
            if any(x["nodeId"] == a["nodeId"] for x in steps + conditions + scheduled + dropped + unverified):
                continue
            fact = facts.get(a["nodeId"])
            verdict, detail = decide(work, b, a, hit["level"], fact, rt_links)
            entry = {"nodeId": a["nodeId"], "name": a["name"], "apiName": a["apiName"], "type": t, "hitLevel": hit["level"]}
            if verdict == "place":
                entry.update(when=detail["when"], rung=detail["rung"], triggerOrder=detail.get("triggerOrder"),
                             flags=detail["flags"],
                             activity=fact["activity"], outcome=fact["outcome"],
                             input=fact.get("input") if t in ("Flow", "Apex Trigger") else b["boxOutcome"],
                             evidence=fact.get("evidence"), confidence=fact.get("confidence"))
                if detail.get("target"):
                    entry["target"] = detail["target"]
                steps.append(entry)
            elif verdict == "scheduled":
                entry.update(activity=fact["activity"], outcome=fact["outcome"], evidence=fact.get("evidence"),
                             flags=detail["flags"])
                scheduled.append(entry)
            elif verdict == "condition":
                entry.update(condition=fact["condition"], evidence=fact.get("evidence"), flags=detail["flags"])
                conditions.append(entry)
            elif verdict == "dropped":
                dropped.append({**entry, "reason": detail})
            else:
                unverified.append({**entry, "reason": detail})
    leaves = lambda s: s["when"] == "transition"   # the save that takes the record on from the status comes second
    steps.sort(key=lambda s: (leaves(s), order_key(s)))
    for i, s in enumerate(steps, 1):
        s["position"] = i
        shares = [x for x in steps if x is not s and x["rung"] == s["rung"] and leaves(x) == leaves(s)]
        if shares and s.get("triggerOrder") is None:
            s["flags"].append(NO_ORDER_FLAG)
    return {"box": {k: b.get(k) for k in ("id", "diagramId", "boxKey", "boxText", "value", "boxOutcome", "isFirstStatus",
                                         "object", "objectLabel", "fieldLabel")},
            **({"recordType": b["recordType"]["label"]} if b.get("recordType") else {}),
            "steps": steps, "conditions": conditions, "scheduled": scheduled, "dropped": dropped, "unverified": unverified,
            "coverage": coverage}


RUNG_NAMES = {1: "Flow, before save", 2: "Apex trigger, before save", 3: "Apex trigger, after save", 4: "Assignment rule",
              5: "Auto-response rule", 6: "Workflow rule", 7: "Process Builder", 8: "Flow, after save"}


def objects_md(o, basis_name):
    """The objects part of one box in report.md: before and after, what is written with its evidence, flags."""
    lines = ["Objects on the status box (what the automations write replaces the data-model objects):",
             "", f"- Before: {', '.join(o['before']) if o.get('before') is not None else 'not read yet'}",
             f"- After: {', '.join(o['after'])}" + (f" (also written, in the box note: {', '.join(o['overflow'])})" if o["overflow"] else ""),
             ""]
    if o["written"]:
        lines += ["| Object | Operations | Written by | Evidence |", "|---|---|---|---|"]
        for w in o["written"]:
            lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in [
                f"{w['label']} ({w['object']})", ", ".join(w["operations"]) or "written (operation not stated)",
                "; ".join(w["automations"]), "<br>".join(w["evidence"])]) + " |")
        lines.append("")
    if o["flagged"]:
        lines += ["Flagged (usage basis, no records):"] + [f"- {f['reason']}" for f in o["flagged"]] + [""]
    elif basis_name == "configuration":
        lines += ["Basis: configuration, so objects with no records are not flagged.", ""]
    if o["unclear"]:
        lines += [f"Read or write could not be told apart, so not added: {', '.join(o['unclear'])}.", ""]
    if o["unresolved"]:
        lines += ["Writes whose object could not be worked out, so not added:"] + [f"- {u}" for u in o["unresolved"]] + [""]
    return lines


def rollup_md(ru):
    if not ru:
        return []
    lines = ["# Record-type boxes on the split level", "",
             "Each record-type box shows its lifecycle object, then the objects its statuses' automations write most often "
             f"(mode: {ru[0]['mode']}; the number is how many of its statuses write or show each).", ""]
    for x in ru:
        lines.append(f"- {x['boxText'] or x['recordType']} (box {x['boxKey']} on {x['diagramId']}): "
                     + ", ".join(f"{o['name'] or o['label']}" + (f" ({o['boxes']})" if o.get("boxes") else "") for o in x["objects"])
                     + (f"; shown: {', '.join(x['after'])}" if x.get("after") else ""))
    return lines + [""]


def report_md(reports, ru=(), basis_name="configuration"):
    lines = ["# Automations per status box", ""]
    for r in reports:
        b = r["box"]
        rt = f" ({r['recordType']})" if r.get("recordType") else ""
        lines += [f"## {b['boxText']}{rt}: {b['value']}", ""]
        if r["steps"]:
            lines += ["| # | Type | Name | Hit level | When | Save step | Trigger order | Activity | Outcome | Input | Evidence | Confidence | Flags |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for s in r["steps"]:
                when = s["when"] + (f" to {s['target']}" if s.get("target") else "")
                lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in [
                    s["position"], s["type"], s["name"], s["hitLevel"], when, RUNG_NAMES.get(s["rung"], "unknown"),
                    s.get("triggerOrder") if s.get("triggerOrder") is not None else "not set",
                    s["activity"], s["outcome"], s["input"], s.get("evidence") or "", s.get("confidence") or "",
                    "; ".join(s["flags"])]) + " |")
        else:
            lines.append("No automations found for this status.")
        lines.append("")
        if r.get("scheduled"):
            lines.append("Scheduled at this status (not part of the save): " + "; ".join(
                f"{x['name']}: {x['activity']}" for x in r["scheduled"]))
            lines.append("")
        if r["conditions"]:
            lines.append("Conditions to append to the status box: " + " AND ".join(
                c["condition"] + (f" ({'; '.join(c['flags'])})" if c.get("flags") else "") for c in r["conditions"]))
            lines.append("")
        for title, key in (("Dropped", "dropped"), ("Unverified", "unverified")):
            if r[key]:
                lines.append(f"{title}:")
                lines += [f"- {x['type']} {x['name']}: {x['reason']}" for x in r[key]]
                lines.append("")
        if r.get("objects"):
            lines += objects_md(r["objects"], basis_name)
        lines.append("Coverage: " + "; ".join(f"{t}: {lvl}" for t, lvl in r["coverage"].items()))
        lines.append("")
    lines += rollup_md(list(ru))
    return "\n".join(lines)


# ----------------------------------------------------------------- layout rules

def wrap(text):
    """Line text as written. manage_diagram turns line breaks in a label into spaces and the editor wraps
    the label itself, so the 20-30 character lines of the layout rules cannot be set from here; the
    TEXT_LIMITS on the facts keep the labels short instead."""
    return text or ""


def grid(canvas=None):
    """(x0, y0, step, per_row) for a chain on a child level's canvas: six boxes a row, five when the canvas is
    narrower than WIDE, starting MARGIN_X in from the canvas's left edge."""
    c = canvas or DEFAULT_CANVAS
    per_row = 6 if c["w"] >= WIDE else 5
    step = min(STEP_X, (c["w"] - 2 * MARGIN_X - BOX_W) // (per_row - 1))
    return c["x"] + MARGIN_X, c["y"] + MARGIN_Y, step, per_row


def chain(r):
    """A status box's automations as one linear chain, in the order Salesforce runs them. First the save that brings
    the record to the status (value and create): its before-save steps, then the validation check (one gate for
    all the rules, which Salesforce checks together), then the after-save steps. Then the save that takes the
    record on from the status (transitions from it). Each entry: kind (step or gate), step, k of n (the step's place
    on its own save), and trigger (the line into the first entry of each save: the status outcome, then the status
    change)."""
    arrive = [s for s in r["steps"] if s["when"] != "transition"]
    leave = [s for s in r["steps"] if s["when"] == "transition"]
    box = r["box"]
    out = [{"kind": "step", "step": s, "k": k + 1, "n": len(arrive)} for k, s in enumerate(arrive)]
    if r.get("conditions"):
        at = sum(1 for s in arrive if s.get("rung") in (1, 2))   # validation runs after the before-save steps
        out.insert(at, {"kind": "gate", "conditions": r["conditions"]})
    if out:
        out[0]["trigger"] = box["boxOutcome"]
    if leave:
        subject = f"{box.get('objectLabel') or 'Record'} {(box.get('fieldLabel') or 'status').lower()}"
        targets = {s.get("target") for s in leave}
        to = f" to '{next(iter(targets))}'" if len(targets) == 1 and None not in targets else ""
        change = f"{subject} changes from '{box['value']}'{to}"
        out += [{"kind": "step", "step": s, "k": k + 1, "n": len(leave), **({"trigger": change} if k == 0 else {})}
                for k, s in enumerate(leave)]
    return out


def gate_text(r):
    n = len(r["conditions"])
    obj = (r["box"].get("objectLabel") or "record").lower()
    return {"activity": f"Check the {obj} can be saved at '{r['box']['value']}'",
            "outcome": "All {} conditions met".format(n) if n > 1 else "The condition is met",
            "blocked": "Save blocked: a validation rule failed" if n > 1 else "Save blocked: the validation rule failed"}


def gate_note(r):
    conds = r["conditions"]
    shared = [f for f in conds[0].get("flags", []) if all(f in c.get("flags", []) for c in conds)]

    def own(c):
        rest = [f for f in c.get("flags", []) if f not in shared]
        return f"{c['condition']} [{c['name']}" + (f"; {'; '.join(rest)}" if rest else "") + "]"
    return (f"Validation rules: Salesforce checks them all together on the save that brings the record to "
            f"'{r['box']['value']}', after the before-save steps and before the after-save steps. If any fails, the "
            f"save is blocked, the user sees its error message, and nothing after this check runs.\n"
            f"Conditions to save the record at '{r['box']['value']}':\n" + "\nAND ".join(own(c) for c in conds)
            + (f"\n({'; '.join(shared)})" if shared else ""))


def no_order_note(links):
    """The level note that explains a chain's arbitrary places, or None."""
    loose = [e["step"] for e in links if e["kind"] == "step" and NO_ORDER_FLAG in e["step"]["flags"]]
    if not loose:
        return None
    groups = defaultdict(list)
    for s in loose:
        groups[RUNG_NAMES.get(s["rung"], "save step not stated")].append(s["name"])
    lines = [f"{g}: {'; '.join(names)}." for g, names in groups.items()]
    fix = ("Setting a trigger order on these flows (1-2000) would fix their order."
           if all(s["type"] == "Flow" for s in loose)
           else "Flows can be given a trigger order (1-2000); other automation types cannot be ordered.")
    # a level note loses its line breaks, so it is written as sentences
    return ("No trigger order set. These automations run in the same save step and none of them has a trigger order, "
            "so Salesforce runs them in no guaranteed order: their order on this chain is arbitrary. "
            + " ".join(lines) + " " + fix)


def child_changes(r, reg=None, stubs=(), canvas=None):
    """The changes that lay out one box's child level (layout rules): every automation in one linear chain, in the
    order Salesforce runs them (chain), left to right, six a row (grid). Parent boundary labels enter the first
    box and leave the last; each automation's outcome labels the internal line to the next. The validation rules are one check
    box in the chain, with a second line out where the save is blocked. Each automation box has a resource named
    after its type, a link to the automation and a note with what starts it, its save step, its outcome, the
    evidence and its flags. Notes under the chain: automations with no set order, scheduled flows, or nothing runs.
    stubs: keys of the unattached boundary lines a new child level comes with; a chain replaces them."""
    links = chain(r)
    changes = [{"op": "remove", "kind": "line", "key": k} for k in stubs] if links else []
    box = r["box"]
    boundary = box.get("boundary")
    x0, y0, step_x, per_row = grid(canvas)
    outcomes = []
    for i, e in enumerate(links):
        ref = f"a{i + 1}"
        pos = {"x": x0 + (i % per_row) * step_x, "y": y0 + (i // per_row) * ROW_Y}
        if e["kind"] == "gate":
            g = gate_text(r)
            changes.append({"op": "add", "kind": "activity", "ref": ref, "text": g["activity"], "position": pos})
            rtype = ((reg or {}).get("Validation Rule") or {}).get("resourceType", "System")
            changes.append({"op": "add", "kind": "resource", "activity": ref, "name": "Validation Rule", "type": rtype})
            for c in e["conditions"]:
                if c.get("apiName"):
                    changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "metadata",
                                    "apiName": c["apiName"], "metadataType": "Validation Rule",
                                    **({"refModelId": box["refModelId"]} if box.get("refModelId") else {}),
                                    "description": "A validation rule this check stands for"})
            changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note",
                            "title": "About this check", "text": gate_note(r)})
            changes.append({"op": "add", "kind": "line", "ref": f"x{i + 1}", "from": {"activity": ref}, "to": {"terminator": True} if boundary is not None else None,
                            "fromSide": "bottom", "label": wrap(g["blocked"])})
            outcomes.append(g["outcome"])
        else:
            s, k, n = e["step"], e["k"], e["n"]
            changes.append({"op": "add", "kind": "activity", "ref": ref, "text": s["activity"], "position": pos})
            rtype = ((reg or {}).get(s["type"]) or {}).get("resourceType", "System")
            changes.append({"op": "add", "kind": "resource", "activity": ref, "name": s["type"], "type": rtype})
            if s.get("apiName"):
                changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "metadata", "apiName": s["apiName"],
                                "metadataType": s["type"], **({"refModelId": box["refModelId"]} if box.get("refModelId") else {}), "description": f"The {s['type'].lower()} this step stands for"})
            save = {"value": f"the save that brings the record to '{box['value']}'",
                    "create": "the save that creates the record",
                    "transition": (f"the save that moves the record from '{box['value']}' to '{s['target']}'" if s.get("target")
                                   else f"the save that moves the record on from '{box['value']}'")}[s["when"]]
            order = s.get("triggerOrder")
            note = [f"{s['type']}: {s['name']}",
                    f"Starts: {s['input']}",
                    f"Save step {k} of {n} on {save}: {RUNG_NAMES.get(s['rung'], 'save step not stated')}"
                    + (f", trigger order {order}." if order is not None else "."),
                    f"Outcome: {s['outcome']}",
                    f"Evidence: \"{s.get('evidence') or ''}\" (confidence {s.get('confidence') or 'not given'})",
                    f"Found at {s['hitLevel']} level in the dependency graph."]
            if any(isinstance(w, dict) for w in s.get("writes") or []):
                note.append("Writes: " + "; ".join(
                    f"{w['label']} ({', '.join(w['operations']) or 'written'}" + (f", {w['via']}" if w.get("via") else "") + ")"
                    for w in s["writes"] if isinstance(w, dict)))
                cut = [w["label"] for w in s["writes"] if isinstance(w, dict)][MAX_LISTED - 1:]   # the Flow resource takes one place
                if cut:
                    note.append(f"Not shown as resources (a box carries at most {MAX_LISTED}): {', '.join(cut)}.")
            if s["flags"]:
                note.append("Flags: " + "; ".join(s["flags"]))
            if s.get("target"):
                note.append(f"Leads to the status '{s['target']}'.")
            changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note",
                            "title": "About this automation", "text": "\n".join(note)})
            outcomes.append(s["outcome"])
        if i == 0:
            inputs = boundary.get("inputs", []) if boundary is not None else [{"label": wrap(e["trigger"])}]
            for j, line in enumerate(inputs):
                changes.append({"op": "add", "kind": "line", "ref": "in" if j == 0 else f"in{j + 1}",
                                "from": None, "to": {"activity": ref}, "toSide": "left", "label": line["label"],
                                **({"parentLine": line["key"]} if "key" in line else {})})
        else:
            new_row = i % per_row == 0
            changes.append({"op": "add", "kind": "line", "ref": f"l{i}", "from": {"activity": f"a{i}"},
                            "to": {"activity": ref}, "fromSide": "bottom" if new_row else "right",
                            "toSide": "top" if new_row else "left", "label": wrap(e.get("trigger") or outcomes[i - 1])})
    if links:
        outputs = boundary.get("outputs", []) if boundary is not None else [{"label": wrap(outcomes[-1])}]
        for j, line in enumerate(outputs):
            changes.append({"op": "add", "kind": "line", "ref": "out" if j == 0 else f"out{j + 1}",
                            "from": {"activity": f"a{len(links)}"}, "to": None, "fromSide": "right", "label": line["label"],
                            **({"parentLine": line["key"]} if "key" in line else {})})
    rows = (len(links) + per_row - 1) // per_row
    notes = [no_order_note(links)]
    if r.get("scheduled"):
        notes.append("Scheduled at this status, not part of the save: " + " ".join(
            f"{x['name']} (scheduled flow): {x['activity']}; {x['outcome']}." for x in r["scheduled"]))
    if not links and not r.get("scheduled"):
        notes.append(f"No automation runs when the record reaches '{box['value']}'.")
    for j, text in enumerate(t for t in notes if t):
        changes.append({"op": "add", "kind": "note", "text": text,
                        "position": {"x": x0 + j * 2 * step_x, "y": y0 + rows * ROW_Y + (60 if rows else 0)}})
    return changes


# ----------------------------------------------------------------- objects written by automations
#
# A status box with automations shows the objects those automations write (create, update or delete), next to the
# lifecycle object, instead of the objects the data model links to the step. What an automation writes is read
# deterministically: first the dependency graph's "using" rows (their read and write flags, and the flow elements
# named in relationshipDescription), then the automation's own definition (get_metadata_source: a flow's Create,
# Update and Delete Records elements, the DML statements of Apex). Flows and Apex classes an automation calls are
# followed, so a subflow's writes count for the automation that calls it. Never the automation's name.

MAX_RESOURCES = 5        # the record-type roll-up keeps five resources a box (draw-process-map layout conventions)
USES_RESERVED = 2        # the roll-up keeps two object places while people and systems leave room under MAX_LISTED
WRITE_ELEMENTS = {"Create Record": "create", "Update Record": "update", "Delete Record": "delete"}
APEX_WORDS = {"insert": ["create"], "update": ["update"], "upsert": ["create", "update"], "delete": ["delete"]}   # Apex rows
OPS = ("create", "update", "delete")
FOLLOWED = ("Flow", "Apex Class")                       # called automations: what they write counts for the caller
SOURCE_TYPES = ("Flow", "Apex Trigger", "Apex Class", "Process Builder Workflow", "Workflow Rule")
RESULT_EXT = {"using": ".ndjson", "source": ".ndjson", "usage": ".json"}
def box_limit():
    """The most resources any box carries, people included (max_resources_on_box in the plugin's
    data/style-process.csv, shared by every skill that draws boxes)."""
    path = SKILL.parents[1] / "data" / "style-process.csv"
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("setting") == "max_resources_on_box":
                    return int(row["value"])
    except (OSError, ValueError):
        pass
    return 7


MAX_LISTED = box_limit()   # status and automation boxes: the role, the lifecycle object, then written objects, up to this
ABOUT_STEP = "About this step"   # the status box note map-process-from-data-model writes; only its "Objects used" part changes
STATUS_NOTE = "Objects written behind this step"   # the separate note of the first version: folded into ABOUT_STEP, removed
AUTOMATION_NOTE = "Objects this automation writes"
ROLLUP_NOTE = "Objects written by automations in this lifecycle"
ROLLUPS = ("written", "level", "off")
VERB = {"create": "created", "update": "updated", "delete": "deleted"}


def norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def is_object_type(t):
    return (t or "").endswith("Object") or t == "Platform Event"


def elements(description):
    """[(kind, label)] from a dependency row's relationshipDescription: "- Update Record 'Update Deal'"."""
    out = []
    for line in (description or "").splitlines():
        m = re.match(r"\s*-\s*([A-Za-z][A-Za-z ]*?)\s*(?:'(.*)')?\s*$", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


# --- saved calls (work folder writes/)

def wdir(work):
    return work.dir / "writes"


def saved_calls(work, kind):
    """[(n, nodeIds, result path)] of the saved calls of one kind: the script writes <kind>-<n>.request.json when it
    asks for the call; the result counts once it is saved next to it."""
    out = []
    for req in wdir(work).glob(f"{kind}-*.request.json"):
        n = int(req.name[len(kind) + 1:].split(".")[0])
        res = wdir(work) / f"{kind}-{n}{RESULT_EXT[kind]}"
        if res.exists():
            out.append((n, load(req, "request").get("nodeIds", []), res))
    return sorted(out)


def covered(work, kind):
    return {n for _, nodes, _ in saved_calls(work, kind) for n in nodes}


def next_index(work, kind):
    return 1 + max([n for n, _, _ in saved_calls(work, kind)] or [0])


def using_rows(work):
    by = defaultdict(list)
    for _, _, path in saved_calls(work, "using"):
        for r in ndjson(path):
            by[(r.get("node") or {}).get("nodeId")].append(r)
    return by


def stored_sources(work):
    out = {}
    for _, _, path in saved_calls(work, "source"):
        for r in ndjson(path):
            if r.get("nodeId"):
                out[r["nodeId"]] = r
    return out


def objects_signature(work):
    """What the objects part of the report rests on: every saved writes call, the basis and the roll-up mode."""
    h = hashlib.sha1()
    for kind in RESULT_EXT:
        for n, nodes, path in saved_calls(work, kind):
            h.update(f"{kind}{n}{sorted(nodes)}".encode("utf-8"))
            h.update(path.read_bytes())
    for _, res in library_rounds(work.dir / "draw"):
        h.update(res.read_bytes())
    h.update(f"{basis(work)}|{work.rollup}".encode("utf-8"))
    return h.hexdigest()[:12]


# --- basis and usage (the usage contract of map-process-from-data-model, read tolerantly)

def basis(work):
    """'usage' or 'configuration': scope.json metadata.basis; without it onlyWithRecords true means usage; else
    configuration."""
    md = (work.scope or {}).get("metadata") or {}
    if md.get("basis") in ("usage", "configuration"):
        return md["basis"]
    return "usage" if md.get("onlyWithRecords") is True else "configuration"


def usage_of(entry):
    """{"available": bool, "total": int or None} from an inventory object's usage, or a get_component_usage item,
    or None when it says nothing. available false is never read as zero."""
    if not isinstance(entry, dict):
        return None
    u = entry.get("usage") if isinstance(entry.get("usage"), dict) else entry
    if u.get("available") is False:
        return {"available": False, "total": None}
    total = u.get("total")
    if total is None and isinstance(u.get("records"), dict):
        total = u["records"].get("total")
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return None
    return {"available": True, "total": int(total)}


def object_usage(work):
    """{object API name: usage} from the inventory, then from the usage calls this skill saved."""
    out = {}
    for o in (work.inventory or {}).get("objects", []):
        u = usage_of(o.get("usage")) if "usage" in o else None
        if u and o.get("apiName"):
            out[o["apiName"]] = u
    by_node = {o.get("nodeId"): o.get("apiName") for o in (work.inventory or {}).get("objects", [])}
    for _, _, path in saved_calls(work, "usage"):
        doc = load(path, "get_component_usage result")
        for item in doc.get("items") or [doc]:
            usage = item.get("usage") or {}
            api = (usage.get("object") or {}).get("apiName") or by_node.get(item.get("nodeId")) or item.get("apiName")
            u = usage_of(usage)
            if api and u and api not in out:
                out[api] = u
    return out


def zero_records(work, api, usage):
    """True when the run is on the usage basis and the org is known to hold no records of the object."""
    u = usage.get(api)
    return basis(work) == "usage" and bool(u) and u["available"] and u["total"] == 0


# --- reading definitions

def strip_ns(xml):
    return re.sub(r'\sxmlns(?::\w+)?="[^"]*"', "", xml or "", count=1)


def flow_root(xml):
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(strip_ns(xml))
    except ET.ParseError:
        return None


def flow_variables(root):
    return {v.findtext("name"): v.findtext("objectType") for v in root.findall("variables") if v.findtext("objectType")}


def flow_source_writes(xml, flows_by_api=None):
    """[(operation, element label, object or None, reference)] for every Create, Update and Delete Records element
    of a flow or Process Builder definition. The object is the element's own, else the one its reference holds:
    $Record (the trigger object), a variable's object type, a Get Records element's object, or a called flow's
    output variable (flows_by_api: {apiName: xml}). A related record ($Record.Partner__r) is left to the graph."""
    root = flow_root(xml)
    if root is None:
        return None
    trigger = root.findtext("start/object") or ""
    for pm in root.findall("processMetadataValues"):
        if pm.findtext("name") == "ObjectType" and not trigger:
            trigger = pm.findtext("value/stringValue") or ""
    variables = flow_variables(root)
    lookups = {x.findtext("name"): x.findtext("object") for x in root.findall("recordLookups")}
    subflows = {x.findtext("name"): x.findtext("flowName") for x in root.findall("subflows")}

    def resolve(ref):
        if not ref:
            return None
        if ref in ("$Record", "myVariable_current"):
            return trigger or None
        head, _, tail = ref.partition(".")
        if head.startswith("$") or head == "myVariable_current":
            return None
        if not tail:
            return variables.get(head) or lookups.get(head)
        if head in subflows and "." not in tail:
            called = flow_root((flows_by_api or {}).get(subflows[head]) or "")
            return flow_variables(called).get(tail) if called is not None else None
        return None
    out = []
    for tag, op in (("recordCreates", "create"), ("recordUpdates", "update"), ("recordDeletes", "delete")):
        for el in root.findall(tag):
            ref = el.findtext("inputReference")
            out.append((op, el.findtext("label") or el.findtext("name"), el.findtext("object") or resolve(ref), ref))
    return out


APEX_DML = re.compile(r"\b(insert|update|upsert|delete)\s+(?:new\s+([A-Za-z_]\w*)\s*\(|([A-Za-z_][\w.]*)\s*;)", re.I)
APEX_DB = re.compile(r"\bDatabase\.(insert|update|upsert|delete)\w*\s*\(\s*(?:new\s+([A-Za-z_]\w*)\s*\(|([A-Za-z_][\w.]*))", re.I)
APEX_DECL = re.compile(r"\b(?:(?:List|Set)\s*<\s*([A-Za-z_]\w*)\s*>|([A-Za-z_]\w*)\s*\[\s*\]|([A-Za-z_]\w*))\s+"
                       r"([A-Za-z_]\w*)\s*(?=[=;,)])")
APEX_OPS = {"insert": ["create"], "update": ["update"], "upsert": ["create", "update"], "delete": ["delete"]}


def apex_writes(body, known):
    """[(operations, statement, object or None)] for every DML statement of an Apex body. known: {lower-case API
    name: API name} of the objects the code is known to use; a variable's declared type counts only when it is one
    of them, so a DML statement on an untyped or unknown variable stays unresolved."""
    code = re.sub(r"/\*.*?\*/|//[^\n]*", " ", body or "", flags=re.S)
    code = re.sub(r"'(?:\\.|[^'\\])*'", "''", code)
    types = {}
    for m in APEX_DECL.finditer(code):
        t, var = m.group(1) or m.group(2) or m.group(3), m.group(4)
        if t.lower() in known or var not in types:
            types[var] = t
    out = []
    for rx in (APEX_DML, APEX_DB):
        for m in rx.finditer(code):
            t = m.group(2) or types.get((m.group(3) or "").split(".")[0])
            out.append((APEX_OPS[m.group(1).lower()], re.sub(r"\s+", " ", m.group(0)).strip(), known.get((t or "").lower())))
    return out


# --- what one automation writes

def graph_access(rows):
    """(writes, reads, unclear, calls) from one automation's own using rows. A row writes when its write flag is
    set or it names a Create, Update or Delete Record element; it only reads when just its read flag is set; a row
    that names neither (and is not just the Start element, the trigger) cannot be told apart and is unclear."""
    writes, reads, unclear, calls = {}, set(), set(), []
    for r in rows:
        rel = r.get("related") or {}
        t = rel.get("type") or ""
        els = elements(r.get("relationshipDescription"))
        if t in FOLLOWED:
            calls.append(rel)
            continue
        if is_object_type(t):
            api, label, node = rel.get("apiName"), rel.get("name"), rel.get("nodeId")
        elif t == "Field" and rel.get("object"):
            api, label, node = rel["object"], None, None
        else:
            continue
        if not api:
            continue
        ops = {WRITE_ELEMENTS[k] for k, _ in els if k in WRITE_ELEMENTS}
        words = [x for x in re.findall(r"[A-Za-z]+", r.get("relationshipDescription") or "") if x.lower() in APEX_WORDS] \
            if not els else []   # Apex rows say "Insert", "Update", "Read" instead of naming flow elements
        ops |= {o for x in words for o in APEX_WORDS[x.lower()]}
        # an object row naming a Create, Update or Delete Record element is that element's object, so it is written;
        # a field row names the element it appears in even when the field is only read there (a value assigned to
        # another record), so a field counts as written only with its write flag
        if r.get("write") is True or (ops and t != "Field"):
            w = writes.setdefault(api, {"object": api, "label": label, "nodeId": node, "operations": set(), "evidence": []})
            w["label"], w["nodeId"] = w["label"] or label, w["nodeId"] or node
            w["operations"] |= ops
            said = "; ".join([f"{k} '{lab}'" for k, lab in els if k in WRITE_ELEMENTS] + words) or "write flag"
            ev = f"dependency graph{' (field ' + str(rel.get('apiName')) + ')' if t == 'Field' else ''}: {said}"
            if ev not in w["evidence"]:
                w["evidence"].append(ev)
        elif r.get("read") is True:
            reads.add(api)
        elif r.get("read") is None and r.get("write") is None and is_object_type(t) and any(k != "Start" for k, _ in els):
            unclear.add(api)   # an object row naming elements but neither flag: read and write cannot be told apart
    for w in writes.values():   # a field row repeats its object's row: keep it only when it is the only evidence
        if any(not e.startswith("dependency graph (field") for e in w["evidence"]):
            w["evidence"] = [e for e in w["evidence"] if not e.startswith("dependency graph (field")]
    return writes, reads - set(writes), unclear - set(writes) - reads, calls


def add_write(writes, api, label, node, ops, evidence):
    w = writes.setdefault(api, {"object": api, "label": label, "nodeId": node, "operations": set(), "evidence": []})
    w["label"], w["nodeId"] = w["label"] or label, w["nodeId"] or node
    w["operations"] |= set(ops)
    if evidence not in w["evidence"]:
        w["evidence"].append(evidence)


def automation_writes(work, nodes, rows, sources, facts=None):
    """{nodeId: {"writes": [...], "reads", "unclear", "unresolved", "basis"}} for every automation in nodes ({nodeId:
    {name, apiName, type}}), each with what the flows and Apex classes it calls write ("via subflow 'X': ...")."""
    labels = {o.get("apiName"): o.get("name") for o in (work.inventory or {}).get("objects", [])}
    node_ids = {o.get("apiName"): o.get("nodeId") for o in (work.inventory or {}).get("objects", [])}
    known = {api.lower(): api for api in labels if api}
    for rs in rows.values():
        for r in rs:
            rel = r.get("related") or {}
            if is_object_type(rel.get("type")) and rel.get("apiName"):
                known[rel["apiName"].lower()] = rel["apiName"]
                labels.setdefault(rel["apiName"], rel.get("name"))
                node_ids.setdefault(rel["apiName"], rel.get("nodeId"))
    flows_by_api = {s.get("apiName"): s.get("xml") for s in sources.values() if s.get("xml")}
    own = {}

    def own_of(node):
        if node in own:
            return own[node]
        writes, reads, unclear, calls = graph_access(rows.get(node, []))
        unresolved, used = [], ["dependency graph"] if rows.get(node) else []
        src = sources.get(node) or {}
        if src.get("status") == "ok":
            used.append("definition")
            if src.get("xml") and (src.get("sfType") or nodes.get(node, {}).get("type")) not in ("Apex Trigger", "Apex Class"):
                found = flow_source_writes(src["xml"], flows_by_api)
                if found is None:
                    unresolved.append("its definition could not be read")
                for op, label, obj, ref in found or []:
                    kind = {"create": "Create", "update": "Update", "delete": "Delete"}[op] + " Records"
                    api = known.get((obj or "").lower(), obj)
                    if api:
                        add_write(writes, api, labels.get(api), node_ids.get(api), [op],
                                  f"definition: {kind} '{label}'" + (f" ({ref})" if ref else ""))
                    elif not any(f"'{label}'" in e for w in writes.values() for e in w["evidence"]):
                        unresolved.append(f"{kind} '{label}' on {ref or 'an unnamed reference'}: its object could not be worked out")
            elif src.get("body"):
                for ops, stmt, api in apex_writes(src["body"], known):
                    if api:
                        add_write(writes, api, labels.get(api), node_ids.get(api), ops, f"definition: {stmt}")
                    else:
                        unresolved.append(f"'{stmt}': the object of this DML statement could not be worked out")
        fact = (facts or {}).get(node) or {}
        if not used and fact.get("writes"):
            for x in fact["writes"]:
                api = known.get((x.get("object") or "").lower()) or next((a for a, lab in labels.items() if norm(lab) == norm(x.get("object"))), x.get("object"))
                add_write(writes, api, labels.get(api), node_ids.get(api), [o for o in x.get("operations", []) if o in OPS],
                          f"explanation (not checked against the definition): \"{x.get('evidence', '')}\"")
            used.append("explanation")
        own[node] = {"writes": writes, "reads": reads, "unclear": unclear, "unresolved": unresolved, "calls": calls,
                     "basis": used}
        return own[node]

    def full(node, path):
        mine = own_of(node)
        writes = {api: {**w, "operations": set(w["operations"]), "evidence": list(w["evidence"])} for api, w in mine["writes"].items()}
        reads, unclear, unresolved = set(mine["reads"]), set(mine["unclear"]), list(mine["unresolved"])
        for rel in mine["calls"]:
            sub = rel.get("nodeId")
            if not sub or sub in path:
                continue
            via = f"via {'subflow' if rel.get('type') == 'Flow' else 'Apex class'} '{rel.get('name') or rel.get('apiName')}'"
            if sub not in rows and sub not in sources:
                unresolved.append(f"{via}: not read yet")
                continue
            got = full(sub, path | {sub})
            for api, w in got["writes"].items():
                for ev in w["evidence"]:
                    add_write(writes, api, w["label"], w["nodeId"], w["operations"], f"{via}: {ev}")
            reads |= got["reads"]
            unclear |= got["unclear"]
            unresolved += [f"{via}: {u}" for u in got["unresolved"]]
        return {"writes": writes, "reads": reads - set(writes), "unclear": unclear - set(writes) - reads,
                "unresolved": unresolved, "basis": mine["basis"]}
    out = {}
    for node, info in nodes.items():
        got = full(node, {node})
        out[node] = {"nodeId": node, "name": info.get("name"), "apiName": info.get("apiName"), "type": info.get("type"),
                     "writes": [{"object": api, "label": w["label"] or labels.get(api) or api,
                                 "objectNodeId": w["nodeId"] or node_ids.get(api),
                                 "operations": [o for o in OPS if o in w["operations"]], "evidence": w["evidence"]}
                                for api, w in sorted(got["writes"].items())],
                     "reads": sorted(got["reads"]), "unclear": sorted(got["unclear"]), "unresolved": got["unresolved"],
                     "basis": got["basis"]}
    return out


def probe_nodes(placed, rows):
    """{nodeId: {name, apiName, type}}: the placed automations and every flow or Apex class they call, followed
    through the saved using rows."""
    nodes = dict(placed)
    frontier = list(placed)
    while frontier:
        n = frontier.pop()
        for r in rows.get(n, []):
            rel = r.get("related") or {}
            if rel.get("type") in FOLLOWED and rel.get("nodeId") and rel["nodeId"] not in nodes:
                nodes[rel["nodeId"]] = {"name": rel.get("name"), "apiName": rel.get("apiName"), "type": rel["type"]}
                frontier.append(rel["nodeId"])
    return nodes


def placed_automations(reports):
    return {s["nodeId"]: {"name": s["name"], "apiName": s["apiName"], "type": s["type"]}
            for r in reports for s in r["steps"]}


def placed_writes(work, reports, facts):
    """What every placed automation writes, with what the flows and Apex classes it calls write: from the saved using
    rows and definitions, and from the facts' writes for an automation with neither. The report and the drawing both
    take it from here with the same facts, so every object the report lists is drawn."""
    rows = using_rows(work)
    return automation_writes(work, probe_nodes(placed_automations(reports), rows), rows, stored_sources(work), facts or {})


def writes_next(work, reports, facts):
    """The next call the objects part needs, or None: the using rows of every placed automation and of what it
    calls, their definitions, and (usage basis only) the record counts of written objects the inventory lacks."""
    rows = using_rows(work)
    nodes = probe_nodes(placed_automations(reports), rows)
    for kind, tool, wanted, limit, extra, why in (
            ("using", "get_dependencies", sorted(set(nodes) - covered(work, "using")), 1000, {"lookingFor": "using"},
             "what each automation (and each flow or Apex class it calls) reads and writes: the rows' read and write "
             "flags and the elements they name"),
            ("source", "get_metadata_source",
             sorted(n for n in nodes if nodes[n]["type"] in SOURCE_TYPES and n not in covered(work, "source")), 5000, {},
             "each automation's definition: a flow's Create, Update and Delete Records elements, Apex DML statements")):
        if wanted:
            n = next_index(work, kind)
            chunk = wanted[:limit]
            save(wdir(work) / f"{kind}-{n}.request.json", {"nodeIds": chunk})
            return {"action": "call", "tool": tool, "arguments": work.call_args(nodeIds=chunk, **extra),
                    "saveTo": str(wdir(work) / f"{kind}-{n}{RESULT_EXT[kind]}"),
                    "save": "download every part and join them in index order (call again with identical arguments "
                            "until status is complete)", "why": why}
    if basis(work) != "usage":
        return None
    usage = object_usage(work)
    aw = automation_writes(work, nodes, rows, stored_sources(work), facts)
    wanted = sorted({w["objectNodeId"] for a in aw.values() for w in a["writes"]
                     if w["object"] not in usage and w["objectNodeId"]} - covered(work, "usage"))
    if not wanted:
        return None
    n = next_index(work, "usage")
    save(wdir(work) / f"usage-{n}.request.json", {"nodeIds": wanted[:50]})
    return {"action": "call", "tool": "get_component_usage", "arguments": work.call_args(nodeIds=wanted[:50]),
            "saveTo": str(wdir(work) / f"usage-{n}.json"), "save": "the whole result, as JSON",
            "why": "the run is on the usage basis: record counts of objects automations write that the inventory "
                   "does not hold, so an object with no records can be flagged"}


# --- what each box shows

def known_object_names(work):
    """{normalised name: name} of every Object resource on the levels this run has read: the library's spelling."""
    out = {}
    d = work.dir / "draw"
    for path in sorted(d.glob("*.json")) if d.exists() else []:
        if not path.name.startswith(("parent-", "layout-")):
            continue
        for a in (load(path, "diagram read").get("diagram") or {}).get("activities", []):
            for x in a.get("resources", []):
                if x.get("type") == "Object" and x.get("name"):
                    out.setdefault(norm(x["name"]), x["name"])
    return out


def library_paths(d, n):
    """(request, result) of library check round n: objects-library(.request).json, then objects-library-<n>."""
    stem = "objects-library" if n == 1 else f"objects-library-{n}"
    return d / f"{stem}.request.json", d / f"{stem}.json"


def library_rounds(d):
    """[(names, result path)] of the library checks saved so far, in order. The first checks every name new to the
    levels; each later one checks the names the drawing's rule gave instead of names the library holds as another
    type, until no unchecked name is left."""
    out, n = [], 1
    while True:
        req, res = library_paths(d, n)
        if not (req.exists() and res.exists()):
            return out
        out.append((load(req, "library check request").get("names", []), res))
        n += 1


def library_check(work):
    """(names the space library holds as another type than Object, names new to the library) from the dry run the
    objects part makes before its first write, a round at a time (library_rounds)."""
    other, new = set(), []
    for names, res in library_rounds(work.dir / "draw"):
        for issue in load(res, "library check").get("issues", []):
            m = re.match(r"changes\[(\d+)\]", issue.get("path") or "")
            if not m or int(m.group(1)) >= len(names):
                continue
            name = names[int(m.group(1))]
            if issue.get("code") == "resource_type_differs":
                other.add(norm(name))
            elif issue.get("code") == "resource_created":
                new.append(name)
    return other, [n for n in new if norm(n) not in other]


def resource_name(obj, known, other=()):
    """The name an object is drawn under, as the drawing names it. A level that already shows the object as an Object
    resource, under its label, its API name or one of the drawing's renamed forms, keeps that name. Otherwise its
    label, unless the space library holds the label as another type (a Human called Contact would draw that person):
    then the drawing's rule, object_rename in the plugin's scripts/layout_engine/write_loop.py: the API name when it
    differs and the library does not hold it as another type too, else "<label> (object)", else "<label> (object,
    <API name>)". None when every form is held as another type: the object is then named only in the box note."""
    label = obj.get("label") or obj.get("object")
    api = obj.get("object")
    forms = [label + OBJECT_SUFFIX, f"{label} (object, {api})"] if label else []
    for cand in [label, api] + forms:
        if cand and norm(cand) in known and norm(cand) not in other:
            return known[norm(cand)]
    name = label
    usable = bool(api) and norm(api) != norm(label) and norm(api) not in other
    while name is not None and norm(name) in other:
        name = object_rename(name, api, usable)
        usable = False
    return name


def object_places(others):
    """How many Object resources a status or automation box with this many other resources (people, systems)
    shows: what is left of MAX_LISTED, so no box carries more than MAX_LISTED resources, people included. People
    are never removed, so a box they already fill shows no object; every object left off is named in its note."""
    return max(0, MAX_LISTED - others)


def split_cap(others):
    """How many Object resources a record-type box with this many other resources shows: five resources in all
    with at least two objects, and never more than MAX_LISTED resources with the people included."""
    return min(max(USES_RESERVED, MAX_RESOURCES - others), object_places(others))


def tally(r, aw):
    """{API name: {"object", "label", "objectNodeId", "operations", "automations": [names], "evidence": [...], "first"}}
    of what a box's automations write, in chain order."""
    out = {}
    for i, s in enumerate(r["steps"]):
        for w in (aw.get(s["nodeId"]) or {}).get("writes", []):
            t = out.setdefault(w["object"], {"object": w["object"], "label": w["label"], "objectNodeId": w["objectNodeId"],
                                             "operations": [], "automations": [], "evidence": [], "first": i, "depth": 99})
            # how many calls away the write is: 0 when the automation itself writes, 1 through a subflow it calls...
            t["depth"] = min([t["depth"]] + [e.count("via ") for e in w["evidence"]])
            if s["name"] not in t["automations"]:
                t["automations"].append(s["name"])
            by = t.setdefault("by", {})
            by[s["name"]] = [o for o in OPS if o in set(by.get(s["name"], [])) | set(w["operations"])]
            t["operations"] = [o for o in OPS if o in set(t["operations"]) | set(w["operations"])]
            t["evidence"] += [f"{s['name']}: {e}" for e in w["evidence"]]
    return out


def ranked(lifecycle, written):
    """The lifecycle object first, then the written objects by the number of automations writing them; among equals,
    objects created before objects only updated or deleted, then what the automation writes itself before what the
    flows and classes it calls write, then the chain order and the label."""
    rest = sorted((t for api, t in written.items() if api != lifecycle["object"]),
                  key=lambda t: (-len(t["automations"]), "create" not in t["operations"], t.get("depth", 0), t["first"],
                                 (t["label"] or "").lower()))
    return [lifecycle] + rest


def automation_order(writes, lifecycle):
    """One automation's written objects as its box shows them: the lifecycle object first, then what it creates, then
    what it writes itself before what the flows and classes it calls write, then by label."""
    return sorted(writes, key=lambda w: (w["object"] != lifecycle, "create" not in w["operations"],
                                         min(e.count("via ") for e in w["evidence"]) if w["evidence"] else 0,
                                         (w["label"] or "").lower()))


def flag_text(t, verb_ops=None):
    ops = verb_ops or t["operations"]
    verb = " and ".join(VERB[o] for o in ops) or "written"
    who = "; ".join(t["automations"])
    these = "this automation" if len(t["automations"]) == 1 else "these automations"
    return (f"{t['label']}: {verb} by {who}, but the org holds no {t['label']} records, so {these} may never run "
            f"in practice")


def box_objects(work, r, aw, usage, others=1, before=None, known=None, other=()):
    """What a status box with automations shows: the lifecycle object and the objects its automations write,
    replacing the data-model objects; the objects past MAX_LISTED resources (people included) go in the box note."""
    if not r["steps"]:
        return None
    known = known or {}
    b = r["box"]
    written = tally(r, aw)
    life = written.get(b.get("object")) or {"object": b.get("object"), "label": b.get("objectLabel") or b.get("object"),
                                            "objectNodeId": None, "operations": [], "automations": [], "evidence": []}
    target = ranked(life, written)
    names = []
    for t in target:
        name = resource_name(t, known, other)
        if name is not None and norm(name) not in {norm(x) for x in names}:
            names.append(name)
    places = object_places(others)   # at most MAX_LISTED resources a box, people included; the note lists all
    flagged = [{"object": t["object"], "reason": flag_text(t)} for t in written.values()
               if zero_records(work, t["object"], usage)]
    all_unclear = sorted({x for s in r["steps"] for x in (aw.get(s["nodeId"]) or {}).get("unclear", [])} - set(written))
    unresolved = [f"{s['name']}: {u}" for s in r["steps"] for u in (aw.get(s["nodeId"]) or {}).get("unresolved", [])]
    return {"lifecycleObject": life["object"], "before": before, "after": names[:places], "overflow": names[places:],
            "written": [{**{k: t[k] for k in ("object", "label", "operations", "automations", "evidence")},
                         "by": t.get("by", {}),
                         "name": resource_name(t, known, other) or t["label"]} for t in target if t["object"] in written],
            "flagged": flagged, "unclear": all_unclear, "unresolved": unresolved}


def before_objects(work, b):
    """The Object resources a status box shows before this change, and how many other resources it has."""
    read = work.dir / "draw" / f"parent-{b['diagramId']}.json"
    if read.exists():
        for a in load(read, "parent read")["diagram"]["activities"]:
            if a["key"] == b["boxKey"]:
                rs = a.get("resources", [])
                return [x["name"] for x in rs if x.get("type") == "Object"], sum(1 for x in rs if x.get("type") != "Object")
    return b.get("objectsBefore"), 1


def rollup(work, reports, aw, known=None, reads=None, other=()):
    """Per record-type box on the split level: the lifecycle object, then the objects written most often across its
    statuses (written mode: the number of status boxes whose automations write each), or shown most often on its
    statuses after this change (level mode). [] when the mode is off or the levels are not one record type's."""
    if work.rollup == "off":
        return []
    known = known or {}
    out = []
    by_level = defaultdict(list)
    for r in reports:
        if r.get("recordType"):
            by_level[r["box"]["diagramId"]].append(r)
    for level, rs in by_level.items():
        read = (reads or {}).get(level)
        path = work.dir / "draw" / f"parent-{level}.json"
        if read is None and path.exists():
            read = load(path, "parent read")
        boundary = ((read or {}).get("diagram") or {}).get("boundary") or {}
        count = defaultdict(lambda: {"boxes": 0, "automations": set(), "label": None, "create": False, "depth": 99})
        life = {"object": rs[0]["box"].get("object"), "label": rs[0]["box"].get("objectLabel")}
        acts = {a["key"]: a for a in ((read or {}).get("diagram") or {}).get("activities", [])}
        for r in rs:
            written = tally(r, aw)
            if work.rollup == "written" or r["steps"]:
                for api, t in written.items():
                    count[api]["boxes"] += 1
                    count[api]["automations"] |= set(t["automations"])
                    count[api]["label"] = t["label"]
                    count[api]["create"] |= "create" in t["operations"]
                    count[api]["depth"] = min(count[api]["depth"], t["depth"])
            elif work.rollup == "level":
                for x in acts.get(r["box"]["boxKey"], {}).get("resources", []):
                    if x.get("type") == "Object":
                        count[x["name"]]["boxes"] += 1
                        count[x["name"]]["label"] = x["name"]
        order = sorted((api for api in count if norm(api) != norm(life["object"]) and norm(count[api]["label"]) != norm(life["label"])),
                       key=lambda a: (-count[a]["boxes"], -len(count[a]["automations"]), not count[a]["create"],
                                      count[a]["depth"], (count[a]["label"] or a).lower()))
        target = [life] + [{"object": a, "label": count[a]["label"] or a, "boxes": count[a]["boxes"]} for a in order]
        out.append({"diagramId": boundary.get("diagramId"), "boxKey": (boundary.get("activity") or {}).get("key"),
                    "boxText": (boundary.get("activity") or {}).get("text"), "level": level,
                    "recordType": rs[0].get("recordType"), "mode": work.rollup,
                    "objects": [{"object": t["object"], "label": t["label"], "boxes": t.get("boxes"),
                                 "name": resource_name(t, known, other)} for t in target]})
    return out


# --- notes

def verbs_by(by):
    """'created and updated by A; updated by B and C' from {automation: [operations]}."""
    groups = {}
    for name, ops in by.items():
        groups.setdefault(tuple(ops), []).append(name)
    def listed(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
    return "; ".join(f"{listed([VERB[o] for o in ops]) if ops else 'written'} by {listed(names)}"
                     for ops, names in groups.items())


NOTE_LIMIT = 2000   # the most characters manage_diagram takes in one note


def objects_used(r, objs, shown, compact=False):
    """The "Objects used" part of a status box's About this step note: every Object resource on the box, each with
    what the automations behind it do to it, and the opening line that says what the section lists."""
    b = r["box"]
    by_name = {norm(w["name"]): w for w in objs["written"]}
    replaced = [x for x in (objs.get("before") or []) if norm(x) not in {norm(n) for n in shown}]
    lines = ["Objects used: what the automations behind this step (its child level) write"
             + (f", replacing the objects the data model links to it ({', '.join(replaced)})" if replaced else "")
             + "; objects they only read are not shown; the evidence is in the run's report.md."]
    shown_set = {norm(n) for n in shown}
    every = list(shown)   # then every object left off, the lifecycle object too when the box's people fill it
    for name in list(objs.get("after") or []) + list(objs.get("overflow") or []) + [w["name"] for w in objs["written"]]:
        if norm(name) not in {norm(x) for x in every}:
            every.append(name)
    items = []   # (label, what the automations do to it)
    for name in every:
        w = by_name.get(norm(name))
        if w is None:
            items.append((name, f"the record this step moves to '{b['value']}'; the automations do not write it"))
            continue
        label = w["label"] + (f" (shown as {name})" if norm(name) != norm(w["label"]) else "")
        items.append((label, verbs_by(w.get("by") or {a: w["operations"] for a in w["automations"]})))
    if compact:   # a note too long for the server: objects the same automations write the same way share a line
        grouped = {}
        for label, what in items:
            grouped.setdefault(what, []).append(label)
        lines += [f"- {', '.join(labels)}: {what}" for what, labels in grouped.items()]
    else:
        lines += [f"- {label}: {what}" for label, what in items]
    hidden = [by_name[norm(n)]["label"] if norm(n) in by_name else n for n in every if norm(n) not in shown_set]
    if hidden:
        lines.append(f"Not shown as resources (a box carries at most {MAX_LISTED}): " + ", ".join(hidden) + ".")
    for f in objs.get("flagged", []):
        lines.append(f"Flag: {f['reason']}.")
    return lines


def rewrite_about(text, section):
    """The About this step note with its "Objects used" part (the line and the list under it) replaced by section;
    What happens, Why, Stage value and anything else stay as they are. Without such a part the section is added."""
    lines = (text or "").split("\n") if text else []
    at = next((i for i, x in enumerate(lines) if x.startswith("Objects used")), None)
    if at is None:
        return "\n".join(lines + section)
    end = at + 1
    while end < len(lines) and lines[end].startswith(("- ", "Also written (past", "Not shown as resources", "Flag: ")):
        end += 1
    return "\n".join(lines[:at] + section + lines[end:])


def rollup_note(ru, shown, overflow):
    if len(ru["objects"]) <= 1:
        return None
    life = ru["objects"][0]["label"]
    what = ("the number of its statuses whose automations write each" if ru["mode"] == "written"
            else "the number of its statuses that show each")
    lines = [f"Besides the {life}, the Object resources on this box are the objects the automations of this record "
             f"type's statuses write most often ({what}):"]
    lines += [f"- {o['label']}" + (f" (shown as {o['name']})" if o.get("name") and norm(o["name"]) != norm(o["label"]) else "")
              + f": {o['boxes']}" for o in ru["objects"][1:]]
    if overflow:
        lines.append(f"Also written (a box shows at most {MAX_RESOURCES} resources): {', '.join(overflow)}.")
    return "\n".join(lines)


# --- changes to one box, from a fresh read

def box_object_changes(act, names, note_title, note_text_of, cap=None):
    """manage_diagram changes that give one box its Object resources (names, in order) and its owned note, from the
    box as read (resources, attachments). Only Object resources and that note change; people, systems and every
    other attachment stay. note_text_of(shown, overflow) gives the note's text."""
    rs = act.get("resources", [])
    others = [x for x in rs if x.get("type") != "Object"]
    current = [x["name"] for x in rs if x.get("type") == "Object"]
    places = cap(len(others)) if cap else object_places(len(others))
    shown, overflow = names[:places], names[places:]
    keep = {norm(n) for n in shown}
    have = {norm(n) for n in current}
    changes = [{"op": "remove", "kind": "resource", "activity": act["key"], "name": n} for n in current if norm(n) not in keep]
    changes += [{"op": "add", "kind": "resource", "activity": act["key"], "name": n, "type": "Object"} for n in shown
                if norm(n) not in have]
    text = note_text_of(shown, overflow)
    mine = [a for a in act.get("attachments", []) if a.get("type") == "note" and a.get("title") == note_title]
    same = text is not None and len(mine) == 1 and re.sub(r"\s+", "", mine[0].get("text") or "") == re.sub(r"\s+", "", text)
    if not same:
        changes += [{"op": "remove", "kind": "attachment", "activity": act["key"], "type": "note", "key": a["key"]} for a in mine]
        if text:
            changes.append({"op": "add", "kind": "attachment", "activity": act["key"], "type": "note", "title": note_title,
                            "text": text})
    return changes


def objects_plans(work, reports, aw, usage, known, drilled, skip=(), other=()):
    """[(diagramId, kind, targets, hashbasis)]: every level the objects part changes. kind status: the lifecycle
    level's status boxes by key; child: a child level's automation boxes by the API name they link; split: the
    record-type boxes."""
    plans = []
    by_level = defaultdict(list)
    for r in reports:
        if r["steps"] and r["box"]["diagramId"] not in skip:
            by_level[r["box"]["diagramId"]].append(r)
    for level, rs in by_level.items():
        targets = {}
        for r in rs:
            before, _ = before_objects(work, r["box"])
            objs = box_objects(work, r, aw, usage, before=before, known=known, other=other)
            names = objs["after"] + objs["overflow"]
            _, others = before_objects(work, r["box"])
            targets[r["box"]["boxKey"]] = {"names": names, "note": STATUS_NOTE, "r": r, "objs": objs,
                                           "shown": names[:object_places(others)]}
        plans.append((level, "status", targets))
        for r in rs:
            child = drilled.get(r["box"]["boxKey"], {}).get(level)
            if not child or child in skip:
                continue
            ct = {}
            for s in r["steps"]:
                ws = automation_order((aw.get(s["nodeId"]) or {}).get("writes", []), r["box"].get("object"))
                if not ws:
                    continue
                flags = [flag_text({**w, "automations": [s["name"]]}) for w in ws if zero_records(work, w["object"], usage)]
                names = [n for n in (resource_name(w, known, other) for w in ws) if n]
                ct[s["apiName"]] = {"names": names, "note": AUTOMATION_NOTE, "writes": ws, "flags": flags,
                                    "shown": names[:MAX_LISTED - 1]}
            if ct:
                plans.append((child, "child", ct))
    split = defaultdict(dict)
    for ru in rollup(work, reports, aw, known, other=other):
        if ru["diagramId"] and ru["boxKey"] is not None and ru["diagramId"] not in skip and ru["level"] not in skip:
            split[ru["diagramId"]][ru["boxKey"]] = {"names": [o["name"] for o in ru["objects"] if o["name"]],
                                                    "note": ROLLUP_NOTE, "ru": ru}
    plans += [(d, "split", t) for d, t in split.items()]
    return plans


def plan_hash(kind, targets, extra=""):
    def plain(t):
        out = {k: v for k, v in t.items() if k in ("names", "note", "writes", "flags", "objs", "ru")}
        if t.get("shown") is not None and t["shown"] != t["names"]:
            out["shown"] = t["shown"]   # only a box the resource limit cuts changes its level's hash
        return out
    blob = json.dumps({str(k): plain(t) for k, t in targets.items()}, sort_keys=True, default=str) + kind + str(extra)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def level_object_changes(kind, targets, read):
    changes = []
    acts = read["diagram"]["activities"]
    for a in acts:
        if kind == "child":
            apis = [x.get("apiName") for x in a.get("attachments", []) if x.get("type") == "metadata"]
            t = next((targets[x] for x in apis if x in targets), None)
        else:
            t = targets.get(a["key"])
        if not t:
            continue
        if kind == "status":
            # one note a box: the separate note of the first version goes, and About this step lists the objects
            res = box_object_changes(a, t["names"], STATUS_NOTE, lambda shown, overflow: None)
            others = sum(1 for x in a.get("resources", []) if x.get("type") != "Object")
            shown = t["names"][:object_places(others)]
            about = [x for x in a.get("attachments", []) if x.get("type") == "note" and x.get("title") == ABOUT_STEP]
            old = about[0].get("text") if about else ""
            new = rewrite_about(old, objects_used(t["r"], t["objs"], shown))
            if len(new) > NOTE_LIMIT:
                new = rewrite_about(old, objects_used(t["r"], t["objs"], shown, compact=True))
            if len(new) > NOTE_LIMIT:
                names = list(dict.fromkeys(w["name"] for w in t["objs"]["written"]))
                hidden = [name for name in names if norm(name) not in {norm(n) for n in shown}]
                section = ["Objects used: " + ", ".join(names)]
                if hidden:
                    section.append("Not shown as resources: " + ", ".join(hidden))
                new = rewrite_about(old, section)
            if len(new) > NOTE_LIMIT:
                raise SetupError(f"Box {a['key']}: complete object names and protected note exceed {NOTE_LIMIT} characters; shorten the names or protected prose with the person before writing")
            if not about or re.sub(r"\s+", "", old or "") != re.sub(r"\s+", "", new):
                res += [{"op": "remove", "kind": "attachment", "activity": a["key"], "type": "note", "key": x["key"]}
                        for x in about]
                res.append({"op": "add", "kind": "attachment", "activity": a["key"], "type": "note", "title": ABOUT_STEP,
                            "text": new})
            changes += res
        elif kind == "child":
            # the objects are in the box's About this automation note (child_changes); the separate note goes
            changes += box_object_changes(a, t["names"], t["note"], lambda shown, overflow: None)
        else:
            def text_of(shown, overflow, t=t):
                return rollup_note(t["ru"], shown, overflow)
            changes += box_object_changes(a, t["names"], t["note"], text_of, cap=split_cap)
    return changes


def objects_next(work, reports, skip, facts=None):
    """The next call that puts the objects automations write on the boxes, or None when every level is done.
    Each level is read afresh (with its attachments) and only its Object resources and the note this part owns are
    changed; a level is done when its marker holds the hash of what it was given."""
    d = work.dir / "draw"
    aw = placed_writes(work, reports, facts)
    usage = object_usage(work)
    known = known_object_names(work)
    drilled = defaultdict(dict)
    for path in d.glob("parent-*.json"):
        doc = load(path, "parent read")
        for a in doc["diagram"]["activities"]:
            if a.get("drilldown"):
                drilled[a["key"]][doc.get("diagramId") or path.stem[len("parent-"):]] = a["drilldown"]
    for path in d.glob("children-*.json"):
        parent = path.name[len("children-"):].rsplit("-", 1)[0]
        for c in load(path, "add child result").get("children", []):
            drilled[c["activity"]][parent] = c["diagramId"]
    other, _ = library_check(work)
    plans = objects_plans(work, reports, aw, usage, known, drilled, skip, other)
    for kind_level, kind, targets in plans:
        n = None
        if kind == "child":
            n, result = latest_write(d, kind_level)
            if result is None or result.get("skipped") or write_failed(result):
                continue
        h = plan_hash(kind, targets, n)
        marker = d / f"objects-{kind_level}.json"
        mark = load(marker, "objects marker") if marker.exists() else {}
        if mark.get("hash") == h:
            continue
        written = d / f"objects-written-{kind_level}-{h}.json"
        # the read is keyed by the boxes it serves and the last write here, not by the names, so the library check
        # (which can change names) does not need a second read
        rkey = plan_hash(kind, {k: {} for k in targets}, f"{n}|{mark.get('version')}")
        read = d / f"objects-read-{kind_level}-{rkey}.json"
        if written.exists():
            res = load(written, "objects write")
            if res.get("status") == "running" or failure_code(res) in ("save_failed", "partial_save"):
                return {"action": "reconcile-write", "level": kind_level, "result": str(written),
                        "how": "Wait for the same map's complete outline if copying; read the level and reconcile resource, attachment and child side effects and genuine refs before replay."}
            if write_failed(res):
                # not done: the result and the read it was planned from are set aside, so the next run of next reads
                # the level afresh and plans the write again
                kept = set_aside(work, written, read)
                return {"action": "stop", "why": "the objects write was not saved", "level": kind_level,
                        "result": str(kept), "how": not_saved_how(res, kind_level)}
            save(marker, {"hash": h, "version": res.get("version")})
            continue
        if not read.exists():
            return {"action": "call", "tool": "get_diagram", "arguments": {"diagramId": kind_level, "include": ["attachments"]},
                    "saveTo": str(read), "save": "the whole result, as JSON",
                    "why": "its boxes' resources and notes as they are now: only Object resources and the objects note change"}
        rounds = library_rounds(d)
        checked = {norm(nm) for names, _ in rounds for nm in names}
        names = sorted({nm for _, _, ts in plans for t in ts.values() for nm in t["names"]
                        if norm(nm) not in known and norm(nm) not in checked})
        doc = require_complete(load(read, "objects read"))
        names = names[:10]
        if names and doc["diagram"]["activities"]:
            req, res = library_paths(d, len(rounds) + 1)
            save(req, {"names": names})
            key = doc["diagram"]["activities"][0]["key"]
            return {"action": "call", "tool": "manage_diagram", "arguments": {
                        "diagramId": kind_level, "baseVersion": doc["version"], "dryRun": True, "createResources": True,
                        "changes": [{"op": "add", "kind": "resource", "activity": key, "name": nm, "type": "Object"}
                                    for nm in names]},
                    "saveTo": str(res), "save": "the whole result, as JSON (a dry run: nothing is saved)",
                    "why": "before the first write, for every object name no level shows yet: which names the space library "
                           "holds as another type (resource_type_differs: a Human called Contact would be drawn instead, so "
                           "the object takes the drawing's next name, which is checked the same way) and which are new "
                           "(resource_created: added as Object)"}
        try:
            changes = level_object_changes(kind, targets, doc)
        except SetupError as exc:
            return {"action": "stop", "why": "complete object note exceeds the server limit", "level": kind_level,
                    "how": str(exc)}
        if not changes:
            save(marker, {"hash": h, "unchanged": True})
            continue
        args = {"diagramId": kind_level, "baseVersion": load(read, "objects read")["version"], "changes": changes,
                "createResources": True}
        removes = sum(1 for c in changes if c["op"] == "remove")
        if removes:
            args["confirm"] = True
        return {"action": "call", "tool": "manage_diagram", "arguments": args, "saveTo": str(written),
                "save": "the whole result, as JSON",
                "why": {"status": "the status boxes show the objects their automations write",
                        "child": "each automation box shows the objects it writes",
                        "split": "each record-type box shows the objects written most often in its lifecycle"}[kind],
                "note": "createResources adds missing Object resources to the space library (they are added without "
                        "asking); people and systems are never added here",
                "onError": "save the result at saveTo even when it failed, and run next: a failed write is set aside "
                           "(the level is read afresh) and next says what to do"}
    return None


def via_of(w):
    """'via subflow 'Create Invoice'' when the automation writes the object only through what it calls, else ''."""
    if not w["evidence"] or any(not e.startswith("via ") for e in w["evidence"]):
        return ""
    e = min(w["evidence"], key=lambda x: x.count("via "))
    return ", ".join(m for m in re.findall(r"via (?:subflow|Apex class) '[^']*'", e))


def objects_report(work, reports, facts):
    """Adds objects to every report box with steps and returns (writes doc, roll-up list)."""
    aw = placed_writes(work, reports, facts)
    usage = object_usage(work)
    known = known_object_names(work)
    other, _ = library_check(work)
    for r in reports:
        before, others = before_objects(work, r["box"])
        r["objects"] = box_objects(work, r, aw, usage, others=others, before=before, known=known, other=other)
        for s in r["steps"]:
            s["writes"] = [{"object": w["object"], "label": w["label"], "operations": w["operations"],
                            "via": via_of(w)}
                           for w in automation_order((aw.get(s["nodeId"]) or {}).get("writes", []), r["box"].get("object"))]
    ru = rollup(work, reports, aw, known, other=other)
    for x in ru:
        x["after"] = [o["name"] for o in x["objects"][:split_cap(1)] if o["name"]]
        x["overflow"] = [o["name"] or o["label"] for o in x["objects"][split_cap(1):]]
    return {"basis": basis(work), "automations": aw}, ru


# ----------------------------------------------------------------- next

def emit(work, action):
    def bind(call, tool):
        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            if work.team:
                arguments["teamId"] = work.team
            if tool in ("get_diagram", "get_metadata_component", "get_component_usage"):
                arguments["delivery"] = "file"
            if tool == "get_diagram":
                arguments.setdefault("include", ["layout", "attachments"])
        if tool in ("get_dependencies", "get_metadata_source", "list_metadata_by_criteria") and str(call.get("saveTo", "")).endswith(".ndjson"):
            call["save"] = "Use scripts/acquire_result.py native --input REPLY.json --out " + call["saveTo"] + "; retain its .acquisition.json sidecar and repeat until exit 0 with every part and failure accounted for"
        for child in call.get("calls", []):
            bind(child, child.get("tool", tool))
    bind(action, action.get("tool"))
    if action.get("tool") == "manage_diagram" and action.get("arguments", {}).get("changes"):
        batches = split_changes(action["arguments"]["changes"])
        if len(batches) > 1:
            digest = hashlib.sha256(json.dumps(action["arguments"], sort_keys=True).encode()).hexdigest()[:16]
            path = work.dir / "draw" / ".plans" / f"{digest}.json"
            plan = dict(action["arguments"], dryRunFirst=True)
            plan.pop("dryRun", None)
            save(path, plan)
            final = action.get("saveTo")
            dry_target = final if action["arguments"].get("dryRun") else None
            if dry_target:
                final = final.replace("/dry-", "/written-")
            step = next_batch(path, final)
            if step["action"] == "done" and dry_target:
                save(Path(dry_target), {"issues": [], "batchResults": step["result"]["batchResults"]})
            if step["action"] == "done":
                action = {"action": "continue", "how": "All batches are saved with genuine intermediate versions; run next again."}
            else:
                action = step
    if action.get("action") not in ("done", "skipped"):   # done.json stands only while the latest next finished the run
        set_aside(work, work.dir / "done.json", folder="superseded")
    save(work.dir / "_next.json", action)
    print(json.dumps(action, indent=1, ensure_ascii=False))
    return 0


def load_facts(work, autos):
    facts, problems = {}, {}
    for node in autos:
        path = work.dir / "facts" / f"{node}.json"
        bpath = work.dir / "briefs" / f"{node}.json"
        if path.exists() and bpath.exists():
            fact = load(path, "facts")
            bdoc = load(bpath, "brief")
            p = facts_problems(fact, bdoc)
            if p:
                problems[node] = p
            else:
                fact["_source"] = bdoc.get("evidenceSource", "explanation")
                facts[node] = fact
    return facts, problems


def analyse(work):
    counts = work.manifest()
    rows = work.rows()
    per_box = candidates(work, counts, rows)
    return counts, rows, per_box, automations(per_box)


def cmd_next(args):
    work = Work(args.work)
    counts = work.manifest()
    if counts is None:
        return emit(work, {"action": "call", "tool": "get_dependencies",
                           "arguments": work.call_args(lookingFor="where_used", mode="manifest", nodeIds=work.all_nodes(), delivery="file"),
                           "saveTo": str(work.dir / "metadata" / "manifest.json"), "save": "the whole result, as JSON"})
    need = work.needed_row_types(counts)
    missing = [t for t in need if not work.rows_path(t).exists()]
    if missing:
        return emit(work, {"action": "calls", "tool": "get_dependencies", "calls": [
            {"arguments": work.call_args(lookingFor="where_used", nodeIds=need[t], sfType=t),
             "saveTo": str(work.rows_path(t)),
             "save": "download every part and join them in index order (call again with identical arguments until status is complete)"}
            for t in missing]})
    _, rows, per_box, autos = analyse(work)
    calls = []
    for t, columns in ATTRIBUTE_TYPES.items():
        names = sorted({a["apiName"] for a in autos.values() if a["type"] == t and a.get("apiName")})
        for i in range(0, len(names), 100):
            target = work.dir / "metadata" / f"attributes-{slug(t)}-{i // 100 + 1}.ndjson"
            if not target.exists():
                calls.append({"arguments": work.call_args(metadataList=[t], columns=columns,
                                filters=[{"column": "api_name", "operator": "eq", "value": name} for name in names[i:i + 100]]),
                              "saveTo": str(target)})
    if calls:
        return emit(work, {"action": "calls", "tool": "list_metadata_by_criteria", "calls": calls,
                           "save": "acquire every native part, terminal status/resultId and all failures using acquire_result.py native; save the sidecar with the rows",
                           "why": "stored active, subtype, trigger and order evidence for every requested automation"})
    state = explain_state(work, autos)
    wanted, given_up = explain_wanted(work, autos, state)
    if wanted:
        n = len(list((work.dir / "explain").glob("*.json"))) + 1
        by_aspect = defaultdict(list)
        for aspect, node in wanted:
            by_aspect[aspect].append(node)
        calls = []
        for aspect, nodes in by_aspect.items():
            for i in range(0, len(nodes), EXPLAIN_BATCH):
                calls.append({"waitSeconds": max([state.get(node, {}).get(aspect, {}).get("retryAfterSeconds") or 0
                                                 for node in nodes[i:i + EXPLAIN_BATCH]] or [0]),
                              "arguments": work.call_args(aspect=aspect, nodeIds=nodes[i:i + EXPLAIN_BATCH], delivery="file"),
                              "saveTo": str(work.dir / "explain" / f"{n}.json")})
                n += 1
        return emit(work, {"action": "calls", "tool": "explain_metadata_components", "calls": calls,
                           "save": "the whole result as JSON (download it when it comes as a file); items that are "
                                   "running are polled; failed/rate_limited items get one retry after their retryAfterSeconds delay",
                           **({"withoutExplanation": given_up} if given_up else {})})
    described = descriptions(work)
    if given_up and not list((work.dir / "metadata").glob("descriptions*.json")):
        nodes = sorted(given_up)
        return emit(work, {"action": "calls", "tool": "get_metadata_component", "calls": [
            {"arguments": work.call_args(nodeIds=nodes[i:i + 50]), "saveTo": str(work.dir / "metadata" / f"descriptions-{i // 50 + 1}.json")}
            for i in range(0, len(nodes), 50)],
            "save": "the whole result, as JSON",
            "why": "no explanation could be generated for these automations; their own descriptions are the fallback evidence, "
                   "flagged on every step that rests on them",
            "withoutExplanation": given_up})
    pending = []
    for node, a in autos.items():
        if stored_block(a, work.attrs):
            continue
        expl = explanation(work, a, state)
        if expl is None and described.get(node):
            expl = {"aspect": "description", "narrative": described[node], "confidence": None,
                    "why": given_up.get(node)}
        if expl is None:
            continue
        bpath = work.dir / "briefs" / f"{node}.json"
        save(bpath, brief(work, a, expl, per_box))
        if not (work.dir / "facts" / f"{node}.json").exists():
            pending.append(node)
    facts, problems = load_facts(work, autos)
    if pending or problems:
        return emit(work, {"action": "agents", "agent": "automation-firing-reader",
                           "briefs": [str(work.dir / "briefs" / f"{n}.json") for n in pending + list(problems)],
                           "factsDir": str(work.dir / "facts"),
                           "findings": problems,
                           "how": "one agent per up to 8 briefs, in parallel; each writes facts/<nodeId>.json per brief"})
    reports = [box_report(work, b, per_box, autos, facts, record_type_links(work, rows)) for b in work.boxes]
    step = writes_next(work, reports, facts)
    if step:
        return emit(work, step)
    report = work.dir / "report.json"
    if not report.exists() or load(report, "report").get("objectsInput") != objects_signature(work):
        return emit(work, {"action": "run", "command": f"python3 {Path(__file__)} report {work.dir}"})
    return draw_next(work, set(args.skip or []), args.redraw, facts)


# ----------------------------------------------------------------- report

def cmd_report(args):
    work = Work(args.work)
    _, rows, per_box, autos = analyse(work)
    state = explain_state(work, autos)
    _, given_up = explain_wanted(work, autos, state)
    facts, problems = load_facts(work, autos)
    if problems:
        raise SetupError("facts files have problems; run next")
    rt_links = record_type_links(work, rows)
    reports = [box_report(work, b, per_box, autos, facts, rt_links) for b in work.boxes]
    for r in reports:
        for x in r["unverified"]:
            if x["nodeId"] in given_up and x["nodeId"] not in facts:
                x["reason"] = given_up[x["nodeId"]] + " and it has no description"
    writes_doc, ru = objects_report(work, reports, facts)
    save(wdir(work) / "writes.json", writes_doc)
    save(work.dir / "report.json", {"boxes": reports, "basis": writes_doc["basis"], "rollup": ru,
                                    "objectsInput": objects_signature(work)})
    other, new = library_check(work)
    lib = []
    if new or other:
        names = [nm for round_names, _ in library_rounds(work.dir / "draw") for nm in round_names]
        lib = ["# Space library", ""]
        if new:
            lib.append(f"Object resources new to the space library, added as Object when first drawn: {', '.join(new)}.")
        if other:
            held = [n for n in names if norm(n) in other]
            lib.append(f"Held by the library as another type (a person or system), so the object is drawn under the "
                       f"drawing's next name (its API name, '<label> (object)' or '<label> (object, <API name>)'): "
                       f"{', '.join(held)}.")
        lib.append("")
    (work.dir / "report.md").write_text(report_md(reports, ru, writes_doc["basis"]) + "\n".join(lib), encoding="utf-8")
    placed = sum(len(r["steps"]) for r in reports)
    print(f"{len(reports)} boxes, {placed} automation steps placed, "
          f"{sum(1 for r in reports if has_child(r))} boxes get a child level; report.md written")
    return 0


# ----------------------------------------------------------------- draw

def layout_hash(r, reg):
    return hashlib.sha1(json.dumps(child_changes(r, reg), sort_keys=True).encode("utf-8")).hexdigest()[:12]


def write_failed(res):
    """True when a saved manage_diagram result changed nothing: saved false, an error, or an issue of severity error."""
    return ((res.get("status") == "running" or not (write_complete(res) or res.get("skipped"))) or bool(res.get("error"))
            or any((i or {}).get("severity") == "error" for i in res.get("issues") or []))


def failure_code(res):
    err = res.get("error")
    if isinstance(err, dict):
        return err.get("code") or err.get("message") or "error"
    if err:
        return str(err)
    return next((i.get("code") for i in res.get("issues") or [] if (i or {}).get("severity") == "error"), None) or "not saved"


def not_saved_how(res, level):
    return (f"{failure_code(res)}: verify level {level} and reconcile any side effects before replay. When someone has it open in the editor "
            f"(lock_held), run next --skip {level} to go on with the other levels, and next without it "
            f"once they have left it; otherwise run next: the level is read afresh and the write planned again")


def set_aside(work, *paths, folder="failed"):
    """Moves saved files into draw/<folder>/ under a new number (never over another), so the step they belong to
    runs again; returns where the first one went. Moving instead of deleting keeps the evidence and works in a
    folder that refuses deletes."""
    target = work.dir / "draw" / folder
    first = None
    for p in map(Path, paths):
        if not p.exists():
            continue
        target.mkdir(parents=True, exist_ok=True)
        k = 1
        while (target / f"{p.stem}.{k}{p.suffix}").exists():
            k += 1
        p.rename(target / f"{p.stem}.{k}{p.suffix}")
        first = first or target / f"{p.stem}.{k}{p.suffix}"
    return first


def drawn_levels(d):
    """(child levels the skill drew, child levels left as they were because they already had boxes), from the last
    write to each; a write that saved nothing is neither."""
    drawn, left = [], []
    for path in sorted(d.glob("written-*.json")) if d.exists() else []:
        child = path.name[len("written-"):-len(".json")]
        _, result = latest_write(d, child)
        if result.get("skipped"):
            left.append(child)
        elif not write_failed(result):
            drawn.append(child)
    return drawn, left


def refused_levels(d):
    """{child level: record} of the child levels someone edited after the skill drew them (a redraw refused with
    version_conflict): the skill never draws over their edits."""
    return {p.name[len("refused-"):-len(".json")]: load(p, "refused level") for p in d.glob("refused-*.json")} \
        if d.exists() else {}


def skipped_levels(d, reports, skip, refused):
    """[{diagramId, title, reason}]: the levels passed with --skip (open in the editor; edited by someone when the level
    holds a refused child level) and the refused child levels."""
    titles, holds = {}, defaultdict(set)
    for r in reports:
        titles.setdefault(r["box"]["diagramId"], None)
    for path in d.glob("parent-*.json") if d.exists() else []:
        doc = load(path, "parent read")
        level = doc.get("diagramId") or path.stem[len("parent-"):]
        titles[level] = doc.get("title")
        texts = {r["box"]["boxKey"]: r["box"].get("boxText") for r in reports if r["box"]["diagramId"] == level}
        for a in doc["diagram"]["activities"]:
            if a.get("drilldown"):
                titles.setdefault(a["drilldown"], texts.get(a["key"]) or a.get("text"))
    for path in d.glob("children-*.json") if d.exists() else []:
        level = path.name[len("children-"):].rsplit("-", 1)[0]
        texts = {r["box"]["boxKey"]: r["box"].get("boxText") for r in reports if r["box"]["diagramId"] == level}
        for c in load(path, "add child result").get("children", []):
            titles.setdefault(c["diagramId"], texts.get(c["activity"]))
    for path in d.glob("layout-*.json") if d.exists() else []:
        title = load(path, "child read").get("title")
        if title:
            titles[path.stem[len("layout-"):]] = title
    for child, rec in refused.items():
        holds[rec.get("parent")].add(child)
        titles[child] = titles.get(child) or rec.get("boxText")
    out = [{"diagramId": x, "title": titles.get(x) or x,
            "reason": "edited by someone" if x in refused or holds.get(x) else "open in the editor"} for x in sorted(skip)]
    out += [{"diagramId": c, "title": titles.get(c) or c, "reason": "edited by someone"} for c in sorted(refused) if c not in skip]
    return out


def latest_write(d, child):
    """(n, result) of the last write to a child level: written-<child>.json is 0, rewritten-<child>-<n>.json n."""
    found = []
    if (d / f"written-{child}.json").exists():
        found.append((0, d / f"written-{child}.json"))
    for path in d.glob(f"rewritten-{child}-*.json"):
        found.append((int(path.stem.rsplit("-", 1)[1]), path))
    if not found:
        return None, None
    n, path = max(found)
    return n, load(path, "write result")


def text_only_changes(added, layout):
    """When the boxes and lines the last write added are the ones the new layout adds (same texts, labels and
    places), the changes that only swap the texts that differ: each box's note attachment and the level note. Keeps
    the boxes, so their numbers and anything a person attached to them stay. None when the chain itself changed."""
    def bare(text):   # the server puts spaces after some quotes, brackets and slashes: compare without spaces
        return re.sub(r"\s+", "", text or "")

    def shape(items):
        """Boxes (text, place, resources, metadata links) and line labels; new boxes' resources and links are
        separate changes keyed by the box's ref."""
        def extras(c):
            if "attachments" in c or "resources" in c:   # as the server reports a box it added
                return (sorted(x["name"] for x in c.get("resources", [])),
                        sorted(x.get("apiName") for x in c.get("attachments", []) if x.get("type") == "metadata"))
            ref = c.get("ref")
            return (sorted(x["name"] for x in items if x.get("kind") == "resource" and x.get("activity") == ref),
                    sorted(x["apiName"] for x in items if x.get("kind") == "attachment" and x.get("activity") == ref
                           and x.get("type") == "metadata"))
        acts = [(bare(c["text"]), c.get("position", {}).get("x", c.get("x")), c.get("position", {}).get("y", c.get("y")),
                 extras(c)) for c in items if c.get("kind") == "activity"]
        lines = [bare(c.get("label")) for c in items if c.get("kind") == "line"]
        return acts, sorted(lines)
    new_adds = [c for c in layout if c["op"] == "add"]
    if shape(added) != shape(new_adds) or (len([c for c in added if c["kind"] == "note"])
                                            != len([c for c in new_adds if c["kind"] == "note"])):
        return None
    old_acts = [c for c in added if c["kind"] == "activity"]
    refs = [c["ref"] for c in new_adds if c["kind"] == "activity"]
    changes = []
    for old, ref in zip(old_acts, refs):
        note = next(c for c in new_adds if c["kind"] == "attachment" and c["activity"] == ref and c["type"] == "note")
        key = next((a["key"] for a in old.get("attachments", []) if a["type"] == "note"), None)
        if key is not None:
            changes.append({"op": "remove", "kind": "attachment", "activity": old["key"], "type": "note", "key": key})
        changes.append({**note, "activity": old["key"]})
    old_notes = [c for c in added if c["kind"] == "note"]
    new_notes = [c for c in new_adds if c["kind"] == "note"]
    for o, nn in zip(old_notes, new_notes):
        changes.append({"op": "update", "kind": "note", "key": o["key"], "text": nn["text"]})   # keep where a person put it
    return changes


def level_version(d, level, result):
    """The newest version of a level this run knows: its last layout write, or a later objects write."""
    mark = d / f"objects-{level}.json"
    return max(result.get("version") or 0, (load(mark, "objects marker").get("version") or 0) if mark.exists() else 0)


OWN_BOX_NOTES = ("About this automation", "About this check")


def with_current_note_keys(added, result):
    """The boxes the skill drew, with the keys their note has now. A text-only redraw removes a box's note and adds
    a new one, which takes a new key when another note sits on the box (the objects part's), so the keys are taken
    from the last write's diff (each changed box's note as it is after that write)."""
    keys = {}
    for c in (result.get("diff") or {}).get("changed", []):
        if c.get("kind") == "activity":
            for a in (c.get("after") or {}).get("attachments", []):
                if a.get("type") == "note" and a.get("title") in OWN_BOX_NOTES:
                    keys[c["key"]] = a["key"]
    out = []
    for x in added:
        if x.get("kind") == "activity" and x.get("key") in keys:
            x = {**x, "attachments": [a for a in x.get("attachments", []) if a.get("type") != "note"]
                 + [{"key": keys[x["key"]], "type": "note"}]}
        out.append(x)
    return out


def redraw_call(work, d, r, child, n, result, h):
    """Replace what the last write added to a child level with the current layout, in one all-or-nothing change.
    When only texts changed (flags, evidence, conditions), only those are swapped and the boxes stay."""
    added = (result.get("diff") or {}).get("added", [])
    if not any(x.get("kind") == "activity" for x in added):
        # the last write only swapped texts, so its diff adds nothing: what the skill drew is the plan's basis
        plan = d / f"plan-{child}-{n}.json"
        added = (load(plan, "plan") if plan.exists() else {}).get("basis") or added
    canvas = load(d / f"layout-{child}.json", "child read")["diagram"].get("canvas")
    layout = child_changes(r, work.reg, canvas=canvas)
    added = with_current_note_keys(added, result)
    changes = text_only_changes(added, layout)
    basis = added if changes is not None else None
    if changes is None:
        changes = ([{"op": "remove", "kind": "line", "key": x["key"]} for x in added if x.get("kind") == "line"]
                   + [{"op": "remove", "kind": "activity", "key": x["key"]} for x in added if x.get("kind") == "activity"]
                   + [{"op": "remove", "kind": "note", "key": x["key"]} for x in added if x.get("kind") == "note"]
                   + layout)
    save(d / f"plan-{child}-{n + 1}.json", {"hash": h, **({"basis": basis} if basis else {})})
    return emit(work, {"action": "call", "tool": "manage_diagram",
                       "arguments": write_args(r, work.reg, child, level_version(d, child, result), changes, confirm=True),
                       "saveTo": str(d / f"rewritten-{child}-{n + 1}.json"), "save": "the whole result, as JSON",
                       "why": "the report changed since this child level was drawn: what the skill drew is replaced",
                       "onError": f"version_conflict: someone edited the level since the skill drew it, and the skill does not "
                                  f"draw over their edits: run next --skip {r['box']['diagramId']} and tell the person this child "
                                  f"level still shows the earlier chain (report.md holds the current one)"})


def failed_child_write(work, d, r, child, n, result):
    """A child-level write that saved nothing does not count as drawn. Its result is set aside (for the first
    write, with the level read it was planned from, so the level is read afresh), the write is planned again on the
    next run of next, and the run stops with what to do."""
    path = d / (f"written-{child}.json" if n == 0 else f"rewritten-{child}-{n}.json")
    if n == 0:
        kept = set_aside(work, path, d / f"layout-{child}.json")
        how = not_saved_how(result, child)
    else:
        kept = set_aside(work, path)
        if failure_code(result) == "version_conflict":
            # someone edited the level since the skill drew it: it is never drawn over, and no longer holds the run up
            save(d / f"refused-{child}.json", {"child": child, "parent": r["box"]["diagramId"], "boxText": r["box"].get("boxText"),
                                               "reason": "edited by someone", "result": str(kept)})
        how = (f"{failure_code(result)}: the redraw of child level {child} saved nothing. version_conflict: someone "
               f"edited the level since the skill drew it, and the skill does not draw over their edits: run next --skip "
               f"{r['box']['diagramId']} and tell the person this child level still shows the earlier chain (report.md "
               f"holds the current one). lock_held: someone has it open; run next --skip {child} to go on "
               f"with the other levels, and next --redraw once they have left it")
    return emit(work, {"action": "stop", "why": "a child-level write saved nothing, so the level is not drawn",
                       "level": child, "result": str(kept), "how": how})


def has_child(r):
    """A status box gets a child level when something runs on its save, a validation rule guards it, or a
    scheduled flow is tied to it."""
    return bool(r["steps"] or r.get("conditions") or r.get("scheduled"))


def write_args(r, reg, child, version, changes, confirm=False):
    """manage_diagram arguments for a child level. createResources adds any resource the space library lacks (the
    check box's Validation Rule, an automation type's resource); the hand-off names what was added."""
    return {"diagramId": child, "baseVersion": version, "changes": changes,
            **({"confirm": True} if confirm else {}), "createResources": True}


def read_layout(work, d, child):
    """Emits the read of a child level with its canvas and returns True, or returns False when it is read."""
    path = d / f"layout-{child}.json"
    if path.exists():
        require_complete(load(path, "child layout"))
        return False
    emit(work, {"action": "call", "tool": "get_diagram", "arguments": {"diagramId": child, "include": ["layout"]},
                       "saveTo": str(path), "save": "the whole result, as JSON",
                       "why": "its canvas, where the chain is placed (a child level's canvas does not always start at 0), "
                              "its version and its boundary stubs"})
    return True


def draw_next(work, skip=(), redraw=False, facts=None):
    reports = load(work.dir / "report.json", "report")["boxes"]
    d = work.dir / "draw"
    drawn_boxes = {c["activity"]: c["diagramId"] for path in d.glob("children-*.json")
                   for c in load(path, "add child result").get("children", [])} if d.exists() else {}
    todo = [r for r in reports if has_child(r) or (redraw and r["box"]["boxKey"] in drawn_boxes)]
    stale = []
    refused = refused_levels(d)
    by_parent = defaultdict(list)
    for r in todo:
        by_parent[r["box"]["diagramId"]].append(r)
    for parent, rs in by_parent.items():
        if parent in skip:
            continue
        read = d / f"parent-{parent}.json"
        if not read.exists():
            return emit(work, {"action": "call", "tool": "get_diagram", "arguments": {"diagramId": parent},
                               "saveTo": str(read), "save": "the whole result, as JSON",
                               "why": "the level's version, and which status boxes already have a child level"})
        doc = load(read, "parent read")
        rs = [{**r, "box": {**r["box"], "boundary": parent_boundary(doc, r["box"]["boxKey"]), "refModelId": work.ref}} for r in rs]
        drill = {a["key"]: a.get("drilldown") for a in doc["diagram"]["activities"]}
        for added in d.glob(f"children-{parent}-*.json"):
            for c in load(added, "add child result").get("children", []):
                drill[c["activity"]] = c["diagramId"]
        without = [r for r in rs if not drill.get(r["box"]["boxKey"]) and has_child(r)]
        if without:
            added = d / f"children-{parent}-{doc['version']}.json"
            if added.exists():
                return emit(work, {"action": "call", "tool": "get_diagram", "arguments": {"diagramId": parent},
                                   "saveTo": str(read), "save": "the whole result, as JSON (it replaces the earlier read)",
                                   "why": "the add saved no child level ids; read them from the level"})
            return emit(work, {"action": "call", "tool": "manage_diagram",
                               "arguments": {"diagramId": parent, "baseVersion": doc["version"],
                                             "changes": [{"op": "add", "kind": "child", "activity": r["box"]["boxKey"]} for r in without]},
                               "saveTo": str(added), "save": "the whole result, as JSON",
                               "note": "each status box gets its child level; its Object resources and Objects used note reflect the automations behind it"})
        for r in rs:
            child = drill.get(r["box"]["boxKey"])
            if not child or child in skip:   # --skip takes a status level (all its child levels) or one child level
                continue
            written = d / f"written-{child}.json"
            n, result = latest_write(d, child)
            if result is not None and (result.get("status") == "running" or failure_code(result) in ("save_failed", "partial_save")):
                return emit(work, {"action": "reconcile-write", "level": child,
                                   "how": "Wait on this map's complete outline if copying; read the level and reconcile side effects and genuine saved refs before replay."})
            if result is not None and write_failed(result):
                return failed_child_write(work, d, r, child, n, result)
            if child in refused:   # someone edited it since the skill drew it: never drawn over, listed when the run ends
                continue
            if result is not None:
                if result.get("skipped"):
                    continue
                h = layout_hash(r, work.reg)
                plan = d / f"plan-{child}-{n}.json"
                if plan.exists() and load(plan, "plan").get("hash") == h:
                    continue
                if redraw:
                    return 0 if read_layout(work, d, child) else redraw_call(work, d, r, child, n, result, h)
                stale.append(child)
                continue
            # a new child level holds one unattached stub per line in or out of its box; it is read first for
            # them, its version and its canvas
            if read_layout(work, d, child):
                return 0
            cdoc = load(d / f"layout-{child}.json", "child read")
            if cdoc["diagram"]["activities"]:
                save(written, {"skipped": "the child level already has activities; it was left as it is"})
                continue
            stubs = [ln["key"] for ln in cdoc["diagram"]["lines"] if ln.get("from") is None and ln.get("to") is None]
            # the level keeps the title Elements gives it (its box's text); confirm covers removing the stubs
            args = write_args(r, work.reg, child, cdoc["version"],
                              child_changes(r, work.reg, stubs, cdoc["diagram"].get("canvas")), confirm=bool(stubs))
            save(d / f"plan-{child}-0.json", {"hash": layout_hash(r, work.reg)})
            first = not any(d.glob("written-*.json"))
            dry = d / f"dry-{child}.json"
            if first and not dry.exists():
                return emit(work, {"action": "call", "tool": "manage_diagram", "arguments": {**args, "dryRun": True},
                                   "saveTo": str(dry), "save": "the whole result, as JSON",
                                   "then": "the first child level is previewed; reconcile failed or partial saves before any replay"})
            if dry.exists():
                errors = [i for i in load(dry, "dry run").get("issues", []) if i.get("severity") == "error"]
                if errors:
                    return emit(work, {"action": "stop", "why": "the dry run has errors", "errors": errors, "dryRun": str(dry),
                                       "how": f"nothing was written: show the person these errors; once their cause is fixed, "
                                              f"move {dry} out of the draw folder and run next to preview the level again"})
            return emit(work, {"action": "call", "tool": "manage_diagram", "arguments": args,
                               "saveTo": str(written), "save": "the whole result, as JSON",
                               "onError": "save the result at saveTo even when it failed, and run next: a failed write "
                                          "is set aside with the level read it was planned from (version_conflict or stub "
                                          "keys that are not there: the level is read afresh) and next says what to do"})
    if stale:
        return emit(work, {"action": "stale", "levels": stale,
                           "why": "these child levels were drawn from an earlier report; run next --redraw to replace "
                                  "what the skill drew on them with the current layout"})
    step = objects_next(work, reports, set(skip) | set(refused), facts)
    if step:
        return emit(work, step)
    # nothing is left but the levels passed with --skip and the refused ones: the run is finished
    skipped = skipped_levels(d, reports, skip, refused)
    drawn, left = drawn_levels(d)
    object_levels = sum(1 for x in d.glob("objects-*.json") if re.fullmatch(r"objects-[0-9a-f]{24}\.json", x.name)) \
        if d.exists() else 0
    # every child level and objects write is saved: the marker a calling run (map-process-from-data-model) waits for
    save(work.dir / "done.json", {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "levelsDrawn": len(drawn),
        "childLevels": drawn, "leftAsTheyWere": left, "boxes": len(reports),
        "boxesWithChildLevel": sum(1 for r in reports if has_child(r)),
        "boxesWithAutomations": sum(1 for r in reports if r["steps"]),
        "automationsPlaced": sum(len(r["steps"]) for r in reports), "objectLevels": object_levels,
        "skippedLevels": skipped, "report": str(work.dir / "report.md")})
    if skipped:
        return emit(work, {"action": "skipped", "levels": sorted(skip), "skippedLevels": skipped,
                           "doneFile": str(work.dir / "done.json"),
                           "how": "the run is finished apart from these levels, and done.json lists them: name each in the "
                                  "hand-off as not drawn or not updated, with its reason. Running next without --skip later "
                                  "draws the ones that were only open in the editor and rewrites done.json without them; "
                                  "the skill never draws over a level someone edited"})
    return emit(work, {"action": "done", "levels": len(drawn),
                       **({"leftAsTheyWere": left, "leftWhy": "these child levels already had boxes, so the skill left "
                                                              "them as they were: name them in the hand-off"} if left else {}),
                       "doneFile": str(work.dir / "done.json"),
                       "objectLevels": object_levels,
                       "overlaps": sorted({f"{x.name.split('-')[2]}: {i.get('message')}" for x in d.glob("objects-written-*.json")
                                           for i in load(x, "objects write").get("issues", []) if i.get("code") == "overlap"}),
                       "overlapsWhy": "boxes grow 24 px a resource; the server reports a box that now overlaps another. The skill "
                                      "moves nothing: tell the person, who can move the box in the editor",
                       "report": str(work.dir / "report.md")})


def cmd_layout(args):
    work = Work(args.work)
    reports = load(work.dir / "report.json", "report")["boxes"]
    for r in reports:
        if has_child(r):
            print(json.dumps({"box": r["box"]["boxText"], "changes": child_changes(r, work.reg)}, ensure_ascii=False))
    return 0


def cmd_check_facts(args):
    work = Work(args.work)
    _, _, _, autos = analyse(work)
    facts, problems = load_facts(work, autos)
    for node, p in problems.items():
        for line in p:
            print(f"ERROR {node}: {line}")
    print(f"{len(facts)} facts files pass, {len(problems)} have errors")
    return 1 if problems else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("boxes")
    b.add_argument("--model", required=True)
    b.add_argument("--inventory", required=True)
    b.add_argument("--reads", required=True)
    b.add_argument("--ref-model-id", required=True)
    b.add_argument("--team-id")
    b.add_argument("--scope", help="the run's scope.json: its metadata.basis (usage or configuration) decides the no-records flags")
    b.add_argument("--out", required=True)
    for name in ("next", "report", "layout", "check-facts"):
        sp = sub.add_parser(name)
        sp.add_argument("work")
        if name == "next":
            sp.add_argument("--skip", action="append",
                            help="a level to leave for later, such as one someone is editing: a status level (with its "
                                 "child levels) or one child level (repeatable)")
            sp.add_argument("--redraw", action="store_true",
                            help="replace what the skill drew on child levels whose report has changed")
    args = p.parse_args(argv)
    try:
        return {"boxes": cmd_boxes, "next": cmd_next, "report": cmd_report, "layout": cmd_layout,
                "check-facts": cmd_check_facts}[args.cmd](args)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
