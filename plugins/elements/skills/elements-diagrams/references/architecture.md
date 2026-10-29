# Architecture diagrams

Read and change architecture cards and lines with `get_diagram` and `manage_diagram`.
Use the [diagram type table](diagram-types.md) for subtype spellings and preserve stored values in ZIP archives.
Cards and lines are under `diagram.activities` and `diagram.lines`; follow [result handling](../SKILL.md#read-tool-results) and the [one-level workflow](change-one-level.md).

## The card

An architecture card is an activity with more parts than a process step:
- **title**: the activity `text`;
- **attributes**: rows on the card, in order, each with a `key`, a `title` and an optional `description`;
- **footer text**: a short description under the attributes (`footerText`);
- **resources**: at most one is the **header icon** (`role: "header"`), drawn next to the title; the others are **footer icons** (`role: "footer"`), drawn in rows at the bottom. A resource with `hidden: true` is not drawn.

`get_diagram` returns these on architecture levels only, and each line's `startShape` and `endShape`. A line stored with no shapes reads `none` → `classic`, as the editor draws it. Container cards stay read only, under `diagram.unmodelled`.

## Salesforce diagram conventions

Follow these when drawing or extending architecture levels. Change what the user asked for; suggest other changes.

- **System architecture**: one card per system or platform (Sales Cloud, MuleSoft, an enterprise resource planning (ERP) system). The header icon is the
  system's resource; the footer says in one line what the system does here; attributes hold the facts that matter for
  the design (edition, owner, integration pattern). A line says which system calls or feeds which, labelled with what
  flows ("orders", "nightly sync"); its default end is an arrow at the receiver.
- **Data model**: one card per object, titled with its name. Each attribute is a field: the title is the field name,
  the description its type or meaning. A line is a relationship, labelled with its kind ("lookup", "master-detail"),
  and its ends show cardinality in crow's-foot notation: a new line goes zero or one → zero or many, from the parent
  object to the child.
- **Interaction flow**: cards for the people, systems and services that take part; a line per message or call, in
  the order they happen, labelled with the message; the default end is an arrow.
- **Business capability map**: one card per capability, titled with what the business can do (a noun phrase, "Quote
  management"); attributes for sub-capabilities or measures; the footer for its scope.
- **Agent interaction**: cards for the agent, the user and the systems it uses; the footer states the agent's job; a
  line per request or answer, with a classic arrow.
- **Resource assignments**: follow the [one-level issue actions](change-one-level.md#issue-actions), including `rasci_not_human` on non-Human resources.

## Changes

Attributes are addressed by the card key and the attribute `key` from `get_diagram`. A new attribute gets the card's
highest attribute key + 1, as in the editor, and never a key the same change removes; a key freed by a removal can
come back in a later change, so read the card again before one. `position` is 1-based; left out on an add, the attribute goes last. Each attribute is one change item;
split large diagrams using the [change limits](change-one-level.md#six-steps).

```json
{"diagramId": "aaaaaaaaaaaaaaaaaaaa0320", "baseVersion": 7, "dryRun": true, "changes": [
  {"op": "add", "kind": "attribute", "activity": 12, "title": "Annual revenue", "description": "Currency", "position": 2},
  {"op": "update", "kind": "attribute", "activity": 12, "key": 3, "title": "Industry", "position": 1},
  {"op": "remove", "kind": "attribute", "activity": 12, "key": 5},
  {"op": "update", "kind": "activity", "key": 12, "footerText": "Customer record"},
  {"op": "add", "kind": "resource", "activity": 12, "name": "Sales Cloud", "role": "header"},
  {"op": "add", "kind": "activity", "ref": "opp", "text": "Opportunity", "footerText": "Deals in progress", "after": 12},
  {"op": "add", "kind": "attribute", "activity": "opp", "title": "Amount"},
  {"op": "add", "kind": "line", "from": {"activity": 12}, "to": {"activity": "opp"}, "label": "lookup"},
  {"op": "update", "kind": "line", "key": 20, "endShape": "er_one_to_many"}
]}
```

- **Attributes and footer text are plain text.** A title or footer that is rewritten loses the formatting it had;
  Text sent as it reads is left alone. `footerText: ""` clears the footer. A description is one line: the save turns a line break into a space. Limits, counted as the save stores the text: an attribute title 2,000 characters, a description 400, a footer 1,000.

### `text_too_long` and card fit

Shorten text using stored-text costs: `&` counts as 5, `<`/`>` as 4, no-break space as 6; footer line breaks count as 4 and description double quotes as 6 (other quotes as 1). Cards grow to fit, as in the editor: new cards start at 200 x 100 pixels (agent interaction 400 x 120). Minimum height is 60 plus 26 per attribute, 50 for a footer, 55 for the first footer-icon row, 50 for each additional row, and 20 margin when a footer/icon exists. Icons widen a card by 54 per icon that does not fit, only when icons change. Cards keep any greater size and never shrink. Titles are not measured, so shorten overflowing titles.

### Header and line changes
- **One header per card.** `role: "header"` on a resource add or update makes it the header icon; the one before
  becomes a footer icon, with warning `header_replaced`. `role: "footer"` on the header leaves the card with no header.
- **Line ends.** `startShape` and `endShape` set the arrowheads and take the tool values below (`describe_diagram_schema`
  lists them); the editor's labels and ZIP `flForm.start`/`flForm.end` spellings are separate. A new line without them gets the diagram type's default; changing a shape keeps the line's route and
  label. Which side of a card a line attaches to is a different input, `fromSide` and `toSide`, as on any diagram
  ([line sides](change-one-level.md#layout-and-colour)).

| Tool value | The editor's name |
|---|---|
| `none` | None |
| `block_thin` | Full arrow |
| `classic` | Classic arrow |
| `diamond` | Diamond |
| `er_zero_to_one` | Zero or one |
| `er_mand_one` | Mandatory one |
| `er_one` | One |
| `er_zero_to_many` | Zero or many |
| `er_many` | Many |
| `er_one_to_many` | One or many |

| Diagram type | A new line's ends |
|---|---|
| System architecture, interaction flow, capability | `none` → `block_thin` |
| Data model | `er_zero_to_one` → `er_zero_to_many` |
| Agent interaction | `none` → `classic` |

- **Removals.** Removing an attribute removes only it, counts toward `confirm` like other removals, and is asked
  first: use the removal confirmation in [the one-level workflow](change-one-level.md#six-steps).

Issue codes: `attribute_not_found` means no attribute with that key on the card; read it again. Attributes, footer text, roles and line shapes on other types return `invalid_input`. Architecture diagrams skip Universal Process Notation (UPN) warnings from [upn-modelling.md](upn-modelling.md). ZIP import writes the supplied content: maintain these rules manually there.
