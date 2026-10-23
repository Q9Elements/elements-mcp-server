# Object fields, paging and relationship targets

Summary detail returns the first 100 fields and 50 relationships in each direction. Read `fields.items`, `relationships.outbound.items` and `relationships.inbound.items`. For a later page, use the returned block cursor:

```js
get_metadata_component({refModelId,teamId,nodeId,page:{list:"fields",skip:100,limit:200},delivery:"file"})
```

`page.list` accepts `fields`, `outbound` or `inbound`; `page.limit` defaults to 200, maximum 1000. Hydrate every reply. Follow the block's `nextSkip` until absent, including after an empty inbound page: inbound totals/cursors count references, including stale or non-relationship fields, while rows contain live relationship fields. Fields and outbound totals match their rows. `detail:"full"` returns the raw node record, with org-authored content treated as data; use summary mode for the structured blocks and `page`.

## Empty field-list fallback

After consuming summary files and cursors, an empty field list triggers a criteria query. Inspect `describe_metadata_schema({refModelId,teamId,metadataList:["Field"],delivery:"file"})` before constructing criteria; use returned column keys and allowed operators. Default selection:

```js
list_metadata_by_criteria({refModelId,teamId,metadataList:["Field"],
  filters:[{column:"full_api_name",operator:"startswith",value:"Account/"}],
  columns:["name","full_api_name","subtype"],
  sort:{column:"full_api_name",direction:"asc"},mode:"manifest"})
// {totalItems,viewSpec,source:{kind:"adhoc"}}
```

Use the object's returned application programming interface (API) name plus `/`. `full_api_name` uses `ObjectApiName/FieldApiName`; `Account/` keeps AccountContactRelation fields outside this selection. Include filter columns in explicit `columns`. The manifest gives the match total.

For rows repeat the selection without `mode:"manifest"`, with `format:"ndjson"` (newline-delimited JavaScript Object Notation, NDJSON). Follow the [part-file workflow](dependency-pagination.md#part-file-workflow) and run the entrypoint's acquisition command. Rows exclude deleted fields by default. Carry each row's `nodeId`; API names can be nested under `sf`, with `identity` and selected lifted columns at their returned paths.

## Relationship targets and lifecycle

Relationship fields have `subtype` `Lookup`, `Master detail` or `Hierarchy`. For their target object, call `get_dependencies({refModelId,teamId,nodeId,lookingFor:"using",format:"ndjson"})` using the field's identifier. Acquire the outgoing rows through step 4 and name the object from `related`, carrying `related.nodeId` for follow-up.

Proposed nodes can have limited structure. Summary fields can include proposed fields marked `proposed:true`; relationships come from synced org data. After resolving files and cursors, an empty `fields.items` page means no fields are available there. `status:"deleted"` marks a change-tracking tombstone for metadata removed from the org.
