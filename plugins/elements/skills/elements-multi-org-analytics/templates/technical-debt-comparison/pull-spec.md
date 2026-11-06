# Pull spec: Technical Debt Comparison

## Contents

- [Step 1: everything in the Multi-Org Overview pull spec](#step-1-everything-in-the-multi-org-overview-pull-spec)
- [Step 1b: denominator-only type counts (D calls per org)](#step-1b-denominator-only-type-counts-d-calls-per-org)
- [Step 2: tech debt summary (1 call per org)](#step-2-tech-debt-summary-1-call-per-org)
- [Step 3: the denominator rule (this is the whole template)](#step-3-the-denominator-rule-this-is-the-whole-template)
- [Step 4: comparison rules](#step-4-comparison-rules)
- [Step 5: render (deferred)](#step-5-render-deferred)
- [Meaning lives elsewhere](#meaning-lives-elsewhere)

Builds on the Multi-Org Overview pull. Run that spec first, into the same dated directory. This
template needs the Overview's manifest counts as **denominators**, and without them its ratios are
not safe to render.

Access and refusals: [Tool contracts](../../references/tool-contracts.md).
File recovery: [Recipe contract, section 1](../../references/recipe-contract.md#1-the-snapshot-store).
Run the planner with `--with-tech-debt`; its call count includes the added denominator and summary calls.

## Step 1: everything in the Multi-Org Overview pull spec

Discovery, per-org totals, managed/custom split, curated type counts, query schemas, freshness responses and manifests.
Not optional. Section 3 below explains which denominators come from where.

## Step 1b: denominator-only type counts (D calls per org)

`descriptions_filled_out` reports ten areas; the Overview's six curated types only supply denominators
for six of them. Without these four, record types, profiles, permission sets and permission set
groups blank for every org, honest, but it empties the template's second section.

For each type outside the chosen curated list, `list_metadata_by_criteria(refModelId, metadataList=[<type>], mode="manifest",
filters=[{column:"status",operator:"neq",value:"deleted"}])`
→ `raw/<date>/<slug>/list_metadata_by_criteria/manifest__type__<snake_case_type>.json`

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

Record only added types in `denominatorTypes`; types already curated reuse their counts.
Keep them separate. `curatedTypes` drives the Overview's columns and its `nodes_*` metrics; merging
these four in would silently add four columns and 24 metric rows to a template that does not need
them, and would charge every Overview run four extra calls per org.

## Step 2: tech debt summary (1 call per org)

`understand_org_health({refModelId,teamId,area:"tech_debt",delivery:"file"})` → `raw/<date>/<slug>/understand_org_health__tech_debt.json`

Store the JavaScript Object Notation (JSON) payload verbatim. Read `{area,refModelId,items,cacheAge,dataAsOf}` and
select items by `key`; item order is independent of meaning.

| Item key | Shape | Use |
|---|---|---|
| `tech_debt_summary` | `breakdown:[{key,value}]`, `total:null`; categories include `processBuilders`, `workflowRules`, `customProfiles`, `inactiveMetadata`, `fieldsDeletion`, `outdatedApi` | raw counts |
| `inactive_metadata` | sparse `breakdown:[{key:<type>,value:<count>}]` | raw counts; resolve missing types against counts and presence |
| `outdated_api_version_<version>` | one item per version, `detail.apiVersion` and type-count `breakdown` | raw counts by application programming interface (API) version |
| `descriptions_filled_out` | percentage `breakdown:[{key,value}]`, `unit:"percent"`, `total:null` | Ranked Comparison input |

An item with `available:false` and `reason` blanks its dimension. A successful response that omits
`descriptions_filled_out` makes documentation coverage unavailable for that org: name the org and
missing item in the output, and leave coverage blank rather than treating it as zero. Treat an unavailable
`outdated_api_version` item as missing evidence; a successful response with no version items
has no outdated-version rows. Overlapping counts and percentages have `total:null`, so totals
are read only when the item defines an additive total. Summary freshness comes from `dataAsOf`.

## Step 3: the denominator rule (this is the whole template)

The [card's denominator example](card.md#guardrails-as-code-this-template-is-the-showcase)
shows why a reported 0% requires a confirmed nonzero denominator. Schema type options alone
supply no evidence that an org has no flows.

For every coverage ratio:

1. Take the denominator from the Overview's curated manifest counts for the matching type.
2. If the denominator is 0 or the type is typed `absent` / `not_synced` / `unknown`, blank the
   ratio and say why. Do not render 0. Do not include the org in that ratio's peer set.
3. Only ratios with a confirmed non-zero denominator enter a ranking or an outlier calculation.

`descriptions_filled_out` keys are plural display labels (`Validation rules`, `Apex classes`,
`Perm set groups`) and do not match metadata type names. Map them explicitly; do not derive the
mapping by string munging.

## Step 4: comparison rules

Section 1: Outlier Surfacing (primary). Peer-median baseline, extremes named.

The peer set is the implementation group by default. **Outlier statistics require N >= 8 peers.**
Observed spaces hold a single-digit number of orgs across several implementations, so on that data
the script must use extremes-and-spread wording and emit zero outlier flags. `helpers.outlier_verdict` owns this
switch; the render never reimplements it and never softens it.

Below 8 peers the words "outlier", "anomaly" and "significant" do not appear. Name the extremes,
show the spread, stop.

Section 2: Ranked Comparison, restricted. Only within-org ratios with a known good direction;
in practice only `descriptions_filled_out`, where higher is better. Never rank
`tech_debt_summary` category `outdatedApi`, `inactiveMetadata`, or any other raw count: they scale with org
size and with managed-package content, not with quality.

No composite debt score. This template has no weights or component contract for one. For a
customer-requested composite, use the Architecture Scorecard worked example in
[Comparison patterns](../../references/comparison-patterns.md) and show every component and weight.

## Step 5: render (deferred)

This template has no renderer. Read
[the design reference](../../assets/deferred/render_technical_debt_comparison.py) for design context;
it is not a runnable entry point. Deliver the pull and its coverage limitations; render the Overview
baseline using its supported command.

## Meaning lives elsewhere

This spec pulls and composes. For what any individual flag means: why a profile counts as custom,
what makes metadata inactive, which API versions matter, load `elements-tech-debt`. Do not
restate its definitions here; one place for domain meaning.
