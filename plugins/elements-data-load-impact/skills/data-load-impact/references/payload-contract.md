# Load-impact payload contract

Contract version **1.0.0**. This document is the public boundary shared by the local
`load_input_prep.py` profiler, the org-context exporter, the rules-data generator, and the
server-side load-impact service. It is authoritative for Objects 1–3 below.

The local profiler is offline and standard-library-only. Raw records never cross the session
LLM boundary. A completed payload contains derived metadata names, counts, distributions,
warnings, generated aggregate SOQL, and (unless hashing is requested) only the top-K parent IDs.

## Object 1: load-impact payload

### Worked example

```json
{
  "contractVersion": "1.0.0",
  "generatedBy": {
    "adapter": "csv",
    "rulesVersion": "1.0.1",
    "script": "load_input_prep.py"
  },
  "targets": [
    {
      "object": "Task",
      "operation": "insert",
      "writtenFields": ["ActivityDate", "Status", "WhatId"],
      "estimatedVolume": 3,
      "volumeSource": "row_count",
      "upsert": null,
      "aggregates": {
        "relationshipColumns": [
          {
            "column": "WhatId",
            "polymorphic": true,
            "populatedRows": 2,
            "nullRows": 1,
            "nonIdRows": 0,
            "typeDistribution": [
              {"object": "Account", "prefix": "001", "rows": 2}
            ],
            "fanIn": {
              "distinctParents": 1,
              "maxRowsPerParent": 2,
              "histogram": [
                {"bucket": "1", "parents": 0},
                {"bucket": "2-10", "parents": 1},
                {"bucket": "11-100", "parents": 0},
                {"bucket": "101-1000", "parents": 0},
                {"bucket": "1001-10000", "parents": 0},
                {"bucket": ">10000", "parents": 0}
              ],
              "topParents": [{"id": "001000000000005", "rows": 2}],
              "idRepresentation": "raw"
            }
          }
        ],
        "predicateStats": [
          {
            "ruleId": "SF_LOCK_TASK_RELATIONSHIPS_V1",
            "fields": ["ActivityDate", "Status"],
            "evaluableRows": 3,
            "matchingRows": 1,
            "note": "rows where Status = Completed AND ActivityDate non-null"
          }
        ],
        "unresolved": []
      }
    }
  ],
  "asks": [
    {"question": "Which load operation will run: insert, update, or upsert?", "answered": true},
    {"question": "Which fields does the load WRITE?", "answered": true}
  ],
  "assumptions": [
    {
      "key": "skewThreshold",
      "value": 10000,
      "label": "community consensus, not officially documented"
    }
  ],
  "warnings": []
}
```

### Root fields

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `contractVersion` | semantic-version string | yes | Object 1 schema version. This implementation emits `1.0.0`. |
| `generatedBy` | GeneratedBy | yes | Producer and rules-data identity. |
| `targets` | Target[] | yes | Non-empty load targets. The local CLI emits one target per invocation. |
| `asks` | AskAudit[] | yes | Required confirmations retained as answered audit entries. Pending asks are never put in a payload. |
| `assumptions` | Assumption[] | yes | Named non-factual thresholds used downstream. |
| `warnings` | string[] | yes | File-level degraded or non-evaluable conditions. Empty when none. |

### `GeneratedBy`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `script` | string | yes | Exactly `load_input_prep.py`. |
| `adapter` | enum | yes | `csv` for counted file measurements; `soql` for query-defined loads and header-only CSV files with `--volume`. |
| `rulesVersion` | semantic-version string | yes | Exact `rulesVersion` read from Object 3. |

