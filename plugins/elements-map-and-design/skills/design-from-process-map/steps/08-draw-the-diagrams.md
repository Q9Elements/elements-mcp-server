# 08 Draw the diagrams

State: `design-approved`

## Purpose

Draw the approved design once, as drafts in Elements: the data model (one map per area when it is split) and the system architecture, each checked by the diagram reviewer and each linking back to the source map in its description.

## Procedure

1. Run `python3 "$SKILL/scripts/design.py" slice "$ENG" --project "<slots.project_name>"`, adding `--lower-confidence` when `check.confidence` is `lower`. It writes one model per diagram in `drawing/models/`; metadata attachments on derived entities carry `slots.ref_model_id` as `refModelId` and `metadataType` from the entity kind (`Standard Object` or `Custom Object`).
Resume rule for steps 2 and 3: skip a model whose work folder holds `review.json` (drawn and reviewed); when the folder holds `plan.json` but no `review.json`, run the drawing protocol's `next` for each data model area and the architecture to resume at the first unfinished write. If it stops because a saved metadata attachment lacks `refModelId`, start that drawing again from the model in a new drawing folder with the run's selected reference model.

2. For each `drawing/models/data-model*.json`, run the `draw-data-model` skill from its step 1b with that model file and the work folder `$ENG/drawing/<file name without .json>/`. Add `--skip metadata` to its plan when `slots.reference_source` is `documentation`.
3. For `drawing/models/architecture.json`, run the `draw-system-architecture` skill from its step 1b with the work folder `$ENG/drawing/architecture/`.
4. The solution architect approved the design at the checkpoint, so the drawing skills ask nothing more. Where a drawing skill would ask, take this call and record it in `decisions_log`:
   - a plan `WARN` line: go on with the plan as it is;
   - `fix-preflight` with missing icons: plan again with `--drop-icons` naming them;
   - `org_not_connected`, `metadata_not_found` or `metadata_no_access`: plan again with `--skip metadata`;
   - `lock_held` or `being_edited`: ask the solution architect to leave edit mode in Elements, then send again.
5. After each drawing, copy its map name and the `diagramUrl` from `drawing/<name>/review/top.json` into `deliverables.data_model_maps` (one `{"name", "url"}` each) or `deliverables.architecture_map`. The reviewer's verdict is saved as `drawing/<name>/review.json`.
6. Before TR-20, rebuild `deliverables.data_model_maps` and `deliverables.architecture_map` from every `drawing/<name>/review/top.json` whose folder holds `review.json` (map name and `diagramUrl`, as in step 5), so a drawing finished in an earlier session keeps its link.

## Outcomes, in precedence order

The first that holds wins.

- **TR-20 — Every model in `drawing/models/` is drawn and its review verdict is saved.** `{"current_state": "diagrams-drawn", "current_step": "steps/09-assemble-the-solution-overview.md"}`. Next card: `steps/09-assemble-the-solution-overview.md`.
- **TR-21 — Otherwise (a drawing stopped on an error its protocol does not resolve).** Record the drawing, the error and its work folder in `blocked` (`entered_from: "design-approved"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. Record the default call in `decisions_log` and tell the solution architect.

## Failure

The state stays at `design-approved` until every model is drawn.
