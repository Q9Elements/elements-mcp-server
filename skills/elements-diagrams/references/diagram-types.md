# Elements Diagram Types

Use this reference when the user wants to create a new diagram and hasn't specified a type, or when you need to identify what kind of diagram you're working with.

---

## How to Recommend a Type

Read the user's input (description, transcript, goal) and match it to the most appropriate subtype below. State your recommendation and why, then ask for confirmation before proceeding.

If the user is editing or reading an existing diagram, the `subtype` field in the level file tells you the type; do not change it.

---

## UPN Family (`type: "upn"`)

These diagrams model processes, journeys, and instructions using Universal Process Notation (UPN): activities in boxes, connected by flowlines, organised in swimlanes by role.

| Subtype | When to use |
|---------|-------------|
| `upn` | A business process with roles, steps, and decision points. Default choice for "how does X work" or "map this process". |
| `customerJourney` | The experience of a customer moving through touchpoints: awareness, engagement, purchase, support. Focus is on the customer perspective, not internal operations. |
| `agentInstruction` | Step-by-step instructions for an AI agent: what to do, in what order, under what conditions. Choose when the subject is an AI agent workflow or automation instruction set. |
| `whiteboard` | Freeform, no fixed structure. Use for brainstorming, loose idea capture, or diagrams that don't fit a formal notation. |

**Drilldown rules for UPN family:**
- `upn` can drill into: `upn`, `customerJourney`, `interactionFlow`, `agentInstruction`
- `customerJourney` can drill into: `customerJourney`, `upn`, `interactionFlow`, `agentInstruction`
- `agentInstruction` can drill into: `agentInstruction`, `interactionFlow`

---

## Architecture Family (`type: "architecture"`)

These diagrams model systems, capabilities, data, and technical interactions. They do not use UPN notation.

| Subtype | When to use |
|---------|-------------|
| `systemArchitecture` | High-level view of systems, platforms, and their relationships. Use for "what systems are involved" or infrastructure/solution architecture. |
| `capability` | A business capability map: what the organisation *can do*, independent of how. Use for capability modelling, gap analysis, or strategic planning. |
| `dataModel` | Entities, attributes, and relationships. Use when the subject is data structure, schema design, or ERD-style modelling. |
| `interactionFlow` | How components, systems, or services interact at a technical level: API calls, events, messages. More detailed than system architecture. |
| `agentInteraction` | Interactions between AI agents and the systems or humans they communicate with. Choose when the diagram shows multi-agent orchestration or agent-to-system messaging. |

**Drilldown rules for architecture family:**
- `systemArchitecture` can drill into: `systemArchitecture`, `interactionFlow`, `dataModel`
- `capability` can drill into: `capability`, `systemArchitecture`, `dataModel`, `interactionFlow`, `upn`, `customerJourney`
- `dataModel` can drill into: `dataModel`, `interactionFlow`, `systemArchitecture`
- `interactionFlow` can drill into: `interactionFlow`, `dataModel`
- `agentInteraction` can drill into: `agentInstruction`, `agentInteraction`

---

## Generation Constraints

`generate_process_map` currently only generates `upn` subtype diagrams. All other subtypes must be created manually via export/edit/import or through the Elements UI.
