# System architecture conventions

How this plugin draws system landscapes and solution architectures in Elements, why, and what the Elements MCP write path can and cannot set. The style follows the Salesforce Well-Architected diagram framework (architect.salesforce.com/diagrams) and its reference diagrams. Every size below is in `data/style-architecture.csv` with the measurement behind it.

## 1. Two kinds of diagram, one map type

Both use create_map type `system_architecture`. Reads use type `architecture` and subtype `system_architecture`. The difference is in the model, not the drawing:

| | System landscape | Solution architecture |
|---|---|---|
| Question it answers | What systems do we run, and how are they connected? | How does this one solution work across systems? |
| Cards | Products and outside systems; components only when they matter | The solution's systems, with the components that do the work as attributes |
| Lines | The mechanism and timing ("Out of the box connector · batch") | Numbered steps ("3. Experience API · real-time") when the order matters |
| Typical size | 12-20 cards, groups for each org or product family | 6-12 cards |
| Well-Architected level | Level 1 (the big picture) | Levels 2-3 (a subset of products, key integration points and data flows) |

Well-Architected's rule for both: one message per diagram, read left to right and top to bottom, and a header that states the purpose, scope and message. The map's title and description are that header.

## 2. Where the cards go

The script places one **hub** in the centre: the system the diagram is about, marked `hub: true` in the model, otherwise the Salesforce or middleware system with the most integrations. Several hubs (MuleSoft above Data 360) stack in the centre column in model order. Every other card goes in one of four **zones**, from `data/architecture-zones.csv`:

| Zone | Holds | Default when |
|---|---|---|
| Left: Sources | Systems whose data flows into the hub | an outside app or data store that only sends, or exchanges both ways (a system of record) |
| Right: Destinations | Systems the hub sends data to | an outside app, data store, middleware or channel that only receives |
| Top: Engagement | Salesforce apps that use the hub's data | a Salesforce system that receives from the hub or exchanges both ways with it |
| Bottom: Ingestion | Apps and channels that feed the hub | a channel (web, mobile), a Salesforce app or a middleware (ETL) tool that only sends; a channel or middleware that exchanges both ways |

A card with no line to a hub joins the zone of the cards it is connected to (Slack beside the Sales and Service orgs). The model's `zone` overrides all of this; use it when the user wants a card somewhere else, as the Well-Architected landscape puts Marketing Cloud on the right as a destination though it is a Salesforce product.

Left and right zones are columns of up to 6 cards, centred on the hub, 340 px from it; a seventh starts a second column further out, its cards set level with the gaps of the column inside it so their lines to the hub pass between those cards. Top and bottom zones are rows centred on the hub, kept between the two side columns so their lines never cross a column; when a row is full, the next row sits further out, shifted by half a card so its lines pass between the cards of the first. Within a zone, cards joined to each other sit next to each other, and a card joined to two others sits between them.

A **Key** card sits at the top left: what an arrow means, the timing words used, and the card colours used. A **text box** names each zone at its outer edge ("Sources", "Destinations", "Engagement", "Ingestion"; "Systems of record", "Connected systems", "Channels and apps" when a zone mixes directions). Both can be switched off (`--no-key`, `--no-headings`) or changed in `data/style-architecture.csv` and `data/architecture-zone-headings.csv`.

## 3. Cards

A card is 200 px wide. Its parts:

| Part | Set through `manage_diagram` as | Holds |
|---|---|---|
| Header icon | `add resource` with `role: "header"` | The system's `icon`, else the first row of `data/system-icons.csv` matching its name and kind: the Salesforce product logos ("Data Cloud Logo", "Mulesoft Logo", "Sales Logo"...), "AWS", "Salesforce" |
| Title | the activity `text` | The system's `name` |
| Attributes | `add attribute` | The system's `attributes` (components or capabilities), at most 6 (the 6th sums up the rest); a group with none lists its members |
| Footer | the activity `footerText` | The system's `footer`, cut at 20 words (`footer_max_words`) and 200 characters, ending "…", so a long text does not stretch the card |
| Footer icons | `add resource` with `role: "footer"` | The system's `footerIcons`, else a group's members' logos; at most 3 |
| Fill and border | `fill`, `border` | Grey (fill `#DDE2E8`, border `#3E4A56`) for apps and data stores outside Salesforce; the theme for Salesforce, middleware and channels (`data/system-kinds.csv`) |

