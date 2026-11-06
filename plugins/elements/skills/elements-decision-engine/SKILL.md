---
name: elements-decision-engine
description: >-
  Plans Salesforce automation and schema changes with the Elements Decision Engine over Model
  Context Protocol (MCP), from inventory and option selection through impact, architecture risk,
  and a delivery draft in a local HyperText Markup Language (HTML) report. Use when creating or updating automation, objects,
  fields, or record types; asking "what breaks if I change this field", "what fires when X changes",
  "how should I build this automation", "plan this schema change", or "draft stories for this change".
  Do NOT use for metadata lookup or explanation alone (elements-metadata), or broad org health
  assessment (elements-org-diagnostic).
---

# Elements Decision Engine

Turn a proposed Salesforce change into an evidence-backed approach and delivery draft.

| Owner | Responsibility |
|---|---|
| User | Desired outcome and option selection |
| Skill | Routing, tool sequencing, and presentation |
| Server | Analysis and stored mission artifacts |

Salesforce metadata stays unchanged. Elements stores internal analysis artifacts; returned requirements
and stories remain drafts. A successful call returns framed JavaScript Object Notation (JSON); a tool
refusal has `isError:true` and unframed JSON with `error`. A successful job can have `status:"failed"`.

## Numbered workflow

1. Route the request. Restate the intended change. Ask before inventory only when the target object
   or intent is unclear; otherwise inventory first and resolve field ambiguity from open questions.

   | Intent | Read at entry | Entry tools |
   |---|---|---|
   | Create or update automation | [Automation workflow](references/automation.md) | `run_automation_inventory`, `run_automation_recommendation` |
   | Choose how to add or change an object, field, or record type | [Schema workflow](references/schema.md) | `run_schema_inventory`, `run_schema_recommendation` |
   | Existing field update or deletion impact | [Shared analysis](references/shared-analysis.md) | `run_dependency_scan` |
   | Field impact and what fires next | [Field-change recipe](references/field-change.md) | Scan, impact, then `run_data_load_impact` |
   | Architecture risk of specified metadata | [Shared analysis](references/shared-analysis.md) | `run_architecture_risk_analysis` |

   For mixed schema and automation work, identify the prerequisite and use separate missions. Carry
   agreed intent between missions in `changeDescription`; give each mission its own backlog draft.
   Proposed schema may need a sync before resolution as existing metadata. For new requirements with
   no stated deliverable, continue through backlog. Stop at recommendations when the user asks which
   approach to take; record selection only when requested. Otherwise stop at the requested deliverable.

2. Resolve context and targets. When several connected servers expose the tools, choose the server for
   the environment the user names and keep it for the workflow; clarify if the environment is ambiguous.
   Call `list_reference_models({delivery:"file"})` when context is needed. Keep
   `referenceModels[].refModelId` and `activeSpace.teamId`; pass `teamId` on data calls. On
   `active_space_required`, follow the elements-spaces context flow and retry with that `teamId`.
   Reference model, node, and mission identifiers are 24 hexadecimal characters. Carry parsed identifiers;
   keep `refModelId`, `nodeId`, `missionId`, runtime `jobId`, and file-result `resultId` distinct.
   To resolve a named object, field, or automation, read [Targets](references/targets.md).

3. Run the mission loop, one step at a time to avoid run-cap and capacity refusals:
   1. Start the relevant mission tool; keep `missionId` with the user, space, and reference model.
   2. Parse successful text between `[TOOL DATA START]` and `[TOOL DATA END]`. Before interpreting
      missing fields, consume whole-result files and nested moved values using
      [Results and presentation](references/results.md). Pass `delivery:"file"` on potentially large
      stage calls and polls; status-only receipts and selection replies stay inline. While `running`,
      poll `get_analysis_result` with the same context at the interval in that reference.
   3. Route finished responses on `status`, then `outcome`, then counts as the results reference directs.
      Selection, revision, and confirmation calls follow the same loop; finished results can arrive directly.
   4. Save completed responses locally. Without `step`, polling returns the latest run. With `step`, it
      returns that step's last finished result, or `not_found`; if it names the latest run's step, it
      returns that run. Step names: `automation_inventory`, `automation_recommendation`, `dependency_scan`,
      `change_impact_analysis`, `architecture_risk_analysis`, `backlog_draft`, `schema_inventory`,
      `schema_recommendation`. Runtime analysis and explanations repeat their originating calls instead.
   5. On `run_in_progress`, poll `get_analysis_result` on this mission; keep the same mission.
      On other refusals, read [Refusals](references/refusals.md) for policy order, exact messages,
      and recovery. Read `error` first, preserve optional `message`, `flag`, and `hint`, and keep feature,
      permission, and transport failures separate. On a switch hint, resolve the intended authorized
      space with `get_space_context`, call `set_active_space`, and retry; report any further refusal.

4. Handle decisions and downstream analysis using [Shared analysis and decisions](references/shared-analysis.md).
   Record the selected approach before analysis. `selectedOptionId` carries the choice; carry clarifications
   in `changeDescription` on later calls that accept it. Impact requires it; risk accepts optional context
   on either path; backlog accepts it optionally on a mission. Preserve the last completed stage on failure;
   retry after addressing the cause or a transient failure, then stop if it recurs. Use a fresh mission
   for materially changed requests or post-analysis selection changes because artifacts retain earlier analysis.

5. Deliver a concise digest after each completed stage and one self-contained local HTML report using [the template](templates/report.html) and the results reference's field map.
   Write or update the report at stages the user will see and at the final stage. Check Python 3 with
   `python3 --version` (install Python 3 from python.org if absent), then run
   `python3 scripts/check_report.py /absolute/path/report.html` from this skill directory. The
   [validator](scripts/check_report.py) checks placeholders, enabled-tab content, and scripts inside panels;
   fix and re-run until it passes, then inspect the rendered report before presenting it. If scripts
   cannot run, manually search for `{{`, check each enabled tab has content beyond its heading or
   “Pending.”, and check panel content contains no script element. Publishing or external records follow
   the user's explicit request.

```text
- [ ] Route intent and requested stopping point
- [ ] Resolve server, space, reference model, and targets
- [ ] Consume files and all pages; route status before counts
- [ ] Record decisions; complete the requested analysis or draft
- [ ] Preserve refusals, failures, coverage, and missing evidence
- [ ] Validate and inspect the report; deliver digest and local file
```
