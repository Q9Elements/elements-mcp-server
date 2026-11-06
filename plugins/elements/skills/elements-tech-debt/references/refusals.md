# Refusals and recovery

Every tool refusal has `isError:true` and unframed JavaScript Object Notation (JSON). Read `error`, then optional `message`, `flag`, `hint`, `details`, `reason`, `allowedValues`, `capsApplied` and retry guidance. Quote any returned message exactly. `missing_required_scope` supplies `requiredScope`; `missing_required_inputs` supplies `missingInputs` and `inputDescriptions`; both omit `message`.

Open Authorization (OAuth) scopes are `mcp:spaces:read` for discovery/listing and `mcp:metadata:read` for metadata calls. History also checks that the space is non-suspended. Feature refusals describe a missing capability; permissions describe resource access.

| Error / condition | Next action |
|---|---|
| `feature_not_enabled`, `licenseFlags.mcpServer` | Returned message: `Elements MCP is not enabled for this space`. Resolve enablement or report affected evidence unavailable. |
| `feature_not_enabled`, `plan.proPlus` | Returned message: `Requires a Pro Plus space`. It means the Space needs a Core or Advanced Metadata Management plan. |
| `feature_not_enabled`, `licenseFlags.analyticsCloud` | Quote the returned server message verbatim and suggest the user contact their Elements representative. |
| `feature_not_enabled`, `licenseFlags.orgDependencyExplorer` | Returned message: `Requires Dependency Explorer add-on`. Contact the Elements representative, who can match the message to the plan. |
| `not_found` | Resolve the intended identifier and view permission; preserve the returned message. |
| `access_denied` on a new code search | Obtain edit access or report code coverage unknown. |
| `active_space_required` | Call `get_space_context`, resolve the intended authorized space, pass its `teamId`, then retry. |
| `unauthorized_space` | Resolve an authorized space with `get_space_context`; retry only in the intended authorized space. |
| Feature refusal with a space-switch `hint` | Call `get_space_context`, resolve the intended authorized space, call `set_active_space`, then retry. Resource permissions still apply. |
| `missing_required_scope`, `missing_required_inputs` | Obtain `requiredScope` or supply `missingInputs` using `inputDescriptions`, then retry. |
| `unauthorized`, other access/licence refusals | Report the access explanation and unavailable evidence; continue with valid evidence. |
| `invalid_input`, `invalid_filter_column`, `invalid_filter_operator`, `invalid_filter_value`, `parent_object_not_found` | Correct the supported selection from returned details. A manifest ceiling uses step 4's split procedure. |
| `code_search_not_indexed` | Initialize code search in Elements, then retry; code coverage stays unknown. |
| `sync_in_progress` | Wait for sync completion before retrying; code coverage stays unknown. |
| `code_search_indexing_failed` | Run a code-search sync again in Elements, then retry. |
| `rate_limited`, `at_capacity`, `server_busy`, `result_file_busy` | Outer errors use `retryAfter` seconds when present. Follow the returned instruction and retry the same refused call. |
| Running jobs or failed bulk items | Use returned `retryAfterSeconds` when present. Missing guidance leaves an explicit limitation; retain resumable arguments/cursor for pending work. |
| Terminal job/file failures | Preserve `result_file_failed`, `result_file_timeout`, `file_output_failed`, `result_too_large`, `result_stalled`, `read_timeout` or other returned code/message. Stop this attempt; a later retry needs an explicitly retryable condition and returned instruction. Narrow oversized selections. |

Capacity is shared across native file jobs. Use returned refusals and instructions to determine retry behavior. Apply a user-specified polling bound when provided; otherwise continue only while returned instructions support progress. If the runtime cannot continue, report pending work with selection, `resultId`, cursor and retry guidance for resumption.
