# 06 Derive the access matrix

State: `structure-derived`

## Purpose

Work out who needs what access: for every step, the person, agent or system that does it, the objects it creates, reads, updates or deletes, and the permission controller that grants it, reusing or extending what the org already has where it can. This card also runs again after the solution architect corrects the design.

## Procedure

1. **Route `org`** (`slots.reference_source`): collect the `nodeId` of every entity in `derive/data-model.json` that has one. When there is none, skip the `get_access` bullet and add to `evidence.gaps` that no mapped object exists in the org yet; the `permission-holders` pull still runs.
   - Call `get_access` with `refModelId` and `nodeIds`, at most 1000 per call; name the pulls `access-1`, `access-2`, .... While `status` is `running`, call again with the same arguments. Record each pull in `evidence/pulls.json` with its `nodeIds`, and save each part as `evidence/<pull>-<index>.ndjson` (`evidence/access-1-0.ndjson`), following `nextPartsFrom`, as in card 04. Acquire failedFile whenever failedTotal exceeds inline failed, verify full failure coverage, and copy every failure with its reason into evidence.gaps. Retain terminal status/resultId and the native acquisition fields in each pull. Use default holder mode, whose rows are node/holder/access.
   - Pull `list_metadata_by_criteria` with `metadataList: ["Permission Set", "Permission Set Group"]` and `columns: ["name", "api_name", "type", "description"]` the same way, as pull `permission-holders`.
   - Run `python3 "$SKILL/scripts/prepare_evidence.py" "$ENG" --verify <pull>` for each pull; on `REFUSED`, fetch or record what its `ERROR` lines name.
   - On a return from the checkpoint, keep a pull that still verifies and whose `nodeIds` are unchanged; pull again only what changed, and remove from `evidence/pulls.json` an `access-` pull this round no longer needs.
2. Run the `access-deriver` agent with `pluginRoot`, `eng`, `route` (`slots.reference_source`), `outputPath` (`$ENG/derive/access.json`) and, when `derive/corrections.json` exists, the access corrections of every round in it as `findings` (the agent writes the whole matrix afresh, so a correction left out is lost). The agent reads only the part files `evidence/pulls.json` records for each pull, so a part file an earlier pull left on disk is not read.
3. Run `python3 "$SKILL/scripts/check_access_matrix.py" "$ENG"`. Send its `ERROR` lines back to the agent as `findings`, at most twice.
4. Record in `decisions_log` the permission controllers the agent chose to reuse, extend and create, with their evidence.

## Outcomes, in precedence order

The first that holds wins.

- **TR-15 — The check ends with `WROTE access-matrix.csv` (exit 0).** `{"current_state": "design-derived", "current_step": "steps/07-review-the-design.md"}`. Next card: `steps/07-review-the-design.md`.
- **TR-16 — Otherwise (the check still fails after two rounds).** Record the remaining `ERROR` lines in `blocked` (`entered_from: "structure-derived"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. Record the default call in `decisions_log` and tell the solution architect.

## Failure

When `model.json` has no entities, the merge of card 05 did not run: write `{"current_state": "evidence-gathered", "current_step": "steps/05-derive-data-model-and-integrations.md"}` and say why.
