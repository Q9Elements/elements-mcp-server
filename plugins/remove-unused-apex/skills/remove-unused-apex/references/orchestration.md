# Orchestration reference

## Dispatching agents

`data/agent-tiers.csv` assigns each agent a capability tier and effort. When the host lets the
orchestrator choose a subagent model, `strong` is the most capable model the host offers and `fast` is
its cheaper general model, at the row's effort. When the host offers no choice, the agent runs on the
inherited model. The orchestrator itself is never downgraded. The table is host-neutral; each agent's
`model` frontmatter is the Claude host's mapping of its tier, `fast` to `sonnet` and `strong` to
`opus`. Other hosts map by tier.

## Shipped surfaces and what each is authoritative for

- `steps/*.md`: the cards; each owns one state's procedure and outgoing transitions.
- `data/*.csv`: the single authority for every value, including the counted-set decision procedure, the thresholds
  table, root kinds and liveness tests, event-resolution precedence, execution-context codes, the
  reasoning vocabulary (incoming-edge readings, verdicts, review-first reasons, rescue signals), the
  looks-dead-but-is-not patterns, quarantine rules, the reviewer's dispositions, blocked reasons,
  blind-spot markers, the telemetry gap mapping, and the capability register.
- `references/method-notes.md` (design rules, scope, platform constraints), `data-contracts.md` (every
  exchanged file and the candidate bundle), `evidence-acquisition.md` (the Setup banner and egress),
  `kickoff-checklist.md` (the opening customer checklist), `story-template.md`
  (story section order), and `orchestration.md` (agent tiers, shipped surfaces, human decisions, and
  session rules).
- `templates/execution-state.json`: the tracker every engagement copies; authoritative for its schema.
- `agents/` (plugin level): `candidate-reasoner`, `removal-plan-generator`, `removal-plan-reviewer`.
- `scripts/` (plugin level): `capacity_triage.py`, `candidates_report.py`, `merge_reasoning.py`, `review_page.py`,
  `removal_plan.py` (the planner the generator wraps), `group_check.py`, and `lint.py`.

## Human decisions

Card 04 records the customer's reviewer's ruling on every selected package, with row overrides from
`data/dispositions.csv`. Once the reviewer declares the review finished, each displayed candidate
without a ruling is recorded `decide-later`; candidates not displayed remain unruled. The reviewer
name is recorded on card 04. The analyst's only other ruling is a lower reasoning batch size (T-3).
Elements computes evidence, agents reason, and the script plans.

## Session rules

- Customer-facing prose names business outcomes, never mechanism.
- Record every human decision in `decisions_log` with who, what, and date. Record evidence captures,
  including the Setup banner and bundle `computedAt` and `syncTimestamp`, the same way.
- Never claim certainty of non-use. State the telemetry window with every figure. Keep candidate
  confidence at or below medium. Print
  every reportable blind spot defined for `work/bundle/blind-spots.json` in each report that relies on
  the bundle. Resolve ambiguity toward retaining more code.
- Poll `get_unused_apex_candidates` with identical arguments at the T-7 interval and cap. Its signed
  uniform resource locator (URL) lives T-9; fetch the bundle at once and request a fresh URL on fetch
  failure. Do not store the URL. For `get_dependencies`, pass `lookingFor`, `nodeId`,
  `refModelId: slots.model_id`, and `teamId: slots.space_id`. In single-type mode, pass `sfType` and
  `limit: 100`, then increase `skip` by 100 until a page returns fewer than 100 rows. Read automation
  context from selected candidate rows. Card 03 defines string-search polling and self-match handling
  for `code_search`.
- Copy identifiers and qualified names programmatically from tool responses and files. Keep the full estate in
  Elements and the local bundle; provide agents and the orchestrator only contract-defined summaries
  and selected rows.
- Every error the method makes is toward keeping code. When a rule is ambiguous, take the reading that
  retains more.
- The reviewer's name is recorded on card 04, not at kickoff.
- At `removal-planned`, report the deliverables and stop. On re-invocation, ask whether the user wants
  a new engagement or a review of the finished engagement.
