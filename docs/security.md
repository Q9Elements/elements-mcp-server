# Security overview

This page summarizes the controls behind the Elements Model Context Protocol (MCP) server, in plain language, for anyone evaluating whether to connect it to their Salesforce Org.

## What the server can reach

Elements stores Salesforce **metadata and configuration**, along with usage telemetry used by some tools: record counts and Apex execution telemetry from Salesforce Event Monitoring logs. Metadata includes object and field definitions, flows, Apex class and trigger metadata, validation rules, permission sets, dependency maps, and the like. It never stores Salesforce business records (accounts, contacts, opportunities, transactions), so no MCP tool can reach them either.

The MCP server never connects to your Salesforce org. Tools read synced metadata and, where relevant, usage telemetry already held in Elements. Elements itself never creates, updates, deletes, or deploys Salesforce metadata, so neither can anything over MCP. Tools that write create or update only Elements artifacts: Spaces, metadata views, MetaFields and their values, proposed metadata nodes, diagrams, and user stories. See [Human review for changes](#human-review-for-changes).

## Sign-in and authorization

The server uses OAuth 2.1, with PKCE mandatory on every authorization request and no client secrets to manage; you sign in with your existing Elements account in your browser. See [authentication](authentication.md) for the full flow.

## You choose what a connection can do

At consent you see which client is connecting and the scope families it requests; clients are offered the same full set by default, though a client may request fewer. You do not choose scopes. The choice you make is which Space(s) it can use. Elements controls which Spaces are licensed for MCP. Your Space administrator controls your personal Elements permissions, which determine what you can actually do. A connection never gains access to a Space you didn't explicitly grant, and Spaces are never added to an existing connection silently; changing the Spaces a connection can use means revoking it and reconnecting. Scopes themselves never exceed your Elements permissions. See [scopes](scopes.md).

Tool availability is worked out across all the Spaces authorized for a connection. Which tools you see depends on the Spaces you authorize: a tool appears if at least one authorized Space makes it available. Role requirements, such as Space admin or Author, and rights to a specific resource are checked when you call a tool; a call without the required access is refused with `access_denied`. Changes to your role, license, or Space membership take effect on your next call, with no need to reconnect.

## Tenant isolation

A connection can only ever act within the Space(s) you consented to. A tool call naming a Space outside that grant is rejected outright. `revoke_access` works while at least one consented Space has an active membership and is not suspended, even if that Space lacks MCP access. If every consented Space is suspended or you are no longer an active member of any of them, the server refuses every request. Revoke the connection from the Connected apps tab in your Elements profile instead.

When no Space is active, Elements uses your eligible default Space if you consented to it, or else the one eligible consented Space if there is exactly one; otherwise the call returns `active_space_required`. A Space named explicitly must also be authorized and MCP-enabled.

Like the Elements web app, tools can read the diagram templates available to you (Elements' Public Templates, public Spaces you belong to, and your company's internal template Spaces): `list_map_templates`, `get_process_map_outline` and `get_diagram` read them, and `create_map_from_template` copies a template into a Space you granted, with your own rights there. No tool changes anything in a template Space, and every such read and copy is audited.

Access tokens are also bound to the Elements MCP server itself (per RFC 8707): a token issued for this server can't be replayed against any other Elements endpoint.

## Token handling

Access tokens are short-lived, and refresh tokens rotate on every use and are single-use; a reused (and therefore likely stolen) refresh token is detected and the connection is revoked. Tokens are opaque and stored hashed, never in a form that could be replayed if exposed. See [authentication](authentication.md) for exact lifetimes.

## Managing and revoking connections

You can review and revoke your own MCP connections at any time from your Elements profile: open the 'Connected apps' tab, find the connection, and click 'Revoke'. Space administrators can review the connections into their Space and remove their Space from them. A Space that hasn't been enabled for MCP simply won't appear as an option at consent, and removing a user from a Space (or disabling MCP for it) automatically cuts that Space out of the user's existing connections.

## Input and output safeguards

Every tool declares a strict schema for its arguments. Supported compatibility aliases are normalized first; the resulting arguments are validated against the schema before tool logic runs, and unsupported fields are rejected. Tool arguments are never passed to a shell or executed as code.

Results are guarded on the way out, too. Every tool result is sanitized to remove hidden characters that could smuggle instructions past a human reader, and results are size-bounded; an oversize result is offered through an explicit retrieval step rather than silently dumped into your assistant's context. Tools that return AI-generated narrative additionally screen that text for instruction-like content and explicitly mark it as untrusted data, so a well-behaved client treats it as material to read, not directives to follow. The server itself never executes or re-ingests anything a tool returns.

## Human review for changes

Most tools are read-only: they answer questions about your org without changing anything. Tools labeled Writes to Elements in [tools-reference](tools-reference.md) are `set_active_space`, `create_space`, `save_metadata_view`, `create_proposed_node`, `create_metafield`, `set_metafield_values`, `set_metafield_dependency`, `create_map`, `create_map_from_template`, `generate_process_map`, `upload_process_map_image`, `generate_stories_from_diagram`, and `run_schema_inventory`. They write only inside Elements, never to Salesforce itself. `manage_diagram` adds resources to the space library only when the change asks for it with `createResources: true`, only for a user with the resource admin right in the space (as adding a resource in Elements requires), and at most 10 per change. A resource it added stays in the library if the save then fails. It attaches Salesforce metadata to a step only for a user with the edit or manage role on a reference model that holds it, as attaching it in Elements requires, and only from the space's own reference models the user may view and its stories (a reference model the user may not view is neither searched nor named in an error); removing an attachment removes the link, never the metadata or the story. Each of those tools requires its family's elevated scope (`create`/`write`) on top of your Elements role and resource rights. `revoke_access` is labeled Destructive in Elements; it revokes the connection and requires no scope.

The most consequential writes are draft-gated. `create_proposed_node` records planned Salesforce metadata as a node explicitly marked *proposed* in the reference model (a placeholder for people to review in Elements, not a change to your org); calling it requires edit rights on that reference model, and the call fails if they are missing. `manage_diagram` only ever changes one level's working DRAFT, with three exceptions: it adds resources to the space library when asked (below); it creates child levels of that level, which inherit the level's edit rights; and, only when a removal is confirmed, it sends the child level of a removed step to the recycle bin. It never removes a line linked off-page to another diagram, never writes while someone has that level open for editing, and needs edit rights on that diagram. An agent session on a level leaves one history snapshot of the level before its first change, attributed "AI agent on behalf of" the user (there is no restore action yet; a change more than 30 minutes after the last one, or after the level was saved another way, starts a new one), and an audit event (map, level, versions before and after, number of changes, resources added to the library), and counts against a budget of 20 diagram writes a minute per user, shared with `create_map` and `create_map_from_template`. `create_map` makes an empty map with one blank DRAFT, recorded as one history entry "Created by AI agent on behalf of" the user and audited like a save; if that history entry cannot be written, the map is soft-deleted again. A failure inside the map service itself, between saving the map and its diagram, is not undone. `create_map_from_template` copies a template you may view and copy into your Space through the same service as Use template in Elements, without its comments, data table records, linked stories, requirements and Salesforce metadata, or its links to diagrams outside the template; the copy runs in the background, is audited, writes no history entry, and counts against the same budget; a copy whose job cannot start is soft-deleted again (`save_failed`), and `partial_save` names a map that could not be removed or whose copy went on. `import_diagram` has none of these and refuses only while another user has a level open for editing; it only ever replaces a diagram's working DRAFT, requires the Author role in the Space and edit rights on that specific diagram, failing the call if they are missing. Defining MetaFields (`create_metafield`, `update_metafield`, `set_metafield_dependency`) requires Space admin; the role is checked when each tool is called and a caller without it receives `access_denied`; `get_metafields` returns `caller.canDefineFields` so an assistant can distinguish "you lack the role" from "this does not exist." Publishing an approved version is deliberately **not possible over MCP**: in Elements it is a password-confirmed action, so it stays a human step in the Elements UI. There is no direct delete tool, and no tool ever mutates Salesforce itself; however, `update_metafield` can irreversibly remove MetaField values held in Elements when applicability is narrowed or options are removed, and `set_metafield_values` can clear values. `manage_diagram` moves a removed step's child level to the recycle bin, not out of Elements, and only when the removal is confirmed. Follow the counting-before-destructive-edit recipe in the [`elements-metafields` skill](../plugins/elements/skills/elements-metafields/SKILL.md#destructive-edits); see [tools-reference](tools-reference.md) for which tools write and what they write.

## AI-assisted analysis and your data

Some tools produce answers with the help of a large language model: `explain_metadata_components`; the Decision Engine tools `run_automation_inventory`, `run_automation_recommendation`, `run_schema_inventory`, `run_schema_recommendation`, `run_dependency_scan`, `run_change_impact_analysis`, `run_architecture_risk_analysis`, `run_backlog_draft`, and `get_analysis_result`; and `generate_process_map` and `generate_stories_from_diagram`. Narratives generated from org-authored Salesforce metadata carry an `_untrusted` notice: treat them as data, never as instructions. These tools run through the same license-gated AI services the Elements web application already uses; the MCP server adds no separate model integration, credentials, or data path. Only request-relevant metadata needed to produce an answer is sent to the model (never Salesforce business records, which Elements doesn't hold). Analysis responses are returned to you. Generated process maps and stories are saved in Elements, and Decision Engine runs retain analysis as internal Elements artifacts.

## Audit logging

Every tool call is logged with who made it, which Space it ran in, which tool it called, and the outcome. Sign-in and connection events (granted, refreshed, revoked) are logged too. These records are written to secure, append-only storage operated by Elements and used for security monitoring and incident investigation; they aren't currently exposed inside the Elements app, so if you need a connection's activity investigated, contact Elements support. What you can review yourself at any time is each active connection, exactly what it's allowed to do, and when it last signed in; see [Managing and revoking connections](#managing-and-revoking-connections).

## Rate limits

Connections are rate-limited and capped on concurrency, and each tool call has a maximum execution time, so a runaway or misbehaving client can't overwhelm your org's data.

## Platform compliance

The MCP server runs on the same platform, services, and database as the rest of Elements; there is no separate MCP backend. Platform-level security documentation, including SOC 2, ISO 27001:2022, and our Data Processing Agreement, is available at [trust.elements.cloud](https://trust.elements.cloud/).

## Learn more

- [Authentication](authentication.md)
- [Scopes](scopes.md)
- [Tools reference](tools-reference.md)
- [Troubleshooting](troubleshooting.md)
