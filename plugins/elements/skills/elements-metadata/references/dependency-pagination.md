# Dependency caching & pagination

How to cache `get_dependencies` results and paginate truncated groups without flooding the
main context. Referenced from SKILL.md step 4.

## Workspace cache

Skill artifacts live under `.elements/{spaceId}/{refModelId}/` at the **workspace root**;
resolve the root with `git rev-parse --show-toplevel`, falling back to the current directory
only if that fails (`{spaceId}` is the same value as the `teamId` passed to the tools). A wrong
root misses existing caches and causes needless re-fetches.

Dependency results are cached at:

```
.elements/{spaceId}/{refModelId}/deps/{nodeId}-{direction}.json
```

where `direction` is `incoming` or `outgoing`.

**Check the cache before calling the tool.** If the file exists and its `fetchedAt` timestamp
is less than 24 hours old, use the cached data and skip the fetch/paginate/merge steps entirely.
Trust the `fetchedAt` field inside the file, not file mtime; a clone/copy/worktree checkout
resets mtime to "now", making a stale cache look fresh.

## Paginating truncated groups

For each group where `count > deps.length`, assign **one subagent to that group**. The subagent
fetches pages serially so every offset comes from the response immediately before it. Page responses
are large and must not transit the main context. If the client has no subagent facility, fetch the
pages serially in the main agent, write each page straight to its file, and keep only the file paths
in context.

A page can return fewer rows than the `limit` you asked for: the size backstop trims it (e.g.
`limit: 50` returning 25 rows) and records the resume point as `_truncated.nextSkip`, nested inside
`_truncated`, not at the top level. Never compute the next offset as `skip + limit`.

The first page to fetch starts at `deps.length` of the group in the initial grouped response. For
every later page, call `get_dependencies` with the previous page's `_truncated.nextSkip`; when the
page has no `_truncated`, use that page's `skip + deps.length`. Continue until the collected row
count matches the group's `count`.

Give each group subagent this task:

> "For this dependency group, call get_dependencies with refModelId=`<id>`, nodeId=`<id>`,
> lookingFor=`<dir>`, sfType=`<type>`, limit=50, and the supplied starting `skip`. In flat
> single-type mode the tool returns `{deps, sfType, skip, limit}`. Write each **whole response
> object** as JSON to
> `.elements/{spaceId}/{refModelId}/deps/{nodeId}-{direction}-page-{sfType}-{skip}.json`.
> Fetch the next page serially from this response's `_truncated.nextSkip`, or from
> `skip + deps.length` when the response has no `_truncated` (a page can hold fewer rows than
> `limit`). Return the file paths and combined item count."

(Write the whole `{deps, sfType, skip, limit}` object, not the bare array, so the merge below
can read `.deps` off each page file consistently.)

Different truncated groups may run in parallel. Pages within one group remain serial.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note, nextSkip}`, with **`nextSkip`** present inside
`_truncated` when the tool paginates. Resume the next call from `_truncated.nextSkip` rather than from
your own offset arithmetic; the backstop also rewrites `pageSize` and sets `hasMore` to stay
consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Merging page files

Once all subagents complete, merge in the main context:

```
for each truncated group:
  all_deps = initial_deps_from_first_fetch
  for each page file in skip order:
    all_deps += read_json(page_file).deps
    delete page_file
  assert len(all_deps) == count
  group.deps = all_deps
```

## Writing the cache

After merging, write the complete result:

```json
{
  "fetchedAt": "<ISO timestamp>",
  "nodeId": "...",
  "refModelId": "...",
  "direction": "incoming",
  "groups": [
    { "type": "Report", "count": 421, "deps": [ ...all 421 items... ] },
    { "type": "Flow",   "count": 16,  "deps": [ ...16 items... ] }
  ]
}
```

Path: `.elements/{spaceId}/{refModelId}/deps/{nodeId}-{direction}.json`
