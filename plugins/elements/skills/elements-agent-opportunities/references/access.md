# Access requirements and refusals

Model Context Protocol (MCP) calls use Open Authorization (OAuth) scopes. Space context and
reference-model listing use `mcp:spaces:read`; metadata tools use `mcp:metadata:read`.
The ordinary reads in this workflow require reference-model view access:
`scan_agentic_opportunities`, `get_component_usage`, `get_dependencies`,
`describe_metadata_schema`, `list_metadata_by_criteria`, and `understand_org_health` areas
`field_population` and `object_dependencies`. View-only access suffices; field population uses
these ordinary requirements. Schema discovery applies reference-model view access when `refModelId`
is supplied. `list_reference_models` and `get_space_context` use the authorized Space.
Listing, scanning and usage also enforce unsuspended-space guards.
Context returns `active` and paged `authorized` spaces; `isSet` marks explicit session selection.
Reference-model listing returns `activeSpace{teamId,name}` and `referenceModels`; select the intended
entry's `refModelId`. Reference model and component `nodeId` identifiers have 24 hexadecimal characters.

`explain_metadata_components` requires metadata read scope and reference-model view access.
| Missing requirement | Exact message | Flag where relevant |
|---|---|---|
| MCP | `Elements MCP is not enabled for this space` | `licenseFlags.mcpServer` |
| `plan.proPlus` | `Requires a Pro Plus space` | The Space needs a Core or Advanced Metadata Management plan. |
| `licenseFlags.orgAIAnalysis` | `Requires Org AI Analysis add-on` | The Space needs Automation & Execution Intelligence on Core Metadata Management; Advanced includes it. |
| `elementsGPTEnabled` | `Requires Elements AI to be enabled for this space` | Contact the Elements representative, who can match the message to the plan. |
| Missing or invisible reference model | `Org model not found or you don't have access to it.` | `not_found` error |

Feature refusals use `feature_not_enabled`. Preserve and quote returned `error`, `flag`, `message`
and `hint` exactly; mark affected evidence unavailable. A missing MCP flag always carries the hint
because another granted space has MCP enabled, but that space can still lack another flag this
call needs. For any other missing flag, the hint means another granted space has every flag this
call needs. Resolve the intended space with `get_space_context`, then use
`set_active_space` and retry there. Resource authorization still applies to the retry.
Calls share the token's request budget. On `rate_limited` or `at_capacity`, stop issuing calls,
wait the returned `retryAfter` or other
retry instruction, retry the failed call, and continue sequentially. Each retry remains subject to refusal.
