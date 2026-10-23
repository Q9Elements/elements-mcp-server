---
name: elements-metafields
description: Define, connect, populate, update, and verify customer MetaFields on Salesforce metadata with get_metafields, create_metafield, set_metafield_dependency, update_metafield, and set_metafield_values. Use when the user says "set up MetaFields", "classify our objects by X", "tag metadata with retention priority", "populate MetaFields in bulk", or "rename or narrow MetaFields". Do NOT use for filtered metadata lists (use elements-metadata-query), finding or explaining one named node (use elements-metadata), or choosing a classification methodology or field catalog (use the relevant playbook).
---

# elements-metafields

Define customer-created MetaFields through Model Context Protocol (MCP) tools, connect dependent picklists, classify
nodes, and verify results. Each MetaField is a queryable column, distinct from built-in node properties. The
engagement's playbook supplies the field catalog.

## Requirements and results

All tool groups require an unsuspended Space. Scopes below use the `mcp:metadata:
prefix. Reference model permissions and Space roles are separate.

| Tool group | Scope suffix | Access | Refusal |
|---|---|---|---|
| `get_metafields` | `read` | Space membership | `feature_not_enabled` |
| `search_metadata`, `get_metadata_component`, `describe_metadata_schema`, `list_metadata_by_criteria` | `read` | Reference model view | `not_found` |
| `create_metafield`, `update_metafield`, `set_metafield_dependency` | `write` | Space admin | `access_denied` |
| `set_metafield_values` | `write` | Reference model edit | `access_denied` or `not_found` |

Read `error` before optional `message`. Hydrate files and moved values before treating missing data as empty, including
with `fileError`. Request `delivery:"file"` on `get_metafields`, `describe_metadata_schema`, and `search_metadata`; omit
`delivery` on `list_metadata_by_criteria` in every mode. On a refusal, oversized reply, or search page, read [access and
results](references/access-and-results.md) for messages, hydration, and continuation. When several connected servers
expose the same tool, use the server for the environment the user names.

## 1. Discover the existing schema

Call `get_metafields({include:"definitions",teamId?,implementationId?,delivery:"file"})` first. The result describes one
implementation with its `name`; select a returned `allowedValues` identifier when requested, and repeat for each
selected implementation. Use the returned:

- `implementationId` for later reads and as `implementation` in `create_metafield`.
- `definitions[].id` for writes and `columnKey` for criteria queries.
- `definitions[].options[].id` and `label` to translate values.
- `availableMetadataTypes`, when returned to an admin, for `appliesTo`; the schema tool lists a different enum.
- `capacity` and `caller.canDefineFields` before definition or dependency writes. If the latter is false,
  ask a Space admin to perform those writes; continue reads, local previews, and permitted value writes.

`include` accepts `definitions`, `dependencies`, or `all` (default). `metafieldId` narrows definitions and participating
matrices.

## 2. Define only the missing fields

Each implementation holds 25 MetaFields, shared across engagements; MCP exposes no deletion tool. Calculate all missing
fields first and require `capacity.remaining` to cover them. Otherwise stop and ask the user to resolve the schema in
Elements before creating a partial catalog. Create one field per `create_metafield` call. Types: `text`, `longtext`,
`datetime`, `number`, `list`, `multi_picklist`. Options are required for the last two and rejected for the others.

| Property | Constraint |
|---|---|
| `title` | 2–60 characters; its snake_cased `columnKey` must be unique among sibling fields |
| `options` | 1–50; each `label` is 1–100 characters or an integer |
| `placeholder` | 2–60 characters |
| `min`, `max` | Integers or `null`, for `number` only |
| top-level `predefined` | `list` only; preselects the first option |
| option `predefined` | `multi_picklist` only; at most one option |

On a conflict, refresh definitions, adopt an exact-title match, or choose a distinct column key. Refresh after creation
to obtain generated field and option identifiers.

## 3. Wire dependent picklists

Before wiring a dependency or writing either side, read [dependent fields](references/dependent-fields.md). Confirm the
intended pair with the user before calling `set_metafield_dependency`; that reference gives pair constraints, matrix
construction, local previews, recovery, and the orphan sweep after reclassification.

## 4. Classify nodes in bulk

Scope every `nodeFilter` with `metadataList`; never set `allNodes:true` in a write filter. Before the first bulk write,
read [bulk writes](references/bulk-writes.md) for clearing, accounting, coverage, pacing, and the criteria file loop.
For selection construction, read [filter patterns](references/filter-patterns.md), including controller-value
decomposition. Use exactly one selector per value: `nodeFilter` for data-expressible populations, or `nodeIds` for
individual judgement and bounded, locally sorted top-N cohorts. Account for requested and skipped nodes. A filter
contains selection fields only, without columns, sorting, or paging. Discover filter columns with
`describe_metadata_schema({refModelId,metadataList,delivery:"file"})`: use `value`, `allowedOperators`, `filterable`,
and option `id`. `tags`, `optimization_status`, and `parent_manage_package` are display-only; use `parent_object` only
with its advertised operators. In criteria reads with explicit `columns`, include every filter column or the call is
rejected.

Write a local plan with the selection, manifest pre-count, intended counts per value, and exact assignments. Validate
identifiers, eligibility, and scope against the returned schema before execution. Picklist writes use option
identifiers; `multi_picklist` uses an array. Group operations under `assignments[].values[]`. Synthetic request, with
fake identifiers for reference model, field, option:

```json
{"refModelId":"aaaaaaaaaaaaaaaaaaaa0301","assignments":[{"metafieldId":"aaaaaaaaaaaaaaaaaaaa0302","values":[{"value":"aaaaaaaaaaaaaaaaaaaa0303","nodeFilter":{"metadataList":["Field"],"filters":[{"column":"retention","operator":"is_exists","value":false}]}}]}]}
```

Responses contain `results`, `dispatch`, and `capsApplied`: at most 40 operations, 4,000 node references, and 40 write
chunks per call. Write-free refusals name the fix: split or shrink on `batch_too_large`; add a target-field guard on
`filter_resolves_too_many`, or narrow a bounded cohort. For example, `resolved:5000,written:4000,remaining:1000`
requires another self-draining call.

```text
- [ ] Validate the plan and manifest pre-count before the first write.
- [ ] Inspect resolved, exclusions, failures, unknown outcomes, and skip samples after each call.
- [ ] Stop on drainStalled or fullySkipped and report the affected coverage.
- [ ] Reconcile unknown outcomes by reading before retrying.
- [ ] For a self-draining operation, reissue the byte-identical call until remaining is 0.
- [ ] Verify every intended target-value count; fix and re-run until it passes.
```

## 5. Verify by reading

For each target value, query `list_metadata_by_criteria` with `refModelId`, `mode:"manifest"`, the cohort's
`metadataList`, filter columns in `columns`, and `eq` on the target `columnKey`. Compare `totalItems` with the plan's
intended count. A drained filter alone proves no coverage. Each query verifies one reference model; repeat for every
reference model in scope. Report terminal exclusions and unresolved outcomes.

## Destructive edits

Validate title updates against step 2's column-key constraint.
`update_metafield` requires a changed property: `title`, `appliesTo`, `options`, `predefined`, `min`, `max`, or
`placeholder`. Renaming an option preserves values when its existing `id` is kept; an id-less option matches by label,
creates a new option if unmatched, and removes omitted options. Narrowing `appliesTo` or removing options purges values
across every reference model and synced org in the implementation. Write and validate a local change plan: pre-count
populated nodes with `is_exists:true` before narrowing types, or `eq` on each removed option, across affected reference
models. Call without `confirm`; inspect `{applied:false,preview,next}`, present the counts, and get explicit approval
before repeating with `confirm:true`. A zero-impact or nondestructive update can apply immediately. Compare returned
`queuedValueDeletions` with the pre-counts. Purges run asynchronously; pause and re-count until settled before judging
verification. For managed-package widening, read the eligibility section in [bulk writes](references/bulk-writes.md).
Fix and re-run verification until counts match the approved plan.

## Scope

| Request | Route |
|---|---|
| Set up, populate, rename, or narrow MetaFields | This workflow |
| Choose a methodology or field catalog | Relevant playbook |
| List metadata matching criteria | `elements-metadata-query` |
| Find or explain one named node | `elements-metadata` |
