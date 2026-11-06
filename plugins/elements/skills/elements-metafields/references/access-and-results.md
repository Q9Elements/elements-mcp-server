# Access, results, and search continuation

Use this reference on a refusal, oversized response, incomplete schema read, or search page.
The requirements table in [SKILL.md](../SKILL.md#requirements-and-results) owns scopes and roles.
Reference model reads require `refModelId`, including a type-only `describe_metadata_schema` call.

## Refusals and Space selection

Model Context Protocol (MCP) successes contain JavaScript Object Notation (JSON) between
`[TOOL DATA START]` and `[TOOL DATA END]`. Outer refusals have `isError:true` and unframed JSON.
Read the refusal code before quoting any returned message; `missing_required_scope` and
`missing_required_inputs` have no `message`. An accepted job with `status:"failed"` is a separate
failure shape; stop that attempt and report its nested `error`, `message`, and conditional retry hint.

| Condition | Code and returned message or action |
|---|---|
| Missing MCP flag | `feature_not_enabled`: `Elements MCP is not enabled for this space` |
| `plan.proPlus` | `feature_not_enabled`: `Requires a Pro Plus space`; the Space needs a Core or Advanced Metadata Management plan. |
| Definition or dependency write without Space admin | `access_denied`: `Requires space admin rights in this space.` |
| Missing or invisible reference model | `not_found`; quote the returned message unchanged |
| Visible reference model without edit access for values | `access_denied`; quote the returned message unchanged |
| Space unresolved for a multi-space token | `active_space_required`; resolve the intended authorized Space |
| Unauthorized explicit `teamId` | `unauthorized_space`: `The requested teamId is not authorized for this OAuth token.` |

Open Authorization (OAuth) tokens can cover several Spaces. Pass the intended `teamId`, or on
`active_space_required` use [elements-spaces](../../elements-spaces/SKILL.md) to resolve it.
Preserve `error`, `flag`, `message`, and any `hint`. A switch hint can accompany any missing required
flag when another granted Space satisfies all flags for that tool and mode. Follow it only for
the user's intended environment: resolve with `get_space_context`, announce a session change,
then use `set_active_space` and retry. Space selection does not grant resource permission.

## Hydration and ordinary delivery

A reply within the 30,000-character budget stays inline even when file delivery is requested.
For an oversized reply, consume the complete returned file and hydrate moved values. Inspect root
`file`, `_truncated.inFile`, `_oversize.movedToFile`, and nested `{file:{url,...}}` descriptors
before reading status, access flags, totals, or cursors. Restore moved values at their original
paths, including `definitions`, `dependencies`, `nodes`, `columns`, `parts`, and `failed`.

Download immediately, parse each descriptor's `format`, and verify supplied byte and row counts
and Secure Hash Algorithm 256-bit (SHA-256) checksum. Read each returned `expiresInSeconds` for
that link; repeat the same read for fresh links after expiry or failed fetch. Link validity and
file retention are separate. An empty or failed download is unavailable evidence, not a zero-node result.

On `fileError`, consume every usable returned file and moved value as well as inline evidence;
follow supported continuation and report any remaining gap. Publication failure does not establish
that all evidence is inline. A complete file can duplicate an inline sample; consume it once.
`_oversize.refusedInline:true` or any unrecovered moved value leaves coverage incomplete.
A page file covers only that page; it does not replace later tool pages.

For definitions or dependencies still incomplete after hydration, repeat `get_metafields` narrowed
with returned `implementationId` and `metafieldId`. For native criteria parts, use the
[criteria file loop](bulk-writes.md#criteria-file-loop).

## Search limits and paging

Use `search_metadata` for individual judgement cohorts. Pass required `refModelId` and 1–20
`queries`. Trim generated terms and discard or replace variants outside 2–256 characters.
A short term refuses the whole request with `invalid_input` and
`Input does not satisfy the tool schema: queries.<index>: Search for at least 2 characters.`
The detail identifies the failing array position. If no usable term remains, ask for a keyword.

Optional `sfType` is at most 64 characters; `limit` is 1–200 (default 50); integer `skip` is
0–100000 (default 0). Results merge and deduplicate all query variants. Returned `nodes` include
`nodeId`, `name`, `apiName`, `sfType`, and `path`; paging fields are `count`, `totalItems`,
`pageSize`, `numPages`, `skip`, and `hasMore`. `totalItems` counts all matches.

After hydrating each page, follow an actual `_truncated.nextSkip` when returned; otherwise, while
`hasMore` is true, advance `skip` by hydrated `nodes.length`. Keep the query arguments fixed.

## Identifier domains

Carry identifiers from parsed responses: `teamId` selects a Space, `implementationId` selects
the shared MetaField schema, `refModelId` selects a reference model, and `nodeId` selects a node.
Definition and option `id` values select fields and values. Criteria `resultId` identifies a file
result and stays in local acquisition accounting, rather than becoming an input selector.
