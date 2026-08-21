# Troubleshooting

## I can't connect, or no Spaces show up at consent

The most common cause is that the Space isn't enabled for the MCP server yet: MCP access is a licensed feature that Elements enables per Space. If a Space you expect to see is missing from the consent screen, it isn't licensed for MCP yet; once it is, reconnect and it will appear.

## I'm stuck in a sign-in loop

Clear your client's saved Elements authorization and try again. How you do this depends on the client:

- **Claude Code / Claude Desktop / claude.ai**: remove and re-add the MCP connection, or use the client's disconnect/"forget this server" option, then reconnect.
- **Cursor / VS Code / Codex**: remove the server entry from your MCP config, add it back, and sign in again.

A stale or partially completed consent is almost always the cause; a clean reconnect resolves it.

## I get a 401 or 405 error

The MCP endpoint only accepts authenticated `POST` requests. A `GET` without a bearer token (for example, opening the endpoint URL directly in a browser) returns `401 Unauthorized`, because authentication is checked before the method. An authenticated `GET` returns `405 Method Not Allowed` with an `Allow: POST` header. Both are expected, not a sign anything is broken. See [transport](transport.md); make sure your client is configured to `POST` to the endpoint rather than treat it as a page to load.

## I hit a rate limit or a `server_busy` error

The server allows 60 requests per minute per token and also caps each token at 20 concurrent requests. Going over the per-minute limit locks the token for 60 seconds (`rate_limited`), while hitting the concurrency cap (`too_many_concurrent_requests`) just asks you to wait for in-flight calls to finish. On top of that there's a global cap of 128 concurrent requests across all connections; at capacity the server reports `server_busy`. Each of these carries a `retryAfter` in seconds; wait it out in full before resuming, then resume at a slower pace. Retrying early simply fails; it does **not** extend the lockout.

**Watch the error code, not the HTTP status.** Every JSON-RPC request returns **HTTP 200** when it hits one of these limits; that is deliberate, because MCP clients render a non-JSON-RPC status as a generic "server isn't responding" that the model can't react to. For a `tools/call` request the limit arrives as a JSON-RPC result with `isError: true` and the code above; for the other methods (`initialize`, `tools/list`) it arrives as a JSON-RPC `error` object with code `-32000`, carrying the same code and `retryAfter` in its `data`. A real `429` or `503` is reserved for requests that aren't JSON-RPC at all. So a client that triages on status codes alone will see these as ordinary successes; triage on the error code in the payload. In every case, reduce how many tool calls you run in parallel.

## A tool call fails with `tool_timeout`

You shouldn't normally hit this: large result sets are paginated, an oversize result comes back as a compact summary with an explicit way to retrieve the rest, and long-running analyses run asynchronously with a status the skill polls; the Elements skills handle all of that for you. The 30-second execution ceiling exists as a backstop, so a `tool_timeout` usually means one extremely broad query. Narrow it (a more specific search term, a smaller filter, a single node instead of a broad sweep) and retry.

## I'm connected to more than one Space: how do I pick?

If your connection is authorized for more than one Space, ask your assistant to list them (or call `list_authorized_spaces` directly) and tell it which one to use. It can switch the active Space at any point in the conversation with `set_active_space`. See the `elements-spaces` skill.

## I get `active_space_required` or `unauthorized_space`

Both come from Space selection on a connection granted more than one Space. `active_space_required` means a tool call didn't say which Space to use; the assistant should call `list_authorized_spaces` and pass the right `teamId` to the tool, or pick one once with `set_active_space`. `unauthorized_space` means a tool call named a Space outside what you granted at consent; the call is rejected. If you need that Space, reconnect and include it in the grant.

## My assistant says a tool is missing, or a tool call is refused

Tool visibility is gated by the plan, licenses, and your role across all Spaces authorized for the connection. A tool that no authorized Space passes those gates for is **hidden from the tool list entirely**; your assistant genuinely can't see it, so it may say it "can't do that" rather than report an error. And if your connection spans several Spaces, you may see a tool your *current* Space can't use; calling it returns a `forbidden` error naming the failed check (for example, a Pro-plan gate). See [security](security.md#you-choose-what-a-connection-can-do), check the **Requires** column in [tools-reference](tools-reference.md), or switch to a Space with the right plan. After a licensing change, start a new session so your client re-fetches the tool list.

## Some Elements tools are silently missing from Cursor's tool list

Cursor drops any tool whose combined user-chosen server key and tool name exceeds 60 characters. Name the server `elements`, the key used throughout these docs, then start a new Cursor session so it re-fetches the tool list.

## How do I disconnect or revoke access?

Removing the server from your client's config stops that client using it, but the server-side grant stays until it expires. To revoke it immediately, open your Elements profile, select the 'Connected apps' tab, find the connection, and click 'Revoke'; it takes effect on the very next call. See [security](security.md#managing-and-revoking-connections).

## I'm not sure which host to use

Match the URL you see in your browser when you're logged into Elements, not your location. See the app-URL → host table in the [README](../README.md) or [transport](transport.md).

## Still stuck?

Reach out to your usual Elements contact.
