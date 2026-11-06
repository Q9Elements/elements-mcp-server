# Data model conventions

How `scripts/layout_data_model.py` draws an Elements data model, and why. Written for the person who has to explain a drawing or change the house style; the numbers live in `data/style-data-model.csv`, the colours in `data/entity-kinds.csv` and the line ends in `data/relationship-ends.csv` and `data/er-line-ends.csv`, so change them there, not here.

## 1. What a data model shows

A data model (an entity-relationship diagram) shows what data the business keeps and how the pieces relate: an Account has many Contacts, an Opportunity has many products, every Invoice Line belongs to exactly one Invoice. Architects use it to agree on a design, to explain an org to someone new, and to see what a change to one object touches.

```
                 ┌──────────────┐
                 │ Account      │  card: object name
                 │ # Account Nm │  key fields; # marks the field that identifies the record
                 │ Type         │
                 └──────┬───────┘
          o|            │ o|            ||          one end, at the parent
    ┌───────────────────┼──────────────────┐
    o<                  o<                 o<       many end, at the child
┌────────┐  o|    o< ┌────────┐       ┌───────────┐
│ Case   │◄──────────│ Contact│       │ Invoice   │
└────────┘           └────────┘       │ Invoice__c│  footer: API name, when it differs
                                      └───────────┘
```

## 2. Where each model item goes

| Model item | Drawn as |
|---|---|
| Entity | A card titled with its `name`, coloured by its `kind` (`data/entity-kinds.csv`: grey standard, purple custom, white external, amber proposed). |
| `apiName` | The card's footer, when it differs from the name (`Invoice__c` under "Invoice"; not "Account" under "Account"). |
| Fields | Attributes on the card, six by default (`--max-fields` at the plan): the identifying field (`key: primary`, written `# Account Name`), required fields, relationship fields (`key: foreign`), then the rest. Each attribute's description is the field type, plus "required" and "inferred" where they apply. Fields beyond that number are named in the plan's warnings, not drawn. |
| Relationship | One line from the "one" end to the "many" end, so a `many-to-one` relationship is drawn the other way round. Its `label`, when it has one; two lines between the same two cards get their field name as label so they can be told apart. An inferred relationship's label ends "(inferred)". |
| `fromEnd`, `toEnd`, `cardinality`, `kind` | The symbols at the two ends of the line (section 3). |
| Entity `attachments`, `inferred` | Attachments on the card; an inferred entity gets a note attachment titled Inferred. |
| The model as a whole | A Key card left of the diagram lists the colours and line ends used. |

## 3. Line ends

Each end of a line says how many records at that card relate to one record at the other card:

| End | Symbol | Elements shape | Reads |
|---|---|---|---|
| `zero-or-one` | o\| | `er_zero_to_one` | at most one, may be missing (an optional lookup) |
| `exactly-one` | \|\| | `er_mand_one` | exactly one (a master-detail parent, a required lookup) |
| `one` | \| | `er_one` | one, without saying whether it may be missing |
| `zero-or-many` | o< | `er_zero_to_many` | any number, including none (the usual child end) |
| `one-or-many` | \|< | `er_one_to_many` | at least one |
| `many` | < | `er_many` | many, without saying whether there must be one |
| `none` | (none) | `none` | no symbol: a plain line end |

Defaults (`data/relationship-ends.csv`): every relationship is drawn zero-or-one at the parent and zero-or-many at the child, which is also what Elements gives a new line on a data model. A master-detail parent is exactly-one instead (a detail record cannot exist without its master). When a model is built from the org, a required lookup is also exactly-one at the parent. A relationship's own `fromEnd` and `toEnd` override the defaults, and that is how a user's "make that end mandatory" becomes a change: set the end in the model and amend the diagram.

`manage_diagram` sets any of these ends on either end of a line.

## 4. Layout

The layout follows the hand-made data models in the exemplar folder (nine maps from the Salesforce industry clouds): cards on a grid, parents above children, a hub object at the top of its group, lines short and square.

