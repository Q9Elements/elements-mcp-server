"""Helpers shared by the design-from-process-map scripts.

Standard library only (Python 3.8 or later), except build_solution_overview.py,
which needs python-docx, and render_diagram.py, which pictures diagrams with
LibreOffice or else Pillow when either is installed (probe reports both). Shape checks reuse the plugin's validator
(scripts/validate.py) so every file is checked against its JSON Schema the
same way as the shared model.

    python3 common.py probe     # report the tools a run needs
"""

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from mcp_result import hydrate, native_errors, owner_api, require_complete

import validate  # noqa: E402  (the plugin's model validator)

SetupError = validate.SetupError
Findings = validate.Findings
load_json_strict = validate.load_json_strict

SCHEMAS = SKILL / "schemas"
DATA = SKILL / "data"
RUBRIC_CSV = DATA / "derivability-rubric.csv"
CRUD_CSV = DATA / "crud-verbs.csv"
EVIDENCE_TYPES_CSV = DATA / "integration-evidence-types.csv"
SECTIONS_CSV = DATA / "solution-overview-sections.csv"

START, END = "START", "END"
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


# ---------------------------------------------------------------- files

def load_json(path, what="file"):
    try:
        return hydrate(load_json_strict(path))
    except OSError as exc:
        raise SetupError(f"cannot read {what} {path}: {exc}")
    except ValueError as exc:
        raise SetupError(f"{what} {path} is not valid JSON: {exc}")


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_ndjson(paths):
    rows = []
    for path in paths:
        try:
            with open(path, encoding="utf-8-sig") as handle:
                for number, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except ValueError as exc:
                        raise SetupError(f"{path} line {number} is not JSON: {exc}")
        except OSError as exc:
            raise SetupError(f"cannot read {path}: {exc}")
    return rows


def read_csv(path, columns):
    """Rows of a data file as dicts; the header must hold every named column."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            if missing:
                raise SetupError(f"{Path(path).name} lacks column(s) {', '.join(missing)}")
            return [{k: (v or "").strip() for k, v in row.items()} for row in reader]
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_schema(name):
    schema = load_json(SCHEMAS / name, "schema")
    validate.check_schema_keywords(schema, "#")
    return schema


def shape_errors(document, schema_name):
    """Check a document against one of this skill's schemas; return error lines."""
    schema = load_schema(schema_name)
    findings = Findings()
    validate.check_shape(document, schema, "", schema, findings)
    return findings.errors


# ---------------------------------------------------------------- text and ids

def norm(text):
    return " ".join((text or "").split()).casefold()


def slug(text, limit=40):
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return value[:limit].rstrip("-") or "x"


def model_id(*parts):
    """An id the business-architecture model accepts, built from parts and kept under 64 characters."""
    raw = "-".join(str(p) for p in parts if p not in (None, ""))
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.") or "x"
    if not clean[0].isalnum():
        clean = "x" + clean
    if len(clean) > 64:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        clean = clean[:55].rstrip("-.") + "-" + digest
    assert MODEL_ID.match(clean), clean
    return clean


def first_word(text):
    match = re.match(r"\W*\(?([A-Za-z]+)", text or "")
    return match.group(1).casefold() if match else ""


# ---------------------------------------------------------------- data files

def load_rubric(path=RUBRIC_CSV):
    rows = read_csv(path, ["rule_id", "checked_by", "applies_to", "weight", "threshold", "rule"])
    rules, pass_mark = [], None
    for row in rows:
        if row["checked_by"] == "score":
            try:
                pass_mark = float(row["threshold"])
            except ValueError:
                raise SetupError(f"{Path(path).name}: the pass mark row needs a number in threshold")
            continue
        if row["checked_by"] not in ("script", "agent"):
            raise SetupError(f"{Path(path).name}: checked_by must be script, agent or score, not '{row['checked_by']}'")
        if row["applies_to"] not in ("activity", "line", "level"):
            raise SetupError(f"{Path(path).name}: applies_to must be activity, line or level, not '{row['applies_to']}'")
        try:
            row["weight"] = float(row["weight"])
        except ValueError:
            raise SetupError(f"{Path(path).name}: rule {row['rule_id']} needs a number in weight")
        rules.append(row)
    if pass_mark is None:
        raise SetupError(f"{Path(path).name} has no pass mark row (checked_by score)")
    return rules, pass_mark


