# Plan output and evidence fields

The response sketch names fields, not captured org data:

```js
{
  package: {namespace,nodeId,displayName,componentCounts,inventoriedComponents,
            inventoryTruncated?,inventoryCap?},
  summary: {
    externalReferences: {items,references,byType},
    standardPolymorphicLookups: {items,references,note},
    activeAutomations: {items,byType},
    packageInternal: {items,references,note},
    accessGrants: {permissions,grants,byPermissionType,
                  topPermissions:[{type,label,grants,assignedUsers}]},
    outgoingReferences: {references,note}
  },
  plan:[{step,action,description,count?}],nextStep
}
```

`componentCounts` holds Salesforce's per-type package counts. `inventoriedComponents` counts resolved components including subcomponents such as fields, so these denominators differ. The inventory covers both the namespace subtree and managed components grafted onto core objects. Deleted inventory nodes are excluded; missing dependers and dependers marked `deleted` or `proposed` are excluded from blocker rows.

| `action` | Emitted when |
|---|---|
| `deactivate_automations` | Active external automations exist |
| `remediate_external_references` | External references exist |
| `clean_permission_assignments` | Permission holders grant access to package components |
| `resync_and_verify` | Always |
| `uninstall_package` | Always, last |

Automations include Apex Triggers, Flows, Processes, Validation Rules, Workflow Rules, Approval Processes, Assignment Rules, Escalation Rules, Duplicate Rules and Auto-Response Rules. A missing active flag counts as active; `mustDeactivate` identifies the actionable rows.

## Blocker and permission pages

`mode:"blockers"` and `mode:"permissions"` return `totalItems,pageSize,numPages,skip,hasMore` plus their respective array. Page size defaults to 50, accepts 1–200; `skip` accepts 0–100,000.

```js
blockers:[{dependerId,sfType,name,apiName,path,references,componentsReferenced,
           components:[{name,apiName,sfType}],active,mustDeactivate}]
permissions:[{type,label,grants,assignedUsers}]
```

Blockers sort by type then name. `dependerId` is the stable identity; use `path` as a display location when available. Both `path` and `apiName` can be null. `references` counts edges into the package; `componentsReferenced` counts distinct `(name,apiName,sfType)` tuples. `components` samples at most 20 tuples. Expand it through the drill-down reference when needed.

Permission rows sort by grants descending, then label. `type` is the stored holder label; display it as returned. `grants` counts access records for package components. `assignedUsers` is a per-holder count, with `null` meaning unknown; it supplies no named roster or deduplicated total. Plan `topPermissions` contains at most 10 holders. Permissions mode skips the dependency sweep.

Standard polymorphic lookup exclusion applies to a Field whose application programming interface (API) name contains no `__` and whose synced `referenceTo` has multiple targets. These platform fields, such as Task's Related To, are reported separately because target-package objects leave their allowed targets on removal.

The default `format:"json"` returns the row array as JavaScript Object Notation (JSON). `format:"ndjson"` puts newline-delimited JSON (NDJSON) rows in `data`; `format:"csv"` puts comma-separated values (CSV) in `data`. Each CSV page or native CSV part repeats its header; retain one header when joining. Apply shared paging to these formats as well.
