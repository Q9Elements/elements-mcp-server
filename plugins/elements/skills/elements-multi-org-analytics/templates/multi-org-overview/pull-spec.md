# Pull spec: Multi-Org Overview

## Contents

- [Step 1: discovery](#step-1-discovery)
- [Step 2: per-org pull](#step-2-per-org-pull)
- [Step 3: derive and render](#step-3-derive-and-render)
- [Row-level pulls](#row-level-pulls)

The exact Model Context Protocol (MCP) call sequence that fills one dated snapshot directory. Follow it literally; it is
re-runnable without this skill loaded. Re-running a date overwrites only that date.

Access and refusals: [Tool contracts](../../references/tool-contracts.md).
File recovery and storage: [Recipe contract, section 1](../../references/recipe-contract.md#1-the-snapshot-store).
Run `<skill-dir>/scripts/plan_pull.py` from the user's working directory as directed in workflow
step 3; its ordered plan owns slugs and cost. The `raw/` and `derived/` paths below are inside the
`snapshots/` store in that working directory.
Pass the chosen `teamId` on every data call below.

## Step 1: discovery

1. `get_space_context({skip:0,pageSize:50})`: read `authorized` and `pagination`.
   Resolve whole-result files and nested moved-to-file values first. Follow
   `_truncated.nextSkip`, otherwise returned `nextSkip`, otherwise advance by actual authorized entries,
   until `pagination.hasMore` is false. Pick the Space from the complete list. `active` describes
   session context; `list_reference_models.activeSpace` confirms the explicit data-call Space.
2. `list_reference_models({teamId,delivery:"file"})`: this is the org list. It accepts no paging
   arguments. Read a budget-fit reply inline; otherwise resolve its complete file and any nested
   moved-to-file array before reading `referenceModels` and `count`. If complete recovery fails,
   report incomplete discovery before confirmation.
3. After confirming the orgs, `describe_metadata_schema({refModelId:<first confirmed reference model>,teamId,delivery:"file"})`:
   store `types:[{name,salesforceName,aliases}]` verbatim at
   `raw/<date>/describe_metadata_schema.json`. Record the call as
   `discoveryCalls["describe_metadata_schema.json"]:{tool:"describe_metadata_schema",arguments:{refModelId,teamId,delivery:"file"}}`
   in the discovery record. The registry describes accepted types, separately from per-org presence.
   If discovery or this schema call is delivered as a file, follow the response-file rules in
   [Recipe contract](../../references/recipe-contract.md). A schema authorization failure blanks type classification.

Write the `list_reference_models` response to `raw/<date>/list_reference_models.json`, adding
`confirmedOrgs` (the confirmed `refModelId` values) and `discoveryCalls` (global-file provenance).
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

Take from each entry: `refModelId`, `name`, `implementation.name` and access fields.
Persist org selection before the per-org pull, as directed in workflow step 2.
Use the planner's org paths; a collision stops the pull before any directory is written.

## Step 2: per-org pull

For each confirmed org, one call at a time. Before count
queries, call `describe_metadata_schema({refModelId,teamId,allNodes:true,delivery:"file"})`, save it as
`types_present.json` and validate the filter columns and operators. Follow the response and paging
rule in [Recipe contract](../../references/recipe-contract.md).
Then call `understand_org_health({refModelId,teamId,area:"structure",delivery:"file"})` and save
`understand_org_health__structure.json`. Apply the
[freshness fields contract](../../references/recipe-contract.md#freshness-fields-the-rules-that-matter).
Reuse the schema response for presence in Step 2d.

### 2a. Total nodes (1 call)

`list_metadata_by_criteria(refModelId, allNodes=true, mode="manifest",
filters=[{column:"status",operator:"neq",value:"deleted"}])`
→ `raw/<date>/<slug>/list_metadata_by_criteria/manifest__all_nodes.json`

`totalItems` is the org's total node count. Manifest mode returns counts only, one call regardless of org size.

The default query excludes `status:"deleted"` tombstones unless a status predicate or a MetaField
named `status` suppresses it. For consistent live-node denominators, use
`{column:"status",operator:"neq",value:"deleted"}` in every count query after schema discovery
confirms that `status` is the built-in component column. A conflicting MetaField requires resolving
the correct status column before labelling the counts live nodes.

### 2b. Managed/custom split (1 call)

`list_metadata_by_criteria(refModelId, allNodes=true, mode="manifest",
filters=[{column:"manage_package",operator:"eq",value:true},
{column:"status",operator:"neq",value:"deleted"}])`
→ `raw/<date>/<slug>/list_metadata_by_criteria/manifest__all_nodes__managed.json`

`custom_nodes = total_nodes - managed_nodes`. Apply the
[normalization tiers](../../references/comparison-patterns.md#the-three-normalization-tiers).

### 2c. Curated type counts (T calls, 6 by default)

For each curated type, `list_metadata_by_criteria(refModelId, metadataList=[<type>], mode="manifest",
filters=[{column:"status",operator:"neq",value:"deleted"}])`
→ `raw/<date>/<slug>/list_metadata_by_criteria/manifest__type__<snake_case_type>.json`

Default curated types:

| Type | Why |
|---|---|
| `Field` | Largest population in every validated org; the size proxy |
| `Custom Object` | Salesforce schema footprint |
| `Flow` | Current-generation automation |
| `Apex Class` | Code footprint |
| `Apex Trigger` | Code footprint, separated from classes on purpose |
| `Validation Rule` | Config-level business logic |

The list is a scope fence, not a boundary; widen it in a bespoke recipe and the planner reports
the call cost. Type names come from `describe_metadata_schema.types[].name`. Unknown names return
`invalid_input`. Runtime registry membership is discovered from the response.

### 2d. Interpret presence (reuse the per-org schema call)

Apply [Zero is not a default](../../references/recipe-contract.md#zero-is-not-a-default)
to `totalItems` and `types_present.json`; that contract defines the four presence states,
customer-supplied inventory evidence and positive-count disagreements.

### 2e. Manifest

Write `raw/<date>/<slug>/manifest.json` with: `snapshotDate`, `pulledAt` (Coordinated Universal Time, UTC), `teamId`,
`spaceName`, `refModelId`, `orgName`, `orgSlug`, `implementationName`, `syncStatus`, `syncTime`
(= health `dataAsOf` verbatim), `skillVersion`, `mcpBaselineVersion`, `recipe`, `curatedTypes`,
`typesPresentCaptured`, and a `files` map of every file written to the tool and arguments that
produced it.

Use the manifest schema and freshness rules in [Recipe contract, section 2](../../references/recipe-contract.md#2-manifestjson).

## Step 3: derive and render

```
python3 <skill-dir>/scripts/render_multi_org_overview.py --snapshots <store> --date <date> --out <file>.html \
  [--peer-groups <groups.json>]
```

The render script regenerates `derived/metrics.csv` from raw, then writes the Hypertext Markup Language (HTML). Raw is never
edited. Re-running the render is side-effect-free apart from those two outputs.

## Row-level pulls

This template answers its questions from manifest counts. Before extending it with rows, read
[Row pulls](../../references/row-pulls.md).
