# Technical Debt Comparison

"Which orgs need cleanup attention most — and is that real, or just their size and architecture?"

The second half of the question is the point. Any org with more stuff has more debt-shaped numbers.
This template exists to separate orgs that are genuinely behind from orgs that are merely large or
package-heavy.

The pull methodology is available; this recipe has no renderer yet.

Requires the Multi-Org Overview pull into the same dated directory. Not a suggestion: this
template's ratios take their denominators from the Overview's manifest counts, and without them the
ratios are not safe to render (see "The denominator rule" below).

## Patterns

Outlier Surfacing (primary) — peer-median baseline, extremes named.
Ranked Comparison (second section only) — restricted to good-direction within-org ratios.

## Metrics

| Metric name (verbatim in `metrics.csv`) | Type | Meaning |
|---|---|---|
| `debt_custom_profiles` | observed | Custom profiles flagged |
| `debt_inactive_metadata` | observed | Inactive components flagged |
| `debt_outdated_api` | observed | Components on outdated API versions |
| `debt_process_builders` | observed | Legacy Process Builders |
| `debt_workflow_rules` | observed | Legacy Workflow Rules |
| `description_coverage_<area>_pct` | observed | Documentation coverage, per area, only where the denominator is confirmed non-zero |

Coverage areas: objects, record types, fields, apex classes, apex triggers, flows, profiles,
permission sets, perm set groups, validation rules. Six take their denominators from the Overview's
curated types; the other four need the denominator-only types this template's pull spec adds. An
area whose denominator was never pulled blanks with that reason rather than appearing as 0%.

Raw `debt_*` counts appear beside org size and the custom/managed share so their scale is visible.
They are not ranked.

## Visualization default

Ratio dot-plots, one row per coverage area, with a peer-median line. The median absolute deviation (MAD) band is drawn only
when the peer set has 8 or more orgs.

## Guardrails-as-code — this template is the showcase

**The N≥8 switch.** `helpers.outlier_verdict` decides the method, and the render never second-guesses
it. At 8 or more peers: median + MAD, flag beyond 3 MADs. Below 8: extremes-and-spread wording and
zero outlier flags — the words "outlier", "anomaly" and "significant" do not appear.

Observed spaces hold a single-digit number of orgs across several implementations, so on real data
this template runs entirely in the below-8 branch. That is the honest result, not a degraded one.

**The denominator rule.** `descriptionCoverage` reports 0 both for "nothing is documented" and for
"there is nothing to document" — the payload cannot tell you which. Live proof:

| Org | "Validation rules" coverage | Validation rules it actually has |
|---|---|---|
| Org A | 0 | 63 |
| Org B | 0 | 0 |

Org A documents none of 63. Org B has none. Ranked naively they score identically. So every
ratio takes its denominator from the Overview's manifest counts; a zero or unresolved denominator
blanks the ratio, states why, and drops that org from that ratio's peer set.

**Raw counts are never ranked.** Org A reports `outdatedApi: 79` against Org C's `0`,
but Org A is 76% managed-package nodes. The share cannot identify which components carry the debt.
A league table on that count would conflate org size and package content with quality.

Difference is not deficiency. Deficiency wording is permitted only for good-direction ratios.
Everything else is stated as an observation.

Freshness taints comparisons. Stale orgs stay in, flagged. A failed latest attempt is shown as a
separate sync-failing signal; it does not make recently synced data stale. A failed org is often
also old, so it displays both signals.

## Customization points

- Peer grouping — implementation grouping by default; customer-declared groups override.
- Which coverage areas are ranked.
- The 3-MAD threshold, if a customer has a house convention.
- Freshness signals — stale after 7 elapsed days, with sync failure reported independently.

The Overview renderer accepts `--peer-groups <path>`, with JSON shaped as
`{"Group name": ["implementation--org", ...]}`. Declared groups override implementation grouping;
unmentioned orgs retain their implementation group, and the page shows the exact membership used.
A redesigned Technical Debt renderer should retain that interface.

## Scope fence

**No composite debt score.** Weighted composites are the riskiest pattern in the methodology and are
deliberately not shipped. If a customer wants one, the Architecture Scorecard worked example in
`references/comparison-patterns.md` shows how to do it properly — components and weights visible,
never a bare number.

- For what any individual flag *means* — why a profile counts as custom, what makes metadata
  inactive, which API versions matter → load `elements-tech-debt`. Meaning lives there.
- For node-level "what exactly changed" → `elements-change-briefing`.
- For a plain inventory with no judgment at all → Multi-Org Overview.
