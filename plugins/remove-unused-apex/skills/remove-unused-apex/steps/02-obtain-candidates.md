# 02 Obtain the candidate set

State: `prerequisites-confirmed`

## Purpose

Obtain the complete candidate bundle, persist the orchestration inputs, reconcile the measured window,
and present the script-rendered headline. The estate stays in the bundle; the conversation receives
only the evidence summary and named blind spots.

## Procedure

1. **Call the tool and preserve its envelope** (`data/capabilities.csv` CAP-01). Call
   `get_unused_apex_candidates` with `refModelId: slots.model_id`, `teamId: slots.space_id`,
   `staleAfterDays: 90`, the method constant in `data/thresholds.csv` T-11, and
   `capacity: { allocation, displayedPercent, readAt }` from card 01, adding `charactersUsed` only
   when the exact optional integer is known, and
   `stringSearch: false`.
   - `status: "computing"`: re-call with identical arguments at the interval and up to the cap in
     `data/thresholds.csv` T-7; tell the user it is computing.
   - `status: "disqualified"`: use outcome TR-05, TR-06, TR-19, or TR-20.
   - `status: "complete"`: write the complete response, excluding `bundleUrl`, to
     `work/bundle/envelope.json`. Fetch `bundleUrl` into `work/bundle/` immediately, verify
     its 256-bit Secure Hash Algorithm (SHA-256) `bundleSha256`, and record `bundle.sha256`, `bundle.computedAt`, `bundle.directory`, and
     `bundle.summary`. The uniform resource locator (URL) lives only T-9; re-call the tool for a fresh
     URL if the fetch fails, and
     never persist the URL. The `bundleUrl` host is authoritative for the bundle download.
2. **Reconcile the window.** From `work/bundle/telemetry-ledger.json`, record
   `bundle.windowStart`, `bundle.windowEnd`, `bundle.requestedDays`, `bundle.effectiveDays`,
   `bundle.interval`, `bundle.typesAbsent`, and each event type's `daysProcessed` in
   `bundle.eventTypes`. Compare `bundle.effectiveDays` with
   `telemetryProbe.daysAvailable`. When the effective window is shorter, record an ingestion anomaly
   with both figures in `open_items`; do not pause. State the requested and effective windows in plain
   terms, such as "asked 90, watched 31." This ledger confirms windows longer than the probe's 30-day
   lookback and refreshes the per-type telemetry days. Days inside the span with no data or a dropped
   file appear per type as `missingDays` and do not shorten the span.
   Read `work/bundle/catalog.csv`. Apex execution telemetry is required: take TR-05 if `ApexExecution`
   appears in `bundle.typesAbsent`, is absent from `bundle.eventTypes`, or has `daysProcessed` equal to
   zero. Apex trigger telemetry is required when `catalog.csv` contains at least one row with
   `kind=trigger` and `isManagedPackage=false`; in that case, take TR-05 if `ApexTrigger` appears in
   `bundle.typesAbsent`, is absent from `bundle.eventTypes`, or has `daysProcessed` equal to zero.
   Check these conditions before writing the capacity input or reporting candidates.
3. **Write the capacity input.** Copy `work/bundle/catalog-summary.json` to
   `work/bundle/catalog-summary.with-capacity.json` and add `capacity.readAt` from card 01 as
   `readAt`. The tool already writes `allocation`, `displayedPercent`, `charactersUsed`, `bandLow`,
   `bandHigh`, `reconciled`, `residual`, and `calibration`; copy them unchanged. Record `capacity.countedTotal`,
   `capacity.reconciled`, `capacity.residual`, and `capacity.anomalies` from that file. If reconciliation
   is false, diagnose the direction and size once and record it in `open_items`; do not smooth the
   result. Record every counted row with an empty `lengthWithoutComments` in `open_items`. Label all
   later capacity figures unreconciled while either condition remains.
4. **Select every package needed for the target.** Read `candidateCapacity` from
   `work/bundle/catalog-summary.json`; do not
   load `candidates.csv` or `components.json` into the conversation. The minimum held span is
   `data/thresholds.csv` T-12; an effective window below it uses TR-15 before any candidate list is
   reported. Run exactly:

   `python3 <plugin>/scripts/capacity_triage.py --engagement <dir>`

   Record the paths and counts from `work/triage/summary.json` in `triage`, including selected,
   deferred, found-in-use, kept-use-unknown, unknown-length, confirmed characters, selected characters, shortfall,
   `stringSearch`, and outcome. The initial `stringSearch` value is `not_run`. The script reads
   and sorts the complete local files; the conversation receives only the compact summaries.
   A package contains the target class, its candidate Apex callers and non-test candidate Apex string
   holders recursively, every member of its
   strongly connected component, and every candidate reached through a test of any member, with those
   expansions repeated to a fixed point, plus tests attached by the planner's shared rule.
   A non-test Apex caller or string holder that is in use makes the package `in-use`. A non-Apex string
   holder or Flow reference whose use Elements cannot see makes the package `kept-use-unknown`.
   Packages with unknown counted characters stay `unknown-length`. Only `selected` packages contribute
   to the capacity target.
   Selection continues in deterministic rank order until the exact target is covered or eligible
   candidates are exhausted. The outcome is `target_covered`, `candidates_exhausted`, or
   `already_at_target`.
