# Pull spec — Multi-Org Overview

The exact Model Context Protocol (MCP) call sequence that fills one dated snapshot directory. Follow it literally; it is
re-runnable without this skill loaded. Re-running a date overwrites only that date.

## Cost

```
calls = 3 + orgs x (2 + T + p)
```

where `T` is the number of curated types (6 by default) and `p` is 1 for an org if any
curated type returned 0, otherwise 0. At 6 orgs and 6 types the pull costs 51 calls when
every org needs a presence probe, about 1 minute at 50 calls/min. At 100 orgs it costs
803 calls with no presence probes, about 16 minutes.

Make the calls sequentially, one at a time, at ~50 calls/min. The 60 calls/min budget belongs to the
token and other sessions on it spend it too, so a lockout can arrive below the pace. Rate limiting
comes back as a tool error, `{"error":"rate_limited", …, "retryAfter":60}`, not an HTTP status: wait
`retryAfter` seconds, resume at a slower pace, and double the wait if the next call is also
`rate_limited`. Every file is written per-org, so resuming re-runs only the orgs whose files are
missing.

Pass the chosen `teamId` on every call below. Do not call `set_active_space`; it changes shared
session state that other work on the same token relies on.

## Step 1 — discovery (3 calls, once per run)

1. `list_authorized_spaces` — pick the Space.
2. `list_reference_models(teamId)` — this is the org list.
3. `list_supported_metadata_types(teamId)` — the global list of types Elements can sync at all
   (about 95). Write it verbatim to `raw/<date>/list_supported_metadata_types.json`.

Write the `list_reference_models` response to `raw/<date>/list_reference_models.json`, adding one
top-level field after confirmation: `confirmedOrgs`, the list of confirmed `refModelId` values.
Keep the returned reference-model entries otherwise verbatim. The renderer reads `confirmedOrgs`:
a confirmed org with no directory, or whose directory has no `manifest.json` because the pull
stopped before step 2e, is named on the page as "confirmed but not pulled" with its reason and is
counted in the header. An org left out of `confirmedOrgs` is out of scope: it has no directory, and
if a directory for it is present anyway, the renderer leaves it out of every count and names it on
the Evidence tab as outside `confirmedOrgs`. A directory's `manifest.json` `refModelId` alone decides
whether it is in scope; the directory name matters only for a directory with no manifest. A
confirmed org whose directory holds the manifest of an org outside `confirmedOrgs` is named as not pulled; a directory whose manifest disagrees with its own name or files, or belongs to another confirmed org, stops the render with an error naming the directory. A record
without `confirmedOrgs` renders, with an Evidence note that the two cases cannot be told apart.

Store the supported-type response so the renderer can distinguish a type Elements does not sync
from a type absent in one org.

Take from each entry: `refModelId`, `name`, `implementation.name`, `syncStatus`, `lastSyncCompleted`.

`syncStatus` values: `updated` (last sync succeeded), `failed` (reported as sync failing) and
`inProgress` (reported as sync running: the counts are taken while a sync is running).

**Confirm the org list with the user before pulling.** Org selection is customer configuration, not
agent inference. Persist that selection as `confirmedOrgs` in the per-date discovery record before
the per-org pull begins. If the Space holds one org, this is a single-org question: say so and
offer `elements-org-diagnostic`, and pull only if the user still wants a baseline for later orgs.

Org slug. Slug is `<implementation-name>--<org-name>`, both lowercased with non-alphanumerics
collapsed to `-`. Do not slug on org name alone: org names are not unique across
implementations. One observed space has three separate orgs all named "Production".

**Check for collisions before writing anything.** Build every confirmed org's slug first. If two
match — two orgs in one implementation whose names normalize identically, such as `QA 1` and `QA-1` —
stop with an error naming both `refModelId`s. One directory would otherwise hold two orgs and
silently overwrite one.

## Step 2 — per-org pull

For each confirmed org, one call at a time:

### 2a. Total nodes (1 call)

`query_metadata(refModelId, allNodes=true, mode="manifest")`
→ `raw/<date>/<slug>/query_metadata/manifest__all_nodes.json`

`totalItems` is the org's total node count. Manifest mode returns counts only — no rows — so this is
one cheap call regardless of org size (observed orgs range from about 8k to over 250k nodes).

Note the denominator: `query_metadata` excludes `status: deleted` (change-tracking tombstones) unless
you filter for it explicitly. Every count in this spec is therefore "live nodes", consistently.

### 2b. Managed/custom split (1 call)

`query_metadata(refModelId, allNodes=true, mode="manifest",
filters=[{column:"manage_package", operator:"eq", value:true}])`
→ `raw/<date>/<slug>/query_metadata/manifest__all_nodes__managed.json`

