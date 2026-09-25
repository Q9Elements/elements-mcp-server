# Data contracts

Every file the cards, agents, and scripts exchange, with its exact shape. Paths are relative to the
**engagement directory** (the directory holding `execution-state.json`). Scripts live in the plugin's
`scripts/` directory (two levels up from this skill) and read the decision tables in `data/`; a
script never restates a value that a `data/*.csv` file defines.

All comma-separated value (CSV) files use 8-bit Unicode Transformation Format (UTF-8), Request for
Comments (RFC) 4180 quoting, and a header row. Timestamps use `YYYY-MM-DDThh:mm:ssZ`, are Coordinated
Universal Time (UTC), and end in `Z`; dates without a time use `YYYY-MM-DD`. Booleans are `true` / `false`.
Empty means unknown, never zero. Apex identity everywhere is the **qualified name**:
`Namespace.Name` when the class carries a namespace prefix, else `Name`.

## Engagement directory layout

```
execution-state.json
work/bundle/     the candidate bundle plus the two card 02 orchestration files
work/triage/     capacity summary, package ledger, full candidate inventory, deferred inventory, and targeted string holders
work/reasoning/  paired payload and return JavaScript Object Notation (JSON) files per card 03 unit
work/grouping.csv          card 03 step 5: qualifiedName, groupLabel, groupOrder, groupNote (input to the merge)
work/reasoned-candidates.csv
work/review/     dispositions.csv from card 04
work/plan/       card 05 resolved metadata names, tranche manifests, validation receipt, and plan outputs
stories/         one Markdown story per removal unit, annotation ruling, or precursor rewrite
report/          the customer-facing reports
```

`execution-state.json` holds `slots.model_id`, the reference-model identifier, and
`slots.elements_base_url`, the `baseUrl` returned by card 04's single `get_dependencies` call for
the first displayed row. The template initializes `slots.elements_base_url` to `null`.

## The candidate bundle (`work/bundle/`)

`get_unused_apex_candidates` returns a signed uniform resource locator (URL)
(120 s) to an archive holding exactly these files, and inline `summary`, `ledger`, and `blindSpots`:
`telemetry-ledger.json`, `catalog.csv`, `catalog-summary.json`, `schedule-liveness.csv`, `closure.json` (counts
only), `candidates.csv`, `components.json`, `blind-spots.json`, and `edges.csv`; every dependency edge whose
component or ref-component is a candidate, in the eight-column `MetadataComponentDependency` shape below plus
`parentUsed`, `parentNodeId`, `childNodeId`, so the planner can order units and name outside callers, and the
review artifact can deep-link both ends, without another read. No class bodies, no user ids. Shapes are the
**Outputs** below.

Card 02 also writes two review-page inputs in this directory:

- `envelope.json`, written by card 02 from the tool's `complete` response with `bundleUrl` removed.
- `catalog-summary.with-capacity.json`, written by card 02 as a copy of `catalog-summary.json`,
  which carries the tool's capacity fields, plus `readAt`.

The request includes `stringSearch`, which defaults to false.
The tool's response envelope: `status` ∈ `computing` (re-call with identical arguments in 30 s) |
`disqualified` (`reason` ∈ `NO_APEX_TELEMETRY`, `SYNC_INCOMPLETE`, `INGEST_PENDING`,
`TELEMETRY_NOT_COLLECTED`; `ledger` inline) | `complete` (`computedAt`, `syncTimestamp`, `summary`, `bundleUrl`, `bundleSha256`, `ledger`,
`blindSpots`) | `error` (stage named; never a partial result). A response may carry further fields,
including `telemetryHighWater` or `owner`; the playbook reads the named fields and keeps the rest in
`envelope.json`.

## Plan invariants (checked by the generator, falsified by the reviewer)

Every `remove` row appears exactly once across tranche units, quarantine rows, and blocked units. Every
`annotate` row has one annotation story and appears in no tranche. No `keep` or `decide-later` row
appears anywhere; quarantine rows cite Q-04 or Q-06 only and carry their structured
evidence; units are strongly connected components with their test classes attached; consumers precede
providers as the tranche's reading order; each tranche deploys as one deployment. A unit whose consumer is quarantined or blocked is itself blocked (Salesforce refuses to delete a referenced class); a unit with a
scheduled, record-triggered, or platform-event-triggered Flow referrer is blocked. When a bundle has a
Flow edge but lacks `MetadataComponentTriggerType`, the planner records `flow-trigger-block` as
unevaluated and exits with status 2 unless the analyst explicitly allows the unevaluated state.
A Process Builder Workflow or Workflow Rule referrer places only the affected unit in `blockedUnits`
and `unevaluatedRules`; the planner writes and validates the remaining plan. Its `blockedReason`
names the referrer's own type and says that the class stays until the process or rule is deactivated
or confirmed unused. `--allow-unevaluated-flow-rule` applies only to Flow referrers. Process Builder
Workflow and Workflow Rule referrers never enter a destructive manifest.
Q-04 uses only `work/triage/string-holders.csv`: a non-test holder outside the confirmed removal set blocks
the named class. Q-06 covers an incoming edge from a surviving class or trigger, including an unresolved Apex
endpoint. `capacity-totals.json` keeps deletion, annotation, and realized figures distinct, with
`confirmedRealized` null. A surviving test class that directly references a placed removal unit is
listed in that unit's `precursorRewrites`; it is edited in the same deployment and does not trigger
Q-06. A shared surviving test has one entry in every unit whose member it references. The
`survivor-references` invariant names every catalog class or trigger that directly references a
removed member without either Q-06 handling for a non-test caller or a `test-edit` precursor rewrite
for a test caller. Each edited surviving test has exactly one precursor story in its tranche, and the
test appears in that tranche's `package.xml`. Every story follows its shape in
`references/story-template.md`.