5. **Render and report.** Run exactly:

   `python3 <plugin>/scripts/candidates_report.py --engagement <dir>`

   The renderer writes `report/02-candidates.md` from the bundle. Fill its
   `<!-- prose: ... -->` slots without recomputing any count. Tell the user only the state line, the
   required characters, total candidate count, the ten largest components by characters from
   `candidateCapacity`, every blind spot in one paragraph, and what runs next. When triage selects a
   package, card 03 runs the selected-class string check next. When triage selects no package, no
   string check runs and the report says so.

## Outcomes, in precedence order

The first that holds wins.

- **TR-05 — `disqualified` with reason `NO_APEX_TELEMETRY`, or a complete bundle whose ledger lacks
  `ApexExecution` telemetry or has zero `daysProcessed` for it, or lacks `ApexTrigger` telemetry or has
  zero `daysProcessed` for it when `catalog.csv` contains a row with `kind=trigger` and
  `isManagedPackage=false`.** Record
  `blocked.reason: "NO_APEX_TELEMETRY"`, `blocked.evidence` naming the missing or zero-day event
  type(s) together with the ledger's event-type summary, `blocked.owner` per
  `data/blocked-reasons.csv`, and
  `blocked.entered_from: "prerequisites-confirmed"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-06 — `disqualified` with reason `SYNC_INCOMPLETE`.** Record
  `blocked.reason: "SYNC_INCOMPLETE"`, `blocked.evidence` as the tool's message, `blocked.owner` per
  `data/blocked-reasons.csv`, and `blocked.entered_from: "prerequisites-confirmed"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-19 — `disqualified` with reason `INGEST_PENDING`.** Tell the customer: "Elements has not
  ingested this org's telemetry yet; the daily pull runs at 15:00 Coordinated Universal Time (UTC). Resume after it." Record
  `blocked.reason: "INGEST_PENDING"`, the tool response in `blocked.evidence`, `blocked.owner` per
  `data/blocked-reasons.csv`, and `blocked.entered_from: "prerequisites-confirmed"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md` in the same turn.
- **TR-20 — `disqualified` with reason `TELEMETRY_NOT_COLLECTED`.** Tell the customer: "Elements is
  not collecting the Event Monitoring data. The Unused Apex playbook only works with production
  orgs. If this is a production org, ask your Elements administrator to confirm that Event Monitoring
  is licensed for the Elements Space." Record `blocked.reason: "TELEMETRY_NOT_COLLECTED"`, the tool
  response in `blocked.evidence`, `blocked.owner` per `data/blocked-reasons.csv`, and
  `blocked.entered_from: "prerequisites-confirmed"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md` in the same turn.
- **TR-15 — the bundle is complete and the held telemetry is below T-12 (`bundle.effectiveDays` below 29 held days).** Record
  `blocked.reason: "INSUFFICIENT_TELEMETRY"`; `blocked.evidence` with `requestedDays`,
  `effectiveDays`, `windowStart`, `windowEnd`, and the date T-12 is reached, calculated as
  `windowStart` plus 29 days (the day whose daily ingest holds the twenty-ninth held day); `blocked.owner`
  per `data/blocked-reasons.csv`; and
  `blocked.entered_from: "prerequisites-confirmed"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md` in the same turn.
- **TR-07 — the bundle is complete and `summary.candidates.total` is zero.** Write
  `report/final-report.md` from the renderer output, stating that the evidence supports no removals in
  this window and listing every blind spot. Record "no candidates, engagement closed" in
  `decisions_log`. Write `{"current_state": "removal-planned", "current_step": null}`. Terminal.
- **TR-21 — the bundle is complete, `summary.candidates.total` is greater than zero, and triage
  selected no package (`triage.selectedPackages` is zero).** Write `report/final-report.md` from the
  candidate renderer output with a section for each applicable cause, using counts in
  `work/triage/summary.json`:
  - `already_at_target`: the org meets the capacity target.
  - `unknown-length`: Elements holds no `lengthWithoutComments` for these classes, so the playbook
    cannot show their reclaim. List their qualified names from the `unknown-length` rows of
    `work/triage/deferred.csv`. The Elements space administrator owns the missing class lengths;
    a new engagement can run after a completed sync carries them.
  - `inUse` and `keptUseUnknown`: name each package and its reason from
    `work/triage/packages.json`.
  List every reportable blind spot. Tell the customer that candidates exist but none can be selected,
  with each cause and count. Record "candidates obtained, none selectable, engagement closed" in
  `decisions_log` with the counts. Write
  `{"current_state": "removal-planned", "current_step": null}`. Terminal.
- **TR-08 — the bundle is complete, `summary.candidates.total` is greater than zero, and triage
  selected at least one package.** Record "candidate
  set obtained" in `decisions_log` with `computedAt`, counts, and capacity reconciliation. Write
  `{"current_state": "candidates-obtained", "current_step": "steps/03-reason-candidates.md"}` and
  dispatch `steps/03-reason-candidates.md` in the same turn.

## Stop rule

Do not stop after card 02. Dispatch the written next card in the same turn. A terminal TR-07 or TR-21 ends the
engagement, while TR-05, TR-06, TR-15, TR-19, and TR-20 dispatch the blocked card. TR-15 stops the
procedure before capacity triage.

## Failure

If the tool returns `status: "error"`, polling exceeds T-7, the checksum differs, or the tool stops
resolving, stay on `prerequisites-confirmed`, record the evidence in `open_items`, and tell the user
what is needed. Never use a partial bundle.
