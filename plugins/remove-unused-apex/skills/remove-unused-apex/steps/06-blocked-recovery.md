# 06 Blocked

State: `blocked`

## Purpose

The engagement is stopped on a named blocker with a named owner. Being blocked is a place the
engagement can stand, with defined ways back, rather than an error. The only reasons that lead here are
those in `data/blocked-reasons.csv`.

## Procedure

1. Read `blocked.reason`, `blocked.evidence`, `blocked.owner`, and `blocked.entered_from` and restate
   them to the user plainly: what is unmet, who can establish it, which card sent the engagement here.
2. The engagement waits on the owner. When the user reports the blocker addressed, verify the matching
   condition before recovering. For `NO_APEX_TELEMETRY`, a fresh `has_event_monitoring` probe must
   return `hasEventMonitoring: true` with `daysAvailable` at or above T-13. When the engagement
   restarts, card 02 re-checks the ledger's `ApexExecution` and `ApexTrigger` telemetry. For
   `INSUFFICIENT_TELEMETRY`, today must be on or after the date recorded in `blocked.evidence`; card 01
   restarts the checks and card 02 recomputes the held telemetry span. Use `list_reference_models` for
   sync status and tool resolution for a missing primitive. `INGEST_PENDING` recovers once a 15:00
   Coordinated Universal Time (UTC) run has passed since the block, then restarts card 02.
   `TELEMETRY_NOT_COLLECTED`
   recovers when the Elements space administrator confirms the space's plan, its Event Monitoring
   sync setting, and that the selected reference model is the production org. Recovery always
   verifies the recorded blocker.
3. On recovery, clear the `blocked` record into `decisions_log` (what was established, by whom, when)
   and reset `blocked` to nulls.

## Outcomes

`INGEST_PENDING` resumes card 02 because the prerequisite evidence is already valid. Every other
recovery restarts card 01 so sync status, capacity figures, and telemetry days are captured together.
Preserve `capacity.target` as the customer's engagement intent. Invalidate bundle-dependent
triage, feasibility, and review scope. The reviewed dispositions stay on disk under `work/review/` for
reference but are not reused against a refreshed bundle because the candidate set can change.

- **TR-13 — the blocking condition named in `blocked.reason` is verified resolved** (`NO_APEX_TELEMETRY`:
  a fresh `has_event_monitoring` probe returns `hasEventMonitoring: true` with `daysAvailable` at or
  above T-13; card 02 re-checks the ledger's `ApexExecution` and `ApexTrigger` telemetry when the
  engagement restarts; `SYNC_INCOMPLETE`:
  `list_reference_models` reports the sync complete; `MISSING_PRIMITIVE`: both required tools resolve;
  `INSUFFICIENT_TELEMETRY`: today is on or after the date recorded in `blocked.evidence`;
  `INGEST_PENDING`: a 15:00 UTC run has passed since the block;
  `TELEMETRY_NOT_COLLECTED`: the Elements space administrator confirms the space's plan and Event
  Monitoring sync setting and that the model is the production org). For `INGEST_PENDING`, write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-obtain-candidates.md"}`
  and dispatch `steps/02-obtain-candidates.md`. For every other reason, write
  `{"current_state": "ready", "current_step": "steps/01-check-prerequisites.md"}` so the
  prerequisite checks re-run in full, then dispatch `steps/01-check-prerequisites.md`.

## Stop rule

Do not stop after recovery. Dispatch the written next card in the same turn. Stay on card 06 only
while the recorded blocker remains unresolved.

## Failure

If the reported fix does not match the recorded reason, or re-running the failed check fails again, the
engagement stays `blocked` with the new evidence appended to `blocked.evidence`; `blocked.reason` is
never changed while blocked. There is no other exit from this state; a blocker that cannot be established
ends the engagement by the owner's explicit decision, recorded in `decisions_log`, not by a transition.
