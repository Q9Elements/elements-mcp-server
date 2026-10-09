# Elements MCP server

The Elements MCP server lets your AI assistant securely query your Elements Space and connected Salesforce Org (metadata, dependencies, access, automation, tech debt, and more) using your existing Elements permissions. Connect once with a browser sign-in; no API keys or secrets to manage.

## What you need

- **MCP enabled for your Space**: MCP access is a licensed feature that Elements enables per Space.
- **An MCP client**: any client that supports remote MCP servers over Streamable HTTP with the MCP specification's OAuth 2.1 + PKCE authorization flow; tested with Claude (CLI and Cowork), Codex CLI, ChatGPT (Work), and Cursor.
- **The right plan**: most metadata analysis needs a **Pro** Space; metadata queries and custom views need **Enterprise**; org-health analytics need an **Analytics Cloud** license; and some capabilities carry their own license (AI Analysis, Dependency Explorer, Org-to-Diagram, Change Tickets, story generation, Decision Engine). See the Requires column in [`docs/tools-reference.md`](docs/tools-reference.md).

## What you can do

Elements Skills package the MCP server's tools into ready-to-use capabilities. Ask your assistant in plain language and it picks the right skill.

**Understand your org** (available now)

| Skill | What it does |
|---|---|
| [`elements-spaces`](plugins/elements/skills/elements-spaces/SKILL.md) | List, switch, and create Elements Spaces |
| [`elements-metadata`](plugins/elements/skills/elements-metadata/SKILL.md) | Explore and explain Salesforce metadata: objects, fields, flows, triggers, automation |
| [`elements-access`](plugins/elements/skills/elements-access/SKILL.md) | Audit who has access to a metadata node, and why |
| [`elements-metadata-query`](plugins/elements/skills/elements-metadata-query/SKILL.md) | Build ad-hoc filtered lists of metadata and save them as custom views |
| [`elements-org-diagnostic`](plugins/elements/skills/elements-org-diagnostic/SKILL.md) | Run a full org health diagnostic across structure, automation, tech debt, compliance, and governance |
| [`elements-change-briefing`](plugins/elements/skills/elements-change-briefing/SKILL.md) | Report every metadata node created or updated in a date window, with velocity and anomaly highlights |
| [`elements-tech-debt`](plugins/elements/skills/elements-tech-debt/SKILL.md) | Deep-dive tech debt: resolve flagged nodes, check blast radius, produce a remediation list |
| [`elements-package-uninstall`](plugins/elements/skills/elements-package-uninstall/SKILL.md) | Plan a Salesforce managed-package removal: inventory components, sweep dependencies, produce a sequenced removal plan |
| [`elements-agent-opportunities`](plugins/elements/skills/elements-agent-opportunities/SKILL.md) | Scan the whole Org to find, rank, and justify agentic opportunities |

**Across your orgs** (available now)

| Skill | What it does |
|---|---|
| [`elements-multi-org-analytics`](plugins/elements/skills/elements-multi-org-analytics/SKILL.md) | Compare every org in your Space: dated snapshots plus a self-contained HTML report whose numbers trace to the raw responses |

**Model & decide** (available now)

| Skill | What it does |
|---|---|
| [`elements-decision-engine`](plugins/elements/skills/elements-decision-engine/SKILL.md) | Plan automation or schema changes, trace field references and runtime fire chains with the [field-change recipe](plugins/elements/skills/elements-decision-engine/references/field-change.md), and draft a backlog |
| [`elements-metafields`](plugins/elements/skills/elements-metafields/SKILL.md) | Define and populate custom fields on Salesforce metadata in Elements, including dependent picklists and bulk classifications |
| [`elements-org-to-process`](plugins/elements/skills/elements-org-to-process/SKILL.md) | Generate a Salesforce lifecycle object's process diagram straight from synced org metadata |

**Deliver the change** (available now)

| Skill | What it does |
|---|---|
| [`elements-diagrams`](plugins/elements/skills/elements-diagrams/SKILL.md) | Generate, read, export, edit, and re-import Elements process-map diagrams |
| [`elements-stories`](plugins/elements/skills/elements-stories/SKILL.md) | List existing user stories and generate new ones from a process diagram's activities |

More skills for Model & decide and Deliver the change ship over time.

See [`docs/skills.md`](docs/skills.md) for the full capability catalog with example prompts.

## Install

Pick whichever front door matches your client; sign-in happens via your browser the first time you use a tool.

