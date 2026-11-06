"""The shared core of every process reader that works one level at a time.

A reader (map-process-from-data-model, map-agent-as-process) writes a brief per
level; a process-level-writer agent turns each brief into a level outline
(schemas/level-outline.schema.json); the reader's build script turns the outlines
into one business-architecture model. What does not depend on the source lives here:

- outline_errors: the outline rules the schema cannot express;
- outline_boundary: the labels of the lines into and out of one box, which the
  level behind it copies onto its starts and ends;
- check_outline: one outline against its brief, driven by the brief's generic
  fields (cover, outlineRules, budget, parent), so scripts/check_outline.py serves
  every reader;
- LevelWalker: follows the outlines down from levels/top.json and writes the
  model's roles, activities, flows and gaps; a reader subclasses it for what its
  source adds (objects as entities, package components as resources).

Standard library only; Python 3.8 or later.
"""

from mcp_result import hydrate, require_complete

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
if str(PLUGIN / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN / "scripts"))

import validate  # noqa: E402  (the plugin's model validator)

SetupError = validate.SetupError
Findings = validate.Findings
read_csv = validate.read_csv
split_list = validate.split_list

OUTLINE_SCHEMA = PLUGIN / "schemas" / "level-outline.schema.json"
MODEL_SCHEMA = PLUGIN / "schemas" / "ba-model.schema.json"
START, END = "START", "END"  # the model ids of a level's free start and end in flows
NOTE_TITLE = "About this step"  # title of the note every reader puts on every box
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")  # the id pattern ba-model.schema.json accepts

# Outline rules a brief may set in outlineRules; these defaults are the strict ones.
DEFAULT_RULES = {
    "selfLoops": False,         # a line from a step to itself (a wait or a retry on the same box)
    "performers": [],           # ids in a step's uses that count as its performer, besides a human role
    "usesOnOverview": False,    # boxes that stand for an item may carry uses (shown as resources)
    "warnStepWithoutUses": True,  # warn on a detail step that uses nothing and is not inferred
}


# ---------------------------------------------------------------- files and text

def load_json(path, what="file"):
    try:
        return hydrate(validate.load_json_strict(path))
    except OSError as exc:
        raise SetupError(f"cannot read {what} {path}: {exc}")
    except ValueError as exc:
        raise SetupError(f"{what} {path} is not valid JSON: {exc}")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def shape_errors(document, schema_path):
    """Check a document against a JSON Schema file with the plugin's validator; return error lines."""
    schema = load_json(schema_path, "schema")
    validate.check_schema_keywords(schema, "#")
    findings = Findings()
    validate.check_shape(document, schema, "", schema, findings)
    return findings.errors


def norm(text):
    return " ".join((text or "").split()).casefold()


def slug(text, limit=40):
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return value[:limit].rstrip("-") or "x"


def model_id(*parts):
    """An id the business-architecture model accepts, built from parts and kept under 64 characters."""
    raw = ".".join(p for p in parts if p)
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.") or "x"
    if not clean[0].isalnum():
        clean = "x" + clean
    if len(clean) > 64:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        clean = clean[:55].rstrip("-.") + "-" + digest
    assert MODEL_ID.match(clean), clean
    return clean


def dedupe(labels):
    seen, kept = set(), []
    for label in labels:
        key = norm(label)
        if key not in seen:
            seen.add(key)
            kept.append(label)
    return kept


