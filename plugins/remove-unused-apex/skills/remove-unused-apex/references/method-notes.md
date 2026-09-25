# Method reference

The deliverable is a **capacity-targeted, evidence-backed set of removable Apex packages, ruled on by the customer, turned
into removal and annotation stories with consumers listed first for reading order, each tranche deploying as one, and the capacity each reclaims.** The
customer executes every change; the playbook deploys, deletes, and deactivates nothing.

## Scope boundary

- **In:** every org-owned Apex class and trigger, including unmanaged and unlocked package code, which
  counts toward the limit.
- **Out:** managed-package Apex (exempt from the limit; never a candidate, but kept in the graph as a
  caller); removing a package and the code coupled to it; finding duplicate capability across classes;
  reclaiming characters inside classes that stay; severity definitions, deprecation
  windows, and tracker choice. These remain the customer's business.
- **Not a phase:** restrict-and-observe. Apex classes have no off switch; only triggers do. The method
  gives one line of advice on review-first items (the **Advice for review-first items** section of
  `references/story-template.md`) and nothing more.
- **Deployment choice:** the customer chooses the Salesforce command-line interface (CLI), Workbench, or
  their own pipeline. The playbook supplies the destructive-changes manifest and validation contract.

## Prerequisites before candidate computation

Card 01 requires two customer inputs, the Setup Apex Classes banner and the capacity target, and one
access check, the bundle host. A target usage percentage needs the banner's exact character count;
when the banner does not show it, card 01 asks once for the target as a percentage to free or a
number of characters. It confirms that the org is synced to Elements with the sync
complete, and establishes that Event Monitoring is on. The probe establishes Event Monitoring when
`hasEventMonitoring` is true and `daysAvailable` meets T-13 (one distinct daily log date); the
candidate tool checks for daily Apex usage telemetry when it computes the bundle. The artificial intelligence (AI) analysis
entitlement controls one rescue signal; the report identifies when that signal is unavailable.

**Event Monitoring is required for candidate computation.** Every Apex event type except
`ApexUnexpectedException` is a paid entitlement. Card 01 treats `hasEventMonitoring: true` with
T-13 dates as proof of the paid entitlement. One returned daily log date means the Event Monitoring
add-on is on.

## Design rules

- **Window adequacy is measured.** The observation window `W` is the method constant of 90 calendar days in
  Coordinated Universal Time (UTC), ending yesterday. The effective window is the telemetry the org
  holds, and the report states both. A class whose only plausible use is on a cadence longer
  than `W` is caught by the rescue pass on card 03, never by a kickoff question.
- **The measure is what Setup says it is.** The Apex Classes page states it: "characters of Apex Code
  (excluding comments and @isTest annotated classes) … includes both Apex Classes and Triggers". No
  application programming interface (API)
  exposes the figure or the allocation; the playbook captures the banner at intake and reconciles to it.
  The counted-set rules reproduce that figure: Σ `LengthWithoutComments` over unmanaged classes without a
  class-level `@IsTest` annotation plus unmanaged triggers equals the banner to the character on a clean
  org (whitespace included; comments excluded). A residual on card 02 is therefore a fact about the org,
  such as unlocked packages, invalid rows, or a deployment between the two reads, to diagnose and never a
  reason to bend the rules.
- **The counted set is a decision procedure** (`data/counted-set-rules.csv`): the first decisive rule
  is the receipt. The capacity total is reconciled to the figure Setup displays within the band
  `data/thresholds.csv` T-1 gives; a residual is diagnosed, never smoothed, and an unreconciled estate
  proceeds **without capacity figures** and says so.
- **Capacity selection is package-based.** `capacity_triage.py` sorts known candidate lengths by
  counted characters, then qualified name. A package contains the target class, its candidate Apex
  callers and non-test candidate Apex string holders recursively, every member of its strongly
  connected component, and every candidate reached
  through a test of any member, with those expansions repeated to a fixed point, plus tests attached
  by the planner's shared rule. Classes a package calls are not pulled in merely
  because they are providers. Selection stops when feasible reclaim covers the customer target or
  eligible candidates are exhausted.
- **Every outside reference resolves to an outcome.** A surviving Apex caller or string holder makes
  the package `in-use`. A non-Apex string holder or Flow reference whose use Elements cannot see makes
  the package `kept-use-unknown`. Eligible candidate callers and string holders join the package.
  Unknown character lengths remain `unknown-length`. Only `selected` packages contribute capacity.
