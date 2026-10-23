# 01 Scope the run

State: `not-started`

## Purpose

Agree with the architect which org the landscape is drawn from: one of the reference models (synced copies of a Salesforce org) in their Elements space.

## Procedure

1. Call `get_space_context`. Use the `active` space. When it is null and several spaces are authorized, ask which one first, with the names it lists. Keep its `teamId`.
2. Call `list_reference_models`. When it lists one model, that is the one. When it lists several and the request does not name one, ask the architect which, in one message listing them by name; say in the same message that the map will be called "<model name> integration landscape" with the org card named after the model, unless they want other names.
3. Once the model is known, create the engagement directory in the working directory: `<model name>-org-integrations/`, the name lower-cased with spaces and punctuation as `-`. When that folder exists and holds a state file at `not-started`, fill that state file instead of creating a folder. When it exists otherwise, put a number before the tail: `<model name>-2-org-integrations/`, `<model name>-3-org-integrations/` and so on. Copy `templates/execution-state.json` into it and fill: `slots.space_id` (the `teamId`), `slots.ref_model_id` and `slots.ref_model_name` (copied from step 2), `slots.map_name` (the architect's, else "<model name> integration landscape"), `slots.hub_name` (the architect's, else the model name), `engagement.name` (the map name) and `engagement.started` (today).
4. Record in `decisions_log` the model chosen and each name, the architect's or the default.

## Outcomes, in precedence order

The first that holds wins.

- **TR-01 — No space or reference model is chosen yet: no reference model is listed, or several spaces or models are and the architect names none.** Nothing is written: the state file does not exist yet. Say what is missing (a reference model must be synced in this space) or ask again in the same sitting; the run stays at `not-started`. Next card: `steps/01-scope-the-run.md`.
- **TR-02 — The model is chosen and the engagement directory is created with its slots filled.** `{"current_state": "scoped", "current_step": "steps/02-take-the-inventory.md"}`. Next card: `steps/02-take-the-inventory.md`.
- **TR-03 — Otherwise (the model is chosen but a name was left unanswered).** Fill what is unanswered with the defaults of step 3. `{"current_state": "scoped", "current_step": "steps/02-take-the-inventory.md"}`. Next card: `steps/02-take-the-inventory.md`. Record the default call in `decisions_log` and tell the architect.

## Failure

When the Elements tools do not answer, tell the architect what is needed (the Elements connection, access to the space) and stop; nothing is written, so the next session starts this card again.
