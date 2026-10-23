# Writing a system architecture model

How to turn what the user gives you (a description in chat, a solution design document, a picture of a diagram) into the `systems` and `integrations` of a model in `schemas/ba-model.schema.json`. The drawing script does the layout; the model decides what is true. Two examples in the plugin's `examples/` folder show the result: [`data-360-aws-landscape.json`](../../../examples/data-360-aws-landscape.json) (a landscape with groups) and [`mulesoft-data-360-solution.json`](../../../examples/mulesoft-data-360-solution.json) (a solution with two hubs and numbered steps), both redrawn from Salesforce Well-Architected reference diagrams.

## 1. Landscape or solution

Ask, or tell from the request:

- **"Our landscape", "all our systems", "what connects to Salesforce"**: a landscape. Cards are products and outside systems. Lines carry the mechanism and timing. Group each Salesforce org or product family (a "Sales org" holding Agentforce, Tableau Next and Data Cloud One) so the top level stays under about 20 cards.
- **"How does X work", "the design for project Y", "the integration for Z"**: a solution. Cards are the systems the solution touches, with the components that do the work as `attributes` (MuleSoft: "API management: experience, process and system APIs"). Number the integrations with `step` when the order matters.

One message per diagram. When the user's material covers two stories (the AWS ingestion and the ads activation), offer two diagrams, or one landscape with drill-downs.

## 2. Systems

| Field | What to write |
|---|---|
| `id` | A short slug, unique in the model |
| `name` | What the business calls it, as on the user's material: "Data 360 Home Org", "ERP System". Unique, because the reviewer matches cards by name: two cards both called "Marketing Cloud" need telling apart ("Marketing Cloud Engagement") |
| `kind` | `salesforce` (any Salesforce product or org), `middleware` (MuleSoft, Informatica, Boomi, any ETL or integration platform), `external-app` (ERP, billing, HR, ads platforms, outside SaaS), `data-store` (warehouses, lakes, lakehouses, object storage), `channel` (website, mobile app, portal) |
| `hub` | `true` on the system the diagram is about; several hubs stack in the centre. Leave it out and the script picks the Salesforce or middleware system with the most integrations |
| `zone` | Only to override the default placement (section 2 of `architecture-conventions.md`): `left`, `right`, `top` or `bottom` |
| `attributes` | Components or capabilities worth reading on the card, at most 6, a few words each |
| `footer` | One short phrase: its role ("Collect, unify and activate customer data"), the edition, or the owner |
| `icon` | Only when the automatic choice (`data/system-icons.csv`) is wrong or missing; the name must be in the space's resource library |
| `footerIcons` | Rarely: small logos for what the card holds; a group gets its members' logos without asking |
| `parent` | The group this system belongs to. Groups are one level deep |
| `inferred`, `evidence` | `inferred: true` when the material implies the system without naming it, with where you saw it |

## 3. Integrations

| Field | What to write |
|---|---|
| `from`, `to` | Where the data starts and where it arrives. For "Salesforce calls the ERP to get a price", data the user cares about arrives in Salesforce, but the call starts in Salesforce: use `direction: "two-way"` with `from` the caller. Join members of a group directly; the drawing lifts the line onto the group card |
| `direction` | `two-way` only when the material says data flows both ways; one-way is the default. "Syncs", "integrates" or what the product usually does is not enough: draw it one-way from the system the material names as sending, and record the direction in `gaps` |
| `technology` | The mechanism as people name it: "REST API", "Platform Events", "Bulk API", "Zero Copy", "Data Activation", "Out of the box connector", "MuleSoft". This is the line's label, so keep it to 2-4 words |
| `label` | Instead of the technology, when the line should say something else ("Grounding data", "Orders and invoices") |
| `pattern` | The Salesforce integration pattern from `data/integration-patterns.csv`, when you can tell it (table below). It drives the Well-Architected checks |
| `timing` | `real-time`, `near-real-time` or `batch`, only when the material says or the mechanism settles it (Bulk API is batch; Platform Events are near real-time; a synchronous callout is real-time). When the material gives a schedule more exact than the value (nightly, hourly, every 15 minutes), keep its word in `label` ("Nightly orders", read as "Nightly orders · batch") so the line says what the person said |
| `step` | The order in a solution's flow |
| `inferred`, `evidence` | As for systems; the label gets "(inferred)" |

### Choosing the pattern (Salesforce Integration Patterns and Practices)

| The data moves because | Pattern | Salesforce is | Timing | Well-Architected recommends |
|---|---|---|---|---|
| Salesforce calls another system and waits for the answer | `request-reply` | the caller (`from`) | real-time | External Services; Apex callout through a Named Credential; HTTP Callout from Flow |
| Salesforce tells another system something happened and does not wait | `fire-and-forget` | the caller (`from`) | near real-time | Platform events from Flow; Pub/Sub API; Change Data Capture; Event Relay |
| Data is copied in bulk on a schedule | `batch-data-sync` | either end | batch or near real-time | An ETL tool with Bulk API; Data 360 data actions and activations; Data Graph and Connect APIs through MuleSoft |
| Another system creates, reads, updates or deletes Salesforce data | `remote-call-in` | the receiver (`to`) | any | REST, Composite or GraphQL API; Bulk API 2.0 for volume; Pub/Sub API; Platform Events |
| The Salesforce screen refreshes when data changes | `ui-update` | the receiver | near real-time | Platform events or Pub/Sub API with a Lightning component |
| Salesforce shows data kept elsewhere without copying it | `data-virtualization` | the receiver | real-time | Salesforce Connect; Data 360 Zero Copy; Data Cloud One |

`data/integration-mechanisms.csv` lists every mechanism Well-Architected rates for each pattern (best, good, fit or suboptimal) and the validator warns when a technology matches a suboptimal one (Outbound Message for fire and forget; a callout from a trigger for request and reply; SOAP API for remote call-in). Tell the user the warning and the recommended mechanisms; draw what they actually run.

## 4. From a picture of a diagram

Read the picture as a list before writing JSON: every box (with its inner boxes as attributes or, when lines join the inner boxes, as members of a group), every line with its arrows and its pill text. A pill such as "Zero Copy (Query & File Federation)" is the `technology`; a clock or other icon you cannot read is not a timing, so leave `timing` out and say so in `gaps`. Keep the picture's left-to-right story by setting `zone` where the defaults would move a card.

## 5. From a solution design document

Take systems from the architecture or context section, integrations from the interface list (often a table: source, target, mechanism, frequency, volume). Frequency maps to timing ("every 15 minutes", "nightly" are batch; "on save", "event" are near real-time; "synchronous", "on demand with response" are real-time). Record in `gaps` interfaces the document lists without a mechanism or direction.

## 6. Before you draw

Show the user the systems (name, kind, zone or hub) and the integrations (from, to, label as it will read) in two short tables, and ask one question if something is open: which system is the hub, whether a flow is one-way, what timing an interface has. Keep to those columns: a field you worked out rather than read (a `pattern`, a mechanism a Well-Architected check recommends) is not shown as fact in a table or a sentence; offer it as a question the user can confirm. When a line will read a timing word the user did not say ("Nightly orders · batch" for "nightly"), say in one line that the drawing adds the Key's timing word for it. Then validate and plan.
