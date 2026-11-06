# 04 Trace the automations

State: `systems-confirmed`

## Purpose

Find, for every confirmed system not traced yet, the flows, Apex and other automations that exchange data with it, and what each one reads, writes and calls, so the integrations can be worked out from evidence rather than names.

## Procedure

The round is `trace.round`. On a resumed run, run the scripts in order and fetch only what their `ERROR` lines name.

1. Run `python3 "$SKILL/scripts/trace_plan.py" terms "$ENG"`. Copy each `GAP` line into `open_items`.
2. For each `SEARCH <pull> '<term>'` line: call `run_code_search` with `query` the term. Searches build one at a time on the server, about a minute each, so start them all, then call each again with the same arguments, a few at a time, until its `status` is `complete`. Record the answer as that pull and download each part at once: code-search links expire after 120 seconds, so when one has expired, call again for fresh links. An answer with no rows is recorded with `partsTotal` 0 and no parts.
3. Run `python3 "$SKILL/scripts/trace_plan.py" hits "$ENG"`.
4. For each entry of `whereUsed` in `trace/round-<round>/batches.json`: call `get_dependencies` with `lookingFor: "where_used"`, its `nodeIds` and `attributes: ["description"]`, recorded under its `pull` name.
5. Run `python3 "$SKILL/scripts/trace_plan.py" automations "$ENG"`.
6. For each entry of `using` in `batches.json`: call `get_dependencies` with `lookingFor: "using"`, its `nodeIds` and `attributes: ["description"]`, recorded under its `pull` name.
7. For each entry of `summary` in `batches.json`: call `explain_metadata_components` with `aspect: "summary"` and its `nodeIds`; while any item is `running`, call again with the same arguments after its `retryAfterSeconds`, for up to 16 minutes; an item failed with `rate_limited` is asked once more after its `retryAfterSeconds`. Save the last whole answer as `trace/round-<round>/<file>`; failed items stay in it as they are. Do the same for the `chain` entry with `aspect: "chain"`.
8. Run `python3 "$SKILL/scripts/trace_plan.py" pack "$ENG"`. Record in `decisions_log` the automations found per system and the explanations that failed.

## Outcomes, in precedence order

The first that holds wins.

- **TR-10 — A search or dependency call fails, not just `running`, after a fresh call.** Record the call and the error in `blocked` (`entered_from: "systems-confirmed"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`.
- **TR-11 — `pack` ends `PACKED`.** `{"current_state": "automations-traced", "current_step": "steps/05-derive-the-integrations.md"}`. Next card: `steps/05-derive-the-integrations.md`.
- **TR-12 — Otherwise.** Record what stopped the trace in `blocked` (`entered_from: "systems-confirmed"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. Record the default call in `decisions_log` and tell the architect.

## Failure

`REFUSED` (exit 1): fetch what its `ERROR` lines name and run the script again. A `SETUP` line (exit 2): fix the file it names and run the step again. The state stays at `systems-confirmed` until `pack` prints `PACKED`.

Every final run_code_search query, including configured, inferred and architect-added terms, contains 2-512 trimmed characters. Out-of-range terms are explicit gaps in searches.json and retain their meaning in the gap text; never truncate them. Native registers keep status/resultId/counts/parts and complete failures. Bind slots.space_id and the selected server in drawing/connection.json before handing the model to the drawing skill.
