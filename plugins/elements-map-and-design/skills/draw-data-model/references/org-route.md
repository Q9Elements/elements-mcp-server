# Building a data model from the org

How to turn "draw Account, Contact, Opportunity and Case" into a model file, from what Elements already knows about the org (its Metadata Dictionary). Nothing is read from Salesforce directly and nothing is fetched from the web.

For each native row request in this page, save the complete tool reply to REPLY.json and run `python3 "$PLUGIN/scripts/acquire_result.py" native --input REPLY.json --out "$WORK/metadata/<kind>-<request>.ndjson"`. Repeat for polling and part cursors until exit 0. Pass these joined request files, with their `.acquisition.json` sidecars, to the scripts below. The collector retains status/resultId, final counts, indexed parts, hashes and all failed records; a partial request is an explicit coverage gap. Original downloaded parts are acquisition inputs, while each consumer file holds the complete joined request.

Why files and not answers: an object's full description (`get_metadata_component`) is tens of kilobytes and would have to be copied into a file by hand. The two list tools below write their rows as NDJSON files with download links instead, so `curl` saves them as they are and a script reads them. The run downloads three things and runs one script.

All files go into the run's work folder (`$WORK`, the skill's `DIR`), relationship and field rows under `$WORK/metadata/`. `$PLUGIN` is the plugin folder; `$REF_MODEL` is the `refModelId` from step 1.

## 1. The reference model

`list_reference_models`; use the only one or ask which org. Keep its `refModelId` (and `teamId` when the token spans several spaces).

## 2. The objects

For each object the user names, call `search_metadata` with `refModelId`, a few spelling variants (`"opportunity product"`, `"OpportunityLineItem"`) and no type filter, then keep the rows whose `sfType` is `Standard Object` or `Custom Object`. When a name matches several objects (a managed package's copy, a label shared by two objects), ask the user which, listing name and API name.

"Account and its related objects" means: start with Account, run step 3, then `build_data_model.py neighbours` (step 5) and offer the top of that list.

Write the chosen objects as `$WORK/objects.json`, in the order the user named them (the first object anchors the layout):

```json
[{"nodeId": "6acdf98fb000e2f39adfb494", "name": "Account", "apiName": "Account", "sfType": "Standard Object"}]
```

## 3. The relationships

Chunk objects into at most 1000 node IDs per call:

`get_dependencies` with `refModelId`, `teamId`, `nodeIds` (at most 1000 from `objects.json`), `lookingFor: "where_used"`, `fieldTypes: "relationship"`, `includePopulation: true`.

It answers `status: "running"` until the rows are ready: call again with identical arguments. Then download every part with `curl -fsSL -o "$WORK/metadata/relationships-<index>.ndjson" "<url>"`. Download every native dependency part within its `expiresInSeconds`, 1800 seconds in this contract; repeat the same call for fresh links. Retain completion and all failure records using the shared acquisition procedure. When a reply lists fewer parts than `partsTotal`, call again with `partsFrom` set to `nextPartsFrom` until every part is saved; a missing part means missing relationships.

Each row is one Lookup, Master detail or Hierarchy field (`related`) on an object (`carryingObject`) that points at one of the objects (`node`).

## 4. The fields

One call per object (they can run in parallel):

`list_metadata_by_criteria` with `refModelId`, `metadataList: ["Field"]`, `filters: [{"column": "full_api_name", "operator": "startswith", "value": "<ApiName>/"}]`, `columns: ["name", "api_name", "full_api_name", "subtype", "required"]`.

Note the `/`: a field's full API name is `Account/Name` in Elements. Download each part into `$WORK/metadata/fields-<apiName>-<index>.ndjson` within its `expiresInSeconds` (30 minutes), with `partsFrom` as above when there are more parts than one reply lists.

For more than about 15 objects, one call without the filter downloads every field of the org instead (a few megabytes); save its parts as `$WORK/metadata/fields-all-<index>.ndjson` so the build's `fields-*.ndjson` pattern finds them. The script keeps only the objects in scope.

Metadata attachments in the resulting model carry the selected `refModelId`; retain it when adding links or handing the model to the drawer.

## 5. Build

```bash
python3 "$PLUGIN/scripts/build_data_model.py" build --objects "$WORK/objects.json" \
  --relationships "$WORK"/metadata/relationships-*.ndjson --fields "$WORK"/metadata/fields-*.ndjson \
  --title "Sales core data model" --ref-model "$REF_MODEL" --out "$WORK/model.json"
```

Add `--description` with one sentence on what the map is for, and `--fields-per-entity N` when the user wants more or fewer fields than six; pass the same number as `--max-fields` at the plan, which otherwise draws six. When amending a map, write to `--out "$WORK/addition.json"` (the skill's step 1c).

What the script decides, so you can explain it:

| Question | Answer |
|---|---|
| Which objects | Exactly those in `objects.json` |
| Which relationships | Every relationship field between two objects in scope, except system fields in `data/system-fields.csv` (owner, created by, record type...) |
| Line ends | Master-detail: exactly one at the parent. Lookup that is required: exactly one at the parent. Any other lookup: the house default, zero-or-one to zero-or-many |
| Labels | A line is labelled with its field's label when the label is not just the parent's name ("Partner Account", "Parent Case"), when an object points at itself, and when two lines join the same two objects |
| Fields on a card | The record name or number (marked `#`), required fields, relationship fields, status-like picklists, then the rest, up to six; system fields and second fields with the same label are left out |
| Kind (colour) | Standard or custom from the object's type |

```bash
python3 "$PLUGIN/scripts/build_data_model.py" neighbours --objects "$WORK/objects.json" \
  --relationships "$WORK"/metadata/relationships-*.ndjson --top 10
```

lists objects outside the scope that point at objects in scope, most direct links first. Fields that can point at almost anything (`WhatId`, `ParentId` on activities and system objects) are shown as polymorphic and not counted, so they do not crowd the list. Offer the top few; to add one, append it to `objects.json` and repeat steps 3 to 5 (step 3 must include the new object, so its own relationships are found).

## 6. Check what you built

Open `model.json` and look before drawing: entity names are the labels people see; a relationship you did not expect is real (the org has that field), but say so to the user when it looks surprising (Opportunity has a Contact lookup most orgs never fill). Then go back to step 2 of the skill.
