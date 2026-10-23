---
name: elements-org-to-process
description: Generate, retrieve, and interpret Salesforce lifecycle process maps with generate_process_map and get_process_map, and assess their artificial intelligence and automation opportunities. Use when the user says "generate org to process", "show me the Case process", "what's the Opportunity lifecycle", "org to process for [Salesforce object]", or "find agent opportunities in this process". Do NOT use for maps from descriptions, transcripts, or images (use elements-diagrams), org-wide opportunity scans (use elements-agent-opportunities), or story generation (use elements-stories).
---

# elements-org-to-process

Use the Elements Model Context Protocol (MCP) server for the environment the user names.
If several servers expose these tools and the environment is unclear, ask which one to use.
Terms: application programming interface (API), JavaScript Object Notation (JSON), Universal Process Notation (UPN), artificial intelligence (AI).

## Tools

| Tool | Purpose and plan |
|---|---|
| `get_space_context` / `set_active_space` | Resolve the authorized space |
| `list_reference_models` | Select a readable reference model |
| `search_metadata` | Verify object API names |
| `generate_process_map` | Create org-object process maps asynchronously |
| `get_process_map` | Poll and read a compact process map |
| `list_process_maps` / `export_diagram` | Find process maps / export a ZIP archive |

Generation also requires `mcp:diagrams:create`,
Editor/Author role, and reference model edit access. On a refusal, quote `error` and any returned `message` exactly;
read [Access and refusals](references/org-to-process.md#access-and-refusals) for the next action.
Tool visibility reflects feature flags across the grant; the selected space and caller still need access.

## Checklist

```text
- [ ] Resolve space and retain teamId.
- [ ] Resolve the reference model when generation or metadata discovery needs it.
- [ ] Verify the object or retain the supplied diagram identity.
- [ ] Check for an existing process map before creating one.
- [ ] Generate when requested; retain each diagram/map pair and any failures.
- [ ] Poll, recover files, and validate complete evidence.
- [ ] Interpret the process and its warnings.
- [ ] Offer opportunities; prepare evidence, apply rubric, and offer a report.
```

## Workflow

For a supplied process map, start at step 1, then step 6 with its identifiers.
For an object request, follow all steps. Run commands from this skill's directory.

1. **Space.** Call `get_space_context`. Announce `active` when present, even if `isSet: false`.
   If `active === null`, page `authorized` while `pagination.hasMore`: use `_truncated.nextSkip`
   when supplied, otherwise `pagination.skip + authorized.length`, keeping `pageSize` fixed.
   `pagination.totalItems` counts authorized spaces. Ask the user to choose, call
   `set_active_space({teamId})`, and announce its returned name. Retain `teamId` on data calls.

2. **Reference model.** If its identifier is missing, call `list_reference_models({teamId, delivery:"file"})`.
   Before consuming files, read [Tool replies](references/org-to-process.md#tool-replies).
   Read `referenceModels[].refModelId`; use the sole `generationEligible: true` reference model,
   or ask which one when several qualify. If none qualifies, report its status/role and access gap.
   Its `count` counts readable reference models. Recover its complete unpaged list before selecting.

3. **Object.** Accept an API name supplied by the user. For business language, generate variants
   ("deals" → `["Opportunity","Deal","Deal__c"]`), trim each, and keep terms of 2 through 256 characters.
   If none remains, ask for a usable keyword. Call `search_metadata({teamId, refModelId, queries,
   sfType:"Standard Object", delivery:"file"})`; search `"Custom Object"` separately when relevant.
   `sfType` is one string; a list returns `invalid_input`. Read `nodes[].apiName`; `nodeId` is a
   metadata node identifier. Page using [Paging](references/org-to-process.md#paging) and ask which
   object when several match. Pass the confirmed name to generation.

4. **Existing process map.** Call `list_process_maps({teamId, query:"Case", mode:"page", format:"json",
   delivery:"file"})`, substituting the confirmed object name. Follow the paging rules above.
   Offer a matching process map for retrieval; generate a new one when the user chooses creation.

5. **Generate.** Creation persists process maps. Never repeat generation to refresh a failed file link;
   regeneration requires separate user confirmation. Read [Generation](references/org-to-process.md#generation)
   for fan-out, clarification, partial starts, and recovery before calling `generate_process_map`.
   Use `source:"org_object"`, `refModelId`, `objectApiName`, and `teamId`. One call covers the object's
   record types. Retain every returned `mapId`, `diagramId`, and diagram link with its record type.

6. **Poll and recover.** Before reading each reply, use [Tool replies](references/org-to-process.md#tool-replies).
   Call `get_process_map({diagramId, teamId, delivery:"file"})` for each selected diagram, following
   [Polling](references/org-to-process.md#polling) until complete. Save the hydrated result as `result.json`.
   For a content-bearing result, run [scripts/build_finder_payload.py](scripts/build_finder_payload.py):
   `python3 scripts/build_finder_payload.py result.json --check`.
   If transitions remain unavailable, read [Transition recovery](references/transition-recovery.md) and run
   [scripts/rebuild_transitions.py](scripts/rebuild_transitions.py) as directed there. Fix and re-run until it passes.
   Without script execution, compare both recovered array lengths with the metadata counts manually.
   Report any unresolved gap and withhold the rubric for that diagram.

7. **Interpret.** Use [Interpreting results](references/org-to-process.md#interpreting-results) for lifecycle,
   automation, and path questions. Lead with business meaning, the source diagram link, and material warnings.

8. **Opportunities.** Offer an assessment for a complete UPN process map. Read
   [Agent Finder](references/agent-finder.md), then run the payload script named in step 6:
   `python3 scripts/build_finder_payload.py result.json --output payload.json`.
   With recovered transitions, add `--transitions transitions.json` to both validation and build commands.
   Without execution, use the reference's payload table. Evaluate every activity and apply its rubric;
   offer the persistent report described there. These recommendations are conversation output.

## Handoff

For a selected opportunity, give the activity text, chosen `agentType`, and source diagram as the build specification.
Use `elements-stories` for a story backlog, `elements-diagrams` for description/image generation or diagram edits,
and `elements-agent-opportunities` for an org-wide scan.

Scripts require Python 3, using only its standard library. Check `python3 --version`; if unavailable,
install Python 3 through the environment's package manager or use the manual fallbacks above.
