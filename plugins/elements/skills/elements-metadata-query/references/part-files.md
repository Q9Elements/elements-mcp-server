# Part-file acquisition

1. Page mode returns JavaScript Object Notation (JSON) in newline-delimited form (NDJSON) by default,
   or comma-separated values (CSV) with `format: "csv"`. A native envelope carries `status`,
   `resultId`, `totalRows`, `partsTotal`, `parts`, and `failed`; completion adds `computedAt`.
   Part descriptors carry `index`, `url`, `format`, `rows`, `bytes`, `sha256`, and
   `expiresInSeconds`. Verify `sha256` using Secure Hash Algorithm 256-bit (SHA-256).
2. Keep space, `refModelId`, types or saved-view selector, filters, columns, sort, mode, and
   format fixed. Save each `(resultId, index)` once in index order, preventing duplicate rows.
   Use a dedicated output directory per query. If `resultId`, an observed `computedAt`, or an
   acquired checksum changes, discard earlier acquisition before joining; mixing computations
   produces an unsound result. The script records each part's reply provenance. Confirm running parts
   against completed descriptors (format, bytes, digest and rows) before joining. Retained parts must
   share the completed `computedAt`; without it, only descriptors in the current completed reply
   establish coherence. Exit 3 requests the first missing or unconfirmed index.
3. Pass returned `nextPartsFrom` exactly as `partsFrom` (initial cursor zero). While running,
   wait `retryAfterSeconds` (30 seconds if absent) before the next call. A missing cursor while
   running means wait for more parts, preventing premature completion. Even a cursor beyond the
   available parts returns a successful envelope; follow its instruction or request missing indices.
4. Stop on `status: "failed"`, preserving nested `error`, `message`, and any `retryAfterSeconds`
   for a deliberate later retry. At complete, verify every index through `partsTotal - 1`, each
   descriptor's bytes, digest and rows, then reconcile the row sum with `totalRows`. `totalItems`
   counts matching metadata nodes; running `totalRows` and `partsTotal` cover finished batches.
   Example: `totalItems: 7`, `totalRows: 7`, `partsTotal: 2`, parts of 4 and 3 rows means seven
   matching metadata nodes. Report any discrepancy instead of claiming full coverage.
5. Reconcile inline `failed`, `failedTotal`, and downloaded `failedFile`. If the total exceeds
   inline failures and the file is absent, repeat the read and report incomplete failure details.
   Report accounted failures as partial coverage even when all parts verify. When retrying a
   component with `rowsWritten`, remove its partial rows before merging the reread to avoid
   duplicates.
6. Every CSV part has a header. Join in index order with one header; count parsed records after
   the header, including quoted multiline fields. NDJSON row counts are line counts.

## Run the validator

Check `python3 --version`. Install Python 3 from python.org or the runtime's package manager if
available; the script needs only its standard library. Save each parsed, hydrated native page
as a JSON file. Run the command in workflow step 3 with the newest reply, or supply several
reply files in acquisition order. It caches verified parts and state in the dedicated output
directory and creates `part-INDEX.ndjson` or `part-INDEX.csv`, then `rows.ndjson` or `rows.csv`.
An empty result creates an empty `rows.ndjson`. It also verifies and saves `failed.ndjson` when
provided. Read exit codes and next actions in `python3 scripts/fetch_parts.py --help`.
Only exit 0 establishes complete, verified acquisition; read its failure report before presenting.
Every invocation removes the joined output first, so a failed attempt cannot leave a stale
success. On a nonzero exit, apply the named fix or continuation and rerun with the fresh reply
until it passes.
