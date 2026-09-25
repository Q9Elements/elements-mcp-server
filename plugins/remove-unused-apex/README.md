# Remove Unused Apex

Remove Unused Apex is a guided analysis playbook for Salesforce administrators, architects, and consultants. It uses an org's execution telemetry and dependency graph to identify candidate Apex classes and triggers, select dependency-complete packages toward a capacity target, and prepare customer-reviewed removal plans.

## What it does and when to use it

- Use it when the org is near the Apex character limit, when you need to identify unused or dead Apex, or when you want to reclaim Apex capacity.
- The playbook looks for code with no recorded use during its effective telemetry window and reports evidence, uncertainty, and blind spots for review.
- It selects packages toward a target stated as characters, a percentage of the allocation to free, or a target usage percentage.
- This is analysis only. You make every change. Elements does not change, delete, deactivate, or deploy anything in Salesforce.
- The playbook does not claim certainty that a class is unused. Its evidence errs toward keeping code when use is uncertain.

## Requirements

- Install and connect the core `elements` plugin to the Elements Model Context Protocol (MCP) server. This playbook adds no server or app of its own.
- Use an Enterprise Elements Space with the Dependency Explorer license, which gates `has_event_monitoring`, `get_unused_apex_candidates`, and `code_search`. The Space's plan must include the tools used by the cards: `has_event_monitoring`, `get_unused_apex_candidates`, `list_reference_models`, `get_dependencies`, `code_search`, `get_metadata_node`, and `get_node_change_history`.
- Use a production Salesforce org synced to Elements. Its reference model must show a completed sync.
- The org must have Salesforce Event Monitoring enabled, including the Event Monitoring add-on and daily Apex event logs. The initial check requires at least one distinct daily log date.
- The candidate bundle must include `ApexExecution` telemetry with at least one processed day.
- When the production org contains its own unmanaged Apex triggers, the bundle must also include `ApexTrigger` telemetry with at least one processed day.
- Candidate analysis requests a 90-calendar-day window in Coordinated Universal Time (UTC), ending yesterday. The effective window is limited to telemetry Elements holds and must contain at least 29 held calendar days.
- Python 3 must run where the playbook scripts run.
- The environment that downloads the candidate bundle needs network access to the bundle host. The kickoff check probes the host from that environment. If the probe fails because of name resolution, connection refusal, or timeout, ask information technology (IT) to allow the exact host printed by the playbook. For an unlisted Elements instance, ask Elements support for the host.

## Install

### Claude Code

```text
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install remove-unused-apex@elements
```

### Claude Desktop and claude.ai

- Open 'Customize' → 'Plugins'.
- Install `remove-unused-apex` from the `Q9Elements/elements-mcp-server` marketplace.

### Codex

```text
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add remove-unused-apex@elements
```

### ChatGPT

