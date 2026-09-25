# 03 Reason over the selected packages

State: `candidates-obtained`


## Purpose

Complete targeted string checks and the one-directional rescue pass for every selected package.
Deferred candidates remain represented in `work/triage/candidates.csv`; they are not assessment
failures.

## Procedure

1. **Check selected names as strings.** Read selected package headers from
   `work/triage/packages.json`. For every selected Apex class, call
   `code_search` with `refModelId: slots.model_id`, `teamId: slots.space_id`, and its bare name as
   `query`; when different, search its qualified name in a second call. A first call can return
   `status: "indexing"`;
   re-call with identical arguments about every 30 seconds until `status: "complete"` returns
   results. Search one class at a time. Search selected Apex classes only. Apex
   triggers are not searched: code references do not use trigger names, and an object-named trigger
   such as `Lead` would match every file that names that object. Write comma-separated values (CSV) to
   `work/triage/string-holders.csv` with columns `qualifiedName`, `holderName`, `holderType`,
   `holderIsTest`, and `holderInSelectedSet`. Drop a self-match only when the holder has the same
   qualified name and the candidate's own Apex kind. A same-named Flow or other non-Apex holder stays
   outside the removal set. Set `holderIsTest` from the matched bundle catalog row:
   match the hit's `nodeId` to catalog `nodeId`, then read `isTestClass`, `kind`, `isManagedPackage`,
   and `name`. `holderIsTest` is true when `isTestClass` is true, or when `kind=class`,
   `isManagedPackage` is true, and `name` ends in `Test`, `_Test`, or `Tests`; otherwise it is false.
   Write `false` for a non-Apex holder.
   A hit counts only when its holder is not a test class and
   is outside the proposed selected set. Write
   `work/triage/string-search-status.json` as `{ "status": "available" }`. Run
   `python3 <plugin>/scripts/capacity_triage.py --engagement <dir>` again. A non-test Apex holder that is
   an eligible candidate joins the package. A non-test Apex holder that is not a candidate or is ruled
   `keep` makes the package `in-use`. A non-Apex holder whose use Elements cannot see makes the package
   `kept-use-unknown`. Selection continues after either kept outcome. Check any newly selected class and repeat until every
   selected class has a completed search. When `code_search` is unavailable, write the holders header
   with no data rows and write `work/triage/string-search-status.json` as
   `{ "status": "unavailable" }`; rerun triage so `summary.json.stringSearch` is `unavailable`.
   State that blind spot in the report and every story. Never invent a search result.
   On a later optional selection run, prior `remove` and `annotate` rulings stay excluded and
   contribute to `summary.json.confirmedCharacters`; prior `keep` rulings stay excluded;
   `decide-later` rows are eligible again. All prior-ruling outcomes use candidate status `ruled`.
   Record the final run's counts from `work/triage/summary.json` in `triage`. If
   `triage.selectedPackages` is zero, skip steps 2 to 6 and take TR-22 or TR-23.
2. **Plan assignments.** A package contains the target class, its candidate Apex callers and non-test
   candidate Apex string holders recursively,
   every member of its strongly connected component, and every candidate reached through a test of
   any member, with those expansions repeated to a fixed point, plus tests attached by the planner's
   shared rule. Each selected package is one unit. Split a package above
   `reasoning.fragmentSize` into fragment units of at most that many assigned rows. The default comes from
   `data/thresholds.csv` T-3. The payload carries `assignedMembers`, the candidate rows the agent must
   return, separately from `component`. Component context contains its label, original size, summed
   characters, selected package member names with `lastModifiedDate`, and each assigned row's
   same-minute cluster count computed by the script over the complete original component using
   `data/thresholds.csv` T-6. Run

   `python3 <plugin>/scripts/reasoning_payloads.py --engagement <dir>`

   A new selection run archives the prior payload and return files, `return-batch-*.json` included,
   under `work/reasoning/previous/`. Each unit's payload is named by package,
   `payload-<packageId>.json`, with fragments named `<packageId>-fragment-N`. Each payload carries
   `packageId` and `componentLabel` separately. Its `rows` and `assignedMembers` contain only that
   unit's assigned rows. The script also packs the units, in order, into the `batches` of
   `work/reasoning/manifest.json`: each fragment unit is a batch on its own, and whole packages share
   a batch up to the same row limit.
