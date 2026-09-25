# 05 Plan the removal

State: `list-reviewed`


## Purpose

Turn the customer's confirmed rulings into deletion tranches that list consumers first for reading
order, with each tranche deploying as one unit, plus separate annotation stories. The deterministic
planner writes the plan, stories, validation receipt, and
closing report; agents validate and explain its output.

## Procedure

1. **Validate planning inputs.** Require at least `data/thresholds.csv` T-12 held telemetry days,
   a complete dispositions file, and a selected-class string-search status of `available` or
   `unavailable`. A `not_run` status blocks planning. An `annotate` ruling is valid only for a
   test-only class with no entry-point signal.
2. **Resolve non-Apex application programming interface (API) names.** Read the confirmed `remove`
   rulings and their incoming edges. For every non-Apex referrer that the plan can delete, call the
   Elements `get_metadata_node` capability with `nodeId: edge.parentNodeId` and
   `refModelId: slots.model_id` and `teamId: slots.space_id`, one node id per call. Issue the calls in
   parallel in one turn. Write
   `work/plan/api-names.json` as an object that maps each
   returned node id to `{ "apiName": "<apiName>" }`. Omit a node whose response has no API name; the
   planner turns that referrer into a manual Setup step. Process Builder Workflow and Workflow Rule
   referrers are evaluated as automation and are not deletion-name lookups.
3. **Generate the plan.** Give the **removal-plan-generator** agent (tier `fast`, effort high) the
   engagement directory. Follow [`references/orchestration.md`](../references/orchestration.md) and
   `data/agent-tiers.csv` for agent dispatch. When `work/triage/summary.json.stringSearch` is
   `available`, run from the engagement directory:

   `python3 <plugin>/scripts/removal_plan.py --dispositions work/review/dispositions.csv --candidates work/bundle/candidates.csv --catalog work/bundle/catalog.csv --edges work/bundle/edges.csv --api-names work/plan/api-names.json --reasoned work/reasoned-candidates.csv --string-holders work/triage/string-holders.csv --catalog-summary work/bundle/catalog-summary.with-capacity.json --out-dir work/plan --stories-dir stories`

   When the status is `unavailable`, replace
   `--string-holders work/triage/string-holders.csv` with `--string-search-unavailable`. Do not pass
   `--allow-unevaluated-flow-rule`. Exit status 2 with `flow-trigger-block` unevaluated means re-run
   the candidate tool on a server that emits `MetadataComponentTriggerType`, or record the block.
   The flag applies only to Flow referrers. A Process Builder Workflow or Workflow Rule referrer
   puts its unit in `blockedUnits`, keeps that unit in `unevaluatedRules`, and does not stop the rest
   of the plan. Its `blockedReason` names the referrer's own type and says that the class stays until
   the process or rule is deactivated or confirmed unused.
   The script writes `work/plan/*`, `stories/*.md`, and `report/final-report.md`. It lists deletion
   units with consumers before providers as reading order; each tranche deploys as one deployment. Each surviving edited test has one
   precursor story and appears in its tranche's `package.xml`; that manifest deploys with the
   tranche's `destructiveChangesPost.xml`. It writes one `@isTest` annotation story per `annotate`
   ruling outside the tranches, because those stories delete nothing.
4. **Check deterministic invariants.** The generator reads `work/plan/validation.json` and checks
   placement, consumer-before-provider reading order, test attachments, test-edit precursor deployment,
   survivor references, and capacity totals against
   `references/data-contracts.md`. It returns paths, counts, and named counterexamples; it writes
   nothing. Repair a named input and re-run the generator when an invariant fails. Never edit a
   generated story by hand.
5. **Falsify the plan.** Give the **removal-plan-reviewer** agent (tier `strong`, effort high) the
   dispositions, plan outputs, candidate bundle, stories, `data/quarantine-rules.csv`, and
   `references/story-template.md`. The reviewer confirms every ruling is placed exactly once, each
   tranche pairs its `package.xml` and `destructiveChangesPost.xml` for one deployment, annotation
   stories sit outside tranches, quarantine output and evidence agree with the rulings and rules the
   planner evaluates, and every story matches its required shape. Class source and org access facts
   appear as reader checks in the story. Write `BLOCKS` and `DISCRETION`
   findings to `plan.reviewFindings`. Fix every `BLOCKS` finding and regenerate. Put each
   `DISCRETION` finding in `open_items`.
