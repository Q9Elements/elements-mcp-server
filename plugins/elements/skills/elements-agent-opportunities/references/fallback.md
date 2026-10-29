# Fallback when the scan is unavailable

Explain the returned refusal first and use the access requirements for each fallback read.
Call `describe_metadata_schema(refModelId,delivery:"file")` for object type labels, then repeat
with those labels in `metadataList` for column keys and operators. Use `list_metadata_by_criteria`
to query objects with discovered
record-count, last-modified-record and last-created-record columns; reproduce `minRecordCount`
with the discovered record-count filter. Follow the acquisition procedure for every file and page.
Run the merge validator with the completed selection's total and `--key nodeId`.

Read selected heavy-column values from their discovered keys, such as `record_count`, when present.
Cached parts can retain earlier projections; absent selected values remain unavailable. Field rows
retain the nested facts used by the ratio calculator. Then acquire every page of:

```text
understand_org_health(refModelId,area:"field_population",delivery:"file")
understand_org_health(refModelId,area:"object_dependencies",delivery:"file")
```

Both return `items`, `cacheAge`, `dataAsOf` and `pagination{totalItems,pageSize,numPages,skip,hasMore}`.
Join object `nodeId` to item `key` or `detail.nodeId`. Population `breakdown[{key,value}]` holds
field-band counts; dependency breakdown holds touchpoints and `nodes` gives distinct components.
Preserve those units. Apply the scoring rubric to observed signals and label in-skill ranking as
provisional when required factors or recomputes are unavailable. Report velocity and engagement
unavailable on this path, and state its higher call cost. Finish with the same report and digest.
