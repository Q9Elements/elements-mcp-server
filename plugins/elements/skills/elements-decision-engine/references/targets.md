# Resolve targets

Use parsed `nodes[].nodeId`, `apiName`, and `path` to verify the target and its parent object.
Metadata discovery and component reads use `mcp:metadata:read`; `search_metadata` and
`get_metadata_component` require reference model view access.

1. Call `search_metadata` with `refModelId`, `teamId`, 1 to 20 `queries`, optional `sfType`
   (up to 64 characters), `limit:200`, and `delivery:"file"`. Allowed `limit` is 1 to 200
   (default 50); `skip` is 0 to 100000 (default 0).
2. Trim each generated query variant and send only terms of 2 to 256 characters. One unusable term
   refuses the whole call with `invalid_input`, naming the indexed field such as `queries.1`, with
   `Search for at least 2 characters.` Ask for a keyword when no usable term remains.
3. Consume inline or file evidence and further pages using [Results](results.md).
   `count` is the page count; `totalItems` is the search total.
4. Read `get_metadata_component({refModelId,teamId,nodeId,delivery:"file"})` when identity or structure
   needs confirmation. A summary carries `nodeId`; `detail:"full"` keeps the raw document's `_id`.
   Summary structure lists contain `items`, `total`, and `nextSkip`. Follow nested cursors with
   `page:{list,skip}`, using `list:"fields"`, `"outbound"`, or `"inbound"`.
   An empty structure page can still carry a continuation cursor.
