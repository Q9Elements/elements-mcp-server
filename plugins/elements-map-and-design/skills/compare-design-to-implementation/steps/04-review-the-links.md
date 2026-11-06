# 04 Review the links

State: `links-proposed`

## Purpose

The checkpoint before anything is written to the map: the analyst sees, for every unlinked box, the components proposed and why, or why none is (the step needs no org support, or the org has nothing for it), and approves, changes or drops them.

## Procedure

1. When `checks.links_approved_on` is set and `links/approved.json` exists, run `python3 "$SKILL/scripts/match.py" confirm "$ENG"` and `python3 "$SKILL/scripts/read_design.py" build "$ENG"`, and take TR-10 or TR-11 by the count `confirm` prints; nothing is asked again.
2. When `links/corrections.json` holds a last round without `"applied": true`, run `python3 "$SKILL/scripts/match.py" confirm "$ENG"` first and handle its output as in step 5.
3. Show the table `python3 "$SKILL/scripts/match.py" table "$ENG"` prints, or after corrections the one `confirm` prints. Say what approval does: when `slots.can_edit` is true, the links are added to the map's draft; when false, they are used for this check only and listed in the report.
4. Ask the analyst to approve the table, or to say what to drop, add or change.
5. **Corrections:** append them to `links/corrections.json` as one round, `{"rounds": [{"date", "by": "the analyst", "corrections": [op, ...]}]}`, each op an object `{"op": "<name>", ...}` with the fields `match.py` lists for it: `drop` (box, nodeId), `drop-box` (box: leave it unlinked), `add` (box, nodeId, apiName, sfType, name, why, and for a field its object's API name as `object` when the search path shows it), `no-org-support` (box, reason), `nothing-found` (box, gapNote). For a component the analyst names, find it with `search_metadata` and copy its `nodeId`, `apiName` and `sfType`; when several match, ask which. Run `python3 "$SKILL/scripts/match.py" confirm "$ENG"`; on `ERROR` lines, correct the ops to say what the analyst said and run it again. Once it prints `CONFIRMED`, set `"applied": true` on that round, show the table it printed, and ask again.
6. **Approved as shown:** run `python3 "$SKILL/scripts/match.py" confirm "$ENG"`. Once it prints `CONFIRMED`, set `checks.links_approved_on` (today), record the approval and each correction in `decisions_log` with `who` "the analyst", and run `python3 "$SKILL/scripts/read_design.py" build "$ENG"`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-10 — The analyst approved, `confirm` printed `CONFIRMED` with at least one link.** `{"current_state": "links-approved", "current_step": "steps/05-write-the-links.md"}`. Next card: `steps/05-write-the-links.md`.
- **TR-11 — The analyst approved and `confirm` printed `CONFIRMED 0 link(s)`.** `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}`. Next card: `steps/06-assess-the-boxes.md`.
- **TR-12 — Otherwise (no clear answer, or corrections not yet applied).** `{"current_state": "links-proposed", "current_step": "steps/04-review-the-links.md"}`. Next card: `steps/04-review-the-links.md`. Tell the analyst the run waits for their answer. Record the default call in `decisions_log`.

## Failure

When `links/proposed.json` is missing, card 03 did not finish: write `{"current_state": "links-missing", "current_step": "steps/03-offer-to-match.md"}` and say why.
