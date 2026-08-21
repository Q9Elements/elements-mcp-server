---
name: elements-agent-opportunities
description: >-
  Scan an entire Salesforce org's telemetry and schema to find, rank, and justify agentic
  opportunities ("40 candidates, here are the top 3, and why") without a human architect spending
  weeks. Use when the user asks to find agent opportunities, where they should use agents/AI, for an
  AI roadmap for their org, to scan their org for automation or agent candidates, or for an agentic
  opportunity scan. Read-only: it finds and justifies opportunities; it does NOT build agents. Do NOT use to
  rank agent opportunities inside one already-generated lifecycle process diagram (an object's record-type
  activities) — use elements-org-to-process's Agent Finder rubric for that scoped view.
---

# Elements: Agentic Opportunity Scan

This skill turns one org-wide telemetry scan into a ranked, justified set of agentic opportunities. The
server tool `scan_agentic_opportunities` does the mechanical aggregation and scoring; **you are the
judgment layer**: you classify each object's signal vector into an opportunity type, pick the finalists,
deep-dive them, and write the "why" from the numbers the org actually produced. Every claim traces to a
`scoreFactor` or a telemetry field; that is the whole point: the receipts are real.

**Key tools this skill relies on:** `scan_agentic_opportunities` and `get_object_usage`, alongside the
standard Elements metadata tools. **Non-goal:** building agents — that's the agent platform's job.

## Prerequisites
- Token scopes **`mcp:spaces:read mcp:metadata:read`**. Multi-space token → pass `teamId` on every call.
- A **`refModelId`** (the synced Salesforce org). Resolve with `list_reference_models` if unknown.
- Read/analyze only; nothing is written to Salesforce or Elements.
- License tiers differ by tool: `scan_agentic_opportunities`, `get_object_usage`, `get_field_population`, and
  `get_dependencies` need a Pro space; `get_object_dependency_analysis` needs an Enterprise space — if it 403s
  on license, use `get_dependencies` for the same Stage 3 confirmation instead; `explain_metadata_item` needs
  the org AI-analysis license plus GPT feature access.

## Telemetry is tiered; never present a gap as "no usage"
The scan degrades gracefully. Before writing anything, read `summary.eventLogsAvailable` and each object's
`velocity.dataAvailable` / `population.dataAvailable`, and choose language accordingly:
- **`eventLogsAvailable: false`** → the org isn't syncing Event Monitoring. Say "engagement signals require
  Event Monitoring sync (not enabled here)", never "this object is unused."
- **`eventLogsAvailable: true` but every object's `engagement.available` is false** → the space is *licensed*
  for Event Monitoring but has no synced event-log data yet. Treat engagement as unavailable (as above) and do
  not use the assistant/deflection lane; never promise view/user counts you can't produce.
- **Exclude managed-package objects unless you want them.** `objectTypes` takes `standard`,
  `custom`, `namespace` (managed-package objects, both kinds) or `all`, and defaults to `all`.
  Package logging and plumbing tables often rank high on volume signals while being useless as agent
  candidates, so scan with `custom` or `standard` to keep them out of the ranking.
- **Automation counts (`automation.totalDependencies` / `byType`) are declarative/config only**; they come
  from `sf.summaryInfoObjects` and **exclude record-triggered Flows, Apex classes/triggers, and Global
  Actions**. A low count is a hint, not proof of an automation gap; confirm with `get_object_dependency_analysis`
  in Stage 3 before telling a customer an object is under-automated.
- **`velocity.dataAvailable: false`** → no daily record snapshots for that object. Fall back to
  `records.lastModified`/`lastCreated` recency language ("last touched …"), not "no growth."
- **`mode: "manifest"` cannot answer the velocity question.** A manifest summary skips the velocity
  aggregation and reports `velocityDataAvailable: null` — unknown, *not* unavailable. Use a page call
  before saying anything about growth data coverage.
- **`velocity.basis: "netRecordDelta"`** → velocity is net record change from daily snapshots, NOT a
  created/updated/deleted split. Say "net +N records / 30d", and note "created/updated/deleted breakdown
  needs the CUD usage package."
