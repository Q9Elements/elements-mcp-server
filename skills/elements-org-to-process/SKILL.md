---
name: elements-org-to-process
description: Generate, retrieve, and interpret Elements org-to-process diagrams derived from the org's actual record types and lifecycle fields for Salesforce lifecycle objects such as Case or Opportunity, and find Agentforce agent opportunities in them. Use when user says "generate org to process", "show me the Case process", "what's the Opportunity lifecycle", "org to process for [Salesforce object]", "find agent opportunities in this process", or asks about a Salesforce lifecycle object diagram. Do NOT use for an org-wide agent-opportunity scan across every object with no process diagram in hand; use elements-agent-opportunities instead.
---

# elements-org-to-process

## Tools

| Tool | Purpose |
|------|---------|
| `get_active_space` / `set_active_space` / `list_authorized_spaces` | Space management |
| `list_reference_models` | List available Salesforce reference models |
| `metadata_search` | Resolve business language to real Salesforce objects (verify candidate API names before generating) |
| `generate_org_to_process` | Start async generation; fans out one diagram per record type, auto-selects or asks about lifecycle/workflow fields. Returns `diagrams[]` (each with a `diagramId`) or a `clarificationNeeded` prompt |
| `get_process_map` | Poll a `diagramId` for the completed skinny process map |

Finding agent opportunities is **not** a tool — you do it yourself by applying
[references/agent-finder.md](references/agent-finder.md) to the skinny map from `get_process_map`.

## Quick start

**Object known:** `get_active_space` → `generate_org_to_process` (just `refModelId` + `objectApiName`) →
answer any `clarificationNeeded` prompts → poll each returned `diagramId` with `get_process_map` until
complete.

**Freeform / browsing:** `get_active_space` → `list_reference_models` → map the user's words to candidate
objects yourself, verify with `metadata_search` (see below) → `generate_org_to_process` → poll
`get_process_map`.

Then, when the map is complete, offer to find agent opportunities — read
[references/agent-finder.md](references/agent-finder.md) and apply it to the skinny map.

## Resolving a business question to an object

There is no question-deconstruction tool — you are the LLM, so map the user's business language to candidate
Salesforce object API names yourself, then **verify** them with `metadata_search` before generating:

- Generate query variants for the user's term. "deals" → `["Opportunity", "Deal", "Deal__c"]`; "tickets" →
  `["Case", "Ticket__c"]`; "prospects" → `["Lead", "Contact"]`.
- Call `metadata_search` for the variants, constraining with `sfType: "Standard Object"` and
  `sfType: "Custom Object"`, and use the returned, real API names — never invent Salesforce API names.
- If several real objects match, show a short picklist and let the user choose.
- Pass the confirmed `objectApiName` (and `refModelId`) to `generate_org_to_process`.

## Generating the map

`generate_org_to_process` takes `refModelId` + `objectApiName` (required) and optional
`lifecycleFieldApiName`, `recordTypeDeveloperName`, `workflowFieldApiName`, `teamId` (`teamId` required only
when the token spans multiple spaces). It starts asynchronous generation and returns an envelope
`{status: "running", message, inputs, resolved, diagrams: [...]}` — never a bare array. When some record
types fail to start, the envelope also carries `errors: [{recordTypeDeveloperName, error}, ...]` alongside
the diagrams that did start (the `message` reads "Started X of Y"); poll the started diagrams and report
the failures. Requires a Pro Space with the org-to-diagram (Enterprise) license; scope `diagrams:create`.

- **Record-type fan-out:** when the object has multiple record types and you do **not** pass
  `recordTypeDeveloperName`, the tool fans out — one diagram **per record type** — for full coverage. Each
  is a `diagrams[]` entry with its own `diagramId`, `diagramUrl`, `recordTypeDeveloperName`, and
  `status: "running"`. Pass `recordTypeDeveloperName` to restrict to one (a not-found error lists the
  available names if it doesn't exist). An object with no record types (or only Master) produces a single
  diagram with `recordTypeDeveloperName: null`. Each diagram covers **all** values of the lifecycle field
  (they become the lifecycle states), so per-record-type fan-out is complete coverage.
- **`clarificationNeeded`:** the lifecycle field is resolved once at object level; workflow fields apply to
  reserved objects (Case / Opportunity / Lead) and are resolved per record type before any generation
  starts. For either, if several candidates exist and none was specified, the tool returns
  `{clarificationNeeded: true, field, question, options, hint}` instead of generating. This is not an error —
  relay the `question` and `options` (each has `label` + `value`) to the user, then call
  `generate_org_to_process` again with that `field` set to the chosen `value`, keeping the inputs already
  provided. A lone lifecycle/workflow field is auto-selected with no prompt.
- **Poll:** poll each `diagrams[].diagramId` with `get_process_map` every 30s until `status` is `complete`
  (or failed).

## Finding Agent Opportunities

Once `get_process_map` returns a completed UPN diagram, offer to find Agentforce agent opportunities. This is
a rubric you apply directly — **read [references/agent-finder.md](references/agent-finder.md)** and run it
against the skinny map. It yields a ranked list of activities, each with an `agentType` (Conversational
Agent, AI Workflow, or Deterministic Automation) and a `reason`, keeping only activities that clear the
rubric's 80% confidence gate.

When the findings land, offer to deliver them as a **persistent report** (HTML/Markdown file, or your
client's shareable page mechanism): a recommendations section with the evidence quoted from the skinny
map(s), plus one section per record-type diagram summarising how that process runs, with a link to the
diagram — the reference's "Step 4b" describes the structure.

This output is conversation-level only and is not written back to Elements. If the user wants to turn one of
the opportunities into a delivery backlog, hand off to the `elements-stories` skill.

## Space Context

Call `get_active_space` first. If `isSet: false` and `activeTeamId` is null, call `list_authorized_spaces`,
show options, ask user to choose, then call `set_active_space`. If `activeTeamId` is non-null, announce the
default and proceed.

## Workflow

Read [references/org-to-process.md](references/org-to-process.md) before starting any task.
