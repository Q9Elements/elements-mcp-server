# Writing a level from a data model

How the `process-level-writer` agent turns a brief into one level of the process. The method is the one used by hand for the Manufacturing Cloud map (see [`manufacturing-exemplar.md`](manufacturing-exemplar.md)): explain each step as *what happens, why, the outcome that proves it is done, the objects used, who does it, and what comes next*, first for the whole system (one step per capability), then for each capability (one step per one to three of its objects).

The notation rules every Elements process map follows are in [`../../draw-process-map/references/upn-rules.md`](../../draw-process-map/references/upn-rules.md). This file adds what is specific to inferring a process from a data model. The file format is the plugin's [`../../../schemas/level-outline.schema.json`](../../../schemas/level-outline.schema.json), shared by every process reader; in it, a step's `uses` holds the objects' apiNames and `item` the capability a box stands for.

## Contents

1. Why a data model tells you the process
2. The step format
3. The top level (brief mode `overview`)
4. A child level (brief mode `detail`)
4a. A level built on a lifecycle (brief mode `lifecycle`)
5. Outcome labels
6. Roles
7. Decisions and loops
8. Marking what was inferred
9. Before writing the file
10. Worked example

## 1. Why a data model tells you the process

A data model records what a business has to remember. Each object exists because some step creates or changes it, and each reference field says one record cannot be completed before another exists. So:

- **Every object is created or updated by at least one step.** An object no step touches is either not used or a step is missing.
- **Records come after the records they point at.** A Sales Agreement Product points at its Sales Agreement, so the agreement is created first. Master-detail is strict (the detail cannot exist alone); a lookup is usually, not always, an order.
- **The kind of object says where its step sits.** Reference data (terms, codes, templates, definitions) is set up before anything uses it; the main record of the capability (agreement, claim, visit) starts the core work; its lines and junctions follow; events (transactions, transfers, adjustments) happen to it over time; numbers derived from it (facts, targets, forecasts) come last and feed a review. [`../data/object-archetypes.csv`](../data/object-archetypes.csv) has the name endings that suggest each kind, and the brief gives each object's archetype.
- **Status and stage values are the outcomes.** A Sales Agreement status with Draft, Approved, Rejected, Activated and Expired says the agreement is drafted, reviewed, approved or rejected, activated, and in time expires. When the brief's mode is `lifecycle`, the values are the level: one step per value (section 4a).

What a data model does not say: who does each step, and the order of steps that do not depend on each other. Write those from what the business does, and keep them plausible rather than clever.

## 2. The step format

Each step in the outline has:

| Field | The method's question | Rule |
|---|---|---|
| `name` | What is the step? | The box text: an active verb and its object, sentence case, 2 to 6 words. "Create sales agreement", not "Sales agreement creation" or "Create SalesAgreement". |
| `what` | What happens? | One or two sentences, from the object descriptions in the brief. |
| `why` | Why? | What the business gets, or what would go wrong without the step. One sentence. |
| `next[].outcome` | What is the desired outcome? | The label of the line to the next step. See section 5. |
| `uses` | Which objects are used? | apiNames from the brief. |
| `roles` | Who is responsible? | The person or team doing it first. See section 6. |
| `next[].to` | What comes next? | The step this outcome starts. |

`what` and `why` are not drawn as box text; they go into an "About this step" note on the box, with each object's description, so someone who does not know the system can learn it from the map.

## 3. The top level (brief mode `overview`)

One box per item in the brief: each item is a capability (or an area holding capabilities), and the step's `item` is its capability id. Do not add boxes that stand for no capability, and do not split or merge items; the capability list was confirmed before this level is written.

- **Box text** describes the capability as work: "Process warranty claims", "Manage sales agreements", "Forecast account sales". At most 6 words. The capability's noun-phrase name is already on the capability itself.
- **Order** follows the value chain of the system. A typical order for an industry cloud: define what is sold (products, terms) → agree and sell (agreements, contracts) → plan (targets, forecasts) → fulfil (inventory, shipments) → service (claims, visits) → relationship and feedback, which loops back to the start. Use the brief's `dependsOn` and `suggestedOrder` as hints: a capability whose objects point at another's usually comes after it.
- **Supporting capabilities** run alongside the main chain rather than in it (fleet management and manufacturing programs in Manufacturing Cloud). The brief marks them `supporting`. Give each its own start and end, and no line to or from the main chain unless one capability truly hands work to it.
- **One role per box:** the person who owns the capability, such as "Warranty manager". Leave `uses` empty on this level: the build shows each box's main records itself (an object with a lifecycle first), and the objects each step uses go on the child level.
- **Starts:** what triggers the system's work from outside, such as "New product line approved for launch", or an output of a process this map does not cover: "Opportunity moved to Proposal/Price Quote" entering the sales agreements box. A start may enter a box in the middle of the chain.
- **Lines and ends** carry the outcome the next capability needs: "Warranty terms active for all products". The main chain may loop from the last box back to the first ("Partner visit findings recorded") instead of ending.
- **Short labels: 40 characters at most** on every line of this level. Each one becomes a start or end label on the child levels of the boxes it joins, and the server can shorten those free ends, so the house label limit preserves room beside the box.
- **Links:** the capability's help links are added to its box automatically; add a link only when the brief gives another.

