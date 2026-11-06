# 06 Rehearse and reconcile

State: `package-ratified`

## Purpose

Offer a small-batch sandbox check of the ratified controls and report measured results when the owner chooses it.

## Procedure


1. When `rehearsal.choice` is null, build short
   customer-language bullet reasons to rehearse from this engagement's state. Name active rules in
   `analysis.duplicateRules` whose `DUPLICATES_DETECTED` rejections would be counted; name each
   `package.incidentClassRulings` class marked `measured-in-rehearsal` whose effect would be measured;
   name ratified `bypass` and `deactivate` actions whose behavior would be checked; name lock controls
   and ratified parent grouping, concurrency, or batch-size settings whose small-batch behavior and
   possible lock-ladder changes would be checked. Include "automation outside the expected fire chain"
   as a reason to rehearse. Use one line per applicable reason and save those exact lines
   in `rehearsal.reasonsToRehearse`.
   A zero-row checklist follows the same rehearsal choice and evidence procedure, including
   the check for automation outside the expected fire chain.

2. This playbook does not change Salesforce metadata. Check the capture path locally before asking
   about rehearsal.
   First compare `manifest.loader` with `work/package/parameters.json.loader` and its supported
   Application Programming Interface (API) in `data/tool-matrix.csv`. The Salesforce command-line
   interface (sf CLI) path covers exactly one confirmed insert, update, or upsert target with a
   local comma-separated value (CSV) source file, `api: "Bulk API 2.0"`,
   `batchSize: "server-managed"`, `concurrencyMode: "parallel"`,
   either value of `groupByParentId`, and `assignmentRulesEnabled: false`. Its command must match the
   confirmed object, operation, written fields, and assignment-rule setting. A query-defined load
   without a source file uses the manual path. Serial mode or a numbered batch size,
   a different API, or more than one target also uses the manual path because this CLI cannot set
   those parameters. State the first mismatch in one line, for example "The ratified load needs
   serial mode, which this sf CLI cannot run, so the rehearsal runs
   manually." Mark the sf CLI path unavailable and do not ask for an alias. Recheck
   this local mapping after every TR-23 lock-ladder change and every return from card 05.

   Read the source header through `load_input_prep.py count` and read `parentSortField` from
   `work/package/parameters.json`. When `groupByParentId` is true
   and that field is present in the confirmed source header, sort the rehearsal batch by it.
   When the field is null or absent from the header, use file order on either path and state
   "parent grouping was not rehearsed" as a risk in the rehearsal result and final report.
   For a local CSV source, run one slice command shared by both capture paths:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/load_input_prep.py" slice --file <confirmed-local-source> --out work/rehearsal/batch.csv --rows <rehearsal_batch_rows from data/thresholds.csv> [--sort-by <parentSortField only when grouping is on and the field is in the source header>]`.
   Read its aggregate JavaScript Object Notation (JSON) output: `rows`,
   `candidateWrittenFields`, and `lineEnding`. Require a positive row count. Compare the header
   field names with the confirmed target, allowing `Id` or the upsert match field as an identifier
   but no unratified write columns. For update, require `Id` first; for upsert, require the confirmed
   match field in the header. Never open `batch.csv` in model context. If slicing or the header
   check fails, report the aggregate-safe mismatch and use the manual path. The customer
   prepares a batch of at most `rehearsal_batch_rows` rows from the correct source for that path.
   A query-defined load uses a customer-prepared local batch. When grouping is on and
   `parentSortField` is known in that batch, the customer sorts it by that field; otherwise
   the batch stays in file order and carries the stated risk.

   Check whether `sf` is installed. When it is, tell the customer "I am checking sf CLI for
   rehearsal sandbox aliases" and run `sf org list --json`; collect aliases in
   `result.sandboxes`. This command lists local authentication and does no sandbox work.
   The sf CLI path can run when the local mapping and slice pass and a sandbox alias is listed.
   When `rehearsal.choice` is null, show the saved reasons and ask once: "Rehearse this load in
   the sandbox (recommended), or skip? If rehearsing with sf CLI, which listed full-copy
   sandbox alias should I use, or none for manual steps?" Omit the alias sentence when the sf
   CLI path cannot run. Record `rehearsal.choice`, the owner's name in `rehearsal.choiceBy`,
   and the `now.py` time in `rehearsal.choiceOn` and `decisions_log`. Record an alias or the
   literal `none` in `rehearsal.sandboxAlias` when offered. On later entries, reuse the saved
   choices. A skip takes TR-19 before any sandbox work. For rehearsal, a missing or stale alias,
   `none`, or an unavailable sf CLI path sets `rehearsal.capturePath` to `manual`.

   **sf CLI path.**

   For a chosen alias, say one plain line naming the action and alias **before every CLI action**,
   including reads, setup, load, result export, log retrieval, and cleanup. These action notices
   accompany the checklist-applied reply required below. Run
   `sf data query --target-org <alias> --query "SELECT Id, IsSandbox FROM Organization" --json`.
   Require exactly one row with `IsSandbox: true` and the org identifier matching the selected
   alias in `sf org list`. Record its Id in `rehearsal.sandboxOrgId`. On false, missing, or
   inconsistent evidence, refuse every write, say "<alias> is not verified as a sandbox; use the
   manual rehearsal", set `rehearsal.capturePath` to `manual`, and select the manual path.

   When the mapping matches, follow `references/sf-cli-rehearsal.md`.

   **Manual path.** For a successful local slice, give the same
   `work/rehearsal/batch.csv` to the customer to load. The customer
   applies the ratified checklist in the full-copy sandbox and loads that file with the ratified
   parameters. For a query-defined load without a source file, the customer loads at most
   `rehearsal_batch_rows` rows of its query result.
   In Setup, Debug Logs, set a trace flag for the load user and set the DebugLevel values to
   `ApexCode=FINE`, `ApexProfiling=FINE`, `Callout=INFO`, `Database=INFO`, `System=INFO`,
   `Validation=FINE`, `Visualforce=INFO`, and `Workflow=FINE`; it
   lasts at most 24 hours. Download logs from Setup, Debug Logs or with `sf apex get log`. If a log
   downloaded immediately after the load is empty, check its size and download it again. Keep the
   success and error CSV files from the same load job. Data Loader writes both files. When no rows failed, a header-only error file is accepted. A single debug
   log truncates at 20 megabytes (MB); recapture a truncated log with a smaller batch. The
   customer hands over logs, the success file, and the error file from that same job. For a local
   source, the batch file is the loaded file. Completeness
   depends on this handoff; when filenames carry job identifiers, the local script rejects
   differing ids.
   In a chat app with no local path to the source, rehearsal files (loader success and error files,
   debug logs) belong in Claude Code or Codex CLI.
