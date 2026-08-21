---
name: elements-metafields
description: Define and populate the custom fields your Elements Space defines on Salesforce metadata. Use when the user says "set up MetaFields", "classify our objects by X", "tag metadata with retention priority", or "populate MetaFields in bulk". Drives discovery, definition, dependent-picklist wiring, classification, and verification. Do NOT use for a filtered metadata list (use elements-metadata-query); do NOT use to find or explain one named node (use elements-metadata); do NOT choose a classification methodology or field catalog—the methodology belongs in a playbook.
---

# elements-metafields

Define customer-created MetaFields on Salesforce metadata in Elements, connect dependent picklists,
classify nodes in bulk, and verify the result. MetaFields are distinct from Elements' built-in node
properties, although each MetaField also appears as a queryable column.

This skill provides the capability for any classification job. It does not decide which fields,
options, or matrices a particular engagement should use.

## Preconditions

- The Space must be Enterprise.
- Defining fields and dependencies requires Space admin. Populating values requires edit rights on
  the reference model.
- Start with `list_metafields` and inspect `caller.canDefineFields`. If it is `false`, stop any
  requested definition work and tell the user a Space admin must do it; existing fields can still be
  populated with model edit rights. The four definition tools are hidden from non-admin tokens: if
  `create_metafield` is absent, that is the non-admin case, not a missing feature.
- When several Spaces are authorized, pass the target `teamId` or establish the active Space first.

## Workflow

### 1. Discover the existing schema

Call `list_metafields` before creating or interpreting anything:

```
list_metafields(teamId?)
--> { implementations: [{ implementationId, capacity, metafields,
                           availableMetadataTypes? }],
      caller: { canDefineFields } }
```

Use the returned:

- `implementationId` for definition and dependency calls.
- `metafields[].id` for all writes, and `columnKey` for `query_metadata`.
- `options[].id` and `options[].label` to translate between stored values and human labels.
- `availableMetadataTypes` for `appliesTo`. It is admin-only. Do not substitute
  `list_supported_metadata_types`; that is a different enum and omits managed-package pseudo-types.
- `capacity` for the 25-field gate described below.

If a full listing is oversized, recover with `implementationId` and `metafieldId` filters. For an
oversized dependency listing, use `controllerMetafieldId` and `dependentMetafieldId` filters on
`list_metafield_dependencies`.

### 2. Define only the missing fields

Create fields one at a time with `create_metafield`; do not batch definition creation. Supported
types are `text`, `longtext`, `datetime`, `number`, `list`, and `multiPicklist`—there is no boolean
or checkbox type. List and multiPicklist fields require options, and options are rejected for every
other type.

The schema refuses a call outside these limits, so size the definition before sending it:

| Field | Limit |
|---|---|
| `title` | 2–60 characters. Its **snake_cased** form is the `columnKey` `query_metadata` filters on, so it must snake_case to something no sibling MetaField already produces |
| `options` | 1–50 per MetaField; each `label` is 1–100 characters or an integer |
| `placeholder` | 2–60 characters |
| `min` / `max` | `number` type only; integers, or `null` for no bound |

**Two different fields are called `predefined`.** The top-level `predefined` is `list` only and
preselects the first option. The `predefined` *inside* an option is `multiPicklist` only, and at most
one option may carry it.

Two distinct refusals guard the title, and they want different responses:

- **`metafield_title_exists`** — a MetaField with this exact title is already there. It carries
  `existingMetafieldId`: inspect and adopt that field rather than retrying creation.
- **`metafield_title_conflict`** — a *differently* titled sibling snake_cases to the same
  `columnKey` (so "Retention Priority" collides with "retention priority"). Pick a title with a
  distinct snake_cased form; there is nothing to adopt.

Refresh `list_metafields` after creation to obtain generated MetaField and option ids.

### 3. Wire dependent picklists

Use `create_metafield_dependency` only after both definitions and their option ids exist. The
controller must be `list`; the dependent must be `list` or `multiPicklist`; their `appliesTo` sets
must overlap. `relationMap` is keyed entirely by option ids and must include every controller option.
Use an explicit `[]` when a controller value permits no dependent value.

