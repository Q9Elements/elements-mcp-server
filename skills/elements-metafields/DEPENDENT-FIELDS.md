# Dependent MetaFields — how the matrix actually behaves

Worked examples for dependent-picklist definition and bulk writes. Every "measured" claim below
was verified live — the write-path and re-classification behaviour on 2026-08-02, the definition
tools and matrix advisory on 2026-08-19 — not inferred. Read this before wiring a dependency or
writing to either side of one.

The one fact that reframes everything else: **the matrix is a write gate, not an invariant.**
It is consulted only at the moment a value is written. Nothing ever re-checks existing values,
so the data can hold combinations the matrix forbids — and after a controller re-classification,
it usually does (see §4).

---

## 1. The model

One dependency = one **controller** (must be `list`) → one **dependent** (`list` or
`multiPicklist`), with a `relationMap` keyed entirely by **option ids**:

```json
{
  "controllerMetafieldId": "<Tier id>",
  "dependentMetafieldId": "<Action id>",
  "relationMap": {
    "OPT_CORE":   ["OPT_KEEP", "OPT_REVIEW"],
    "OPT_LEGACY": ["OPT_RETIRE", "OPT_REVIEW"],
    "OPT_FROZEN": []
  }
}
```

- **Every controller option must appear, and MCP enforces it.** Omitting one is refused with
  `dependency_map_incomplete`, whose `invalid` array names the missing option ids — on
  `create_metafield_dependency` and `update_metafield_dependency` alike. (A dependency created
  outside MCP can hold an absent key, which permits nothing at write time exactly as `[]` does; you
  may read that back, but you cannot write it.) Use `[]` to say "this controller value permits
  nothing" — it is accepted, and a matrix that is `[]` throughout is legal.
- **One dependent can be paired only once.** Pairing a second controller to a dependent that
  already has one is refused with `already_dependent`. There is no delete tool, so a wrong pairing
  is fixed in the Elements UI or neutralised by mapping every controller option to every dependent
  option.
- `list_metafield_dependencies` returns the matrix twice: `relationMap` joined to option **labels**
  for reading, and `rawRelationMap` as bare id arrays. `rawRelationMap` is the exact shape
  `update_metafield_dependency` expects, so read-modify-write it rather than rebuilding from labels.
- The `appliesTo` sets of the two fields must overlap; the dependency binds only where both apply.
- `update_metafield_dependency` replaces the **matrix only** — it can never re-pair the fields.
- A rule needing two simultaneous controllers ("Tier = Core AND Region = EU permits X") cannot be
  expressed. Model it as one synthetic combined controller field ("Core-EU", "Core-Other", …) or
  accept enforcement of only one axis.

## 2. Writing the dependent: one operation per controller value, one call

The whole mapping is a single call — each permitted dependent value gets one operation whose
filter selects on the *controller* value (full example: FILTER-PATTERNS.md pattern 5):

```json
[{"value": "OPT_KEEP",   "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "tier", "operator": "eq", "value": "OPT_CORE"}]}},
 {"value": "OPT_RETIRE", "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "tier", "operator": "eq", "value": "OPT_LEGACY"}]}}]
```

Never fire one dependent value at a mixed selection: every node whose controller value forbids it
is classified and rejected individually rather than excluded up front, and can push the call into
a post-read `batch_too_large` refusal that a same-controller-value selection never hits. One
same-size comparison (3,600 nodes) measured a mostly-rejected selection at 8.5 s against 4.6 s for
a fully-permitted one — one observation, not causally isolated, but selecting by controller value
first cannot cost more and is the only decomposition guaranteed to terminate. On **either side** of
a dependency — the controller too, not just the dependent — prefer operations of 1,000–2,000 nodes.

Controller and dependent assignments **can share one call**: the tool partitions dependent
picklists internally and writes the controller first, so a single call carrying both succeeded
3/3 on each side (measured 2026-08-19). Ordering matters between *calls*, not within one.

## 3. Nodes with no controller value can never receive a dependent value

Measured: a dependent write to a node whose controller is empty is **skipped**, not refused —
`written: 0`, `skippedSample: [{reason: "dependent_value_not_permitted", controllerValue:
"no_option"}]`. Three consequences:

- These nodes are **invisible to drain loops**: they never leave the resolved set, so a round
  reporting `written: 0` while the manifest count stays above zero is this case (or
  `type_not_applicable`), not an error to retry. Stop and report the gap.
- Populating a dependent across a whole population therefore needs the controller classified
  first. Within a single call the tool handles that ordering for you; across calls, classify the
  controller before writing the dependent, or every unclassified node skips.
- `controllerValue: "no_option"` in a skip sample is the diagnostic to look for.
- A **`controller_write_not_applied`** entry in `failedCount` is the separate, retryable case: the
  node's controller write did not complete, so the dependent write had no permitted value to check
  against. Re-issue the call rather than reporting a gap — unlike `dependent_value_not_permitted`,
  this one is not terminal.

## 4. Re-classifying the controller strands the dependent (measured)

Writing a controller value is **never** checked against the dependent values nodes already hold.
Measured sequence: controller `Alfa` + dependent `One` (permitted) → rewrite controller to
`Gamma`, whose matrix row permits **nothing** → the write succeeds and the node now holds
`Gamma` + `One`, a combination the matrix forbids. No error, no cleanup, invisible until audited.

So after ANY controller re-classification, sweep for orphans — for each controller value `V`,
count each dependent value `D` the new row does not permit:

```json
{"mode": "manifest", "filters": [
  {"column": "tier",   "operator": "eq", "value": "OPT_FROZEN"},
  {"column": "action", "operator": "eq", "value": "OPT_KEEP"}]}
```

Any non-zero count is an orphan cohort: rewrite it to a permitted value with the same
two-predicate filter, or clear it — **clearing is always permitted** (measured: `null` wrote
through under a permits-nothing controller value). Clearing is the escape hatch that cannot be
blocked by the matrix; use the type-specific clear value (SKILL.md matrix).

**Narrowing the matrix strands values the same way, and its advisory count will not tell you how
many.** `update_metafield_dependency` never deletes values already on nodes (measured: three nodes
still held a value after the matrix stopped permitting it) and returns
`nodesHoldingNowForbiddenValues`. That number is a **delta, not a census**: it counts nodes this
change newly forbade, relative to the previous matrix. Narrow twice and the second call reports
**0** while the same nodes are still stranded — measured 2026-08-19: narrowing to permit nothing
returned `0` with three stranded nodes, while reaching the identical end state from an
all-permitted matrix returned `3`. A widening returns `null`. So treat it as a hint on the call
that caused it, and run the two-predicate orphan sweep above for the real count.

## 5. Reading back: counts for auditing, labels in rows

Verify dependent populations with `mode: "manifest"` counts per (controller value, dependent
value) pair — counts are the audit tool, and the orphan sweep in §4 is built on them. Page rows
render selected MetaField columns as option **labels**, not ids; translate a label back to its
option id via `list_metafields` before reusing it in a filter or write. `get_metadata_node`
returns bare option ids instead.
