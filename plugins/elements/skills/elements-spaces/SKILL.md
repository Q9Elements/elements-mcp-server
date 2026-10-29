---
name: elements-spaces
description: Manage Elements.cloud spaces; list the spaces the user can access, get or set the active space, and create new consulting or free spaces. Use when the user says "what space am I in", "switch to a different space", "list my spaces", "create a space", or a space must be resolved before other Elements work can start. Do NOT use for managing members or roles (use the Elements user interface) or exploring org metadata (use elements-metadata).
---

# elements-spaces

## Tools

Use the Model Context Protocol (MCP) server for the user's named environment when several connections expose these tools.

| Tool | Purpose | Arguments and response |
|---|---|---|
| `get_space_context` | Return the active space and a page of authorized spaces. | Optional `skip` (integer, 0 to 100000, default 0) and `pageSize` (integer, 1 to 100, default 50). Returns `active` (space object or null), `isSet`, `authorized` (space objects), and `pagination` with `skip`, `pageSize`, `totalItems`, `numPages`, `hasMore`. Each space object has `teamId`, `name`, `role`, `state`, `isDefault`, `isActive`. |
| `set_active_space` | Select an authorized space for the session. | Required `teamId`. Returns `activeTeamId`, `name`, `role`, and `nextStep.description`. |
| `list_reference_models` | List readable reference models in a space. | Optional string `teamId` and string `search` (case-insensitive name filter). Returns `activeSpace.{teamId,name}`, `referenceModels`, `count`, and `nextStep`. Each reference model's `refModelId` identifies it for metadata tools. |
| `create_space` | Create a free or consulting space. | Required `name` (2 to 100 characters); optional `prefix` (2 to 5 characters), `description` (up to 5000 characters), and `type` (`"free"` or `"consulting"`). Returns either `clarificationNeeded` with a question and options, or the created `teamId`, `name`, and `nextStep`. |

## Resolve, list, or switch spaces

1. Call `get_space_context({})`. When `active` is non-null, use `active.teamId` and announce `active.name` as the resolved default if `isSet: false`; `isSet: true` marks an explicit choice.
2. For a space list, null `active`, or a name lookup, fetch every `authorized` page before presenting or selecting spaces. Ask the user to choose when needed; resolve a supplied name against the full list and ask when ambiguous. Carry returned identifiers to avoid selecting the wrong space.
3. For paging, hydrate the full page before counting entries. While `pagination.hasMore` is true, call `get_space_context` with `skip` equal to returned `pagination.skip` plus consumed authorized entries, and `pageSize` equal to returned `pagination.pageSize`.
4. To select or switch, call `set_active_space({teamId})` and announce returned `name`. For a single call in another authorized space, pass its `teamId` to that data tool; switch when changing the session default or when the tool lacks `teamId`.
5. When reference models are needed, call `list_reference_models({teamId, delivery: "file"})`. It is unpaged and lists the space resolved for the call: passed `teamId`, else active space. Ask which reference model to use when several are returned.

Read replies that fit the response budget inline. For `file`, `_truncated.inFile` or `_oversize.movedToFile`, download every returned file immediately using its own `expiresInSeconds`; hydrate whole results and restore moved values at their original paths before interpreting missing data. On `fileError`, combine inline evidence with every usable file and moved value, follow supported continuation, and report unresolved gaps as incomplete. Repeat the same read for fresh links after expiry or failed download.

```text
- [ ] Resolve the intended space and carry its returned identifier.
- [ ] Fetch and hydrate every required page or file.
- [ ] Announce a requested switch; select a reference model when needed.
- [ ] For creation, use the requested type and relay nextStep.
```

### Worked example

Synthetic calls and abbreviated parsed responses in JavaScript Object Notation (JSON); the user chooses Fictional Sandbox:

```json
[
  {"tool":"get_space_context","arguments":{},"response":{"active":null,"isSet":false,"authorized":[{"teamId":"aaaaaaaaaaaaaaaaaaaa0204","name":"Fictional Consulting"},{"teamId":"aaaaaaaaaaaaaaaaaaaa0319","name":"Fictional Sandbox"}],"pagination":{"skip":0,"pageSize":50,"totalItems":2,"numPages":1,"hasMore":false}}},
  {"tool":"set_active_space","arguments":{"teamId":"aaaaaaaaaaaaaaaaaaaa0319"},"response":{"activeTeamId":"aaaaaaaaaaaaaaaaaaaa0319","name":"Fictional Sandbox"}},
  {"tool":"list_reference_models","arguments":{"teamId":"aaaaaaaaaaaaaaaaaaaa0319","delivery":"file"},"response":{"referenceModels":[{"refModelId":"bbbbbbbbbbbbbbbbbbbb8f21","name":"Fictional Org"}],"count":1}}
]
```

## Access, flags, roles, and refusals

| Tool | Open Authorization (OAuth) scope and feature flags | Permission or role |
|---|---|---|
| `get_space_context` | `mcp:spaces:read`; MCP flag on a granted space. | Reads spaces granted to the token. |
| `set_active_space` | `mcp:spaces:read`; MCP flag on the target space. | `teamId` must be an authorized membership. |
| `list_reference_models` | `mcp:spaces:read`. | Reference model view access suffices. |
| `create_space` | `mcp:spaces:create`. | Private cloud requires a verified enterprise domain; consulting requires a multi-space editor license. |

Successful data is JSON between `[TOOL DATA START]` and `[TOOL DATA END]`. Refusals have `isError: true` and unframed JSON: read `error` first, quote `message` when present, and preserve `flag`, `hint` and extra fields. `missing_required_scope` supplies `requiredScope`; `missing_required_inputs` supplies `missingInputs` and `inputDescriptions`; both omit `message`.

- `feature_not_enabled` with `flag: "licenseFlags.mcpServer"` means `Elements MCP is not enabled for this space`.
- `feature_not_enabled` with `flag: "plan.proPlus"` means `Requires a Pro Plus space`.
- When a hint says to switch, call `get_space_context`, resolve the intended authorized space, call `set_active_space` and retry there. Report any further refusal as returned.
- A reference model that is missing or not visible returns `not_found`: `Org model not found or you don't have access to it.`
- `unauthorized_space` says `The requested space is not authorized for this OAuth token.` for `set_active_space`, or `The requested teamId is not authorized for this OAuth token.` for a data-call `teamId`. Both carry `Call get_space_context to see the spaces this token may use.` as `hint`.
- If space resolution is ambiguous, `active_space_required` says `This OAuth token is authorized for multiple Elements spaces. Call get_space_context, choose one, and pass its teamId into the next tool call.`
- Consulting creation without its entitlement returns `access_denied`: `Creating a consulting space requires a multi-space editor license. A free space can be created instead.`

## Create a space

1. Call `create_space` with `name`, any supplied `prefix` or `description`, and `type: "free"` or `type: "consulting"` when the user specifies it. With no requested type, omit `type`: multi-space editors receive clarification; other callers get a free space.
2. On `clarificationNeeded: true`, ask for the type and retry with the answer. After a consulting `access_denied`, ask whether the user wants a free space; retry as free only after their answer.
3. On success, announce returned `name` and `teamId`, then relay `nextStep`: an Elements administrator enables the new space's MCP Server license, then the user reauthorizes this client.

## Scope boundaries

| Question | This skill? |
|---|---|
| "What space am I in?" / "switch space" / "list my spaces" | Yes |
| "Create a consulting or free space" | Yes, see Create a space |
| "Add users to a space" / manage members or roles | No, use the Elements user interface |
| "Explore the org's metadata" | No, use [elements-metadata](../elements-metadata/SKILL.md) after the space is set |