A dependency has one controller and one dependent. A rule that requires two simultaneous
controllers cannot be expressed as one matrix. `update_metafield_dependency` replaces only the
matrix; it cannot re-pair the fields. Use `list_metafield_dependencies` to inspect the raw map and
joined labels before changing it — `implementationId` is required, and the controller/dependent id
filters are the recovery path when a large implementation truncates the listing.

**Get the pairing right the first time: there is no delete tool.** Once two fields are paired,
availability rules block re-pairing that dependent, so a wrong pairing cannot be corrected over MCP.
The only ways out are removing it in the Elements UI, or neutralising it by mapping every controller
option to every dependent option. Confirm the pair with the user before calling
`create_metafield_dependency`.

**Before wiring a dependency or bulk-writing either side of one, read
[DEPENDENT-FIELDS.md](DEPENDENT-FIELDS.md)** — the matrix is a write gate, not an invariant:
re-classifying a controller strands existing dependent values (measured), empty-controller nodes
are unwritable and invisible to drain loops, and clearing is the one write the matrix can never
block. That file carries the worked orphan-sweep and two-pass population recipes.
### 4. Classify nodes in bulk

**Read [BULK-WRITES.md](BULK-WRITES.md) before the first bulk write** — clearing semantics per type,
dependent-value decomposition, the drain loop's accounting, and the cases that loop silently misses.
For selection *shapes* read [FILTER-PATTERNS.md](FILTER-PATTERNS.md); for either side of a dependent
picklist read [DEPENDENT-FIELDS.md](DEPENDENT-FIELDS.md). The core habit: put a predicate on the
target MetaField into every bulk filter.

Every `(metafieldId, value)` operation selects its nodes with **exactly one** of two modes:

- **`nodeFilter`** — the `query_metadata` selection shape (`metadataList`, `filters`, `allNodes`)
  without columns, sort, or paging. The server resolves ids itself, so no id ever crosses your
  output: a whole population is one call. Use it whenever the selection is expressible as data —
  which includes every drain pass and every dependent-picklist mapping.
- **`nodeIds`** — explicit ReferenceModelNode ids from `query_metadata` or `metadata_search`. Use it
  only for judgement passes, where you read nodes individually and decided per node. **Anything
  larger or data-expressible must use `nodeFilter`.** The binding constraint here is your own
  context, not the server: id transport costs ~70 tokens per node round-trip, so a few thousand ids
  consume the window you need for the judgement itself (measured 2026-08-02: a 5,368-node id-mode
  run is impossible in a 256k window).

There is no selection size to pre-compute — the response is the protocol. The enforced caps per
call, all echoed back in `capsApplied`, are **40 operations**, **4,000 node references** and **40
write chunks**. Those are the only sizes that refuse a call; the tool chunks internally to the
100-node bulk operation the write core takes, so callers never pace at that size. Refusals are
write-free and name the fix: `batch_too_large` (split the call or shrink each selection) and
`filter_resolves_too_many` (add a predicate on the target MetaField — `isExists false` or
`neq <value>` — to make the filter self-draining, which is almost always what was meant).

Picklist values are option ids, never labels; a multiPicklist value is an array of option ids. Values
synchronize across every synced org in the implementation. Clearing is type-specific — the matrix is
in [BULK-WRITES.md](BULK-WRITES.md), and `datetime` cannot be cleared at all.

**The reissue loop.** An operation is *self-draining* when its `nodeFilter` carries a predicate on the
target MetaField that no node holding the target value can satisfy. Such an operation writes a
bounded tranche and returns `remaining`: re-issue the **byte-identical call** until `remaining: 0`,
never paginating or adjusting the filter between rounds. Two results end the loop instead:

- **`drainStalled: true`** (`written: 0`, `remaining > 0`, no failures) — every node left is
  permanently skipped. **Stop re-issuing.**
- **`fullySkipped: true`** — nothing was written and everything was skipped, with nothing retryable.
  Read `skippedSample` before reporting success. The server sets this flag in both selection modes,
  so use it rather than inferring the condition from the counts.

