# 04 Review the list with the customer

State: `candidates-reasoned`

## Purpose

The customer looks at the selected packages before anything is planned for removal. A named person
rules on package membership with the evidence in front of them; deferred candidates remain outside
the displayed decision scope.

## Procedure

1. **Name the reviewer.** Ask who at the customer rules on removals, and record the name (a person, not
   a role) in `review.reviewer`. If more than one, record all and who arbitrates.
2. **Build the review page.** Before running the renderer, call `get_dependencies` once for the
   first displayed row, with `lookingFor: "incoming"`, its `nodeId`,
   `refModelId: slots.model_id`, `teamId: slots.space_id`, and `limit: 1`.
   Display order is selected package order, then review-first before confident, then descending
   counted characters, then qualified name. Record the response's `baseUrl` in
   `execution-state.json` as `slots.elements_base_url`; record `null` when it is absent.
   Build from `work/triage/packages.json` and
   `work/reasoned-candidates.csv` as one self-contained HyperText Markup
   Language (HTML) file,
   `report/04-review-pack.html`; tabs per grouping; within each, review-first rows first, then confident.
   Run `python3 <plugin>/scripts/review_page.py --engagement <engagement-dir> --org-name "<org name>" --reviewer "<review.reviewer>" --ref-model-id "<id>"`;
   omit `--ref-model-id` when it is unavailable; pass `--out <path>` only when the standard report path must be
   overridden.
   One section per selected package appears in selection order. Each section shows candidate members,
   attached tests, counted characters, the running total against `capacity.target.requiredCharacters`,
   and every reason for doubt with its quotes. The page shows selected packages only. Each package heading
   is the package seed class name. If the seed is blank, use the first non-blank member
   `groupLabel`, then the package id; show its `groupNote` beneath. Per row, show the class and its
   verdict in plain words,
   the counted characters and, when `capacity.reconciled` is true, the corresponding percentages; an evidence pop-up (telemetry in words, count/rate,
   automation summary, string-reference hits, dependencies both ways with the inbound non-Apex referrers
   named as "delete or edit these first"), a deep link to the node in Elements, and the matching lines
   from `data/looks-dead-but-is-not.csv` for items that look dead but might not be, with the check each
   names. The telemetry window and every blind spot go at the top, never below the fold; the default *All groups*
   view shows them above the table. The page carries a
   decision control per row (the values in `data/dispositions.csv`) and a note field. The `annotate`
   ruling appears only for a test-only class with no entry-point signal. The page has a package-level
   ruling that applies to every displayed member unless overridden, a reviewer-name field pre-filled from step 1, a *Review finished* button,
   and an *Export dispositions.csv* button. Rulings are saved into the page itself (on a published-artifact
   surface through the page's save action; from a local browser by re-downloading the page). When a
   reviewer asks why a class is not on the list, answer from `work/triage/packages.json`
   (`inUseBecause`, `keptBecause`) or `work/triage/deferred.csv` (not needed for this target).
3. **Present it** (`data/capabilities.csv` CAP-06). If the host has a published-artifact surface, publish the file as a
   private Artifact and record its uniform resource locator (URL) in `review.artifact`; otherwise hand
   the reviewer the file and record
   its path. The reviewer may rule in the page, return the exported `dispositions.csv`, or rule in
   conversation; the orchestrator accepts any of these and writes every ruling itself; never an agent.
   When more than one copy comes back, the one carrying the *Review finished* declaration is authoritative;
   record its 256-bit Secure Hash Algorithm (SHA-256) digest next to the bundle digest in
   `decisions_log`. If two copies disagree, stop and ask the
   reviewer; never merge silently. Say plainly that the file holds the customer's own metadata (class names,
   descriptions, automation summaries) before it is mailed anywhere.
4. **Record every ruling** using one of the values in `data/dispositions.csv`, with the reviewer's name, date, and
   note in `work/review/dispositions.csv` (contract in `references/data-contracts.md`). Every displayed candidate
   has exactly one row; when the reviewer **declares the review finished**, every displayed candidate
   still without a ruling is written `decide-later`. Candidates not displayed have no row and stay unruled. Record the session in `decisions_log` (reviewer, date, the
   declaration, counts of each ruling).
5. **Review-first advice.** For every `remove` ruling on a review-first item, give the reviewer the one
   line the method offers in conversation: where a reversible switch exists, such as an inactive
   trigger, aborted schedule, or revoked class access, use it for one customer-defined business cycle
   before deleting. Each story carries the same advice in **Advice for review-first items**. The
   orchestrator and review page leave `note` empty unless the reviewer supplies text. The playbook
   adds no trial or soaking phase beyond that one line of advice.
6. **Record counts** in `review.remove`, `review.annotate`, `review.keep`, `review.decideLater`, `review.completedOn`,
   `review.dispositionsFile`; increment `review.revision`; copy the `decide-later` count into
   `open_items`. The `decide-later` names are the matching rows in `work/review/dispositions.csv`;
   `work/triage/deferred.csv` holds candidates deferred by triage. Whenever a package is ruled `keep`,
   the page states confirmed reclaim so far against the target.

## Outcomes, in precedence order

The first that holds wins.

- **TR-10 — the reviewer has declared the review finished and at least one selected package member is ruled
  `remove` or `annotate`.** Write `{"current_state": "list-reviewed", "current_step": "steps/05-plan-removal.md"}`.
  Next card: `steps/05-plan-removal.md`.
- **TR-11 — the reviewer has declared the review finished and every candidate is ruled `keep` or
  `decide-later`.** Nothing is to be planned. Write `report/final-report.md`: the reviewed list with its
  rulings, the target, required and confirmed characters, outcome `target_unmet`, selected, deferred,
  found-in-use, and kept-use-unknown counts, a `## Decide-later rulings` table from
  `work/review/dispositions.csv` with class and reviewer note, a `## Not reviewed this round` sentence
  with the row count from `work/triage/deferred.csv` and no deferred names, the blind spots, and the
  telemetry window;
  record "review complete; no
  removals ruled" in `decisions_log`. Write `{"current_state": "removal-planned", "current_step": null}`.
  Terminal.

## Stop rule

Stop after writing either outcome. Card 04 pauses at the human review gate before card 05, and
TR-11 is terminal.

## Failure

If the reviewer is unavailable, or has ruled on part of the list without declaring the review finished,
stay on `candidates-reasoned` and record the pending set in `open_items`; neither outcome holds until the
declaration is recorded. If the reviewer asks for evidence the pack does not hold (a change history, who
last modified a class), call `get_node_change_history` with `nodeId: <node id>`,
`refModelId: slots.model_id`, and `teamId: slots.space_id`. For `get_dependencies`, use
`lookingFor: "incoming"`, `nodeId: <node id>`, `refModelId: slots.model_id`, and
`teamId: slots.space_id`. Add the result to the pack and continue; a
ruling is never pressed for.
