# Elements Map and Design

Elements Map and Design (plugin name `elements-map-and-design`) maps and designs Salesforce business architecture as well-laid-out Elements diagrams:

- **From the connected org** (through Elements): the business process its objects support, data models, how one automation or a chain of automations works, the automations behind each status or stage, and every outside system the org exchanges data with.
- **From vendor documentation**: a product's out-of-the-box process (Salesforce clouds, Dynamics 365, HubSpot, ServiceNow).
- **From your documents, pictures or descriptions**: process maps, customer journeys, data models, interaction flows, capability maps and system architecture.
- **From a process map in Elements**: the solution design it implies (a data model, a system architecture, a data access matrix and a solution overview document), or a check of how far the org implements it, coloured on the map.
- **From an agent package** (a Claude skill, agent or plugin, an Elements playbook, a framework such as GSD): what it does, as a process for sign-off.

Data models and system architecture diagrams can be amended; the other diagram types are drawn new. Diagrams are created as drafts in Elements. Nothing in Salesforce is changed.

## Start here

Type `/start` (in full, `/elements-map-and-design:start`) and say what you want in plain words. The `start` skill is the front door: it works out the diagram, what you are giving it and whether you want a new map, a change or a check against the org, and runs the right skill or playbook. It also resumes a run in progress ("pick up the design check").

You can also call a skill by name when you know which one you want:

| Skill | Use it for |
|---|---|
| `start` | Anything; the front door |
| `explain-automation` | How one Flow, Apex class or trigger, or rule works |
| `trace-automation-chain` | Everything that fires after something happens, end to end |
| `map-process-from-data-model` | The business process of a whole system, or one object, from its data model |
| `show-status-automations` | The automations that run at each status or stage of a process map built from the org |
| `map-org-integrations` | Every system the org connects to, drawn as a landscape (playbook) |
| `design-from-process-map` | The solution design a process map implies (playbook) |
| `compare-design-to-implementation` | How far the org implements a design drawn in Elements (playbook) |
| `map-agent-as-process` | What a skill, plugin, playbook or agent framework does, as a process |

The five drawing skills (`draw-process-map`, `draw-data-model`, `draw-interaction-flow`, `draw-capability-map`, `draw-system-architecture`) are hidden from the `/` menu (`user-invocable: false`). They only draw from a validated model, so people reach them through `start` or a reader; Claude can still call them.

## Status

Everything in the table below is built except use cases 8 (service catalogue) and 9 (process or journey from tickets), which are paused; the status column says how far each piece has been run.

