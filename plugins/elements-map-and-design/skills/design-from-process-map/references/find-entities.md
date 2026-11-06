# Finding the data a process needs

The method the `data-model-deriver` follows. Two phases: first as a **process analyst**, find the logical entities the process handles, without looking at any system; then as a **technical architect**, match each one to the target system's objects. Separating them keeps the target system's vocabulary from hiding what the process actually needs.

## Phase 1: logical entities (the process analyst)

Read `inventory.json` and `process-model.json` (the process as read). The evidence for data is in four places:

| Where | What it gives | Example |
|---|---|---|
| Object resources on a step (`resources` of type Object) | An entity the map's author named | Lead, Quote |
| Metadata attachments on a step (`metadata`) | An entity already tied to a real object, with its API name, node id and selected `refModelId` | Product2 "Product" |
| Nouns in step text | Things the step acts on | "Review **lead** information", "Generate **quote**" |
| Nouns in line labels (the outcomes) | Records created or changed, and their states | "**Account, contact and opportunity** created from lead", "**Opportunity** marked as closed won" |

Leave out resources of type Human, System and Platform / Capability: those are who and with what, not data. A system can still hold data the process needs; that is the integration deriver's concern.

1. **List every candidate noun** with the steps it appears on. Keep the map's words.
2. **Group nouns that mean the same thing** into one logical entity: "Account", "customer", "company", "business" become one entity when the process uses them for the same record. Keep a noun apart when the process treats it differently (a "Prospect" person who reviews a quote is a role, not a record; a "prospect" company before conversion is a Lead). Record every noun you grouped in `sourceNouns`.
3. **Drop what is not data:** a status ("qualified") is a field of an entity, not an entity; a document produced and sent (a PDF quote) is usually a file on the entity, unless the process stores it as its own record.
4. **Relationships** come from steps that create one record from another ("Convert lead" creates Account, Contact, Opportunity), steps that act on two entities together, and lines that hand one record to the next step. Give each relationship its cardinality in the direction one-to-many, and the steps that show it.
5. **Key fields** only where the process names them: a status the lines move through ("Opportunity stage updated to Proposal"), a score the step uses ("segment leads based on scores"), a date that triggers a step. Mark fields you work out as `inferred`, with why.

## Phase 2: matching to the target system (the technical architect)

Read `evidence/targets.json`: the target system's objects (standard, custom and, for an org, external), and on the org route each object's existing fields.

1. **Metadata attachments are taken as given:** the entity is that object, with its `apiName`, `nodeId` and `refModelId` copied from the attachment. Derived entity attachments use the target org selected in `slots.ref_model_id` and include `metadataType` from the entity kind: `Standard Object` for `standard`, `Custom Object` for `custom`.
2. **Match by meaning, then by name.** Prefer a standard object that does the job ("Customer" is Account in Salesforce) over a custom one with a similar label. For an org, prefer an existing custom object over proposing a new one when its description fits.
3. **Kind:** `standard` for the vendor's object, `custom` for one that exists in the org but is not standard (route org only), `external` for an object that lives in another system the process names, `proposed` when nothing in the target system fits.
4. **Evidence:** for each entity, why it maps where it does ("Object resource on 'Convert lead'; Account is the standard customer object"), or why it is proposed ("no scoring object among the 282 org objects").
5. **Fields on existing objects:** a field the process names is `existing` when the object's `fields` hold it (copy its API name and type); otherwise it is new, marked `inferred` with why. Say which in the field's `description`.
6. **Size:** when there are more entities than the rubric's R30 threshold (`data/readability-rubric.csv` at the plugin root), group them into `areas` by the top-level process step that uses them most, so each data model diagram stays readable.

## What a good result looks like

- Every entity names the steps that use it and the nouns it came from.
- Proposed entities are few and each says why nothing existing fits.
- A process with a confidence of lower (a map that failed the check) has more inferred items, each marked.
