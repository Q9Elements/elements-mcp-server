---
name: draw-system-architecture
description: "Draws and amends Elements system architecture diagrams (system landscapes and solution architectures) in the Salesforce Well-Architected style: the hub in the centre, a card per system, an arrowed line per integration labelled with mechanism and timing, middleware, a drill-down per system and a key, with Well-Architected checks on every integration. Builds the model from a description, a solution design document, a picture of a diagram or a model file, or amends an existing diagram. Not for discovering integrations from org metadata (map-org-integrations)."
user-invocable: false
---

# Draw or amend a system architecture diagram

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

A system architecture diagram in Elements is a map of type `system_architecture`. Each system is a card: its product logo as the header icon, its name, its components as attributes, a footer sentence and footer icons. Each integration is a line with an arrow where the data arrives (at both ends when it flows both ways), labelled with how the data moves and when ("Data Activation · batch"). A group of systems (a Salesforce org holding Agentforce, Tableau Next and Data Cloud One) is one card with a drill-down level showing its members. `references/architecture-conventions.md` explains every drawing rule and why; read it when you need to explain a choice, a warning or a limit. `references/modelling-guide.md` explains how to turn what the user gives you into a model; read it before writing one.

The layout and every write are computed by a script, not by you: `scripts/layout_architecture.py` picks the hub, puts every other card in a zone around it (`data/architecture-zones.csv`), sizes the cards as the server does, chooses the side each line joins, picks icons (`data/system-icons.csv`), colours (`data/system-kinds.csv`) and timing words (`data/integration-timing.csv`), and splits the writes into `manage_diagram` batches. Your job is to get the model right, run the script, carry each step to Elements exactly as given, save what comes back, and report. Diagrams are drawn and changed through `create_map` and `manage_diagram` only: that write path never replaces a level whole, so the map stays amendable by this skill.

Follow the plugin's [drawing protocol](../../references/drawing-protocol.md) with `<script>` = `scripts/layout_architecture.py`. This file adds the model-building steps and what is particular to architecture diagrams.

Paths: this file's folder holds `references/`; the plugin root (`<plugin>` in commands) is two levels up and holds `scripts/`, `data/`, `schemas/`, `examples/`, `agents/` and `references/`. Run scripts with `python3`, giving full paths.

## 0. Which job

| The user | Job | Start at |
|---|---|---|
| describes systems and how they connect, or attaches a solution design, architecture document or picture of a diagram | New diagram from a description | 1a |
| gives or points at a model file (another skill wrote it) | New diagram from a model | 1b |
| names an existing system architecture diagram and wants it changed or tidied | Amend | 1c |

Work folder: the one the calling skill names (map-org-integrations and design-from-process-map pass one), otherwise `<subject>-architecture/` (protocol section 1).

## 1a. Write the model from a description

Follow `references/modelling-guide.md`. In short:

1. Decide with the user, in one question when it is not obvious, whether this is a **landscape** (the whole estate, products as cards, mechanisms on the lines) or a **solution** (one solution, components as attributes, numbered steps on the lines).
2. List the systems: `name` as people say it, `kind`, the `hub` (what the diagram is about), `attributes` for components, `footer`. Put systems that sit together in one org or product family under a group with `parent`.
3. List the integrations: `from` is where the data starts, `to` where it arrives; `direction: "two-way"` only when the source says data flows both ways. A verb such as "syncs" or "integrates", or what a product usually does, does not settle it: draw it one-way, from the system the source names as sending, and record the direction as a gap. Give `technology` (the mechanism people name), `pattern` from `data/integration-patterns.csv` when you can tell it, and `timing` when the source says it or the mechanism settles it (Bulk API is batch). Never invent a mechanism or timing, because the line states it as fact: leave it out when the source says nothing, and mark the integration `inferred` with its `evidence` when the source only implies it.
4. Write `meta.title` and a one-sentence `meta.description` that says the diagram's purpose, scope and message (Well-Architected asks every diagram for one).
5. Record in `gaps` what the source leaves open (an integration with no stated mechanism or direction, a system whose role is unclear).

Before drawing, show the user the systems and the integrations in two short tables (modelling guide section 6), and correct the model from their answer. Show only what the source states; anything you worked out (a `pattern`, a mechanism) is a question, not a column, and a timing word the user did not say ("batch" for "nightly") gets one line saying the drawing adds it.

## 1b. Take a model file

The model follows `schemas/ba-model.schema.json` with `systems` and `integrations`. Go to step 2.

A model another skill wrote may carry more than a description gives (the `map-org-integrations` playbook writes such models from org metadata):

- an integration's `via`: the middleware the data passes through. A middleware is drawn as its own card with the systems it carries joined to it, or, when it carries more than `middleware_fold_threshold` systems (`data/style-architecture.csv`) or its `placement` is `label`, as a "via" label on their lines;
- an integration's `automations` and `objects`, with the model's `automations`, `entities` and `interactions`: each system whose integrations list them gets a drill-down level showing, left to right, the system, the middleware, the automations and the objects (`references/architecture-conventions.md` section 7);
- metadata `attachments` on systems, automations and entities, each carrying the selected `refModelId`. Plan with `--drop-unresolved` when some may not resolve by API name: those links are left off their cards and listed when the write loop is done, instead of stopping the run.

## 1c. Read the diagram to amend

