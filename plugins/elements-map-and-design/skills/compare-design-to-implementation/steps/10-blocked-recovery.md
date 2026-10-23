# 10 Blocked recovery

State: `blocked`

## Purpose

A write to the map was refused: someone has a level open in edit mode, the analyst may not edit the map, or Elements refused the change for another reason. This card waits for the cause to clear and returns to where the run was.

## Procedure

1. Read `blocked.reason` and `blocked.entered_from`, and tell the analyst, in plain words, what stopped the run and what clears it: closing edit mode on that level in Elements (the outline's `lock` names who has it), the edit role on the map, or the edit role on the reference model.
2. Check: call `get_process_map_outline` with `slots.map_id` and look at the `lock` of the levels in scope; call `list_process_maps` with the map's name and look at `canEdit`. A lock or permission cause is cleared when no level in scope is locked and `canEdit` is true, or the analyst says it is cleared. Any other refusal: show the analyst Elements' message in plain words and add it to `open_items`; it is cleared only when the analyst says it is (after changing the level, or asking the Elements team), since running the same write again gives the same answer.
3. When the cause is permission and the analyst chooses to go on without writing: set `slots.can_edit` to false and record the choice in `decisions_log`; the cause counts as cleared (card 05 then uses the links for the check only; card 07 offers no colours).

## Outcomes, in precedence order

The first that holds wins.

- **TR-28 — The cause is cleared.** Write `current_state` as `blocked.entered_from` and `current_step` as the card the dispatch table gives for it, as one edit, and clear `blocked`. Next card: that card.
- **TR-29 — Otherwise.** `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. The run waits here. Record the default call in `decisions_log` and tell the analyst.

## Failure

When `blocked.entered_from` is empty or names no state of the dispatch table, resume from `scoped`: move the saved level reads (`levels/<levelNumber>.json`, not `outline.json`) into `levels/stale/` first, so card 02 reads every level again; every later card redoes only what its files do not already hold. Tell the analyst.
