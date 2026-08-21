---
name: elements-stories
description: List existing Elements user stories and generate new ones from a process diagram's activities. Use when user says "list stories", "what stories exist for this diagram", "generate stories from this diagram", "create user stories from these activities", or asks to turn a process map into a backlog of stories. Do NOT use to generate the diagram itself (use elements-diagrams or elements-org-to-process first).
---

# elements-stories

## Tools

| Tool | Purpose |
|------|---------|
| `get_active_space` / `set_active_space` / `list_authorized_spaces` | Space management |
| `list_stories` | List existing user stories in the active space (up to 100 per call) |
| `generate_stories_from_diagram` | Bulk-generate AI user stories from selected activities in a diagram |

`list_diagrams` and `get_process_map` (both from the Diagrams skill) are not owned by this skill but
are required steps before generating: `list_diagrams` gives you the diagram's `mapId`, and
`get_process_map` (called with that diagram's `diagramId`) gives you an activity's `mxKey` to select it.

> **`generate_stories_from_diagram` persists the stories it creates directly into Elements — no
> separate save step is needed (see below).**

## Quick start

- **Review existing stories:** `get_active_space` → `list_stories`.
- **Generate from a diagram:** `get_active_space` → `list_diagrams` (Diagrams skill) to find the
  diagram and its `mapId`/`diagramId` → `get_process_map` with that `diagramId` to see the diagram's
  activities and their `mxKey`s → show the user the activity list and let them pick which ones to
  generate from → `generate_stories_from_diagram` with the `mapId` and the chosen `activityMxKeys` →
  `list_stories` to retrieve and show what was created.

## Generating stories from a diagram

`generate_stories_from_diagram` takes `mapId` (required) and optional `activityMxKeys` (if omitted,
every activity in the diagram is used), plus an optional `requirementId` to link the generated
stories to a parent requirement instead of creating them standalone. **Always show the user the
activity list first** (from `get_process_map`) and let them choose which activities to generate
from, rather than defaulting to "all activities" silently — a large diagram can produce a lot of
stories in one call.

One story is generated per activity **resource** (a human or system participant), with human
resources taking priority: if an activity has any human resource, only its human resources generate
stories and its system resources are skipped; only when an activity has no human resource does each
of its system resources generate one. Each story gets a headline, description, and acceptance
criteria.

Activities without both an incoming and an outgoing flowline, or without any resource, are silently
skipped and excluded from the response entirely — the only sign is that `total` comes back lower
than the number of activities you selected. `total`/`completed`/`failed` instead track activities
that qualified: `completed` succeeded, `failed` hit a generation error — check it and tell the user
which stories didn't come through.

This requires a Pro Space, a story-generation license, an Enterprise-active Space, the Requirements
Manager role, and edit access to the diagram. If no authorized Space meets the license and
Requirements Manager role gates, the tool is absent; if the tool is visible, missing edit access to
the diagram returns a clean permission error rather than a partial result.

## Reviewing stories

`list_stories` takes an optional `diagramId`; there's no `search`, `limit`, `skip`, or `format`
parameter — every call returns up to 100 stories, and `total` reports the count across the whole
Space, not scoped to `diagramId`. Passing `diagramId` does not filter which stories come back: it's
only echoed onto each returned story's `diagramId` field (or left `''` if you didn't pass one), not
read from the story's actual diagram link — don't rely on it to scope results or to identify which
diagram a story belongs to. `list_stories` itself requires a Pro Space and a story-generation
license; without either, the tool won't appear in your tool list.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note}`, plus **`nextSkip`** when the tool paginates —
resume the next call from `nextSkip` rather than from your own offset arithmetic, since the backstop
also rewrites `pageSize` and sets `hasMore` to stay consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Space Context

Call `get_active_space` first. If `isSet: false` and `activeTeamId` is null, call
`list_authorized_spaces`, show options, ask user to choose, then call `set_active_space`. If
`activeTeamId` is non-null, announce the default and proceed.
