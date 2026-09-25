---
name: elements-stories
description: List existing Elements user stories and generate new ones from a process diagram's activities. Use when user says "list stories", "what stories exist for this diagram", "generate stories from this diagram", "create user stories from these activities", or asks to turn a process map into a backlog of stories. Do NOT use to generate the diagram itself (use elements-diagrams or elements-org-to-process first).
---

# elements-stories

## Tools

| Tool | Purpose |
|------|---------|
| `get_active_space` / `set_active_space` / `list_authorized_spaces` | Space management |
| `list_stories` | List existing user stories in a space (20 per page by default, up to 100) |
| `generate_stories_from_diagram` | Bulk-generate AI user stories from selected activities in a diagram |

`list_diagrams` and `get_process_map` (both from the Diagrams skill) are not owned by this skill but
are required steps before generating: `list_diagrams` gives you the diagram's `mapId`, and
`get_process_map` (called with that diagram's `diagramId`) gives you an activity's `mxKey` to select it.

> **`generate_stories_from_diagram` queues generation in the background and returns as soon as the
> work is queued, with the number of stories queued and the `diagramId`. Stories are created in
> Elements as generation completes. Poll `list_stories` with that `diagramId` every 15 to 30
> seconds while `generation.status` is `running` (two stories settled in about 30 seconds), then
> judge the outcome from the counts and the stories themselves (see
> [Judging the outcome](#judging-the-outcome)); `status` alone is advisory.**

## Quick start

- **Review existing stories:** `get_active_space` → `list_stories`.
- **Generate from a diagram:** `get_active_space` → `list_diagrams` (Diagrams skill) to find the
  diagram and its `mapId`/`diagramId` → `get_process_map` with that `diagramId` to see the diagram's
  activities and their `mxKey`s → show the user the activity list and let them pick which ones to
  generate from → `list_stories` with the `diagramId` to record the baseline `totalItems` (page to the end if unavailable) →
  `generate_stories_from_diagram` with the `mapId` and the chosen `activityMxKeys` → poll
  `list_stories` with the returned `diagramId` until generation stops running, judge the outcome, then
  show what was created.

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
skipped and excluded from the queued total entirely. The only sign is that the number queued comes
back lower than the number of activities you selected.

This requires a Pro Space, a story-generation license, the Requirements Manager role, and edit
access to the diagram. If no authorized Space meets the license and
Requirements Manager role gates, the tool is absent; if the tool is visible, missing edit access to
the diagram returns a clean permission error rather than a partial result.

### Judging the outcome

`list_stories` called with the `diagramId` returns the stories linked to that diagram and, while the
job record lasts, a `generation` object:

| Field | Meaning |
|---|---|
| `status` | `running`, `done` or `failed`. Advisory once the job stops: the counts and the stories decide. |
| `total` | stories queued |
| `completed` / `failed` | stories that finished / stories that failed |
| `error` | optional message the job recorded; it can describe a job-level exception raised after every story completed |
| `billingId` | optional identifier of the job's story-generation billing record; quote it only for a billing or support question |
| `updatedAt` | when the job record last changed |

The `generation` key expires some time after the job settles; once it is absent, the `stories` list
is the only record of the run.

Record the baseline story count from `list_stories.totalItems`, or page to `hasMore:false` and count all
rows if `totalItems` is unavailable. On each poll, use the new `totalItems` (or the full paged count) minus
that baseline for the number of new stories; the first page's `stories.length` is only a page count. A poll
before the `generation` object appears is **Pending**: keep polling. Once `generation` appears, use its
counts and the new story count to decide when `status` stops `running`. If the job record later expires,
use the queued total returned by `generate_stories_from_diagram` and the new story count:

- **Delivered:** `completed == total`, `failed == 0`, and the number of new stories matches `completed`.
  Report success, including when `status` reads `failed` or `error` is set; mention that mismatch as
  a server-side status anomaly, never as a generation failure. Observed live: `status: "failed"`,
  `error: "Cannot read properties of undefined (reading 'catch')"`, `completed: 2`, `failed: 0`,
  and both stories created.
- **Partly failed:** `failed` is above 0. Report which selected activities have no new story, and
  pass on `error` when present.
- **Pending:** the job has no `generation` object yet, is still `running`, has fewer new stories than `completed`, or has stopped with `completed + failed < total` and no terminal failure evidence. Keep polling while the job can still settle.
- **Failed:** the job has stopped with a failure and no new stories linked to the diagram. Report the failure with `error` when present.

If a stopped job has `completed + failed < total`, report the unsettled remainder separately; do not
count it as delivered. When terminal failure evidence is present, name those activities as not generated.

## Reviewing stories

`list_stories` takes an optional `diagramId` that filters the result to stories linked to that
diagram, plus `limit` (default 20, maximum 100), `skip`, `format` (`json`, `ndjson` or `csv`) and
`mode: "manifest"` for counts only; there is no `search`. When `diagramId` is present and a story
generation ran recently, the response also carries the `generation` object described in
[Judging the outcome](#judging-the-outcome). `list_stories` itself requires a
Pro Space and a Change Tickets license; without either, the tool will not appear in your tool list.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note, nextSkip}`, with **`nextSkip`** present inside
`_truncated` when the tool paginates. Resume the next call from `_truncated.nextSkip` rather than from
your own offset arithmetic. The outer response
envelope rewrites `pageSize`, `hasMore`, and `numPages` to match what was actually returned; those
fields are not inside `_truncated`. `_truncated.totalItems` is the size of the trimmed list before
trimming, not the envelope's own `totalItems` or `totalObjects`, which represent the whole corpus.
Which list gets trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`,
`deps`, `chains`), falling back to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`**. That is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Space Context

Call `get_active_space` first. If `isSet: false` and `activeTeamId` is null, call
`list_authorized_spaces`, show options, ask user to choose, then call `set_active_space`. If
`activeTeamId` is non-null, announce the default and proceed.

`get_active_space` reports the session's active space and ignores any `teamId` you pass, so it
cannot confirm a different space. To confirm the space a `teamId` points at, read
`activeSpace {teamId, name}` from `list_reference_models` called with that `teamId`, or find the
`teamId` in `list_authorized_spaces`.
