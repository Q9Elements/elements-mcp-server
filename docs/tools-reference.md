# Tools reference

The Elements Model Context Protocol (MCP) server exposes 56 tools. Which tools you see depends on the Spaces you authorize. Role requirements, such as Space admin or Author, and access to a named reference model, diagram, or view are checked when you call a tool; a call without required access is refused with `access_denied`.

The required inputs column names the required selection or the required fields. Other optional fields are described by the tool schema. All data tools accept a Space override, and read tools accept `delivery` where supported. Read `delivery` behavior in [Large results](#large-results).

The Metadata table lists the add-on required by a tool. Roles and access to a named resource are checked when you call a tool.

These labels describe the Model Context Protocol (MCP) annotation each tool sends. **Read-only** means `readOnlyHint: true`; **Writes to Elements** means `readOnlyHint: false` and `destructiveHint: false`; **Destructive in Elements** means `readOnlyHint: false` and `destructiveHint: true`. Whatever its label, every tool reads and changes only data stored in Elements, the Elements database: diagrams, MetaFields, saved views, proposed nodes, Spaces, and this connection's authorization. No tool writes to, deploys to, or deletes anything in a Salesforce org.

- `import_diagram` replaces every DRAFT level of one diagram with the levels in an imported ZIP file. Without `confirm: true`, it changes nothing and returns a preview of the levels it would replace. It updates the DRAFT only; publishing remains a person's action in the Elements user interface.
- `manage_diagram` can remove activities, lines, notes, and text boxes from one diagram level. Removing an activity also removes its attachments and links. Removing more than 5 elements or 30% of a level requires `confirm: true`. Removing an activity with a child level requires `confirmDrilldownRemoval: true` and sends the child level to the recycle bin. Each agent session leaves a history entry of the level before its first change.
- `update_metafield`: narrowing which metadata types a MetaField applies to, or removing options, irreversibly deletes those values from every node that holds them across every reference model in the implementation. The tool first returns a preview of affected nodes and applies the change only when repeated with `confirm: true`.
- `revoke_access` revokes this MCP client's authorization to Elements. The next request starts the authorization flow again. It deletes no data and requires `confirm: true`.

## Spaces

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `get_space_context` (Read-only) | Shows the active Space and pages Spaces authorized for this connection. | No required inputs. Optional: teamId, skip, pageSize. | `mcp:spaces:read` |  |
| `set_active_space` (Writes to Elements) | Selects the Space for following calls. | teamId. | `mcp:spaces:read` |  |
| `create_space` (Writes to Elements) | Creates an Elements Space. | name; optional prefix, description. | `mcp:spaces:create` |  |
| `revoke_access` (Destructive in Elements) | Revokes this client connection after confirmation. | confirm: true. | None | At least one consented Space must have an active membership and not be suspended; otherwise revoke the connection from the Connected apps tab in Elements. Confirmation required. |

## Metadata

| Tool | What it does | Required inputs | Required scope | Required add-on* | Access requirements |
|---|---|---|---|---|---|
| `list_reference_models` (Read-only) | Lists Salesforce reference models available in a Space. | No required inputs. Optional: teamId, search. | `mcp:spaces:read` |  |  |
| `get_dependencies` (Read-only) | Returns dependency rows for selected metadata nodes. | refModelId, nodeIds or nodeId; direction and metadata selection options. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_metadata_component` (Read-only) | Returns fields or relationships for a metadata node. | refModelId and exactly one of nodeId or nodeIds; optional page.list for single-component paging. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `explain_metadata_components` (Read-only) | Explains metadata behavior in plain English. | aspect and metadata node selection; refModelId when identifying a node. | `mcp:metadata:read` | Automation & Execution Intelligence* |  |
| `run_data_load_impact` (Read-only) | Analyzes automation and record-lock impact for a planned data load. | refModelId and one or more target definitions. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `search_metadata` (Read-only) | Finds reference-model metadata by search terms. | refModelId, search terms. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_component_change_history` (Read-only) | Lists change history for a metadata component. | refModelId, nodeId. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_component_usage` (Read-only) | Returns usage and telemetry for an object. | refModelId, nodeId. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_metadata_source` (Read-only) | Returns source for selected metadata nodes. | refModelId, nodeIds. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_access` (Read-only) | Audits access granted to selected metadata nodes. | refModelId and nodeId or nodeIds. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `describe_metadata_schema` (Read-only) | Describes available metadata types and query columns. | refModelId; optional metadataList or allNodes. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `list_metadata_by_criteria` (Read-only) | Lists metadata matching criteria or a saved cleanup view. | refModelId; criteria or a view id. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `save_metadata_view` (Writes to Elements) | Saves a metadata criteria view. | refModelId, name, viewSpec. | `mcp:metadata:write` |  | edit access to the reference model |
| `create_proposed_node` (Writes to Elements) | Adds a proposed metadata node to a reference model. | refModelId, metadataType, label, apiName, parentId identifying the parent container. | `mcp:metadata:write` |  | edit access to the reference model. |
| `list_managed_packages` (Read-only) | Lists managed packages and component counts. | refModelId. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `plan_package_uninstall` (Read-only) | Plans a managed package removal and identifies dependencies. | refModelId, package selection. | `mcp:metadata:read` |  | view access to the reference model where required. |
| `get_metafields` (Read-only) | Lists MetaField definitions and dependencies. | No required inputs; optional implementationId and filters. | `mcp:metadata:read` |  |  |
| `create_metafield` (Writes to Elements) | Creates a MetaField definition. | implementation, title, type, appliesTo; list and multi-picklist types also require options. | `mcp:metadata:write` |  | Space admin role. |
| `update_metafield` (Destructive in Elements) | Updates a MetaField definition. | metafieldId and at least one definition field. | `mcp:metadata:write` |  | Space admin role. |
| `set_metafield_values` (Writes to Elements) | Sets MetaField values on selected nodes. | refModelId and assignments: [{metafieldId, values: [...]}]; each value selects nodes with nodeIds or nodeFilter. | `mcp:metadata:write` |  | edit access to the reference model. |
| `set_metafield_dependency` (Writes to Elements) | Creates or replaces the dependency matrix between two MetaFields; values already on nodes are never deleted. | controllerId, dependentId, relationMap. | `mcp:metadata:write` |  | Space admin role. |
| `list_metadata_changes` (Read-only) | Lists metadata change records in a date range. | refModelId; optional fromDate, toDate, metadataTypes, status. | `mcp:metadata:read` |  | view access to the reference model where required. |

\* Advanced Metadata Management includes every add-on. On Core Metadata Management, this add-on is required in addition to Agentic Org Management, which the MCP server itself requires.

## Org health

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `understand_org_health` (Read-only) | Returns a selected org-health dimension. | refModelId, area. | `mcp:metadata:read` | view access to the reference model. |
| `get_org_health_detail` (Read-only) | Returns detail rows for an org-health chart or item. | refModelId, chartType; chart-specific detail inputs. | `mcp:metadata:read` | view access to the reference model. |

## Agent opportunities

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `scan_agentic_opportunities` (Read-only) | Ranks objects for agentic opportunities using usage signals. | refModelId. | `mcp:metadata:read` | view access to the reference model where required. |

## Diagrams

| Tool | What it does | Read/Write | Required scope | Per-resource check |
|---|---|---|---|---|
| `list_process_maps` (Read-only) | Lists process maps by name fragment or folder and reports your role and edit rights for each map. | Read | `mcp:diagrams:read` |  |
| `get_process_map_outline` (Read-only) | Lists every level of one process map: titles, how levels nest, activity counts, and publish and edit status, including a map still being copied from a template. | Read | `mcp:diagrams:read` | View access to that map |
| `get_diagram` (Read-only) | Reads one level of a process map or architecture diagram: activities, resources and RASCI (Responsible, Accountable, Support, Consulted, Informed), lines, notes and text boxes, with optional layout and attachments. | Read | `mcp:diagrams:read` | View access to that map |
| `describe_diagram_schema` (Read-only) | Returns JSON Schema for `get_diagram` and `manage_diagram`, including diagram fields and issue codes | Read | `mcp:diagrams:read` |  |
| `manage_diagram` (Destructive in Elements) | Changes one level of a diagram in place: adds, updates, moves or removes activities, resources, lines, notes and text boxes, adds child levels and attachments. Previews the change first; large removals and removing a child level need your confirmation. | Write | `mcp:diagrams:create` | Diagram edit access, including level edit rights where applicable; manage role on the map to change the top level's title or description; edit or manage role on the reference model to attach its metadata |
| `create_map` (Writes to Elements) | Creates a new, empty map with one blank top-level diagram. | Write | `mcp:diagrams:create` | Author role ("You don't have permission to create maps in this space.");  |
| `list_map_templates` (Read-only) | Lists the diagram templates you can start a map from. | Read | `mcp:diagrams:read` |  |
| `create_map_from_template` (Writes to Elements) | Starts a new map as a copy of a template; the copy runs in the background. | Write | `mcp:diagrams:create` | Author role ("You don't have permission to create maps in this space."); View access and Can copy on the template |
| `get_process_map` (Read-only) | Polls for completion after process-map generation and returns generated process-map details; to read a diagram, use `get_diagram` | Read | `mcp:diagrams:read` | View access to that diagram |
| `generate_process_map` (Writes to Elements) | Generates a process map from text or images, or from a Salesforce lifecycle object; poll `get_process_map` for completion. | Write | `mcp:diagrams:create` | Author role; edit access to the reference model for `org_object` source |
| `upload_process_map_image` (Writes to Elements) | Uploads an image for use as input to process-map generation | Write | `mcp:diagrams:create` | Author role. |
| `export_diagram` (Read-only) | Exports a diagram as a ZIP (map plus per-level JSON) with presigned download and upload URLs, for editing and re-import | Read | `mcp:diagrams:read` | Manage access to that diagram |
| `import_diagram` (Destructive in Elements) | Imports an edited diagram ZIP back into Elements, replacing the current DRAFT in place; releasing an approved version stays a human step in the Elements UI | Write | `mcp:diagrams:create` | Author role; Edit access to that diagram |

## Stories

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `list_stories` (Read-only) | Lists stories in a Space or on a diagram. | No required inputs. Optional: diagramId, skip, limit, mode. | `mcp:stories:read` |  |
| `generate_stories_from_diagram` (Writes to Elements) | Generates draft stories from diagram activities. | mapId; optional activityMxKeys to select activities. | `mcp:stories:create` | requirements manager role; edit access to the diagram. |

## Decision Engine

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `run_automation_inventory` (Read-only) | Inventories automation relevant to a proposed change. | refModelId, request. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_automation_recommendation` (Read-only) | Recommends automation implementation options. | refModelId, missionId. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_dependency_scan` (Read-only) | Scans direct dependencies for a proposed change. | refModelId; missionId or standalone target. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_change_impact_analysis` (Read-only) | Analyzes the impact of a proposed change. | refModelId, missionId, change description. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_architecture_risk_analysis` (Read-only) | Analyzes architecture risks in a proposed change. | refModelId and missionId or standalone target. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_backlog_draft` (Read-only) | Drafts requirements and stories for delivery. | refModelId, missionId. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_schema_inventory` (Writes to Elements) | Inventories schema related to a proposed change. | refModelId, request. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `run_schema_recommendation` (Read-only) | Recommends schema implementation options. | refModelId, missionId. | `mcp:decisionEngine:read` | edit access to the reference model. |
| `get_analysis_result` (Read-only) | Retrieves a Decision Engine mission result. | refModelId, missionId. | `mcp:decisionEngine:read` | edit access to the reference model. |

## Playbook tools

| Tool | What it does | Required inputs | Required scope | Access requirements |
|---|---|---|---|---|
| `has_event_monitoring` (Read-only) | Checks whether Apex event monitoring data is available for a reference model. | refModelId. | `mcp:metadata:read` | view access to the reference model. |
| `get_unused_apex_candidates` (Read-only) | Ranks potentially unused Apex using synced metadata and telemetry. | refModelId. | `mcp:metadata:read` | view access to the reference model. |
| `run_code_search` (Read-only) | Searches indexed source for literal text. | refModelId, query. | `mcp:metadata:read` | view access to the reference model. |

## Large results

Six tools always return result rows as downloadable part files: `get_dependencies`, `get_access`, `run_code_search`, `list_metadata_changes`, `list_metadata_by_criteria`, and `get_metadata_source`. They return NDJSON (newline-delimited JSON) or comma-separated values (CSV) where supported. Tools with a manifest mode can return counts without row files. These tools use `partsFrom` to list additional parts; their rows do not use `skip` and `limit`. Five accept the dispatcher `delivery` field, which does not change their file-based rows; it can move an oversized manifest reply to a file. `list_metadata_changes` does not accept `delivery`.

Other read tools answer inline. The dispatcher has a 30,000-character response budget. If a reply exceeds it, large values or lists move to a file or are shortened with a continuation hint. `delivery: "file"` requests a file only when the reply exceeds that budget; smaller replies stay inline. File-only results stop at 2,000,000 rows or 2 GiB total. A read that takes longer than 60 seconds for a batch can fail with a timeout. Each reply states how long its links last (`expiresInSeconds`); call again for fresh links.

## Writes

Tools that write change Elements content or connection state. They do not change Salesforce. `revoke_access` ends the connection. Diagram changes affect working drafts; publishing remains a human action in Elements.