## Resolution data tables

The server resolves event rows to classes reading the same decision tables this package ships.
`data/quiddity-codes.csv` columns are `code`, `meaning`, `context`, `resolution_method`, `root_kind`, and
`protects`; the full 28-code legend, never a hardcoded code list. The blank default
row and any unrecognized code use the `UD` behavior: unknown context, no class resolution, and no protected root.
`data/event-resolution-precedence.csv` orders the join methods; the first method that resolves a row wins.
Execution context is `production`, `test`, or `unknown`. Test context never protects a class; a class
resolved in an unknown context still protects in the safe direction, but `UD` and an unrecognized
quiddity resolve no class.

## Outputs

### `work/bundle/telemetry-ledger.json`

(spec §4): `{ capturedAt, syncTimestamp, interval: "daily", requestedDays: 90, effectiveDays,
windowStart: max(today − N, coverageStart), windowEnd, coverageStart, eventTypes: { <T>: { firstDay, lastDay,
daysProcessed, spanDays, missingDays } }, typesAbsent: [...], scheduledJobNames: { names, current, pruneAfterDays: 100 },
automationContextMissing, verdict: "OK|NO_APEX_TELEMETRY|SYNC_INCOMPLETE", notes }`. Per type, `missingDays`
equals `spanDays − daysProcessed`, derived by the tool when it writes the ledger; the ledger lists no
missing dates. The tool's `NO_APEX_TELEMETRY` verdict means no `telemetrycoverage` doc has
`daysProcessed > 0`. Card 02 also blocks with this reason when a complete ledger lacks required
telemetry (see card 02 step 2). When the
held telemetry spans fewer calendar days than T-12 (`effectiveDays` below T-12), the engagement blocks
before a candidate list is produced.

The ledger also carries:

```json
{
  "coverage": {
    "status": "ok",
    "source": "ApexCodeCoverageAggregate",
    "capturedAt": "<timestamp>",
    "rows": 0,
    "coveredLines": 0,
    "totalLines": 0,
    "orgWideFraction": 0.0,
    "newestStamp": "<timestamp>",
    "oldestStamp": "<timestamp>",
    "rowsOnNewestDay": 0,
    "rowsWithoutAggregate": 0,
    "error": null
  }
}
```

`coverage.status` is `ok` or `unavailable`. Its `error` is
`{ "stage": "token" | "query" | "parse", "message": "..." }` or null. An unavailable block has
empty coverage columns. The server includes this ledger block for other consumers; the playbook does
not read it. `orgWideFraction` equals
`coveredLines / totalLines` over every aggregate row. `rowsWithoutAggregate` counts each counted class
with no matching aggregate row.

### `work/bundle/catalog.csv` + `work/bundle/catalog-summary.json`

`catalog.csv` holds every synced Apex Class and Apex Trigger node whose Elements status is neither deleted nor
proposed. A class removed from the org remains in Elements as a deleted node; it is outside the catalog, the counted
total, the candidate set, the edge set and telemetry resolution.

`catalog.csv` columns (spec §4): `nodeId`, `sfId`, `qualifiedName`, `name`, `namespacePrefix`, `kind`
(`class|trigger`), `triggerObject`, `isManagedPackage`, `isTestClass`, `apiVersion`, `lengthWithoutComments`,
`countedRule`, `countedCharacters`, `coverageFraction`, `linesCovered`, `linesUncovered`, `coverageStamp`,
`lastModifiedDate`, `lastExecutedDate`,
`lastExecutedDirect`, `lastExecutedVia`, `executionCount`, `executionRate`, `scheduledJobNames`, `scheduleLive`.
`isManagedPackage` = `nodeDetails.isManaged`; `isTestClass` = `nodeDetails.isTest` (true only for a
**class-level** `@IsTest` annotation); `EXEMPT_DYNAMIC_APEX` is not evaluated (named in
`catalog-summary.json.rulesNotEvaluated`; no bodies in production).

`coverageFraction` is the synchronized `nodeDetails.testCoverage` value. `linesCovered`,
`linesUncovered`, and `coverageStamp` describe the matching aggregate row, and are empty when no row
matches the class; `blind-spots.json.coverageMissing` names each affected counted class. The server
includes these columns for other consumers; the playbook does not read them.

- `countedRule` is a `rule` id from `data/counted-set-rules.csv`, applied in that file's order; the
  first rule whose condition holds wins.
- `countedCharacters` is `lengthWithoutComments` when the rule says counted, `0` when exempt, empty
  when the rule says counted but `lengthWithoutComments` is empty (an extraction failure; never zero).

`catalog-summary.json`:

