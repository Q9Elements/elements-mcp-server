# Capability map conventions

How `scripts/layout_capability.py` draws a capability map, and why. Written for the person who has to explain a drawing or change the house style; the numbers live in `data/style-capability.csv` and the colours in `data/capability-ratings.csv`, so change them there, not here.

## 1. What a capability map shows

A business capability map shows **what the organisation can do** (Sell, Service, Bill, Analyse), independent of who does it or how. Each capability breaks down into sub-capabilities. Architects use it to line business goals up with technology: which capabilities matter for a goal, which are weak, and what supports them.

The Elements team's hand-made exemplars (the Change Intelligence capability assessment and the Salesforce Customer 360 template) draw sub-capabilities as boxes inside bigger boxes. The drawing skill cannot draw a box around other boxes (section 4), so it keeps the exemplars' grid and turns every grouping box into a **heading**:

```
BUSINESS DRIVERS
[Driver 1]   [Driver 2]   [Driver 3]   [Driver 4]   [Driver 5]       the goals the map serves

 ASSESSMENT    OPERATIONAL      CONFIGURATION    IMPACT              top-level capabilities: headings
[Advanced]     KNOWLEDGE        KNOWLEDGE        ASSESSMENT          in capitals over their column
[Interm.]     [Card]           [Card]            Technical impact    a group: a sub-heading
[Under.]      [Card]            Metadata          [Card]             with its cards under it
[Missing]      Business process  dictionary       [Card]
               [Card]           [Card]
               [Card]           [Card]

[Band card]  [Band card]                                             foundation layers below the grid
```

Every card in a column shares one left edge, so the map reads as a clean grid, and the headings carry the structure.

## 2. Where each model item goes