### `Target`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `object` | Salesforce API-name string | yes | Target object. The SOQL command parses the first simple `FROM`; a supplied `--object` must match. The CSV command requires `--object`. |
| `operation` | enum | yes | `insert`, `update`, or `upsert`; always confirmed by the data-load owner. |
| `writtenFields` | unique sorted API-name string[] | yes | Fields the load writes. Never inferred from CSV headers or a SOQL SELECT list. |
| `estimatedVolume` | non-negative integer | yes | Exact CSV data-row count or owner estimate for a query-defined load or header-only chat attachment. Header-only `--volume` requires a positive integer. |
| `volumeSource` | enum | yes | `row_count` for the `csv` adapter; `user_supplied` for the `soql` adapter, including header-only CSV files with `--volume`. |
| `upsert` | Upsert or null | yes | Non-null only when `operation` is `upsert`. |
| `aggregates` | Aggregates | yes | Aggregate-only lock, predicate, and resolution evidence. |

### `Upsert`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `matchField` | API-name string | yes | External-ID match field confirmed by the data-load owner. |
| `insertShare` | number, 0 through 1 | yes | Fraction expected to insert, supplied by the data-load owner. |
| `shareSource` | enum | yes | `user_supplied` in v1.0.0. |

The update share is `1 - insertShare`. Unresolved evidence belonging only to that share carries
`branch: "update"`, `volumeShare`, and `estimatedVolume`. The insert branch still follows insert
semantics: an absent relationship column means null and is complete, not unresolved.

### `Aggregates`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `relationshipColumns` | RelationshipAggregate[] | yes | Measured CSV or supplementary aggregate-result evidence, sorted by `column`. |
| `predicateStats` | PredicateStat[] | yes | Evaluated Object 3 row predicates, sorted by `ruleId`. |
| `unresolved` | Unresolved[] | yes | Evidence the local inputs cannot determine, sorted by `column`. |

### `RelationshipAggregate`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `column` | API-name string | yes | Relationship field from Object 3 and/or Object 2. |
| `polymorphic` | boolean or null | yes | From Object 2 when supplied. Without Object 2, an Object 3 `columnTargets.include` list proves `false` at length one and `true` above one; otherwise this is `null`, never a guess. |
| `populatedRows` | non-negative integer | yes | Rows whose relationship value is a valid 15- or 18-character alphanumeric Salesforce ID. |
| `nullRows` | non-negative integer | yes | Rows whose relationship ID is empty. |
| `nonIdRows` | non-negative integer | yes | Non-empty rows whose value is not a 15- or 18-character alphanumeric Salesforce ID. These values are never included in any distribution or parent output. |
| `flag` | enum | when `nonIdRows > 0` | Exactly `non_id_values`; accompanied by a file-level warning that the column may be mis-mapped. |
| `typeDistribution` | TypeDistribution[] | yes | Populated-row counts grouped by three-character prefix, sorted by prefix. |
| `fanIn` | FanIn | yes | Rows-per-parent distribution. |

For a relationship column measured directly from the input CSV, the sum of `populatedRows`,
`nullRows`, and `nonIdRows` equals `estimatedVolume`; `validate_payload()` enforces this invariant
on the CSV path.
For a `--soql-result` aggregate export, these counts are the grouped result totals. A non-ID value
is counted but is never copied, hashed, prefix-grouped, or included in fan-in/top-parent evidence.

### `TypeDistribution`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `prefix` | string, at most 3 characters | yes | First three characters of a populated relationship ID. |
| `object` | string or null | yes | Per-org resolution from Object 2 `keyPrefixes`; never a global-table guess. |
| `rows` | non-negative integer | yes | Rows carrying the prefix. |
| `flag` | enum | when unresolved | Exactly `unresolved_prefix` when `object` is null. |

### `FanIn`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `distinctParents` | non-negative integer | yes | Count of distinct non-null parent IDs. |
| `maxRowsPerParent` | non-negative integer | yes | Largest count for one parent; zero when none. |
| `histogram` | HistogramBucket[6] | yes | Fixed ordered buckets: `1`, `2-10`, `11-100`, `101-1000`, `1001-10000`, `>10000`. |
| `topParents` | TopParent[] | yes | At most `--top-k`, ordered by descending rows then raw ID for ties. |
| `idRepresentation` | enum | yes | `raw`, or `sha256_12` when `--hash-ids` is used. |

