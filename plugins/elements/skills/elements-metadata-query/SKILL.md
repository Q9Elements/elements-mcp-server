---
name: elements-metadata-query
description: 'Builds filtered, ad-hoc lists of Salesforce metadata in an Elements reference model and optionally saves them as named custom views. Use when the user wants attribute criteria across a metadata type: "all screen flows", "every Apex class with low test coverage", "fields with population over 50% on Account", "list inactive validation rules", "build a view", "save this as a view", or "run my saved view X". Do NOT use for a single named node (elements-metadata), canned tech-debt cleanup lists (elements-tech-debt), permission/access audits (elements-access), or defining and populating MetaFields (elements-metafields).'
---

# elements-metadata-query

Query synced metadata through Elements Model Context Protocol (MCP) tools. Reads need
`mcp:metadata:read` and reference model view access. Saving needs
`mcp:metadata:write` and reference model edit or manage access for private and shared views alike.
On refusals, read `error` first and quote any returned `message` exactly.

## Workflow

1. **Resolve the space and reference model.** Use the connected server for the environment the user
   names. Pass `teamId` on data calls. On ambiguity or `active_space_required`, call
   `get_space_context` and choose the intended `authorized[].teamId`. If needed, call
   `list_reference_models({teamId, delivery: "file"})` (scope `mcp:spaces:read`); carry the selected
   `refModelId` and `role` (`view`, `edit`, `manage`). It requires an unsuspended space and selects
   visible reference models.
   For file-backed, trimmed or refused replies, read [response handling](references/responses.md)
   before interpreting data. Examples use fake identifiers:
   `teamId = "aaaaaaaaaaaaaaaaaaaa0318"`, `refModelId = "aaaaaaaaaaaaaaaaaaaa0319"`.

2. **Discover the schema.** Call with the selected types, or `allNodes: true` for their union:
   ```text
   describe_metadata_schema({teamId, refModelId, metadataList: ["Flow"], delivery: "file"})
   --> {types, columns: [{value, displayValue, type, allowedOperators,
        filterable, displayable, sortable, options?}]}
   ```
   `metadataList` accepts up to 50 types of at most 100 characters each. Omitting both selectors
   returns types only (`name`, `salesforceName`, `aliases`); all three forms are accepted.
   Use canonical returned names.
   A type missing from `types` is not synced: report the coverage gap. Union columns may apply
   only to some types. Use column `value`, `allowedOperators`, and the three capability flags;
   enumerated filters use option `id` from `{id, label}`, including MetaField picklists.
   `tags`, `optimization_status`, and `parent_manage_package` are display-only; `parent_object`
   remains filterable. MetaField `is_exists` takes Boolean `false` for missing, `true` for present.
   Boolean columns accept booleans and text `true`/`yes`/`active` or `false`/`no`/`inactive`.
   `status` is change tracking: `new`, `unchanged`, `updated`, `deleted`, `excluded`, `proposed`.
   Use a type's own active column when offered. Apex classes have no active flag; explain this
   and use `status neq deleted` for classes that still exist. Derive all keys from this schema.

