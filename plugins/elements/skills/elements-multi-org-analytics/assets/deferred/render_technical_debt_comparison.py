#!/usr/bin/env python3
# Deferred pending Overview field feedback. Its centerpiece — median+MAD outlier
# statistics — requires N>=8 peers, while the validated space's largest peer group
# is 3 and three of four groups are singletons. A redesign should be
# extremes-and-spread-first with outlier statistics as the rare upgrade.
"""Render a self-contained Technical Debt Comparison from raw snapshots.

The renderer builds on the Multi-Org Overview snapshot spine, resolves every
documentation ratio against its curated manifest denominator, regenerates tidy
metrics, and writes an offline HTML report with inline CSS and SVG charts.

Usage:
  render_technical_debt_comparison.py --snapshots STORE --date YYYY-MM-DD
                                      --out FILE.html [--as-of ISO-INSTANT]
                                      [--peer-groups FILE.json]
"""

import sys
from pathlib import Path

from helpers import (
    BASE_CSS,
    CONTENT_CSS,
    CURRENT_CSS,
    FLAG_CSS,
    PeerGroupArgumentError,
    PEER_COMPARISON_N_MIN,
    PROVENANCE_CSS,
    SECTION_HEADING_CSS,
    SVG_TEXT_CSS,
    TAB_CSS,
    TECH_DEBT_METRICS,
    aggregate_org,
    coverage_denominator_metric,
    coverage_ratios,
    derived,
    derived_title,
    escape_html,
    format_percent,
    freshness,
    grouping_in_use,
    implementation_mention,
    load_snapshot,
    load_tech_debt,
    normalize_tiers,
    observation_collector,
    observed,
    omitted,
    inactive_detail_metric,
    outdated_api_detail_metric,
    org_mention,
    org_sort_key,
    outlier_verdict,
    build_cli_parser,
    partition_peer_groups,
    peer_group_kind,
    pull_reconciliation_evidence,
    provenance_shell,
    rank_metric,
    resolve_as_of,
    resolve_peer_groups,
    result,
    sync_failing,
    sync_time_value,
    tab_shell,
    type_count_contradiction_evidence,
    unavailable_coverage_ratios,
    unusable_snapshot_evidence,
    write_metrics_csv,
)

def _load_orgs(store_root, date):
    orgs = load_snapshot(store_root, date)
    date_dir = Path(store_root) / "raw" / date
    for org in orgs:
        org["tech_debt"] = load_tech_debt(date_dir / org["slug"])
        if org["tech_debt"] is None:
            org["coverage_ratios"] = unavailable_coverage_ratios(
                "get_tech_debt_summary unavailable: raw file absent; tool may be unlicensed"
            )
        else:
            org["coverage_ratios"] = coverage_ratios(org["tech_debt"], org)
    areas = _coverage_areas(orgs)
    for area in areas:
        prototype = next(
            org["coverage_ratios"][area]
            for org in orgs
            if area in org["coverage_ratios"]
        )
        for org in orgs:
            if area not in org["coverage_ratios"]:
                org["coverage_ratios"][area] = prototype._replace(
                    value=None,
                    denominator=None,
                    reason="not reported for this org",
                )
    return orgs


def _coverage_areas(orgs):
    seen = set()
    areas = []
    for org in orgs:
        for area in org["coverage_ratios"]:
            if area not in seen:
                seen.add(area)
                areas.append(area)
    return areas