def load_crud_verbs(path=CRUD_CSV):
    rows = read_csv(path, ["verb", "crud", "notes"])
    verbs = {}
    for row in rows:
        if not re.fullmatch(r"C?R?U?D?", row["crud"]) or not row["crud"]:
            raise SetupError(f"{Path(path).name}: '{row['verb']}' has crud '{row['crud']}'; use letters C, R, U, D in that order")
        verbs[row["verb"].casefold()] = row["crud"]
    return verbs


# ---------------------------------------------------------------- engagement

def eng_path(eng, *parts):
    return Path(eng).joinpath(*parts)


def level_files(eng):
    """The saved level reads, by level number, as read_process_map.py expects them."""
    outline = load_json(eng_path(eng, "levels", "outline.json"), "the map outline")
    items = outline.get("items")
    if not isinstance(items, list) or not items:
        raise SetupError("levels/outline.json holds no levels (save the whole get_process_map_outline answer)")
    if outline.get("status") not in (None, "complete"):
        raise SetupError("levels/outline.json is from a map still being copied; read the outline again")
    return outline, items


# ---------------------------------------------------------------- process areas

def process_areas(model, integrations_section=None, inventory=None):
    """One entry per top-level step of the model, in the map's order: the steps under it, the entities those steps use
    and the relationships between them, the integrations serving those steps (by the integrations section's steps)
    with the systems they join, and the step's own drill-down level from inventory.json when there is one."""
    children = {}
    for a in model["activities"]:
        children.setdefault(a.get("parent"), []).append(a["id"])

    def walk(aid):
        out = [aid]
        for c in children.get(aid, []):
            out += walk(c)
        return out

    acts = {a["id"]: a for a in model["activities"]}
    entity_ids = {e["id"] for e in model.get("entities", [])}
    served = {i["id"]: set(i.get("steps", [])) for i in (integrations_section or {}).get("integrations", [])}
    levels = {lv.get("parent"): lv for lv in (inventory or {}).get("levels", []) if lv.get("parent")}
    areas = []
    for aid in children.get(None, []):
        steps = walk(aid)
        used = []
        for s in steps:
            for ref in acts[s].get("uses", []):
                if ref in entity_ids and ref not in used:
                    used.append(ref)
        keep = set(used)
        rels = [r for r in model.get("relationships", []) if r["from"] in keep and r["to"] in keep]
        ints = [i for i in model.get("integrations", []) if served.get(i["id"], set()) & set(steps)]
        systems = []
        for i in ints:
            for end in (i["from"], i["to"]):
                if end not in systems:
                    systems.append(end)
        areas.append({"activity": aid, "name": acts[aid]["name"], "steps": steps, "entities": used, "relationships": rels,
                      "integrations": [i["id"] for i in ints], "systems": systems, "level": levels.get(aid)})
    return areas


# ---------------------------------------------------------------- probe

def probe():
    lines, ok = [], True
    lines.append(f"python {sys.version.split()[0]}" + ("" if sys.version_info >= (3, 8) else "  NEEDS 3.8 or later"))
    ok = ok and sys.version_info >= (3, 8)
    curl = shutil.which("curl")
    lines.append(f"curl {'found' if curl else 'MISSING: install curl to download Elements result parts'}")
    ok = ok and bool(curl)
    try:
        import docx  # noqa: F401
        lines.append("python-docx found")
    except ImportError:
        lines.append("python-docx MISSING: run 'python3 -m pip install python-docx' (the solution overview needs it)")
        ok = False
    try:
        import PIL  # noqa: F401
        lines.append("Pillow found: diagram pictures can be drawn without LibreOffice")
    except ImportError:
        lines.append("Pillow not found: without LibreOffice too, the document links to the diagrams without pictures "
                     "(python3 -m pip install Pillow)")
    office = shutil.which("soffice") or shutil.which("libreoffice") or (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice" if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None)
    lines.append(f"LibreOffice {'found: diagram pictures are converted with it' if office else 'not found: Pillow draws the diagram pictures when it is installed (LibreOffice: https://www.libreoffice.org)'}")
    print("\n".join(lines))
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


def office_binary():
    for candidate in (shutil.which("soffice"), shutil.which("libreoffice"),
                      "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def run(cmd, timeout=180):  # seconds; one LibreOffice conversion or offline layout plan takes far less
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "probe":
        sys.exit(probe())
    print(__doc__.strip())
    sys.exit(2)
