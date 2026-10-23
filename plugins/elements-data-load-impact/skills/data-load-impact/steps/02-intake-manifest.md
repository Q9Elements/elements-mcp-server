# 02 Intake and confirm the manifest

State: `prerequisites-confirmed`

## Purpose

Turn the planned local load into a confirmed aggregate-only manifest and strict one-object analysis
calls without exposing record data to the model.

## Procedure

1. **Hold the privacy gate.** Never open, read, paste, summarize, or ask the user to paste raw
   comma-separated value (CSV) rows, Salesforce Object Query Language (SOQL) results, or debug logs.
   Scripts may read those files locally. The orchestrator may read only their aggregate outputs.
2. For a local comma-separated value (CSV) load file, run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" count --file <local-source>`
   from the engagement directory. Read its row count and `candidateWrittenFields`, never its rows.
   Use the count as `estimatedVolume` and the header names as proposed written fields. Propose the object and operation from the source file name and header (an `Id` column
   suggests update); the owner corrects them in the same confirmation with the fields. For a query-defined load without a file, include the owner's approximate
   volume and written fields in the same confirmation. Include the external-identifier match field
   and approximate insert share for upsert, and the portal-role fact for User insert or upsert.
   Ask one question that shows the proposed object, operation, counted rows, and written fields;
   names the loader and its Application Programming Interface (API) choices from `data/tool-matrix.csv`; and includes the upsert match field,
   expected insert share, or portal-role fact when applicable. The owner confirms or corrects
   everything in one reply. Record the chosen loader and API as `manifest.loader` and `manifest.api`. Do not ask the owner to type
   field names already shown from the header. Write the confirmed targets
   to `manifest.targets`, and record the confirming person and time in `manifest.confirmedBy`,
   `manifest.confirmedOn`, and `decisions_log`.
3. For User insert or upsert, record the portal-role answer, matching operation or operations,
   person's name, and date and time in `manifest.roleBasedPortalUser` and `decisions_log`. On yes, add one
   `User:<operation>=role_based_portal_user` entry per matching operation to `manifest.targetFacts`.
   On no, leave `manifest.targetFacts` empty. When there is no User insert or upsert, record
   `applicable: false` without asking the question.
4. Before the exporter runs, make one `list_metadata_by_criteria` call per target object, with
   `refModelId` from `slots.model_id`, `teamId` from `slots.space_id`, `metadataList: ["Field"]`,
   and one `parent_object eq` filter for that object. Include `parent_object`, `api_name`,
   `subtype`, `delete_constraint`, `required`, `manage_package`, `full_api_name`, and `status` in
   `columns`. Make no more than five calls, one per target object. Save each tool reply verbatim
   under `work/intake/criteria-fields-replies/<object>/<n>.json` as
   `{"savedAt": "<International Organization for Standardization (ISO) 8601 date and time in Coordinated Universal Time (UTC)>", "reply": <tool reply>}`; `<n>` is the reply's call order.
   Poll `running` after `retryAfterSeconds`, pass `nextPartsFrom` as `partsFrom` to fetch more
   parts, and retry a refusal after its `retryAfter`, within the `poll_cap` in
   `data/thresholds.csv`. Run these calls serially. Join each object's replies with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/part_files.py" join --replies work/intake/criteria-fields-replies/<object> --out work/intake/criteria-fields-<object>.ndjson`.
   Give the **org-context-exporter** agent `slots.model_id`, `slots.space_id`, the target objects,
   and these joined Field rows. It requests full component documents inline in batches of at most
   10 node identifiers for the reference fields, target objects, and every object in those fields'
   `referenceTo`. It resolves referenced objects with inline `search_metadata`, keeping exact `apiName`
   matches of object types; on `_truncated`, it halves the batch and repeats. A polymorphic field
   with more than 50 distinct targets contributes only its first 50 names in lexicographic order,
   bounding document work. The agent keeps all declared targets and names every capped or unreadable
   object and missing prefix in `couldNotCover`. Referenced objects contribute `keyPrefixes` only;
   relationship inventories remain limited to load targets. The agent returns Object 2 from
   `references/payload-contract.md`. The
   orchestrator writes it to `work/intake/org-context.json` and sets `manifest.orgContextFile`.