3. **Hold the privacy gate.** Run the local scripts without opening a log or error file in model
   context. Only automation names, types, fire counts, completeness, and aggregate error counts
   cross that boundary.
4. From the engagement directory run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rehearsal_fired.py" <local-debug-log> [more logs] --success-file <success.csv> [more success files] --error-file <error.csv> [more error files] --rows-loaded <count from the loaded batch file> --out work/rehearsal/observed.json`

   For the sf CLI path, use the slice output's `rows` value as the loaded count. For a manual
   load from a local source, count the actual loaded batch with
   `load_input_prep.py count --file <loaded-batch-path>`. For a query-defined load without
   a source file, use success rows plus failed rows as the loaded count and state
   "row completeness not independently checked" as a risk in the rehearsal result and final report.

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rehearsal_reconcile.py" --checklist work/package/checklist.csv --parameters work/package/parameters.json --observed work/rehearsal/observed.json --out work/rehearsal/reconciliation.csv --summary-out work/rehearsal/summary.json [--accepted-lock-errors <rehearsal.lockErrorsAccepted>]`

   Record `rehearsal.successFiles`, `rehearsal.errorFiles`, `rehearsal.rowsLoaded`,
   `observedFile`, `reconciliationFile`, `summaryFile`,
   `controlFailures`, `informationalNotObserved`, `measuredIncidentClasses`,
   `duplicatesDetected`, and `lockErrors`. Pass `--accepted-lock-errors` only when the owner accepted a persistent count
   at card 05. Keep `rehearsal.unpredicted` as the running union of prior names and types;
   the current summary's `unpredicted` lists this round only. A leave-on automation absent from this batch is informational.
   State the verified sandbox by its alias and org name for the sf CLI path; for manual evidence, by the org name carried in the customer's files. Refer to result files by role (the success file, the error file), never by file name.
   Manual-file identity does not block the run. In the rehearsal result and
   `report/final-report.md`, state once: "The rehearsal ran as sf CLI user <username>, not the
   production load user; production-user sharing and user-specific bypass were not exercised."
   Include this line only for the sf CLI path.
