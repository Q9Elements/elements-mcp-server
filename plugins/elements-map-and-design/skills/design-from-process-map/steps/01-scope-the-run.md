# 01 Scope the run

State: `not-started`

## Purpose

Agree with the solution architect, in one sitting, which process map the design comes from, which system it is for, and what it is matched against: the Salesforce org connected to Elements, or the vendor's official documentation.

## Procedure

1. Call `get_space_context`. Use the `active` space. When it is null and several spaces are authorized, ask which one first, with the names it lists. Keep its `teamId`.
2. Call `list_reference_models`. Keep the list for step 3.
3. Ask the solution architect, in one message:
   - which process map the design comes from (a name or a link);
   - the target system: vendor and product, such as "Salesforce Sales Cloud" or "Microsoft Dynamics 365 Sales";
   - for a Salesforce target, whether to match against the org connected to Elements (name the reference models from step 2) or against Salesforce's documentation only;
   - their name, for the document and the approvals;
   - optionally, the customer's name and a logo file for the document's title page.
   Say what happens when they leave something out: no org choice means documentation; the project name is the map's name.
4. Find the map: `list_process_maps` with `query` from their words. When several match, ask once which one, by name. Keep its `mapId` and `name`.
5. Once the map is found and a target system is named, create the engagement directory in the working directory: `<map name>-design-from-process-map/`, the name lower-cased with spaces and punctuation as `-`. When that folder exists and holds a state file at `not-started` (a session that stopped in this card), fill that state file instead of creating a folder. When it exists otherwise, put a number before the tail: `<map name>-2-design-from-process-map/`, `<map name>-3-design-from-process-map/` and so on. Copy `templates/execution-state.json` into the new folder and fill: `engagement.name` (the project name), `engagement.started` (today), `slots.source_map` (`map_id` and `name` from step 4), `slots.space_id`, `slots.target_system`, `slots.reference_source` (`org` or `documentation`), `slots.ref_model_id` (copied from step 2, org only), `slots.customer_name`, `slots.customer_logo` (an absolute path), `slots.project_name`, `slots.prepared_by` (their name).
6. Record in `decisions_log` each value the solution architect gave and each default taken.

## Outcomes, in precedence order

The first that holds wins.

- **TR-02 — The map cannot be found or opened in the space, or the solution architect names no target system.** Nothing is written: the state file does not exist yet. Say what is missing and ask again in the same sitting; the run stays at `not-started`. Next card: `steps/01-scope-the-run.md`.
- **TR-01 — The map is found, and the target system and source of reference are recorded.** `{"current_state": "scoped", "current_step": "steps/02-read-and-check-the-map.md"}`. Next card: `steps/02-read-and-check-the-map.md`.
- **TR-03 — Otherwise.** Take the defaults of step 3 for what is unanswered and record them. `{"current_state": "scoped", "current_step": "steps/02-read-and-check-the-map.md"}`. Next card: `steps/02-read-and-check-the-map.md`. Record the default call in `decisions_log` and tell the solution architect.

## Failure

When the Elements tools do not answer, tell the solution architect what is needed (the Elements connection, access to the space) and stop; nothing is written, so the next session starts this card again.
