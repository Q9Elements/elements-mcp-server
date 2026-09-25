#!/usr/bin/env python3
"""Render a self-contained Elements Multi-Org Overview from raw snapshots.

The renderer regenerates ``<store>/derived/metrics.csv`` from raw per-org
observations, then writes an offline HTML report with inline CSS and SVG.

Usage:
  render_multi_org_overview.py --snapshots STORE --date YYYY-MM-DD --out FILE.html
                               [--as-of ISO-INSTANT] [--peer-groups FILE.json]
"""

import sys
from pathlib import Path

from helpers import (
    BASE_CSS,
    CONTENT_CSS,
    CURRENT_CSS,
    FLAG_CSS,
    PROVENANCE_CSS,
    SECTION_HEADING_CSS,
    SVG_TEXT_CSS,
    TAB_CSS,
    PeerGroupArgumentError,
    all_store_metrics_rows,
    build_cli_parser,
    classify_type_count,
    confirmed_orgs_pulled_sentence,
    coverage_denominator_metric,
    escape_html,
    format_number,
    format_percent,
    freshness,
    grouping_in_use,
    implementation_mention,
    load_discovery,
    load_snapshot,
    load_store_snapshots,
    normalize_tiers,
    org_mention,
    org_sort_key,
    out_of_scope_org_dirs,
    partition_peer_groups,
    peer_group_kind,
    provenance_shell,
    resolve_as_of,
    resolve_peer_groups,
    sync_failing,
    sync_running,
    sync_time_value,
    tab_shell,
    trend_observations,
    type_count_contradiction_evidence,
    type_metric_name,
    unpulled_confirmed_orgs,
    unusable_snapshot_evidence,
    write_metrics_csv,
)


def trend_snapshot_dates(store_root, current_date):
    """Return sorted dates for trends, or no dates until two snapshots exist."""
    dates = [
        date
        for date, orgs in load_store_snapshots(store_root, current_date)[0]
        if date <= current_date and orgs
    ]
    return dates if len(dates) >= 2 else []


def _display(value, unit=None):
    if unit == "percent":
        return format_percent(value)
    if isinstance(value, (int, float)):
        return format_number(value)
    return escape_html(value)


def _blank(reason):
    """Render an absent value with its reader-facing reason in place."""
    return f'<span class="omission">—<span>{escape_html(reason)}</span></span>'


def _input_orgs(orgs, as_of):
    return ", ".join(org_mention(org, as_of, org["slug"]) for org in orgs)


def _plain_org_input(org, as_of):
    """Name an org in text-only surfaces while retaining freshness signals."""
    signals = []
    if freshness(org, as_of)[1]:
        signals.append("stale")
    if sync_failing(org):
        signals.append("sync failing")
    suffix = f" ({', '.join(signals)})" if signals else ""
    return org["slug"] + suffix


def _context_line(org, as_of):
    normalized = normalize_tiers(org)
    total = org["total_nodes"]
    if total is None:
        total_text = _blank("raw count file absent; dimension unavailable")
    else:
        total_text = _display(total)
    share = normalized["custom_share_pct"]
    if share is None:
        reason = (
            "normalization input unavailable"
            if total is None or org["managed_nodes"] is None
            else "total_nodes denominator is zero"
        )
        share_text = _blank(reason)
    else:
        share_text = _display(share, "percent")
    return (
        f"of {total_text} total_nodes · {share_text} custom_share_pct "
        f"(custom_nodes / total_nodes for {org_mention(org, as_of, org['slug'])})"
    )


def _count_cell(value, org, metric, as_of):
    if value is None:
        return _blank("raw count file absent; dimension unavailable")
    context = _context_line(org, as_of)
    if metric == "custom_nodes":
        context = (
            "derived from total_nodes − managed_nodes for "
            f"{org_mention(org, as_of, org['slug'])} · {context}"
        )
    return f'{_display(value)}<span class="context">{context}</span>'