1. Find the map: `list_process_maps` with a `query` from the user's words. Confirm the one you found by name; it must be subtype `system_architecture`, and `canEdit` must be true (otherwise tell the user they need edit rights).
2. Read its top level: `get_diagram` with `diagramId` and `include: ["layout"]` and `delivery: "file"` with selected teamId; save the whole result as `read.json`. Read each drill-down level the same way (`get_process_map_outline` lists them) and save them as `read-<n>.json`.
3. Turn them into a model: `python3 <plugin>/scripts/layout_architecture.py from-diagram read.json [read-1.json ...] --out model.json`. Tell the user each `GAP` line (a kind guessed from the card colour, a line that does not join two system cards).
4. Make the user's change in `model.json`, editing the JSON directly: add a system (with `kind`, and `zone` if the user says where), add or change an integration (`technology`, `timing`, `direction`, `step`), rename, or delete. Removals are only written with `--allow-remove` (step 3).

Amending changes the top level. A new group card gets its drill-down; the members of a group that already has a drill-down are not changed (the plan warns): tell the user to change that level in Elements, or redraw the map. A system's drill-down of automations and objects is not read back (`from-diagram` reads groups only) and not changed.

## 2. Check the model

Validate with `--for system-architecture` (protocol section 1). The Well-Architected checks deserve a sentence each when they warn: R43 (Salesforce at the wrong end for the pattern), R44 (a mechanism Well-Architected rates suboptimal, with the recommended ones), R45 (a timing the pattern does not have). They are advice: the user may keep the design, and the diagram draws it as given.

## 3. Plan

**New diagram:** `python3 <plugin>/scripts/layout_architecture.py plan MODEL --workdir DIR`, adding as needed `--name "TEXT"`, `--no-key` (no Key card), `--no-headings` (no zone names), `--drop-icons "A,B"` (draw those cards without their icon), `--skip metadata,story,link,note`, `--drop-unresolved` (leave off any metadata link the space cannot resolve, and list it at `done`), `--create-resources` (only after the user agreed, see `fix-preflight` in step 4).

**Amend:** `python3 <plugin>/scripts/layout_architecture.py amend MODEL --read read.json --workdir DIR`, with `--drop-icons`, `--skip` and `--create-resources` as for a new diagram, plus:

- `--allow-remove` only after the user has confirmed, by name, the cards and lines the plan lists as `KEEP` and wants them gone;
- `--relayout` when the user asks to tidy the whole diagram, or the plan warns that a card will grow over another. It moves every card, the Key card included, to a fresh layout and re-routes every line; cards and lines keep their attachments, and zone headings stay where they are.

What to tell the user about the plan (protocol section 2):

- per level: how many cards and lines, which system is the hub, how many cards sit in each zone, and the drill-downs (groups, and systems with their automations and objects);
- amend: each `ADD`, `UPDATE` and `REMOVE` line, and each `KEEP` line;
- the `WARN` lines here are too many cards on a level, a long system name, a long label, more than three footer icons, and each middleware drawn as a label because it carries more systems than the threshold.

Offer `DIR/preview.svg` (and `preview-<group>.svg` per drill-down): a picture of the planned layout. Positions and sides are exact; Elements chooses each line's bends and places labels itself.

## 4. Write

The protocol's write loop, with these further actions:

| `action` | Do |
|---|---|
| `preflight` | Send `manage_diagram` with `arguments` (always a dry run: it adds every icon once to throwaway cards). Nothing is written. |
| `fix-preflight` | Some icons are not in the space's resource library (`missingIcons`). Follow `how`: ask the user, per icon, to use a close match from the message (set the system's `icon` in the model), to draw without it (`--drop-icons`), or to add it to the library as a name without a picture (`--create-resources`). Then validate and plan again into the same folder: nothing has been written yet, so the map already created is reused and the preflight runs again. |
| `library-batch`, `library-cleanup` | Only with `--create-resources`. Send `manage_diagram` with `arguments`; the cleanup removes the throwaway card with `"confirm": true` and needs no question. |

A group's drill-down line batch removes the lines `add child` seeded on that level and adds each again attached to the member it really joins, linked to its parent line. A system's drill-down removes them and draws its own lines between the system, middleware, automations and objects; none continues a line of the level above, because the hub is not on that level, so none is linked.

One error is particular to architecture diagrams:

- `position_out_of_bounds`: the plan follows the canvas as it grows, so the level differs from what the plan expects. Read the level with `get_diagram` and `include: ["layout"]` and `delivery: "file"` with selected teamId and tell the user; leave the cards where they are, because the check compares every position with the plan.

## 5. Check and report

Check with the protocol (layout rubric rows R48-R50: positions and overlaps; every card's icon, attributes and footer; every integration once between the right cards with the planned arrows and label; every group's drill-down and its linked lines; lines likely to run through a card; `diagramType` `system-architecture`). In the report, also give the validator's Well-Architected advice and the icons drawn without a logo.

What the drawing does not do (detail in `references/architecture-conventions.md` section 8): cards are 200 px wide and cannot be stretched or nested as containers, so a group is a card with a drill-down rather than a box around its members; lines join the middle of a card's side, so several lines into the hub meet at one point; Elements chooses each line's bends and centres its label on it; timing is a word in the label, not a clock icon; a card whose text wraps may grow taller when opened in the editor.

Saved reads also accept subtype systemArchitecture; creation uses system_architecture.
