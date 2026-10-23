"""Paths, constants, errors, data-file reading and small text helpers every layout script uses.

Part of the shared layout engine (see __init__.py). Standard library only; Python 3.8 or later.
"""

import csv
import hashlib
import json
import re
from pathlib import Path
from mcp_result import hydrate, map_name


PLUGIN = Path(__file__).resolve().parents[2]


STYLE_PATH = PLUGIN / "data" / "style-process.csv"


STYLE_FILES = {"interaction-flow": PLUGIN / "data" / "style-interaction.csv"}  # every other type: STYLE_PATH


RUBRIC_PATH = PLUGIN / "data" / "readability-rubric.csv"


TYPES_PATH = PLUGIN / "data" / "diagram-types.csv"


START, END = "START", "END"


MAX_CHANGES = 100


NEW_NAMES_PER_CHANGE = 10      # manage_diagram adds at most 10 new library resources per change (too_large)


RESOURCE_TYPE = {"human": "Human", "system": "System", "ai-agent": "System"}


USES_TYPE = {"entities": "Object", "systems": "System"}


ATTACHMENT_KINDS = ("metadata", "story", "link", "note")


TOP = "top"


class SetupError(Exception):
    pass


class PlanError(Exception):
    pass


def read_csv(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
                    for row in csv.DictReader(handle) if any((v or "").strip() for v in row.values())]
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def load_style(diagram_type):
    """Settings for one diagram type from its style file, as numbers where they are numbers."""
    style = {}
    path = STYLE_FILES.get(diagram_type, STYLE_PATH)
    for row in read_csv(path):
        if diagram_type in row.get("applies_to", "").split("|"):
            value = row["value"]
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
            style[row["setting"]] = value
    needed = ["box_width", "box_height_base", "resource_row_height", "col_gap", "row_gap", "max_columns",
              "max_boxes_per_level", "max_decision_outcomes", "free_end_clearance", "free_end_length_vertical",
              "label_max_chars", "end_label_max_chars", "max_resources_shown", "canvas_blank_width",
              "canvas_blank_height", "canvas_margin_factor", "top_margin", "band_gap"]
    missing = [n for n in needed if n not in style]
    if missing:
        raise SetupError(f"{path.name}: no value for {', '.join(missing)} applying to {diagram_type}")
    if style.get("max_resources_on_box") is not None and style["max_resources_shown"] > style["max_resources_on_box"]:
        raise SetupError(f"{path.name}: max_resources_shown ({style['max_resources_shown']}) is over "
                         f"max_resources_on_box ({style['max_resources_on_box']}), Xavery's limit for any box")
    return style


def map_type(diagram_type):
    for row in read_csv(TYPES_PATH):
        if row.get("diagram_type") == diagram_type:
            return row["create_map_type"]
    raise SetupError(f"{TYPES_PATH.name}: no row for diagram type {diagram_type}")


def norm(text):
    return " ".join((text or "").split()).casefold()


def squash(text):
    """A read label compared without any spaces: the server wraps long labels with line breaks, which a read
    returns as spaces, even inside a word ("hands- on", "( inferred)")."""
    return "".join((text or "").split()).casefold()


def make_ref(prefix, ident):
    """A manage_diagram ref (1-40 characters) that is stable for a model id."""
    ref = f"{prefix}{ident}"
    if len(ref) <= 40:
        return ref
    digest = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}{ident[:30 - len(prefix)]}~{digest}"


def attachment_changes(act, ref, skip):
    changes = []
    for item in act.get("attachments", []):
        kind = item["type"]
        if kind in skip:
            continue
        change = {"op": "add", "kind": "attachment", "activity": ref, "type": kind}
        if kind == "metadata":
            change["apiName"] = item["apiName"]
            if item.get("refModelId"):
                change["refModelId"] = item["refModelId"]
            if item.get("metadataType"):
                change["metadataType"] = item["metadataType"]
            if item.get("text"):
                change["description"] = item["text"][:2000]
        elif kind == "story":
            change["storyId"] = item["storyId"]
        elif kind == "link":
            change.update(title=item["title"][:120], url=item["url"])
        else:
            change.update(title=item["title"][:120], text=item["text"])
        changes.append(change)
    if act.get("inferred") and "note" not in skip:
        evidence = "; ".join(act.get("evidence", [])) or "Worked out by the reader; the source does not state it."
        changes.append({"op": "add", "kind": "attachment", "activity": ref, "type": "note", "title": "Inferred", "text": evidence})
    return changes


