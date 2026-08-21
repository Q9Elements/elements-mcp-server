# Transport

The Elements MCP server is a remote server. It speaks the Streamable HTTP transport from the official `@modelcontextprotocol/sdk`, in JSON-response mode. There is no stdio transport and no SSE stream to keep open; every call is a plain HTTP request/response.

## Endpoint

There's a single endpoint:

```
POST /api/v1/mcp
```

Use it as `https://<your-instance-host>/api/v1/mcp`, where `<your-instance-host>` matches the URL you see in your browser when you're logged into Elements, not your location:

| App URL (what's in your browser) | MCP endpoint |
|---|---|
| app.q9elements.com | `https://api.q9elements.com/api/v1/mcp` |
| app.us.elements.cloud | `https://api.us.elements.cloud/api/v1/mcp` |
| app.ja1.elements.cloud | `https://api.ja1.elements.cloud/api/v1/mcp` |
| app.me1.elements.cloud | `https://api.me1.elements.cloud/api/v1/mcp` |

A `GET` to this endpoint without a bearer token returns `401 Unauthorized` (authentication runs before the method check), and an authenticated `GET` returns `405 Method Not Allowed` with an `Allow: POST` header. The server never opens a long-lived stream, so there's nothing to `GET`; every client should issue a `POST` for every call.

## Protocol details

- Every request and response carries an `MCP-Protocol-Version` header identifying the protocol version in use.
- The server advertises `tools` as its only capability: no sampling, elicitation, or resource subscriptions.
- The server is stateless between requests; it doesn't hold a session open on your behalf, so a client can reconnect at any time without losing anything beyond its own OAuth token state.

## What this means for client configuration

Because it's plain HTTP, connecting is just a URL: no separate process to spawn, no stdio pipe to manage, and no persistent socket to keep alive. See [getting-started](getting-started.md) for the exact config block for your client, and [authentication](authentication.md) for how sign-in happens the first time you use a tool.
