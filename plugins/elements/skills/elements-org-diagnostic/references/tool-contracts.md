# Diagnostic tool contracts

Model Context Protocol (MCP) success text encloses JavaScript Object Notation (JSON) between `[TOOL DATA START]` and `[TOOL DATA END]`. Parse that payload, then resolve file delivery before interpreting it.

## Ownership and identifiers

| Owner | Responsibility |
|---|---|
| Caller | Select space and reference model, preserve returned identifiers and arguments, acquire files and pages, report gaps. |
| Dispatcher | Authorize space and scope, frame replies, apply file delivery and response budgeting. |
| Health tools | Enforce area/chart permissions, compute counts, rows, and pagination. |
| Local merger | Validate acquired row objects and expected counts; report duplicate keys. |

A summary's `detail.nodeId` identifies its drillable object; a drill row's `nodeId` identifies the returned component. A fallback summary `key` with `detail:null` is a display key. Select drill targets from returned detail.

## Authorization and refusal handling

Refusals use `isError:true` and unframed JSON. Read `error`, then optional `message`, `flag`, `hint`, and relevant `reason`/`details`. Preserve exact returned text. `missing_required_scope` carries `requiredScope`; `missing_required_inputs` carries `missingInputs` and `inputDescriptions`; both omit `message`.
When a hint directs a space switch, resolve the user's intended authorized space through `get_space_context`, announce the switch, call `set_active_space`, and retry there. The reference model permission remains a separate check.

| Condition | Code, message, and action |
|---|---|
| MCP flag missing | `feature_not_enabled`, `flag:"licenseFlags.mcpServer"`, `Elements MCP is not enabled for this space`; select a granted eligible space. |
| `plan.proPlus` | `feature_not_enabled`, `flag:"plan.proPlus"`, `Requires a Pro Plus space`; it means the Space needs a Core or Advanced Metadata Management plan. |
| `licenseFlags.analyticsCloud` | Quote the returned message verbatim and suggest the user contact their Elements representative. |
| Ambiguous space | `active_space_required`, `This OAuth token is authorized for multiple Elements spaces. Call get_space_context, choose one, and pass its teamId into the next tool call.` Resolve the returned authorized space. OAuth means Open Authorization. |
| Unauthorized space | `unauthorized_space`, `The requested teamId is not authorized for this OAuth token.` Read authorized spaces. |
| Missing/invisible reference model | `not_found`; confirm the identifier and caller's reference model view access. |

`tools/list` checks flags across granted spaces/modes. A listed tool can refuse the selected space or reference model. For outer `rate_limited`, `server_busy`, or `at_capacity`, wait returned `retryAfter` seconds and retry the same call sequentially. Without a delay, report incomplete evidence. Tools absent from the list also leave evidence unavailable.

## Calls and response fields

| Tool | Contract used here |
|---|---|
| `get_space_context` | `{}` initially. Authorized-space pages use `skip` 0–100000, `pageSize` 1–100 (default 50). Read `active`, `isSet`, `authorized[].{teamId,name,role,state,isDefault,isActive}`, `pagination.{skip,pageSize,totalItems,numPages,hasMore}`. Consume all pages before claiming an exhaustive list, advancing by actual acquired spaces. `isSet` identifies explicit session selection; `active` can be an automatic fallback. |
| `set_active_space` | Required authorized `teamId`; returns `activeTeamId`, `name`, `role`. |
| `list_reference_models` | Optional `teamId` selects an authorized space; omission uses the active/default space. Requires `mcp:spaces:read` and an unsuspended space. Returns `activeSpace.{teamId,name}`, `referenceModels[].{refModelId,name,status,role}`, `count`; the list is unpaged. |
| `understand_org_health` | Only governance accepts `fromDate`/`toDate`. Only ranked object areas accept `skip` 0–100000 and `limit` 1–200 (default 50), returning nested `pagination.{totalItems,pageSize,numPages,skip,hasMore}`. `cacheAge` is seconds since assembly; `dataAsOf` is last sync. |
| `get_org_health_detail` | Required `refModelId`, `chartType`; optional `teamId`, `skip` 0–100000, `limit` 1–200 (default 50), `detail:"summary"|"full"` (default summary). Chart-specific constraints are in the drill recipes. Returns lean `items[].{nodeId,name,apiName,sfType,status}` plus dates; full detail expands node data. Pagination is top-level `{totalItems,pageSize,numPages,skip,hasMore}`. Field rows add numeric `percentFilled`. |

## Object analytics

`field_population` ranks objects by adoption gap: returned `zero + below25` band values. Its `total` sums field-band counts. For example, 12 zero-filled plus 8 below-25-percent fields gives a gap of 20. Bands and object node arguments are in the drill recipes.
`object_dependencies` ranks objects by summed dependency touchpoints. Each breakdown has `{key,value,nodes}`: `value` counts references, `nodes` counts distinct components for that type. Summary counts can exceed drill component counts. Read the returned drill total as its list size.
Default example of a parsed summary item: `{"key":"bbbbbbbbbbbbbbbbbbbb0320","label":"Example__c","total":20,"detail":{"chartType":"field_population","nodeId":"bbbbbbbbbbbbbbbbbbbb0320"},"breakdown":[{"key":"zero","value":12},{"key":"below25","value":8},{"key":"below50","value":0},{"key":"below75","value":0},{"key":"above75","value":0}]}`. Identifiers are fabricated.

## File delivery and row paging

Eligible reads request `delivery:"file"`; responses within the 30,000-character budget stay inline. Space context/switch calls omit `delivery`. For oversized replies, download root `file` and nested `{file:{...}}` values at paths in `_oversize.movedToFile`. `_truncated.inFile:true` identifies page rows in the root file. Whole-result files replace the payload; page files restore `_truncated.field`; moved values restore their original paths. Count a complete acquired page once, replacing its inline preview. `_truncated.totalItems` is the query total; `pageItems` is the pre-trim page size.
Read each descriptor's `expiresInSeconds`, download immediately, and repeat the identical read for fresh links after expiry or failed fetch. Verify supplied checksums, byte counts, and row counts. Failed reacquisition leaves coverage incomplete.
On `fileError` at the root or within `_truncated`/`_oversize`, consume usable files, moved values, and inline evidence; report remaining gaps. If `_oversize.refusedInline:true`, retry once with `delivery:"file"`; if it repeats, narrow the request and report incomplete evidence.
A file covers only its identified page or value. For health rows, use returned `nextSkip` or `_truncated.nextSkip` if present; otherwise advance from returned `skip` by fully acquired rows. Continue while `hasMore:true` and acquired rows are below `totalItems`; stop at `hasMore:false` or the total, then reconcile coverage. With 201 objects and 200 acquired at `skip:0`, continue at `skip:200`. A stalled cursor or missing page leaves coverage incomplete.
