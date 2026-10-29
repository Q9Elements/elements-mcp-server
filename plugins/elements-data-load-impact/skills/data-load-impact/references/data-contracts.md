# Data contracts

Every persisted path is relative to the **engagement directory**, the directory containing
`execution-state.json`. Scripts live in the plugin's `scripts/` directory and read the decision tables
under `skills/data-load-impact/data/`. The Salesforce command-line interface (sf CLI) runs an
chosen rehearsal batch on the customer's signed-in sandbox.

All comma-separated value (CSV) files use 8-bit Unicode Transformation Format (UTF-8), Request for
Comments (RFC) 4180 quoting, and a header row. JavaScript Object Notation (JSON) files use UTF-8.
Dates and times use International Organization for Standardization (ISO) 8601 in Coordinated
Universal Time (UTC). Empty means unknown, never zero.

## Engagement directory

```text
execution-state.json
work/intake/                 org context, owner answers, profiler payloads, strict calls, residue
work/bundle-baseline/        one <object>-<operation>/ bare-target bundle per load target
work/bundle/                 one <object>-<operation>/ complete analysis bundle per load target
work/analysis/managed-packages.json
                             managed namespaces and trigger names grouped by target object
work/narration/              one order-of-execution narrative per touched object
work/bypass/audit-set.json   bundle and narration automation names with evidence origins
work/bypass/verdicts.csv
work/source/                 targets.json, saved replies, manifest.json, and metadata source under
                             <type>/<name>.xml with Apex .cls or .trigger bodies when returned
work/package/                checklist.csv and parameters.json
work/rehearsal/              duplicate-rules.json, observed.json, reconciliation.csv,
                             summary.json, unpredicted.json (running union after TR-24), batch.csv for local-source loads, local CLI job
                             output, same-job result CSV files, and load-user debug logs
report/                      impact report, safety package, final report
stories/                     five core stories; one duplicate follow-up when active rules exist
```

## Tool calls and bundles

`work/intake/tool-targets.json` is `{ "calls": [...] }`. Each call has `object` and `arguments`;
`arguments` contains `refModelId`, `depthBound`, `teamId` when the Space is known, and a `targets`
array of length one. Its target accepts
only `object`, `writtenFields`, `operation`, positive `estimatedVolume`, and optional projected
`aggregates`. For a local CSV file, card 02 counts data rows before the baseline call and verifies
that the later profiler payload reports the same volume with `volumeSource: "row_count"`. For a
query-defined load without a file or a header-only chat attachment, the owner supplies an
approximate positive volume. A header-only attachment uses `load_input_prep.py csv --volume N`
and the Salesforce Object Query Language (SOQL) profiling route, with `generatedBy.adapter: "soql"` and
`volumeSource: "user_supplied"`. Its parent skew comes only from grouped lookup counts with a `c`
column passed through `--soql-result COLUMN=RESULT.csv`.
`manifest.loader` is the owner's chosen loader from `data/tool-matrix.csv`; card 05 passes it to
`checklist.py --loader`. Card 02 asks the owner to confirm the loader and proposed manifest on
every entry.
`work/intake/residue.json` keeps every profiler field excluded by the strict tool schema.
The projected call target is the source for `writtenFields`; bundle `targets.json` follows the server
summary shape and does not carry that field. The manifest records the conditional portal-role answer under `roleBasedPortalUser`. Its
`targetFacts` array contains only confirmed
`User:<operation>=role_based_portal_user` values for card 05; field-based Group Table facts come from
`work/intake/tool-targets.json`.

A complete bundle contains:

```text
fire-chain-digest.csv  alternatives.csv  automations.csv  lock-rows.csv
fan-in.csv              receipts.csv      targets.json     coverage.json
rule-catalog.json       rules-data.json   response.json
```

The saved `envelope.json` omits `bundleUrl` and retains the job identifier, computation date and time,
bundle digest, and summary. `rules-data.json` is engagement evidence from a baseline bundle; the
plugin ships no snapshot.