**Height.** The server sizes a card from what it holds: `60 + 26 × attributes`, plus 70 for footer text, 75 for footer icons, or 125 for both; at least 100 px. A header icon adds nothing. Three footer icons keep the card 200 px wide; each icon past three adds 54 px of width, which is why the drawing stops at three.

**Icons in the library.** `manage_diagram` refers to a resource by name, and the space's resource library decides which names exist, so it differs per space. The test space's library, for example, has the Salesforce product logos (`Commerce Logo`, `Data Cloud Logo`, `Experience Logo`, `Heroku Logo`, `Industries Logo`, `Marketing Logo`, `Mulesoft Logo`, `Platform Logo`, `Sales Logo`, `Service Logo`, `Slack Logo`, `Tableau Logo`) and a few vendor icons (`AWS`, `Salesforce`, `Stripe`, `DocuSign`, `JIRA`, `LinkedIn`, `Gmail`, `Google Drive`, `Excel`, `Email`, `Website`); it has none for Agentforce, Snowflake, Databricks, SAP, Oracle, Workday or ServiceNow. Each run's preflight dry run checks every icon before anything is written, and the user chooses per missing icon: a close match, no icon, or a new library name (a name without a picture until someone uploads one in Elements).

## 4. Lines

Every line is an integration, drawn from where the data starts (`from`) to where it arrives (`to`):

- **One-way**: no shape at the start, an arrow (`block_thin`) at the end: the system architecture default.
- **Two-way**: an arrow at both ends. `from` is the side that starts the exchange.

**Label**: the integration's `label`, else its `technology`, else its pattern's short name; then ` · ` and the timing word when `timing` is set; then `N. ` in front when `step` is set; then ` (inferred)` when the integration is inferred. The server wraps labels at about 20 characters (a read returns "real-time" as "real- time"; comparisons ignore spaces).

**Timing** (`data/integration-timing.csv`) replaces the clock icons of the Well-Architected landscapes, which a line cannot carry: *real-time* (the caller waits for the answer), *near real-time* (sent as it happens, no waiting), *batch* (moved in bulk on a schedule). The Key card explains the ones used.

