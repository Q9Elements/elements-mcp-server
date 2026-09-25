---
name: elements-decision-engine
description: >-
  Plans Salesforce automation and schema changes with the Elements Decision Engine over Model
  Context Protocol (MCP), from inventory and option selection through impact, architecture risk,
  and a delivery draft. Use when creating or updating automation, objects, fields, or record types,
  requesting recommendations, assessing field-change impact including its automation fire chain, or reviewing
  architecture risk.
  Do NOT use for metadata lookup or explanation alone (elements-metadata), or broad org health
  assessment (elements-org-diagnostic).
---

# Elements Decision Engine

Turn a proposed Salesforce change into an evidence-backed approach and delivery draft. The user
owns the desired outcome and option selection; this skill owns routing, tool sequencing, and
presentation; the server owns analysis and mission artifacts. Salesforce metadata stays unchanged.
Elements stores internal analysis artifacts; returned requirements and stories remain drafts.

Run one step at a time per mission and handle its finished status before chaining another tool.
Record the user's selected approach before analyzing it. `selectedOptionId` carries only the choice;
carry clarifications in `changeDescription` on the next calls that accept it. Mission impact requires it;
architecture risk accepts optional context on mission and standalone paths; backlog accepts it optionally
on a mission. Stop at the requested deliverable: recommendations, field impact, standalone risk, or a draft.

## Route the request

Restate the intended change and resolve the reference model with `list_reference_models` when needed.
Ask before inventory only when the target object or intent is unclear. Otherwise inventory first and
resolve field ambiguity from recommendation open questions. Use `metadata_search` and `get_metadata_node`
to resolve concrete targets; preserve parent-object context.

| Intent | Read | Entry tools |
|---|---|---|
| Create or update automation | [Automation workflow](references/automation.md) | `run_automation_inventory`, `run_automation_recommendation` |
| Choose how to add or change an object, field, or record type | [Schema workflow](references/schema.md) | `run_schema_inventory`, `run_schema_recommendation` |
| Impact of an existing field update or deletion, with no approach to choose | [Shared analysis](references/shared-analysis.md) | `run_dependency_scan` with the object and field, or confirmed node identifier |
| Field update or deletion: what it affects and what fires next | [Field-change recipe](references/field-change.md) | `run_dependency_scan`, `run_change_impact_analysis`, `run_data_load_impact` |
| Architecture risk of specified metadata | [Shared analysis](references/shared-analysis.md) | `run_architecture_risk_analysis` with a resolved `nodeId`, plus `metadataType` and `apiName` |

For impact of an existing field update or deletion, use standalone field impact. If they also ask what
fires or the change triggers next, use the [field-change recipe](references/field-change.md). Use schema
workflow to choose how to add or change schema.

For a mixed schema-and-automation request, identify the prerequisite change and use separate missions
for each path. Carry the agreed intent between them explicitly. Proposed schema may require a later
sync before it can be resolved as existing metadata. For recommendation-only requests,
record a selection only if requested.

## Execution contract

Every call needs `refModelId`; also pass `teamId` for a token authorized for multiple spaces. The token
needs `mcp:decisionEngine:read`, a Decision Engine license and enabled artificial intelligence features,
reference-model edit access, and an unsuspended space. Explain structured errors by cause: scope,
entitlement, access, or mission ownership.

1. Start the relevant `run_*` tool. Keep its `missionId` with the user, space, and reference model.
2. On `status:"running"`, call `get_analysis_result` with the same context. Follow its polling guidance
   while keeping the user informed.
3. When polling returns the finished step, handle its actual `status` before starting another step.
   Selection, revision, and confirmation calls also follow this execution pattern. A tool may return
   a finished response directly, notably stored architecture-risk pages.
4. Keep completed responses locally for the report: polling serves the mission's current run, while
   the server stores the artifacts needed for later steps. Match `step` to the requested operation.
5. Handle run errors by their contract: `run_in_progress` means poll the mission instead of restarting;
   `too_many_runs` means finish or wait for one of the five live runs per user and space before starting
   another mission. A run still running 8 minutes after it started is reported `failed`; start a fresh run.
   `too_many_concurrent_requests` and `server_busy` carry `retryAfter:5`. `rate_limited` allows 60
   requests per minute per token, including polls, and carries `retryAfter:60`. Wait the returned delay
   before resuming; call tools one at a time.

Read [Results and presentation](references/results.md) for status handling, field mappings, and paging.

On failure, preserve the last completed stage and retry only after addressing the cause or a transient
failure; stop if it recurs. Start a fresh mission for materially changed requests or post-analysis
selection changes because mission artifacts retain earlier analysis.

## Shared analysis

For decision handling, shared analysis, and backlog sequencing, follow
[Shared analysis and decisions](references/shared-analysis.md).

## Deliverables

Provide a concise chat digest after each completed stage and maintain one self-contained local HTML
(HyperText Markup Language) report in the workspace using [the template](templates/report.html).
Apply the rendering and evidence rules in the results reference. Write the report file after the
first completed stage, then rewrite that same file after every later stage completes.
Verify rendering before presenting the report. Publishing or creating external records follows the
user's explicit request.
