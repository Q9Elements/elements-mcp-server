#!/usr/bin/env python3
"""Write the brief each process-level-writer agent works from, for an agent package.

Usage:
  prepare_briefs.py top --inventory inventory.json --out briefs/top.json --outline-path levels/top.json [--title TEXT]
  prepare_briefs.py children --inventory inventory.json --outline levels/top.json --out-dir briefs/ [--levels-dir levels/]

top       one overview brief: one item per stage, with its purpose, its outcomes and the
          stage each leads to, the people who decide there, and the components it calls.
          A recovery stage gets no item, and the outcomes that lead to it no line: the run
          resumes where it stopped, so each stage's own level carries its recovery.
children  one detail brief per top-level box whose stage has a level of its own: the
          stage's instructions, its outcomes, the components it calls (every one to be
          placed on a step or explained in a gap), the labels of the lines into and
          out of the parent box, which the child level copies exactly, and, when the
          stage can fail into recovery, the recovery card to draw as its own loop.

The writer checks its outline with the plugin's scripts/check_outline.py, which reads
the brief's cover, outlineRules, budget and parent. A brief holds data only; how to
write a level from a package is in references/articulation-rules.md (rulesPath).
Exit 0 on success, 1 when the outline or inventory has a problem, 2 on a setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import sys
from pathlib import Path

import common
from common import SetupError

MAX_STEPS = 10  # boxes on one level (max_boxes_per_level in the plugin's data/style-process.csv)


def load_inventory(path):
    inv = common.load_json(path, "inventory")
    problems = common.shape_errors(inv)
    if problems:
        raise SetupError("the inventory does not match its schema; run inventory_package.py again:\n  " + "\n  ".join(problems[:10]))
    return inv


def describe(comp, prefixes):
    row = {"id": comp["id"], "kind": comp["kind"], "resource": common.display_name(comp, prefixes)}
    if comp.get("description"):
        row["description"] = comp["description"]
    return row


def rules(inv):
    """Outline rules for a package: an agent can be a step's performer; waits and retries loop on one box;
    top boxes carry the resources of their stage."""
    performers = [common.ASSISTANT] + [c["id"] for c in inv["components"] if c["kind"] == "agent"]
    return {"selfLoops": True, "performers": performers, "usesOnOverview": True, "warnStepWithoutUses": False}


def cmd_top(args):
    inv = load_inventory(args.inventory)
    prefixes = common.load_prefixes()
    comps = {c["id"]: c for c in inv["components"]}
    items, links = [], []
    for stage in inv["stages"]:
        if stage.get("recovery"):
            continue  # drawn inside each stage that can fail, as its 'Resolve the block' step
        item = {"id": stage["id"], "name": stage["name"], "source": stage["source"],
                "drillsDown": stage["drillDown"], "instructionCount": len(stage["instructions"])}
        for field in ("purpose", "terminal", "who", "finishedWhen", "humanMoments", "failure", "command"):
            if stage.get(field):
                item[field] = stage[field]
        if not stage["drillDown"] and stage["instructions"]:
            item["instructions"] = stage["instructions"]
        item["outcomes"] = [o for o in stage["outcomes"] if not o.get("recovery")]
        if len(item["outcomes"]) < len(stage["outcomes"]):
            item["failuresHandledInside"] = [o["condition"] for o in stage["outcomes"] if o.get("recovery")]
        item["calls"] = [common.display_name(comps[c], prefixes) for c in stage["uses"] if c in comps and not
                         any(i["id"] == c for i in stage.get("indirect", []))]
        items.append(item)
        for outcome in item["outcomes"]:
            links.append({"from": stage["id"], "to": outcome["to"], "label": outcome["condition"]})
    package = inv["package"]
    title = args.title or f"How {package['name']} runs"
    brief = {"level": "top", "mode": "overview", "source": "agent-package", "title": title[:80],
             "outlinePath": str(args.outline_path), "rulesPath": str(common.RULES), "parent": None,
             "package": package, "humanRoles": inv["humanRoles"], "items": items,
             "suggestedOrder": [i["id"] for i in items],
             "components": [describe(c, prefixes) for c in inv["components"]],
             "cover": {"items": [i["id"] for i in items], "links": links,
                       "mayUse": [c["id"] for c in inv["components"]]},
             "outlineRules": rules(inv),
             "budget": {"min": len(items), "max": max(MAX_STEPS, len(items))}}
    common.write_json(args.out, brief)
    inside = sum(1 for s in inv["stages"] if s.get("recovery"))
    print(f"Top-level brief: {len(items)} stage(s), {len(links)} outcome line(s)"
          f"{f'; {inside} recovery stage(s) left to the stage levels' if inside else ''}; written to {args.out}.")
    if len(items) > MAX_STEPS:
        print(f"WARN {len(items)} stages is more than the {MAX_STEPS} boxes a level reads well with; the drawing warns (R01)")
    return 0


def cmd_children(args):
    inv = load_inventory(args.inventory)
    prefixes = common.load_prefixes()
    comps = {c["id"]: c for c in inv["components"]}
    stages = {s["id"]: s for s in inv["stages"]}
    outline = common.load_json(args.outline, "outline")
    errors = common.process_levels.shape_errors(outline, common.OUTLINE_SCHEMA) or \
        common.process_levels.outline_errors(outline, rules(inv))
    if errors:
        for line in errors:
            print(f"ERROR {args.outline}: {line}")
        return 1
    levels_dir = Path(args.levels_dir) if args.levels_dir else Path(args.outline).parent
    roles_in_use = common.dedupe([r["name"] for s in outline["steps"] for r in s.get("roles", [])] + inv["humanRoles"])
    written, problems = [], []
    for step in outline["steps"]:
        sid = step.get("item")
        if not sid:
            continue
        stage = stages.get(sid)
        if stage is None:
            problems.append(f"step '{step['id']}' stands for stage '{sid}', which is not in the inventory")
            continue
        if not stage["drillDown"]:
            continue
        inputs, outputs = common.process_levels.outline_boundary(outline, step["id"])
        parent = {"level": outline["level"], "stepId": step["id"], "name": step["name"], "inputs": inputs, "outputs": outputs}
        uses = [c for c in stage["uses"] if c in comps]
        recovery = None
        failures = [o for o in stage["outcomes"] if o.get("recovery")]
        if failures:
            rec = stages[failures[0]["to"]]
            recovery = {"stage": {k: rec[k] for k in ("id", "name", "source", "purpose", "instructions", "outcomes",
                                                      "humanMoments", "failure") if rec.get(k)},
                        "failures": [o["condition"] for o in failures],
                        "owners": inv["humanRoles"],
                        "components": [describe(comps[c], prefixes) for c in rec["uses"] if c in comps]}
        brief = {"level": sid, "mode": "detail", "source": "agent-package", "outlinePath": str(levels_dir / f"{sid}.json"),
                 "rulesPath": str(common.RULES), "parent": parent, "package": inv["package"],
                 "stage": {k: stage[k] for k in ("id", "name", "source", "purpose", "instructions", "outcomes",
                                                 "humanMoments", "failure", "who", "finishedWhen") if stage.get(k)},
                 "components": [describe(comps[c], prefixes) for c in uses],
                 "indirect": stage.get("indirect", []),
                 **({"recovery": recovery} if recovery else {}),
                 "rolesInUse": roles_in_use,
                 "cover": {"uses": uses, "mayUse": [common.ASSISTANT] + ([c["id"] for c in recovery["components"]] if recovery else [])},
                 "outlineRules": rules(inv),
                 "budget": {"min": 1, "max": MAX_STEPS, "instructions": len(stage["instructions"])}}
        out = Path(args.out_dir) / f"{sid}.json"
        common.write_json(out, brief)
        written.append((sid, out))
    for line in problems:
        print(f"ERROR {line}")
    for sid, out in written:
        print(f"detail   {sid} -> {out}")
    print(f"{len(written)} brief(s) written, {len(problems)} problem(s).")
    return 1 if problems else 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Write the briefs for the process-level-writer agents (agent package).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("top")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--outline-path", type=Path, required=True, help="where the writer saves the top-level outline")
    p.add_argument("--title")
    p = sub.add_parser("children")
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--outline", type=Path, required=True, help="the written top level")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--levels-dir", type=Path, help="where child outlines go; the outline's folder when left out")
    args = parser.parse_args(argv)
    try:
        return {"top": cmd_top, "children": cmd_children}[args.command](args)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
