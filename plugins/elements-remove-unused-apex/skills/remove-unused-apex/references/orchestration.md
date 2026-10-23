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

Card 04 records the customer's ruling on every selected package, with row overrides from
`data/dispositions.csv`. Once the reviewer declares the review finished, each displayed candidate
without a ruling is recorded `decide-later`; candidates not displayed remain unruled. The reviewer's
name and, when multiple names are given, the arbiter come from the reviewer-name field on the copy
carrying the *Review finished* declaration or from exported dispositions' `decidedBy` values. A named
person is required in the record. Ask when rulings arrive in conversation, when the returned copy or
exported dispositions carry no reviewer name, or when they carry a role rather than a person. Give
review-first advice once in conversation after the review is declared finished when at least one
review-first item is ruled `remove`. The analyst's only other ruling is a lower reasoning batch size (T-3).
Elements computes evidence, agents reason, and the script plans.

## Session rules

- Customer-facing prose names business outcomes, never mechanism.
- Record every human decision in `decisions_log` with who, what, and date. Record evidence captures,
  including the Setup banner and bundle `computedAt` and `syncTimestamp`, the same way.
- Never claim certainty of non-use. State the telemetry window with every figure. Keep candidate
  confidence at or below medium. Print
  every reportable blind spot defined for `work/bundle/blind-spots.json` in each report that relies on
  the bundle. Resolve ambiguity toward retaining more code.
- Poll `get_unused_apex_candidates` with identical arguments up to the T-7 cap (60 polls or
  30 minutes, whichever comes first), waiting for returned `retryAfterSeconds` or 30 seconds when
  absent. Stop at the time bound even if the next delay would extend past it.
  Preserve `capacity.readAt` and `stringSearch`. Its signed uniform resource
  locator (URL) has no returned lifetime field. Under T-9, fetch at once; re-call the tool for a
  fresh link if the fetch fails; never persist the URL. If the fresh link also fails, record the
  evidence and pause. Read automation context from selected candidate rows. Card 03 defines
  string-search polling and self-match handling for `run_code_search`.
- Parse a successful Model Context Protocol (MCP) response from the JavaScript Object Notation
  (JSON) text between `[TOOL DATA START]` and `[TOOL DATA END]` in its `content` array. An outer
  `isError: true` carries unframed JSON text. Read `error` first, then optional `message`, `flag`,
  `hint`, `reason` or `details`. `missing_required_scope` carries `requiredScope` without `message`;
  `missing_required_inputs` carries `missingInputs` and `inputDescriptions` without `message`.
  A successful transport response can still contain `status: "failed"`;
  that is a terminal job failure. Record its returned fields instead of assuming `error.code`.
  For outer errors `rate_limited`, `server_busy`, `too_many_concurrent_requests`, `at_capacity`,
  `unused_apex_analyses_at_capacity`, or `result_file_busy`, honor `retryAfter` in seconds before
  retrying the same request. For `status: "running"` or `status: "failed"` payloads, the conditional
  hint is `retryAfterSeconds` in seconds. Failed jobs end the attempt; retain any hint for a later
  retry rather than polling a failed job. If a retry response supplies no delay, use a tool-specific
  fallback where the card gives one; otherwise record the missing guidance and pause that operation.
  Poll repeat-call jobs using the same tool and identity arguments. Candidate identity includes
  `refModelId`, `teamId`, `staleAfterDays`, `capacity` (including `readAt`), and `stringSearch`;
  preserve returned `jobStartedAt` as evidence. `resultId` identifies a file result, not a reference
  model, metadata node, or mission. Preserve it in local evidence; these tools resume through the
  same call arguments and their returned part cursor. Native part-file jobs share a maximum of
  three active results per reference model and ten across the cluster, including source and change
  records. Candidate analyses have their own returned capacity refusals. See
  `references/mcp-contract.md` for inputs, access policy, refusals, and the complete call inventory.
- Before interpreting missing arrays, inspect `file`, `_truncated.inFile`, `_oversize.movedToFile`,
  and nested `{file: {url, ...}}` descriptors. Download whole-result files and moved values at once,
  parse their declared format, and restore each value at its original path, including `parts` and
  `failed`. A wholly moved page omits its inline row key; consume duplicate inline samples only once.
  A file descriptor carries `url`, `format`, `rows`, `bytes`, `sha256`, and `expiresInSeconds`;
  verify the checksum and honor that returned lifetime. Re-call with the same arguments for fresh
  links after expiry or fetch failure. A dispatcher file's lifetime applies to that file, not to an
  enclosed bundle URL. Unavailable data is never an empty array.
- **File-delivery rule.** Whenever a call requests `delivery: "file"`, a reply that fits the size
  budget contains inline rows with no `file` or `fileError`; read those rows inline. An oversized
  reply contains `file` with `url` and `expiresInSeconds`, and may include a checksum and row count;
  download it immediately, verify every supplied checksum and row count, and read the rows from disk.
  A supplied checksum is mandatory; a matching row count never substitutes for it. When no checksum
  is supplied, use a declared row count as the integrity check. In either case, continue
  the tool's own paging until no further pages remain: follow `_truncated.nextSkip` or the tool's
  `hasMore`/`nextSkip`, and preserve nested page cursors. A single file never replaces remaining
  pages. A reply with `fileError` means the file could not be written; its rows or trimmed page are
  inline, and paging continues using the cursors the reply describes. Retry a refused or incomplete
  page at a smaller limit before advancing.
