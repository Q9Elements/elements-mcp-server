# Space resolution and refusals

Preserve `error`, `flag`, `message` and any `hint`; use the following action for the returned condition. Model Context Protocol (MCP) policy, space role and reference model permission are separate checks.

| Condition | Action |
|---|---|
| `active_space_required` | Call `get_space_context()` and resolve the user's intended authorized space. Pass its `teamId` on the data call. |
| `unauthorized_space` | Inspect authorized spaces with `get_space_context`; use an authorized `teamId`. |
| `wrong_active_space` | Follow the returned reference model binding instruction and resolve the intended space before retrying. |
| `feature_not_enabled` | Report the returned flag and message. On a switch hint, resolve the intended authorized space with `get_space_context`, call `set_active_space`, retry there and report any new refusal as returned. |
| `not_found` with `Org model not found or you don't have access to it.` | Report missing or invisible reference model access, with coverage unavailable. |
| `missing_required_scope` | Request authorization with the required scope before retrying. |
| `missing_required_inputs` / `invalid_input` | Correct the indicated arguments using `details` and any returned `allowedValues`. |

Missing MCP returns `Elements MCP is not enabled for this space`. Explanation can also return `Requires Org AI Analysis add-on`, which means the Space needs Automation & Execution Intelligence on Core Metadata Management; Advanced includes it. For any other refusal, contact your Elements representative, who can match it to your plan.

For a session-wide switch requested by the user, announce the target and call `set_active_space({teamId})`. On success read `activeTeamId`, `name`, `role` and `nextStep`, then announce the returned space name. An explicit data-call `teamId` selects that call's space; `list_reference_models` reports it in `activeSpace`.

`get_space_context` accepts `skip` and `pageSize`. It returns `active` (space object or null), `isSet`, the current `authorized` page and `pagination` with `hasMore`. `active` describes session context. Omit `delivery`. `pageSize` defaults to 50 and accepts 1 to 100; `skip` accepts 0 to 100000. Hydrate each reply using the entrypoint's reading resource; follow `_truncated.nextSkip` or advance by consumed page length while `pagination.hasMore`, stopping when no continuation remains and `pagination.hasMore:false`.

An Open Authorization (OAuth) transport rejection can precede tool dispatch: Hypertext Transfer Protocol (HTTP) 403 `insufficient_scope`, with description `The user's Enterprise account is suspended or closed.` or `No authorized active Elements spaces are available.` Report that transport error and request restored authorization/access.
