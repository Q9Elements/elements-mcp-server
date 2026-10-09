---
name: elements-multi-org-analytics
description: Compose the single-org Elements MCP tools into reliable cross-org analytics over many Salesforce orgs in one Space - discover the orgs, fan out the same query per org, write dated snapshots to disk, and render a self-contained HTML artifact whose every number traces back to a raw MCP response. Use when the question spans more than one org, e.g. "compare our orgs", "across all our orgs", "which org has the most X", "how does our sandbox differ from prod", "give me an overview of our Salesforce orgs", or anything phrased about an estate or a multi-org landscape. Do NOT use for a deep-dive on a single org - use elements-org-diagnostic, elements-tech-debt or elements-metadata; do NOT use to explain what an individual flag or metric means, which belongs to the matching single-org skill.
---

# elements-multi-org-analytics

Elements Model Context Protocol (MCP) discovery tools find the Space and its orgs. This skill composes
per-org metadata answers into cross-org analytics that hold up — with per-org freshness stamps, honest
gaps, and a re-runnable recipe instead of a one-off answer.

Deliver a recipe: pull instructions that write dated
snapshots to disk, plus a Python script that renders those snapshots into static, self-contained
Hypertext Markup Language (HTML) a customer can email to someone with no Elements access and no AI.

> Prerequisite: the rest of the elements skill suite, satisfied by construction — the plugin
> bundles it. Cross-org work needs the same Space-level licences the single-org tools need; an
> unlicensed tool blanks one dimension of a comparison, never the whole artifact.

Requires: Enterprise Space with an Analytics Cloud license.

## Concepts

- One Space (`teamId`) holds N Salesforce connections and N reference models — the synced,
  analyzable copy of each org. N orgs / N reference models / one Space is the intended shape.
- `refModelId` is the addressing unit for per-org queries. Pass one scalar id per
  query; discovery tools list the available Spaces, models, and metadata types. Raw Salesforce `orgId` is display-only.
- `list_reference_models` returns only what the caller may see. Per-org role-based access control (RBAC) inside the Space is
  real: a user can see org A and not org C. Your org list is already correctly scoped; never work
  around a missing org.
- Implementation grouping comes from the same call and is the default peer key.
- Prod/sandbox lineage is not exposed over MCP. `list_reference_models` returns
  `implementation`, `sourceType` (always `salesforce`), `orgId`, `name` and the sync fields — and
  nothing that says which org is production and which is its sandbox. Do not infer it from org
  names: "Full sandbox" reads obvious and "Production" does not distinguish three different
  orgs that all carry that name. Lineage, when a comparison needs it, is customer-declared like
  any other peer grouping, and is shown on the page.

## Core workflow

Discover → confirm → fan out → snapshot → render.

1. `list_authorized_spaces` → `list_reference_models(teamId)`. Pass the chosen `teamId` on
   every call of the pull. Do not call `set_active_space`: it changes shared session state, and
   other work running on the same token would move to the new Space mid-pull.
2. **Confirm the org list with the user.** Org selection is customer configuration, not agent
   inference. The confirmed list is persisted as `confirmedOrgs` in the discovery record
   (`list_reference_models.json`); manifests do not carry it.
   - One org in the Space (or one confirmed): this is a single-org question. Say so and offer
     `elements-org-diagnostic`. Render the Overview only if the user still wants a baseline for
     later orgs; the renderer then titles it "Single-Org Overview" and says so on the page.
3. Fan out the same query per org: scalar `refModelId` calls made sequentially, one at a time,
   paced to ~50 calls/min. Attempt-and-classify: a missing tool or an authorization failure is an
   expected runtime condition, caught and labelled, never fatal.
4. Write dated snapshots to disk. See `references/recipe-contract.md` for the layout and the
   manifest schema.
5. Run the template's render script. It regenerates `metrics.csv` from raw, then writes the HTML.

For large pulls, finish the refresh in one session and analyze the stored manifests and
`metrics.csv` in another. This keeps per-org tool payloads out of the analysis context.

### Org slugs

`<implementation-name>--<org-name>`, lowercased with non-alphanumerics collapsed to `-`. Org names
repeat across implementations (one observed space has three separate orgs all named "Production"),
so the implementation prefix is required.

Before writing any org directory, build the slugs for every confirmed org. If two match, stop with a
clear error naming both `refModelId`s; one directory would otherwise silently overwrite the other.

## The four comparison patterns

1. Cross-Org Aggregation — raw counts with explicit org-count denominators; nothing judged.
2. Outlier Surfacing — *the default framing* for quality questions; peer-median baseline,
   extremes named.
3. Ranked Comparison — only on within-org ratios with a known good direction. Never on raw
   counts. Composite scores must show components and weights.
4. Drift Detection — prod/sandbox pairs (the pairing must be customer-declared; see Concepts)
   and org-vs-itself over time (once snapshots accrue).

