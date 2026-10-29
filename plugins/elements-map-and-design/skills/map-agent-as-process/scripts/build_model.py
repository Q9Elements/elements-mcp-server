#!/usr/bin/env python3
"""Turn the level outlines of an agent package into one business-architecture model.

Usage:
  build_model.py --inventory inventory.json --levels-dir levels/ --out model.json
                 [--view business|technical] [--interaction-flow] [--coverage coverage.json] [--title TEXT]

The level walk is the plugin's scripts/process_levels.py (shared with
map-process-from-data-model): every outline is checked, child levels must start and
end with their parent box's labels, ids are made unique. This script adds what a
package gives:
  - each component a step uses becomes a resource on its box, named by
    data/resource-prefixes.csv ('AI Assistant', 'Agent: x', 'MCP tool: server/tool')
    and filtered by the view: business shows the people, the AI Assistant, agents,
    skills, commands and one 'MCP Server: X' per server; technical also shows MCP
    tools, scripts, data, templates and references (and no server);
  - a box that drills down also shows the resources of its level, as the business view
    shows them (the technical detail stays on the level);
  - the box note gives the stage's source file, its outcomes as the package states
    them, and every component it calls, whatever the view shows;
  - coverage: every stage has a box (a recovery stage has none: each stage that can fail
    carries it on its own level), every component the inventory lists for a stage
    is on that stage's box or level, and components no stage calls become gaps;
  - with --interaction-flow, the call graph as automations and interactions, for
    draw-interaction-flow.

Run scripts/validate.py MODEL --for process next.
Exit 0: model written, no errors. 1: errors (the model is written when its shape is
valid). 2: setup problem.

Standard library only; Python 3.8 or later.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import common
from common import SetupError, model_id

KIND_LABEL = {"assistant": "AI Assistant", "agent": "Agent", "skill": "Skill", "command": "Command", "mcp-server": "MCP server",
              "mcp-tool": "MCP tool", "script": "Script", "data": "Data table", "template": "Template", "reference": "Reference"}


class Builder(common.process_levels.LevelWalker):
    def __init__(self, inv, levels_dir, view):
        self.inv = inv
        self.prefixes = common.load_prefixes()
        self.comps = {c["id"]: c for c in inv["components"]}
        self.stages = {s["id"]: s for s in inv["stages"]}
        performers = [common.ASSISTANT] + [c["id"] for c in inv["components"] if c["kind"] == "agent"]
        super().__init__(levels_dir, {"selfLoops": True, "performers": performers, "usesOnOverview": True,
                                      "warnStepWithoutUses": False})
        self.view = view
        self.placed = {}        # stage id -> component ids on its box or level
        self.boxes = {}         # stage id -> top-level activity id
        self.unknown = set()
        self.gapped = set()     # component ids an outline explains in a gap

    # ------------------------------------------------------------ hooks

    def child_level(self, level, outline, step):
        sid = step.get("item")
        if level == "top" and sid in self.stages and self.stages[sid]["drillDown"]:
            return sid
        return None

    def child_uses(self, sid):
        path = self.levels_dir / f"{sid}.json"
        if not path.exists():
            return []
        try:
            outline = common.load_json(path, "outline")
        except SetupError:
            return []
        return [u for s in outline.get("steps", []) for u in s.get("uses", [])]

    def shown(self, ids, view=None):
        """Component ids as the view shows them, in data/resource-prefixes.csv order."""
        column = "business_view" if (view or self.view) == "business" else "technical_view"
        out = []
        for cid in ids:
            comp = self.comps.get(cid)
            if comp is None:
                continue
            if self.prefixes[comp["kind"]][column] == "yes":
                out.append(cid)
            elif comp["kind"] == "mcp-tool" and self.prefixes["mcp-server"][column] == "yes":
                out.append(f"server:{comp['server']}")
        out = [c for c in common.dedupe(out) if c in self.comps]
        return sorted(out, key=lambda c: (self.prefixes[self.comps[c]["kind"]]["order"], out.index(c)))

    def decorate(self, level, step, activity, here, overview):
        uses = list(step.get("uses", []))
        child = []
        sid = step.get("item") if level == "top" else level
        if level == "top":
            if sid not in self.stages:
                self.error(here, f"stands for stage '{sid}', which is not in the inventory" if sid else
                           "a box on the top level stands for a stage; give the step its stage id as item")
            else:
                self.boxes[sid] = activity["id"]
                if self.stages[sid]["drillDown"]:
                    child = self.child_uses(sid)
        uses = common.dedupe(uses + child)
        for cid in uses:
            if cid not in self.comps:
                self.unknown.add(cid)
                self.error(here, f"uses '{cid}', which is not a component in the inventory")
        if sid in self.stages:
            self.placed.setdefault(sid, set()).update(c for c in uses if c in self.comps)
        # A box that drills down shows its level's resources in the business view: the technical detail is on the level.
        for cid in common.dedupe(self.shown([u for u in uses if u not in child]) + self.shown(child, "business")):
            role = {"name": common.display_name(self.comps[cid], self.prefixes),
                    "kind": self.prefixes[self.comps[cid]["kind"]]["role_kind"]}
            activity["roles"].append(self.assign(role, here))
        seen, roles = set(), []
        for a in activity["roles"]:
            if a["role"] not in seen:
                seen.add(a["role"])
                roles.append(a)
        activity["roles"] = roles

    def note_lines(self, level, step):
        lines = []
        sid = step.get("item") if level == "top" else None
        stage = self.stages.get(sid) if sid else None
        if stage:
            lines.append(f"Defined in: {stage['source']}")
            if stage.get("outcomes"):
                lines.append("Outcomes in the package:")
                for o in stage["outcomes"]:
                    target = self.stages[o["to"]]["name"] if o.get("to") in self.stages else "end of the run"
                    lines.append(f"- {o.get('id', '') + ': ' if o.get('id') else ''}{o['condition']} → {target}")
        calls = [c for c in step.get("uses", []) if c in self.comps and c != common.ASSISTANT]
        if calls:
            lines.append("Calls:")
            for cid in calls:
                comp = self.comps[cid]
                desc = common.process_levels.first_sentence(comp.get("description", ""), 160)
                lines.append(f"- {KIND_LABEL[comp['kind']]} {comp['name']}" + (f": {desc}" if desc else ""))
        return lines

    def gap_about(self, about):
        self.gapped.add(about)
        return None  # component ids are not model items; the gap keeps the id in its note

    # ------------------------------------------------------------ coverage and model

    def coverage(self):
        rows = []
        for sid, stage in self.stages.items():
            if stage.get("recovery"):
                if sid in self.boxes:
                    rows.append(("warn", f"recovery stage '{stage['name']}' has a box on the top level; the stages that can fail carry it on their own levels"))
                continue
            if sid not in self.boxes:
                rows.append(("error", f"stage '{stage['name']}' ({sid}) has no box on the top level"))
                continue
            if stage["drillDown"] and sid not in self.visited:
                rows.append(("error", f"stage '{stage['name']}' has no level of its own; write levels/{sid}.json"))
            missing = [c for c in stage["uses"] if c not in self.placed.get(sid, set())]
            for cid in missing:
                if cid not in self.gapped:
                    rows.append(("warn", f"stage '{stage['name']}' calls {cid}, which is on none of its steps"))
        for item in self.inv["unused"]:
            if item.get("mentionedIn"):
                continue
            self.gaps.append({"note": f"{item['id']}: part of the package ({item['path']}) but no stage calls it and no other file mentions it; it may be dead."})
            rows.append(("warn", f"{item['id']} is never called"))
        if self.inv["unclassified"]:
            self.gaps.append({"note": "Files the reader could not place: " + ", ".join(self.inv["unclassified"][:20])})
        for gap in self.inv["gaps"]:
            self.gaps.append({"note": gap["note"]})
        return rows

    def interaction_flow(self):
        """The call graph: the package calls each component, stage by stage; a component calls what it reaches."""
        pkg_id = model_id("auto", "package")
        autos = [{"id": pkg_id, "name": self.inv["package"]["name"], "type": "other",
                  "summary": (self.inv["package"].get("description") or "The agent package")[:240],
                  "attributes": [{"title": f"Format: {self.inv['package']['format']}"}]}]
        column = "business_view" if self.view == "business" else "technical_view"
        ids = {}
        for comp in self.inv["components"]:
            if comp["kind"] in ("assistant", "mcp-server") or self.prefixes[comp["kind"]][column] != "yes" and comp["kind"] != "mcp-tool":
                continue
            if comp["kind"] == "mcp-tool" and self.view == "business":
                continue
            ids[comp["id"]] = model_id("auto", comp["id"].replace(":", "-").replace("/", "-"))
            autos.append({"id": ids[comp["id"]], "name": common.display_name(comp, self.prefixes), "type": "other",
                          **({"summary": comp["description"][:240]} if comp.get("description") else {}),
                          "attributes": [{"title": f"Kind: {KIND_LABEL[comp['kind']]}"},
                                         {"title": ("Stages: " + ", ".join(self.stages[s]["name"] for s in comp["usedBy"] if s in self.stages))[:200]}]})
        interactions, order = [{"from": "START", "to": pkg_id, "kind": "triggers", "order": 1, "label": "Package run"}], 2
        for stage in self.inv["stages"]:
            via = {i["id"]: i["via"] for i in stage.get("indirect", [])}
            for cid in stage["uses"]:
                if cid not in ids:
                    continue
                src = ids.get(via.get(cid), pkg_id)
                interactions.append({"from": src, "to": ids[cid], "kind": "calls", "order": order, "label": stage["name"][:60]})
                order += 1
        return autos, interactions

    def model(self, title, with_flow):
        package = self.inv["package"]
        model = {
            "schemaVersion": "1.0",
            "meta": {
                "title": title[:80],
                "description": (f"What the agent package {package['name']} ({package['format']}) does, read from its files by the "
                                f"map-agent-as-process skill on {date.today().isoformat()}; {self.view} view. Stages, their order "
                                "and the people who decide are as the package states them; have the package's owner confirm the wording."),
                "author": "map-agent-as-process",
                "sources": [{"kind": "document", "ref": package["path"][:500], "note": f"Agent package, format {package['format']}"}],
            },
            "roles": self.roles,
            "activities": self.activities,
            "flows": self.flows,
            "gaps": self.gaps,
        }
        if with_flow:
            model["automations"], model["interactions"] = self.interaction_flow()
        return {k: v for k, v in model.items() if v != []}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Build the business-architecture model of an agent package from its level outlines.")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--levels-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--view", choices=("business", "technical"), default="business")
    parser.add_argument("--interaction-flow", action="store_true", help="also write the call graph for draw-interaction-flow")
    parser.add_argument("--coverage", type=Path, help="where to write the coverage findings as JSON")
    parser.add_argument("--title", help="map name; the top outline's title, or 'How <package> runs', when left out")
    args = parser.parse_args(argv)
    try:
        inv = common.load_json(args.inventory, "inventory")
        problems = common.shape_errors(inv)
        if problems:
            raise SetupError("the inventory does not match its schema; run inventory_package.py again:\n  " + "\n  ".join(problems[:10]))
        builder = Builder(inv, args.levels_dir, args.view)
        builder.walk("top")
        findings = builder.coverage()
        top = builder.levels_dir / "top.json"
        title = args.title or (common.load_json(top, "outline").get("title") if top.exists() else None) or f"How {inv['package']['name']} runs"
        model = builder.model(title, args.interaction_flow)
        shape = builder.check_model_shape(model)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    for severity, message in findings:
        (builder.error if severity == "error" else builder.warn)("coverage", message)
    for line in shape:
        builder.errors.append(f"ERROR model shape {line}")
    if not shape:
        common.write_json(args.out, model)
    if args.coverage:
        common.write_json(args.coverage, {"errors": [l for l in builder.errors], "warnings": builder.warnings,
                                          "unused": [u for u in inv["unused"] if not u.get("mentionedIn")]})
    for line in builder.errors + builder.warnings:
        print(line)
    levels = len({a.get("parent") for a in builder.activities})
    verdict = "FAIL" if builder.errors else "PASS"
    written = f" Written to {args.out}." if not shape else " Not written: the model's shape is invalid."
    print(f"{verdict}: {len(builder.errors)} error(s), {len(builder.warnings)} warning(s). {len(builder.activities)} step(s) on "
          f"{levels} level(s), {len(builder.flows)} line(s), {len(builder.roles)} resource(s), {args.view} view.{written}")
    return 1 if builder.errors else 0


if __name__ == "__main__":
    sys.exit(main())
