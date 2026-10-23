# 01 Check prerequisites

State: `ready`

## Purpose

Establish the minimum requirements for candidate computation: both customer inputs (the Setup Apex
Classes banner and the capacity target) are in hand, the required tools resolve, Event Monitoring is
on, the model exists, the candidate tool confirms sync readiness, and the bundle host is reachable.
Card 02 establishes telemetry sufficiency from the bundle's held calendar-day span.

## Procedure

1. **Inputs gate.** Both customer inputs must be in the conversation before anything else runs: the
   text or screenshot of the banner in **Setup > Apex Classes** (`data/capabilities.csv` CAP-05) shown
   in `references/evidence-acquisition.md`, and how much Apex capacity the customer wants back: a percentage of the allocation
   to free, a target usage percentage, or a number of characters. Ask once for any missing input and stop.
   Parse the banner into `capacity.displayedPercent`, `capacity.allocation`, and `capacity.readAt`,
   the banner read time as an International Organization for Standardization (ISO) 8601 timestamp
   in Coordinated Universal Time (UTC), ending in
   `Z`, such as `2026-01-15T09:30:00Z`. When the banner supplies the exact current count, also record
   `capacity.charactersUsed`; omit that optional integer when it is unknown. The limit interprets the percentage, and the used
   figure, when present, confirms the
   counted-character total. Card 02 reconciles the used figure against the counted total; a
   deployment between the banner reading and the bundle appears there as a residual. Record
   `capacity.target` as `{ wording, kind, value, requiredCharacters, alreadyAtTarget }`. The `kind` is
   `free_percent`, `target_percent`, or `characters`. Calculate the exact target:
   `ceil(allocation * value / 100)` for `free_percent`;
   `charactersUsed - floor(allocation * value / 100)` for `target_percent`; and `value`
   for `characters`. A target usage requires the exact current count. When the kind is
   `target_percent` and the banner does not show the exact count, ask the customer once to restate the
   target as a percentage to free or a number of characters, and record the restated target. When the target usage is already met, set `requiredCharacters` to zero and
   `alreadyAtTarget` to true; the engagement still runs. On a restart from card 06, the confirmation, target, and capacity figures
   already in `execution-state.json` satisfy the gate.
2. **Slots and tool surface.** The Elements Model Context Protocol (MCP) tools must resolve and be
   authenticated, with `list_reference_models` and `get_dependencies` available; if Elements does not
   resolve at all, stop and say the playbook has not started. Both `get_unused_apex_candidates` and
   `has_event_monitoring` must resolve on the MCP server; if either is missing, outcome TR-01. Confirm
   that `python3` can run `scripts/removal_plan.py --help` from the plugin directory. Call
   `list_reference_models` with `delivery: "file"` and fill `slots.space_id` from `activeSpace.teamId`, `slots.model_id`
   from the selected `referenceModels[].refModelId`, and `slots.org_label` from its name.
   On `active_space_required`, call `get_space_context` and read `active`, `authorized`, and
   `pagination`. Follow every authorized-space page with `skip` and `pageSize` before treating the
   list as exhaustive. Use the resolved space, or ask for the intended space together with the model
   when ambiguous, then pass its `teamId` to `list_reference_models` and subsequent data calls.
   Listing tests feature flags across the grant; calls still check the selected space and reference
   model permissions. Follow `references/mcp-contract.md` for exact flag and permission refusals.
   When a feature refusal carries `hint`, call `get_space_context`, ask the customer which
   authorized space holds the production reference model, pass that space's `teamId`, and re-run
   this step. The retry can still be refused; record that refusal as returned. A refusal without
   `hint` records the missing flag and its owner.
   Hydrate whole-result files before reading these arrays under `references/orchestration.md`.
   `get_space_context.active` describes the session; passing it `teamId` does not validate a data-call
   override. If exactly one model is visible, take it and say so; otherwise ask which model to use,
   the one question allowed after the inputs gate. Slots are never written back into this package.
