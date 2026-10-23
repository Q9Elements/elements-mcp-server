# Method notes

What the comparison rests on, and what the Elements tools can and cannot do for it.

## What "implemented" means here

A box of an approved design states what happens to what, and its outgoing lines state the outcome that proves it happened. A step is implemented when the org's metadata does or records each part: the object exists, the field the outcome sets has the values it needs, the automation runs on the right object and event and does what the box says. Names are a hint, never proof: the assessor reads the definition (Flow XML through the plugin's `flow_to_steps.py`, Apex source, rule XML), then dependency rows, then descriptions. Inactive, deleted and proposed components implement nothing.

The verdict is about one org, production or a sandbox, as Elements last synced it. A change made in Salesforce since the last sync is not seen; the report names the org.

## The roll-up

A box with a level beneath it is judged on its own links and on its children's verdicts by `data/rollup.csv`, deepest level first. Children that need no org support are left out of the count. A child not assessed keeps the parent from being green. Levels outside the scope (above it) are not judged.

## Links

- A link ties a box to one component in every org the space syncs: the `Account` object of production and of each sandbox is one linked thing. The diagram's read names one org's copy (`refModelId` and `nodeId` of the attachment), whichever org it was linked from, so the org compared is the analyst's choice at kickoff, never read off the links.
- A link naming another org's copy, or one Elements marks `unresolved` or `restricted`, is looked up in the org compared by its type and API name (`list_metadata_by_criteria`, one call per type, and per object for fields with `parent_object`; several `api_name eq` filters in one call are OR-combined, and `parent_object` narrows them). Found once: the check follows it to that org's copy. Not found, or only deleted: the component is missing in that org, and its box is judged without it. Found more than once: the link is left out and named.
- Boxes are linked to metadata with `manage_diagram` `add attachment` (`type: "metadata"`), by API name and type, with `metadataType` and the selected `refModelId` always given: an object's name alone also matches picklist values of the same name.
- A field is linked as `Object.Field`. Its object's API name comes from `get_metadata_component` with `detail: "full"` (sf.fullApiName or canonical identity/parentPath), joining the selected object inventory by API name; objectName is a display label and unresolved canonical owners are gaps.
- A picklist value cannot be linked on its own when a value set holds the same value (Elements answers `metadata_ambiguous` and offers no way to choose), so the field is linked and the values are named in the link's description.
- A record type links by its API name; when two objects have record types with the same API name, Elements refuses it and the refusal is listed in the report.
- Proposed nodes (`create_proposed_node`) cannot be attached to boxes.
- A refused link (`metadata_not_found`, `metadata_ambiguous`, `metadata_no_access`) is taken out of the write and listed; the comparison still uses it, as approved but not saved.

## Colours and notes

- `manage_diagram` sets a box's `fill`; when a box had no colour of its own, Elements also gives it a border. Both are saved before the first write and both are put back on reset (`null` returns a box to the theme).
- A note is drawn 150 pixels square whatever its text (`data/limits.csv` `note_size_px`), and the editor shows about 25 to 30 words of it at default zoom; the rest is cut off on the canvas. `manage_diagram` cannot size a note.
- Sticky notes are free notes on the level (Elements does not tie a note to a box). They go above the box, or below, right or left when that is taken. Each starts with "Design check:", and the legend with "Design check legend:", so a reset without the run's files still finds them. A reset never removes a note without that marker.
- A box recoloured by hand after the check is left as it is on reset, and named.
- Every write goes to the draft. When the map has a released version, the draft shows as changed until the colours are reset or the draft is released.

## Evidence the tools give

- `get_metadata_source` returns stored definitions for up to 5,000 nodes in one call; managed Apex answers `managed_code_hidden`, a custom field's row holds its whole object's XML (`xmlScope: "object"`), and standard objects and fields have none (`no_stored_definition`). A picklist field's values come from `list_metadata_by_criteria` on `Custom Value` rows of its object instead (`parentPath` ends in the field's API name; `nodeDetails.active`).
- An object's fields come from `list_metadata_by_criteria` on `Field` with `parent_object` (one object per call, and the filtered column must also be among the columns); it answers in part files, so a large object never passes through the conversation.
- `get_dependencies` `using` rows carry `read`, `write`, `triggerType` and `triggerAction`; `where_used` on an object or field lists the automations, layouts and reports that use it.
- `get_component_change_history` `change_logs` gives who changed a component and when; the newest entries go into the pack.
- An `explain_metadata_components` item can end `failed` (`generation_failed`), on some servers every item; the pack lists each failed or missing explanation as a gap, and the assessor works from definitions and dependency rows.
- `search_metadata` matches the start of each word of a name or API name, not descriptions: single words find things, a phrase only finds names that hold it whole, and an everyday word (sales, call) brings mostly noise. So round 1 searches the objects and single words a box names, and adds the fields of each object whose name is one of those words and the automations that use it; the matcher asks for a second round of words for a box whose candidates do not settle it.
