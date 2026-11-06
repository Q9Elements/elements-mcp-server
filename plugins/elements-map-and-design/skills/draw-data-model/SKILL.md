---
name: draw-data-model
description: "Draws and amends Elements data models (entity-relationship diagrams): a card per object with its key fields and API name, crow's-foot relationship lines, parents above children; then checks the result. Builds the model from Salesforce objects named in the Elements Metadata Dictionary, takes a model file, or reads an existing data model to add or remove objects, fields and relationships, change line ends or tidy the layout. Use for \"draw the data model (ERD) of these objects\". Not for designing new objects or other diagram types."
user-invocable: false
---

# Draw or amend a data model

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

A data model in Elements is a map of type `data_model` with one level. Each object is a card: its name, its key fields as attributes, its API name as the footer, coloured by kind. Each relationship is a line from the "one" end to the "many" end with an entity-relationship end symbol at each card. `references/data-model-conventions.md` explains every drawing rule and why; read it when you need to explain a choice, a warning or a limit to the user.

The layout and every write are computed by scripts, not by you: `scripts/layout_data_model.py` places the cards, chooses the sides each line joins, picks the line ends (`data/relationship-ends.csv`, `data/er-line-ends.csv`) and colours (`data/entity-kinds.csv`), and splits the writes into `manage_diagram` batches. Your job is to get the model right, run the scripts, carry each step to Elements exactly as given, save what comes back, and report.

Follow the plugin's [drawing protocol](../../references/drawing-protocol.md) with `<script>` = `scripts/layout_data_model.py`. This file adds the model-building steps and what is particular to data models.

Paths: this file's folder holds `references/`; the plugin root (`<plugin>` below) is two levels up and holds `scripts/`, `data/`, `schemas/`, `agents/` and `references/`. Run scripts with `python3`, giving full paths.

Copy this checklist and tick each step:

```text
- [ ] 0. Pick the job
- [ ] 1. Build the model from the org (1a), take a model file (1b) or read the map to amend (1c)
- [ ] 2. Validate; fix and re-run until it passes
- [ ] 3. Plan, and tell the user what it will do
- [ ] 4. Write, one `next` step at a time
- [ ] 5. Check and report
```

## 0. Which job

| The user | Job | Start at |
|---|---|---|
| names Salesforce objects, an object and its related objects, or an app's objects | New map from the org | 1a |
| gives or points at a model file (another skill wrote it) | New map from a model | 1b |
| names an existing data model and wants it changed or tidied | Amend | 1c |

Work folder (`DIR` below): the one the calling skill names (design-from-process-map passes one per model), otherwise `<subject>-data-model/` (protocol section 1).

## 1a. Build the model from the org

Follow `references/org-route.md`. In short: resolve the objects with `search_metadata`, save them as `objects.json`, download their relationship fields (`get_dependencies`) and their fields (`list_metadata_by_criteria`), and run `scripts/build_data_model.py build`. Then:

- run `build_data_model.py neighbours` and offer the user the top related objects they did not name, in one question (they may add some, then build again);
- ask whether any object should be drawn as proposed (not built yet) or external (another system), only if they mentioned such objects; set `kind` in the model.

## 1b. Take a model file

The model follows `schemas/ba-model.schema.json` with `entities` and `relationships`. Nothing to do here but step 2.

## 1c. Read the map to amend

