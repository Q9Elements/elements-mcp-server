# Playbooks

A playbook is a separate plugin that runs one well-defined Salesforce process end to end with the Elements Model Context Protocol (MCP) server and your org's real evidence from Elements. It works in stages you can pause and resume, with points where a person makes a decision, and hands back an analysis and deliverables such as stories. It analyzes only; you make every change in Salesforce.

A skill answers a question or does one task. A playbook guides a multi-stage engagement with decision points and saved progress.

Each playbook needs the core `elements` plugin installed and connected to the Elements MCP server. A playbook adds no MCP server or app of its own. Playbooks that run scripts need Python 3 where the tool runs. See each playbook page for its requirements.

Playbooks are plugins: each one brings its own agents and scripts along with its skill, so playbooks are not included in [`elements-core-skills.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements-core-skills.zip) and can't be installed as loose skills. Install each playbook as a plugin, using the steps for your tool below.

## Install a playbook

- **Claude Code:** run `/plugin install elements-remove-unused-apex@elements`, `/plugin install elements-data-load-impact@elements`, `/plugin install elements-map-and-design@elements` or `/plugin install elements-change-impact@elements` after adding the `Q9Elements/elements-mcp-server` marketplace.
- **Claude Desktop / claude.ai:** from the same marketplace, open 'Customize' → 'Plugins' → 'Yours' or 'Discover', then install the playbook.
- **Codex:** run `codex plugin add elements-remove-unused-apex@elements`, `codex plugin add elements-data-load-impact@elements`, `codex plugin add elements-map-and-design@elements` or `codex plugin add elements-change-impact@elements` after adding the `Q9Elements/elements-mcp-server` marketplace.
- **ChatGPT:** upload the plugin package [`elements-remove-unused-apex.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements-remove-unused-apex.zip) from the repository's `dist` folder. You do not need 'Add app'; the playbook uses the Elements app from the core plugin.
- **Cursor, VS Code, and other tools:** run `npx plugins add Q9Elements/elements-mcp-server --target <tool>` and select the playbook.

## Playbooks

| Playbook | Purpose | Tested tools | Full page |
|---|---|---|---|
| `elements-remove-unused-apex` | Find the Apex your Salesforce org can safely remove. | Claude: command-line interface (CLI) and Cowork; ChatGPT (Work); Codex: CLI | [Remove Unused Apex](../plugins/elements-remove-unused-apex/README.md) |
| `elements-data-load-impact` | Plan a Salesforce data load: what it fires, the safety controls, and an ordered backlog. | Claude: command-line interface (CLI) and the Claude app | [Data Load Impact](../plugins/elements-data-load-impact/README.md) |
| `elements-map-and-design` | Map and design your Salesforce business architecture as Elements diagrams. | Claude: CLI | [Elements Map and Design](../plugins/elements-map-and-design/README.md) |
| `elements-change-impact` | Analyze the impact of a proposed Salesforce automation or schema change. | Codex: command-line interface (CLI) | [Analyze Change Impact](../plugins/elements-change-impact/README.md) |
