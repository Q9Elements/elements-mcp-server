# 08 Blocked recovery

State: `blocked`

## Purpose

Something stopped the run: a pull or search that cannot be completed, a reference model that syncs none of the integration metadata, an agent's file that still fails after its fix rounds, a fault in the playbook itself, or a drawing error. This card gets it unstuck and returns to where the run was.

## Procedure

1. Read `blocked.reason` and `blocked.entered_from`.
2. **An agent's file that still fails its check** (`entered_from` `scoped` or `automations-traced`, with `ERROR` lines as the reason): when `blocked.reason` repeats the `ERROR` lines of the last retry recorded in `decisions_log`, it is a fault in the playbook: report it as in step 3 (a) and take TR-21. Otherwise there is no question for the architect: record the retried `ERROR` lines in `decisions_log` (`what`: one more attempt after a block; `evidence`: the lines), and the cause counts as resolved for one more attempt with a fresh agent; take TR-20.
3. Before treating a block as a failed call:
   - (a) **A fault in the playbook** (any `entered_from`; `blocked.reason` holds a `SETUP` line or `validate.py` errors): tell the architect, in plain words, that the playbook itself failed, not their org or Elements, and ask them to report it to the playbook's maintainer with the lines in `blocked.reason`; take TR-21. When the architect says the playbook has been updated, record it in `decisions_log` as one more attempt after a block; the cause is resolved: take TR-20.
   - (b) **A drawing error** (`entered_from` `integrations-approved`; an error the drawing protocol does not resolve and card 07's step 4 does not list): when `decisions_log` already records a re-plan after the same error, treat it as (a). Otherwise move the work folder aside, `mv "$ENG/drawing/landscape" "$ENG/drawing/landscape-<n>"` with the next free number; when it holds `map.json`, add its map to `open_items` as a partial draft superseded by the new map, to delete in Elements. Record the re-plan in `decisions_log` with the error as evidence; the cause is resolved: take TR-20.
4. **A call that failed** (`entered_from` `scoped`, `systems-confirmed` or `integrations-approved`): call it once more with the same arguments. When it answers, the cause is resolved; take TR-20. When it fails again, tell the architect, in plain words, what stopped the run and what would resolve it: the Elements connection, access to the space or the reference model, leaving edit mode in Elements.
5. **Nothing to work from** (`NOT SYNCED`): tell the architect, in plain words, and that a landscape needs the integration metadata synced in Elements. When the architect says the metadata is now synced, remove the `notSynced` entries from `evidence/pulls.json`; the cause is resolved: take TR-20. A different reference model is a new landscape: a new engagement directory from card 01.

## Outcomes, in precedence order

The first that holds wins.

- **TR-20 — The cause is resolved.** Write `current_state` as `blocked.entered_from` and `current_step` as the card the dispatch table gives for it, as one edit, and clear `blocked`. Next card: that card.
- **TR-21 — Otherwise.** `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. The run waits here. Record the default call in `decisions_log` and tell the architect.

## Failure

When `blocked.entered_from` is empty or names no state of the dispatch table, resume from `scoped`: card 02 keeps every pull already recorded and card 03 applies the architect's earlier corrections again, so only what is missing is redone. Tell the architect.
