# Comparison patterns

The methodology this skill teaches. Four patterns, three normalization tiers, one set of guardrails,
and a worked example of a composite score.

Read this when designing a bespoke comparison, or when deciding whether a customer's request is
answerable honestly.

---

## The four patterns

### 1. Cross-Org Aggregation

"What do we have?" Raw counts summed across orgs, with explicit org-count denominators. Nothing
is judged, ranked, or scored.

Use when the question is inventory. This is the safest pattern and the right default for a first
conversation — it establishes the shape of the estate before anyone argues about quality.

Requirements: every total states how many orgs it covers, and any org excluded for licensing or
staleness is named. "412 flows across 6 orgs" is honest; "412 flows" is not.

### 2. Outlier Surfacing — *the default framing for quality questions*

"Which orgs are unlike their peers?" A peer-median baseline with the extremes named.

Prefer this over ranking whenever the question sounds like "which org is worst". It answers the real
question without inventing a total order over things that are not totally ordered.

**The N≥8 rule is absolute.** With 8 or more peers: median + median absolute deviation (MAD), flag beyond 3 MADs. Below 8:
name the extremes, show the spread, and do not use the words *outlier*, *anomaly*, or
*significant*. Three orgs do not have a distribution.

Baseline is the peer median, never the best org. Comparing everyone to the strongest performer
manufactures deficiency out of ordinary variation.

### 3. Ranked Comparison — *restricted*

"Order these orgs." Only legitimate on **within-org ratios with a known good direction**.

Test-coverage percentage has a good direction: higher is better, and it is already normalized by org
size. Documentation coverage likewise. Flow count does not: more flows is neither better nor worse,
and a bigger org has more of them.

Never rank raw counts. A league table of "most technical debt" is a league table of org size, or of
how many managed packages someone installed.

Composite scores must show their components and weights on the page. A bare score is unfalsifiable.

### 4. Drift Detection

"Has this diverged from what it should match?" Two modes, one diff engine.

- Mode A — declared pairs. Prod vs its sandbox, live over MCP. Needs no accumulated history, but
  it does need the customer to declare which orgs are paired — MCP does not expose lineage (see
  Peer groups above).
- Mode B — org vs itself over time. Needs two or more dated snapshots.

Differences are divergence facts, never deficiencies — a sandbox ahead of prod is a release in
flight, not a defect. Run the zero-vs-absent check on both sides before any "missing in X" claim,
and flag the pair if either side is stale.

---

## The three normalization tiers

Apply in order. Skipping a tier is how a comparison becomes a falsehood.

Tier 1 — within-org percentages compare directly. A percentage already carries its denominator.
These are the only numbers safe to put side by side without further work.

Tier 2 — raw counts never appear bare. A count always appears beside total node size and the
custom/total share, so the reader can see whether a big number means a big problem or a big org.

**Tier 3 — split managed from custom before any comparison.** Managed-package components are not the
customer's build and usually not the customer's problem.

This tier is not theoretical. In one space:

| Org | Total nodes | Managed | Managed share |
|---|---|---|---|
| Org A | 26,103 | 19,842 | 76% |
| Org B | 9,563 | 69 | 0.7% |

By raw total, Org A is nearly three times the build. By custom nodes it is 6,261 against 9,494, so it is
smaller. Any comparison that skipped tier 3 would have said the opposite of the truth.

What cannot be normalized over MCP: per-user, per-license, and per-data-volume normalization.
The inputs are not exposed. Say so plainly rather than substituting a proxy that looks quantitative.

---

## Peer groups

Default peer key: implementation grouping, read from `list_reference_models`. Customer-declared
groups override it.

Prod/sandbox lineage is not available over MCP. `list_reference_models` exposes
`implementation`, `orgId`, `name`, `sourceType` (always `salesforce`) and the sync fields — nothing
identifies which org is production and which is its sandbox. The temptation is to read it off the
name, and one space shows why that fails in both directions: "Full sandbox" is
obvious, while three separate orgs are all called "Production". Pairing orgs on a guessed lineage is
the same error as comparing on an unshown grouping.

So lineage is **customer-declared**, like any other grouping, and shown on the page. This bites
Drift Detection hardest: its lineage-pair mode needs the customer to say which orgs are paired
before it can run at all.

Show the grouping on the page. The agent never runs a comparison against a guessed grouping without
displaying it first — org selection and grouping are customer configuration, not agent inference.

A practical consequence: most spaces will not reach 8 orgs *per peer group* even when they have many
orgs overall. In observed spaces most implementations hold one org and the largest peer group is
about 3. Expect the below-8 branch to be the common case, and make sure it reads as a real answer rather
than an apology.

