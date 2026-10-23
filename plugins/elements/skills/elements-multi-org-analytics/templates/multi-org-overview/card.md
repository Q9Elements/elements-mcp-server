# Multi-Org Overview

"What do we have, across all our orgs?"

The starting template for an estate overview. It counts what is in every org
you can see and shows the counts side by side, grouped by implementation, and it judges nothing.

Access and refusals: [Tool contracts](../../references/tool-contracts.md).

## Pattern

**Cross-Org Aggregation.** Raw counts with explicit org-count denominators. Also owns the trending
demonstration: the trend section activates by itself once the store holds two or more dated
snapshots, so the same recipe becomes a time series with no edit.

## Metrics

Observation metrics are sourced from `list_metadata_by_criteria` manifest counts. Derived values name their
observation inputs and contributing orgs on the page. There are no interpretive claims here and
therefore no footnotes on the Report tab.

| Observation metric name (verbatim in `metrics.csv`) | Meaning |
|---|---|
| `total_nodes` | Live metadata nodes in the org (excludes `status: deleted` tombstones) |
| `managed_nodes` | Nodes belonging to managed packages |
| `nodes_field` | Curated type count |
| `nodes_custom_object` | Curated type count |
| `nodes_flow` | Curated type count |
| `nodes_apex_class` | Curated type count |
| `nodes_apex_trigger` | Curated type count |
| `nodes_validation_rule` | Curated type count |
| `org_name` | Identity row (text): the org's name from its manifest |
| `org_slug` | Identity row (text): the org's directory slug |
| `implementation_name` | Identity row (text): the org's implementation group |
| `sync_time` | Freshness row (text): the org's last completed sync, the as-of stamp |

The page also derives `custom_nodes` (`total_nodes - managed_nodes`), `managed_share_pct`, and
`custom_share_pct`. These have no comma-separated values (CSV) rows; their rendered context names the input observations and
contributing orgs.

Observation names are the contract: what the page shows for an observation is what the CSV holds,
so a reader can grep for it. Renaming an observation metric breaks the audit path; add a new one
instead.

Also shown, from `list_reference_models` via each org's `manifest.json`, not counted: implementation
group and access fields. Health `dataAsOf` supplies the per-org sync stamp; `syncStatus` is
defined by the [freshness contract](../../references/recipe-contract.md#freshness-fields-the-rules-that-matter).

Customer-declared production and sandbox pairs can be shown as peer groups. See "Peer groups" in
[Comparison patterns](../../references/comparison-patterns.md) for the grouping rule.

## Visualization default

Headline tiles, a per-org table grouped by implementation, and a grouped bar chart of custom vs
managed nodes per org (inline Scalable Vector Graphics (SVG)). Raw counts never appear bare; every count sits beside total
node size and the custom share, per normalization tier 2.

## What the guardrails do on this page

- Apply the managed/custom split from [Normalization tiers](../../references/comparison-patterns.md#the-three-normalization-tiers).
- **Zero vs absent, three ways.** A blank cell says which it is; `not present in this org`,
  `not synced by Elements`, or `presence not probed` (or `presence unconfirmed` for an unverified enumeration). A `0` on this page always means an observed
  zero. Nothing is imputed and no gap is silently filled.
- **Staleness is visible, not corrected.** Stale orgs stay in the comparison and are flagged; they
  are excluded from trend deltas. Unknown freshness also excludes an org from trends.
- Intentional difference is not deficiency. Orgs differ because they do different jobs. This
  template states differences as observations and never as findings.

## Customization points

- Curated type list; six types by default. Widen it in the pull spec; the planner shows
  the resulting call count.
- Peer grouping; defaults to implementation grouping. Customer-declared groups override, and
  the grouping in use is shown on the page rather than assumed.
- Freshness signals follow the [manifest contract](../../references/recipe-contract.md#freshness-fields-the-rules-that-matter).
- Tiles: which three headline numbers lead.

The Overview renderer accepts `--peer-groups <path>`, with JavaScript Object Notation (JSON) shaped as
`{"Group name": ["implementation--org", ...]}`. Declared groups override implementation grouping;
unmentioned orgs retain their implementation group, and the page shows the exact membership used.

## Scope fence

This template makes no health judgment. It will not tell you which org is worst, which needs
cleanup, or what to fix. It has no scores and no rankings.

- For "which orgs need cleanup attention, and is that real or just their size?" → Technical Debt
  Comparison.
- For what a specific flag or metric *means* → load the matching single-org skill
  (`elements-tech-debt`, `elements-metadata`). Meaning lives there; this skill only pulls and
  composes.
- For node-level "what exactly changed" → `elements-change-briefing`.
