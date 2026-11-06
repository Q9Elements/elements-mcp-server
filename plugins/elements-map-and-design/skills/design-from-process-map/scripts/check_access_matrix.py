"""Check the data access matrix against the model and write it as a CSV.

    python3 check_access_matrix.py ENG
    python3 check_access_matrix.py ENG --check   # the same checks, writing nothing (for the access-deriver)

Reads ENG/derive/access.json (the access-deriver's file) and ENG/model.json.
Every row must name an activity, a role or system, an entity (and a system
when given) of the model, CRUD letters and a controller listed in
'controllers'; every controller must be used and name roles or systems of the
model; and every step that uses an entity in the model must have at least one
row for it, so no step is dropped. ERROR lines and exit 1 when not; on a pass
writes ENG/access-matrix.csv and prints its row count. A row whose CRUD
differs from data/crud-verbs.csv's default for its verb gets a WARN line, for
the checkpoint to show.
"""

import csv
import sys

from common import SetupError, eng_path, load_crud_verbs, load_json, shape_errors

ACTION_WORDS = {"create": "New", "extend": "Update", "reuse": "Existing"}
COLUMNS = ["Level", "Step", "Resource", "Resource type", "System", "Object", "API name", "Kind", "CRUD", "Fields",
           "Permission controller", "Controller type", "New or update", "Evidence"]


def main(argv):
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "--check"):
        print(__doc__.strip())
        return 2
    eng, check_only = argv[1], len(argv) == 3
    try:
        access = load_json(eng_path(eng, "derive", "access.json"), "derive/access.json")
        model = load_json(eng_path(eng, "model.json"), "model.json")
        verbs = load_crud_verbs()
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    errors = [f"derive/access.json {e}" for e in shape_errors(access, "access.schema.json")]
    if errors:
        for line in errors:
            print(f"ERROR {line}")
        print("REFUSED fix derive/access.json and check again")
        return 1
    acts = {a["id"]: a for a in model.get("activities", [])}
    roles = {r["id"]: r for r in model.get("roles", [])}
    systems = {s["id"]: s for s in model.get("systems", [])}
    entities = {e["id"]: e for e in model.get("entities", [])}
    controllers = {c["name"]: c for c in access["controllers"]}
    warnings, used, covered = [], set(), set()
    for row in access["rows"]:
        where = f"row {row['id']}"
        if row["step"] not in acts:
            errors.append(f"{where}: step '{row['step']}' is not an activity of the model")
        if row["resource"] not in roles and row["resource"] not in systems:
            errors.append(f"{where}: resource '{row['resource']}' is not a role or system of the model")
        if row["entity"] not in entities:
            errors.append(f"{where}: entity '{row['entity']}' is not an entity of the model")
        if row.get("system") and row["system"] not in systems:
            errors.append(f"{where}: system '{row['system']}' is not a system of the model")
        if row["controller"] not in controllers:
            errors.append(f"{where}: controller '{row['controller']}' is not listed in controllers")
        used.add(row["controller"])
        covered.add((row["step"], row["entity"]))
        default = verbs.get(row["verb"].casefold())
        if default and default != row["crud"]:
            warnings.append(f"{where}: '{row['verb']}' gives {default} by data/crud-verbs.csv, the row says {row['crud']}")
    for name, c in controllers.items():
        if name not in used:
            errors.append(f"controller '{name}' is used by no row")
        for p in c["personas"]:
            if p not in roles and p not in systems:
                errors.append(f"controller '{name}': persona '{p}' is not a role or system of the model")
        if c["action"] in ("reuse", "extend") and not c.get("existing"):
            errors.append(f"controller '{name}' is to {c['action']} an existing controller but names none in 'existing'")
    for act in acts.values():
        for ref in act.get("uses", []):
            if ref in entities and (act["id"], ref) not in covered:
                errors.append(f"step '{act['name']}' ({act['id']}) uses {entities[ref]['name']} but has no access row for it")
    for line in errors:
        print(f"ERROR {line}")
    if errors:
        print("REFUSED fix derive/access.json and check again")
        return 1
    if check_only:
        for line in warnings:
            print(f"WARN {line}")
        print(f"CHECKED {len(access['rows'])} rows, {len(controllers)} permission controllers; the matrix fits the model")
        return 0
    level_of = {}
    for act in acts.values():
        level_of[act["id"]] = act["id"].split("-")[1] if act["id"].count("-") >= 2 else ""
    path = eng_path(eng, "access-matrix.csv")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in access["rows"]:
            res = roles.get(row["resource"]) or systems.get(row["resource"])
            ent = entities[row["entity"]]
            ctl = controllers[row["controller"]]
            writer.writerow([
                level_of.get(row["step"], ""), acts[row["step"]]["name"], res["name"],
                "integration user" if row.get("integrationUser") else (res.get("kind") or ""),
                systems[row["system"]]["name"] if row.get("system") else "", ent["name"], ent.get("apiName", ""),
                ent.get("kind", ""), row["crud"], "; ".join(row.get("fields", [])), ctl["name"], ctl["type"],
                ACTION_WORDS[ctl["action"]], "; ".join(row["evidence"])])
    for line in warnings:
        print(f"WARN {line}")
    print(f"WROTE access-matrix.csv: {len(access['rows'])} rows, {len(controllers)} permission controllers")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
