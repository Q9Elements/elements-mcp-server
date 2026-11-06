# Discovery

## Space and reference model

Use confirmed identifiers for the intended space. When space resolution is needed, `get_space_context` identifies authorized spaces; pass the intended `teamId` to subsequent reads. For `active_space_required`, resolve the intended authorized space before retrying. For `wrong_active_space`, pass the reference model's space identifier or reauthorize with that space selected.
Call `list_reference_models({teamId,delivery:"file"})`, omitting optional `teamId` when the session already resolves the intended space. This read requires `mcp:spaces:read` and an unsuspended space. It is unpaged and lists visible reference models in the selected space. Read `referenceModels[].refModelId` and `activeSpace.teamId` from the parsed reply; entries supply the reference model identifier, and the active-space object supplies the space identifier.

## Find the component

Call `search_metadata({refModelId,queries,sfType?,limit?,skip?,teamId?,delivery:"file"})`. Supply 1 to 20 trimmed query terms, each 2 to 256 characters. Replace or drop unusable terms; if none remains, ask for a keyword. An invalid term refuses the whole request; validation details identify its array position.
`sfType` is an optional string of at most 64 characters. `limit` accepts integers 1 to 200 (default 50); use 200 for a broad search to reduce calls. `skip` accepts integers 0 to 100000 (default 0).
The reply has `nodes` carrying `nodeId,name,apiName,sfType,path`, plus `count,totalItems,skip,hasMore`; `count` is the page length. While `hasMore` is true, increase `skip` by the nodes returned, and retain all pages needed to resolve the intended component. If zero nodes arrive with `hasMore:true`, report stalled discovery rather than repeating the same page indefinitely.
Use `get_metadata_component({refModelId,nodeId,teamId?,delivery:"file"})` to disambiguate a match. It requires metadata read scope and reference model view permission. A parsed match that already identifies the intended component suffices.

## Hydrate discovery and oversized count replies

Request `delivery:"file"` on eligible discovery reads. Replies within the 30,000-character budget stay inline; read them there. For oversized replies, inspect returned files and hydrate root `file`, `_truncated.inFile`, `_oversize.movedToFile`, and nested `{file:{...}}` values before interpreting missing data. A page file covers only that page; continue the tool's pagination separately.
Apply the descriptor expiry and download rules in acquisition.md to all returned files; verify supplied bytes, digest and row counts where present. The native-parts script handles access row envelopes, so hydrate discovery files separately.
On `fileError`, consume every usable file, moved value and inline field. For `list_reference_models`, retry once with `delivery:"file"`; if publication fails again, narrow with `search` and report reference models still missing. For other reads, follow supported continuation and report the remaining gap. Publication failure does not prove that all evidence is inline.
