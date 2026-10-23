"""Helpers shared by the compare-design-to-implementation scripts.

Standard library only (Python 3.8 or later). Shape checks reuse the plugin's validator (scripts/validate.py), so
every file an agent writes is checked against its JSON Schema the same way as the shared model.

    python3 common.py probe     # report the tools a run needs
"""

import csv
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from mcp_result import hydrate, native_errors, owner_api, require_complete, write_complete
from manage_batches import bounded_plan

import validate  # noqa: E402  (the plugin's model validator)

SetupError = validate.SetupError
Findings = validate.Findings

DATA = SKILL / "data"
SCHEMAS = SKILL / "schemas"
AUTOMATION_TYPES_CSV = PLUGIN / "data" / "automation-types.csv"
COLOURED = ("supported", "partial", "not-supported")
VERDICTS = COLOURED + ("not-assessed", "no-org-support")
NOTE_MARKER = "Design check:"          # first words of every note this playbook adds; reset finds notes by it
LEGEND_MARKER = "Design check legend:"  # first words of the legend note


class Failed(Exception):
    """A check found problems; the message lines are printed and the script exits 1."""

    def __init__(self, lines):
        super().__init__("\n".join(lines))
        self.lines = list(lines)


# ---------------------------------------------------------------- files

def load_json(path, what="file"):
    try:
        return hydrate(validate.load_json_strict(path))
    except OSError as exc:
        raise SetupError(f"cannot read {what} {path}: {exc}")
    except ValueError as exc:
        raise SetupError(f"{what} {path} is not valid JSON: {exc}")


def write_json(path, data):
    """Write through a temporary file and a rename, so a reader never sees half a file."""
    if isinstance(data, dict) and all(key in data for key in ("diagramId", "baseVersion", "changes")):
        data = bounded_plan(dict(data, dryRunFirst=True))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_ndjson(path):
    rows = []
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


def shape_errors(document, schema_name):
    schema = load_json(SCHEMAS / schema_name, "schema")
    validate.check_schema_keywords(schema, "#")
    findings = Findings()
    validate.check_shape(document, schema, "", schema, findings)
    return findings.errors


def load_state(eng):
    return load_json(Path(eng) / "execution-state.json", "the state file")


# ---------------------------------------------------------------- data files

def load_verdicts(path=DATA / "verdicts.csv"):
    rows = read_csv(path, ["verdict", "colour", "fill", "label", "legend", "coloured"])
    out = {r["verdict"]: r for r in rows}
    if set(out) != set(VERDICTS) or len(rows) != len(VERDICTS):
        raise SetupError(f"verdicts.csv must hold exactly the verdicts {', '.join(VERDICTS)}")
    for v in VERDICTS:
        row = out[v]
        if (v in COLOURED) != (row["coloured"] == "yes"):
            raise SetupError(f"verdicts.csv: {v} must have coloured {'yes' if v in COLOURED else 'no'}")
        if v in COLOURED and not re.match(r"^#[0-9A-Fa-f]{6}$", row["fill"]):
            raise SetupError(f"verdicts.csv: {v} needs a fill such as #9FE2A9")
        if v not in COLOURED and row["fill"]:
            raise SetupError(f"verdicts.csv: {v} has no colour, so its fill stays empty")
    fills = [out[v]["fill"].upper() for v in COLOURED]
    if len(set(fills)) != len(fills):
        raise SetupError("verdicts.csv: the three fills must differ")
    return out


ROLLUP_OWN = ("supported", "partial", "not-supported", "none")
ROLLUP_CHILDREN = ("all-supported", "all-not-supported", "mixed", "all-not-assessed", "none")


def load_rollup(path=DATA / "rollup.csv"):
    rows = read_csv(path, ["own", "children", "parent", "why"])
    out = {}
    for row in rows:
        key = (row["own"], row["children"])
        if row["own"] not in ROLLUP_OWN or row["children"] not in ROLLUP_CHILDREN:
            raise SetupError(f"rollup.csv: unknown own/children {key}")
        if row["parent"] not in VERDICTS:
            raise SetupError(f"rollup.csv: {key} gives unknown verdict {row['parent']}")
        if key in out:
            raise SetupError(f"rollup.csv: {key} appears twice")
        out[key] = row["parent"]
    missing = [(o, c) for o in ROLLUP_OWN for c in ROLLUP_CHILDREN if (o, c) not in out]
    if missing:
        raise SetupError("rollup.csv lacks " + ", ".join(f"{o} x {c}" for o, c in missing))
    for (own, children), parent in out.items():
        if parent == "supported" and (children in ("all-not-assessed", "mixed", "all-not-supported")):
            raise SetupError(f"rollup.csv: {own} x {children} must never give a supported parent")
    return out


def automation_sf_types():
    rows = read_csv(AUTOMATION_TYPES_CSV, ["type", "sf_types"])
    out = set()
    for row in rows:
        for t in row["sf_types"].split("|"):
            if t.strip():
                out.add(norm(t))
    return out