def _type_cell(type_name, org, as_of):
    count = org["type_counts"].get(type_name)
    state = classify_type_count(
        type_name,
        count,
        org.get("types_present"),
        org.get("supported_types", set(org["type_counts"])),
    ).state
    if state == "observed":
        return _count_cell(count, org, type_metric_name(type_name), as_of)
    reasons = {
        "not_pulled": "not pulled for this org",
        "absent": "not present in this org",
        "not_synced": "not synced by Elements",
        "unknown": (
            "list_supported_metadata_types.json absent; licensing classification unavailable"
            if org.get("supported_types") is None
            else "presence not probed"
        ),
    }
    return _blank(reasons[state])


def _curated_types(orgs):
    seen = set()
    result = []
    for org in orgs:
        for type_name in org["type_counts"]:
            if type_name not in seen:
                seen.add(type_name)
                result.append(type_name)
    return result


def _share_cell(org, numerator_metric, as_of):
    normalized = normalize_tiers(org)
    metric = f"{numerator_metric.removesuffix('_nodes')}_share_pct"
    value = normalized[metric]
    if value is None:
        reason = (
            "normalization input unavailable"
            if org["total_nodes"] is None or org["managed_nodes"] is None
            else "total_nodes denominator is zero"
        )
        return _blank(reason)
    return (
        f'{_display(value, "percent")}<span class="context">derived from '
        f"{numerator_metric} / total_nodes for "
        f"{org_mention(org, as_of, org['slug'])}</span>"
    )


