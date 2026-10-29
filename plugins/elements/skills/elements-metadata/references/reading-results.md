# Reading results and identifiers

Model Context Protocol (MCP) replies contain text in `content`. Parse successful JavaScript Object Notation (JSON) between `[TOOL DATA START]` and `[TOOL DATA END]`. Outer refusals have `isError:true` and unframed JSON. Read `error` first, then `message`, `flag`, `hint` and `details` when present; `missing_required_scope` and `missing_required_inputs` have no `message`.

## Files and pages

Request `delivery:"file"` for eligible reads that page or can be trimmed. Replies within the 30,000-character budget stay inline. Omit `delivery` on `get_dependencies`, `get_access` and `list_metadata_by_criteria` in every mode; their row streams use native files.

1. Inspect root `file`, `_truncated.inFile`, `_oversize.movedToFile` and nested `{file:{url,...}}` values before interpreting missing data. Whole-page files can omit inline arrays; complete files can duplicate inline samples. Consume the complete value once.
2. Download whole results/pages and moved values, parse their declared format, and restore each value at its original path. This includes `referenceModels`, `nodes`, `fields`, `relationships`, `narrative`, `parts` and `failed`.
3. Use each descriptor's returned `expiresInSeconds`; download immediately. Verify supplied bytes, Secure Hash Algorithm 256-bit (SHA-256) and row counts. Repeat the same read for fresh links after expiry or fetch failure. Inner and outer descriptors each govern their own link.
4. On `fileError`, consume all usable files, moved values and inline evidence, then follow supported continuation and report remaining gaps. `_oversize.refusedInline:true` means unavailable coverage.
5. Continue later tool pages: use `_truncated.nextSkip`, tool `hasMore`/`nextSkip`, and nested block cursors. A file covers only its call's page.

```text
- [ ] Parse success or refusal, reading error first.
- [ ] Hydrate and verify all returned files and moved values.
- [ ] Consume each value once and follow every supported continuation.
- [ ] State remaining coverage gaps.
```

Outer refusals use `retryAfter` in seconds, including `at_capacity`, `server_busy`, `rate_limited` and `too_many_concurrent_requests`. Successful running/failed jobs use `retryAfterSeconds` when present, also in seconds. `status:"failed"` ends that attempt; report its `error`, `message` and recovery instruction, retaining a wait for any permitted later retry. Native file failures carry nested `error` objects; explanation failures carry string `error` values.

## Identifiers

Carry `teamId` for the space, `refModelId` for the reference model and `nodeId` for its node from parsed replies. Reference model and node identifiers have 24 hexadecimal characters; shape alone establishes no membership. A native file `resultId` is a separate 64-character SHA-256 computation identifier. Poll computations by repeating their producer call.
