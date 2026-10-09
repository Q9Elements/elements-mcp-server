#!/usr/bin/env python3
"""Load and normalize Elements multi-org snapshots for renderer scripts.

Import this module from a template renderer to share the authoritative raw-file
loading, type-presence classification, normalization, statistics, and tidy CSV
rules. It is not a standalone command; renderers call ``load_snapshot`` and
``all_metrics_rows`` before writing their own artifact.
"""

import argparse
import csv
import html
import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple


class TypeCountState(NamedTuple):
    state: str


class OutlierVerdict(NamedTuple):
    method: str
    baseline: object
    spread: object
    outlier_indices: tuple
    uniform: bool
    spread_degenerate: bool


class CoverageRatio(NamedTuple):
    metric_name: str
    area: str
    metadata_type: str
    value: object
    denominator: object
    reason: object


class AsOfResolution(NamedTuple):
    instant: str
    notice: str


class PeerGrouping(NamedTuple):
    groups: dict
    source: str
    source_name: str
    declared_group_names: frozenset


class Discovery(NamedTuple):
    recorded: bool
    confirmed: object
    models_by_id: dict
    slugs_by_ref_model_id: dict


class PeerGroupArgumentError(ValueError):
    """A customer-supplied peer-group file is not usable."""


DESCRIPTION_COVERAGE_TYPES = {
    "Objects": "Custom Object",
    "Record types": "Record Type",
    "Fields": "Field",
    "Apex classes": "Apex Class",
    "Apex triggers": "Apex Trigger",
    "Flows": "Flow",
    "Profiles": "Profile",
    "Permission sets": "Permission Set",
    "Perm set groups": "Permission Set Group",
    "Validation rules": "Validation Rule",
}

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STALE_AFTER_DAYS = 7


def escape_html(value):
    return html.escape(str(value), quote=True)


def format_number(value):
    return f"{value:,}"


def format_percent(value):
    return "—" if value is None else f"{format_decimal_1(value)}%"


def format_decimal_1(value):
    """Format a stated magnitude without forcing an overflowing float conversion."""
    try:
        return f"{value:.1f}"
    except OverflowError:
        return f"{value}.0"


def _org_slug_component(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def build_org_slug(implementation_name, org_name):
    """Build the raw-directory identity from implementation and org names."""
    return "--".join(
        (_org_slug_component(implementation_name), _org_slug_component(org_name))
    )


def build_confirmed_org_slugs(reference_models, confirmed_ref_model_ids):
    """Build every selected slug and reject collisions before any org is written."""
    confirmed_ids = set(confirmed_ref_model_ids)
    slugs_by_ref_model_id = {}
    ref_model_id_by_slug = {}
    for model in reference_models:
        ref_model_id = model["refModelId"]
        if ref_model_id not in confirmed_ids:
            continue
        slug = build_org_slug(model["implementation"]["name"], model["name"])
        colliding_ref_model_id = ref_model_id_by_slug.get(slug)
        if colliding_ref_model_id is not None:
            raise ValueError(
                f"Confirmed org slug collision {slug!r}: refModelIds "
                f"{colliding_ref_model_id!r} and {ref_model_id!r}"
            )
        ref_model_id_by_slug[slug] = ref_model_id
        slugs_by_ref_model_id[ref_model_id] = slug
    return slugs_by_ref_model_id


def _stale_marker(org, as_of, *, svg=False):
    if not as_of or not freshness(org, as_of)[1]:
        return ""
    if svg:
        return '<tspan class="stale-marker"> · stale</tspan>'
    return ' <span class="stale-marker">stale</span>'


def _sync_failing_marker(org, *, svg=False):
    if not sync_failing(org):
        return ""
    if svg:
        return '<tspan class="sync-failing-marker"> · sync failing</tspan>'
    return ' <span class="sync-failing-marker">sync failing</span>'


def org_mention(org, as_of, text=None, *, svg=False):
    """Render one org mention with freshness inseparably attached."""
    tag = "tspan" if svg else "span"
    label = org["org_name"] if text is None else text
    return (
        f'<{tag} class="org-mention">{escape_html(label)}'
        f'{_stale_marker(org, as_of, svg=svg)}'
        f'{_sync_failing_marker(org, svg=svg)}</{tag}>'
    )


def implementation_mention(org, *, svg=False):
    """Render an implementation name in HTML or inline SVG."""
    tag = "tspan" if svg else "span"
    return f"<{tag}>{escape_html(org['implementation_name'])}</{tag}>"


def sync_time_value(org):
    """Render the manifest sync instant as escaped text."""
    return escape_html(org["sync_time"])


def _as_of_arg(value):
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected an ISO-8601 instant with trailing Z or explicit offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "expected an ISO-8601 instant with trailing Z or explicit offset"
        )
    return value


def is_calendar_date(value):
    if not DATE_PATTERN.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


class _AnalyticsArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if not DATE_PATTERN.fullmatch(parsed.date):
            self.error("--date must use YYYY-MM-DD")
        if not is_calendar_date(parsed.date):
            self.error("--date must be a valid calendar date in YYYY-MM-DD form")
        return parsed


