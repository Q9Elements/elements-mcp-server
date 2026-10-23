# Data Load Impact

This playbook turns a planned Salesforce bulk data load into a ratified pre-load safety package, an optional small-batch sandbox rehearsal, and an ordered backlog the customer executes. The data-load owner sees reasons to rehearse and chooses whether to do it. When the owner chooses rehearsal and the Salesforce command-line interface (sf CLI) is signed in to a verified rehearsal sandbox and can match the ratified parameters, the playbook runs the small test batch and captures its evidence. It slices up to 200 rows from the local comma-separated value (CSV) source, names the checklist actions and signed-in CLI user, and waits for the customer's `applied` reply before each load. On a chosen manual path, the customer runs the batch. On the CLI path, the rehearsal report names the CLI user and the production-user sharing and bypass behavior that the rehearsal did not exercise. The playbook never performs the production load or changes Salesforce metadata.

## Prerequisites

- The requirements for the core Elements plugin. Core plan subscribers also need the Automation & Execution Intelligence add-on.
- Access to the `run_data_load_impact`, `list_reference_models`, `get_space_context`, `list_metadata_by_criteria`, `search_metadata`, `get_metadata_component`, `get_metadata_source`, and `explain_metadata_components` tools.
- Python 3 using the standard library only.
- A host that can run the shipped local scripts, such as Claude Code or the Claude app, with network access to Amazon Simple Storage Service (S3) for source downloads.
- Privacy: in the Claude app, an attached file may be read into the conversation. For a file with real rows, run the playbook in Claude Code, or attach a copy that has only the columns the load writes.
- A full-copy sandbox when the owner chooses the recommended small-batch rehearsal.
- Optional: sf CLI signed in to that rehearsal sandbox. Without it, the customer runs the rehearsal manually and supplies the same-job debug logs, success file, and error file.
- A named data-load owner, planned source path or Salesforce Object Query Language (SOQL) file, and local access to any comma-separated value (CSV) files, debug logs, and the rehearsal loader success and error files when rehearsing.

## Install

### Claude Code

```text
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements-data-load-impact@elements
```

To start a new engagement, ask: "Plan the impact of my Salesforce data load." Run this from the directory that will hold the engagement. To resume, open that directory and ask: "Resume my in-progress data-load impact engagement."

### Codex

```text
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements-data-load-impact@elements
```

To start a new engagement, ask: "Help me rehearse my planned Salesforce data load." Run this from the directory that will hold the engagement. To resume, open that directory and ask: "Resume my in-progress data-load impact engagement."

## Run

Invoke the `data-load-impact` skill with the planned load from the session working directory. The kickoff card copies `templates/execution-state.json` into that directory and gathers the kickoff slots once. The engagement name is the source file name plus the current date. To resume, open the engagement directory and use its `execution-state.json`. On every entry to card 02, the data-load owner confirms the loader and proposed manifest in one exchange. A manual rehearsal of a query-defined load uses at most `rehearsal_batch_rows` rows of the query result.

The bypass auditor reads downloaded metadata source files locally; the session sees up to two quoted source lines per automation, one for evidence and one for non-firing evidence. Raw CSV rows, SOQL results, and debug-log lines stay on the customer's machine. Bypass instructions and report groups distinguish load-user hooks from switches that affect every user. Owner-added steps reach their named stories with the ruling time; rollback exports appear in pre-load setup. Downstream automation types come from bundle nodes and the local source manifest. The terminal deliverables are `report/final-report.md` and five or six ordered Markdown files under `stories/`.

Claude Code honors `model: sonnet` for the bypass auditor and `model: haiku` for the organization context exporter agent. Claude app (Cowork) support for the model field is unconfirmed. Copilot support for these plugin agents is unconfirmed. A host that ignores the field runs the agent on the session model.