| Piece | What it does | Status |
|---|---|---|
| `start` skill (the front door) | Classifies a request by diagram type, source and mode (create, amend, or check against the org), looks it up in `data/routes.csv`, runs the right reader or playbook (or writes the model itself on a generic route) and hands the validated model to the right drawing skill; resumes a run in progress from its folder | Built |
| Routing table (`data/routes.csv`) | Every diagram type × source × mode combination: dedicated reader or playbook, generic, direct, planned, paused, external or unsupported; `drawing_skill` in `data/diagram-types.csv` | Built; checked by `tests/test_routes.py`, which also checks that every skill is reachable from the table, that a check goes to the design check, and that only the drawing skills are hidden from the menu |
| Shared model (`schemas/`) | The one file format readers write and drawing skills read | Built |
| Validator (`scripts/validate.py`) | Checks a model is complete and consistent before drawing; every layout script runs it as a gate and refuses a failing model | Built |
| Drawing protocol (`references/drawing-protocol.md`) | The steps every drawing skill shares: validate, plan, the write loop, common errors, check and review, report | Built |
| Readability rubric (`data/readability-rubric.csv`) | The rules diagrams are checked against | Built |
| Process and journey layout conventions (`skills/draw-process-map/references/`, `data/style-process.csv`, `data/line-sides.csv`) | The line-side rules, the house style measured on the six reference exemplar maps, the UPN rules, and what the MCP write path can set | Built |
| Shared layout engine (`scripts/layout_engine/`) | What more than one diagram type uses: level placement, line geometry, the resumable write loop, preflights (with the library types of close matches and object renames), the whole-read rule for saved review reads, and the layout check. Layout scripts import it and never each other | Built; checked by `tests/test_layout_engine.py` |
| Layout script (`scripts/layout_process.py`) | Places boxes, chooses every line's sides, splits the writes into `manage_diagram` batches, steps a run, and checks the drawn levels (rubric rows R13–R17) | Built |
| `draw-process-map` skill | Draws a model as a process map or customer journey with all its child levels | Built |
| `diagram-reviewer` agent | Checks a finished diagram against its model and the rubric, adding the layout check's findings | Built |
| Interaction flow layout (`scripts/layout_interaction.py`, `data/style-interaction.csv`, `data/automation-elements.csv`, `data/automation-types.csv`) | Turns automations and their steps into cards with header icons, attributes and footers, places them with the process-map engine (chain level and one logic level per automation, loop bodies as drill-downs), wires chain lines through the levels, and steps and checks the run | Built |
| `draw-interaction-flow` skill | Draws a model of automations as an Elements interaction flow | Built |
| Capability map layout (`scripts/layout_capability.py`, `data/style-capability.csv`, `data/capability-ratings.csv`) | Places drivers, a grid of columns with text-box headings over capability cards (sub-headings for groups), bands and a rating legend on one level, from the sizes manage_diagram gives cards and text boxes (it cannot resize either, so groupings are headings rather than boxes); writes everything with manage_diagram in canvas-sized batches, moves anything that lands out of place, and checks the drawn level (rubric rows R26-R28) | Built |
| `draw-capability-map` skill (use case 5) | Draws a model's capabilities and drivers as an Elements business capability map | Built |
| Data model layout and org reader (`scripts/layout_data_model.py`, `scripts/build_data_model.py`, `data/style-data-model.csv`, `data/er-line-ends.csv`, `data/relationship-ends.csv`, `data/entity-kinds.csv`, `data/system-fields.csv`) | Builds a data model from Salesforce objects in the Metadata Dictionary; lays it out parents-above-children with crow's-foot line ends and writes it with `manage_diagram`; reads a drawn data model back into a model and amends it in place (objects, fields, lines, line ends, tidy); checks the drawn level (rubric rows R32-R34) | Built |
| `draw-data-model` skill (use case 3) | Draws or amends an Elements data model from org objects, a model file or an existing map | Built |
| System architecture layout (`scripts/layout_architecture.py`, `data/style-architecture.csv`, `data/architecture-zones.csv`, `data/architecture-zone-headings.csv`, `data/system-kinds.csv`, `data/system-icons.csv`, `data/integration-timing.csv`, `data/integration-mechanisms.csv`) | Lays out a hub with sources left, destinations right, engagement above and ingestion below; draws groups as cards with a drill-down whose lines continue the parent lines; labels lines with mechanism and timing and adds a key; writes with `manage_diagram` only; reads a drawn diagram back into a model and amends it in place; checks the drawn levels (rubric rows R48-R50) | Built |
| `draw-system-architecture` skill (use case 6) | Draws or amends an Elements system landscape or solution architecture from a description, a document, a picture, a model file or an existing map, with the Salesforce Well-Architected integration checks (rubric rows R40-R47) | Built |
| `map-process-from-data-model` skill (use case 1) | Works out a whole system's multi-level process from its data model (the vendor's documentation, or a Salesforce org's objects in the Metadata Dictionary) and hands the model to `draw-process-map`. Agents: `system-doc-reader`, `capability-grouper`, `process-level-writer`. A linear eight-stage run that ends with drawing the map and, on route metadata, the automations behind each status box (`show-status-automations`); `scripts/status.py` names the next stage from the work folder's files and says when the run is complete | Built and tested offline; golden Manufacturing Cloud model in `examples/`; stage 8 not yet run |
| `map-agent-as-process` skill (use case 10) | Draws what an agent package does (a Claude skill, agent or plugin, a script-backed skill, an Elements playbook, or a framework such as GSD) as a process stakeholders can sign off: stages as the top level, instructions as the level behind each, people as Human resources, and the AI Assistant, agents, skills, MCP servers and tools and scripts as System resources (`Agent:`, `MCP Server:`, `MCP tool: server/tool`, `Script:`), in a business or a technical view; optionally the call graph as an interaction flow. Formats are rows of `data/agent-package-formats.csv`. Shares the level-by-level core with `map-process-from-data-model`: `scripts/process_levels.py`, `scripts/check_outline.py`, `schemas/level-outline.schema.json` and the `process-level-writer` agent | Built and tested offline on `design-from-process-map`; GSD and other-platform adapters not yet tried on a real package |
| `explain-automation` skill (use case 4, part 1) | Explains one Flow, Process Builder, Apex class or trigger, OmniScript or rule as a logic level, card by card, from its definition (Flow XML through `scripts/flow_to_steps.py`) or from what Elements' dependency graph names. Agent: `automation-logic-reader` | Built |
| `trace-automation-chain` skill (use case 4, part 2) | Walks a chain of automations through Elements' dependency graph (`scripts/trace_chain.py`: calls, saves, platform events), checks it with the person, reads each automation's logic with one agent each in parallel, and draws a chain level with a logic level under each automation | Built |
| `show-status-automations` skill | For the status or stage boxes of a process map built from the org, finds the automations that run when a record reaches each value (`scripts/status_automations.py`), explains each in business language (`automation-firing-reader` agent, from Elements' explanations), and gives each status box a child level of its automations in save order, with the objects they write. `map-process-from-data-model` runs it after drawing | Built; tested offline by `tests/test_status_automations.py` |
| Process or journey from tickets (use case 9) | Skill + ticket reader agent | Abandoned / paused: left out for now; routes marked `paused` |
| `design-from-process-map` playbook (use case 7) | From a process map in Elements and a target system the solution architect chooses: checks every level can carry a design, gathers the target system's evidence (a connected org or the vendor's documentation), derives the data model, the integrations and a data access matrix, holds one checkpoint, then draws the data model and the system architecture and assembles a solution overview document (Word) that walks the process area by area, with the access matrix as its own CSV. Agents: `process-quality-assessor`, `data-model-deriver`, `integration-deriver`, `access-deriver`, `solution-overview-writer`, with `system-doc-reader` and `diagram-reviewer`. A state-machine playbook: one card per state, an execution-state file, `scripts/lint.py` | Built and tested offline on a fixture; not yet run |
| `map-org-integrations` playbook (use case 12) | From a connected org's metadata in Elements: takes the integration inventory (connected apps, remote sites, credentials, external services, platform events, external objects, managed packages and where each points), resolves it into the outside systems it proves (`data/known-systems.csv`, `data/not-external.csv`, then the `system-classifier` agent), checks the list with the architect, traces every system's automations (code search, where-used on its credentials and callout classes, what each automation reads and writes), has the `integration-tracer` agent work out each exchange and the systems reached only through a middleware (one more search pass for those), checks the integration list with the architect, and draws a landscape: the org in the centre, a middleware as a card or a "via" label by `middleware_fold_threshold` (or when the top level would pass `max_cards_per_level`), one drill-down per system (system, middleware, automations, objects), every card linked to its metadata. A state-machine playbook: one card per state, an execution-state file, `scripts/lint.py` | Built: 30 integrations with 18 outside systems, reviewer pass; step-8 reviews done |
| `compare-design-to-implementation` playbook (use case 13) | Checks how far a connected org implements an approved design drawn in Elements (process map, journey, interaction flow, system architecture or data model), box by box: reads the map (the whole map, or one level with the levels beneath), proposes metadata links for boxes that have none (`metadata-matcher`, one agent per level, from the objects the boxes name, their fields and the automations that use them) for the analyst to approve before anything is written, gathers each linked component's definition, dependencies, picklist values, change history and explanation, judges every linked box (`implementation-assessor`, one agent per box, in waves), rolls the verdicts up through the levels (`data/rollup.csv`) and writes a gap report; on the analyst's yes, colours the boxes green, yellow or red with a sticky note on each gap and a legend, and removes them again on "reset the colours" (original fills saved first). A state-machine playbook: one card per state, an execution-state file, `scripts/lint.py` | Built: two-level test map, 9 links proposed and written, 8 boxes judged, map coloured; reset dry-run clean |
| Service catalogue of an org (use case 8) | Playbook | Abandoned / paused: left out for now; routes marked `paused` |

