# 07 Draw the landscape

State: `integrations-approved`

## Purpose

Draw the approved landscape once, as a draft map in Elements: the org in the centre with every system around it, one drill-down per system showing its middleware, automations and objects, every card linked to its metadata, checked by the diagram reviewer.

## Procedure

1. Run `python3 "$SKILL/scripts/build_landscape_model.py" model "$ENG"`, every metadata attachment in the generated model carries `slots.ref_model_id` as `refModelId`; then run `python3 "$PLUGIN/scripts/validate.py" "$ENG/drawing/model.json" --for system-architecture`. Record each `WARN` line in `decisions_log` as a call taken as it is.
2. Resume rule: when `$ENG/drawing/landscape/` holds `review.json`, the map is drawn and reviewed: go to step 5. When it holds `plan.json` but no `review.json`, run the drawing protocol's `next` to resume at the first unfinished write. If it stops because a saved metadata attachment lacks `refModelId`, start that drawing again from the model in a new drawing folder with the run's selected reference model.
3. Run the `draw-system-architecture` skill from its step 1b with the model `$ENG/drawing/model.json` and the work folder `$ENG/drawing/landscape/`, adding `--drop-unresolved` to its plan.
4. The drawing skill asks nothing more. Where it would ask, take this call and record it in `decisions_log`:
   - a plan `WARN` line: go on with the plan as it is;
   - `fix-preflight` with missing icons: plan again with the same options and `--drop-icons` naming them;
   - `org_not_connected` or `metadata_no_access`: plan again with the same options and `--skip metadata`;
   - `lock_held` or `being_edited`: ask the architect to leave edit mode in Elements, then send again;
   - a timeout whose change the read-back shows saved: save the result fields from the read, as the protocol says, and go on.
5. Copy the map name and the `diagramUrl` from `drawing/landscape/review/top.json` into `deliverables.map_name` and `deliverables.map_url`, and the reviewer's verdict from `drawing/landscape/review.json` into `deliverables.review_verdict`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-18 — The map is drawn and the reviewer's verdict is saved as `drawing/landscape/review.json`.** `{"current_state": "delivered", "current_step": null}`. Report (below) and stop.
- **TR-19 — Otherwise (the model fails validation, or the drawing stopped on an error its protocol does not resolve).** Record the error and the work folder in `blocked` (`entered_from: "integrations-approved"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. Record the default call in `decisions_log` and tell the architect.

The final report, in the architect's words, from the run's files so it can be repeated at `delivered`: the map's link (`deliverables.map_url`) and how many drill-downs it has; the systems on it, and those set aside (the noise counts and the architect's drops in `systems.json` and `integrations.json`); the integrations, with the inferred ones named; each middleware drawn as a label, from `placement` in `drawing/model.json`; the reviewer's verdict and findings from `drawing/landscape/review.json`; the metadata that could not be linked, from the `unlinkable` list `layout_architecture.py next` prints at `done`; the gaps in `integrations.json` and the `open_items` not already among them; and that the map is a draft a person releases in Elements.

## Failure

The state stays at `integrations-approved` until the map is drawn and reviewed.