def _ratio_chart(collector, metric_name, implementation_name, observations, verdict, as_of):
    def chart_percent(value):
        """Clamp geometry only; labels retain the source value verbatim."""
        if value <= 0:
            return 0.0
        if value >= 100:
            return 100.0
        return float(value)

    width = 940
    left = 230
    plot_width = 620
    top = 36
    row_height = 36
    height = top + row_height * len(observations) + 34
    chart_parts = []
    if verdict.method == "median_mad":
        lower = max(0, verdict.baseline - 3 * verdict.spread)
        upper = min(100, verdict.baseline + 3 * verdict.spread)
        band_x = left + chart_percent(lower) / 100 * plot_width
        band_width = (
            chart_percent(upper) - chart_percent(lower)
        ) / 100 * plot_width
        chart_parts.append(
            f'<rect x="{band_x:.2f}" y="12" width="{band_width:.2f}" '
            f'height="{height - 30}" class="mad-band">'
            f'{derived_title(collector, "mad_band_" + metric_name, [org for org, _ in observations], f"three MAD band: {lower:.1f}% to {upper:.1f}%", (lower, upper))}</rect>'
        )
    if verdict.baseline is not None:
        median_x = left + chart_percent(verdict.baseline) / 100 * plot_width
        chart_parts.append(
            f'<line x1="{median_x:.2f}" y1="12" x2="{median_x:.2f}" '
            f'y2="{height - 18}" class="median-line">'
            f'{derived_title(collector, "peer_median_" + metric_name, [org for org, _ in observations], f"Peer median {format_percent(verdict.baseline)}", (verdict.baseline,))}</line>'
        )
    for index, (org, value) in enumerate(observations):
        y = top + index * row_height
        x = left + chart_percent(value) / 100 * plot_width
        dot_class = "flagged-dot" if index in verdict.outlier_indices else "ratio-dot"
        chart_parts.append(
            f'<text x="8" y="{y + 5}" class="svg-org">{org_mention(org, as_of, svg=True)}</text>'
            f'<circle cx="{x:.2f}" cy="{y}" r="6" class="{dot_class}">'
            f'<title>{escape_html(metric_name)}</title></circle>'
            f'<text x="{x + 10:.2f}" y="{y + 5}" class="svg-value">{observed(collector, org, metric_name, value, as_of=as_of, unit="svg-percent")}</text>'
        )
    return (
        f'<svg class="ratio-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape_html(metric_name)} peer dot plot">{"".join(chart_parts)}</svg>'
    )


def _omission_list(omissions, as_of):
    if not omissions:
        return ""
    items = "".join(
        f'<li><strong>{org_mention(org, as_of)}</strong> — '
        f'{omitted(org, ratio.metric_name, ratio.reason)}</li>'
        for org, ratio in omissions
    )
    return f'<div class="omissions"><span>Omitted from this peer set</span><ul>{items}</ul></div>'


def _extreme_summary(collector, metric_name, observations, verdict, as_of):
    if not observations:
        return '<p class="method">No safely comparable observations in this peer set.</p>'
    low_value = min(value for _, value in observations)
    high_value = max(value for _, value in observations)
    low_orgs = [org for org, value in observations if value == low_value]
    high_orgs = [org for org, value in observations if value == high_value]
    low_names = ", ".join(org_mention(org, as_of) for org in low_orgs)
    high_names = ", ".join(org_mention(org, as_of) for org in high_orgs)
    source_orgs = [org for org, _ in observations]
    return (
        f'<p class="method">N={derived(collector, "peer_n_" + metric_name, source_orgs, len(observations))} · lowest '
        f'{low_names} {observed(collector, low_orgs[0], metric_name, low_value, as_of=as_of, unit="percent")} · highest '
        f'{high_names} {observed(collector, high_orgs[0], metric_name, high_value, as_of=as_of, unit="percent")} · spread '
        f'{derived(collector, "spread_" + metric_name, source_orgs, verdict.spread, unit="decimal-1")} percentage points · peer median '
        f'{derived(collector, "peer_median_" + metric_name, source_orgs, verdict.baseline, unit="percent")}. No statistical flags at this peer-set size.</p>'
    )


def _mad_summary(collector, metric_name, observations, verdict, as_of):
    source_orgs = [org for org, _ in observations]
    base = (
        f'<p class="method">N={derived(collector, "peer_n_" + metric_name, source_orgs, len(observations))} · peer median '
        f'{derived(collector, "peer_median_" + metric_name, source_orgs, verdict.baseline, unit="percent")} · MAD '
        f'{derived(collector, "mad_" + metric_name, source_orgs, verdict.spread, unit="decimal-1")} percentage points.'
    )
    if verdict.uniform:
        return base + " Uniform peer values; no flags.</p>"
    if verdict.spread_degenerate:
        return base + (
            " No dispersion by MAD; flagging is undefined at this spread.</p>"
        )
    flagged = [observations[index][0] for index in verdict.outlier_indices]
    if not flagged:
        return base + ' No values exceed three MADs.</p>'
    names = ", ".join(
        org_mention(org, as_of) for org in flagged
    )
    return base + f' <span class="method-flag">Outlier flag beyond three MADs: {names}</span></p>'


