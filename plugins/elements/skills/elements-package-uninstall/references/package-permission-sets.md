# Package-owned permission sets

Read when a permission page lists a Permission Set or Permission Set Group. The plan's holder rows identify grants and labels but carry no package-ownership field. Query managed sets to distinguish target-package assignment work from org-owned access cleanup. Assignment findings are evidence for the cleanup plan; test uninstall readiness in the sandbox.

```js
list_metadata_by_criteria({
  refModelId,teamId,mode:"page",format:"ndjson",
  metadataList:["Permission Set","Permission Set Group"],
  filters:[{column:"manage_package",operator:"eq",value:true}],
  columns:["name","manage_package","assigned_users"]
})
```

If a column is unknown or refused, call `describe_metadata_schema({refModelId,metadataList:["Permission Set","Permission Set Group"],teamId,delivery:"file"})`. Read returned column `value` keys, `allowedOperators` and Boolean option identifiers; include every filter column in `columns`, correct the query, and retry. Schema calls with both `metadataList` and `allNodes` omitted return supported `types:[{name,salesforceName,aliases}]`; supported types alone do not establish synced data availability.

The criteria result includes `totalItems,viewSpec,source` and native file-job metadata. `totalItems` counts the selection; `totalRows` counts written rows. Acquire and validate all parts using [response and file handling](response-and-file-handling.md). Rows use newline-delimited JavaScript Object Notation (JSON), abbreviated NDJSON. A fabricated row is:

```json
{"nodeId":"bbbbbbbbbbbbbbbbbbbb0319","parentPath":"Namespace.acme.PermissionSet","name":"Fictional Sales Access","sf":{"apiName":"Sales_Access"},"nodeDetails":{"isManaged":true},"status":"updated","assignedUsers":12}
```

Match `parentPath` beginning with `Namespace.acme.` for target `acme`; carry the row's `nodeId`. The query includes managed sets across the org; use the target `parentPath` subtree to establish ownership. Flag target-package rows with positive `assignedUsers` for assignment cleanup; preserve unknown counts as unknown.