`HistogramBucket` has required string `bucket` and required non-negative integer `parents`.
`TopParent` has required string `id` and required non-negative integer `rows`. A `sha256_12` ID
is the first 12 lowercase hexadecimal characters of SHA-256 over the canonical ID text.

Every valid 15- or 18-character Salesforce ID is canonicalized to its first 15 characters,
case-sensitively, before parent counting, prefix resolution, tie-breaking, or hashing. Consequently,
both forms of the same Salesforce ID contribute to one parent, and raw `TopParent.id` values are
always the canonical 15-character form.

### `PredicateStat`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `ruleId` | string | yes | Object 3 rule identity. |
| `fields` | sorted API-name string[] | yes | Fields required by the row predicate. |
| `evaluableRows` | non-negative integer | yes | Rows evaluated after all predicate fields were confirmed present. |
| `matchingRows` | non-negative integer | yes | Rows matching every condition; never greater than `evaluableRows`. |
| `note` | string | yes | Human-readable predicate meaning supplied by Object 3. |

If `conditions.all` is absent or empty, any required CSV column is absent, or an operator is
unsupported, no statistic is emitted for that predicate and `warnings` names the rule and says
why. An incomplete predicate never matches vacuously. Target-, self-, and other non-row predicates
are not evaluated locally. A predicate's supplied `note` is copied verbatim. As a defensive
compatibility fallback, an otherwise evaluable predicate with no `note` receives the generic text
`Row predicate from rules data; human-readable note unavailable.` and a warning naming the rule.

### `Unresolved`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `column` | API-name string | yes | Relationship whose aggregate is unknown. |
| `reason` | string enum | yes | `update_stored_values_unknown` or `soql_row_values_unavailable`. |
| `resolution` | enum | yes | Exactly `generated_soql`. |
| `soql` | string | yes | Generated aggregate template using `...loaded set...`; the data-load owner replaces that placeholder. |
| `branch` | enum | upsert update-only evidence | Exactly `update`. |
| `volumeShare` | number | with `branch` | Upsert update share. |
| `estimatedVolume` | number | with `branch` | Total target volume multiplied by `volumeShare`; may be fractional because the share is an estimate. |

The generated query is:

```sql
SELECT <column>, COUNT(Id) c FROM <object>
WHERE Id IN (...loaded set...)
GROUP BY <column> ORDER BY COUNT(Id) DESC
```

`validate_payload()` requires unresolved SOQL to start with `SELECT`, contain `GROUP BY`, and
retain the `...loaded set...` placeholder.

The supplementary CSV passed as `--soql-result <column>=<file.csv>` must contain at least the
named relationship column and aggregate alias `c`; additional exporter columns are ignored.
The script consumes the grouped IDs locally and emits only Object 1 aggregates. The named column
must exist in the relationship inventory. On the CSV adapter, a column already measured from the
load file is a hard conflict unless `--soql-result-override` is supplied; an override replaces the
CSV measurement and emits a warning, so a supplementary input is never silently ignored.

### `AskAudit`, `Assumption`, and warnings

| Object / field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `AskAudit.question` | string | yes | Confirmation question. |
| `AskAudit.answered` | boolean | yes | Always `true` in a written payload. |
| `Assumption.key` | string | yes | Stable assumption key. |
| `Assumption.value` | JSON scalar | yes | Assumed value. |
| `Assumption.label` | string | yes | Provenance/certainty label. |
| warning entry | string | yes | Degradation that did not prevent a valid aggregate payload. |

### Pending-ask envelope

Pending asks are not Object 1. When required information is missing, the CLI exits 2, writes no
payload, and prints one JSON object to stdout:

