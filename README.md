# Elements MCP server

The Elements MCP server lets your AI assistant securely query your Elements Space and connected Salesforce Org (metadata, dependencies, access, automation, tech debt, and more) using your existing Elements permissions. Connect once with a browser sign-in; no API keys or secrets to manage.

## What you need

- **MCP enabled for your Space**: MCP access is a licensed feature that Elements enables per Space.
- **An MCP client**: any client that supports remote MCP servers over Streamable HTTP with the MCP specification's OAuth 2.1 + PKCE authorization flow; tested with Claude, Codex, and Cursor.
- **The right plan**: most metadata analysis needs a **Pro** Space; metadata queries and custom views need **Enterprise**; org-health analytics need an **Analytics Cloud** license; and some capabilities carry their own license (AI Analysis, Dependency Explorer, Org-to-Diagram, Change Tickets, story generation). See the Requires column in [`docs/tools-reference.md`](docs/tools-reference.md).

## What you can do

Elements Skills package the MCP server's tools into ready-to-use capabilities. Ask your assistant in plain language and it picks the right skill.

**Understand your org** (available now)

| Skill | What it does |
|---|---|
| [`elements-spaces`](skills/elements-spaces/SKILL.md) | List, switch, and create Elements Spaces |
| [`elements-metadata`](skills/elements-metadata/SKILL.md) | Explore and explain Salesforce metadata: objects, fields, flows, triggers, automation |
| [`elements-access`](skills/elements-access/SKILL.md) | Audit who has access to a metadata node, and why |
| [`elements-metadata-query`](skills/elements-metadata-query/SKILL.md) | Build ad-hoc filtered lists of metadata and save them as custom views |
| [`elements-org-diagnostic`](skills/elements-org-diagnostic/SKILL.md) | Run a full org health diagnostic across structure, automation, tech debt, compliance, and governance |
| [`elements-change-briefing`](skills/elements-change-briefing/SKILL.md) | Report every metadata change in a date window, with velocity and anomaly highlights |
| [`elements-tech-debt`](skills/elements-tech-debt/SKILL.md) | Deep-dive tech debt: resolve flagged nodes, check blast radius, produce a remediation list |
| [`elements-package-uninstall`](skills/elements-package-uninstall/SKILL.md) | Plan a Salesforce managed-package removal: inventory components, sweep dependencies, produce a sequenced removal plan |
| [`elements-agent-opportunities`](skills/elements-agent-opportunities/SKILL.md) | Scan the whole Org to find, rank, and justify agentic opportunities |

**Model & decide** (available now)

| Skill | What it does |
|---|---|
| [`elements-metafields`](skills/elements-metafields/SKILL.md) | Define and populate custom fields on Salesforce metadata in Elements, including dependent picklists and bulk classifications |
| [`elements-org-to-process`](skills/elements-org-to-process/SKILL.md) | Generate a Salesforce lifecycle object's process diagram straight from synced org metadata |

**Deliver the change** (available now)

| Skill | What it does |
|---|---|
| [`elements-diagrams`](skills/elements-diagrams/SKILL.md) | Generate, read, export, edit, and re-import Elements process-map diagrams |
| [`elements-stories`](skills/elements-stories/SKILL.md) | List existing user stories and generate new ones from a process diagram's activities |

More skills for Model & decide and Deliver the change ship over time.

See [`docs/skills.md`](docs/skills.md) for the full capability catalog with example prompts.

## Install

Pick whichever front door matches your client. Each connects both the skills and the MCP server; sign-in happens via your browser the first time you use a tool.

**Any agent (skills only), via the cross-vendor Agent Skills CLI:**
```
npx skills add Q9Elements/elements-mcp-server
```

**Claude Code (skills + MCP server):**
```
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements@elements
```

**Codex (skills + MCP server):**
```
codex plugin marketplace add Q9Elements/elements-mcp-server
```
then install `elements` from the list, and run `codex mcp login elements`.

**Cursor (skills + MCP server):** get the skills with `npx skills add Q9Elements/elements-mcp-server`, then click the button that matches the URL in your browser when you are logged into Elements:

- **app.q9elements.com** (most customers): [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5xOWVsZW1lbnRzLmNvbS9hcGkvdjEvbWNwIn0=)
- **app.us.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS51cy5lbGVtZW50cy5jbG91ZC9hcGkvdjEvbWNwIn0=)
- **app.ja1.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5qYTEuZWxlbWVudHMuY2xvdWQvYXBpL3YxL21jcCJ9)
- **app.me1.elements.cloud**: [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=elements&config=eyJ1cmwiOiJodHRwczovL2FwaS5tZTEuZWxlbWVudHMuY2xvdWQvYXBpL3YxL21jcCJ9)

See [`docs/getting-started.md`](docs/getting-started.md) for Claude Desktop, VS Code, and manual MCP-only setup.

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
- [`docs/security.md`](docs/security.md): security overview
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common issues

## License

Apache License 2.0; see [LICENSE](LICENSE). This license covers the skills, docs, and packaging in this repository; the Elements MCP server itself is a hosted service operated by Elements.cloud.