```json
{ "rows": 0, "byRule": { "<rule>": { "count": 0, "characters": 0 } },
  "countedCharactersTotal": 0, "nullLengthRows": 0, "anomalies": ["<qualifiedName> …"],
  "allocation": 0, "displayedPercent": 0.0, "charactersUsed": null,
  "bandLow": 0, "bandHigh": 0, "reconciled": true, "residual": 0, "calibration": 1.0,
  "rulesNotEvaluated": ["EXEMPT_DYNAMIC_APEX"] }
```

`bandLow`/`bandHigh` come from `data/thresholds.csv` (`T-1`): `charactersUsed ± 600` when the exact
figure was captured, else the percentage band; `reconciled` is null when neither was supplied; `calibration` =
counted total / (allocation × displayedPercent). `charactersUsed` is always present and is null when the
exact integer was not supplied. The tool-call input omits `charactersUsed` when it is unknown.

The summary also carries a compact `candidateCapacity` object:

```json
{
  "knownCharacters": 0,
  "unknownLengthCandidates": 0,
  "deciles": [{ "rankFrom": 1, "rankTo": 10, "rows": 10,
    "characters": 0, "cumulativeCharacters": 0 }],
  "largestCandidates": [{ "qualifiedName": "Example", "componentLabel": "Example",
    "countedCharacters": 0 }],
  "largestComponents": [{ "label": "Example", "size": 1, "countedCharacters": 0,
    "unknownLengthMembers": 0 }]
}
```

The two largest lists contain at most 20 entries. `deciles` partitions candidates by rank. The
candidate count comes from envelope `summary.candidates.total` (the same count as
`closure.json.candidates.total`), not from `candidateCapacity`.

Every CSV text cell whose first character is `=`, `+`, `-`, or `@` arrives with one leading
apostrophe. Readers strip that one apostrophe for display and keep the stored bundle unchanged.

### Execution evidence on the node (`lastExecuted`)

Observed and inferred use collapse onto the node's top-level
`lastExecuted {date, direct, via, count, rate}` (top-level, not `nodeDetails`, because
the sync wipes `nodeDetails`); the closure's reached set is the same object with `direct: false, via`.
`direct` is the kind of the *latest* evidence (not sticky); `count > 0` means the node ran under its own
name. Unmatched and non-root event counts are logged at ingest and are not persisted because nothing
in the playbook consumes them.

### `work/bundle/schedule-liveness.csv`

`qualifiedName`, `rootKind`, `live`, `evidence`, `source`: one row per class in
`scheduledjobnames.apexClassIds` of a name with current `lastSeen` (≤ 100 days) and no in-window `lastExecuted`;
`rootKind = schedulable`, `live = true`, `evidence` = job name + `lastSeen`, `source = scheduledjobnames`. A live
schedule counts as use, so these classes are excluded from `candidates.csv`: they receive no ruling and never enter
the plan. `capacity_triage.py` and `removal_plan.py` read this file only to give a listed class the `scheduled`
entry-point channel.

### `work/bundle/closure.json`, `work/bundle/candidates.csv`, `work/bundle/components.json`, `work/bundle/blind-spots.json`

`closure.json` contains counts only: `{ "used": { "direct": n, "inferred": n }, "scheduledUnobserved": n,
"candidates": { "total": n, "neverSeen": n, "stale": n, "T": n, "U": n }, "edges": n }`; no member lists.

`candidates.csv`: the complete catalog column list above plus `set` (`T|U`), `incomingFromP`, `incomingFromCandidates`,
`incomingFromTest`, `incomingFromOther`, `incomingOtherTypes` (`;`-joined parent `sf.type`s), `incomingTotal`,
`incomingReading` (a `reading` id from `data/incoming-edge-reading.csv`), `componentLabel`,
`outgoingWithinCandidates`, `description`, `automationSummary`, `intentTags` (`;`-joined),
`automationContextAvailable`, `stringReferenceHits`, `stringReferenceNodes` (`;`-joined),
`stringReferenceOutsideCandidates`, `capacityRank`, `cumulativeCountedCharacters`, and
`cumulativeCandidateCharacterFraction`. Rows with known length are ordered by `countedCharacters` descending,
then qualified name; unknown lengths follow by qualified name. Rank and cumulative fields are empty for unknown
lengths. The three bulk string-reference columns are empty because the request defaults `stringSearch` to false;
card 03 writes targeted findings to `work/triage/string-holders.csv`. `set = T` when `incomingFromTest > 0` and
`incomingFromP + incomingFromOther = 0`, else `U`.
There is no declared-root column; `components.json anyDeclaredRoot` is always null.
`incomingFromP > 0` is an ingest anomaly (`alarming`), never a class judgement. `incomingFromOther` is for
the **planner** (the referrer must be in the unit or the unit is blocked), not a reasoner reading.

`components.json`: `[{ "label": "<smallest qualifiedName>", "size": n, "members": [...],
"externalInboundEdges": n, "anyDeclaredRoot": null, "countedCharacters": n,
"unknownLengthMembers": n, "sccs": [[members…]] }]`, sorted by `countedCharacters`
descending. `countedCharacters` sums known lengths and `unknownLengthMembers` counts members with
unknown lengths. Readers render a fully unknown component as `unknown`, even when its known sum is
zero. `sccs` orders units consumer before provider as reading order. Components are the weakly connected components of the subgraph
induced on the candidate set.

