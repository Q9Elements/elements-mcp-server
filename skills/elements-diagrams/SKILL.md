---
name: elements-diagrams
description: Generate, read, export, edit, and import Elements.cloud process map diagrams. Use when user says "generate a process map", "make a process map from this transcript", "create a map from this description", "read this diagram", "modify a diagram", "edit diagram JSON", "add a step to the diagram", "remove an activity", "rename a swimlane", "change a flowline", "re-import a diagram into Elements", or provides a .zip export from Elements.cloud and asks to make changes.
---

# elements-diagrams

## Tools

| Tool | Purpose |
|------|---------|
| `get_active_space` / `set_active_space` / `list_authorized_spaces` | Space management |
| `upload_process_map_image` | Upload images (base64) for map generation |
| `generate_process_map` | Start async map generation; returns `diagramId` |
| `get_process_map` | Fetch result or poll until `status: "complete"` |
| `list_diagrams` | List diagrams in the active space; each result includes `myRole`, `canEdit`, `canRelease`, `governanceMode` |
| `export_diagram` | Export a diagram as a zip; returns `downloadUrl`, `uploadUrl`, and `s3Key` |
| `import_diagram` | Import a modified zip back (writes the DRAFT) |

`generate_process_map`, `upload_process_map_image`, and `import_diagram` require the Author role and are absent from the tool list only when no authorized Space grants it; reading and listing diagrams need no role. When these tools are visible, every call still re-checks the Author role in the Space it runs against, so a permission error from that role check points to that Space rather than a retryable glitch.

`export_diagram` and `import_diagram` each additionally re-check the caller's access to that specific diagram: `export_diagram` needs `myRole: "manage"` (from `list_diagrams`), `import_diagram` needs `canEdit: true`. Neither call degrades gracefully on denial — both throw a permission error with no partial result. See [references/editing-workflow.md](references/editing-workflow.md) for the full access-check sequence.

> **Releasing is not available over MCP.** Promoting a DRAFT to an approved (READY) version requires password re-confirmation in production, so it stays a human step in the Elements UI. `canRelease` on `list_diagrams` tells you whether the *user* could do it there; when they want a versioned snapshot, direct them to release in Elements.

## Quick start

- **Generate:** `get_active_space` → `generate_process_map` with `name` and `guidance` → poll `get_process_map` every 30s
- **Edit:** `list_diagrams` → `export_diagram` → download ZIP → edit → upload → `import_diagram`
- **Read:** `get_active_space` → `get_process_map` with `diagramId`

## Space Context

Call `get_active_space` first. If `isSet: false` and `activeTeamId` is null, call `list_authorized_spaces`, show options, ask user to choose, then call `set_active_space`. If `activeTeamId` is non-null, announce the default and proceed.

## Workflows

Read the relevant reference before starting:

- **Choose a diagram type** (new diagram, type unclear) → [references/diagram-types.md](references/diagram-types.md)
- **Generate a map** from text, transcript, or images → [references/map-generation.md](references/map-generation.md)
- **Read an existing diagram** by `diagramId` → [references/map-generation.md](references/map-generation.md)
- **Export, edit, validate, and import a diagram zip** → [references/editing-workflow.md](references/editing-workflow.md)

Supporting references (read when needed during editing):
- **Field rules and JSON editing guide** → [references/editing-guide.md](references/editing-guide.md)
- **Full schema reference** → [references/schema.json](references/schema.json)
- **Validator** (`scripts/validate.py`): run after every edit; fix all errors before importing
