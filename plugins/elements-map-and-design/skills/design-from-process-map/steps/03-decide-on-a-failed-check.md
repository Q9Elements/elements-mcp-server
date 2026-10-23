# 03 Decide on a failed check

State: `check-failed`

## Purpose

Some levels of the map do not say clearly enough who does what to what, so a design derived from them would rest on guesses. The solution architect decides whether to go on anyway, fix the map first, or stop.

## Procedure

1. From `check/scores.json`, show each level below the pass mark: its title, its score against the pass mark, a link to the level (`url`), and each finding as the step or line it concerns, why it falls short (`why`, or for a script finding its rule, `rule_text`), and the suggested wording (`fix`) when there is one. Group the findings by level, shortest list first.
2. Ask the solution architect to choose, in one question:
   - **continue anyway**: the design is derived from the whole map as it is, and every deliverable says it is lower confidence;
   - **fix the map and resume**: they change the map in Elements and say when it is done; the run reads it again;
   - **stop for now**.
3. Record the choice in `decisions_log` with the scores as evidence.

## Outcomes, in precedence order

The first that holds wins.

- **TR-08 — The solution architect chooses to continue anyway.** Set `check.confidence` to `lower`. `{"current_state": "map-checked", "current_step": "steps/04-gather-target-evidence.md"}`. Next card: `steps/04-gather-target-evidence.md`.
- **TR-09 — The solution architect says the map is fixed.** `{"current_state": "scoped", "current_step": "steps/02-read-and-check-the-map.md"}`. Next card: `steps/02-read-and-check-the-map.md`.
- **TR-10 — Otherwise (they stop, or give no clear answer).** `{"current_state": "check-failed", "current_step": "steps/03-decide-on-a-failed-check.md"}`. Next card: `steps/03-decide-on-a-failed-check.md`. Tell them the run is paused here and resumes with this question. Record the default call in `decisions_log`.

## Failure

When `check/scores.json` is missing, the score never ran: write `{"current_state": "scoped", "current_step": "steps/02-read-and-check-the-map.md"}` and run card 02 again.