5. Read `work/rehearsal/summary.json` and route from its computed fields. Present its
   `measuredIncidentClasses` lines, the duplicate count beside active rule names, and each
   `not measurable` line in the acceptance question.
   Lock controls rest on the analysis: a zero `UNABLE_TO_LOCK_ROW` count in a small batch does not prove them.
   Present the highest usage and ceiling for each governor limit and namespace.
   Present evidence completeness. Run the lock ladder only when `lock_errors`
   is the sole blocker:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" --apply-lock-ladder --checklist work/package/checklist.csv --parameters work/package/parameters.json --lock-errors <rehearsal.lockErrors> --parameters-out work/package/parameters.json`

   Exit 0 applies rung 1 or 2. Read its rung and the new `parameterChanges` entries, record the
   rung, count, changed parameters, and `changedOn` in `rehearsal.ladderChanges` and
   `decisions_log` with author `lock ladder`, and clear `rehearsal.lockErrorsAccepted`. The customer
   applies the changed parameter and reruns the test batch. Exit 2 means serial mode already ran or
   is unavailable in the chosen loader; TR-22 sends the measured count to card 05 as a known risk.
   The owner can accept that count in either case when the five lock parameters are unchanged from
   the prior finalized values. On passing evidence, present each
   ladder change in one line with its test-batch result and ask the owner to accept the whole
   rehearsal, including those changes. Record the accepting person's name and date and time in
   `rehearsal.acceptedBy`, `rehearsal.acceptedOn`, and `decisions_log`.

## Outcomes, in precedence order

The first condition that holds wins.

- **TR-19 — the owner chose to skip the rehearsal.**
  Write `{"current_state": "rehearsal-closed", "current_step": "steps/07-deliver-backlog.md"}`. Next card: `steps/07-deliver-backlog.md`.
- **TR-20 — `summary.json` has no blockers and the owner accepts every ladder change, not-measurable line, and the result.**
  Write `{"current_state": "rehearsal-closed", "current_step": "steps/07-deliver-backlog.md"}`. Next card: `steps/07-deliver-backlog.md`.
- **TR-21 — `summary.json` has `evidenceComplete: false`.** Record the gap in
  `open_items`, write `{"current_state": "package-ratified", "current_step": "steps/06-rehearse.md"}`. Next card: `steps/06-rehearse.md`. Recapture the evidence.
- **TR-22 — `blockers` includes `control_failure` or `measured_incident_class`, the lock ladder exits 2, or the owner declines the rehearsal result.** Keep the failure evidence,
  write `{"current_state": "bypass-audited", "current_step": "steps/05-ratify-safety-package.md"}`. Next card: `steps/05-ratify-safety-package.md`. Revisit the controls, let the owner declare no-go, or have the owner rule on the persistent lock count. Card 03 is not rerun.
- **TR-23 — `blockers` contains only `lock_errors` and the lock ladder exits 0.** Keep `package-ratified`,
  write `{"current_state": "package-ratified", "current_step": "steps/06-rehearse.md"}`. Next card: `steps/06-rehearse.md`. Rerun the test batch with the changed finalized parameter. No owner exchange occurs here.
- **TR-24 — `blockers` includes `unpredicted_automation`.** Merge these
  reconciliation rows into `work/rehearsal/unpredicted.json` by name and type, preserving entries
  from earlier rounds. Set `rehearsal.unpredicted` to that same running union and write
  `{"current_state": "impact-analyzed", "current_step": "steps/04-audit-bypass.md"}`. Next card: `steps/04-audit-bypass.md`.
  Card 03 is not rerun.

- **TR-25 — Otherwise.** `{"current_state": "package-ratified", "current_step": "steps/06-rehearse.md"}`. Next card: `steps/06-rehearse.md`. Record the default call in `decisions_log` and tell the user. The default never accepts a result for the owner.

## Stop rule

After TR-19, dispatch card 07 in the same turn. Stop on a question to the owner, a self-loop, or a terminal state.

## Failure

An unreadable success or error file takes TR-21. On another local script error or an owner answer still pending, record the aggregate-safe gap in `open_items` and take TR-25, the default self-loop on `package-ratified`. The default never accepts a result for the owner.
