# Layout conventions: process maps and customer journeys

This is the house style the `draw-process-map` skill follows when it places boxes and lines. It has two sources:

- **The plugin's line rules** (section 4): which side of a box every line leaves and enters. They fit what `manage_diagram` can draw, which is a line attached at the middle of any side of a box.
- **The six exemplar maps** (56 levels, 345 boxes, 544 lines, every level read): spacing, grid, wording, starts and ends, journeys. Where the exemplars do something `manage_diagram` cannot reproduce, this file says so.

The numbers the layout script uses are in [`../../../data/style-process.csv`](../../../data/style-process.csv); the line rules in machine-readable form are in [`../../../data/line-sides.csv`](../../../data/line-sides.csv). Notation rules (what a box and a line mean, how to word them) are in [`upn-rules.md`](upn-rules.md). The exemplar levels, with their ids and measurements, are in [`exemplars.csv`](exemplars.csv).

## Contents

- Why the exemplars look good
- Words used here
- 1. The shape of a level
- 2. Grid and spacing
- 3. Order and numbering
- 4. Lines: which side they leave and enter
- 5. Labels
- 6. Starts and ends
- 7. Boxes
- 8. Customer journeys: what changes
- 9. What the MCP write path can and cannot set
- 10. Do not copy these
- 11. How this was measured
- Appendix: measurements by map

## Why the exemplars look good

A reader can follow the main path of an exemplar level without effort. Five habits produce that:

1. **One straight main path per row.** The steps that happen in the normal case run left to right along one row, and the lines between them are straight.
2. **A strict grid.** Boxes in a row line up, boxes in a column share their left edge, and the gaps are even.
3. **Lines leave and enter on the side facing where they go.** Forward lines go from the right side to the left side; a branch leaves from the bottom or top; a loop back goes over the row, never through it.
4. **Labels have room.** The gap between boxes is sized for the label of the line that crosses it.
5. **Everything off the main path has a fixed place.** Alternatives sit in the rows above and below, loops run over the row, starts are on the left, ends on the right, notes are in the margins.

## Words used here

| Term | Meaning |
|---|---|
| Level | One diagram page in a map. The top level is `1`; the page behind box 3 is `1.3`. |
| Box | An activity: one step, drawn as a rounded rectangle with a number, text and resources. |
| Resource | A role, system or object listed inside a box ("Sales Representative", "Opportunity"). |
| Line | A flowline: an arrow from one box to another, labelled with the outcome that triggers the next step. |
| Happy path | The sequence of steps in the normal, expected case. |
| Decision box | A box with two or more outgoing lines, each a different outcome. |
| Side | The edge of a box a line leaves (`fromSide`) or enters (`toSide`): top, bottom, left or right. `manage_diagram` attaches a line at the middle of the side. |
| Free end | A line end not attached to a box: where a level starts or finishes. |
| End marker | A terminator: a small filled circle at a free end, marking a start trigger or an end state. |
| Connector | An off-page marker at a free end that links to a line on another diagram (a hand-over between processes). |
| Stub | The short line between a free end and its box. |
| Drill-down | A child level behind a box, showing how that step is done. |
| Canvas | The area in which `manage_diagram` accepts positions; `get_diagram` with `include: ["layout"]` and `delivery: "file"` with selected teamId returns it. |
| Tidy | The server's automatic arrangement (`manage_diagram` op `tidy`, also applied when boxes are added to an empty level without positions). The skill places boxes itself instead. |

## 1. The shape of a level

The exemplars reuse a small set of arrangements. Each item names a level that shows it.