Also check **`resolved`** on every round. A filter that matched nothing returns
`resolved: 0, written: 0, remaining: 0` with an empty `skippedSample` and no flag at all — clean
success, nothing written. And **never set `allNodes: true` in a `nodeFilter`**: a MetaField
predicate is only applied when its column is selected, and `nodeFilter` has no `columns` key to
select it — so under `allNodes` the predicate is silently dropped and a self-draining operation
becomes a write across the entire reference model. Unlike `query_metadata`, there is no way to make
it safe from the caller's side. Scope every `nodeFilter` with `metadataList`.

`failedCount` and `unknownCount` are retryable; `skippedCount` is terminal. Never retry an `unknownCount` write without reading the affected nodes first; [BULK-WRITES.md](BULK-WRITES.md) carries the pacing limits and the partial-failure rules. Bringing a whole
population to one value takes **two** passes (`isExists: false`, then `neq <target>`), because `neq`
excludes nulls. [BULK-WRITES.md](BULK-WRITES.md) has the predicate tables and the reasoning.

### 5. Verify by reading

For each field, call `query_metadata` in `mode: "manifest"` with the MetaField `columnKey` in
`columns` and a `{column: "<columnKey>", operator: "isExists", value: true}` filter. Compare
`totalItems` with the sum of `results[].written`, and verify **per target value** (`eq <target>`) —
a drain predicate reaching 0 proves nothing on its own. In an implementation with more than one
reference model, the query verifies one model only. How values render on read, and the traps in
reusing them, are in [BULK-WRITES.md](BULK-WRITES.md).

## Mechanics that bite

- `list_metadata_columns` returns enumerated options as `{id, label}` pairs. Use `id` in filters.
- MetaField columns advertise `isExists`; it is the counting operator for populated values.
- When `query_metadata` has an explicit `columns` list, every filter column must also be selected or
  the call is rejected. Add the column to `columns`.
- Node reads may expose bare option ids. Use `list_metafields` to recover their labels.
- To rename an option with `update_metafield` without deleting node values, include its existing
  option `id`. An id-less option falls back to matching the existing label; a new unmatched label
  creates an option, and omitted options are removed with their values.

## The 25-field capacity gate

Each implementation can hold 25 MetaFields. The capacity is shared across engagements and is
effectively permanent because MCP exposes no delete tool. Before defining anything, calculate the
total fields the methodology needs and require `capacity.remaining` to cover all of them. If it does
not, stop and ask the user to resolve the schema in Elements; do not create a partial catalog.

**Widening `appliesTo` to a managed package widens it to the whole package.** A
`"<Package> Managed package"` entry grants the field to every node in that package regardless of
metadata type, so one entry can multiply the writable population by an order of magnitude. The
pseudo-type cannot be queried through `metadataList`, so that population cannot be counted in
advance — keep the metadata-type predicate in every `nodeFilter` on a widened field.

## Destructive edits

Narrowing `appliesTo` or removing options with `update_metafield` irreversibly purges affected
values from **every reference model and every synced org in the implementation**. Before narrowing
types, count all populated nodes with `mode: "manifest"`, the MetaField in `columns`, and
`isExists: true`. Before removing an option, repeat with `operator: "eq"` and that option id. Report
the counts and get explicit approval. Each count covers only the reference model queried, so repeat
across models when an implementation has more than one.

**The tool counts the damage for you.** A destructive `update_metafield` returns
`queuedValueDeletions` alongside the new definition — implementation-wide counts of the nodes losing
values. Use it to confirm your own pre-count, and quote it when reporting what happened.

**The purge is asynchronous.** It is queued rather than applied inline, so a verification query run
immediately afterwards can still count values that are on their way out. Re-count after a pause
before concluding anything from a post-edit number.

`update_metafield` requires at least one property to change (`title`, `appliesTo`, `options`,
`predefined`, `min`, `max`, `placeholder`); a call with none is refused. A `title` that would collide
with an existing field's column key is refused on both `create_metafield` and `update_metafield`.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "Set up MetaFields and classify these objects" | Yes, discover → define → wire → classify → verify |
| "Populate retention priority across these nodes" | Yes, using option ids and bulk assignments |
| "Rename this option without losing classifications" | Yes, preserve its option id on update |
| "Which fields and values should our migration methodology use?" | No, use the relevant playbook |
| "List metadata matching these criteria" | No, use `elements-metadata-query` |
| "Explain this one Flow or field" | No, use `elements-metadata` |
