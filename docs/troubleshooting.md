# Troubleshooting

The Elements Model Context Protocol (MCP) server reports access and connection problems with the messages below.

## I can't connect, or no Spaces show up at consent

The most common cause is that the Space isn't licensed for the MCP server yet. MCP is included in Advanced Metadata Management, or in Core Metadata Management with the Agentic Org Management add-on, and Elements enables it per Space. If a Space you expect to see is missing from the consent screen, it isn't licensed yet; once it is, reconnect and it will appear.

## I'm stuck in a sign-in loop

Clear your client's saved Elements authorization and try again. How you do this depends on the client:

- **Claude Code / Claude Desktop / claude.ai**: remove and re-add the MCP connection, or use the client's disconnect/"forget this server" option, then reconnect.
- **Cursor / VS Code / Codex**: remove the server entry from your MCP config, add it back, and sign in again.

A stale or partially completed consent is almost always the cause; a clean reconnect resolves it.

## I get a 401 or 405 error

The MCP endpoint only accepts authenticated `POST` requests. A `GET` without a bearer token (for example, opening the endpoint URL directly in a browser) returns `401 Unauthorized`, because authentication is checked before the method. An authenticated `GET` returns `405 Method Not Allowed` with an `Allow: POST` header. Both are expected, not a sign anything is broken. See [transport](transport.md); make sure your client is configured to `POST` to the endpoint rather than treat it as a page to load.

## I hit a rate limit or a `server_busy` error

The server allows 60 requests per minute per token and also caps each token at 20 concurrent requests. Going over the per-minute limit locks the token for 60 seconds (`rate_limited`), while hitting the concurrency cap (`too_many_concurrent_requests`) just asks you to wait for in-flight calls to finish. On top of that there's a global cap of 128 concurrent requests across all connections; at capacity the server reports `server_busy`. Diagram changes and exports (`manage_diagram`, `create_map`, `create_map_from_template`, `import_diagram`, `export_diagram`) also run one at a time on each server process, so a second one sent at the same moment gets `server_busy` too, with a short `retryAfter`; send the same call again once it has passed. Each of these carries a `retryAfter` in seconds; wait it out in full before resuming, then resume at a slower pace. Retrying early simply fails; it does **not** extend the lockout.

**Watch the error code, not the HTTP status.** Every JSON-RPC request returns **HTTP 200** when it hits one of these limits; that is deliberate, because MCP clients render a non-JSON-RPC status as a generic "server isn't responding" that the model can't react to. For a `tools/call` request the limit arrives as a JSON-RPC result with `isError: true` and the code above; for the other methods (`initialize`, `tools/list`) it arrives as a JSON-RPC `error` object with code `-32000`, carrying the same code and `retryAfter` in its `data`. A real `429` or `503` is reserved for requests that aren't JSON-RPC at all. So a client that triages on status codes alone will see these as ordinary successes; triage on the error code in the payload. In every case, reduce how many tool calls you run in parallel.

## A tool call fails with `tool_timeout`

Large-result behavior depends on the tool. `get_dependencies`, `get_access`, `run_code_search`, `list_metadata_changes`, `list_metadata_by_criteria`, and `get_metadata_source` return their rows as part files. Other read tools answer inline and may move oversized values to a file or shorten a list with a continuation hint. For a timeout, narrow the search, filter, or node selection and retry. See [tools reference](tools-reference.md#large-results).

## I'm connected to more than one Space: how do I pick?

If your connection is authorized for more than one Space, ask your assistant to list them (or call `get_space_context` directly) and tell it which one to use. It can switch the active Space at any point in the conversation with `set_active_space`. See the `elements-spaces` skill.

## I get `active_space_required` or `unauthorized_space`

Both come from Space selection. Elements uses an eligible active Space, eligible default Space, or a single eligible Space when no Space is active. `active_space_required` means no Space could be selected; name an authorized, MCP-enabled Space in your prompt, or ask your assistant to switch with `set_active_space`. `get_space_context` reports the current active Space and authorized Spaces. Asking your assistant to list reference models in a named Space identifies that Space's reference models. `unauthorized_space` means a tool call named a Space outside what you granted at consent; this can happen even when the connection is authorized for only one Space, and the call is rejected. Elements never uses a Space outside the grant. If you need that Space, revoke the connection and reconnect with it included in the grant.

## My assistant says a tool is missing, or a tool call is refused

The tool list depends on the plan and license flags of your authorized Spaces. Role requirements, such as Space admin or Author, are checked when a tool is called; a call without the required role is refused with `access_denied`. And if your connection spans several Spaces, you may see a tool your *current* Space can't use; calling it can return `feature_not_enabled` with the missing plan or feature flag, or `access_denied` naming the required Elements role or resource access. A feature-flag refusal can include a hint to call `get_space_context` and then `set_active_space` when another authorized Space makes the tool available. Role and resource refusals do not always include that hint. See [security](security.md#you-choose-what-a-connection-can-do), check the **Required add-on** column in [tools-reference](tools-reference.md), or switch to a Space with the right access. After an access change, start a new session so your client re-fetches the tool list. Common feature refusals include `Elements MCP is not enabled for this space`, `Requires a Pro Plus space`, `Requires Org AI Analysis add-on`, `Requires Decision Engine add-on`, `Requires Org 2 Process add-on`, `Requires Analytics 360 add-on`, `Requires Dependency Explorer add-on`, `Requires Change Tickets add-on`, `Requires Diagram to Ticket add-on`, and `Requires Elements AI to be enabled for this space`. `Requires a Pro Plus space` means the Space needs a Core or Advanced Metadata Management plan. `Requires Org AI Analysis add-on` means the Space needs the Automation & Execution Intelligence add-on on Core Metadata Management; Advanced Metadata Management includes it. For `Requires Analytics 360 add-on`, quote the returned message verbatim and contact your Elements representative, who can match it to your plan. For any other refusal, contact your Elements representative, who can match it to your plan.

## ChatGPT says a plugin upload is a duplicate

The plugin name can remain on your account after you uninstall it. Log out of ChatGPT and back in. If ChatGPT still refuses the upload, the name is held by an earlier upload.

## A plugin, its skills, or its tools don't appear in ChatGPT

After you upload or connect a plugin, log out of ChatGPT and back in.

## Codex skills aren't listed

Run `/skills` and turn on the Elements skills you need. Invoke a skill with `$`, for example `$elements-spaces`.

## Claude Desktop or claude.ai shows `${user_config.apiHost}` in the connector URL

Replace `${user_config.apiHost}` with your Elements host. See the [Claude Desktop / claude.ai setup](getting-started.md#claude-desktop--claudeai) for the full steps.

## Some Elements tools are silently missing from Cursor's tool list

Cursor drops any tool whose combined user-chosen server key and tool name exceeds 60 characters. Name the server `elements`, the key used throughout these docs, then start a new Cursor session so it re-fetches the tool list.

## How do I disconnect or revoke access?

Removing the server from your client's config stops that client using it, but the server-side grant stays until it expires. Refresh tokens last 30 days from the last refresh, so a connection used at least monthly stays signed in. To revoke it immediately, open your Elements profile, select the 'Connected apps' tab, find the connection, and click 'Revoke'; it takes effect on the very next call. See [security](security.md#managing-and-revoking-connections).

## I'm not sure which host to use

Match the URL you see in your browser when you're logged into Elements, not your location. See the app-URL → host table in the [README](../README.md) or [transport](transport.md).

## Still stuck?

Reach out to your usual Elements contact.