## How the pieces fit

```
request ──► start (front door) ──► reader ──► model.json ──► validate.py ──► drawing skill ──► Elements diagram
            data/routes.csv picks the reader,                (the gate)                            │
            data/diagram-types.csv the drawing skill         diagram-reviewer  ◄───────────────────┘
```

The front door works out which diagram the person wants, what they are giving as input and whether it is new, a change or a check against the org, and looks that up in `data/routes.csv`. A check, a solution design from a process map and an org integration landscape go to a playbook, which runs its own steps and pauses for the person's approval. A reader works out what is true and writes the model; where no reader exists yet the route is `generic` and the front door writes the model itself (`skills/start/references/generic-modelling.md`). The validator checks the model, and every layout script runs it again before planning, so nothing is drawn from a model that fails. A drawing skill turns the model into an Elements diagram with consistent styling and layout, following `references/drawing-protocol.md`. The reviewer checks the result. [`schemas/README.md`](schemas/README.md) explains the model and why it exists.

### Where each rule lives

| Layer | Holds | Where |
|---|---|---|
| Orchestration | Which source goes to which reader and drawing skill | `skills/start/`, `data/routes.csv`, `data/diagram-types.csv` |
| Readers | How to work out one kind of model from one kind of source | `map-process-from-data-model`, `map-agent-as-process` (both on the shared level-by-level core, `scripts/process_levels.py`), `explain-automation`, `trace-automation-chain`, `show-status-automations`, and the model-building sections of `draw-data-model` and `draw-system-architecture` |
| Playbooks | Long runs that pause for approval and resume from a state file | `design-from-process-map`, `map-org-integrations`, `compare-design-to-implementation` |
| Contracts | The model's shape, styles, the rubric | `schemas/`, `data/` |
| Drawing | How to draw one diagram type | one `draw-*` skill each, on top of `references/drawing-protocol.md` |
| Enforcement | No drawing from a failing model; no route to a missing skill; no skipped stage | `validate.gate` in every layout script, `tests/test_routes.py`, the readers' `scripts/status.py` |