def _org_table(orgs, curated_types, as_of):
    headers = "".join(
        f"<th>{escape_html(type_metric_name(name))}</th>" for name in curated_types
    )
    body = []
    for org in sorted(orgs, key=org_sort_key):
        elapsed, stale = freshness(org, as_of)
        failing = sync_failing(org)
        running = sync_running(org)
        status_class = (
            "flag" if stale or failing or running or elapsed is None else "current"
        )
        if elapsed is None:
            status_text = "sync_time is after the as-of instant"
        else:
            signals = []
            if stale:
                signals.append("stale")
            if failing:
                signals.append("sync failing")
            if running:
                signals.append("sync running")
            signal_text = " · ".join(signals) if signals else "current"
            status_text = (
                f"{escape_html(org['sync_status'])} · {signal_text} · "
                f"{elapsed} elapsed days from sync_time to as-of"
            )
        type_cells = "".join(
            f"<td>{_type_cell(type_name, org, as_of)}</td>"
            for type_name in curated_types
        )
        body.append(
            "<tr>"
            f'<th scope="row"><span class="org-name">{org_mention(org, as_of)}</span>'
            f'<span class="slug">{org_mention(org, as_of, org["slug"])}</span></th>'
            f'<td><span class="{status_class}">{status_text}</span></td>'
            f"<td>{_count_cell(org['total_nodes'], org, 'total_nodes', as_of)}</td>"
            f"<td>{_count_cell(org['managed_nodes'], org, 'managed_nodes', as_of)}</td>"
            f"<td>{_count_cell(org['custom_nodes'], org, 'custom_nodes', as_of)}</td>"
            f"<td>{_share_cell(org, 'managed_nodes', as_of)}</td>"
            f"<td>{_share_cell(org, 'custom_nodes', as_of)}</td>"
            f"{type_cells}</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>org_name / org_slug</th><th>Freshness</th><th>total_nodes</th>"
        "<th>managed_nodes</th><th>custom_nodes</th><th>managed_share_pct</th>"
        f"<th>custom_share_pct</th>{headers}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def _bar_chart(orgs, as_of):
    ordered = sorted(
        (
            org
            for org in orgs
            if org["total_nodes"] is not None
            and org["managed_nodes"] is not None
            and org["custom_nodes"] is not None
        ),
        key=org_sort_key,
    )
    unavailable = [org for org in orgs if org not in ordered]
    omission_notice = ""
    if unavailable:
        omission_notice = (
            '<p class="omissions">Chart dimension unavailable: raw total or '
            "managed count file absent for "
            f"{_input_orgs(unavailable, as_of)}.</p>"
        )
    if not ordered:
        return omission_notice
    width, left, plot_width, row_height = 960, 210, 500, 86
    height = 44 + row_height * len(ordered)
    maximum = max((org["total_nodes"] for org in ordered), default=1) or 1
    rows = []
    for index, org in enumerate(ordered):
        normalized = normalize_tiers(org)
        y = 38 + index * row_height
        custom_width = org["custom_nodes"] / maximum * plot_width
        managed_width = org["managed_nodes"] / maximum * plot_width
        title_org = escape_html(_plain_org_input(org, as_of))
        rows.append(
            f'<text x="8" y="{y + 17}" class="svg-org">{org_mention(org, as_of, svg=True)}</text>'
            f'<rect x="{left}" y="{y}" width="{custom_width:.2f}" height="20" rx="3" class="bar-custom"><title>custom_nodes from total_nodes − managed_nodes for {title_org}</title></rect>'
            f'<text x="{left + custom_width + 7:.2f}" y="{y + 15}" class="svg-value">custom_nodes {_display(org["custom_nodes"])} from total_nodes − managed_nodes</text>'
            f'<rect x="{left}" y="{y + 27}" width="{managed_width:.2f}" height="20" rx="3" class="bar-managed"><title>managed_nodes observation for {title_org}</title></rect>'
            f'<text x="{left + managed_width + 7:.2f}" y="{y + 42}" class="svg-value">managed_nodes {_display(org["managed_nodes"])}</text>'
            f'<text x="{left}" y="{y + 64}" class="svg-context">total_nodes {_display(org["total_nodes"])} · custom_share_pct {_display(normalized["custom_share_pct"], "percent") if normalized["custom_share_pct"] is not None else "not observed"} from custom_nodes / total_nodes</text>'
        )
    return (
        f'<svg class="bar-chart" viewBox="0 0 {width} {height}" role="img" '
        'aria-label="custom_nodes and managed_nodes peer chart">'
        f"{''.join(rows)}</svg>{omission_notice}"
    )


def _peer_group_sections(grouping, curated_types, as_of):
    sections = []
    comparable_groups, no_peer_orgs = partition_peer_groups(grouping.groups)
    if no_peer_orgs:
        sections.append(
            '<section class="peer-group no-peers"><h3>Organizations without peers</h3>'
            '<p>These organizations have no peers in their group and are shown once, '
            "without a comparison chart.</p>"
            f"{_org_table(no_peer_orgs, curated_types, as_of)}</section>"
        )
    for implementation_name, peers in comparable_groups.items():
        members = _input_orgs(peers, as_of)
        sections.append(
            '<section class="peer-group"><div class="section-heading">'
            f"<h3>{escape_html(implementation_name)}</h3>"
            f'<span>{len(peers)} {"org" if len(peers) == 1 else "orgs"}: {members} · '
            f"{peer_group_kind(grouping, implementation_name)}</span></div>"
            f"{_org_table(peers, curated_types, as_of)}"
            '<div class="chart-card"><h4>custom_nodes and managed_nodes</h4>'
            '<p>Each derived custom_nodes label names total_nodes and managed_nodes; '
            "shares name their numerator and denominator.</p>"
            f"{_bar_chart(peers, as_of)}</div></section>"
        )
    return "".join(sections)


def _headline_tiles(orgs, as_of):
    count = len(orgs)
    complete = all(
        org["total_nodes"] is not None and org["custom_nodes"] is not None
        for org in orgs
    )
    total = sum(org["total_nodes"] for org in orgs) if complete else None
    custom = sum(org["custom_nodes"] for org in orgs) if complete else None
    share = custom / total * 100 if complete and total else None
    missing = ", ".join(
        _plain_org_input(org, as_of)
        for org in orgs
        if org["total_nodes"] is None or org["custom_nodes"] is None
    )
    reason = f"raw count dimension unavailable for: {missing}"
    sources = _input_orgs(orgs, as_of)
    org_word = "org" if count == 1 else "orgs"
    evidence_suffix = (
        f": {sources}" if count <= 3 else " — listed in Evidence"
    )
    total_text = _display(total) if total is not None else _blank(reason)
    custom_text = _display(custom) if custom is not None else _blank(reason)
    share_text = (
        _display(share, "percent")
        if share is not None
        else _blank(reason if not complete else "total_nodes denominator is zero")
    )
    return (
        '<div class="tiles">'
        f'<article class="tile"><span>org_count</span> <strong>{count}</strong> <small>count of {count} {org_word}{evidence_suffix}</small></article>'
        f'<article class="tile"><span>total_nodes</span> <strong>{total_text}</strong> <small>sum of total_nodes across {count} {org_word}{evidence_suffix}</small></article>'
        f'<article class="tile"><span>custom_nodes</span> <strong>{custom_text}</strong> <small>sum of custom_nodes (total_nodes − managed_nodes) across {count} {org_word}{evidence_suffix} · of {total_text} total_nodes · {share_text} custom_share_pct</small></article>'
        "</div>"
    )


def _aggregate_inputs(orgs, as_of):
    inputs = (
        ("org_count", orgs, "count"),
        (
            "total_nodes",
            [org for org in orgs if org["total_nodes"] is not None],
            "sum",
        ),
        (
            "custom_nodes",
            [org for org in orgs if org["custom_nodes"] is not None],
            "sum of per-org total_nodes − managed_nodes",
        ),
    )
    items = []
    for metric, contributors, derivation in inputs:
        count = len(contributors)
        org_word = "org" if count == 1 else "orgs"
        names = _input_orgs(contributors, as_of) if contributors else "none"
        items.append(
            f"<li><code>{metric}</code> — {derivation} across {count} "
            f"{org_word}: {names}</li>"
        )
    return (
        '<div class="aggregate-inputs"><h2>Aggregate inputs</h2>'
        '<p>Organizations contributing to each headline aggregate:</p>'
        f'<ul>{"".join(items)}</ul></div>'
    )


def _trend_section(store_root, current_date, as_of):
    dates = trend_snapshot_dates(store_root, current_date)
    if not dates:
        return ""
    points, empty_dates, excluded = trend_observations(store_root, current_date)
    if len(points) < 2:
        omissions = "".join(
            f"<li>{escape_html(date)} · {_blank(reason)}</li>"
            for date, reason in empty_dates
        )
        return (
            '<section id="trend-section" class="trend"><h2>Trend</h2>'
            '<p>No trend is shown: fewer than two usable dated observations remain.</p>'
            f"<ul>{omissions}</ul></section>"
        )

    maximum = max((point[2] for point in points), default=1) or 1
    chart_width, chart_height, left, top = 900, 250, 50, 20
    plot_width, plot_height = 800, 170
    denominator = max(len(points) - 1, 1)

    def coordinates(value_index):
        return [
            (
                left + index / denominator * plot_width,
                top + (1 - point[value_index] / maximum) * plot_height,
            )
            for index, point in enumerate(points)
        ]

    def polyline(values, css_class):
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in values)
        circles = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="{css_class}" />'
            for x, y in values
        )
        return f'<polyline points="{coords}" class="{css_class}" />{circles}'

    labels = "".join(
        f'<text x="{left + index / denominator * plot_width:.1f}" y="225" text-anchor="middle" class="svg-context">{escape_html(point[0])}</text>'
        for index, point in enumerate(points)
    )
    table_rows = []
    for date, orgs, total, custom, share in points:
        sources = _input_orgs(orgs, as_of)
        share_text = (
            _display(share, "percent")
            if share is not None
            else _blank("trend total_nodes denominator is zero")
        )
        table_rows.append(
            "<tr>"
            f'<th scope="row">{escape_html(date)}</th><td>{len(orgs)} orgs: {sources}</td>'
            f"<td>{_display(total)} · sum of total_nodes observations from: {sources}</td>"
            f"<td>{_display(custom)} · sum of custom_nodes (total_nodes − managed_nodes) from: {sources}</td>"
            f"<td>{share_text} · custom_nodes / total_nodes from: {sources}</td></tr>"
        )
    omissions = "".join(
        f"<li>{escape_html(date)} · {_blank(reason)}</li>"
        for date, reason in empty_dates
    )
    exclusion_items = "".join(
        f"<li>{org_mention(org, as_of)} — sync was already stale before the trend window</li>"
        for org in excluded
    )
    exclusions = (
        '<div class="trend-exclusions"><p>Trend-only exclusion: orgs already stale '
        f"before the window do not contribute to deltas.</p><ul>{exclusion_items}</ul></div>"
        if excluded
        else ""
    )
    absent = (
        f'<div class="trend-omissions"><p>Dates absent from the trend:</p><ul>{omissions}</ul></div>'
        if omissions
        else ""
    )
    return (
        '<section id="trend-section" class="trend"><h2>Trend</h2>'
        '<p>Derived aggregates from the named per-org observations in each dated snapshot.</p>'
        f"{exclusions}{absent}"
        '<div class="legend"><span class="total-key">total_nodes</span><span class="custom-key">custom_nodes</span></div>'
        f'<svg class="trend-chart" viewBox="0 0 {chart_width} {chart_height}" role="img" aria-label="total_nodes and custom_nodes by snapshot date">'
        f'{polyline(coordinates(2), "line-total")}{polyline(coordinates(3), "line-custom")}{labels}</svg>'
        '<div class="table-wrap"><table><thead><tr><th>Date</th><th>Input orgs</th><th>total_nodes</th><th>custom_nodes</th><th>custom_share_pct</th></tr></thead>'
        f"<tbody>{''.join(table_rows)}</tbody></table></div></section>"
    )


