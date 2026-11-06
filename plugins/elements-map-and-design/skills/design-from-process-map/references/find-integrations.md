# Finding the systems and integrations a process needs

The method the `integration-deriver` follows. First as a **process analyst**: which systems the process runs on, named or implied, and where data passes between them. Then as a **technical architect**: what already exists in the target system and how each exchange should work.

## Phase 1: systems and the integration matrix (the process analyst)

1. **Named systems** are resources of type System or Platform / Capability in `inventory.json` ("Web-to-Lead", "Salesforce dashboard"). Group names that mean one system ("Salesforce dashboard" belongs to the target Salesforce org).
2. **Implied systems** show where a step needs a system the map does not name: a website that captures leads, email that sends a quote, a marketing tool that runs nurture campaigns, a finance system that invoices. Mark each `inferred`, with the steps and words that imply it.
3. **The target system** chosen at kickoff is always a system, marked `hub: true`.
4. **The integration matrix:** for every handoff where data moves from one system to another (a line whose two steps run on different systems, or a step that sends or receives something outside the target system), record from, to, the data in business words, and the steps. A handoff with no system on one side, done by hand, goes to `manualHandoffs` unless the design should automate it; say which in its note.

## Phase 2: existing and proposed, and how each exchange works (the technical architect)

Read `evidence/targets.json`: for an org, `integrationEvidence` lists named credentials, connected apps, external services, platform events and the like, and `packages` the installed managed packages.

1. **Existing or proposed:** an integration is `existing` when the evidence shows it (a named credential to the ERP's endpoint, a connected app for the website, a package for the marketing tool, Web-to-Lead for a web form); otherwise `proposed`. On the documentation route every integration is proposed unless the vendor provides it out of the box.
2. **Pattern:** choose from `data/integration-patterns.csv` at the plugin root by who calls whom and whether the caller waits: request and reply, fire and forget, batch data synchronization, remote call-in, UI update based on data changes, data virtualization. Set `timing` to one the pattern allows.
3. **Mechanism (`technology`):** name how it works (REST API, Platform Events, Bulk API, Change Data Capture, out-of-the-box connector, the package's own sync) and avoid a mechanism `data/integration-mechanisms.csv` rates suboptimal for the pattern.
4. **Middleware:** add an integration platform (kind `middleware`) when three or more systems exchange the same data, when an exchange needs transformation or orchestration across systems, or when the org already has one; otherwise point to point. Say why in its evidence.
5. **Labels:** keep each line's label within `label_max_chars` of `data/style-architecture.csv` at the plugin root, counting the ` (proposed)` that `design.py slice` adds to a proposed integration. The data in full goes in `data`.

## What a good result looks like

- Every system and integration names the steps it serves.
- Implied systems are marked inferred and say what implies them.
- No exchange is left out: what the design leaves manual is listed in `manualHandoffs`.
