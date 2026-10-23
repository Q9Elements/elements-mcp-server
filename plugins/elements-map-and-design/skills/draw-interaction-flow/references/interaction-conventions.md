# Interaction flow conventions

How this plugin draws interaction flows in Elements, and what the Elements MCP write path can and cannot set. The measurements come from probe maps in a test space; `data/style-interaction.csv` holds each value with its evidence.

## 1. Levels

| Level | Cards | Lines | Laid out |
|---|---|---|---|
| **Chain** (top level of a map with several automations or with interactions) | One per automation, plus each object, platform event, system or role an interaction names. `trace-automation-chain` names an object or event only where several automations meet (a hub) | Numbered: "3. Updates Invoice/Credit Note" | Left to right, wrapping after 5 cards |
| **Logic** (one per automation: the child level of its chain card, or the top level when there is one automation) | One per step | The order the steps run in, outcomes labelled | Left to right, wrapping after 5 cards |
| **Drill-down** inside logic (a loop's body) | One per step of the body | As on a logic level | The same |

A map with one automation and no interactions draws that automation's logic on its top level. Any other map has the chain on top and one child level per automation with steps.

## 2. Cards

A card is 200 px wide. Its parts:

| Part | Set through `manage_diagram` as | Holds |
|---|---|---|
| Header icon | `add resource` with `role: "header"` | Chain level: `chain_resource` of the automation's type in `data/automation-types.csv` (Apex, Flow or Workflow). Logic level: `resource` of the step's element in `data/automation-elements.csv`. Object, event, system and role cards have none |
| Title | the activity `text` | The `name` of the automation, step, object, system or role |
| Attributes | `add attribute` with `title` and `description` | At most 6 (the 6th sums up the rest); titles cut at 60 characters, the full text in the description. An object or event card has one: "Object: Invoice__c" or "Platform event: Calculate_Commission__e" |
| Footer | the activity `footerText` | The automation's or step's `summary` (another card's `description`), cut at 250 characters |
| Fill and border | `fill`, `border` | Object and platform event cards on the chain level only: `#DCEBFA` fill, `#2A4D8D` border |

**Height.** The server sizes a card from what it holds and ignores line wrapping: `60 + 26 × attributes + 70 with a footer`, at least 100 px (2/3/4/6/8 attributes give 112/138/164/216/268; a footer of any length adds 70). The layout uses exactly that, so the cards in a row share their middle and the lines between them are straight. Cards made in the editor are taller (210–256 px for three attributes and a long footer), so the editor may grow a card whose text wraps; `row_gap` (160 px) leaves room for it. Long titles, attributes and footers are what make a card grow: keep them short.

**Header icons are standard Elements resources.** Elements ships Flow, Apex, Workflow, Automation and Action, and every Salesforce flow element (Start, Screen, Get Records, Create Records, Update Records, Delete Records, Roll Back Records, Assignment, Decision, Collection Filter, Collection Sort, Loop, Pause, Wait, Send email, Custom Error, Add Prompt Instructions), as standard resources of type Flow, each with its own icon. `data/automation-types.csv` and `data/automation-elements.csv` name them with type Flow, and the drawing uses them as they are: it never adds a header icon to the space's resource library, `--create-resources` included, because an icon added that way is a custom resource that hides the standard one.

`manage_diagram` matches a resource by name only; sending `type` changes nothing. When a space's library also holds a custom resource of the same name (in an Elements test space: Flow, Apex, Workflow, Automation and Assignment, as Industry), `manage_diagram` puts the custom one on the card and warns `resource_type_differs` ("Flow is Industry in the space library, not Flow; that one is used"). The preflight dry run finds these before anything is written and stops (`fix-preflight`, `standardIcons.shadowed`). The fix is in the space: remove the custom entries from its resource library in Elements, and the standard ones are used. A user who wants to draw anyway plans with `--allow-custom-icons`.

Not standard, and not drawn as header icons: Subflow, Process Builder, Transform, Post to Chatter, Platform Event, Apex Trigger, OmniScript, Integration Procedure, Validation Rule, Email Alert, Outbound Message (`resource_not_found` in a test space). A subflow step uses Flow, Process Builder uses Flow, triggers and classes use Apex, the other rule types use Workflow.

## 3. Lines

The line rules are the process map's (`data/line-sides.csv`, [process map layout conventions](../../draw-process-map/references/layout-conventions.md)): the first-listed line out of a card is the main path, right side to left side; other outcomes leave the top, then the bottom; a line back to an earlier card loops over the top. Three differences:

- **A fault path leaves the bottom** when the bottom is free, not the top. The top is where a wrapped main path runs back, and a failure reads naturally below the step that failed.
- **A card that a line loops back into keeps its own outcomes off the top**, for the same reason: on the chain level, an automation that updates the hub object it was started from loops back into the hub's top, so the hub's second outcome leaves the bottom.
- **Lines meeting at one point carry no "all must arrive" meaning.** UPN reads several lines into one point that way; an interaction flow does not, so the drawing does not warn about it.

**Inferred lines.** An inferred line's label ends "(inferred)", as on process maps, except on a level where every line of the logic is inferred (an automation rebuilt from Elements without its definition). There the suffix would sit on every label and make each one wrap, so no label carries it; instead the level's first card gets one note titled `Inferred` saying every line on the level is inferred. Each card's own `Inferred` note still gives its evidence. Chain lines continued on the level keep their own marking.

New lines get the interaction flow default ends: no shape at the start, `block_thin` at the end. Lines seeded by `add child` have `classic` ends; the drawing replaces them (section 4), so every line has the same ends.

## 4. Drill-downs and boundary lines

`add child` works on interaction flow cards: the child level is an interaction flow too, seeded with free-ended copies of the card's lines in and out, each linked by `parentLine`. As on process maps, the drawing removes each seeded line and adds it again with the same label and `parentLine`, attached to the right card:

- On an automation's logic level, each chain line into its card enters the Start card; each chain line out leaves the step that causes it (the interaction's `fromStep`, else the last step of the main path, with a warning). A plain end line from that same step is dropped, so the step does not get two ways out.
- When that step sits inside a loop body, the chain line leaves the Loop card on the logic level and, inside the body, the step itself, with the same label; the two are linked like any boundary line. When the `fromStep` is a card with a drill-down, inside it the line leaves the drill-down's last step (with a warning: name the step itself).
- On a loop body, the line in reads "For each item" and the lines back to the Loop card "Next item"; the Loop card's own line on reads "After last item". The body's lines are linked to the Loop card's by position rather than by label: on interaction flow levels, a parent line left without a same-labelled line is linked to the first free line from START (or to END).
- A decision with many outcomes may have them in a drill-down: one START line per outcome, labelled with it, and an unlabelled END line from each branch. One START and one END are linked to the Decision card's lines; the others start and end at plain terminators.

## 5. What the drawing cannot do

- Start and end lines use server routing and can be shortened or use another clear side; inspect returned layout; the layout check (rubric row R15) keeps 260 px clear for them beside a card and 140 px above or below. Long labels on them overlap the card: the plan warns past 40 characters.
- `manage_diagram` places a card only inside the canvas: 2000 × 1200 px on a blank level, then the bounding box of what is written plus half its size on each side. The plan centres each level on the blank canvas; a level taller or wider than it (three decision outcomes stacked above and below a wrapped row, say) is anchored to an edge instead, whichever placement lets every card be written in the fewest writes. A level no placement fits is refused: split it.
- Labels sit centred on their lines and wrap at about 20 characters.
- The editor chooses each line's route between the two sides the plan sets.
- Card heights grow in the editor when text wraps (section 2); the layout cannot know by how much.

A future MCP (Model Context Protocol) server release may lift these limits: `type` choosing between same-named resources (or the standard resource preferred), the card height the editor will render, start and end line length, and label position.