- Upload [`remove-unused-apex.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/remove-unused-apex.zip) from the repository's dist folder.
- The core plugin provides the Elements app, so there is no separate Add app step.
- Upload the zip again for each playbook release.

### Other tools

```text
npx plugins add Q9Elements/elements-mcp-server --target <tool>
```

Then select `remove-unused-apex`.

## Start and resume

Try one of these prompts:

- “Find the Apex my org can safely remove.”
- “We're near the Apex character limit. What can we reclaim?”
- “Resume my unused-Apex review.”

At kickoff, provide:

- The banner from **Setup > Apex Classes**, pasted into the conversation or shared as a screenshot. It shows the percentage used and allocation; include the exact current character count when the banner provides it.
- Your capacity target: a percentage of the allocation to free, a target usage percentage, or a number of characters. A target usage percentage needs the exact current character count. If the banner omits it, the playbook asks you once to restate the target as a percentage to free or a number of characters.
- When more than one Elements reference model is visible, choose the model for the production org. With one model, the playbook selects it and tells you.
- If the bundle-host check fails, ask your IT team to allow the host the playbook names.

The engagement state is saved in `execution-state.json` in the working directory you establish at kickoff. To continue later, say “resume”; the playbook reads that file and continues from its recorded card. Keep the file and its working directory together.

## Stages at a glance

| Stage | What happens and what you do |
|---|---|
| 00 Kickoff | Provide the Setup Apex Classes banner and capacity target; establish the working directory for the engagement state file. |
| 01 Check prerequisites | Confirm the production model, completed sync, tools, Event Monitoring, Python 3, and bundle-host access. Resolve any missing input or blocker. |
| 02 Obtain candidates | Elements builds the candidate bundle. The playbook checks telemetry coverage, measures the effective window, and selects dependency-complete packages toward your target. |
| 03 Reason over candidates | The playbook checks selected class names for string references and assesses evidence and reasons for doubt. Deferred candidates stay outside this round's review. |
| 04 Review the list | Name the human reviewer. Review the page and rule on every displayed candidate with **remove**, **keep**, **annotate**, or **decide-later**. When the reviewer declares the review finished, any displayed candidate still without a ruling is recorded as **decide-later**. |
| 05 Plan removal | The playbook prepares and checks the plan from confirmed rulings. Accept a shortfall, or request another selection round when more candidates can be selected. |
| 06 Blocked recovery | Review the recorded blocker and its owner. Once the condition is resolved, resume; the playbook verifies it and restarts the applicable checks. |

A reviewer may rule in the review page, return its exported file, or provide rulings in conversation. Candidates not displayed in the review page have no ruling and remain unruled.

## What you get

- A self-contained HyperText Markup Language (HTML) review page showing selected packages, evidence, uncertainty, the telemetry window, and blind spots. A published artifact is used when the host provides that surface; otherwise, review the local file.
- A comma-separated values (CSV) export of the reviewer's rulings, `dispositions.csv`.
- Markdown removal stories for planned deletion units and separate annotation stories for eligible test-only classes. Removal stories put consumers before providers for reading order and group each tranche as one deployment.
- A deployment manifest for each tranche, with `package.xml` and `destructiveChangesPost.xml` intended for the same deployment.
- A validate-only release command in the removal and test-rewrite stories. It validates the exact manifest with all local tests:

  ```text
  sf project deploy start --manifest package.xml --post-destructive-changes destructiveChangesPost.xml --test-level RunLocalTests --dry-run
  ```

- A closing report covering the telemetry window, candidate set, rulings, capacity totals, target outcome, tranches, quarantine, blind spots, validation, and release gate.
- Capacity forecasts for planned removals and annotations. Confirmed realized capacity is measured after deployment by comparing the Salesforce Tooling delta with the movement in the Setup Apex Classes figure. The report confirms realized capacity only when those figures reconcile within the method's 600-character tolerance.

## Tools it uses

Playbook-specific Elements tools:

- `has_event_monitoring`: checks whether daily Apex event logs are available for the org.
- `get_unused_apex_candidates`: computes the candidate bundle, execution and dependency evidence, telemetry ledger, blind spots, and capacity summary.

Core Elements tools also called by the cards:

- `list_reference_models`: finds the org's reference model and reports its sync status.
- `get_dependencies`: reads dependency relationships and targeted evidence for review.
- `code_search`: searches selected class names for string references.
- `get_metadata_node`: resolves non-Apex referrer names for removal planning.
- `get_node_change_history`: retrieves a class's change history when the reviewer requests that evidence.

## Data handling

- The engagement directory stores `execution-state.json`, the local state and progress record.
- The `work/` folder stores the downloaded candidate bundle and intermediate files used for analysis and planning.
- The review page and stories contain org class names and evidence. The review page also shows descriptions and automation summaries; reviewer notes may include anything the reviewer typed.
- The candidate bundle link is short-lived. The playbook downloads the bundle promptly and never stores the link.
- The playbook makes no changes in Salesforce.
- Before sharing the review page or stories, check the class names, metadata summaries, notes, and anything the reviewer typed. These files contain information from your org.

## Tested with

- Claude: CLI and Cowork.
- ChatGPT (Work).
- Codex: CLI.
- Other tools are untested.

## Version

Version 1.0.0.
