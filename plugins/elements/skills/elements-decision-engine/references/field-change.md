# Field-change recipe

For a field update or deletion, answer what references the field and must change, and what automation fires when its value changes, including what it triggers on related records. The Decision Engine (DE) scan is static and one hop; its impact analysis also supplies the deletion cascade. Runtime fire-chain evidence is separate.

## 1. Resolve references and change impact

Call `run_dependency_scan({refModelId, objectApiName, fieldApiName, analysisMode})`, using `analysisMode:"update_field"` for an update or `"delete"` for deletion. For a standalone scan, omit `missionId` to start a mission; follow the shared-analysis status, paging, and evidence rules in the parent skill and [Results and presentation](results.md).

Then call `run_change_impact_analysis({refModelId, missionId, changeDescription, analysisMode})` with the same mode and mission. Report direct references, analysis targets, impact work, and coverage. A delete plan includes its ordered delete cascade and caps. Stop after impact unless the user asks for architecture risk or a backlog.

For field-target report references, apply the report rules in [Results and presentation](results.md).

## 2. Evaluate what fires

This step uses `run_data_load_impact`:

```text
run_data_load_impact({
  refModelId,
  targets: [{object, operation:"update", writtenFields:[fieldApiName], estimatedVolume:1}],
  depthBound
})
```

`targets` accepts 1 to 5 entries. Each target requires `object`, `operation`, `writtenFields`, and positive integer `estimatedVolume`; update requires nonempty `writtenFields`. Set `operation` to the record operation performed by the new or changed automation on that object (`insert`, `update`, `upsert`, or `delete`), and set `writtenFields` to the fields it writes. For example, an automation that creates Task records uses `object:"Task"` and `operation:"insert"`. Volume affects only load-risk evidence. Use the default `depthBound` of 5; use 10 only when the user asks for the complete chain or the depth-5 result reports `depth_bound_reached` (or still has rows at depth 5 when no marker is available). The graph budget can stop traversal before either bound. If status is `computing`, repeat the identical call after `retryAfterSeconds` (normally about 30 seconds) until complete. Treat a structured `model_not_synced` error as a terminal outcome: the reference model is mid-sync. For other `error` statuses, follow its `instruction`. Treat `disqualified` as another terminal outcome for runtime analysis.

Combine fields for one object in one target when a union of possible triggers is enough: `writtenFields` is treated as a set, so the result is the union. Use one target per field for field-by-field attribution. Multiple fields still need one DE mission per field for step 1; run missions sequentially because each user and Space can have at most five live DE runs. Batch runtime targets in groups of up to five. In one report, count a shared dependent or automation once and list every field whose path reaches it.

The completed response summarizes the analysis and provides `bundleUrl`; download the bundle for full evidence within 120 seconds, after which the link expires. The tool response carries counts; the per-target `directAutomations.matched`, `validationRules.matched`, and `fireChain[].digest[]` detail lives in `response.json` inside the bundle. For each target, inspect those entries, including `minDepth` and variants. Digest rows with no `entity` carry `targetAlternatives`; report these as possible targets, not confirmed entities. Variant fields include `firingAutomation`, `mechanism`, `lockConsequence`, `valueChange`, and `recursiveSave`. Include target and branch coverage, top-level `coverage`, and `coverage.absenceIsEvidence`.

Lead with automations that fire because they read the changed field. Separate them from the upper-bound set that fires on every save of the object, such as triggers or automations that read no fields. Summarize the upper-bound chain by depth with object and automation counts, and state where the graph budget stopped traversal. The runtime result is an upper bound. A nonmatching Apex trigger is still assumed to fire when read evidence is partial, marked by an `automation_fire_assumed_partial_reads` receipt. Each hop uses fields the preceding automation writes. Entry criteria and value conditions such as `ISCHANGED` or “only when updated to meet criteria” are not modelled. Static references such as formulas, layouts, and reports are covered by step 1. Approval and escalation rules are not walked.

For a field deletion, step 2 describes what currently runs because of the field, which loses that trigger, and what fires if the field is blanked before removal. Step 1 is authoritative for the deletion and cascade. In step 2, use the record operation the automation performs on each target object; `operation:"delete"` models deleting records, not deleting the field.

The runtime tool requires an Enterprise Space, view access to the reference model, and a fully synced model. It does not require the DE license or edit access. If the model is mid-sync, tell the user that a sync is in progress, that step 1 results come from the last completed sync, and that rerunning after the sync completes provides runtime evidence. If step 2 is unavailable or refused, deliver step 1 and any permitted step 3 analysis, marking step 3 automations as not confirmed by runtime analysis.

## 3. Confirm first-hop triggers

Use `directAutomations.matched` from the bundle as the first-hop set; digest rows can describe later chain variants. If step 2 was refused with `model_not_synced` or `disqualified`, step 3 may use the automations found in step 1 as its first-hop set, and mark them as not confirmed by runtime analysis. On a `create_new` path where step 1 finds no existing automations, step 3 may instead use automations named by the user that appear in the inventory rows, marking them as not confirmed by runtime analysis. If no such automations appear, report that step 3 has no first-hop set and skip it. Do not treat `minDepth` as the hop count in a representative path. For each first-hop automation, call `explain_metadata_item({refModelId, nodeId, aspect:"chain"})` and read `result.sections`; small responses arrive inline, while large responses may be written to a file by the client. The tool has no sections-only option. If the result has `status:"generating"`, wait for `retryAfterSec:30` and retry within `maxWaitSec:240`. Check whether real entry criteria depend on the changed field. Use one of five verdicts: “confirmed trigger”, “reads the field but entry criteria do not depend on it”, “fires on every save of this object”, “runs inside a first-hop trigger”, or “not triggered by a save”. Use “runs inside a first-hop trigger” for a class or helper invoked by a trigger that fires on every save. Actions, utilities, and API services belong under “not triggered by a save” when evidence shows they are invoked directly. Apex classes with mechanism `unknown` and no trigger events also use that verdict unless the chain shows otherwise. If the node type is unsupported or its summary is missing, report that result. Inspect at most about 10 first-hop automations; list any remainder as unconfirmed.

## Report

Use one report from the existing template. Fill Dependencies and Change Impact from step 1; put steps 2 and 3 in the “What fires” tab. State the one-hop scan, delete-cascade caps (`maxDepth:6`, `maxNodes:100`, with the six-month lookback applying to reports), upper-bound fire chain, unmodelled conditions, and every step not run with its reason in coverage.

**Illustrative example:** “What happens if `Job__c.Status__c` is deleted?” The delete scan and impact return 3 flows, 1 validation rule, 1 report, and a delete order. Updating `Status__c` returns 2 first-hop flows; one writes `Invoice__c.Stage__c`, which fires an Invoice trigger at depth 2. Step 3 confirms one flow's entry criteria use `Status__c`; the other fires on any update.
