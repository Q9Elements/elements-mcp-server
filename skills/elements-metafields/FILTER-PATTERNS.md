# nodeFilter construction patterns

Worked examples for `set_metafield_values` filter mode. Every "what happens" below was measured
live (2026-08-02), not inferred. Read this before writing any `nodeFilter`; the goal is a correct
filter on the first call, not a repaired one after a refusal.

The one habit that prevents most mistakes: **put a predicate on the target MetaField itself into
every bulk-assignment filter.** It makes the operation self-draining (any size is then safe,
tranches automatically) and idempotent (re-running never rewrites finished nodes).

---

## 1. Assign a value to a whole population

Intent: set `Retention = High` (option id `RET_HIGH`) on every Field node.

❌ **Don't** select the population by what it *is*:

```json
{"value": "RET_HIGH", "nodeFilter": {"metadataList": ["Field"], "filters": []}}
```

What happens: writing `Retention` doesn't change any node's type, so re-running this filter
matches the same nodes forever — the server cannot tranche it safely. An oversized selection is
refused write-free (`filter_resolves_too_many`); a smaller one works but rewrites every node
every time you run it.

✅ **Do** select by what the write *changes*:

```json
{"value": "RET_HIGH", "nodeFilter": {"metadataList": ["Field"],
  "filters": [{"column": "retention", "operator": "isExists", "value": false}]}}
```

What happens: every written node leaves the match set. Any population size is safe — an oversized
selection writes a bounded tranche and returns `remaining`; re-issue the **byte-identical** call
until `remaining: 0`.

**Then run a second pass** to correct nodes holding a *different* value — `neq` excludes empty
nodes, so one predicate never covers both:

```json
{"value": "RET_HIGH", "nodeFilter": {"metadataList": ["Field"],
  "filters": [{"column": "retention", "operator": "neq", "value": "RET_HIGH"}]}}
```

(Sequential calls, not one call: a call may carry only one self-draining operation per MetaField.)
Finish when **both** predicates count 0 in a `query_metadata mode:"manifest"` check. Measured
consequence of skipping the second pass: a `neq`-only loop once drained to zero with 33% of the
population never written.

## 2. Classify by attribute buckets

Intent: `Picklist` fields → `Simple`, `Lookup` fields → `Relational`.

✅ One operation per bucket, all in **one call**, each with the target-field guard added:

```json
[{"value": "OPT_SIMPLE", "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "subtype", "operator": "eq", "value": "Picklist"},
   {"column": "classification", "operator": "isExists", "value": false}]}},
 {"value": "OPT_RELATIONAL", "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "subtype", "operator": "eq", "value": "Lookup"},
   {"column": "classification", "operator": "isExists", "value": false}]}}]
```

Why the guard: without it each bucket op is non-draining (see pattern 1) and an oversized bucket
is refused; with it every bucket is tranche-safe and the whole call is re-runnable after any
interruption. Bucket on **enumerated columns** (`subtype`, picklists — filter by option id) and
check the buckets are disjoint; two operations writing different values to an overlapping node in
one call resolve by input order, which is rarely what you meant.

❌ Don't page `query_metadata` and send the ids — explicit ids are for judgement passes only.
Anything expressible as data belongs in the filter.

## 3. Filters on the SAME column are OR; different columns are AND

Measured: `[{retention eq HIGH}, {retention eq LOW}]` resolved the **union** of both groups
(3,062 + 200 = 3,262 written in one call) — same-column predicates behave like an `IN` list, the
production view-builder semantics. Predicates on *different* columns AND-combine.

✅ To intersect on one column, use an excluding operator instead of stacking equalities:
`{retention neq HIGH}` or a `range`. To target "either subtype A or B with one value", stacking
`subtype eq A` + `subtype eq B` in one filter is correct and intentional — but then the target
guard from pattern 1 is doing the draining, not the subtype predicates.

## 4. String prefixes: startswith needs 4+ characters and matches exactly

- A prefix under 4 characters is refused write-free with `invalid_filter_value`.
- A valid prefix matches true prefixes only — in rows, counts, and `set_metafield_values`
  filter resolution: `startswith "ProductServ"` selects `ProductServ*` nodes, never every
  `Product*` node.

Bucketing on an enumerated column (pattern 2) remains the better shape when one exists.

## 5. Dependent picklists: one operation per controller value, one call

Intent: populate dependent field `Action` from controller `Tier` (matrix: `Core → Keep`,
`Legacy → Retire`, …).

✅ Decompose by controller value — the whole mapping is a single call:

```json
[{"value": "OPT_KEEP",   "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "tier", "operator": "eq", "value": "OPT_CORE"}]}},
 {"value": "OPT_RETIRE", "nodeFilter": {"metadataList": ["Field"], "filters": [
   {"column": "tier", "operator": "eq", "value": "OPT_LEGACY"}]}}]
```

❌ Don't fire one dependent value at a mixed selection: every node whose controller value forbids
it is individually classified and rejected, which costs more than filtering and can push a batch
that passed the size check into a `batch_too_large` refusal. On dependency fields (either side),
prefer selections of 1,000–2,000 nodes per operation. For the deeper behaviours — orphaned
values after controller re-classification, empty-controller nodes, the orphan-sweep recipe —
see [DEPENDENT-FIELDS.md](DEPENDENT-FIELDS.md).

## 6. Don't pre-count; send and react

There is no need to check a filter's size before writing. The response tells you everything:

- `remaining > 0` → re-issue the byte-identical call (self-draining tranche in progress).
- `filter_resolves_too_many` → the operation wasn't self-draining and was too big; add the
  target-field predicate (pattern 1) — that is almost always what was meant — or narrow it.
- `batch_too_large` → too many operations or ids, or the call needs too many internal write
  groups: do what the message says — split the operations across calls or shrink each selection.
- `resolved` is your evidence of what the filter hit; verify a mass write against an independent
  `query_metadata mode:"manifest"` count per **target value**, not per populated field.

For the per-call caps and the smaller sizing that dependency fields need, see
[SKILL.md](SKILL.md) — it states them once so the two files cannot drift apart.

## 7. Clearing is an assignment too

Clearing uses the same machinery with the predicate inverted: the qualifying self-draining guard
for a clearing value is `isExists true` (nodes still holding a value), and the clear value is
type-specific (see the matrix in SKILL.md — `list` clears with `null` only, `datetime` cannot be
cleared, `text` clears with `""`).

```json
{"value": null, "nodeFilter": {"metadataList": ["Field"],
  "filters": [{"column": "retention", "operator": "isExists", "value": true}]}}
```
