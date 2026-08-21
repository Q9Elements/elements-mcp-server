---
name: elements-spaces
description: Manage Elements.cloud spaces; list the spaces the user can access, get or set the active space, and create new consulting or free spaces. Use when the user says "what space am I in", "switch to a different space", "list my spaces", "create a space", or a space must be resolved before other Elements work can start. Space membership and roles are managed in the Elements UI, not here. Do NOT use for exploring org metadata; use elements-metadata instead.
---

# elements-spaces

## Tools

| Tool | Purpose |
|------|---------|
| `list_authorized_spaces` | List all accessible spaces |
| `get_active_space` | Return the current active space |
| `set_active_space` | Switch to a different space |
| `create_space` | Create a new space |

## Resolving the active space

Call `get_active_space` first.

- `isSet: true`: confirmed, proceed
- `isSet: false`, `activeTeamId` non-null: server resolved a default; announce it and proceed
- `activeTeamId` null: call `list_authorized_spaces`, show options, ask user to choose, then call `set_active_space`

If the user asks to switch spaces at any point, call `set_active_space` and announce the change before proceeding.

## Creating a Space

1. If user explicitly requests a **consulting** space, call `create_space` with `name` and `type: "consulting"`. Otherwise call with `name` only.
2. If response contains `clarificationNeeded: true`: user is a multi-space editor. Ask: consulting space or free space? Then call `create_space` again with `type` set to their answer.
3. If response contains `error: 'insufficient_permissions'`: tell the user they need a multi-space editor license to create a consulting space. Ask if they want a free space instead. Do not create anything automatically.
4. On success, announce the new space and relay the returned `nextStep` message: the space becomes usable through this client once an Elements administrator enables the MCP Server license for it and the user re-authorizes.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "What space am I in?" / "switch space" / "list my spaces" | Yes |
| "Create a consulting or free space" | Yes, see Creating a Space |
| "Add users to a space" / manage members or roles | **No**, space membership is managed in the Elements UI |
| "Explore the org's metadata" | No, use `elements-metadata` (after the space is set) |
