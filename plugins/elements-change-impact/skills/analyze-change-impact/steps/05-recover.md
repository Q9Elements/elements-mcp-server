# 05 Recover

State: `blocked`

## Purpose

Retry one transient required read, then deliver held evidence with the missing part explained.

## Procedure

1. Match `blocked.reason` to `data/blocked-causes.csv`; the first matching row in file order wins. Preserve the entered state and card. A transient cause gets one automatic retry; a permanent cause gets none. Do not ask the runner to choose between retry and delivery.
2. When a transient retry is due, set `blocked.retried=true` before returning to the entered card. That card reruns its required read with the original arguments. On success, clear `blocked` there and continue; on failure, return here preserving `blocked.retried=true`.
3. When no automatic retry remains, set `incomplete={reason,entered_from}` using the original state. Card 04 writes the report and a "not drafted" backlog with the row's customer text and fix. A later "retry" reply follows card 01 TR-03.

## Outcomes, in precedence order

- **TR-17 — The cause is transient and `blocked.retried` is false.** Set `blocked.retried=true` and write `{"current_state":"<blocked.entered_from>","current_step":"<blocked.entered_step>"}` in one edit. Next card: `blocked.entered_step`.
- **TR-18 — Otherwise.** Set `incomplete={"reason":"<blocked.reason>","entered_from":"<blocked.entered_from>"}` and write `{"current_state":"impact-traced","current_step":"steps/04-deliver.md"}` in one edit. Next card: `steps/04-deliver.md`. Record the default call in `decisions_log` and tell the runner.

## Failure

If `blocked.reason` has no table row or `entered_from` has no dispatch card, record the inconsistency in `open_items` and keep this state until corrected. Never invent a recovery route.