- **Parents above children.** Every object is placed under one parent: its master-detail parent when it has one, otherwise the parent nearest the top (the hub). So Case, which looks up to Account and to Contact, sits next to Contact under Account, joined to Contact by a short line across, instead of a row further down with a long line from Account.
- **Rows.** Children sit in a row under their parent, tops aligned, 80 px apart, and the parent is centred over them. The lines leave the parent's bottom and fan out to the children's tops like an organisation chart. Each row starts 160 px below the bottom of the tallest card in the row above (130 px plus 30 px in case the editor grows a card whose text wraps).
- **Neighbours stay together.** Children related to each other are placed side by side in a chain (Contract, then Order, then Invoice), and children whose other lines lead left or right are moved that way, so lines between them are short.
- **Many children.** A parent with more than seven children keeps the ones that have children of their own in the row below and stacks the others in a column beside itself (right first, then left, up to eight each), each joined to the parent's side. This is how the exemplars draw Route and Residential Loan Application.
- **Groups and bands.** Objects with no parent in the diagram start groups; groups sit side by side, 160 px apart, the biggest first and then the ones most connected to what is already placed. When the groups would run wider than 3,400 px the next group starts a band below.
- **Other lines.** A line that is not parent-to-child in the layout (Account to Case above, Product to Asset) takes the pair of sides whose route crosses no card, does not run along another line, crosses few lines and is short. Elements draws each line as a square route through the middle of the gap between the two cards, and the script predicts that route the same way, so what `preview.svg` shows is what Elements draws.
- **Self relationships** (Parent Account) are a small loop at one corner of the card; a second one on the same card takes another corner.

## 5. Why it is written with manage_diagram, and what that costs

`manage_diagram` is the one write path that can also amend a diagram later: add a card, a field or a line, change a line end, move cards, without touching anything else on the level. A new map and an amendment are therefore drawn the same way. `manage_diagram` decides some things itself:

- **Card size.** Every card is 200 px wide. Its height is 60 px plus 26 px per attribute plus 70 px for a footer, never less than 100 px (measured on a probe map). Elements does not allow for text that wraps, so the editor may grow a card when it is opened; the 30 px allowance between rows covers a line or so.
- **Line ends join the middle of a side.** A line leaves and enters at the middle of a top, bottom, left or right side. Several lines into one side therefore meet at one point; the script spreads lines over sides where it can (it costs a line 400 points to share a side another line uses).
- **The canvas.** Positions are accepted only inside the canvas: 2000 x 1200 px from (0, 0) on a new map, then the content plus half its width and height on each side. The plan centres the layout on the blank canvas and writes the cards in as many batches as the canvas needs to grow around them.
- **One label per line**, centred. The exemplars' small role labels at each end ("parent of", "child of") cannot be written.

What the exemplars do that `manage_diagram` cannot write, so this drawing does not do: a hub stretched into a long bar so every child line drops straight onto it (Account, Financial Account, Tour), lines attached anywhere along a side, the API name as a small second title line, and nested record-type boxes inside an object.

## 6. Amending

`from-diagram` reads a drawn data model back into a model file: card titles become entity names, attributes fields (`# ` marks the primary field), footers API names, card colours kinds (when they match `data/entity-kinds.csv`), and line end shapes become `fromEnd` and `toEnd`, with the cardinality worked out from which end is many. The user's change is made in that file; `amend` then compares it with the diagram:

- **Matching.** A card matches the entity with the same name, or whose API name is the card's text or footer. A line matches a relationship between the same two cards, in either direction; two lines between the same cards are paired by label. Fields match by title.
- **Changes** are written in place: new fields at their place in the order, descriptions and footers updated, line ends and labels updated (on a line drawn the other way round, the start and end shapes are swapped to match), colours updated when the model gives a kind.
- **New cards** go into the nearest free space next to the card they relate to (below it, then beside it), inside the current canvas, and their lines take sides as in section 4.
- **Nothing is removed unless asked.** A card, field or line the model no longer has is listed as kept; `--allow-remove` removes them, after the user has confirmed. The Key card is the drawing's own and is updated to match the colours and ends now used.
- **Tidy.** `--relayout` lays the whole model out again and moves every card there, keeping each card's key, attachments and anything else on it, and re-routes every line.

A card grows when fields are added and never shrinks. When a grown card would overlap the one below, the plan warns and suggests `--relayout`.

## 7. Changing the style

- Spacing, card sizing, how many fields, row and column limits: `data/style-data-model.csv`.
- Colours and the Key's wording: `data/entity-kinds.csv`.
- Default line ends per cardinality and kind: `data/relationship-ends.csv`; the end names, shapes and meanings: `data/er-line-ends.csv`.
- Fields never shown when building from the org: `data/system-fields.csv`.
- After a change, plan the example into a scratch folder and look at its `preview.svg`: `python3 scripts/layout_data_model.py plan examples/sales-service-data-model.json --workdir SCRATCH`.
