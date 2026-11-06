# 02 Read the design

State: `scoped`

## Purpose

Read every level in scope, the boxes on it, what each box is linked to, and the levels beneath; follow each link to the copy of its component in the org being compared; and find which boxes have no metadata linked yet.

## Procedure

1. For each item of `levels/outline.json` in scope (every item when `slots.scope` is `map`; otherwise the level whose `levelNumber` is the scope and every level whose number starts with it and a dot), call `get_diagram` with its `diagramId` and `include: ["layout", "metadata", "notes"]` and `delivery: "file"` with selected teamId, and save the answer whole as `levels/<levelNumber>.json`. A large level answers with a file link (`delivery: "file"`): download it to the same name. A level already saved in this run is not read again.
2. Run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`. When it names levels that are not saved, read them as in step 1 and run it again. When it refuses for too many boxes, tell the analyst how many there are and ask for one level to check; set `slots.scope` to the level they name and run it again.
3. **Follow the links into the org.** When `build` printed `TO RESOLVE`, run `python3 "$SKILL/scripts/read_design.py" org-plan "$ENG"` and make every `list_metadata_by_criteria` call it prints, saving each answer's parts as the pull it names (the session contract). For an answer with no rows, save the whole genuine reply as `$ENG/empty-reply.json`, then run `python3 "$SKILL/scripts/save_pull.py" "$ENG" <pull> list_metadata_by_criteria --reply "$ENG/empty-reply.json"`. Empty success requires `status: "complete"`, result identity and settled part and failure coverage. Run `python3 "$SKILL/scripts/read_design.py" org-map "$ENG"`, then `build` again.
4. Run `python3 "$SKILL/scripts/read_design.py" coverage "$ENG"`.
5. Tell the analyst how many boxes are in scope, how many of the boxes with no level beneath them are linked to metadata, and, by level, which are not. Say how many links were followed from another org's copy to this org's (`FOLLOWED`), and name each linked component this org does not have (`NOT IN ORG`): its box is judged without it, so the gap shows in the report. Name any link `coverage` prints as `UNRESOLVED` (nothing to look it up by, or several components of this org match it): it is left out.

## Outcomes, in precedence order

The first that holds wins.

- **TR-04 — `coverage` printed `ALL LINKED`.** `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}`. Next card: `steps/06-assess-the-boxes.md`.
- **TR-05 — `coverage` printed `UNLINKED`.** `{"current_state": "links-missing", "current_step": "steps/03-offer-to-match.md"}`. Next card: `steps/03-offer-to-match.md`.
- **TR-06 — Otherwise (a level could not be read, `build` still refuses, or a link is still to be looked up).** `{"current_state": "scoped", "current_step": "steps/02-read-the-design.md"}`. Next card: `steps/02-read-the-design.md`. Tell the analyst what stopped the read. Record the default call in `decisions_log`.

## Failure

When `levels/outline.json` is missing, card 01 did not finish: write `{"current_state": "not-started", "current_step": "steps/01-scope-the-run.md"}` and say why.