`custom_nodes = total_nodes - managed_nodes`. This split is not optional: it is normalization tier 3
and it must be applied before any cross-org comparison. In one space the split is the whole
story: Org A is 76% managed-package nodes (19,842 of 26,103) while Org B
is 0.7% (69 of 9,563), so their raw totals of 26k vs 9.5k say almost nothing about how much either
customer built.

### 2c. Curated type counts (T calls, 6 by default)

For each curated type, `query_metadata(refModelId, metadataList=[<type>], mode="manifest")`
→ `raw/<date>/<slug>/query_metadata/manifest__type__<snake_case_type>.json`

Default curated types:

| Type | Why |
|---|---|
| `Field` | Largest population in every validated org; the size proxy |
| `Custom Object` | Data model footprint |
| `Flow` | Current-generation automation |
| `Apex Class` | Code footprint |
| `Apex Trigger` | Code footprint, separated from classes on purpose |
| `Validation Rule` | Config-level business logic |

The list is a scope fence, not a boundary — widen it in a bespoke recipe and the cost formula tells
you what that costs. Type names must come from `list_supported_metadata_types`; an unsupported name
fails with an opaque `mcp_tool_failed` rather than a helpful error (observed behaviour: `"Visualforce
Page"` fails, the supported spelling is `"Apex Page"`).

### 2d. Presence probe (0 or 1 call — only when a curated type returned 0)

**A count of 0 does not mean the type is absent, and `query_metadata` cannot tell you which it is.**
A valid type name that the org has none of returns `totalItems: 0`, exactly like a type the org has
but is empty of. `Validation Rule` returns 0 on Org B and 63 on Org A, from identical calls.

So when — and only when — at least one curated type returned 0 for an org:

`list_metadata_columns(refModelId, allNodes=true)` → write the response verbatim to
`raw/<date>/<slug>/types_present.json`. The renderer reads the `type` column's `options` itself;
each option is an `{id, label}` pair and both count as presence, because an id can differ from the
supported-type name (id `Field Update`, label `Workflow Field Update`).

That list is org-derived: one observed org returns 42 types, another 33. A curated type in the list
is present in the org; a curated type absent from it is not present in that org.

Skip this call when every curated type returned a non-zero count — a non-zero count is self-evident
presence. Typically only a few orgs need the probe.

This yields the three-way typing the render requires:

| Condition | Typed as | Rendered as |
|---|---|---|
| Count 0 and not in `list_supported_metadata_types` | not synced by Elements | blanked, with reason |
| Supported, absent from the org's `type` options | not present in this org | `—`, with reason |
| Present, `totalItems: 0` | observed zero | `0` |

A positive `query_metadata` count always wins even when `list_supported_metadata_types` omits the
type. Render the observed value and record a Known unknown that names the type and both disagreeing
sources; never reject the snapshot for this contradiction.

### 2e. Manifest

Write `raw/<date>/<slug>/manifest.json` with: `snapshotDate`, `pulledAt` (UTC), `teamId`,
`spaceName`, `refModelId`, `orgName`, `orgSlug`, `implementationName`, `syncStatus`, `syncTime`
(= `lastSyncCompleted` verbatim), `skillVersion`, `mcpBaselineVersion`, `recipe`, `curatedTypes`,
`typesPresentCaptured`, and a `files` map of every file written to the tool and arguments that
produced it.

`syncTime` is `lastSyncCompleted` copied verbatim, never reformatted and never derived from
`updatedAt`. `updatedAt` means "record touched"; on an org whose sync is failing it can read weeks
newer than `lastSyncCompleted`.

## Step 3 — derive and render

```
python3 scripts/render_multi_org_overview.py --snapshots <store> --date <date> --out <file>.html \
  [--peer-groups <groups.json>]
```

The render script regenerates `derived/metrics.csv` from raw, then writes the HTML. Raw is never
edited. Re-running the render is side-effect-free apart from those two outputs.

## Row-level pulls are not part of this template

Observed orgs range from about 8k to over 250k nodes, so a row-level `allNodes` pull is roughly 170
to over 5,000 pages. This template's questions are all answerable from manifest counts, so it never pulls rows.

If a bespoke variant does need rows, use `format:"csv"`. The first column is `_id`, a 24-character
hexadecimal node identifier; use it as the row identifier. Date columns contain International
Organization for Standardization (ISO) 8601 strings. Assemble pages with keep page 1 whole, strip
line 1 of every later page, append. Never `cat` CSV pages because every page carries its own header.
Page headers are byte-identical across pages of the same query, which makes stripping safe.

Two CSV facts worth knowing before parsing: booleans come back as their option labels, not
`true`/`false` (`manage_package` → `Yes`/`No`, `active` → `Active`/`Inactive`), and only
`query_metadata` builds its header from the requested column list. The other tools sharing the
serializer keep union-of-keys CSV where an all-empty column can still vanish — pull those as JSON.
