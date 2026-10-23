# Change one level

## Contents

- [Six steps](#six-steps)
- [Change syntax](#change-syntax)
- [Layout and colour](#layout-and-colour)
- [Child levels](#child-levels)
- [Attachments](#attachments)
- [Issue actions](#issue-actions)
- [Save failures and access](#save-failures-and-access)
- [Boundaries](#boundaries)

Use `manage_diagram` for activities, resources, Responsible, Accountable, Supporting, Consulted and Informed (RASCI) assignments, lines, notes, text boxes, layout, level title and description. Child operations also create or populate a child level. Follow [SKILL.md](../SKILL.md#read-tool-results) for Model Context Protocol (MCP) result handling.

## Six steps

1. **Find the level when needed.** With only `mapId`, call `get_process_map_outline`. Its levels give number, title, parent level/activity, activity count, published/changed state and editor lock. A held lock means wait for the editor to leave edit mode, including when it is the user.
2. **Read the level.** Call `get_diagram` with `diagramId` and `delivery: "file"`; use [the copying branch](../SKILL.md#copying-template-branch) on running. Keep `version` and element keys. For layout changes, add `include: ["layout"]`: boxes under `diagram.activities`, `diagram.notes`, `diagram.texts` have pixel `x,y,w,h`; activities expose fill/border and `diagram.canvas` gives bounds.
3. **Write only the requested change.** Use the syntax and relevant sections below. A blank map from `create_map` returns `mapId`, `diagramId` and `version: 0`: add the whole diagram with no positions so the server lays it out. Apply [UPN rules](upn-modelling.md) or [architecture conventions](architecture.md).
4. **Dry run.** Send `dryRun: true`. Show `diff` (added, changed, removed) and `issues`; removed lines identify removals caused by their activity. Fix blocking `severity: "error"` issues and dry-run again until they pass. Use the action table below for warnings too.
5. **Confirm removals.** Name every element in `diff.removed`, and disappearing resources or attributes in `diff.changed`, before asking. Moving steps into a child counts as removal from this level. Above 5 removed elements or 30% of the level, `confirm_required` requires `confirm: true` after agreement. Each call allows 100 change items; a level allows 150 activities and 300 lines (`too_large`): split larger work.
6. **Apply the same change and `baseVersion` without `dryRun`.** Inspect `saved` and `issues`. `saved: false` plus `unchanged` means "already that way": same version, no new history, no retry. A dry run also has `saved: false`, so check context. `saved: true` returns the new `version`, `idMap` (refs to keys), `diff`, optional `children` and `diagramUrl`.

```text
- [ ] Find level if needed; read version, keys and requested detail
- [ ] Write the change using returned keys
- [ ] Dry-run; fix blocking issues and re-run until they pass
- [ ] Show diff/issues and confirm every removal or move
- [ ] Apply the same change and baseVersion
- [ ] Inspect saved/issues and report version or unchanged outcome
```

The history label is "AI agent on behalf of" the user (AI means artificial intelligence). A session records one snapshot before its first change. A change after the 30-minute history-session gap, or after another save such as an editor save, starts another entry.

## Change syntax

New elements get a `ref` that later items can use as `after`, a line's activity endpoint, or a resource's `activity`. Text is plain text. Line ends are `{"activity": 4}` (key or ref), `{"terminator": true}`, or `null` for free input/output. Read `describe_diagram_schema` for the JavaScript Object Notation (JSON) change format and issue codes.

Synthetic input with a fake 24-hex diagram identifier:

```json
{"diagramId": "aaaaaaaaaaaaaaaaaaaa0319", "baseVersion": 12, "dryRun": true, "changes": [
  {"op": "add", "kind": "activity", "ref": "approve", "text": "Approve proposal", "after": 4},
  {"op": "add", "kind": "resource", "activity": "approve", "name": "Sales Manager", "rasci": "A"},
  {"op": "add", "kind": "line", "from": {"activity": 4}, "to": {"activity": "approve"}, "label": "ready"},
  {"op": "update", "kind": "line", "key": 21, "from": {"activity": "approve"}},
  {"op": "remove", "kind": "note", "key": 30}
]}
```

Expected preview: `dryRun: true`, `saved: false`, version 12, additions for the step/line, a changed line 21 and removed note 30. A resource removal instead appears in its activity's `diff.changed`.

## Layout and colour

- Add/update activity, note or text box: `position: {"x": 640, "y": 120}`, whole pixels at the top-left inside canvas. Omit it to place an activity right of `after`, otherwise its incoming source. Server sizes boxes from text/resources. Leave 80 pixels beside and 40 above/below other boxes; `overlap` is a warning. Lines follow moved boxes.
- Activity line ends accept `fromSide`/`toSide`: `top`, `bottom`, `left`, `right`, at side centres. Omit for server routing. Non-activity ends get `line_side_unsupported`. On a new terminator/free line, the activity side also places its other end; on a stored line that end stays put. Changing one side keeps the other end and label; full reads return the sides.
- Default endpoint placement prefers clear unused points beside the box, then falls back beside it even if occupied/obstructed. Read back the layout. A moved default free end tries normal length beside, then below/above when halfway is blocked. Explicit sides retain their constraints.
- `fill`/`border`: hex `#RGB` or `#RRGGBB`, for example `"#FFA500"`; omitted preserves style. Read layout first and reuse exact stored spelling for a retained custom colour: `#ffa500` differs from `#FFA500`, and `#112233` from `#123`. Theme properties compare case-insensitively.
- Null fill/border selects theme colours. A box with no other own styling follows the theme and reads null; other own styling stays, with theme colour as hex. Theme title, footer and attribute styles stay outside custom box styling.
- Recolouring normalizes resource styles per type. This can make the first visible colour match save a normalization; an identical repeat can be unchanged.
- `{"op": "tidy", "keys": [3, 5, 8]}` arranges selected activities left to right by lines after the other changes, preserving canvas order. Omit `keys` for all activities; other elements stay put. A blank level receiving activities with no position or tidy is laid out as a tidy of all. Show moved boxes in the dry run.

## Child levels

`{"op": "add", "kind": "child", "activity": 4}` creates an empty child seeded with the step's inbound/outbound lines as linked boundary lines. `activity` takes a key or new ref; numbering uses the step's `number`. Fill it using returned `children[].diagramId`.

`{"op": "add", "kind": "child", "activities": [5, 6], "text": "Assess the request"}` moves those existing keys into a child behind a new step, like "Send to child" in the editor:

- Interior lines and lines to terminators, free ends or off-page links move with the steps.
- Crossing lines become child boundaries; this level retains copies with the same key/label to the new step, preserving links from other children.
- A moved boundary loses its `parentLine`. Another add/update targeting a moved step/crossing line gets `ref_unknown_key`.
- The preview shows removals and `drilldown: "new"`, a marker rather than an identifier. Ask before moving.

On a child, `parentLine` on a line add/update links its free input/output boundary to the same-direction parent line from `get_diagram.boundary`; null unlinks. Links survive renames.

`children` returns `activity`, `levelNumber`, `diagramId` and, for moves, `moved` keys. The diagram identifier is null during dry run or failed save read-back; `diff_predicted` directs discovery with `get_process_map_outline`.

Remove a step with a child only after agreement and with `confirmDrilldownRemoval: true` on its remove item, separately from call-level `confirm`. The child and descendants go to the recycle bin as a map of their own.

## Attachments

Find the reference model with `list_reference_models`, metadata with `search_metadata`, and story numbers with `list_stories`, following [paged discovery](map-generation.md#paged-discovery).

- Metadata: `{"op": "add", "kind": "attachment", "activity": 4, "type": "metadata", "apiName": "Account.Discount__c"}`. API means application programming interface. Fields use `Object.Field`, including managed-package fields without namespace prefix. Add `metadataType` for name collisions, `refModelId` for reference model collisions, optional `description` for the reason.
- Story: `type: "story"` with displayed `storyId`.
- Link: `type: "link"`, `title`, and `url` using Hypertext Transfer Protocol (HTTP) or its secure form (HTTPS), up to 1024 characters.
- Note: `type: "note"`, `title`, `text`. Link/note titles have 2–120 characters.
- Remove: `{"op": "remove", "kind": "attachment", "activity": 4, "type": "story", "key": 2}`, using type/key from the read's include result. Uniform Resource Locator (URL) library entries use `link`. Removal deletes the link only and needs agreement.

Attachments have no update operation: ask the user to edit them in Elements. Removing then adding produces a different attachment.

## Issue actions

| Action | Code | Meaning and next action |
|---|---|---|
| Fix and dry-run | `version_stale` | Read the level again and rebuild |
| Fix and dry-run | `position_out_of_bounds` | Pick a position inside canvas |
| Ask, then dry-run | `resource_not_found` | Use close matches; if none fits, obtain agreement for `createResources: true` and supply resource `type`; resource admin right required, at most 10 new resources per change |
| Fix and dry-run | `resource_invalid` | Choose a library-valid name |
| Tell user | `resource_created`, `resource_type_differs` | Save adds library entries, or uses the existing name's different type |
| Fix and dry-run | `metadata_not_found`, `metadata_ambiguous` | Use candidates' type/path/refModelId to disambiguate |
| Tell user | `org_not_connected`, `metadata_no_access` | No synced org, or no edit/manage access to its reference model |
| Fix and dry-run | `story_not_found`, `story_ambiguous` | Resolve the intended displayed story number |
| Tell user | `not_licensed` | Preserve the returned server message verbatim; if its meaning is unclear, suggest contacting the Elements representative |
| Tell user | `attachment_duplicate`, `attachment_groups_missing` | Already attached, or space lacks All group so attachment shows in edit mode only |
| Tell user before removal | `attachments_deleted` | Removed step's attachments/links are deleted permanently |
| Fix and dry-run | `drilldown_exists`, `child_not_allowed` | Existing child/linked diagram, or subtype cannot create its own child type |
| Ask user | `drilldown_child`, `drilldown_removed` | Obtain child-removal agreement; explain recycle-bin outcome |
| Ask user | `offpage_linked` | Leave the step/line out or have its link removed in editor first |
| Fix and dry-run | `parent_line_invalid` | Check child level, parent, free end and matching parent direction |
| Fix or tell user | `boundary_unmatched` | Link/relabel unmatched boundaries or explain the warning |
| Fix and dry-run | `rasci_not_human` | RASCI letters belong on Human resources only |
| Fix or tell user | `upn_*` | Follow [UPN warnings](upn-modelling.md) or explain retained warnings |
| Fix or tell user | `attribute_not_found`, `header_replaced` | Follow [architecture rules](architecture.md) |
| Ask user | `theme_colour_unsupported` | Blocking stored-theme colour, including resource colours: show message, ask for recolouring in editor; dry run has issues, apply returns `validation_failed` with issues |

## Save failures and access

| Code | Next action |
|---|---|
| `lock_held` | Ask editor to leave edit mode or wait for another save; dry run uses `being_edited` warning |
| `version_conflict` | Read again and rebuild |
| `validation_failed` | Nothing saved; fix issues |
| `save_failed` | Read again: message can report removed attachments, changed metadata/story links or a created child despite no diagram save |
| `partial_save` | Read again before any further operation |
| `server_busy` | Another change/create/import/export runs; follow shared pacing rule |
| `rate_limited` | Saves allow 20 changes per minute, including `create_map` and template copies; wait and batch small edits |
| `access_denied` | Diagram: `Requires edit access to diagram <diagramId>.` Top header: `The top level's title and description are the map's; changing them needs the manage role on the map.` |
| `not_found` | Diagram/map is gone or invisible; read messages are in [read refusals](map-generation.md#read-and-create-refusals) |
| `invalid_input` | Fix malformed change, architecture-only item on another type, or released-only level (`This diagram has no draft to change.`) |

A timeout may still save: read before retrying.

## Boundaries

Not changed here: box sizes, fonts and other styling, swimlanes, images, requirements and other attachment kinds, moving notes/text boxes into children, or linking an existing level as a drill-down. Read requirements using [include kinds](map-generation.md#reading-an-existing-diagram). An off-page-linked line cannot be removed alone or with its step; an off-page end cannot be rerouted, but can be relabelled.
