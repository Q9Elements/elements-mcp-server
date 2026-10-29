# Where an automation's definition comes from

Drawing the logic card by card needs the definition. Ask once at kickoff which source the person can offer: a local Salesforce Developer Experience (SFDX) project, a retrieve from an org they name, an attached file, or Elements stored definitions; also offer Elements dependency evidence only. Use the agreed source; when several are available, follow this order and stop at the first that has the definition. Acquire stored source when chosen or when the other sources are unavailable. With no definition, rebuild from dependency evidence and mark the steps inferred. Never retrieve from an org the person did not name.

| Order | Source | How | What it gives |
|---|---|---|---|
| 1 | A local SFDX project the person has (a folder with `force-app/` or `sfdx-project.json`) | Find the file by application programming interface (API) name (paths below) | That file's definition |
| 2 | Salesforce, retrieved | The Salesforce command-line interface (CLI): `sf project retrieve start --metadata Flow:Trigger_Commission --target-org <alias> --output-dir <work>/retrieved`. Check that `sf --version` runs and `sf org list` shows the alias. When a Salesforce DX Model Context Protocol (MCP) server is connected, use its retrieve tool | The retrieved definition |
| 3 | A file the person attaches | Ask for it by name | That file's definition |
| 4 | Elements stored definition | `get_metadata_source`, native acquisition, then `scripts/save_definition.py` | Available stored Extensible Markup Language (XML) or Apex body, with sync/version provenance |
| 5 | Elements dependency evidence | Canonical `using` rows and component description | Which elements exist; rebuild their order as inferred |

Elements can return the latest stored definition through `get_metadata_source`. When using this source, request the chosen node in `nodeIds` (at most 5000), with selected `teamId`/`refModelId`; poll running, acquire every native part cursor and all failure evidence. Use each row's available XML or Apex body, checking status and reason. `no_stored_definition`, `file_missing` and `managed_code_hidden` are explicit source gaps; status `ok` can still hide a managed Apex body. Record sync/version provenance.

Run `python3 <plugin>/scripts/save_definition.py --rows SOURCE.ndjson --node-id <nodeId> --type <local-type> --out-dir <bundle>`. It preserves Apex body separately from metadata XML, writes `source.json` provenance and gaps, and saves available Flow XML as `definition.flow-meta.xml` for `flow_to_steps.py`. For `xmlScope: object`, pass `--component` with the confirmed component name; select that entry. If acquisition or source is unavailable, agree an alternative or carry an explicit source gap.

## File paths in an SFDX project

| Automation | Path under `force-app/main/default/` | Bundle file name |
|---|---|---|
| Flow, Process Builder | `flows/<ApiName>.flow-meta.xml` | `definition.flow-meta.xml` |
| Apex class | `classes/<Name>.cls` | `definition.cls` |
| Apex trigger | `triggers/<Name>.trigger` | `definition.trigger` |
| Workflow rule | `workflows/<Object>.workflow-meta.xml` (the rule is one `<rules>` entry) | `definition.xml` |
| Assignment, auto-response, escalation rule | `assignmentRules/<Object>.assignmentRules-meta.xml`, `autoResponseRules/<Object>.autoResponseRules-meta.xml`, `escalationRules/<Object>.escalationRules-meta.xml` | `definition.xml` |
| Approval process | `approvalProcesses/<Object>.<Name>.approvalProcess-meta.xml` | `definition.xml` |
| Validation rule | `objects/<Object>/validationRules/<Name>.validationRule-meta.xml` | `definition.xml` |
| OmniScript | `omniScripts/<Name>.os-meta.xml`, or the DataPack JSON | `definition.xml`, or `definition.json` for a DataPack |
| Integration Procedure | `omniIntegrationProcedures/<Name>.oip-meta.xml`, or the DataPack JSON | `definition.xml`, or `definition.json` for a DataPack |

The `--metadata` names for `sf project retrieve start` are `Flow:<ApiName>`, `ApexClass:<Name>`, `ApexTrigger:<Name>`, `Workflow:<Object>`, `AssignmentRules:<Object>`, `AutoResponseRules:<Object>`, `EscalationRules:<Object>`, `ApprovalProcess:<Object>.<Name>`, `ValidationRule:<Object>.<Name>`, `OmniScript:<Name>`, `OmniIntegrationProcedure:<Name>`.

## Preparing a bundle

For each automation, in `bundles/<automation id>/`:

1. `trace_chain.py bundle` makes the folder and writes `context.json` ([`data-contracts.md`](data-contracts.md)), `using.json` and `component.json`.
2. `definition.<ext>`: the file found, copied as it is, named as in the table above.
3. For a Flow or Process Builder with a definition: run `python3 <plugin>/scripts/flow_to_steps.py definition.flow-meta.xml --automation-id <id> --api-name <ApiName> --ref-model-id <selected-refModelId> --out draft.json` in the bundle folder. Its structure is exact; the agent keeps it and adds what [`logic-reading.md`](logic-reading.md) lists under way 1 (footers, words for API-name titles, gaps, chain outputs).

A Flow's stored, retrieved, attached or local XML is the version saved at that source: say which in the report when it may differ from the active version in the org.
