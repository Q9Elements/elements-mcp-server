# Story template

Every file under `stories/` follows one of these shapes. `scripts/removal_plan.py` writes each story;
a wrong story is corrected through its inputs and regenerated.

## Deletion or dependency-rewrite story

1. **Title:** `Remove <unit label>` or `Rewrite <caller> so <unit label> can be removed`.
2. **Identity:** every class and trigger in the unit, qualified names, Salesforce Id values, and the
   test classes that go with them.
3. **Capacity reclaimed:** counted characters for the unit, with zero-reclaim test classes listed
   separately.
4. **Evidence:** verdict per member, reasons for doubt, relevant blind spots, the targeted
   string-search result or its availability blind spot, and the telemetry window. When the search
   is available, state the result for every member, including no outside holder and each exempt test
   holder. List every event type absent from the telemetry ledger and explain that a class run only
   through an absent type looks unused.
   When a member is the only non-test static Apex caller of a non-candidate class that executed in
   the telemetry window, include `sole_caller_of_executed_class` in its reasons for doubt and name
   the executed class in supporting evidence.
5. **Impact:** incoming edges at planning time, the behavior that changes when the unit is gone,
   each deleted non-Apex referrer by type and application programming interface (API) name, each surviving test edited in the
   deployment, and each surviving class left without an incoming non-test Apex caller by the removal.
   State `Left with no caller after this removal: none.` and
   `Surviving test edits in this deployment: none.` when the respective lists are empty.
6. **Steps:** manifest placement and operational blockers. State that the units in the tranche
   deploy atomically as one deployment and that the manifest lists members alphabetically, an order
   with no meaning. Include `Referrers removed in the same deployment
   (`destructiveChangesPost`):`, followed by each referrer by type and name, or `None.` List each
   surviving test edited in the deployment under its own heading, `Surviving tests edited in the same
   deployment (`package.xml`):`. A blocked unit states under that heading, for each surviving test
   that references it, `Once unblocked, <test> must stop referencing <class>.` A blocked unit keeps
   every operational check its members carry. When a member has no scheduled job name
   but its name or automation summary names a schedule, require checking Setup > Scheduled Jobs for
   the class and deleting any pending job, since a pending scheduled job blocks the delete. For a
   member with `sole_caller_of_executed_class`, require checking Setup > Scheduled Jobs and, if a job
   exists, stopping for a new ruling before deletion. State:
   `Salesforce refuses to delete a referenced class, so each referrer lands in the same atomic
   deployment.` Put deleted Apex, attached tests, and deleted non-Apex referrers in
   `destructiveChangesPost.xml`. A non-Apex referrer enters that manifest under the application
   programming interface (API) name resolved from its `parentNodeId`, without a namespace copied
   from the edge label. When the API name is
   unavailable, omit the referrer from the manifest and state `delete <label> in Setup` as a manual
   step. A Process Builder Workflow or Workflow Rule is never put in the destructive manifest;
   require deactivation in Setup. When its API name carries no namespace prefix, state that
   deactivating is not enough: its inactive versions are deleted too, since any flow version
   referencing the class blocks the delete. A managed (namespaced) referrer omits that step. For each other deleted non-Apex referrer, state that the bundle
   does not contain incoming dependencies into it and require the reviewer to remove it from every
   page that uses it or deactivate it before deletion. State that production Apex has no Delete
   action in Setup. Removal is a Metadata API deployment with a destructive-changes manifest, and it
   runs all local tests. Supported routes are the Salesforce command-line interface (CLI), a
   Workbench zip, or the customer's own pipeline. Change sets cannot delete Apex.
7. **Verification:** validate the exact production manifest with all local tests before release. The
   Salesforce CLI validate-only command is
   `sf project deploy start --manifest package.xml --post-destructive-changes destructiveChangesPost.xml --test-level RunLocalTests --dry-run`.
   Require rollback on error and no ignore-errors behavior; any later metadata change invalidates the
   validation. Every story carries the fixed reviewer checklist the planner renders.
8. **Recovery packet:** immutable backup location and checksum, restore manifest, and honest recovery
   time. Deletion is irreversible, and recovery is a forward deployment through the same gates.
9. **Advice for review-first items:** where a reversible switch exists, such as an inactive trigger,
   aborted schedule, or revoked class access, use it for one customer-defined business cycle before
   deleting. Append each member's non-blank disposition `note` as the reviewer's note.

## Edited-test precursor story

1. **Title:** `Rewrite <test> so <units> can be removed`. One edited test has exactly one story in
   the tranche containing every removal unit it unblocks.
2. **Identity:** the surviving Apex test class, its qualified name, and Salesforce Id.
3. **Capacity reclaimed:** zero; the story edits a surviving test.
4. **Evidence:** names each removed class the test directly references and the tranche that
   removes it.
5. **Impact:** every removed class the test stops referencing and every surviving class it keeps
   referencing.
6. **Steps:** edit the test source, preserve its tested behavior for surviving classes, and list the test in
   the tranche's `package.xml`.
7. **Verification:** run
   `sf project deploy start --manifest package.xml --post-destructive-changes destructiveChangesPost.xml --test-level RunLocalTests --dry-run`
   from the tranche directory and require all local tests to pass.
8. **Recovery packet:** restore the prior test only together with the removed classes it references.
9. **Advice for review-first items:** deploy the test edit and deletions as one atomic deployment.

## Annotation story

1. **Title:** `Annotate <qualified name> as @isTest`.
2. **Identity:** qualified name and Salesforce Id.
3. **Capacity reclaimed:** the class's counted characters.
4. **Evidence:** only test classes call it, no entry-point signal exists, the telemetry window, the
   targeted string-search result when available, and every event type absent from the telemetry
   ledger.
5. **Impact:** `@isTest` stops the class's characters counting toward the allocation; nothing is
   deleted.
6. **Steps:** add `@isTest` to the class declaration and deploy through the customer's normal
   pipeline.
7. **Verification:** run the class's tests, refresh the unused Apex bundle, and confirm its characters
   stop counting.
8. **Recovery packet:** remove the annotation and redeploy the prior source if the class must return
   to production use.
9. **Advice for review-first items:** confirm with the code owner that the class is a test factory.