```json
{
  "asks": [
    {
      "key": "writtenFields",
      "question": "Which fields does the load WRITE? ... suggestion only; confirmation required ...",
      "required": true
    }
  ]
}
```

Every pending ask has exactly `key` (stable answer-file key), `question` (string), and
`required: true`. Required keys are:

| Key | Raised by | Satisfied by |
| --- | --- | --- |
| `operation` | every adapter when absent | `--operation` or `answers.operation` |
| `writtenFields` | every adapter when absent | `--written-fields` or `answers.writtenFields` |
| `estimatedVolume` | SOQL command when volume is absent | `--volume` / `--estimated-volume` or `answers.estimatedVolume` |
| `upsertMatchField` | upsert when absent | `--upsert-match-field` or `answers.upsertMatchField` |
| `upsertInsertShare` | upsert when absent | `--upsert-insert-share` or `answers.upsertInsertShare` |
| `query` | SOQL adapter parse failure | corrected query file |

An answers file must have a JSON-object root. Non-null `operation` and `upsertMatchField` values
must be strings; `writtenFields` must be a string or an array containing only strings;
`estimatedVolume` must be a non-negative JSON integer (booleans, floats, objects, and numeric
strings are rejected); and `upsertInsertShare` must be a JSON number from 0 through 1 (booleans
are rejected). A null value remains unanswered. Wrong types exit nonzero with a one-line error
naming `answers.<key>` and the expected type; they are never coerced.

The CSV header and SOQL SELECT list may appear only in the ask question as candidate field names,
explicitly marked as a suggestion. They are never adopted as `writtenFields` without confirmation.
For a header-only chat attachment, the CSV command takes the owner's estimate explicitly through
`--volume N`. It requires a header, zero data rows, and a positive integer estimate, then uses the
SOQL profiling route. Row predicates remain unevaluated and lookup evidence comes only from
owner-supplied grouped results with a `c` count column through `--soql-result COLUMN=RESULT.csv`.
Without those counts, written lookup fields remain unresolved. The CSV command ignores
`answers.estimatedVolume`; counted files always use their row count.

## Object 2: org-context export

One engagement-local JSON document exported through Elements. `_sample` exists only in the
hand-authored sample and is ignored by the profiler.

### Root fields

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `_sample` | boolean | sample only | Marks non-customer fixture data. |
| `orgContextVersion` | semantic-version string | yes | Object 2 schema version; sample is `1.0.0`. |
| `refModelId` | string | yes | Elements reference-model identity. |
| `exportedAt` | RFC 3339 timestamp string | yes | Export time. |
| `keyPrefixes` | map<string,string> | yes | Per-org three-character prefix to object API name from full target and directly referenced Object documents. |
| `objects` | map<string,OrgObject> | yes | Target-object relationship inventories keyed by object API name. |

The org-context parser preserves JSON member pairs long enough to detect duplicate entries inside
`keyPrefixes`. A duplicate prefix is a hard error naming that prefix; the last value never silently
replaces the first.

The exporter fetches full Object documents for the load targets and every object in their reference
fields' `referenceTo`. For a polymorphic field with more than 50 distinct targets, it fetches the
first 50 names in lexicographic order to bound document work. It retains all declared relationship
targets and reports every omitted object or unreadable prefix in `couldNotCover` beside Object 2.
Only load targets receive relationship inventories in `objects`. Unresolved observed prefixes
remain explicit in the aggregate payload.

### `OrgObject` and `RelationshipField`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `OrgObject.relationshipFields` | RelationshipField[] | yes | Relationship fields for that target object. |
| `RelationshipField.apiName` | API-name string | yes | Relationship column. |
| `RelationshipField.subtype` | string | yes | Metadata subtype, including `Lookup` or `MasterDetail`. |
| `RelationshipField.custom` | boolean | yes | Whether the field is custom. |
| `RelationshipField.polymorphic` | boolean | yes | Whether IDs may target multiple object types. |
| `RelationshipField.targets` | API-name string[] | yes | Metadata-declared possible targets; may be empty if unavailable. |
| `RelationshipField.deleteConstraint` | string or null | yes | Metadata deletion behavior, without inference. |
| `RelationshipField.deletionEvidenceSource` | string or null | yes | Source of the deletion fact, or null if unavailable. |