## Bypass verdicts

Each narration file includes `object`, `narrative`, and `automations`. The automation list contains
every explicitly named automation as `{name, type}`, with `apiName` only when supplied by the tool.
It includes Process Builder Workflow and Workflow Rule names even when absent from the bundle. An empty
list means no named automations; a missing list requires regeneration with the narrator.
`bypass_set.py` builds `work/bypass/audit-set.json` from all bundles, narrations, package lookups,
duplicate rules, and rehearsal names. Each audit key is `(target, type, apiName)`, with one entry per
distinct automation. Digest-only entries use the firing node's `sfType` from `response.json`, then
direct automation types by node identifier or name, then email-sender types; unresolved types use
`Automation` in the provisional set. Narration matches on the
same object and metadata type by exact application
programming interface (API) name; when `apiName` is omitted, its name may match the exact name or
label. Explicit names retain their namespaces. Unmatched narration rows carry
`origin: narration-only`. The orchestrator resolves their node identifiers and ownership for source
and activation checks. After source fetch, `bypass_set.py --audit-set ... --source-manifest ... --out ...`
uses the checklist's shared node-identifier type resolver in `dli_common.py` to normalize every
automation. One shared alias map emits synced Salesforce type names. Manifest names supply resolved
application programming interface (API) names. Aliases sharing a node and target merge before keys
freeze, preferring the bundle identity and retaining `narrationNames`, `narrationEvidence`, and
supplied activation evidence. The checklist and reports retain each narrated object, including related objects.

Card 04 writes `work/source/targets.json` as an array of firing automations with `nodeId`,
`apiName`, and `type`. The orchestrator calls `get_metadata_source` for those nodes, saves each reply
in the `{"savedAt": "<UTC ISO 8601 time>", "reply": <complete tool reply>}` format, and runs
`scripts/source_files.py fetch`. The fetch command joins replies by `nodeId`, writes source files,
and records each file's `status`, `reason`, `xmlScope`, and `syncDate` in `manifest.json`.
`syncDate` comes from the selected Reference Model's `sync.timestamp`. Validation Rule and Workflow
Rule formulas come from fetched Extensible Markup Language (XML) files. The manifest outcomes
`not_found`, `no_stored_definition`, and `file_missing` mean source is unavailable; those verdicts
are `unknown`. `managed_code_hidden` keeps its XML without a body and yields `unknown` with
coverage failure "package code is hidden"; its package row stays `leave-on`. `scan` returns plausible helper
class names from Apex bodies and Apex Flow actions, excluding downloaded classes, declared
variables, local classes, comments, strings, platform types, known object names, and package
namespaces evidenced by schema references. Field names remain eligible as class candidates.
Card 04 resolves candidates with `search_metadata` restricted to Apex Class and exact `apiName`
matches, fetches one helper level, then scans once more.
The auditor reads source files directly from manifest paths and assesses each source component once
by `nodeId`. Project identical `verdict`, `scope`, `switch`, and `evidence` onto that node's target
rows; retain target firing evidence separately. Validation rejects conflicting shared-source hook facts.
Non-firing requires source proof of inactivity or a condition that the incoming fire-chain path cannot
satisfy. A different start or trigger object alone cannot disprove a cascade. Validation rejects
bundle non-firing evidence consisting only of a record-triggered start object and load targets, or
a trigger declaration with an optional load-target list; failure exits 1 through the audit input error.
A `present` verdict quotes a reachable check that skips the automation's work for this load and names
its exact `switch` and `scope`. Partial error exemptions and commented-out calls do not qualify.
Scope is `user` for Hierarchy custom settings and
Custom Permissions, and `org-wide` for List custom settings and Custom Metadata. The auditor uses
`data/bypass-mechanisms.csv` and the switch rows' `nodeDetails.customSettingsType`.
Each evidence field returns one quoted source line; whole source files stay local to the auditor.

