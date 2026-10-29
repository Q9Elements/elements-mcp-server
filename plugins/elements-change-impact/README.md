# Analyze Change Impact

Analyze Change Impact is a guided assessment for Salesforce administrators, architects, and consultants. It compares supported approaches to an automation or schema change, traces affected components and save-driven automation, and prepares an impact report with a draft delivery backlog. You make and deliver the change.

## Start and resume

Try one of these prompts:

- “Assess the impact of adding values to Opportunity.Lost_Reason__c.”
- “Compare approaches for adding an approval step to Opportunity.”
- “Resume my change-impact assessment.”

At kickoff, provide:

- A sentence describing the proposed automation or schema change, including the object and named element when known.
- The Elements space and org model to use when more than one is available. With one suitable model, the playbook selects it and tells you.
- Answers to any confirmation or approach question. For an automation delete, the playbook may ask whether to delete despite lost work or move uncovered work first.

The engagement directory stores `execution-state.json` and the run's files. To continue later, provide the directory containing that file and say “resume”. The playbook continues from its recorded stage.

Before offering approaches, including for requests without a named change set, the playbook checks for automation that matches the requested purpose and writes the relevant field or creates the requested record. When it finds a confirmed match, that option leads as “Use what you already have”. Apex classes with an unknown active status remain candidates unless an inactive or deleted fact excludes them.

When strong evidence supports a way to meet your stated intent with materially less change, the playbook offers at most one alternative. A reuse option includes its evidence and population percentage and keeps the named element unchanged. Your named change stays the default and is always listed. Decide requests include the alternative at the approach pick; named updates and deletes offer it in one line at confirmation. Taking it follows the existing correction and confirmation route.

For named automation updates, the playbook compares current and proposed entry conditions when the conditions change. Its order-of-execution screen combines those comparisons with the existing field screen to show pre-existing conflicts. Reports covering several elements show each element's incoming references separately from outgoing connections, and label any direction that was not assessed. Before an approach pick, each automation option includes save-driven effects for its writes and creations. Identical targets share one analysis across options, and the first impact trace reuses those results on the same model sync.

Each automation option's org-pattern fit counts its own object's held inventory. A missing inventory reads "not known". Dependent classification combines every relation before selecting a component's strongest effect. A dependent affected by several changed elements receives one defect story with every source and judgement retained in the backlog data. Markdown descriptions preserve their line order.

The save-order screen places Process Builder after before-save flows and before after-save flows. Two Process Builders on the same object have no guaranteed order. An empty peer screen is clear; hidden managed-package writes remain insufficient evidence and say "managed package: source not visible".

## What it does and when to use it

- Use it before building a Salesforce automation or schema change, including when you need to compare approaches, update or delete a named element, or understand the effects of a proposed change.
- It checks whether existing automation already does the requested work, traces incoming references and outgoing connections, reviews save-driven effects, and identifies dependencies, migration needs, and order-of-execution concerns.
- For automation deletes, it checks which jobs would be lost or partly covered and asks whether to delete anyway or move the uncovered work first.
- Every complete run produces a backlog. A finding is blocking only when no backlog story resolves it and it makes the change unsafe as planned. Findings resolved by backlog stories remain in the report. Blocking findings lead the report and appear as flags at the top of both backlog files with their text.
- The backlog contains change, defect, grouped review and regression stories. Change-story acceptance criteria define tests for the change, including its boundary cases. Existing paths stay in the report; a regression story covers cross-story interactions found in the run.
- This is analysis and planning only. You make every change. The playbook does not change Salesforce metadata or save Elements stories.
- Field population is reported as a percentage only.

## Requirements

- Install and connect the core `elements` plugin to the Elements Model Context Protocol (MCP) server. MCP must be enabled for the Elements space.
- Automation summaries require Automation & Execution Intelligence (an add-on on Core Metadata Management; included in Advanced Metadata Management). Summaries must already exist for an automation in the target org. The playbook checks this first and stops before confirming or tracing the change until the summaries are available. Wait for summaries to finish, then say retry.
- Use an Elements model for the Salesforce org. A model with an earlier completed sync can be analyzed while its latest sync failed or remains in progress; the report identifies that status and uses the last complete sync. If the model has never completed a sync, wait for one and retry.
- Python 3 must run where the playbook scripts run.