`blind-spots.json`: `{ "managedOpaque": n, "rulesNotEvaluated": ["EXEMPT_DYNAMIC_APEX"], "nonTraversedEdgeSources":
{ "<sf.type>": n }, "nameHeldInData": "declared", "packagePlatformDispatch": "declared",
"incomingFromPAnomalies": n, "coverageMissing": ["<qualifiedName>"] }`. Every key is reportable except
a key whose name contains `coverage`, which reports never print. A `stringEvidence` key is reportable
only when no string-holders file is supplied; the targeted string search then stands in its place.
A fixed list: class names held in custom-settings/metadata *data* and
customer classes instantiated by package or platform code by configured name are invisible to graph and index and are
stated, not detected.

The response envelope replaces the full coverage-missing array with
`blindSpots.coverageMissingCount` and a bounded `blindSpots.coverageMissingPreview`. The complete list remains
only in `blind-spots.json`. The telemetry ledger adds `unresolvedHolders`, an array of unresolved configured-name
holders used by Q-06. The customer-facing requirement remains 30 days of telemetry; the machine gate is T-12's
29 held days because the newest published day can arrive after the ingest.

### `work/bundle/edges.csv`

`MetadataComponentId`, `MetadataComponentName`, `MetadataComponentType`, `MetadataComponentNamespace`,
`RefMetadataComponentId`, `RefMetadataComponentName`, `RefMetadataComponentType`,
`RefMetadataComponentNamespace` (one row = *component references ref-component*), plus `parentUsed`,
`parentNodeId`, `childNodeId`, and `MetadataComponentTriggerType`. The last column holds the Flow
parent's raw trigger type and is empty for a Flow with none and for every non-Flow parent. The planner
maps `Scheduled` to `scheduled`, every value beginning with `Record` to `recordtriggered`, and
`PlatformEvent` to `platformevent`; all three mapped values block the removal unit.
For a non-Apex parent, `MetadataComponentName` and `MetadataComponentNamespace` can be display values;
`parentNodeId` is the identity used to resolve its manifest application programming interface (API)
name.

### `work/triage/summary.json`

One JSON object summarizes the current selection. Integer fields are `requiredCharacters`,
`confirmedCharacters`, `selectedCharacters`, `shortfall`, `unknownLengthCandidates`,
`eligibleDeferred`, and `selectedPackages`. `counts` maps `selected`, `deferred`, `inUse`,
`keptUseUnknown`, `unknown-length`, and `ruled` to integers. `outcome` is `target_covered`,
`candidates_exhausted` or `already_at_target`. `stringSearch` is `not_run`,
`available`, or `unavailable`. `target` contains string `wording`, string `kind`, numeric `value`,
integer `requiredCharacters`, and boolean `alreadyAtTarget`. `blindSpots` contains
`stringSearchUnavailable: true` only when search is unavailable.

```json
{"target": {"wording": "free 100000 characters", "kind": "characters", "value": 100000,
 "requiredCharacters": 100000, "alreadyAtTarget": false},
 "requiredCharacters": 100000, "confirmedCharacters": 25000, "selectedCharacters": 80000,
 "shortfall": 0, "counts": {"selected": 4, "deferred": 10, "inUse": 1,
 "keptUseUnknown": 1, "unknown-length": 0, "ruled": 2},
 "unknownLengthCandidates": 0, "eligibleDeferred": 10, "selectedPackages": 2,
 "outcome": "target_covered", "stringSearch": "available", "blindSpots": {}}
```

`not_run` means card 03 has not written a holders file. `available` means the targeted searches
completed. `unavailable` means card 03 wrote the header-only holders file and the explicit status
file below; only this value creates a string-search blind spot in reports and stories.

### `work/triage/packages.json`

An ordered JSON array contains one object per package considered in the current selection. `packageId`,
`seed`, and `componentLabel` are strings. `selectionOrder`, `countedCharacters`, and
`runningCharacters` are integers. `status` is `selected`, `in-use`, `kept-use-unknown`, or
`unknown-length`. `members`, `tests`, `inUseBecause`, and `keptBecause` are string arrays.
`inUseBecause` explains the Apex callers or string holders known to be in use. `keptBecause` explains
the non-Apex holders and Flow, Process Builder Workflow, or Workflow Rule references whose use
Elements cannot see. Each such reference gives the package status `kept-use-unknown`. `testOnly` and
`entryPointSignal` are booleans, and `reviewerText` is
the settled customer-facing string for test-only rows.
A package contains the target class, its candidate Apex callers and non-test candidate Apex string
holders recursively, every member of its
strongly connected component, and every candidate reached through a test of any member, with those
expansions repeated to a fixed point, plus tests attached by the planner's shared rule.
`componentContext` is an object with string `label`; integer `size`; integer or null
`countedCharacters`; integer or null `externalInboundEdges`; boolean or null `anyDeclaredRoot`; and
`members`, an array of objects with string `qualifiedName`, string `lastModifiedDate`, and integer
`sameMinuteClusterCount`.

