# Files and hand-offs

Every file a run writes lives in one work folder, so a run can be stopped and resumed and every step can be checked. The skill creates it at kickoff: `map-process-from-data-model/<system-slug>/` in the current working directory unless the person names another place. In commands, `$WORK` is that folder, `$SKILL` this skill's folder and `$PLUGIN` the plugin's folder (two levels up).

## Contents

- scope.json
- inventory.json
- clusters.json
- capabilities.proposal.json
- Briefs
- Level outlines
- model.json: the hand-off to drawing
- coverage.json
- Stages 7 and 8: the drawing and the status automations

```
$WORK/
├── scope.json                  # what the person confirmed at kickoff
├── docs/index.json             # route docs: the index run's partial inventory
├── docs/detail-<nn>.json       # route docs: one partial inventory per detail run
├── metadata/*.ndjson           # route metadata: downloaded Elements result parts
├── metadata/lifecycle/*.json   # route metadata: saved get_metadata_component results of lifecycle fields and values
├── metadata/record-type-objects-<label>.json  # route metadata: saved get_org_health_detail (objects_by_record_type)
├── metadata/record-type-processes-<n>.ndjson, process-values-<n>.ndjson  # Lead, Opportunity, Case: record type -> process -> values
├── metadata/process-<record type>.json        # route metadata: saved get_process_map of a generated record type map
├── metadata/usage-<n>.json     # basis usage: saved get_component_usage results, 50 objects each
├── inventory.json              # objects, relationships, capabilities (inventory.py)
├── clusters.json               # suggested groups of objects (cluster_objects.py)
├── capabilities.proposal.json  # the capability-grouper's proposal
├── briefs/top.json             # what the top-level writer gets (prepare_briefs.py top)
├── briefs/<capability>.json    # what each child-level writer gets (prepare_briefs.py children)
├── briefs/<capability>--<record type>.json  # a record type's lifecycle brief, under a split level
├── levels/top.json             # the top level, written by process-level-writer
├── levels/<capability>.json    # one level per capability, written by process-level-writer (a split level: by prepare_briefs.py)
├── levels/<capability>--<record type>.json  # one lifecycle level per record type (writer, or import_org_process.py)
├── model.json                  # the business-architecture model (build_model.py)
├── coverage.json               # check_coverage.py findings
├── drawing/                    # stage 7: draw-process-map's work folder (scope.json drawing.dir)
└── status-automations/         # stage 8: show-status-automations' work folder, done.json when it has finished
```

## scope.json

Written by the skill at kickoff. `scripts/status.py` checks it holds the system, route and mode, and keeps `stage` up to date.

```json
{
  "system": "Salesforce Manufacturing Cloud",
  "variant": "Current release, out of the box",
  "route": "docs",
  "mode": "checkpoints",
  "title": "Business Process (Manufacturing Cloud)",
  "metadata": {"refModelId": null, "teamId": null, "objects": null, "orgType": null, "basis": null,
               "onlyWithRecords": null, "named": []},
  "focus": null,
  "statusAutomations": true,
  "drawing": {"dir": "/work/map-process-from-data-model/manufacturing-cloud/drawing"},
  "generatorFallback": {"run": null, "levels": {}},
  "stage": "inventory"
}
```

- `focus`: the object's API name when the person asked for the process of one object (scope `object`); `inventory.py focus` copies it into the inventory.

