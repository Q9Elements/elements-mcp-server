# 10 Blocked recovery

State: `blocked`

## Purpose

Something stopped the run: a level that cannot be read, no target objects, or an agent's file or a drawing that still fails after its fix rounds. This card gets it unstuck and returns to where the run was.

## Procedure

1. Read `blocked.reason` and `blocked.entered_from`.
2. **An agent's file that still fails its check** (`entered_from` `scoped`, `evidence-gathered`, `structure-derived` or `diagrams-drawn`, with `ERROR` lines as the reason): when `blocked.reason` repeats the `ERROR` lines of the last retry recorded in `decisions_log`, the same errors came back: show the solution architect the `ERROR` lines and ask how to proceed. Otherwise there is no question for the solution architect: record the retried `ERROR` lines in `decisions_log` (`what`: one more attempt after a block; `evidence`: the lines), and the cause counts as resolved for one more attempt with a fresh agent; take TR-24.
3. **Anything else:** tell the solution architect, in plain words, what stopped the run and what would resolve it: access to the map or the space, a different target system or source of reference, leaving edit mode in Elements.
4. **A new target system or source of reference:** find and record it as card 01 steps 2 and 3 do (`list_reference_models` for an org), update `slots`, record it in `decisions_log`, clear `review` and `deliverables` to their template values and `evidence.gaps` to `[]`, and move what was gathered and derived for the old target aside so none of it is reused: `mv "$ENG/derive" "$ENG/derive-<YYYY-MM-DD>"`, `mv "$ENG/evidence" "$ENG/evidence-<YYYY-MM-DD>"`, and the same for `drawing` and `overview` when they exist (today's date). Maps already drawn for the old target stay in Elements as drafts; name them in `decisions_log` as superseded. The run then resumes at `map-checked`, whatever `entered_from` says.

## Outcomes, in precedence order

The first that holds wins.

- **TR-24 — The cause is resolved.** Write `current_state` as `blocked.entered_from` (or `map-checked` after step 4) and `current_step` as the card the dispatch table gives for it, as one edit, and clear `blocked`. Next card: that card.
- **TR-25 — Otherwise.** `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. The run waits here. Record the default call in `decisions_log` and tell the solution architect.

## Failure

When `blocked.entered_from` is empty or names no state of the dispatch table, ask the solution architect which stage to resume from, and use `scoped` when they cannot say.
