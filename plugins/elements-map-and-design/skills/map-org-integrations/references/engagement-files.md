# The engagement directory

Every file a run writes, who writes it and who reads it. `$ENG` is the engagement directory, the folder holding `execution-state.json`. Files with a schema follow the schemas in `../schemas/`; `N` is the trace round.

| Path in `$ENG` | Written by (card) | Read by | Format |
|---|---|---|---|
| `execution-state.json` | the orchestrator, every card | every card; `trace_plan.py` (`trace.round`, `slots.hub_name`); `build_landscape_model.py` (`trace.round`, `slots`) | `../templates/execution-state.json` |
| `evidence/pulls.json` | the orchestrator (02, 04): one entry per list answer, or `{"notSynced": true}` | `inventory.py` and `trace_plan.py`, to check a pull is whole before reading it | as the session contract in [`SKILL.md`](../SKILL.md) gives it |
| `evidence/<pull>-<index>.ndjson` | `curl` of each part (02, 04) | the scripts, reading only the parts `pulls.json` records | Elements rows |
| `evidence/packages.json` | `list_managed_packages`, every page joined (02) | `inventory.py build` | `{"packages": [...]}` |
| `evidence/source-ids.json` | `inventory.py source-ids` (02) | card 02 (the `get_metadata_source` calls), `inventory.py build` | the nodeIds whose definition names an endpoint, in batches with their pull names |
| `inventory.json` | `inventory.py build` (02) | `resolve_systems.py propose` | one item per inventory row: type, role, namespace, description, endpoint URL and domain; the packages; the types not synced |
| `systems/proposal.json` | `resolve_systems.py propose` (02) | `resolve_systems.py build` | matched vendors with their evidence; unmatched items with candidates; items set aside with the reason |
| `systems/unmatched.json` | `resolve_systems.py propose` (02) | `system-classifier` | the items for the classifier, each with an id `u1`, `u2`, ... |
| `systems/classified.json` | `system-classifier` (02) | `resolve_systems.py build` | `../schemas/classified.schema.json` |
| `systems/proposed.json` | `resolve_systems.py build` (02) | `resolve_systems.py confirm` | the proposed systems, never changed after card 02 |
| `systems/corrections.json` | the orchestrator (03): the architect's check-1 corrections as ops | `resolve_systems.py confirm` | `{"rounds": [{"date", "by", "corrections", "applied"}]}` |
| `systems.json` | `resolve_systems.py build` (02), `confirm` (03); `trace_plan.py pack` (04) marks `tracedRound`; `build_landscape_model.py merge` (05) adds systems named behind a middleware | `resolve_systems.py show`, `trace_plan.py`, `build_landscape_model.py`, card 05 (which systems this round traced) | every system with its kind, how it was found, evidence, search terms, status and trace round; the items set aside; the architect's drops |
| `trace/round-N/searches.json` | `trace_plan.py terms` (04) | `trace_plan.py hits`, `pack` | the searches of the round with their pull names; the terms not searched, as gaps |
| `trace/round-N/hits.json` | `trace_plan.py hits` (04) | `trace_plan.py automations`, `pack` (every round's gateways) | per system: automations, key fields, gateways |
| `trace/round-N/batches.json` | `trace_plan.py hits` and `automations` (04) | card 04 (the calls to make), `trace_plan.py` | `whereUsed`, `using` (pull names and nodeIds), `summary` and `chain` (file names and nodeIds), `notExplained` |
| `trace/round-N/automations.json` | `trace_plan.py automations` (04) | `trace_plan.py pack` | per system: every automation found and what found it |
| `trace/round-N/explain-<aspect>-<k>.json` | `explain_metadata_components` answer, saved whole with its failed items (04) | `trace_plan.py pack` | Elements answer; narrative prose is read through `scripts/metadata_narrative.py` at the plugin root from strings, summary objects and chain objects |
| `trace/packs/<system id>.json` | `trace_plan.py pack` (04) | `integration-tracer`, `build_landscape_model.py check-found` and `merge` | one system's evidence: inventory items, gateways, automations with descriptions, explanations, objects, fields, calls; key fields; gaps |
| `trace/found/<system id>.json` | `integration-tracer` (05) | `build_landscape_model.py check-found` and `merge` | `../schemas/found.schema.json` |
| `integrations/merged.json` | `build_landscape_model.py merge` (05) | `build_landscape_model.py correct` | the integrations as derived, before any correction |
| `integrations/corrections.json` | the orchestrator (06): the architect's check-2 corrections as ops | `build_landscape_model.py merge` and `correct` | `{"rounds": [{"date", "by", "corrections", "applied"}]}` |
| `integrations.json` | `build_landscape_model.py merge` (05) and `correct` (06) | `build_landscape_model.py show` and `model`, card 07 (the report) | the hub, systems, integrations with via, automations and objects, what each automation does to each object, middleware placements set by the architect, gaps, drops |
| `drawing/model.json` | `build_landscape_model.py model` (07) | `validate.py`, `draw-system-architecture`, `diagram-reviewer` | the plugin's shared model (`schemas/ba-model.schema.json` at the plugin root); all metadata attachments carry `slots.ref_model_id` as `refModelId` |
| `drawing/landscape/` | the drawing skill's work folder (07) | card 07 (`plan.json` and `review.json` for the resume rule, `review/top.json` for the link) | the drawing protocol's files |

Pull names in `evidence/`: `inventory-<type>` for each row of `../data/inventory-types.csv`; `sources`, `sources-2`, ... for the endpoint definitions (card 02); `search-<term>` for each code search, `gateways-rN-<k>` and `using-rN-<k>` for the dependency calls (card 04).

Every native pull retains terminal status, resultId, final counts, completed parts, failedTotal and all failed records (including failedFile coverage). Part hashes and row counts prove the files; terminal state and failures prove the coverage. Keep each result attempt separate and report source-row availability reasons as source gaps. See the shared result-acquisition contract.
