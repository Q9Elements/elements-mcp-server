# 03 Confirm the systems

State: `systems-proposed`

## Purpose

Check 1. Before anything is traced, the architect sees the outside systems the metadata proves, each with its evidence, and merges, renames, drops or adds entries, so the expensive tracing runs only on systems they recognise.

## Procedure

1. When `systems/corrections.json` exists, run `python3 "$SKILL/scripts/resolve_systems.py" confirm "$ENG"` first and handle its output as in step 4.
2. Run `python3 "$SKILL/scripts/resolve_systems.py" show "$ENG"` and show the architect, in one message: the systems with how each was found and its evidence; the classifier's calls, each with its reason and confidence; and the items set aside as not outside systems, counted by reason.
3. Ask the architect to confirm the list, or to say what to merge, rename, drop or add (for a system they add: what kind it is, and whether it is middleware).
4. **Corrections:** append them to `systems/corrections.json` as one round, `{"rounds": [{"date", "by": "the architect", "corrections": [op, ...]}]}`, each as an op `resolve_systems.py` lists (drop, rename, merge, kind, add), naming systems as `show` names them. Run `python3 "$SKILL/scripts/resolve_systems.py" confirm "$ENG"`; when it prints `ERROR` lines, correct the ops you wrote to say what the architect said and run it again. Once it prints `CONFIRMED`, set `"applied": true` on that round, show the corrected list as in step 2, and ask again.
5. **Confirmed as shown:** run `python3 "$SKILL/scripts/resolve_systems.py" confirm "$ENG"`. Once it prints `CONFIRMED`, set `checks.systems_confirmed_on` (today) and record the confirmation and each correction in `decisions_log` with `who` "the architect".

## Outcomes, in precedence order

The first that holds wins.

- **TR-08 — The architect confirms the list as shown, with every round of corrections applied, and `confirm` printed `CONFIRMED`.** `{"current_state": "systems-confirmed", "current_step": "steps/04-trace-the-automations.md"}`. Next card: `steps/04-trace-the-automations.md`.
- **TR-09 — Otherwise (no clear answer, or corrections not yet applied).** `{"current_state": "systems-proposed", "current_step": "steps/03-confirm-the-systems.md"}`. Next card: `steps/03-confirm-the-systems.md`. Tell the architect the run waits for their answer. Record the default call in `decisions_log`.

## Failure

When `systems/proposed.json` is missing, card 02 did not finish: write `{"current_state": "scoped", "current_step": "steps/02-take-the-inventory.md"}` and say why.
