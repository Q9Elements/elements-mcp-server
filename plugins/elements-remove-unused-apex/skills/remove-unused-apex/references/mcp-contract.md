# Elements Model Context Protocol contract inventory

Model Context Protocol (MCP) requests use the registered tool names below and parsed response
identifiers. This inventory covers the entrypoint, cards, references, data tables, local scripts,
fixtures, and tests. It defines the tool contract; `references/data-contracts.md` defines local
bundle and planning files. JavaScript Object Notation (JSON), newline-delimited JSON (NDJSON),
comma-separated values (CSV), uniform resource locator (URL), application programming interface
(API), and 256-bit Secure Hash Algorithm (SHA-256) retain these meanings throughout this file.

## Inputs, outputs and ownership

Input: one production Salesforce reference model, the Setup Apex Classes capacity banner, and the
customer's capacity target. Output: verified candidate evidence, selected dependency-complete
packages, customer rulings, and local removal and annotation stories. A refusal has outer
`isError: true` and unframed JSON containing `error`; read `error` first, then `message`, `flag` and
`hint` when present. A successful
transport response with `status: "failed"` ends that job attempt. Neither supplies an empty result.

For example, allocation 6,000,000 and a target of 5 percent to free require 300,000 characters.
A candidate response disqualified for `NO_APEX_TELEMETRY` records the telemetry blocker and owner;
it does not supply a usable candidate set. A feature refusal records the missing feature instead.

| Owner | Responsibility |
|---|---|
| Server dispatcher | Schema, Open Authorization (OAuth) scopes, space selection, feature flags, refusal framing and optional whole-result files. |
| Tool and file helper | Resource guards, job identity, bundle or part production, counts, signed links and cursors. |
| Playbook orchestrator | Stable arguments, hydration, immediate downloads, integrity checks, evidence accounting, local state and customer handoff. |
| Local scripts | Validate saved evidence and compute triage, rendering and plans; they make no MCP calls. |
| Customer | Intended space and reference model, capacity target, rulings and Salesforce changes. |

## Flags and permissions

Flags and permissions are separate checks. Tool availability and model permissions are separate checks. Model permissions are checked on calls;
listing tools checks whether any granted space satisfies flags for any mode, without testing the
caller's role. A listed tool can refuse the chosen space or reference model.

| Tools | OAuth scope | Resource permission and extra conditions | Map correction |
|---|---|---|---|
| `get_space_context` | `mcp:spaces:read` | Authorized grant; active/authorized space discovery. | C10 |
| `list_reference_models` | `mcp:spaces:read` | Unsuspended space; readable reference models only. | C10 |
| `has_event_monitoring`, `get_unused_apex_candidates` | `mcp:metadata:read` | Reference model binding and view. Salesforce Event Monitoring licensing, collection and telemetry remain separate evidence. | C11 |
| `run_code_search` | `mcp:metadata:read` | Reference model view for cached results; edit for a new search. Sync/index readiness still applies. | C5 |
| `describe_metadata_schema`, `list_metadata_by_criteria` | `mcp:metadata:read` | Reference model view. | C1 |
| `get_dependencies`, `get_access`, `get_metadata_component`, `get_component_change_history` | `mcp:metadata:read` | Reference model binding and view; history retains a non-suspension check. Access user enumeration additionally needs Editor and a billable plan. | C9 |

The candidate and Event Monitoring tools check reference model binding and view access. Domain permission holders,
customer roles, copyright licensing, local plan state, and the telemetry requirements keep their
domain meaning (C17).

## Refusals and recovery

Quote server text exactly. In the parameterized messages, substitute the parsed identifier.

