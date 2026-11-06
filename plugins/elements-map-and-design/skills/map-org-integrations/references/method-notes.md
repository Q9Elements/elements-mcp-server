# Method notes

What the playbook relies on and why, for whoever adapts it. The cards are the authority for what a run does.

## Where the evidence comes from

- **What proves an outside system** is in `../data/inventory-types.csv`. The endpoint URL of a remote site, named credential or external credential is the strongest clue to the vendor (`hubapi.com` is HubSpot, `springcm.com` DocuSign, `hook.eu1.make.com` Make), so their stored definitions are read with `get_metadata_source`. A connected app's stored definition holds only its id, dates and creator, so a connected app is matched by its name. The package namespace of a row is in its `parentPath` (`Namespace.HubSpot_Inc.RemoteSiteSetting`).
- **Matching order** (`resolve_systems.py propose`): Salesforce's own apps, domains and generated credentials are set aside first; then a known vendor by domain, namespace or name; then in-org packages are set aside; whatever is left, and anything that matches two vendors (a vendor's file bucket on AWS), goes to the classifier. Permission sets only support a system already proven, never prove one.
- **Tracing** searches each system's terms with `run_code_search` (a literal, case-insensitive search of Flow and Apex source), then asks `get_dependencies` which automations use the system's gateways: its credentials, external services and platform events, and the Apex classes and other gateway types (custom metadata among them, `../data/hit-types.csv`) the search hit. An automation that calls a middleware only through a shared callout class, without naming the middleware, is found only this second way. Domains are not searched: flows call through named credentials and classes, not URLs.
- **Descriptions carry the indirect systems.** A flow described as "sends those invoices to Xero" through Make names Xero; the tracer reads descriptions, explanations and key fields for the systems behind a middleware, and those get one more search pass.

## What the Elements tools cannot do here

- Poll each search using the returned state and retry instruction; queueing and completion time depend on the deployment and workload. Searches serialize per search type and reference model. Code-search links last 120 seconds; use each producer's descriptor for other files.
- `explain_metadata_components` can fail for every item: `generation_failed`; `missing_automation_summary` for the chain aspect when the org was synced without its automation summaries; and `rate_limited` past about ten generations a minute, where calling again restarts the failed generations first. The trace stands on names, descriptions and dependency rows, and failed explanations are gaps.
- A callout class that never names its vendor (a generic `WebhookCallout` class that reads its endpoint from custom metadata) is not hit by the search, so it is not a gateway; the automations that call it are still found when they name the middleware's custom metadata or the vendor, and the tracer reads the class from their `calls`.
- A managed package cannot be linked to a card: the card links to the package's applications and permission sets, and names the package in a note when no application of it is found.
- Every metadata attachment carries `slots.ref_model_id` as `refModelId`. A card links metadata by the API name the Metadata Dictionary lists, never with a namespace prefix added: a packaged remote site, named credential or permission set resolves by its bare name (`HAPI`), a packaged application by its prefixed one (`HubSpot_Inc__HubSpot_Sync`). An attachment that still does not resolve is dropped from its card and listed in the final report (`--drop-unresolved`), rather than dropping every link with `--skip metadata`.
- `add child` on a system architecture card creates a system architecture level, so a system's drill-down is drawn as a system architecture level, not an interaction flow.

## Drawing rules decided for this playbook

- A middleware is its own card, with the systems it carries joined to it, until it carries more than `middleware_fold_threshold` systems, or the top level would have more than `max_cards_per_level` cards (both in the plugin's `data/style-architecture.csv`); then those systems join the org directly and their lines read "via <middleware>: <what moves>". The architect can set either at check 2.
- A system's drill-down reads left to right: the system, the middleware, the automations, the objects. A middleware's drill-down shows the systems it carries and its own integrations' automations; the automations behind a carried system are on that system's drill-down.
- Amending a drawn landscape (run again and compare) is not part of this playbook: each run draws a new map.
