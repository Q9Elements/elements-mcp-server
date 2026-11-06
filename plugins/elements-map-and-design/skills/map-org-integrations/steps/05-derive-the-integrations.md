# 05 Derive the integrations

State: `automations-traced`

## Purpose

Work out, system by system, every exchange the traced automations carry (from where, to where, through which middleware, what moves, how and when) and name the systems the org reaches only through a middleware, so they can be traced too.

## Procedure

1. For each system that `systems.json` marks `tracedRound` equal to `trace.round`, check its file when it exists: `python3 "$SKILL/scripts/build_landscape_model.py" check-found "$ENG" "$ENG/trace/found/<system id>.json"`. A file that prints `FOUND OK` is already derived: skip its agent.
2. Run the `integration-tracer` agent for each system still needed, in parallel, each with `pluginRoot`, `eng` (`$ENG`), `pack` (`$ENG/trace/packs/<system id>.json`) and `outputPath` (`$ENG/trace/found/<system id>.json`).
3. Run `check-found` for each file the agents wrote. Send a file's `ERROR` lines back to its agent as `findings`, at most `fix_rounds` times (`data/limits.csv`).
4. Run `python3 "$SKILL/scripts/build_landscape_model.py" merge "$ENG"`.
5. Record in `decisions_log` the integrations found, the inferred ones, and each system named behind a middleware with the automations that named it.

## Outcomes, in precedence order

The first that holds wins.

- **TR-13 — `merge` ends `NEW SYSTEMS`: systems named only behind a middleware, added to `systems.json`, still to be searched.** In one edit, add 1 to `trace.round` and write `{"current_state": "systems-confirmed", "current_step": "steps/04-trace-the-automations.md"}`. Next card: `steps/04-trace-the-automations.md` (one more search pass, for the new systems only). Tell the architect which systems were found behind which middleware.
- **TR-14 — `merge` ends `MERGED`.** `{"current_state": "integrations-derived", "current_step": "steps/06-review-the-integrations.md"}`. Next card: `steps/06-review-the-integrations.md`.
- **TR-15 — Otherwise (a tracer's file still fails after its fix rounds, or `merge` refuses).** Record the remaining `ERROR` lines in `blocked` (`entered_from: "automations-traced"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. Record the default call in `decisions_log` and tell the architect.

## Failure

A missing pack (`no evidence packs`, or a pack for a system `systems.json` marks traced) means card 04 did not finish: write `{"current_state": "systems-confirmed", "current_step": "steps/04-trace-the-automations.md"}` and say why.