An area level (an overview brief whose `parent` is set) follows the same rules, and also section 4's rule on starts and ends: copy the parent box's labels.

## 4. A child level (brief mode `detail`)

- **Use every object in `objects`.** The coverage check fails when an owned object is used by no step. When an object genuinely has no step (a technical object the documentation lists but nobody works with), leave it out and add a gap whose `about` is its apiName, saying why.
- **Use shared objects only where a step really reads or updates them** (Account on "Identify claim participants"). They need no step of their own.
- **Start from `suggestedOrder`** (records before the records that point at them; set-up before the main record before lines, events and measures). Change it when the business order differs, for example a review between two creation steps.
- **One to three objects per step.** A box shows at most five resources (roles and objects together), so a step with one role can show four objects. Put a main record and its detail lines in one step when the same person enters them together ("Define sales agreement products" uses the product and its attributes). Split when a different person does the work or something must happen in between.
- **Number of steps:** within the brief's `typicalSteps` where you can, never more than 10. A level with more objects than ten steps can carry is a capability that should have been split; record a gap rather than squeezing.
- **Starts and ends:** the brief's `parent.inputs` and `parent.outputs` are the labels of the lines into and out of the box this level drills down from. Copy each one exactly, character for character: every input becomes a `start` on the step it triggers (usually the first), every output an `end` on the step that produces it (usually the last). The drawing skill links them to the parent's lines, and the build fails when one is missing.
- **Other triggers** the data model shows, such as a product request raised by field service, may be extra starts. Each one is reported as a gap (the parent box does not show it), and a start into a step that is also reached from another step is drawn entering at the same point, which UPN reads as "all must arrive". Add them only when the step cannot be understood without them, and keep their labels to 40 characters at most.

## 4a. A level built on a lifecycle (brief mode `lifecycle`)

A capability whose main object has a status or stage picklist is drawn as that picklist: the capability's level holds **one step per value**, in the brief's `lifecycle` (also in `cover.lifecycle`). With record types, the level above it splits the capability by record type (prepare_briefs.py writes that split), and this level holds only the values its `recordType` uses. Each value has its `value` (spell it exactly), and may say `default`, `closed` and, if closed, `won`; `ordered: true` means the values are listed in the org's order.

For each value, write the business outcome and the most likely activity that puts the record in that value:

- **The outcome:** "<Object> <field label> updated to '<value>'", in lower case after the object, so for the value Nurture of Opportunity Stage: "Opportunity stage updated to 'Nurture'". It is the label of the first line out of the step (or of its end), and that line carries `"sets": {"object": "<apiName>", "value": "<value>"}`.
- **The activity:** the most likely business activity that results in the record being updated to that value, as an active-verb statement that names no role. For the stage Sales Engaged: "Verify business readiness", not "Sales development rep verifies business readiness". Set the step's `value` to the value it stands for.
- **The role is a resource, not text:** put the person or team who does the activity in `roles` (section 6), never in the box text.

Then join the steps:

