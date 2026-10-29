# The Manufacturing Cloud exemplar

The hand-made map this skill learns from, and the golden model it is compared with. Read on 18 October 2026, every level with `get_diagram` (layout and attachments).

- Map: "Business Process (Manufacturing Cloud)", `6acf8cd5eee7bbb95ed909a2`; top level `6acf8cd6eee7bbb95ed909a5`.
- Golden model: [`../../../examples/manufacturing-cloud.json`](../../../examples/manufacturing-cloud.json), every box and line transcribed, each activity with a `diagramRef` back to its box. It passes `validate.py --for process`, and `draw-process-map` can draw it to recreate the map (`layout_process.py plan` on it gives 11 levels and only label-length and wrap warnings).
- Sources the map was made from: the Data Model Gallery's Manufacturing category (`https://developer.salesforce.com/docs/platform/data-models/guide/manufacturing-cloud-category.html`) for the capabilities, and the Manufacturing Cloud developer guide's Standard Objects (`https://developer.salesforce.com/docs/atlas.en-us.mfg_api_devguide.meta/mfg_api_devguide/mfg_api_overview.htm`) for the objects.

## How it was made

By hand with ChatGPT and ElementsGPT, in eight steps. The skill does each step as follows.

| Manual step | Who and with what | Output | In this skill |
|---|---|---|---|
| 1. Explain the top-level process | ChatGPT, from the data model | Objects grouped by capability; the high-level process of using them, step by step | Inventory, capability grouping, top-level writer |
| 2. Capture the top-level process | ElementsGPT | Top-level diagram | Model built; drawn by `draw-process-map` |
| 3. Refine the top-level process | Diagram app | Distinct, verifiable, unique outcome per step | Articulation rules, `check_coverage.py` C05 and C09 |
| 4. Explain the use of a capability | ChatGPT | How to use *all* objects of one capability, step by step | One child-level writer per capability; C02 checks every object is used |
| 5. Capture the detailed capability process | ElementsGPT | Child diagram | Model built; drawn by `draw-process-map` |
| 6. Refine the child process | Diagram app | Distinct, verifiable outcomes | As step 3 |
| 7. Sanity check | Diagram app | All levels self-reviewed; Salesforce help links attached | `validate.py`, `check_coverage.py`, help links on top-level boxes |
| 8. Review the diagram | Author (R), VP Product and an industry expert (C) | Map approved by experts; back to step 6 when it needs changes | The person and their experts, after drawing |

The prompt used in steps 1 and 4:

> I want to have an articulation of a business process that explains when and how to use each object. The format of each step should be: What happens, why, desired outcome, objects used, role responsible for execution, followed by: [name of next step]. The trigger for the entire process is outcome from [previous step name] which is '[...]'

The level outline keeps exactly these fields: `what`, `why`, `next[].outcome`, `uses` (the objects), `roles`, `next[].to`, and the level's `starts`.

## What the map looks like

- **Top level:** 10 boxes, one per capability. Eight form the main chain, from product information through warranty terms, sales agreements, targets, forecasting, inventory and warranty claims to partner visits, which loops back to the start. Two more, fleets and manufacturing programs, sit under a "Supporting processes" heading, each with its own start and end. Each box has exactly one person (the capability owner) and one link, "How to? (Salesforce help)", to the capability's help article. No objects on top-level boxes (the skill shows each capability's main records there, so a reader sees at first sight what the box works on).
- **Child levels:** one per top-level box, 3 to 10 boxes (median 7). 68 boxes in all. Each box has one person (59) or two (9), then the objects it uses as Object resources: one object on 34 boxes, two on 22, three on 8, four or five on 3, none on 1. 92 objects in all.
- **Boxes:** verb first, 4 words at the median on child levels.
- **Starts:** most child levels chain to the next child level with off-page connectors; some levels have extra outside triggers ("Product request raised", "Change in business condition") with a note asking for the linked process to be documented.
- **Decisions:** only two levels have them: the customer reviews of agreements and contracts in Sales Agreements, and forecast adjustments in Advanced Account Forecasting. Everything else is a straight sequence.

## How the capabilities map to the vendor's grouping

| Top-level box | Data Model Gallery guide |
|---|---|
| Create product and asset information | none: the map groups Product, Catalog, Category, Price Book, Business Brand, Asset and its participants and milestones here |
| Define and manage warranty terms | Warranty Terms |
| Establish and maintain sales agreements | Sales Agreements |
| Set and track sales goals for account managers | Account Manager Target |
| Predict future sales | Advanced Account Forecast |
| Track and manage inventory levels | Inventory |
| Submit, process and manage warranty claims | Warranty Claims |
| Track and organize customer and partner engagements | Visits |
| Manage fleets of assets | Fleets |
| Create and manage manufacturing programs | Program Based Business & Advanced Account Forecasting (its forecasting objects are already in "Predict future sales") |

The gallery also holds four Manufacturing guides the map does not show: Channel Partner Inventory Tracking, Product Service Campaign Management, Warranty Supplier Recovery, and Warranty Supplier Recovery Plus Vehicle. A run on the gallery finds 13 guides plus the core product and asset objects, more than ten boxes, so the grouper merges some (the two supplier recovery guides into one, partner inventory into inventory) or adds areas.

Guides list shared objects too (Account, Contact, Product, User, Period, Location); the map uses them where a step needs them and never gives them a step of their own. That is why hubs are shared rather than owned.

## Keep

- One box per capability on the top level, with one owner and a help link.
- Every capability object used on its child level; one to three objects per box.
- Set-up objects first (terms, templates, sets, codes), then the main record, its lines and junctions, then events, then the numbers derived from them.
- The main chain looping back; supporting capabilities beside it with their own start and end.
- A note on every box explaining each object it uses (the skill's "About this step" note; the hand-made map has an "Objects used" note on one box).

## Do not copy

- **Benefit-style outcome labels** (28 of 101 labels): "Clear warranty terms, leading to increased customer trust and satisfaction." Write the state that proves the step is done.
- **Long labels:** 23 labels exceed 100 characters (median 83, longest 165).
- **Long top-level box text:** 7 to 12 words ("Set and track sales goals for account managers based on sales agreements").
- **A persona per box:** 51 roles across 78 boxes, 32 of them used once ("Record Keeper", "Task Manager", "Template Designer"). Reuse a small set of roles.
- **Child levels whose starts and ends do not match their box:** the off-page connectors carry other text (level 1.1 ends with "All relevant stakeholders are identified …" where its box's output is "Accurate and up-to-date product information …"). The golden model sets them to the box's labels; the skill copies them.
- **An unlabelled line** (Sales Agreements: review back to products) and **a cut-off label** (Account Manager Targets: "… based on sales agreements and").
- **A box with no object** ("Generate Advanced Account Forecasts" in manufacturing programs) and **an object whose API name the reference does not list** (Advanced Account Forecast Formula).
- **Title Case box text** ("Define Warranty Terms"). Use sentence case.

## Comparing a run with the golden model

```bash
python3 "$SKILL/scripts/check_coverage.py" "$WORK/model.json" --inventory "$WORK/inventory.json" \
  --golden "$PLUGIN/examples/manufacturing-cloud.json"
```

It matches each golden capability to the generated capability owning most of the same objects, reports the share of the golden map's objects the generated steps also use, and lists the number of boxes per level for both. A good run matches every golden capability above about 60% object overlap, uses at least 90% of the golden objects, and keeps child levels within 3 to 10 boxes. It will not match labels or box text word for word, and should not.