**Sides.** A line between a card and the hub joins the card's side facing the hub and the hub's side facing the card (a left card: its right side into the hub's left). Cards next to each other in a column join bottom to top; in a row, side to side; cards further apart in one column or row join round the outside. Any other line takes the pair of sides whose likely route crosses no card and the fewest other lines. All lines join the middle of a side, so lines from one zone into the hub meet at one point: Elements cannot attach a line elsewhere.

**Merged lines.** Two integrations that lift onto the same two cards with the same label and direction (two members of a group fed the same way) are one line on that level; the drill-down shows both.

## 5. Groups and drill-downs

A system that other systems name as `parent` is a **group**: a Salesforce org, a product family, a platform. It is one card on its level (members listed as attributes, their logos as footer icons) with a drill-down level, as Well-Architected nests cards in a container. Groups are one level deep.

On the drill-down:

- each member is a card, stacked in one column, joined members next to each other;
- integrations between members are lines between their cards;
- each integration with the outside is a line from a free end into the member's left side (data coming in) or from the member's right side to a free end (data going out), linked by `parentLine` to the line on the level above. `add child` seeds one free-ended copy of each parent line; the drawing removes it and adds the line again attached to the member, because a seeded free end stays where the server put it and would bend the line;
- the label names the system at the other end: "Agentforce in Slack: Slack app", or "From Data 360 Home Org" when that with the mechanism would pass 40 characters (the server can shorten the free end; the mechanism is on the parent line).

## 6. Middleware between two systems

An integration whose model names a `via` passes through a middleware (Make between the org and Xero). How it is drawn depends on how many systems the middleware carries (the ends of its `via` integrations that are not a hub or a Salesforce system):

- **As a card** (the default, up to `middleware_fold_threshold` systems): two lines, the hub to the middleware and the middleware to the system. The hub's line is labelled with the mechanism (`technology`) and is shared by every integration through that middleware in the same direction; the system's line carries the integration's label. The carried systems sit in the middleware's zone.
- **As a label** (more systems than the threshold, or the system's `placement` is `label`): one line from the hub to each system, labelled "via Make: Invoices" (`via_label_format`). The middleware keeps a card only when it is an end of an integration of its own; the plan warns which middleware is drawn this way.

A middleware's `placement` (`card` or `label`) overrides the threshold.

## 7. A system's drill-down

When a model's integrations list the `automations` that carry them and the `objects` those touch (with `interactions` saying which automation reads, writes or runs on which object), each system on the top level gets a drill-down level, read left to right:

| Column | Cards |
|---|---|
| 1 | The system; for a middleware, the systems it carries |
| 2 | The middleware it is reached through; for a middleware, itself |
| 3 | The automations: a card each, its type's icon from `data/automation-types.csv` (`chain_resource`), its attributes, its summary as footer (cut at 20 words, as every footer), its metadata links |
| 4 | The objects, coloured by kind as on a data model (`data/entity-kinds.csv`), with the API name when it differs from the label, ordered so their lines cross as little as possible |

Lines join neighbouring columns and point the way the data moves: toward the system when it is the integration's destination, from an object into the automation that reads it or runs on it ("reads", "runs on"), from an automation into the object it writes ("writes"). The system-to-middleware line carries the integration's label; when there is no middleware, the system-to-automation lines carry it. A middleware's drill-down shows the systems it carries and the automations of its own integrations; the automations behind a carried system are on that system's drill-down. Empty columns are left out, so a system with no middleware has its automations next to it. The automations a system reaches directly sit at the top of their column with the system level with them, and each middleware sits level with its own automations below, so the system's direct lines never cross a middleware card. Within each group, the automations are drawn in the order that keeps each object's automations closest together, so automations that share an object sit next to each other. An automation's only object sits level with it; several objects only it uses stack around it, or on the side away from an object it shares; an object two automations next to each other use sits midway between them, the lower one moved down so it fits beside its neighbours; any other shared object sits as near the middle of its automations as the objects above it allow. Two exchanges between the same two cards are two lines on separate paths: the second joins the bottom of both cards (else the top), wherever that route crosses no card. On the top level a second line moves only when such a route stays short and uses no side another card's lines use; lines from a zone all meet the hub at one point, so a second line between a zone card and the hub usually keeps the first line's path. An exchange no automation carries joins the objects it names straight from the system or middleware, those objects sitting in the automations column, unless an automation on the level already shows the object; an exchange with neither automations nor objects (one inferred from a connected app) has no line on the drill-down and shows on the top level only.

`add child` seeds free-ended copies of the card's lines on the new level; the drill-down removes them and draws its own lines between cards, so it has no free ends and no `parentLine` links. Columns are `chain_col_gap` apart and cards `chain_stack_gap` apart; a level taller than the canvas is written in several passes. Above `max_cards_per_level` cards the plan warns.

## 8. What the drawing cannot do

- **Resize or nest.** `manage_diagram` sizes every card itself, so there are no containers, no stretched hub bars and no cards inside cards. Groups use drill-downs instead.
- **Attach a line anywhere but the middle of a side.** Lines into the hub converge at one point per side.
- **Route lines or place labels.** Elements chooses each line's bends between the two sides the plan sets and centres its label on it. Labels of lines that share a run can sit close together; keep technology names short.
- **Icons on lines.** Timing is a word in the label and the Key explains it.
- **Know the editor's card heights.** A card whose title, attributes or footer wrap may grow when opened in the editor; the layout keeps 30 px for that.
- **Canvas.** `manage_diagram` places a card only inside the canvas: 2000 × 1200 px on a blank level, then the content plus half its size on each side. A landscape is wider than that, so the plan writes it in two or three passes, centre first.
- **Amend drill-downs.** Amending changes the top level; a new group card gets its drill-down, an existing drill-down is left as it is. A system's drill-down of automations and objects is drawn new only.
- **Link a managed package.** Metadata links resolve by API name and type; a package itself has none, so a card links to the package's applications and permission sets instead.
