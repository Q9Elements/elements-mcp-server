# Change-record acquisition

## Selection and row contract

Pin space, reference model, explicit dates, filters, mode, sort, detail and format for one acquisition. Omit `delivery`, `limit` and `skip` on every `list_metadata_changes` call; manifests also omit `partsFrom`.

| Filter | Accepted values and effect |
|---|---|
| `metadataTypes` | 1 to 50 trimmed names, each 1 to 80 characters; use returned type names |
| `status` | 1 to 3 entries from `new,updated,deleted`; omission includes `proposed`, planned Elements components whose author is the Elements user |
| `changedBy` | 1 to 20 trimmed recorded names, each 1 to 121 characters without control characters; exact case-insensitive match |
| `excludeSystemChanges:true` | Removes Automated Process and Salesforce, Inc.; retains unknown authors |
| `parentObject` | Object application programming interface (API) name matching `[A-Za-z0-9_]{1,120}`; selects children, excluding the object's own changes and top-level Custom Label/External Service |
| `nodeIds` | 1 to 50 component identifiers, deduplicated |

Apply requested filters identically to manifest and records. Manifest fields are `totalItems`, `window`, `byStatus[].{status,count}`, `byType[].{type,count}`, `byChangedBy[].{changedBy,count}` and `unknownChangedBy`.
For records use `mode:"page",sortBy:"changed_date",detail:"summary",format:"ndjson"`. Newline-delimited JavaScript Object Notation (NDJSON) files hold rows directly, newest first. `sortBy:"component"` orders by type, API name, then newest first.
Rows contain `changeLogId,nodeId,apiName,label,type,parentObjectApiName,status,changedBy,changedDate,summary`; `detail:"full"` adds `description`. Current text can be null; summary and description are capped at 2,000 characters plus a truncation marker.

## Native part loop

The envelope contains `refModelId,window,totalItems,status,resultId,totalRows,partsTotal,parts,failed,batchesDone,batchesTotal,_untrusted,instruction`.
Running adds `retryAfterSeconds`; complete adds `computedAt`. Each part has `index,url,format,rows,bytes,sha256,expiresInSeconds`.
Batches read 1,000 records and produce one or more parts. While running, `totalRows` and `partsTotal` count written output so far; they become final at complete. Completed results can be reused for 1,800 seconds, independently of signed-link validity.

1. Save one parsed, hydrated reply to disk or pipe it into the acquisition script using `-` as its reply argument. The script appends it to `changes-capture.json` in arrival order.
2. Acquire every exposed part, including running replies. Verify unchanged bytes using Secure Hash Algorithm 256-bit (SHA-256), byte length and parsed object-row count. Files are `changes-{resultId}-part-{index}.ndjson`.
3. Use actual `nextPartsFrom` as the next call's `partsFrom`. While running, wait `retryAfterSeconds`; absent cursor means wait for more written parts and repeat the current request. `resultId` stays local, while `partsFrom` advances descriptor enumeration.
4. On changed identity, discard held parts/descriptors and restart at `partsFrom:0`. Changed `computedAt` or overlapping format, checksum, byte or row counts reset the held capture and parts. Refreshes may change links while retaining identical content; reuse verified bytes once. Confirm running parts against completed descriptors before success; exit 3 requests the first unconfirmed `partsFrom` index. Reused completed descriptors must match the final `computedAt`; without it, the current reply must describe every part. Missing indices or non-advancing cursors require reconciliation.
5. Account for `failed` and conditional `failedTotal,failedFile`. Download and verify a full failure file when present; a preview can omit entries. If publication fails, repeat the call for recovery and retain the unresolved total. `deadline_exceeded` entries are retryable; `rowsWritten` requires removing that component's partial rows before rereading it. Keep those retries separate until failures and duplicates reconcile.
6. At `complete`, finish descriptor enumeration. Require all indices from zero through `partsTotal - 1`, no unresolved failures, and parsed rows equal to final `totalRows`, `totalItems` and manifest total. Empty complete results are valid. A failed job ends this attempt; retain its evidence and follow the errors reference linked from setup.

## Script actions and isolation

The downloader accepts a saved reply and cache directory. `--capture-dir "$CACHE/candidates/Profile"` puts a narrowed acquisition's capture, parts and master in that directory. Use one acquisition per directory and one writer at a time. Keep the main corpus intact when narrowing by type or node.

| Exit | Next action |
|---|---|
| 0 | Run the printed merger command, replacing `--expected` with the manifest total; merger success publishes `changes-master.ndjson` |
| 3 | Call the producer with the printed cursor/delay and pinned selection; save and process the next reply |
| 2 | Repeat the same call and descriptor cursor for fresh links, then retry the download |
| 1 | Correct invalid capture data, reconcile failures or reacquire inconsistent bytes, then retry; report remaining evidence as partial |

The merger verifies the final identity's accumulated descriptors, local files and counts before replacing the master. It preserves existing output on failure, repairs final newlines only after byte verification, rejects parsing errors and `$$__tp__` leakage, and reports key statistics. Require distinct non-null `changeLogId` values to equal the record count; repeated `nodeId` values represent separate events.