If Object 2 is omitted, the profiler still runs. Every observed prefix has `object: null` and
`flag: "unresolved_prefix"`, and Object 1 contains the degraded-mode warning. Prefixes are never
resolved from a cross-org/global prefix table.

## Object 3: profiler rules data

This document is generated from the production rules-data service and stamped
with `RULES_VERSION`. The local profiler does not maintain a second Task/Event/locking table.
`_sample` exists only in the hand-authored sample and is ignored.

### Root fields

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `_sample` | boolean | sample only | Marks non-production fixture rules. |
| `rulesVersion` | semantic-version string | yes | Rules export version copied to Object 1. |
| `objectSpecific` | map<string,ObjectRule> | yes | Rules keyed by object API name. |
| `genericLookup` | GenericLookup | yes | Rule IDs and note for org-specific lookup/master-detail behavior. |

### `ObjectRule`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `relationshipColumns` | unique API-name string[] | yes | Object-specific lock-relevant relationship fields. |
| `columnTargets` | map<string,ColumnTargets> | yes | Target inclusion/exclusion restrictions from the server rules. |
| `columnOutcomes` | map<API-name,map<operation,string>> | when the server rule supplies field outcomes | Per-column operation outcomes generated from server `fieldOutcomes`. |
| `predicates` | Predicate[] | yes | Structured predicate inputs. |
| `outcomes` | map<operation,string> | yes | Server rule outcome by applicable operation. |

The effective required-column inventory is the union of `relationshipColumns` and Object 2's
`relationshipFields`. This makes built-in rules and org-specific custom lookup/master-detail
facts additive. For a given column, consumers read `columnOutcomes[column]` first and fall back to
the object-level `outcomes` map when no per-column override exists.

### `ColumnTargets`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `include` | API-name string[] | exactly one of include/exclude | Only these target types apply. |
| `exclude` | API-name string[] | exactly one of include/exclude | These target types do not apply. |

### `Predicate` and `Conditions`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `ruleId` | string | yes | Stable rule identity. |
| `fields` | API-name string[] | yes | Fields required to evaluate; empty for target-only rules. |
| `scope` | enum | yes | `row`, `target`, or `self`. Only `row` is evaluated by the CSV adapter. |
| `appliesTo` | map<operation,string> | yes | Operations and server-side outcome/conditionality. |
| `conditions` | Conditions | every `scope: "row"` predicate | Machine-evaluable form. |
| `note` | string | yes | Human-readable meaning copied into Object 1 stats. |

`Conditions.all` is a producer-required, non-empty Condition array for every v1 row-scope
predicate. Every condition must match for a row to match. Consumers skip the predicate with a
warning naming its `ruleId` when `conditions.all` is absent/empty or an operator is unknown; they
never interpret an empty conjunction as a match. The wire shape is
`{"all": [{"field": "ApiName", "operator": "equals", "value": "text"}]}`; `value` is omitted
for `not_null`.

| Condition field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `field` | API-name string | yes | Row field. |
| `operator` | enum | yes | `equals` or `not_null` in contract 1.0.0. |
| `value` | JSON scalar | when operator is `equals` | Exact value converted to text before comparison. |

Unsupported or incomplete predicate data is reported as non-evaluable; the profiler never
guesses an interpretation.

### `GenericLookup`

| Name | Type | Required | Semantics |
| --- | --- | --- | --- |
| `note` | string | yes | Explains that Object 2 supplies org-specific relationship fields. |
| `rules` | string[] | yes | Server rule IDs applied after Object 2 inventory resolution. |
| `predicates` | Predicate[] | no | Sanctioned additive structured predicates for generic lookup behavior. |