3. **Telemetry probe.** Call `has_event_monitoring` with `refModelId: slots.model_id` and
   `teamId: slots.space_id`. Record `hasEventMonitoring`, `daysAvailable`, `oldestLogDate`, and
   `newestLogDate` in `telemetryProbe` and in `decisions_log` as "telemetry probe". The probe checks
   whether daily Apex event logs exist for the org and reports their window using the oldest and newest
   log dates and days available. Feature and access refusals leave this check incomplete; they do
   not establish `hasEventMonitoring: false`. Event Monitoring
   is on when `hasEventMonitoring` is true and `daysAvailable` meets `data/thresholds.csv` T-13 (one
   distinct daily log date). One returned daily log date means the Event Monitoring add-on is on. A false
   probe means no daily Apex log date was found in the 30-day lookback. The add-on may be missing, or
   the org's daily logs may have stopped. Tell the customer both readings and quote the probe's
   `reason`. Below that threshold, use outcome TR-02.
4. **Version, model, and sync.** Confirm that `engagement.playbook_version` equals this package's
   `plugin.json` version. On resume, stop on a mismatch, state both versions, and ask how to proceed.
   Confirm from the `list_reference_models` response that `slots.model_id` exists. Record its
   `status` as returned in `decisions_log`, labeled as model status. `createdAt` and `updatedAt`
   are model dates. Verify sync readiness with `get_unused_apex_candidates`, using card 02 step 1's
   request arguments and polling rules. A complete response disqualified for `SYNC_INCOMPLETE`
   uses TR-03. Any other complete response passes this sync check; card 02 handles its bundle or
   other disqualification. Record the response status, disqualification, and reason as sync-check
   evidence in `decisions_log`. Card 02 repeats the identical request to obtain the bundle and a
   fresh download link. A failed or unfinished check follows this card's Failure rule.
5. **Bundle host reachability.** The instance is the Elements host that the MCP connector points at.
   Select its bundle host from `references/evidence-acquisition.md`. From the environment that will
   download the bundle, run:

   `curl -sS -o /dev/null --max-time 10 -w '%{http_code}' https://<host>/`

   Any Hypertext Transfer Protocol (HTTP) status means the host is reachable; Amazon Web Services
   (AWS) Simple Storage Service (S3) returns 403 to an unsigned request. Curl exit 6, 7, or 28 blocks
   the check because of Domain Name System (DNS) failure, connection refused, or timeout. Print the
   exact host the customer's IT team must allow, record it in `open_items`, stay on `ready`, and stop
   until the same probe passes. For an instance not listed in the table, ask Elements support for its
   bundle host.
6. **Unused window** (`data/thresholds.csv` T-11 and T-12). The window is 90 calendar days in
   Coordinated Universal Time (UTC), ending yesterday because today's daily file does not exist yet.
   A class is unused when it has not run directly, or through anything that ran, in that window. The
   window is cut to the telemetry Elements holds, and card 02 states the requested and effective
   figures.

## Outcomes, in precedence order

The first that holds wins.

- **TR-01 — `get_unused_apex_candidates` or `has_event_monitoring` does not resolve.** Record
  `blocked.reason: "MISSING_PRIMITIVE"`, `blocked.evidence` naming the missing tool or tools,
  `blocked.owner` as the person filling the owner role in `data/blocked-reasons.csv`, and
  `blocked.entered_from: "ready"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-02 — the probe returned `hasEventMonitoring: false` or `daysAvailable` below T-13.** Record
  `blocked.reason: "NO_APEX_TELEMETRY"`, `blocked.evidence` as the probe response, `blocked.owner` per
  `data/blocked-reasons.csv`, and `blocked.entered_from: "ready"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-03 — `get_unused_apex_candidates` returned `status: "complete", disqualified: true` with
  reason `SYNC_INCOMPLETE` during the prerequisite checks.** Record
  `blocked.reason: "SYNC_INCOMPLETE"`, `blocked.evidence` as the tool response, `blocked.owner` per
  `data/blocked-reasons.csv`, and `blocked.entered_from: "ready"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-04 — every check above passed.** Record "prerequisites confirmed" in `decisions_log` with the
  capacity figures, capacity target, model status, sync-check evidence, probe figures, and 90-day window. Write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-obtain-candidates.md"}`.
  Next card: `steps/02-obtain-candidates.md` in the same turn.

## Stop rule

Stop only when a required input is missing, bundle-host reachability fails, or an outcome blocks the
engagement. TR-04 dispatches card 02 in the same turn.

## Failure

If a check cannot be completed, stay on `ready`, record what is missing in `open_items`, and tell the
user what completes the check. Apply `references/orchestration.md` for retryable refusals and
terminal failed jobs. Only a tool that does not resolve is TR-01.