`work/bypass/verdicts.csv` columns are `target`, `type`, `apiName`, `verdict`, `scope`, `switch`, `evidence`, `nonFiring`,
`nonFiringEvidence`, `active`, and `activeEvidence`. `verdict` is exactly
`present`, `absent`, or `unknown`. Exactly one evidenced verdict identifies each audit entry by the
same `(target, type, apiName)` key. Validation rejects missing, repeated, extra, or ambiguous verdicts.
Legacy verdicts with omitted identity fields must resolve to one audit entry. Checklist construction
preserves distinct keyed verdicts; ambiguous legacy lookups carry `unknown` with ambiguity evidence.
A `present` verdict with missing or unrecognized scope uses `org-wide` wording. Scope and switch
may be empty for `absent` and `unknown` verdicts.
Narration-only rows require activation evidence from `get_metadata_component`: `active` is `true`,
`false`, or `unknown`, with `activeEvidence` quoting status or naming the lookup failure. Inactive
rows require `nonFiring: true` and status evidence; they are recorded as not firing and excluded
from load risks. Unverified activation requires an unknown verdict and empty `nonFiring`; it carries
a named coverage risk. Owner reports and stories render a separate plain coverage statement,
including "activation could not be verified" for unresolved activation. Technical evidence stays in
work files. Bundle rows may leave activation fields empty. Card 04 validates verdict
coverage and activation evidence with `bypass_set.py` before completing the audit.

## Safety package

Draft files are `work/package/checklist.draft.csv` and `parameters.draft.json`. Owner-completed copies
are `checklist.owner.csv` and `parameters.owner.json`. Finalization writes
`work/package/checklist.csv` with these columns:

```text
target,automation_kind,automation_type,automation_api_name,automation_name,bypass_verdict,bypass_scope,bypass_switch,
proposed_disposition,blast_radius,side_effect_flags,replacement_data_quality_check,evidence,owner_ruling
```

A load with no automation rows uses a header-only checklist in draft, owner, and finalized files.
Finalization accepts matching zero-row checklists. Story generation accepts them when parameters
carry `packageStatus: "finalized"`, a non-empty `ratifiedBy`, and `goNoGo: "go"`; every row in a
non-empty checklist requires an owner ruling. The five core stories render from parameters,
owner steps, incident controls, the rehearsal choice, and rollback rules. Checklist-driven criteria
are absent. After owner steps and pre-load export requirements, an otherwise empty setup or
re-enable story gets this criterion: "No automation fires for this load; confirm that again
against the org before loading."

`work/analysis/managed-packages.json` has the shape
`{ "<Object>": [{"namespace": "...", "triggers": ["..."]}] }`.
Verdict `scope` and `switch` persist as `bypass_scope` and `bypass_switch`. For a `bypass` row,
`blast_radius` is "Load user only" for `user` or "Every user while the switch is off" for
`org-wide`. Reports group these rows under "Bypass for the load user" and "Bypass for every user
while the switch is off", respectively. Missing scope uses the latter group. Row disposition stays
`bypass`. For the safety-package contract, see `scripts/CLI.md`.
Card 04 and card 05 use the same manifest type resolver, with source types taking precedence for
every resolved node. Bundle firing nodes, direct automation and email-sender inventories supply
remaining known types; a node without a known type uses `Automation`. Checklist generation rejects
supplied typed verdicts that do not join a checklist identity.
Managed validation rules retain `namespace` and `isManaged` ownership in audit inputs; qualified
source names also establish the rule namespace. Their checklist rows carry `managed_component`
in `side_effect_flags`, propose `leave-on`, and reject a `deactivate` owner ruling.

