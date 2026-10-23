# The engagement directory

Every file a run writes, who writes it and who reads it. `$ENG` is the engagement directory, the folder holding `execution-state.json`. Files with a schema follow the schemas in `../schemas/`; `N` is the matching round; a box id is `L<levelNumber>-<key>` (`L1.3-36`).

| Path in `$ENG` | Written by (card) | Read by | Format |
|---|---|---|---|
| `execution-state.json` | the orchestrator, every card | every card; `read_design.py` (`slots.scope`, `slots.ref_model_id`); `match.py` (`match.round`); `evidence.py` (`slots.ref_model_name`) | `../templates/execution-state.json` |
| `levels/outline.json` | the orchestrator (01): every page of `get_process_map_outline` joined | `read_design.py build` | `{"mapId", "name", "items": [...]}` |
| `levels/<levelNumber>.json` | the orchestrator (02, 05, 08, 09): the `get_diagram` answer with `include: ["layout", "metadata", "notes"]` and `delivery: "file"` with selected teamId, whole | `read_design.py build` | Elements answer |
| `design.json` | `read_design.py build` | every later script | per level: diagram id, version, canvas, boxes, free notes (marked `ours` when they start with the playbook's marker), text boxes; per box: text, resources, attributes, footer, notes, lines in and out, links (`ok`, `missing-in-org`, `to-resolve` or `unresolved`; `diagram` or `approved-not-saved`; `followed` when the read named another org's copy), parent, child level, children, decision, layout |
| `links/org-plan.json` | `read_design.py org-plan` (02) | card 02 (the calls), `read_design.py org-map` | the lookups of the links not in the run's org: per call its pull, type, filters and columns; per link its key and pull |
| `links/org-map.json` | `read_design.py org-map` (02), merged across rounds | `read_design.py build` | `{"refModelId", "found": {key: {"nodeId", "name", "status"}}, "missing", "ambiguous"}`, a key being `<type>|<API name>` lower-cased |
| `coverage.json` | `read_design.py coverage` (02) | `match.py terms`, `briefs` and `table`, card 03 | the boxes without a level beneath and without links, by level |
| `match/round-N/searches.json` | `match.py terms` (03) | `match.py objects` and `briefs` | the searches of the round, each with its id, term, query variants and boxes |
| `match/round-N/<search id>.json` | the orchestrator (03): the `search_metadata` answer, whole | `match.py objects` and `briefs` | Elements answer |
| `match/round-N/objects.json` | `match.py objects` (03) | `match.py briefs`, card 03 | the objects among the hits and the pull for their where-used rows |
| `match/round-N/briefs/<level>.json` | `match.py briefs` (03) | `metadata-matcher`, `match.py check` and `table` | one level's unlinked boxes with their candidates |
| `match/round-N/found/<level>.json` | `metadata-matcher` (03) | `match.py check`, `next-round`, `terms` (the next round) and `table` | `../schemas/matches.schema.json` |
| `links/proposed.json` | `match.py table` (03, 04) | `match.py confirm` | per box: decision, links with why and confidence, reason, note |
| `links/corrections.json` | the orchestrator (04): the analyst's corrections as ops | `match.py confirm` | `{"rounds": [{"date", "by", "corrections", "applied"}]}` |
| `links/approved.json` | `match.py confirm` (04) | `match.py resolve` and `plan`, `read_design.py build` | the approved links and decisions per box, with counts |
| `links/resolve.json`, `links/resolve/<nodeId>.json` | `match.py resolve` (the list); the `get_metadata_component` answer with `detail: "full"` (05) | card 05 (the calls); `match.py plan` reads `links/resolve/<nodeId>.json` (a field's object) | Elements answer |
| `links/plan/<level>.json` | `match.py plan`, `match.py drop-failed` (05) | `manage_batches.py next`, card 05 | `{"diagramId", "baseVersion", "changes", "refs", "dryRunFirst"}`, plus `batches` for multiple batches; `changes` is the first batch and `refs` aligns with all batches flattened in order |
| `links/plan/<level>.saved.json` | `manage_batches.py next` (05), after every batch completes | `match.py plan` and card 05 (which levels are done) | combined write evidence: final version, merged idMap and genuine batchResults |
| `<plan-directory>/.batches/<plan-stem>/<plan-hash>/<batch>.dry.json`, `<batch>.json` | the orchestrator (05, 08, 09), at the runner's `saveTo` | `manage_batches.py next`; `match.py drop-failed` (dry-run issues within the selected batch) | whole genuine preview and real responses, bound to the complete plan's hash |
| `links/not-saved.json` | `match.py drop-failed` (05) | `match.py plan`, `evidence.py rollup` (the report) | the links Elements refused, with the reason |
| `evidence/plan.json` | `evidence.py plan` (06) | the other `evidence.py` commands, card 06 (the calls) | the boxes to assess, their linked components, and the batches and pulls to fetch |
| `evidence/component-<k>.json`, `history-<k>.json`, `explain-<k>.json` | the orchestrator (06): `get_metadata_component`, `get_component_change_history`, `explain_metadata_components` answers, whole | `evidence.py pack` | Elements answers |
| `evidence/pulls.json`, `evidence/<pull>-<index>.ndjson` | the orchestrator (02, 03, 06): every list answer and its parts | `read_design.py org-map`, `match.py briefs`, `evidence.py related` and `pack`, which read only the parts `pulls.json` records | the session contract in [`SKILL.md`](../SKILL.md) |
| `evidence/related.json` | `evidence.py related` (06) | `evidence.py pack`, card 06 | the automations acting on the linked objects and fields, and their pull |
| `assess/packs/<box>.json`, `assess/defs/` | `evidence.py pack` (06) | `implementation-assessor`, `evidence.py check` | one box's evidence; explanation strings and summary/chain objects become prose through the plugin's `scripts/metadata_narrative.py`; the definitions it points at, with a flow's steps from the plugin's `flow_to_steps.py` with the compared `refModelId` passed as `--ref-model-id` |
| `assess/verdicts/<box>.json` | `implementation-assessor` (06) | `evidence.py check` and `rollup` | `../schemas/assessment.schema.json` |
| `assess/checked.json` | `evidence.py check` (06) | `evidence.py wave` and `rollup` | the boxes whose verdict passed, with its file |
| `results.json`, `report.md` | `evidence.py rollup` (06) | `colour.py plan`; cards 07 and 09 (the report) | every box's verdict, note and how it was reached; the report by level |
| `colour/originals.json` | `colour.py plan` (08), never overwritten | `colour.py reset-plan` | each coloured box's fill and border before the first colour write |
| `colour/plan/<level>.json` | `colour.py plan` (08) | `manage_batches.py next`, card 08, `colour.py record` | `{"diagramId", "baseVersion", "changes", "confirm", "notes", "fills", "dryRunFirst"}`, plus `batches` for multiple batches |
| `colour/saved/<level>.json`, `colour/reset-saved/<level>.json` | `manage_batches.py next` (08, 09), after every batch completes | cards 08 and 09 | combined write evidence: final version, merged idMap and genuine batchResults |
| `colour/applied.json` | `colour.py record` (08) | `colour.py reset-plan` and `reset-verify` | per level: the note keys and fills written |
| `colour/reset/<level>.json` | `colour.py reset-plan` (09) | `manage_batches.py next`, card 09 | `{"diagramId", "baseVersion", "changes", "confirm", "dryRunFirst"}`, plus `batches` for multiple batches |

Pull names in `evidence/`: `org-<k>` (card 02); `match-rN-where-used` and `match-rN-fields-<k>` (card 03); `source-<k>`, `using-<k>`, `where-used-<k>`, `values-<k>` and `source-related` (card 06). Save each whole reply through `scripts/save_pull.py ENG PULL TOOL --reply REPLY.json`, one register update at a time, including complete empty replies.

Every native pull retains terminal status, resultId, final counts, completed parts, failedTotal and all failed records (including failedFile coverage). Part hashes and row counts prove the files; terminal state and failures prove the coverage. Keep each result attempt separate and report source-row availability reasons as source gaps. See the shared result-acquisition contract.