- `get_dependencies` accepts one `nodeId` or `nodeIds`, with `refModelId: slots.model_id`,
  `teamId: slots.space_id`, and `lookingFor: "where_used"` for referrers or `"using"` for dependencies.
  Use `mode: "manifest"` for counts: read `nodes[].nodeId`, `nodes[].count`, `nodes[].byType`,
  `totalItems`, and `failed`. An optional `sfType` filters the related component type. A manifest
  returns counts and page planning, not rows. For the rows, repeat without `mode` (the default is
  `"page"`), preserving the node selection, direction, and type filter. Omit `skip` and `limit`;
  omit `format` for default newline-delimited JSON (NDJSON) files, or use `"ndjson"` or `"csv"`.
  `limit` applies only to manifest page planning. Use the file-part rules below for singular and
  bulk calls. Read `node`, `related`, and `direction` in each downloaded row: `node.nodeId` is the
  queried endpoint; `related.nodeId` is the referrer for `where_used` and dependency for `using`.
  These rows are a separate contract from the candidate bundle's `edges.csv`.
- `get_access` liveness reads pass the class `nodeId`, `refModelId: slots.model_id`,
  `teamId: slots.space_id`, and `type: "profile"` for the guest-profile check. Rows come as native
  part files for either selector: omit `delivery`, `skip`, `limit` and `includeUsers`; omit `format`
  for NDJSON or use `"csv"`. Use `mode: "manifest"` only for holder counts. Read `holder.type`,
  `holder.name` and `access` in each downloaded `{node, holder, access}` row under the part-file
  rules below. A class listed in `failed` has incomplete access evidence, not zero grants.
- For row-paged `get_component_change_history` reads, request `delivery: "file"` and `limit: 200`
  (the tool maximum), applying the file-delivery rule above. Follow `_truncated.nextSkip` first,
  then returned `nextSkip`,
  using `skip` and preserving the other arguments. Use actual returned row count only when the
  response explicitly indicates further rows and supplies no cursor. A short or empty page with a
  cursor still needs continuation. For `get_metadata_component` summary sublists, read `fields.items`
  and `relationships.inbound.items` or `.outbound.items`; follow each nested `nextSkip` with
  `delivery: "file"` and `page: { list, skip, limit: 1000 }` (the tool maximum), applying the
  file-delivery rule above, including after an empty page when a cursor exists. Single-component
  name lookups keep their inline request.
- The liveness sources in `data/root-kinds.csv` use `list_metadata_by_criteria` with `metadataList`
  and `mode: "page"`. Obtain model-specific active/status column keys from `describe_metadata_schema`
  with the same `refModelId`, `teamId`, and `metadataList`; read keys from `columns[].value`.
  Both tools require metadata read scope and reference model view access.
  `Requires a Pro Plus space` means the Space needs a Core or Advanced Metadata Management plan; an invisible
  reference model returns `not_found`, "Org model not found or you don't have access to it."
  Record the returned gap and its owner using the access policy in `references/mcp-contract.md`.
  Use only columns with `filterable: true` and their `allowedOperators` for filters. The list-valued
  `tags`, `optimization_status`, and `parent_manage_package` columns are display-only; scalar
  `parent_object` remains filterable. Clean-up view date cutoffs are computed when the view is read;
  polling a cached completed file can reuse that result for 1,800 seconds. Include every filter
  column in any explicit `columns` list; read returned node
  identifiers as `nodeId` and application programming interface (API) names at `sf.apiName` when
  nested there. Metadata change-tracking `status` does not establish runtime activity: use the
  type's actual active/status column.
- `run_code_search`, page-mode `list_metadata_by_criteria`, `get_dependencies` and `get_access`
  return part files. Omit `delivery` on these four tools in every mode.
  Always read each returned `expiresInSeconds`, download at once, and repeat the identical call
  for a fresh link.
  CSV (comma-separated values) output strips hidden Unicode and prefixes formula-like cells with
  a single quote; read identifiers from parsed response fields rather than spreadsheet rendering.
  Download `parts` in `index` order, follow the actual `nextPartsFrom` with
  `partsFrom`, and concatenate in that order. Keep `partsFrom` fixed while polling each part page;
  preserve the other arguments and omit row `skip` and `limit`. Scope saved parts to `resultId`.
  If it changes, discard held parts and restart descriptor enumeration at `partsFrom: 0`. Verify
  each part's `sha256`, `bytes`, and `rows`; identical identity/index/checksum with fresh links is
  the same part. Reconcile unique downloaded part indices with `partsTotal` and parsed rows with
  `totalRows` at completion. Retain only the first CSV header when joining. Always omit `format` for
  `run_code_search`. Parts can arrive while `status: "running"`; honor `retryAfterSeconds` and poll
  the same page until complete. `partsTotal` and `totalRows` cover finished batches until
  `status: "complete"`. Completion requires that status, every part page downloaded, and an empty
  `failed` list. An absent `failedTotal` with an empty `failed` means no failures. When `failedTotal`
  or `failedFile` is present, account for every failure they report; download `failedFile`
  immediately and honor its `expiresInSeconds`. Use each failed entry's `rowsWritten` to identify
  rows written before that component failed and discard those rows before retrying that component.
  An unavailable failure file or an inline preview shorter than `failedTotal` leaves failure
  accounting incomplete. Replace refreshed parts by index rather
  than appending duplicates; a retry can repeat partially written rows. Use `totalRows` for written
  rows, not a count of queried nodes. When failures remain, report incomplete evidence rather than
  interpreting missing relationships as non-use.
- Copy identifiers and qualified names programmatically from tool responses and files. Keep the full estate in
  Elements and the local bundle; provide agents and the orchestrator only contract-defined summaries
  and selected rows.
- Every error the method makes is toward keeping code. When a rule is ambiguous, take the reading that
  retains more.
- Card 04 records the reviewer's name from the completed review copy or exported dispositions.
- At `removal-planned`, report the deliverables and stop. On re-invocation, ask whether the user wants
  a new engagement or a review of the finished engagement.