Finalized `parameters.json` field names include `packageStatus`, `api`, `batchSize`, `concurrencyMode`,
`serialModeEvidence`, `groupByParentId`, `parentSortField`, `incidentControls`, `parameterChanges`,
`ratifiedBy`, `ratifiedOn`, `goNoGo`, `knownRisks`, `knownRisksAcceptedOn`, and
`uncontrolledIncidentClasses`, and `ownerSteps`. The `parameterChanges` entries contain `changedBy` and `changedOn`.
`parameters.owner.json.ownerSteps` is an optional array of `{story, step, ruledOn}`. `story` is
exactly `pre-load`, `load`, `export-and-reconcile`, `re-enable`, or `rollback`; `step` is the
owner's instruction and `ruledOn` is the answer's time. Both are nonempty strings. Card 05 records
each owner answer that adds or changes a step. Finalization validates and copies these entries to
`parameters.json`, preserving them on package rebuilds. `stories.py` renders each as an acceptance
criterion in its named story with `ruledOn`. Targets with an `upsert` or `update` operation add an
export criterion to story 01. Invalid entries exit 1 with an `error: ownerSteps ...` diagnostic.
Per-file grouping uses `load` steps beginning `Sort <file or target> by <field>`; story 02 renders
these steps once each in place of the scalar `parentSortField` grouping criterion.

## Rehearsal

`rehearsal.choice` is `rehearse` or `skip`. Card 06 records the owner's name and time in
`choiceBy` and `choiceOn`, and the exact customer-language reasons shown to the owner in
`reasonsToRehearse`, including automation outside the expected fire chain. Card 06 asks when the
choice is null and reuses a recorded choice. A skip goes directly to card 07. The final report repeats those reasons as
named stated risks. Story generation receives `--rehearsal-choice skip` and reads no rehearsal
result; the ratified checklist and parameters remain its execution authority.

For a chosen rehearsal, `rehearsal.capturePath` is `sf-cli` or `manual`; it stays null on a skip.
Card 06 first matches the finalized parameters
and a confirmed local CSV source to the sf CLI command. For a local-source load on either capture path,
`load_input_prep.py slice` writes `work/rehearsal/batch.csv` with the header and up to
`rehearsal_batch_rows` from `data/thresholds.csv`. Its aggregate JSON provides the actual
`rows`, `candidateWrittenFields`, and output `lineEnding` (`LF` or `CRLF`). Card 06 passes that
`rows` value to `rehearsal_fired.py`; the sf path passes `lineEnding` to the sf bulk command.
The manual path gives that same sliced file to the customer to load and counts rows from it.
When `groupByParentId` is true and `parentSortField` is in the source header, the single slice
sorts the selected rows by that field on either path. Without that field, both paths use file
order and carry "parent grouping was not rehearsed" as a risk. A slice or header failure uses
the manual path with a customer-prepared batch.
For a query-defined load, the manual rehearsal loads at most `rehearsal_batch_rows` rows of
the query result. Success plus failed rows is the loaded count and the result states
"row completeness not independently checked" as a risk. A query-defined
load without a source file uses the manual path. Only then does card 06 look for aliases.
`rehearsal.sandboxAlias` records the owner's
one-time alias choice or the literal `none`; null means no alias question was asked.
`rehearsal.sandboxOrgId` records the identifier returned by the
sandbox verification query. Before each sf load, card 06 names the checklist actions for that
alias and the authenticated CLI username as the user every load-user bypass must cover; it waits
for the customer's `applied` reply. `rehearsal.cliRuns` contains one entry per CLI attempt with
`target` (an object with `object` and `operation`), `loadUserUsername`, `loadUserId`,
`appliedBy`, `appliedOn`, `debugLevelId`, `traceFlagId`,
`jobId`, `loadStartedOn`, `loadEndedOn`, `successFile`, `errorFile`, `logFiles`, and
`cleanupStatus`. `logFiles` is a list of local paths. `cleanupStatus` has `traceFlag` and
`debugLevel` values of `not-created`, `pending`, `deleted`, or `failed`. Card 06 writes each field
and records each created identifier immediately so
cleanup deletes only that run's records. A failed cleanup retains the leftover identifier, reports
it for optional customer cleanup, and allows the next load. A later TR-23 rehearsal rechecks the
finalized parameter mapping without another alias question. The CLI route requires Bulk API 2.0,
server-managed batch
size, parallel concurrency, either value of `groupByParentId`, and one confirmed target with a local batch file.
Other ratified sets use the manual path.

