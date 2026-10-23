# Gathering the inventory: the two routes

Both routes end with the same file, `inventory.json` ([`../schemas/inventory.schema.json`](../schemas/inventory.schema.json)): the objects in scope, how they reference each other, and (route docs, when the vendor groups them) the capabilities they belong to. Everything after the inventory is the same for both routes.

For each native row request in this page, save the complete tool reply to REPLY.json and run `python3 "$PLUGIN/scripts/acquire_result.py" native --input REPLY.json --out "$WORK/metadata/<kind>-<request>.ndjson"`. Repeat for polling and part cursors until exit 0. Pass these joined request files, with their `.acquisition.json` sidecars, to the scripts below. The collector retains status/resultId, final counts, indexed parts, hashes and all failed records; a partial request is an explicit coverage gap. Original downloaded parts are acquisition inputs, while each consumer file holds the complete joined request.

| | Route `docs` | Route `metadata` |
|---|---|---|
| Use when | The system is one Elements does not sync (Microsoft Dynamics 365, HubSpot, ServiceNow), or the person wants the out-of-the-box process of a product, such as a greenfield Manufacturing Cloud or Media Cloud | The person wants the process their own Salesforce org supports, as configured |
| Reads | The vendor's official data model and API documentation | A reference model in the Elements Metadata Dictionary |
| Capabilities | Often given by the vendor (Salesforce's Data Model Gallery has one guide per capability); otherwise inferred | Always inferred: an org mixes standard, customised and custom objects |
| Who reads | The `system-doc-reader` agent, with web search and fetch | This skill, with Elements tools; nothing is fetched from the web |

When it is not clear which route the person means, ask: "Do you want the process the product supports out of the box, read from the vendor's documentation, or the process your org supports, read from its objects in Elements?"

## Route docs

1. **System and variant.** Take them from `scope.json`; kickoff confirmed them with the person before any reading.
2. **Index run.** Send one `system-doc-reader` in `index` mode. It finds the vendor's capability index (a page grouping objects by capability) and object reference (every object with its API name), starting from [`../data/doc-sources.csv`](../data/doc-sources.csv), and writes `docs/index.json`: the capabilities as the vendor names them, with their guide URLs and the objects each lists, every object in the reference with its API name, a how-to link per capability when the vendor has one, and gaps.
3. **Detail runs.** Send `system-doc-reader` agents in `detail` mode in parallel: one per capability, or one per 25 objects when the vendor gives no grouping. Each reads the object reference pages for its objects and writes `docs/detail-<nn>.json` (numbered `01`, `02` and so on): a description per object, its reference fields (lookup and master-detail, with targets), its status, stage or type picklists with their values, and a `lifecycle` for an object whose status or stage picklist carries its workflow. Salesforce reference pages list picklist values alphabetically, so a lifecycle from them has `ordered: false` unless another vendor page (a help article on the default stages, a status diagram) gives the order; the writer of the object's level then works the order out.
4. **Merge,** with the index first: the order of the files decides which capability owns an object two guides list.

```bash
python3 "$SKILL/scripts/inventory.py" merge "$WORK/docs/index.json" "$WORK"/docs/detail-*.json --out "$WORK/inventory.json"
```

The merge marks platform objects and hubs, flags polymorphic fields, and resolves an object a vendor lists under several capabilities: the first capability owns it, the others share it, and hubs (Account, Contact, Product) are shared by all until the grouper gives them an owner. It lists objects that are in no source capability; the grouper places them.

The doc readers record a gap wherever a page does not show an API name, a URL or a relationship.

## Route metadata

1. **Space and reference model.** `get_space_context`, then `list_reference_models`; use the only model or ask which one. Keep `refModelId` (and `teamId` when the token spans several spaces). When more than one connected Elements server offers these tools, use the one for the environment the person names, and ask when they name none.
2. **Scope.** Take the answers kickoff recorded in `scope.json`:
   - **Which objects** (`metadata.objects`): the entire org, or a subset: standard objects only; standard and custom; standard, custom and managed-package objects; or objects the person names (`metadata.named`).
   - **What kind of org** (`metadata.orgType`): `production`, `full-sandbox` or `other-sandbox`. No Elements tool says which (the reference model, the org health summary and the metadata types carry no org type), so the person is asked.
   - **The basis** (`metadata.basis`): `usage`, only objects that hold records are drawn; or `configuration`, every object in scope is drawn. Usage is offered only for production or a full sandbox; any other sandbox runs on configuration (SKILL.md, *Usage or configuration*). Older scope files have `metadata.onlyWithRecords` instead: `true` reads as usage, `false` or null as configuration.
3. **Objects.** `list_metadata_by_criteria` with `metadataList` set by the scope, `columns: ["name","api_name","type","description","record_count","manage_package","last_created_record_date"]`, and the filters below. It answers `status: "running"` until the rows are ready: call again with identical arguments. Then download every part file with `curl` within its `expiresInSeconds` (30 minutes) into `$WORK/metadata/objects-<n>.ndjson`. When a reply lists only some of the parts (`partsTotal` is larger than the parts listed, and it gives `nextPartsFrom`), call again with the same arguments plus `partsFrom` set to `nextPartsFrom`, until every part is downloaded; a missing part means missing objects.

| Scope | `metadataList` | `filters` |
|---|---|---|
| Entire org | `["Standard Object","Custom Object"]` | none |
| Standard only | `["Standard Object"]` | none |
| Standard and custom | `["Standard Object","Custom Object"]` | `{column:"manage_package", operator:"eq", value:false}` |
| Standard, custom and managed | `["Standard Object","Custom Object"]` | none |
| Named objects | `["Standard Object","Custom Object"]` | none; pass the names to `inventory.py --only` |

   Do not filter on `record_count`, on either basis. The filter works (in testing, `record_count > 0` returned the 15 objects that hold records), but an object it leaves out never reaches the inventory, so the map cannot name it as "configured but holding no records", and its count per record type is lost. Which objects hold records is read in step 8 instead. The rows do carry `record_count` now; `inventory.py from-metadata` uses it only for the old `hasRecords` flag.
4. **Relationships.** Collect the `nodeId` of every object row, then call `get_dependencies` with `nodeIds` (up to 1,000 per call; more in further calls), `lookingFor: "where_used"`, `fieldTypes: "relationship"`, `includePopulation: true`. Poll the same way, collect every part with `partsFrom` as above, and download each within its `expiresInSeconds` (1800 seconds in this contract; repeat the same call for fresh links) into `$WORK/metadata/relationships-<n>.ndjson`. Each row is one lookup, master-detail or hierarchy field on `carryingObject` pointing at `node`, with how often it is filled.
5. **Build the inventory** (then steps 6 and 7 for the lifecycles and record types, and step 8 for usage):

```bash
python3 "$SKILL/scripts/inventory.py" from-metadata \
  --objects "$WORK"/metadata/objects-*.ndjson \
  --relationships "$WORK"/metadata/relationships-*.ndjson \
  --basis "$BASIS" \
  --system "Acme production org" --ref-model "$REF_MODEL" \
  --scope-note "Standard and custom objects" \
  --out "$WORK/inventory.json"
```

`$BASIS` is `scope.json` `metadata.basis`. Do not pass `--all-have-records`: it marks every object as holding records without looking, which is how the Opportunity live run came to mark all 24 objects as holding records when every one but User and Price Book holds none (the option stays for old runs, and now warns when a row's `record_count` is 0). When the person named the objects, add `--only` followed by their API names. The script drops relationships from platform objects (activities, files, sharing rows), flags a field that points at more than five object types as polymorphic, and marks an object that eight or more others look up to (its own master-detail children aside) as a hub.

6. **Lifecycles.** The values of each object's status or stage picklist, in the org's order. A field with no active values is recorded as a gap and skipped; the inventory retains the available lifecycles. A value node missing from the saved results requires acquisition before continuing:
   1. `list_metadata_by_criteria` with `metadataList: ["Field"]`, `filters` `{column:"subtype", operator:"eq", value:"Picklist"}` and, on `api_name` (same column, so any of them matches), `eq` `StageName`, `Status`, `Stage`, `State` and `endswith` `Status__c`, `Stage__c`, `State__c`; `columns: ["name","api_name","parent_object","subtype","percent_filled","help_text"]`. Download the parts into `$WORK/metadata/fields-<n>.ndjson`.
   2. `python3 "$SKILL/scripts/inventory.py" lifecycle-candidates --inventory "$WORK/inventory.json" --fields "$WORK"/metadata/fields-*.ndjson --out "$WORK/metadata/lifecycle-fields.json"`. It picks one field per object in scope (StageName, then Status, then a custom status or stage field) and lists the others; with checkpoints, show the person an object with several and pass their pick as `--choose Object.Field`.
   3. `get_metadata_component` with the `nodeIds` it lists (50 at a time) and `detail: "full"`; acquire delivery file replies completely, joining every `_truncated.nextSkip` page by node ID with acquire_result.py generic before saving `$WORK/metadata/lifecycle/fields-<n>.json`. Each field lists its value nodes in `nodes`.
   4. `get_metadata_component` with those value node ids (50 at a time), `detail: "full"`; acquire delivery file replies completely and merge their pages before saving `$WORK/metadata/lifecycle/values-<n>.json`. A value carries its order (`nodeDetails.order`), whether it is active, and in its summary whether it is closed, won or the default.
   5. `python3 "$SKILL/scripts/inventory.py" lifecycle --inventory "$WORK/inventory.json" --fields "$WORK"/metadata/lifecycle/fields-*.json --values "$WORK"/metadata/lifecycle/values-*.json`, with the record type files of step 7 when the scope has any.

   On Lead, Opportunity and Case the values a record type uses are set by its process, not by its picklist values: step 7.4.

7. **Record types** (route metadata only), for the objects with a lifecycle:
   1. `understand_org_health` with selected IDs, area structure and delivery file gives the available objects_by_record_type buckets. For each relevant actual bucket label, call `get_org_health_detail` with chartType objects_by_record_type, the label, selected IDs and delivery file. Hydrate and merge every hasMore or `_truncated.nextSkip` page before saving `$WORK/metadata/record-type-objects-<label>.json`. Unavailable dimensions or failed pages are explicit gaps and cannot justify skipping record-type analysis. Skip the remaining record-type steps only when complete evidence shows none of the lifecycle objects has custom record types.
   2. `list_metadata_by_criteria` with `metadataList: ["Record Type"]` and `{column:"active", operator:"eq", value:true}`; download into `$WORK/metadata/record-types-<n>.ndjson`. `inventory.py` keeps only the record types of the listed objects and leaves out Master (every object has it; it is the absence of record types).
   3. Every object except Lead, Opportunity and Case: `get_dependencies` with the value node ids of those objects' lifecycle fields (from step 6.4), `lookingFor: "where_used"`, `sfType: "Record Type"`; save every row in `$WORK/metadata/value-usage-<n>.ndjson`. Each row pairs a value (`node`) with a record type that uses it (`related`).
   4. Lead, Opportunity and Case: their stage or status values live on the record type's sales, support or lead process, not on the picklist field (a record type also uses the values of its other picklists directly, so step 3 does not answer it). Two calls:
      1. `get_dependencies` with the node ids of those objects' record types (from step 7.2), `lookingFor: "using"`, `sfType: "Process"`; save the rows in `$WORK/metadata/record-type-processes-<n>.ndjson`. Each row pairs a record type (`node`) with the process it uses (`related`): Add_On_Opportunity uses "Opportunity Process". Several record types may share one process.
      2. `get_dependencies` with the node ids of those processes, `lookingFor: "using"`, `sfType: "Custom Value"`; save the rows in `$WORK/metadata/process-values-<n>.ndjson`. The custom values are the process's stage or status values: the same value nodes the field lists, so their order, closed and won flags come from step 6.4.
   5. Run step 6.5 again with `--record-types "$WORK"/metadata/record-types-*.ndjson --record-type-objects "$WORK"/metadata/record-type-objects-*.json`, plus `--value-usage "$WORK"/metadata/value-usage-*.ndjson` (step 3) and `--record-type-processes "$WORK"/metadata/record-type-processes-*.ndjson --process-values "$WORK"/metadata/process-values-*.ndjson` (step 4) for the files there are. Each record type gets the values it uses, in the field's order, and on Lead, Opportunity and Case the name of its process. A record type that uses none is warned about, and its level shows every value; a Lead, Opportunity or Case record type with no process values is warned about, and that object stays an ordinary object on the steps that use it.

   A capability whose main object has record types gets a split level: a root step, then one box per record type linked to the record type in Elements, each drilling down to that record type's lifecycle level. Each record type's level is generated first with `generate_process_map` (`source: "org_object"`, `objectApiName`, `recordTypeDeveloperName`, `lifecycleFieldApiName`; when it answers `clarificationNeeded`, as it may on Lead, Opportunity and Case, pass the field it offers that matches the lifecycle field as `workflowFieldApiName`), polled with `get_process_map` until complete, saved as `$WORK/metadata/process-<record type>.json`, and taken over with `import_org_process.py`; when that fails, a writer writes it from its `lifecycle` brief (SKILL.md, stage 5).

8. **Usage** (basis usage only; skip it on basis configuration). Once steps 6 and 7 have written the lifecycles and record types:
   1. `get_component_usage` with `nodeIds` set to the `nodeId` of every object in `inventory.json`, 50 per call (more in further calls; when a reply is trimmed, call again with `skip` set to `_truncated.nextSkip`). Save each result as it comes back in `$WORK/metadata/usage-<n>.json`. For an object it returns `records.total`, `records.byRecordType` (records per record type label, Master as "*Without Record Type*"), `lastCreated`, `lastModified`, and `velocity` (net change in the record count over 7 and 30 days, from daily snapshots).
   2. `python3 "$SKILL/scripts/inventory.py" usage --inventory "$WORK/inventory.json" --results "$WORK"/metadata/usage-*.json --scope "$WORK/scope.json"`. It writes each object's `usage`, each lifecycle record type's `usage.total` (matched by label, then API name) and the inventory's `basis`, and lists the objects that hold no records. It warns about an object it has no usage for, or whose usage is unavailable: that object counts as used, because missing telemetry is not zero records.
   3. When the person asked for one object's process and that object holds no records, it prints `STOP` and exits 1: tell the person, and offer basis configuration (set `scope.json` `metadata.basis` to `configuration` and rerun step 8.2 with its existing `--scope` argument) or another org.

For a standard Salesforce object, the Data Model Gallery's guides are a reference grouping (Sales Agreement belongs to the Manufacturing guide "Sales Agreements"); the capability grouper may use them as evidence, but the org's own objects and relationships decide.

## Large scopes

An entire org can hold a thousand objects. Nothing changes in the method; the scripts page and the grouper works from `clusters.json` rather than the raw list. When more than ten capabilities result, the grouper adds areas: the top level shows the areas, each area's level shows its capabilities, and each capability drills down to its steps.

On basis usage, step 8 costs one `get_component_usage` call per 50 objects (twenty for a thousand). That is why the object list is not pre-filtered on `record_count` even in a large org: the cost is small, and the objects holding no records are kept so the map can name them. `cluster_objects.py` sets them aside before grouping (`unusedObjects`), so they never make up a capability of their own.

## Scope object

When the person asked for the process of one object (`scope.json` `focus`), read that object and the objects it relates to, and nothing else:

- **Route docs:** the index run is not needed. Send one `system-doc-reader` in `detail` mode for the object and the objects its reference page links to (its master-detail children and the lookups to it the page lists), and write `docs/detail-01.json`; merge it alone.
- **Route metadata:** `get_metadata_component` on the object's `nodeId` lists its relationships both ways (walk `inbound` with `page` until `nextSkip` is absent): the objects it looks up to and those that point at it. Those and the object are the named objects: step 3 for standard and custom objects, step 4 for their `nodeId`s, step 5 with `--only` and their API names, then steps 6, 7 and 8.

`inventory.py focus` then keeps the object, its master-detail children and the objects that look up to it alone; what it looks up to (Account, Contact) is shared.

For lifecycle fields and value nodes, use nodeIds batches of at most 50, detail full and delivery file. Hydrate every reply, merge all `_truncated.nextSkip` batch pages by node ID and record item failures before building lifecycles. Resolve owner API names from sf.fullApiName or canonical identity/parentPath, joining the object inventory by API name; unresolved owners are explicit gaps.

Read the available `objects_by_record_type` buckets from `understand_org_health` area structure. For every relevant actual label, request `get_org_health_detail` with `chartType: "objects_by_record_type"`, that label, selected IDs and `delivery: "file"`. Acquire every hasMore or `_truncated.nextSkip` page and join the items. An unavailable dimension or failed page is a gap and cannot justify skipping record-type analysis. Read each generated diagramId with `get_process_map` and delivery file; poll running only, import the fully hydrated top-level activities/transitions and use the writer fallback for complete/empty.
