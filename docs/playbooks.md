# Playbooks

A playbook is a separate plugin that runs one well-defined Salesforce process end to end with the Elements Model Context Protocol (MCP) server and your org's real evidence from Elements. It works in stages you can pause and resume, with points where a person makes a decision, and hands back an analysis and deliverables such as stories. It analyzes only; you make every change in Salesforce.

A skill answers a question or does one task. A playbook guides a multi-stage engagement with decision points and saved progress.

Each playbook needs the core `elements` plugin installed and connected to the Elements MCP server. A playbook adds no MCP server or app of its own. Playbooks that run scripts need Python 3 where the tool runs. See each playbook page for its plan and license requirements.

## Install a playbook

- **Claude Code:** run `/plugin install remove-unused-apex@elements` after adding the `Q9Elements/elements-mcp-server` marketplace.
- **Claude Desktop / claude.ai:** from the same marketplace, open 'Customize' → 'Plugins' → 'Yours' or 'Discover', then install the playbook.
- **Codex:** run `codex plugin add remove-unused-apex@elements` after adding the `Q9Elements/elements-mcp-server` marketplace.
- **ChatGPT:** upload [`remove-unused-apex.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/remove-unused-apex.zip) from the repository's `dist` folder. You do not need 'Add app'; the playbook uses the Elements app from the core plugin.
- **Cursor, VS Code, and other tools:** run `npx plugins add Q9Elements/elements-mcp-server --target <tool>` and select the playbook.

## Playbooks

| Playbook | Purpose | Tested tools | Full page |
|---|---|---|---|
| `remove-unused-apex` | Find the Apex your Salesforce org can safely remove. | Claude: CLI and Cowork; ChatGPT (Work); Codex: CLI | [Remove Unused Apex](../plugins/remove-unused-apex/README.md) |