```json
{"packageId": "PKG-0001", "selectionOrder": 1, "status": "selected", "seed": "LargeClass",
 "componentLabel": "shared-component", "componentContext": {"label": "shared-component", "size": 2,
 "countedCharacters": 42000, "externalInboundEdges": 0, "anyDeclaredRoot": false,
 "members": [{"qualifiedName": "Caller", "lastModifiedDate": "<timestamp>", "sameMinuteClusterCount": 1}]},
 "members": ["Caller", "LargeClass"], "tests": ["LargeClassTest"],
 "countedCharacters": 42000, "runningCharacters": 42000, "testOnly": false,
 "entryPointSignal": false, "reviewerText": "", "inUseBecause": [], "keptBecause": []}
```

### `work/triage/candidates.csv`

Every bundle candidate appears exactly once. `qualifiedName` is the string Apex name;
`countedCharacters` is the integer character count or an empty string when unknown; `componentLabel`
is the string component identifier; `status` is `selected`, `deferred`, `in-use`,
`kept-use-unknown`, `unknown-length`, or `ruled`; `packageId` is the string package identifier or
empty; and `reason` is the string selection, use, deferral, or ruling explanation. A prior `remove`,
`annotate`, or `keep` ruling has status
`ruled`; `remove` and `annotate` contribute to `confirmedCharacters`; `decide-later` is eligible
again. The inventory also carries `testOnly`, `entryPointSignal`, `entryPointChannels`, and
`reviewerText`. `entryPointChannels` is present on every row: the `;`-separated entry-point channels
the bundle signals for the class, in the order `scheduled`, `REST` (Representational State Transfer),
`SOAP` (Simple Object Access Protocol), `Invocable`, `Batchable`,
`Queueable`, `Schedulable`, and empty when none. A scheduled-job name, schedule liveness, or a true
`scheduleLive` gives `scheduled`; the class name and automation summary give the others.
`entryPointSignal` is `true` exactly when the row is test-only and `entryPointChannels` is non-empty.
For a test-only row with unknown `countedCharacters` and no entry-point signal, `reviewerText` says
"characters stop counting (Elements holds no length for this class)".

```csv
qualifiedName,countedCharacters,componentLabel,status,packageId,reason,testOnly,entryPointSignal,entryPointChannels,reviewerText
LargeClass,40000,shared-component,selected,PKG-0001,selected by capacity priority,false,false,Queueable;Schedulable,
```

### `work/triage/deferred.csv`

The columns and types match `work/triage/candidates.csv`. It contains only `deferred` and
`unknown-length` rows and preserves bundle order: `qualifiedName` is the string Apex name,
`countedCharacters` is the integer character count or an empty string when unknown,
`componentLabel` is the string component identifier, `status` is `deferred` or `unknown-length`,
`packageId` is an empty string, and `reason` is the string deferral explanation.

```csv
qualifiedName,countedCharacters,componentLabel,status,packageId,reason,testOnly,entryPointSignal,entryPointChannels,reviewerText
LaterClass,12000,later-component,deferred,,capacity priority,false,false,,
```

### `work/triage/string-holders.csv`

`qualifiedName` is the string candidate name searched; `holderName` is the string matching metadata
holder name; `holderType` is the string holder metadata type; `holderIsTest` is true when
`isTestClass` is true, or when `kind=class`, `isManagedPackage` is true, and `name` ends in `Test`,
`_Test`, or `Tests`; otherwise it is false. Match the code-search hit's `nodeId` to catalog `nodeId`
and read the catalog fields `isTestClass`, `kind`, `isManagedPackage`, and `name`. `holderInSelectedSet`
is a boolean search-time membership
flag. The selected-set flag is advisory; triage and planning recompute membership from current
packages and dispositions, comparing Apex names case-insensitively. A holder that is a test is exempt.
A self-match has the candidate's qualified name and its own Apex kind. A same-named Flow or other
non-Apex holder remains outside the removal set.

```csv
qualifiedName,holderName,holderType,holderIsTest,holderInSelectedSet
LargeClass,Integration_Config,Apex Class,false,false
```

When search is unavailable, this file contains its header and no data rows. An absent file means
the search has not run, never that it found no holders.

### `work/triage/string-search-status.json`

One JSON object contains `status`, either `available` or `unavailable`. The file is optional while
search is `not_run`; when present, `string-holders.csv` is also present.

```json
{"status": "unavailable"}
```

### `work/reasoning/payload-<unit>.json`; written by `scripts/reasoning_payloads.py`

Card 03 runs `scripts/reasoning_payloads.py`. `<unit>` is `<packageId>` or
`<packageId>-fragment-N`. `window.start` and `window.end` are
the ledger's `windowStart` and `windowEnd`.

`{ refModelId, teamId, packageId, componentLabel,
package: { packageId, selectionOrder, countedCharacters, runningCharacters, inUseBecause, keptBecause, tests,
testOnly, entryPointSignal, reviewerText }, component: { label, size, externalInboundEdges,
anyDeclaredRoot, countedCharacters, members: [{ qualifiedName, lastModifiedDate,
sameMinuteClusterCount }] },
fragment: { index, of } | null, assignedMembers: [<selected candidates.csv rows>], rows:
[<the same assigned candidates.csv rows>], window: { start, end }, thresholds: { massDeploymentCluster },
vocab: { rescueSignals, verdicts, reviewFirstReasons, incomingEdgeReading } }` (`vocab` paths are relative to the plugin root).

`assignedMembers` is mandatory and is the fragment's exact, disjoint assignment. `rows` contains only
those assigned rows. Fragment assignments are pairwise disjoint and their union equals the package.
`component` supplies compact whole-component context without duplicating every candidate row. The
script, not the reasoner, computes each member's same-minute cluster count.

