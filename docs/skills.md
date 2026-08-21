# Skills catalog

You don't call tools directly; you ask your assistant for what you want, in plain language, and it picks the right skill. A skill is a packaged capability: it decides which underlying tools to call, in what order, and how to present the result. Tools, in turn, are gated by the connection's scopes and by your own Elements permissions (see [`scopes.md`](scopes.md)).

Elements organizes its capabilities around three steps: **understand your org**, **model & decide** what to change, and **deliver the change**. Skills are grouped the same way below, so the catalog grows one step at a time as later releases ship.

## Understand your org

These thirteen skills are available now. They're all read-only against your Salesforce Org: nothing they do changes Salesforce. Some can additionally create or change artifacts held in Elements. Most of those are purely additive: the Spaces skill can create a new Space, Metadata Query can save a view, and Diagrams and Stories can create Elements content. **MetaFields is the exception: it overwrites.** Populating a classification replaces whatever value a node already held, and updating a MetaField definition can irreversibly purge values across every synced org in the implementation. Count what you are about to change before you change it; the skill carries the recipe.

Each skill lists what it **Requires**: the Space plan, license, or role its tools are gated on. Plan, license, and role gates can hide tools from your assistant entirely, so a skill may report a capability as unavailable because of your role; see [security](security.md#you-choose-what-a-connection-can-do).

### Spaces (`elements-spaces`)

Lists, switches, and creates Elements Spaces, the workspace an assistant operates in.

**Requires:** any MCP-enabled Space.

**When it triggers:** "create a space", "switch to a different space", "list my spaces", "what space am I in", or any question about space setup, consulting Spaces, or Space permissions.

**Example**
> **You:** "What Space am I in, and can you switch me to the Acme project Space?"
>
> **You get back:** confirmation of your current Space, the list of Spaces you're authorized for, a switch to the one you asked for, and confirmation of the change.

**Tools it uses:** `get_active_space`, `list_authorized_spaces`, `set_active_space`, `create_space`; see [`tools-reference.md`](tools-reference.md).

### Metadata Explorer (`elements-metadata`)

Finds and explains individual Salesforce metadata nodes (objects, fields, flows, triggers, validation rules) with answers resolved from the org's synced metadata, not inferred, using keyword search, full node detail, dependency tracing, and a plain-English explanation of what an automation does.

**Requires:** Pro Space; the plain-English automation explanation also needs GPT features enabled for the Space.

**When it triggers:** "show me the metadata for…", "what fields does this object have", "explain this flow", "what depends on this".

**Example**
> **You:** "Explain the loyalty points flow and show me what depends on it."
>
> **You get back:** the flow resolved by name, its upstream and downstream dependencies grouped by type, and a narrative covering what it does, when it runs, what it touches, and why it's risky.

**Tools it uses:** `list_reference_models`, `metadata_search`, `get_metadata_node`, `get_dependencies`, `explain_metadata_item`, `get_access`, `list_supported_metadata_types`; see [`tools-reference.md`](tools-reference.md).

### Access Audit (`elements-access`)

Audits permission-level access to a single metadata node (which Profiles, Permission Sets, Permission Set Groups, and Groups grant access, and to how many users), plus a per-user "why do they have access" lookup. It does not list individual users by name.

**Requires:** Pro Space.

**When it triggers:** "who has access to this object/field", "audit access", "what does this profile/permission set grant", "who can edit this field and why".

**Example**
> **You:** "Who can edit the credit limit field, and how many people does each grant reach?"
>
> **You get back:** the field resolved by name, then each Profile, Permission Set, and Group that grants edit access, with an assigned-user count per grant (no individual names).

**Tools it uses:** `get_access`, `list_reference_models`, `metadata_search`, `get_metadata_node`; see [`tools-reference.md`](tools-reference.md).

### Metadata Query / Custom Views (`elements-metadata-query`)

Builds a filtered, ad-hoc list of metadata by attribute (for example, every flow on an old API version) and can save the result as a named custom view, shared or private.

**Requires:** Enterprise Space.

**When it triggers:** "all screen flows", "every Apex class with low test coverage", "fields with population over X on an object", "list inactive validation rules", "build a view of…", "save this as a view".

**Example**
> **You:** "List all screen flows on an API version below the latest, and save it as a view."
>
> **You get back:** the filterable columns discovered for flows, the matching rows with a total count, and, if you confirm, a saved named view you can reuse later.

**Tools it uses:** `list_reference_models`, `list_metadata_columns`, `query_metadata`, `save_metadata_view`, `list_supported_metadata_types`; see [`tools-reference.md`](tools-reference.md).

### Org Diagnostic (`elements-org-diagnostic`)

Runs a broad baseline health check across structure, automation, tech debt, compliance, and governance, and synthesizes one ranked risk summary, optionally enriched with field-population and dependency hotspots.

**Requires:** Pro Space + Analytics Cloud license; the dependency-hotspot enrichment also needs an Enterprise Space.

**When it triggers:** "run an org diagnostic", "check org health", "give me a first-pass assessment", "where should we look first".

**Example**
> **You:** "Run an org diagnostic and tell me where to look first."
>
> **You get back:** a severity rating and top concerns for each of the five dimensions, an overall risk level with a short narrative, a saved report, and an offer to drill into the worst areas.

**Tools it uses:** `get_active_space`, `list_reference_models`, `get_org_structure`, `get_automation_health`, `get_tech_debt_summary`, `get_compliance_summary`, `get_governance_summary`, `get_field_population`, `get_object_dependency_analysis`, `get_analytic_drill_down`, `get_object_dependency_drill_down`; see [`tools-reference.md`](tools-reference.md).

### Change Briefing (`elements-change-briefing`)

Reports every metadata node changed in a date window (classified new, updated, or deleted), with an overall velocity figure, a breakdown by metadata type, anomaly highlights, and the Salesforce metadata for the most significant changes.

**Requires:** Pro Space + Analytics Cloud license.

**When it triggers:** "what changed recently", "give me a change briefing", "list all changes this month", or any question about unusual or unexpected changes.

**Example**
> **You:** "What changed in the org this week, and were there any unusual spikes?"
>
> **You get back:** a velocity headline and by-type breakdown for the week, the list of changed nodes, any anomalies flagged, and the underlying metadata pulled for the most significant changes.

**Tools it uses:** `get_active_space`, `list_reference_models`, `get_governance_summary`, `get_analytic_drill_down`, `get_metadata_node`, `get_node_change_history`; see [`tools-reference.md`](tools-reference.md).

### Tech Debt (`elements-tech-debt`)

Deep-dives the tech-debt dimension: resolves flagged nodes, checks each one's dependency blast radius and how recently it was touched, and produces a ranked, actionable remediation list.

**Requires:** Pro Space + Analytics Cloud license; the quick clean-up views also need an Enterprise Space.

**When it triggers:** "investigate tech debt", "show me what to fix first", or any question about inactive or outdated metadata.

**Example**
> **You:** "What should we clean up first?"
>
> **You get back:** a ranked list of cleanup candidates, each with its blast radius, when it was last changed, and a recommended action, filtered down to items you can actually remove.

**Tools it uses:** `get_active_space`, `list_reference_models`, `get_tech_debt_summary`, `run_quick_cleanup_view`, `get_dependencies`, `get_node_change_history`, `get_analytic_drill_down`; see [`tools-reference.md`](tools-reference.md).

### Agent Opportunities (`elements-agent-opportunities`)

Scans an entire org's telemetry and schema to find, rank, and justify agentic opportunities ("40 candidates, here are the top 3, and why") without a human architect spending weeks. Read-only: it finds and justifies opportunities; it doesn't build agents.

**Requires:** Pro Space; some enrichment steps also use GPT features and Enterprise-gated dependency analytics.

**When it triggers:** "find agent opportunities", "where should we use agents/AI", "give me an AI roadmap for my org", "scan my org for automation or agent candidates".

**Example**
> **You:** "Scan my org and tell me the top few places we should use an Agentforce agent."
>
> **You get back:** a ranked shortlist of objects, each with its signal vector (record volume, free-text ratio, automation density, growth) and the score factors that justify why it made the list, plus suggested deep-dives for the finalists.

**Tools it uses:** `scan_agentic_opportunities`, `get_object_usage`, `get_dependencies`, `explain_metadata_item`, `get_field_population`, `get_object_dependency_analysis`, `list_reference_models`; see [`tools-reference.md`](tools-reference.md).

### Package Uninstall (`elements-package-uninstall`)

Plans the removal of a Salesforce managed package: inventories the package's components (as completely as the licensed tools allow; Enterprise is authoritative), sweeps the whole set for incoming dependencies, and classifies each reference as a real uninstall blocker, a package-internal dependency that is auto-removed on uninstall, or a harmless non-issue, then flags active automations to deactivate and permission sets/profiles to clean up, and produces a sequenced removal plan. Read-only: it plans the removal and evidences the blockers; it never runs the uninstall.

**Requires:** Pro Space (inventory via search); Enterprise unlocks query-based inventory; code search additionally needs the Dependency Explorer license.

**When it triggers:** "uninstall this managed package", "remove the X package", "can we get rid of this package", "what would it take to remove <package>", "package removal plan".

**Example**
> **You:** "What would it take to remove the Consensus managed package?"
>
> **You get back:** the package's components grouped by type (as complete as your Space's licensed tools allow; Enterprise is authoritative), an incoming-dependency sweep across them, every reference classified as a blocker / cleanup item / auto-removed / non-issue, the active automations to deactivate first, and a sequenced runbook from resolving blockers through a sandbox dry-run to the production uninstall and post-removal verification.