def _unpulled_section(unpulled):
    """Name confirmed orgs with no usable pull where they would have appeared."""
    if not unpulled:
        return ""
    items = "".join(
        f"<li><strong>{escape_html(item['org_name'])}</strong> "
        f"({escape_html(item['implementation_name'])}) · "
        f"<code>{escape_html(item['slug'])}</code> · refModelId "
        f"<code>{escape_html(item['ref_model_id'])}</code> · "
        f"{_blank('confirmed but not pulled; ' + item['reason'])}</li>"
        for item in unpulled
    )
    return (
        '<section class="peer-group unpulled"><h3>Confirmed orgs not pulled</h3>'
        "<p>These orgs are in the confirmed selection for this snapshot but have no "
        "usable pull, so they appear in no count, tile or chart. Re-run the pull for "
        f"them to include them.</p><ul>{items}</ul></section>"
    )


def _single_org_notice(orgs, unpulled):
    if len(orgs) != 1 or unpulled:
        return ""
    return (
        '<section class="peer-group single-org"><h3>One org in this snapshot</h3>'
        "<p>This snapshot holds one org, so no cross-org comparison applies and the "
        "aggregates below equal that org's own counts. For a health read of this org, "
        "use the <code>elements-org-diagnostic</code> skill.</p></section>"
    )