- `mode`: `checkpoints` stops for the person's confirmation after the capability list and after the top level; `autopilot` runs to the end. The person chooses at kickoff.
- `stage`: the last stage finished: `kickoff`, `inventory`, `capabilities`, `top`, `areas` (only when capabilities have areas), `children`, `model`, `draw`, `status-automations`. `scripts/status.py` records it from the files in the work folder; on resume, run that script rather than trusting this field.
- `statusAutomations` (route metadata): the kickoff answer to "Expose the automations behind each status?". True, or missing, runs stage 8; false counts stage 8 as done without running it.
- `drawing.dir`: the drawing's work folder, which `draw-process-map` writes into; absolute, or relative to the work folder; `$WORK/drawing/` when missing.
- `generatorFallback` (route metadata): why levels meant to come from Elements' org-to-process were written by `process-level-writer` agents instead (the stage-5 fallback). `levels` maps a record type's level id to the reason (the `generate_process_map` error, an empty map, or the person's choice); `run`, on a one-object run, says why `elements-org-to-process` did not draw the object. See *Levels written by the fallback* below.
- `metadata.objects`: `entire-org`, `standard`, `standard-custom`, `standard-custom-managed` or `named`.
- `metadata.orgType` (route metadata): `production`, `full-sandbox` or `other-sandbox`, as the person said; Elements does not record it.
- `metadata.basis` (route metadata): `usage` (draw only objects that hold records) or `configuration` (draw every object in scope). `usage` needs `orgType` `production` or `full-sandbox`; `status.py` stops at kickoff otherwise. See *Appendix: the usage contract*.
- `metadata.onlyWithRecords`: the older form of the basis, kept so old work folders still run: `true` reads as usage, `false` or null as configuration. When both are set, `basis` wins. Write both (`basis` usage with `onlyWithRecords` true) so older tools read the same answer.

## inventory.json

[`../schemas/inventory.schema.json`](../schemas/inventory.schema.json). Partial inventories from the doc reader have the same shape. `scripts/inventory.py check` checks one.

The rules the schema cannot express, which `inventory.py set-capabilities` and `check` enforce:

- every object that is neither platform nor hub is owned by exactly one capability, or listed as unassigned with a reason (it becomes a gap);
- a hub is owned by at most one capability and may be shared by any;
- an area (a capability other capabilities name as `parent`) owns no objects, and areas do not nest;
- at most ten capabilities on the top level and ten under any area;
- capability names differ among siblings.

## clusters.json

Written by `cluster_objects.py`, read by the capability grouper. Not a contract anything else depends on: each cluster has `members` (apiName, name, kind, how many in-scope objects reference it), `rootObjects` (members that are not the detail of another member), `hubsUsed`, `linksToOtherClusters`, and, when the inventory already has source capabilities, `notInAnySourceCapability`. Also `hubs` (with how many clusters use each) and `platformObjects`.

## capabilities.proposal.json

Written by the capability-grouper agent; applied with `inventory.py set-capabilities`.

```json
{
  "capabilities": [
    {"id": "warranty-claims", "name": "Warranty claims", "origin": "source",
     "description": "Claims for repairs under warranty, from submission to payment.",
     "objects": ["Claim", "ClaimItem", "ClaimCoverage", "ClaimCoveragePaymentDetail", "ClaimParticipant"],
     "sharedObjects": ["Account", "Asset"],
     "docUrl": "https://developer.salesforce.com/docs/platform/data-models/guide/warranty-claims.html",
     "evidence": ["Data Model Gallery guide 'Warranty Claims'"]}
  ],
  "unassigned": [{"apiName": "sfcma__SetupWizardSteps__c", "reason": "Managed-package setup data, not a business record"}],
  "notes": "Optional: how the grouping was decided, for the person."
}
```

Each capability has the fields of the inventory schema's `capability`.

Lifecycles: an object's `lifecycle` holds its status or stage picklist (`field`, `label`, and on route metadata `fieldNodeId`, the field's node, which show-status-automations reads), its active `values` (each `value`, its Elements `nodeId` on route metadata, and `closed`, `won`, `default` where the source says), whether the source gives their order (`ordered`), where they come from (`source`), and on route metadata the object's custom record types (`recordTypes`: each `name` (developer name), `label`, `nodeId`, the `values` it uses, in the field's order, and on Lead, Opportunity and Case the `process` those values come from). `inventory.py lifecycle` writes it on route metadata; the doc reader writes it on route docs. `check` refuses a value listed twice or won but not closed; `lifecycle` warns about a record type that uses none of the values, and about a Lead, Opportunity or Case record type with no process values.

Which levels a lifecycle drives is worked out from the inventory alone (`common.lifecycle_plan`, so the brief, build and status scripts agree): in each capability that owns objects (not an area), the main object is the owned object with a lifecycle that the capability's other objects point at most (a Lead, Opportunity or Case counts only when each of its record types has its process values, `common.lifecycle_ready`) (with a `focus`, that object). The capability's level is then a lifecycle level, or, with record types, a split level whose record type boxes each drill down to a lifecycle level `<capability>--<record type slug>`.