- **`population.dataAvailable: false`** → no field-population telemetry; don't infer adoption from it.
- **Managed-package objects** (apiName has a namespace prefix like `abc__Object__c`): include and flag them,
  but note their schema isn't the customer's to change; recommend around them.

## Workflow

### Stage 0: Context
Resolve the space + reference model (`get_active_space` / `list_authorized_spaces` / `list_reference_models`).
Check `.elements/{spaceId}/{refModelId}/agent-opportunities.md` for a run < 24h old; if present, mention it and
reuse it (instant replay) instead of re-scanning. Specifics:
- **`{spaceId}` is the same value as the `teamId` you pass to the tools** (the Elements space id).
- **Root `.elements/` at the workspace top**, found with `git rev-parse --show-toplevel` (fall back to the
  current directory only if that fails), not the process cwd, which may be a subdir. A wrong root makes you
  miss an existing cache and needlessly re-scan.
- **Age check:** read the file's first line, which must be `generatedAt: <ISO8601 UTC>` (see Stage 4); compute
  age from that. Only if the header is genuinely absent, fall back to file mtime, and treat mtime as
  unreliable (a `git clone`/copy/worktree checkout rewrites it to "now", so a stale scan can look fresh); when
  you fall back, say so and lean toward re-scanning if anything looks off.
- **Reuse vs re-scan:** if the user is doing a normal scan, mention the cached run and reuse it by default
  (offer a fresh re-scan as an option). If the user explicitly asked to re-scan, skip the cache.
- **What to present on replay:** echo the cached digest's telemetry-coverage line + the top-3 finalists block
  (scores + one-line receipts), and state plainly it's a cached result from `<generatedAt>`. Offer to open the
  saved HTML. Do **not** call any scan tool on the replay path.

