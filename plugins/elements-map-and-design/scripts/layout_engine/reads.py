"""The whole-read rule: a saved review read is the whole get_diagram answer, never trimmed or summarised.

The layout check, the diagram-reviewer and the skills that work on a drawn map after it (show-status-automations
matches its boxes through diagram.boundary) all read these files. A read saved with boxes and lines only checks
nothing about roles, RASCI or attachments and matches nothing later, without any error, so a read that is not
whole is refused: next asks for it again and check writes no layout-check.json until every read is whole.

Part of the shared layout engine (see __init__.py). Standard library only; Python 3.8 or later.
"""

import json
from pathlib import Path

from .base import PlanError, TOP, read_json


REVIEW_INCLUDE = ["layout", "attachments"]                    # what the review reads ask get_diagram for
ANSWER_FIELDS = ("diagramId", "diagramUrl", "version", "levelNumber")   # at the top of every whole answer
LAYOUT_FIELDS = ("x", "y", "w", "h")                           # on every box when include has layout


class TrimmedReads(PlanError):
    """Saved reads that are not the whole get_diagram answer, one line per file in .lines.

    str() joins the lines with a new line and "ERROR ", so a command that prints f"ERROR {exc}" prints one
    ERROR line per file."""

    def __init__(self, lines):
        self.lines = list(lines)
        super().__init__("\nERROR ".join(self.lines))


def refuse(workdir, lines):
    """Raise TrimmedReads for these lines. A layout-check.json an earlier check wrote is moved aside to
    layout-check.stale.json first, because other skills take layout-check.json as the sign the drawing is checked."""
    stale = Path(workdir) / "layout-check.json"
    if stale.exists():
        try:
            stale.replace(stale.with_name("layout-check.stale.json"))
        except OSError:
            pass
    raise TrimmedReads(lines)


def expected_content(level, skip=()):
    """What a whole read of a planned level must show at least: whether the plan drew any box, gave any box
    resources and gave any box attachments (metadata the preflight found unlinkable, skip, is not written, so it
    does not count).

    Lower bounds only: a whole read of a level whose plan placed resources shows resources on at least one box.
    Box and line counts are left to the layout check, which reports a drawing that differs from its plan."""
    boxes = resources = attachments = False
    for batch in level.get("batches", []):
        for change in batch.get("changes", []):
            if change.get("op") != "add":
                continue
            if change.get("kind") == "activity":
                boxes = True
            elif change.get("kind") == "resource":
                resources = True
            elif change.get("kind") == "attachment" and not (
                    change.get("type") == "metadata" and (change.get("apiName"), change.get("metadataType")) in skip):
                attachments = True
    return {"boxes": boxes, "resources": resources, "attachments": attachments}


