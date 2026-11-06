# 04 Gather the target-system evidence

State: `map-checked`

## Purpose

Collect, once, what the derivation matches the process against: the objects that already exist in the target system and, for a connected org, the integrations it already has.

## Procedure

The route is `slots.reference_source`.

**Route `org`** (pass `refModelId` = `slots.ref_model_id` on every call):

1. Call `describe_metadata_schema` with no `metadataList`; keep its `types` names.
2. Call `list_metadata_by_criteria` with `metadataList: ["Standard Object", "Custom Object", "External Object"]` and `columns: ["name", "api_name", "type", "description", "record_count", "manage_package"]`. While `status` is `running`, call again with the same arguments. Record the pull `objects` in `evidence/pulls.json`: `{"tool": "list_metadata_by_criteria", "totalRows", "partsTotal", "parts": [{"index", "rows", "sha256"}]}`, copied from the answer (`totalRows` null when the answer gives none). Download every part with `curl -fsSL -o "$ENG/evidence/objects-<index>.ndjson" "<url>"` within its `expiresInSeconds`. When the answer lists fewer parts than `partsTotal`, call again with `partsFrom` set to `nextPartsFrom`, and add those parts to the same pull. Links that expired: call again with the same arguments for fresh ones.
3. Pull the fields the same way, as pull `fields`: `metadataList: ["Field"]`, `columns: ["name", "api_name", "full_api_name", "subtype", "required"]`, no filter.
4. For each `metadata_type` of `data/integration-evidence-types.csv`: when step 1's `types` holds it, pull it the same way with `metadataList: ["<metadata_type>"]` and `columns: ["name", "api_name", "type", "description"]`, as pull `integration-<slug>` (the type lower-cased, spaces as `-`: `integration-named-credential`); otherwise record `"integration-<slug>": {"notSynced": true}`.
5. Call `list_managed_packages`; when `numPages` is more than 1, page with `skip` and join every page's `packages` into one list. Save `{"packages": [...]}` as `evidence/packages.json`.
6. Run `python3 "$SKILL/scripts/prepare_evidence.py" "$ENG" --route org`.

**Route `documentation`:**

1. Run the `system-doc-reader` agent in `index` mode with `system` (`slots.target_system`), `variant` ("current release, out of the box"), `pluginRoot` and `outputPath` (`$ENG/evidence/doc-inventory.json`).
2. Run `python3 "$SKILL/scripts/prepare_evidence.py" "$ENG" --route documentation`.

Copy each `GAP` line into `evidence.gaps`.

## Outcomes, in precedence order

The first that holds wins; both follow a run of `prepare_evidence.py` that ended with exit 0 or 4.

- **TR-11 — It ends with `NO TARGET OBJECTS` (exit 4).** Record in `blocked` that no target objects were found (`entered_from: "map-checked"`). `{"current_state": "blocked", "current_step": "steps/10-blocked-recovery.md"}`. Next card: `steps/10-blocked-recovery.md`.
- **TR-12 — Otherwise.** `{"current_state": "evidence-gathered", "current_step": "steps/05-derive-data-model-and-integrations.md"}`. Next card: `steps/05-derive-data-model-and-integrations.md`. Tell the solution architect how many objects and how much integration evidence were found, and each gap.

## Failure

`REFUSED` (exit 1) or a `SETUP` line (exit 2): fix or fetch what it names (its `ERROR` lines, or the file the `SETUP` line names) and run the script again. The state stays at `map-checked` until the script runs clean.
