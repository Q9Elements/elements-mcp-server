# 05 Derive the data model and the integrations

State: `evidence-gathered`

## Purpose

Work out, from the process, the data it handles and the systems it touches: the logical entities matched to the target system's objects as standard, custom or proposed, and the systems with the integrations between them, each with a Salesforce Well-Architected pattern.

## Procedure

1. For each section whose file exists (`derive/data-model.json`, `derive/integrations.json`), run `python3 "$SKILL/scripts/design.py" check-section "$ENG" data-model` (or `integrations`). A section that prints `SECTION OK` is already derived (a resumed run): skip its agent. A section whose file does not exist, or that does not print `SECTION OK`, needs its agent.
2. Run the agents still needed, in parallel, each with `pluginRoot`, `eng` (`$ENG`), `targetSystem` (`slots.target_system`), `route` (`slots.reference_source`) and `outputPath`:
   - `data-model-deriver`, `outputPath` `$ENG/derive/data-model.json`;
   - `integration-deriver`, `outputPath` `$ENG/derive/integrations.json`.
3. Run `check-section` for both. Send a section's `ERROR` lines back to its agent as `findings`, at most twice.
4. Run `python3 "$SKILL/scripts/design.py" merge "$ENG"`. Route each `ERROR` line by what it is about, whatever its prefix (`data-model:` or `system-architecture:`): entities or relationships to the data model agent, systems or integrations to the integration agent. Send a line printed under both prefixes once. Then merge again; at most two rounds.
5. Record in `decisions_log` the calls the agents made, as counts with examples: entities standard, custom and proposed; systems and integrations existing and proposed; middleware placed; each agent's gaps.

## Outcomes, in precedence order

The first that holds wins.

- **TR-13 — The merge ends with `MERGED` (exit 0).** `{"current_state": "structure-derived", "current_step": "steps/06-derive-the-access-matrix.md"}`. Next card: `steps/06-derive-the-access-matrix.md`.
- **TR-14 — Otherwise (a section or the merge still fails after two rounds).** Record the remaining `ERROR` lines in `blocked` (`entered_from: "evidence-gathered"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`. Record the default call in `decisions_log` and tell the solution architect.

## Failure

A `SETUP` line naming `process-model.json` means card 02 did not finish: write `{"current_state": "scoped", "current_step": "steps/02-read-and-check-the-map.md"}` and say why. A missing `evidence/targets.json` (the agents read it) means card 04 did not finish: write `{"current_state": "map-checked", "current_step": "steps/04-gather-target-evidence.md"}`.