def build_cli_parser(description):
    parser = _AnalyticsArgumentParser(description=description)
    parser.add_argument("--snapshots", required=True, help="snapshot store root")
    parser.add_argument("--date", required=True, help="snapshot date (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, help="output HTML file")
    parser.add_argument(
        "--as-of",
        type=_as_of_arg,
        default=None,
        help="UTC ISO instant for deterministic freshness calculations",
    )
    parser.add_argument(
        "--peer-groups",
        default=None,
        help="JSON file mapping customer-declared group names to org slug lists",
    )
    return parser


def org_sort_key(org):
    return (org["implementation_name"], org["org_name"], org["slug"])


def peer_groups(orgs):
    groups = defaultdict(list)
    for org in orgs:
        groups[org["implementation_name"]].append(org)
    return {
        name: sorted(peers, key=org_sort_key)
        for name, peers in sorted(groups.items())
    }


def resolve_peer_groups(orgs, path=None):
    """Resolve the shown grouping, applying a validated customer override."""
    if path is None:
        return PeerGrouping(
            peer_groups(orgs),
            "implementation",
            "snapshot manifests",
            frozenset(),
        )

    path = Path(path)
    try:
        with path.open(encoding="utf-8") as handle:
            pairs = json.load(handle, object_pairs_hook=lambda items: items)
    except FileNotFoundError as exc:
        raise PeerGroupArgumentError(f"peer-groups file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PeerGroupArgumentError(
            f"peer-groups file is not valid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(pairs, list):
        raise PeerGroupArgumentError(
            "peer-groups JSON must be an object mapping group names to org slug lists"
        )

    mapping = {}
    for group_name, slugs in pairs:
        if group_name in mapping:
            raise PeerGroupArgumentError(
                f"peer-groups JSON repeats group name {group_name!r}"
            )
        mapping[group_name] = slugs

    known = {org["slug"]: org for org in orgs}
    assigned = {}
    groups = {}
    for group_name, slugs in mapping.items():
        if not isinstance(group_name, str) or not group_name.strip():
            raise PeerGroupArgumentError("peer-group names must be non-empty strings")
        if not isinstance(slugs, list) or not slugs:
            raise PeerGroupArgumentError(
                f"peer group {group_name!r} must contain a non-empty list of org slugs"
            )
        peers = []
        for slug in slugs:
            if not isinstance(slug, str) or not slug:
                raise PeerGroupArgumentError(
                    f"peer group {group_name!r} contains a non-string org slug"
                )
            if slug not in known:
                raise PeerGroupArgumentError(f"unknown org slug in peer groups: {slug}")
            if slug in assigned:
                raise PeerGroupArgumentError(
                    f"org slug {slug} appears in more than one peer group: "
                    f"{assigned[slug]!r} and {group_name!r}"
                )
            assigned[slug] = group_name
            peers.append(known[slug])
        groups[group_name] = sorted(peers, key=org_sort_key)

    fallback = defaultdict(list)
    for org in orgs:
        if org["slug"] not in assigned:
            fallback[org["implementation_name"]].append(org)
    for implementation_name, peers in sorted(fallback.items()):
        label = implementation_name
        if label in groups:
            label = f"{implementation_name} (implementation fallback)"
        groups[label] = sorted(peers, key=org_sort_key)
    return PeerGrouping(
        dict(sorted(groups.items())),
        "customer-declared",
        path.name,
        frozenset(mapping),
    )


def peer_group_kind(grouping, group_name):
    if group_name in grouping.declared_group_names:
        return "customer-declared peer group"
    return "implementation peer group"


def partition_peer_groups(groups):
    """Return comparable groups and singleton orgs under the shared N>=2 rule."""
    comparable = {}
    without_peers = []
    for name, peers in groups.items():
        if len(peers) < PEER_COMPARISON_N_MIN:
            without_peers.extend(peers)
        else:
            comparable[name] = peers
    return comparable, sorted(without_peers, key=org_sort_key)


def grouping_in_use(grouping, as_of):
    """Render the actual grouping and membership used by a comparison."""
    if grouping.source == "implementation":
        explanation = "implementation grouping from snapshot manifests"
    else:
        explanation = (
            f"customer-declared peer groups from {escape_html(grouping.source_name)}; "
            "unmentioned orgs retain their implementation group"
        )
    items = []
    for name, orgs in grouping.groups.items():
        members = ", ".join(org_mention(org, as_of, org["slug"]) for org in orgs)
        items.append(
            f'<li><strong>{escape_html(name)}</strong> — {len(orgs)} '
            f'{"org" if len(orgs) == 1 else "orgs"}: {members}</li>'
        )
    return (
        '<section class="grouping-in-use"><h2>Grouping in use</h2>'
        f'<p>{explanation}.</p><ul>{"".join(items)}</ul></section>'
    )


BASE_CSS = """* { box-sizing:border-box; }
body { margin:0; background:var(--wash); color:var(--ink); font:14px/1.45 Arial, Helvetica, sans-serif; }
.page { max-width:1500px; margin:0 auto; padding:24px; }
.snapshot-header { position:sticky; top:0; z-index:5; margin:0 0 18px; padding:14px 18px; border:1px solid #b9c5e8; border-radius:10px; background:#eaf0ff; font-weight:700; white-space:nowrap; }
"""

TAB_CSS = """.tab-input { position:absolute; opacity:0; pointer-events:none; }
.tab-labels { display:flex; gap:8px; border-bottom:1px solid var(--line); }
.tab-labels label { padding:10px 18px; border:1px solid transparent; border-bottom:0; border-radius:8px 8px 0 0; cursor:pointer; font-weight:700; }
#tab-report:checked ~ .tab-labels label[for=tab-report], #tab-evidence:checked ~ .tab-labels label[for=tab-evidence] { background:var(--paper); border-color:var(--line); color:var(--blue); }
.panel { display:none; padding:24px 0; }
#tab-report:checked ~ .panels #report-panel, #tab-evidence:checked ~ .panels #evidence-panel { display:block; }
"""

SECTION_HEADING_CSS = ".section-heading { display:flex; align-items:baseline; justify-content:space-between; gap:16px; }\n"

CONTENT_CSS = """h2, h3, h4 { margin:0 0 10px; }
.table-wrap { overflow:auto; margin:12px 0 20px; }
table { width:100%; border-collapse:collapse; background:var(--paper); }
th, td { min-width:130px; padding:10px 12px; border:1px solid var(--line); text-align:left; vertical-align:top; }
thead th { background:#eef2f8; font:700 12px/1.3 monospace; }
.org-name, .omission, .omission span, .context, .slug { display:block; }
.org-name { font-weight:700; }
.context, .slug, .omission span { margin-top:3px; font-size:11px; }
.omission { color:var(--muted); }
"""

FLAG_CSS = ".flag { background:#fff0dc; color:var(--amber); border:1px solid #efc48d; }\n"

CURRENT_CSS = (
    ".current { background:#e9f7f3; color:#12655d; "
    "border:1px solid #a6d9d0; }\n"
)

SVG_TEXT_CSS = """.svg-org { fill:var(--ink); font:700 13px Arial, sans-serif; }
.svg-value { fill:var(--ink); font:12px monospace; }
"""

PROVENANCE_CSS = """.provenance { display:grid; grid-template-columns:max-content 1fr; gap:8px 18px; }
.provenance dt { font-weight:700; }
.provenance dd { margin:0; }
.generated { margin-top:24px; padding-top:16px; border-top:1px solid var(--line); font-weight:700; }
code { white-space:nowrap; }
"""


def tab_shell(tab_name, report, evidence):
    return (
        '<div class="tabs">\n'
        f'<input class="tab-input" type="radio" name="{tab_name}" id="tab-report" checked>\n'
        f'<input class="tab-input" type="radio" name="{tab_name}" id="tab-evidence">\n'
        '<div class="tab-labels" role="tablist"><label for="tab-report">Report</label><label for="tab-evidence">Evidence</label></div>\n'
        f'<div class="panels"><section class="panel" id="report-panel">{report}</section><section class="panel" id="evidence-panel">{evidence}</section></div>\n'
        "</div>"
    )


def provenance_shell(orgs, date, store_root, recipe_title, as_of=None):
    manifests = [org["manifest"] for org in orgs]

    def values(field):
        return ", ".join(
            sorted(
                {
                    escape_html(manifest.get(field, "not recorded"))
                    for manifest in manifests
                }
            )
        )

    slugs = ", ".join(
        org_mention(org, as_of, org["slug"])
        if as_of is not None
        else escape_html(org["slug"])
        for org in orgs
    )
    as_of_row = (
        ""
        if as_of is None
        else f"<dt>As-of instant</dt><dd>{escape_html(as_of)}</dd>"
    )
    return (
        '<h2>Provenance</h2><dl class="provenance">'
        f"<dt>Snapshot date</dt><dd>{escape_html(date)}</dd>"
        f"{as_of_row}"
        f'<dt>Orgs pulled</dt><dd>{len(orgs)} {"org" if len(orgs) == 1 else "orgs"} · {slugs}</dd>'
        f"<dt>Skill version</dt><dd>{values('skillVersion')}</dd>"
        f"<dt>MCP baseline version</dt><dd>{values('mcpBaselineVersion')}</dd>"
        f"<dt>Recipe name</dt><dd>{values('recipe')}</dd>"
        f"<dt>Store path</dt><dd><code>{escape_html(store_root)}</code></dd></dl>"
        f'<p class="generated">Generated by the {recipe_title} recipe · '
        "ask your assistant to customize or re-run it</p>"
    )


def _read_json(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Required raw file is missing: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in required raw file {path}: {exc}") from exc


def _required_field(data, field, path):
    try:
        return data[field]
    except KeyError as exc:
        raise ValueError(f"Required field {field!r} is missing from {path}") from exc


def _validated_instant_field(manifest, field, manifest_path, *, required):
    value = manifest.get(field)
    if value is None and not required:
        return None
    if value is None:
        raise ValueError(f"Required field {field!r} is missing from {manifest_path}")
    try:
        parsed = _parse_instant(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Manifest field {field} in {manifest_path} must be an ISO-8601 "
            "instant with trailing Z or an explicit offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"Manifest field {field} in {manifest_path} must be an ISO-8601 "
            "instant with trailing Z or an explicit offset"
        )
    return value


def _validate_manifest(manifest, manifest_path, date, org_directory_name):
    snapshot_date = _required_field(manifest, "snapshotDate", manifest_path)
    if snapshot_date != date:
        raise ValueError(
            f"Manifest snapshotDate {snapshot_date!r} does not match date directory "
            f"{date!r}: {manifest_path}"
        )
    org_slug = _required_field(manifest, "orgSlug", manifest_path)
    if org_slug != org_directory_name:
        raise ValueError(
            f"Manifest orgSlug {org_slug!r} does not match org directory name "
            f"{org_directory_name!r}: {manifest_path}"
        )
    _validated_instant_field(manifest, "syncTime", manifest_path, required=True)
    _validated_instant_field(manifest, "pulledAt", manifest_path, required=False)
    files = _required_field(manifest, "files", manifest_path)
    if not isinstance(files, dict):
        raise ValueError(f"Manifest files in {manifest_path} must be an object")
    ref_model_id = _required_field(manifest, "refModelId", manifest_path)
    for relative_path, entry in files.items():
        _validate_file_provenance_entry(
            relative_path, entry, ref_model_id, manifest_path
        )


def _expected_tool_for_file(relative_path):
    if relative_path.startswith("query_metadata/"):
        return "query_metadata"
    if relative_path == "types_present.json":
        return "list_metadata_columns"
    return Path(relative_path).name.removesuffix(".json")


def _validate_file_provenance_entry(
    relative_path, entry, ref_model_id, manifest_path
):
    if not isinstance(relative_path, str) or not isinstance(entry, dict):
        raise ValueError(
            f"manifest.files in {manifest_path} must map file paths to provenance objects"
        )
    tool = entry.get("tool")
    arguments = entry.get("arguments")
    if not isinstance(tool, str) or not tool.strip() or not isinstance(arguments, dict):
        raise ValueError(
            f"manifest.files entry for {relative_path} in {manifest_path} must "
            "name a tool and its arguments"
        )
    expected_tool = _expected_tool_for_file(relative_path)
    if tool != expected_tool:
        raise ValueError(
            f"manifest.files entry for {relative_path} in {manifest_path} names "
            f"tool {tool!r}; filename convention requires {expected_tool!r}"
        )
    actual_ref_model_id = arguments.get("refModelId")
    if actual_ref_model_id != ref_model_id:
        raise ValueError(
            f"manifest.files entry for {relative_path} in {manifest_path} has "
            f"arguments.refModelId {actual_ref_model_id!r}; manifest refModelId "
            f"is {ref_model_id!r}"
        )


def _require_file_provenance(manifest, relative_path, manifest_path):
    entry = manifest["files"].get(relative_path)
    if not isinstance(entry, dict):
        raise ValueError(
            f"manifest.files in {manifest_path} has no provenance entry for "
            f"{relative_path}"
        )
    _validate_file_provenance_entry(
        relative_path, entry, manifest["refModelId"], manifest_path
    )


def _type_slug(type_name):
    return re.sub(r"[^a-z0-9]+", "_", type_name.lower()).strip("_")


OUTLIER_N_MIN = 8
PEER_COMPARISON_N_MIN = 2


def type_metric_name(type_name):
    """Return the public tidy metric name for a curated metadata type."""
    return f"nodes_{_type_slug(type_name)}"


def coverage_denominator_metric(type_name):
    """Return the tidy metric name for a pulled coverage denominator."""
    return f"coverage_denominator_{_type_slug(type_name)}"


def _total_items(path):
    payload = _read_json(path)
    value = _required_field(payload, "totalItems", path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Required field 'totalItems' is not an integer in {path}")
    return value


def _optional_total_items(org_dir, manifest, relative_path, manifest_path):
    """Load a count dimension, returning None when its raw file is absent."""
    path = org_dir / relative_path
    if not path.is_file():
        return None
    _require_file_provenance(manifest, relative_path, manifest_path)
    return _total_items(path)


def types_present_from_payload(payload, path):
    """Return the org's type names from a presence-probe file.

    Accepts the verbatim ``list_metadata_columns(allNodes=true)`` response, whose
    ``type`` column carries ``options`` as ``{id, label}`` pairs, and the older
    ``{"types": [...]}`` extract. Both an option id and its label count as
    presence, because an id can differ from the supported-type name (for example
    id ``Field Update`` with label ``Workflow Field Update``).
    """
    if isinstance(payload, dict) and "types" in payload:
        return payload["types"]
    columns = _required_field(payload, "columns", path)
    type_column = next(
        (
            column
            for column in columns
            if isinstance(column, dict) and column.get("value") == "type"
        ),
        None,
    )
    if type_column is None or not isinstance(type_column.get("options"), list):
        raise ValueError(
            f"No 'type' column with options in the list_metadata_columns response {path}"
        )
    names = []
    for option in type_column["options"]:
        for key in ("id", "label"):
            name = option.get(key) if isinstance(option, dict) else None
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names


def load_discovery(store_root, date):
    """Read the per-date discovery record and its confirmedOrgs selection."""
    path = Path(store_root) / "raw" / date / "list_reference_models.json"
    if not path.is_file():
        return Discovery(False, None, {}, {})
    payload = _read_json(path)
    entries = payload.get("referenceModels", payload.get("items", []))
    models_by_id = {
        entry["refModelId"]: entry
        for entry in entries
        if isinstance(entry, dict) and "refModelId" in entry
    }
    confirmed = payload.get("confirmedOrgs")
    if confirmed is None:
        return Discovery(True, None, models_by_id, {})
    if not isinstance(confirmed, list) or any(
        not isinstance(ref_model_id, str) for ref_model_id in confirmed
    ):
        raise ValueError(f"confirmedOrgs must be a list of refModelId strings in {path}")
    slugs = build_confirmed_org_slugs(
        [
            model
            for model in models_by_id.values()
            if isinstance(model.get("implementation"), dict)
            and "name" in model["implementation"]
            and "name" in model
        ],
        confirmed,
    )
    return Discovery(True, list(confirmed), models_by_id, slugs)


def unpulled_confirmed_orgs(store_root, date, orgs):
    """Return confirmed orgs with no loaded manifest, each with a visible reason."""
    discovery = load_discovery(store_root, date)
    if discovery.confirmed is None:
        return []
    date_dir = Path(store_root) / "raw" / date
    pulled_ids = {org["ref_model_id"] for org in orgs}
    result = []
    for ref_model_id in discovery.confirmed:
        if ref_model_id in pulled_ids:
            continue
        model = discovery.models_by_id.get(ref_model_id, {})
        slug = discovery.slugs_by_ref_model_id.get(ref_model_id)
        if slug is None:
            reason = "confirmed refModelId is absent from the discovery record's entries"
        elif (date_dir / slug).is_dir():
            other_ref_model_id = _manifest_ref_model_id(date_dir / slug)
            if other_ref_model_id is not None and other_ref_model_id != ref_model_id:
                reason = (
                    f"org directory {slug} holds the manifest of refModelId "
                    f"{other_ref_model_id}"
                )
            else:
                reason = "pull incomplete: manifest.json not written"
        else:
            reason = "no org directory written"
        implementation = model.get("implementation")
        result.append(
            {
                "ref_model_id": ref_model_id,
                "slug": slug or ref_model_id,
                "org_name": model.get("name", "name not recorded"),
                "implementation_name": (
                    implementation.get("name", "not recorded")
                    if isinstance(implementation, dict)
                    else "not recorded"
                ),
                "reason": reason,
            }
        )
    return result


def confirmed_orgs_pulled_sentence(count):
    """Evidence sentence for a snapshot in which every confirmed org was pulled."""
    if count == 1:
        return "All 1 confirmed org was pulled."
    return f"All {count} confirmed orgs were pulled."


def _manifest_ref_model_id(org_dir):
    """The refModelId a directory's manifest names, or None when it names none.

    None covers a missing, unreadable or malformed manifest, and a manifest with
    no string refModelId.
    """
    manifest_path = org_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    ref_model_id = manifest.get("refModelId")
    return ref_model_id if isinstance(ref_model_id, str) else None


def _org_dir_in_scope(org_dir, discovery):
    """True when an org directory belongs to the confirmed selection.

    With no confirmedOrgs list every directory is in scope. With one, a directory
    whose manifest names a refModelId is in scope exactly when that refModelId is
    confirmed; its name plays no part. A directory without a manifest, or whose
    manifest names no refModelId, is in scope when its name is a confirmed slug,
    so an incomplete pull is reported and a malformed manifest fails by name.
    """
    if discovery.confirmed is None:
        return True
    ref_model_id = _manifest_ref_model_id(org_dir)
    if ref_model_id is not None:
        return ref_model_id in discovery.confirmed
    return org_dir.name in discovery.slugs_by_ref_model_id.values()


def out_of_scope_org_dirs(store_root, date):
    """Name the org directories left out because they are outside confirmedOrgs."""
    date_dir = Path(store_root) / "raw" / date
    if not date_dir.is_dir():
        return []
    discovery = load_discovery(store_root, date)
    return [
        org_dir.name
        for org_dir in sorted(path for path in date_dir.iterdir() if path.is_dir())
        if not _org_dir_in_scope(org_dir, discovery)
    ]


def load_snapshot(store_root, date):
    """Load all org records for a dated raw snapshot without altering the store."""
    date_dir = Path(store_root) / "raw" / date
    if not date_dir.is_dir():
        raise FileNotFoundError(f"Required raw snapshot directory is missing: {date_dir}")

    supported_types_path = date_dir / "list_supported_metadata_types.json"
    if supported_types_path.is_file():
        supported_types_payload = _read_json(supported_types_path)
        supported_type_entries = _required_field(
            supported_types_payload, "types", supported_types_path
        )
        supported_types = {
            _required_field(entry, "single", supported_types_path)
            for entry in supported_type_entries
        }
    else:
        supported_types = None

    discovery = load_discovery(store_root, date)
    confirmed_slugs = set(discovery.slugs_by_ref_model_id.values())
    orgs = []
    for org_dir in sorted(path for path in date_dir.iterdir() if path.is_dir()):
        if not _org_dir_in_scope(org_dir, discovery):
            # Outside the confirmed selection; out_of_scope_org_dirs names it
            # on the Evidence tab.
            continue
        manifest_path = org_dir / "manifest.json"
        if not manifest_path.is_file() and org_dir.name in confirmed_slugs:
            # A confirmed org whose pull stopped before its manifest was written;
            # unpulled_confirmed_orgs reports it in place.
            continue
        manifest = _read_json(manifest_path)
        _validate_manifest(manifest, manifest_path, date, org_dir.name)
        total_nodes = _optional_total_items(
            org_dir,
            manifest,
            "query_metadata/manifest__all_nodes.json",
            manifest_path,
        )
        managed_nodes = _optional_total_items(
            org_dir,
            manifest,
            "query_metadata/manifest__all_nodes__managed.json",
            manifest_path,
        )

        curated_types = _required_field(manifest, "curatedTypes", manifest_path)

        type_counts = {}
        for type_name in curated_types:
            relative_path = f"query_metadata/manifest__type__{_type_slug(type_name)}.json"
            type_counts[type_name] = _optional_total_items(
                org_dir, manifest, relative_path, manifest_path
            )

        denominator_counts = {}
        for type_name in manifest.get("denominatorTypes", []):
            relative_path = f"query_metadata/manifest__type__{_type_slug(type_name)}.json"
            denominator_counts[type_name] = _optional_total_items(
                org_dir, manifest, relative_path, manifest_path
            )

        types_path = org_dir / "types_present.json"
        if types_path.is_file():
            _require_file_provenance(manifest, "types_present.json", manifest_path)
            types_present = types_present_from_payload(_read_json(types_path), types_path)
        else:
            types_present = None

        ref_model_id = _required_field(manifest, "refModelId", manifest_path)
        slug = _required_field(manifest, "orgSlug", manifest_path)
        orgs.append(
            {
                "slug": slug,
                "org_name": _required_field(manifest, "orgName", manifest_path),
                "implementation_name": _required_field(
                    manifest, "implementationName", manifest_path
                ),
                "ref_model_id": ref_model_id,
                "sync_status": _required_field(manifest, "syncStatus", manifest_path),
                "sync_time": _required_field(manifest, "syncTime", manifest_path),
                "total_nodes": total_nodes,
                "managed_nodes": managed_nodes,
                "custom_nodes": (
                    total_nodes - managed_nodes
                    if total_nodes is not None and managed_nodes is not None
                    else None
                ),
                "type_counts": type_counts,
                "denominator_counts": denominator_counts,
                "types_present": types_present,
                "supported_types": supported_types,
                "manifest": manifest,
                "snapshot_date": date,
            }
        )
    return orgs


def load_tech_debt(org_dir):
    """Load and normalize one org's technical-debt summary."""
    org_dir = Path(org_dir)
    manifest_path = org_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    _validate_manifest(manifest, manifest_path, org_dir.parent.name, org_dir.name)
    path = org_dir / "get_tech_debt_summary.json"
    if not path.is_file():
        return None
    _require_file_provenance(manifest, "get_tech_debt_summary.json", manifest_path)
    payload = _read_json(path)
    severity = _required_field(payload, "techDebtSeverity", path)
    inactive = _required_field(payload, "inactiveMetadata", path)
    api_table = _required_field(payload, "outdatedAPIVersions", path)
    coverage_entries = _required_field(payload, "descriptionCoverage", path)

    if not isinstance(severity, dict):
        raise ValueError(f"Required field 'techDebtSeverity' is not an object in {path}")
    if not isinstance(inactive, dict):
        raise ValueError(f"Required field 'inactiveMetadata' is not an object in {path}")
    if not isinstance(api_table, list):
        raise ValueError(f"Required field 'outdatedAPIVersions' is not an array in {path}")
    if not isinstance(coverage_entries, list):
        raise ValueError(f"Required field 'descriptionCoverage' is not an array in {path}")

    def require_integer(value, field):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field} value {value!r} is not an integer in {path}")

    for name, value in severity.items():
        require_integer(value, f"techDebtSeverity.{name}")
    for name, value in inactive.items():
        require_integer(value, f"inactiveMetadata.{name}")

    if api_table:
        if not isinstance(api_table[0], list) or any(
            not isinstance(column, str) for column in api_table[0]
        ):
            raise ValueError(
                f"outdatedAPIVersions header must be an array of strings in {path}"
            )
        expected_width = len(api_table[0])
        for row_index, row in enumerate(api_table[1:], start=1):
            if not isinstance(row, list) or len(row) != expected_width:
                raise ValueError(
                    f"outdatedAPIVersions row {row_index} must contain "
                    f"{expected_width} cells in {path}"
                )
            for column_index, value in enumerate(row):
                require_integer(
                    value,
                    f"outdatedAPIVersions[{row_index}][{column_index}]",
                )

    header = api_table[0] if api_table else []
    return {
        "tech_debt_severity": dict(severity),
        "inactive_metadata": dict(inactive),
        "outdated_api_header": list(header),
        "outdated_api_versions": [list(row) for row in api_table[1:]],
        "description_coverage": {
            _required_field(entry, "key", path): _required_field(entry, "value", path)
            for entry in coverage_entries
        },
    }


def unavailable_coverage_ratios(reason):
    """Return the canonical coverage dimensions blanked with one visible reason."""
    return {
        area: CoverageRatio(
            f"description_coverage_{_type_slug(area)}_pct",
            area,
            metadata_type,
            None,
            None,
            reason,
        )
        for area, metadata_type in DESCRIPTION_COVERAGE_TYPES.items()
    }


def coverage_ratios(tech_debt, org):
    """Resolve documentation coverage only against observed non-zero counts."""
    ratios = {}
    available_counts = {
        **org.get("denominator_counts", {}),
        **org["type_counts"],
    }
    supported_types = org.get("supported_types")
    if supported_types is not None:
        supported_types = set(supported_types)
        supported_types.update(org.get("denominator_counts", {}))
    for area, value in tech_debt["description_coverage"].items():
        metadata_type = DESCRIPTION_COVERAGE_TYPES.get(area)
        metric_name = f"description_coverage_{_type_slug(area)}_pct"
        denominator = available_counts.get(metadata_type)
        reason = None

        if metadata_type is None:
            reason = "unmapped coverage area"
        elif metadata_type not in available_counts:
            reason = "denominator not pulled"
        else:
            state = classify_type_count(
                metadata_type,
                denominator,
                org.get("types_present"),
                supported_types,
            ).state
            if state != "observed":
                reason = {
                    "not_pulled": "denominator raw file absent; dimension unavailable",
                    "absent": "type not present in org",
                    "not_synced": "type not synced by Elements",
                    "unknown": (
                        "list_supported_metadata_types.json absent; licensing classification unavailable"
                        if supported_types is None
                        else "type presence unknown"
                    ),
                }[state]
            elif denominator == 0:
                reason = "denominator is zero"

        ratios[area] = CoverageRatio(
            metric_name,
            area,
            metadata_type or "",
            value if reason is None else None,
            denominator,
            reason,
        )
    return ratios


def _parse_instant(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError("instant must be a string or datetime")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def resolve_as_of(orgs, date, requested=None):
    """Resolve a deterministic as-of instant and disclose manifest timing gaps."""
    pulled_at = [
        org["manifest"].get("pulledAt")
        for org in orgs
        if org["manifest"].get("pulledAt")
    ]
    missing_count = len(orgs) - len(pulled_at)
    if requested is not None:
        instant = requested
    elif pulled_at:
        instant = max(pulled_at, key=_parse_instant)
    else:
        instant = f"{date}T23:59:59Z"

    notices = []
    if not pulled_at:
        notices.append(
            "No manifests record pulledAt; "
            f"using snapshot-date end {instant} for a deterministic as-of."
        )
    elif missing_count:
        notices.append(
            "Some manifests lack pulledAt; "
            f"the latest recorded instant is {max(pulled_at, key=_parse_instant)}."
        )
    else:
        notices.append("All manifests record pulledAt.")

    distinct_instants = {_parse_instant(value) for value in pulled_at}
    if len(distinct_instants) > 1:
        notices.append(
            "Distinct pulledAt values were recorded; "
            f"the latest is {max(pulled_at, key=_parse_instant)}."
        )
    return AsOfResolution(instant, " ".join(notices))


def staleness_days(sync_time, as_of):
    """Return the number of complete elapsed days since an ISO-8601 sync instant."""
    return (_parse_instant(as_of) - _parse_instant(sync_time)).days


def freshness(org, as_of):
    elapsed = staleness_days(org["sync_time"], as_of)
    if elapsed < 0:
        return None, False
    stale = elapsed > STALE_AFTER_DAYS
    return elapsed, stale


def sync_failing(org):
    """Return the independent latest-sync-attempt failure signal."""
    return org["sync_status"] == "failed"


def sync_running(org):
    """Return True when a sync was in progress while the snapshot was pulled."""
    return org["sync_status"] == "inProgress"


def classify_type_count(type_name, count, types_present, supported_types):
    """Classify whether a curated type count is observed or should be omitted."""
    if count is None:
        return TypeCountState("not_pulled")
    if count > 0:
        return TypeCountState("observed")
    if supported_types is None:
        return TypeCountState("unknown")
    if type_name not in supported_types:
        return TypeCountState("not_synced")
    if types_present is not None:
        if type_name not in types_present:
            return TypeCountState("absent")
        return TypeCountState("observed")
    return TypeCountState("unknown")


def type_count_contradiction_evidence(orgs, as_of):
    """Name positive counts that contradict the global supported-types list."""
    items = []
    for org in sorted(orgs, key=org_sort_key):
        supported = org.get("supported_types", set())
        if supported is None:
            continue
        observed_counts = {
            type_name: (count, type_metric_name(type_name))
            for type_name, count in org["type_counts"].items()
        }
        for type_name, count in org.get("denominator_counts", {}).items():
            observed_counts.setdefault(
                type_name,
                (count, coverage_denominator_metric(type_name)),
            )
        for type_name, (count, metric) in sorted(observed_counts.items()):
            if count is None or count <= 0 or type_name in supported:
                continue
            items.append(
                f'<li>{org_mention(org, as_of)} · <code>query_metadata</code> reports '
                f'{escape_html(type_name)} as <code>{escape_html(metric)}</code> '
                f'with positive count {format_number(count)}, but '
                "<code>list_supported_metadata_types</code> omits it; the count is "
                "retained and the discovery contradiction remains a known unknown.</li>"
            )
    if not items:
        return ""
    return '<h3>Snapshot contradictions</h3><ul>' + "".join(items) + "</ul>"


def normalize_tiers(org):
    """Return an org record with within-org managed and custom percentages."""
    normalized = dict(org)
    total = org["total_nodes"]
    if total is None or org["managed_nodes"] is None or org["custom_nodes"] is None:
        normalized["managed_share_pct"] = None
        normalized["custom_share_pct"] = None
        return normalized
    if total == 0:
        normalized["managed_share_pct"] = None
        normalized["custom_share_pct"] = None
    else:
        normalized["managed_share_pct"] = org["managed_nodes"] / total * 100
        normalized["custom_share_pct"] = org["custom_nodes"] / total * 100
    return normalized


def median(values):
    """Return the median of values, or None for an empty iterable."""
    ordered = sorted(values)
    size = len(ordered)
    if size == 0:
        return None
    midpoint = size // 2
    if size % 2:
        return ordered[midpoint]
    lower = ordered[midpoint - 1]
    upper = ordered[midpoint]
    if isinstance(lower, int) and isinstance(upper, int):
        total = lower + upper
        if total % 2 == 0:
            return total // 2
        if abs(total).bit_length() > 1023:
            return Decimal(total) / 2
    return (lower + upper) / 2


def mad(values):
    """Return the unscaled median absolute deviation, or None when empty."""
    values = list(values)
    baseline = median(values)
    if baseline is None:
        return None
    return median([abs(value - baseline) for value in values])


def outlier_verdict(values, n_min=OUTLIER_N_MIN):
    """Choose robust outliers only when there are enough peer observations."""
    values = list(values)
    baseline = median(values)
    uniform = bool(values) and len(set(values)) == 1
    if len(values) < n_min:
        spread = max(values) - min(values) if values else None
        return OutlierVerdict(
            "extremes_and_spread", baseline, spread, (), uniform, False
        )

    spread = mad(values)
    if spread == 0:
        return OutlierVerdict("median_mad", baseline, spread, (), uniform, True)
    indices = tuple(
        index
        for index, value in enumerate(values)
        if abs(value - baseline) > 3 * spread
    )
    return OutlierVerdict("median_mad", baseline, spread, indices, uniform, False)


def metrics_rows(orgs, date):
    """Return tidy rows for per-org values read from raw snapshot files."""
    rows = []
    for org in orgs:
        if "org_name" in org:
            rows.append((date, org["slug"], "org_name", org["org_name"]))
        rows.append((date, org["slug"], "org_slug", org["slug"]))
        if "implementation_name" in org:
            rows.append(
                (
                    date,
                    org["slug"],
                    "implementation_name",
                    org["implementation_name"],
                )
            )
        if "sync_time" in org:
            rows.append((date, org["slug"], "sync_time", org["sync_time"]))
        for metric in ("total_nodes", "managed_nodes"):
            value = org[metric]
            if value is not None:
                rows.append((date, org["slug"], metric, value))

        supported_types = org.get("supported_types", set(org["type_counts"]))
        for type_name, count in org["type_counts"].items():
            state = classify_type_count(
                type_name, count, org.get("types_present"), supported_types
            )
            if state.state == "observed":
                rows.append((date, org["slug"], type_metric_name(type_name), count))

        for type_name, count in org.get("denominator_counts", {}).items():
            state = classify_type_count(
                type_name, count, org.get("types_present"), supported_types
            )
            if state.state == "observed":
                rows.append(
                    (date, org["slug"], coverage_denominator_metric(type_name), count)
                )
    return rows


def all_metrics_rows(orgs, date):
    """Return this date's raw per-org observation rows."""
    return sorted(metrics_rows(orgs, date), key=lambda row: (row[0], row[1], row[2]))


def trend_observations(store_root, current_date):
    """Return raw-derived trend points, empty dates, and pre-window stale orgs."""
    snapshots = [
        (date, orgs)
        for date, orgs in load_store_snapshots(store_root, current_date)[0]
        if date <= current_date
    ]
    if len(snapshots) < 2:
        return [], [], []

    first_orgs = next((orgs for _, orgs in snapshots if orgs), [])
    pulled_at = {
        org["manifest"].get("pulledAt")
        for org in first_orgs
        if org["manifest"].get("pulledAt")
    }
    first_date = next((date for date, orgs in snapshots if orgs), current_date)
    window_as_of = (
        max(pulled_at, key=_parse_instant)
        if pulled_at
        else f"{first_date}T23:59:59Z"
    )
    points = []
    empty_dates = []
    excluded_by_slug = {}
    for date, orgs in snapshots:
        if not orgs:
            empty_dates.append((date, "no org observations were pulled"))
            continue
        missing_dimensions = [
            org["slug"]
            for org in orgs
            if org["total_nodes"] is None or org["custom_nodes"] is None
        ]
        if missing_dimensions:
            empty_dates.append(
                (
                    date,
                    "trend count dimension unavailable for: "
                    + ", ".join(sorted(missing_dimensions)),
                )
            )
            continue
        eligible = []
        for org in orgs:
            already_stale = (
                staleness_days(org["sync_time"], window_as_of) > STALE_AFTER_DAYS
            )
            if already_stale:
                excluded_by_slug.setdefault(org["slug"], org)
            else:
                eligible.append(org)
        if not eligible:
            empty_dates.append((date, "no trend-eligible org observations remain"))
            continue
        total = sum(org["total_nodes"] for org in eligible)
        custom = sum(org["custom_nodes"] for org in eligible)
        share = custom / total * 100 if total else None
        points.append((date, eligible, total, custom, share))
    excluded = sorted(excluded_by_slug.values(), key=org_sort_key)
    return points, empty_dates, excluded


def all_store_metrics_rows(store_root, trend_end_date=None):
    """Return raw per-org observations from every usable dated snapshot."""
    store_root = Path(store_root)
    snapshots, _ = load_store_snapshots(store_root, trend_end_date)
    rows = []
    for date, orgs in snapshots:
        rows.extend(all_metrics_rows(orgs, date))
    return sorted(rows, key=lambda row: (row[0], row[1], row[2]))


def load_store_snapshots(store_root, current_date=None):
    """Load usable dated directories, skipping broken non-current snapshots."""
    raw_dir = Path(store_root) / "raw"
    if not raw_dir.is_dir():
        return [], []
    shaped_dates = sorted(
        path.name
        for path in raw_dir.iterdir()
        if path.is_dir() and DATE_PATTERN.fullmatch(path.name)
    )
    snapshots = []
    unusable = []
    for date in shaped_dates:
        if not is_calendar_date(date):
            unusable.append(
                (
                    date,
                    "calendar-invalid directory name; ignored during store discovery",
                )
            )
            continue
        try:
            orgs = load_snapshot(store_root, date)
            snapshots.append((date, orgs))
        except (OSError, TypeError, ValueError) as exc:
            if date == current_date:
                raise
            unusable.append((date, str(exc)))
    return snapshots, unusable


def unusable_snapshot_evidence(store_root, current_date):
    unusable = load_store_snapshots(store_root, current_date)[1]
    if not unusable:
        return ""
    items = "".join(
        f"<li><code>{escape_html(date)}</code> — unusable for derived metrics and "
        f"trends: {escape_html(reason)}</li>"
        for date, reason in unusable
    )
    return f"<h2>Unusable snapshot dates</h2><ul>{items}</ul>"


def write_metrics_csv(rows, path):
    """Write tidy metric rows with the public contract header."""
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date", "org", "metric", "value"))
        writer.writerows(rows)
