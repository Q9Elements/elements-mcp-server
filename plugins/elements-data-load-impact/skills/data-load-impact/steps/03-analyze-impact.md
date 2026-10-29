# 03 Analyze impact

State: `manifest-confirmed`

## Purpose

Obtain complete per-object fire-chain and load-risk evidence, then explain it as one impact report.

## Procedure

1. Read `work/intake/tool-targets.json`. For each `calls[]` entry, call
   `run_data_load_impact` with that entry's unchanged `arguments`. Every call contains exactly one
   object, with `refModelId` from `slots.model_id` and `teamId` from `slots.space_id`. Run these calls
   serially, never in parallel.
2. On `running`, call again with identical arguments after `retryAfterSeconds`, up to
   `poll_cap` in `data/thresholds.csv`. On `fire_chain_analyses_at_capacity`, `server_busy`,
   `rate_limited`, or `too_many_concurrent_requests` refusals, wait the returned `retryAfter` and
   retry the identical call within the same cap. Retry a `failed` reply
   with `retryAfterSeconds` using the identical arguments within the cap. If transport fails
   without a tool reply, wait 60 seconds and retry the identical call within the cap. Beyond the
   cap, record an open item and take TR-12, the default self-loop on `manifest-confirmed`. Do not
   retry `bundle_too_large`; record an internal open item and take TR-12.
3. On `complete`, write the envelope without `bundleUrl`, download the bundle immediately, verify
   `bundleSha256`, and unzip below `work/bundle/<object>-<operation>/`. If the URL expires or download fails, call
   again with identical arguments for a fresh URL. Never store the URL. Record object, job identifier,
   computation date and time, digest, and directory in `analysis.calls`.
4. Call `list_metadata_by_criteria` with `refModelId` from `slots.model_id`, `teamId` from
   `slots.space_id`, and `metadataList: ["Duplicate Rule"]`. Poll while `running` after
   `retryAfterSeconds`; for a refusal, wait `retryAfter` and retry within `poll_cap` in
   `data/thresholds.csv`. Follow `nextPartsFrom` until no more parts remain. Save each tool reply
   verbatim under `work/analysis/duplicate-rule-replies/<n>.json` as
   `{"savedAt": "<International Organization for Standardization (ISO) 8601 date and time in Coordinated Universal Time (UTC)>", "reply": <tool reply>}`; `<n>` is the reply's call order.
   Join the replies with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/part_files.py" join --replies work/analysis/duplicate-rule-replies --out work/analysis/duplicate-rules.ndjson`.
   Read the joined rows, retaining rows whose `parentObject` is a manifest target and whose
   `nodeDetails.active` is true. Record names grouped by object in `analysis.duplicateRules`,
   including an empty list for each target object. Write the same mapping to
   `work/rehearsal/duplicate-rules.json` for report generation and the backlog.
5. For every `automation_managed_excluded` receipt on a target object, call Elements
   `search_metadata` with `refModelId` from `slots.model_id` and `teamId` from `slots.space_id`,
   `sfType: "Apex Trigger"`, and the trigger name as the query. A managed
   result has a path beginning `Managed Packages`, followed by its namespace. Resolve node detail
   when several nodes have the same trigger name and retain every managed node whose trigger belongs
   to the target object. If node detail cannot establish the object, retain every managed namespace
   returned for that name and say that the target association is unverified in the report. Group
   trigger names by target and namespace in `work/analysis/managed-packages.json`, shaped as
   `{ "<Object>": [{"namespace": "<namespace>", "triggers": ["<trigger>"]}] }`. Record the same
   mapping in `analysis.managedPackages`. An unresolved lookup leaves the package for TR-24.
6. Immediately before dispatching a parallel batch, tell the owner this exact sentence, replacing
   `<objects>` with that batch's object names: "The **Order of Execution Narrator** agent is explaining
   what fires when <objects> records save." Emit one sentence per batch. Dispatch the narrators in
   parallel, giving each `slots.model_id`, `slots.space_id`, each distinct
   object node identifier named in `fire-chain-digest.csv`, and that object's digest rows as card
   text, including structural roll-up paths. The digest is the source for whether a roll-up path
   reaches that object. The agent calls `explain_metadata_components` with
   `aspect: "order_of_execution"`; it polls `running` after `retryAfterSeconds` up to
   `maxWaitSeconds`, and retries `rate_limited` after its `retryAfterSeconds`. It reads the tool's
   `beforeSave`, `afterSave`, `risks`, and `dataMigration` facts and returns `narrative` as
   `{"toolFacts": ["<plain sentence per populated phase fact>"], "explanation": "<digest explanation>"}`.
   It omits empty and `Not found` phases and the tool's `source` field. The renderer prints facts
   as bullets followed by the explanation paragraph. The orchestrator writes each response to
   `work/narration/<object>.json`, including the agent's structured `automations` list of every
   named automation, even when absent from the digest. Preserve explicit application programming
   interface (API) names, namespaces, metadata types, and the narrated object so card 04 can identify
   each automation. Names alone do not prove activation or firing.
7. Run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/impact_report.py" work/bundle/<object>-<operation> [more bundle directories] --residue work/intake/residue.json --duplicate-rules work/rehearsal/duplicate-rules.json --managed-packages work/analysis/managed-packages.json --narration work/narration/<object>.json [more narration files] --out report/03-impact.md`

   Set `analysis.reportFile`. Set `analysis.absenceIsEvidence` to true only when the "Overall
   absence is evidence" value in the report is true for every target object. Record unresolved
   managed trigger names for card 04 and card 06.
   Regenerate this file from its inputs after a rerun.

## Outcomes, in precedence order

The first condition that holds wins.

- **TR-09 — the tool throws `model_not_synced` or returns `model_resynced`.** Set `blocked` to
  `{"reason": "SYNC_INCOMPLETE", "owner": "Salesforce administrator", "entered_from": "03", "evidence": ["<tool status>"]}`,
  record it in `decisions_log`, and write
  `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card:
  `steps/08-blocked-recovery.md`.
- **TR-10 — the tool returns final `validation_failed`.** Record every rejected name in `open_items`
  and write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-intake-manifest.md"}`.
  Next card: `steps/02-intake-manifest.md`.
- **TR-11 — every one-object bundle is complete, verified, duplicate rules and managed-package lookups are recorded, narrated, and represented in `report/03-impact.md`.**
  Record "impact analyzed" in `decisions_log` and write
  `{"current_state": "impact-analyzed", "current_step": "steps/04-audit-bypass.md"}`. Next card:
  `steps/04-audit-bypass.md`.

- **TR-12 — Otherwise.** `{"current_state": "manifest-confirmed", "current_step": "steps/03-analyze-impact.md"}`. Next card: `steps/03-analyze-impact.md`. Record the default call in `decisions_log` and tell the user. No partial bundle is kept.

## Stop rule

After TR-11, dispatch card 04 in the same turn. Dispatch card 08 in the same turn after TR-09. Stop on TR-10 or TR-12.

## Failure

On infrastructure error, poll-cap exhaustion, incomplete bundle, digest mismatch, or report failure, record the aggregate-safe error in `open_items` and take TR-12, the default self-loop on `manifest-confirmed`; keep no partial bundle.
