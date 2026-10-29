"""Check the target-system evidence is complete and turn it into one targets file.

    python3 prepare_evidence.py ENG --route org            # org pulls in ENG/evidence/
    python3 prepare_evidence.py ENG --route documentation  # ENG/evidence/doc-inventory.json
    python3 prepare_evidence.py ENG --verify PULL          # one later pull, such as access

Route org reads ENG/evidence/pulls.json, the part files it lists
(evidence/<pull>-<index>.ndjson: the pulls objects, fields and one per
integration evidence type) and evidence/packages.json. Every part named
in pulls.json must be saved with the row count and SHA-256 the tool reported,
the parts must add up to the pull's totalRows, and every metadata type of
data/integration-evidence-types.csv must have a pull or be marked
{"notSynced": true}; otherwise the script refuses (exit 1), so a list read in
part is never taken for the whole list.

Route documentation reads ENG/evidence/doc-inventory.json, the
system-doc-reader's index-mode inventory.

Writes ENG/evidence/targets.json: the target system's objects (with kind
standard, custom or external, and on the org route their fields), the
integration evidence (org route only), the installed packages and the gaps.
On the documentation route every object is the target system's own, so its
kind is standard. Prints OBJECTS n, INTEGRATION EVIDENCE n,
GAP lines, and exits 4 with NO TARGET OBJECTS when no object was found.

--verify checks one pull of pulls.json the same way (every part saved, rows
and SHA-256 as reported, totalRows reached), prints VERIFIED <pull> <n> rows
(exit 0) or ERROR lines and REFUSED (exit 1), also for a pull pulls.json does
not record, and writes nothing.
"""

import argparse
import sys

from common import (EVIDENCE_TYPES_CSV, SetupError, eng_path, load_json, read_csv, read_ndjson, sha256, slug,
                    write_json)

from mcp_result import native_errors, require_complete

KINDS = {"Standard Object": "standard", "Custom Object": "custom", "External Object": "external"}


def pull_rows(eng, name, pull, errors):
    if pull.get("notSynced"):
        return None
    errors.extend(f"pull {name}: {error}" for error in native_errors(pull))
    parts = pull.get("parts") or []
    if pull.get("partsTotal") is not None and len(parts) != pull["partsTotal"]:
        errors.append(f"pull '{name}' lists {len(parts)} part(s) but the tool reported partsTotal {pull['partsTotal']}; "
                      "call again with partsFrom and record every part")
    rows, counted = [], 0
    for part in parts:
        path = eng_path(eng, "evidence", f"{name}-{part['index']}.ndjson")
        if not path.exists():
            errors.append(f"pull '{name}' part {part['index']} is not saved at evidence/{path.name}")
            continue
        if part.get("sha256") and sha256(path) != part["sha256"]:
            errors.append(f"pull '{name}' part {part['index']} does not match the SHA-256 the tool reported; download it again")
            continue
        got = read_ndjson([path])
        if part.get("rows") is not None and len(got) != part["rows"]:
            errors.append(f"pull '{name}' part {part['index']} has {len(got)} rows, the tool reported {part['rows']}")
        counted += len(got)
        rows.extend(got)
    if pull.get("totalRows") is not None and counted != pull["totalRows"] and not errors:
        errors.append(f"pull '{name}' has {counted} rows in its parts, the tool reported totalRows {pull['totalRows']}")
    return rows


