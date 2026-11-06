# Deterministic script command-line interfaces

All card commands run from the engagement directory and invoke each script as `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py"`; the test suite and `lint.py` are developer commands run from the plugin root. Shipped commands also accept `python3 -I`, including sibling-module imports, from any engagement directory. A successful command exits 0. A contract, input, or file error exits 1 with one aggregate-safe line on standard error, except where a command defines specific codes below. Invalid command syntax exits 2 through `argparse`, except `load_input_prep.py`, where exit 2 is the documented pending-questions result.

Scripts never print raw comma-separated value (CSV) rows, Salesforce Object Query Language (SOQL) results, debug-log lines, record identifiers, or field values. Success messages contain counts and completion status only.

## `now.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/now.py"
```

Output: the host clock's current Coordinated Universal Time (UTC) in International Organization for
Standardization (ISO) 8601 format. Run it at each event whose time the playbook records.

## `load_input_prep.py`

Purpose: count a local CSV load before the baseline call, or profile a local CSV file, header-only
chat attachment with an owner estimate, or SOQL extract definition into aggregate-only Object 1
JavaScript Object Notation (JSON).

Count form:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" count --file LOAD.csv
```

The count form needs no rules file and prints `{"rows": N, "candidateWrittenFields": ["FieldName"]}`
on standard output. `N` is the number of data rows, excluding the header. The field names come
from the header for the owner's single manifest confirmation. It handles UTF-8 with a byte order mark, carriage return
and line feed endings, and quoted multiline cells. A header-only file returns zero. When the
session has no local path to the source, card 02 accepts only a header-only source attachment and
uses the owner's approximate positive row count for the baseline call. For a local load file,
the CSV profiler records the counted rows as `targets[0].estimatedVolume` with
`volumeSource: "row_count"`; card 02 compares the two counts before continuing and never asks the
owner for volume. A nonpositive load volume stops before the baseline call.

Slice form for the rehearsal:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" slice --file LOAD.csv --out work/rehearsal/batch.csv --rows 200
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" slice --file LOAD.csv --out work/rehearsal/batch.csv --rows 200 --sort-by Parent__c
```

Use the `rehearsal_batch_rows` value in `data/thresholds.csv` for `--rows`. The script writes the
header and up to that many first data rows to the local output file. With `--sort-by`, it
stably sorts those selected rows by the named header field and keeps the header first. Card 06
passes `parentSortField` from finalized parameters only when grouping is on and the field is in
the source header. Without a known field, the batch stays in file order and the playbook states
"parent grouping was not rehearsed" as a risk. It prints only
`{"rows": N, "candidateWrittenFields": ["FieldName"], "lineEnding": "LF|CRLF"}`; the row count
is the number actually written, and `lineEnding` names the output's record terminator for the
sf CLI `--line-ending` flag. The output is UTF-8 without a byte order mark. The command rejects
an empty source, a nonpositive limit, an absent sort field, malformed selected rows, and an output path equal to the
source path. It replaces the output only after writing a complete batch.

CSV form:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" csv --file LOAD.csv --object OBJECT --rules RULES-DATA.json --out PAYLOAD.json [--operation insert|update|upsert] [--written-fields FIELD,...] [--volume N] [--answers ANSWERS.json] [--org-context ORG-CONTEXT.json] [--hash-ids] [--top-k N] [--soql-result COLUMN=RESULT.csv] [--soql-result-override] [--upsert-match-field FIELD] [--upsert-insert-share FRACTION]
```

For a header-only chat attachment, pass `--volume N` explicitly with the owner's positive integer
estimate. This option requires a header and zero data rows. It profiles through the SOQL route,
emitting `generatedBy.adapter: "soql"`, `estimatedVolume: N`, and `volumeSource: "user_supplied"`.
Confirm written fields from the header; an `Id` column suggests update. Row predicates stay
unevaluated. Written lookups remain unresolved until the owner supplies grouped counts through
`--soql-result COLUMN=RESULT.csv`; these results must contain the lookup column and a `c` count
column. They need no `--soql-result-override` because the header contains no measurements.
Use `--hash-ids` so parent identifiers in the aggregate payload are hashed.
For example, `--volume 12000` records 12,000 planned rows; a grouped result with counts 11,000
and 1,000 records two parents and a maximum of 11,000 rows per parent.
An empty source, any data rows, a nonpositive estimate, or an ungrouped result exits 1 with an
aggregate-safe error and leaves any existing payload unchanged. Without `--volume`, the CSV form
counts the file's rows. `answers.estimatedVolume` applies to the SOQL form only.

