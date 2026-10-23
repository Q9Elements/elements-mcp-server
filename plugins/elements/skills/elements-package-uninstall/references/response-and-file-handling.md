# Response and file handling

Parse JavaScript Object Notation (JSON) between `[TOOL DATA START]` and `[TOOL DATA END]` in the Model Context Protocol (MCP) text response. Outer `isError:true` refusals carry unframed JSON. Inspect `error` before optional `message,flag,hint`; `missing_required_scope` and `missing_required_inputs` carry no `message`. Preserve returned `details,allowedValues,capsApplied,retryAfter,requiredScope,missingInputs,inputDescriptions`. Quote refusals and report unavailable evidence; access-specific next actions live in [access and refusals](access-and-refusals.md).

## Delivery and hydration

Request `delivery:"file"` on discovery, package plan/pages, schema and full component reads. Within the 30,000-character ordinary budget, the reply stays inline. Before treating a field as absent, hydrate root `file`, `_truncated.inFile`, `_oversize.movedToFile` and nested `{file:...}` replacements, recursively. A wholly moved page can omit its inline array. `_oversize.refusedInline:true` means unavailable inline evidence, not zero rows.

Download files immediately, using each descriptor's returned `expiresInSeconds`; verify supplied `bytes` and `sha256` (Secure Hash Algorithm 256-bit, SHA-256). After expiry or failed fetch, repeat the same tool call for fresh links. On `fileError`, consume usable files and inline evidence, follow supported continuation and report the remaining gap. A page file covers only that page.

For package/discovery row pages, prefer `_truncated.nextSkip`; otherwise advance `skip` by actual rows consumed. `_truncated.pageItems` describes the pre-trim page; `_truncated.totalItems` describes the query total. Nested moved arrays retain their continuation context. If `hasMore` is true but no usable cursor or consumed row permits progress, report incomplete evidence. Finish only after every page is consumed and `hasMore:false`.

## Native file jobs and validator

Omit `delivery` on `get_dependencies`, `list_metadata_by_criteria`, `run_code_search` and `get_access`. Row calls use `partsFrom`, with row offsets and `limit` omitted; manifest calls omit `partsFrom`. Keep space, reference model, selectors, filters, direction, query and format identical while polling, changing only the returned descriptor cursor. Run calls sequentially to avoid `at_capacity`. Native `resultId` is a 64-character hexadecimal SHA-256 file-result key; poll by repeating the producing tool call. Part descriptors contain `index,url,format,rows,bytes,sha256,expiresInSeconds`.

Save each reply as JSON, either the MCP content envelope or its parsed payload. Hydrate dispatcher files first; the validator accepts native job replies, not arbitrary page files. From the skill directory run:

```sh
python3 scripts/fetch_parts.py response.json --output evidence/selection
```

Use one output directory per selection, including format. The executable [fetch_parts.py](../scripts/fetch_parts.py) uses only the Python 3 standard library. It downloads native parts in index order, verifies byte counts, checksums and row counts, and records `(resultId,index)` with each part's reply provenance in `state.json`. Parts acquired while running require confirmation against completed descriptors (format, bytes, checksum and rows). Retained parts must share the completed `computedAt`; without it, only descriptors in the current completed reply establish coherence. Exit 3 requests the first missing or unconfirmed index. It validates retained files again, skips verified duplicates, and resets parts when `resultId` changes. Changed completion identity or known part checksums clear acquisition and require a fresh call from `partsFrom:0`. Preserve coherent attempts when refreshing links; if exposed metadata cannot establish coherence, report incomplete coverage. A stable `resultId` alone is insufficient proof of unchanged bytes.

| Exit | Meaning and next action |
|---|---|
| 0 | Acquisition complete and verified; read `failures.json` and report unresolved failures before analysis |
| 1 | Invalid input, failed job or verification mismatch; fix the reported input or use a fresh output directory and reacquire from part 0, then run again |
| 2 | Download failed; repeat the identical tool call for fresh links, save its reply and run again |
| 3 | More evidence required; follow the printed `partsFrom`, wait or failure-file instruction, save the next reply and run again |

Fix and re-run until acquisition exits 0. A zero exit establishes verified acquisition, not failure-free org coverage. The script prints and saves `failed`, checks `failedTotal` and downloads/verifies any `failedFile`. Reading its failure report is part of the validation.

## Completion and failures

1. Download every exposed part immediately, including during `status:"running"`. Follow actual `nextPartsFrom` as `partsFrom`; wait `retryAfterSeconds` while running. An absent cursor while running means wait for more parts. Running `partsTotal,totalRows` describe completed batches only.
2. Require `status:"complete"`, every descriptor segment acquired and the sum of verified row counts equal to `totalRows`. `parts:[]` can mean an at/past-tail cursor: follow `instruction`, lower the cursor for missing earlier parts, or poll unfinished work. Empty parts alone do not establish zero rows.
3. Inspect `failed,failedTotal,failedFile` even at completion. A missing failure file with truncated inline failures requires repeating the call; unresolved missing failures mean incomplete coverage. Retry only as instructed. Before merging a retry, remove a failed node's partial rows when its entry has `rowsWritten`; preserve legitimate multiple edges per node.
4. `status:"failed"` ends that attempt. Report nested `error,message,instruction`, and use a conditional `retryAfterSeconds` only for an instructed later retry. Outer refusals such as `at_capacity,server_busy,rate_limited,too_many_concurrent_requests` instead use `retryAfter`; wait its returned value before repeating the same call. With no retry guidance, report the gap.
