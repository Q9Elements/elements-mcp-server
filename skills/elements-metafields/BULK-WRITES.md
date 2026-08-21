# Bulk writes: the full `set_metafield_values` contract

Read this before the first bulk write of an engagement. [SKILL.md](SKILL.md) carries the selection
modes, the caps and the reissue loop; everything below is the detail those rules rest on. For
selection *shapes* see [FILTER-PATTERNS.md](FILTER-PATTERNS.md), and for either side of a dependent
picklist see [DEPENDENT-FIELDS.md](DEPENDENT-FIELDS.md).

## Values, and how each type clears

Picklist values are option ids, never labels. A multiPicklist value is an array of option ids.
Values synchronize across every synced org in the implementation.

Clearing is type-specific:

| Type | Clear value | Values that do not clear |
|---|---|---|
| `text` | `""` | `null` raises `incorrect_text_value` |
| `longtext` | `""` writes, but does **not** clear for `isExists` — see below | `null` raises `incorrect_text_value` |
| `number` | `null` or `""` | — |
| `datetime` | Cannot be cleared | `null` and `""` raise `incorrect_date_value` |
| `list` | `null` | `""` is refused |
| `multiPicklist` | `null` or `[]` | `""` is refused |

**A `longtext` field cannot be brought to a cleared state over MCP.** Writing `""` stores an empty
string, but the node still counts as *present* for `isExists: true` (measured against the shipping
build; `text` behaves correctly, going absent). That breaks the clearing drain below: the qualifying
predicate for a clearing assignment is `isExists: true`, so the same nodes re-resolve every round and
a byte-identical re-issue returns an identical `resolved`/`written` forever. Under the caps
`remaining: 0` hides it and one round looks like success while every verification query keeps
reporting the original count; over the caps the loop does not terminate. Do not run a clearing drain
on a `longtext` field: write the empty string once, report the field as emptied-but-still-counted,
and treat the `isExists` count as unusable for that field.

Duplicate `nodeIds`, and duplicate option ids inside a multiPicklist value, are de-duplicated
before the write, so a repeated id neither double-counts write credits nor stores a value twice.

For a field on **either side** of a dependent-picklist relationship prefer selections of **1,000–2,000 nodes**: a
dependency batch can be refused after the read phase well below the general ceiling, and that
applies to writes on the *controller* just as much as the dependent (measured 2026-08-02).

## Dependent fields: decompose by controller value

Give each permitted dependent
value its own operation whose `nodeFilter` selects on the *controller* value: the whole four-way
mapping (`Core → Must retain`, `Secondary → Optional`, …) is a single call with one filter per
operation. Firing one value at a mixed selection makes the tool classify and reject every node the
matrix disallows, which costs more than filtering and can push a batch that passed the size check
into a `batch_too_large` refusal.

## Self-draining operations

**Draining a population with a filter.** An operation is **self-draining** when its `nodeFilter`
carries a predicate on the *target* MetaField that no node holding the target value can satisfy:

| Assignment | Qualifying predicate |
|---|---|
| any non-clearing value | `{column: <target>, operator: "isExists", value: false}` |
| value `X` | `{column: <target>, operator: "neq", value: X}` |
| a clearing value (per the matrix above) | `{column: <target>, operator: "isExists", value: true}` |

> **Never set `allNodes: true` in a `nodeFilter`.** A MetaField predicate is only applied when its
> column is among the selected columns, and `nodeFilter` accepts only `metadataList`, `allNodes` and
> `filters` — there is no `columns` key, so a write can never select the column the way
> `query_metadata` can. Under `allNodes` the target-MetaField predicate is therefore always dropped:
> the selection silently becomes every node in the reference model while `resolved` and `remaining`
> still look normal, and the drain writes the value across the whole model a tranche per round,
> reporting success each time. Always scope a `nodeFilter` with `metadataList`.

