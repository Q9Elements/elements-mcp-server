# Files a run writes

Both reader skills (`explain-automation` and `trace-automation-chain`) and the `automation-logic-reader` agent pass work to each other through these files. Every file is JSON, written into the run's work folder.

```
<work folder>/
├── trace/                      the walk (scripts/trace_chain.py); explain-automation's stops at its one automation
│   ├── trace.json              the walk's state: nodes, links, lookups, decisions
│   ├── lookups/<key>.json      each terminal acquired dependency collection with native status/resultId/parts/failures
│   └── describe/<n>.json       every get_metadata_component result
├── chain.json                  the chain level as a model (trace_chain.py assemble)
├── links.json                  what each chain line is about (trace_chain.py assemble)
├── bundles/<automation id>/    one per automation: what the reader agent is given
│   ├── context.json            the automation and the chain lines in and out of it (trace_chain.py bundle)
│   ├── definition.<ext>        the source, when one was found: .flow-meta.xml, .cls, .trigger, .json, .xml
│   ├── draft.json              Flows and Process Builders: scripts/flow_to_steps.py's fragment
│   ├── using.json              canonical using rows and native acquisition/failure evidence (trace_chain.py bundle)
│   └── component.json          the get_metadata_component document (trace_chain.py bundle)
├── logic/<automation id>.json  one fragment per automation, written by the reader agent
├── model.json                  the whole model (scripts/build_interaction_model.py merge)
└── drawing/                    draw-interaction-flow's work folder (plan, results, review)
```

## context.json

What the reader needs beyond the source. `scripts/trace_chain.py bundle` writes it in both skills.

```json
{
  "automation": {"id": "trigger_commission", "name": "Trigger Commission", "type": "flow",
                 "apiName": "Trigger_Commission", "description": "...",
                 "attachments": [{"type": "metadata", "apiName": "Trigger_Commission", "metadataType": "Flow", "refModelId": "111111111111111111111111"}]},
  "nodeId": "6acdfafbb000e2f39ae0ddf8",
  "sfType": "Flow",
  "managed": false,
  "details": {"active": true, "subtype": "Record-triggered", "triggerType": "RecordAfterSave"},
  "entry": ["Stage__c = Approved", "Stage__c = Paid", "Generate_Commission__c"],
  "launchedFrom": [],
  "incoming": [{"id": "i3", "label": "Invoice/Credit Note saved (Stage__c = Approved; Stage__c = Paid)", "kind": "triggers", "from": "invoice_credit_note__c"}],
  "outgoing": [{"id": "i6", "label": "Publishes Calculate Commission Line Item", "kind": "publishes",
                "to": "calculate_commission_line_item_from_pe", "object": "Calculate_Commission_Line_Item__e",
                "elementsThatDoIt": ["Create Record 'Create Commission Line Items'"]}],
  "elements": [{"element": "Update Record 'Update Invoice Record'", "relation": "update", "item": "Invoice_Credit_Note__c"}],
  "files": {"using": "using.json", "component": "component.json"}
}
```

- For a single automation (explain-automation), `incoming` holds the line from `START` that triggers it and `outgoing` the lines to `END` for what it writes or publishes. The merge there has no `--base`, so its `chainOutputs` pass `check-fragment` but do not reach the model.
- `launchedFrom` lists the buttons, quick actions and Lightning pages the dependency graph names as using the automation, each as `<type>: <name>`.
- `elements` are the element lines the dependency graph names, with what each does to which item: the evidence for a rebuild when there is no definition.

## A fragment (logic/<automation id>.json)

One automation's logic. `scripts/flow_to_steps.py` writes one from a Flow's XML (as `draft.json`), with `--ref-model-id` set to the run's selected reference model; the reader agent writes the final one. The bundle's `automation.attachments` carries that same `refModelId`; retain it in every metadata attachment of the fragment.

```json
{
  "fragmentVersion": 1,
  "source": {"kind": "flow-xml", "file": "Trigger_Commission.flow-meta.xml"},
  "automation": {"id": "trigger_commission", "name": "Trigger Commission", "type": "flow", "apiName": "Trigger_Commission",
                 "summary": "Creates the commission line items for an invoice once it is approved or paid.",
                 "attributes": [{"title": "Record-triggered flow: after save"}],
                 "attachments": [{"type": "metadata", "apiName": "Trigger_Commission", "metadataType": "Flow", "refModelId": "111111111111111111111111"}]},
  "steps": [{"id": "trigger_commission.start", "name": "Record-triggered start", "automation": "trigger_commission",
             "element": "start", "attributes": [{"title": "Invoice_Credit_Note__c UPDATED"}], "sourceRef": "start"}],
  "connectors": [{"from": "START", "to": "trigger_commission.start", "label": "Record-triggered", "kind": "next"}],
  "gaps": [],
  "chainOutputs": [{"interaction": "i6", "fromStep": "trigger_commission.Create_Commission_Line_Items"}],
  "hints": {"trigger": {}, "reads": [], "writes": [], "publishes": [], "calls": []}
}
```

- `source.kind`: `flow-xml`, `apex-source`, `omniscript-json`, `rule-xml`, or `elements` (rebuilt from Elements' evidence). The merge turns it into a model source.
- `automation`, `steps`, `connectors` and `gaps` are in the model's format (`schemas/ba-model.schema.json`). Step ids are unique across the whole model: start them with the automation id and a dot.
- A step may carry `callsApiName` (the API name of the flow or class it calls); the merge turns it into `calls` when that automation is in the model.
- `chainOutputs` (optional) names, for each chain line out of the automation, the step that causes it.
- `hints` (optional, from `flow_to_steps.py`) say which step reads, writes, publishes or calls what; the merge uses them for chain lines that have no `chainOutputs` entry.

Check a fragment with `python3 scripts/build_interaction_model.py check-fragment FRAGMENT --context context.json`.

## chain.json and links.json

`chain.json` is a model with `automations`, hub `entities`, numbered `interactions` (ids `i1`, `i2`...) from `START` and to `END`, and `gaps`. `links.json` says, under `interactions`, for each interaction id, what it is about: `{"kind": "writes" | "publishes" | "calls", "object": "<API name>", "calls": "<automation id>"}`, plus `automations` (model id → Elements node id) and `entities` (model id → API name). `build_interaction_model.py merge --base chain.json --links links.json` reads both.

For a traced chain, each excluded automation and candidate has a left-out gap
with its stored reason. Unconfirmed Apex object references and inferred
writes are uncertainty gaps; only established writes produce write lines or
recursion gaps.

`using.json` contains the acquired canonical dependency rows under rows plus terminal status, resultId, indexed parts and all failures. Each row uses node, related and relationshipDescription. `source.json`, when stored source is used, records the definition producer, stored availability, version/sync provenance, files and gaps; the logic reader keeps this provenance.
