#!/usr/bin/env python3
"""Join the org's integration inventory into one file.

Usage:
  python3 inventory.py source-ids ENG     # the nodeIds whose stored definition names an endpoint
  python3 inventory.py build ENG          # verify every pull and write ENG/inventory.json

The run saves, in ENG/evidence/: packages.json
({"packages": [...]}, every page of list_managed_packages), pulls.json (one entry per list call: its parts'
index, rows and sha256, or {"notSynced": true}) and each part as <pull>-<index>.ndjson. Pull names:
inventory-<type> for each row of data/inventory-types.csv, and the pulls evidence/source-ids.json names for the
get_metadata_source calls (sources, sources-2, ...).

source-ids  Checks the inventory pulls and writes evidence/source-ids.json: the nodeIds of every row whose type
            reads its source (data/inventory-types.csv, read_source yes), in batches of source_batch
            (data/limits.csv), each with the pull name to record its get_metadata_source answer under.
build       Checks every pull; joins the rows into ENG/inventory.json: one item per inventory row with its type,
            role, namespace (from parentPath), description and, from its stored definition, the endpoint URL and
            domain (or the named credential an external service calls through); the managed packages; the
            types this model does not sync.

Exit 0 with READY or INVENTORY. Exit 1 REFUSED: a pull is incomplete (its ERROR lines say what to fetch again).
Exit 2: setup problem. Exit 4 NOT SYNCED: none of the types that prove a system is synced for this model.
"""

import re
import sys
from pathlib import Path

import common
from common import SetupError

ENDPOINT_TAGS = re.compile(r"<(url|endpoint|parameterValue)>\s*(https?://[^<\s]+)\s*</\1>", re.I)  # where a stored definition holds its URL: remote site <url>, named credential <endpoint> or URL <parameterValue>
NAMED_CREDENTIAL_TAGS = re.compile(r"<(namedCredentialReference|namedCredential)>\s*([^<\s]+)\s*</\1>", re.I)  # where an external service names the named credential it calls through


def inventory_pulls(eng):
    types = common.load_inventory_types()
    pulls = common.load_pulls(eng)
    errors = []
    for row in types:
        name = "inventory-" + common.type_slug(row["metadata_type"])
        if name not in pulls:
            errors.append(f"pull {name} ({row['metadata_type']}) is not recorded in evidence/pulls.json; pull it, or record "
                          f'"{name}": {{"notSynced": true}} when describe_metadata_schema does not list the type')
            continue
        errors += common.verify_pull(eng, name, pulls)
    return types, pulls, errors


def namespace_of(row):
    path = row.get("parentPath") or ""
    match = re.match(r"^Namespace\.([^.]+)\.", path)
    return match.group(1) if match else ""


def source_ids(eng):
    types, pulls, errors = inventory_pulls(eng)
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED")
        return 1
    reading = {r["metadata_type"] for r in types if r["read_source"] == "yes"}
    ids = []
    for row in types:
        name = "inventory-" + common.type_slug(row["metadata_type"])
        if row["metadata_type"] not in reading or pulls[name].get("notSynced"):
            continue
        ids += [r["nodeId"] for r in common.pull_rows(eng, name, pulls) if r.get("nodeId")]
    ids = list(dict.fromkeys(ids))
    size = common.load_limits()["source_batch"]
    batches = [{"pull": "sources" if k == 0 else f"sources-{k + 1}", "nodeIds": ids[i:i + size]}
               for k, i in enumerate(range(0, len(ids), size))]
    common.write_json(Path(eng) / "evidence" / "source-ids.json", {"nodeIds": ids, "batches": batches})
    print(f"{len(ids)} node(s) to read with get_metadata_source in {len(batches)} call(s), written to evidence/source-ids.json")
    print("READY")
    return 0


def build(eng):
    eng = Path(eng)
    types, pulls, errors = inventory_pulls(eng)
    sources = {}
    source_batches = []
    if (eng / "evidence" / "source-ids.json").exists():
        source_batches = common.load_json(eng / "evidence" / "source-ids.json").get("batches", [])
    else:
        errors.append("evidence/source-ids.json is missing: run inventory.py source-ids first")
    for batch in source_batches:
        errors += common.verify_pull(eng, batch["pull"], pulls)
    packages_path = eng / "evidence" / "packages.json"
    if not packages_path.exists():
        errors.append("evidence/packages.json is missing: save every page of list_managed_packages as {\"packages\": [...]}")
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED")
        return 1
    for batch in source_batches:
        for row in common.pull_rows(eng, batch["pull"], pulls):
            sources[row.get("nodeId")] = row
    packages = common.require_complete(common.load_json(packages_path, "the package list")).get("packages")
    if not isinstance(packages, list):
        raise SetupError("evidence/packages.json needs a 'packages' list")

    items, not_synced, counts = [], [], {}
    for row in types:
        name = "inventory-" + common.type_slug(row["metadata_type"])
        if pulls[name].get("notSynced"):
            not_synced.append(row["metadata_type"])
            continue
        rows = common.pull_rows(eng, name, pulls)
        counts[row["metadata_type"]] = len(rows)
        for r in rows:
            sf = r.get("sf") or {}
            item = {"nodeId": r.get("nodeId"), "type": row["metadata_type"], "role": row["role"],
                    "direction": row["direction"], "name": r.get("name") or sf.get("apiName") or "",
                    "apiName": sf.get("apiName") or r.get("name") or "", "namespace": namespace_of(r),
                    "description": " ".join((r.get("description") or "").split())[:500],
                    "managed": bool((r.get("nodeDetails") or {}).get("isManaged"))}
            source = sources.get(r.get("nodeId"))
            if source is not None:
                text = (source.get("xml") or "") + "\n" + (source.get("body") or "")
                url = ENDPOINT_TAGS.search(text)
                if url:
                    item["url"] = url.group(2)
                    item["domain"] = common.host_of(url.group(2))
                credential = NAMED_CREDENTIAL_TAGS.search(text)
                if credential:
                    item["namedCredential"] = credential.group(2)
                if source.get("status") not in (None, "ok") or source.get("reason"):
                    item["sourceMissing"] = source.get("reason") or source.get("status")
            items.append(item)
    proof_types = [r["metadata_type"] for r in types if r["role"] == "proof"]
    proof_synced = [t for t in proof_types if t not in not_synced]
    inventory = {"items": items,
                 "packages": [{"namespace": p.get("namespace"), "nodeId": p.get("nodeId"),
                               "displayName": p.get("displayName"), "totalComponents": p.get("totalComponents")}
                              for p in packages if p.get("namespace")],
                 "typesNotSynced": not_synced, "counts": counts, "gaps": common.native_gaps(pulls)}
    common.write_json(eng / "inventory.json", inventory)
    for t in not_synced:
        print(f"GAP {t} is not synced for this reference model, so it was not read")
    print(f"{len(items)} item(s) of {len(counts)} type(s); {len(inventory['packages'])} managed package(s)")
    if not proof_synced:
        print("NOT SYNCED: none of the metadata types that prove an outside system is synced for this reference model")
        return 4
    print("INVENTORY")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("source-ids", "build"):
        print(__doc__.strip())
        return 2
    try:
        return source_ids(argv[1]) if argv[0] == "source-ids" else build(argv[1])
    except SetupError as exc:
        print(f"SETUP {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
