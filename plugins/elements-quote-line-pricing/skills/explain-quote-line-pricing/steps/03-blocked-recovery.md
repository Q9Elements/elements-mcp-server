# 03 Blocked recovery

State: `blocked`

## Purpose

Help the right person restore the evidence needed to explain the quote line.

## Procedure

On entry from card 01, do steps 1 and 2 and stop. On the user's next message, evaluate the outcomes.

1. Read `blocked.reason`, `blocked.evidence` and `blocked.owner`, and the matching row in `data/blocked-reasons.csv`. Restate the issue, owner and recovery step in business language.
2. **Human moment, owner named in the row:** wait for the user to report recovery.

## Outcomes, in precedence order

The first that holds wins.

- **TR-14: The user says they are finished.** Write `{"current_state": "engagement-closed", "current_step": null}`. Terminal: report the distinct quote lines with saved-answer entries in `decisions_log`, then stop.
- **TR-15: The user reports the blocker addressed, switches route, or names another quote line.** For a route switch, set `slots.route` from the message; set `slots.org_alias` from the message, or to null when the message gives none or the route is `hosted-mcp`. For another line, set `slots.quote_line_ref` from the message. Clear `slots.quote_line_id` and all `diagnostics` fields so card 01 gathers fresh evidence after recovery, keeping the earlier evidence directory on disk. Record the `blocked` values and the reported recovery in `decisions_log`, then set `blocked.reason`, `blocked.owner` and `blocked.evidence` to null. Write `{"current_state": "kickoff", "current_step": "steps/01-build-diagnostics.md"}`. Next card: `steps/01-build-diagnostics.md` in the same turn.
- **TR-16: Otherwise.** Restate the blocker. Write `{"current_state": "blocked", "current_step": "steps/03-blocked-recovery.md"}`. Next card: `steps/03-blocked-recovery.md`. Record the default call and evidence in `decisions_log`, tell the user, and stop.

## Failure

If `blocked.reason` has no row in `data/blocked-reasons.csv`, re-check the reason and tell the user the state file does not match this playbook. Record the mismatch in `open_items` and stay on `blocked` until it is resolved.