Full methodology, including the Architecture Scorecard worked example, is in
`references/comparison-patterns.md`.

## Normalization and guardrails

Three tiers, applied in order. (1) Within-org percentages compare directly. (2) Raw counts never
appear bare — always beside total node size and the custom/total share. (3) Managed-package vs
custom-built is split before any comparison.

Tier 3 is not optional. In one space an org at 26,103 total nodes is 76% managed-package
while another at 9,563 is 0.7%; by custom nodes the "bigger" org is the smaller build. Skipping the
split reverses the answer.

The listed MCP tools supply no per-user, per-license or per-data-volume denominators. Say so; do
not substitute a proxy.

The guardrails:

- Intentional difference ≠ deficiency. Structural differences are observations. Deficiency
  wording is earned only by good-direction ratios.
- Zero vs absent. Report a zero only after the manifest confirms the type exists in that org.
- Absence of metadata ≠ absence of capability. No flows may mean automation lives elsewhere.
  Type it as an inference gap.
- **No silent omission.** Every org or dimension excluded — by licensing, staleness, or a missing
  denominator — is named in the artifact, where it would have appeared.
- Staleness taints comparisons. Per-org freshness stamps always; stale orgs flagged; trend
  deltas exclude orgs stale before the window.
- **Outlier math is median + median absolute deviation (MAD) at N≥8, flag beyond 3 MADs.** Below ~8 peers,
  statistical outlier language is forbidden — name extremes, show spread.

Expect the below-8 branch to be the common case: peer groups are usually smaller than org counts.

### Zero vs absent, concretely

A count of `0` from `query_metadata` is ambiguous. A valid type name the org has none of returns
`totalItems: 0` — identical to a type that exists and is empty. Resolve it three ways:

| Condition | Typed as | Rendered as |
|---|---|---|
| Count 0 and not in `list_supported_metadata_types` | not synced by Elements | blanked, with reason |
| Supported, absent from the org's `type` options | not present in this org | `—`, with reason |
| Present, count 0 | observed zero | `0` |

The org's own type list comes from `list_metadata_columns(refModelId, allNodes=true)`: store the
response verbatim as `types_present.json` and the renderer reads the `type` column's options, where
an option's id and its label both count as presence. It is org-derived (one observed org returns 42
types, another 33). You only need this call when a count came back 0; a non-zero count is
self-evident presence.
A positive `query_metadata` count always wins even when `list_supported_metadata_types` omits the
type: render it and name both disagreeing sources in Known unknowns.

**Never print 0 for something you did not observe as zero.** In the derived layer that rule reads:
emit no row at all. A missing row means "not observed"; there is no sentinel value.

## Provenance and freshness

Each org's `manifest.json` carries the Space and reference-model ids, org and implementation names,
the tool and arguments behind every file, the pull timestamp, skill and baseline versions, and the
freshness fields.

- **`syncTime` is `lastSyncCompleted` verbatim.** Staleness is elapsed days since it.
- `syncStatus` is carried alongside. Observed values are `updated` (last sync succeeded),
  `failed` and `inProgress`. `failed` produces an independent sync failing signal; it does not
  make fresh data stale. `inProgress` produces a sync running signal: the counts were taken
  while a sync was running and may shift on the next pull. Staleness is driven only by elapsed days
  past the threshold. An org can be sync failing, stale, both, or neither.
- `updatedAt` is forbidden as a freshness input; it means "record touched". On an org whose
  sync is failing it can read weeks newer than the last successful sync.

A stale org's payloads look perfectly healthy. Summary tools return complete, well-formed
responses for orgs that have not synced in months. The stamp is the only signal — which is why every
artifact carries per-org stamps and separate header counts for stale and sync-failing orgs.

Every rendered observation traces in two hops: page → `metrics.csv` row → that org's
`manifest.json` → the raw file. Derived values have no comma-separated values (CSV) row; they name their contributing orgs
and observation inputs on the page. The load-bearing rule is **name stability** — rendered
observation metric names match the CSV verbatim, so a reader can grep for what they see. Add new
observation metrics; never rename old ones.

## Licensing degradation

Four points, in force always:

0. Scope discovery — the analyzable universe is the MCP-enabled Spaces the user can access.
1. Attempt-and-classify — tool absence and per-Space authorization failure are expected
   conditions. Attempt, catch, classify. Never die on them.
2. Per-dimension degradation — an unlicensed tool blanks one column of a comparison, never the
   whole artifact.
3. No silent omission — every org or dimension excluded by licensing is labelled in the output.

An absent tool-output file is licensing degradation, not store corruption: blank and label the
dependent dimension. A file that is present but invalid JavaScript Object Notation (JSON), lacks provenance, or contradicts its
directory identity remains a hard failure.

## Scale

