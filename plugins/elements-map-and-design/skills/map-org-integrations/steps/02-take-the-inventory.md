# 02 Take the inventory

State: `scoped`

## Purpose

Collect, once and in bulk, the org metadata that shows another system talks to it (connected apps, remote sites, credentials, external services, platform events, managed packages), read where each one points, and turn it into a proposed list of outside systems, each with the evidence behind it.

## Procedure

On a resumed run, run the scripts in order and fetch only what their `ERROR` lines name.

1. Call `describe_metadata_schema` with no `metadataList`; keep its `types` (name, `salesforceName` and `aliases` of each).
2. For each row of `data/inventory-types.csv`: when step 1's `types` holds its `metadata_type` (by name, Salesforce name or alias), call `list_metadata_by_criteria` with `metadataList: ["<metadata_type>"]` and `columns: ["name", "api_name", "type", "description", "manage_package"]`, as pull `inventory-<type>` (the type lower-cased, spaces as `-`: `inventory-named-credential`), recorded and downloaded as the session contract says; otherwise record `"inventory-<type>": {"notSynced": true}` in `evidence/pulls.json`.
3. Call `list_managed_packages`; when `numPages` is more than 1, page with `skip` and join every page's `packages`. Save `{"packages": [...]}` as `evidence/packages.json`.
4. Run `python3 "$SKILL/scripts/inventory.py" source-ids "$ENG"`. For each batch in `evidence/source-ids.json`, call `get_metadata_source` with its `nodeIds`, recorded under its `pull` name and downloaded the same way.
5. Run `python3 "$SKILL/scripts/inventory.py" build "$ENG"`. Copy each `GAP` line into `open_items`. When it ends `NOT SYNCED`, stop here: TR-05.
6. Run `python3 "$SKILL/scripts/resolve_systems.py" propose "$ENG"`.
7. When it ends `CLASSIFY`, run `python3 "$SKILL/scripts/resolve_systems.py" build "$ENG" --check`; when it prints `CLASSIFIED OK`, the classifier's file from an earlier session stands: skip the agent. Otherwise (it prints ERROR or SETUP), run the `system-classifier` agent with `pluginRoot`, `eng` (`$ENG`) and `outputPath` (`$ENG/systems/classified.json`).
8. Run `python3 "$SKILL/scripts/resolve_systems.py" build "$ENG"`. Send its `ERROR` lines back to the agent as `findings` and build again, at most `fix_rounds` times (`data/limits.csv`).
9. Record in `decisions_log` how many systems were proposed from the known-systems list and from the classifier, and each classifier call at `low` confidence with its reason.

## Outcomes, in precedence order

The first that holds wins.

- **TR-04 — A pull cannot be completed: a call fails, or parts are still missing after a fresh call.** Record the pull and the error in `blocked` (`entered_from: "scoped"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`.
- **TR-05 — `inventory.py build` ends `NOT SYNCED` (exit 4).** Record in `blocked` that this reference model syncs none of the metadata that proves an outside system (`entered_from: "scoped"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`.
- **TR-06 — `resolve_systems.py build` ends `PROPOSED`.** `{"current_state": "systems-proposed", "current_step": "steps/03-confirm-the-systems.md"}`. Next card: `steps/03-confirm-the-systems.md`.
- **TR-07 — Otherwise (the classifier's file still fails after its fix rounds).** Record the remaining `ERROR` lines in `blocked` (`entered_from: "scoped"`). `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card: `steps/08-blocked-recovery.md`. Record the default call in `decisions_log` and tell the architect.

## Failure

`REFUSED` (exit 1) from `inventory.py`: fetch what its `ERROR` lines name (a fresh call for expired links) and run it again. A `SETUP` line (exit 2): fix the file it names and run the step again. The state stays at `scoped` until `resolve_systems.py build` has run.
