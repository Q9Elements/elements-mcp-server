# 07 Review the design

State: `design-derived`

## Purpose

The checkpoint. The solution architect sees the derived design in their own terms, in one sitting, and approves it or corrects it before anything is drawn.

## Procedure

1. For a session that stopped inside this card: when the last round in `derive/corrections.json` lacks `"applied": true`, apply its data and systems corrections as in step 4 first. Then run `python3 "$SKILL/scripts/design.py" merge "$ENG"`. When it does not print `MERGED`, fix what it reports as in step 4 and merge again; when it still fails, take TR-19. After `MERGED`, run `python3 "$SKILL/scripts/design.py" stale "$ENG"`; on `STALE`, take TR-18 without asking again.
2. Show, in one message, from the run's files:
   - when `check.confidence` is `lower`, that first;
   - **the data**: a table of entities from `derive/data-model.json`: name, standard, custom or proposed, the object it maps to, the nouns it came from; then the relationships in a line each;
   - **the systems**: a table of integrations from `derive/integrations.json`: from, to, data, pattern, timing, existing or proposed; where middleware sits; the handoffs left manual;
   - **the access**: per permission controller from `derive/access.json`, the personas it serves, reuse, extend or create, and its object permissions; the `WARN` lines of `python3 "$SKILL/scripts/check_access_matrix.py" "$ENG" --check`;
   - **the calls to rule on**: every proposed entity, proposed integration, middleware placement and created permission controller, each with its evidence;
   - the gaps from all three files and `evidence.gaps`;
   - when `check/scores.json` shows levels below the pass mark, those levels.
3. Ask the solution architect to approve, or to say what to change.
4. **Corrections:** append them as given to `derive/corrections.json` (`{"rounds": [{"date", "by", "corrections": [...]}]}`). Apply corrections to the data or the systems to `derive/data-model.json` or `derive/integrations.json`, editing only what they named; access corrections stay in `corrections.json` for the access-deriver. Run `design.py check-section` for the section files changed and `design.py merge "$ENG"`; fix what they report in the files you edited. Once it prints `MERGED`, set `"applied": true` on that round. Record each correction in `decisions_log` with `who` as the solution architect's name.

## Outcomes, in precedence order

The first that holds wins.

- **TR-17 — The solution architect approves.** Set `review.approved_by` (`slots.prepared_by` unless someone else approves) and `review.approved_on`. `{"current_state": "design-approved", "current_step": "steps/08-draw-the-diagrams.md"}`. Next card: `steps/08-draw-the-diagrams.md`.
- **TR-18 — The solution architect gives corrections, and they are applied and the merge passes.** `{"current_state": "structure-derived", "current_step": "steps/06-derive-the-access-matrix.md"}`. Next card: `steps/06-derive-the-access-matrix.md` (the access matrix is derived again, then this card shows the design again).
- **TR-19 — Otherwise (no clear answer, or corrections not yet applied).** `{"current_state": "design-derived", "current_step": "steps/07-review-the-design.md"}`. Next card: `steps/07-review-the-design.md`. Tell them the run waits for their approval. Record the default call in `decisions_log`.

## Failure

When `access-matrix.csv` is missing, card 06 did not finish: write `{"current_state": "structure-derived", "current_step": "steps/06-derive-the-access-matrix.md"}` and say why.