1. Find the map: `list_process_maps` with a `query` from the user's words. Confirm the one you found by name; it must be type `architecture`, subtype `data_model`, and `canEdit` must be true (otherwise tell the user they need edit rights).
2. Read its level: `get_diagram` with `diagramId` and `include: ["layout"]` and `delivery: "file"` with selected teamId. Save the whole result as `DIR/read.json`.
3. Turn it into a model: `python3 <plugin>/scripts/layout_data_model.py from-diagram DIR/read.json --out DIR/model.json`. Tell the user any `GAP` line (a line end the model cannot hold is left as it is).
4. Make the user's change in `DIR/model.json`, editing the JSON directly:
   - **Line ends.** Find the relationship by its two entity ids and set `fromEnd` or `toEnd` (the end at the `from` or `to` entity) to one of `zero-or-one`, `exactly-one`, `one`, `zero-or-many`, `one-or-many`, `many`, `none`. "Every contact must have an account" is `exactly-one` at Account; "an order has at least one line" is `one-or-many` at the line item. Keep a many end only where the cardinality says many (the validator warns otherwise, rule R31); change `cardinality` too when the user changes which side is many.
   - **Fields.** Add, remove or reorder the entity's `fields`. Mark the identifying field `"key": "primary"`, relationship fields `"key": "foreign"`.
   - **New objects from the org.** Build a model with `references/org-route.md` for the new objects together with the objects already on the map (so relationships between them are found), writing it with `--out DIR/addition.json` so it does not overwrite the amended model, then `python3 <plugin>/scripts/build_data_model.py merge DIR/model.json DIR/addition.json --out DIR/model.json`.
   - **New objects the user describes** (not in the org): add an entity with `"kind": "proposed"` and the relationships the user gives.
   - **Removals.** Delete the entity, field or relationship from the model. Removals are only written with `--allow-remove` (step 3).

## 2. Check the model

Validate (protocol section 1): `python3 <plugin>/scripts/validate.py MODEL --for data-model`, where `MODEL` is the model file. Fix errors in the model, or send it back to whoever wrote it, and re-run until it passes. For warning R30 (more than 30 objects), suggest splitting the map by area.

## 3. Plan

**New map:** `python3 <plugin>/scripts/layout_data_model.py plan MODEL --workdir DIR`, adding as needed `--max-fields N` (fields per card, default 6; `0` draws names only), `--no-api-names`, `--no-legend` (no Key card), `--label-fields` (label every line with its field), `--skip metadata,story,link,note`, `--name "TEXT"`.

**Amend:** `python3 <plugin>/scripts/layout_data_model.py amend DIR/model.json --read DIR/read.json --workdir DIR`, with the same field options, plus:

- `--allow-remove` only after the user has confirmed, by name, the cards, lines and fields the plan lists as `KEEP` and wants them gone, because it deletes them from the diagram;
- `--relayout` when the user asks to tidy the whole diagram, or the plan warns that a card will grow over another. It moves every card and re-routes every line; keys, attachments and anything else on the cards stay.

What to tell the user about the plan (protocol section 2):

- new map: how many cards and lines, and whether a Key card is drawn;
- amend: each `ADD`, `UPDATE` and `REMOVE` line, and each `KEEP` line (what stays on the diagram because the model no longer has it, and that it can be removed on request);
- the `WARN` lines here are fields not shown, a long name, a card that will grow over another, and a large model.

Offer `DIR/preview.svg`: a picture of the planned layout. Elements routes each line the same way the preview draws it, so it is a faithful preview of lines and positions (Elements' own theme sets the final colours).

## 4. Write

The protocol's write loop; data models use only its common actions. One error is particular to them:

- `position_out_of_bounds`: the plan keeps every card inside the canvas as it grows, so this error is unexpected. Read the level with `include: ["layout"]` and `delivery: "file"` with selected teamId, stop and tell the user. Leave the cards where they are: a card moved by hand no longer matches the plan, and the check fails it (R32).

## 5. Check and report

Check with the protocol (layout rubric rows R32-R34: positions and overlaps, every card's fields and footer, every line between the right cards with the planned ends, lines running through cards; `diagramType` `data-model`; `levels` is `DIR/review/top.json`).

What the drawing does not do (detail in `references/data-model-conventions.md` section 5): every card is 200 px wide, so a hub object is not stretched into a long bar as in the hand-made exemplars; lines join the middle of a card's side, and Elements chooses each line's bends; a line carries one label, not a role at each end; a card whose name or fields wrap may grow taller when opened in the editor.

Saved reads also accept subtype dataModel; creation uses data_model.
