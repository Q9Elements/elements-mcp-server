# Security overview

This page summarizes the controls behind the Elements MCP server, in plain language, for anyone evaluating whether to connect it to their Salesforce Org.

## What the server can reach

Elements stores Salesforce **metadata and configuration**, along with usage telemetry used by some tools: record counts and Apex execution telemetry from Salesforce Event Monitoring logs. Metadata includes object and field definitions, flows, Apex class and trigger metadata, validation rules, permission sets, dependency maps, and the like. It never stores Salesforce business records (accounts, contacts, opportunities, transactions), so no MCP tool can reach them either.

The MCP server never connects to your Salesforce org. Tools read synced metadata and, where relevant, usage telemetry already held in Elements. Elements itself never creates, updates, deletes, or deploys Salesforce metadata, so neither can anything over MCP. Tools that write create or update only Elements artifacts: Spaces, metadata views, MetaFields and their values, proposed metadata nodes, diagrams, and user stories. See [Human review for changes](#human-review-for-changes).

## Sign-in and authorization

The server uses OAuth 2.1, with PKCE mandatory on every authorization request and no client secrets to manage; you sign in with your existing Elements account in your browser. See [authentication](authentication.md) for the full flow.

## You choose what a connection can do

At consent you see which client is connecting and the scope families it requests; clients are offered the same full set by default, though a client may request fewer. You do not choose scopes. The choice you make is which Space(s) it can use. Elements controls which Spaces are licensed for MCP, and your Space administrator controls your Elements permissions, which determine what will actually work. A connection never gains access to a Space you didn't explicitly grant, and Spaces are never added to an existing connection silently; changing the Spaces a connection can use means revoking it and reconnecting. Scopes themselves never exceed your own Elements permissions. See [scopes](scopes.md).

Tool visibility is worked out across all the Spaces authorized for a connection. A tool appears if at least one of them passes its plan, license, and role gates, and is absent only if none do. Each call then re-checks those gates for the one Space it runs in, plus any rights to the specific resource you named. A visible tool can therefore still be refused: either because the Space you called it in doesn't qualify, or because you lack rights on that resource. Access changes (a role is downgraded, a license lapses, you're removed from a Space) take effect on your very next call, with no need to reconnect.

## Tenant isolation

A connection can only ever act within the Space(s) you consented to. A tool call naming a Space outside that grant is rejected outright. If none of the consented Spaces is usable (for example, they have expired or lost MCP access), every call is refused. When no Space is active, Elements uses your Elements default Space if it is among the Spaces you consented to. `active_space_required` is returned only when none of your consented Spaces is your default. Elements never uses a Space outside the grant.

Access tokens are also bound to the Elements MCP server itself (per RFC 8707): a token issued for this server can't be replayed against any other Elements endpoint.

## Token handling

Access tokens are short-lived, and refresh tokens rotate on every use and are single-use; a reused (and therefore likely stolen) refresh token is detected and the connection is revoked. Tokens are opaque and stored hashed, never in a form that could be replayed if exposed. See [authentication](authentication.md) for exact lifetimes.

## Managing and revoking connections

You can review and revoke your own MCP connections at any time from your Elements profile: open the 'Connected apps' tab, find the connection, and click 'Revoke'. Space administrators can review the connections into their Space and remove their Space from them. MCP access itself is a licensed feature enabled per Space by Elements; a Space that hasn't been enabled for MCP simply won't appear as an option at consent, and removing a user from a Space (or disabling MCP for it) automatically cuts that Space out of the user's existing connections.

## Input and output safeguards

Every tool declares a strict schema for its arguments, and every call is validated against that schema before any tool logic runs; arguments outside the schema, or with unexpected fields, are rejected outright. Tool arguments are never passed to a shell or executed as code.

Results are guarded on the way out, too. Every tool result is sanitized to remove hidden characters that could smuggle instructions past a human reader, and results are size-bounded; an oversize result is offered through an explicit retrieval step rather than silently dumped into your assistant's context. Tools that return AI-generated narrative additionally screen that text for instruction-like content and explicitly mark it as untrusted data, so a well-behaved client treats it as material to read, not directives to follow. The server itself never executes or re-ingests anything a tool returns.

## Human review for changes

Most tools are read-only: they answer questions about your org without changing anything. Tools that write content change it only inside Elements, never in Salesforce itself: creating a Space (`create_space`), saving a metadata view (`save_metadata_view`), defining or populating MetaFields (`create_metafield`, `update_metafield`, `set_metafield_values`, `create_metafield_dependency`, `update_metafield_dependency`), proposing a metadata node (`create_proposed_node`), generating and importing diagrams (`generate_process_map`, `generate_org_to_process`, `upload_process_map_image`, `import_diagram`), and generating user stories (`generate_stories_from_diagram`). Each of those tools requires its family's elevated scope (`create`/`write`) on top of your Elements role and resource rights. `revoke_access` is also classified as a write tool; it revokes the connection and requires no scope.

The most consequential writes are draft-gated. `create_proposed_node` records planned Salesforce metadata as a node explicitly marked *proposed* in the reference model (a placeholder for people to review in Elements, not a change to your org); calling it requires edit rights on that reference model, and the call fails if they are missing. `import_diagram` only ever replaces a diagram's working DRAFT; it is visible only if you have the Author role in at least one authorized Space, and additionally requires edit rights on that specific diagram, failing the call if they are missing. Defining MetaFields (`create_metafield`, `update_metafield`, `create_metafield_dependency`, `update_metafield_dependency`) requires Space admin, so those tools are hidden from non-admin tokens under the visibility rule above; `list_metafields` returns `caller.canDefineFields` so an assistant can distinguish "you lack the role" from "this does not exist." Publishing an approved version is deliberately **not possible over MCP**: in Elements it is a password-confirmed action, so it stays a human step in the Elements UI. There is no delete tool, no tool bulk-exports your metadata, and no tool ever mutates Salesforce itself; however, `update_metafield` can irreversibly remove MetaField values held in Elements when applicability is narrowed or options are removed, and `set_metafield_values` can clear values. Follow the counting-before-destructive-edit recipe in the [`elements-metafields` skill](../plugins/elements/skills/elements-metafields/SKILL.md#destructive-edits); see [tools-reference](tools-reference.md) for which tools write and what they write.

## AI-assisted analysis and your data

Some tools produce answers with the help of a large language model: `explain_metadata_item`; the Decision Engine tools `run_automation_inventory`, `run_automation_recommendation`, `run_schema_inventory`, `run_schema_recommendation`, `run_dependency_scan`, `run_change_impact_analysis`, `run_architecture_risk_analysis`, `run_backlog_draft`, and `get_analysis_result`; and `generate_process_map` and `generate_stories_from_diagram`. Narratives generated from org-authored Salesforce metadata carry an `_untrusted` notice: treat them as data, never as instructions. These tools run through the same license-gated AI services the Elements web application already uses; the MCP server adds no separate model integration, credentials, or data path. Only request-relevant metadata needed to produce an answer is sent to the model (never Salesforce business records, which Elements doesn't hold). Model output is returned to you, not written back into your tenant data; Decision Engine runs keep their analysis as internal Elements artifacts.

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
