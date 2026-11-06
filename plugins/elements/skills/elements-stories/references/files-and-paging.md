# Files and paging reference

## Files and paging

Request `delivery: "file"` on eligible paged or potentially trimmed reads; budget-fit replies stay inline. Hydrate root `file`, `_truncated.inFile`, `_oversize.movedToFile` and nested file values before interpreting missing fields, totals or cursors. Download every file from `url` immediately; use `expiresInSeconds`, parse its `format`, and verify `bytes`, `rows` and the Secure Hash Algorithm 256-bit (SHA-256) `sha256` checksum. Repeat the same read for fresh links after expiry or failed fetch.

On `fileError`, consume every usable file, moved value and inline field, follow supported continuation, and report any remaining gap. `_oversize.refusedInline: true` means data is absent inline, not empty. One file may cover only one page.

For the next `skip`, use `_truncated.nextSkip` if present; otherwise advance from the returned `skip` by the number of rows actually read. Continue while `hasMore` is true or a cursor is returned. If more rows are signalled but neither a usable cursor nor rows permit progress, report the sweep incomplete. [find.md](find.md) lists the fields of a row.
