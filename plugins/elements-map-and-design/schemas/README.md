# The business-architecture model

Every skill in this plugin either **works out what is true** about a business (by reading metadata, documents, tickets or an existing diagram) or **draws it** as an Elements diagram. The model is the file that passes between the two. Readers write it; drawing skills read it.

## Why there is one shared model

Without it, every source would need its own route to every diagram type: tickets to a process map, metadata to a process map, a process map to a data model, and so on. With five sources and six diagram types that is up to thirty separate pieces of logic, and a change to how data models are drawn would have to be made in each of them.

With one model in between, each reader is built once and each drawing skill is built once. A new source works with every existing diagram type straight away, and a new diagram type works with every existing source.

## What is in it

One JSON file. Every content section is optional; a model needs at least one item, or at least one gap when the reader found nothing.

| Section | Holds | Drawn on |
|---|---|---|
| `meta` | Title, who wrote the model, and its sources (required) | — |
| `roles` | People, teams, systems and AI agents that do the work | Process maps, journeys (as resources) |
| `activities` | Process steps or journey touchpoints; `parent` puts an activity on the child level of another; `uses` names the entities, systems and automations a step relies on | Process maps, journeys |
| `flows` | Lines between activities on one level; `START` and `END` mark how a level begins and ends; `sets` names the lifecycle value an entity has once the line's outcome holds | Process maps, journeys |
| `entities` | Data objects with the fields worth showing, and a `lifecycle` (the status or stage picklist the record moves through, its values in order) | Data models; process maps (as Object resources) |
| `relationships` | How entities relate: cardinality, kind (lookup, master-detail), the field that holds it, and optionally `fromEnd`/`toEnd` to override the line end drawn at either entity (`data/er-line-ends.csv`) | Data models |
| `systems` | Applications, middleware, data stores, channels; `hub` marks the one the diagram is about, `zone` pins a card's place, `parent` puts a system in a group (a card with a drill-down), `attributes` and `footer` fill its card | System architecture |
| `integrations` | How data moves between systems: `from` where it starts, `to` where it arrives, `direction`, the `technology` (the line's label), a `pattern` from `data/integration-patterns.csv`, `timing` and, in a solution, its `step` | System architecture |
| `automations` | Flows, Apex, OmniScripts and other automation, each with a short `summary` and card `attributes` | Interaction flows (one card each on the chain level) |
| `interactions` | What triggers, calls, reads, writes or publishes what, in order; a role can start a chain. `START` and `END` mark where the chain begins and ends; `fromStep` names the step of the `from` automation that causes the line | Interaction flows (the chain level) |
| `steps` | One automation's logic, a card per step: `element` is its kind from `data/automation-elements.csv` (Get Records, Decision, Loop...), `parent` puts it in the drill-down of another step (a loop's body), `calls` names the automation a subflow or action runs | Interaction flows (one logic level per automation) |
| `connectors` | Lines between steps on one level, with a `kind` (next, outcome, default, fault, loop-each, loop-done, scheduled, goto); `START` and `END` as on flows | Interaction flows |
| `capabilities` | A tree of what the business can do; `realisedBy` points at the items that deliver each one. For drawing: `rating` (a value of a scale in `data/capability-ratings.csv`, shown as the box colour), `placement` (`band` for a full-width layer below the columns, with `bandRow` to share a row), `childrenAs` (`list` draws sub-capabilities as lines of text) and `icon` (a library resource as header icon) | Capability maps |
| `drivers` | The business goals or problems the capabilities serve, each with a short `description` | Capability maps (a band of cards across the top) |
| `levelNotes` | Sticky notes about a level as a whole: `parent` names the level (as an activity's parent does), `near` the box the note sits beside (step 1 when left out), then a short `title` and `text`; `purpose` says what wrote it (`usage`: how much the org uses the object or record type the level follows) | Process maps, journeys (a note beside the box) |
| `gaps` | What the reader could not establish, and why | Reported to the person, never drawn as fact |

`data/diagram-types.csv` lists which sections each diagram type needs and uses. The full field list, with a description of every field, is in [`ba-model.schema.json`](ba-model.schema.json). A complete worked model is in [`../examples/lead-to-opportunity.json`](../examples/lead-to-opportunity.json).

A metadata attachment identifies its item with `apiName`, `metadataType` whenever the source supplies the type, and the run's selected `refModelId`. A field uses `Object.Field`. Drawers send `refModelId` on `manage_diagram` `add attachment`, so names shared by reference models resolve within the selected model. The field is optional in saved models; every drawer fills it at planning from the drawing's connection or the run's execution state, scope or trace. On resume, a saved plan with a metadata attachment missing `refModelId` stops and asks the user to start that drawing again from the model in a new drawing folder with the selected reference model. See [drawing protocol](../references/drawing-protocol.md) for context locations and resume rules. `nodeId` records provenance for reporting; the server resolves attachments by name, type and reference model.

## Rules for whoever writes a model

- **Ids are unique across the whole model**, not just within a section, so any reference is unambiguous. Use short readable ids such as `qualify` or `opp-trigger`.
- **Refer to other items by id**: an activity's roles, a line's ends, a capability's parent.
- **A line joins two activities on the same level.** To show the inside of a step, give the inner activities that step as their `parent` and connect them with their own lines, starting from `START` and ending at `END`. The same holds for steps and connectors: a step's `automation` and `parent` decide its level, and a connector joins two steps of one level.
- **Write names for the reader of the diagram.** Activities start with a verb ("Qualify lead"); capabilities are noun phrases ("Lead management"); neither uses API names. Drawing skills use `name` as the box text exactly, and the diagram reviewer matches boxes to model items by that text, so names must differ wherever boxes share a diagram: on one process level, among sibling capabilities, and across roles, entities, systems and automations.
- **RASCI is for people.** Give `rasci` only on roles of kind `human`.
- **List the expected outcome first.** Among the lines out of an activity, put the one for the normal, expected case first. Process and journey drawing puts the first-listed line on the main path, and lays the other outcomes out above and below it.
- **One outcome to several activities is one label.** Lines out of one activity with the same label are drawn as one outcome starting those activities in parallel; give alternatives different labels.
- **Say when a step waits for everything.** Set `join: "all"` on an activity that may start only once every line into it has arrived. Without it, any one incoming line starts it.
- **Keep the link back to a source diagram.** When an activity is read from an existing Elements diagram, record its `diagramRef` (diagram id and box key) so later steps can link back to it.
- **Mark what you worked out.** Set `inferred: true` on anything the source did not state, and say why in `evidence`. Drawing skills flag inferred items on the diagram: a note attachment titled "Inferred" on a box, and "(inferred)" at the end of a line's label.
- **Record what you could not do** in `gaps`: a step no ticket covers, a chain the tracer stopped following, a field the document does not explain. Never fill a gap silently.

## Conventions every drawing skill follows

So that a person can read any diagram the plugin draws, and the `diagram-reviewer` agent can check it, every drawing skill:

- writes an item's `name` as its box text exactly, and a line's `label` as its line text;
- flags inferred items: a note attachment titled "Inferred" on the box, with the item's evidence as its text, and "(inferred)" at the end of an inferred line's label (an interaction flow level whose every line is inferred carries one level-wide note on its first card instead);
- numbers interaction lines by their `order`: "3. Stage = Closed Won", or "3." when the interaction has no label;
- puts each item's `attachments` on its box.

## The validator

`scripts/validate.py` checks a model before anything is drawn from it:

```bash
python3 scripts/validate.py model.json                 # any model
python3 scripts/validate.py model.json --for data-model # and that it can be drawn as a data model
```

It checks, in this order:

1. **Shape.** The file matches the schema: required fields present, values from the allowed lists, no misspelt field names (it suggests the right one).
2. **Model rules the schema cannot express.** Ids are unique, and every reference points at an item that exists and is the right kind. Drill-down levels and capability trees do not loop. Each line stays on one level and appears once. Names are unique where boxes are matched by name (a step's name per automation level). RASCI is only on human roles. Integration patterns are listed in `data/integration-patterns.csv`. A step's `element` is listed in `data/automation-elements.csv`, its `parent` is a step of the same automation, and an interaction's `fromStep` is a step of its `from` automation. The model is not empty.
3. **Diagram fit** (with `--for`). The model has the section that diagram type needs.
4. **Readability.** The `checked_by=validator` rules in `data/readability-rubric.csv`: too many boxes on one level, unlabelled decision branches, steps with no lines, API names used as box text, and so on. Each is reported at its row's `severity`. Deleting a rule's row switches it off; changing its `threshold` changes the limit.

Exit code 0 means no errors (warnings may remain). 1 means the model has errors. 2 means a setup problem: the model file, the schema or a data file could not be read or does not fit the script, or the command line was wrong. On exit 0 or 1 the last line gives the counts, including how many items are marked inferred and how many gaps are recorded.

What it cannot check is whether the model is **right**: whether the process described is the real one. That is the job of the `diagram-reviewer` agent after drawing, and finally of the person reading the diagram.

## Changing the model

The schema is the only definition of the model's shape; the validator reads it rather than repeating it. To add a field:

1. Add it to `ba-model.schema.json` with a `description`. A new top-level array section is picked up by the validator automatically; if a diagram type uses it, add it to `data/diagram-types.csv`.
2. If it points at other items, add the reference check to `check_model_rules` in `scripts/validate.py`.
3. Use it in `examples/lead-to-opportunity.json` and add a test in `tests/test_validate.py`.
4. Change `schemaVersion` when an existing model would stop being valid: removing or renaming a field, or making one required. Until the plugin's first release (version 1.0.0 in its manifests), no saved models exist outside tests, so the schema changes without a version change.

The validator stops with a setup error if the schema uses a JSON Schema keyword it does not enforce, so a rule added to the schema can never be silently skipped.

All drawing routes trim the final map name after overrides and transformations and require 2-80 characters before create_map. Whitespace-only names, a one-character visible name and out-of-range overrides produce a name error.

Metadata readback can name another viewable reference model for the same item. The diagram reviewer matches the API name and metadata type when supplied, accepting a differing `refModelId`.