**Tools it uses:** `get_active_space`, `set_active_space`, `list_reference_models`, `list_managed_packages`, `list_supported_metadata_types`, `metadata_search`, `list_metadata_columns`, `query_metadata`, `plan_package_uninstall`, `get_dependencies`, `get_metadata_node`, `get_access`, `code_search`; see [`tools-reference.md`](tools-reference.md).

## Model & decide

Skills for structuring and classifying metadata, recommending how to implement a change, and analyzing its impact before you build it.

### MetaFields (`elements-metafields`)

Defines the custom fields your Space uses on Salesforce metadata, wires dependent picklists, populates classifications in bulk (by explicit node ids for judgement passes, or by server-side filters for whole-population passes), and verifies the result. Defining fields and dependencies requires the Space admin role, while populating values requires edit access to the reference model. It can also update definitions, including destructive changes that purge values across synced orgs.

**Requires:** Enterprise Space

**When it triggers:** "set up MetaFields", "classify our objects by X", "tag metadata with retention priority", "populate MetaFields in bulk".

**Example**
> **You:** "Set up a retention-priority MetaField for our objects, classify them, and verify the result."
>
> **You get back:** the existing MetaField schema and capacity checked first, any approved definitions and dependency matrices created with stable option IDs, the matching metadata classified in bulk, and a read-back count that reconciles the writes and skips.