| Model item | Drawn as |
|---|---|
| `drivers` | A row of cards under a "BUSINESS DRIVERS" heading at the top, one per grid column. A driver's `description` is the card's footer. |
| Top-level capability with sub-capabilities drawn as cards | A heading in capitals, centred over its column. |
| Second-level capability with sub-capabilities drawn as cards (a **group**) | A sub-heading in its own case, centred in the column, with its cards under it. |
| Any capability with no sub-capabilities, or whose sub-capabilities are list lines | A card. At the top level it is a category card: navy border, light tint, its `description` as the footer (like the Customer 360 template's category boxes). |
| Order in a column | The cards that sit straight under the top-level heading come first, then each group in model order, so a card is never read as part of the group above it. |
| Fourth-level capability | A list line (card attribute) on its third-level card. |
| Anything deeper | Not drawn; the plan lists it as a gap and the validator warns (R05). |
| `childrenAs: list` | That capability's sub-capabilities are list lines on its card, so it is a card rather than a heading. `--children-as list` makes this the default for every lowest level. |
| Top-level capability with `placement: band` | Below the grid. A band whose sub-capabilities are cards is a heading over a row of them; a band that is a card shares a row with the other card bands of its `bandRow` (like Data and Einstein Trust Layer in the template). |
| `rating` | The card's fill colour from the rating scale, with a legend of the whole scale in a column left of the grid under the scale's title. A heading or a list line cannot take a colour; the plan warns. |
| `icon` | The card's header icon: a resource of that name from the space library. A heading cannot carry one; an icon the library lacks is left out and reported. |
| `inferred: true` | A note attachment titled Inferred on the card, holding the evidence. A heading cannot carry it; the plan warns. |
| `description` | On a top-level card or a driver, the footer; on a card below the top level, a note attachment titled Description. A heading cannot show it; the plan warns, naming the headings. |
| `attachments` | Attachments on the card: metadata (with the selected `refModelId`), stories, links and notes. Not on headings (the plan warns). |
| `realisedBy` | Not drawn. It links the capability to the processes, entities and systems other diagrams show. |

## 3. Sizes and spacing

Every number below is a row of `data/style-capability.csv`.

- **Cards.** Elements makes every card on a capability map 200 px wide. Its height follows its content: 130 px with a footer plus 26 px per list line; without a footer, 60 px plus 26 px per list line and at least 100 px, so it stays 100 px until its second list line. The title does not make a card taller, so the plan warns at 60 characters; the footer does not either, so it warns at 120.
- **Headings.** A text box is always 120 x 80 px. Its text is 14 px, centred across and down the box, wraps at about 104 px and is cut after about four lines; it cannot be bold or bigger. A heading is centred over its 200 px column (40 px in). The first card under it starts 4 px below the box, which leaves about 30 px between the text and the card. Top-level headings are in capitals when every word is 13 letters or fewer (CONFIGURATION is 116 px, INTERDEPENDENCIES would not fit); a word over 17 letters does not fit at all, and the plan warns.
- **Columns.** 200 px of card and a 40 px gap: 240 px. Headings in a row share their top; six columns fit in a row before the rest wrap to a new row.
- **Stacks.** 10 px between cards, 16 px before a sub-heading (its text box adds about 25 px of space above its text). A column holds eight cards or groups before the rest continue in the next column, split so the stacks are about the same height (the plan warns).
- **Rows.** 50 px between the drivers row, the rows of the grid and the band rows.
- **Legend.** Shown only when at least one card is coloured: one swatch card per value of the scale, in a column 60 px left of the grid, under a heading with the scale's title, level with the first grid row.

## 4. Why headings rather than boxes

The exemplars nest boxes: a column box holds group boxes, which hold capability boxes.

`manage_diagram`, which draws everything on the level, cannot size anything it creates: every card is 200 px wide with a height set by its footer and list lines, and every text box is 120 x 80 px (the `evidence` column of `data/style-capability.csv` records the measurements). A parent therefore cannot be drawn around its children, and indenting the children under a parent card reads as a staircase. Headings keep the structure readable instead:

- the **column** says which top-level capability a card belongs to;
- the **heading** over it names that capability, in capitals;
- a **sub-heading** names a group, and the cards under it up to the next sub-heading are its members;
- all cards share one left edge, so nothing looks out of place.

Nothing overlaps, so the order things are created in does not matter for how they stack; the script creates them top to bottom so each batch fills the canvas from the top.

What a heading gives up: a text box has no fill, border, footer, icon or attachments, so a capability that groups others cannot show its rating, description, icon, attachments or Inferred note. The plan lists each one.

## 5. How the writes go

- A blank level accepts positions inside 2000 x 1200 px; once it has content, the canvas grows with it, and `next` takes its size from the level read after each batch. `next` sends the cards and headings that fit the current canvas (at most 100 changes per call), reads the level, and sends the rest.
- Every batch is dry-run first. The dry run catches header icons the space library lacks (left out and reported) and positions the canvas refuses (tried again in a later batch).
- Once everything is on the level, a read-back compares each position with the layout computed from the sizes Elements reports, and moves any that differ. With the measured sizes in the style file there is normally nothing to move.

## 6. Changing the style

- Spacing, heading case, the category card colours and the drivers heading: `data/style-capability.csv`.
- Rating scales and colours: `data/capability-ratings.csv`. Add a scale by adding rows with a new `scale` name; `order` sets the legend order. Fills should stay light enough for dark text.
- After a change, plan `examples/change-intelligence-capabilities.json` to compare its `preview.svg` with the exemplar.

## 7. Known limits

- No grouping boxes (section 4); a heading cannot show a rating, description, icon or attachment.
- A band is one card wide or a row of cards, not one full-width box.
- Card titles and footers are not measured: a long one can crowd its card. Headings over about 50 characters are cut.
- Headings are the theme's text colour (blue) and size; the Elements editor's dark theme also darkens light fills, though the rating colours still read apart.
- One level only, with no drill-downs and no links to process maps, data models or architecture diagrams (`realisedBy` is not drawn).
