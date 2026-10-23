# 05 Write the links

State: `links-approved`

## Purpose

Add the approved links to the boxes on the map's draft, so the design carries them after the check, and read the levels back so the comparison uses what Elements saved.

## Procedure

1. When `slots.can_edit` is false: run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`, tell the analyst the links are used for this check only, and take TR-13.
2. Run `python3 "$SKILL/scripts/match.py" resolve "$ENG"`. For each nodeId it prints, call `get_metadata_component` with that `nodeId` and `detail: "full"` and save the answer as `links/resolve/<nodeId>.json`; run it again until it prints `RESOLVED`.
3. Run `python3 "$SKILL/scripts/match.py" plan "$ENG"`. For each `links/plan/<level>.json` without a `links/plan/<level>.saved.json` beside it:
   1. Run `python3 "$PLUGIN/scripts/manage_batches.py" next "$ENG/links/plan/<level>.json" --result "$ENG/links/plan/<level>.saved.json"`. For each printed call, use the selected server and space `teamId`, send its `arguments`, and save the whole genuine response at `saveTo`. Repeat until `action: "done"`; the runner previews and applies every batch and writes the combined saved record.
   2. When a dry-run answer has issues of severity `error` about single changes (`changes[i]`), run `python3 "$SKILL/scripts/match.py" drop-failed "$ENG" <level> <saveTo> --batch <batch>` using the runner's batch number and saved dry-run path. This drops only the refused changes and retains all remaining batches' references. If earlier batches were saved, read every level again, run `read_design.py build` and `match.py plan` before continuing, so saved links are accounted for at the current version. Otherwise repeat the batch runner on the updated plan; when no changes remain the level is done. When `drop-failed` refuses because an error is not about one change, or a warning says `being_edited`, take TR-14 with the issue as the reason.
   3. On `version_conflict`, read every level in scope again, run `read_design.py build` and `match.py plan`, and start again from the first level without a `.saved.json`. On an uncertain save or running copy, follow the session's write recovery before continuing the runner. Any other refusal: take TR-14 with it as the reason.
4. Read every level written again with `get_diagram` (`include: ["layout", "metadata", "notes"]` and `delivery: "file"` with selected teamId) into `levels/<levelNumber>.json`, then run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`.
5. Tell the analyst how many links were added and on which steps, and which Elements refused and why (from `links/not-saved.json`).

## Outcomes, in precedence order

The first that holds wins.

- **TR-14 — A write was refused as a whole: a level is open in edit mode (`being_edited`), the analyst may not edit it, or an error is not about one change.** Set `blocked.reason` (the issue and the level), `blocked.owner` ("the analyst") and `blocked.entered_from` ("links-approved"). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`.
- **TR-13 — Every level's plan is saved or had nothing left to write, and `build` ran on the fresh reads (or the map is not editable and `build` ran).** `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}`. Next card: `steps/06-assess-the-boxes.md`.
- **TR-15 — Otherwise (writes left to send).** `{"current_state": "links-approved", "current_step": "steps/05-write-the-links.md"}`. Next card: `steps/05-write-the-links.md`. Record the default call in `decisions_log` and tell the analyst.

## Failure

When `links/approved.json` is missing, card 04 did not finish: write `{"current_state": "links-proposed", "current_step": "steps/04-review-the-links.md"}` and say why.
