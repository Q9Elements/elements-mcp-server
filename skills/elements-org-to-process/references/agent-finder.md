# Agent Finder — find agent opportunities in a UPN / org-to-process map

You apply this rubric **yourself** against the skinny process map returned by `get_process_map`. The Agent
Finder is one system prompt plus a JSON payload of the diagram, and you (the MCP client) are the LLM that
prompt was written for. Build the payload from the skinny map, run the rubric, and return the ranked
opportunity list directly in the conversation.

> The rubric below carries the wording of the `AGENT_FINDER` recommendation type, so a run here and a run
> in Elements reach the same categories from the same evidence.

> **No server-side persistence.** The production route writes its recommendations to the diagram so the
> Elements UI recommendations panel can render them. This skill does **not** — its output is
> conversation-level only. Do not tell the user to look for these opportunities in the Elements
> recommendations panel; they will not appear there.

---

## Step 1 — build the rubric payload from the skinny map

The rubric expects exactly this shape (one entry per activity):

```json
{
  "processName": "string",
  "processDescription": "string",
  "activities": [
    {
      "id": "string",
      "text": "string",
      "inputFlowlines":  [{ "id": "string", "text": "string" }],
      "outputFlowlines": [{ "id": "string", "text": "string" }],
      "resources":       [{ "name": "string", "type": "string" }]
    }
  ]
}
```

The skinny JSON from `get_process_map` (org-to-process enrichment, `subtype: "upn"`) maps 1:1 onto it. Build
`inputFlowlines` / `outputFlowlines` yourself by matching `transitions` against each activity id:

| Rubric input | Skinny source |
|---|---|
| `processName` / `processDescription` | `metadata.name` / `metadata.description` |
| `activities[].id` / `.text` | `activities[].id` / `.text` |
| `activities[].resources` | `activities[].resources` → `{name, type}` (drop the `main` flag) |
| `activities[].inputFlowlines` | `transitions` where `toActivityId === activity.id` → `{id, text: label}` |
| `activities[].outputFlowlines` | `transitions` where `fromActivityId === activity.id` → `{id, text: label}` |

**Every activity is evaluated** — the production type does no activity filtering
(`categorizeAgentFinderActivities` returns `validActivities: activities`). Do not pre-drop lone or
structurally-incomplete activities.

`compatibleInputs` / `compatibleOutputs` are **excluded** for Agent Finder — do not build or use them (they
belong to the UPN quality rubric, not this one).

**Optional context (extension beyond the production rubric):** the skinny map also carries `lifecycleStates`
and `automations`. Production does not send these. You MAY use them as *supporting* context — e.g. to note
an activity is already fully covered by an existing Flow, or to relate an opportunity to a lifecycle state —
but they must not change the core suitability verdict, and if you lean on them, say so explicitly so the
result stays comparable to the production Agent Finder.

---

## Step 2 — the rubric (verbatim)

Role: You are an expert in AI-driven automation design for business processes.

Scope: Your job is to analyze a process diagram described via a JSON payload and assess each and every
activity for its suitability to be handled by one of the following: Conversational Agent (conversational,
autonomous, judgment-driven), AI Workflow (record-triggered flow that calls AI prompts or services, and then
performs database operations, no conversational interaction), Deterministic Automation (rule-based logic
implemented in Flow or Apex only without any AI).

Each diagram JSON contains the following: "text": what needs to be done, usually phrased as an active verb
sentence; "inputFlowlines": zero or more preconditions, both inputs and triggers for the activity. And
"outputFlowlines": zero or more business outcomes resulting from executing the activity.

Evaluate activities (pairing of inputFlowlines, activity text, and outputFlowlines) for the following
opportunities:

**Conversational Agent:** If the trigger for the activity is variable, situational, and unpredictable
(e.g. "Issue reported by user via chat", "Issue handed over from…", "Call finished" and similar), and if
inputs may require fuzzy, unstructured data (e.g. "emails", "transcripts", "messages", "documents", "plans",
"outlines", "notes", "calls", "recordings" etc.), and if activity text points to probabilistic reasoning,
pattern recognition, or interpretation (e.g. activity text contains verbs like "analyze", "predict",
"recommend", "classify", "detect", "investigate", "generate", "write", "document", "summarize", "outline",
"respond", "propose", "discover", and similar), and if the outcome is variable, contextual, and judgment
based (e.g. "Business proposal created" or "Email sent" or "Recommendation to help with the problems
offered", "Plan shared", "Monitoring", and similar), and if resource on the activity is not an AI Agent
already (e.g. 'AI Agent', 'Agent', 'AI' etc.), then suggest this activity should be handled by a
conversational agent. Only proceed if you are 80% certain about the recommendation.

**AI workflow:** If the trigger for the activity is precise, concrete, and discrete (e.g. "Opportuntity
closed won" or "Action invoked by the user"), and if inputs may require fuzzy, unstructured data (e.g.
"emails", "transcripts", "messages", "documents", "plans", "outlines", "notes", "calls", "recordings" etc.),
and if activity text points to probabilistic reasoning, pattern recognition, or interpretation (e.g.
activity text contains verbs like "analyze", "predict", "recommend", "classify", "detect", "investigate",
"generate", "write", "document", "summarize", "outline", "respond", "propose", "discover", and similar), and
if the outcome is precise, concrete, and discrete (e.g. "Record created" or "Lead status updated to…" or
"Record/field populated with…"), and if resource on the activity indicates it is done by a human today (e.g.
"Sales manager", "Marketing admin", "Sales rep", "Developer", "Line manager", etc.) then suggest this
activity should be handled by an AI workflow, utilizing record triggered automation like flow or apex
invoking prompt templates or agents. Only proceed if you are 80% certain about the recommendation.

**Deterministic automation:** If the trigger for the activity is precise, concrete, and discrete (e.g.
"Opportunity closed won" or "Record created"), and if inputs require precise, concrete, and structured data
(e.g. "opportunity value", "case priority", "start and end dates", "fields filled out", "number", "record
ID" and similar.), and if activity text points to rule-based, deterministic reasoning (e.g. activity text
contains verbs like "calculate", "update", "assign", "notify", "route", "validate" and similar), and if the
outcome is precise, concrete, and discrete (e.g. "Record created" or "Lead status updated to…" or
"Record/field populated with…"), and if resource on the activity is not already an automation (e.g. "Flow",
"Apex", "Automation", "Workflow"), then suggest this activity should be handled by a deterministic
automation, like flow or apex. Only proceed if you are 80% certain about the recommendation.

Your job is to read each activity, its inputFlowlines, its outputFlowlines, resources, and its text. Then use
the previously provided scope and rules to suggest where conversational agents, AI workflows, or
deterministic workflows could be applied. Only make recommendations if you are 80% confident. If no changes
are needed, do not propose anything for that activity.

---

## Step 3 — resources & reason (verbatim rules)

For each activity you recommend, attach the resources that identify the automation type:

- **Conversational Agent** → propose one resource `{"name": "AI Agent", "type": "System"}`.
- **AI workflow** → propose two resources `{"name": "Prompt template", "type": "System"}` and
  `{"name": "Flow", "type": "System"}`.
- **Deterministic automation** → propose one resource `{"name": "Flow", "type": "System"}`.

**reason:** The justification should be provided in the format of "Trigger for the activity is (e.g.
variable, situational, and unpredictable OR precise, concrete, and discrete). It requires (e.g. fuzzy,
unstructured data OR precise, concrete, and structured data), like… . The implied reasoning required to
perform the activity is … because… . And the outcome is (e.g. variable, contextual, and judgment based or
precise, concrete, and discrete). For this reason, there is [N]% confidence that this process activity can be
accelerated with (type of automation)."

---

## Step 4 — agent-type mapping & output contract

Map the proposed resources to a human-readable agent type:

| Proposed resources contain… | `agentType` |
|---|---|
| an "AI Agent" resource | **Conversational Agent** |
| a "Prompt template" **and** a "Flow" resource | **AI Workflow** |
| a "Flow" resource only | **Deterministic Automation** |
| no resources | **Deterministic Automation** |

(Match on resource name, case-insensitive; the "AI Agent" test wins if present.)

Return a **ranked** list — strongest opportunities first — of objects with exactly these fields:

```json
{
  "activityId":   "the activity id from the skinny map",
  "activityText": "the activity text",
  "agentType":    "Conversational Agent | AI Workflow | Deterministic Automation",
  "reason":       "the production reason format from Step 3, ending in the [N]% confidence sentence"
}
```

Rules:

- Include an activity **only if it clears the 80% confidence gate** for one of the three types. Below 80%,
  omit it — do not force a verdict.
- One verdict per activity (the strongest applicable type).
- The `reason` MUST follow the Step 3 format and end with the explicit `[N]% confidence` sentence naming the
  chosen automation type.
- If no activity clears the gate, say so plainly rather than inventing weak opportunities.

---

## Step 4b — deliver the assessment as a persistent report

Nothing from this rubric is persisted server-side, so once the user confirms the findings are useful, offer
to capture the assessment as a report they can keep and share — an HTML or Markdown file, or your client's
shareable page/artifact mechanism if it has one. Structure it as:

- **One section or tab per record-type diagram, first**, then end with an **Agent Recommendations**
  section/tab (the conclusion reads last; make it the one open by default when the medium supports it).
- **Agent Recommendations**: the ranked list, each entry carrying its **evidence quoted from
  the skinny map** — the trigger and outcome transition labels (cite the source diagram and transition id),
  the input signals, the current resources ("who does this today") — plus the production-format reason and
  confidence. Call out patterns that recur across record-type diagrams; independent recurrence strengthens a
  recommendation and usually means one agent covers several processes.
- Each **record-type section/tab**: a plain-language summary of how the process runs, derived
  from the skinny JSON (entry path, main loops, closure paths), its lifecycle states, the automation already
  in place (from `automations`), the key counts (activities / transitions / states), a link to the diagram
  (`diagramUrl`), and any `warnings` surfaced as data notes.
- Also include what was **assessed but not recommended** (below the 80% gate, or already automated) — the
  exclusions are part of the evidence.

## Step 5 — handoff to build

When the user picks an opportunity to build, carry the evidence forward: the activity text, the chosen
`agentType`, and the diagram it came from. Building the agent itself happens on the agent platform, outside
Elements. For a delivery backlog of stories per action, hand off to `elements-stories`.
