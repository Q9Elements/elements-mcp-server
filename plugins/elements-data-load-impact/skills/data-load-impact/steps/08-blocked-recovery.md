# 08 Recover a blocked engagement

State: `blocked`

## Purpose

Keep a named blocker, its owner, and its evidence explicit until the exact failed condition is proven
resolved.

## Procedure

1. Read `blocked.reason`, `blocked.owner`, `blocked.entered_from`, and `blocked.evidence`. Restate what
   is unmet, who owns it, and which card entered the block. The reason must be
   `MISSING_PRIMITIVE` or `SYNC_INCOMPLETE` from `data/blocked-reasons.csv`.
2. Wait for the named owner to report a fix, then verify that exact condition:

   - For `MISSING_PRIMITIVE`, confirm every required tool in card 01 resolves and authenticates.
   - For `SYNC_INCOMPLETE`, repeat the card 02 baseline `run_data_load_impact` call for the first
     `manifest.targets` entry, using the same arguments, `refModelId`, and `teamId` from
     `slots.model_id` and `slots.space_id`. A `running` or `complete` reply proves the sync. A
     `model_not_synced` refusal or `model_resynced` failure leaves the condition unresolved.

3. When verified, append the reason, evidence, who established the fix, and date and time to
   `decisions_log`; reset every `blocked` field to null. Do not reuse analysis evidence after recovery.

## Outcomes

- **TR-28 — the condition named in `blocked.reason` is verified resolved.** Write
  `{"current_state": "ready", "current_step": "steps/01-check-prerequisites.md"}`. Next card:
  `steps/01-check-prerequisites.md`.

- **TR-29 — Otherwise.** `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. Record the default call in `decisions_log` and tell the user. The report restates what is unmet and who owns it; keep the reason and owner unchanged.

## Stop rule

After TR-28, dispatch card 01 in the same turn. Stop on TR-29.

## Failure

If the reported fix does not resolve the recorded condition, append the new evidence to `blocked.evidence` and take TR-29, the default self-loop on `blocked`. Never change the reason while blocked and never invent a third blocked reason.
