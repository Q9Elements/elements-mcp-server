---
name: explain-quote-line-pricing
description: "Explains how one Salesforce quote line's price was calculated, and answers follow-up questions including price rule change history, from Quote Line Microscope logs read through the Salesforce command-line interface (CLI) or Salesforce Hosted Model Context Protocol (MCP) and from Elements metadata history; saves progress in execution-state.json. Use when a user asks 'why is this quote line priced this way', 'which price rules affected this line', or to resume an in-progress quote line pricing explanation. Do NOT use for changing prices or explaining an entire quote."
---

# Explain quote line pricing

## What this delivers

Provide a plain-language answer grounded in evidence for a question about one Salesforce CPQ quote line, and answer follow-up questions. The analysis is read-only and covers calculator price rules captured by Quote Line Microscope (QLM).

## How this playbook runs

1. Resolve the core `elements` Model Context Protocol (MCP) tools `get_space_context`, `list_reference_models`, `search_metadata`, and `get_component_change_history`. Stop before starting if they do not resolve. Make no authenticated Elements call until card 01's `next` prints it; the first printed call is `get_space_context`. Use the servers specified in card 01 step 4.
2. Locate `execution-state.json` in the current working directory or the engagement directory the user supplies. For a new request with no state file, use the supplied engagement directory or default to the current working directory, copy `templates/execution-state.json` into it, and tell the user where progress is saved. For a resume request with no state file there, ask for the engagement directory. The state file's directory is the engagement directory; put every persisted artifact there. At kickoff, card 01 fills the route (`cli` or `hosted-mcp`), org alias for the command-line interface (CLI) route, quote line identifier or name, and question from the message, then asks for missing inputs together through TR-01. The quote line identifier resolved from evidence is populated by the playbook. Keep slots in the state file, never in the plugin.
3. Read `current_state`, open its card from the dispatch table, and do what the card says. Each card writes `current_state` and `current_step` together as one edit, then reports where the engagement stands.
4. After a transition, continue to the next card in the same turn unless it is a self-loop, waits for the user's answer, or is terminal. The orchestrator writes state; agents return evidence. Shipped commands assemble factual deliverables from state and evidence files, with judgement supplied as structured input. The compose script owns every factual list in an answer; agents explain those facts within their own topic. Copy every identifier and query response from tool output unchanged; a retyped value can corrupt the explanation.

All paths below resolve from this skill directory; agents and scripts reside in the plugin's `agents/` and `scripts/` directories, two levels up.

## State dispatch

| current_state | card |
|---|---|
| `kickoff` | `steps/01-build-diagnostics.md` |
| `diagnostics-built` | `steps/02-answer-questions.md` |
| `blocked` | `steps/03-blocked-recovery.md` |
| `engagement-closed` | terminal; report the distinct quote lines with saved-answer entries in `decisions_log` and stop |

The initial state is `kickoff` and the initial card is `steps/01-build-diagnostics.md`. When a situation matches no named condition on the current card, take its default outcome, record the call and evidence in `decisions_log`, and tell the user. If `current_state` matches no row, stop and say "this state file does not match this playbook".

## Shipped surfaces

- `steps/` holds the procedure and transitions for each state.
- `templates/execution-state.json` defines the engagement state and slots.
- `data/` holds the access, routing, report, warning, and recovery definitions read by the cards and scripts.
- `references/guides/` holds the agents' evidence guides.
- `agents/` holds the agents' interpretation contracts; `scripts/` gathers and assembles evidence and answers.

## Human moments

- Card 01: the user provides the route, applicable org alias, quote line, and question together at kickoff.
- Card 03: the user creates the QLM diagram when its log is missing; the administrator resolves an access, package, route, or query blocker as appropriate. Wait for the user to report recovery before rechecking.

## Session contract

Use customer-language prose. Record each human decision and orchestrator default in `decisions_log` with who decided, what was decided, the evidence, and the date. Follow each card's batching and pagination instructions, including limits and incomplete-result handling. The playbook reads Salesforce and Elements data and writes engagement files, not org data. On re-invocation of a closed engagement, report the distinct quote lines with saved-answer entries in `decisions_log` and stop; start a new engagement directory for a new question.