def load_link_types(path=DATA / "link-types.csv"):
    """Linkable types by normalised name: {kind, qualify, sf_type}; automations come from the plugin's automation-types.csv."""
    rows = read_csv(path, ["sf_type", "kind", "qualify", "why"])
    out = {}
    for row in rows:
        if row["qualify"] not in ("", "object"):
            raise SetupError(f"link-types.csv: {row['sf_type']} has qualify '{row['qualify']}'")
        key = norm(row["sf_type"])
        if key in out:
            raise SetupError(f"link-types.csv: {row['sf_type']} appears twice")
        out[key] = {"sf_type": row["sf_type"], "kind": row["kind"], "qualify": row["qualify"]}
    for t in automation_sf_types():
        out.setdefault(t, {"sf_type": t, "kind": "automation", "qualify": ""})
    return out


def load_limits(path=DATA / "limits.csv"):
    rows = read_csv(path, ["name", "value", "why"])
    out = {}
    for row in rows:
        try:
            out[row["name"]] = int(row["value"])
        except ValueError:
            raise SetupError(f"limits.csv: {row['name']} must be a whole number")
    need = ["note_max_words", "assessor_wave", "matcher_rounds", "terms_per_box", "more_terms_per_box", "hits_per_search",
            "candidates_per_box", "automations_per_object", "dependency_rows_per_component",
            "change_logs_per_component", "definition_chars_per_component", "boxes_per_run", "note_gap_px", "note_size_px"]
    missing = [n for n in need if n not in out]
    if missing:
        raise SetupError("limits.csv lacks " + ", ".join(missing))
    return out


# ---------------------------------------------------------------- text and ids

def norm(text):
    return " ".join((text or "").split()).casefold()


def slug(text, limit=48):
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return value[:limit].rstrip("-") or "x"


def word_count(text):
    return len((text or "").split())


def box_id(level, key):
    return f"L{level}-{key}"


def level_sort_key(level):
    return [int(p) if p.isdigit() else p for p in str(level).split(".")]


def is_object_type(sf_type):
    return norm(sf_type) in ("standard object", "custom object", "object", "external object", "big object")


# ---------------------------------------------------------------- pulls (NDJSON part files)

def load_pulls(eng):
    path = Path(eng) / "evidence" / "pulls.json"
    if not path.exists():
        return {}
    return load_json(path, "the pull register")


def verify_pull(eng, name, pulls=None):
    """Error lines for one recorded pull: every part saved, with the rows and sha256 the answer gave."""
    pulls = load_pulls(eng) if pulls is None else pulls
    entry = pulls.get(name)
    if entry is None:
        return [f"pull {name} is not recorded in evidence/pulls.json"]
    errors = [f"pull {name}: {error}" for error in native_errors(entry)]
    parts = entry.get("parts") or []
    total = entry.get("partsTotal")
    if total is not None and len(parts) != total:
        errors.append(f"pull {name}: {len(parts)} of {total} parts recorded; call again with partsFrom set to nextPartsFrom")
    rows = 0
    for part in parts:
        path = Path(eng) / "evidence" / f"{name}-{part['index']}.ndjson"
        if not path.exists():
            errors.append(f"pull {name}: part {part['index']} is not saved as {path.name}; call again for a fresh link")
            continue
        if part.get("sha256") and sha256(path) != part["sha256"]:
            errors.append(f"pull {name}: part {part['index']} does not match its sha256; download it again")
            continue
        count = len(read_ndjson(path))
        if part.get("rows") is not None and count != part["rows"]:
            errors.append(f"pull {name}: part {part['index']} has {count} rows, the answer said {part['rows']}")
        rows += count
    if not errors and entry.get("totalRows") is not None and rows != entry["totalRows"]:
        errors.append(f"pull {name}: {rows} rows saved, the answer said {entry['totalRows']}")
    return errors


def pull_rows(eng, name, pulls=None):
    pulls = load_pulls(eng) if pulls is None else pulls
    entry = pulls.get(name) or {}
    rows = []
    for part in sorted(entry.get("parts") or [], key=lambda p: p["index"]):
        rows += read_ndjson(Path(eng) / "evidence" / f"{name}-{part['index']}.ndjson")
    return rows


# ---------------------------------------------------------------- running a command

def run(main_fn):
    """Exit 0 on success, 1 on Failed (its lines printed), 2 on SetupError."""
    try:
        code = main_fn()
    except Failed as exc:
        for line in exc.lines:
            print(f"ERROR {line}")
        sys.exit(1)
    except SetupError as exc:
        print(f"SETUP: {exc}")
        sys.exit(2)
    sys.exit(code or 0)


def probe():
    lines, ok = [], True
    lines.append(f"python {sys.version.split()[0]}" + ("" if sys.version_info >= (3, 8) else "  NEEDS 3.8 or later"))
    ok = ok and sys.version_info >= (3, 8)
    curl = shutil.which("curl")
    lines.append(f"curl {'found' if curl else 'MISSING: install curl to download Elements result parts'}")
    ok = ok and bool(curl)
    try:
        load_verdicts()
        load_rollup()
        load_link_types()
        load_limits()
        lines.append("data files load")
    except SetupError as exc:
        lines.append(f"data files: {exc}")
        ok = False
    print("\n".join(lines))
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "probe":
        sys.exit(probe())
    print(__doc__.strip())
    sys.exit(2)


def native_gaps(pulls):
    return [f"{name}: {failure.get('nodeId')} {failure.get('error') or failure.get('reason')}"
            for name, entry in pulls.items() for failure in entry.get('failed', [])]