Dependencies point one way: the front door names readers, readers name the drawing skill they hand to, drawing skills name the reviewer. No skill or agent names who calls it.

## Models

The plugin names no model in its skills. Each agent and skill has a tier in `data/model-tiers.csv`: `strong` (the most capable reasoning model a platform offers) where judgement is the work, `fast` (its cheaper general model) where the work is bounded and checked by a script. `data/model-hosts.csv` maps the tiers to each platform's models; on Claude, `strong` is Opus and `fast` is Sonnet, which is what each agent's `model:` line says. A platform with no row uses its own most capable and cheaper models, or the session's model when it cannot choose per agent. [`references/model-policy.md`](references/model-policy.md) explains it; `tests/test_model_tiers.py` keeps the agents in step with it.

| Tier | Agents | Skills (advice for the session model) |
|---|---|---|
| `strong` | `diagram-reviewer`, `automation-logic-reader`, `capability-grouper`, `process-level-writer`, `process-quality-assessor`, `data-model-deriver`, `integration-deriver`, `access-deriver`, `solution-overview-writer`, `integration-tracer`, `metadata-matcher`, `implementation-assessor` | the front door, every reader, `design-from-process-map`, `map-org-integrations`, `compare-design-to-implementation`, `draw-data-model`, `draw-system-architecture` |
| `fast` | `system-doc-reader`, `system-classifier` | `draw-process-map`, `draw-interaction-flow`, `draw-capability-map` when drawing a model file that already exists |

## Interaction flows: how the skills fit

Three skills and one agent work together to draw Salesforce automations as Elements interaction flows. Each skill can be used on its own, but two of them hand over to the third.

| The person asks | Start with | What it does | Then |
|---|---|---|---|
| "How does Trigger Commission work?" "Explain this flow." | `explain-automation` | Finds the one automation, gets its definition (Flow XML, Apex source) or what Elements knows about it, and has the `automation-logic-reader` agent turn it into steps | Hands its model to `draw-interaction-flow` |
| "How are commission line items calculated, end to end?" "What fires after an opportunity closes?" | `trace-automation-chain` | Walks the chain of automations through Elements' dependency graph, asks the person to confirm what is in it, then runs one `automation-logic-reader` agent per automation in parallel | Hands its model to `draw-interaction-flow` |
| "Draw this model" (a model file already exists) | `draw-interaction-flow` | Lays out and writes the map, then checks it with the layout check and the `diagram-reviewer` agent | Reports the map link and any findings |

```
explain-automation ──────┐
                         ├──► automation-logic-reader ──► model.json ──► draw-interaction-flow ──► Elements map
trace-automation-chain ──┘    (one agent per automation)                          │
                                                                                  └──► diagram-reviewer
```

**Why there is no single script that runs it all.** A script cannot call the Elements tools, start agents, or stop to ask the person a question, and the chain skill has to do all three. So the two reader skills are the orchestrators: each lists its stages in order. The parts that repeat many times are done by scripts that say what to do next: `trace_chain.py next` names the next Elements call during the walk, and `layout_interaction.py next` names the next diagram write. Each answer is saved to a file before the script is asked again, so a run can stop and resume at any point.

