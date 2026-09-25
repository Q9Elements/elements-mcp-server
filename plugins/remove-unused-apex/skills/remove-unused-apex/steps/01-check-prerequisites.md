# 01 Check prerequisites

State: `ready`

## Purpose

Establish the minimum requirements for candidate computation: both customer inputs (the Setup Apex
Classes banner and the capacity target) are in hand, the required tools resolve, Event Monitoring is on, the sync is complete, and the bundle host is
reachable. Card 02 establishes telemetry sufficiency from the bundle's held calendar-day span.

## Procedure

1. **Inputs gate.** Both customer inputs must be in the conversation before anything else runs: the
   text or screenshot of the banner in **Setup > Apex Classes** (`data/capabilities.csv` CAP-05) shown
   in `references/evidence-acquisition.md`, and how much Apex capacity the customer wants back: a percentage of the allocation
   to free, a target usage percentage, or a number of characters. Ask once for any missing input and stop.
   Parse the banner into `capacity.displayedPercent`, `capacity.allocation`, and `capacity.readAt`,
   the time the banner was read. When the banner supplies the exact current count, also record
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
   `list_reference_models` and fill `slots.space_id`, `slots.model_id`, and `slots.org_label`. If
   exactly one model is visible, take it and say so; otherwise ask which model to use, the one
   question allowed after the inputs gate. Slots are never written back into this package.
3. **Telemetry probe.** Call `has_event_monitoring` with `refModelId: slots.model_id` and
   `teamId: slots.space_id`. Record `hasEventMonitoring`, `daysAvailable`, `oldestLogDate`, and
   `newestLogDate` in `telemetryProbe` and in `decisions_log` as "telemetry probe". The probe checks
   whether daily Apex event logs exist for the org and reports their window using the oldest and newest
   log dates and days available. Event Monitoring
   is on when `hasEventMonitoring` is true and `daysAvailable` meets `data/thresholds.csv` T-13 (one
   distinct daily log date). One returned daily log date means the Event Monitoring add-on is on. A false
   probe means no daily Apex log date was found in the 30-day lookback. The add-on may be missing, or
   the org's daily logs may have stopped. Tell the customer both readings and quote the probe's
   `reason`. Below that threshold, use outcome TR-02.
4. **Version, model, and sync.** Confirm that `engagement.playbook_version` equals this package's
   `plugin.json` version. On resume, stop on a mismatch, state both versions, and ask how to proceed.
   Confirm from the `list_reference_models` response that `slots.model_id` exists and its last sync
   completed. Record `sync.timestamp` and `sync.status`. An in-progress, failed, partial, or unknown
   sync is outcome TR-03.
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
- **TR-03 — the sync is incomplete, failed, or its status cannot be established.** Record
  `blocked.reason: "SYNC_INCOMPLETE"`, `blocked.evidence` as the status text, `blocked.owner` per
  `data/blocked-reasons.csv`, and `blocked.entered_from: "ready"`. Write
  `{"current_state": "blocked", "current_step": "steps/06-blocked-recovery.md"}`. Next card:
  `steps/06-blocked-recovery.md`.
- **TR-04 — every check above passed.** Record "prerequisites confirmed" in `decisions_log` with the
  capacity figures, capacity target, sync timestamp, probe figures, and 90-day window. Write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-obtain-candidates.md"}`.
  Next card: `steps/02-obtain-candidates.md` in the same turn.

## Stop rule

Stop only when a required input is missing, bundle-host reachability fails, or an outcome blocks the
engagement. TR-04 dispatches card 02 in the same turn.

## Failure

If a check cannot be completed, stay on `ready`, record what is missing in `open_items`, and tell the
user what completes the check. Retry a tool that errors. Only a tool that does not resolve is TR-01.