**Tools it uses:** `list_metafields`, `create_metafield`, `update_metafield`, `set_metafield_values`, `list_metafield_dependencies`, `create_metafield_dependency`, `update_metafield_dependency`, `query_metadata`; see [`tools-reference.md`](tools-reference.md).

### Org-to-Process (`elements-org-to-process`)

Generates an org-to-process diagram derived from the org's actual record types and lifecycle fields for a Salesforce lifecycle object (Case, Opportunity, Lead, a custom object): the object's lifecycle field values become the process states, with the automations that move records between them. When an object has several record types, one call generates a diagram per record type for full coverage. Completed diagrams can then be screened for Agentforce agent opportunities: each process activity is assessed against a suitability rubric and returned as a ranked list (Conversational Agent, AI Workflow, or Deterministic Automation, each with a reason).

**Requires:** Pro Space + Org-to-Diagram license.

**When it triggers:** "generate org to process", "show me the Case process", "what's the Opportunity lifecycle", "org to process for [object]", "find agent opportunities in this process".

**Example**
> **You:** "Map our Case process and tell me where an agent would help."
>
> **You get back:** one generated process diagram per Case record type (polled to completion), a business-language walkthrough of the lifecycle states and the automations already in place, and a ranked list of activities suited to an Agentforce agent, an AI workflow, or deterministic automation, each with its reasoning.

**Tools it uses:** `list_reference_models`, `metadata_search`, `generate_org_to_process`, `get_process_map`; see [`tools-reference.md`](tools-reference.md).

## Deliver the change

Skills for turning an approved change into diagrams and generated artifacts.

### Diagrams (`elements-diagrams`)

Generates, reads, exports, edits, and re-imports Elements process-map diagrams. Create a UPN map from a description, transcript, or images; export a diagram to edit its JSON; and import the edited version back as a DRAFT (releasing an approved version stays a human step in the Elements UI).

**Requires:** any MCP-enabled Space; generating, uploading, or importing needs the Author role; exporting a diagram for editing needs a Pro Space; listing and reading need no role.

**When it triggers:** "generate a process map", "make a map from this transcript", "read this diagram", "add a step / rename a swimlane / change a flowline", "re-import a diagram into Elements", or when you hand over a `.zip` export from Elements.cloud.

**Example**
> **You:** "Turn this onboarding call transcript into a process map, then add an approval step before go-live."
>
> **You get back:** a generated UPN map, its diagram exported for editing, the approval activity added, and the edited diagram re-imported as a DRAFT for you to review and release in Elements.

**Tools it uses:** `list_diagrams`, `get_process_map`, `generate_process_map`, `upload_process_map_image`, `export_diagram`, `import_diagram`; see [`tools-reference.md`](tools-reference.md).

### Stories (`elements-stories`)

Lists existing Elements user stories and generates new ones from selected activities in a process diagram, one story per activity resource with a headline, description, and acceptance criteria.

**Requires:** Pro Space + story-generation license; generating (not just listing) also needs an Enterprise-active Space and the Requirements Manager role.

**When it triggers:** "list stories", "what stories exist for this diagram", "generate stories from this diagram", "create user stories from these activities".

**Example**
> **You:** "Generate user stories from the approval and notification steps in this diagram."
>
> **You get back:** the diagram's activities shown so you can pick which to use, then one generated story per activity resource (headline, description, acceptance criteria) for the ones you selected.

**Tools it uses:** `list_stories`, `generate_stories_from_diagram`; see [`tools-reference.md`](tools-reference.md).
