#!/usr/bin/env python3
"""Join logic fragments (one per automation) and an optional chain into one interaction flow model, or check a fragment.

Usage:
  python3 build_interaction_model.py merge --fragments PATH [PATH ...] --out MODEL.json
                                       [--base CHAIN.json] [--links LINKS.json] [--title TITLE] [--author NAME]
  python3 build_interaction_model.py check-fragment FRAGMENT.json [--context CONTEXT.json]

A fragment is what scripts/flow_to_steps.py or the automation-logic-reader agent writes for one automation:
{"fragmentVersion": 1, "source": {...}, "automation": {...}, "steps": [...], "connectors": [...], "gaps": [...],
 "chainOutputs": [{"interaction": ID, "fromStep": STEP_ID}], "hints": {...}}. The file formats are in
skills/explain-automation/references/data-contracts.md.

merge           Adds each fragment's automation, steps, connectors and gaps to the base (the chain model that
                scripts/trace_chain.py assemble writes) or to a new model. An automation already in the base keeps
                its id, name and attributes (the chain card's facts from Elements); the fragment brings its summary
                and description, adds its attachments, and its attributes when the base has none.
                A step's callsApiName becomes 'calls' when the model has an automation with that API name. An
                interaction out of an automation gets its fromStep from the fragment's chainOutputs, or else from
                the fragment's hints and LINKS (which object or event the interaction is about).
check-fragment  Checks one fragment the way validate.py checks a model, plus: every step belongs to the
                fragment's automation, and every chainOutputs entry names a step of the fragment and (with
                --context, the chain context the reader was given) an interaction out of this automation.

Exit 0: written, or the fragment has no errors (warnings may remain). Exit 1: errors, listed. Exit 2: setup problem.
Standard library only; Python 3.8 or later.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402  (the plugin's model validator)

FRAGMENT_ONLY_STEP_KEYS = ("callsApiName",)
STEP_SUMMARY_CHARS = 160
ATTRIBUTE_CHARS = 60
SOURCE_KINDS = {"flow-xml": "document", "apex-source": "document", "omniscript-json": "document", "rule-xml": "document",
                "elements": "metadata", "metadata": "metadata", "user": "user", "document": "document"}


def load(path):
    return validate.load_json_strict(path)


def fragment_paths(items):
    paths = []
    for item in items:
        path = Path(item)
        if path.is_dir():
            paths.extend(sorted(p for p in path.glob("*.json")))
        else:
            paths.append(path)
    return paths


def norm(text):
    return " ".join((text or "").split()).casefold()


# ---------------------------------------------------------------- merge

def merge(fragments, base=None, links=None, title=None, author=None):
    model = json.loads(json.dumps(base)) if base else {"schemaVersion": "1.0", "meta": {"title": "", "sources": []}}
    for section in ("automations", "steps", "connectors", "interactions", "gaps"):
        model.setdefault(section, [])
    meta = model["meta"]
    automations = {a["id"]: a for a in model["automations"]}
    by_api = {norm(a.get("apiName")): a for a in model["automations"] if a.get("apiName")}
    outputs, hints_of = {}, {}
    notes = []
    for path, fragment in fragments:
        auto = fragment.get("automation") or {}
        aid = auto.get("id")
        if not aid:
            raise ValueError(f"{path}: the fragment has no automation id")
        target = automations.get(aid) or by_api.get(norm(auto.get("apiName")))
        if target is None:
            target = {k: v for k, v in auto.items()}
            model["automations"].append(target)
            automations[aid] = target
            if target.get("apiName"):
                by_api[norm(target["apiName"])] = target
        else:
            if target["id"] != aid:
                notes.append(f"{path.name}: automation '{aid}' is '{target['id']}' in the base; its steps are moved to it")
            for key in ("summary", "description"):
                if auto.get(key):
                    target[key] = auto[key]
            if auto.get("attributes") and not target.get("attributes"):
                target["attributes"] = auto["attributes"]
            for key in ("apiName", "type"):
                if auto.get(key) and not target.get(key):
                    target[key] = auto[key]
            have = {json.dumps(a, sort_keys=True) for a in target.get("attachments", [])}
            for attachment in auto.get("attachments", []):
                if json.dumps(attachment, sort_keys=True) not in have:
                    target.setdefault("attachments", []).append(attachment)
            if auto.get("inferred") and not target.get("inferred"):
                target["inferred"] = True
                target["evidence"] = target.get("evidence", []) + auto.get("evidence", [])
        owner = target["id"]
        for step in fragment.get("steps", []):
            step = dict(step)
            step["automation"] = owner
            model["steps"].append(step)
        model["connectors"].extend(fragment.get("connectors", []))
        model["gaps"].extend(fragment.get("gaps", []))
        for item in fragment.get("chainOutputs", []):
            outputs[item["interaction"]] = item["fromStep"]
        hints_of[owner] = fragment.get("hints", {})
        source = fragment.get("source", {})
        kind = SOURCE_KINDS.get(source.get("kind"), "document")
        ref = source.get("file") or source.get("ref") or auto.get("apiName") or owner
        if not any(s.get("ref") == ref for s in meta.get("sources", [])):
            meta.setdefault("sources", []).append({"kind": kind, "ref": ref[:500]})
    # calls: API names become automation ids.
    for step in model["steps"]:
        api = step.pop("callsApiName", None)
        if api and "calls" not in step and norm(api) in by_api and by_api[norm(api)]["id"] != step["automation"]:
            step["calls"] = by_api[norm(api)]["id"]
    # fromStep on interactions out of an automation with steps.
    steps_of = {}
    for step in model["steps"]:
        steps_of.setdefault(step["automation"], set()).add(step["id"])
    links = (links or {}).get("interactions", {})
    for item in model["interactions"]:
        ident, src = item.get("id"), item["from"]
        if src not in steps_of or "fromStep" in item:
            continue
        if ident in outputs and outputs[ident] in steps_of[src]:
            item["fromStep"] = outputs[ident]
            continue
        guess = step_from_hints(hints_of.get(src, {}), links.get(ident, {}), item, automations, model["steps"])
        if guess and guess in steps_of[src]:
            item["fromStep"] = guess
    if not meta.get("description") and len(model["automations"]) == 1 and model["automations"][0].get("summary"):
        meta["description"] = model["automations"][0]["summary"]
    if not meta.get("title"):
        meta["title"] = (title or (model["automations"][0]["name"] if len(model["automations"]) == 1 else "Automation chain"))[:80]
    elif title:
        meta["title"] = title[:80]
    if author:
        meta["author"] = author[:100]
    if not meta.get("sources"):
        meta["sources"] = [{"kind": "user", "ref": "conversation"}]
    for section in ("automations", "steps", "connectors", "interactions", "gaps"):
        if not model[section]:
            del model[section]
    return model, notes


def step_from_hints(hints, link, interaction, automations, steps):
    kind = link.get("kind") or interaction.get("kind")
    obj = norm(link.get("object"))
    if kind in ("writes", "triggers") and obj:
        for item in hints.get("writes", []):
            if norm(item.get("object")) == obj:
                return item["step"]
    if kind == "publishes" and obj:
        for item in hints.get("publishes", []):
            if norm(item.get("event")) == obj:
                return item["step"]
    if kind == "calls":
        callee = automations.get(link.get("calls") or interaction["to"], {})
        for step in steps:
            if step.get("calls") == callee.get("id") and step["automation"] == interaction["from"]:
                return step["id"]
        for item in hints.get("calls", []):
            if norm(item.get("apiName")) == norm(callee.get("apiName")):
                return item["step"]
    return None


# ---------------------------------------------------------------- check one fragment

def check_fragment(fragment, context=None):
    findings = validate.Findings()
    schema = validate.load_schema()
    sections = validate.content_sections(schema)
    types = validate.load_diagram_types(sections)
    rules = validate.load_validator_rules(types)
    auto = fragment.get("automation")
    if not isinstance(auto, dict) or "id" not in auto:
        findings.error("fragment", "has no automation with an id")
        return findings
    steps = []
    for step in fragment.get("steps", []):
        steps.append({k: v for k, v in step.items() if k not in FRAGMENT_ONLY_STEP_KEYS})
    model = {"schemaVersion": "1.0", "meta": {"title": (auto.get("name") or "Fragment")[:80] or "Fragment",
                                              "sources": [{"kind": "user", "ref": "fragment"}]},
             "automations": [auto], "steps": steps, "connectors": fragment.get("connectors", []), "gaps": fragment.get("gaps", [])}
    model = {k: v for k, v in model.items() if v != []}
    validate.check_shape(model, schema, "", schema, findings)
    if findings.errors:
        return findings
    validate.check_model_rules(model, sections, validate.load_patterns(), findings)
    for index, step in enumerate(fragment.get("steps", [])):
        if step.get("automation") != auto["id"]:
            findings.error(f"steps[{step.get('id', index)}].automation", f"is '{step.get('automation')}'; every step of this fragment belongs to '{auto['id']}'")
    ids = {s["id"] for s in steps}
    allowed = None
    if context:
        allowed = {i["id"] for i in context.get("outgoing", []) if "id" in i}
    for index, item in enumerate(fragment.get("chainOutputs", [])):
        where = f"chainOutputs[{index}]"
        if item.get("fromStep") not in ids:
            findings.error(f"{where}.fromStep", f"'{item.get('fromStep')}' is not a step of this fragment")
        if allowed is not None and item.get("interaction") not in allowed:
            findings.error(f"{where}.interaction", f"'{item.get('interaction')}' is not one of the interactions out of this automation in the context ({', '.join(sorted(allowed)) or 'none'})")
        # The step that does it, when Elements names it, is the one to name: not the Loop card that holds it.
        doers = next((set(i.get("elementsThatDoIt") or []) for i in (context or {}).get("outgoing", []) if i.get("id") == item.get("interaction")), set())
        named = next((s for s in steps if s["id"] == item.get("fromStep")), None)
        if doers and named and named.get("sourceRef") not in doers:
            matches = [s["id"] for s in steps if s.get("sourceRef") in doers]
            if matches:
                findings.warn(f"{where}.fromStep", f"'{named['id']}' is not the step Elements names for this line ({'; '.join(sorted(doers))}); "
                                                   f"name {' or '.join(matches)}, even inside a drill-down")
    if allowed:
        given = {i.get("interaction") for i in fragment.get("chainOutputs", [])}
        for ident in sorted(allowed - given):
            findings.warn("chainOutputs", f"interaction '{ident}' has no fromStep; the line out of this automation's level will leave its last step")
    if not findings.errors:
        validate.check_readability(model, "interaction-flow", types, rules, findings)
    # The reading method's limits (skills/explain-automation/references/logic-reading.md), tighter than the rubric's.
    for step in steps:
        if len(step.get("summary", "")) > STEP_SUMMARY_CHARS:
            findings.warn(f"steps[{step['id']}]", f"footer is {len(step['summary'])} characters; the method keeps a step's footer under {STEP_SUMMARY_CHARS}")
    for item in [auto] + steps:
        for attribute in item.get("attributes", []):
            if len(attribute["title"]) > ATTRIBUTE_CHARS:
                findings.warn(f"{'automation' if item is auto else 'steps[' + item['id'] + ']'}", f"attribute {json.dumps(attribute['title'])} is over {ATTRIBUTE_CHARS} characters; shorten it and put the rest in its description")
    return findings


# ---------------------------------------------------------------- main

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Build an interaction flow model from logic fragments, or check a fragment.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_merge = sub.add_parser("merge")
    p_merge.add_argument("--fragments", nargs="+", required=True, help="fragment files or folders of them")
    p_merge.add_argument("--base", help="the chain model from trace_chain.py assemble")
    p_merge.add_argument("--links", help="links.json from trace_chain.py assemble")
    p_merge.add_argument("--title")
    p_merge.add_argument("--author")
    p_merge.add_argument("--out", required=True)
    p_check = sub.add_parser("check-fragment")
    p_check.add_argument("fragment")
    p_check.add_argument("--context", help="the chain context the reader was given")
    args = parser.parse_args(argv)
    try:
        if args.command == "merge":
            fragments = [(path, load(path)) for path in fragment_paths(args.fragments)]
            if not fragments:
                print("ERROR no fragment files found")
                return 1
            base = load(args.base) if args.base else None
            links = load(args.links) if args.links else None
            model, notes = merge(fragments, base, links, args.title, args.author)
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(model, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            for note in notes:
                print(f"NOTE {note}")
            print(f"Wrote {args.out}: {len(model.get('automations', []))} automation(s), {len(model.get('steps', []))} steps, "
                  f"{len(model.get('interactions', []))} interactions, {len(model.get('gaps', []))} gap(s). Next: validate.py {args.out} --for interaction-flow")
            return 0
        fragment = load(args.fragment)
        context = load(args.context) if args.context else None
        findings = check_fragment(fragment, context)
        for line in findings.errors + findings.warnings:
            print(line)
        print(f"{len(findings.errors)} error(s), {len(findings.warnings)} warning(s).")
        return 1 if findings.errors else 0
    except validate.SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