def read_problems(read, child, include=REVIEW_INCLUDE, expected=None, diagram_id=None):
    """What keeps a saved read from being the whole get_diagram answer, as short phrases; [] when it is whole.

    child: the level drills down from a box, so its read names that box under diagram.boundary.activity, with
    the box's lines in and out as boundary.inputs and boundary.outputs (the top level's boundary is null).
    expected: expected_content() of the level's plan, or None."""
    if not isinstance(read, dict):
        return ["it is not a get_diagram answer (not a JSON object)"]
    problems = []
    if read.get("_truncated"):
        problems.append("it is a trimmed answer (_truncated)")
    if isinstance(read.get("file"), dict) or (isinstance(read.get("_oversize"), dict) and read["_oversize"].get("refusedInline")):
        problems.append("it holds a file link (file.url) in place of the answer: download the file at once (the link "
                        "lasts two minutes) and save what it holds")
    missing = [field for field in ANSWER_FIELDS if field not in read]
    if missing:
        problems.append("no " + ", ".join(missing))
    diagram = read.get("diagram")
    if not isinstance(diagram, dict):
        problems.append("no diagram (the boxes and lines)")
        return problems
    for key in ("activities", "lines"):
        if not isinstance(diagram.get(key), list):
            problems.append(f"no diagram.{key}")
    boundary = diagram.get("boundary")
    if child:
        if not (isinstance(boundary, dict) and "activity" in boundary
                and (boundary["activity"] is None or (isinstance(boundary["activity"], dict) and "text" in boundary["activity"]))):
            problems.append("no diagram.boundary with the parent activity this level drills down from")
        elif not all(isinstance(boundary.get(key), list) for key in ("inputs", "outputs")):
            problems.append("no diagram.boundary inputs and outputs (the parent activity's lines in and out)")
    elif "boundary" not in diagram:
        problems.append("no diagram.boundary (null on the top level)")
    acts = [a for a in diagram.get("activities") or [] if isinstance(a, dict)] if isinstance(diagram.get("activities"), list) else []
    lines = diagram.get("lines") if isinstance(diagram.get("lines"), list) else []
    bare = sum(1 for a in acts if "key" not in a or "text" not in a)
    if bare:
        problems.append(f"{bare} of {len(acts)} boxes without key or text")
    bare = sum(1 for ln in lines if not isinstance(ln, dict) or not all(k in ln for k in ("key", "from", "to")))
    if bare:
        problems.append(f"{bare} of {len(lines)} lines without key, from or to")
    if "layout" in include:
        bare = sum(1 for a in acts if not all(k in a for k in LAYOUT_FIELDS))
        if bare:
            problems.append(f"{bare} of {len(acts)} boxes without x, y, w, h (include layout)")
        if not isinstance(diagram.get("canvas"), dict):
            problems.append("no diagram.canvas (include layout)")
    if diagram_id and read.get("diagramId") and read["diagramId"] != diagram_id:
        problems.append(f"it is the read of diagram {read['diagramId']}, not of this level ({diagram_id})")
    if expected and not acts:
        if expected.get("boxes") and isinstance(diagram.get("activities"), list):
            problems.append("no boxes, though the plan drew some")
    elif expected:
        if expected.get("resources") and not any(a.get("resources") for a in acts):
            problems.append("no resources on any box, though the plan gave boxes roles, systems or objects")
        if expected.get("attachments") and "attachments" in include and not any(a.get("attachments") for a in acts):
            problems.append("no attachments on any box, though the plan attached metadata, stories, links or notes (include attachments)")
    return problems


def saved_read_problems(path, child, include=REVIEW_INCLUDE, expected=None, diagram_id=None):
    """read_problems() of a saved file; a file that is not JSON is one problem."""
    try:
        read = read_json(path)
    except (OSError, ValueError) as exc:
        return [f"it cannot be read as JSON ({exc})"]
    return read_problems(read, child, include, expected, diagram_id)


def reread(path, diagram_id=None, include=REVIEW_INCLUDE, problems=None):
    """The ERROR line (without the ERROR word) for a review read that is missing or not whole."""
    call = f"get_diagram ({'diagramId ' + diagram_id + ', ' if diagram_id else ''}include {json.dumps(include)}, delivery file)"
    if problems is None:
        return f"{path} is missing: read the level whole with {call} and save the whole result"
    return f"{path} is not the whole get_diagram answer ({'; '.join(problems)}): re-read it whole with {call} and save the whole result"


def review_refusals(workdir, the_plan=None, diagram_ids=None, skip=(), include=REVIEW_INCLUDE):
    """One line per review read in DIR/review/ that is missing or not whole; [] when every one is whole.

    With a plan whose levels have slugs, every level needs its read, checked against what its plan placed;
    without one, the files in DIR/review/ are checked as they are (a file not named top.json is a child level)."""
    workdir = Path(workdir)
    diagram_ids = diagram_ids or {}
    lines = []
    levels = [lv for lv in (the_plan or {}).get("levels", []) if isinstance(lv, dict) and lv.get("slug")]
    if levels:
        for level in levels:
            slug = level["slug"]
            path = workdir / "review" / f"{slug}.json"
            if not path.exists():
                lines.append(reread(path, diagram_ids.get(slug), include))
                continue
            problems = saved_read_problems(path, slug != TOP, include, expected_content(level, skip), diagram_ids.get(slug))
            if problems:
                lines.append(reread(path, diagram_ids.get(slug), include, problems))
        return lines
    for path in sorted((workdir / "review").glob("*.json")):
        problems = saved_read_problems(path, path.stem != TOP, include)
        if problems:
            lines.append(reread(path, None, include, problems))
    return lines
