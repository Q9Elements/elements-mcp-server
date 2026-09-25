---
name: elements-agent-opportunities
description: >-
  Scan an entire Salesforce org's telemetry and schema to find, rank, and justify agentic
  opportunities ("40 candidates, here are the top 3, and why") without a human architect spending
  weeks. Use when the user asks to find agent opportunities, where they should use agents/AI, for an
  AI roadmap for their org, to scan their org for automation or agent candidates, or for an agentic
  opportunity scan. Read-only: it finds and justifies opportunities; it does NOT build agents. Do NOT use to
  rank agent opportunities inside one already-generated lifecycle process diagram (an object's record-type
  activities); use elements-org-to-process's Agent Finder rubric for that scoped view.
---

# Elements: Agentic Opportunity Scan

The server tool `scan_agentic_opportunities` aggregates and scores the org's signals. Classify each
object, select finalists, inspect their evidence, and explain the ranking with `scoreFactors` and
telemetry fields. Use `get_object_usage` to inspect each finalist.

## Prerequisites
- Token scopes `mcp:spaces:read mcp:metadata:read`. Multi-space token → pass `teamId` on every call.
- A `refModelId` (the synced Salesforce org). Resolve with `list_reference_models` if unknown.
- Read/analyze only; nothing is written to Salesforce or Elements.
- License tiers differ by tool: `scan_agentic_opportunities`, `get_object_usage`, `get_field_population`, and
  `get_dependencies` need a Pro space. Field-level verification in Stage 2 requires an Enterprise
  space for `list_metadata_columns` and `query_metadata`; the fallback's
  `get_object_dependency_analysis` also requires Enterprise. `explain_metadata_item` needs the org
  artificial intelligence (AI) analysis license plus Generative Pre-trained Transformer (GPT) features.

## Telemetry is tiered; never present a gap as "no usage"
The scan degrades gracefully. Before writing anything, read `summary.eventLogsAvailable` and each object's
`velocity.dataAvailable` / `population.dataAvailable`, and choose language accordingly:
- `eventLogsAvailable: false` → the org isn't syncing Event Monitoring. Say "engagement signals require
  Event Monitoring sync (not enabled here)", never "this object is unused."
- `eventLogsAvailable: true` but every object's `engagement.available` is false → the space is *licensed*
  for Event Monitoring but has no synced event-log data yet. Treat engagement as unavailable (as above) and do
  not use the assistant/deflection lane; never promise view/user counts you can't produce.
- Choose the scan scope before ranking. `objectTypes` takes `standard`,
  `custom`, `namespace` (managed-package objects, both kinds) or `all`, and defaults to `all`.
  Package logging and plumbing tables often rank high on volume signals while being useless as agent
  candidates. To exclude them, scan with `custom` or `standard` and state the scope in the report.
- Automation counts (`automation.totalDependencies` / `byType`) are declarative/config only; they come
  from `sf.summaryInfoObjects` and exclude record-triggered Flows, Apex classes/triggers, and Global
  Actions. A low count is a hint, not proof of an automation gap; confirm with `get_dependencies`
  in Stage 3 before telling a customer an object is under-automated.
- `velocity.dataAvailable: false` → no daily record snapshots for that object. Fall back to
  `records.lastModified` recency language ("last touched …"; `records.lastCreated` comes only with
  `detail: "full"`), not "no growth."
- `mode: "manifest"` cannot answer the velocity question. A manifest summary skips the velocity
  aggregation and reports `velocityDataAvailable: null` — unknown, *not* unavailable. Use a page call
  before saying anything about growth data coverage.
- Velocity is a net record delta. `velocity.net30` (and `net7`, with `detail: "full"`) is net record
  change from daily snapshots, not a created/updated/deleted split; `detail: "full"` rows state this as
  `velocity.basis: "netRecordDelta"`, and summary rows omit `basis` but carry the same kind of number.
  The snapshot window behind it is `velocity.windowDays` in the `get_object_usage` response, which can
  be shorter than 30 on a recently created reference model. Say "net +N records over the last
  <windowDays> days", taking both numbers from the response, and note "created/updated/deleted (CUD) breakdown needs the CUD usage package."
- `population.dataAvailable: false` → no field-population telemetry; don't infer adoption from it.
- When included, flag managed-package objects (apiName has a namespace prefix like
  `abc__Object__c`) and recommend around schema the customer cannot change.

## Workflow