## Related Object 4 server output

Object 4 is server-owned related output and is not validated by this local Object 1 validator.
Two additive shapes are ratified: entries in `lockRows` may carry a `branch` field identifying the
operation branch that produced the row, and `masterDetailEdges` is object-shaped metadata rather
than a scalar or string list. Consumers of Object 4 must preserve those fields; the local profiler
does not synthesize or validate them.

## Operation branching

- **Insert:** an absent required relationship column means the load writes null. It has
  cardinality zero, is omitted from `relationshipColumns`, and never creates an unresolved entry.
  A relationship column present in the CSV but absent from confirmed `writtenFields` is likewise
  omitted, with a warning listing every present-but-unwritten relationship column.
- **Update:** an absent column does not reveal the stored relationship value. Emit one
  `update_stored_values_unknown` entry and its generated aggregate query. A matching
  `--soql-result` replaces that unresolved entry on the second run.
- **Upsert:** apply both rules. The absent insert share is complete/null; the update share emits
  branch-labeled unresolved evidence. A present relationship column still reports full-file NEW
  value aggregates, while its update share emits `update_stored_values_unknown` for the pre-write
  STORED values. The data-load owner supplies both match field and insert share.
- **SOQL:** a SELECT list describes fields read, not fields written. The confirmed written fields
  control insert relevance; update/upsert still require stored-value aggregates. The pasted query
  itself is never copied into Object 1.

PK chunking is an extraction concern and is not represented anywhere in Object 1.

## Extending with a new adapter

An adapter converts one local input type into the same logical result used by the two built-in
adapters. It must return enough information to build one validated `Target`:

| Adapter result | Required behavior |
| --- | --- |
| object | Return a parsed or explicitly supplied object API name; raise an ask when parsing is required but impossible. |
| operation | Return only an operation confirmed by the data-load owner; otherwise raise `operation`. |
| written fields | Return only names confirmed by the data-load owner; otherwise raise `writtenFields` and label inferred candidates as suggestions. |
| volume | Return an exact count with its source, or raise `estimatedVolume`; never estimate silently. |
| upsert | For upsert, require `upsertMatchField` and `upsertInsertShare`. |
| relationship evidence | Return aggregate counts only, using the Object 2/Object 3 union; apply insert/update/upsert branching exactly. |
| predicate evidence | Evaluate only Object 3 executable row conditions whose fields are present; warn for non-evaluable predicates. |
| warnings | Return explicit degradation messages; never substitute guessed facts. |

The adapter must not return or retain raw records in Object 1. It may propose local input field
names only in the pending-ask envelope. Add its adapter name to the `GeneratedBy.adapter` enum,
write behavior tests through the CLI, pass the result through `validate_payload()`, and serialize
with sorted keys and deterministic list ordering.

The v1 validator type-checks every array before iteration, rejects unknown fields on every nested
object (including histogram buckets and top parents), and reports an indexed offending path.
It also requires `unresolved_prefix` exactly when a type-distribution object's `object` is null,
API-name strings in every predicate `fields` entry, and adapter-consistent volume sources
(`row_count` for CSV and `user_supplied` for SOQL).

## Version policy

`contractVersion` follows semantic versioning:

- Patch: wording/clarification or validator correction that does not change accepted data.
- Minor: backward-compatible additive fields or enum values. Consumers must ignore documented
  optional fields introduced by a supported minor version.
- Major: field removal/rename, required-field addition, type change, or semantic incompatibility.

`orgContextVersion` and `rulesVersion` version their own producer schemas independently. An Object
1 producer copies Object 3's exact `rulesVersion`; it does not derive it from `contractVersion`.
The v1.0.0 local validator rejects unknown Object 1 fields so accidental raw data cannot leak;
support for a future minor contract must be added deliberately before that version is emitted.
