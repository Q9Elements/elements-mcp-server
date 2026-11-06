# nodeFilter construction patterns

## Contents

- [Assign one value across a population](#1-assign-one-value-across-a-population)
- [Classify by attribute buckets](#2-classify-by-attribute-buckets)
- [Combine filters](#3-combine-filters)
- [String prefixes](#4-string-prefixes)
- [Dependent picklists](#5-dependent-picklists)
- [Check scope and respond to results](#6-check-scope-and-respond-to-results)
- [Clearing](#7-clearing)

Synthetic fragments below belong inside `assignments[].values`, grouped under a discovered
`metafieldId` with `refModelId` on the full request. [SKILL.md](../SKILL.md#4-classify-nodes-in-bulk)
contains a complete request. Use returned field, option, and reference model identifiers in real
calls. All example identifiers are fake 24-character hexadecimal placeholders.

| Identifier | Option label |
|---|---|
| `aaaaaaaaaaaaaaaaaaaa0a01` | High retention |
| `aaaaaaaaaaaaaaaaaaaa0a02` | Low retention |
| `aaaaaaaaaaaaaaaaaaaa0b01` | Simple classification |
| `aaaaaaaaaaaaaaaaaaaa0b02` | Relational classification |
| `aaaaaaaaaaaaaaaaaaaa0c01` | Core tier |
| `aaaaaaaaaaaaaaaaaaaa0c02` | Archived tier |
| `aaaaaaaaaaaaaaaaaaaa0d01` | Keep action |
| `aaaaaaaaaaaaaaaaaaaa0d03` | Retire action |

## 1. Assign one value across a population

Intent: assign High retention to every Field node. A population-only filter is a plausible input
that needs a target-field guard before it can drain:

```json
{"value":"aaaaaaaaaaaaaaaaaaaa0a01","nodeFilter":{"metadataList":["Field"],"filters":[]}}
```

Writing retention does not change a node's type, so this filter keeps matching written nodes.
A small cohort rewrites them on each call; an oversized cohort refuses write-free. Use the
predicate describing what the assignment changes:

```json
{"value":"aaaaaaaaaaaaaaaaaaaa0a01","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"retention","operator":"is_exists","value":false}]}}
```

Then, in a separate call, correct nodes holding a different value:

```json
{"value":"aaaaaaaaaaaaaaaaaaaa0a01","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"retention","operator":"neq","value":"aaaaaaaaaaaaaaaaaaaa0a01"}]}}
```

`neq` excludes nulls. In a population of 300 nodes with 100 empty values, a `neq`-only pass misses
those 100 nodes. Run both passes for full coverage; each predicate must count zero afterwards.
Use the [write checklist](../SKILL.md#4-classify-nodes-in-bulk) for continuation and target-value
verification. For an empty-only request, run only the first pass and verify that intended cohort.

## 2. Classify by attribute buckets

Intent: Picklist fields become Simple; Lookup fields become Relational. Use one guarded operation
per call, with disjoint buckets. These built-in `subtype` values illustrate schema-returned enum
identifiers; discover the actual values before constructing the filters.

Call 1:

```json
[{"value":"aaaaaaaaaaaaaaaaaaaa0b01","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"subtype","operator":"eq","value":"Picklist"},
  {"column":"classification","operator":"is_exists","value":false}]}}]
```

Call 2:

```json
[{"value":"aaaaaaaaaaaaaaaaaaaa0b02","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"subtype","operator":"eq","value":"Lookup"},
  {"column":"classification","operator":"is_exists","value":false}]}}]
```

The target guard makes each bucket drainable. If existing values also need correction, apply
pattern 1's second pass to each bucket. Enumerated-column filters use option identifiers.
Overlapping operations writing different values to one node resolve in input order; disjoint
buckets keep the planned value unambiguous.

## 3. Combine filters

Same-column filters OR-combine; different columns AND-combine. Two `retention eq` predicates
select a union. For disjoint groups of 300 and 200 nodes, this filter selects 500:

```json
[{"column":"retention","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0a01"},
 {"column":"retention","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0a02"}]
```

To express an intersection on one column, use an appropriate excluding operator or a `range`.
For either subtype A or B, stacking subtype equalities expresses the intended union; a separate
target-field guard supplies the draining behavior.

## 4. String prefixes

`startswith` requires at least four characters; a shorter prefix returns `invalid_filter_value`
without writing. For a shorter requested prefix, retrieve a practical broader cohort, then filter
actual application programming interface (API) names locally. Sort locally for an ordered or
bounded top-N request. A valid prefix matches exactly: `ProductServ` selects `ProductServ*`
names, rather than all `Product*` names, in counts, rows, and write-filter resolution.
Use an enumerated bucket when the schema offers one that expresses the intent directly.

## 5. Dependent picklists

Intent: populate Action from Tier, where Core permits Keep and Archived permits Retire.
Decompose a bounded mapping into one operation per controller value:

```json
[{"value":"aaaaaaaaaaaaaaaaaaaa0d01","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"tier","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0c01"}]}},
 {"value":"aaaaaaaaaaaaaaaaaaaa0d03","nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"tier","operator":"eq","value":"aaaaaaaaaaaaaaaaaaaa0c02"}]}}]
```

These operations have no target guard: keep the bounded mapping within the call caps. For larger
populations, guard the target and run each dependent value in a separate call with pattern 1's
coverage passes. Selecting controller cohorts avoids individually rejected writes that can exceed
the read-phase dependency budget.

When a dependent filter selects on a controller value being newly written, write the controller
in one call and the dependent in the next: all filters resolve before writes land. Otherwise,
controller and dependent assignments can share one call; list the controller operation first,
as a dependent listed first validates against the stored controller value. For orphan sweeps and
empty controllers, read [dependent fields](dependent-fields.md).

## 6. Check scope and respond to results

Validate the selection against the local plan and follow the
[write checklist](../SKILL.md#4-classify-nodes-in-bulk) for result handling and independent counts.
The [accounting table](bulk-writes.md#reading-the-accounting) distinguishes failed, unknown,
skipped, excluded, and empty cohorts; resolve those diagnostics before declaring completion.

## 7. Clearing

Use the [clearing matrix and predicates](bulk-writes.md#values-and-clearing) to select the type's
clear value and qualifying cohort. Example for a list field:

```json
{"value":null,"nodeFilter":{"metadataList":["Field"],"filters":[
  {"column":"retention","operator":"is_exists","value":true}]}}
```