SOQL form:

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" soql --query-file QUERY.soql --rules RULES-DATA.json --out PAYLOAD.json [--object OBJECT] [--operation insert|update|upsert] [--written-fields FIELD,...] [--volume N] [--answers ANSWERS.json] [--org-context ORG-CONTEXT.json] [--hash-ids] [--top-k N] [--soql-result COLUMN=RESULT.csv] [--soql-result-override] [--upsert-match-field FIELD] [--upsert-insert-share FRACTION]
```

Profiler inputs: local load evidence; `rules-data.json` copied from a baseline `run_data_load_impact`
bundle; optional org context and supplementary aggregate SOQL results. Output: one profiler payload.
For unresolved lookup fields, one result file may contain all lookup columns from a single
ungrouped query. Repeat `--soql-result COLUMN=RESULT.csv` for each column, using that same file.
A grouped result with a `c` count column is also accepted.
Exit 2 writes a pending-questions JSON envelope to standard output and does not write the payload.

## `tool_targets.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tool_targets.py" PAYLOAD.json [PAYLOAD.json ...] --ref-model-id ID [--team-id SPACE-ID] --out TOOL-TARGETS.json --residue RESIDUE.json [--depth-bound 1..10]
```

Input: one or more profiler payloads. Pass `--team-id` when the Space is known; each call then
includes `teamId` with `refModelId`. Outputs: `TOOL-TARGETS.json` with `calls[]`, where every call
has exactly one strict `targets` entry, and `RESIDUE.json` with every field the production schema
rejects. Zero volume, more than 200 written fields, unresolved type entries, and other
non-projectable inputs are never coerced. Invoke `run_data_load_impact` once per
`calls[].arguments` object.

## `part_files.py join`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/part_files.py" join --replies REPLIES-DIR --out JOINED.ndjson
```

Both arguments are required. The orchestrator saves each Model Context Protocol (MCP) tool reply
verbatim inside this JSON envelope as `REPLIES-DIR/<n>.json`, with `n` starting at 1 in call order:

```json
{"savedAt": "2030-01-01T00:00:00Z", "reply": {"status": "complete", "resultId": "example", "computedAt": "2030-01-01T00:00:00Z", "totalRows": 0, "partsTotal": 0, "parts": [], "failed": []}}
```

`savedAt` is the UTC ISO 8601 time when the orchestrator saves that reply. `reply` is the complete
tool reply object, including its part metadata. Replies are read in numeric filename order. The
script uses the last `(resultId, computedAt)` group. Running replies belong to the following
complete reply; returning to `running` after `complete` resets collection. A changed `computedAt`
starts a new group even when `resultId` stays the same.

The final reply must be `complete`, contain no `nextPartsFrom`, and supply, across the kept
replies, exactly the indices `0..partsTotal-1`. A repeated index must have the same Secure Hash
Algorithm 256-bit (SHA-256) checksum. A final failed reply, any non-empty `failed`, or a non-null
`failedTotal` in the kept replies refuses the join. A complete zero-part, zero-row result writes
an empty file. Refusal replies without `resultId` and with an `error` key are skipped when grouping
saved replies. A refusal before a recovered successful reply does not prevent the join; a final
refusal leaves the result incomplete.

Every part must have `format: "ndjson"` (newline-delimited JSON, NDJSON). Its expiry is the save
time of the reply listing it plus its own `expiresInSeconds`. A repeated part uses its latest
listing's save time and metadata. All needed parts must be unexpired before downloading. The
script accepts only Hypertext Transfer Protocol Secure (HTTPS) links with status 200, non-empty
content and no Hypertext Markup Language (HTML) error page. It verifies each part's SHA-256 and
`bytes`, joins parts in index order, and checks the joined row count against `totalRows`. Output
uses a temporary file followed by atomic replacement; a refused join preserves existing output.
Standard output is one JSON object containing only `parts`, `rows`, and `bytes`, for example
`{"parts": 2, "rows": 2, "bytes": 18}`. Diagnostics contain neither Uniform Resource Locators
(URLs) nor row content.

