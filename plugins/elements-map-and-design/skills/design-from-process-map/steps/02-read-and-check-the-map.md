# 02 Read and check the map

State: `scoped`

## Purpose

Read every level of the source map into the run, and check each level can carry a design: who does each step, what each step does to what, and what each step produces.

## Procedure

1. Call `get_process_map_outline` with `mapId` (`slots.source_map.map_id`). While `status` is `running`, call again with the same arguments. When `hasMore` is true, page with `skip` and keep every item. Save the whole answer, with every item, as `levels/outline.json`.
2. For every item of the outline, call `get_diagram` with its `diagramId` and `include: ["all", "layout"]` and `delivery: "file"` with selected teamId, and save the whole answer as `levels/<levelNumber>.json`. Copy the top level's `diagramUrl` into `slots.source_map.url`.
3. Run `python3 "$SKILL/scripts/read_process_map.py" build "$ENG"`. `REFUSED` names levels with no saved read: read them as in step 2 and run it again.
4. Run `python3 "$SKILL/scripts/check_process_map.py" check "$ENG"`.
5. Run the `process-quality-assessor` agent with `pluginRoot`, `eng` (`$ENG`) and `outputPath` (`$ENG/check/wording.json`). It returns the wording findings for every level.
6. Run `python3 "$SKILL/scripts/check_process_map.py" score "$ENG"`. Exit 1 (`REFUSED`): send its `ERROR` lines back to the agent as `findings` and score again, at most twice.

## Outcomes, in precedence order

The first that holds wins.

- **TR-04 — A level cannot be read (no access, being copied, not found), or its findings still do not fit after two rounds.** Record the level and the reason in `blocked` (`entered_from: "scoped"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`.
- **TR-05 — The score ends with `FAILED`: one or more levels are below the pass mark.** `{"current_state": "check-failed", "current_step": "steps/03-decide-on-a-failed-check.md"}`. Next card: `steps/03-decide-on-a-failed-check.md`.
- **TR-06 — The score ends with `ALL PASS`.** Set `check.confidence` to `normal`. `{"current_state": "map-checked", "current_step": "steps/04-gather-target-evidence.md"}`. Next card: `steps/04-gather-target-evidence.md`.
- **TR-07 — Otherwise.** `{"current_state": "check-failed", "current_step": "steps/03-decide-on-a-failed-check.md"}`. Next card: `steps/03-decide-on-a-failed-check.md`. Record the default call in `decisions_log` and tell the solution architect.

## Failure

A `SETUP` line (exit 2): fix what it names and run the step again, except a map still being copied, which is TR-04. The state stays at `scoped` until the score has run on every level.
