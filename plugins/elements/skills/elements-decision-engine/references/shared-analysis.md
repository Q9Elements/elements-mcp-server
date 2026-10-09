# Shared analysis and decisions

## User decisions

Explain the recommended option, alternatives, and trade-offs in plain language. Let the user discuss
or select an approach; map their choice to `options[].optionId` and pass `selectedOptionId` yourself.
Ask when their response is ambiguous. A recommendation is a proposal until selected. Handle revision
according to the workflow reference. `coverage.reviewedAutomations` and `coverage.reviewedNodes` are
integer counts of each recommender's shortlist; the response does not identify shortlist members.
Treat a named target as covered when it appears in the inventory rows (`automations[]` for automation
or `schemaNodes[]` for schema). For automation, a target also counts as covered when it appears in any
`options[].targetAutomationIds`. Tell the user that shortlist membership is not returned. Start at most
one fresh inventory mission for the same named targets, and only for targets covered by neither source.
If the fresh mission still does not cover a named target, tell the user which targets the Decision
Engine could not reach and continue with the covered targets. Stop if none of the named targets are
covered.
If the user chooses a target outside the options, confirm it with `metadata_search` or `get_metadata_node`,
run a standalone dependency scan and impact analysis, and explain that a delivery draft needs an accepted
option. Do not present standalone `no_draft` as the answer.

On `needs_confirmation`, present the returned guardrail and ask whether to proceed. Answer on
`run_architecture_risk_analysis` with the same `missionId`, the result's `gateId`, and `proceed:true`
to run or `proceed:false` to skip. A `proceed` answer requires a pending `needs_confirmation`; submitting
it before one exists or with another `gateId` fails with `invalid_input`. Keep reasons for
skipped analysis visible in the delivery draft.

## Mission sequence

After an accepted automation option with `implementationMode:"update_existing"`, or a schema option with mode `reuse` or `extend`:

1. Call `run_dependency_scan({refModelId, missionId})`. An explicit target overrides the accepted option;
   supply one only when it represents the intended target. Without `missionId`, standalone field impact
   requires `refModelNodeId` or both `objectApiName` and `fieldApiName`; `objectApiName` alone is invalid.
   Preserve the returned mission.
   Use `analysisMode:"update_field"` for field updates and `"delete"` for requested deletion analysis; omit it for automation changes.
   Apply the status rules in [Results and presentation](results.md) before continuing. Include the agreed
   change and clarifications in `changeDescription` on impact, risk, and backlog calls that accept it.
2. Call `run_change_impact_analysis({refModelId, missionId, changeDescription, analysisMode?})`, passing
   the same `analysisMode` used on the scan. Deletion analysis requires `analysisMode:"delete"` on both
   calls. Present work units, complexity, investigations, and coverage. For an impact-only request,
   finish here.
3. Call `run_architecture_risk_analysis({refModelId, missionId, changeDescription?})`. Handle
   confirmation, then present findings, failures, exclusions, and coverage. Standalone risk first resolves
   a supported metadata node with `metadata_search` or `get_metadata_node`, then passes its `nodeId`,
   `metadataType`, and `apiName`; optional `changeDescription` adds context on either path. Supported types
   are Flow, Apex Trigger, Apex Class, Lightning Component Bundle, Aura Definition Bundle, Validation Rule,
   Approval Process, Assignment Rule, Auto-Response Rule, and Escalation Rule. Fields and objects return
   `skipped`.
4. Call `run_backlog_draft({refModelId, missionId, changeDescription?})`. Present the requirement, stories,
   and remaining investigations (Markdown inside `backlogDraft.requirement.notes`). `persisted:false`
   means these requirements and stories are proposed drafts. Surface `architectureRiskConsumed` so the
   user knows whether risk evidence informed the draft.
