# Scoring and lane judgment

## Contents

- [Score factors](#score-factors)
- [Field-query recipe](#field-query-recipe)
- [Recompute and stopping](#recompute-and-stopping)
- [Lane judgment](#lane-judgment)
- [Signal fields](#signal-fields)

## Score factors

The server emits six normalized factors. Full-detail `scoreFactors` entries contain
`factor`, `weight`, `value`, `contribution` and `detail`; summary entries contain only nonzero
`factor`/`contribution` pairs, largest first. Values are clamped to 0–1; raw contributions are
`weight × value × 100`. The server rescales the sum by total weight / available weight when
velocity or recency is unavailable. Factor contributions themselves retain their raw weights.

| Factor | Weight | Normalization before clamping |
|---|---|---|
| `unstructuredRatio` | 0.28 | Unstructured fields / classified fields; short Text can inflate it |
| `recordVolume` | 0.24 | log10(records + 1) / log10(100000) |
| `automationGap` | 0.18 | 1 − min(1, configuration count / 20) |
| `recordVelocity` | 0.14 | log10(max(0, net) + 1) / log10(10000); unavailable if snapshots absent |
| `recency` | 0.10 | 0.5^(ageDays / 90), from last modified or last created record |
| `schemaComplexity` | 0.06 | min(1, fields / 150) |

Cite the largest one or two contributions and their `detail` or matching signal fields.
For example, 19,056 records contribute about 20.5 volume points. A big table whose other factors
are mostly zero supplies a weak agent signal. Inspect usage series before assigning a cause to
falling velocity, such as archiving or deletion.

## Field-query recipe

Call `describe_metadata_schema(refModelId,metadataList:["Field"],delivery:"file")` once. Discover
actual column keys, population units and `allowedOperators`. For an unnamespaced object, query:

```text
list_metadata_by_criteria(refModelId,metadataList:["Field"],
  filters:[{column:"full_api_name",operator:"startswith",value:"Request__c/"}],
  columns:["full_api_name","subtype","length"])
```

For namespaced objects use the full prefix `acme/acme__Account_Profile__c/`. Every filter column
must appear in explicit `columns`. Unknown filter keys return `invalid_filter_column`; omitting
an explicit filter column returns `invalid_input`. `tags`, `optimization_status` and
`parent_manage_package` are display-only list columns; scalar `parent_object` supports filtering.
Field rows carry `nodeId`, `sf.apiName`, `sf.fullApiName` and `nodeDetails.{subtype,length}`.
Acquire all parts before running the ratio calculator. Name each object's parts separately.

The calculator counts Long Text Area (`subtype:"Text area"`, length above 255) and Rich Text Area
(`subtype:"Rich text area"`). `--include-short-text-area` also counts short Text Area or absent length;
use this only when the user asks for that broader definition. String, Email, Phone, Url and
Encrypted string are structured for this screen. Distinct field rows form the denominator;
compare against `schema.fieldsTotal` and report a mismatch. The calculator's output `object` is
the path before the final field segment, including namespace; ranking matches its final segment
to a unique scan `apiName` (application programming interface name).

For population, `understand_org_health(refModelId,area:"field_population",delivery:"file")` gives
object-band counts: join `item.key` or `item.detail.nodeId`, then read `breakdown[{key,value}]`
for `zero`, `below25`, `below50`, `below75` and `above75`; `total` sums fields. To verify individual
human-content fields, repeat the field query with an added filter on the discovered population
column: use `gt` only if advertised, with 50 percent expressed in that column's units. Select
`full_api_name` and the population column. Intersect returned names with the qualifying long-form
fields. A populated majority means strictly above 50 percent; lower values do not qualify.

## Recompute and stopping

The workflow's adjusted score is `server score − raw unstructuredRatio contribution + 28 × recomputedRatio`.
This is a screening adjustment, distinct from rerunning the server's availability rescaling.
Retain the original server score, both ratios and the score source in the report. Example:
Web_Lead__c has 56 fields and one long-form `Comments__c`; server ratio 0.571 becomes 0.018,
and its raw free-text contribution falls from about 16.0 to 0.5. EmailMessage has 44 fields with
HtmlBody, TextBody and Headers as long-form fields: 0.295 becomes 0.068; adjusted score
`58.84 − 8.26 + 28 × 0.068 = 52.48` after rounding. Field purpose still determines the lane.

Save one calculator output per recomputed object. For a failed query or unavailable field rows,
save an unavailable attempt in exactly this JavaScript Object Notation (JSON) shape:

```json
{"object":"Request__c","recomputedRatio":null,"reason":"Quote the returned refusal or acquisition failure"}
```

Run the ranking script with the complete merged scan and all saved ratio files; it writes a
full `ranking`, `top3`, `nextNodeIds`, `status` and `nextAction`. It marks rows `recomputed` or
`server ratio`, replaces the free-text contribution, sorts by adjusted score and uses `nodeId`
to order equal scores. Unchecked scores reaching the lowest current finalist require another
round. An unavailable required recompute leaves ranking unresolved; retain its server ratio,
label “server ratio, unverified; may count short Text fields,” and report the reason. Invalid
inputs also return unresolved: repair them and rerun. A corpus with fewer than three rows
verifies all available rows; an empty corpus reports no candidates rather than a verified top three.

## Lane judgment

Use the short table in SKILL.md with these rules. Apply Cleanup first for zero or stale records,
then Conversational for qualifying content, then the confirmed automation lanes for other busy
objects. Keep a primary lane provisional until required checks finish. Cognitive-overload and
Assistant / deflection can be secondary opportunities alongside a primary lane.

Conversational requires two or more long-form fields carrying content people write or read:
message bodies, request details and case notes. Require field purpose and populated-majority
evidence. Integration payloads, stack traces, limits dumps, identifier lists and queue buffers
are machine content. Integration_Log__c's Payload__c, Stack_Trace__c and Limits_Snapshot__c
fail that criterion. Support_Request__c's Request_Details__c, Steps_Taken__c and
Additional_Information__c qualify when at least two are populated; EmailMessage's HtmlBody
and TextBody qualify under the same condition. One auxiliary Comments__c on a structured
staging object fails the criterion. Unavailable population keeps Conversational provisional.

For structured busy objects, inspect incoming automation before choosing gap or well-automated.
Substantial existing logic supports the latter; little confirmed logic plus an unmet business
process supports a deterministic gap. High record volume alone cannot establish either lane.
For Cognitive-overload, require available population skewed to empty/low bands across many fields.
For Assistant / deflection, require available object engagement plus manual patterns on hot paths.
Skip pure cleanup or managed-package plumbing as finalists when a better agent story exists;
record the reason. Business relevance and a useful spread of lanes can qualify the ranking choice.

## Signal fields

Both detail modes include `records.total`, `records.lastModified`, `schema.fieldsTotal`, `custom`,
`unstructured`, `structured`, `unstructuredRatio`, `automation.totalDependencies`,
`velocity.net30`, `trend`, `dataAvailable`, `population.adoptionGap`, `dataAvailable`, and
`engagement.views30d`, `available` (nested keys stay under their corresponding parent).
Full detail adds `records.byRecordType`, `records.lastCreated`, `schema.formula`,
`automation.byType`, `velocity.net7`, `velocity.basis:"netRecordDelta"`, and population
`bands:{zero,below25,below50,below75,above75}`. Missing net deltas are null.