- **Root liveness.** A root that cannot fire confers no reachability: an inactive trigger, a
  `Schedulable` with no schedule and no observed run, a page on no layout, an `@AuraEnabled` class
  granted to no profile. Liveness is what makes silence interpretable: inactive root + silence = dead;
  live root + silence = the window may be too short.
- **Declared roots are not merged into "used".** Representational State Transfer (REST), Simple Object
  Access Protocol (SOAP), Aura, invocable, async, and email roots
  are externally callable by definition, but treating that as use makes a genuinely dead endpoint
  undiscoverable. It becomes a printed *reason* on the candidate instead.
- **Sound over-approximation.** Every static path is assumed possible; no dead-branch or parameter
  analysis. The closure traverses any node type that can reach Apex (flow → subflow → Apex, page →
  controller, component → `@AuraEnabled`, platform-event subscribers, scheduled jobs) and stops at
  dynamic dispatch, package boundaries, ambiguous identity, and untrusted edges, emitting that residue
  as declared blind spots. Every error is toward over-retention.
- **Test-only reachability is its own category.** A non-test class is test-only when at least one test
  calls it and no production, candidate, or other caller does. With three or more test callers and no
  entry-point signal, it becomes its own selection unit and those tests are not attached. With one or
  two test callers, or an entry-point signal, its tests stay attached. A test factory with no
  entry-point signal can be ruled `annotate`; its characters then count toward the target while
  nothing is deleted.
- **Incoming edges are the liveness signal; outgoing edges only order removal.** A dead class may
  freely call live classes; the caller is what died.
- **The rescue pass is one-directional.** An agent may move a candidate from *confident* to *review
  first*; it never moves one toward removal and never issues a use verdict. Signals are applied
  strongest first (`data/rescue-signals.csv`) and every flag quotes the text it relied on.
- **The verdict vocabulary is fixed** (`data/verdicts.csv`). "Dormant removal candidate" is at most
  medium confidence; there is no "certain".
- **The human gate sits between reasoning and planning.** The customer rules on selected packages;
  when the reviewer declares the review finished, every displayed candidate still without a ruling is
  written `decide-later`, and candidates not displayed have no row and stay unruled. The pipeline is
  not one continuous large language model (LLM) walk.
- **The removal plan is deterministic.** A shipped script, wrapped by an agent, performs the
  topological sort, cycle collapse, dependency ordering, story rendering, and report rendering.
- The playbook does not read test coverage, and the customer's sandbox deployment applies Salesforce's own coverage gate.
- **Capacity totals stay distinct:** confirmed realized, deletion forecast reconciled, unreconciled
  deletion candidate, and annotation forecast.
- **The LLM never sees the universe.** Elements computes over the estate; scripts read the complete
  local bundle; agents and the orchestrator receive compact summaries and selected rows.

The bundle contains dependency facts, and targeted `code_search` results live in
`work/triage/string-holders.csv`. The planner evaluates the rules those files support; reviewers check
declared-root and access facts in the class source.

## Platform constraints that shape the method

- Scheduled Apex is identified in telemetry by the **cron job name**, not the class; the name is free
  text, munged (`:` becomes `-`), need not contain the class name, and the tables that resolve it purge
  within the window `data/thresholds.csv` T-2 gives. The candidate tool snapshots them at every telemetry
  pull and joins against the snapshot, never live state.
- `AsyncApexJob.Status` is not execution evidence for scheduled jobs (they abort their own schedule
  after running); the event row says whether it ran, the job row only links it to a class.
- Event log files are not a system of record: partitions can be missing, and a gap is
  indistinguishable from "never ran". The ledger names every gap and the verdict `unknown` exists for
  classes whose runs could fall inside one.
- Deleted Apex cannot be restored by Salesforce; recovery is a forward deploy through the same gates.
  Every story carries a recovery packet.
- Production Apex has no Delete action in Setup. Removal is a Metadata application programming
  interface deployment with a destructive-changes manifest, and it runs all local tests. The
  validate-only Salesforce CLI route is
  `sf project deploy start --manifest package.xml --post-destructive-changes destructiveChangesPost.xml --test-level RunLocalTests --dry-run`.
  A Workbench zip or the customer's own pipeline may perform the same deployment. Change sets cannot
  delete Apex.
- The dependency graph does not see strings. Card 03 searches each selected class name and records
  typed holders. A non-test holder outside the selected or confirmed set blocks the package and sends
  the class to review first. An unavailable search is a named blind spot in the summary, report, and
  every story.