### `work/reasoning/manifest.json`

One object names the current selection's units and batches: `units` is an array of unique string unit
names; `batches` packs those units, in `units` order, into one reasoner dispatch each. A fragment unit is
a batch on its own; a package unit joins the current batch while the batch's `rows` total (the sum of
its units' `assignedMembers` counts) stays at or below the fragment size in use (T-3), otherwise it
starts the next batch. A package is never split across batches. Batch ids are `batch-01`, `batch-02`,
and so on. `scripts/reasoning_payloads.py` archives existing `payload-*.json` and `return-*.json` files
(batch returns included) in `work/reasoning/previous/<UTC timestamp>/` before writing this manifest.
`scripts/merge_reasoning.py` reads only the listed units and batches and rejects any payload or return
file not listed. In `execution-state.json`, `reasoning.completed` and `reasoning.pending` hold batch ids
from this manifest: a batch is completed once its return merges, and pending while it awaits a valid return.

```json
{"units": ["PKG-0001", "PKG-0003", "PKG-0002-fragment-1"],
 "batches": [{"batch": "batch-01", "units": ["PKG-0001", "PKG-0003"], "rows": 37},
             {"batch": "batch-02", "units": ["PKG-0002-fragment-1"], "rows": 50}]}
```

### `work/reasoning/return-batch-NN.json`; written by the orchestrator from one reasoner's batch return

```json
{"batch": "batch-01", "units": [<one return-<unit>.json document per unit the batch lists>]}
```

The merge refuses a batch return whose `batch` is missing or differs from the id in its file name. It
unpacks each batch return into its per-unit returns and checks each one exactly as a
`return-<unit>.json`; a failure inside a batch names the batch id. It refuses a batch return that omits
a unit its manifest batch lists, carries a unit not listed, or lists a unit twice. A unit comes from a
batch return or from its own `return-<unit>.json`, never both.

### `work/reasoning/return-<unit>.json`; one unit's return

```json
{ "packageId": "PKG-0001", "componentLabel": "shared-component", "fragment": null, "members": [
    { "qualifiedName": "…", "verdict": "<verdict id>", "confidence": "high|medium",
      "bucket": "confident|review-first", "reasons": ["<reason id>"…],
      "quotes": ["<verbatim text relied on>"…], "cadenceSignalAvailable": true } ],
  "couldNotAssess": [ { "qualifiedName": "…", "why": "…" } ],
  "componentNote": "one quote-free paragraph on what the members appear to be together" }
```

`verdict` ids come from `data/verdicts.csv`; `reasons` from `data/review-first-reasons.csv`.
Every assigned member appears in exactly one of `members` or `couldNotAssess`. The merge adds
`telemetry_gap` and source quotes to matching rows, including rows synthesized from `couldNotAssess`,
using `data/telemetry-gap-mapping.csv`. The reasoner leaves this rule to the merge.

The merge also reads `work/bundle/catalog.csv`, `work/bundle/edges.csv`, and the telemetry ledger. For
each selected candidate that is the only non-test static Apex caller of a non-candidate class whose
`lastExecutedDate` falls within the ledger window, it adds `sole_caller_of_executed_class` and sets
`bucket=review-first` only when the callee has a direct execution signal
(`lastExecutedDirect=true`) or an inferred execution signal through a node other than that candidate
(`lastExecutedVia` names a different node). An inference through the candidate itself does not
qualify. When the execution signal qualifies and `executionCount` is present, the merge quotes the
executed class and count as executions in the window. Other static non-test Apex callers prevent this
reason; test callers do not. The review page and planner consume the merged reason.

`data/telemetry-gap-mapping.csv` has columns `source,eventTypes`. `source` is either an Elements
referrer type name as it appears in `incomingOtherTypes`, or `entry:<channel>` for a channel in the
triage `entryPointChannels`. `eventTypes` is a `;`-separated list; a source is watched when any one of
its event types is present in the ledger. For each present event type, the true-gap count is its
`missingDays` limited by the smallest `missingDays` of other present types whose `firstDay` and
`lastDay` bounds contain its whole span. Other types do not cap its count. With no qualifying other
type, its true-gap count is its own `missingDays`. This is a conservative bound because the ledger has
per-type totals, not per-day dates. An event type in `typesAbsent` contributes `bundle.effectiveDays`.
A source's count is the smallest count among its mapped types. The merge adds `telemetry_gap` when
any watched source has a count above zero, sets `bucket=review-first`, and quotes each such source once
with its true-gap days (e.g. "entry:Queueable: QueuedExecution true gap 12 of 30 days"). It does not
duplicate a reason already supplied by the reasoner. A referrer type with no mapping row adds nothing;
static referrers run no code. A row's `entryPointChannels` come from `work/triage/candidates.csv`,
joined on `qualifiedName`.

Invariants checked on the return: `verdict` ∈ `data/verdicts.csv`; `reasons` ⊆
`data/review-first-reasons.csv`; no member moves to `confident` after arriving `review-first`; every
`review-first` member has at least one reason; every rescue-signal reason has at least one quote; every
assigned member appears in exactly one of `members` or `couldNotAssess`.

