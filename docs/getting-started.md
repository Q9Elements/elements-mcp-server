# Get started

Connect your AI assistant to the Elements MCP server so it can query your Space and connected Salesforce Org on your behalf. Every config below is URL-only; sign-in happens through your browser the first time you use a tool.

## Prerequisites

- MCP access is a licensed feature that Elements enables per Space.
- An MCP client. Any client that supports remote MCP servers over Streamable HTTP with the MCP specification's OAuth 2.1 + PKCE authorization flow should work; Elements has been tested with Claude (CLI and Cowork), Codex CLI, ChatGPT (Work), and Cursor. Setup steps for common clients are below.
- Your Space's plan determines what's available: most metadata analysis needs a **Pro** Space, metadata queries and custom views need **Enterprise**, and org-health analytics need an **Analytics Cloud** license; and some capabilities carry their own license (AI Analysis, Dependency Explorer, Org-to-Diagram, Change Tickets, story generation, Decision Engine). See the Requires column in [tools-reference](tools-reference.md), or the per-skill Requires lines in [skills.md](skills.md).

## Find your MCP endpoint

Elements runs on multiple instances, and the MCP endpoint depends on which instance your Org lives on. Match the URL you see in your browser when you're logged into Elements; don't guess based on where you're located:

| App URL (what's in your browser) | MCP endpoint |
|---|---|
| app.q9elements.com | `https://api.q9elements.com/api/v1/mcp` |
| app.us.elements.cloud | `https://api.us.elements.cloud/api/v1/mcp` |
| app.ja1.elements.cloud | `https://api.ja1.elements.cloud/api/v1/mcp` |
| app.me1.elements.cloud | `https://api.me1.elements.cloud/api/v1/mcp` |

The config snippets below use `<your-host>` as a placeholder for the host from this table.

## Connect your client

### Claude Code

Install the skills and the MCP server together with the plugin:

```
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements@elements
```

During installation, the plugin asks for 'Elements API host'. Enter the host from the endpoint table above, for example `api.q9elements.com`. If you skipped this prompt, run `/plugin configure elements@elements`.

Then run `/mcp`, choose 'elements', and approve access in the browser tab.

### Claude Desktop / claude.ai

Claude Desktop and claude.ai use the same plugin and connector UI:

1. Open 'Customize' → 'Plugins', click '+ Add' → 'Add marketplace', and enter `Q9Elements/elements-mcp-server`.
2. Under 'Plugins' → 'Yours', open 'Elements' and go to its 'Connectors' tab.
3. Next to 'elements', click 'Add for your team'.
4. The URL field shows `https://${user_config.apiHost}/api/v1/mcp`. Replace `${user_config.apiHost}` with your host from the endpoint table above, so the URL reads, for example, `https://api.q9elements.com/api/v1/mcp`; then click 'Continue' and follow the prompts to sign in and approve access.

Your Claude plan or organization settings may not allow adding the connector; check Anthropic's current documentation.

### Codex

Install the skills with the plugin:

```
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements@elements
codex mcp add elements --url https://<your-host>/api/v1/mcp
codex mcp login elements
```

Start Codex and invoke a skill with `$`, for example `$elements-spaces`. If the Elements skills aren't listed, run `/skills` and turn them on.

The plugin deliberately doesn't bundle the MCP server: the Codex plugin format accepts only a fixed URL, and the right endpoint depends on which Elements instance your Org is on.

### ChatGPT

ChatGPT has no plugin marketplace; the zip installs the Elements skills only. Add the MCP server separately as an app, using the endpoint for your Elements instance from the table above.

1. Download [`elements.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements.zip) from the repository's `dist` folder.
2. ChatGPT rejects an upload as a duplicate if the plugin name remains on your account, even after uninstalling it; logging out and back in refreshes the plugin list. If an older Elements plugin is installed, uninstall it from 'Plugins' → 'Personal' → the plugin's '…' menu → 'Uninstall', then log out of ChatGPT and back in.
3. On the 'Plugins' page, click '+', upload `elements.zip`, then install it.
4. Open the plugin and click 'Add app'. Enter a name, for example `Elements`, set 'Server URL' to the MCP endpoint for your instance from the table above, leave 'Authentication' as 'OAuth', tick 'I understand and want to continue', then click 'Create'.
5. Sign in: go to 'Plugins' → 'Personal' → the plugin's '…' menu → 'Manage' → '…' → 'View plugin detail' → the app under 'App' → '…' → 'Manage' → 'Connect' (or 'Connect another account') → 'Sign in with <app name>'. Then sign in to Elements and approve access.
6. Try it: `@Elements.cloud List my Elements.cloud spaces.` If the plugin or its tools don't appear, log out of ChatGPT and back in.
7. To update, download the new `elements.zip` and use the app's '…' → 'Upload new version', or uninstall and upload again.

### Cursor

Add an entry to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "elements": {
      "url": "https://<your-host>/api/v1/mcp"
    }
  }
}
```

Cursor completes the sign-in automatically the first time you use a tool. An Add-to-Cursor button for each instance is also available in the [README](../README.md), if you'd rather not edit the file by hand.

Get the skills with `npx plugins add Q9Elements/elements-mcp-server --target cursor`; select `elements` when the plugin list appears.

### VS Code (Copilot)

Add an entry to `.vscode/mcp.json` in your workspace (or to your user profile's `mcp.json` for every workspace):

```json
{
  "servers": {
    "elements": {
      "type": "http",
      "url": "https://<your-host>/api/v1/mcp"
    }
  }
}
```

VS Code prompts you to start the server, then signs you in through your browser the first time you use a tool. VS Code supports the OAuth 2.1 dynamic client registration flow the MCP server uses, so you provide only the URL, no client ID or secret.

Get the skills with `npx plugins add Q9Elements/elements-mcp-server --target vscode`; select `elements` when the plugin list appears. Agent plugins are a Preview feature in VS Code, so turn on the `chat.plugins.enabled` setting if your organization manages it.

### Microsoft Copilot Studio

Copilot Studio connects through a custom connector, and its setup differs from every other client in one way that matters: the OAuth client is registered when the *maker* creates the connector, but nobody signs in until an end user creates a connection, which is a separate, later step. Follow Microsoft's [Connect your agent to an existing MCP server](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent) for the current UI, with these Elements specifics:

- Use the MCP endpoint for your instance from the table above as the server URL.
- Choose **OAuth 2.0** authentication and the **Dynamic** option, for servers that support dynamic client registration. Elements supports it (RFC 7591), so there is no client ID or secret to create and nothing to configure on the Elements side. If the connector asks for authorization and token URLs explicitly, take them from `https://<your-host>/.well-known/oauth-authorization-server`.
- Elements accepts the Power Platform consent redirect (`https://global.consent.azure-apim.net/redirect/...`) as part of that registration; you don't need to allowlist it anywhere in Elements.
- **Create a connection and sign in within 24 hours of saving the connector.** Do it yourself as soon as the connector is saved; don't leave the first sign-in for users to do later.

> **Why the 24-hour deadline matters.** A client registration that has never completed a sign-in is discarded after 24 hours. Because Copilot Studio registers the client at connector-creation time, a connector that is built and then handed over days later fails with `invalid_client` (*"The client_id is not registered"*), which reads like a broken configuration rather than an expiry. The fix is to recreate the connector and sign in straight away. Once any user has signed in successfully the registration is permanent and this never applies again.

### Manual install (no npm, no plugin system)

The skills are plain folders of Markdown; you can install them with nothing but git:

```
git clone https://github.com/Q9Elements/elements-mcp-server
cp -r elements-mcp-server/plugins/elements/skills/* <your agent's skills directory>/
```

Common skills directory: `.agents/skills/` (Codex). Then add the MCP server with the URL-only config for your client above. Claude Code, Claude Desktop, and claude.ai use the [Claude Code](#claude-code) and [Claude Desktop / claude.ai](#claude-desktop--claudeai) plugin setup above.

## Sign in and consent

The first time your client calls a tool, it opens your browser to log in with your existing Elements credentials. Review the client, then choose which Space(s) the connection can use and approve. Clients are offered the same full scope set by default, though a client may request fewer; you never pick scopes. Only the Spaces you select are ever available to that connection; new Spaces are never added automatically. To change which Spaces a connection can use, revoke it and reconnect.

You can review or revoke the connection at any time from the 'Connected apps' tab of your Elements profile; see [security](security.md#managing-and-revoking-connections).

## Verify it's working

Ask your assistant something simple, such as "list my Elements Spaces" or "what Space am I in?" A working connection returns your Space list or the active Space without any further prompts.

## Your first 10 minutes

Once connected, work up from a single node to a whole-org view; each prompt is labeled with what the Space needs:

1. **"Show me the metadata for the Account object, and what depends on it."**: metadata detail and dependency tracing *(Pro Space)*
2. **"Explain what the [name] flow does, in plain English."**: automation explained as a narrative *(Pro Space + AI Analysis license + GPT features)*
3. **"What changed in the org this week? Anything unusual?"**: a change briefing with velocity and anomalies *(Pro Space + Analytics Cloud license)*
4. **"Run an org health diagnostic and tell me where to look first."**: the full five-dimension baseline *(Pro Space + Analytics Cloud license)*

If a prompt reports a missing capability, that's licensing, not a fault; see [troubleshooting](troubleshooting.md). The full menu, with more example prompts per skill, is in [skills.md](skills.md).

## Next steps

- [`skills.md`](skills.md): the full capability catalog, with example prompts for each skill.
- [`multi-org-analytics.md`](multi-org-analytics.md): comparing all the orgs in your Space, and keeping the comparison fresh.
- [`authentication.md`](authentication.md): how the OAuth 2.1 sign-in flow works.
- [`scopes.md`](scopes.md): the scope families clients are offered by default and the checks applied to every tool call.
- [`troubleshooting.md`](troubleshooting.md): common connection issues.
