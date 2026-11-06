#!/usr/bin/env python3
"""Print an ordered, local pull plan as JavaScript Object Notation (JSON).

Usage: python3 scripts/plan_pull.py --discovery raw/DATE/list_reference_models.json
       --template multi-org-overview [--types 'Field,Flow'] [--with-tech-debt] [--space-pages N]

Exit 0: plan valid; validate discovered columns, then execute the printed calls.
Exit 2: input invalid; repair the named discovery, selection or collision and re-run.
This command reads local files and writes only its plan to standard output.
"""

import argparse
import json
from pathlib import Path
import re
import sys

from helpers import _read_json, build_confirmed_org_slugs


# The Overview pull spec defines the default scope; explicit --types customizes it.
DEFAULT_TYPES = "Field,Custom Object,Flow,Apex Class,Apex Trigger,Validation Rule"


def make_plan(path, types, with_tech_debt=False, space_pages=1):
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError("discovery must be a resolved object")
    reference_models = data["referenceModels"]
    confirmed = data["confirmedOrgs"]
    team_id = data["activeSpace"]["teamId"]
    if not isinstance(team_id, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", team_id):
        raise ValueError("activeSpace.teamId must be a discovered 24-hex Space identifier")
    if space_pages < 1:
        raise ValueError("space-pages must be the positive number of discovery pages consumed")
    type_slugs = [re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") for value in types]
    if not all(type_slugs) or len(set(type_slugs)) != len(type_slugs) or any(len(value) > 100 for value in types):
        raise ValueError("types must be nonempty canonical names with distinct filenames, at most 100 characters each")
    if (not isinstance(confirmed, list) or not confirmed
            or any(not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{24}", value) for value in confirmed)
            or len(set(confirmed)) != len(confirmed)):
        raise ValueError("confirmedOrgs must contain distinct, confirmed 24-hex reference model identifiers")
    if not isinstance(reference_models, list):
        raise ValueError("referenceModels must be a resolved array")
    available = {entry["refModelId"] for entry in reference_models}
    if not set(confirmed) <= available:
        raise ValueError("confirmedOrgs includes reference models missing from discovery")
    slugs = build_confirmed_org_slugs(reference_models, confirmed)
    orgs = []
    for ref_model_id in confirmed:
        base = {"refModelId": ref_model_id, "teamId": team_id}
        calls = []

        def add(tool, file, **arguments):
            calls.append({"tool": tool, "file": file, "arguments": {**base, **arguments}})

        def count(file, **selection):
            add("list_metadata_by_criteria", "list_metadata_by_criteria/" + file,
                mode="manifest", filters=[{"column": "status", "operator": "neq", "value": "deleted"}],
                **selection)

        add("describe_metadata_schema", "types_present.json", allNodes=True, delivery="file")
        add("understand_org_health", "understand_org_health__structure.json", area="structure", delivery="file")
        count("manifest__all_nodes.json", allNodes=True)
        count("manifest__all_nodes__managed.json", allNodes=True)
        calls[-1]["arguments"]["filters"].insert(0, {"column": "manage_package", "operator": "eq", "value": True})
        for type_name in types:
            slug = re.sub(r"[^a-z0-9]+", "_", type_name.lower()).strip("_")
            count(f"manifest__type__{slug}.json", metadataList=[type_name])
        if with_tech_debt:
            # These coverage areas supplement the Overview's six default types.
            for type_name in ("Record Type", "Profile", "Permission Set", "Permission Set Group"):
                if type_name not in types:
                    slug = re.sub(r"[^a-z0-9]+", "_", type_name.lower()).strip("_")
                    count(f"manifest__type__{slug}.json", metadataList=[type_name])
            add("understand_org_health", "understand_org_health__tech_debt.json", area="tech_debt", delivery="file")
        orgs.append({"refModelId": ref_model_id, "slug": slugs[ref_model_id],
                     "directory": str(path.parent / slugs[ref_model_id]), "calls": calls})
    # Discovery includes Space pages, the reference-model list and the accepted-type schema.
    total = space_pages + 2 + sum(len(org["calls"]) for org in orgs)
    # The 50-call pacing budget is defined in the tool contracts.
    return {"discoveryCalls": [{"tool": "describe_metadata_schema", "file": "describe_metadata_schema.json",
                                "arguments": {"refModelId": confirmed[0], "teamId": team_id, "delivery": "file"}}],
            "orgs": orgs, "totalCalls": total, "minutesAt50CallsPerMinute": total / 50}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", required=True, type=Path)
    parser.add_argument("--template", required=True, choices=["multi-org-overview"])
    parser.add_argument("--types", default=DEFAULT_TYPES)
    parser.add_argument("--with-tech-debt", action="store_true")
    parser.add_argument("--space-pages", type=int, default=1, help="actual discovery page count (default: one)")
    args = parser.parse_args(argv)
    try:
        plan = make_plan(args.discovery, [value.strip() for value in args.types.split(",")],
                         args.with_tech_debt, args.space_pages)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        parser.error(f"{exc}; repair discovery or selection and re-run the planner")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
