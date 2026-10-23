# Refusals and run recovery

Read root `error` first. `missing_required_scope` supplies `requiredScope` and
`missing_required_inputs` supplies `missingInputs`; either can omit `message`.
Preserve returned details and recovery fields such as `hint` and `allowedValues`.

## Policies and permissions

The first missing flag wins. Model Context Protocol (MCP) is the first check on each path.


| Path | Add-on check | Scope and resource access |
|---|---|---|
| Eight mission tools and `get_analysis_result` |  | `mcp:decisionEngine:read`, unsuspended space, reference model edit access |
| `explain_metadata_components` | Automation & Execution Intelligence | `mcp:metadata:read`, reference model view access |
| `run_data_load_impact` |  | `mcp:metadata:read`, reference model view access, fully synced reference model |

`Requires a Pro Plus space` means the Space needs a Core or Advanced Metadata Management plan. For `Requires Org AI Analysis add-on`, the Space needs Automation & Execution Intelligence on Core Metadata Management; Advanced includes it. For any other refusal, contact the Elements representative, who can match it to the plan.

Feature refusals use `error:"feature_not_enabled"`:

| Flag | Exact message |
|---|---|
| `licenseFlags.mcpServer` | `Elements MCP is not enabled for this space` |
| `licenseFlags.decisionEngine` | `Requires Decision Engine add-on` |
| `licenseFlags.orgAIAnalysis` | `Requires Org AI Analysis add-on` |
| `plan.proPlus` | `Requires a Pro Plus space` |
| `elementsGPTEnabled` | `Requires Elements AI to be enabled for this space` |

A visible reference model with view-only access fails mission calls with `access_denied` and
`Requires edit access to org model <refModelId>.` An inaccessible reference model returns
`not_found` and `Org model not found or you don't have access to it.` Keep permission failures
separate from feature flags. For a mid-sync runtime refusal, report that step 1 uses the last completed
sync and that runtime evidence requires rerunning after sync completion.

## Run recovery

| Error | Next action |
|---|---|
| `run_in_progress` | Use the same mission's poll as directed in SKILL.md. |
| `too_many_runs` | Poll existing missions until a run finishes; each user and space permits five live runs. |
| `server_busy`, `rate_limited` | Wait returned `retryAfter` before resuming sequential calls. |

A refusal is `isError:true`; a failed accepted job uses `status:"failed"` inside a successful response.
Keep protocol or transport failures separate from both. Per-item explanation retries use the timing
and terminal-state rules in [Field-change recipe](field-change.md).