| Exit | Meaning |
|---|---|
| 0 | Joined successfully. |
| 2 | Incomplete result, paging or indices; also invalid command syntax. |
| 3 | A needed part has expired; make the identical tool call again and save its replies. |
| 4 | Failed result or reported item failures. |
| 5 | Integrity, malformed input, download or file error. |

## `source_files.py fetch` and `scan`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_files.py" fetch --replies REPLIES-DIR --root SOURCE-DIR --sync-date SYNC-TIMESTAMP
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_files.py" scan [--root SOURCE-DIR]
```

All `fetch` arguments are required. `scan` defaults `--root` to `work/source`. `fetch` joins saved
`get_metadata_source` replies using the envelope and rules above into temporary local NDJSON.
Rows carry `{nodeId, apiName, sfType, lastModifiedDate, status, reason, xmlScope, xmlFormat, xml,
body}` and are keyed by `nodeId`, independent of their input order.

For `status: "ok"`, the script writes Extensible Markup Language (XML) to `<root>/<sfType>/<apiName>.xml` and a non-null
`body` to `.cls` for Apex Class, `.trigger` for Apex Trigger, or `.body` for other types. The
manifest outcome is `downloaded`. For `not_available`, the outcome equals `reason`:
`not_found`, `no_stored_definition` or `file_missing`. `managed_code_hidden` keeps XML when
present and writes no body. Unsafe `apiName` or `sfType` path characters reject that row with
outcome `failed` and error `unsafe_name`; other rows continue.

`<root>/manifest.json` has a `files` array. Entries record `nodeId`, `apiName`, `type` (the row's
`sfType`), `status`, `outcome`, `reason`, `xmlScope`, and `syncDate` from `--sync-date`. Written
files appear as `xml: {"path": "<relative path>"}` and `body: {"path": "<relative path>"}`. The
manifest merges by `nodeId`, replacing matching entries and retaining the other entries for the
helper round. Source text stays in source files; the manifest contains paths and outcomes.
Standard output contains only counts for outcomes present in the merged manifest, for example
`{"downloaded": 2, "not_found": 1}`. URLs and source text stay out of standard output and the
manifest. Exit codes 2 through 5 propagate join refusals as above; other source or manifest
errors exit 1 with a safe diagnostic. A successful fetch exits 0, including row-level failures
recorded in the manifest.

`scan` reads downloaded Apex Class and Apex Trigger bodies and Flow XML from manifest paths and
prints `{"missingCalledClasses": ["HelperClass"]}` for one helper-class fetch. It discovers
static calls (keeping the class name from namespace-qualified calls), constructors, superclass
names and Apex Flow actions. It excludes comments, string literals, local classes, platform types,
downloaded Apex classes, and known object names. Declared instance receivers are excluded within
their declaring block; method and loop parameters apply to their following braced body. Qualified
calls rooted in those variables or platform types are also excluded. Field names remain eligible
as class candidates, and constructors remain eligible when a local variable shares their name.
Schema names come from standard objects, manifest object entries, Flow object references, and Apex
query and schema references. Namespaced schema references also identify package namespace receivers
to exclude.
Apex metadata XML and other source types supply no helper calls. These are candidate
names; resolve them with `search_metadata` restricted to Apex Class and keep exact `apiName`
matches. The scan exits 0 on success or 1 on a source or manifest error. The auditor reads source
files directly from manifest paths.

## `bypass_set.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bypass_set.py" BUNDLE-DIR [BUNDLE-DIR ...] --narration NARRATION.json [NARRATION.json ...] [--managed-packages MANAGED-PACKAGES.json] [--duplicate-rules DUPLICATE-RULES.json] [--unpredicted-automations UNPREDICTED.json] --out AUDIT-SET.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bypass_set.py" --audit-set AUDIT-SET.json --source-manifest SOURCE-MANIFEST.json --out AUDIT-SET.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bypass_set.py" --audit-set AUDIT-SET.json --verdicts VERDICTS.csv
```

Build inputs are bundle `automations.csv`, `fire-chain-digest.csv`, and every touched object's
narration. Narration requires `object` and `automations`, an array of `{name, type}` with optional
explicit `apiName`. Empty arrays are valid; missing arrays require regeneration with the narrator.
The script identifies automations by `(target, type, apiName)`. Narration matches a bundle entry
on the same object and metadata type by exact application programming interface (API) name, or by
exact name or label when narration supplies no `apiName`. Explicit names retain their namespaces.
It includes direct and transitive bundle automations, managed namespaces, active duplicate rules
and rehearsal observations once per identity. It adds unmatched narration names
with `origin: narration-only` and `originEvidence` stating "named in the order-of-execution
explanation; not in the Elements load analysis". Audit rows retain `target`, `apiName`, `name`,
`type`, and any supplied `nodeId`. The orchestrator resolves narration names using schema-derived
synced types, including Process Builder Workflow and Flow, and retries the exact full label without
a type filter. It retains resolved ownership as `namespace` and `isManaged`.
After source fetch, normalization uses `files[]` in the source manifest to resolve every node's type
through the checklist's shared resolver in `dli_common.py`. The shared alias map emits synced type
names, including `Process Builder Workflow` and `Workflow Rule`. Manifest `apiName` supplies the
resolved name. Rows sharing a node and target merge, preferring the bundle row and retaining
`narrationNames`, `narrationEvidence`, and supplied activation evidence. Distinct targets stay separate.
Normalization freezes the `(target, type, apiName)` keys before auditor dispatch; `--out` may name
the input audit-set file. Conflicting resolved identities fail without replacing the output.

Verdict rows carry the audit entry's `target`, `type`, and `apiName`. Validation requires exactly one
evidenced `present`, `absent`, or `unknown` verdict per audit identity and no extras. Legacy verdicts
with omitted identity fields must resolve to exactly one audit entry. Narration additions also require `active` (`true`, `false`, `unknown`) and
`activeEvidence` from metadata. Inactive additions require `nonFiring: true` and
`nonFiringEvidence`. Unverified activation requires `verdict: unknown` and empty `nonFiring`.
Assess a shared source component once by `nodeId` and project identical `verdict`, `scope`, `switch`,
and `evidence` onto its target rows. Validation rejects conflicting shared-source hook facts;
target-specific `nonFiring` and `nonFiringEvidence` may differ. A present hook skips the automation's
work for this load; a partial error exemption or commented-out call does not qualify.
Malformed input or incomplete evidence exits 1 with an aggregate-safe error; failed builds preserve
existing output. Success prints only completion status and counts.

## `impact_report.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/impact_report.py" BUNDLE-DIR [BUNDLE-DIR ...] --out REPORT.md [--residue RESIDUE.json] [--duplicate-rules DUPLICATE-RULES.json] [--managed-packages MANAGED-PACKAGES.json] [--narration NARRATION.json ...] [--audit-set AUDIT-SET.json] [--bypass-verdicts VERDICTS.csv] [--unpredicted-automations UNPREDICTED.json]
```

Inputs: complete downloaded bundle directories and optional local residue. Output: one Markdown impact report with a section per target. It lists automations from `automations.csv`, managed-code namespace gaps from receipts, response-only email sender, parent volume, gated-column, skew-source, and per-branch coverage evidence. Every unresolved residue column is named with its generated SOQL and marked as incomplete coverage.
The optional duplicate-rules input maps each target object to its active rule names. The
managed-packages input maps target objects to namespaces and trigger names. Narration files carry
the narrator's `object` and `narrative`; repeated `--narration` flags and multiple narratives for
one object all render. A structured `narrative` contains `toolFacts`, a list of plain sentences
for populated phases, and `explanation`, a paragraph connecting those facts to digest evidence.
The renderer prints one bullet per fact followed by the explanation paragraph. It omits empty
facts, phases whose entire value is `Not found`, and the tool's `source` field, and expands raw
phase keys to readable labels. The "Automations that fire" section uses matching branch and trigger-event
evidence. The missing-namespace notice appears when no package lookup is supplied for that target.
The bypass verdicts input omits an automation from that section when its `nonFiring` field is
`true`. Direct automations with empty trigger events remain listed with "trigger events unknown".
Pass the audited verdicts on report regeneration so the report reflects metadata entry
conditions. Narration punctuation is normalized to commas where it contains an em dash.
With `--audit-set` and audited verdicts, narration-only additions render with their origin, bypass
verdict and activation evidence for both load targets and related touched objects. Active additions
are marked as potentially firing; inactive additions are marked not firing. Unverified activation
is stated as unverified. The report validates activation evidence before rendering these additions.

## `checklist.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" BUNDLE-DIR [BUNDLE-DIR ...] --loader LOADER --confirmed-api API --tool-targets TOOL-TARGETS.json --bypass-verdicts VERDICTS.csv [--audit-set AUDIT-SET.json] --managed-packages MANAGED-PACKAGES.json --duplicate-rules DUPLICATE-RULES.json --checklist-out DRAFT-CHECKLIST.csv --parameters-out DRAFT-PARAMETERS.json [--source-manifest SOURCE-MANIFEST.json] [--prior-parameters PARAMETERS.json] [--data-dir DIR] [--named-serial-operation REASON] [--target-fact OBJECT:OPERATION=FACT ...] [--unpredicted-automations UNPREDICTED.json]

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" --finalize --draft-checklist DRAFT-CHECKLIST.csv --draft-parameters DRAFT-PARAMETERS.json --owner-checklist OWNER-CHECKLIST.csv --owner-parameters OWNER-PARAMETERS.json --checklist-out CHECKLIST.csv --parameters-out PARAMETERS.json [--prior-parameters PARAMETERS.json] [--data-dir DIR]

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" --apply-lock-ladder --checklist CHECKLIST.csv --parameters PARAMETERS.json --lock-errors COUNT --parameters-out PARAMETERS.json [--data-dir DIR]
```

Draft mode reads the projected tool calls and bundle evidence, then writes a checklist and proposed
execution parameters. On every return from rehearsal, pass the prior finalized package with
`--prior-parameters` in draft mode. The draft proposes its effective `groupByParentId`,
`parentSortField`,
`concurrencyMode`, `api`, `batchSize`, and `serialModeEvidence` values. Finalize mode compares the owner-completed copies with the draft, validates
each owner ruling and replacement check, records parameter changes with who and when, and recomputes
all incident controls. A finalized parameters file carries `packageStatus: "finalized"`.
Finalize mode accepts matching header-only draft and owner checklists and still requires
`ratifiedBy` and `ratifiedOn` for the parameters.
The loader and confirmed Application Programming Interface (API) come from `manifest.loader` and
`manifest.api`; the draft preserves that API when the loader supports it. A Bulk API 2.0 loader uses
server-managed batch size and parallel concurrency. If a serial reason applies and the confirmed
API cannot run serial mode, the draft records `serialModeUnavailable` and `knownRisks` for the owner
to rule, including when Data Loader is confirmed on Bulk API 2.0.
The managed-packages input maps each target object to namespace and trigger-name groups from card
03's metadata lookup. Receipts and that mapping produce one `Managed Package` row per target and
package; the duplicate-rules input produces one `Duplicate Rule` row per active rule name and target,
which finalization keeps `leave-on`.
Rehearsal observations use name and type as their checklist identity, so distinct automation types
sharing a name each retain a row.
`--audit-set` adds narration-only automations with origin and activation evidence. Inactive additions
are `leave-on` with `non_firing` and excluded from load risks. Unverified activation carries
`activation_unknown` and a named `knownRisks` entry. Process Builder Workflow participates in governor-limit
exposure and uses the existing bypass or deactivation disposition. Stories preserve narration-only
origin and the evidenced firing state, and restore deactivated Process Builder Workflows to their prior state.
Owner reports and stories render a plain coverage statement instead of raw lookup evidence, including
"activation could not be verified" when unresolved. Technical evidence stays in work files.
Checklist and report verdict lookups retain each entry's object, type, and name through delivery.
Verdict rows carry `scope` (`user` or `org-wide`) and `switch` for each `present` hook. The auditor
uses Hierarchy custom settings and Custom Permissions as user-scopable, and List custom settings
and Custom Metadata as org-wide. Checklist columns `bypass_scope` and `bypass_switch` retain these
values; a missing or unrecognized scope on `present` defaults to `org-wide`. A `bypass` row's
`blast_radius` reads "Load user only" for `user` and "Every user while the switch is off" for
`org-wide`. Its disposition remains `bypass`.
The audit and checklist share a node-identifier type resolver. Card 04 normalizes every automation
from `work/source/manifest.json` before auditor dispatch, and card 05 passes the same manifest.
Bundle firing nodes, direct automation and email-sender inventories supply remaining known types,
with `Automation` used only when no type is known. Checklist generation rejects supplied typed
verdicts that do not match a checklist identity. A downstream Apex Class
uses the existing `review: runs only when invoked ...` rule unless it has a present bypass hook.
Managed validation rules propose `leave-on`. Ownership comes from `namespace`, `isManaged`, or the
namespace on the resolved rule name, including qualified manifest names. Their checklist rows retain
`managed_component` in `side_effect_flags`; finalization rejects `deactivate` for these rows.
Verdict rows may include `nonFiring` and `nonFiringEvidence`. An evidenced `true` overrides a
firing proposal to `leave-on` even when the bypass verdict is `absent`; it marks the row
`non_firing`. An explicit `false` keeps the automation in scope. A `true` value without evidence is rejected. A `measured-in-rehearsal` incident
class keeps `controlled: false` until its rehearsal result is recorded. An owner "applies"
answer is represented in `knownRisks`, while `incidentClassRulings` holds only
`not-applicable` and `measured-in-rehearsal`.
Direct Flows and Apex Triggers with no matching event for the operation propose `leave-on` and
carry `non_firing` evidence. A validation rule with explicit `loadDataPasses: true` bundle evidence
also proposes `leave-on`; otherwise the usual disposition applies. The card 05 recommendation
matches each proposed disposition.
Reconciliation merges identical package rulings by namespace. Finalization rejects conflicting
package rulings across targets;
the subscriber rules `leave-on` or an evidenced package bypass, never `deactivate`. Unknown bypass
verdicts propose `leave-on` except for email senders and Apex Classes. Apex Classes propose
`review: ...` unless a present hook supports `bypass`. Owner parameters carry `changedOn`, the time
of the owner's answer, and `incidentClassRulings` for `not-applicable` or
`measured-in-rehearsal` owner rulings. Finalization retains `duplicateRulePredictions` and
`preLoadChecks`, assigning named duplicate rules their target-specific checklist row numbers.
Owner parameters may carry `ownerSteps`, an array of `{story, step, ruledOn}`. `story` is exactly
`pre-load`, `load`, `export-and-reconcile`, `re-enable`, or `rollback`; `step` and `ruledOn` are
nonempty strings holding the owner's instruction and answer time. Finalization copies the entries
to `parameters.json`; package rebuilds preserve them. Invalid entries, including unknown story
values, exit 1 with a single `error: ownerSteps ...` line. An omitted array means no added steps.
Finalization
accepts a package before go or no-go so the reviewer can evaluate it; card 05 finalizes again with
the owner's decision after reviewer blocks close.
Finalization persists trimmed owner rulings. On every return from rehearsal, pass
`--prior-parameters` again in finalize mode. It preserves the change record and records each owner
parameter change against the prior effective value, including a return to the draft value. An
email sender ruled `leave-on` automatically adds "<automation> may send email during the load"
to finalized `knownRisks` for the go or no-go decision. It clears a retained
`unexpected_email: measured-in-rehearsal` ruling because the owner has accepted that email risk.
An accepted persistent lock count remains
valid only while the five lock parameters keep their prior
effective values. The lock ladder command atomically replaces finalized parameters at the same
path without changing checklist rulings. It groups by parent on rung 1 only when
`parentSortField` is known. Otherwise it goes to rung 2 or the owner's rung 3. On rung 2,
it switches to Bulk Application Programming Interface (API) 1.0 serial mode and records the measured
lock error count as serial-mode evidence. It records each changed parameter with author `lock ladder`
and the current date and time, then recomputes incident controls. Exit 0 prints the applied rung;
exit 2 prints that serial mode already ran or is unavailable in the chosen loader. When the loader
cannot run required serial mode, exit 2 writes `serialModeUnavailable` and its known risk to the
parameters file. Exit 1 reports an
invalid input or package.

`checklist.py` derives these facts from `TOOL-TARGETS.json`: `account_owner_write` from
`Account.OwnerId`, `user_role_id_present_or_changed` from `User.UserRoleId`, `user_role_reparent` from
`UserRole.ParentRoleId`, and `territory_reparent_or_membership_change` from
`Territory.ParentTerritoryId` or the `UserTerritory.UserId` and `UserTerritory.TerritoryId` membership
fields. Do not pass those four facts with `--target-fact`; the command rejects them.

Repeat `--target-fact User:<operation>=role_based_portal_user` only for a User insert or upsert whose
records include portal (Experience Cloud) users with a role. This fact depends on record content that
the aggregate manifest does not carry.

## `rehearsal_fired.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rehearsal_fired.py" DEBUG.log [DEBUG.log ...] --success-file SUCCESS.csv [more success CSV files] --error-file ERROR.csv [more error CSV files] --rows-loaded N --out OBSERVED.json
```

Inputs: local Salesforce debug logs and same-job success and error files. Bulk API 2.0 uses
`sf__Id`, `sf__Created`, and `sf__Error`; Bulk API 1.0 and Data Loader use `Id`, `Success`,
`Created`, `Error`, or Data Loader `ERROR`. Data Loader success files with `ID` and `STATUS` are
accepted. A mixed Bulk API 1.0 result counts success and failed
rows separately. `N` is the loaded batch's local row count from `load_input_prep.py count` or its
recorded query count. Output contains names, types, fire counts, processed-log count, completeness,
success and error row counts, aggregate `DUPLICATES_DETECTED` and `UNABLE_TO_LOCK_ROW` counts,
queued-email count, and the highest usage ratio's used and ceiling values for each governor limit
by namespace. The parser reads the event type from the field after the timestamp and line number;
ordinary debug-message payloads never become events. A class name remains observable at 15 or 18
characters.
Managed package entries count by namespace; duplicate-rule invocations count by rule name.
Apex method entries count by class name. A header-only failed-records file is valid when there
are no failed rows.
Completeness requires at least one nonempty log, balanced execution markers where present, no
truncation marker, and success plus error rows equal `N`. Aliases of one result file count once.
When result filenames carry job identifiers, mismatched identifiers are rejected; other filenames
rely on the customer's same-job handoff. Fully blank trailing CSV lines are ignored;
malformed quoting, duplicate headers, broken rows, and empty failed-row errors fail before output.
Raw rows, log content, and identifiers are never emitted.

## `rehearsal_reconcile.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rehearsal_reconcile.py" --checklist CHECKLIST.csv --parameters PARAMETERS.json --observed OBSERVED.json --out RECONCILIATION.csv [--summary-out SUMMARY.json] [--accepted-lock-errors COUNT] [--data-dir DIR]
```

`--parameters` is required and its incident-class ruling array is validated. The finalized
checklist supplies expected silence for `deactivate` and `bypass`, and may-fire
expectations for `leave-on` and Apex Class `review: ...`. A generic or absent type matches by
name; known types must also match. Same-named allowed Duplicate Rules on different targets
reconcile as one observed name. The summary reports evidence completeness, control failures,
unpredicted automation, informational non-observations, duplicate and lock counts, blockers,
and `rehearsalPassed`. Positive lock counts block unless the owner accepted a count after serial
mode ran or when the recorded loader cannot run it; a new count above that accepted value blocks.
Duplicate counts do not. The parameters supply measured incident-class rulings. The summary lists
measured values by class; a measured queued email or governor usage at or above the percentage in
`data/thresholds.csv` adds `measured_incident_class` to blockers and routes to card 05. A missing
measure is `not measurable for <name>` in the summary and does not block. The summary always
reports the observed queued-email count, including when an email sender is accepted as a named risk.
Lock contention uses the aggregate `UNABLE_TO_LOCK_ROW` count as its rehearsal measure, including
zero. The same count drives the lock ladder independently of incident-class measurement.

## `stories.py`

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stories.py" --checklist CHECKLIST.csv --parameters PARAMETERS.json --duplicate-rules DUPLICATE-RULES.json --rehearsal-choice rehearse|skip --org-context ORG-CONTEXT.json --tool-targets TOOL-TARGETS.json --bundle BUNDLE_DIR [--bundle BUNDLE_DIR ...] --out-dir stories/ [--data-dir DIR] [--template TEMPLATE.md]
```

