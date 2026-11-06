# Exhaustive object corpus

Use this procedure when the user requests every object, with one directory per area and acquisition attempt under the skill's cache root. Work on hydrated `items`, applying the file-delivery and continuation rules linked in workflow step 3.

1. Request each ranked area with `understand_org_health({refModelId,teamId,area,skip:0,limit:200,delivery:"file"})`.
2. Save each acquired page as `page-00.ndjson`, `page-01.ndjson`, and so on: newline-delimited JavaScript Object Notation (JSON), abbreviated NDJSON, with one item object per line. Retain `key`, `label`, `total`, `detail`, and `breakdown`.
3. Follow continuation until the stopping condition, then compare acquired rows with `pagination.totalItems`. A failed or stalled continuation means incomplete coverage.
4. Run the bundled merger separately for each area, substituting paths and the returned total:

```sh
python3 {skill-dir}/scripts/merge_ndjson.py .elements/{spaceId}/{refModelId}/{area} \
  .elements/{spaceId}/{refModelId}/{area}/master.ndjson --expected {pagination.totalItems} --key key
```

The merger accepts a directory of `*page*.ndjson`/`*part*.ndjson` files or an explicit glob, excludes its output, and orders by the final numeric filename index. It joins trailing newlines, requires JSON objects, verifies the expected count, rejects `$$__tp__` leakage, checks the supplied key is non-null, and reports duplicates. Keep areas and attempts separate so counts describe one acquisition.
Exit 0 means local checks pass; reconcile duplicate keys and acquisition gaps before claiming exhaustive coverage. Exit 1 means repair or reacquire inputs/output and re-run. Exit 2 means run `--help` and correct arguments. Fix and re-run until it passes.

If the runtime cannot execute scripts, manually join pages in numeric order with row boundaries intact; validate every row as a JSON object, compare the count with the returned total, check required keys and `$$__tp__` leakage, and reconcile duplicates. Report any checks the runtime cannot complete.
Aggregate only the needed counts and rankings from `master.ndjson` with Python 3; surface the aggregate rather than loading the corpus into conversation context.
