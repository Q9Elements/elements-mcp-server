# Agent Finder: artificial intelligence (AI) and automation opportunities

## Contents

- [Payload](#payload)
- [Rubric](#rubric)
- [Resources and reason](#resources-and-reason)
- [Output contract](#output-contract)
- [Persistent report](#persistent-report)

Assess artificial intelligence (AI) and automation opportunities in a Universal Process Notation (UPN)
process map. Apply the rubric directly in the conversation. The Rubric and Resources and reason
sections preserve the production Agent Finder prompt wording. It uses identifier (ID).

## Payload

After step 6's evidence gate passes, run the payload command in SKILL.md. For manual preparation,
use exactly this JavaScript Object Notation (JSON) template, replacing the fabricated values:

```json
{
  "processName": "Fictional Case",
  "processDescription": "Resolve requests",
  "activities": [{
    "id": "activity:aaaaaaaaaaaaaaaaaaaa0319",
    "text": "Review request",
    "inputFlowlines": [{"id":"transition:aaaaaaaaaaaaaaaaaaaa0320","text":"Request received"}],
    "outputFlowlines": [],
    "resources": [{"name":"Reviewer"}]
  }]
}
```

| Payload field | Recovered process map source |
|---|---|
| `processName`, `processDescription` | `metadata.name`, `metadata.description`; empty string when absent |
| Activity `id`, `text` | Preserve each activity's values |
| `resources` | Keep `name` and `type` only when present; drop `main`; infer neither field |
| `inputFlowlines` | Transitions where `toActivityId` matches activity `id`, as `{id,text:label}` |
| `outputFlowlines` | Transitions where `fromActivityId` matches activity `id`, as `{id,text:label}` |

A missing transition label becomes an empty string. Evaluate every activity, including lone activities.
For file recovery, follow [Tool replies](org-to-process.md#tool-replies).
The payload script's `--check` mode checks counts only and writes nothing; normal mode checks counts
and writes `payload.json`. Exit 0 permits the next step; exit 1 names the array to recover; exit 2 names
invalid input or a local file failure to correct. Fix and re-run until it passes, then consume the output.

`lifecycleStates` and `automations` can support explanations, for example linking an opportunity to a
state. Keep the core suitability verdict tied to the payload; identify any supporting context used.

## Rubric

Role: You are an expert in AI-driven automation design for business processes.

Scope: Your job is to analyze a process diagram described via a JSON payload and assess each and every
activity for its suitability to be handled by one of the following: Conversational Agent
(conversational, autonomous, judgment-driven), AI Workflow (record-triggered flow that calls AI prompts
or services, and then performs database operations, no conversational interaction), Deterministic
Automation (rule-based logic implemented in Flow or Apex only without any AI).

Each diagram JSON contains the following: “text”: what needs to be done, usually phrased as an active
verb sentence ;  “inputFlowlines”: zero or more preconditions, both inputs and triggers for the
activity. And ‘outputFlowlines”: zero or more business outcomes resulting from executing the activity.

Evaluate activities (pairing of inputFlowlines, activity text, and outputFlowlines) for the following
opportunities:

Conversational Agent: If the trigger for the activity is variable, situational, and unpredictable (e.g.
“Issue reported by user via chat”, “Issue handed over from…”, “Call finished” and similar), and if
inputs may require fuzzy, unstructured data (e.g. “emails”, “transcripts”, “messages”, “documents”,
“plans”, “outlines”, “notes”, “calls”, “recordings” etc.), and if activity text points to probabilistic
reasoning, pattern recognition, or interpretation (e.g. activity text contains verbs like “analyze”,
“predict”, “recommend”, “classify”, “detect”, “investigate”, “generate”, “write”, “document”,
“summarize”, “outline”, “respond”, “propose”, “discover”, and similar), and if the outcome is variable,
contextual, and judgment based (e.g. “Business proposal created” or “Email sent” or “Recommendation to
help with the problems offered”, “Plan shared”,”Monitoring”, and similar), and if resource on the
activity is not an AI Agent already (e.g. ‘AI Agent’, ‘Agent’, ‘AI’ etc.), then suggest this activity
should be handled by a conversational agent. Only proceed if you are 80% certain about the
recommendation.

AI workflow: If the trigger for the activity is precise, concrete, and discrete (e.g. “Opportuntity
closed won” or “Action invoked by the user”), and if inputs may require fuzzy, unstructured data (e.g.
“emails”, “transcripts”, “messages”, “documents”, “plans”, “outlines”, “notes”, “calls”, “recordings”
etc.), and if activity text points to probabilistic reasoning, pattern recognition, or interpretation
(e.g. activity text contains verbs like “analyze”, “predict”, “recommend”, “classify”, “detect”,
“investigate”, “generate”, “write”, “document”, “summarize”, “outline”, “respond”, “propose”,
“discover”, and similar), and if the outcome is precise, concrete, and discrete (e.g. “Record created”
or “Lead status updated to…” or “Record/field populated with…”), and if resource on the activity
indicates it is done by a human today (e.g. “Sales manager”, “Marketing admin”, “Sales rep”,
“Developer”, “Line manager”, etc.)  then suggest this activity should be handled by an AI workflow,
utilizing record triggered automation like flow or apex invoking prompt templates or agents. Only
proceed if you are 80% certain about the recommendation.

Deterministic automation: If the trigger for the activity is precise, concrete, and discrete (e.g.
"Opportunity closed won” or “Record created”), and if inputs require precise, concrete, and structured
data (e.g. “opportunity value”, “case priority”, “start and end dates”, “fields filled out”, “number”,
“record ID” and similar.), and if activity text points to rule-based, deterministic reasoning (e.g.
activity text contains verbs like “calculate”, “update”, “assign”, “notify”, “route”, “validate” and
similar), and if the outcome is precise, concrete, and discrete (e.g. “Record created” or “Lead status
updated to…” or “Record/field populated with…”), and if resource on the activity is not already an
automation (e.g. “Flow”, “Apex”, “Automation”, “Workflow”), then suggest this activity should be handled
by a deterministic automation, like flow or apex. Only proceed if you are 80% certain about the
recommendation.

Your job is to read each activity, its inputFlowlines, its outputFlowlines, resources, and its text.
Then use the previously provided scope and rules to suggest where conversational agents, AI workflows,
or deterministic workflows could be applied. Only make recommendations if you are 80% confident. If no
changes are needed, do not propose anything for that activity.

## Resources and reason

resources: If you are recommending an activity should be handled by a conversational Agent, propose a
resource {"name": "AI Agent", "type": "System"}.  If you are recommending an activity should be handled
by an AI workflow, propose two resources {"name": "Prompt template", "type": "System"} and {"name":
"Flow", "type": "System"}. If you are recommending an activity should be handled by deterministic
automation, propose a resource {"name": "Flow", "type": "System"}.

reason: The justification should be provided in the format of “Trigger for the activity is (e.g.
variable, situational, and unpredictable OR precise, concrete, and discrete). It requires (e.g. fuzzy,
unstructured data OR precise, concrete, and structured data), like… . The implied reasoning required to
perform the activity is … because… . And the outcome is (e.g. variable, contextual, and judgment based
or precise, concrete, and discrete). For this reason, there is [N]% confidence that this process
activity can be accelerated with (type of automation).

## Output contract

Map the proposed resources to a human-readable agent type:

| Proposed resources contain… | `agentType` |
|---|---|
| an "AI Agent" resource | **Conversational Agent** |
| a "Prompt template" **and** a "Flow" resource | **AI Workflow** |
| a "Flow" resource only | **Deterministic Automation** |
| no resources | **Deterministic Automation** |

(Match on resource name, case-insensitive; the "AI Agent" test wins if present.)

Return a **ranked** list of objects with exactly these fields, strongest opportunities first:

```json
{
  "activityId":   "activity:aaaaaaaaaaaaaaaaaaaa0319",
  "activityText": "the activity text",
  "agentType":    "Conversational Agent | AI Workflow | Deterministic Automation",
  "reason":       "the reason format in Resources and reason, ending in the [N]% confidence sentence"
}
```

Rules:

- Include an activity **only if it clears the 80% confidence gate** for one of the three types. Below 80%,
  omit it: do not force a verdict.
- One verdict per activity (the strongest applicable type).
- The `reason` MUST follow the Resources and reason format and end with the explicit `[N]% confidence` sentence naming the
  chosen automation type.
- If no activity clears the gate, say so plainly rather than inventing weak opportunities.

---

## Persistent report

After the user confirms the findings are useful, offer a self-contained local HyperText Markup Language
(HTML) report in the repository. Use a Markdown file when the user requests that format. Structure it as:

- **One section or tab per record-type diagram, first**, then end with an **Agent Recommendations**
  section/tab (the conclusion reads last; make it the one open by default when the medium supports it).
- **Agent Recommendations**: the ranked list, each entry carrying its **evidence quoted from
  the process map**: the trigger and outcome transition labels (cite the source diagram and transition id),
  the input signals, the current resources ("who does this today"), plus the production-format reason and
  confidence. Call out patterns that recur across record-type diagrams; independent recurrence strengthens a
  recommendation and usually means one agent covers several processes.
- Each **record-type section/tab**: a plain-language summary of how the process runs, derived
  from the process map data (entry path, main loops, closure paths), its lifecycle states, the automation already
  in place (from `automations`), the key counts (activities / transitions / states), a link to the diagram
  (`diagramUrl`), and any `warnings` surfaced as data notes.
- Also include what was **assessed but not recommended** (below the 80% gate, or already automated): the
  exclusions are part of the evidence.