Inputs: the finalized owner-ratified checklist, finalized go-ratified parameters, the three sequencing
data files, and the story template. Every checklist row needs an owner disposition; every validation
rule ruled `deactivate` needs `replacement_data_quality_check`; parameters need
`packageStatus: "finalized"`, non-empty `ratifiedBy`, and `goNoGo: "go"`. Story controls use
`owner_ruling`, never the draft proposal. The duplicate-rules input is the object-to-active-rule
mapping from card 03. Any named active rule adds one post-load rejection review story.
A header-only checklist is accepted with finalized go-ratified parameters and produces all five
core stories from parameters, owner steps, incident controls, the rehearsal choice, and rollback
rules. Every row in a non-empty checklist still requires an owner ruling. Setup and re-enable
criteria include only applicable controls. After owner steps and pre-load export requirements,
an otherwise empty setup or re-enable story gets this criterion: "No automation fires for this
load; confirm that again against the org before loading."
Each `--bundle` supplies target and automation names. Org context and projected tool targets
identify written lookup fields between targets so the load story names parent-first order and
the identifier regeneration step. Repeated lock lines appear once with a count. The story
names `parentSortField` when grouping uses one, or explains why grouping could not be applied.
Card 07 passes the recorded rehearsal choice. With `skip`, stories use the ratified parameters,
carry measured-class uncertainty as a stated risk, and cite the final report's rehearsal risks
instead of reconciliation evidence. No rehearsal result file is read.
An accepted rehearsal removes the stale "sandbox not yet established" risk. Upsert rollback
deletes only rows marked `sf__Created` true and restores updated rows from the pre-load export.
Targets with an `upsert` or `update` operation include the export criterion in story 01 before any load.
Each finalized `ownerSteps` entry becomes an acceptance criterion in its named core story, with
the owner's `ruledOn` time. Both finalization and story generation reject an invalid story value
with exit 1 and a single `error: ownerSteps ...` diagnostic.
Bypass setup names `bypass_switch` and uses `bypass_scope`: `user` enables the ratified load-user
bypass; `org-wide` says "Turn off `<switch>` for `<automation>`; this affects every user until it
is turned back on". Missing scope uses the org-wide instruction. Safety-package and final reports
group these rows under "Bypass for the load user" or "Bypass for every user while the switch is off".
Story 01 carries the finalized pre-load checks. Story 02 states operational instructions in plain
language, renders parameter changes as short lines, and uses `knownRisksAcceptedOn` for risk
acceptance. Each known risk is one criterion; the parameter-change list omits its aggregate
`knownRisks` change.
Report and story renderers preserve supplied automation names and risk text. The session contract
keeps internal notes out of those inputs; lint checks rendered fixtures for internal markers.
Story 04 restores applied controls or verifies the ratified state when nothing was
switched off.

## `lint.py`

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/lint.py
```

Checks the 17 data files, closed vocabularies, ruling coverage, blocked recovery, threshold consumers,
incident controls, synthetic bundle columns, uncatalogued rule overlap, rules snapshot exclusion,
customer-facing punctuation, card script existence and accepted arguments, card data-file citations,
exact transition ownership between the cards and `SKILL.md`, matching Claude and Codex plugin
manifests, and the license identifier in `LICENSE`.

## Tests

```text
cd scripts
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .
```
