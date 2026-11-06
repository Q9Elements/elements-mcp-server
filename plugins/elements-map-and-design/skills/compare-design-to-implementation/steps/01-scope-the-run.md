# 01 Scope the run

State: `not-started`

## Purpose

Agree with the analyst which design is checked: one map in their Elements space, and either the whole map or one level of it with the levels beneath, and which of the space's synced orgs (reference models: production or a sandbox) it is compared against. A request to reset the colours of a design checked earlier is scoped here too, when its engagement directory cannot be found.

## Procedure

1. Call `get_space_context`. Use the `active` space. When it is null and several spaces are authorized, ask which one, with the names it lists. Keep its `teamId`.
2. **Find the map.**
   - A link or id: a link holds `/diagram/<diagramId>`; call `get_diagram` with that `diagramId` and `detail: "summary"`, and keep its `mapId` and `levelNumber`. A bare id is a `mapId` when `get_process_map_outline` finds it, else a `diagramId`.
   - Words ("our lead qualification process"): call `list_process_maps` with `query` set to each distinctive word or phrase of the request, one call each (`limit` 20). Exactly one map whose name is the one the request gives: take it and say which. Otherwise list the matches by name and type and ask which, in the kickoff message of step 6; none: say so, list the space's maps with `list_process_maps` and no query (`limit` 50), and ask. While the map is not settled, go to step 6.
3. Call `get_process_map_outline` with the `mapId` and `limit` 200 (with `skip` for every further page); its `name` is the map's name. Call `list_process_maps` with `query` set to that name and keep the row whose `mapId` is the map's: its `type`, `subtype` and `canEdit`.
4. **Create the engagement directory** in the working directory: `<map name>-design-check/`, the name lower-cased with spaces and punctuation as `-`. When that folder holds a state file at `not-started`, fill that one instead; when it exists otherwise, add a number before the tail (`<map name>-2-design-check/`). Copy `templates/execution-state.json` into it, and save every outline page's `items` joined, with the map's `mapId` and `name`, as `levels/outline.json`: `{"mapId", "name", "items": [...]}`.
5. **Settle the scope and the org.** For a reset, the scope is `map` unless the request names a level, and the reference model is not needed (leave it null): skip the rest of this step.
   - The request pointed at one level (a link to a level below the top, or a level named): the scope is that level's `levelNumber`, with every level beneath it. The map has one level: the scope is `map`. Otherwise ask whether to check the whole map or one level, listing the levels by number and title (at most 20, then "and N more").
   - **The org to compare against.** A link on a box ties it to one component in every org the space syncs, production and each sandbox alike, so the links do not say which org's build is judged; the analyst does. Call `list_reference_models` (with `teamId`). One listed: that is the reference model; say which org it is. Several: when the request names one of them (by name or org id), take it; otherwise ask which org the design is compared against, listing each by `name`, `implementation.name`, `orgId` and when it was last synced (`updatedAt`). As a hint, read the top level in scope with `get_diagram` (`include: ["metadata"]`) and say which of them its links were made in (their `refModelId`); a hint never settles it.
   - A level in scope whose outline `lock` names a holder: tell the analyst who has it open, since writes to it will wait until they close it.
6. Ask every open question of steps 2 and 5 in one message.
7. Fill the state file: `slots.space_id`, `slots.map_id`, `slots.map_name`, `slots.map_url` (the top level's link, `https://<host>/diagram/<diagramId>?v=draft` from the answer's `diagramUrl`), `slots.scope`, `slots.ref_model_id` and `slots.ref_model_name` (copied from the answers), `slots.can_edit` (from step 3), `engagement.name` (the map name) and `engagement.started` (today). Record the map, scope and org chosen, and who chose them, in `decisions_log`.

## Outcomes, in precedence order

The first that holds wins.

- **TR-02 — The request is to reset the colours of this map, and the map is settled.** Set `slots.scope` to `map` unless the request names a level. `{"current_state": "coloured", "current_step": "steps/09-keep-or-reset.md"}`. Next card: `steps/09-keep-or-reset.md`.
- **TR-01 — The map, the scope and the org are settled, the engagement directory is created with its slots filled and `levels/outline.json` saved.** `{"current_state": "scoped", "current_step": "steps/02-read-the-design.md"}`. Next card: `steps/02-read-the-design.md`.
- **TR-03 — Otherwise (a question of step 6 is unanswered).** Nothing more is written; when the state file exists, `{"current_state": "not-started", "current_step": "steps/01-scope-the-run.md"}`. Next card: `steps/01-scope-the-run.md`. Tell the analyst the check waits for their answer. Record the default call in `decisions_log` when the state file exists.

## Failure

When the Elements tools do not answer, tell the analyst what is needed (the Elements connection, access to the space) and stop; nothing is written, so the next session starts this card again. When no reference model is listed, say that a design can only be compared once its org is synced in Elements, and stop at `not-started`.
