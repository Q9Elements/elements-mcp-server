---
name: draw-process-map
description: "Draws a validated model as an Elements business process map (UPN) or customer journey with every child level, through manage_diagram, then checks the result against the layout rules and the model. Called by the start skill or a reader once a model with activities exists. Not for working out what the process is, editing an existing map, or data models, capability maps or architecture diagrams."
user-invocable: false
---

# Draw a process map or customer journey

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

Input: a model file in the format of `schemas/ba-model.schema.json` with activities and flows. Output: a new draft map in the active Elements space, every level laid out by the house style, and a review verdict.

The layout is computed by a script, not by you: `scripts/layout_process.py` places the boxes, chooses the side every line leaves and enters (`data/line-sides.csv`), sizes the gaps (`data/style-process.csv`) and splits the writes into `manage_diagram` batches. Your job is to run it, carry each batch to Elements exactly as given, save what comes back, and report. To explain a warning, read [layout-conventions.md](references/layout-conventions.md): the house layout rules, measured from the exemplar levels in [exemplars.csv](references/exemplars.csv). For what boxes and lines mean, read [upn-rules.md](references/upn-rules.md).

Follow the plugin's [drawing protocol](../../references/drawing-protocol.md) with `<script>` = `scripts/layout_process.py`. This file adds only what is particular to process maps and journeys.

Paths: this file's folder holds `references/`; the plugin root is two levels up and holds `scripts/`, `data/`, `schemas/`, `agents/` and `references/`.

## 1. Choose the diagram type

**journey** when the user asks for a customer journey, or the activities are things the customer does, in the customer's voice, with stages. **process** otherwise. Ask when it is unclear. A journey needs a role named Customer on every activity; the plan warns where one is missing.

Validate with `--for process` or `--for journey` (protocol section 1). Work folder: the one the calling skill names (map-process-from-data-model passes `drawing.dir`), otherwise `<model name>-drawing/`.

## 2. Plan the layout

`python3 <plugin>/scripts/layout_process.py plan MODEL --type process --workdir DIR` (or `--type journey`), adding as needed:

- `--skip metadata` when the active space has no connected Salesforce org. When the preflight or a dry run reports `org_not_connected`, `metadata_not_found` or `metadata_no_access`, plan again with it (protocol section 4 says into which folder). `--skip` also takes `story`, `link` and `note`, comma separated.
- Objects are always drawn: each step's `uses` become Object (and System) resources after the people doing it, so a reader can see at first sight whether the step is right. On a box with more than five resources the objects keep two places (`USES_RESERVED`) and the first person always stays; what is left out is named in a `WARN`. Add `--no-uses` only when the user asks not to see them.
- Missing Object resources are added to the space's resource library without asking: their names come from the data model (the documentation or the Metadata Dictionary). `--no-create-objects` turns that off.
- `--create-resources` adds missing people and systems as well, only after the user has agreed to those names (see `preflight` below). Either way the run adds names before drawing, at most 10 per change.
- `--apply-renames` and `--accept-type-clashes` answer a `fix-preflight` step (section 3).

