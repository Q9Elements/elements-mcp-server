# Dependent MetaFields

## Contents

- [The dependency](#the-dependency)
- [Inspect and preview the matrix](#inspect-and-preview-the-matrix)
- [Empty controller values](#empty-controller-values)
- [Reclassification and orphan sweeps](#reclassification-and-orphan-sweeps)
- [Verification](#verification)

Read before wiring a dependency or writing either side. The matrix is a write gate: it validates
new dependent writes, while existing values can hold combinations the current matrix forbids.
Use [pattern 5](filter-patterns.md#5-dependent-picklists) for operation decomposition and ordering;
use [bulk writes](bulk-writes.md) for clearing values, sizing, accounting, and file acquisition.

## The dependency

One dependency has one controller (`list`) and one dependent (`list` or `multi_picklist`). Their
`appliesTo` sets must overlap; the relationship binds where both fields apply. `relationMap` keys
and values are option identifiers. Synthetic identifiers below are fake 24-character hexadecimal
placeholders; use returned identifiers for real calls.

| Identifier | Meaning |
|---|---|
| `aaaaaaaaaaaaaaaaaaaa0f01` | Tier field |
| `aaaaaaaaaaaaaaaaaaaa0f02` | Action field |
| `aaaaaaaaaaaaaaaaaaaa0c01` | Core controller option |
| `aaaaaaaaaaaaaaaaaaaa0c02` | Archived controller option |
| `aaaaaaaaaaaaaaaaaaaa0c03` | Frozen controller option |
| `aaaaaaaaaaaaaaaaaaaa0d01` | Keep dependent option |
| `aaaaaaaaaaaaaaaaaaaa0d02` | Review dependent option |
| `aaaaaaaaaaaaaaaaaaaa0d03` | Retire dependent option |

```json
{
  "controllerId": "aaaaaaaaaaaaaaaaaaaa0f01",
  "dependentId": "aaaaaaaaaaaaaaaaaaaa0f02",
  "relationMap": {
    "aaaaaaaaaaaaaaaaaaaa0c01": ["aaaaaaaaaaaaaaaaaaaa0d01", "aaaaaaaaaaaaaaaaaaaa0d02"],
    "aaaaaaaaaaaaaaaaaaaa0c02": ["aaaaaaaaaaaaaaaaaaaa0d03", "aaaaaaaaaaaaaaaaaaaa0d02"],
    "aaaaaaaaaaaaaaaaaaaa0c03": []
  }
}
```

Include every controller option. An incomplete map returns `dependency_map_incomplete`, with
`invalid` listing missing option identifiers. `[]` permits no dependent value; an entirely empty
set of permitted values is legal. A read can contain an absent controller key, which also permits
nothing; supply that key explicitly when writing the map.

A dependent can be paired only once. `set_metafield_dependency` creates a pair or replaces the
matrix for that same pair; it cannot re-pair fields. An incorrect pair requires removal in the
Elements user interface (UI), or neutralisation by permitting every dependent option for every
controller option. On a pairing conflict, inspect dependencies and confirm the intended pair
before proceeding.

A rule requiring two simultaneous controllers needs a combined synthetic controller field, such
as `Core-EU` and `Core-Other`, or enforcement on one axis only.

## Inspect and preview the matrix

Read `get_metafields({implementationId,include:"dependencies",delivery:"file"})` before changing
an existing matrix. Follow [result hydration](access-and-results.md#hydration-and-ordinary-delivery).
The result supplies joined `relationMap` labels for reading and `rawRelationMap` option identifier
arrays for read-modify-write. The setter takes the latter shape. Select a directional pair locally
by `controller.id` and `dependent.id`.

For a preview-only request, show the current `rawRelationMap` beside the proposed map locally.
Validate every controller key and dependent option against definitions. Calling
`set_metafield_dependency` applies the matrix immediately; it has no preview mode.
The applied response includes the full dependency, `outcome:"created"` or `"replaced"`, and
`nodesHoldingNowForbiddenValues`.

## Empty controller values

A node without a controller value cannot receive a non-clearing dependent value. In explicit-id
mode it is a terminal skip, for example `written:0` with
`skippedSample:[{reason:"dependent_value_not_permitted",controllerValue:null}]`.
Filter mode removes it before writing and reports `excludedAtResolve.count` and
`excludedAtResolve.byReason`. A manifest still counts it, so a completed drain can leave a gap.
Report that gap and classify the controller before trying the dependent again.

`controller_write_not_applied` in `failedCount` is retryable: the controller write did not complete.
Reissue after reconciling any unknown controller outcomes; keep this separate from terminal
`dependent_value_not_permitted` skips.

## Reclassification and orphan sweeps

Controller writes are accepted independently of stored dependent values. For example, changing
Core plus Keep to Frozen plus Keep succeeds even though the example matrix permits nothing for
Frozen. After controller reclassification or matrix narrowing, count forbidden pairs: for each
controller option, query each dependent option that its current row forbids.

Synthetic manifest request using the legend above and a fake reference model identifier:

```json
{"refModelId":"aaaaaaaaaaaaaaaaaaaa0301","metadataList":["Field"],
 "mode":"manifest","columns":["tier","action"],"filters":[
  {"column":"tier","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0c03"},
  {"column":"action","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0d01"}]}
```

If `totalItems` is 3, all three nodes are orphaned values. Rewrite that cohort to a permitted
value, or clear it with the same two-predicate selection. Clearing a dependent is always allowed,
including under a controller row permitting nothing; use the type-specific value from the
[clearing matrix](bulk-writes.md#values-and-clearing).

`nodesHoldingNowForbiddenValues` is a delta of newly forbidden nodes relative to the replaced
matrix, not a census of every orphan. It can be `null` when the count is unavailable, including
on widening. Use the pair sweep for the real count; replacing a matrix does not delete stored values.

## Verification

Verify each intended controller/dependent pair with manifest counts, and every forbidden pair
with a zero count. Fix orphan cohorts and re-run the sweep until it passes. For row labels and raw
option identifiers, follow [reading node values](bulk-writes.md#reading-node-values).