The finalized checklist supplies the reconciliation expectations: `deactivate` and `bypass`
are expected silent; `leave-on` and Apex Class `review: ...` may fire. `observed.json` contains
`complete`, `logsProcessed`, `truncatedLogCount`, `incompleteLogCount`, `rowsLoaded`,
`successRowsRead`, `errorRowsRead`,
`errorCounts` for `DUPLICATES_DETECTED` and `UNABLE_TO_LOCK_ROW`, `queuedEmails`, and
`governorLimits` with the highest usage ratio's used and ceiling per limit and namespace, and `automations[]` with
`name`, `type`, and `fireCount`. `reconciliation.csv` columns are `name`, `type`,
`expectation`, `observed_count`, and `result`.
Success and failed rows come from one load job and must sum to `rowsLoaded`. The sf CLI path fetches
the same-job files; on the manual path the customer supplies them. The parser rejects differing job
identifiers when their filenames carry them.
At least one nonempty
log is required. Execution starts and finishes balance when present; zero of each is valid. Managed
code is observed by namespace as `Managed Package`; duplicate-rule invocations appear by rule name
as `Duplicate Rule`; Apex method entries appear by class name as `Apex Class`.

`summary.json` contains `evidenceComplete`, `controlFailures`, `unpredicted`,
`informationalNotObserved`, `measuredIncidentClasses`, `duplicatesDetected`, `lockErrors`, `lockErrorsAccepted`, `blockers`,
and `rehearsalPassed`. Lock errors block above the owner-accepted count, or above zero when no
acceptance exists. A queued email or governor limit at or above
`governor_limit_rehearsal_percent` blocks a measured class and routes to card 05 under TR-22;
otherwise the class is `measured clean`. A class or namespace without a debug-log measure is
`not measurable for <name>` and is shown once at acceptance. Duplicate counts are informational. `rehearsal.lockErrorsAccepted` records the
count the owner accepted after serial mode ran or when the recorded loader cannot run it.
TR-20 requires this round's summary `unpredicted` to be empty and no measured-class blocker.
A measured-class blocker takes TR-22 before
the automatic lock ladder's TR-23.
`rehearsal.ladderChanges` lists each automatic rung with its rung, lock count,
changed parameter names, and date and time. The same change appears in `decisions_log`; the
owner's TR-20 acceptance covers every listed change. The next test batch uses the changed
finalized parameters while TR-23 loops on `package-ratified`.
An accepted lock count remains valid only while `groupByParentId`, `concurrencyMode`, `api`, `batchSize`, and
`serialModeEvidence` match the package under which the owner accepted it. Card 05 clears the count
when the owner changes any of these values.
`analysis.duplicateRules` groups active rule names by target object. Card 03 writes that mapping
to `work/rehearsal/duplicate-rules.json`; both impact report commands and story generation read it.
`work/rehearsal/unpredicted.json` and `rehearsal.unpredicted` contain the running union
of names and types selected by TR-24, keyed by name and type across rehearsal rounds.
Card 05 keeps distinct checklist rows with the same name and different types.

## State invariants

`current_state` and `current_step` change in one write. Every human decision appears in
`decisions_log` with the person's name, decision, and date and time. The matching block also records
its named `By` and `On` fields. `blocked.reason` is null, `MISSING_PRIMITIVE`, or `SYNC_INCOMPLETE`.
Persisted state is limited to metadata names, aggregate counts, local artifact paths, named decisions,
and aggregate-safe evidence. Signed URLs, customer rows, query results, debug-log lines, production
execution records, and MetaField rulings stay outside state.
