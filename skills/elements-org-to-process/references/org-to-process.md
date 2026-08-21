# Org-To-Process Workflow

Generate, retrieve, inspect, or explain an Elements org-to-process diagram for a Salesforce lifecycle object such as Case or Opportunity.

## Generation Inputs

**Required:**

- `refModelId`: Elements reference model containing the Salesforce metadata
- `objectApiName`: Salesforce object API name (e.g. `Case`, `Opportunity`)

**Optional — `generate_org_to_process` resolves these itself (see Phase 3):**

- `lifecycleFieldApiName`: lifecycle/status field (e.g. `Status`, `StageName`)
- `recordTypeDeveloperName`: record type developer name
- `workflowFieldApiName`: workflow field (reserved objects only: Case, Lead, Opportunity)

For the **lifecycle and workflow fields** the tool: auto-selects when there is exactly one candidate; returns a `clarificationNeeded` prompt when there are several; proceeds without one where valid (a non-reserved object has no workflow field); and returns a not-found error **with the available list** when a specified value doesn't exist. **Record types never clarify**: omitted → the tool fans out one diagram per record type in the same call (or a single no-record-type diagram when only Master exists); specified → a single diagram (not-found error with the available list if the name doesn't exist).

## Concurrency Constraint

One `generate_org_to_process` call handles all record types of an object itself (server-side fan-out) — never issue multiple generate calls for the same object to cover its record types. The server holds a per-object generation lock for the duration of each async generation, so a **separate** generate call for an object that is still generating surfaces an "already running" error; wait for its diagrams to complete first. Generate calls for **different objects**, and read-only calls (`get_process_map`, `metadata_search`), can run in parallel freely.

---

## Phase 1: Space

Call `get_active_space`. Resolve space if needed (see Space Context in SKILL.md).

---

## Phase 2: Read Existing Diagram (if diagramId already known)

If the user provides a `diagramId`, call `get_process_map` and skip directly to **Phase 5**.

---

## Phase 3: Resolve Generation Inputs

`generate_org_to_process` now resolves the optional inputs itself, so there are two paths:

**Direct (recommended when the object is known):** call `generate_org_to_process` with just `refModelId` + `objectApiName`. If it returns `clarificationNeeded`, handle it (below) and call again with the chosen value set. Repeat until it returns `status: "running"`. The tool auto-selects lone candidates and proceeds without a record type when only Master exists — so a single-record-type, single-status-field object generates with no prompting at all.

**Discovery (freeform question, or to browse before generating):**

1. If no `refModelId`, call `list_reference_models`. Use the only `generationEligible` model automatically; show a picklist if multiple are returned.
2. If the user gave a freeform question, map their business language to candidate Salesforce object API names yourself (you are the LLM — there is no deconstruction tool), then verify with `metadata_search` using query variants constrained by `sfType: "Standard Object"` / `"Custom Object"` (e.g. "deals" → `["Opportunity", "Deal", "Deal__c"]`). Show the real matches as a concise picklist and ask the user to choose when more than one matches. See "Resolving a business question to an object" in SKILL.md.
3. Record types and lifecycle/workflow fields are resolved inline: `generate_org_to_process` fans out over record types itself and returns a `clarificationNeeded` prompt (with the available options) when a lifecycle or workflow field is ambiguous.

Do not invent Salesforce API names — pass values returned by `metadata_search` (or supplied by the user).

### Handling `clarificationNeeded`

`generate_org_to_process` may return `{clarificationNeeded: true, field, question, options, hint}` instead of starting generation. This is **not** an error. Show the `question` and `options` (each has `label` + `value`), ask the user to choose, then re-call `generate_org_to_process` with that `field` set to the chosen `value`, **keeping the inputs already provided**. Only lifecycle field and workflow field ever ask for clarification (resolution order lifecycle field → workflow field, so up to two in sequence); record types are never a clarification — the tool fans out over them automatically.

---

## Phase 4: Generate

Call `generate_org_to_process` with the resolved inputs. It returns immediately with `status: "running"` and a `diagrams[]` array — one entry per record type when the object has several (fan-out), otherwise a single entry. Each entry carries its own `diagramId`, `diagramUrl`, and `recordTypeDeveloperName`. If some record types failed to start, the response also carries an `errors[]` array (`recordTypeDeveloperName` + `error` each) alongside the diagrams that did start — poll the started ones and report the failures. Report how many diagrams generation started (the `message` states "Started X of Y").

---

## Phase 5: Poll and Interpret

Poll each returned `diagramId` with `get_process_map` in 30-second increments until `status: "complete"` or failed.

When `status: "complete"`, answer using the `process` object, not the raw visual diagram.

---

## Interpreting Results

- `process.metadata`: diagram name, description, subtype, state, activity and transition counts
- `process.lifecycleStates`: lifecycle/status values and associated activity ids
- `process.activities`: process steps with text, resources, and source Salesforce attachments; join with
  `lifecycleStates[].activityIds` for each activity's lifecycle state
- `process.transitions`: directed links between activities with optional labels
- `process.automations`: automation activities — assignment rules, flows, auto-response rules, global actions,
  or resources typed System or Industry
- `process.warnings`: serializer caveats (e.g. visual connectors that could not be mapped to activities)

Prefer business-language answers. Mention implementation details like `mxKey` only when diagnosing diagram structure.

**Lifecycle questions:** start from `lifecycleStates`, then inspect related `activities` and `transitions`.

**Automation questions:** start from `automations`, include source attachment type and name when present.

**Path questions:** use `transitions`. If transitions contain unmapped endpoints, state that the exported diagram has visual connectors that could not be mapped to process activities.

**Completeness/audit questions:** include counts from `metadata` and summarise any `warnings`.