| Condition | `error`, extras and exact `message` |
|---|---|
| MCP disabled | `feature_not_enabled`, `flag: "licenseFlags.mcpServer"`, "Elements MCP is not enabled for this space" |
| `plan.proPlus` | `feature_not_enabled`, `flag: "plan.proPlus"`, "Requires a Pro Plus space"; it means the Space needs a Core or Advanced Metadata Management plan. |
| `licenseFlags.orgDependencyExplorer` | `feature_not_enabled`, `flag: "licenseFlags.orgDependencyExplorer"`, "Requires Dependency Explorer add-on"; contact your Elements representative, who can match it to your plan. |
| Feature missing here, present in another authorized space | Same `feature_not_enabled` code, `flag` and message, plus `hint: "Call get_space_context to see the spaces this token may use, then set_active_space."` A retry in another space can still be refused. |
| Invisible reference model | `not_found`, "Org model not found or you don't have access to it." |
| New search lacks edit | `access_denied`, `permission: "edit on the org model"`, "Requires edit access to org model <refModelId>." |
| Missing scope | `missing_required_scope`, `requiredScope`; no `message`. |
| Missing inputs | `missing_required_inputs`, `missingInputs`, `inputDescriptions`; no `message`. |
| Ambiguous space | `active_space_required`, "This OAuth token is authorized for multiple Elements spaces. Call get_space_context, choose one, and pass its teamId into the next tool call." |
| No selected space for binding | `active_space_required`, "No active Elements space is selected on this token. Pass teamId, or call get_space_context." |
| Unauthorized explicit space | `unauthorized_space`, "The requested teamId is not authorized for this OAuth token." |
| Reference model in another space | `wrong_active_space`, "This reference model belongs to a different space than the token's active one. Pass that space's teamId (see get_space_context), or re-authorize with it selected. Note: list_reference_models only lists the active space." |
| Access user enumeration lacks Editor | `forbidden`, "includeUsers needs the Editor role in this space; user lists are not shown to viewers. Call again without includeUsers for the permission holders." |
| Access user enumeration lacks billable plan | `feature_not_enabled`, "includeUsers is not available on this space's plan; the Elements UI does not list users here either. Call again without includeUsers for the permission holders." |
| Native file pool full | `at_capacity`, `retryAfter: 30`, "This reference model already has 3 file results being written. Retry with the same arguments shortly." |

OAuth transport failures precede dispatch. Hypertext Transfer Protocol (HTTP) 403 with
`insufficient_scope` can report "The user's Enterprise account is suspended or closed." or
"No authorized active Elements spaces are available." Keep these distinct from tool refusals.
For tool `invalid_input`, retain the schema's `details` and correct the named field; do not retry
unchanged. Unsupported names raise protocol `MethodNotFound`.

The session retry dictionary in `references/orchestration.md` includes `rate_limited`,
`server_busy`, `too_many_concurrent_requests`, `at_capacity`,
`unused_apex_analyses_at_capacity`, and `result_file_busy`: honor returned `retryAfter`.
Candidate infrastructure errors can return `unused_apex_candidates_infrastructure` with `stage`.
Capture only fields returned by the server. For candidate failures, Salesforce-specific
`statusCode` and `errorCode` are conditional; if absent, record unavailable cause detail and ask
for that evidence rather than inferring a Salesforce error. A failed job may supply
`retryAfterSeconds` for a later attempt, not continued polling of that failed attempt.

Native file jobs can fail with `read_timeout`, `result_file_failed`, `file_output_failed`, or
`result_too_large`. A complete job can still contain failed components. Retain `failed`,
`failedTotal`, `failedFile`, and each component's `rowsWritten`; missing failure evidence leaves
the operation incomplete. Follow the session file rules before interpreting any missing array.

## Tool calls, response paths and termination

For every data call, `refModelId` comes from the selected `referenceModels[].refModelId` and
`teamId` from `activeSpace.teamId` or the chosen authorized space. Metadata `nodeId` comes from
bundle catalog rows, edges, or tool rows. History `changeLogId` comes from `changeLogs[]._id`.
A native `resultId` identifies a file computation; it is never a model, node, mission or resume
argument. This playbook uses no mission tool. Preserve returned identifiers as text, never by
retyping names or constructing links.