def _scope_evidence(store_root, date, unpulled):
    discovery = load_discovery(store_root, date)
    if discovery.confirmed is None:
        source = (
            "has no confirmedOrgs list"
            if discovery.recorded
            else "is absent (no list_reference_models.json), so it has no confirmedOrgs list"
        )
        text = (
            f"The discovery record {source}; an org left out of scope cannot be told "
            "apart from a selected org whose pull was interrupted."
        )
    elif unpulled:
        text = (
            f"{len(discovery.confirmed)} confirmed orgs; "
            f"{len(unpulled)} not pulled (named on the Report tab)."
        )
    else:
        text = confirmed_orgs_pulled_sentence(len(discovery.confirmed))
    if discovery.confirmed is not None:
        excluded = out_of_scope_org_dirs(store_root, date)
        if excluded:
            text += (
                " Left out of every count as outside confirmedOrgs (directory present): "
                + ", ".join(excluded)
                + "."
            )
    return f"<h2>Org selection</h2><p>{escape_html(text)}</p>"


def _evidence(orgs, date, store_root, as_of, timing_notice, unpulled=()):
    rows = []
    for org in sorted(orgs, key=org_sort_key):
        elapsed, stale = freshness(org, as_of)
        failing = sync_failing(org)
        if elapsed is None:
            age_status = '<span class="flag">sync_time is after the as-of instant</span>'
        elif stale:
            age_status = '<span class="flag">stale</span>'
        else:
            age_status = '<span class="current">current</span>'
        if failing:
            sync_status = '<span class="flag">sync failing</span>'
        elif sync_running(org):
            sync_status = (
                '<span class="flag">sync running: counts were taken while a sync '
                "was in progress</span>"
            )
        else:
            sync_status = '<span class="current">not failing</span>'
        
        elapsed_text = (
            "—"
            if elapsed is None
            else f"{elapsed} elapsed days from sync_time {sync_time_value(org)} to as-of {escape_html(as_of)}"
        )
        rows.append(
            "<tr>"
            f'<th scope="row">{org_mention(org, as_of)}<span class="slug">{org_mention(org, as_of, org["slug"])}</span></th>'
            f"<td>{implementation_mention(org)}</td><td>{escape_html(org['sync_status'])}</td>"
            f"<td>{sync_status}</td><td>{age_status}</td>"
            f"<td><code>{sync_time_value(org)}</code></td><td>{elapsed_text}</td></tr>"
        )
    return (
        '<section class="evidence-section"><h2>Snapshot timing evidence</h2>'
        f"<p>{escape_html(timing_notice)}</p>{unusable_snapshot_evidence(store_root, date)}"
        f"{_scope_evidence(store_root, date, unpulled)}"
        f"{_aggregate_inputs(orgs, as_of)}"
        '<h2>Freshness evidence</h2><div class="table-wrap"><table><thead><tr>'
        '<th>org_name / org_slug</th><th>implementation_name</th><th>syncStatus</th>'
        '<th>Sync signal</th><th>Data age</th><th>sync_time</th><th>elapsed days</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        '<h2>Known unknowns</h2><ul>'
        '<li>Per-user, per-license, and per-data-volume normalization is not obtainable over MCP; no proxy is substituted.</li>'
        '<li>Production/sandbox lineage is not exposed by <code>list_reference_models</code>; lineage-based grouping is customer-declared.</li>'
        '<li>Counts come only from <code>query_metadata</code> manifest counts. <code>get_org_structure</code> counts use a different, undocumented basis and are deliberately not mixed in; observed Apex and Permission Set figures disagree for the same orgs.</li>'
        "</ul>"
        f"{type_count_contradiction_evidence(orgs, as_of)}"
        f"{provenance_shell(orgs, date, store_root, 'Multi-Org Overview', as_of)}"
        "</section>"
    )