1. **Main path row.** Every level has one, starting at the left (Sales `1`, Revenue `1`, every journey level). The skill puts the happy path on the main row.
2. **Rows above and below for alternatives.** The skill puts a decision's second outcome in the row above and its third in the row below, one column to the right (section 4). The exemplars mostly put alternatives below their source: "Nurture leads" under "Qualify and convert leads" (Sales `1`).
3. **Row wrap.** When the main path has more than six steps it continues on a second row, starting again at the left (Revenue `1`: 7 + 7 boxes; Service `1.4`; Sales `1.6`). Prefer moving steps into a drill-down; wrap only when the level needs the steps.
4. **Continuous management bar.** An ongoing activity that oversees the whole process ("Monitor and report on sales forecast") is one box along the bottom, with the emphasis border (section 7), its output looping back to the first box (Sales `1`, Service `1`). `manage_diagram` cannot widen a box, so the layout script places it as an ordinary box, by its lines like any other step.
5. **Set-up box above the flow.** Configuration that feeds the process sits above the main row with a line down into the step it enables (Revenue `1.2`, "Configure Advanced Approvals", numbered 99 so it stays out of the sequence).
6. **Supporting processes.** Activities that run alongside the main process but not in sequence form a separate group below it, each with its own start and end, under a text heading (Automotive `1`: "Manage Fleets", "Plan visits and audits at the dealerships").
7. **Several entry paths.** When a level can start in more than one way, the start boxes are stacked in the first column, each fed from the left (Service `1.2`: five ways a case arrives).
8. **Swimlanes for scenarios, not roles.** Only one of 56 levels has swimlanes, and they separate two ways of reaching the same outcome (Service `1.2`). Roles are never lanes: who does a step is a resource on its box. `manage_diagram` cannot draw swimlanes.
9. **Notes in the margins.** Sticky notes (78 across the exemplars) sit above the main row, at the left edge or at the right edge, never on the grid. The layout script puts a model's level notes (`levelNotes`) above and to the left of the box they belong to, 30 px clear of it, and moves them on when that spot touches a box, a line or a start or end label (`level_note_spot` in `scripts/layout_engine/geometry.py`).

## 2. Grid and spacing

| What | Exemplars | Use | Why |
|---|---|---|---|
| Box width | One width per level, 120–205 px; journeys always 160 | 150 (fixed by the server) | Boxes created through `manage_diagram` are always 150 px wide. |
| Box height | 80 + 24 px per resource in 315 of 345 boxes | 100 + 24 px per resource (server) | Height is predictable, so the layout script can place rows before writing. |
| Gap between boxes in a row | Median 181 px (middle half 165–196) | 180 (process), 160 (journey) | The gap holds the line's label: about 20 characters a line, roughly 125 px. |
| Distance between box left edges | Median 330–365 px | 330 | 150 + 180. |
| Gap between rows | Median 140 px (middle half 107–192) | 140 below the tallest box of the row | Room for loop-back lines over a row, their labels, and lines to the rows above and below. |
| Row alignment | Tops of boxes in a row line up | Same middle | Lines attach at the middle of a side, so boxes that share their middle keep happy-path lines straight. Boxes of different heights then show uneven tops and bottoms; that is the price of straight lines. |
| Column alignment | Left edges in a column line up | Same left edge | Keeps the grid. |
| Boxes per row | Rows wrap after 6–7 boxes | At most 6 | Six columns (6 × 330 = 1,980 px) fit the 2,000 px canvas of a blank level (section 9). |
| Boxes per level | Child levels 2–11 (median 6); top levels 5–14 | At most 10 | The server warns above 10 (`upn_level_too_many_activities`); the Elements UPN guide says no more than 12 on screen. |
| Clear space around free ends | Stubs of about 160 px | Keep 260 px clear left of a first box and right of a last box, and 140 px above or below a box with an early end | The house style draws start and end lines 240 px long (120 px from a top or bottom). The server still draws them 80 px (40 px), so the space stays clear for the longer line. |

## 3. Order and numbering

- **Numbers follow reading order,** column by column: the main-path box, then any box above or below it in the same column, then the next column. Most exemplar levels number this way (Sales `1`: 1 above 2, 3 above 4).
- **Numbers are drill-down addresses.** Box 3 on level `1` owns level `1.3`. A box that has a child level is never renumbered.
- **Numbers outside the sequence are allowed** for a box that is not a step in the flow (the set-up box numbered 99 in Revenue `1.2`).

## 4. Lines: which side they leave and enter

Every line is drawn with `fromSide` and `toSide` set; [`line-sides.csv`](../../../data/line-sides.csv) has the same rules with ids L01–L13.

**The three core rules**

1. **Happy path:** leave the source from the middle of its right side, enter the target at the middle of its left side.
2. **Loop back to an earlier step** (rework, retry, correction): leave from the middle of the top, enter the earlier box at the middle of its top. The line runs over the row.
3. **Decision with several outcomes:** each outcome leaves from a different side, in this order: right, top, bottom.
   - A loop back always takes the top. On a decision box that has one, the other outcomes use right, then bottom.
   - A fourth or later outcome reuses the side facing its target. UPN reads two lines leaving one point as parallel paths, not alternatives, so the skill warns that a decision with more than three outcomes is worth splitting.

**Where the targets go**

| Outcome | Leaves from | Target is placed | Enters at |
|---|---|---|---|
| Happy path, first outcome | Right | Same row, next column | Left |
| Second outcome | Top | Row above, next column | Left |
| Third outcome (or second when a loop back has the top) | Bottom | Row below, next column | Left |
| Loop back | Top | Earlier in the sequence | Top |