**Level notes.** A model may carry `levelNotes`: sticky notes that belong to a level as a whole rather than to one box, such as the usage note map-process-from-data-model writes on each lifecycle level (how many records the object or record type holds, and how recently they changed). The plan places each one beside its box (`near`; by default step 1, the box the level's first start line enters): above and to the left of it, 30 px clear, where the exemplar maps keep their notes. When that spot touches a box, a line or a start or end label, or is outside the canvas, it tries directly above, then below-left, below, and further left. The note goes into the same write as its box, so it uses that write's canvas. Its drawn text is the note's title as a first sentence followed by its text. `--skip note` leaves level notes out with the note attachments. A note that finds no free place is left out with a `WARN`, and so is a note over about 400 characters (the server draws every note 150 × 150 px).

What to tell the user about the plan: each level with its box and line counts from the summary, and each `WARN` line. `WARN` lines particular to process maps include a decision with more than three outcomes, lines that will overlap (including two parent lines with one label, drawn as one line on the child level), a level over 10 boxes, a main path that wraps onto a second row, a journey box without the Customer role, and a long label.

## 3. Write the map

The protocol's write loop, with these further actions:

| `action` | Do |
|---|---|
| `preflight` | Send `manage_diagram` with `arguments`, which hold `"dryRun": true`; send it only as a dry run. It adds every distinct role, system, object and library attachment once to throwaway boxes, and each object whose API name differs from its name also under that API name. Nothing is written. A step with `purpose` adds the close matches the first preflight offered, to learn the library type of each. |
| `fix-preflight` | The space cannot take part of the model. Follow `how`, then validate and plan again into the same folder: only the empty map exists so far, and the new plan reuses it. `renames` lists objects to rename to `libraryName`: the library holds them under their API name, or (`reason`) holds their name under another type, such as a person, so they take their API name, or `<name> (object)` (`suffixed`) when that does not help. Apply them without asking: plan again into the same folder with the same options and `--apply-renames`, which writes the renamed copy `<model>.renamed.json` beside the model, leaves the model as it is, validates the copy and plans from it. The copy is the model from then on, for the diagram-reviewer too. |
| `library-batch` | For missing Object resources, and for every missing name with `--create-resources`. Send `manage_diagram` with `arguments`: it adds the missing names listed in `names` (at most 10) on a throwaway box on the top level. Dry run first, as for `write-batch`. |
| `library-cleanup` | Send `manage_diagram` with `arguments`, which carry `"confirm": true`: it removes the throwaway boxes, and the names stay in the library. |

Errors particular to process maps:

- `resource_not_found` (the preflight finds these): the named roles or systems are not in the space's resource library (missing objects are added by `library-batch` and never listed). Show the user each name with its close matches and the type the library holds each under (`closeMatches`), and ask, per name, whether to use a close match or add the name to the library. Mark a match with `typeDiffers` as another type when offering it: the box would show that type's icon, a person for Human. Use a match by renaming the role or system in the model; add names by planning again with `--create-resources`.
- `typeClashes` (rare): objects whose name the library holds under another type and that none of the renames avoids (the API name, `<name> (object)`, `<name> (object, <API name>)`), so the box would show a person or a system. Ask the user, per object, to rename the entity in the model (the new name is added as an Object) or to draw it as the library holds it (plan again with `--accept-type-clashes`).
- `rasci_not_human`: the library holds that name as a system or capability, so it cannot carry R, A, S, C or I. Ask the user for a person's role name instead, or drop the letters in the model.
- `too_large` (more than 10 new library names in one change): the `library-batch` steps keep every change within that limit, so stop and show the issue.

Lines carry `fromSide` and `toSide`. Send them as given, even when the `manage_diagram` tool description in view does not list them: without them every line runs right-middle to left-middle.

## 4. Check and report

When a write step lists `unlinkable` attachments (picklist values or record types whose names are not unique in the org), it has left them out; name them in the report.

Check with the protocol (layout rubric rows R13–R17; `diagramType` `process` or `journey`). In the report, also list the names added to the library (the `resource_created` warnings of the `library-batch` results), the names the library holds under another type (the preflight's `resource_type_differs` warnings, such as a system the library holds as a person), and each entity renamed (`renamed` in the `done` step) with its reason. Name every `suffixed` rename so the person knows, for example, that "Contact (object)" is the Contact object, drawn under that name because the library holds Contact as a person.

What the drawing cannot do, for the report: start and end lines follow server routing, which can shorten the requested free end; check the returned layout, labels sit centred on their lines, and the editor chooses each line's route between the two sides the plan set. Section 9 of [layout-conventions.md](references/layout-conventions.md) has the detail.

When the model's `meta.author` is `map-process-from-data-model`, the run is not over: return to that skill and run its `scripts/status.py` on its work folder (the model's folder) before the final answer.