def _rendered_observation_metric_names(orgs):
    """Return the observation names this renderer will display for these orgs.

    With no pulled org there is no observation to display; the page still names
    every confirmed-but-unpulled org.
    """
    if not orgs:
        return set()
    names = {"org_name", "org_slug", "implementation_name", "sync_time"}
    for org in orgs:
        if org["total_nodes"] is not None:
            names.add("total_nodes")
        if org["managed_nodes"] is not None:
            names.add("managed_nodes")
        supported = org.get("supported_types", set(org["type_counts"]))
        for type_name, count in org["type_counts"].items():
            if classify_type_count(
                type_name, count, org.get("types_present"), supported
            ).state == "observed":
                names.add(type_metric_name(type_name))
        for type_name, count in org.get("denominator_counts", {}).items():
            if count is not None and count > 0 and (
                supported is not None and type_name not in supported
            ):
                names.add(coverage_denominator_metric(type_name))
    return names


CSS = """
:root { color-scheme: light; --ink:#172033; --muted:#667085; --line:#d9dee8; --paper:#fff; --wash:#f5f7fb; --blue:#3157d5; --teal:#16857a; --amber:#a85b00; }
""" + BASE_CSS + TAB_CSS + """.tiles { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin-bottom:28px; }
.tile, .chart-card, .peer-group, .trend, .evidence-section { background:var(--paper); border:1px solid var(--line); border-radius:12px; }
.tile { padding:18px; }
.tile > span, .tile > small { display:block; }
.tile > span { font-family:monospace; font-weight:700; }
.tile strong { display:block; margin:4px 0; font-size:30px; }
.tile small, .context, .slug, .section-heading span, .chart-card p { color:var(--muted); }
.peer-group, .trend, .evidence-section { margin-bottom:22px; padding:20px; }
""" + SECTION_HEADING_CSS + CONTENT_CSS + """.flag, .current { display:inline-block; padding:3px 7px; border-radius:999px; font-size:12px; font-weight:700; }
""" + FLAG_CSS + CURRENT_CSS + """.stale-marker, .sync-failing-marker { display:inline-block; margin-left:6px; padding:3px 7px; border-radius:999px; background:#fff0dc; color:var(--amber); border:1px solid #efc48d; font-size:12px; font-weight:700; }
.chart-card { margin-top:16px; padding:16px; }
.bar-chart, .trend-chart { display:block; width:100%; height:auto; overflow:visible; }
.bar-custom { fill:var(--blue); min-width:1px; }
.bar-managed { fill:var(--teal); min-width:1px; }
""" + SVG_TEXT_CSS + """.svg-context { fill:var(--muted); font:11px monospace; }
.legend { display:flex; gap:24px; margin:10px 0; font-family:monospace; }
.total-key::before, .custom-key::before { content:""; display:inline-block; width:16px; height:3px; margin:0 7px 3px 0; }
.total-key::before { background:var(--teal); }
.custom-key::before { background:var(--blue); }
.line-total, .line-custom { fill:none; stroke-width:3; }
polyline.line-total { stroke:var(--teal); } circle.line-total { fill:var(--teal); stroke:var(--paper); }
polyline.line-custom { stroke:var(--blue); } circle.line-custom { fill:var(--blue); stroke:var(--paper); }
""" + PROVENANCE_CSS + """@media (max-width:800px) { .page { padding:12px; } .tiles { grid-template-columns:1fr; } .snapshot-header { position:static; } }
"""


