# Field-change recipe

## Contents

- Resolve references and change impact
- Evaluate what fires
- Confirm first-hop triggers
- Report

Answer what references a changed field, what must change, and what fires on related records.
Static impact, runtime traversal, and first-hop explanations provide separate evidence.

## 1. Resolve references and change impact

Call `run_dependency_scan({refModelId,teamId,objectApiName,fieldApiName,analysisMode})`, omitting `missionId` for a standalone request.
Use `analysisMode:"update_field"` for updates or `"delete"` for deletion. Apply [Results](results.md) for statuses, counts, and paging.
Then call `run_change_impact_analysis({refModelId,teamId,missionId,changeDescription,analysisMode})` with the same mode and mission.
Report references, analysis targets, work, coverage, and ordered deletion consequences. Add risk or backlog only when requested.

## 2. Evaluate what fires

Call the Model Context Protocol (MCP) runtime tool:

```text
run_data_load_impact({refModelId, teamId,
  targets:[{object,operation:"update",writtenFields:[fieldApiName],estimatedVolume:1}], depthBound})
```

Omit `delivery`; the tool supplies its bundle. Optional `teamId` selects the space. Use these input and polling rules:

- `targets` accepts 1 to 5 entries. Each requires `object`, `operation`, `writtenFields`, and positive integer `estimatedVolume`.
  Object is nonempty; operations are `insert`, `update`, `upsert`, or `delete`. Update and upsert require nonempty written fields;
  insert and delete accept `[]`, including a trigger object on which a new automation writes no fields. Match the record operation
  and fields written per object. Creating Tasks uses `object:"Task"`, `operation:"insert"`. Volume affects load risk only.
- `depthBound` is 1 to 10, default 5. Use 10 for a requested complete chain or `depth_bound_reached` at depth 5
  (or rows at depth 5 without a marker). The graph budget can stop traversal earlier.
- Keep parsed `jobId` with exact targets, depth, space, and reference model. Identity includes these arguments and the sync timestamp;
  changing targets or depth selects another job. Keep it distinct from the mission and file-result identifiers in SKILL.md.
- While `running`, repeat identical arguments after `retryAfterSeconds`, or about 30 seconds if absent. A failed response ends this
  attempt; use `message` and any `instruction` for a later retry. Mid-sync or disqualified runtime analysis is unavailable.

Combine an object's fields in one target for a union of possible triggers; `writtenFields` is a set. Use separate targets for
field attribution and one Decision Engine mission per field for step 1, sequentially under the [run cap](refusals.md).
Batch runtime targets within the input bound above. Count shared dependents or automation once and list every contributing field.

On completion, consume dispatcher files under [Results](results.md), then acquire the bundle:

- Download `bundleUrl` immediately; use returned `expiresInSeconds` and verify `bundleBytes` and `bundleSha256`
  (Secure Hash Algorithm 256-bit). Repeat identical arguments for fresh links after expiry or failed fetch. Completed results have a
  23-hour reuse threshold; recomputation can keep `jobId`, so retain `computedAt` and separate attempts. Missing bundles mean missing evidence.
- Summary `targetsAnalyzed` counts targets. Bundle `response.json` has a per-target entry with `directAutomations.matched`,
  `validationRules.matched`, `assignmentRules`, `fireChain`, and `loadRisk`. Upsert has separate insert and update branches.
  Inspect `minDepth` and variants; rows without `entity` have `targetAlternatives`, which are possible targets.
- Variants include `firingAutomation`, `mechanism`, `lockConsequence`, `valueChange`, and `recursiveSave`. Preserve target/branch
  coverage, top-level `coverage`, and `coverage.absenceIsEvidence`.

Lead with automation reading the changed field; separate the upper-bound set firing on every save, including triggers and automation
reading no fields. Summarize chain depth with object/automation counts and graph-budget stops. Partial Apex read evidence can assume
firing via an `automation_fire_assumed_partial_reads` receipt. Each hop uses the preceding automation's written fields.
Entry criteria and value conditions (`ISCHANGED`, “only when updated to meet criteria”) are unmodelled. Static formulas, layouts,
and reports belong to step 1; approval and escalation rules are outside runtime traversal.

