# Security overview

This page summarizes the controls behind the Elements MCP server, in plain language, for anyone evaluating whether to connect it to their Salesforce Org.

## What the server can reach

Elements stores Salesforce **metadata and configuration only**: object and field definitions, flows, Apex class and trigger metadata, validation rules, permission sets, dependency maps, and the like. It never stores Salesforce business records (accounts, contacts, opportunities, transactions), so no MCP tool can reach them either.

The MCP server never connects to your Salesforce org. Every tool reads from metadata already synced into the Elements database, and Elements itself never creates, updates, deletes, or deploys Salesforce metadata, so neither can anything over MCP. The tools that write, write only Elements' own artifacts: diagrams, metadata views, and user stories. See [Human review for changes](#human-review-for-changes).

## Sign-in and authorization

The server uses OAuth 2.1, with PKCE mandatory on every authorization request and no client secrets to manage; you sign in with your existing Elements account in your browser. See [authentication](authentication.md) for the full flow.

## You choose what a connection can do

At consent you see which client is connecting and the fixed scope set every connection receives; the choice you make is which Space(s) it can use. Elements controls which Spaces are licensed for MCP, and your Space administrator controls your permissions, which determine what will actually work. A connection never gains access to a Space you didn't explicitly grant, and Spaces are never added to an existing connection silently; granting a new Space means consenting again. Scopes themselves never exceed your own Elements permissions. See [scopes](scopes.md).

Tool visibility is worked out across all the Spaces authorized for a connection. A tool appears if at least one of them passes its plan, license, and role gates, and is absent only if none do. Each call then re-checks those gates for the one Space it runs in, plus any rights to the specific resource you named. A visible tool can therefore still be refused: either because the Space you called it in doesn't qualify, or because you lack rights on that resource. Access changes (a role is downgraded, a license lapses, you're removed from a Space) take effect on your very next call, with no need to reconnect.

## Tenant isolation

A connection can only ever act within the Space(s) you consented to. A tool call naming a Space outside that grant is rejected outright. If a connection somehow has no Space it's currently allowed to use, it's asked to pick one explicitly rather than Elements silently defaulting across Spaces.

Access tokens are also bound to the Elements MCP server itself (per RFC 8707): a token issued for this server can't be replayed against any other Elements endpoint.

## Token handling

Access tokens are short-lived, and refresh tokens rotate on every use and are single-use; a reused (and therefore likely stolen) refresh token is detected and the connection is revoked. Tokens are opaque and stored hashed, never in a form that could be replayed if exposed. See [authentication](authentication.md) for exact lifetimes.

## Managing and revoking connections

You can review and revoke your own MCP connections at any time from your Elements profile: open the 'Connected apps' tab, find the connection, and click 'Revoke'. Space administrators have the same visibility and control over connections into their Space. MCP access itself is a licensed feature enabled per Space by Elements; a Space that hasn't been enabled for MCP simply won't appear as an option at consent, and removing a user from a Space (or disabling MCP for it) automatically cuts that Space out of the user's existing connections.

## Input and output safeguards

Every tool declares a strict schema for its arguments, and every call is validated against that schema before any tool logic runs; arguments outside the schema, or with unexpected fields, are rejected outright. Tool arguments are never passed to a shell or executed as code.

Results are guarded on the way out, too. Every tool result is sanitized to remove hidden characters that could smuggle instructions past a human reader, and results are size-bounded; an oversize result is offered through an explicit retrieval step rather than silently dumped into your assistant's context. Tools that return AI-generated narrative additionally screen that text for instruction-like content and explicitly mark it as untrusted data, so a well-behaved client treats it as material to read, not directives to follow. The server itself never executes or re-ingests anything a tool returns.

## Human review for changes

Most tools are read-only: they answer questions about your org without changing anything. The tools that do write change content only inside Elements, never in Salesforce itself: creating a Space (`create_space`), saving a metadata view (`save_metadata_view`), defining or populating MetaFields (`create_metafield`, `update_metafield`, `set_metafield_values`, `create_metafield_dependency`, `update_metafield_dependency`), proposing a metadata node (`create_proposed_node`), generating and importing diagrams (`generate_process_map`, `generate_org_to_process`, `upload_process_map_image`, `import_diagram`), and generating user stories (`generate_stories_from_diagram`). Every one of these requires its family's elevated scope (`create`/`write`) on top of your normal Elements role and resource permissions.

The most consequential writes are draft-gated. `create_proposed_node` records planned Salesforce metadata as a node explicitly marked *proposed* in the reference model (a placeholder for people to review in Elements, not a change to your org); calling it requires edit rights on that reference model, and the call fails if they are missing. `import_diagram` only ever replaces a diagram's working DRAFT; it is visible only if you have the Author role in at least one authorized Space, and additionally requires edit rights on that specific diagram, failing the call if they are missing. Defining MetaFields (`create_metafield`, `update_metafield`, `create_metafield_dependency`, `update_metafield_dependency`) requires Space admin, so those tools are hidden from non-admin tokens under the visibility rule above; `list_metafields` returns `caller.canDefineFields` so an assistant can distinguish "you lack the role" from "this does not exist." Publishing an approved version is deliberately **not possible over MCP**: in Elements it is a password-confirmed action, so it stays a human step in the Elements UI. There is no delete tool, no tool bulk-exports your metadata, and no tool ever mutates Salesforce itself; however, `update_metafield` can irreversibly remove MetaField values held in Elements when applicability is narrowed or options are removed, and `set_metafield_values` can clear values. Follow the counting-before-destructive-edit recipe in the [`elements-metafields` skill](../skills/elements-metafields/SKILL.md#destructive-edits); see [tools-reference](tools-reference.md) for which tools write and what they write.

## AI-assisted analysis and your data

A few tools produce their answer with the help of a large language model: currently `explain_metadata_item`. Its narrative is generated from org-authored Salesforce metadata, so the response carries an `_untrusted` notice: treat the narrative as data, never as instructions. They run through the same license-gated AI services the Elements web application already uses; the MCP server adds no separate model integration, credentials, or data path. Only the request-relevant metadata needed to produce the answer is sent to the model (never Salesforce business records, which Elements doesn't hold), and the model's output is returned to you, not written back into your tenant data.

## Audit logging

Every tool call is logged with who made it, which Space it ran in, which tool it called, and the outcome. Sign-in and connection events (granted, refreshed, revoked) are logged too. These records are written to secure, append-only storage operated by Elements and used for security monitoring and incident investigation; they aren't currently exposed inside the Elements app, so if you need a connection's activity investigated, contact Elements support. What you can review yourself at any time is each active connection and exactly what it's allowed to do; see [Managing and revoking connections](#managing-and-revoking-connections).

## Rate limits

Connections are rate-limited and capped on concurrency, and each tool call has a maximum execution time, so a runaway or misbehaving client can't overwhelm your org's data.

## Platform compliance

The MCP server runs on the same platform, services, and database as the rest of Elements; there is no separate MCP backend. Platform-level security documentation, including SOC 2, ISO 27001:2022, and our Data Processing Agreement, is available at [trust.elements.cloud](https://trust.elements.cloud/).

## Learn more

- [Authentication](authentication.md)
- [Scopes](scopes.md)
- [Tools reference](tools-reference.md)
- [Troubleshooting](troubleshooting.md)