### `work/reasoned-candidates.csv`; `scripts/merge_reasoning.py`

The card 03 merge reads `work/bundle/candidates.csv`, every matching unit named in
`work/reasoning/manifest.json`, and the grouping CSV `work/grouping.csv` passed with `--grouping`.
It checks the reasoner invariants before writing only selected candidates and the candidate columns plus
`verdict`, `confidence`, `bucket`, `reasons`, `quotes`, `cadenceSignalAvailable`, `componentNote`, `groupLabel`,
`groupOrder`, and `groupNote`. The presentation grouping has exactly one group per selected package, ordered by
package selection order; `groupLabel` names the package in plain words and `groupNote` is one line, in reviewer language, on why the
package looks removable, never a repeat of the label. A group can contain any positive number of candidates; `scripts/group_check.py` checks
that the group member union equals the selected-package member union.

### `report/02-candidates.md` from `scripts/candidates_report.py`

Card 02 runs `python3 <plugin>/scripts/candidates_report.py --engagement <dir>`. The script writes the
window and per-event-type days, required reclaim, candidate counts, packages found in use with every
`inUseBecause` line, packages kept because use is unknown with every `keptBecause` line, the ten largest
components, and named blind spots from compact summaries. It does not load the full candidate or
component inventory into the conversation.
The report renders an unknown character total as `unknown`; a partly known total shows the known
characters plus the count of rows with unknown length. When no package is selected, the
selected-class string search reads `not run (no package selected)`.
It marks orchestrator prose slots as `<!-- prose: ... -->`; the orchestrator fills those slots without
computing counts in prose.

### `report/04-review-pack.html`; `scripts/review_page.py`

One self-contained HyperText Markup Language (HTML) review file generated from
`work/reasoned-candidates.csv` and the bundle. Its
  `<script id="review-state" type="application/json">` block embeds `meta`, the evidence ledger and blind spots,
