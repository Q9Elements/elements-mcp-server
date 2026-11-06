---
name: draw-interaction-flow
description: "Draws a validated model of Salesforce automations as an Elements interaction flow, then checks the layout: one automation as its logic (a card per step: Get Records, Decision, Loop, Update Records...), or a chain as a card per automation with each one's logic in a child level. Called once explain-automation, trace-automation-chain or another reader has written the model. Not for working out what an automation does, editing an existing map, or other diagram types."
user-invocable: false
---

# Draw an interaction flow

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

Input: a model file in the format of `schemas/ba-model.schema.json` with automations, and their steps and connectors, interactions or both. Output: a new draft interaction flow map in the active Elements space, every level laid out by the house style, and a review verdict.

The layout is computed by a script, not by you: `scripts/layout_interaction.py` decides what goes on which level, places the cards with the process-map engine, chooses the side every line leaves and enters, sizes the cards as the server does, and splits the writes into `manage_diagram` batches. Your job is to run it, carry each batch to Elements exactly as given, save what comes back, and report. [The interaction flow conventions](references/interaction-conventions.md) explain the cards, the header icons, the lines and what the drawing cannot do.

Follow the plugin's [drawing protocol](../../references/drawing-protocol.md) with `<script>` = `scripts/layout_interaction.py`. This file adds only what is particular to interaction flows, above all the header icons.

Paths: this file's folder holds `references/`; the plugin root is two levels up and holds `scripts/`, `data/`, `schemas/`, `agents/` and `references/`.

**Header icons are standard Elements resources** (Flow, Apex, Workflow, Start, Decision, Assignment and the other flow elements; [conventions](references/interaction-conventions.md) section 2). The run never adds one to the space library, `--create-resources` included: an icon added that way becomes a custom resource that hides the standard one in every later drawing.

## 1. Check the model

Validate with `--for interaction-flow` (protocol section 1). Work folder: the one the calling skill passes (`explain-automation` and `trace-automation-chain` pass `$WORK/drawing`); for a model file on its own, `<model name>-drawing/` next to it.

## 2. Plan the layout

`python3 <plugin>/scripts/layout_interaction.py plan MODEL --workdir DIR`, adding as needed:

- `--skip metadata` when the active space has no connected Salesforce org, or a dry run reports `org_not_connected`, `metadata_not_found` or `metadata_no_access`. Plan again before anything is written.
- `--drop-icons "Name,Name"` only after the user has agreed to draw without standard icons the space lacks (see `resource_not_found` below).
- `--allow-custom-icons` only after the user has agreed to draw with custom icons where the space library holds a custom resource named like a standard icon (see `fix-preflight` below).

What to tell the user about the plan: whether it is a logic map (one automation) or a chain map, and how many levels (the first line of the summary gives both). The `WARN` lines particular to interaction flows include a level over 12 cards, a main path that wraps onto a second row, a chain line with no step to leave from, a step with no header icon, long labels, and cards over 260 px tall.

## 3. Write the map

The protocol's write loop, with these further actions:

| `action` | Do |
|---|---|
| `preflight` | Send `manage_diagram` with `arguments` (always a dry run: it adds every header icon and library attachment once to throwaway cards). Nothing is written. |
| `fix-preflight` | The space cannot take part of the model. Follow `how`, then validate and plan again into the same folder: nothing has been written yet, the map already created is reused, and the preflight runs again, also after a fix made only in the space. When it has `standardIcons`, `shadowed` lists header icons the space library also holds as custom resources of the same name (`libraryType`, often Industry): `manage_diagram` matches resources by name only, so the cards would get the custom icons. Tell the user the names and ask whether to remove those custom entries from the space's resource library in Elements first, or to draw with the custom icons (`--allow-custom-icons`). `missing` lists standard icons the space does not have: see `resource_not_found` below. |
| `library-batch`, `library-cleanup` | Not returned for an interaction flow: every resource on its cards is a standard header icon, which the run never adds to the library. |

Errors particular to interaction flows:

- `resource_not_found` (the preflight finds these): a header icon is not in the space's library. The standard icons are in every space Elements has seeded; when one is missing, show the user the name with the close matches the issue lists. When the user agrees to draw without it, plan again into the same folder with `--drop-icons "Name,Name"`: those cards are drawn without a header icon and the plan prints a `DROPPED` line for each icon. Edit `data/automation-elements.csv` or `data/automation-types.csv` only if the user wants the change for every run.
- `resource_type_differs` on a header icon: the space library holds a custom resource of that name. The preflight stops on it (`fix-preflight` above) unless the run was planned with `--allow-custom-icons`.

## 4. Check and report

Check with the protocol (layout rubric rows R13–R17; `diagramType` `interaction-flow`). In the report, name the header icons drawn without their icon (the plan's `DROPPED` lines) and, when the run was planned with `--allow-custom-icons`, the header icons drawn as custom resources (the `resource_type_differs` warnings), and tell the user what the drawing cannot do, from section 5 of [the conventions](references/interaction-conventions.md).