- **One step per value, no more and no less.** A value no step stands for fails the check, unless a gap about the object says why (a value only an integration sets, a value no longer used). Do not add boxes that stand for no value; work that happens between two values belongs to the step of the value it leads to.
- **The main path follows the order.** Starts (the parent's inputs, copied exactly) go into the step of the first value: the `default` one, or the first in order. Each step's first line goes to the step of the next open value, so the main path reads the values in order; the check warns when it goes back. With `ordered: false`, work the order out from what the values mean, and say how in a gap.
- **Other lines out of a step are conditions, not outcomes.** They lead to a step elsewhere and carry the condition that leads there ("Customer not interested", "Details missing"), with no `sets`: only the step standing for a value sets it.
- **A closed value that is not won** is reached from each step where the record can be lost or cancelled, by a condition line, and its own outcome is an end: "Opportunity stage updated to 'Closed Lost'".
- **A won value, or the last closed value, ends the level:** its step's end carries the parent's output label, copied exactly, and the `sets` of its value.
- **Waiting values** ("With customer", "On hold") are steps too: the activity is the hand-over that puts the record there ("Request customer information"), and a condition line from it returns to the step that resumes the work.
- **Objects:** every step lists the lifecycle object in `uses`, with the brief's other objects where the step creates or updates them; together the steps use every object in `cover.uses`. Under a record-type split, `cover.uses` holds the lifecycle object only: the capability's other objects are in `mayUse`, shared by the record types' levels, so use those this record type's work touches (a Performance Objective when an employee is onboarded, not when a shareholder is).
- **More than ten values:** the step budget is the number of values plus two at most. Write one step per value even past ten, and say in a gap that the record type or field should be reviewed.

For a Team Member record type Shareholder, whose Status values are Active (default), Left and Ex-Employee, and a parent box with input "Shareholder team member needed" and output "Shareholder team member processed" (shortened):

```json
{"steps": [
  {"id": "active", "name": "Onboard shareholder", "value": "Active", "uses": ["Team_Member__c"],
   "roles": [{"name": "HR administrator"}], "what": "...", "why": "...",
   "next": [{"to": "left", "outcome": "Team Member status updated to 'Active'",
             "sets": {"object": "Team_Member__c", "value": "Active"}}]},
  {"id": "left", "name": "Process shareholder departure", "value": "Left", "uses": ["Team_Member__c"],
   "roles": [{"name": "HR administrator"}], "what": "...", "why": "...",
   "next": [{"to": "ex-employee", "outcome": "Team Member status updated to 'Left'",
             "sets": {"object": "Team_Member__c", "value": "Left"}}]},
  {"id": "ex-employee", "name": "Retain former employee shareholding", "value": "Ex-Employee",
   "uses": ["Team_Member__c"], "roles": [{"name": "Company secretary"}], "what": "...", "why": "..."}],
 "starts": [{"to": "active", "trigger": "Shareholder team member needed"}],
 "ends": [{"from": "ex-employee", "outcome": "Shareholder team member processed",
           "sets": {"object": "Team_Member__c", "value": "Ex-Employee"}}]}
```

On basis usage the build adds a usage note beside the level's first step (how many records the object or record type holds and how recently they changed). The writer does not write it, and does not repeat those figures in a step's `what` or `why`.

## 5. Outcome labels

The label on a line is what is now true, so that someone could check it happened.

- **A completed state, naming the record or status that proves it:** "Sales agreement created in status 'Draft'", "Every product linked to its warranty terms", "Claim moved to 'Approved'". Not an instruction ("Create the agreement") and not a benefit ("Clear warranty terms, leading to increased customer trust").
- **Distinct:** every line on a level carries its own label. Lines out of one box may share a label: they are then one outcome that starts those steps in parallel, so share a label only when both steps really start at once.
- **Expected outcome first:** list a step's `next` entries with the normal, expected outcome first. The drawing puts the first-listed line on the main path and the others above and below it; an end is drawn after the step's `next` lines.
- **A step that waits for everything** that comes into it gets `"join": "all"`; without it, any one incoming line starts it.
- **Short:** at most 100 characters between boxes on a child level, and at most 40 on the top and area levels and on any extra start or end (they are drawn on short start and end lines). The limits come from the plugin's [`../../../data/style-process.csv`](../../../data/style-process.csv) (`label_max_chars`, `end_label_max_chars`).
- **Starts** describe the triggering event the same way: "Opportunity moved to Closed Won".
- **A status or stage change** is written "<Object> <field label> updated to '<value>'"; on a lifecycle level the line carries `sets` (section 4a).

## 6. Roles

- **The person or team doing the step comes first**, by job title: "Warranty manager", "Claims processor", "Inventory specialist". Use a customer or partner when they do it ("Submit warranty claim": Customer or Dealer).
- **Reuse role names across levels.** A system is run by ten to twenty roles, not one per box: the hand-made Manufacturing map has 51 roles on 78 boxes, 32 of them used once, and reads worse for it. Use the names in `rolesInUse` (the roles already on the top and area levels) wherever they fit, and add a new role only for a job none of them does. The build merges roles by name, ignoring case, and the coverage check warns when too many roles appear on one box only.
- **Every step has a person or team first,** even an automated one: the person accountable for it. A **system role** (`kind: system`) follows them for a step the application does on its own, such as calculating forecasts. An **AI agent** (`kind: ai-agent`) follows them only when the documentation describes one.
- **Never name a role like an object.** "Supplier" the person and Supplier the record would both be drawn as resources on the same map, and an Elements resource library holds one name under one type only. Name the person: "Supplier contact", "Dealer principal". The coverage check (C13) fails a model where a role and an object share a name.
- **RASCI** only when more than one person is involved: `R` for who does it, `A` for who signs it off, `C` for who is asked (a customer reviewing an agreement), `I` for who is told. RASCI is for people only.

## 7. Decisions and loops

Add a decision (a step with more than one line out) only where the data model shows a state that can go two ways:

- a status, stage or approval picklist with an accepted and a rejected value (Claim status Approved or Rejected);
- an approval, review or exception object (Advanced Account Forecast Adjustment means forecasts get corrected);
- return, recall or cancellation objects (Return Order means some orders come back).

Each outcome is distinct. A rework outcome goes back to the step that fixes it ("Claim returned in status 'Draft' for missing details" back to "Record repaired items"). A decision the data model does not support gets `"inferred": true` on its line.

## 8. Marking what was inferred

The whole map is inferred from a data model, and the model's description says so; do not set `inferred` on every step. Set it only on:

- a step that uses no object (a meeting, a review, a hand-over);
- a decision or loop no field or object supports.

Use `evidence` for what supports a step when it is not obvious: a field and its values, a documentation section. Use `gaps` for what the brief does not answer: an object with no description, an order the data model leaves open, a role the documentation does not name.

## 9. Before writing the file

Check, in this order:

1. Every apiName in the brief's `objects` is in some step's `uses`, or in a gap.
2. Every `parent.inputs` label is a `trigger` and every `parent.outputs` label is an `outcome` of an end, copied exactly (detail and area levels).
3. Every step has a line in (a start or another step's `next`) and a line out (`next` or an end), and no step has a line to itself.
4. Every step has a person or team first.
5. Box texts start with a verb, are 2 to 6 words, and are all different.
6. Outcome labels are completed states, all different on the level (starts and ends included), at most 100 characters (40 on the top and area levels and on extra starts and ends).
7. At most 10 steps.
8. On a lifecycle level: one step per value of `cover.lifecycle`, each with its `value`, its first line out (or its end) setting that value and naming it, and no other line setting a value (section 4a).

## 10. Worked example

A brief for Sales Agreements (detail mode) owns Sales Agreement, Sales Agreement Product, Sales Agreement Product Attribute, Sales Agreement Product Schedule, Contract, Sales Contract Line, Order and Order Product. The parent box "Manage sales agreements" has inputs "Warranty terms active for all products" and "Opportunity moved to Proposal" and output "Agreement active, orders flowing". A good outline (shortened to four of its steps):

```json
{
  "schemaVersion": "1.0",
  "level": "sales-agreements",
  "steps": [
    {"id": "create", "name": "Create sales agreement",
     "what": "The sales manager records the long-term agreement with the customer: its term, the negotiated prices and the volumes.",
     "why": "Without it, committed volumes and prices live in documents that planning and forecasting cannot read.",
     "roles": [{"name": "Sales manager", "rasci": "R"}], "uses": ["SalesAgreement"],
     "next": [{"to": "products", "outcome": "Sales agreement created in status 'Draft'"}]},
    {"id": "products", "name": "Define agreement products",
     "what": "Each product the customer commits to is added with its price, quantity and attributes.",
     "why": "Planned quantities per product drive the schedule, the forecasts and production.",
     "roles": [{"name": "Sales manager"}], "uses": ["SalesAgreementProduct", "SalesAgreeProductAttribute"],
     "next": [{"to": "schedule", "outcome": "Every committed product on the agreement with price and quantity"}]},
    {"id": "review", "name": "Review agreement with customer",
     "what": "The customer checks the products, schedule and prices.",
     "why": "Both sides commit to the same volumes before the agreement is activated.",
     "roles": [{"name": "Sales manager", "rasci": "R"}, {"name": "Customer representative", "rasci": "C"}],
     "uses": ["SalesAgreement"],
     "next": [{"to": "contract", "outcome": "Sales agreement moved to 'Approved'"},
              {"to": "products", "outcome": "Changes requested by the customer", "inferred": true}]},
    {"id": "orders", "name": "Process customer orders",
     "what": "Orders placed under the agreement are recorded with their products.",
     "why": "Actual quantities are compared with the agreement's planned quantities.",
     "roles": [{"name": "Customer service representative"}], "uses": ["Order", "OrderItem"]}
  ],
  "starts": [
    {"to": "create", "trigger": "Warranty terms active for all products"},
    {"to": "create", "trigger": "Opportunity moved to Proposal"}
  ],
  "ends": [{"from": "orders", "outcome": "Agreement active, orders flowing"}]
}
```

Compared with the hand-made level it replaces, the outcomes name a record and a state ("created in status 'Draft'") instead of describing a benefit, the review loop has one labelled line instead of two (one unlabelled), and the starts copy the parent's labels so the drill-down matches its box.
