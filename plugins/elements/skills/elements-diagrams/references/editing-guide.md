# Editing Guide

Detailed rules for modifying Elements diagram JSON. Referenced from SKILL.md.

---

## Importer Allowlist

The importer picks fields by an explicit whitelist; unknown fields are silently ignored.

| Element | Fields read by importer |
|---|---|
| activity | `mxKey, number, text, position, customStyle, style*,  footerText, resourcesPerRow, attributes, resources, attachments, drilldowns (presence only), image` |
| flowline | `mxKey, text, srcType, srcId, tgtType, tgtId, srcPosition, tgtPosition, customStyle, style, flForm, terminator, position, waypoints, connector` |
| swimlines | Container: `position {x, y, w, h}, horizontal, style, lines[]`; each line: `mxKey, text, size, style`. `position` (all four numbers) and `horizontal` are required whenever `lines` is non-empty |
| note | `mxKey, text, position, paperClass, locked` |
| text element | `mxKey, text, number, customStyle, style*, locked, position, link` |
| diagram image | `uuid, mxKey, position, copyImage, link` |
| resource | `mxKey, name, type, hidden, position, rasci` |

`*` `style` is only read when `customStyle: true`.

Resources are matched to the target team's library by **(name, type)** case-insensitively. `resourceDbId` is irrelevant to the importer.

---

## Resources: Auto-Creation

Resources are resolved via `findOrCreate` during import:
- If a resource with the same `name` + `type` exists in the target team → reused, no duplicate created.
- If it doesn't exist → **created automatically** in the target team's library.
- For cross-team imports of non-system resources, the icon is also copied from S3.

To add a new resource to an activity, include it in the activity's `resources[]` with `name`, `type`, and the other required fields. It will appear in the team library after import.

System resources (built-in platform resources, `system: true`) are looked up but never re-created; if one doesn't exist in the target team, it is silently omitted from the activity.

---

## Attachments: What Transfers

All attachment types on an activity round-trip through import, including their `groups` permission array:

| Type | Behaviour |
|---|---|
| `URL` | Transferred as-is |
| `IMAGE` | Image file re-uploaded to S3 with a new UUID; reference updated |
| `TEXT` | Note content re-uploaded to S3; embedded note images also re-uploaded |
| `refModelAttachments` | Re-created if the entry has non-empty `refModel` and `refModelNode`; import throws if either is missing |
| `requirementAttachments` | Re-created if the entry has a non-empty `requirement` id; import throws if missing |
| `storyAttachments` | Re-created if the entry has a non-empty `story` id; import throws if missing |
| `orgModelAttachments` | Re-created only when `sfNode` resolves to a Salesforce node that belongs to the target space; otherwise that one attachment is silently omitted |

`refModelAttachments`, `requirementAttachments`, and `storyAttachments` reference records (ref model node, requirement, story) by id — importing into a different space than the one the export came from will carry over stale ids that don't resolve there. Preserve these ids verbatim when editing within the same space.

---

## Adding an Activity

Minimum required fields:

```json
{
  "mxKey": 99,
  "number": 5,
  "text": "Activity description",
  "strippedText": "Activity description",
  "position": {"x": 500, "y": 200, "w": 180, "h": 120},
  "customStyle": false,
  "container": false,
  "locked": false,
  "attributePadding": false,
  "attributes": [],
  "resources": [],
  "attachments": [],
  "refModelAttachments": [],
  "orgModelAttachments": [],
  "requirementAttachments": [],
  "storyAttachments": [],
  "drilldowns": []
}
```

**`number`**: an integer from `1` to `999`, unique within the level. Controls both display sequence and child drilldown level. Never reuse a number that already has a drilldown: activity `number: 3` in level `1` owns level `1.3.json`, and changing the number would orphan the child.

**Positioning**: inspect neighbouring activities to avoid overlap. Standard size: `w: 180, h: 120–150`. Add a flowline if the activity belongs in the process sequence.

---

## Removing an Activity

1. Remove the activity from `activities[]`.
2. Remove all flowlines where `srcId` or `tgtId` equals the activity's mxKey.
3. If the activity had a non-empty `drilldowns` array, also remove the child level file(s) from the zip. Child = `parentLevel.activityNumber` (e.g. activity `number: 4` in level `1` → delete `1.4.json` and any descendants like `1.4.1.json`).

---

## Adding a Flowline

Minimum required fields:

```json
{
  "mxKey": 100,
  "text": "",
  "strippedText": "",
  "srcType": "activity",
  "srcId": 17,
  "tgtType": "activity",
  "tgtId": 22,
  "srcPosition": null,
  "tgtPosition": null,
  "customStyle": false,
  "position": {
    "offset": {"x": 0, "y": 0},
    "x": 0,
    "y": 15,
    "connectionPoints": {"exitX": 0.5, "exitY": 1, "entryX": 0.5, "entryY": 0}
  },
  "waypoints": null,
  "lineTexts": [],
  "connector": {"links": []}
}
```

**Connection point fractions (0–1):**

| Anchor | exitX/entryX | exitY/entryY |
|---|---|---|
| Top centre | 0.5 | 0 |
| Bottom centre | 0.5 | 1 |
| Left centre | 0 | 0.5 |
| Right centre | 1 | 0.5 |

`srcType`/`tgtType` may be `"activity"` or `"swimline"`. The corresponding `srcId`/`tgtId` must be an mxKey that exists in the appropriate element array.