5. For each target, call `run_data_load_impact` once at a time with exactly one bare target
   containing only `object`, `writtenFields`, `operation`, and positive `estimatedVolume`, plus
   `refModelId` and `teamId` from `slots.model_id` and `slots.space_id`. Use the step 2 row count
   for a CSV target and the owner's estimate for a query-defined target. Poll `running` with
   identical arguments after `retryAfterSeconds`, up to `poll_cap` in `data/thresholds.csv`. For
   `fire_chain_analyses_at_capacity`, `server_busy`, `rate_limited`, or
   `too_many_concurrent_requests` refusals, wait the returned `retryAfter` and retry the identical
   call within the same cap. Retry a `failed` reply with `retryAfterSeconds` using the identical arguments
   within the cap. If transport fails without a tool reply, wait 60 seconds and retry the identical
   call within the cap. Do not call multiple analyses in parallel.

   On `complete`, copy `summary.syncRecency.lastSyncCompleted` to `sync.timestamp`. Download the
   complete baseline bundle immediately, verify its 256-bit Secure Hash Algorithm (SHA-256) digest,
   and store it below `work/bundle-baseline/<object>-<operation>/`. Save the response without
   `bundleUrl` as `envelope.json`; never persist the signed Uniform Resource Locator (URL). Use
   `rules-data.json` from the first bundle and require the same `rulesVersion` in every baseline
   bundle. A `validation_failed` result is final for those names and is shown to the owner before
   local profiling.
6. From the engagement directory, run `load_input_prep.py` once per target using the matching form in
   `scripts/CLI.md`, the baseline `rules-data.json`, `work/intake/org-context.json`, and `--hash-ids`.
   For example:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" csv --file <local-source> --object <object> --rules work/bundle-baseline/<object>-<operation>/rules-data.json --out work/intake/payload-N.json --operation <operation> --written-fields <fields> --org-context work/intake/org-context.json --hash-ids`

   If it exits 2, read the pending-questions JavaScript Object Notation (JSON) envelope from standard
   output. Use the confirmed manifest to answer its operation, written-field, upsert, and volume keys.
   Write `work/intake/answers-N.json` with those values and rerun with
   `--answers work/intake/answers-N.json`. For a CSV target, compare the payload's
   `targets[0].estimatedVolume` with the count used in step 5. If the count changed, repeat steps 2 and 5 with the
   current file before continuing. The model may read the ask envelope and aggregate payload, never
   the source.
7. A relationship key prefix identifies the referenced object type; it does not prove that a record
   exists. For update and upsert unresolved stored values, write one combined query file under
   `work/intake/` containing one Salesforce Object Query Language (SOQL) query per referenced object.
   Each query selects all lookup fields needed for that object and the loaded-set match field, with
   the loaded-set predicate filled from the local source. Give this one file to the customer to run;
   they save each result locally. Pass the same result file once per lookup field with repeated
   `--soql-result COLUMN=RESULT.csv` flags.
   Never open a result file. If the customer declines, record each unassessed field as a named load
   risk for the existing go or no-go question; request no other evidence.
8. Run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tool_targets.py" work/intake/payload-1.json [more payloads] --ref-model-id <slots.model_id> --team-id <slots.space_id> --out work/intake/tool-targets.json --residue work/intake/residue.json`

   Do not hand-edit a rejected target. Set `manifest.payloadFiles`, `manifest.toolTargetsFile`,
   `manifest.residueFile`, `manifest.calls`, `manifest.rulesVersion`, and
   `manifest.privacyGateHeld` from these outputs.
9. Record incomplete residue and the one-call-per-object plan beside the confirmed manifest. Present
   these findings in the analysis without another owner question.

## Outcomes

- **TR-04 — the baseline call is refused with `model_not_synced` or fails with `model_resynced`.**
  Set `blocked` to `{"reason": "SYNC_INCOMPLETE", "owner": "Salesforce administrator", "entered_from": "02", "evidence": ["<tool status>"]}`,
  record the facts in `decisions_log`, and write
  `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Dispatch card
  08 in the same turn.

- **TR-07 — the data-load owner confirms every target, the privacy gate is held, and steps 5 to 8 wrote `work/intake/tool-targets.json` without failure.** Write
  `{"current_state": "manifest-confirmed", "current_step": "steps/03-analyze-impact.md"}`. Next
  card: `steps/03-analyze-impact.md`.

- **TR-08 — Otherwise.** `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-intake-manifest.md"}`. Next card: `steps/02-intake-manifest.md`. Record the default call in `decisions_log` and tell the user. The report names the error in aggregate terms only.

## Stop rule

After TR-04, dispatch card 08 in the same turn. After TR-07, dispatch card 03 in the same turn.
Stop on TR-08.

## Failure

For a baseline refusal `model_not_synced` or failed job `model_resynced`, take TR-04. For
`bundle_too_large`, a non-retryable failure, transport failure, or poll-cap exhaustion, put only the
aggregate-safe error in `open_items` and take TR-08. On an unresolved ask, nonpositive volume,
changed CSV row count, schema rejection, digest mismatch, or rules-version mismatch, take TR-08.
Never copy a raw record, result row, or signed URL into state.
