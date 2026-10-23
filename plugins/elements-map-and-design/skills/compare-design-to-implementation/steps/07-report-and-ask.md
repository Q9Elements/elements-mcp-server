# 07 Report and ask

State: `assessed`

## Purpose

The analyst sees how far the org implements the design, step by step, and decides whether the diagram is colour-coded to show it.

## Procedure

1. Show the report from `report.md` in short: the counts by verdict; for each level, the steps partly or not supported with what is missing; how many steps were not assessed (no metadata linked) and how many need no org support; the links used but not saved, and those Elements refused. Say that `report.md` in the engagement directory holds the whole table, and that the links added at card 05 stay on the map whatever happens next.
2. When `slots.can_edit` is false, say the colours cannot be applied because the analyst cannot edit this map, and take TR-20. When `results.json` counts no box fully, partly or not supported (every step is not assessed or needs no org support), say there is nothing to colour and take TR-20.
3. When `checks.colouring_answer` is null, ask whether to colour the design: boxes green (fully supported), yellow (partly) or red (not supported), a sticky note of at most the length `data/limits.csv` sets (`note_max_words`) on each yellow and red box saying what is missing, and a legend on each level; all on the map's draft, and removed again by asking to reset the colours. Record the answer in `checks.colouring_answer` and in `decisions_log` with `who` "the analyst".

## Outcomes, in precedence order

The first that holds wins.

- **TR-20 — The analyst said no, the map cannot be edited, or there is nothing to colour.** Set `deliverables.outcome` to "report only" and say why in `decisions_log`. `{"current_state": "delivered", "current_step": null}`. Next card: none (terminal). Report the deliverables: the report, and the links added.
- **TR-19 — The analyst said yes.** Set `checks.colouring_approved_on` (today). `{"current_state": "colouring-approved", "current_step": "steps/08-colour-the-design.md"}`. Next card: `steps/08-colour-the-design.md`.
- **TR-21 — Otherwise (no clear answer).** `{"current_state": "assessed", "current_step": "steps/07-report-and-ask.md"}`. Next card: `steps/07-report-and-ask.md`. Tell the analyst the run waits for their answer. Record the default call in `decisions_log`.

## Failure

When `results.json` is missing, card 06 did not finish: write `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}` and say why.
