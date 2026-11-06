# 06 Review the integrations

State: `integrations-derived`

## Purpose

Check 2. Before anything is drawn, the architect sees every integration found (from, to, through which middleware, what moves, the automations that carry it and the objects they touch), where each middleware will be drawn, and what could not be established, and approves or corrects it.

## Procedure

1. When the last round in `integrations/corrections.json` lacks `"applied": true`, apply it as in step 4 first.
2. Run `python3 "$SKILL/scripts/build_landscape_model.py" show "$ENG"` and show the architect, in one message: the integration list; where each middleware is drawn and why (its own card, or a "via" label on the lines when it carries more systems than the threshold or level 1 would pass the card limit); the calls to rule on: every integration marked inferred and every system named only behind a middleware, each with its evidence; the systems with no integration found; the gaps.
3. Ask the architect to approve, or to say what to change: drop or edit an integration, add one, drop, rename or merge a system, or draw a middleware the other way.
4. **Corrections:** append them to `integrations/corrections.json` as one round, `{"rounds": [{"date", "by": "the architect", "corrections": [op, ...]}]}`, each as an op `build_landscape_model.py` lists (drop-integration, edit-integration, add-integration, drop-system, rename-system, merge-systems, placement), naming integrations by their `#` and systems as `show` names them. Run `python3 "$SKILL/scripts/build_landscape_model.py" correct "$ENG"`; when it prints `ERROR` lines, correct the ops you wrote to say what the architect said and run it again. Once it prints `CORRECTED`, set `"applied": true` on that round, show the corrected list as in step 2, and ask again.
5. On approval, set `checks.integrations_approved_on` (today). Record the approval and each correction in `decisions_log` with `who` "the architect".

## Outcomes, in precedence order

The first that holds wins.

- **TR-16 — The architect approves the list as shown, with every round of corrections applied.** `{"current_state": "integrations-approved", "current_step": "steps/07-draw-the-landscape.md"}`. Next card: `steps/07-draw-the-landscape.md`.
- **TR-17 — Otherwise (corrections still to apply or show, or no clear answer).** `{"current_state": "integrations-derived", "current_step": "steps/06-review-the-integrations.md"}`. Next card: `steps/06-review-the-integrations.md`. Tell the architect the run waits for their approval. Record the default call in `decisions_log`.

## Failure

When `integrations.json` is missing, card 05 did not finish: write `{"current_state": "automations-traced", "current_step": "steps/05-derive-the-integrations.md"}` and say why.