## Install

### Claude Code

```text
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements-change-impact@elements
```

### Claude Desktop and claude.ai

- Open 'Customize' → 'Plugins'.
- Install `elements-change-impact` from the `Q9Elements/elements-mcp-server` marketplace.

### Codex

```text
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements-change-impact@elements
```

### ChatGPT

- Upload [`elements-change-impact.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements-change-impact.zip) from the repository's dist folder.
- The core plugin provides the Elements app, so there is no separate Add app step.
- Upload the zip again for each playbook release.

### Other tools

```text
npx plugins add Q9Elements/elements-mcp-server --target <tool>
```

Then select `elements-change-impact`.

## Stages at a glance

| Stage | What happens and what you do |
|---|---|
| 00 Start | Describe the proposed change and establish the working directory for the engagement files. |
| 01 Understand the change | Select a synced org model, resolve the target elements, check that automation summaries exist, and confirm the request. If summaries are missing, wait for the automation summaries to finish, then say retry. |
| 02 Choose an approach | Review supported options, evidence, and any automation already doing the work. For a delete with uncovered work, answer whether to delete anyway or move the work first. |
| 03 Trace impact | Review dependencies, possible source references, data loading effects, migration needs, save order, and any findings. Some evidence may be unavailable and is identified in the report. |
| 04 Deliver | Receive the impact report and draft backlog. Blocking findings lead the report and appear as flags at the top of the backlog files. |
| 05 Recover | Resolve a recorded blocker and say retry. A transient read is retried once automatically; if it still fails, the playbook delivers an incomplete report and a backlog marked not drafted with the reason. |

## What you get

- A self-contained HyperText Markup Language (HTML) impact report, `impact-report.html`, with a JavaScript Object Notation (JSON) report record, `impact-report.json`.
- A draft Markdown backlog, `backlog.md`, and its JSON record, `backlog.json`, with proposed work, acceptance criteria, delivery order, and any flags. Story member files accompany grouped work where needed.
- The report describes the confirmed request, selected org model and sync date, alternatives and choices, affected components, evidence gaps, data and automation effects, migration needs, findings, and proposed delivery work.
- Incoming references and outgoing connections are shown separately. A direction that was not read is marked “not assessed”. A completed read with no results is reported as zero.
- The backlog is a draft and has not been saved as Elements stories. Each complete run drafts it, with blocking findings flagged at the top.
- The report identifies a failed latest sync and states that the analysis uses its last complete sync. For a sync in progress, it says: "A newer sync is in progress; this analysis uses the last complete sync."

## Tools it uses

Elements tools used by the playbook:

- `get_space_context` and `list_reference_models`: identify the available Elements space and org models.
- `search_metadata`, `get_metadata_component`, `get_metadata_source`, and `list_metadata_by_criteria`: resolve targets and read model details, definitions, fields, and values.
- `get_dependencies`: read component relationships and dependency evidence.
- `explain_metadata_components`: check automation summaries and provide automation evidence; card 01 handles its absence as an automation-summary prerequisite stop.
- `run_code_search`: search for possible source references outside available Apex bodies.
- `run_data_load_impact`: assess save-driven effects of a change.

The playbook's local scripts normalize evidence, compare options, check dependencies and save order, build the draft backlog, and render the report.

## Data handling

- The engagement directory stores `execution-state.json`, report and backlog files, and intermediate evidence used by the analysis.
- The `work/` folder stores downloaded evidence bundles and normalized files used to produce the report and backlog.
- The report and backlog may contain org object, field, automation, and component names; descriptions and automation summaries; dependency and source-reference evidence; population percentages; findings; and your request and replies.
- The playbook does not change Salesforce metadata or save Elements stories. Review report, backlog, and member files before sharing them because they contain information from your org and conversation.

## Tested with

- Claude Code Command Line Interface (CLI) and Codex CLI on 2026-10-22 Pacific Daylight Time (PDT) against the Elements MCP release of that date.
- Other tools are untested.

## Version

Version 1.1.0.
