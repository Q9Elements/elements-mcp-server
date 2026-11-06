# Data contracts: show-status-automations

Every file the run reads or writes in `$WORK`. JSON unless the name says
otherwise; `status_automations.py` writes all of them except the saved tool
results (the skill saves those) and `facts/` (the agents write those).

## Contents

- [boxes.json (input)](#boxesjson-input)
- [Saved tool results](#saved-tool-results)
- [writes/ (what each placed automation writes)](#writes-what-each-placed-automation-writes)
- [draw/ files of the objects part](#draw-files-of-the-objects-part)
- [briefs/ and facts/](#briefsnodeidjson-script-and-factsnodeidjson-agent)
- [report.json and report.md](#reportjson-and-reportmd)
- [done.json](#donejson)

## boxes.json (input)

```json
{
  "refModelId": "6acdf381b03e6e54beac4a1c",
  "teamId": "optional, when the token holds several spaces",
  "boxes": [{
    "id": "any unique id (the model activity id in hook mode)",
    "diagramId": "the level the status box is on",
    "boxKey": 24,
    "boxText": "Validate expansion signal against usage",
    "object": "Opportunity", "objectLabel": "Opportunity",
    "field": "StageName", "fieldLabel": "Stage",
    "value": "Marketing Qualified",
    "valueNodeId": "the value on the field (not the standard value set's copy)",
    "fieldNodeId": "...", "objectNodeId": "...",
    "recordType": {"name": "Add_On_Opportunity", "label": "Add On Opportunity", "nodeId": "..."},
    "isFirstStatus": false,
    "boxOutcome": "Opportunity stage updated to 'Marketing Qualified'",
    "statuses": ["every value of the field, in order"]
  }]
}
```

Optional keys for the objects part:

- `scope`, `inventory`: paths (absolute, or relative to `$WORK`) of the
  map-process-from-data-model run's `scope.json` and `inventory.json`. Left out,
  `../scope.json` and `../inventory.json` are used when they exist. `scope.json`
  `metadata.basis` (`usage` or `configuration`; without it `onlyWithRecords`
  true means usage, anything else configuration) decides the no-records flags;
  `inventory.json` `objects[].usage` (`available`, `total`, ...) gives record
  counts. Both are read tolerantly: a missing key means "not known".
- `objectsBefore`: per box, the objects the model gives the step (written by
  `boxes`); `report.md` shows them as "Before" when the level has not been read.
- `objectsRollup`: `written` (default), `level` or `off`; how the record-type
  boxes of the split level are given objects.

`boxes` records each box's `boundary.inputs` and `boundary.outputs` as `{key, label}` entries from its parent level. Before writing a child, the drawing loop takes these from the saved parent read. Each metadata attachment uses the top-level `refModelId`; the report carries it on each box.

`recordType` is left out when the level is not one record type's.
`isFirstStatus` is true for the box the level starts at (a line from the
level's start or its parent's input comes into it); create-only automations
count only there.

## Saved tool results

| File | Tool | What |
|---|---|---|
| `metadata/manifest.json` | `get_dependencies` where_used, mode manifest | counts per node and type, over every value, field, object and record type node |
| `metadata/rows-<type>.ndjson` | `get_dependencies` where_used, sfType = type | the rows of one registry type over the nodes that have a count; every part joined |
| `metadata/attributes-<type>-<n>.ndjson` | `list_metadata_by_criteria` | each candidate's stored attributes (flows: name, api_name, active, subtype, trigger_type, trigger_order, async_run), up to 100 API names a call; no attribute request when no candidate type needs one |
| `explain/<n>.json` | `explain_metadata_components` | one file per call, numbered in call order; the script reads the latest status of each automation and aspect |
| `metadata/descriptions-<n>.json` | `get_metadata_component` (summary) | the fallback evidence when no explanation can be generated |
| `draw/parent-<diagramId>.json` | `get_diagram` | a level holding status boxes |
| `draw/children-<diagramId>-<version>.json` | `manage_diagram` `add child` | its `children` list gives each new child level's diagramId |
| `draw/dry-<childId>.json`, `draw/written-<childId>.json` | `manage_diagram` | the preview of the first child level, and each write |
| `draw/plan-<childId>-<n>.json` (script) and `draw/rewritten-<childId>-<n>.json` | `manage_diagram` | the hash of the layout write n was made from, and each redraw; a level whose hash differs from the current report is stale |
| `draw/layout-<childId>.json` | `get_diagram` include layout | every child level before its first write or a redraw: its canvas (where the chain is placed), version and boundary stubs; delete it to read the level afresh |
| `draw/refused-<childId>.json` (script) | | a child level whose redraw `manage_diagram` refused with `version_conflict`: someone edited it, so it is never drawn over and never `stale` again, and it is listed in `skippedLevels` |
| `draw/failed/<name>.<k>.json` (script) | | a saved write (child level or objects) that saved nothing, moved here by `next` with the read it was planned from, so the level is read afresh and the write planned again; never counted as drawn |

## writes/ (what each placed automation writes)

| File | Tool | What |
|---|---|---|
| `writes/using-<n>.ndjson` | `get_dependencies` lookingFor `using` | the rows of round n: first the placed automations, then the flows and Apex classes they call; every part joined |
| `writes/source-<n>.ndjson` | `get_metadata_source` | the definitions of every Flow, Apex Trigger, Apex Class, Process Builder and Workflow Rule among them |
| `writes/usage-<n>.json` | `get_component_usage` | usage basis only: record counts of written objects the inventory has none for (50 a call) |
| `writes/<kind>-<n>.request.json` (script) | | the nodeIds the script asked for in that call; a call counts once its result is saved beside it |
| `writes/writes.json` (script) | | per automation: `writes` `[{object, label, objectNodeId, operations: [create, update, delete], evidence: [...]}]`, `reads`, `unclear` (read or write cannot be told), `unresolved` (writes whose object cannot be worked out), `basis` (dependency graph, definition, explanation) |

Evidence strings say where each write was read: `dependency graph: Create Record
'Create Invoice'`, `dependency graph (field EndDate): ...`, `definition: Create
Records 'Create Invoice' (Invoice)`, `definition: insert eir;`, prefixed `via
subflow 'X': ` or `via Apex class 'X': ` for what a called automation writes.

## draw/ files of the objects part

| File | What |
|---|---|
| `draw/objects-library.json`, `.request.json` | the one dry run that checks every new Object resource name against the space library (`resource_type_differs`: the library holds it as a person or system, so the API name is used; `resource_created`: new, added as Object) |
| `draw/objects-read-<diagramId>-<key>.json` | `get_diagram` include `attachments` of a level before its objects write |
| `draw/objects-written-<diagramId>-<hash>.json` | the `manage_diagram` result of the objects write |
| `draw/objects-<diagramId>.json` (script) | the marker: the hash of what the level was given and the version written; a level whose hash matches is done |

A note over 2,000
characters (the server's limit) groups objects the same automations write the same
way on one line.

Notes the objects part writes (one note a box):

- status box: the "Objects used" part of "About this step" (the line starting
  "Objects used", the "- " list under it and its "Also written (past" and "Flag:"
  and "Not shown as resources" lines); the rest of the note is kept as read. It needs the level read with note
  text (`include` `attachments` or `notes`). A separate note titled
  "Objects written behind this step" on the box is removed;
- automation box: the "Writes:" line of "About this automation" comes from the
  layout (`child_changes`, from each step's `writes`); a separate note titled
  "Objects this automation writes" on the box is removed;
- record-type box: "Objects written by automations in this lifecycle", when at least one object beyond the lifecycle object is listed.

A text-only redraw replaces a box's note with a new one, which takes a new key;
the next redraw takes the keys from the last write's diff (`diff.changed[].after`),
so save that part of each write result.

## briefs/<nodeId>.json (script) and facts/<nodeId>.json (agent)

The brief holds the automation (`nodeId`, `name`, `apiName`, `type`), the
`object`, `field`, `fieldLabel`, `statusValues`, the map's `recordTypes`,
`linkedAt` (status and hit level per box that found it), the dependency
`relationships`, and `explanation` (`aspect`, `narrative`, `confidence`).
`narrative` preserves the returned shape: a chain object with `sections` and
`chainRelationGroups`, a summary object with `purpose` and `text`, or plain
text. Chain sections include nested prose in `whenItRuns`. The shared helper `scripts/metadata_narrative.py` at the plugin root reads these shapes. Fact quotations
are checked against prose values, excluding `confidenceScore` and
`chainRelationGroups`.
When no explanation could be generated, `explanation.aspect` is
`description`, the narrative is the component's description and
`evidenceSource` is `description`; every step resting on it is flagged.

The facts file is described in the `automation-firing-reader` agent;
`check-facts` checks it.

## report.json and report.md

Per box: `box` (id, diagramId, boxKey, boxText, value, boxOutcome, refModelId, boundary,
isFirstStatus, objectLabel, fieldLabel), `recordType`, and

- `steps`: in placement order, each with `position`, `type`, `name`,
  `apiName`, `nodeId`, `hitLevel`, `when` (value, transition or create),
  `target` (transition), `rung` (the save step, 1-8, or null when not
  stated), `triggerOrder` (a flow's stored order, or null), `activity`,
  `outcome`, `input`, `evidence`, `confidence`, `flags`; transitions from the
  status come last, as the save that leaves it;
- `scheduled`: schedule-triggered flows kept for the status, listed beside the
  chain, not placed;
- `conditions`: validation rules kept for the status, with `condition` and
  `apiName`; drawn as one check box in the chain;
- `dropped` and `unverified`: each with `reason`;
- `coverage`: per registry type, the level it was found at, `none found`, or
  why it does not apply;
- `objects` (boxes with steps only; null otherwise): `lifecycleObject`,
  `before` (the Object resources the box had), `after` (the ones it shows as resources, in
  order), `overflow` (written
  objects named only in the note), `written` (`object`, `label`, `name` as drawn, `operations`,
  `automations`, `by` (operations per automation), `evidence`), `flagged` (`object`,
  `reason`: no records, usage basis only), `unclear`, `unresolved`;
- each step also has `writes`: `[{object, label, operations, via}]`, what it
  writes in box order (`via`: the subflow or Apex class chain when it writes the
  object only through them), drawn as the "Writes:" line of its note.

Top level: `basis` (`usage` or `configuration`), `rollup` (per record-type box:
`diagramId`, `boxKey`, `boxText`, `level`, `mode`, `objects` with `boxes`
counts, `after`, `overflow`) and `objectsInput`, the hash of the writes files
the report was made from: `next` reruns the report when it changes.

`report.md` is the same as a table per box, for the person to review before
any diagram changes.

## done.json

Written by `next` when the run is finished, and only then: at `done` (every
child level and every objects write is saved) and at `skipped` (nothing is left
but the levels in `skippedLevels`). A run started from
map-process-from-data-model works in `<its work folder>/status-automations/` and
waits for this file there. Any other action `next` prints moves an earlier
`done.json` into `draw/superseded/`, so the file stands only while the latest
`next` finished the run.

- `at`: when, in UTC (ISO 8601).
- `levelsDrawn` and `childLevels`: how many child levels the skill drew, and
  their diagramIds.
- `leftAsTheyWere`: child levels that already had boxes, so the skill left them.
- `boxes`, `boxesWithChildLevel`, `boxesWithAutomations` (boxes with placed
  steps) and `automationsPlaced`.
- `objectLevels`: the levels the objects part wrote or found already right;
  `report`: the path of `report.md`.
- `skippedLevels`: `[{diagramId, title, reason}]`, empty after `done`. The
  levels passed with `--skip` have the reason "open in the editor", or "edited
  by someone" for a status level holding a refused child level; each refused
  child level is listed with "edited by someone". A later run of `next` that
  draws a level writes the file again without it.

Every native row file is the complete joined request output of scripts/acquire_result.py native, with its adjacent .acquisition.json sidecar. The sidecar records terminal status, resultId, parts/counts, saved digest and every failure, including failedFile coverage. Missing or incomplete acquisition evidence is refused before rows are used.
