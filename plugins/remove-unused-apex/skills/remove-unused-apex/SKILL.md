---
name: remove-unused-apex
description: Finds Apex candidates that may reclaim capacity and produces a customer-reviewed removal plan. It selects dependency-complete packages, records customer rulings, and creates removal and annotation stories. Use when a customer is near the Apex character limit, asks which Apex is unused or dead, or wants to reclaim Apex capacity. Do not use for direct org changes; the customer performs every change.
---

# Remove unused Apex

The customer says: *remove unused Apex from this org.* This playbook obtains what the org's execution
telemetry and dependency graph can show and answers: *these classes are unused as far as the evidence
goes: ranked by confidence, each with the reason for any doubt, worth this many characters of the
allocation, with consumers listed before providers for story reading order.* Each tranche deploys as one
deployment. The customer reviews the
list and then executes the removals. Elements executes nothing in the org.

The input is one org, synced to Elements, with Apex execution telemetry, which is a hard prerequisite.
`ApexExecution` must appear in the complete bundle ledger with `daysProcessed` above zero.
`ApexTrigger` must appear with `daysProcessed` above zero when `work/bundle/catalog.csv` contains at
least one row with `kind=trigger` and `isManagedPackage=false`. Missing required telemetry disqualifies
the org.
At kickoff, the customer pastes the Setup capacity banner, states the Apex capacity target, and, only when the
bundle-host probe fails, asks information technology (IT) to allow the named host. Three stages, three owners:
**Elements computes** the candidate bundle (`get_unused_apex_candidates`), **a shipped script selects**
dependency-complete packages (`capacity_triage.py`), **agents reason** over selected rows, and **a shipped
script plans** the confirmed removal. The large language model (LLM) receives bounded summaries and selected
evidence, never the estate or the complete candidate inventory. `references/method-notes.md` carries the design rules; `data/*.csv` every value;
`references/data-contracts.md` every exchanged file. Read `references/orchestration.md` for agent,
evidence, and session rules.

## How this playbook runs

This file, the current card, and the execution state define the orchestration.
Every relative path in this package resolves against this file's own directory (`steps/`, `data/`,
`references/`, `templates/` are its siblings); the agents live in the plugin's `agents/` directory two
levels up, and the scripts in the plugin's `scripts/` directory two levels up.

1. **New or resume.** Look for `execution-state.json` by asking where the engagement lives or checking
   the working directory. The directory holding it is **the engagement directory**: every persisted
   artifact goes there, in the layout `references/data-contracts.md` gives. A state file means a
   resumed engagement: read `current_state` and dispatch its card. No state file means a new
   engagement: dispatch `steps/00-kickoff.md` before any tool call. Card 00 establishes the engagement
   directory and state file. Slots are never written back into this package.
2. **Dispatch one card.** Open card 00 for a new engagement or the card matching `current_state` for a
   resumed engagement, then do what it says. Once `execution-state.json` exists (card 00 creates it in
   its step 2; every later dispatch finds it), project the six mainline cards (00 to 05) of the state
   dispatch table as an ordered progress list with the current card marked, through whatever progress,
   task or plan affordance the host provides. `blocked` is a status on the current item, not
   a step; with no affordance, print the list once. The list projects `execution-state.json` and is
   never a second source of truth. Each card ends by writing `current_state` and `current_step`
   together, as one edit, updating the projected list in the same turn if the host has one, then
   telling the user where the engagement stands in plain business terms. Dispatch the next card unless the card says to stop. Card 00 stops after printing
   the kickoff block and writing `ready`.
   Card 01 stops only when a required input is missing, bundle-host reachability fails, or an outcome
   blocks; on TR-04 it dispatches card 02 in the same turn. Card 02 dispatches its written next card in
   the same turn, including the blocked card for TR-05, TR-06, TR-15, TR-19, or TR-20.
   Card 03 stops for the reviewer hand-off; when its string check leaves no selected package, it
   closes the engagement (TR-22) or dispatches card 05 for earlier standing `remove` or `annotate`
   rulings (TR-23). Card 04 stops for the review gate. Card 05 either completes the engagement or,
   when the customer requests another selection round and regenerated triage selects a package,
   dispatches card 03 (TR-17). A round that selects nothing completes the engagement (TR-24).
3. **Evidence surfaces.** A card obtains evidence and produces deliverables through the Elements Model
   Context Protocol (MCP) tools, files in the engagement directory, conversation with the user, and,
   for the review pack on card 04 only, a published-artifact surface when the host has one; when it
   does not, the pack file is the review artifact. These are the only evidence surfaces. Presentation
   affordances the host provides (a progress list, a task panel, a plan view) carry no evidence and may
   be used to project the state defined in this file.
4. **The orchestrator writes state; agents return evidence; the planner script writes its plan.** No agent
   writes `execution-state.json`, `work/review/dispositions.csv`, or anything in the org. The
   `candidate-reasoner` returns JavaScript Object Notation (JSON) and writes nothing. The
   `removal-plan-generator` runs and checks the deterministic script but writes nothing. The script
   writes under `work/plan/`, `stories/`, and `report/`.

## State dispatch

| current_state | card |
|---|---|
| `kickoff` | `steps/00-kickoff.md` |
| `ready` | `steps/01-check-prerequisites.md` |
| `prerequisites-confirmed` | `steps/02-obtain-candidates.md` |
| `candidates-obtained` | `steps/03-reason-candidates.md` |
| `candidates-reasoned` | `steps/04-review-list.md` |
| `list-reviewed` | `steps/05-plan-removal.md` |
| `blocked` | `steps/06-blocked-recovery.md` |
| `removal-planned` | terminal; report the deliverables listed in card 05 (or the final report written when card 02, 03, or 04 closed the engagement) and stop |

The initial state is `kickoff` and the initial card is `steps/00-kickoff.md`.

Every transition is defined on the card that owns the from-state, as an explicit outcome with its
condition and its state write. If a situation matches no outcome on the current card, do not invent a
transition: record what happened in `open_items`, tell the user, and stay on the current state. If
`current_state` matches no dispatch row, stop and tell the user the state file does not match this
playbook; never guess a card.

## Capacity loop transition

| Transition | From | Condition | To | Preserved input |
|---|---|---|---|---|
| TR-17 | `list-reviewed` | The target is short, the customer requests another selection round, and regenerated triage selects a package | `candidates-obtained` | Prior dispositions |
| TR-24 | `list-reviewed` | The customer requests another selection round and regenerated triage selects no package | `removal-planned` | The delivered plan |
| TR-23 | `candidates-obtained` | A later round's string check leaves no selected package and earlier `remove` or `annotate` rulings stand | `list-reviewed` | Prior dispositions |

Card 05 regenerates `work/triage/` before choosing TR-17 or TR-24, excluding candidates already
ruled `keep`, `remove`, or `annotate`.