### A peer group of one is not a comparison

Below 8 peers you lose outlier *statistics*. Below 2 peers you lose the comparison itself, and
so omit the comparison chart and show the org in the ungrouped table.

A peer group with fewer than two orgs draws no comparison chart, because a single value
would appear to have a peer baseline when it does not. Its orgs appear once, in a compact
table, stated plainly as having no peers in their group and shown without comparison.

Do not fix a thin peer group by pooling every org into one global peer set. Peer grouping is
customer configuration; regrouping orgs so a chart looks fuller is precisely the "comparison on an
unshown grouping" this methodology forbids. If the customer wants a different grouping, they declare
one and it is shown on the page.

---

## Guardrails

These ship verbatim in SKILL.md. They are the rules that make bespoke analytics reliable.

Intentional difference ≠ deficiency. Structural differences between orgs are observations. Only
good-direction ratios earn deficiency wording.

**Zero vs absent.** A zero is reported only after the manifest confirms the type exists in that org.
Everything else is blanked with a reason, in place.

Absence of metadata ≠ absence of capability. No flows does not mean no automation — it may mean
automation lives in Apex, in a managed package, or outside Salesforce. Type this as an inference gap.

No silent omission. Every org or dimension excluded by licensing, staleness, or a missing
denominator is named in the artifact, where it would have appeared.

Staleness taints comparisons. Per-org freshness stamps always; stale orgs flagged; trend deltas
exclude orgs that went stale before the window. A stale org's payload looks perfectly healthy — the
stamp is the only signal.

Outlier math is median + MAD at N≥8, flag beyond 3 MADs, nothing fancier. Below ~8 peers,
statistical outlier language is forbidden: name extremes, show spread.

---

## Refuse or qualify

The sorting principle: refuse when the output would be a plausible-looking falsehood the reader
cannot detect; qualify a true output that needs context.

Refuse — do the safe alternative and say why:

- Outlier language below N=8.
- Invented freshness (anything derived from `updatedAt`).
- Bare-count league tables, or ranking without a good direction.
- Silent repair of missing data — never imputed, never stale-substituted, never defaulted to 0.

Proceed with visible qualification:

- Stale orgs in comparisons (flagged; excluded from trend deltas only).
- Zeros (observed only where the manifest confirms the type exists).
- Cross-org structural differences (observation wording).
- Small peer groups at N<8 (comparable, just without outlier statistics).

---

## Worked example: the Architecture Scorecard

A composite score across orgs is the most-requested and riskiest thing a customer will ask for. It
is deliberately not shipped as a template — but refusing outright is unhelpful when a customer
genuinely needs one number for a steering committee. Here is how to do it so it stays honest.

### What makes composites dangerous

A single number hides the judgments that produced it: which components, which weights, which
direction, and what happened to the orgs missing an input. Readers treat it as measurement. It is
an opinion with arithmetic attached.

### Composite rules

1. Components must be tier-1 ratios. Every component is a within-org percentage with a known
good direction. If a candidate component is a raw count, it does not go in — normalize it into a
ratio first or drop it.

2. Weights are declared, shown, and few. Three to five components. Weights appear on the page
next to the score, not in a footnote and not only in the code. A reader who disagrees with a weight
must be able to see it and re-do the arithmetic.

**3. A missing component blanks the score — it never scores zero.** If an org has no validation
rules, its validation-rule documentation ratio does not exist. Substituting 0 punishes the org for
something it does not have; substituting the mean invents data. The score for that org is blank,
with the missing component named. This is the rule that most composite implementations get wrong.

4. Components render beside the score, always. The score never appears alone — not in a tile,
not in a table cell, not in the header. A score with its components visible is a summary; a score
without them is a claim.

### Sketch

With components `documentation_coverage_pct`, `test_coverage_pct`, and `active_automation_share_pct`,
weights 0.4 / 0.4 / 0.2:

| Org | Doc % | Test % | Active auto % | Score | Note |
|---|---|---|---|---|---|
| Org A | 85.5 | 62.0 | 91.0 | 77.2 | — |
| Org B | 60.0 | 41.0 | 88.0 | 58.0 | — |
| Org C | 28.6 | — | 74.0 | — | no Apex; test coverage undefined |

Org C has no score because test coverage is undefined. The page states *"Score omitted: test_coverage_pct undefined (org has no
Apex classes)"* where Org C's score would have been — and the weights row `0.4 / 0.4 / 0.2` sits directly
beneath the table.

That is the whole discipline: the reader can see what went in, what was missing, and what it would
take to disagree.