def render_overview(store_root, date, output_path, as_of=None, peer_groups_path=None):
    """Regenerate tidy observation metrics and render one offline overview."""
    store_root = Path(store_root)
    output_path = Path(output_path)
    orgs = load_snapshot(store_root, date)
    as_of_resolution = resolve_as_of(orgs, date, as_of)
    as_of = as_of_resolution.instant
    grouping = resolve_peer_groups(orgs, peer_groups_path)
    derived_dir = store_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)

    rows = all_store_metrics_rows(store_root, date)
    csv_metric_names = {row[2] for row in rows}
    rendered_observation_names = _rendered_observation_metric_names(orgs)
    missing_names = sorted(rendered_observation_names - csv_metric_names)
    if missing_names:
        raise AssertionError(
            "rendered observation metric names missing from metrics.csv: "
            + ", ".join(missing_names)
        )

    stale_orgs = [org for org in orgs if freshness(org, as_of)[1]]
    failing_orgs = [org for org in orgs if sync_failing(org)]
    running_orgs = [org for org in orgs if sync_running(org)]
    unpulled = unpulled_confirmed_orgs(store_root, date, orgs)
    curated_types = _curated_types(orgs)
    report = (
        _single_org_notice(orgs, unpulled)
        + _headline_tiles(orgs, as_of)
        + _unpulled_section(unpulled)
        + grouping_in_use(grouping, as_of)
        + _peer_group_sections(grouping, curated_types, as_of)
        + _trend_section(store_root, date, as_of)
    )
    evidence = _evidence(
        orgs, date, store_root, as_of, as_of_resolution.notice, unpulled
    )
    title = (
        "Single-Org Overview" if len(orgs) == 1 and not unpulled else "Multi-Org Overview"
    )
    extra_signals = ""
    if running_orgs:
        extra_signals += f" · {len(running_orgs)} sync running"
    if unpulled:
        extra_signals += (
            f" · {len(unpulled)} confirmed "
            f'{"org" if len(unpulled) == 1 else "orgs"} not pulled'
        )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · {escape_html(date)}</title>
<style>{CSS}</style>
</head>
<body><main class="page">
<header class="snapshot-header">Data as of {escape_html(date)} snapshot · {len(orgs)} {"org" if len(orgs) == 1 else "orgs"} · {len(stale_orgs)} stale · {len(failing_orgs)} sync failing{extra_signals} — see Evidence · checked {escape_html(as_of)}</header>
{tab_shell('overview-tab', report, evidence)}</main></body></html>
"""
    write_metrics_csv(rows, derived_dir / "metrics.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def main(argv=None):
    parser = build_cli_parser(
        "Render a self-contained Multi-Org Overview from a dated snapshot."
    )
    args = parser.parse_args(argv)
    try:
        render_overview(
            args.snapshots, args.date, args.out, args.as_of, args.peer_groups
        )
    except PeerGroupArgumentError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