**Claude Code (skills + MCP server):**
```
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements@elements
```

**Codex (skills, then the MCP server):**
```
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements@elements
codex mcp add elements --url https://<your-host>/api/v1/mcp
codex mcp login elements
```
Get `<your-host>` from the [App URL to MCP endpoint table](#which-host) below. Start Codex and invoke a skill such as `$elements-spaces`; run `/skills` to turn on any Elements skills that aren't listed.

**ChatGPT (skills + MCP server):** download [`elements.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements.zip) from the repository's `dist` folder and upload it on ChatGPT's 'Plugins' page, then add the MCP server as an app with your endpoint URL. See the [ChatGPT setup steps](docs/getting-started.md#chatgpt).

**Cursor (skills + MCP server):** get the skills with `npx plugins add Q9Elements/elements-mcp-server --target cursor` and select `elements` when the plugin list appears, then click the button that matches the URL in your browser when you are logged into Elements:

- **app.q9elements.com** (most customers): [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5xOWVsZW1lbnRzLmNvbS9hcGkvdjEvbWNwIn0=)
- **app.us.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS51cy5lbGVtZW50cy5jbG91ZC9hcGkvdjEvbWNwIn0=)
- **app.ja1.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5qYTEuZWxlbWVudHMuY2xvdWQvYXBpL3YxL21jcCJ9)
- **app.me1.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5tZTEuZWxlbWVudHMuY2xvdWQvYXBpL3YxL21jcCJ9)

**Other agent tools:** GitHub Copilot CLI, Grok Build, and Kimi Code get the skills with `npx plugins add Q9Elements/elements-mcp-server --target <tool>`; use `github-copilot`, `grok`, or `kimi` as the target, and select `elements` when the plugin list appears. Add the MCP server per that tool's instructions, using the endpoint from the [host table](#which-host).

See [`docs/getting-started.md`](docs/getting-started.md) for Claude Desktop, ChatGPT, VS Code, and manual MCP-only setup.

## Which host?

Elements runs on multiple instances. The MCP endpoint depends on which instance your Elements Org lives on; **match the URL you see in your browser when you're logged into Elements**, not your location:

| App URL (what's in your browser) | MCP endpoint |
|---|---|
| app.q9elements.com | `https://api.q9elements.com/api/v1/mcp` |
| app.us.elements.cloud | `https://api.us.elements.cloud/api/v1/mcp` |
| app.ja1.elements.cloud | `https://api.ja1.elements.cloud/api/v1/mcp` |
| app.me1.elements.cloud | `https://api.me1.elements.cloud/api/v1/mcp` |

## Learn more

- [`docs/skills.md`](docs/skills.md): the full capability catalog
- [`docs/getting-started.md`](docs/getting-started.md): per-client connect instructions
- [`docs/authentication.md`](docs/authentication.md): the OAuth 2.1 sign-in flow
- [`docs/scopes.md`](docs/scopes.md): connection scopes
- [`docs/tools-reference.md`](docs/tools-reference.md): the underlying tool reference
- [`docs/playbooks.md`](docs/playbooks.md): install and use playbook plugins
- [`docs/security.md`](docs/security.md): security overview
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common issues

## What's in this repository

Every installable plugin is a peer directory under `plugins/`, and each one carries its own
manifest. Nothing outside `plugins/` is a plugin component, so `ls plugins/` is the complete list
of what this repository ships.

| Plugin | Role | Install |
|---|---|---|
| [`elements`](plugins/elements/) | The runtime library: the MCP server plus the skills documented above, which are read-only against Salesforce. | `/plugin install elements@elements` |
| [`remove-unused-apex`](plugins/remove-unused-apex/) | A playbook: selects dependency-complete packages toward the capacity target, collects package rulings, and hands back dependency-ordered removal and annotation stories. Analysis only; the customer executes every change. | [Install for your tool](docs/playbooks.md) |

Install playbook plugins separately from the core plugin; see [docs/playbooks.md](docs/playbooks.md) for instructions for each tool.

The root holds the plugin catalogue at `.claude-plugin/marketplace.json`, the MCP server's
published surface (`docs/`, `llms.txt`, and this file), and `dist/`, which carries one zip per plugin
for ChatGPT, built from `plugins/` at each release.

## License

Apache License 2.0; see [LICENSE](LICENSE). This license covers the skills, docs, and packaging in this repository; the Elements MCP server itself is a hosted service operated by Elements.cloud.
