# UPN notation rules for process maps and customer journeys

Universal Process Notation (UPN) is the notation Elements uses for business process maps and customer journeys. This file is what a drawn diagram must mean and how its text is worded. Where things go on the page is in [`layout-conventions.md`](layout-conventions.md).

Sources, paraphrased: the Elements help articles [What is Universal Process Notation (UPN)](https://support.elements.cloud/en/articles/982655-what-is-universal-process-notation-upn-and-how-to-use-it), [Process diagrams: UPN standards review](https://support.elements.cloud/en/articles/11320587-process-diagrams-upn-standards-review) and [Customer journey diagram](https://support.elements.cloud/en/articles/9728899-customer-journey-diagram), plus what the six exemplar maps do.

## 1. One building block

UPN has one shape: a box for an activity, with lines in and out. There are no decision diamonds, gateways or event symbols.

- **The box** says what is done: an active verb and the thing it acts on.
- **A line** is an outcome. Read from the box it leaves, it says why the activity happened and how you know it finished. Read from the box it enters, it says when the next activity starts.
- **Resources** in the box say who does it (people and teams, the Human type) and with what (systems, objects, flows and the other resource types).

## 2. Box text

- Start with an active verb, then its object: "Qualify lead", "Configure pricebooks", "Search for solutions related to my problem".
- Be specific. A noun or a vague label ("Evaluation plan", "Fit") hides what actually happens, and so hides what a system such as Salesforce has to support.
- Keep it short: 2–6 words in the exemplars (median 4). Detail goes into attachments or a drill-down.
- Write it so someone who did not draw the map understands it.
- Use sentence case. No API names: "Create quote", not "Create SBQQ__Quote__c".

## 3. Line labels

- Every line carries a label.
- A label is a distinct, unique and verifiable outcome. Test it by asking how you would know, and could prove, that the activity is done: "Quote approved by the deal desk", "Lead converted to opportunity in status 'Qualification'".
- Write it as a completed state, not an instruction ("Contract signed by the customer", not "Sign contract").
- Name the record or status change that proves the outcome where there is one ("Opportunity moved to 'Proposal/Price Quote'"). This is what ties the map to the Salesforce configuration.
- Two lines leaving one box carry different outcomes. If they would carry the same label, they are one line.
- A line starting a level says what triggers it; a line ending a level says what state the work ends in.

## 4. Resources and RASCI

- Every box has at least one resource, and the person or team responsible comes first.
- RASCI letters (Responsible, Accountable, Supporting, Consulted, Informed) go only on Human resources; the server refuses them on other types. Using RASCI on one box can replace a chain of hand-over boxes between people.
- Systems, objects and flows describe what the step uses; they never carry RASCI.

## 5. Logic without diamonds

Where lines meet a box edge carries meaning:

| Lines | Same point on the edge | Different points |
|---|---|---|
| Leaving a box | One outcome that starts several activities in parallel | Different outcomes, each leading somewhere else (alternatives) |
| Entering a box | All of them must arrive before the activity starts | Any one of them starts the activity |

`manage_diagram` attaches a line at the middle of a side, so a "point" here is a side. The plugin's line rules (`layout-conventions.md`, section 4) follow this table: a decision's outcomes leave from different sides (right, top, bottom), a parallel split leaves from one side, an alternative path rejoining the main path enters a different side from the main path, and a step that waits for several inputs takes them all on its left side. A decision with more than three outcomes has to reuse a side, which reads as parallel; split the decision, and when it cannot be split, make the alternatives clear in the labels.

## 6. Size and drill-downs

- At most 10 boxes on a level in this plugin. The Elements UPN guide's limit is 12 on screen; the server warns above 10 (`upn_level_too_many_activities`) and the plugin's readability rubric uses 10 (R01).
- Detail goes into a child level (drill-down) behind a box, to any depth. A child level explains how its parent box is done, with the same scope: it is not a different view of the same diagram.
- The lines into and out of a child level are the lines into and out of its parent box, with the same labels. Draw them with `parentLine` links so they stay matched.
- Lay a level out left to right and top to bottom.

## 7. The review checks Elements runs

Elements' AI "UPN standards review" (business process diagrams only) checks:

| Check | Plugin rule or server warning |
|---|---|
| Every box has a line in and a line out | R02; `upn_activity_orphan`; `upn_level_no_input`, `upn_level_no_output` |
| Box text is clear, verb-based and grammatical | R08 (business language); the reviewer agent |
| Every line is attached to at least one box | `line_unanchored` (an error: the server refuses it) |
| Every line label is a distinct, unique, verifiable outcome | R03 (branches labelled); `upn_line_unlabelled` |
| Every box has at least one person, system or role | `upn_activity_no_resource`; R07 (every role does something) |

A drawn diagram passes these checks before it is shown to anyone.

## 8. Customer journeys

A customer journey uses the same notation from the customer's point of view.

- **Boxes are things the customer does**, in their own voice: "Compare features and pricing", "Contact my CSM / Account owner for help". The default resource of a journey box is Customer, and it comes first on every box; the channels used (website, email, social media, the product itself) follow.
- **The top level is the stages** of the journey, from becoming aware of a need to advocating for the brand, named consistently and kept to a manageable number (five or six in the exemplars).
- **Each stage drills down** to its touchpoints. A journey box may drill down into another customer journey, a business process (how the company supports that moment), an interaction flow (how systems automate it) or an agent instruction (how an AI agent supports it).
- **Record what the customer feels and expects** at each stage. A note attachment on the stage box works.
- **Drop-offs are outcomes too.** Where the customer leaves the journey, draw a line to a terminator labelled with why: "Customer decides our company is not the right fit".
- **Validate with real customer insight** where it exists, and mark what was inferred (the plugin's "Inferred" note convention).