For field deletion, show what currently runs because of the field and what fires if it is blanked before removal. Step 1 governs
deletion and cascade; runtime `operation:"delete"` models record deletion. For permissions and mid-sync recovery, read [Refusals](refusals.md).
If runtime evidence is unavailable, deliver step 1 and permitted step 3 evidence with first-hop runtime confirmation marked unavailable.

## 3. Confirm first-hop triggers

Use bundle `directAutomations.matched` as the first-hop set; digest variants can describe later hops. `minDepth` is not a representative
path's hop count. If runtime is unavailable, use step 1 automation and mark it unconfirmed by runtime analysis. For `create_new` with
no existing automation in step 1, use user-named automation present in inventory; if none exists, report the missing first-hop set and skip.
Inspect about 10 first-hop automations at most; list the remainder as unconfirmed. Carry parsed identifiers into:

```text
explain_metadata_components({refModelId,teamId,nodeIds,aspect:"chain",delivery:"file"})
```

- Supply exactly one of `nodeId` or `nodeIds`, with at most 25 supplied identifiers. `summary` and `purpose` support standard fields.
  Purpose explains recorded business intent; without linked stories or requirements it completes with `confidence:"Low"` and no
  linked-ticket evidence, without generation. Summary confidence is `High`, `Medium`, `Low`, or `null`; purpose preserves supplied
  confidence or uses `Low`; chain confidence is numeric when supplied; lineage/order confidence is `null`.
- Apply [file delivery](results.md#file-delivery-reply-rule) before reading bulk `items`, `totalItems`, `skip`, and `hasMore`.
  Read each item's `nodeId`, `aspect`, and `status`. Complete chain items have `narrative.sections`, optional `narrative.chainRelationGroups`,
  and root `confidence`, `generatedAt`, and `cached`. Failed items expose `error` and `message`; internal `errorMessage` can be null.
  Preserve failures as terminal for this attempt except the rate-limit case below. Resending a failed component can start generation.
  Unsupported chain types fail with `invalid_input`; missing summaries can yield `missing_automation_summary`. Leave those unconfirmed.
- Finish all pages for the exact `nodeIds` selection, following `_truncated.nextSkip` or `hasMore`. Without a cursor, advance `skip`
  by actual items consumed. Then poll only running items with the same `aspect` and space at `skip:0`; offsets belong to one selection.
  Wait returned `retryAfterSeconds` (normally 30). Measure `maxWaitSeconds` (normally 960) from the first running response;
  report pending items incomplete at that bound. Explanations supply no mission or external job identifier.
- Fabricated example: selection `aaaaaaaaaaaaaaaaaaaa0319`, `bbbbbbbbbbbbbbbbbbbb0420` returns the first complete, the second running.
  Finish that selection's pages, then poll only `bbbbbbbbbbbbbbbbbbbb0420` at `skip:0`. Keep completed items locally.
- Generation starts permit 10 per user and 15 globally per minute; cached reads and held-lock polls start none. Per-item
  `error:"rate_limited"` is terminal in that response and carries `retryAfterSeconds` (normally 60). Retry only after its own delay,
  even if the aggregate running hint is 30; retain other complete and failed items. Outer refusals use [Refusals](refusals.md).

Check entry criteria against the field. For insert/delete, “confirmed trigger” means firing on that operation; state the criteria.
Use five verdicts: “confirmed trigger”, “reads the field but entry criteria do not depend on it”, “fires on every save of this object”,
“runs inside a first-hop trigger”, or “not triggered by a save”. A helper called by an every-save trigger uses the fourth verdict.
Actions, utilities, and application programming interface (API) services invoked directly use the fifth. Apex classes with mechanism
`unknown` and no trigger events also use the fifth unless chain evidence shows otherwise.

## Report

Fill Dependencies and Change Impact from step 1; put steps 2 and 3 in “What fires”. State the one-hop scan, deletion caps/report lookback
from [Results](results.md), upper-bound traversal, unmodelled conditions, and every skipped step with its reason.
Illustrative example: deleting `Job__c.Status__c` returns 3 flows, 1 validation rule, 1 report, and a delete order. Updating it returns
2 first-hop flows; one writes `Invoice__c.Stage__c`, firing an Invoice trigger at depth 2. Step 3 confirms one flow reads `Status__c`
in its entry criteria; the other fires on any update.
