# Refusal actions

Apply SKILL.md's returned-layer and exact-message rules. Match `includeUsers` refusals by their returned message and context, since their codes also serve other failures. Those execution refusals supply no policy flag or switch hint themselves.

| Returned code or condition | Next action |
|---|---|
| `feature_not_enabled` or `forbidden` specifically for `includeUsers` | Apply the holder-evidence retry in Requirements. Preserve the returned reason for unavailable user evidence. |
| Other `feature_not_enabled` | Preserve `flag` and any `hint`; apply the hinted space-switch procedure in SKILL.md. A `plan.proPlus` refusal says `Requires a Pro Plus space`; it means the Space needs a Core or Advanced Metadata Management plan. |
| `at_capacity` | Retry identical arguments after returned `retryAfter`. |
| `active_space_required` or `wrong_active_space` | Apply discovery.md's space resolution. |
| Outer `not_found` | Resolve a reference model visible to the caller. |
| `invalid_input` on selectors | Supply one valid selector, following SKILL.md and acquisition.md's limits; inspect returned field details. |
| Other `invalid_input`, `missing_required_inputs` | Correct the indicated arguments and retry; retain absent messages as absent. |
| `missing_required_scope` | Reauthorize with the required scope before retrying. |
| Per-node `not_found` | Resolve that component within the selected reference model and retry it. |
| Per-node `unsupported_metadata_type` | For a permission-holder node, route its grant inventory to elements-metadata. |
| Per-node `no_access_data` | Report the returned unavailable-permission-record reason; apply the interpretation step in SKILL.md. |
| Per-node `deadline_exceeded` with `retryable:true` | Retry that node and apply acquisition.md's partial-row rule. |
| Job `read_timeout` or `result_too_large` | Narrow the call and retry as a separate acquisition. |
| Job `result_file_failed` or `file_output_failed` | Stop that attempt, preserve its nested error and message, and retry the read for a usable result. |

For other scope, space, permission or transport failures, retain the returned code and context and report what prevents the read. Space selection preserves the token's authorization boundary and reference model visibility requirements.