### Stage 0: Context
Resolve the space + reference model (`get_active_space` / `list_authorized_spaces` / `list_reference_models`). `get_active_space` reports the session's active space and ignores any `teamId` you pass; for a space other than the session's, pass its `teamId` to `list_reference_models` and confirm the space from the response's `activeSpace {teamId, name}` (or from `list_authorized_spaces`).
Check `.elements/{spaceId}/{refModelId}/agent-opportunities.md` for a run < 24h old; if present, mention it and
reuse it (instant replay) instead of re-scanning. Specifics:
- `{spaceId}` is the same value as the `teamId` you pass to the tools (the Elements space id).
- Root `.elements/` at the workspace top, found with `git rev-parse --show-toplevel` (fall back to the
  current directory only if that fails), not the process cwd, which may be a subdir. A wrong root makes you
  miss an existing cache and needlessly re-scan.
- Age check: read the file's first line, which must be `generatedAt: <ISO8601 UTC>` (see Stage 4); compute
  age from that. Only if the header is genuinely absent, fall back to file mtime, and treat mtime as
  unreliable (a `git clone`/copy/worktree checkout rewrites it to "now", so a stale scan can look fresh); when
  you fall back, say so and lean toward re-scanning if anything looks off.
- Reuse vs re-scan: if the user is doing a normal scan, mention the cached run and reuse it by default
  (offer a fresh re-scan as an option). If the user explicitly asked to re-scan, skip the cache.
- What to present on replay: echo the cached digest's telemetry-coverage line + the top-3 finalists block
  (scores + one-line receipts), and state plainly it's a cached result from `<generatedAt>`. Offer to open the
  saved HyperText Markup Language (HTML) report. Do not call any scan tool on the replay path.

