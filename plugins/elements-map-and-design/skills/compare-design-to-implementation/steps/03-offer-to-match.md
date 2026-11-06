# 03 Offer to match

State: `links-missing`

## Purpose

Some boxes have no metadata linked, so they cannot be compared yet. The analyst decides whether the playbook interprets each such box by its name and content and proposes the org components that implement it. Nothing is written to the map here: the proposal goes to the analyst first.

## Procedure

1. When `checks.match_offer_answer` is null: show the unlinked boxes by level, as `coverage` printed them, and ask once whether to propose links for them (objects, fields, record types and the automations that do each step), saying that nothing is linked until they approve the proposal. Record the answer in `checks.match_offer_answer` (`yes` or `no`) and in `decisions_log`.
2. On `no`, take TR-08.
3. On `yes`, run the matching for round N, N being `match.round`. On a resume, start at the first command of the round whose files are missing.
   1. Run `python3 "$SKILL/scripts/match.py" terms "$ENG"`. For each search it prints, call `search_metadata` with its `queries`, the `limit` it gives and `refModelId`, and save the answer whole as `match/round-N/<id>.json`.
   2. Run `python3 "$SKILL/scripts/match.py" objects "$ENG"`. When it prints `OBJECTS`, make the calls it lists: `get_dependencies` with `lookingFor: "where_used"`, the `nodeIds` from `match/round-N/objects.json` and `attributes: ["description", "status"]`, saving the parts as the pull it names (the session contract); and for each object, `list_metadata_by_criteria` for its fields with the filter and columns it prints, saving the parts as the pull it names.
   3. Run `python3 "$SKILL/scripts/match.py" briefs "$ENG"`. Run one `metadata-matcher` agent per brief it lists, all at once, each given `pluginRoot`, `eng`, `brief` (`$ENG/match/round-N/briefs/<level>.json`) and `outputPath` (`$ENG/match/round-N/found/<level>.json`), as absolute paths. When one returns, run `python3 "$SKILL/scripts/match.py" check "$ENG" "$ENG/match/round-N/found/<level>.json"`; on `ERROR` lines, run the agent once more with them as `findings`.
   4. Run `python3 "$SKILL/scripts/match.py" next-round "$ENG"`; on `ERROR` lines, run that level's agent once more with them as `findings`. On `ANOTHER ROUND`, set `match.round` to N + 1 and run this step again from 3.1.
4. Run `python3 "$SKILL/scripts/match.py" table "$ENG"`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-08 — The analyst said no.** `{"current_state": "links-settled", "current_step": "steps/06-assess-the-boxes.md"}`. Next card: `steps/06-assess-the-boxes.md`. Tell the analyst the unlinked boxes stay uncompared and show as not assessed in the report.
- **TR-07 — The analyst said yes and `table` printed `PROPOSED`.** `{"current_state": "links-proposed", "current_step": "steps/04-review-the-links.md"}`. Next card: `steps/04-review-the-links.md`.
- **TR-09 — Otherwise (no answer yet, or the matching is not finished).** `{"current_state": "links-missing", "current_step": "steps/03-offer-to-match.md"}`. Next card: `steps/03-offer-to-match.md`. Tell the analyst what the run waits for. Record the default call in `decisions_log`.

## Failure

When `coverage.json` is missing, card 02 did not finish: write `{"current_state": "scoped", "current_step": "steps/02-read-the-design.md"}` and say why. When a matcher's answer still fails `check` after its second run, add the level and the `ERROR` lines to `open_items` and run a fresh agent once more with them as `findings`. When that fails too, tell the analyst which level could not be matched, with the lines, and stay at `links-missing`; the run resumes here once the agent's answer passes.
