# Expand a finding

## A blocker's full dependency evidence

Use the blocker's `dependerId` as `nodeId`; request outgoing counts and rows for the same selection:

```js
get_dependencies({refModelId,nodeId:dependerId,lookingFor:"using",mode:"manifest",teamId})
get_dependencies({refModelId,nodeId:dependerId,lookingFor:"using",format:"ndjson",teamId})
```

The manifest returns `failed,nodes:[{nodeId,count,byType:[{type,count}]}],totalItems,pageSize,numPages` plus reference model and direction. `totalItems` counts matching edges; an absent failed node's count is unavailable, not zero. Manifest pagination fields describe counts rather than acquired row pages.

A manifest `invalid_input` with `capsApplied.maxRows:20000` refuses the whole selection above 20,000 edges. Follow its hint to narrow by `sfType` or split a bulk selection, keeping filtered denominators separate. If a single node/type still exceeds the ceiling, report unavailable counts and acquire row evidence. An individual oversized node can appear as `too_many_relationships` in file-job failures while other nodes continue.

Row mode defaults to `page`. Acquire and validate the result through [response and file handling](response-and-file-handling.md), running its downloader before interpretation. Each newline-delimited JavaScript Object Notation (JSON), abbreviated NDJSON, row has `node,direction,related,relationshipDescription,read,write,triggerType,triggerAction`. Carry `node.nodeId` and `related.nodeId` from rows.

Use `related.managedPackage` and `related.apiName` as ownership evidence. Confirm uncertain ownership with a full component read, checking the namespace subtree or managed application programming interface (API) name prefix. Among confirmed target-package rows, compare `componentsReferenced` against distinct `(related.name,related.apiName,related.type)` tuples and `references` against edge rows. Different node identifiers can share a tuple. Manifest edge totals can include dangling edges with no written rows; outgoing rows can include other metadata. Explain each difference and failure rather than forcing the totals to match.

Synthetic example: a blocker has `componentsReferenced:3,references:5` and three sampled tuples. The manifest returns seven outgoing Field edges. A complete failure-free result has five target-package rows with three distinct tuples, plus two outside-package rows. Two target rows share a tuple despite different `related.nodeId` values. Report three package components, five package edges and seven outgoing edges separately.

For incoming edges to the blocker, use `lookingFor:"where_used"` through the same manifest-to-rows route.

## One component or its holders

Read a component with `get_metadata_component({refModelId,nodeId,detail:"full",teamId,delivery:"file"})`. Inspect `nodeDetails.active` when a flag is surprising; hydrate moved content before treating fields as absent.

Read holders with `get_access({refModelId,nodeId,format:"ndjson",teamId})`. Optional `mode:"manifest"` supplies `nodes:[{nodeId,holders,byType}],totalItems,pageSize,numPages,failed` for counts. The row route is a native job; run the shared downloader and follow its continuation output. Holder rows are `{node,holder,access}`; `holder` contains `type,nodeId,name,assignedUserCount`. Each holder's assigned count describes that holder, not a deduplicated roster.

Node failures such as `not_found,unsupported_metadata_type,no_access_data,deadline_exceeded` appear in `failed[]`. A completed job with a failed node does not establish zero grants. A permission holder itself is unsupported as the inspected node; choose the package object or field whose holders are needed. Hand deeper permission analysis to `elements-access`.
