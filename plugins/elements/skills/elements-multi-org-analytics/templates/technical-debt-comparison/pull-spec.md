# Pull spec — Technical Debt Comparison

Builds on the Multi-Org Overview pull. Run that spec first, into the same dated directory — this
template needs the Overview's manifest counts as **denominators**, and without them its ratios are
not safe to render.

## Cost

```
calls = <Multi-Org Overview cost> + orgs x (1 + D)
```

where `D` is the number of denominator-only types (4 by default). At 6 orgs that is ~83 calls total.

## Step 1 — everything in the Multi-Org Overview pull spec

Discovery, per-org totals, managed/custom split, curated type counts, presence probes, manifests.
Not optional. Section 3 below explains which denominators come from where.

## Step 1b — denominator-only type counts (D calls per org)

`descriptionCoverage` reports ten areas; the Overview's six curated types only supply denominators
for six of them. Without these four, record types, profiles, permission sets and permission set
groups blank for every org — honest, but it empties the template's second section.

For each, `query_metadata(refModelId, metadataList=[<type>], mode="manifest")`
→ `raw/<date>/<slug>/query_metadata/manifest__type__<snake_case_type>.json`

| Type | Supplies the denominator for |
|---|---|
| `Record Type` | Record types coverage |
| `Profile` | Profiles coverage |
| `Permission Set` | Permission sets coverage |
| `Permission Set Group` | Perm set groups coverage |

Record them in the manifest as `denominatorTypes`, a separate field from `curatedTypes`:

```json
"curatedTypes": ["Field", "Custom Object", "Flow", "Apex Class", "Apex Trigger", "Validation Rule"],
"denominatorTypes": ["Record Type", "Profile", "Permission Set", "Permission Set Group"]
```

Keep them separate. `curatedTypes` drives the Overview's columns and its `nodes_*` metrics; merging
these four in would silently add four columns and 24 metric rows to a template that does not need
them, and would charge every Overview run four extra calls per org.

A reason to pull these from `query_metadata` rather than reading them off
`get_org_structure.permissionControls`: the two disagree, unpredictably. Observed behaviour:
Profile counts matched exactly in every org, while Permission Set counts differed in every one;
one org read 103 here against 46 in the summary tool. Same tool, same org, different basis.

## Step 2 — tech debt summary (1 call per org)

`get_tech_debt_summary(refModelId)` → `raw/<date>/<slug>/get_tech_debt_summary.json`

Pull `get_tech_debt_summary` as JavaScript Object Notation (JSON). Its comma-separated values
(CSV) output can omit an all-empty column, which would make a missing field look absent.

The response carries four sections:

| Section | Shape | Use |
|---|---|---|
| `techDebtSeverity` | flat counts: `processBuilders`, `workflowRules`, `customProfiles`, `inactiveMetadata`, `fieldsDeletion`, `outdatedApi` | raw counts — never ranked bare |
| `inactiveMetadata` | `{type: count}`, only types with a non-zero count | raw counts; absent key means zero-or-absent, see below |
| `outdatedAPIVersions` | array-of-arrays: row 0 is the header, rows 1..n are `[version, per-type counts...]` | raw counts by API version |
| `descriptionCoverage` | `[{key, value}]` percentages | the only Ranked Comparison input |

### Parsing notes

- `outdatedAPIVersions` can be a header row and nothing else. Org C returns exactly
  `[["Version","Flow","Apex Class",...]]` with no data rows. Code that assumes `rows[1]` exists
  crashes on a perfectly healthy org. Treat length 1 as "no outdated API versions".
- `inactiveMetadata` omits zero keys. It is a sparse map, not a fixed shape. A type missing from
  it is not evidence of anything on its own — resolve it against the org's curated counts and
  presence list exactly like any other zero.
- Orgs with `syncStatus: failed` return complete, well-formed summaries. A stale org looks
  healthy at the payload level; only `syncTime` reveals that the data is months old. Never infer
  freshness from the presence or shape of a summary.

## Step 3 — the denominator rule (this is the whole template)

**`descriptionCoverage` reports 0 both for "nothing is documented" and for "there is nothing to
document". They are not distinguishable within the payload.** For example:

| Org | `descriptionCoverage` "Validation rules" | Actual Validation Rules |
|---|---|---|
| Org A | 0 | 63 |
| Org B | 0 | 0 |
| Org C | 0 | 3 |
| Org D | 100 | 162 |

Org A has 63 validation rules and documents none of them. Org B has none at all. Ranking
these two side by side on that number scores a clean org and a genuinely undocumented one
identically — a plausible-looking falsehood the reader cannot detect, so the ratio must be blanked until its denominator is known.

The same trap fires on Org C's `Flows: 0` coverage: that org has no flows
(`Flow` is absent from its `type` options entirely).

So, for every coverage ratio:

1. Take the denominator from the Overview's curated manifest counts for the matching type.
2. If the denominator is 0 or the type is typed `absent` / `not_synced` / `unknown`, blank the
   ratio and say why. Do not render 0. Do not include the org in that ratio's peer set.
3. Only ratios with a confirmed non-zero denominator enter a ranking or an outlier calculation.

`descriptionCoverage` keys are plural display labels (`Validation rules`, `Apex classes`,
`Perm set groups`) and do not match metadata type names. Map them explicitly; do not derive the
mapping by string munging.

## Step 4 — comparison rules

Section 1 — Outlier Surfacing (primary). Peer-median baseline, extremes named.

The peer set is the implementation group by default. **Outlier statistics require N >= 8 peers.**
Observed spaces hold a single-digit number of orgs across several implementations, so on that data
the script must use extremes-and-spread wording and emit zero outlier flags. `helpers.outlier_verdict` owns this
switch; the render never reimplements it and never softens it.

Below 8 peers the words "outlier", "anomaly" and "significant" do not appear. Name the extremes,
show the spread, stop.

Section 2 — Ranked Comparison, restricted. Only within-org ratios with a known good direction —
in practice only `descriptionCoverage`, where higher is better. Never rank
`techDebtSeverity.outdatedApi`, `inactiveMetadata`, or any other raw count: they scale with org
size and with managed-package content, not with quality.

Concretely: Org A reports `outdatedApi: 79` against Org C's `0`, but Org A is 76%
managed-package nodes. The managed share does not establish which components carry that debt. Ranking the raw count
would conflate org size and package content with quality.

No composite debt score. This template has no weights or component contract for one. For a
customer-requested composite, use the Architecture Scorecard worked example in
`references/comparison-patterns.md` and show every component and weight.

## Step 5 — render (deferred)

The Technical Debt renderer is deferred. Its source at
`assets/deferred/render_technical_debt_comparison.py` is a design reference, not a runnable entry
point. Redesign it around extremes and spread first; add median+MAD only as the rare N >= 8 upgrade.
In observed spaces the largest peer group is about 3, and most groups are singletons.

## Meaning lives elsewhere

This spec pulls and composes. For what any individual flag means — why a profile counts as custom,
what makes metadata inactive, which API versions matter — load `elements-tech-debt`. Do not
restate its definitions here; one place for domain meaning.