Pace calls at about 50 per minute per token, leaving room below the observed 60-call rate limit.
Other sessions using the token consume the same budget.

- Disk-first at every N, including N=2. In-context analysis survives only as ad-hoc exploration
  at roughly ten orgs or fewer; a hundred orgs' summaries would cost 150–250k context tokens.
- Estimate calls before pulling: `calls ≈ discovery calls + orgs × (summary calls + Σ pages-per-scoped-type)`,
  `minutes ≈ calls ÷ 50`. If the estimate exceeds about 30 minutes, narrow the pull spec to avoid a long refresh.
- Prefer manifest-mode counts to row pulls. `query_metadata(mode:"manifest")` returns counts
  with no rows, one cheap call regardless of org size. Observed orgs range from about 8k to over 250k
  nodes, so a row-level `allNodes` pull is roughly 170 to over 5,000 pages per org. Most cross-org questions never need rows.
- Full re-pull always. No reliable change cursor exists over MCP. Do not substitute a
  `last_modified_date` filter — that is the Salesforce clock, not the Elements sync boundary, so it
  silently misses nodes that entered the Elements copy late.
- Rate limiting arrives as a tool error, not an HTTP status: `{"error":"rate_limited",
  "message":"Rate limit exceeded: 60 requests/minute per token; …","retryAfter":60}`. It is a rate
  limit, never a licensing gate. Wait `retryAfter` seconds, then resume sequentially at a slower
  pace, doubling the wait if the next call is also `rate_limited`. Per-org files make resume free.
- The workflow has been validated on a single-digit org count. Use the call estimate to plan larger pulls.

## Row-level pulls, when you do need rows

Use `format:"csv"` for `query_metadata`. The first column is `_id`, a 24-character hexadecimal node
identifier; use it as the row identifier. Date columns contain International Organization for Standardization (ISO) 8601 strings.

Paging: keep page 1 whole, strip line 1 of every later page, append. Never `cat` CSV pages —
every page carries its own header. Headers are byte-identical across pages of one query, which is
what makes stripping safe.

Two traps: CSV booleans come back as option labels, not `true`/`false` (`manage_package` →
`Yes`/`No`, `active` → `Active`/`Inactive`). And only `query_metadata` builds its header from the
requested column list — the other tools sharing the serializer keep union-of-keys CSV where an
all-empty column can vanish. Pull those as JSON.

Metadata type names must come from `list_supported_metadata_types`. An unsupported name fails with
an opaque error rather than a helpful one — Elements spells Visualforce pages `"Apex Page"`.

## Templates

Demonstrations, not boundaries. Customers chat their way to bespoke analytics; these show the shape.
Each directory holds a `card.md` (the question, pattern, metrics, customization points, scope fence)
and a `pull-spec.md` (the exact MCP call sequence).

- `templates/multi-org-overview/` — *"What do we have, across all our orgs?"* Cross-Org
  Aggregation, no judgments, and the trending demo: a trend section that self-activates once the
  store holds two dated snapshots. Start with it when the user wants an estate overview.
- `templates/technical-debt-comparison/` — *"Which orgs need cleanup attention, and is that real
  or just their size?"* Outlier Surfacing primary, restricted Ranked Comparison second. Requires
  the Overview pull in the same dated directory, because its ratios take their denominators from
  the Overview's counts. Its renderer is not yet available.


To show a customer the catalog, read the `card.md` files — they are the single source of truth — and
close with the invitation to go bespoke.

## First run

For an estate overview, use the prompt "Give me an overview of our Salesforce orgs."

That walks the Multi-Org Overview conversationally and does three jobs at once — hello-world,
install verifier, and the org-selection moment where the discovered org list is confirmed and
persisted. If discovery returns no Spaces, check the authorization. If it returns no reference models,
check connected orgs and the caller's access. Classify a missing tool by its documented plan,
license, and permission gates.

## Meaning lives in the sibling skills

This skill pulls and composes. It does not define domain terms. For what a flag, metric or component
*means*, load the matching single-org skill — `elements-tech-debt` for debt flags,
`elements-metadata` for a specific node, `elements-change-briefing` for node-level change detail.
One place for domain meaning, so interpretation cannot drift.

On Codex, invoke siblings explicitly by name (`$elements-tech-debt`) — skills can be silently
omitted from the initial listing under its metadata budget.

## Judgment posture

Analyst with receipts. Interpretation is welcome; every claim is typed. Unfootnoted text is
observed fact. Interpretive claims footnote into the Evidence tab and carry their evidence.
Prescriptions only on explicit request, framed as options with evidence.

Refuse an output that would be a plausible falsehood the reader cannot detect; qualify a
true output that needs context. Refuse: outlier language below N=8, invented freshness,
bare-count league tables, silent repair of missing data. Qualify: stale orgs, observed zeros,
structural differences, small peer groups.