def _not_comparable_summary(collector, metric_name, observations):
    observation_count = len(observations)
    noun = "observation" if observation_count == 1 else "observations"
    return (
        '<p class="method">Not comparable for this metric: only '
        f'{derived(collector, "usable_n_" + metric_name, [org for org, _ in observations], observation_count)} usable {noun} remain after blanking; '
        'at least two are required.</p>'
    )


def _no_peers_table(collector, orgs, areas, as_of):
    headers = "".join(
        f'<th>{escape_html(orgs[0]["coverage_ratios"][area].metric_name)}'
        f'<span class="context">{escape_html(area)}</span></th>'
        for area in areas
    )
    rows = []
    for org in sorted(orgs, key=org_sort_key):
        cells = []
        for area in areas:
            ratio = org["coverage_ratios"][area]
            if ratio.value is None:
                value = omitted(org, ratio.metric_name, ratio.reason)
            else:
                value = observed(
                    collector,
                    org,
                    ratio.metric_name,
                    ratio.value,
                    as_of=as_of,
                    unit="percent",
                )
            cells.append(f"<td>{value}</td>")
        rows.append(
            "<tr>"
            f'<th scope="row"><span class="org-name">{org_mention(org, as_of)}</span>'
            f'<span class="slug">{org_mention(org, as_of, org["slug"])}</span></th>'
            f'<td>{implementation_mention(org)}</td>{"".join(cells)}</tr>'
        )
    return (
        '<section class="no-peers"><h3>Organizations without peers</h3>'
        '<p>These organizations have no peers in their implementation group and '
        'are shown without comparison.</p><div class="table-wrap"><table>'
        f'<thead><tr><th>Org</th><th>Implementation group</th>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def _surface_section(collector, orgs, grouping, as_of):
    areas = _coverage_areas(orgs)
    group_cards = []
    comparable_groups, no_peer_orgs = partition_peer_groups(grouping.groups)
    for implementation_name, peers in comparable_groups.items():
        metric_cards = []
        for area in areas:
            ratios = [(org, org["coverage_ratios"][area]) for org in peers]
            observations = [
                (org, ratio.value)
                for org, ratio in ratios
                if ratio.value is not None
            ]
            omissions = [
                (org, ratio) for org, ratio in ratios if ratio.value is None
            ]
            metric_name = ratios[0][1].metric_name
            label = metric_name
            if len(observations) < PEER_COMPARISON_N_MIN:
                summary = _not_comparable_summary(collector, metric_name, observations)
                chart = ""
            else:
                verdict = outlier_verdict(value for _, value in observations)
                if verdict.method == "median_mad":
                    summary = _mad_summary(collector, metric_name, observations, verdict, as_of)
                else:
                    summary = _extreme_summary(
                        collector, metric_name, observations, verdict, as_of
                    )
                chart = _ratio_chart(
                    collector,
                    metric_name,
                    implementation_name,
                    observations,
                    verdict,
                    as_of,
                )
            metric_cards.append(
                f'<article class="metric-card"><h4>{escape_html(label)}</h4>'
                f'{summary}{chart}{_omission_list(omissions, as_of)}</article>'
            )
        group_cards.append(
            f'<section class="peer-group"><div class="section-heading">'
            f'<h3>{derived(collector, "peer_group_name", peers, implementation_name, unit="text")}</h3><span>'
            f'{derived(collector, "peer_org_count", peers, len(peers))} {"org" if len(peers) == 1 else "orgs"} in '
            f'{peer_group_kind(grouping, implementation_name)}</span></div>{"".join(metric_cards)}</section>'
        )
    if group_cards:
        heading = "Coverage peer comparison"
        intro = "Each metric states its own observation count and comparison method."
    else:
        heading = "Coverage without peer comparison"
        intro = "No implementation group contains enough organizations for peer comparison."
    no_peers = _no_peers_table(collector, no_peer_orgs, areas, as_of) if no_peer_orgs else ""
    return (
        f'<section class="report-section"><h2>{heading}</h2><p>{intro}</p>'
        f'{no_peers}{"".join(group_cards)}</section>'
    )


def _ranked_section(collector, orgs, grouping, as_of):
    group_sections = []
    comparable_groups, _ = partition_peer_groups(grouping.groups)
    for implementation_name, peers in comparable_groups.items():
        cards = []
        for area in _coverage_areas(orgs):
            ratios = [(org, org["coverage_ratios"][area]) for org in peers]
            observations = [
                (org, ratio.value) for org, ratio in ratios if ratio.value is not None
            ]
            omissions = [(org, ratio) for org, ratio in ratios if ratio.value is None]
            if len(observations) >= PEER_COMPARISON_N_MIN:
                metric_name = next(
                    ratio.metric_name for _, ratio in ratios if ratio.value is not None
                )
                ranked = rank_metric(metric_name, observations)
                rows = [
                    "<tr>"
                    f'<td>{result(collector, org, "rank_" + metric_name, rank)}</td><th scope="row"><span class="org-name">'
                    f'{org_mention(org, as_of)}</span><span class="slug">'
                    f'{org_mention(org, as_of, org["slug"])}</span></th><td>'
                    f'{observed(collector, org, metric_name, value, as_of=as_of, unit="percent")}</td></tr>'
                    for rank, org, value in ranked
                ]
                rows.extend(
                    "<tr>"
                    f'<td>—</td><th scope="row"><span class="org-name">'
                    f'{org_mention(org, as_of)}</span><span class="slug">'
                    f'{org_mention(org, as_of, org["slug"])}</span></th><td>'
                    f'{omitted(org, ratio.metric_name, ratio.reason)}</td></tr>'
                    for org, ratio in sorted(
                        omissions, key=lambda item: org_sort_key(item[0])
                    )
                )
                body = "".join(rows)
                cards.append(
                    f'<article class="rank-card"><h3>{escape_html(metric_name)}</h3>'
                    f'<div class="table-wrap"><table><thead><tr><th>Rank</th><th>Org</th>'
                    f'<th>{escape_html(metric_name)}</th></tr></thead><tbody>{body}</tbody>'
                    f'</table></div></article>'
                )
            else:
                metric_name = ratios[0][1].metric_name
                cards.append(
                    f'<article class="rank-card"><h3>{escape_html(metric_name)}</h3>'
                    f'{_not_comparable_summary(collector, metric_name, observations)}'
                    f'{_omission_list(omissions, as_of)}</article>'
                )
        group_sections.append(
            f'<section class="peer-group"><div class="section-heading">'
            f'<h3>{derived(collector, "peer_group_name", peers, implementation_name, unit="text")}</h3><span>'
            f'{derived(collector, "peer_org_count", peers, len(peers))} {"org" if len(peers) == 1 else "orgs"} in '
            f'{peer_group_kind(grouping, implementation_name)}</span></div>{"".join(cards)}</section>'
        )
    if not group_sections:
        return ""
    return (
        '<section class="report-section"><h2>Ranked coverage comparison</h2>'
        '<p>Higher documentation coverage ranks first. Only ratios with observed, '
        'non-zero curated denominators enter these lists.</p>'
        f'{"".join(group_sections)}</section>'
    )


def _raw_counts_section(collector, orgs, as_of):
    headers = "".join(f"<th>{escape_html(name)}</th>" for name in TECH_DEBT_METRICS)
    rows = []
    inactive_rows = []
    api_details = []
    for org in sorted(orgs, key=org_sort_key):
        normalized = normalize_tiers(org)
        total_markup = (
            observed(collector, org, "total_nodes", org["total_nodes"], as_of=as_of)
            if org["total_nodes"] is not None
            else omitted(org, "total_nodes", "raw count file absent; dimension unavailable")
        )
        share_reason = (
            "normalization input unavailable"
            if org["total_nodes"] is None or org["managed_nodes"] is None
            else "total_nodes denominator is zero"
        )
        custom_share_markup = (
            observed(collector, org, "custom_share_pct", normalized["custom_share_pct"], as_of=as_of, unit="percent")
            if normalized["custom_share_pct"] is not None
            else omitted(org, "custom_share_pct", share_reason)
        )
        managed_share_markup = (
            observed(collector, org, "managed_share_pct", normalized["managed_share_pct"], as_of=as_of, unit="percent")
            if normalized["managed_share_pct"] is not None
            else omitted(org, "managed_share_pct", share_reason)
        )
        context = (
            f'of {total_markup} total_nodes · '
            f'{custom_share_markup} custom_share_pct · '
            f'{managed_share_markup} managed_share_pct'
        )
        dimension_reason = (
            "get_tech_debt_summary unavailable: raw file absent; tool may be unlicensed"
        )
        tech_debt = org["tech_debt"]
        if tech_debt is None:
            cells = "".join(
                f'<td>{omitted(org, metric_name, dimension_reason)}</td>'
                for metric_name in TECH_DEBT_METRICS
            )
        else:
            severity = tech_debt["tech_debt_severity"]
            cells = "".join(
                f'<td>{observed(collector, org, metric_name, severity[source_name], as_of=as_of)}'
                f'<span class="context">{context}</span></td>'
                for metric_name, source_name in TECH_DEBT_METRICS.items()
            )
        rows.append(
            "<tr>"
            f'<th scope="row"><span class="org-name">{org_mention(org, as_of)}</span>'
            f'<span class="slug">{org_mention(org, as_of, org["slug"])}</span></th>'
            f'<td>{total_markup}</td>'
            f'<td>{custom_share_markup}</td>'
            f'<td>{managed_share_markup}</td>{cells}</tr>'
        )
        inactive = tech_debt["inactive_metadata"] if tech_debt is not None else None
        if inactive:
            inactive_detail = '<ul class="compact-list">' + "".join(
                f'<li><span>{escape_html(type_name)}</span>'
                f'<span class="context">{escape_html(inactive_detail_metric(type_name))}</span>: '
                f'{observed(collector, org, inactive_detail_metric(type_name), count, as_of=as_of)}'
                f'<span class="context">{context}</span></li>'
                for type_name, count in sorted(inactive.items())
            ) + "</ul>"
        else:
            inactive_detail = omitted(
                org,
                "debt_inactive_metadata_detail",
                dimension_reason
                if tech_debt is None
                else "no per-type inactive metadata reported",
            )
        inactive_rows.append(
            "<tr>"
            f'<th scope="row"><span class="org-name">{implementation_mention(org)} · '
            f'{org_mention(org, as_of)}</span><span class="slug">{org_mention(org, as_of, org["slug"])}</span></th>'
            f"<td>{inactive_detail}</td></tr>"
        )

        api_header = tech_debt["outdated_api_header"] if tech_debt is not None else []
        api_rows = tech_debt["outdated_api_versions"] if tech_debt is not None else []
        if api_rows:
            api_headers = "".join(f"<th>{escape_html(name)}</th>" for name in api_header)
            api_headers += "<th>Within-org context</th>"
            api_body = "".join(
                "<tr>"
                + "".join(
                    f'<td><span class="context">{escape_html(outdated_api_detail_metric(column_name, row_index))}</span>'
                    f'{observed(collector, org, outdated_api_detail_metric(column_name, row_index), value, as_of=as_of)}</td>'
                    for column_name, value in zip(api_header, row)
                )
                + f'<td><span class="context">{context}</span></td>'
                + "</tr>"
                for row_index, row in enumerate(api_rows, start=1)
            )
            api_detail = (
                '<div class="table-wrap"><table><thead><tr>'
                f"{api_headers}</tr></thead><tbody>{api_body}</tbody></table></div>"
            )
        else:
            api_detail = (
                '<p>'
                + omitted(
                    org,
                    "debt_outdated_api_detail",
                    dimension_reason if tech_debt is None else "no outdated API versions",
                )
                + "</p>"
            )
        api_details.append(
            f'<article class="api-detail"><h4>{implementation_mention(org)} · '
            f'{org_mention(org, as_of)}</h4><p class="slug">{org_mention(org, as_of, org["slug"])}</p>'
            f"{api_detail}</article>"
        )
    return (
        '<section class="report-section"><h2>Raw debt observations</h2>'
        '<p>Alphabetical within implementation, not ranked. Every raw count is shown '
        'with org size and the custom/managed share because these counts scale with '
        'architecture and package content.</p><div class="table-wrap"><table>'
        '<thead><tr><th>Org</th><th>total_nodes</th><th>custom_share_pct</th>'
        f'<th>managed_share_pct</th>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<h3>Inactive metadata by type</h3><p>Only reported sparse-map entries '
        'are shown; absent types are not rendered as zero.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Org</th><th>Reported type: count</th>'
        f'</tr></thead><tbody>{"".join(inactive_rows)}</tbody></table></div>'
        '<h3>Outdated API versions by org</h3>'
        f'{"".join(api_details)}</section>'
    )


def _evidence(collector, orgs, date, store_root, as_of, timing_notice):
    freshness_rows = []
    denominator_rows = []
    for org in sorted(orgs, key=org_sort_key):
        elapsed, stale = freshness(org, as_of)
        failing = sync_failing(org)
        if elapsed is None:
            age_status = '<span class="flag">sync time is after the as-of instant</span>'
        elif stale:
            age_status = '<span class="flag">stale</span>'
        else:
            age_status = '<span class="current">current</span>'
        sync_status = (
            '<span class="flag">sync failing</span>'
            if failing
            else '<span class="current">not failing</span>'
        )
        elapsed_text = "—" if elapsed is None else f"{elapsed} elapsed days"
        freshness_rows.append(
            "<tr>"
            f'<th scope="row">{org_mention(org, as_of)}<span class="slug">'
            f'{org_mention(org, as_of, org["slug"])}</span></th><td>{implementation_mention(org)}</td>'
            f'<td>{escape_html(org["sync_status"])}</td>'
            f'<td>{sync_status}</td>'
            f'<td>{age_status}</td>'
            f'<td><code>{sync_time_value(org)}</code></td>'
            f'<td>{result(collector, org, "elapsed_days", elapsed) if elapsed is not None else "—"} elapsed days</td></tr>'
        )
        for ratio in org["coverage_ratios"].values():
            rendered_value = (
                observed(
                    collector,
                    org,
                    ratio.metric_name,
                    ratio.value,
                    as_of=as_of,
                    unit="percent",
                )
                if ratio.value is not None
                else omitted(org, ratio.metric_name, ratio.reason)
            )
            note = "included" if ratio.reason is None else ratio.reason
            denominator = (
                omitted(
                    org,
                    f"{ratio.metric_name}_denominator",
                    ratio.reason or "denominator was not observed",
                )
                if ratio.denominator is None
                else observed(
                    collector,
                    org,
                    coverage_denominator_metric(ratio.metadata_type),
                    ratio.denominator,
                    as_of=as_of,
                )
            )
            denominator_rows.append(
                "<tr>"
                f'<th scope="row">{org_mention(org, as_of)}</th>'
                f'<td>{escape_html(ratio.area)}</td>'
                f'<td>{escape_html(ratio.metadata_type or "—")}</td>'
                f'<td>{denominator}</td>'
                f'<td>{rendered_value}</td><td>{escape_html(note)}</td></tr>'
            )
    return (
        '<section class="evidence-section"><h2>Snapshot timing evidence</h2>'
        f'<p>{escape_html(timing_notice)}</p>{pull_reconciliation_evidence(store_root, date, orgs, as_of)}'
        f'{unusable_snapshot_evidence(store_root, date)}'
        '<h2>Freshness evidence</h2>'
        '<div class="table-wrap"><table><thead><tr><th>Org</th><th>Implementation</th>'
        '<th>syncStatus</th><th>Sync signal</th><th>Data age</th><th>syncTime</th><th>elapsed days</th></tr></thead>'
        f'<tbody>{"".join(freshness_rows)}</tbody></table></div>'
        '<h2>Denominator evidence</h2><div class="table-wrap"><table><thead><tr>'
        '<th>Org</th><th>Coverage area</th><th>Curated metadata type</th>'
        '<th>Denominator</th><th>Rendered ratio</th><th>Decision</th></tr></thead>'
        f'<tbody>{"".join(denominator_rows)}</tbody></table></div>'
        '<h2>Known unknowns</h2><ul>'
        '<li>Per-user, per-license, and per-data-volume normalization is not obtainable over MCP; no proxy is substituted.</li>'
        '<li>Production/sandbox lineage is not exposed by <code>list_reference_models</code>; lineage-based grouping is customer-declared.</li>'
        '<li>Counts come only from <code>query_metadata</code> manifest counts. <code>get_org_structure</code> counts use a different, undocumented basis and are deliberately not mixed in; observed Apex and Permission Set figures disagree for the same orgs.</li>'
        '<li><code>descriptionCoverage</code> cannot distinguish “nothing is documented” from “there is nothing to document”; ratios whose denominator is zero or unresolved are blanked rather than assigned a numeric value.</li>'
        '</ul>'
        f'{type_count_contradiction_evidence(collector, orgs, as_of)}'
        f"{provenance_shell(collector, orgs, date, store_root, 'Technical Debt Comparison', as_of)}"
        "</section>"
    )


CSS = """
:root { color-scheme:light; --ink:#172033; --muted:#667085; --line:#d9dee8; --paper:#fff; --wash:#f5f7fb; --blue:#3157d5; --teal:#16857a; --amber:#a85b00; --rose:#b42318; }
""" + BASE_CSS + TAB_CSS + """.report-section, .peer-group, .metric-card, .rank-card, .evidence-section { background:var(--paper); border:1px solid var(--line); border-radius:12px; }
.report-section, .evidence-section { margin-bottom:24px; padding:20px; }
.peer-group { margin-top:16px; padding:18px; }
.metric-card, .rank-card { margin-top:14px; padding:16px; }
""" + SECTION_HEADING_CSS + """.section-heading span, .method, .context, .slug, .omissions { color:var(--muted); }
""" + CONTENT_CSS + """.omissions { margin-top:10px; padding:10px 12px; border-left:3px solid var(--line); }
.omissions span { font-weight:700; }
.omissions ul { margin:6px 0 0; padding-left:20px; }
.flag, .current, .method-flag, .stale-marker, .sync-failing-marker { display:inline-block; padding:3px 7px; border-radius:999px; font-size:12px; font-weight:700; }
""" + FLAG_CSS + """.stale-marker, .sync-failing-marker { margin-left:6px; background:#fff0dc; color:var(--amber); border:1px solid #efc48d; }
""" + CURRENT_CSS + """.method-flag { background:#fee4e2; color:var(--rose); border:1px solid #fecdca; }
.ratio-chart { display:block; width:100%; height:auto; overflow:visible; margin-top:10px; }
.mad-band { fill:#dce5ff; opacity:.75; }
.median-line { stroke:var(--teal); stroke-width:2; stroke-dasharray:5 4; }
.ratio-dot { fill:var(--blue); stroke:var(--paper); stroke-width:2; }
.flagged-dot { fill:var(--rose); stroke:var(--paper); stroke-width:2; }
""" + SVG_TEXT_CSS + PROVENANCE_CSS + """@media (max-width:800px) { .page { padding:12px; } .snapshot-header { position:static; } .section-heading { display:block; } }
"""


def render_technical_debt_comparison(
    store_root, date, output_path, as_of=None, peer_groups_path=None
):
    """Regenerate tidy metrics and render one offline comparison HTML file."""
    store_root = Path(store_root)
    output_path = Path(output_path)
    orgs = _load_orgs(store_root, date)
    as_of_resolution = resolve_as_of(orgs, date, as_of)
    as_of = as_of_resolution.instant
    grouping = resolve_peer_groups(orgs, peer_groups_path)
    derived_dir = store_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    collector = observation_collector(
        store_root, date, orgs=orgs, grouping=grouping, as_of=as_of
    )

    stale_count = sum(freshness(org, as_of)[1] for org in orgs)
    failing_count = sum(sync_failing(org) for org in orgs)
    report = (
        grouping_in_use(collector, grouping, as_of)
        + _surface_section(collector, orgs, grouping, as_of)
        + _ranked_section(collector, orgs, grouping, as_of)
        + _raw_counts_section(collector, orgs, as_of)
    )
    evidence = _evidence(
        collector,
        orgs,
        date,
        store_root,
        as_of,
        as_of_resolution.notice,
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Technical Debt Comparison · {escape_html(date)}</title>
<style>{CSS}</style>
</head>
<body><main class="page">
<header class="snapshot-header">Data as of {escape_html(date)} snapshot · checked {escape_html(as_of)} · {result(collector, aggregate_org(date), "org_count", len(orgs), sources=[org["slug"] for org in orgs])} {"org" if len(orgs) == 1 else "orgs"} · {derived(collector, "orgs_stale", orgs, stale_count)} stale · {derived(collector, "orgs_sync_failing", orgs, failing_count)} sync failing — see Evidence</header>
{tab_shell('technical-debt-tab', report, evidence)}</main></body></html>
"""
    write_metrics_csv(collector.rows(), derived_dir / "metrics.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def main(argv=None):
    parser = build_cli_parser(
        "Render a self-contained Technical Debt Comparison from a dated snapshot."
    )
    args = parser.parse_args(argv)
    try:
        render_technical_debt_comparison(
            args.snapshots,
            args.date,
            args.out,
            args.as_of,
            args.peer_groups,
        )
    except PeerGroupArgumentError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
