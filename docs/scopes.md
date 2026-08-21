# Scopes

## What scopes control

Every tool call is checked against a required scope. Every connection receives the same fixed set of scopes, granted once at consent: you don't pick scopes; the choice you make at consent is which Space(s) the connection can use (see [authentication](authentication.md)). A scope only ever opens the *possibility* of calling a class of tool; it never exceeds your own Elements permissions, and every call is still checked in real time against your actual Elements role, plan, license, and per-resource rights before anything runs. See [security](security.md) for how those layers fit together.

## Scope families

Each scope has the shape `mcp:<family>:<action>`. The elevated action (`create`/`write`) implies the `read` action for the same family; you don't need to request both.

| Family | Read action | Elevated action | Covers |
|---|---|---|---|
| `mcp:spaces` | `mcp:spaces:read` | `mcp:spaces:create` | Listing and switching Spaces; listing a Space's reference models and diagrams; creating a new Space |
| `mcp:metadata` | `mcp:metadata:read` | `mcp:metadata:write` | Searching, exploring, and analyzing Salesforce metadata, including object usage, data lineage, order of execution, and agentic-opportunity scans; saving a metadata view, managing MetaFields, and creating proposed metadata nodes |
| `mcp:diagrams` | `mcp:diagrams:read` | `mcp:diagrams:create` | Reading and exporting process-map diagrams; generating new maps and importing diagram drafts (releasing an approved version stays a human step in the Elements UI) |
| `mcp:stories` | `mcp:stories:read` | `mcp:stories:create` | Listing and generating user stories |

See [tools-reference](tools-reference.md) for the scope each individual tool requires.

## Consent is the envelope, not a per-call prompt

At consent you see the client and the scopes the connection will hold, and you choose the Space(s) it can use, all in one screen. That grant becomes the envelope every later tool call is checked against; there's no separate scope prompt on each individual call after that. Elevated scopes (`write`/`create`) are shown in plain language (for example, "Save views, manage MetaFields & propose changes"), so you can see exactly what the connection will be able to attempt before you approve it.

The scope envelope itself is fixed: every connection is offered the same scope families, and administrators don't tune scopes per connection. What actually narrows a connection is everything else in the grant and the live checks on every call: the Space(s) you consented to, per-Space MCP enablement, and your own current Elements role, plan, and licenses. A connection can never do more than you could do yourself in the Elements web application. See [security](security.md).

## The tool set grows

Elements adds new tools over time within these same scope families. This page, not a fixed count of tools, is the source of truth for what a scope can reach. See [tools-reference](tools-reference.md) for the current list.
