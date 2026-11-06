# Errors and recovery

Parse `isError:true` text as unframed JavaScript Object Notation (JSON). Read `error`, then optional `message`, `flag` and `hint`.
`missing_required_scope` supplies `requiredScope`; `missing_required_inputs` supplies `missingInputs,inputDescriptions`. Either can omit `message`.
Correct `invalid_input` using `details[].{field,issue}`. Distinguish missing tools, transport errors, outer refusals and successfully framed failed jobs when reporting coverage.

| Condition | Action |
|---|---|
| `feature_not_enabled` | Explain returned flag and message separately from resource permission |
| `licenseFlags.mcpServer` | Quote `Elements MCP is not enabled for this space` |
| `plan.proPlus` | Quote `Requires a Pro Plus space`; it means the Space needs a Core or Advanced Metadata Management plan |
| `licenseFlags.analyticsCloud` | Quote the returned server message verbatim and suggest the user contact their Elements representative |
| `not_found` for a reference model | Report hidden or missing reference model; server message is `Org model not found or you don't have access to it.` |
| `active_space_required` | Discover authorized spaces and resolve the intended selection before retrying |
| `wrong_active_space` | Pass the reference model's authorized `teamId`, or reauthorize with that space selected |
| `unauthorized_space` | Use returned discovery guidance to select an authorized space |
| `rate_limited,server_busy,too_many_concurrent_requests,at_capacity` | Wait returned `retryAfter` seconds when supplied, then retry the same arguments |
| Native `status:"failed"` | Stop polling this attempt; quote nested `error,message` and follow `instruction` and conditional `retryAfterSeconds` for a later retry |
| `read_timeout,result_too_large` | Narrow the selection and retry in an isolated acquisition directory |

When a feature-refusal hint says to switch spaces, call `get_space_context`, resolve the user's intended authorized space, call `set_active_space`, then retry there. The hint grants no reference model permission.
For file publication failures, follow the delivery rule in the entrypoint and returned guidance. Preserve unresolved failures as incomplete evidence.

Bound running acquisition to 20 producer polls per attempt as a local interaction budget, so a long-running job returns a useful partial report instead of holding the conversation indefinitely. This budget limits the attempt, not the server job; retain the latest identity, capture, arguments and cursor so a later attempt can continue after its returned delay.
