# Authentication

The Elements MCP server uses OAuth 2.1 to authenticate every connection. You sign in with your existing Elements account in your browser; there are no API keys, secrets, or personal access tokens to create or store.

Any MCP client that implements the MCP specification's authorization flow (OAuth 2.1 with PKCE) drives this flow for you automatically the first time you use a tool; Elements has been tested with Claude, Codex, and Cursor. This page describes what happens under the hood, mainly for anyone integrating a new client or troubleshooting a connection.

## How sign-in works

1. **Your client asks for the server's metadata.** When it calls the MCP endpoint without a token, the server replies `401 Unauthorized` with a `WWW-Authenticate` header pointing at the protected-resource metadata.
2. **Discovery.** Your client reads `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` (and their path-scoped variants) to find the authorization, token, and registration endpoints.
3. **Dynamic client registration.** Your client registers itself using Dynamic Client Registration (RFC 7591). Elements MCP clients register as **public clients** (`token_endpoint_auth_method: none`); there's no client secret to manage or leak.
4. **Authorize and consent.** Your browser opens Elements' sign-in and consent screen. You sign in with your normal Elements credentials, then approve, in one step:
   - the client requesting access
   - the scopes the connection will hold, the same fixed set for every connection (see [scopes](scopes.md))
   - which Space(s) it can use, the one choice that's yours to make

   Elements never grants access to a Space you didn't explicitly select, and it never adds Spaces to an existing connection later; a broader grant always means consenting again.
5. **PKCE.** Every authorization request uses PKCE with the S256 code-challenge method. This is mandatory on every request, not an option the client can skip; it protects the flow even though the client has no secret of its own.
6. **Token exchange.** Your client exchanges the authorization code for an access token and a refresh token at the token endpoint. Only two grant types are supported: `authorization_code` and `refresh_token`; there's no password grant and no client-credentials grant.
7. **Using the token.** Your client sends the access token as a bearer token on every call to the MCP endpoint.
8. **Refreshing.** When the access token expires, your client uses the refresh token to get a new one. Each refresh issues a brand-new refresh token and immediately retires the old one; refresh tokens are single-use and rotate on every use. If a retired refresh token is ever reused, Elements treats that as a sign the token has leaked and revokes the connection.

## Token lifetimes

| Token | Lifetime |
|---|---|
| Authorization code | 5 minutes, single-use |
| Access token | 15 minutes |
| Refresh token | 30 days, rotating, single-use |

## How tokens are protected

- **Opaque.** Tokens carry no readable claims a client (or anyone who intercepts one) could inspect.
- **Hashed at rest.** Tokens are stored as a SHA-256 hash, never in a form that could be replayed if the underlying data were ever read.
- **Resource-bound.** Tokens are bound to the Elements MCP server as their resource (RFC 8707); a token issued for this server can't be replayed against any other Elements endpoint.

## You don't have to do any of this by hand

Your client implements this flow for you. Point it at your MCP endpoint (see [transport](transport.md) and the app-URL → host table in the [README](../README.md)) and follow the browser prompt the first time you use a tool. See [troubleshooting](troubleshooting.md) if a connection or sign-in gets stuck.

You can see every connection created this way (and revoke any of them, effective immediately) from the 'Connected apps' tab of your Elements profile. See [security](security.md#managing-and-revoking-connections).