def chunk(groups):
    batches, current = [], []
    for group in groups:
        if len(group) > MAX_CHANGES:
            if current:
                batches.append(current)
                current = []
            batches.extend(group[i:i + MAX_CHANGES] for i in range(0, len(group), MAX_CHANGES))
            continue
        if current and len(current) + len(group) > MAX_CHANGES:
            batches.append(current)
            current = []
        current = current + group
    if current:
        batches.append(current)
    return batches


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return hydrate(json.load(handle))


def cut(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def dedupe(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def plan_id(result):
    return hashlib.sha1(json.dumps(result, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def unwrap(result):
    """Saved get_diagram results may hold the tool's whole answer or just its data."""
    if isinstance(result, dict) and isinstance(result.get("diagram"), dict):
        merged = dict(result)
        merged.update(result["diagram"])
        return merged
    return result


def slug(text, used):
    base = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:50] or "entity"
    ident, n = base, 2
    while ident in used:
        ident = f"{base}-{n}"
        n += 1
    used.add(ident)
    return ident


def guard_workdir(workdir):
    if (workdir / "results").exists() and any((workdir / "results").rglob("*.json")):
        raise PlanError(f"{workdir} already holds saved writes from a run; plan into a new folder")
    if (workdir / "map.json").exists():
        raise PlanError(f"{workdir} already holds a map; plan into a new folder")


def writes_saved(workdir):
    """True once the run has written to the map: a real batch or library batch result is saved."""
    return any((workdir / sub).exists() and any((workdir / sub).rglob("*.json")) for sub in ("results", "library"))


def prepare_workdir(workdir, the_plan):
    """Check that a work folder can take this plan, and stamp the plan's preflight attempt.

    Planning again into the same folder is allowed until the run has written to the map, so a fix made after the
    preflight (to the model, the flags or the space) reuses the empty map the first plan created instead of leaving
    it behind. A folder that holds writes accepts only the same plan (a resume). A folder whose map belongs to a run
    of the other kind (a new map against an amendment) is refused, so a new plan never draws into an existing map.

    attempt: a plan written into a folder with no writes starts a new preflight attempt, so preflight results saved
    for an earlier attempt are asked for again; a fix made only in the space (identical plan, same planId) then gets
    a fresh check rather than the stale one. A resume keeps the attempt, so its passed preflight stands."""
    workdir.mkdir(parents=True, exist_ok=True)
    plan_path = workdir / "plan.json"
    old = read_json(plan_path) if plan_path.exists() else {}
    written = writes_saved(workdir)
    if written and old.get("planId") != the_plan["planId"]:
        raise PlanError(f"{workdir} already holds writes made from a different plan; plan into a new work folder")
    if (workdir / "map.json").exists() and old and ("map" in old) != ("map" in the_plan):
        raise PlanError(f"{workdir} holds a map from a run of the other kind (a new map against an amendment); "
                        "plan into a new work folder")
    if written:
        the_plan["attempt"] = old.get("attempt", 1)
    else:
        the_plan["attempt"] = old.get("attempt", 1) + 1 if old else 1
    return the_plan


def parse_skip(text):
    skip = {s.strip() for s in (text or "").split(",") if s.strip()}
    unknown = skip - set(ATTACHMENT_KINDS)
    if unknown:
        raise SetupError(f"--skip takes {', '.join(ATTACHMENT_KINDS)}; not {', '.join(sorted(unknown))}")
    return frozenset(skip)