capacity and summary, selected packages and candidate rows, component membership,
the disposition vocabulary,
looks-dead checks, and the mutable review state, whose `reviewer` is seeded from the renderer's `--reviewer` argument
(card 04 step 1's `review.reviewer`). Saving rulings replaces that state block; CSV export uses the same
state. Preserved `remove`, `annotate`, and `keep` rulings carry `alreadyRuled: true` and remain locked;
`decide-later` carries `alreadyRuled: false`, so a reselected row remains editable.
Each package section takes its heading from the package seed, falling back to the first non-blank
member `groupLabel` and then the package id. Its note comes from the first non-blank member `groupNote`, falling back to
"Dependency-complete removal package." A row's inbound and outbound reference lists hold the edges whose
`childNodeId` or `parentNodeId` is the row's `nodeId`, one entry per referring node; `inCandidates` is true only
when the other end's node id is a selected candidate's `nodeId`. Saving from a local browser and exporting CSV
locally each tell the reviewer the file name and that it went to the browser's download folder; exporting CSV through
the downloads capability says "Saved dispositions.csv" and nothing more, because the viewer can confirm or change
the name and the capability may save through an app rather than a browser.
An unknown candidate length is `null` in the embedded row's `chars`; each group carries
`unknownLengthRows` alongside the sum of known `chars`. The page renders `unknown` or a known sum
plus the unknown row count. For a partly known total, its limit share is labeled `at least` and
its projected remaining limit is labeled `at most`. Group shares use known lengths.
The renderer reads `slots.model_id` and `slots.elements_base_url` from the engagement's
`execution-state.json`. It lowercases the base URL and accepts it only when the whole value matches
`^https://([a-z0-9-]+\.)+(elements\.cloud|elements-eng\.cloud|q9elements\.com)$`.
This excludes ports, paths, queries, fragments, user information, and trailing slashes. For each row,
the evidence drawer links to
`{baseUrl}/sf-impact-assessment/{encodeURIComponent(refModelId)}/{encodeURIComponent(nodeId)}`
with text `Open <name> in Elements`, opening a new tab with `rel="noopener"`. The model identifier
comes from `slots.model_id`; the node identifier comes from that row's `nodeId`. When the base URL
is invalid or missing, or the model identifier is missing, the drawer renders no link and keeps the
node and Salesforce identifiers as text.

### `work/review/dispositions.csv`; card 04

`qualifiedName`, `disposition` (`remove`, `annotate`, `keep`, or `decide-later` from
`data/dispositions.csv`), `decidedBy`, `decidedOn`, `note`. `annotate` is valid only for a test-only
candidate with no entry-point signal. Every displayed candidate has exactly one row. When the reviewer
declares the review finished, every displayed candidate still without a ruling is written `decide-later`.
Candidates not displayed have no row and stay unruled.
The `note` column contains only text the reviewer typed, or is empty. The orchestrator and review page
write no advice or generated text into it; review-first advice appears in conversation and in each
story's **Advice for review-first items** section.

### `work/plan/*` and `stories/*.md`; `scripts/removal_plan.py` (card 05)

- `api-names.json`: `{ "<parentNodeId>": { "apiName": "<metadata API name>" } }`. Card 05
  calls the Elements `get_metadata_node` capability once per deletable non-Apex referrer and writes
  the returned API names. The planner uses only the mapped `apiName` in a manifest and does not add
  the namespace from `edges.csv`. An unmapped referrer stays out of the manifest and becomes a
  `delete <label> in Setup` manual step.

- `tranches.json`: `{ "tranches": [{ "tranche": 1, "units": [{ "unit": "<label>",
  "members": [...], "tests": [...], "countedCharacters": n, "quarantined": false,
  "precursorRewrites": [{ "class": "<surviving test qualified name>", "kind": "test-edit",
  "removeReferencesTo": ["<removed qualified name>"] }],
  "destructiveChangesPost": [{ "type": "<metadata type>",
  "name": "<API name>" }], "manualSteps": [{ "type": "<metadata type>",
  "label": "<edge display label>", "nodeId": "<parentNodeId>",
  "action": "delete <label> in Setup" }],
  "flowReferrerTriggerTypes": ["scheduled|recordtriggered|platformevent"] }],
  "operationalBlockers": [...], "manifest": [qualifiedName...],
  "package": ["<edited test qualified name>"], "precursorStories": [{ "class": "<test>",
  "kind": "test-edit", "removeReferencesTo": [...], "keepReferencesTo": [...] }] }],
  "blockedUnits": [...],
  "unevaluatedRules": [{ "rule": "flow-trigger-block", "units": ["<unit label>"] }] }`. Deletion
  units are listed consumers before providers as reading order; each tranche deploys as one. A bundle below T-12 is an input problem
  and produces no plan.
- Blocked units carry `blockedReason` and `precursorRewrites` (the surviving tests that must stop
  referencing the unit once it is unblocked), including `cycle member <name> is quarantined under <rule>`,
  `live Flow referrer <name>`, and `referenced by the <type> <name>; Elements cannot tell whether it
  runs, so this class stays until the process or rule is deactivated or confirmed unused`.
- `quarantine.csv`: `qualifiedName`, `rule` (from `data/quarantine-rules.csv`), `evidence`.
- `capacity-totals.json`: `{ "forecastReconciled": n, "unreconciledCandidate": n,
  "annotationForecast": n, "confirmedRealized": null }`. Deletion and annotation forecasts remain
  distinct, and realized capacity stays null until deployment. Beside these totals, the
  capacity-target section in `report/final-report.md` carries one planner outcome value:
  `target_met` when confirmed characters meet the recorded requirement, `target_unmet` when they do
  not, or `not_recorded` when no integer requirement is present. When capacity is unreconciled, the
  target table labels its figure `Confirmed characters (unreconciled candidate)`; otherwise it uses
  `Confirmed characters`. Selection counts are labelled
  pre-review; remove, annotate, keep, and decide-later counts are labelled post-review.
- `validation.json`: `{ "status": "complete|failed", "counts": {...}, "invariants": [...],
  "counterexamples": [...], "manualSteps": [...] }`. Counts separate `deletionStories`,
  `precursorStories`, and `annotationStories`. The planner computes placement,
  consumer-before-provider reading order, test attachment uniqueness and reachability, edited-test package
  and story placement, survivor references, and capacity-to-manifest reconciliation. Every failed
  invariant carries named counterexamples. `manualSteps` lists each non-Apex referrer omitted from a
  manifest because its API name is unavailable.
- `tranche-<NN>/package.xml` lists every surviving test edited by that tranche.
  `tranche-<NN>/destructiveChangesPost.xml` lists removed Apex and mapped non-Apex metadata. Stories
  deploy the two files together with `--manifest package.xml` and
  `--post-destructive-changes destructiveChangesPost.xml`.
- `stories/<NN>-<unit>.md`: one per removal unit, annotation ruling, or precursor rewrite, following
  the applicable shape in `references/story-template.md`. Annotation stories sit outside tranches and
  state that nothing is deleted. An edited surviving test has one precursor story naming every
  removed class it stops referencing and every surviving class it keeps referencing. Every story
  states targeted string results when search is available, absent telemetry event types, classes
  left without an incoming non-test Apex caller, and the reversible check for each deleted non-Apex
  referrer that applies to the story. A member with `sole_caller_of_executed_class` carries that doubt
  reason and its executed-class quote. Its operational check requires inspecting Setup > Scheduled Jobs
  and stopping for a new ruling when a job exists.
- `report/final-report.md` sections appear in this order: telemetry window; estate, candidates and
  rulings; capacity totals; capacity target; tranches; quarantine; decide-later rulings; not reviewed
  this round; blind spots;
  validation; release gate. Capacity target states target wording, required and confirmed characters,
  outcome, pre-review selected, deferred, found-in-use, and kept-use-unknown counts, and post-review ruling counts.
  It shows ruled remove characters, placed removals, characters held in blocked units, characters
  held in quarantine, annotate rulings, and confirmed characters, and states that ruled remove
  characters are the placed removals plus the characters held in blocked units and in quarantine,
  and confirmed characters are the placed removals plus the annotate rulings. Quarantine carries `### Blocked units` and
  `### Test rewrites` subheadings over the blocked-unit reasons and the precursor-story lines.
  The decide-later rulings table lists every `decide-later` row from
  `work/review/dispositions.csv`, with its class and reviewer note; an empty note appears as `none`.
  The not reviewed this round section gives the row count in `work/triage/deferred.csv`, including
  zero when the file is absent, and names that file without printing deferred names. Deferred
  candidates are triage's long tail outside the capacity cut, not reviewer rulings.