def first_sentence(text, limit=220):
    text = " ".join((text or "").split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def max_decision_outcomes():
    """Outcomes of one decision box before a level reads badly (max_decision_outcomes in data/style-process.csv)."""
    path = PLUGIN / "data" / "style-process.csv"
    if path.exists():
        for row in read_csv(path, ["setting", "value", "applies_to"]):
            if row["setting"] == "max_decision_outcomes" and "process" in split_list(row["applies_to"]):
                try:
                    return int(row["value"])
                except ValueError:
                    raise SetupError(f"{path.name}: max_decision_outcomes '{row['value']}' is not a whole number")
    return 3


def label_limits():
    """(longest line label, longest start or end label) from the plugin's data/style-process.csv.

    A label on a line into or out of a box with a child level becomes a start or end label on
    that child level, where the drawing has the shorter limit."""
    limits = {"label_max_chars": 100, "end_label_max_chars": 40}
    path = PLUGIN / "data" / "style-process.csv"
    if path.exists():
        for row in read_csv(path, ["setting", "value", "applies_to"]):
            if row["setting"] in limits and "process" in split_list(row["applies_to"]):
                try:
                    limits[row["setting"]] = int(row["value"])
                except ValueError:
                    raise SetupError(f"{path.name}: {row['setting']} '{row['value']}' is not a whole number")
    return limits["label_max_chars"], limits["end_label_max_chars"]


def rules_of(source=None):
    """The outline rules in force: DEFAULT_RULES, overridden by a brief's outlineRules or by a rules dict."""
    rules = dict(DEFAULT_RULES)
    if isinstance(source, dict):
        given = source.get("outlineRules", source)
        rules.update({k: v for k, v in given.items() if k in DEFAULT_RULES})
    return rules


# ---------------------------------------------------------------- outlines

def outline_boundary(outline, step_id):
    """Labels of the lines into and out of one step of an outline, in a fixed order.

    inputs: the level's starts into the step, then lines from other steps, in step order.
    outputs: lines to other steps, in order, then the level's ends from the step.
    Briefs hand these to the child level's writer; LevelWalker checks the child level
    against them, so both use this one function.
    """
    inputs, outputs = [], []
    for start in outline.get("starts", []):
        if start.get("to") == step_id:
            inputs.append(start["trigger"])
    for step in outline.get("steps", []):
        for line in step.get("next", []):
            if line.get("to") == step_id and step.get("id") != step_id:
                inputs.append(line["outcome"])
            if step.get("id") == step_id:
                outputs.append(line["outcome"])  # a line back into the same box is an output: the level behind it ends there
    for end in outline.get("ends", []):
        if end.get("from") == step_id:
            outputs.append(end["outcome"])
    return dedupe(inputs), dedupe(outputs)


def outline_errors(outline, rules=None):
    """Rules the outline schema cannot express. Returns error lines."""
    rules = rules_of(rules)
    performers = set(rules["performers"])
    errors = []
    steps = outline.get("steps", [])
    ids = [s.get("id") for s in steps]
    seen = set()
    for step_id in ids:
        if step_id in seen:
            errors.append(f"step id '{step_id}' is used twice")
        seen.add(step_id)
    names = defaultdict(list)
    for step in steps:
        names[norm(step.get("name"))].append(step.get("id"))
    for key, owners in names.items():
        if len(owners) > 1:
            errors.append(f"steps {', '.join(owners)} have the same box text; boxes on one level need different names")
    labels = defaultdict(list)  # label -> [(source, description)]
    for start in outline.get("starts", []):
        labels[norm(start.get("trigger"))].append((START, f"the start into '{start.get('to')}'"))
    for step in steps:
        human = any(role.get("kind", "human") == "human" for role in step.get("roles", []))
        if not human and not performers & set(step.get("uses", [])):
            if performers:
                errors.append(f"step '{step.get('id')}' has no performer; give it a person or team, or one of {', '.join(sorted(performers))} in its uses")
            else:
                errors.append(f"step '{step.get('id')}' has no person or team; put the human role first (a system or AI agent may follow)")
        for line in step.get("next", []):
            if line.get("to") not in seen:
                errors.append(f"step '{step.get('id')}' has a line to '{line.get('to')}', which is not a step on this level")
            elif line.get("to") == step.get("id") and not rules["selfLoops"]:
                errors.append(f"step '{step.get('id')}' has a line to itself; a box cannot loop to itself, so send the rework to the step that fixes it")
            labels[norm(line.get("outcome"))].append((step.get("id"), f"the line from '{step.get('id')}'"))
    for end in outline.get("ends", []):
        labels[norm(end.get("outcome"))].append((END, f"the end from '{end.get('from')}'"))
    for label, owners in labels.items():
        sources = {source for source, _ in owners}
        # Lines out of one step with one label are one outcome starting steps in parallel.
        parallel = len(sources) == 1 and next(iter(sources)) not in (START, END)
        # Several ends with one label: alternative paths that finish in the same state (each record type
        # of a split ends with the parent box's output).
        same_end = sources == {END}
        if len(owners) > 1 and not parallel and not same_end:
            errors.append(f"{' and '.join(d for _, d in owners)} carry the same label '{label}'; every line on a level needs its own outcome (lines out of one step may share one to start steps in parallel)")
    for start in outline.get("starts", []):
        if start.get("to") not in seen:
            errors.append(f"a start goes to '{start.get('to')}', which is not a step on this level")
    for end in outline.get("ends", []):
        if end.get("from") not in seen:
            errors.append(f"an end comes from '{end.get('from')}', which is not a step on this level")
    return errors


def outline_sets(outline):
    """Every lifecycle value an outline's lines set, as (set, label, where) in outline order:
    starts, then each step's lines, then ends."""
    found = []
    for start in outline.get("starts", []):
        if start.get("sets"):
            found.append((start["sets"], start["trigger"], f"the start into '{start['to']}'"))
    for step in outline.get("steps", []):
        for line in step.get("next", []):
            if line.get("sets"):
                found.append((line["sets"], line["outcome"], f"the line from '{step['id']}' to '{line['to']}'"))
    for end in outline.get("ends", []):
        if end.get("sets"):
            found.append((end["sets"], end["outcome"], f"the end from '{end['from']}'"))
    return found


def main_path_sets(outline):
    """The (object, value) pairs set along the main path: from the first start, the first-listed line out of
    each step, and the step's end when it has no line out; loops stop the walk."""
    by_id = {s["id"]: s for s in outline.get("steps", [])}
    starts = outline.get("starts", [])
    if not starts:
        return []
    path = [starts[0].get("sets")]
    current, seen = starts[0]["to"], set()
    while current in by_id and current not in seen:
        seen.add(current)
        nxt = [l for l in by_id[current].get("next", []) if l["to"] != current]
        if nxt:
            path.append(nxt[0].get("sets"))
            current = nxt[0]["to"]
        else:
            ends = [e for e in outline.get("ends", []) if e["from"] == current]
            if ends:
                path.append(ends[0].get("sets"))
            break
    return [(p["object"], p["value"]) for p in path if p]


def lifecycle_level_findings(outline, lifecycle, gapped=(), inherited=()):
    """Check a level built on one lifecycle (brief cover.lifecycle: object, name, field, fieldLabel, values,
    ordered, recordType). Returns (errors, warnings).

    Each value has exactly one step (its `value`), whose work puts the record in that value; the step's
    first line out, or its end, carries the outcome: it sets that value and names it. Other lines out of
    the step are conditions that lead elsewhere and set nothing. With an ordered lifecycle the main path
    meets the open values in their order. An outline taken over from org-to-process is not checked.
    inherited: the parent box's labels (normalised); an end that copies one need not name its value."""
    errors, warnings = [], []
    if outline.get("source") == "org-to-process":
        return errors, warnings
    obj, name = lifecycle["object"], lifecycle.get("name", lifecycle["object"])
    labels = {v["value"]: [v["value"]] + ([v["label"]] if v.get("label") else []) for v in lifecycle["values"]}
    steps_of = defaultdict(list)
    for step in outline.get("steps", []):
        value = step.get("value")
        if value is None:
            warnings.append(f"step '{step['id']}' stands for no {lifecycle.get('fieldLabel', lifecycle['field'])} value; on this level every box is the work that puts the {name} in one value")
            continue
        if value not in labels:
            errors.append(f"step '{step['id']}' stands for '{value}', which is not one of the values ({', '.join(labels)}); spell it as the brief does")
            continue
        steps_of[value].append(step)
        outs = [(l.get("sets"), l["outcome"], f"the line from '{step['id']}' to '{l['to']}'") for l in step.get("next", []) if l["to"] != step["id"]]
        outs += [(e.get("sets"), e["outcome"], f"the end from '{step['id']}'") for e in outline.get("ends", []) if e["from"] == step["id"]]
        if not outs:
            continue
        sets, label, where = outs[0]
        if not sets or sets.get("object") != obj or sets.get("value") != value:
            errors.append(f"step '{step['id']}': its first line out ({where}) carries its outcome, so it sets {obj} to '{value}' "
                          f"(\"sets\": {{\"object\": \"{obj}\", \"value\": \"{value}\"}})")
        elif norm(label) not in inherited and not any(norm(n) in norm(label) for n in labels[value]):
            warnings.append(f"{where}: the outcome '{label}' does not name '{value}'; write it as \"{name} {lifecycle.get('fieldLabel', lifecycle['field']).lower()} updated to '{value}'\"")
        for other_sets, _, other_where in outs[1:]:
            if other_sets and other_sets.get("value") != value:
                errors.append(f"{other_where} sets '{other_sets.get('value')}'; only the step standing for that value sets it, so label this line with the condition that leads there")
    for value in labels:
        if len(steps_of[value]) > 1:
            errors.append(f"'{value}' has {len(steps_of[value])} steps ({', '.join(s['id'] for s in steps_of[value])}); give each value exactly one")
        elif not steps_of[value]:
            line = f"'{value}' has no step; add the activity that puts the {name} in that value"
            (warnings if obj in gapped else errors).append(line + ("; a gap about the object explains it" if obj in gapped else ""))
    if lifecycle.get("ordered"):
        rank = {v["value"]: i for i, v in enumerate(lifecycle["values"]) if not v.get("closed") or v.get("won")}
        seq = [rank[v] for o, v in main_path_sets(outline) if o == obj and v in rank]
        if any(b < a for a, b in zip(seq, seq[1:])):
            warnings.append(f"the main path meets the {name} values out of the org's order ({', '.join(v for v in rank)}); "
                            "list each step's line to the next value first, or say in a gap why the business order differs")
    return errors, warnings


def check_outline(outline, brief):
    """Check one written outline against its brief. Returns (errors, warnings).

    Generic: what the brief's own fields ask for. cover.items: every id has exactly one box
    standing for it (overview levels). cover.links: {from, to, label} pairs of items the source
    connects; a missing line is a warning (to null: an end). cover.uses: every id is in some step's uses or in a gap
    (detail levels). cover.mayUse: further ids a step may use without a warning.
    """
    errors = shape_errors(outline, OUTLINE_SCHEMA)
    rules = rules_of(brief)
    if not errors:
        errors += outline_errors(outline, rules)
    if errors:
        return errors, []
    warnings = []
    cover = brief.get("cover", {})
    if outline["level"] != brief["level"]:
        errors.append(f"level is '{outline['level']}' but the brief is for '{brief['level']}'")
    steps = outline["steps"]
    budget = brief.get("budget", {})
    if budget.get("max") and len(steps) > budget["max"]:
        errors.append(f"{len(steps)} steps; at most {budget['max']} fit on one level")
    gapped = {g.get("about") for g in outline.get("gaps", [])}
    overview = brief["mode"] == "overview"
    if overview:
        expected = list(cover.get("items", []))
        named = [s.get("item") for s in steps]
        for item in expected:
            if named.count(item) != 1:
                errors.append(f"item '{item}' has {named.count(item)} boxes; give it exactly one")
        for step in steps:
            if step.get("item") not in expected:
                errors.append(f"step '{step['id']}' does not stand for one of the brief's items; give it the item id it stands for")
            if step.get("uses") and not rules["usesOnOverview"]:
                warnings.append(f"step '{step['id']}' lists uses; on this level they are left off the box")
    if overview and cover.get("links"):
        box = {s.get("item"): s for s in steps if s.get("item")}
        ends_from = {e["from"] for e in outline.get("ends", [])}
        for link in cover["links"]:
            src, dst = box.get(link.get("from")), box.get(link.get("to")) if link.get("to") else None
            if src is None or (link.get("to") and dst is None):
                continue
            if dst is None:
                found = src["id"] in ends_from
            else:
                found = any(l["to"] == dst["id"] for l in src.get("next", []))
            if not found:
                where = f"'{dst['id']}'" if dst else "an end"
                warnings.append(f"the source has a way from '{link['from']}' to {link.get('to') or 'the end'} ({link.get('label', '')[:60]}); "
                                f"no line from '{src['id']}' to {where}: draw it, or say in a gap why not")
    must = list(cover.get("uses", []))
    known = set(must) | set(cover.get("mayUse", [])) | set(rules["performers"])
    used = {u for s in steps for u in s.get("uses", [])}
    for uid in must:
        if uid not in used and uid not in gapped:
            errors.append(f"'{uid}' is used by no step; use it, or add a gap about it saying why not")
    if must or cover.get("mayUse"):
        for uid in sorted(used - known):
            warnings.append(f"'{uid}' is not in the brief's uses or mayUse; check the id")
    if not overview and rules["warnStepWithoutUses"]:
        for step in steps:
            if not step.get("uses") and not step.get("inferred"):
                warnings.append(f"step '{step['id']}' uses nothing; mark it inferred or give it what it works on")
    if cover.get("lifecycle"):
        inherited = {norm(l) for l in (brief.get("parent") or {}).get("inputs", []) + (brief.get("parent") or {}).get("outputs", [])}
        lc_errors, lc_warnings = lifecycle_level_findings(outline, cover["lifecycle"], gapped, inherited)
        errors += lc_errors
        warnings += lc_warnings
    parent = brief.get("parent")
    if parent:
        starts = {norm(s["trigger"]) for s in outline["starts"]}
        ends = {norm(e["outcome"]) for e in outline.get("ends", [])}
        for label in parent["inputs"]:
            if norm(label) not in starts:
                errors.append(f"no start carries the parent input '{label}'; copy it exactly")
        for label in parent["outputs"]:
            if norm(label) not in ends:
                errors.append(f"no end carries the parent output '{label}'; copy it exactly")
        inputs = {norm(l) for l in parent["inputs"]}
        outputs = {norm(l) for l in parent["outputs"]}
        for start in outline["starts"]:
            if norm(start["trigger"]) not in inputs:
                warnings.append(f"extra start '{start['trigger']}' is not a line into the parent box; it will be reported as a gap")
        for end in outline.get("ends", []):
            if norm(end["outcome"]) not in outputs:
                warnings.append(f"extra end '{end['outcome']}' is not a line out of the parent box; it will be reported as a gap")
    longest, longest_end = label_limits()
    if overview:
        labels = [s["trigger"] for s in outline["starts"]] + [l["outcome"] for s in steps for l in s.get("next", [])] \
            + [e["outcome"] for e in outline.get("ends", [])]
        inherited = {norm(l) for l in (parent or {}).get("inputs", []) + (parent or {}).get("outputs", [])}
        for label in labels:
            if len(label) > longest_end and norm(label) not in inherited:
                warnings.append(f"'{label}' is {len(label)} characters; lines on this level become start and end lines of the child levels, which have room for {longest_end}")
    else:
        for step in steps:
            for line in step.get("next", []):
                if len(line["outcome"]) > longest:
                    warnings.append(f"step '{step['id']}': outcome is {len(line['outcome'])} characters; keep it under {longest}")
    lines_in = {s["to"] for s in outline["starts"]} | {l["to"] for s in steps for l in s.get("next", []) if l["to"] != s["id"]}
    lines_out = {s["id"] for s in steps if any(l["to"] != s["id"] for l in s.get("next", []))} | {e["from"] for e in outline.get("ends", [])}
    max_outcomes = max_decision_outcomes()
    for step in steps:
        if step["id"] not in lines_in:
            errors.append(f"step '{step['id']}' has no line in")
        if step["id"] not in lines_out and not overview:
            errors.append(f"step '{step['id']}' has no line out")
        outcomes = {norm(l["outcome"]) for l in step.get("next", [])} | \
            {norm(e["outcome"]) for e in outline.get("ends", []) if e["from"] == step["id"]}
        if len(outcomes) > max_outcomes:
            warnings.append(f"step '{step['id']}' has {len(outcomes)} different outcomes; at most {max_outcomes} read as one decision, so split it into two steps")
        if len(step["name"].split()) > 6:
            warnings.append(f"step '{step['id']}': box text has {len(step['name'].split())} words; keep it to 6")
    return errors, warnings


# ---------------------------------------------------------------- the walk

class LevelWalker:
    """Turns level outlines into model roles, activities, flows and gaps, from levels/top.json down.

    Subclasses decide, through the hooks below, which boxes drill down (child_level), whether a
    level is an overview (overview), what a step adds to its activity (decorate), what a gap's
    'about' points at (gap_about) and what more to check on a level (check_level).
    """

    def __init__(self, levels_dir, rules=None):
        self.levels_dir = Path(levels_dir)
        self.rules = rules_of(rules)
        self.errors, self.warnings = [], []
        self.roles, self.role_by_name = [], {}
        self.activities, self.flows, self.gaps = [], [], []
        self.visited = set()

    def error(self, where, message):
        self.errors.append(f"ERROR {where}: {message}")

    def warn(self, where, message):
        self.warnings.append(f"WARN {where}: {message}")

    # ------------------------------------------------------------ hooks

    def overview(self, level):
        """True when the boxes of this level stand for items (the top level by default)."""
        return level == "top"

    def child_level(self, level, outline, step):
        """The level to walk into from this step, or None."""
        return None

    def decorate(self, level, step, activity, here, overview):
        """Add what the source gives a step: uses, extra roles, attachments. Called before the note."""

    def note_lines(self, level, step):
        """Lines after 'What happens' and 'Why' in the step's note."""
        return []

    def gap_about(self, about):
        """The model id a gap's 'about' names when it is not a step on its level, or None."""
        return None

    def check_level(self, level, outline, ids, overview):
        """Further checks on one level."""

    def sets_entity(self, obj):
        """The model id of the entity an outline's sets names, or None when this reader has no lifecycles."""
        return None

    def add_sets(self, flow, sets, here):
        if not sets:
            return
        entity = self.sets_entity(sets["object"])
        if entity is None:
            self.warn(here, f"sets '{sets['object']}', which has no lifecycle here; the status change is kept in the label only")
            return
        flow["sets"] = {"entity": entity, "value": sets["value"]}

    # ------------------------------------------------------------ outlines and roles

    def load_outline(self, level, where):
        path = self.levels_dir / f"{level}.json"
        if not path.exists():
            self.error(where, f"no level outline at {path}; write the level for this box")
            return None
        outline = load_json(path, "outline")
        problems = shape_errors(outline, OUTLINE_SCHEMA)
        if not problems:
            problems = outline_errors(outline, self.rules)
        for line in problems:
            self.error(path.name, line)
        if problems:
            return None
        if outline["level"] != level:
            self.error(path.name, f"says level '{outline['level']}' but is the outline for '{level}'")
        return outline

    def role_id(self, role, where):
        key = norm(role["name"])
        kind = role.get("kind", "human")
        if key in self.role_by_name:
            existing = self.role_by_name[key]
            if existing["kind"] != kind:
                self.warn(where, f"role '{role['name']}' is {kind} here but {existing['kind']} elsewhere; kept {existing['kind']}")
            return existing
        entry = {"id": model_id("role", slug(role["name"])), "name": role["name"].strip(), "kind": kind}
        taken = {r["id"] for r in self.roles}
        base, n = entry["id"], 2
        while entry["id"] in taken:
            entry["id"] = model_id(base, str(n))
            n += 1
        self.roles.append(entry)
        self.role_by_name[key] = entry
        return entry

    def assign(self, role, here):
        """A role assignment for an activity, with RASCI kept on human roles only."""
        entry = self.role_id(role, here)
        assignment = {"role": entry["id"]}
        if role.get("rasci"):
            if entry["kind"] == "human":
                assignment["rasci"] = role["rasci"]
            else:
                self.warn(here, f"RASCI dropped from '{role['name']}': it applies to human roles only")
        return assignment

    def note_text(self, level, step):
        lines = [f"What happens: {step['what'].strip()}", f"Why: {step['why'].strip()}"] + self.note_lines(level, step)
        text = "\n".join(lines)
        return text if len(text) <= 5000 else text[:4999] + "…"

    # ------------------------------------------------------------ the walk

    def walk(self, level, parent_activity=None, parent_outline=None, parent_step=None, where="top"):
        if level in self.visited:
            self.error(where, f"level '{level}' is reached twice; each item has one box")
            return
        self.visited.add(level)
        outline = self.load_outline(level, where)
        if outline is None:
            return
        overview = self.overview(level)
        self.outline = outline  # the level being walked, for hooks that look past the step (decorate)
        ids = {s["id"]: (s["id"] if level == "top" else model_id(level, s["id"])) for s in outline["steps"]}
        self.inherited = set()  # the parent box's labels, which a child level copies exactly
        if parent_outline is not None:
            self.check_boundary(level, outline, parent_outline, parent_step)
            self.inherited = {norm(l) for side in outline_boundary(parent_outline, parent_step) for l in side}

        for step in outline["steps"]:
            here = f"{level}.json step '{step['id']}'"
            activity = {"id": ids[step["id"]], "name": step["name"].strip(),
                        "description": f"{step['what'].strip()} {step['why'].strip()}"[:5000],
                        "roles": [self.assign(role, here) for role in step["roles"]]}
            if parent_activity:
                activity["parent"] = parent_activity
            if step.get("join") == "all":
                activity["join"] = "all"
            if step.get("inferred"):
                activity["inferred"] = True
            if step.get("evidence"):
                activity["evidence"] = step["evidence"]
            activity["attachments"] = [{"type": "link", "title": l["title"], "url": l["url"]} for l in step.get("links", [])]
            self.decorate(level, step, activity, here, overview)
            seen_urls, attachments = set(), []
            for att in activity["attachments"]:
                if att.get("type") == "link":
                    if att["url"] in seen_urls:
                        continue
                    seen_urls.add(att["url"])
                attachments.append(att)
            links = [a for a in attachments if a.get("type") == "link"]
            others = [a for a in attachments if a.get("type") != "link"]
            activity["attachments"] = links + [{"type": "note", "title": NOTE_TITLE, "text": self.note_text(level, step)}] + others
            if not activity["roles"]:
                del activity["roles"]
            self.activities.append(activity)

        for start in outline["starts"]:
            flow = {"from": START, "to": ids[start["to"]], "label": start["trigger"].strip()}
            self.add_sets(flow, start.get("sets"), f"{level}.json start into '{start['to']}'")
            self.flows.append(flow)
        for step in outline["steps"]:
            for line in step.get("next", []):
                flow = {"from": ids[step["id"]], "to": ids[line["to"]], "label": line["outcome"].strip()}
                if line.get("inferred"):
                    flow["inferred"] = True
                self.add_sets(flow, line.get("sets"), f"{level}.json step '{step['id']}'")
                self.flows.append(flow)
        for end in outline.get("ends", []):
            flow = {"from": ids[end["from"]], "to": END, "label": end["outcome"].strip()}
            self.add_sets(flow, end.get("sets"), f"{level}.json end from '{end['from']}'")
            self.flows.append(flow)

        for gap in outline.get("gaps", []):
            entry = {"note": gap["note"]}
            about = gap.get("about")
            if about in ids:
                entry["about"] = ids[about]
            elif about and self.gap_about(about):
                entry["about"] = self.gap_about(about)
            elif about:
                entry["note"] = f"{about}: {gap['note']}"
            self.gaps.append(entry)

        self.check_level(level, outline, ids, overview)
        for step in outline["steps"]:
            child = self.child_level(level, outline, step)
            if child:
                self.walk(child, ids[step["id"]], outline, step["id"], f"{level}.json step '{step['id']}'")

    def check_boundary(self, level, outline, parent_outline, parent_step):
        inputs, outputs = outline_boundary(parent_outline, parent_step)
        where = f"{level}.json"
        starts = [s["trigger"] for s in outline["starts"]]
        ends = [e["outcome"] for e in outline.get("ends", [])]
        for label in inputs:
            if norm(label) not in {norm(s) for s in starts}:
                self.error(where, f"no start carries the parent box's input '{label}'; copy it exactly onto the start of the step it triggers")
        for label in outputs:
            if norm(label) not in {norm(e) for e in ends}:
                self.error(where, f"no end carries the parent box's output '{label}'; copy it exactly onto the end of the step that produces it")
        for label in starts:
            if norm(label) not in {norm(i) for i in inputs}:
                self.warn(where, f"starts with '{label}', which is not a line into the parent box; the drill-down will not match its box")
                self.gaps.append({"note": f"Level for '{level}' also starts from '{label}', which comes from outside this map; add that input to its box or link the process it comes from."})
        for label in ends:
            if norm(label) not in {norm(o) for o in outputs}:
                self.warn(where, f"ends with '{label}', which is not a line out of the parent box; the drill-down will not match its box")
                self.gaps.append({"note": f"Level for '{level}' also ends with '{label}', which its box does not show; add that output to the box or the process it hands over to."})

    def check_model_shape(self, model):
        schema = load_json(MODEL_SCHEMA, "schema")
        findings = Findings()
        validate.check_shape(model, schema, "", schema, findings)
        return findings.errors


# ---------------------------------------------------------------- run status

def read_or_none(path):
    """A JSON file, or None when it is missing or not JSON (a status script reads presence, not errors)."""
    try:
        return hydrate(validate.load_json_strict(path))
    except (OSError, ValueError):
        return None


def record_stage(work, done):
    """Write the last finished stage into scope.json, keeping every other field."""
    if not done:
        return None
    path = Path(work) / "scope.json"
    scope = read_or_none(path)
    if not isinstance(scope, dict):
        return None
    stage = done[-1]
    if scope.get("stage") != stage:
        scope["stage"] = stage
        path.write_text(json.dumps(scope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stage


def status_main(status, description, argv=None):
    """The command line every reader's status.py shares: status(work) returns
    {"done": [...], "missing": [...], "do": text, optional "validation", "coverageErrors",
    "doneNotes" ({stage: text}, printed after its DONE line) and "notApplicable" ([[stage, reason]])}."""
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("workdir")
    parser.add_argument("--json", action="store_true", help="print the answer as JSON")
    args = parser.parse_args(argv)
    if not Path(args.workdir).is_dir():
        print(f"SETUP {args.workdir} is not a folder", file=sys.stderr)
        return 2
    out = status(args.workdir)
    record_stage(args.workdir, out["done"])
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    notes = out.get("doneNotes") or {}
    for stage in out["done"]:
        print(f"DONE {stage}" + (f" ({notes[stage]})" if notes.get(stage) else ""))
    for stage, reason in out.get("notApplicable") or []:
        print(f"NOT APPLICABLE {stage} ({reason})")
    for item in out["missing"]:
        print(f"MISSING {item}")
    if "validation" in out:
        print(f"MODEL {out['validation']} Coverage errors: {out['coverageErrors']}.")
    print(f"NEXT {out['do']}")
    return 0
