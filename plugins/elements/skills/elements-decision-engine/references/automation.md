# Automation workflow

Use for creating or updating Salesforce automation. Carry reference model and space context through
all calls and handle each result with the mission loop in SKILL.md.

1. Call `run_automation_inventory` with `request`, optional `objectApiName`, and optional `missionName`.
   Omit `missionId` for a new request. An explicit object resolves scope even when the request omits it.
   On `outcome:"needs_clarification"`, ask about `message` or `unresolvedTargets`, then retry with the
   clarified request or object in the same mission. Present `primaryTarget`, `targets`, `automations`,
   and coverage. Keep description-generation warnings separate from an empty inventory.
2. Call `run_automation_recommendation` with the mission. On `outcome:"needs_selection"`, discuss
   `options`, `recommendedOptionId`, `recommendationRationale`, triggers, trade-offs, conflicts, and
   open questions. Read each option's `implementationMode`: `create_new` or `update_existing`.
   The scan treats empty `targetAutomationIds` as `create_new`. Apply the contradiction rule in
   [Results](results.md) before selection.
3. Record the choice with `selectedOptionId` only, then poll for `acceptedOption`. Identifier errors
   and `none_of_the_above` follow [Results](results.md). For revised options before downstream analysis,
   pass `requestRevision:true` and `feedback`; this reuses the same reviewed set. Apply the named-target
   coverage and fresh-mission rules in [Shared analysis](shared-analysis.md).
4. Check accepted-target coverage before scanning. Compare automations named as hosts or edits in the
   option's label, summary, or user clarifications with `acceptedOption.targetAutomationIds`. Name any
   omitted automation and explain that scan, impact, and risk will not check it. `requestRevision`
   cannot add it to the recommender shortlist. Offer a fresh inventory mission when the shared rule
   permits, or field-change analysis of the fields the option writes.
5. For `acceptedOption.implementationMode:"create_new"`, run a dependency scan, route on status, and
   expect `complete` with `outcome:"no_targets"` and a message. Continue to backlog; claim no blast-radius
   or risk evidence. Offer an optional `run_change_impact_analysis` overlap check on the same mission
   when the user asks about overlap or double-firing, or the requirement forbids duplicate effects
   (such as one email per Case). It can return a placement-only plan or zero requested/completed
   coverage with no work units or placement plan. For that empty result, report “no overlap evidence returned”.
   For runtime checks, apply the [field-change recipe](field-change.md) to the trigger object and
   each target object's record operation and written fields. For example, creating Tasks uses
   `object:"Task"`, `operation:"insert"`, and the fields written. Deletion and rename steps apply only
   when requested for existing metadata.
6. For `acceptedOption.implementationMode:"update_existing"`, follow the scan, impact, risk, and
   backlog sequence in [Shared analysis](shared-analysis.md). With several `targetAutomationIds`, the
   scan resolves the first identifier; impact considers all accepted targets found in the inventory.
   For the overlap conditions in step 5, also apply the field-change recipe's runtime check to the
   trigger object and operation. Resolve `outcome:"needs_clarification"` before continuing; route
   normal completed scans with the count table in [Results](results.md).

Example: “Assign Cases by region.” Inventory Case automation, discuss options, record the user's
selection, then analyze accepted targets and draft delivery work. A recommendation-only request stops
at the options.

```text
- [ ] Inventory the request and resolve clarifications
- [ ] Discuss options and record selection or revision
- [ ] Check named targets against accepted targets
- [ ] Follow the create-new or update-existing path
- [ ] Handle overlap conditions and requested delivery
```