A self-draining operation that resolves over the caps **writes a bounded tranche and returns
`remaining`**: re-issue the **byte-identical call** until `remaining: 0`. Do not paginate, do not
adjust the filter between rounds — the filter re-derives the remaining set each time. One
self-draining operation per MetaField per call, and no other operation in the call may write a
*different* value to that MetaField (`invalid_input` otherwise: a same-call overwrite would
restore drained nodes to a filter-matching state and the reissue loop would never converge;
same-field same-value operations are fine — they coalesce). Give a self-draining operation its
own call rather than mixing it with large explicit-id work — non-drainable work reserves cap
budget first, and a call whose non-drainable work consumes the entire cap is refused write-free.

## Reading the accounting

Filter-mode accounting per operation is `{resolved, written, skippedCount, skippedSample,
skippedSampleTruncated, failedCount, unknownCount, remaining, drainStalled, fullySkipped}`.
Explicit-id operations report **`requested`** in place of `resolved`, and carry no `remaining`.

**`resolved` means different things in different responses, so do not reconcile it naively.** In a
refusal it is the raw count the filter matched; in a successful write it is the count *after*
`appliesTo` eligibility is applied; and an independent `query_metadata mode:"manifest"` count for the
same filter is a third number, because the manifest applies neither eligibility filter. Expect all
three to differ on a field that is not applicable to every type in the selection — a mismatch is not
evidence of a problem. `resolved` also never equals `written + skippedCount`. Use the manifest count
to sanity-check the *order of magnitude* of a mass write, and `eq <target>` per value (below) as the
real proof of completion.

**Retryable versus terminal, because they are re-issued differently:**

