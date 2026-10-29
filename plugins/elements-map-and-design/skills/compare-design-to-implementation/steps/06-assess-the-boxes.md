# 06 Assess the boxes

State: `links-settled`

## Purpose

The comparison itself. For every box linked to metadata, gather what each linked component is and does in the org (its definition, what it reads and writes, the automations acting on it, its change history and Elements' explanation), have one assessor judge the box against the design, and roll the verdicts up so a box with steps beneath it is judged with them.

## Procedure

1. Run `python3 "$SKILL/scripts/evidence.py" plan "$ENG"`. When it prints `NOTHING LINKED`, take TR-16. When it prints `DECISIONS ONLY`, go to step 6.
2. Make every call the plan prints, saving each answer under `evidence/` by the name it gives; the list tools save their parts as the pulls named (the session contract), one `save_pull.py` at a time (each run rewrites `evidence/pulls.json`, so two at once lose a part's record). A file already saved in this run is not fetched again. `explain_metadata_components` is polled as the session contract says.
3. When the plan lists `where_used` calls: run `python3 "$SKILL/scripts/evidence.py" related "$ENG"`, and when it prints `RELATED`, call `get_metadata_source` with the nodeIds in `evidence/related.json` and save the parts as the pull `source-related`.
4. Run `python3 "$SKILL/scripts/evidence.py" pack "$ENG"`. When it names a file or pull that is missing or incomplete, fetch it and run it again.
5. Run `python3 "$SKILL/scripts/evidence.py" wave "$ENG"`. For each box it lists, run one `implementation-assessor` agent, all of the wave at once, each given `pluginRoot`, `eng`, `pack` (`$ENG/assess/packs/<box>.json`) and `outputPath` (`$ENG/assess/verdicts/<box>.json`), as absolute paths. When one returns, run `python3 "$SKILL/scripts/evidence.py" check "$ENG" "$ENG/assess/verdicts/<box>.json"`; on `ERROR` lines, run the agent once more with them as `findings`. Run `wave` again until it prints `ALL ASSESSED`.
6. Run `python3 "$SKILL/scripts/evidence.py" rollup "$ENG"`. Set `deliverables.report` to `report.md` and `deliverables.boxes_compared` to the number of boxes assessed.

## Outcomes, in precedence order

The first that holds wins.

- **TR-16 — `plan` printed `NOTHING LINKED`.** Set `deliverables.outcome` to "nothing compared: no box in scope is linked to metadata". `{"current_state": "delivered", "current_step": null}`. Next card: none (terminal). Tell the analyst that no step could be compared because none is linked to metadata, and that linking boxes, or accepting the proposal at the next check, makes the comparison possible.
- **TR-17 — `rollup` printed `ROLLED UP`.** `{"current_state": "assessed", "current_step": "steps/07-report-and-ask.md"}`. Next card: `steps/07-report-and-ask.md`.
- **TR-18 — Otherwise (calls, packs or verdicts left).** `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}`. Next card: `steps/06-assess-the-boxes.md`. Tell the analyst how many boxes are assessed so far. Record the default call in `decisions_log`.

## Failure

When `design.json` is missing, card 02 did not finish: write `{"current_state": "scoped", "current_step": "steps/02-read-the-design.md"}` and say why. When an assessor's answer still fails `check` after its second run, add the box and the `ERROR` lines to `open_items` and run a fresh agent once more with them as `findings`. When that fails too, tell the analyst which step could not be judged and stay at `links-settled`; the run resumes here once the agent's answer passes.
