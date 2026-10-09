# Tools reference

Elements Skills call the MCP tools listed below. You don't need to call these directly (ask your assistant in plain language and it picks the right skill and tool for you), but this page is the reference if you're building your own integration or want to know exactly what a connection can do.

The tool set grows over time within the [scope families](scopes.md) described there; this table is not a fixed count and will gain rows as new tools ship.

Plan, license, and role gates can hide a tool from the tool list entirely, so a "missing" tool usually means an access gap on the authorized Spaces, not an error; see [security](security.md#you-choose-what-a-connection-can-do).

Columns:

- **Read/Write**: whether the tool changes anything in your Space.
- **Required scope**: the [scope](scopes.md) your connection needs, checked on every call alongside your Elements role, plan, license, and per-resource rights (see [security](security.md)).
- **Requires**: what must be true for the tool to appear in your tool list at all: the Space plan, license, or Elements role it is gated on; a "—" means nothing beyond the base plan. A tool is hidden only when no authorized Space passes these gates; if one passes, it stays visible, and a call against a Space that doesn't qualify fails instead.
- **Per-resource check**: rights checked against the specific diagram, reference model, or view you name when you call it. The tool is visible; the call returns a permission error. A "—" means no rights on a specific resource are checked; the tool's gates are all plan, license, or role gates on the Space. View, Edit, and Manage are access levels granted to you in Elements on that specific diagram or reference model; Manage is the higher level Elements requires for exporting a diagram.

## Spaces

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `get_active_space` | Shows which Space your connection is currently using. It reports the session's active Space whatever `teamId` you pass, so it cannot confirm another Space; for that, read `activeSpace` from `list_reference_models` called with that `teamId`, or find the Space in `list_authorized_spaces` | Read | `mcp:spaces:read` | — | — |
| `list_authorized_spaces` | Lists the Spaces your connection is authorized to use | Read | `mcp:spaces:read` | — | — |
| `set_active_space` | Switches which Space the rest of the conversation uses; this only changes your own connection's state, not any Space data | Read | `mcp:spaces:read` | — | — |
| `revoke_access` | Revokes this client's access to Elements; also how to re-authorize with a different space selection, since the next request restarts the consent flow | Write | — | — | — |
| `create_space` | Creates a new Space; a new Space still needs MCP access enabled by Elements before it can be used here | Write | `mcp:spaces:create` | — | — |

## Metadata

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `list_reference_models` | Lists the synced Salesforce reference models available in the current Space, so you can pick which org copy to analyze; called with a `teamId`, it lists that Space's models and names the Space in `activeSpace {teamId, name}`¹ | Read | `mcp:spaces:read` | — | — |
| `metadata_search` | Finds real synced metadata/configuration definitions by name or API name, not business records, and returns their true API names | Read | `mcp:metadata:read` | Pro Space | — |
| `get_metadata_node` | Shows a synced metadata/configuration node in depth, with fields, relationships, dependencies, and change-history context, not a live business record | Read | `mcp:metadata:read` | Pro Space | — |
| `get_dependencies` | Traces actual incoming or outgoing configuration dependencies from the synced metadata graph, not related business records, so you can assess change impact | Read | `mcp:metadata:read` | Pro Space | — |
| `get_inbound_relationship_population` | Returns every inbound relationship field for up to 25 objects from the synced metadata graph, ranked by population percentage, with one page of up to 200 rows. A null population percentage means analytics are unknown, never zero | Read | `mcp:metadata:read` | Pro Space | View access to that reference model |
| `explain_metadata_item` | Explains one synced metadata item in plain language. A required `aspect` picks which explanation: `chain` (what a Flow, Trigger, or Apex class actually does, from its related automation chain), `data-lineage` (how an object's or field's value gets set, who can change it, and the risks), or `order-of-execution` (the Salesforce save order for an object) | Read | `mcp:metadata:read` | AI Analysis license<br>GPT features enabled for the Space (Starter plans excluded) | — |
| `code_search` | Searches indexed Apex and metadata source for literal strings and informal references that the structured dependency graph cannot see | Read | `mcp:metadata:read` | Enterprise Space<br>Dependency Explorer license | View access to that reference model<br>Edit access to start a new (uncached) search |
| `get_node_change_history` | Shows who changed a metadata node and when, and returns the metadata snapshot of a chosen version (XML, or JSON for Data Cloud types; when a snapshot exists) so you can compare two versions yourself | Read | `mcp:metadata:read` | Pro Space | View access to that reference model |
| `get_access` | Audits which Profiles, Permission Sets, Permission Set Groups, and Groups grant access to a metadata node, how many users each reaches, and why a given user has access; it does not enumerate the individual users | Read | `mcp:metadata:read` | Pro Space | — |
| `list_managed_packages` | Lists the managed packages installed in a reference model, each with its namespace prefix and a per-metadata-type component-count breakdown | Read | `mcp:metadata:read` | Pro Space | — |
| `list_supported_metadata_types` | Lists the Salesforce metadata types Elements can sync and analyze | Read | `mcp:metadata:read` | — | — |
| `list_metadata_columns` | Lists the columns you can filter or display for a metadata type, and the operators valid for each | Read | `mcp:metadata:read` | Enterprise Space | View access to that reference model |
| `list_metafields` | Lists the customer-defined MetaField definitions on Salesforce metadata, including ids, options, applicability, capacity, and admin-only metadata-type choices | Read | `mcp:metadata:read` | Enterprise Space | — |
| `create_metafield` | Creates one customer-defined MetaField on Salesforce metadata in an Elements implementation | Write | `mcp:metadata:write` | Enterprise Space<br>Space admin role | — |
| `update_metafield` | Updates a customer-defined MetaField definition; narrowing applicability or removing options irreversibly purges affected values across every synced org in the implementation | Write | `mcp:metadata:write` | Enterprise Space<br>Space admin role | — |
| `set_metafield_values` | Sets or clears customer-defined MetaField values on many metadata nodes, partitioning dependent picklists internally. Each value selects its nodes with exactly one of an explicit id list (keep these to roughly 1000 ids as a matter of context cost, not an enforced limit; larger or data-expressible selections should use the filter) or a `nodeFilter` (the `query_metadata` selection shape, resolved server-side, so bulk selections cost no id traffic). The enforced caps per call, echoed back in `capsApplied`, are 40 (field, value) operations, 4,000 node references and 40 write chunks. A self-draining filter (one carrying a predicate on the target field that written nodes stop matching) is safe at any size: an oversized selection writes a bounded tranche and returns `remaining` (re-issue the identical call until 0; one self-draining operation per field, and no other operation in the call may write a different value to that field), while any other oversized selection is refused write-free with the fix named in the message. A batch on a field in a dependent-picklist relationship can still be refused below those limits after the read phase | Write | `mcp:metadata:write` | Enterprise Space | Edit access to that reference model |
| `list_metafield_dependencies` | Lists dependent-picklist matrices between MetaFields, with field titles and option labels joined to the raw id map | Read | `mcp:metadata:read` | — | — |
| `create_metafield_dependency` | Creates a dependent-picklist matrix between two MetaFields, with every controller option mapped explicitly | Write | `mcp:metadata:write` | Enterprise Space<br>Space admin role | — |
| `update_metafield_dependency` | Replaces a MetaField dependency matrix without changing its controller/dependent pairing | Write | `mcp:metadata:write` | Enterprise Space<br>Space admin role | — |
| `query_metadata` | Builds a list of configuration metadata with column-based criteria, not business record rows, and excludes deleted (change-tracked) nodes by default unless you filter on `status` (or the Space defines a MetaField named `status`, which suppresses that default). When you supply an explicit `columns` list, every column you filter on must appear in it; a filter on an unselected column is rejected, not silently dropped. To list an object's fields, filter the `Field` type on `full_api_name` `startswith` `<ObjectApiName>/`; a filter on `parent_object` fails (`mcp_tool_failed`), though `parent_object` works as a display column | Read | `mcp:metadata:read` | Enterprise Space | View access to that reference model |
| `plan_package_uninstall` | Plans the removal of an installed managed package: inventories its components, sweeps for incoming dependencies, separates real uninstall blockers from package-internal references, flags automations to deactivate, and returns a sequenced removal plan; it never uninstalls. Its external-reference list also includes standard polymorphic lookup fields (Task and Event "Related To" and similar), which Salesforce usually points at most or all custom objects a package adds; they clear when the package goes and are not real blockers, so the Package Uninstall skill counts them separately | Read | `mcp:metadata:read` | Pro Space | — |
| `run_quick_cleanup_view` | Finds quick cleanup wins with ready-made views for stale reports, unused fields, inactive automation, and other tech debt | Read | `mcp:metadata:read` | Enterprise Space | View access to that reference model |
| `save_metadata_view` | Saves a metadata query as a named, reusable view; refuses `isExists` filters on MetaField columns (`unsupported_operator_for_column`), because the Elements view builder cannot express them; use that operator in transient queries only | Write | `mcp:metadata:write` | Enterprise Space | View access to that reference model<br>Edit access to save a shared view |
| `create_proposed_node` | Registers a proposed metadata node (a planned object, field, Flow, or Prompt Template) in a reference model, so intended Salesforce metadata can be tracked and attached to diagram activities. `parentId` is the immediate folder node, except for `metadataType: "fields"`, where the object node may be passed directly and the object's Fields folder is resolved for you. `apiName` must be a valid Salesforce developer name | Write | `mcp:metadata:write` | Pro Space | Edit access to that reference model |

¹ Reference models are resolved per Space rather than per metadata grant, so this tool checks the `spaces` scope rather than `metadata`.

## Org health

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `get_org_structure` | Summarizes the org's synced structural shape and lets you drill from its automation, object, and integration counts to named metadata | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |
| `get_automation_health` | Assesses org-wide automation health, including fault handling, test coverage, and risk, with drill-downs to named metadata | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |
| `get_tech_debt_summary` | Summarizes org-wide configuration debt, cleanup priorities, and documentation coverage, with every metric traceable to named metadata | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |
| `get_compliance_summary` | Summarizes security posture, permission sprawl, and encrypted or sensitive-data coverage, with drill-downs to named metadata | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |
| `get_governance_summary` | Summarizes change velocity and documentation trends over a date range, so you can see whether documentation keeps pace | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |
| `get_field_population` | Ranks objects by field population to surface adoption gaps, empty or unused fields, and data-quality concerns | Read | `mcp:metadata:read` | Pro Space | View access to that reference model |
| `get_object_dependency_analysis` | Ranks objects by dependency count and metadata type, so you can find the most complex or depended-on objects | Read | `mcp:metadata:read` | Enterprise Space | View access to that reference model |
| `get_object_dependency_drill_down` | Lists the individual dependency nodes behind one object-analysis hotspot | Read | `mcp:metadata:read` | Enterprise Space | View access to that reference model |

## Drill-down

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `get_analytic_drill_down` | Returns the individual metadata items behind a slice of an org-health or analytics chart. For the `changed-metadata` chart, the optional `sfType` narrows the change list to one metadata type; rows come back in storage order, not by modification date | Read | `mcp:metadata:read` | Pro Space<br>Analytics Cloud license | View access to that reference model |

## Agent opportunities

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `scan_agentic_opportunities` | Scans an entire reference model and returns one ranked signal vector per object (record volume, recency, structured-vs-free-text field mix (its `unstructuredRatio` can count short Text fields such as Email or Phone as free text; the Agent Opportunities skill recomputes it for its shortlist from field types), automation density, growth velocity, field population, and engagement), each with the score factors that justify its agentic-opportunity ranking. `objectTypes` selects `standard`, `custom`, `namespace` (managed-package objects) or `all` | Read | `mcp:metadata:read` | Pro Space | View access to that reference model |
| `get_object_usage` | Returns the full usage and telemetry profile for a single object (record counts by type, a daily count series with net deltas, last created/modified dates, and event-log engagement) to deep-dive an opportunity surfaced by the scan. `fromDate`/`toDate` must be supplied together as parseable ISO dates, in order, spanning at most 366 days | Read | `mcp:metadata:read` | Pro Space | View access to that reference model |

## Diagrams

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `list_diagrams` | Lists the process-map diagrams in the Space, with your role and edit rights on each | Read | `mcp:diagrams:read` | — | — |
| `get_process_map` | Reads an existing diagram as structured JSON (activities, transitions, lifecycle states) and polls for completion after process-map or org-to-process generation. On larger diagrams (seen from about 18 activities and 26 transitions) it can return `transitions: []` with a `_truncated` marker while `metadata.transitionCount` holds the real total; the Org-to-Process skill then rebuilds the transitions from `export_diagram`, which takes the diagram's `mapId` (from `list_diagrams`) and needs Manage access | Read | `mcp:diagrams:read` | — | View access to that diagram |
| `generate_process_map` | Generates a UPN process map from a text description, transcript, images, or a combination; you poll `get_process_map` for completion | Write | `mcp:diagrams:create` | Author role | — |
| `generate_org_to_process` | Generates process views from a lifecycle object's actual record types, lifecycle fields, and synced automations, then returns diagram ids to poll; it fans out one diagram per record type and asks you to clarify when several lifecycle or workflow fields qualify | Write | `mcp:diagrams:create` | Pro Space<br>Org-to-Diagram license | Edit access to that reference model |
| `upload_process_map_image` | Uploads an image for use as input to process-map generation | Write | `mcp:diagrams:create` | Author role | — |
| `export_diagram` | Exports a diagram as a ZIP (map plus per-level JSON) with presigned download and upload URLs, for editing and re-import | Read | `mcp:diagrams:read` | Pro Space | Manage access to that diagram |
| `import_diagram` | Imports an edited diagram ZIP back into Elements, replacing the current DRAFT in place; releasing an approved version stays a human step in the Elements UI | Write | `mcp:diagrams:create` | Author role | Edit access to that diagram |

## Stories

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `list_stories` | Lists user stories in a Space, 20 per page by default and up to 100, with `skip`, `format` (`json`, `ndjson` or `csv`) and `mode: "manifest"` for counts only. With a `diagramId`, it returns that diagram's stories and, for a while after a generation run, the run's `generation {status, total, completed, failed}` | Read | `mcp:stories:read` | Pro Space<br>Change Tickets license | — |
| `generate_stories_from_diagram` | Turns selected process-diagram activities into user stories, one per resource, with a headline, description, and acceptance criteria; you can optionally link each to a requirement. Judge the run from the `completed` and `failed` counts and the stories now linked to the diagram: the job `status` can read `failed` after every story was created | Write | `mcp:stories:create` | Pro Space<br>Story generation license<br>Requirements Manager role | Edit access to that diagram |

## Decision Engine

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `run_automation_inventory` | Step 1 of an automation change: inventories the existing automations related to the request and opens the mission the later steps build on; asks for clarification when the target object is ambiguous. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_automation_recommendation` | Step 2 of an automation change: recommends 2–4 implementation options (update existing or create new) and records the one you pick. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_schema_inventory` | Step 1 of a schema change: inventories the objects, fields, and record types related to the request and opens the mission the later steps build on; asks for clarification when the parent object is ambiguous. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_schema_recommendation` | Step 2 of a schema change: recommends 2–4 implementation options (reuse, extend, or create new) and records the one you pick. Creating new goes from the accepted option straight to the backlog draft; reuse and extension also run dependency, impact, and risk analysis. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `get_analysis_result` | Polls the current mission run and returns its finished step result or failure. Takes an optional step (`automation_inventory`, `automation_recommendation`, `dependency_scan`, `change_impact_analysis`, `architecture_risk_analysis`, `backlog_draft`, `schema_inventory`, `schema_recommendation`): without it, returns the mission's latest run; with it, returns that step's last finished result on the same mission, or `not_found`. A run that does not finish within 20 minutes of starting, including time waiting in the queue, or that stops reporting progress for 3 minutes, is reported as failed; start the step again. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_dependency_scan` | Step 3: resolves the target metadata and scans its direct dependencies (where-used). For field updates and deletions, the [field-change recipe](../plugins/elements/skills/elements-decision-engine/references/field-change.md) combines reference and impact analysis with the runtime fire-chain tools. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_change_impact_analysis` | Step 4: analyzes change impact and produces a change plan, including a capped deletion cascade when requested | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_data_load_impact` | Analyzes one to five load targets, each with up to 200 written fields, through direct and transitive automation effects, validation and assignment rules, and lock, roll-up, volume, and fan-in risks. The asynchronous result summarizes every target; its complete evidence bundle link lives for 120 seconds. It reads configuration only, makes no Salesforce calls, and provides evidence for a deactivation decision rather than the decision itself. | Read | `mcp:metadata:read` | Enterprise Space<br>Fully synced reference model | View access to that reference model |
| `run_architecture_risk_analysis` | Step 5: analyzes the change for architecture risks via a prosecutor/verifier review, with a confirmation gate on high-complexity changes. A `needs_confirmation` result is answered with the same `missionId`, its `gateId`, and `proceed:true` to run or `proceed:false` to skip; a proceed answer without a pending `needs_confirmation`, or with another `gateId`, fails with `invalid_input`. | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |
| `run_backlog_draft` | Final step: drafts a requirement and user stories for delivery; the draft is returned for review and is not written into Elements | Read | `mcp:decisionEngine:read` | Decision Engine license<br>GPT features | Edit access to that reference model |

## Playbook tools

### [Remove Unused Apex Playbook](../plugins/remove-unused-apex/README.md)

| Tool | What it does | Read/Write | Required scope | Requires | Per-resource check |
|---|---|---|---|---|---|
| `has_event_monitoring` | Checks whether daily Apex event logs exist in the connected org and reports the observed coverage within a 30-day window. A successful false result means no telemetry was found, not that the entitlement is absent or nothing is used. Daily Apex event logs come from Salesforce Event Monitoring. | Read | `mcp:metadata:read` | Enterprise Space<br>Dependency Explorer license<br>Reference model synced from a connected org | View access to that reference model |
| `get_unused_apex_candidates` | Builds an asynchronous evidence bundle ranking Apex classes and triggers that may be unused from synced metadata and held execution telemetry. A disqualified result is an answer, not an error; completed bundle links live for 120 seconds | Read | `mcp:metadata:read` | Enterprise Space<br>Dependency Explorer license | View access to that reference model |

## About large results

Every tool result passes through a size backstop before it reaches your assistant, because a single
oversized response would otherwise fill its context and stall the conversation. The budget is about
30,000 characters per result, with a hard ceiling of 1,000,000.

- **Over budget with a list to trim:** one list is shortened and the result carries `_truncated`,
  carrying `{field, returnedItems, totalItems, note, nextSkip}`, with `nextSkip` present inside
  `_truncated` (not at the top level) on tools that paginate; resume from `_truncated.nextSkip`.
  `pageSize`, `hasMore` and `numPages` are rewritten on the outer response envelope, not inside
  `_truncated`, to match what was actually returned. `_truncated.totalItems` is the size of the
  trimmed list before trimming; it is not the same number as the envelope's own `totalItems` or
  `totalObjects`, which represent the whole corpus.
- **Over budget with nothing to trim:** the value is returned intact and flagged `_oversize`.
- **Past the hard ceiling:** the result is replaced by an `_oversize` object with
  `refusedInline: true`. Tools that can return something big offer a file or URL option instead;
  for example `get_node_change_history` with `as: "url"`.

A truncated result is a successful call, not an error, so an integration that ignores these flags will
report a short list as if it were complete. Check for `_truncated` and `_oversize` before using a count
or treating a listing as exhaustive. The Elements Skills handle this for you.

The asynchronous analysis tools, `get_unused_apex_candidates` and `run_data_load_impact`, return
`status:"computing"` on the first call and are polled with identical arguments about every 30 seconds.
A finished analysis returns a signed `bundleUrl` to a zip containing the full evidence, valid for 120
seconds, plus a `bundleSha256`. Nothing in the bundle is trimmed by the size backstop, so the bundle is
the complete result and the inline response is the summary.

## About writes

Only a small set of tools write. Each requires its family's elevated scope (`create`/`write`) except `revoke_access`, which has no scope. Everything they write is an Elements artifact; no tool ever mutates Salesforce.

- **Spaces** — `create_space` creates a new Space. (`mcp:spaces:create`)
- **Custom Views of Metadata** — `save_metadata_view` saves a filtered metadata list under a name. (`mcp:metadata:write`)
- **Proposed nodes** — `create_proposed_node` records planned Salesforce metadata as a node marked *proposed* for people to review in Elements, not a change to your org. (`mcp:metadata:write`)
- **MetaFields** — `create_metafield`, `update_metafield`, `create_metafield_dependency` and `update_metafield_dependency` define them; `set_metafield_values` populates or clears values. (`mcp:metadata:write`)
- **Diagrams** — `generate_process_map`, `generate_org_to_process`, `upload_process_map_image` and `import_diagram` create or replace a working DRAFT; releasing an approved version stays a human step in the Elements UI. (`mcp:diagrams:create`)
- **Stories** — `generate_stories_from_diagram` generates draft user stories. (`mcp:stories:create`)
