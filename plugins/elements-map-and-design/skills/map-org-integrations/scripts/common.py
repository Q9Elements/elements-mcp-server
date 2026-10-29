"""Helpers shared by the map-org-integrations scripts.

Standard library only (Python 3.8 or later). Shape checks reuse the plugin's validator (scripts/validate.py), so
every file an agent writes is checked against its JSON Schema the same way as the shared model.

    python3 common.py probe     # report the tools a run needs
"""

import csv
import hashlib
import json
import re
import shutil
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

DATA = SKILL / "data"
SCHEMAS = SKILL / "schemas"
INVENTORY_TYPES_CSV = DATA / "inventory-types.csv"
KNOWN_SYSTEMS_CSV = DATA / "known-systems.csv"
NOT_EXTERNAL_CSV = DATA / "not-external.csv"
HIT_TYPES_CSV = DATA / "hit-types.csv"
LIMITS_CSV = DATA / "limits.csv"
SYSTEM_KINDS = ("salesforce", "middleware", "external-app", "data-store", "channel")  # the shared model's system kinds


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


def shape_errors(document, schema_name):
    """Check a document against one of this skill's schemas; return error lines."""
    schema = load_json(SCHEMAS / schema_name, "schema")
    validate.check_schema_keywords(schema, "#")
    findings = Findings()
    validate.check_shape(document, schema, "", schema, findings)
    return findings.errors


# ---------------------------------------------------------------- text and ids

def norm(text):
    return " ".join((text or "").split()).casefold()


def slug(text, limit=40):
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return value[:limit].rstrip("-") or "x"


def words(text):
    """The words of a name, CamelCase and separators split: 'MakeDataCloud' -> ['make', 'data', 'cloud']."""
    text = re.sub(r"__[a-z]+$", "", text or "")                  # API suffixes such as __e, __c
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return [w for w in re.split(r"[^A-Za-z0-9.]+", text.casefold()) if w]


def phrase_in(phrase, text):
    """Whether every word of phrase appears, in order and adjacent, among the words of text."""
    target, have = words(phrase), words(text)
    if not target:
        return False
    n = len(target)
    return any(have[i:i + n] == target for i in range(len(have) - n + 1))


def host_of(url):
    match = re.match(r"^[a-z][a-z0-9+.-]*://([^/:?#]+)", (url or "").strip(), re.I)
    return match.group(1).casefold() if match else ""


def domain_matches(host, domain):
    host, domain = host.casefold(), domain.casefold().lstrip(".")
    return bool(host) and (host == domain or host.endswith("." + domain))


def system_id(name):
    return slug(name, 48)


# ---------------------------------------------------------------- data files

def split(value):
    return [v.strip() for v in (value or "").split("|") if v.strip()]


def load_limits(path=LIMITS_CSV):
    limits = {}
    for row in read_csv(path, ["setting", "value", "rule"]):
        try:
            limits[row["setting"]] = int(row["value"])
        except ValueError:
            raise SetupError(f"{Path(path).name}: {row['setting']} needs a whole number")
    needed = ["min_term_length", "max_terms_per_system", "max_searches", "max_explained", "explain_batch",
              "dependency_batch", "source_batch", "trace_rounds", "fix_rounds"]
    missing = [k for k in needed if k not in limits]
    if missing:
        raise SetupError(f"{Path(path).name} lacks {', '.join(missing)}")
    return limits


def load_inventory_types(path=INVENTORY_TYPES_CSV):
    rows = read_csv(path, ["metadata_type", "role", "read_source", "direction", "shows"])
    for row in rows:
        if row["role"] not in ("proof", "support", "package-component"):
            raise SetupError(f"{Path(path).name}: {row['metadata_type']} has role '{row['role']}'; use proof, support or package-component")
        if row["read_source"] not in ("yes", "no"):
            raise SetupError(f"{Path(path).name}: {row['metadata_type']} has read_source '{row['read_source']}'; use yes or no")
    return rows


def load_known_systems(path=KNOWN_SYSTEMS_CSV):
    rows = read_csv(path, ["vendor", "kind", "middleware", "aliases", "domains", "namespaces", "search_terms", "icon"])
    systems = []
    for row in rows:
        if row["kind"] not in SYSTEM_KINDS:
            raise SetupError(f"{Path(path).name}: {row['vendor']} has kind '{row['kind']}'; use {', '.join(SYSTEM_KINDS)}")
        if row["middleware"] not in ("yes", "no"):
            raise SetupError(f"{Path(path).name}: {row['vendor']} has middleware '{row['middleware']}'; use yes or no")
        systems.append({"vendor": row["vendor"], "kind": row["kind"], "middleware": row["middleware"] == "yes",
                        "aliases": split(row["aliases"]), "domains": split(row["domains"]),
                        "namespaces": [n.casefold() for n in split(row["namespaces"])],
                        "searchTerms": split(row["search_terms"]), "icon": row["icon"]})
    return systems


def load_not_external(path=NOT_EXTERNAL_CSV):
    rows = read_csv(path, ["match_on", "pattern", "reason"])
    out = []
    for row in rows:
        if row["match_on"] not in ("domain", "api_name", "name", "namespace"):
            raise SetupError(f"{Path(path).name}: match_on '{row['match_on']}'; use domain, api_name, name or namespace")
        try:
            out.append(dict(row, regex=re.compile(row["pattern"], re.I)))
        except re.error as exc:
            raise SetupError(f"{Path(path).name}: pattern {row['pattern']!r} is not a regular expression: {exc}")
    return out


def load_hit_types(path=HIT_TYPES_CSV):
    """Rows by normalised Salesforce type; skip is the compiled skip_name pattern or None."""
    rows = read_csv(path, ["sf_type", "role", "automation_type", "why", "skip_name"])
    out = {}
    for row in rows:
        if row["role"] not in ("automation", "key-field", "gateway"):
            raise SetupError(f"{Path(path).name}: {row['sf_type']} has role '{row['role']}'")
        try:
            row["skip"] = re.compile(row["skip_name"]) if row["skip_name"] else None
        except re.error as exc:
            raise SetupError(f"{Path(path).name}: skip_name of {row['sf_type']} is not a regular expression: {exc}")
        out[norm(row["sf_type"])] = row
    return out


# ---------------------------------------------------------------- pulls

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
    if entry.get("notSynced"):
        return []
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


def type_slug(metadata_type):
    return slug(metadata_type)


# ---------------------------------------------------------------- state

def load_state(eng):
    return load_json(Path(eng) / "execution-state.json", "the state file")


# ---------------------------------------------------------------- probe

def probe():
    lines, ok = [], True
    lines.append(f"python {sys.version.split()[0]}" + ("" if sys.version_info >= (3, 8) else "  NEEDS 3.8 or later"))
    ok = ok and sys.version_info >= (3, 8)
    curl = shutil.which("curl")
    lines.append(f"curl {'found' if curl else 'MISSING: install curl to download Elements result parts'}")
    ok = ok and bool(curl)
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