6. **Compare confirmed reclaim and deliver.** Record `plan.confirmedCharacters` as the sum of
   characters from placed `remove` units and valid `annotate` stories. Compare it with
   `capacity.target.requiredCharacters`. Record `plan.tranches`, `plan.storiesDir`,
   `plan.capacityTotalsFile`, `plan.validationFile`, and the target outcome. State the target,
   required and confirmed characters, outcome, telemetry window, candidate and ruling counts, and
   pre-review selected, deferred, found-in-use, and kept-use-unknown counts. Label remove, annotate, keep, and decide-later
   ruling counts as post-review. The report shows ruled remove characters as placed removals plus
   the characters held in blocked units and in quarantine, beside the annotate rulings and the
   confirmed characters. Link `work/triage/deferred.csv`; do not print deferred
   names. Keep confirmed realized blank until the post-deployment Tooling delta reconciles with the
   Setup movement within T-5.

   Production Apex has no Delete action in Setup. Removal uses a Metadata application programming
   interface (API) deployment with a destructive-changes manifest and runs all local tests.
   Supported routes are the Salesforce command-line interface (CLI), a Workbench zip, or the
   customer's deployment pipeline; change sets cannot delete Apex. The release gate is a
   validate-only deployment of the exact manifest with `RunLocalTests`. A later metadata change
   invalidates that validation, and a failing tranche returns to planning.
7. **Test a requested selection round.** When the plan is clean, confirmed characters are below the
   requirement, `triage.eligibleDeferred` is above zero, and the customer asks for another selection
   round, regenerate triage before leaving this card: run
   `python3 <plugin>/scripts/capacity_triage.py --engagement <dir>` with the preserved
   `work/review/dispositions.csv`. This excludes `keep`, `remove`, and `annotate` rulings and makes
   `decide-later` rows eligible again. Record the new `work/triage/summary.json` counts in `triage`.
   A selection with a package takes TR-17; one with none takes TR-24.

## Outcomes, in precedence order

The first that holds wins.

- **TR-24 — the customer requested another selection round and step 7 selected no package.**
  Tell the customer that no further candidate can be selected and name each cause with its count
  from `work/triage/summary.json`, as card 02 does under TR-21. The delivered plan stands with
  outcome `target_unmet`. Record "selection round requested; no selectable candidate remains;
  removal plan delivered" in `decisions_log` with tranche count, annotation-story count, target,
  shortfall, and capacity totals. Write `{"current_state": "removal-planned", "current_step": null}`.
  Terminal: report `report/final-report.md`, `stories/`, and `work/plan/`, then stop.

- **TR-17 — the generator and reviewer are clean, confirmed characters are below the requirement,
  the customer requested another selection round, and step 7 selected at least one package.**
  Preserve `work/review/dispositions.csv`; append the review revision and shortfall to `decisions_log`. Write
  `{"current_state": "candidates-obtained", "current_step": "steps/03-reason-candidates.md"}`. Next
  card: `steps/03-reason-candidates.md` in the same turn.
- **TR-12 — the generator returned no invariant failure, the reviewer returned no `BLOCKS` finding
  on the current outputs, `report/final-report.md` exists, and confirmed characters meet the
  requirement, no eligible deferred candidate remains, or the customer accepts the shortfall.**
  Record "removal plan delivered" in `decisions_log` with tranche count, annotation-story count,
  target, outcome, and capacity totals. A remaining shortfall uses outcome `target_unmet` and is
  recorded as the customer's choice. Write
  `{"current_state": "removal-planned", "current_step": null}`. Terminal: report
  `report/final-report.md`, `stories/`, and `work/plan/`, then stop.

## Stop rule

Offer another selection round when a customer-chosen keep or decide-later ruling leaves a shortfall;
never force it. On TR-17, dispatch card 03 in the same turn. TR-24 is terminal. Otherwise record the customer's accepted
shortfall under TR-12 and report the deliverables.

## Failure

When a unit is blocked, state its `blockedReason` and what clears it: a live referrer is deactivated
or rewired, or the unit is ruled `keep` or `decide-later`. An unmanaged Process Builder referrer also has its
inactive versions deleted, since any flow version referencing the class blocks the delete. Record the reviewer's decision and
regenerate. If a `BLOCKS` finding survives T-10 generator runs, take it to the customer reviewer, who
chooses a precursor rewrite or changes the ruling to `keep`. The engagement stays on `list-reviewed`
until the plan validates.
