# Tool contracts

Read before discovery, query validation or refusal classification. Model Context Protocol (MCP)
pulls produce JavaScript Object Notation (JSON) payloads for local consumers. File recovery and
snapshot storage follow [Recipe contract, section 1](recipe-contract.md#1-the-snapshot-store).

## Calls and fields consumed

| Tool | Inputs and limits | Output used |
|---|---|---|
| `get_space_context` | `skip:0` initially, integer 0–100000; `pageSize:50`, allowed 1–100; `mcp:spaces:read`; MCP flag | `active,isSet,authorized[],pagination`. Entries include `teamId,name,role,state,isDefault,isActive`. Pagination contains `skip,pageSize,totalItems,numPages,hasMore`. Follow actual `_truncated.nextSkip`, then `nextSkip`, then current skip plus consumed entries; finish at `pagination.hasMore:false`. This Space-management call accepts no `delivery` |
| `list_reference_models` | Chosen `teamId`, `mcp:spaces:read`, unsuspended Space. Unpaged; omit optional `search` for the full list. Request `delivery:"file"` | `activeSpace.{teamId,name},referenceModels[],count,nextStep.description`. Entries: `refModelId,name,status,sourceType,orgId,role,generationEligible,implementation,owner,createdAt,updatedAt`. `implementation` can be null; its name can be null |
| `describe_metadata_schema` | Required `refModelId`, chosen `teamId`; omit selection for accepted types, `allNodes:true` for per-org columns, or `metadataList` (max 50 strings, each max 100 characters). Request `delivery:"file"` | `types:[{name,salesforceName,aliases}]`; with selection, also `columns:[{value,displayValue,type,allowedOperators,filterable,displayable,sortable,options?}]`, options `{id,label}`. `tags,optimization_status,parent_manage_package` are display-only (`filterable:false`); `parent_object` allows discovered scalar filters. Schema results are unpaged |
| `list_metadata_by_criteria` | Required `refModelId`, chosen `teamId`, either `allNodes:true` or `metadataList` (max 50 strings, each max 100 characters). Omit `delivery` in every mode. `mode:"manifest"` counts only; default `mode:"page"` uses native part files. Max 100 filters; max 200 explicit column keys, each max 200 characters; optional single `sort:{column,direction:"asc" or "desc"}` | Manifest: `totalItems,viewSpec,source,viewSpecNote?`. `source:{kind:"adhoc" or "view" or "savedView",id}`; `viewSpec` includes selection, filters, columns and optional sort. Counts are matching metadata nodes. Before rows, read [Row pulls](row-pulls.md) |
| `understand_org_health` | Required 24-character hexadecimal `refModelId`, chosen `teamId`, `area:"structure"` or `"tech_debt"`, `delivery:"file"`. These areas reject `skip,limit,fromDate,toDate` with `invalid_input` | `area,refModelId,items,cacheAge,dataAsOf`. Select items by `key`; fields include `available,reason,total,unit,detail,breakdown`. Breakdown entries are `{key,value}`. `available:false` blanks its dimension; `total:null` denotes non-additive data. `cacheAge` is summary age in seconds. Health results are unpaged |

## Access and failure classification

Criteria and schema reads require `mcp:metadata:read` and reference-model
view access. View-only access passes. An invisible reference model returns `not_found`,
`Org model not found or you don't have access to it.`
Health `structure` and `tech_debt` are included in Core and Advanced.
Discovery lists only reference models visible to the caller. `get_space_context` requires the
scope and flag in the table; reference-model discovery uses its own table row.

| Refusal | Action |
|---|---|
| `feature_not_enabled` | Record its `flag` and message. For `licenseFlags.analyticsCloud`, quote the returned message verbatim and suggest the user contact their Elements representative. Missing MCP: `Elements MCP is not enabled for this space`. Blank only dependent dimensions |
| `not_found` or a permission refusal | Record the visibility or permission reason and blank dependent dimensions |
| `missing_required_scope` | Read `requiredScope`; repair authorization before retrying |
| `missing_required_inputs`, `invalid_input` | Repair from `missingInputs,inputDescriptions` or returned details and discovered schema |
| `invalid_filter_operator` | Read `invalid[].{column,operator,allowed}` and use an advertised operator |
| `MethodNotFound` | Record the unavailable tool and blank dependent dimensions |
| `rate_limited`, `at_capacity`, `server_busy`, `too_many_concurrent_requests` | Wait conditional `retryAfter` seconds; use conservative backoff when absent and resume sequentially |

Successful MCP text blocks frame JSON between `[TOOL DATA START]` and `[TOOL DATA END]`.
Outer refusals have `isError:true` and unframed JSON with root string `error`; inspect it first.
`message` can be absent for missing scope or inputs. Preserve other returned fields, reasons and hints.
Transport and authentication failures require repairing the connection. Successful `status:"failed"`
file-job replies end that attempt; their conditional retry delay is `retryAfterSeconds`.
Running job polling and part reconciliation follow [Row pulls](row-pulls.md).

The per-token rate limit is 60 requests per minute with a 60-second lock when exceeded.
The planner budgets 50 calls per minute to leave room below that limit; other sessions share it.
Native file-writing capacity is 3 jobs per reference model and 10 across the cluster; manifest
counts create no such jobs. Honor returned capacity refusals even during a sequential pull.

## Filters

Discover columns and `allowedOperators` before executing count queries. Public operators are
`eq,neq,gte,gt,lte,lt,contains,doesnotcontain,startswith,endswith,range,is_exists`.
Different columns combine with AND; repeated predicates on one column combine with OR.
`range` uses scalar `value` and `secondValue`. Boolean filters use `true` or `false`.
Include filter columns in an explicit `columns` list so predicates validate.
Use the explicit built-in `status,neq,"deleted"` predicate for live-node denominators.
Resolve a conflicting MetaField named `status` before labelling counts live nodes.
