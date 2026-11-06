"""Helpers shared by the map-agent-as-process scripts.

What every level-by-level process reader shares (outline rules, the boundary
labels, ids, files) is the plugin's scripts/process_levels.py; this file adds
the two data tables of this skill and the package inventory's schema check.

Standard library only; Python 3.8 or later.
"""

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PLUGIN = SKILL.parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import process_levels  # noqa: E402  (the shared core of level-by-level process readers)
from process_levels import (  # noqa: E402,F401  (re-exported for this skill's scripts)
    END, OUTLINE_SCHEMA, START, SetupError, dedupe, load_json, model_id, norm, read_csv, slug, split_list,
    write_json)

DATA = SKILL / "data"
FORMATS_CSV = DATA / "agent-package-formats.csv"
PREFIXES_CSV = DATA / "resource-prefixes.csv"
KNOWN_TOOLS_CSV = DATA / "known-mcp-tools.csv"
INVENTORY_SCHEMA = SKILL / "schemas" / "inventory.schema.json"
RULES = SKILL / "references" / "articulation-rules.md"
ASSISTANT = "assistant"  # the component id of the session that runs the package
STAGE_SOURCES = ("dispatch-table", "stage-table", "headings", "commands", "package-list")


def load_formats(path=FORMATS_CSV):
    rows = read_csv(Path(path), ["format", "priority", "detect", "entry", "stage_source", "recovery_states", "default_mcp_server",
                                 "tested", "notes"])
    for row in rows:
        if row["stage_source"] not in STAGE_SOURCES:
            raise SetupError(f"{Path(path).name}: format '{row['format']}' has stage_source '{row['stage_source']}'; use one of {', '.join(STAGE_SOURCES)}")
        try:
            row["priority"] = int(row["priority"])
        except ValueError:
            raise SetupError(f"{Path(path).name}: format '{row['format']}' priority '{row['priority']}' is not a whole number")
        row["detect"] = split_list(row["detect"])
        row["recovery_states"] = split_list(row["recovery_states"])
    return sorted(rows, key=lambda r: r["priority"])


def load_prefixes(path=PREFIXES_CSV):
    rows = read_csv(Path(path), ["kind", "id_prefix", "name_prefix", "role_kind", "order", "business_view", "technical_view", "path_globs", "notes"])
    table = {}
    for row in rows:
        if row["role_kind"] not in ("system", "ai-agent"):
            raise SetupError(f"{Path(path).name}: kind '{row['kind']}' has role_kind '{row['role_kind']}'; use system or ai-agent")
        for view in ("business_view", "technical_view"):
            if row[view] not in ("yes", "no"):
                raise SetupError(f"{Path(path).name}: kind '{row['kind']}' has {view} '{row[view]}'; use yes or no")
        row["order"] = int(row["order"])
        row["path_globs"] = split_list(row["path_globs"])
        table[row["kind"]] = row
    if "assistant" not in table:
        raise SetupError(f"{Path(path).name}: needs a row for kind 'assistant'")
    return table


def load_known_tools(path=KNOWN_TOOLS_CSV):
    """Tool name -> MCP server, for tools a package names without their server (`search_metadata`)."""
    if not Path(path).exists():
        return {}
    return {row["tool"]: row["server"] for row in read_csv(Path(path), ["server", "tool"])}


def shape_errors(document, schema_path=INVENTORY_SCHEMA):
    return process_levels.shape_errors(document, schema_path)


def display_name(component, prefixes):
    """The resource name drawn on a box: the kind's prefix and the component's name."""
    row = prefixes[component["kind"]]
    if component["kind"] == "assistant":
        return row["name_prefix"]
    return f"{row['name_prefix']}: {component['name']}"