**Common mistakes that cause import validation failure:**
- `srcPosition`/`tgtPosition` must be `null` or `{x: number, y: number}`, **never a string** like `"bottom"` or `"top"`.
- Activity `position` uses `w`/`h`, **never `width`/`height`**. The importer's Joi schema rejects unknown keys.

---

## Filling a Drilldown (Child Level)

The importer only **replaces** existing DRAFT levels — it cannot add new ones. A zip level with no
matching DRAFT level is skipped (`skippedLevels` in the import result), and a `drilldowns` entry
imported onto a parent activity whose child level does not exist leaves a marker pointing nowhere.

A new child level is therefore born in the Elements UI: a person adds a drill-down on the parent
activity, which creates the DRAFT level `<parentLevelNumber>.N` (N = the activity's `number`),
prepopulated with the parent's inbound and outbound flowlines as unattached off-page lines
(`srcType`/`tgtType` `"none"`) carrying the parent's labels.

Then fill it by the normal export round trip:

1. Export; the zip now contains `<parentLevelNumber>.N.json`.
2. Keep the prepopulated off-page lines (same `mxKey` and `text`) and wire each to your first/last
   activities: set `tgtType: "activity"` + `tgtId` on an inbound line, `srcType: "activity"` +
   `srcId` on an outbound one. Give each attached line an explicit free-end `srcPosition`/`tgtPosition`
   placed clear of other elements — two lines sharing a lane render as one arrow chained into another.
3. Add activities and interior flowlines as on any level.
4. Validate, upload, import — the existing level is replaced with your content.

The `drilldowns[].title` and `targetDbId` on the parent activity are display/metadata only. The
structural link is `parentLevelNumber + "." + activity.number`.

---

## Editing Existing Elements

**Text changes:** Update both `text` (may contain HTML like `<br>`, `<div>`, `<b>`) and `strippedText` (plain text; strip all HTML tags). They must stay in sync.

**Swimlane text is plain text and comes back HTML-escaped.** Write new or renamed lane text with a bare `&` (`Requester & Approver`): a lane saved as `&` comes back as `&amp;` in the next export. Lane text that already shows `&amp;` in an export can be left as it is; an untouched `Requester &amp; Approver` lane stayed single-escaped (`&amp;`, not `&amp;amp;`) across three import round trips. When you rename such a lane, write the new text with a bare `&`.

**Style changes:** Only modify the `style` object when `customStyle: true`. To apply a new custom style, set `customStyle: true` and provide a complete style object (see `schema.json` → `$defs.activity_style` for field definitions). To revert to theme default, set `customStyle: false` and leave `style` unchanged (importer ignores it).

---

## Adding Swimlanes

A map from `generate_process_map` has no swimlanes: roles appear only as `resources` on activities, and the level file's `swimlines.lines` is `[]`. To rename a lane on a generated map, first add the lanes, then import; renaming is a `text` edit on a lane that exists.

```json
"swimlines": {
  "position": {"x": -60, "y": -80, "w": 1450, "h": 400},
  "horizontal": 0,
  "lines": [
    {"mxKey": 100, "text": "Employee / Manager"},
    {"mxKey": 101, "text": "Finance"}
  ]
}
```

- `position` is the pool bounding box; size it to enclose the activities' `position` values.
- `horizontal: 0` stacks lanes top to bottom (the usual UPN layout).
- Each lane's `mxKey` must be unique across every element type in the level.

---

## map.json

Three fields, all editable:

```json
{"name": "...", "description": "...", "type": "upn"}
```

- `name`: 2–60 characters. XSS-sanitized on import (HTML stripped).
- `description`: max 5000 characters. XSS-sanitized on import.
- `type`: `"upn"` for process maps; `"architecture"` for architecture/interaction diagrams. Must match the subtype family of the level files.

Diagram-level `name` and `description` (in level files) are also XSS-sanitized; avoid relying on HTML markup in these fields.

---

## Other Supported Features

**`footerText`**: optional string on an activity, displayed below the activity box. Include in the activity object to set it.

**`resourcesPerRow`**: optional integer on an activity, controls how many resource icons appear per row. Include to override the default layout.

**`headerData`**: diagram header and legend. The importer reads `color` (hex string) and `logo` (asset key) for the header, and `legendItems[]` for legend entries. Editable but preserve verbatim unless specifically changing the header.

**`interactions`**: message indicators anchored to flowlines. Fields: `flowlineMxKey`, `offset`, `description`. The `flowlineMxKey` must reference an existing flowline in the level.

**Cross-diagram connector links** (`flowline.connector.links`): re-attached automatically during import. Do not modify these manually; they reference old diagram IDs that the importer remaps internally.

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Duplicate mxKey | Scan ALL element types (activities + flowlines + swimlines + texts + notes + images) before assigning |
| Dangling flowline | When removing an activity, remove every flowline that references its mxKey |
| Missing child level | When adding a drilldown, create the corresponding `.N.json` child file |
| Wrong internal levelNumber | `1.5.json` must contain `"levelNumber": "1.5"` |
| Stale strippedText | After editing `text`, re-derive `strippedText` by stripping all HTML tags |
| Renumbering drilldown activity | Changing `number` on an activity that has a child level breaks the structural link |
| Removed `interactions` key | Keep `interactions: []` on a level with no interactions; deleting the key instead of emptying it breaks import |