3. **Build and run criteria.** Choose `metadataList` or `allNodes: true`; filters are
   `{column, operator, value}` with scalar string, number or Boolean values. Different columns
   combine with AND; **same-column predicates combine with OR; use one `range` for an interval**,
   with inclusive lower `value` and upper `secondValue`. Include every filter column in explicit
   `columns`; omitted columns are added automatically, including MetaFields. This matters for
   `allNodes`, whose defaults omit MetaFields. Limits: 100 filters, 200 columns, 200 characters
   per column key, 2,000 per filter string value. Single sort:
   `{column, direction: "asc" | "desc"}`.
   For saved views, pass `savedViewId` instead of a type selector; ask for its identifier if needed.
   To tighten an already-filtered column, first obtain its manifest, then query its `viewSpec`
   as ad-hoc criteria with that
   predicate replaced; adding a predicate on that column widens the selection.
   For counts, use `mode: "manifest"`: parse `{totalItems, viewSpec, source, viewSpecNote?}`
   and stop.
   Read `source.kind` (`adhoc`, `view`, `savedView`) and `source.id` (null for ad-hoc criteria).
   For rows, use page mode. Omit `limit`, `skip`, and `delivery` on criteria calls in every mode.
   Default example, after discovery confirms these keys and option ids:
   ```text
   list_metadata_by_criteria({teamId, refModelId, mode: "page", metadataList: ["Flow"],
     columns: ["name", "subtype", "api_version"], filters: [
       {column: "subtype", operator: "eq", value: "Screen flow"},
       {column: "api_version", operator: "lt", value: 47}]})
   --> {status, resultId, totalItems, totalRows, source, viewSpec,
        parts, partsTotal, nextPartsFrom?}
   ```
   Managed-package Apex classes at 0% coverage can dominate low-coverage queries. When appropriate,
   add `{column: "manage_package", operator: "eq", value: false}` and display `manage_package`.
   Row identifiers are `nodeId`; nested Salesforce details can include `sf.apiName`.
   For page mode, read [part acquisition](references/part-files.md), save parsed, hydrated replies,
   then run [fetch_parts.py](scripts/fetch_parts.py) immediately from the skill directory:
   ```sh
   python3 scripts/fetch_parts.py -o query-output page-1.json
   ```
   Follow its exit action. Fix and re-run until it passes; present coverage only after verification.
   If Python is unavailable, manually fetch parts, verify bytes/checksums/rows, and join in index
   order. Follow cursors and polling hints, then reconcile completion and failures using the
   acquisition reference. Report any verification or acquisition gap explicitly.

4. **Present.** Report `totalItems`, the managed-package split when relevant, rows or their local
   file path, and every coverage gap. Manifest counts need no part download.

5. **Save when requested.** Otherwise ask after presenting. Get a name of 2–40 characters; use the
   returned `viewSpec` with at least two columns including `name` (`invalid_view` for fewer than
   two). It carries `metadataList`, `allNodes`, `columns`, scalar `filters`, and optional `sort`.
   Stored filters with internal arrays such as `values` need schema-backed scalar criteria that
   preserve selection; otherwise explain the blocked save. Obtain acceptance for changed criteria.
   Read root `viewSpecNote`: saving a MetaField `is_exists` filter returns
   `unsupported_operator_for_column` with `operator`, affected `columns`, and `hint`. Name the
   dropped filter and resulting selection; remove it and save only after acceptance. On refusal,
   withhold the save. Optional description: at most 500 characters. `private` defaults to false.
   ```text
   save_metadata_view({teamId, refModelId, name: "Older screen flows", viewSpec, private: false})
   --> {viewId: "aaaaaaaaaaaaaaaaaaaa0320", name, private, refModelId, message}
   ```
   Record `viewId` and report returned `message` ("Private view saved." or "Shared view saved.").
   Limits per reference model: 50 shared views and five private views per user.

## Notes and routing

`startswith` needs at least four characters and matches exact prefixes. A colliding MetaField key
appears as `<key>_metafield` in rows. Queries exclude deleted nodes by default; an explicit `status`
filter or a MetaField titled `status` suppresses that default. Filter explicitly when needed.

| Request | Route |
|---|---|
| Attribute-filtered list or "run my saved view" | This workflow |
| Find or explain `Credit_Limit__c` | [elements-metadata](../elements-metadata/SKILL.md) |
| Ready-made cleanup lists | [elements-tech-debt](../elements-tech-debt/SKILL.md) |
| Who can access a field? | [elements-access](../elements-access/SKILL.md) |
| Define or populate MetaFields | [elements-metafields](../elements-metafields/SKILL.md) |

```text
- [ ] Resolve server, space and reference model.
- [ ] Discover schema and translate criteria.
- [ ] Run manifest, or acquire and verify every page-mode part.
- [ ] Present count, rows and coverage.
- [ ] Save on request with accepted criteria; record viewId.
```