**What passes between them** (all in the run's work folder):

| File or folder | Written by | Read by |
|---|---|---|
| `trace/` | `trace_chain.py` (the walk and the person's decisions) | `trace_chain.py assemble` and `bundle` |
| `chain.json`, `links.json` | `trace_chain.py assemble` (the chain level) | `build_interaction_model.py merge` |
| `bundles/<automation>/` | `trace_chain.py bundle`, plus the definition and `flow_to_steps.py` draft when there is one | `automation-logic-reader` |
| `logic/<automation>.json` | `automation-logic-reader` (one automation's steps and lines) | `build_interaction_model.py merge` |
| `model.json` | `build_interaction_model.py merge`, checked by `validate.py` | `draw-interaction-flow` |
| `drawing/` | `layout_interaction.py` and the saved Elements answers | `diagram-reviewer` |

The reading method the agent follows, and the formats of these files, live in `skills/explain-automation/references/`; `trace-automation-chain` uses them too.

## Where things go

The plugin mixes small, single-purpose skills (draw a data model, explain one automation) with long multi-stage runs (`map-process-from-data-model`, and the three playbooks). One rule decides where each file lives: **a file sits with the only skill that uses it, and moves to the plugin root as soon as a second skill needs it.** Move it then; never copy it.

| What | Plugin root | Inside `skills/<skill>/` |
|---|---|---|
| Scripts | `scripts/`: used by more than one skill, and every diagram type's layout script (any reader can hand a model to it) | `scripts/`: the steps of that skill's own method (`map-process-from-data-model/scripts/`) |
| Shared layout code | `scripts/layout_engine/`: used by more than one layout script. A layout script imports the engine and `validate.py`, never another layout script | — |
| Data tables | `data/`: read by a root script or by more than one skill | `data/`: read only by that skill's scripts |
| Schemas | `schemas/`: the business-architecture model, which every skill shares | `schemas/`: that skill's own working files (an inventory, a level outline) |
| References | `references/`: guidance several skills follow (the drawing protocol, the model policy) | `references/`: that skill's method and conventions |
| Agents | `agents/`, always: the platform looks for them there. Each needs a row in `data/model-tiers.csv` | — |
| Tests | `tests/`, always, one file per script or skill; fixtures in `tests/fixtures/<skill>/`; development repository only, not published | — |

Three kinds of skill, by size:

- **A single-purpose skill** does one job in one pass: one `SKILL.md`, optional `references/`, and the root scripts. The drawing skills, `explain-automation` and the front door are of this kind.
- **A runbook skill** is a fixed sequence of stages with its own scripts, data and schemas inside its folder, and a status script that names the next stage from the work folder's files. `map-process-from-data-model` is the model.
- **A playbook** is a long job that pauses for approval and resumes days later, built with `build-elements-playbook`: a dispatch `SKILL.md`, one card per state in `steps/`, `templates/execution-state.json`, and its own data and scripts inside its folder. There are three: `design-from-process-map` (UC7), `map-org-integrations` (UC12) and `compare-design-to-implementation` (UC13). UC8, now paused, was planned as another.

Whichever kind, a skill that produces a diagram ends by handing a validated model to a drawing skill. Every skill is reached from `data/routes.csv` or `data/diagram-types.csv`, so the front door can find it, and every playbook is listed in the front door's "A run in progress" table, so it can be resumed; `tests/test_routes.py` checks both.

Naming: skills start with a verb that says the job (`map-`, `draw-`, `explain-`, `trace-`, `show-`, `compare-`, `design-`), and the brand lives once, in the plugin name, which prefixes every command (`/elements-map-and-design:<skill>`). Typing `/elements` or the verb finds them.

## Folder layout

```
elements-map-and-design/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── references/
│   ├── drawing-protocol.md        # the steps every drawing skill shares
│   └── model-policy.md            # strong and fast tiers instead of model names
├── agents/
│   ├── access-deriver.md          # derives CRUD per step and the permission controllers
│   ├── automation-firing-reader.md  # reads when an automation fires against a status or stage
│   ├── automation-logic-reader.md # reads one automation's logic into steps and lines
│   ├── capability-grouper.md      # groups a system's objects into capabilities
│   ├── data-model-deriver.md      # derives entities from a process and matches them to the target system
│   ├── diagram-reviewer.md        # reviews a drawn diagram against its model
│   ├── implementation-assessor.md # judges how far the org implements one step of a design
│   ├── integration-deriver.md     # derives systems and integrations from a process, with patterns
│   ├── integration-tracer.md      # works out one outside system's integrations from its evidence
│   ├── metadata-matcher.md        # proposes the org components behind a level's unlinked boxes
│   ├── process-level-writer.md    # writes one level of a process from its brief
│   ├── process-quality-assessor.md  # judges each process level's wording for derivability
│   ├── solution-overview-writer.md  # writes the prose of the solution overview document
│   ├── system-classifier.md       # classifies integration evidence no known vendor matched
│   └── system-doc-reader.md       # reads a vendor's data model documentation into an object inventory
├── data/
│   ├── automation-elements.csv    # step kinds, their header icons, and how Flow XML, Apex and OmniScript map to them
│   ├── automation-types.csv       # automation types, their Elements metadata types and chain-level header icons
│   ├── capability-ratings.csv     # rating scales for capability maps: values, labels and fill colours
│   ├── entity-kinds.csv           # data model card colours per entity kind, and the Key card's wording
│   ├── er-line-ends.csv           # data model line ends: names, Elements shapes, meanings
│   ├── chain-relations.csv        # how a dependency's relation line ("Update Record ...") joins a chain
│   ├── diagram-types.csv          # each diagram type, the Elements map type, the sections it needs, its drawing skill
│   ├── integration-patterns.csv   # Salesforce integration patterns an integration may name
│   ├── model-hosts.csv            # each platform's models for the strong and fast tiers
│   ├── model-tiers.csv            # each agent's and skill's tier and reasoning effort
│   ├── line-sides.csv             # which side of a box each kind of line leaves and enters
│   ├── readability-rubric.csv     # readability rules, split between validator, reviewer and layout check
│   ├── routes.csv                 # diagram type x source x mode -> reader, for the front door
│   ├── relationship-ends.csv      # default line ends per cardinality and relationship kind
│   ├── style-capability.csv       # card and text-box sizes manage_diagram gives, gaps, heading case and colours for capability maps
│   ├── style-architecture.csv     # card sizing, zone spacing and limits for system architecture
│   ├── style-data-model.csv       # card sizing, spacing and limits for data models
│   ├── style-interaction.csv      # layout and style settings for interaction flows
│   ├── style-process.csv          # layout and style settings for process maps and journeys
│   ├── system-icons.csv           # which library icon a system card gets, from its name and kind
│   ├── system-kinds.csv           # system architecture card colours per system kind, and the Key's wording
│   ├── system-fields.csv          # audit and system fields left off data model cards built from the org
│   └── trace-limits.csv           # how far a chain walk goes, and when an object becomes a hub card
├── examples/
│   ├── change-intelligence-capabilities.json  # golden capability map: the hand-made Change Intelligence assessment
│   ├── salesforce-capability-assessment.json  # a capability map with drivers, ratings, list columns and bands
│   ├── lead-to-opportunity.json   # a process model that uses every section
│   ├── manufacturing-cloud.json   # golden model: the hand-made Manufacturing Cloud map, 11 levels
│   ├── saas-trial-journey.json    # a customer journey model with a child level
│   └── sales-service-data-model.json  # a data model: standard objects, custom Invoice, every line-end case
├── schemas/
│   ├── ba-model.schema.json       # the model's shape, with a description on every field
│   ├── level-outline.schema.json  # one process level as a writer agent writes it; shared by the level-by-level readers
│   └── README.md                  # the model explained
├── scripts/
│   ├── attachment_scope.py        # selected reference model for loaded models and resumed attachment payloads
│   ├── build_data_model.py        # builds a data model from Metadata Dictionary rows; lists related objects; merges
│   ├── build_interaction_model.py # merges automation fragments into one interaction flow model; checks a fragment
│   ├── check_outline.py           # checks one level outline against its brief (run by process-level-writer)
│   ├── flow_to_steps.py           # turns a Flow or Process Builder's XML into steps and lines
│   ├── layout_engine/             # the shared layout engine; layout scripts import it and never each other
│   │   ├── base.py                # paths, constants, errors, data files, text helpers
│   │   ├── geometry.py            # level placement, line sides and routes, canvas growth, card sizing
│   │   ├── write_loop.py          # the resumable next-step loop, preflights, library batches, id maps, renames
│   │   ├── reads.py               # the whole-read rule: a saved review read missing fields is refused
│   │   └── checks.py              # the layout check against the rubric's layout-check rows
│   ├── layout_capability.py       # plans, steps and checks a capability map drawing
│   ├── layout_architecture.py     # plans, writes, reads back, amends and checks a system architecture drawing
│   ├── layout_data_model.py       # plans, writes, reads back, amends and checks a data model drawing
│   ├── layout_interaction.py      # plans, steps and checks an interaction flow drawing
│   ├── layout_process.py          # plans a process or journey drawing; the engine does the rest
│   ├── process_levels.py          # the level-by-level readers' shared core: outline rules, boundary labels, the level walk, run status
│   ├── trace_chain.py             # walks an automation chain through Elements' dependency graph
│   └── validate.py                # model checker, standard library only
├── skills/                        # one folder per skill
│   ├── compare-design-to-implementation/
│   │   ├── SKILL.md               # the playbook: dispatch table, human moments, session contract
│   │   ├── steps/                 # one card per state, 01 to 10
│   │   ├── data/                  # verdicts and colours, roll-up rule, link types, limits
│   │   ├── references/            # the engagement directory's files; method notes and tool limits
│   │   ├── schemas/               # the files the agents write
│   │   ├── templates/             # execution-state.json
│   │   └── scripts/               # read the design, match, evidence, colour, save pulls, lint
│   ├── design-from-process-map/
│   │   ├── SKILL.md               # the playbook: dispatch table, human moments, session contract
│   │   ├── steps/                 # one card per state, 01 to 10
│   │   ├── data/                  # derivability rubric and pass mark, CRUD verbs, integration evidence types, document sections
│   │   ├── references/            # the engagement directory's files; how entities, integrations and access are found
│   │   ├── schemas/               # the files the agents write
│   │   ├── templates/             # execution-state.json and the solution overview's Word template
│   │   ├── assets/                # the Elements.cloud logo for the document's first page
│   │   └── scripts/               # read and check the map, evidence, merge and slice, access matrix, pictures, document, lint
│   ├── draw-capability-map/       # every draw- skill is hidden from the / menu (user-invocable: false)
│   │   ├── SKILL.md               # draw a model's capabilities as a capability map
│   │   └── references/            # where each model item goes, sizes, and why groupings are headings
│   ├── draw-data-model/
│   │   ├── SKILL.md               # draw or amend a data model from org objects, a model file or an existing map
│   │   └── references/            # drawing conventions and why; how to build a model from the org
│   ├── draw-interaction-flow/
│   │   ├── SKILL.md               # draw a model of automations as an interaction flow
│   │   └── references/            # cards, header icons, lines and drill-downs; what the write path can set
│   ├── draw-process-map/
│   │   ├── SKILL.md               # draw a model as a process map or customer journey
│   │   └── references/            # layout conventions, UPN rules, exemplar levels
│   ├── draw-system-architecture/
│   │   ├── SKILL.md               # draw or amend a system landscape or solution architecture
│   │   └── references/            # the modelling guide and the architecture drawing conventions
│   ├── explain-automation/
│   │   ├── SKILL.md               # explain one automation as a logic level
│   │   └── references/            # the reading method, the files a run writes, where definitions come from
│   ├── map-agent-as-process/
│   │   ├── SKILL.md               # work out what an agent package does as a process
│   │   ├── references/            # how a level is written from a package
│   │   ├── schemas/               # the package inventory format
│   │   ├── data/                  # package formats and how each one keeps its stages; resource prefixes and views
│   │   └── scripts/               # inventory, briefs, model build with coverage and views, run status
│   ├── map-org-integrations/
│   │   ├── SKILL.md               # the playbook: dispatch table, human moments, session contract
│   │   ├── steps/                 # one card per state, 01 to 08
│   │   ├── data/                  # inventory types, known systems, not-external rules, hit types, limits
│   │   ├── references/            # the engagement directory's files; method notes and tool limits
│   │   ├── schemas/               # the files the agents write
│   │   ├── templates/             # execution-state.json
│   │   └── scripts/               # inventory, resolve systems, trace plan, integrations and model, lint
│   ├── map-process-from-data-model/
│   │   ├── SKILL.md               # work out a system's process from its data model
│   │   ├── references/            # the method, the two sources, the files, the Manufacturing exemplar
│   │   ├── schemas/               # object inventory format
│   │   ├── data/                  # platform objects, object archetypes, vendor documentation sources
│   │   └── scripts/               # inventory, clusters, briefs, model build, coverage check, run status
│   ├── show-status-automations/
│   │   ├── SKILL.md               # the automations behind each status box, as a child level
│   │   ├── references/            # run steps, firing rules, layout rules, objects on boxes, the files a run writes
│   │   ├── data/                  # the automation registry
│   │   └── scripts/               # status_automations.py: boxes, checks, explanations, layout
│   ├── start/
│   │   ├── SKILL.md               # the front door: resume, classify, route, gate, hand over
│   │   └── references/            # how to write a model when no reader skill exists
│   └── trace-automation-chain/
│       ├── SKILL.md               # map a chain of automations end to end
│       └── references/            # how the walk works and what it cannot see
└── tests/                         # one file per script or skill; development repository only, not published
    ├── fixtures/line-rules.json   # a model that exercises every line-side rule
    ├── fixtures/map-process-from-data-model/  # a small docs and metadata run
    ├── fixtures/map-agent-as-process/  # a real inventory and level outlines of the design-from-process-map playbook
    ├── fixtures/interaction-flow/ # four flows' XML and real Elements answers for the commission chain
    ├── fixtures/data-model/       # five objects' metadata rows, and the review read of the drawn example
    ├── fixtures/design-from-process-map/  # two levels of a Sales Cloud map and hand-written derivations
    ├── fixtures/map-org-integrations/  # a synthetic landscape model and a small synthetic engagement (packs, tracer files)
    ├── test_bug_fixes.py
    ├── test_compare_design.py
    ├── test_design_from_process_map.py
    ├── test_drawing_gate.py
    ├── test_interaction_flow.py
    ├── test_landscape_drilldowns.py
    ├── test_layout_architecture.py
    ├── test_layout_capability.py
    ├── test_layout_data_model.py
    ├── test_layout_engine.py
    ├── test_layout_process.py
    ├── test_lifecycles.py
    ├── test_map_agent_as_process.py
    ├── test_map_org_integrations.py
    ├── test_map_process_from_data_model.py
    ├── test_model_tiers.py
    ├── test_process_status.py
    ├── test_routes.py
    ├── test_status_automations.py
    ├── test_trace_chain.py
    ├── test_usage_basis.py
    ├── test_usage_notes.py
    └── test_validate.py
```

## Requirements

- The core `elements` plugin installed and connected to the Elements Model Context Protocol (MCP) server.
- Python 3.8 or later where the scripts run. The drawing skills need nothing else. The `design-from-process-map` and `map-org-integrations` playbooks also need `curl` (to download Elements result parts); `design-from-process-map` also needs the `python-docx` package for its document, and optionally LibreOffice or Pillow (diagram pictures in the document); `skills/design-from-process-map/scripts/common.py probe` reports what is installed.

## Install

### Claude Code

```text
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements-map-and-design@elements
```

### Claude Desktop and claude.ai

- Open 'Customize' → 'Plugins'.
- Install `elements-map-and-design` from the `Q9Elements/elements-mcp-server` marketplace.

### Codex

```text
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements-map-and-design@elements
```

### ChatGPT

- Upload [`elements-map-and-design.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements-map-and-design.zip) from the repository's dist folder.
- The core plugin provides the Elements app, so there is no separate Add app step.
- Upload the zip again for each playbook release.

## Develop and test

From this plugin's folder in the published plugin:

```bash
python3 scripts/validate.py examples/lead-to-opportunity.json --for process
python3 scripts/layout_process.py plan examples/saas-trial-journey.json --type journey --workdir /tmp/journey-drawing
python3 scripts/layout_process.py plan examples/manufacturing-cloud.json --type process --workdir /tmp/mfg-drawing --skip metadata
python3 scripts/layout_capability.py plan examples/change-intelligence-capabilities.json --workdir /tmp/ci-capability-map
python3 scripts/layout_data_model.py plan examples/sales-service-data-model.json --workdir /tmp/sales-data-model
python3 scripts/layout_architecture.py plan examples/data-360-aws-landscape.json --workdir /tmp/d360-landscape
python3 skills/design-from-process-map/scripts/lint.py
python3 skills/map-org-integrations/scripts/lint.py
python3 skills/compare-design-to-implementation/scripts/lint.py
```

The unit tests and their fixtures are kept in Elements' development repository and are not part of the published plugin; run these commands from the plugin's folder there:

```bash
python3 scripts/flow_to_steps.py tests/fixtures/interaction-flow/Calculate_Commission_Line_Item_from_PE.flow-meta.xml --automation-id calc --out /tmp/calc.json
python3 scripts/build_interaction_model.py merge --fragments /tmp/calc.json --out /tmp/calc-model.json --title "Calculate commission: how it works"
python3 scripts/layout_interaction.py plan /tmp/calc-model.json --workdir /tmp/calc-drawing --skip metadata
python3 -m unittest discover -s tests
```

Two tests compare the validator's shape checks with the `jsonschema` package and are skipped when it is not installed.

To try the plugin in Claude Code without installing it from the marketplace, from the repository root:

```bash
claude --plugin-dir plugins/elements-map-and-design
```

Metadata attachments carry `metadataType` whenever the source supplies the type, and the selected `refModelId`. Every drawer fills missing reference-model identifiers from the run context at planning. On resume, an unscoped saved attachment stops the drawing with a message to start again from the model in a new drawing folder; scoped plans keep their saved preflight and write progress. The context locations and preflight rules are in the [drawing protocol](references/drawing-protocol.md). The diagram reviewer matches metadata by API name and metadata type when supplied; readback can name another viewable reference model for the same item. Explanation prose is read by `scripts/metadata_narrative.py` from string, summary (`purpose`, `text`) and chain (`sections`, `chainRelationGroups`) responses.

The production 2.0 tool contract and saved-result acquisition rules are in [result acquisition](references/result-acquisition.md). Drawing hand-offs retain connection.json (selected server and teamId), full diagram reads use delivery file, and automation definitions follow the agreed local-project, named-org retrieve, attached-file or stored-source choice. Stored source uses get_metadata_source with provenance when chosen or when the other sources are unavailable. Create-map names contain 2-80 trimmed characters.