Keep the cell directly above a box with a top outcome, and directly below a box with a bottom outcome, empty: the line runs through it.

**The cases the core rules don't name**

| Case | Leaves from | Enters at | Why |
|---|---|---|---|
| An alternative path rejoins the main path at a later box, from a lower row | Right | Bottom | It enters at a different point from the main path, which UPN reads as "either path starts this step". |
| The same, from an upper row | Right | Top | As above. Do not also bring a loop back into that box: both would enter its top middle. |
| One outcome starts two or more steps at once (parallel paths) | Right, all from the same point | Left | UPN reads lines leaving one point as parallel. Their first segment is shared, so their identical labels overlap. |
| A step that may start only when every incoming path has finished | (by the source's rule) | Left, all at the same point | UPN reads lines entering one point as "all must arrive". |
| Start of a level (start marker or free start; child-level inputs seeded by `add child`) | — | Left | Same direction as the happy path. |
| End of a level (end marker, free end or hand-over; child-level outputs) | Right | — | As above. |
| An early end (opportunity closed lost) or a customer leaving a journey | By the decision order (usually top or bottom) | — | It is one of the decision's outcomes. |

**A box's sides at a glance:** left takes the main path in; right sends the main path (and parallel paths) out; top carries loops back, the second outcome, and rejoins from above; bottom carries the third outcome and rejoins from below.

**What the exemplars do.** The exemplar editor attaches lines anywhere along a side, so its maps can go further: two lines between the same pair of boxes use different points, forward lines run at the same height on boxes of different sizes, and loops get explicit corners. 224 of 227 forward lines in the exemplars go right side to left side, 9 of 9 lines to a box directly below go bottom to top, and 13 of 18 loops within a row run over or under it.

## 5. Labels

- **Every line has a label** (519 of 544 in the exemplars). The server warns about an unlabelled line (`upn_line_unlabelled`).
- **A label is an outcome, written as a completed state:** "Lead converted to opportunity in status 'Qualification'". Name the record change that proves it where there is one: "Opportunity moved to 'Needs Analysis'". Wording rules are in [`upn-rules.md`](upn-rules.md).
- **The server lays the label out.** It wraps the text at about 20 characters and centres it on the line; line breaks sent in the label are not kept, and its position cannot be set.
- **Keep labels short.** At most about 100 characters (five wrapped lines); exemplar labels have a median of 49–88 characters by map. A label on a line to or from a free end sits on an 80 px stub, so keep it under about 40 characters, or it overlaps the box edge.
- **The gap fits the label.** A wrapped label line is about 125 px wide (20 characters × 6.2 px), inside the 180 px gap.

## 6. Starts and ends

- **A level starts on the left.** The line enters the first box at its left middle. In the exemplars this is a connector when the trigger is another process's output (52 of 93 inputs), an end marker when it is an event from outside the process (26), and a plain free end otherwise (15). `manage_diagram` can draw an end marker or a free end, not a connector.
- **A level ends on the right.** The line leaves the last box from its right middle: an end marker for an end state ("Opportunity marked as closed won"), a free end for a hand-over.
- **Where the server puts them.** The plan requests the configured free-end placement. Server clear-space and collision rules can select another side or shorten the stub; read the returned geometry and keep that region clear (section 2).
- **Child levels.** `manage_diagram` op `add child` creates the child level with one line per parent line in and out, both ends free, each linked by `parentLine` and carrying the parent's label. The skill attaches the inputs to the first boxes (left side) and the outputs to the last (right side), so the boundary matches the parent.

## 7. Boxes

- **Text** is a verb and its object, 2–6 words (median 4 in the exemplars). Journey boxes are written in the customer's voice: "Search for solutions related to my problem".
- **Resources.** Typically two or three per box. The person or team doing the step comes first (340 of 343 exemplar boxes with resources), then the objects and systems used. RASCI letters go only on people. A generated box shows at most five (`max_resources_shown`); when there are more, the objects keep two places and the first person stays. No box, whatever skill draws or amends it, carries more than seven, people included (`max_resources_on_box` in `data/style-process.csv`, Xavery's rule): what is left off is named in a `WARN` for the report.
- **Emphasis.** A dark navy border (`#051e56`) on a white fill marks boxes that are not ordinary steps: continuous management, exception handling ("Mark opportunity as closed lost"), set-up. Nine of 345 exemplar boxes. `manage_diagram` sets the colours; the exemplars' 2 px border and hidden number need the editor.
- **Drill-downs.** 50 exemplar boxes have a child level. On top levels almost every box drills down.

## 8. Customer journeys: what changes

- **The top level is the stages.** Five or six stage boxes in one row, left to right (B2C: explore, consider, decide, await delivery, engage after purchase; B2B: explore, try and acquire, adopt, renew, expand, advocate). Each stage drills down to its touchpoints.
- **The journey loops.** A loop back from the last stage to the first: "Customer remains loyal and advocates for the brand". By rule 2 it leaves the last stage's top and enters the first stage's top.
- **Every box starts with the Customer resource** (Human, 68 of 68 exemplar journey boxes), then the channels the customer uses, mostly as System resources: Website, Email, Social Media, Knowledge Center, Product / Application.
- **Drop-offs are decision outcomes.** Where a customer leaves the journey, the line goes to an end marker, labelled with why: "Customer decides our company is not the right fit". In the exemplars these leave from the top (22 of 39 journey outputs), which the decision order gives them as the second outcome.
- **Touchpoint levels may have several entry paths** stacked in the first column.
- **Spacing is slightly tighter** (gap 160 px).
- **Journey maps use their own theme**, set by the map type `customer_journey`.
- The Elements article on journey diagrams adds: name stages consistently, keep their number manageable, record the customer's emotions and expectations at each stage (a note attachment works), and use drill-downs rather than crowding a stage.

## 9. What the MCP write path can and cannot set

Probe maps establish what `manage_diagram` can set, `fromSide` and `toSide` included (section 11 describes the probes).

| Aspect | `manage_diagram` | Export, edit, import |
|---|---|---|
| Box position | Yes: top-left corner, whole pixels, inside the canvas | Yes |
| Box size | No: 150 px wide, 100 + 24 px per resource tall | Yes |
| Which boxes a line joins | Yes | Yes |
| Line sides | fromSide/toSide choose side middles. Omission uses server routing; read returned layout | Yes |
| A point along a side | No | Yes |
| Corners (waypoints) | No: the editor routes the line between its two sides | Yes |
| Label position | No: centred on the line | Yes |
| Label line breaks | No: the server wraps at about 20 characters | Yes |
| Free-end and end-marker position | The plan requests its configured length; clear-space and collision rules can change the side or distance. Read actual geometry | Yes |
| Colours | Fill and border colour | Full style, including border width and hiding the number |
| Notes | Text and position (yellow only). Every note is drawn 150 × 150 px whatever its text, and loses its line breaks | Colour, size, rotation |
| Swimlanes | No | Yes |
| Tidy | Lays boxes left to right by their lines, with 80 px gaps and rows not aligned | Not applicable |

**The canvas limits a single write.** On a blank level the canvas is 2,000 × 1,200 px from (0, 0). Once a level has content, the canvas is the content's bounding box plus half its width and height on each side. A position outside it is refused (`position_out_of_bounds`). A row of seven boxes at 330 px spacing (2,310 px) cannot be placed on a blank level in one call: place up to six columns first, or write in two passes.

**The write path.** The skill draws through `manage_diagram` only, with the line rules in section 4; the right-hand column shows what the export, edit and import route adds (tested on the polished probe). Beyond `manage_diagram`, further improvements could add label position, a point along a side, and corners.

**Known side effects of drawing at side middles:**

- Parallel lines share their first segment, and their identical labels overlap.
- A fourth decision outcome shares a side with another line; if it ends at an end marker, the marker lands on that line's path.
- Long start/end labels can overlap a box on short returned stubs; check their actual geometry.
- Untested in the editor: how it routes a top-to-top loop over several boxes, a row wrap, and two loops over the same row.

**Server behaviour the script handles** (from the end-to-end runs in section 11):

- **The space's resource library decides which names a write accepts.** A role or system the library lacks is refused (`resource_not_found`, with close matches), and a name the library holds as a system or capability is refused with RASCI letters (`rasci_not_human`). Both block the whole batch. The script therefore starts every run with a preflight: dry runs that add every distinct resource and library attachment of the map to throwaway boxes, before anything is saved. Library matching ignores case. A name the library holds under another type is accepted with a warning (`resource_type_differs`), and the box shows the library's type: a test space holds Contact and User as people. The close matches in a `resource_not_found` message carry no type, so a second dry run adds each one to learn it. An object whose name the library holds under another type is renamed in a copy of the model without asking: to its API name when that differs and the library does not hold it under another type too (Partner to Partner__c), otherwise to "<name> (object)" (Contact to Contact (object)), which is added to the library as an Object. The report names each such rename.
- **A box must fit inside the canvas, and it grows 24 px per resource.** On a blank level (1,200 px tall) a box with about 45 resources leaves the canvas and is refused (`position_out_of_bounds`). The preflight puts at most 25 resources on each throwaway box, side by side.
- **A change adds at most 10 new names to the library** (`too_large`, "11 new library resources, limit 10"), dry runs included. The run adds missing Object resources by default (and every missing name with `--create-resources`) first, 10 per change on a throwaway box on the top level, then removes the boxes; the names stay in the library. The preflight itself never sends `createResources`.
- **A picklist value or record type attachment resolves by its bare name within the selected reference model.** `manage_diagram` finds a Custom Value or Record Type by `apiName`, `metadataType` and the attachment's selected `refModelId`: a value named "New" exists on many fields, so it is refused as `metadata_ambiguous`, and paths such as "Lead.Status.New" are `metadata_not_found`. A picklist value of a standard value set (Opportunity Stage, Lead Status, Case Status) can remain ambiguous within that model, because the value exists on the value set and again on the field. The preflight therefore does not block on these two types: the write batches leave such attachments out and the step lists them as `unlinkable`. Report them to the person with the value's `nodeId` from the model; the box is not given the field or its objects instead.
- **Some libraries hold objects under their API name** (Pricebook2, not Price Book), and some hold both. The preflight also tries each object's API name; when only the API name is there, the entity is renamed in a copy of the model (`--apply-renames`) rather than the label added as a second name.
- **Seeded boundary lines are replaced, preserving parentLine.** The script removes each seeded line and adds a new line with the same label and parentLine in the same change. It requests the configured free end and checks the returned route; the server can select a clear side or shorten the stub.
- **Two parent lines can share a label** (a box handing the same output to two boxes). `add child` seeds one line for each, both with that label, and the child level usually has one END line with it. Matching seeds by label alone would leave the second seeded line unattached. The script pairs seeds with START and END lines in order and draws any extra parent line as a copy of the level's last line with that label, over it, so every parent line has its continuation.
- **Link addresses read back HTML-escaped:** `&` comes back as `&amp;`, on generated and hand-made maps alike. Compare addresses after decoding.
- **The server wraps labels by inserting line breaks**, at about 20 characters and also after a hyphen or a bracket. A read returns each break as a space, so "hands-on" reads back as "hands- on" and "(inferred)" as "( inferred)". Compare read labels with every space removed.

## 10. Do not copy these

The exemplars are good but not perfect. The drawing skill does not reproduce:

- **Overlapping boxes.** Sales `1.1` places two boxes on top of "Set up campaign content".
- **Child boundaries that do not match the parent.** Only 48 of 131 parent lines have a child line with the same label: the templates were built by copying, without `parentLine` links. Drawn levels link every boundary line.
- **Top levels over 10 boxes** (Sales 11, Service `1.4` 11, Automotive 13, Revenue 14). Move the overflow into drill-downs.
- **Alternatives converging on one point.** Five "prospect not interested" lines entering "Mark opportunity as closed lost" at one point (Sales `1.5`) read in UPN as "all five must happen".
- **Unlabelled lines** (25 of 544).
- **Mixed capitalisation in box text** ("Define Warranty Terms" next to "Record asset relationships"). Use sentence case.

## 11. How this was measured

- **Exemplars.** Every level of the six maps was read with `get_diagram` (`include: ["layout"]` and `delivery: "file"` with selected teamId) and exported with `export_diagram`; the two agree on every box position. The export adds what `get_diagram` does not model: exact attachment points, corners, free-end positions, label positions and line breaks, notes, styles and swimlanes. The per-level numbers are in [`exemplars.csv`](exemplars.csv); the measuring scripts are not part of the plugin.
- **Probes.** Probe maps were used to establish what `manage_diagram` can set; they are not listed here.

## Appendix: measurements by map

| Map | Levels | Boxes | Lines | Box widths (px) | Median gap in a row (px) | Median gap between rows (px) |
|---|---|---|---|---|---|---|
| Business Process (Sales Cloud) | 12 | 86 | 130 | 120–171 | 181 | 140 |
| Business Process (Service Cloud) | 7 | 50 | 89 | 130–162 | 170 | 107 |
| Business Process (Automotive) | 14 | 88 | 116 | 150–192 | 187 | 168 |
| Business Process (Revenue Cloud Legacy) | 10 | 53 | 74 | 144–205 | 186 | 216 |
| B2C E-Commerce Customer Journey Map | 6 | 29 | 59 | 160 | 140 | 104 |
| B2B SaaS Customer Journey Map Template | 7 | 39 | 76 | 160 | 186 | 138 |
| **All** | **56** | **345** | **544** | | **181** | **140** |

Wide management bars (1,120 and 1,810 px) and the one 220 px container-like box are left out of the width ranges.
