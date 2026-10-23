# Skills catalog

You don't call tools directly; you ask your assistant for what you want, in plain language, and it picks the right skill. A skill is a packaged capability: it decides which underlying tools to call, in what order, and how to present the result. Tools, in turn, are gated by the connection's scopes and by your Elements permissions (see [`scopes.md`](scopes.md)). The Elements Model Context Protocol (MCP) server provides the tools listed here.

Elements organizes its capabilities around three steps: **understand your org**, **model & decide** what to change, and **deliver the change**. Skills are grouped the same way below, so the catalog grows one step at a time as later releases ship.

When your client has the Elements skills installed (see [getting started](getting-started.md)), you can invoke a skill by name using its slash command, or `$` in Codex (for example `$elements-spaces`). For clients without plugin support, download [`elements-core-skills.zip`](https://github.com/Q9Elements/elements-mcp-server/raw/main/dist/elements-core-skills.zip) and add each skill zip individually, then connect the server as described in [getting started](getting-started.md#other-ai-clients-skills-only).

These fifteen skills are available now. They're all read-only against your Salesforce Org: nothing they do changes Salesforce. Some can additionally create or change artifacts held in Elements. Most of those are purely additive: the Spaces skill can create a new Space, Metadata Query can save a view, and Diagrams and Stories can create Elements content. **MetaFields is the exception: it overwrites.** Populating a classification replaces whatever value a node already held, and updating a MetaField definition can irreversibly purge values across every synced org in the implementation. Count what you are about to change before you change it; the skill carries the recipe.

## Understand your org

Skills list any role or access their tools need. Which tools you see depends on the Spaces you authorize. Role requirements, such as Space admin or Author, are checked when a tool is called, and a call without the required role is refused with `access_denied`; see [security](security.md#you-choose-what-a-connection-can-do).

### Spaces (`elements-spaces`)

Lists and switches among Elements Spaces.

**When it triggers:** "create a space", "switch to a different space", "list my spaces", "what space am I in", or any question about space setup or consulting Spaces.

**Example**
> **You:** "What Space am I in, and can you switch me to the example project Space?"
>
> **You get back:** confirmation of your current Space, the list of Spaces you're authorized for, a switch to the one you asked for, and confirmation of the change.

`get_space_context` always reports the session's active Space, so to confirm a different Space the skill reads it from `list_reference_models` called with that Space's id, or from `get_space_context`.

**Tools it uses:** `get_space_context`, `set_active_space`, `create_space`; see [`tools-reference.md`](tools-reference.md).

### Metadata Explorer (`elements-metadata`)

Finds and explains individual Salesforce metadata nodes (objects, fields, flows, triggers, validation rules) with answers resolved from the org's synced metadata, not inferred, using keyword search, full node detail, dependency tracing, and a plain-English explanation of what an automation does.

**Requires:** explanations need the Automation & Execution Intelligence add-on on Core Metadata Management; Advanced Metadata Management includes it.

**When it triggers:** "show me the metadata for…", "what fields does this object have", "explain this flow", "what depends on this".

**Example**
> **You:** "Explain the loyalty points flow and show me what depends on it."
>
> **You get back:** the flow resolved by name, its upstream and downstream dependencies grouped by type, and a narrative covering what it does, when it runs, what it touches, and why it's risky.

When a node's detail carries no field list, the skill lists an object's fields with `list_metadata_by_criteria` on the `Field` type, filtered by the `<ObjectApiName>/` prefix of `full_api_name`.

**Tools it uses:** `list_reference_models`, `search_metadata`, `get_metadata_component`, `get_dependencies`, `explain_metadata_components`, `get_access`, `describe_metadata_schema`, `list_metadata_by_criteria`; see [`tools-reference.md`](tools-reference.md).

### Access Audit (`elements-access`)

Audits permission-level access to a single metadata node (which Profiles, Permission Sets, Permission Set Groups, and Groups grant access, and to how many users), plus a per-user "why do they have access" lookup. It does not list individual users by name.

**Requires:** view access to the reference model.

**When it triggers:** "who has access to this object/field", "audit access", "what does this profile/permission set grant", "who can edit this field and why".

**Example**
> **You:** "Who can edit the credit limit field, and how many people does each grant reach?"
>
> **You get back:** the field resolved by name, then each Profile, Permission Set, and Group that grants edit access, with an assigned-user count per grant (no individual names).

**Tools it uses:** `get_access`, `list_reference_models`, `search_metadata`, `get_metadata_component`; see [`tools-reference.md`](tools-reference.md).

### Metadata Query / Custom Views (`elements-metadata-query`)

Builds a filtered, ad-hoc list of metadata by attribute (for example, every flow on an old API version) and can save the result as a named custom view, shared or private.

**When it triggers:** "all screen flows", "every Apex class with low test coverage", "fields with population over X on an object", "list inactive validation rules", "build a view of…", "save this as a view".

**Example**
> **You:** "List all screen flows on an API version below the latest, and save it as a view."
>
> **You get back:** the filterable columns discovered for flows, the matching rows with a total count, and, if you confirm, a saved named view you can reuse later.

**Tools it uses:** `list_reference_models`, `describe_metadata_schema`, `list_metadata_by_criteria`, `save_metadata_view`; see [`tools-reference.md`](tools-reference.md).

### Org Diagnostic (`elements-org-diagnostic`)

Runs a broad baseline health check across structure, automation, tech debt, compliance, and governance, and synthesizes one ranked risk summary, optionally enriched with field-population and dependency hotspots.

**When it triggers:** "run an org diagnostic", "check org health", "give me a first-pass assessment", "where should we look first".

**Example**
> **You:** "Run an org diagnostic and tell me where to look first."
>
> **You get back:** a severity rating and top concerns for each of the five dimensions, an overall risk level with a short narrative, a saved report, and an offer to drill into the worst areas.

**Tools it uses:** `get_space_context`, `list_reference_models`, `understand_org_health`, `get_org_health_detail`; see [`tools-reference.md`](tools-reference.md).

### Change Briefing (`elements-change-briefing`)

Reports every metadata node created or updated in a date window, with each node's current status, an overall velocity figure, a breakdown by metadata type, and anomaly highlights; deletions are neither listed nor counted. For the most significant changes it fetches the Salesforce metadata snapshots (XML, or JSON for Data Cloud types) to disk and diffs each against its previous version. It picks those movers type by type, so a type with no captured snapshots (such as Report) cannot crowd them out, and labels any node without a snapshot as "no snapshot captured".

**When it triggers:** "what changed recently", "give me a change briefing", "list all changes this month", or any question about unusual or unexpected changes.

**Example**
> **You:** "What changed in the org this week, and were there any unusual spikes?"
>
> **You get back:** a velocity headline and by-type breakdown for the week, the list of created and updated nodes, any anomalies flagged, and a diff of the underlying metadata for the most significant changes.

**Tools it uses:** `get_space_context`, `list_reference_models`, `understand_org_health`, `get_org_health_detail`, `get_metadata_component`, `get_component_change_history`; see [`tools-reference.md`](tools-reference.md).

### Tech Debt (`elements-tech-debt`)

Deep-dives the tech-debt dimension: resolves flagged nodes, checks each one's dependency blast radius and how recently it was touched, and produces a ranked, actionable remediation list.

**When it triggers:** "investigate tech debt", "show me what to fix first", or any question about inactive or outdated metadata.

**Example**
> **You:** "What should we clean up first?"
>
> **You get back:** a ranked list of cleanup candidates, each with its blast radius, when it was last changed, and a recommended action, filtered down to items you can actually remove.

**Tools it uses:** `get_space_context`, `list_reference_models`, `understand_org_health`, `list_metadata_by_criteria`, `get_dependencies`, `get_component_change_history`, `get_org_health_detail`; see [`tools-reference.md`](tools-reference.md).

### Agent Opportunities (`elements-agent-opportunities`)

Scans an entire org's telemetry and schema to find, rank, and justify agentic opportunities ("40 candidates, here are the top 3, and why") without a human architect spending weeks. Read-only: it finds and justifies opportunities; it doesn't build agents.

**Requires:** explanations need the Automation & Execution Intelligence add-on on Core Metadata Management; Advanced Metadata Management includes it.

**When it triggers:** "find agent opportunities", "where should we use agents/AI", "give me an AI roadmap for my org", "scan my org for automation or agent candidates".

**Example**
> **You:** "Scan my org and tell me the top few places we should use an Agentforce agent."
>
> **You get back:** a ranked shortlist of objects, each with its signal vector (record volume, free-text ratio, automation density, growth) and the score factors that justify why it made the list, plus suggested deep-dives for the finalists. For the shortlist it recomputes the free-text ratio from the object's field types (long and rich text areas only), because the scan's own ratio can count short Text fields such as Email or Phone; both ratios are shown.

**Tools it uses:** `scan_agentic_opportunities`, `get_component_usage`, `get_dependencies`, `explain_metadata_components`, `understand_org_health`, `list_reference_models`, `list_metadata_by_criteria`; see [`tools-reference.md`](tools-reference.md).

### Package Uninstall (`elements-package-uninstall`)

Plans the removal of a Salesforce managed package: inventories the package's components (as completely as the licensed tools allow; available metadata coverage determines completeness), sweeps the whole set for incoming dependencies, and classifies each reference as a real uninstall blocker, a package-internal dependency that is auto-removed on uninstall, or a harmless non-issue (standard polymorphic lookups such as Task and Event "Related To" are listed by the tool among the blockers but counted separately, because they clear when the package goes), then flags active automations to deactivate and permission sets/profiles to clean up, and produces a sequenced removal plan. Read-only: it plans the removal and evidences the blockers; it never runs the uninstall.

**When it triggers:** "uninstall this managed package", "remove the X package", "can we get rid of this package", "what would it take to remove <package>", "package removal plan".

**Example**
> **You:** "What would it take to remove the sample managed package?"
>
> **You get back:** the package's components grouped by type (as complete as your Space's licensed tools allow; available metadata coverage determines completeness), an incoming-dependency sweep across them, every reference classified as a blocker / cleanup item / auto-removed / non-issue, the active automations to deactivate first, and a sequenced runbook from resolving blockers through a sandbox dry-run to the production uninstall and post-removal verification.

**Tools it uses:** `get_space_context`, `set_active_space`, `list_reference_models`, `list_managed_packages`, `describe_metadata_schema`, `search_metadata`, `list_metadata_by_criteria`, `plan_package_uninstall`, `get_dependencies`, `get_metadata_component`, `get_access`, `run_code_search`; see [`tools-reference.md`](tools-reference.md).

## Across your orgs

Every skill above answers about one org at a time. This one composes those single-org answers into a comparison across all the orgs in your Space.

### Multi-Org Analytics (`elements-multi-org-analytics`)

Turns the single-org tools into cross-org analytics: discovers the orgs in your Space, runs the same query against each one, writes dated snapshots to disk, and renders a self-contained HTML report you can email to someone with no Elements access and no AI. Every number on the page traces back to the raw response that produced it. Ships a worked inventory template, plus a technical-debt comparison whose pull methodology is available while its report is being redesigned; both are designed for you to customize conversationally into whatever you actually want to measure. Read-only against Salesforce; it writes only the snapshot files and the report on your own machine.

Because it saves a dated snapshot each time it runs, re-running it weekly turns the same report into a trend without any extra setup.

**Requires:** a Space with more than one connected org to be useful; in a one-org Space it points you to Org Diagnostic instead. Reference models you cannot view are not included. Your assistant must be able to run Python.

**When it triggers:** "compare our orgs", "across all our orgs", "give me an overview of our Salesforce orgs", "which org has the most X", "how does our sandbox differ from prod", or anything phrased about an estate or multi-org landscape.

**Example**
> **You:** "Give me an overview of our Salesforce orgs."
>
> **You get back:** the list of orgs it found, grouped by implementation, for you to confirm; then a snapshot pulled from each one and a single HTML report: per-org size, how much is managed-package versus built by you, counts by metadata type, and an as-of stamp per org with any org that has stopped syncing flagged at the top. No judgments: it counts and shows.

**Tools it uses:** `get_space_context`, `list_reference_models`, `describe_metadata_schema`, `list_metadata_by_criteria`, `understand_org_health`; see [`tools-reference.md`](tools-reference.md).

## Model & decide

Skills for structuring and classifying metadata, recommending how to implement a change, and analyzing its impact before you build it.

### MetaFields (`elements-metafields`)

Defines the custom fields your Space uses on Salesforce metadata, wires dependent picklists, populates classifications in bulk (by explicit node ids for judgement passes, or by server-side filters for whole-population passes), and verifies the result. Defining fields and dependencies requires the Space admin role, while populating values requires edit access to the reference model. It can also update definitions, including destructive changes that purge values across synced orgs.

**When it triggers:** "set up MetaFields", "classify our objects by X", "tag metadata with retention priority", "populate MetaFields in bulk".

**Example**
> **You:** "Set up a retention-priority MetaField for our objects, classify them, and verify the result."
>
> **You get back:** the existing MetaField schema and capacity checked first, any approved definitions and dependency matrices created with stable option IDs, the matching metadata classified in bulk, and a read-back count that reconciles the writes and skips.

**Tools it uses:** `get_metafields`, `create_metafield`, `update_metafield`, `set_metafield_values`, `set_metafield_dependency`, `list_metadata_by_criteria`; see [`tools-reference.md`](tools-reference.md).

### Decision Engine (`elements-decision-engine`)

Plans Salesforce automation and schema changes. The assistant inventories existing automations, objects, fields, or record types, recommends approaches, and records your selection. Accepted existing-target options proceed through dependency, impact, and architecture-risk analysis to a delivery draft. Standalone field-impact requests stop after impact unless more is requested. For a field update or deletion, the [field-change recipe](../plugins/elements/skills/elements-decision-engine/references/field-change.md) also traces static references, delete cascades, and the upper-bound runtime fire chain. An accepted create-new schema option proceeds directly to the backlog. Elements stores analysis artifacts; requirements and stories remain drafts.

**Requires:** reference-model edit access and `mcp:decisionEngine:read` scope.
**When it triggers:** "what automation should I add or change", "add a renewal date field on Account", "change this record type", "review the impact of this field change", or "assess architecture risk".

Requests such as "what automation will this trigger" or "what does that trigger next" on a field change use the field-change recipe. Its runtime stage needs view access to the reference model and a fully synced reference model.

Impact-only requests finish at the impact report; recommendation-only and standalone risk requests finish at their requested result.

**Examples:** "Assign Cases by region" follows the automation path. "Add a renewal date on Account" follows schema inventory and recommendation, then branches according to the selected approach. Both produce a chat digest and an evolving local HTML (HyperText Markup Language) report.

**Tools it uses:** `run_automation_inventory`, `run_automation_recommendation`, `run_schema_inventory`, `run_schema_recommendation`, `get_analysis_result`, `run_dependency_scan`, `run_change_impact_analysis`, `run_data_load_impact`, `explain_metadata_components`, `run_architecture_risk_analysis`, `run_backlog_draft`, `list_reference_models`, `search_metadata`, `get_metadata_component`; see [`tools-reference.md`](tools-reference.md).

### Org-to-Process (`elements-org-to-process`)

Generates an org-to-process diagram derived from the org's actual record types and lifecycle fields for a Salesforce lifecycle object (Case, Opportunity, Lead, a custom object): the object's lifecycle field values become the process states, with the automations that move records between them. When an object has several record types, one call generates a diagram per record type for full coverage. Completed diagrams can then be screened for Agentforce agent opportunities: each process activity is assessed against a suitability rubric and returned as a ranked list (Conversational Agent, AI Workflow, or Deterministic Automation, each with a reason).

**When it triggers:** "generate org to process", "show me the Case process", "what's the Opportunity lifecycle", "org to process for [object]", "find agent opportunities in this process".

**Example**
> **You:** "Map our Case process and tell me where an agent would help."
>
> **You get back:** one generated process diagram per Case record type (polled to completion), a business-language walkthrough of the lifecycle states and the automations already in place, and a ranked list of activities suited to an Agentforce agent, an AI workflow, or deterministic automation, each with its reasoning.

On larger diagrams `get_process_map` can return the activities without their transitions; the skill then rebuilds the transitions from the diagram export, which needs Manage access to the diagram.

**Tools it uses:** `list_reference_models`, `search_metadata`, `generate_process_map`, `get_process_map`, `list_process_maps`, `export_diagram`; see [`tools-reference.md`](tools-reference.md).

## Deliver the change

Skills for turning an approved change into diagrams and generated artifacts.

### Diagrams (`elements-diagrams`)

Generates, reads, exports, edits, and re-imports Elements process-map and architecture diagrams. Start a map from one of your diagram templates, or create a Universal Process Notation (UPN) map from a description, transcript, or images; change a level in place, architecture diagrams included (card attributes, footer text, the header icon and line end shapes, by the Salesforce diagram conventions); export a diagram to edit its JSON; and import the edited version back as a DRAFT (releasing an approved version stays a human step in the Elements UI).

**Requires:** the Author role where applicable; view access to read a map, edit access to edit it, and Manage access to export it.

**When it triggers:** "generate a process map", "make a map from this transcript", "start from a template", "read this diagram", "add a step / rename a swimlane / change a flowline", "re-import a diagram into Elements", or when you hand over a `.zip` export from Elements.cloud.

**Example**
> **You:** "Turn this onboarding call transcript into a process map, then add an approval step before go-live."
>
> **You get back:** a generated UPN map, its diagram exported for editing, the approval activity added, and the edited diagram re-imported as a DRAFT for you to review and release in Elements.

**Tools it uses:** `list_process_maps`, `get_process_map_outline`, `get_diagram`, `describe_diagram_schema`, `manage_diagram`, `create_map`, `list_map_templates`, `create_map_from_template`, `list_reference_models`, `search_metadata`, `list_stories`, `get_process_map`, `generate_process_map`, `upload_process_map_image`, `export_diagram`, `import_diagram`; see [`tools-reference.md`](tools-reference.md).

### Stories (`elements-stories`)

Lists existing Elements user stories and generates new ones from selected activities in a process diagram, one story per activity resource with a headline, description, and acceptance criteria.

**Requires:** the requirements manager role to generate stories.

**When it triggers:** "list stories", "what stories exist for this diagram", "generate stories from this diagram", "create user stories from these activities".

**Example**
> **You:** "Generate user stories from the approval and notification steps in this diagram."
>
> **You get back:** the diagram's activities shown so you can pick which to use, then one generated story per activity resource (headline, description, acceptance criteria) for the ones you selected. The skill judges the run from the completed and failed counts and the stories now linked to the diagram, not from the job's status label alone.

**Tools it uses:** `list_stories`, `generate_stories_from_diagram`; see [`tools-reference.md`](tools-reference.md).

## Playbooks

Playbooks are separate plugins that run a complete Salesforce process end to end. See the [playbook overview](playbooks.md) for what they need and how to install them.