### Stage 1: Org-wide scan (one call)
Call `scan_agentic_opportunities(refModelId, limit: 25, sortBy: "score")` for the ranked top page (the
candidates you'll narrate); this is the primary call and fits inline.

For the **complete ranked table** (all scanned objects, Tab 2 of the report), get the full corpus without
blowing context:
1. `scan_agentic_opportunities(refModelId, mode: "manifest")` → read `totalObjects`, `numPages`.
2. For each page, call with `format: "ndjson", skip: <n*pageSize>` and write each page to a file, then merge
   (the standard manifest→ndjson fan-out; one subagent per page, each returns only its file path). Parse the
   merged file for the table. (For a quick pass you can skip this and just show the top 25; say so.)

Record `summary` (objectsScanned, objectsWithSignal, eventLogsAvailable, velocityDataAvailable).

### Stage 2: Judgment layer (you, no tools)
Classify each object from its signal vector using this taxonomy (the Agent Finder scoring expressed as
explicit heuristics, aligned to its shipped taxonomy). **Cite the `scoreFactors` / signal fields behind every call**;
see `references/scoring.md` for how to read them.

| Signal pattern | Classification |
|---|---|
| High volume + high **structured** ratio + low declarative-automation density **(confirmed low in Stage 3 via dependencies)** | **Deterministic-automation gap** (also a quick-win / cleanup lane) |
| High volume + already heavily automated (confirmed via dependencies) + low/moderate unstructured ratio | **Well-automated / no clear agent gap**: the common case for mature standard objects; note it and move on, don't force a bucket |
| High volume + high **unstructured** ratio (free-text fields populated) | **Conversational agent / AI-workflow** candidate: humans read & write prose at volume |
| High field count + low population (many fields barely filled) | **Cognitive-overload** → agent-assisted data entry, or cleanup |
| High engagement (`engagement.views30d`, `engagement.available:true`) + manual patterns on hot paths | **Assistant / deflection** candidate |
| Zero / stale records regardless of schema | **Cleanup**: route to `elements-tech-debt`, not an agent |

> The scan's `automation` count is declarative/config only (excludes Flows + Apex). "Deterministic-automation gap" and "Well-automated" both hinge on the *real* automation landscape; always confirm with `get_object_dependency_analysis` / `get_dependencies` in Stage 3 before asserting either. Most high-volume standard objects land in **Well-automated**, not a gap.

Pick the **top 3 finalists** (default), usually the highest scores, but apply judgment: skip pure-cleanup
and managed-package-only candidates when a better agent story exists; prefer a spread across classifications
if it makes a richer narrative.

### Stage 3: Deep-dive the finalists
Per finalist, in parallel where possible:
- `get_object_usage(refModelId, nodeId)`: record-by-type counts, the velocity series + net deltas, and
  engagement (the receipts). Quote the striking numbers.
- `scan_agentic_opportunities(refModelId, limit: 3, detail: "full")` (or re-read the finalist) for the full
  `scoreFactors` (weight/value/detail), population `bands`, and `automation.byType`.
- `get_object_dependency_analysis` + `get_dependencies` on the object: the current automation landscape an
  agent would coexist with.
- `explain_metadata_item` with `aspect: "chain"` on the 1–2 heaviest automations touching it: what's already
  handled deterministically.
- `get_field_population` gives per-object band **counts** (how many fields fall in each population band), not
  field names. To name the specific under-populated/unused fields on an object, use `query_metadata` with a
  population filter for that object.
- *(Optional, richer)* `explain_metadata_item` with `aspect: "chain"` on the object's automations: what they do and the chain they sit
  in. It normally returns in one call (~10-20s LLM generation, no polling needed). If another call is already
  generating the same node, you get `{status:"generating", retryAfterSec:30, maxWaitSec:240}` instead —
  **poll every ~30s (never tighter) until it returns, up to ~4 minutes total** (the in-flight lock's TTL; a
  big-object generation can hold it ~60-90s, so one retry is not enough); still generating past ~4 minutes
  means the lock self-expired and the generation likely failed — say so rather than waiting longer. A bare
  `tool_timeout` is the separate, generic per-call deadline — retry once rather than polling.

### Stage 4: Deliverable (two surfaces)
Two surfaces: a chat digest **and** a tabbed HTML artifact (build from `templates/report.html`; if
the client can't render artifacts, the chat digest stands alone):
- **Tab 1 (Executive summary):** N candidates by classification; an explicit **telemetry-coverage statement**
  (which signals are live vs. require Event Monitoring / the CUD package in this org).
- **Tab 2 (Ranked table):** every scanned object: score, classification, one-line why.
- **Tabs 3–5 (one per finalist):** narrative, the signal receipts (charts/numbers), current-automation map,
  recommended agent shape, expected-impact framing.
- **Chat digest:** the top 3 with one paragraph each + the "weeks of architect time in minutes" framing.
Write `.elements/{spaceId}/{refModelId}/agent-opportunities.md` as the cached record (for Stage 0 reuse and
the failure-playbook replay), rooted at the workspace top (`git rev-parse --show-toplevel`). **The VERY FIRST
line MUST be** `generatedAt: <ISO8601 UTC>` (e.g. `generatedAt: 2026-07-06T23:24:00Z`); this is the single
authoritative age source Stage 0 reads; do **not** rely on a prose "Run at …" line or on file mtime (mtime is
reset by clone/copy). After that header, include the telemetry-coverage statement and the top-3 finalists
block so the replay is self-contained. Also save the populated HTML alongside it (`agent-opportunities.html`).

### Stage 5: Handoffs (offer, don't push)
(a) requirement + stories via `elements-stories`;
(b) proposed nodes via `create_proposed_node`.

## Fallback path (if `scan_agentic_opportunities` is unavailable)
`query_metadata` over objects with columns RECORD_COUNT, LAST_MODIFIED_RECORD_DATE, LAST_CREATED_RECORD_DATE
(filter RECORD_COUNT to reproduce `minRecordCount`) → `get_field_population` (manifest, full corpus) → `get_object_dependency_analysis`
(manifest) → join + score in-skill (subagent fan-out per page, merge_ndjson pattern). No velocity/engagement,
~10× the tool calls; it works but is visibly slower.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note}`, plus **`nextSkip`** when the tool paginates —
resume the next call from `nextSkip` rather than from your own offset arithmetic, since the backstop
also rewrites `pageSize` and sets `hasMore` to stay consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Guardrails
- Never equate "no event-log data" with "unused"; state the license gap.
- `velocity.dataAvailable: false` → recency language, not "no growth."
- Managed-package objects: include but flag; recommendations must respect that their schema isn't the
  customer's to change.
- This skill **finds and justifies** opportunities; it does **not** build agents (explicit non-goal).
