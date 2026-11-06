# 09 Keep or reset

State: `coloured`

## Purpose

The design stays coloured for as long as the analyst wants it. When they ask to reset the colours, every box this playbook coloured goes back to the colours it had and every note it added is removed; nothing else on the map changes, and the links added at card 05 stay.

## Procedure

1. When `slots.can_edit` is false, say the reset cannot be written because the analyst cannot edit the map now, and take TR-27. When the analyst's request is not to reset the colours: repeat where the check stands (the counts from `report.md` when it exists, and the map link `slots.map_url`), say that asking to reset the colours removes them, and take TR-27.
2. **Reset.** Read every level in scope with `get_diagram` (`include: ["layout", "metadata", "notes"]` and `delivery: "file"` with selected teamId) into `levels/<levelNumber>.json`, and run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`.
3. Run `python3 "$SKILL/scripts/colour.py" reset-plan "$ENG"`. Without `colour/originals.json` (a reset scoped at card 01 without this run's files), it clears only boxes filled with the colours of `data/verdicts.csv` and removes only notes that start with the playbook's marker; say so to the analyst.
4. For each `colour/reset/<level>.json`, run `python3 "$PLUGIN/scripts/manage_batches.py" next "$ENG/colour/reset/<level>.json" --result "$ENG/colour/reset-saved/<level>.json"`. Send each printed call's `arguments` using the selected server and space `teamId`, save the whole genuine response at `saveTo`, and repeat until `action: "done"`. The runner previews and applies every batch and writes the combined saved record. When an issue has severity `error`, or a warning says `being_edited`, take TR-26 with the issue as the reason. On `version_conflict`, go back to step 2; follow the session's write recovery for an uncertain save or running copy. On any other refusal, take TR-26 with it as the reason. Proceed to step 5 only when every level's runner is done.
5. Read the levels again as in step 2, run `read_design.py build`, then `python3 "$SKILL/scripts/colour.py" reset-verify "$ENG"`. Once it prints `RESET OK`, set `checks.reset_on` (today) and record the reset in `decisions_log` with `who` "the analyst". Name any box `reset-plan` kept because someone recoloured it after the check.

## Outcomes, in precedence order

The first that holds wins.

- **TR-26 — A reset write was refused.** Set `blocked.reason` (the issue and the level), `blocked.owner` ("the analyst") and `blocked.entered_from` ("coloured"). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`.
- **TR-25 — `reset-verify` printed `RESET OK`.** Set `deliverables.outcome` to "colours reset". `{"current_state": "delivered", "current_step": null}`. Next card: none (terminal). Report that the colours and notes are gone and the report stays in `report.md`.
- **TR-27 — Otherwise (no reset asked, or reset writes left).** `{"current_state": "coloured", "current_step": "steps/09-keep-or-reset.md"}`. Next card: `steps/09-keep-or-reset.md`. Record the default call in `decisions_log` and tell the analyst.

## Failure

When `levels/outline.json` is missing, card 01 did not finish: write `{"current_state": "not-started", "current_step": "steps/01-scope-the-run.md"}` and say why.