3. **Reason only over assigned rows, one agent per batch.** For each batch in `manifest.json`
   `batches`, give one **candidate-reasoner** agent (tier `fast`, effort medium) the batch id, every
   payload file the batch lists, and the vocabulary paths in `references/data-contracts.md`. Follow
   [`references/orchestration.md`](../references/orchestration.md) and `data/agent-tiers.csv` for
   agent dispatch. The agent returns one
   JavaScript Object Notation (JSON) document `{"batch": "batch-NN", "units": [...]}` with one
   per-unit return for each payload, covering exactly the assigned rows, and keeps the
   one-directional rescue rule. Save it as `work/reasoning/return-batch-NN.json`. Retry one invalid
   batch return. Record a genuine assessment failure in `couldNotAssess`; never use that value for a
   capacity-deferred row.
4. **Apply deterministic facts.** Give each selected row the structural verdict and incoming-edge
   reading from the shipped data tables. Add `dynamic_dispatch_residue` with the counting holder as
   its quote. The merge in step 5 applies `data/telemetry-gap-mapping.csv` to each selected row and
   adds `telemetry_gap` and source quotes when the ledger supports a true gap. Telemetry-gap facts
   only add reasons or move a row to `review-first`.
5. **Group by package and merge.** Write `work/grouping.csv` with one row per selected candidate:
   `qualifiedName`, `groupLabel`, `groupOrder`, `groupNote`. One selected package is one group, in
   selection order. `groupLabel` is the package's name: a few plain words saying what its members
   share (e.g. "Auto-renewal order batch jobs"), never "Package N" or the seed class name alone.
   `groupNote` is one line on why the package looks removable, never a repeat of the label.
   Use reviewer language: say "last modified YYYY"; say a trigger "did not fire"; for a class reached
   only by its tests, say "only tests call it"; never cite a string hit whose
   only holders are test classes. Run:

   `python3 <plugin>/scripts/merge_reasoning.py --engagement <dir> --grouping work/grouping.csv`

   Then run:

   `python3 <plugin>/scripts/group_check.py --reasoned work/reasoned-candidates.csv --packages work/triage/packages.json`

   The merge accepts disjoint fragments whose union covers the package and rejects a missing assigned
   row. It reads `work/triage/candidates.csv` for entry-point channels and the telemetry ledger for
   true-gap counts. It writes selected rows only.
6. **Report the result.** Tell the customer every selected package in capacity order, its running
   character total, its
   counted characters and reasons for doubt, and the number of deferred candidates. State how many
   selected rows could not be assessed and how many lack cadence evidence. Do not print deferred names.

## Outcomes, in precedence order

The first that holds wins.

- **TR-22 — step 1's final triage selected no package and `work/review/dispositions.csv` is absent
  or holds no `remove` or `annotate` ruling.** Re-run
  `python3 <plugin>/scripts/candidates_report.py --engagement <dir>` and write
  `report/final-report.md` with the cause sections card 02 gives for TR-21, using final triage counts.
  Name string holders from each package's `inUseBecause` or `keptBecause` reason and list every
  reportable blind spot. Tell the customer that the string check found references outside the
  candidate set, give each cause and count, and state that no removal can be planned from this
  evidence. Record "string check left no selectable package, engagement closed" in `decisions_log`
  with the counts. Write `{"current_state": "removal-planned", "current_step": null}`. Terminal.
- **TR-23 — step 1's final triage selected no package and earlier `remove` or `annotate` rulings
  stand.** Tell the customer this round found no further selectable package, with the causes and
  counts from TR-22. Record "selection round selected nothing; planning the existing rulings" in
  `decisions_log` with the counts and `triage.shortfall`. Write
  `{"current_state": "list-reviewed", "current_step": "steps/05-plan-removal.md"}`. Dispatch
  `steps/05-plan-removal.md` in the same turn.

- **TR-09 — every batch is complete, `reasoning.pending` is empty, and every selected row has
  one verdict and one package group.** Record "selected packages reasoned" in `decisions_log` with
  package and bucket counts. Write
  `{"current_state": "candidates-reasoned", "current_step": "steps/04-review-list.md"}`. Next card:
  `steps/04-review-list.md`.

## Stop rule

Stop after TR-09 and hand the complete selected package list to the user for review. TR-22 is
terminal. On TR-23, dispatch card 05 in the same turn.

## Failure

Keep an invalid batch in `reasoning.pending`, named by its batch id, with its evidence in
`open_items`. Retry that batch, or lower `reasoning.fragmentSize` and rerun the payload script. A
selected row that remains unassessable uses verdict `unknown`, bucket `review-first`, and reason
`could_not_assess`. Stay on `candidates-obtained` until every batch is complete.