**Usage.** On route metadata with basis usage, `inventory.py usage` adds the inventory's `basis`, each object's `usage` (how many records it holds, per record type, and how that is changing) and each lifecycle record type's `usage.total`. The scripts decide with `common.object_used` whether an object is drawn. The fields and the rules are in *Appendix: the usage contract*.

## Briefs

Written by `prepare_briefs.py`; one per level; read by one `process-level-writer` each. Data only.

| Field | Overview brief (top level, area level) | Detail brief (a capability's level) |
|---|---|---|
| `mode` | `overview` | `detail`, or `lifecycle` (see below) |
| `level` | `top` or the area id | the capability id |
| `outlinePath` | where the writer saves the outline | same |
| `parent` | `null` on the top level; on an area level, the parent box: `stepId`, `name`, `inputs`, `outputs` | the parent box, same fields |
| `items` | one per capability: name, description, owned object count, key objects, help links, `dependsOn`, `supporting` | — |
| `capability` | — | id, name, description, guide URL, help links |
| `objects` | — | every object to cover, in suggested order, with description, kind, archetype, typical verbs, key fields |
| `sharedObjects` | — | objects owned elsewhere that the capability's objects point at |
| `relationships` | — | reference fields among those objects |
| `suggestedOrder` | capability ids | apiNames |
| `budget` | min and max boxes | max boxes, objects to cover, typical number of steps |
| `rulesPath` | [`articulation-rules.md`](articulation-rules.md) | same |
| `cover` | `items`: the capability ids, one box each | `uses`: the owned objects, each used or in a gap; `mayUse`: the shared objects; in a lifecycle brief, `lifecycle`: the values the level holds, one step each |

A **lifecycle brief** (`mode: "lifecycle"`) is a detail brief for a level built on one lifecycle, with `lifecycle` and `cover.lifecycle`: `object`, `name`, `field`, `fieldLabel`, `ordered`, `recordType` (the label, or null) and the `values` the level must hold, one step each; `object` (the lifecycle object's apiName, name and description); `recordType` (`name`, `label`) under a split, where `cover.uses` holds the lifecycle object only and the capability's other owned objects move to `mayUse` (the record types' levels share them; C02 checks each is used on one of them); and a budget of one step per value (at most the number of values plus two, never fewer than ten).

On basis usage, a brief never offers an object that holds no records: it is left out of `objects`, `sharedObjects`, `relationships`, `cover.uses` and `cover.mayUse`, and listed under `excludedByUsage` (apiName and name) so the writer knows why it is missing; objects whose usage is unknown are listed under `usageUnknown` and offered as usual. An overview brief's item lists them under `withoutRecords` and leaves them out of `keyObjects`. Record type usage is not copied into briefs.

A **split level** is not a brief: `prepare_briefs.py` writes it as the capability's outline (`source: "record-type-split"`): a step `choose` ("Decide which <object> to capture") taking the parent box's inputs and roles, a line per record type ("<label> <object> needed", at most about 40 characters since it is drawn again on a start line) to a step `rt-<slug>` ("Process <label> <object>") whose `item` is the record type's level, and the parent box's outputs as each record type step's ends. It then writes one lifecycle brief per record type, whose `parent` is that record type's box.

With a `focus` object, the top level is the one capability's level (`level: "top"`, no parent): a lifecycle brief, a split outline with its record type briefs, or a detail brief when the object has no lifecycle.

## Level outlines

The plugin's [`../../../schemas/level-outline.schema.json`](../../../schemas/level-outline.schema.json) (shared by every process reader: a step's `uses` holds apiNames, `item` the capability a box stands for), written by the `process-level-writer` agent following [`articulation-rules.md`](articulation-rules.md). The plugin's `scripts/check_outline.py` checks one against its brief while the writer works. `build_model.py` checks each one again: its shape, unique step ids and box texts, lines that point at real steps (never at their own step), a person or team on every step, distinct labels on every line of the level, a box per capability on overview levels, and starts and ends that carry the parent box's labels. A step may carry `value` (the lifecycle value it stands for), and a start, a line or an end `sets` (`object`, `value`): the lifecycle value the record has once the outcome holds. On a lifecycle level, `check_outline.py` and the build check (`process_levels.lifecycle_level_findings`) that each value of `cover.lifecycle` has exactly one step, that the step's first line out (or its end) sets that value and names it, that no other line out of it sets a value, and with an ordered lifecycle that the main path does not go back. An outline with `source: "org-to-process"` (written by `import_org_process.py` from a generated map) is not checked per value, and carries a gap about the object saying so.

## model.json: the hand-off to drawing

A business-architecture model ([`../../../schemas/ba-model.schema.json`](../../../schemas/ba-model.schema.json), explained in [`../../../schemas/README.md`](../../../schemas/README.md)), checked with the plugin's `scripts/validate.py --for process` (`$PLUGIN/scripts/validate.py`). It is what the `draw-process-map` skill draws. What it holds, and what the drawing skill is expected to do with it:

| In the model | Comes from | Drawn as |
|---|---|---|
| `activities` without `parent` | top-level outline | boxes on the top level |
| `activities` with `parent` | child outlines | boxes on the child level behind the parent box; area levels add a third level |
| `activities[].roles` | outline roles, merged by name across levels | resources: the person or team first, RASCI on people only |
| `activities[].uses` | outline `uses` (objects), plus the object whose lifecycle value a line out of the step sets; on a box standing for a capability or an area, its main records (two, or three for an area: objects with a lifecycle first, then the most referenced) | Object resources after the roles, named as the entity, as in the exemplar; on a full box the objects keep two of the five places. Missing names are added to the space library without asking (`--no-create-objects` stops that; `--no-uses` leaves objects out, only when the person asks) |
| `activities[].attachments` | help links; an "About this step" note (what happens, why, the objects used with their descriptions, the value or record type the box stands for); on route metadata a metadata attachment per object, each carrying `refModelId` from the inventory's metadata source, a Record Type attachment on a record type box, and on a value's box only a Custom Value attachment (the value on the field, with its `nodeId`): no Field and no object attachments, which would repeat the same items on every box of the level | attachments on the box (`--skip metadata` when the space has no connected org). `manage_diagram` finds a Custom Value or Record Type by its bare name and type within the attachment's `refModelId`, so one whose name is not unique within that model (including duplicate values of a standard value set) is dropped from the write and reported as `unlinkable`, with its `nodeId` |
| `activities[].join` | outline `join: "all"` | lines into the box meet at one point |
| `flows` from `START` / to `END` | outline starts and ends | free starts and ends; on a child level, linked to the parent's lines with `parentLine` (the labels match exactly) |
| `flows[].sets` | outline `sets`, with the object's entity id | nothing extra: the label already names the value |
| `flows` between activities | outline `next`, in the order written | labelled lines; the first-listed line out of a box is its main path, the others are drawn above and below; lines out of one box with one label start steps in parallel |
| `entities`, `relationships` | inventory objects used or owned (with their `lifecycle`), and their reference fields | not on the process map; available to the data-model drawing skill |
| `capabilities` | inventory capabilities; `realisedBy` holds the box and the owned objects | not on the process map; available to the capability-map drawing skill |
| `levelNotes` | the build, on basis usage only: one per level a lifecycle drives (object lifecycle, record-type split, record-type lifecycle), with `parent` (the box the level drills down from; left out on the top level), `near` (step 1: the box the level's first start enters), `title`, `text` and `purpose` `usage` | a sticky note beside step 1, placed by the drawing script (above-left of the box, clear of boxes and lines); `--skip note` leaves it out |
| `gaps` | inventory, outlines and the build (with `--scope`, one per level the fallback writers wrote) | reported to the person, never drawn |

Objects of a system other than the space's own org are usually not in the space's resource library. The drawing skill's preflight finds them before anything is written and adds them to the library itself, ten per change; missing people and systems it asks about (`--create-resources`). The `diagram-reviewer` accepts Object resources drawn from `uses` without expecting them.

## coverage.json

`check_coverage.py --json` output: `errors` and `warnings` (counts), `findings` (one line each, prefixed with the check code C01 to C16), and with `--golden` a `comparison` block. On basis usage it adds `basis` and `excludedByUsage` (the API names of objects holding no records), and the findings carry `INFO` lines, counted neither as errors nor as warnings: C02 for an owned object left out because it holds no records, and C06 or C15 for a box left with no object for that reason.

C16 compares every pair of role names in the model (difflib ratio, case and spacing ignored; `ROLE_SIMILARITY` 0.88) and names each role's box count and level files (`levels/top.json`, or `levels/<level>.json`, the part of a child box's id before the first dot).

## Stages 7 and 8: the drawing and the status automations

`status.py` counts stage 7 done when `<drawing.dir>/layout-check.json`, `<drawing.dir>/review/top.json` and `<drawing.dir>/review.json` exist: `layout_process.py check` writes the first once every saved review read is whole, and the drawing protocol saves the `diagram-reviewer`'s verdict as the last, so all three exist only when `draw-process-map` has checked its drawing and had it reviewed.

Stage 8 applies on route metadata when `model.json` has a value box (a box a line out of which sets a lifecycle value, as `status_automations.py boxes` finds them); with no value boxes `status.py` prints `NOT APPLICABLE status-automations (no box sets a lifecycle value)`; on route docs it prints `NOT APPLICABLE status-automations (route docs: automations are read from a connected org)` and the run is complete after stage 7. The `boxes` command reads `model.renamed.json` instead of `model.json` when `layout_process.py plan --apply-renames` wrote it (and it is not older than `model.json`), so `boxes.json` names the objects as the drawing does. Its work folder is `$WORK/status-automations/`: `boxes.json` from the `boxes` command `status.py` prints, then the files [`../../show-status-automations/references/data-contracts.md`](../../show-status-automations/references/data-contracts.md) lists, and `done.json`, which `status_automations.py next` writes when it reaches its `done` or `skipped` action. Stage 8 is done when `done.json` exists or `scope.json` `statusAutomations` is false. When `done.json` has a non-empty `skippedLevels` (`[{diagramId, title, reason}]`: levels left alone because they were open in the editor or someone edited them), the run still completes, stage 8's `DONE` line says how many were skipped and names them, and `--json` lists them as `skippedLevels`, so the final answer names each. Until every applicable stage is done, `status.py` prints a `NEXT` stage; then it prints `NEXT Run complete`.

## Levels written by the fallback

`common.generator_levels` lists the levels Elements' org-to-process is meant to write, from the inventory: on route metadata, every record type's lifecycle level, and on a one-object run every lifecycle level (the run stands in for `elements-org-to-process`). `common.fallback_levels` returns those whose outline exists without `"source": "org-to-process"`, each with its reason from `scope.json` `generatorFallback` (`levels[<level>]`, else `run` on a one-object run, else "reason not recorded in scope.json generatorFallback"). `status.py` names them on stage 5's `DONE` line, grouped by reason, and lists them as `fallbackLevels` with `--json`; `build_model.py --scope` adds a gap for each to the model, so the final answer names them with the other gaps.

## Appendix: the usage contract

What a run on basis usage writes and reads. Changes to map-process-from-data-model and show-status-automations read these names, so keep them.

| Where | Field | Meaning |
|---|---|---|
| `scope.json` | `metadata.basis` | `usage` or `configuration`; `metadata.orgType` says whether usage may be chosen |
| `inventory.json` | `basis` | copied from the scope by `inventory.py usage` (or `from-metadata --basis`); left out means configuration |
| `inventory.json` | `objects[].usage` | `available` (false when Elements has no usage for it, with `reason`), `total` (records; null when unknown), `byRecordType` (`{label: count}`, Master aside), `withoutRecordType` (Master's count), `lastCreated`, `lastModified` (ISO date-times or null), `net7`, `net30` (net change in the record count over 7 and 30 days, or null), `windowDays` (days of daily snapshots behind them), `trend`, `readAt` (YYYY-MM-DD) |
| `inventory.json` | `objects[].lifecycle.recordTypes[].usage` | `{"total": int or null}`: that record type's records, matched by label, then by developer name |
| `inventory.json` | `objects[].hasRecords` | the older yes/no flag; `inventory.py usage` sets it from `usage.total` when known. Nothing decides on it any more |

Rules, in `scripts/common.py`:

- `object_used(obj, basis)` returns True, False or None. Under configuration it is always True. Under usage it is True when `usage.total` is above 0, False when it is 0, and None when the usage is missing or unavailable. None is treated as used and named in a gap ("Usage unknown"): missing telemetry is never read as zero records.
- `record_type_used(rt, basis)` is the same for one record type; a record type holding no records stays on the split (it is configuration), and its box note says it holds none.
- `unused_objects(inv)`, `unknown_usage(inv)`, `no_records_line(inv, apis)` ("Configured but holding no records: X, Y") and `usage_stop(inv)` (the stop message when the focus object holds no records) are what the scripts share.
- `lifecycle_plan` does not build a lifecycle level on an object that holds no records; the capability then gets a detail level.
- In the model, an object holding no records is in no activity's `uses` and no metadata attachment; on a level that no lifecycle drives the first box's "About this step" note names those of its capability, a capability box names its own, and `gaps` holds one line per capability. On a level a lifecycle drives, the usage note names the empty objects related to the level's object instead (below), and step 1's note does not.

### The usage note (`levelNotes`)

`build_model.py` writes one `levelNotes` entry per level a lifecycle drives, on basis usage only; under configuration the model has no `levelNotes`. The text comes from `scripts/usage_notes.py`:

| Level | Function | Reads |
|---|---|---|
| object lifecycle | `object_text(usage)` | the object's `usage` |
| record-type lifecycle | `record_type_text(usage, label, count, objectName)` | the object's `usage`; the count from `lifecycle.recordTypes[].usage.total`, else `usage.byRecordType` by label, then developer name (`record_type_count`) |
| record-type split | `split_text(usage, [(label, count)])` | as above, for every record type, then `withoutRecordType` |

- The title is `title(name, usage)`: "Usage of <object or record type label> as of <readAt>". The drawing joins title and text into one note: "<title>. <text>". Example, record-type level: "Usage of Initial Opportunity as of 2026-10-21. 100 records (83% of 120 Opportunity records). Last created 2026-10-20, last modified 2026-10-21 (Opportunity-wide). Net change over 30 days: +12, trend up (Opportunity-wide). Deletions not tracked. Reading: Active."
- The reading is `reading(usage, total)`, with `ACTIVE_DAYS` 30 and `DORMANT_DAYS` 180, counted from `readAt` to the later of `lastCreated` and `lastModified`: No records (total 0), Active (30 days or fewer), Slowing (31 to 180), Dormant (over 180), "Activity dates not available" (neither date).
- `usage.available` false, or a missing total: "Usage not available: <reason>. A telemetry gap, not zero records." No reading. `net30` null: "Net change not available." `windowDays` under 30: "Net change over <n> days: …". The deletions sentence is always "Deletions not tracked." (`DELETIONS`).
- The note ends with `no_records_sentence(names)`: "<n> objects that have a relationship to this object hold no records: A, B, C." (singular "1 object that has a relationship to this object holds no records: A."; left out when there are none). The names are every object in `common.unused_objects(inv, related_objects(inv, <level's object>))`, by label, alphabetical, never truncated. `related_objects` reads the inventory's `relationships` (one row per synced reference field: `from` holds the field, `to` is its target, `kind`): rows of kind `lookup` or `master-detail` with the level's object as `from` or `to`, the object itself excluded; a `polymorphic` row counts only when the level's object is its `to`. The level's object is the lifecycle's object; on the split level, the same object. Step 1's "About this step" note on that level has no "Configured but holding no records" line; capability boxes and levels no lifecycle drives keep theirs (`common.no_records_line`).
- The text has no line breaks (a level note drops them). Parentheses are written as they are: on a note `manage_diagram` stores them unchanged (checked in testing; the space after "(" appears only in wrapped line labels). The figures before the list stay under about 300 characters; `layout_process.py plan` warns when a whole note is over 400 (`NOTE_TEXT_FIT`). Entities keep every owned object (a data model drawn from the same model still shows them), and record type usage is not copied into the model.
