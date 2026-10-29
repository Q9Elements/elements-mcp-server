# 08 Colour the design

State: `colouring-approved`

## Purpose

Show the verdicts on the diagram itself: each assessed box filled with its verdict's colour, a sticky note above each partly or not supported box saying what is missing, and a legend on each coloured level. The colours each box had before are saved first, so the reset puts them back.

## Procedure

1. When the analyst's latest request is to reset the colours, take TR-31. When `slots.can_edit` is false, take TR-30.
2. Read every level in scope again with `get_diagram` (`include: ["layout", "metadata", "notes"]` and `delivery: "file"` with selected teamId) into `levels/<levelNumber>.json`, and run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`, so the plan starts from the levels as they are now.
3. Run `python3 "$SKILL/scripts/colour.py" plan "$ENG"`. A resumed run plans again from step 2.
4. For each `colour/plan/<level>.json`, run `python3 "$PLUGIN/scripts/manage_batches.py" next "$ENG/colour/plan/<level>.json" --result "$ENG/colour/saved/<level>.json"`. Send each printed call's `arguments` using the selected server and space `teamId`, save the whole genuine response at `saveTo`, and repeat until `action: "done"`. Every batch is previewed and applied, including a later batch holding only the legend. When an issue has severity `error`, or a warning says `being_edited`, take TR-23 with the issue as the reason. On `version_conflict`, go back to step 2; follow the session's write recovery for an uncertain save or running copy. On any other refusal, take TR-23 with it as the reason. Proceed to step 5 only when every level's runner is done.
5. Read every planned level again as in step 2, run `read_design.py build`, then `python3 "$SKILL/scripts/colour.py" record "$ENG"`. Set `deliverables.levels_coloured` to the levels it lists.
6. Tell the analyst the design is coloured, with the map link (`slots.map_url`), any note `plan` warned overlaps something, and that asking to reset the colours removes the colours and the notes.

## Outcomes, in precedence order

The first that holds wins.

- **TR-31 — The analyst asks to reset the colours before colouring finished.** `{"current_state": "coloured", "current_step": "steps/09-keep-or-reset.md"}`. Next card: `steps/09-keep-or-reset.md`, which removes whatever was written.
- **TR-30 — The map cannot be edited.** Set `deliverables.outcome` to "report only: the map cannot be edited". `{"current_state": "delivered", "current_step": null}`. Next card: none (terminal). Report the deliverables.
- **TR-23 — A write was refused.** Set `blocked.reason` (the issue and the level), `blocked.owner` ("the analyst") and `blocked.entered_from` ("colouring-approved"). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`.
- **TR-22 — `record` printed `RECORDED`.** `{"current_state": "coloured", "current_step": "steps/09-keep-or-reset.md"}`. Next card: `steps/09-keep-or-reset.md`.
- **TR-24 — Otherwise (writes left, or `record` found a mismatch).** `{"current_state": "colouring-approved", "current_step": "steps/08-colour-the-design.md"}`. Next card: `steps/08-colour-the-design.md`. A mismatch means a level changed while it was written: plan again from step 1. Record the default call in `decisions_log` and tell the analyst.

## Failure

When `results.json` is missing, card 06 did not finish: write `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}` and say why.
