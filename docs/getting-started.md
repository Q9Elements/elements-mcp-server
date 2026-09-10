# Get started

Connect your AI assistant to the Elements MCP server so it can query your Space and connected Salesforce Org on your behalf. Every config below is URL-only; sign-in happens through your browser the first time you use a tool.

## Prerequisites

- MCP access is a licensed feature that Elements enables per Space.
- An MCP client. Any client that supports remote MCP servers over Streamable HTTP with the MCP specification's OAuth 2.1 + PKCE authorization flow should work; Elements has been tested with Claude, Codex, and Cursor. Setup steps for common clients are below.
- Your Space's plan determines what's available: most metadata analysis needs a **Pro** Space, metadata queries and custom views need **Enterprise**, and org-health analytics need an **Analytics Cloud** license; and some capabilities carry their own license (AI Analysis, Change Monitoring, Decision Engine, story generation). See the Requires column in [tools-reference](tools-reference.md), or the per-skill Requires lines in [skills.md](skills.md).

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

Then run `/mcp` to complete sign-in.

If you only want the MCP server (no skills), add it directly:

```
claude mcp add --transport http elements https://<your-host>/api/v1/mcp
```

### Claude Desktop / claude.ai

Claude Desktop and claude.ai connect to remote MCP servers through the same connector UI:

1. Open 'Settings' → 'Connectors'.
2. Click 'Add custom connector'.
3. Enter a name (for example, `Elements`) and the MCP endpoint URL from the table above.
4. Click 'Add', then follow the sign-in prompt.

If you don't see 'Add custom connector', your Claude plan or organization settings may not allow custom connectors; check Anthropic's current documentation.

On Claude Desktop, get the skills separately with `npx skills add -g Q9Elements/elements-mcp-server`. On claude.ai the connector alone is enough; your assistant uses the tools directly.

### Codex

Install the skills with the plugin:

```
codex plugin marketplace add Q9Elements/elements-mcp-server
```

Then install `elements` from the list.

Add the MCP server separately, using the endpoint for your instance from the table above:

```
codex mcp add elements --url https://<your-host>/api/v1/mcp
codex mcp login elements
```

The plugin deliberately doesn't bundle the MCP server: the Codex plugin format accepts only a fixed URL, and the right endpoint depends on which Elements instance your Org is on.

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

Get the skills with `npx skills add Q9Elements/elements-mcp-server`.

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
cp -r elements-mcp-server/skills/* <your agent's skills directory>/
```

Common skills directories: `~/.claude/skills/` (Claude Code, user scope), `.claude/skills/` (Claude Code, project scope), `.agents/skills/` (Codex). Then add the MCP server with the URL-only config for your client above.

## Sign in and consent

The first time your client calls a tool, it opens your browser to log in with your existing Elements credentials. Review the client, then choose which Space(s) the connection can use and approve. The Space selection is the one choice you make; scopes are fixed and identical for every connection. Only the Spaces you select are ever available to that connection; new Spaces are never added automatically.

You can review or revoke the connection at any time from the 'Connected apps' tab of your Elements profile; see [security](security.md#managing-and-revoking-connections).

## Verify it's working

Ask your assistant something simple, such as "list my Elements Spaces" or "what Space am I in?" A working connection returns your Space list or the active Space without any further prompts.

## Your first 10 minutes

Once connected, work up from a single node to a whole-org view; each prompt is labeled with what the Space needs:

1. **"Show me the metadata for the Account object, and what depends on it."**: metadata detail and dependency tracing *(Pro Space)*
2. **"Explain what the [name] flow does, in plain English."**: automation explained as a narrative *(Pro Space + GPT features)*
3. **"What changed in the org this week? Anything unusual?"**: a change briefing with velocity and anomalies *(Pro Space + Analytics Cloud license)*
4. **"Run an org health diagnostic and tell me where to look first."**: the full five-dimension baseline *(Pro Space + Analytics Cloud license)*

If a prompt reports a missing capability, that's licensing, not a fault; see [troubleshooting](troubleshooting.md). The full menu, with more example prompts per skill, is in [skills.md](skills.md).

## Next steps

- [`skills.md`](skills.md): the full capability catalog, with example prompts for each skill.
- [`authentication.md`](authentication.md): how the OAuth 2.1 sign-in flow works.
- [`scopes.md`](scopes.md): the fixed set of scopes every connection holds.
- [`troubleshooting.md`](troubleshooting.md): common connection issues.
