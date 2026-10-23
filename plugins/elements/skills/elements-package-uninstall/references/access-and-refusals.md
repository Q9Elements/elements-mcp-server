# Access and actionable refusals

Model Context Protocol (MCP) availability and reference-model permissions are separate requirements. Open Authorization (OAuth) scopes control the token's permitted operations.

| Calls | Requirements |
|---|---|
| Ordinary metadata calls in this workflow, including criteria and schema | `mcp:metadata:read`, reference-model view access |
| `list_reference_models` | `mcp:spaces:read`, unsuspended space; filters to readable reference models |
| `get_space_context`, `set_active_space` | `mcp:spaces:read`, MCP flag |
| `run_code_search` | An indexed org; uncached search adds reference-model edit access, cached results need view access |

The following messages change the next action. Resource messages refer to the Elements reference model.

| Code | Message | Next action |
|---|---|---|
| `feature_not_enabled` | `Elements MCP is not enabled for this space` | Follow a returned switch hint, or report unavailable evidence |
| `feature_not_enabled` | `Requires a Pro Plus space` | It means the Space needs a Core or Advanced Metadata Management plan |
| `feature_not_enabled` | `Requires Dependency Explorer add-on` | For any refusal, contact the Elements representative, who can match it to the plan |
| `not_found` | `Org model not found or you don't have access to it.` | Rediscover a readable reference model in the intended space |
| `access_denied` | `Requires edit access to org model aaaaaaaaaaaaaaaaaaaa0319.` | Obtain edit access for the actual returned reference model identifier, or report uncached search unavailable |
| `active_space_required` | `This OAuth token is authorized for multiple Elements spaces. Call get_space_context, choose one, and pass its teamId into the next tool call.` | Resolve the user's intended space and pass its `teamId` |
| `wrong_active_space` | `This reference model belongs to a different space than the token's active one. Pass that space's teamId (see get_space_context), or re-authorize with it selected. Note: list_reference_models only lists the active space.` | Select the intended authorized space, then rediscover there |

The edit-refusal identifier is a fabricated placeholder; quote the actual returned message. On a space-switch hint, use `get_space_context`, select the authorized intended space with `set_active_space({teamId})`, retry, and report any new refusal as returned. Use `elements-spaces` for space discovery details.

Report licence, sync and access refusals as unavailable evidence. The common refusal envelope and retry fields live in [response and file handling](response-and-file-handling.md).
