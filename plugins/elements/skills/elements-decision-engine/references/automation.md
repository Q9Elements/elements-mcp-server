# Automation workflow

Use for creating or updating Salesforce automation. Carry the reference-model and space context
through every call, and apply the execution contract in `SKILL.md` after every run.

1. Call `run_automation_inventory` with `request`, optional `objectApiName`, and optional `missionName`.
   Omit `missionId` for a new request. An explicit object can resolve scope even when the request
   omits it. On `needs_clarification`, ask about the returned message/`unresolvedTargets`, then retry with the
   clarified request or object and the same mission. Present `primaryTarget`, `targets`, `automations`,
   and coverage. Treat description-generation warnings separately from an empty inventory.
2. Call `run_automation_recommendation` with the mission. On `needs_selection`, present `options`,
   `recommendedOptionId`, and `recommendationRationale`. Discuss implementation mode, relevant
   triggers, trade-offs, conflicts, and open questions where supplied. Read `implementationMode` on
   each option directly: `create_new` or `update_existing`. The scan treats an option with empty
   `targetAutomationIds` as `create_new`. Compare timing in each label or summary with its
   `phaseBucket`; if they conflict, present the structured `phaseBucket`, show the contradiction, and
   confirm the intended timing before selecting the option. The accepted option also returns
   `implementationMode`.
3. Record the user's choice by calling the same tool with `selectedOptionId` only, then poll for the
   accepted option. Put clarifications from the selection or open-question discussion in `changeDescription`
   on later calls that accept it. For revised options before downstream analysis, call with
   `requestRevision:true` and the user's `feedback`; this reuses the same reviewed automation set.
   `coverage.reviewedAutomations` is an integer count of the recommender's shortlist; the response does
   not identify shortlist members. Check named automations against `automations[]` inventory rows and
   `options[].targetAutomationIds`, and tell the user that shortlist membership is not returned. A named
   automation covered by neither source can trigger at most one fresh inventory mission for the same
   named targets. If it remains uncovered, tell the user the Decision Engine could not reach it and
   continue with covered targets, or stop if none are covered.
4. On `complete` with `acceptedOption`, route using `acceptedOption.implementationMode` and follow
   [shared analysis and decisions](shared-analysis.md) for `update_existing`.
   Before the dependency scan, compare automations named as the host or as edited in the accepted
   option's label or summary with `acceptedOption.targetAutomationIds`. If a named automation is not
   in that list, tell the user that the dependency scan, impact, and risk stages cover only the listed
   targets, and name the automation those stages will not check. Do not present their results as
   covering it. `requestRevision` reuses the same recommender shortlist and cannot add that automation
   to the targets. Offer a fresh inventory mission that names it when allowed by the one-fresh-mission
   rule, or the field-change recipe for the fields the accepted option writes.
   Run the dependency scan for new automation too, and route on its `status` first. For `create_new`,
   expect `no_targets` with only a `message`, then go straight to backlog; do not claim zero blast radius
   or risk. If the user asks about overlap or double-firing, optionally run
   `run_change_impact_analysis` on the same mission as the native check, ahead of the field-change recipe.
   It can return a placement-only plan or `complete` with zero requested and completed coverage, no work
   units, and no placement plan. In that empty case, report “no overlap evidence returned,” not “no
   overlap.” For a new automation, the field-change recipe's “what fires” step applies to the fields it
   will write and the record operation it performs on each target object, as well as its trigger object.
   For example, an automation that creates Task records uses `object:"Task"` and
   `operation:"insert"`, with `writtenFields` set to the fields it writes. Use the matching `insert`,
   `update`, `upsert`, or `delete` operation for each target. Deletion and rename steps do not apply.
   If an accepted option has several `targetAutomationIds`, the scan uses only the first id; impact
   analysis reviews all of them. An unresolved existing target
   returns `needs_clarification`; resolve it before proceeding. `complete` routes on the dependency and
   analysis-target counts as `results.md` describes.

Example: "Assign Cases by region." Inventory the Case automations, explain the returned options,
record the user's selection, and analyze its targets before drafting delivery work. If the user asks
only which approach to choose, stop after presenting recommendations.