| Tool | Arguments used and bounds | Response paths used and stop condition |
|---|---|---|
| `get_space_context` | `skip` 0 to 100000, `pageSize` 1 to 100 (default 50). No `delivery` or `teamId`. | `active`, `authorized`, `pagination`; consume all actual authorized-space pages before declaring the grant exhausted. |
| `list_reference_models` | Selected `teamId`, `delivery: "file"` for potentially trimmed lists. No row limit or skip input. | `activeSpace.teamId`, `referenceModels[].refModelId`, name, status, `createdAt`, `updatedAt`. Hydrate a whole-result file; if still trimmed, narrow using the tool's `search` argument. On `fileError`, use the inline evidence, then retry the same call once or narrow with `search`; the tool has no paging. Model dates do not prove sync readiness. |
| `has_event_monitoring` | 24-hex `refModelId`, `teamId`. | `hasEventMonitoring`, `daysAvailable`, `oldestLogDate`, `newestLogDate`, `reason`. One probe, with the card's one-distinct-day gate; false is telemetry evidence, not entitlement evidence. |
| `get_unused_apex_candidates` | 24-hex IDs; `staleAfterDays: 90` (schema 1 to 3650); `stringSearch: false`; `capacity: {allocation, displayedPercent, readAt, charactersUsed?}`. Allocation is a positive integer, percent 0 to 100, optional count a nonnegative integer, readAt a zoned timestamp. | `status`, `jobStartedAt`, `retryAfterSeconds`; complete disqualification `reason`, `ledger`, `owner`; qualified complete `computedAt`, `syncTimestamp`, `telemetryHighWater`, `summary`, `bundleUrl`, `bundleSha256`, `ledger`, `blindSpots`; failed `stage`, `message` and conditional Salesforce fields. Poll identical arguments to complete/failed or T-7 (60 polls or 30 minutes); wait returned hint or 30 seconds when absent. |
| `run_code_search` | Selected class bare name as trimmed `query` of 2 to 512 characters, plus qualified name when different; `partsFrom` from response. Omit `delivery`, `format`, row skip and limit. | Indexing `status: "running"` and hint precede built-search native parts. Match rows: `nodeId`, `name`, `type`, `referencesFound`. Complete only after every part and failure accounted for; unavailable, unreadable or failed evidence leaves that class incomplete. |
| `describe_metadata_schema` | Same IDs and `metadataList` as criteria, at most 50 type strings of at most 100 characters. `refModelId` remains required. | `columns[].value`, `filterable`, `allowedOperators`, display metadata. Use runtime active/status columns; do not substitute metadata change-tracking status. |
| `list_metadata_by_criteria` | `metadataList: ["Apex Trigger"]` or `["Flow"]`, `mode: "page"`; schema-derived `filters` and `columns` when needed; `partsFrom` from response. Omit `delivery`, skip and limit; default NDJSON or `format: "ndjson"` or `"csv"`. | Native parts with row `nodeId`, `sf.apiName` when nested there, and selected runtime status. Apply native termination below. Display-only columns stay separate from scalar filters, including scalar `parent_object`. |
| `get_dependencies` | Exactly one `nodeId` or `nodeIds` (1 to 50 24-hex IDs); `lookingFor: "where_used"` or `"using"`; optional `sfType: "Flow"` or related type. `mode: "manifest"` for counts, omit mode for rows (default page). Omit row skip, limit and delivery; default NDJSON or format NDJSON/CSV. | Manifest `nodes[].nodeId`, `.count`, `.byType`, `totalItems`, `failed`; rows `node`, `related`, `direction`. `related.nodeId` is the referrer for where_used. Manifest page planning limit does not cap file rows. Apply native termination below. |
| `get_access` | Class `nodeId` (or `nodeIds`, 1 to 50); optional `type: "profile"` for guest liveness. Default `mode: "page"` writes NDJSON part files for both selectors; optional `format: "ndjson"` or `"csv"`; `partsFrom` from the response. `mode: "manifest"` gives counts; its optional `limit` (1 to 100) changes count metadata only. Omit `delivery`, `skip` and `includeUsers`; omit `limit` and `format: "json"` on row calls. | Rows `{node, holder, access}`; read `holder.type`, `holder.name`, `holder.nodeId`, `holder.assignedUserCount`. Manifest `nodes[].holders`, `.byType`, `totalItems`, `failed`. A class in `failed` (`not_found`, `unsupported_metadata_type`, `no_access_data`, `deadline_exceeded`) has incomplete access evidence, never zero grants. Apply native termination below. |
| `get_component_change_history` | One `nodeId`, `limit: 200`, `delivery: "file"`, returned `skip`; default `historyType: "all"`. A snapshot adds parsed `changeLogId`, `historyType: "audit_log"`, `as: "url"`. | `changeLogs`, entries' `_id`, `_truncated.nextSkip`, `nextSkip`, `hasMore`; continue even on an empty page with cursor. Fetch `auditLog.url` and optional `.bodyUrl` using `.ttlSeconds`, not expiresInSeconds. |
| `get_metadata_component` | One `nodeId` from `edge.parentNodeId`, `detail: "summary"`; component sublists use `page: {list, skip, limit: 1000}`, list is `fields`, `inbound` or `outbound`, plus `delivery: "file"`. | Top-level `nodeId`, `apiName`; save API name or let planner produce manual Setup step. For sublists follow `fields.items`, `relationships.inbound.items`, `.outbound.items` and their individual `nextSkip` until absent. |

Criteria filters use schema-discovered column and operator values, include every filter column in
explicit display columns, and keep `tags`, `optimization_status`, and `parent_manage_package`
display-only. Clean-up cutoffs refresh on reading the view; cached file polls can reuse a completed
result. Criteria/dependency manifests contain counts rather than rows. Their native row calls
refuse skip, limit, and JSON format with `invalid_input`; do not use the change-record migration
as a reason to alter these native contracts.