def org(eng):
    pulls = load_json(eng_path(eng, "evidence", "pulls.json"), "evidence/pulls.json")
    types = read_csv(EVIDENCE_TYPES_CSV, ["metadata_type", "shows", "direction"])
    errors, gaps = [], []
    if "objects" not in pulls:
        errors.append("pulls.json has no 'objects' pull (Standard, Custom and External Object rows)")
    if "fields" not in pulls:
        errors.append("pulls.json has no 'fields' pull (Field rows of every object)")
    for row in types:
        if f"integration-{slug(row['metadata_type'])}" not in pulls:
            errors.append(f"pulls.json has no 'integration-{slug(row['metadata_type'])}' entry for {row['metadata_type']}; "
                          "pull it, or record {\"notSynced\": true} when describe_metadata_schema does not list the type")
    if errors:
        return errors, None
    gaps.extend(f"{name}: {failure.get('nodeId')} {failure.get('error') or failure.get('reason')}"
                for name, entry in pulls.items() for failure in entry.get("failed", []))
    objects = []
    for row in pull_rows(eng, "objects", pulls["objects"], errors) or []:
        sf = row.get("sf") or {}
        objects.append({"nodeId": row.get("nodeId"), "name": row.get("name"), "apiName": sf.get("apiName") or row.get("api_name"),
                        "kind": KINDS.get(sf.get("type") or row.get("type"), "custom"),
                        "description": (row.get("description") or row.get("summary") or "")[:500],
                        "managed": bool((row.get("nodeDetails") or {}).get("isManaged"))})
    by_api = {o["apiName"]: o for o in objects if o.get("apiName")}
    for row in pull_rows(eng, "fields", pulls["fields"], errors) or []:
        sf = row.get("sf") or {}
        full = sf.get("fullApiName") or row.get("full_api_name") or ""
        owner = full.split("/", 1)[0] if "/" in full else None
        if owner in by_api:
            details = row.get("nodeDetails") or {}
            by_api[owner].setdefault("fields", []).append(
                {"name": row.get("name"), "apiName": sf.get("apiName") or row.get("api_name"),
                 "type": details.get("subtype") or row.get("subtype"),
                 "required": details.get("required") or row.get("required")})
    evidence = []
    for row in types:
        name = f"integration-{slug(row['metadata_type'])}"
        got = pull_rows(eng, name, pulls[name], errors)
        if got is None:
            gaps.append(f"{row['metadata_type']} is not synced for this org, so integrations of that kind cannot be seen")
            continue
        for item in got:
            sf = item.get("sf") or {}
            evidence.append({"type": row["metadata_type"], "shows": row["shows"], "direction": row["direction"],
                             "name": item.get("name"), "apiName": sf.get("apiName") or item.get("api_name"),
                             "nodeId": item.get("nodeId"),
                             "description": (item.get("description") or item.get("summary") or "")[:500]})
    packages = []
    path = eng_path(eng, "evidence", "packages.json")
    if path.exists():
        answer = require_complete(load_json(path, "evidence/packages.json"))
        for pkg in answer.get("packages", []):
            packages.append({k: pkg[k] for k in ("namespace", "displayName", "name", "label") if k in pkg})
    else:
        errors.append('evidence/packages.json is missing; save the packages of every list_managed_packages page as {"packages": [...]}')
    return errors, {"route": "org", "objects": objects, "integrationEvidence": evidence, "packages": packages, "gaps": gaps}


def documentation(eng):
    inventory = load_json(eng_path(eng, "evidence", "doc-inventory.json"), "evidence/doc-inventory.json")
    objects = [{"name": o.get("name"), "apiName": o.get("apiName"),
                "kind": "standard",
                "description": (o.get("description") or "")[:500], "docUrl": o.get("docUrl")}
               for o in inventory.get("objects", [])]
    gaps = [g.get("note", "") for g in inventory.get("gaps", []) if g.get("note")]
    gaps.append("Documentation route: existing integrations and existing access cannot be seen, so every integration "
                "and every permission controller is proposed")
    return [], {"route": "documentation", "system": inventory.get("system"), "objects": objects,
                "integrationEvidence": [], "packages": [], "gaps": gaps}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("eng")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--route", choices=("org", "documentation"))
    group.add_argument("--verify", metavar="PULL")
    args = parser.parse_args(argv[1:])
    if args.verify:
        try:
            pulls = load_json(eng_path(args.eng, "evidence", "pulls.json"), "evidence/pulls.json")
            errors, rows = [], None
            if args.verify not in pulls:
                errors.append(f"pulls.json has no '{args.verify}' pull; record it as the card says")
            else:
                rows = pull_rows(args.eng, args.verify, pulls[args.verify], errors)
        except SetupError as exc:
            print(f"SETUP {exc}", file=sys.stderr)
            return 2
        for line in errors:
            print(f"ERROR {line}")
        if errors:
            print("REFUSED the pull is incomplete or not recorded; fix what the ERROR lines name and verify again")
            return 1
        print(f"VERIFIED {args.verify} {len(rows or [])} rows")
        return 0
    try:
        errors, targets = org(args.eng) if args.route == "org" else documentation(args.eng)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED the evidence is incomplete; fix the pulls and run again")
        return 1
    write_json(eng_path(args.eng, "evidence", "targets.json"), targets)
    print(f"OBJECTS {len(targets['objects'])}")
    print(f"INTEGRATION EVIDENCE {len(targets['integrationEvidence'])}")
    for gap in targets["gaps"]:
        print(f"GAP {gap}")
    if not targets["objects"]:
        print("NO TARGET OBJECTS neither the org nor the documentation gave any objects")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
