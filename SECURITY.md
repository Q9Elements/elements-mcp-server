# Security policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in the Elements MCP server, the sign-in flow, or anything published in this repository, please report it privately; don't open a public GitHub issue.

Email **success@elements.cloud** with the subject line "Security report: MCP server", including:

- a description of the issue and its impact
- steps to reproduce
- the client and Elements instance you were using (see the app-URL table in the [README](README.md))

We'll acknowledge your report and keep you informed as we investigate. Please give us a reasonable opportunity to remediate before any public disclosure.

## Scope notes

- The Elements MCP server is a hosted service operated by Elements.cloud; this repository contains its skills, documentation, and client packaging. Reports about either are welcome through the same channel.
- For how the server protects your data (OAuth 2.1, consent, tenant isolation, token handling, audit logging), see [docs/security.md](docs/security.md).