### Stage 1: Org-wide scan (one call)
Call `scan_agentic_opportunities(refModelId, limit: 25, sortBy: "score")` for the ranked top page (the
candidates you'll narrate); this is the primary call and fits inline.

For the complete ranked table (all scanned objects, Tab 2 of the report), get the full corpus without
blowing context. `{top}` is the workspace top Stage 0 resolved (`git rev-parse --show-toplevel`, else the
current directory), so the page and master files sit under the same `.elements/` root Stage 0 reads:
1. `scan_agentic_opportunities(refModelId, mode: "manifest")` → read `totalObjects`, `numPages`.
2. For each page, call with `format: "ndjson", skip: <n*pageSize>` and write the returned `data` string to
   `{top}/.elements/{spaceId}/{refModelId}/scan-page-{n}.ndjson` (zero-pad `n`, e.g. `scan-page-00`). Use one
   subagent per page, each returning only its file path, with at most 3 in flight at a time (see Rate
   limit below); without a subagent facility, page sequentially and still write each page straight to its
   file.
3. Merge and verify with the bundled script:

   ```
   python3 <skill-dir>/scripts/merge_ndjson.py '{top}/.elements/{spaceId}/{refModelId}/scan-page-*.ndjson' \
           {top}/.elements/{spaceId}/{refModelId}/scan-master.ndjson --expected {totalObjects} --key nodeId
   ```

   It concatenates the pages in numeric order, checks every line parses and the count equals
   `totalObjects`, and exits 0 only when the merge is intact. Parse the merged file for the table with
   `jq`/`python` rather than reading it back into context. For a preview, show the top page and
   label the ranking provisional; the complete report requires the full corpus.

Record `summary` (objectsScanned, objectsWithSignal, eventLogsAvailable, velocityDataAvailable).

Rate limit. The server allows 60 requests per minute per token, and every session using the same token
draws on that budget. Exceeding it returns a `rate_limited` tool error ("the token is locked for 60
seconds") carrying `retryAfter`. On `rate_limited`, stop issuing calls, wait the full `retryAfter` (retrying
early fails), retry the failed call, then continue one call at a time. It is a throttle, never a licensing
or data signal.

### Stage 2: Judgment layer (you, plus one field-type check per shortlisted object)
Classify each object from its signal vector using this taxonomy (the Agent Finder scoring expressed as
explicit heuristics, aligned to its shipped taxonomy). **Cite the `scoreFactors` / signal fields behind every call**;
see `references/scoring.md` for how to read them.

| Signal pattern | Classification |
|---|---|
| High volume + fewer than two long-form fields carrying the record's main content + low automation (confirmed in Stage 3 via dependencies) | Deterministic-automation gap (also a quick-win / cleanup lane) |
| High volume + fewer than two long-form fields carrying the record's main content + moderate or heavy automation (confirmed via dependencies) | Well-automated / no clear agent gap: note it and move on |
| High volume + two or more populated long-form fields carrying content people write or read | Conversational agent / AI-workflow candidate: humans read & write prose at volume; confirm field purpose and population before assigning this lane |
| High field count + low population (many fields barely filled) | Cognitive-overload → agent-assisted data entry, or cleanup |
| High engagement (`engagement.views30d`, `engagement.available:true`) + manual patterns on hot paths | Assistant / deflection candidate |
| Zero / stale records regardless of schema | Cleanup: route to `elements-tech-debt`, not an agent |

> The scan's `automation` count is declarative/config only (excludes Flows + Apex). "Deterministic-automation gap" and "Well-automated" both hinge on the *real* automation landscape; always confirm with `get_dependencies` for incoming Flows and Apex classes in Stage 3 before asserting either. Most high-volume standard objects land in Well-automated, not a gap.

**Recompute the free-text ratio for an initial shortlist, then expand until the top 3 are verified.**
The scan's `unstructuredRatio` can count short Text fields (Email, Phone, Zip, codes) as free text:
a lead web-form staging object can score 0.571 (32 of 56 fields) while its only long-form field is
a single `Comments__c`. Start with 3 to 5 candidates. Call
`list_metadata_columns(refModelId, metadataList: ["Field"])` once to confirm the field column keys
and discover the population column and its operators. For each object being recomputed, one call at a time:

1. `query_metadata(refModelId, metadataList: ["Field"], filters: [{column: "full_api_name", operator:
   "startswith", value: "<ObjectApiName>/"}], columns: ["full_api_name", "subtype", "length"], format:
   "ndjson", limit: 200)`. The separator is `/`, and a filter column must also
   be listed in `columns`. Write `data` to `{top}/.elements/{spaceId}/{refModelId}/fields-<ObjectApiName>-{n}.ndjson`;
   when `hasMore` is true, page with `skip` into the next file. Filter on `full_api_name`; a `parent_object`
   filter returns `mcp_tool_failed`.
2. `python3 <skill-dir>/scripts/free_text_ratio.py "{top}/.elements/{spaceId}/{refModelId}/fields-<ObjectApiName>-*.ndjson" --fields-total <schema.fieldsTotal> --server-ratio <schema.unstructuredRatio>`
   (quote the entire page pattern; the script expands it and exits 2 if no page file exists). It counts Long Text Area (subtype `Text area`, length
   over 255) and Rich Text Area as free text, lists the fields, and prints `recomputedRatio` beside
   `serverRatio`; add `--include-short-text-area` to also count short Text Area fields. A warning that the row
   count differs from `fieldsTotal` means a missed page.
3. Replace the `unstructuredRatio` score contribution with `28 × recomputedRatio` when available
   (see `references/scoring.md`). One recompute costs one `query_metadata` call when all fields fit
   in one page; each additional page costs another call. Show both ratios wherever the ratio appears
   ("free text 0.018 recomputed, 0.571 server").

After the initial shortlist, use recomputed scores for checked rows and server scores for unchecked
rows to identify the next recompute set. This mixed ordering is provisional. Identify the current
top 3 and their lowest score. Recompute every unchecked top-3 row and every unchecked row whose
server score reaches or exceeds that lowest score, then re-rank the full corpus. Repeat until all
top 3 rows are recomputed and no unchecked row outranks or ties the lowest finalist. Do not finalize
the top 3 while either condition remains. For example, four unchecked scores (56.68, 56.44,
55.39, 55.20) outrank the recomputed shortlist (52.67, 49.71, 48.83, 46.94); recompute all four in
the next round, then apply the same stopping test. Mark each ranked-table row as "recomputed" or
"server ratio" so readers can see which scores still use the server ratio.

When the recompute is unavailable (the query errors, no page file exists, or the script exits 2 with
no rows), keep the server ratio and flag it as "server ratio, unverified; may count short Text fields"
in the table, the finalist tab and the digest. An unavailable recompute does not satisfy the top-3
stopping test; report the unresolved ranking instead of presenting it as verified.

A ratio screens candidates; the field list and population establish the Conversational lane. Count
only long-form fields whose content people write or read, such as message bodies, request details,
and case notes. Machine-written or integration content, including log payloads, stack traces,
limits dumps, id lists, and integration or queue buffers, does not count. `Integration_Log__c` has
`Payload__c`, `Stack_Trace__c`, and `Limits_Snapshot__c` as Apex-written logs and does
not qualify. `Support_Request__c` has `Request_Details__c`, `Steps_Taken__c`, and
`Additional_Information__c` and qualifies when those fields are populated. `EmailMessage` has
`HtmlBody` and `TextBody` and qualifies when both are populated.

Before assigning Conversational, check population for each qualifying field. `get_field_population`
with `refModelId` supplies object-level band counts, not field names. Use the
`list_metadata_columns` result to find the field-population column's actual key, units, and allowed
operators. Then call `query_metadata(refModelId,
metadataList: ["Field"], filters: [{column: "full_api_name", operator: "startswith",
value: "<ObjectApiName>/"}, {column: "<discovered population column>", operator: "gt",
value: <50 percent in the column's units>}], columns: ["full_api_name",
"<discovered population column>"], format: "ndjson", limit: 200)` and page if needed.
The `gt` operator must be listed in `allowedOperators`; include every filter column in `columns`.
Intersect the returned field names with the human-content long-form fields. A field filled on 50%
or fewer records lacks a populated majority and does not count. If field-level population is
unavailable, keep the Conversational lane provisional. For `Web_Lead__c`, one auxiliary
`Comments__c` field is below the conversational criterion; confirmed automation density determines
its structured lane. Apply Cleanup first for zero or stale records, then Conversational for qualifying
content, then the confirmed automation lanes for other high-volume objects. Keep the lane provisional
until the content, population, and Stage 3 dependency checks are complete. Cognitive-overload and
Assistant / deflection describe separate field-population and engagement signals; report them as
secondary opportunities when a primary lane already applies.

Pick the top 3 finalists (default), usually the highest scores after the recompute, but apply judgment:
skip pure-cleanup and managed-package-only candidates when a better agent story exists; prefer a spread across
classifications if it makes a richer narrative.

### Stage 3: Deep-dive the finalists
Per finalist, one call at a time (the Rate limit in Stage 1 applies; three finalists at 4 to 5 calls each
share the token's budget with any other session):
- `get_object_usage(refModelId, nodeId)`: record-by-type counts, the velocity series + net deltas, and
  engagement (the receipts). Quote the striking numbers.
- Retrieve each finalist's full-detail scan row by `nodeId`, paging through
  `scan_agentic_opportunities(refModelId, detail: "full")` if necessary. Finalists selected after
  recomputation can differ from the scan's first three rows. Read its `scoreFactors`
  (weight/value/detail), population `bands`, `automation.byType`, `velocity.net7` / `basis`, and
  `records.lastCreated`.
- `get_dependencies(refModelId, nodeId, lookingFor: "incoming", sfType: "Flow")`, then again with
  `sfType: "Apex Class"`: the automations an agent would coexist with, and the evidence for the
  automation-density lanes.
- If an automation needs explanation, call `explain_metadata_item` with `aspect: "chain"` on
  that Flow, Trigger, or Apex class to see what it handles.
- `get_field_population` gives per-object band counts (how many fields fall in each population band), not
  field names. To name the specific under-populated/unused fields on an object, use `query_metadata` with a
  population filter for that object.
- If another explanation call is already
  generating the same node, you get `{status:"generating", retryAfterSec:30, maxWaitSec:240}` instead —
  poll every ~30s (never tighter) until it returns, up to ~4 minutes total (the in-flight lock's time to live (TTL); a
  big-object generation can hold it ~60-90s, so one retry is not enough); still generating past ~4 minutes
  means the lock self-expired and the generation likely failed — say so rather than waiting longer. A bare
  `tool_timeout` is the separate, generic per-call deadline — retry once rather than polling.

### Stage 4: Deliverable (two surfaces)
Produce a chat digest and a tabbed HTML report (build from
`templates/report.html`; if the client can't render artifacts, the chat digest stands alone):
- Tab 1 (Executive summary): N candidates by classification; an explicit telemetry-coverage statement
  (which signals are live vs. require Event Monitoring / the CUD package in this org).
  Count each object once in its primary lane. Cognitive-overload and Assistant / deflection may also be
  secondary opportunities, so the lane tiles need not sum to the candidate total.
  Fill the report placeholders as follows: `{{REFMODEL_NAME}}` = reference-model name; `{{SCANNED_COUNT}}` =
  number of scanned objects; `{{EXEC_NARRATIVE}}` = executive-summary narrative; `{{N_CANDIDATES}}` =
  candidates with signal; `{{N_CONV}}`, `{{N_DET}}`, `{{N_WELL}}`, and `{{N_CLEANUP}}` = objects whose
  primary lane is conversational-agent, automation-gap, well-automated, or cleanup, respectively;
  `{{N_OVERLOAD}}` = count of objects whose primary or secondary lane is Cognitive-overload;
  `{{N_ASSIST}}` = count of objects whose primary or secondary lane is Assistant / deflection;
  `{{COVERAGE_STATEMENT}}` = signals live in this org and signals requiring Event Monitoring or the CUD
  package; `{{RANKING_STATUS}}` = ranking completion status and any unresolved ranking reason.
- Tab 2 (Ranked table): every scanned object: score, score source ("recomputed" or "server ratio"),
  classification, one-line why. Identify unresolved ranking if the stopping test cannot complete.
- Tabs 3–5 (one per finalist): narrative, the signal receipts (charts/numbers), confirmed Flow and
  Apex class counts from Stage 3, scan config-item count, current-automation map, recommended agent
  shape, expected-impact framing. Fill `F1_FLOWS`, `F1_APEX`, `F1_CONFIG` and the corresponding
  `F2_` and `F3_` placeholders. For finalist 1, fill `{{F1_NAME}}` = object name, `{{F1_CLASS}}` =
  classification, `{{F1_NARRATIVE}}` = finalist narrative, `{{F1_RECORDS}}` = record count,
  `{{F1_UNSTR}}` = free-text ratio with its score source or unverified status, `{{F1_VELOCITY}}` = net
  records per 30 days, `{{F1_FLOWS}}` = confirmed incoming Flow count, `{{F1_APEX}}` = confirmed incoming
  Apex class count, `{{F1_CONFIG}}` = scan config-item count, and `{{F1_CONTENT_FIELDS}}` = qualifying
  content fields with field-level population. For finalists 2 and 3, fill `{{F2_NAME}}`, `{{F3_NAME}}` =
  object names; `{{F2_FLOWS}}`, `{{F3_FLOWS}}` = confirmed incoming Flow counts;
  `{{F2_APEX}}`, `{{F3_APEX}}` = confirmed incoming Apex class counts; and
  `{{F2_CONFIG}}`, `{{F3_CONFIG}}` = scan config-item counts.
- Chat digest: the top 3 with one paragraph each, their scores, evidence, and coverage limits.
Write `.elements/{spaceId}/{refModelId}/agent-opportunities.md` as the cached record, rooted at
the workspace top (`git rev-parse --show-toplevel`). Its first line is
`generatedAt: <ISO8601 UTC>` (e.g. `generatedAt: 2026-07-06T23:24:00Z`), the age source Stage 0 reads.
After that header, include the telemetry-coverage statement and the top-3 finalists
block so the replay is self-contained. Also save the populated HTML alongside it (`agent-opportunities.html`).

### Stage 5: Handoffs (offer, don't push)
(a) "Assess before building" → `elements-decision-engine` on the chosen candidate;
(b) requirement + stories via `elements-decision-engine`: its workflow creates the mission and accepted
option that its final step, `run_backlog_draft`, requires (the scan produces no mission). For stories from
a process diagram instead, use `elements-stories`.

## Fallback path (if `scan_agentic_opportunities` is unavailable)
`query_metadata` over objects with columns RECORD_COUNT, LAST_MODIFIED_RECORD_DATE, LAST_CREATED_RECORD_DATE
(filter RECORD_COUNT to reproduce `minRecordCount`) → `get_field_population` (manifest, full corpus) → `get_object_dependency_analysis`
(manifest) → join + score in-skill (subagent fan-out per page, merged with `scripts/merge_ndjson.py` as in Stage 1). No velocity/engagement,
~10× the tool calls; it works but is visibly slower.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back short even though the
call succeeded. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note, nextSkip}`, with `nextSkip` present inside
`_truncated` when the tool paginates, not at the top level. Resume the next call from
`_truncated.nextSkip` rather than from your own offset arithmetic, since the backstop
also rewrites `pageSize` and sets `hasMore` to stay consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged `_oversize`. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.