| Field | Meaning | What to do |
|---|---|---|
| `failedCount` | Writes that failed | Retryable — re-issue the same call |
| `unknownCount` | Writes whose outcome was not observed | Retryable — but reconcile by reading first (see [Pacing and partial failure](#pacing-and-partial-failure)) |
| `skippedCount` | Nodes that can never take this value | **Terminal** — re-issuing cannot write them; read `skippedSample` for the reasons |
| `drainStalled: true` | `written: 0`, `remaining > 0`, no failures | **Stop re-issuing** — every node left in the selection is permanently skipped |

**`fullySkipped: true`** is the server's own flag for a selection where nothing was written and
everything was skipped with nothing retryable — read `skippedSample` before reporting success. It is
set in both selection modes, including explicit-id operations that have no `remaining` at all, so
prefer it to inferring the condition from the counts. `skippedSampleTruncated: true` means the sample
is shorter than `skippedCount`, so it is not a full list of the reasons.

**A filter that matched nothing looks like a clean success.** It returns
`resolved: 0, written: 0, skippedCount: 0, remaining: 0` with an **empty** `skippedSample` and no
`fullySkipped` flag — so there is nothing to read for a reason. `resolved: 0` is the only signal, and
a typo'd or over-narrow filter is indistinguishable from a genuinely empty target set without it.
Check `resolved` on every filter-mode write.

## Coverage, verification and the cases the loop misses

**Coverage still needs two predicates.** `neq` excludes nulls (measured 2026-08-02: a `neq`-only
loop drained to zero with **33% of the population never written**), so bringing a whole population
to one value takes two passes — `isExists: false` fills the empty nodes, then `neq <target>`
corrects the wrong ones. Finish when *both* predicates count 0 in a manifest query.

**Filter order does not matter** for MetaField `isExists` filters: the server normalises order
and intersects multiple `isExists: false` predicates itself. When a call carries **two or more**
`isExists: false` MetaField predicates, each is resolved as its own branch and a branch over 10,000
nodes refuses with `filter_branch_too_large` — narrow that predicate.

**That 10,000 cap is not a general guardrail.** It exists only on the multi-predicate intersection
path: a call with a *single* `isExists: false` predicate skips branch resolution entirely, so no cap
is checked and no refusal is possible however large the population. A single predicate resolving tens
of thousands of nodes will quietly write a tranche and hand you a `remaining` to loop on. Size the
selection yourself with a manifest count before the first write; do not expect the server to stop
you.

**Verify per target value, not per populated field.** Compare `eq <target>` against that group's total.
A drain predicate reaching 0 is not proof of completion, and neither is `isExists: true` matching the
number of nodes you wrote — both pass while a third of the population holds the wrong value.

Four further cases the drain loop does not handle; each otherwise costs a hang or silent
incompleteness:

- **Clearing** inverts the predicate — `isExists: true` selects the nodes still holding a value
  (that is why it is the qualifying predicate for a clearing assignment).
- **Partially-populated multiPicklists** are invisible to a `neq` pass: a write replaces the whole
  value rather than appending, so a node holding some of the wanted options is excluded and
  silently missed.
- **Type-ineligible nodes** (`type_not_applicable`) and nodes with **no controller value** can never
  receive a value. In **explicit-id** mode they surface as `skippedCount` with a reason in
  `skippedSample`. In **filter** mode they are excluded from `resolved` before the write, so the
  operation reports `resolved: 0, written: 0, skippedCount: 0, remaining: 0` — a clean success that
  accomplished nothing, with no diagnostic to read. A filter-mode write that reports `resolved` far
  below your manifest count is hitting this; confirm the cause by re-running a handful of the node ids
  in explicit-id mode, which does name the reason.
  Because of that pre-exclusion `drainStalled: true` is effectively unreachable for a correctly
  scoped filter: its precondition is ineligible nodes *retained* in `resolved`. Treat it as a
  belt-and-braces stop condition, not something you will normally observe.
- **Managed-package nodes** skip as `type_not_applicable_managed_package` unless the MetaField's
  `appliesTo` includes that package's own **"<Package> Managed package"** entry. Matching the base
  metadata type is **not** enough — and `query_metadata` still shows the column on those nodes, so
  the selection looks eligible right up to the write. To populate them, widen `appliesTo` with
  `update_metafield` first.
  **Adding that entry grants the field to every node in the package, of every metadata type** — the
  pseudo-type is not scoped to the metadata type you had in mind. One entry can multiply the writable
  population by an order of magnitude, and the pseudo-type is not queryable via `metadataList`, so
  the widened population cannot be counted in advance. Add package entries one at a time, keep the
  metadata-type predicate in every `nodeFilter` on a widened field, and expect a later
  `update_metafield` narrowing to report far more `queuedValueDeletions` than the nodes you
  deliberately wrote.
- **Concurrent writers** can stop the counts ever reaching zero.

After a `tool_timeout`, re-query before doing anything else. Writes are not cancelled, so the tool may
have succeeded after reporting failure; a fresh count is the only trustworthy statement of what
happened.

## Verifying by reading

For each field, call `query_metadata` in `mode: "manifest"` with the MetaField `columnKey` included
in `columns` and a `{column: "<columnKey>", operator: "isExists", value: true}` filter.

Compare `totalItems` with the sum of `results[].written` for that field. Investigate
`skippedCount`, `skippedSample`, and every `dispatch.failed` entry. In an implementation with more
than one reference model, the query verifies one model only.

Page rows render selected MetaField columns flat under the column key: list and multiPicklist
values as option **labels** (translate back to option ids via `list_metafields` before reusing
them in filters or writes), scalar types raw. A node with no value omits the key. A `text`
field cleared with `""` renders as an empty string while counting as absent for `isExists`; a
`longtext` field cleared the same way renders empty but still counts as **present** (see the clearing
warning above). `get_metadata_node` returns bare option ids instead of labels.

## Pacing and partial failure

Sustain no more than one request per second. The limit is **60 requests/minute per token**, and
exceeding it locks the token for 60 seconds. On a `rate_limited` error, wait the full `retryAfter`
(60 seconds) before resuming, then resume at a slower pace. A retry issued during the lockout fails
but does **not** extend it: the lock expiry is stamped once, at the moment the limit is crossed.

`dispatch.unknown` means a write was dispatched but its outcome was not observed. It is neither
success nor failure. Do not retry an unknown write; read the affected cohorts to resolve the state.
Only proceed to a dependent classification pass after `dispatch.unknown` is empty or every unknown
outcome has been reconciled by reading.