Candidate disqualification reasons used by cards 01, 02 and 06 are `NO_APEX_TELEMETRY`,
`SYNC_INCOMPLETE`, `INGEST_PENDING`, and `TELEMETRY_NOT_COLLECTED`. The local held-span gate adds
`INSUFFICIENT_TELEMETRY`; unresolved required tools use `MISSING_PRIMITIVE`. These values are local
state or analysis outcomes, not feature refusal codes. Preserve `reason`, `ledger` and `owner`;
`data/blocked-reasons.csv` and the cards own recovery and transitions.

## File branches and identity

The dispatcher can move an entire result or nested arrays to files. Hydrate `file`,
`_truncated.inFile`, `_oversize.movedToFile`, and nested file descriptors at their original paths
before reading `parts`, `failed`, counts or candidate status. Check SHA-256 and returned row/byte
counts, consume inline samples once, and download immediately. Dispatcher files use a separate
returned lifetime from enclosed files or candidate bundles. Eligible paged reads request
`delivery: "file"`; budget-fit inline replies and `fileError` inline fallbacks still page. Trim
or retry a smaller eligible page before advancing. No optional delivery argument belongs on a
native file-only row call, even where its effective schema accepts it.

Native file replies use `status`, `resultId`, `totalRows`, `partsTotal`, `parts`, `failed`,
`batchesDone`, `batchesTotal`, `instruction`, and conditional `nextPartsFrom`/`retryAfterSeconds`;
`computedAt` is complete-only. Parts contain `index`, `url`, `format`, `rows`, `bytes`, `sha256`,
`expiresInSeconds`. Download parts while running, follow actual `nextPartsFrom` as `partsFrom`,
and keep selection arguments fixed. No cursor during running proves completion. Deduplicate by
identity/index/checksum, reset to cursor zero and discard held parts on changed `resultId`, then
require complete status, all unique parts, totalRows reconciliation and resolved failure accounting.
A complete zero-row result can have zero parts. Join CSV with one header. Always read each returned
`expiresInSeconds`, download at once, and repeat the identical call for a fresh link. Shared capacity
is three writes per reference model and ten cluster-wide.

Candidate bundles use `computedAt` and `bundleSha256`, with `jobStartedAt` evidence while running.
The Coordinated Universal Time (UTC) calendar day participates in candidate job identity; a changed
start identity starts a fresh attempt within the overall T-7 polling cap. Never combine bundles or summaries from
different completion identities. Download the bundle immediately and verify bundleSha256; it has
no public lifetime field. On fetch failure repeat the same request for a fresh link, verify its
returned identity, and pause if the refreshed fetch also fails. Telemetry ledger and local catalog
checks determine which card outcome applies. All local counts come from parsed verified files and
returned summaries, not from missing inline samples.

## Surface inventory

| Surface | Contract responsibility |
|---|---|
| `SKILL.md` | Dispatch and evidence ownership; links orchestration and local data contracts. |
| `README.md` | Tool list, C1/C5/C9/C10/C11 prerequisites, bundle download and optional delivery guidance. |
| `steps/01-check-prerequisites.md` | Context/model discovery, probe, candidate sync check, flags versus telemetry. |
| `steps/02-obtain-candidates.md` | Candidate arguments, job states, bundle/hash, summary and telemetry branches. |
| `steps/03-reason-candidates.md` | Selected-class searches, names, parts and incomplete evidence. |
| `steps/04-review-list.md` | History, snapshots, dependency manifest then files. |
| `steps/05-plan-removal.md` | Component API-name lookup from parsed referrer nodes. |
| `steps/06-blocked-recovery.md` | Probe and candidate recovery; preserves domain block owners. |
| `data/root-kinds.csv` | Trigger/Flow criteria, dependency direction, access and guest-profile liveness. |
| `data/capabilities.csv`, `data/thresholds.csv`, `data/blocked-reasons.csv`, `data/looks-dead-but-is-not.csv` | Capability declarations, T-7/T-9/T-11/T-12/T-13, domain blocks and access-root interpretation. |
| `references/orchestration.md` | Response hydration, dictionary use, delivery/paging, native parts and identity. |
| `references/data-contracts.md`, `references/method-notes.md` | Saved envelope, bundle file shapes, telemetry and local plan inputs; targeted code-search method. |
| `scripts/apex_common.py` | Local complete-qualified envelope guard; error-first refusal validation. |
| Agents, card 00, templates and remaining data | Local reasoning, planning, review and state only; no extra tool calls. |
| Developer tests | Stay in the source repository and do not ship. |

Native input, result and lifetime contracts, including single-node `get_access` part files, remain authoritative.
Missing candidate Salesforce failure fields and stronger content-change detection from equal file
result IDs have no guaranteed interpretation: use returned identities and fields, retain uncertainty,
and request the missing evidence if it prevents completion.
