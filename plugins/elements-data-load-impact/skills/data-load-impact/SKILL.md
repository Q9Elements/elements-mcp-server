---
name: data-load-impact
description: Turns a planned Salesforce bulk data load into a ratified pre-load safety package, an optional full-copy-sandbox rehearsal, and an ordered backlog the customer's team executes. Use when a customer asks what a load will fire, how to prevent load incidents, how to choose load parameters, how to rehearse a backfill, or when resuming an in-progress data-load impact engagement. Do NOT use to execute a production load, modify Salesforce metadata, or assess a metadata-change project.
---

# Data-load impact

## What this delivers

This playbook predicts the transitive automation and locking effects of a specific load, records the
data-load owner's safety rulings, offers a recommended full-copy-sandbox rehearsal, and writes an
ordered execution backlog. Each incident class has a named control, an owner not-applicable ruling,
an accepted rehearsal result, or a stated risk when the owner skips rehearsal. When the owner chooses
rehearsal and the customer's
Salesforce command-line interface (sf CLI) is signed in to a verified rehearsal sandbox and can
match the ratified load parameters, the playbook sets temporary load-user logging, runs the small
test batch sliced from the local source after the customer confirms the sandbox checklist is applied
for the signed-in CLI user, and captures its results. On a chosen manual path, the customer runs
that batch. The customer's
team executes the backlog and production load; the playbook makes no Salesforce metadata change.

## How this playbook runs

1. Confirm that the Elements Model Context Protocol (MCP) server connects. Stop if it does not connect.
2. Use the session working directory as the **engagement directory**, where every persisted artifact
   goes. If `execution-state.json` exists there, resume from it; otherwise dispatch kickoff to create
   it and elicit card 00's owner name and source path once when unset. The engagement directory is the working directory for every
   card command. Invoke shipped scripts
   as `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py"`; shipped data lives under
   `${CLAUDE_PLUGIN_ROOT}/skills/data-load-impact/data/`. Put scratch files and redirected output
   under the engagement's `work/` directory.
3. Read `current_state`, open its card from the dispatch table, and do only what that card authorizes.
   Each card writes `current_state` and `current_step` together as one edit, then reports where the
   engagement stands. After TR-01, TR-05, TR-07, TR-11, TR-13, TR-15, or TR-19, dispatch the next card in
   the same turn. Stop only for an owner question, a self-loop, or a terminal state.
4. The orchestrator writes state and engagement files. Agents return evidence only.

## State dispatch

| `current_state` | Card |
|---|---|
| `kickoff` | `steps/00-kickoff.md` |
| `ready` | `steps/01-check-prerequisites.md` |
| `prerequisites-confirmed` | `steps/02-intake-manifest.md` |
| `manifest-confirmed` | `steps/03-analyze-impact.md` |
| `impact-analyzed` | `steps/04-audit-bypass.md` |
| `bypass-audited` | `steps/05-ratify-safety-package.md` |
| `package-ratified` | `steps/06-rehearse.md` |
| `rehearsal-closed` | `steps/07-deliver-backlog.md` |
| `blocked` | `steps/08-blocked-recovery.md` |
| `backlog-delivered` | terminal; report the backlog and final report, then stop |
| `no-go` | terminal; report the owner's no-go decision and final report, then stop |

A situation matching no other outcome on the current card takes that card’s default outcome, recorded in `decisions_log` and reported to the user.
A `current_state` matching no row stops with: "This state file does not match this playbook."

## State machine

| Transition | From | To | Condition |
|---|---|---|---|
| `TR-01` | `kickoff` | `ready` | The owner's name, source path, and privacy rule are recorded. |
| `TR-02` | `kickoff` | `kickoff` | Default: report the missing item. |
| `TR-03` | `ready` | `blocked` | A required primitive is unavailable. |
| `TR-04` | `prerequisites-confirmed` | `blocked` | The card 02 baseline call is refused with `model_not_synced` or fails with `model_resynced`. |
| `TR-05` | `ready` | `prerequisites-confirmed` | Every prerequisite passes. |
| `TR-06` | `ready` | `ready` | Default: report the exact failure. |
| `TR-07` | `prerequisites-confirmed` | `manifest-confirmed` | The data-load owner confirms the manifest and intake writes `work/intake/tool-targets.json` without failure. |
| `TR-08` | `prerequisites-confirmed` | `prerequisites-confirmed` | Default: report the error in aggregate terms. |
| `TR-09` | `manifest-confirmed` | `blocked` | Analysis reports an incomplete or restarted sync. |
| `TR-10` | `manifest-confirmed` | `prerequisites-confirmed` | Analysis rejects an object, field, or operation. |
| `TR-11` | `manifest-confirmed` | `impact-analyzed` | Every one-object analysis is complete. |
| `TR-12` | `manifest-confirmed` | `manifest-confirmed` | Default: keep no partial bundle. |
| `TR-13` | `impact-analyzed` | `bypass-audited` | Every predicted automation has a bypass verdict. |
| `TR-14` | `impact-analyzed` | `impact-analyzed` | Default self-loop. |
| `TR-15` | `bypass-audited` | `package-ratified` | The owner ratifies every control and declares go. |
| `TR-16` | `bypass-audited` | `prerequisites-confirmed` | The owner changes the manifest. |
| `TR-17` | `bypass-audited` | `no-go` | The owner declares no-go. |
| `TR-18` | `bypass-audited` | `bypass-audited` | Default: list what remains unruled; keep rulings and never infer go or no-go. |
| `TR-19` | `package-ratified` | `rehearsal-closed` | The owner skips the rehearsal after seeing the reasons to rehearse. |
| `TR-20` | `package-ratified` | `rehearsal-closed` | Complete evidence has zero control failures, this round's summary `unpredicted` is empty, no measured-class blocker, lock errors stay within the owner-accepted count, and the owner accepts the result including not-measurable lines. |
| `TR-21` | `package-ratified` | `package-ratified` | Rehearsal evidence is incomplete and must be recaptured. |
| `TR-22` | `package-ratified` | `bypass-audited` | A controlled automation fires, a measured class blocks, lock errors persist after serial mode ran or when the loader cannot run it, or the owner declines the rehearsal result. The owner may accept the measured lock count with unchanged lock parameters. |
| `TR-23` | `package-ratified` | `package-ratified` | The lock ladder changes parent grouping or concurrency; the customer reruns the small test batch. |
| `TR-24` | `package-ratified` | `impact-analyzed` | An automation outside both expectation sets is recorded for bypass audit and package rebuild. |
| `TR-25` | `package-ratified` | `package-ratified` | Default: keep evidence gaps open; never accept a result for the owner. |
| `TR-26` | `rehearsal-closed` | `backlog-delivered` | All required script-generated stories and `report/final-report.md` exist. |
| `TR-27` | `rehearsal-closed` | `rehearsal-closed` | Default: regenerate from package inputs; never hand-patch. |
| `TR-28` | `blocked` | `ready` | The recorded blocker is verified resolved. |
| `TR-29` | `blocked` | `blocked` | Default: restate unmet condition and owner; keep reason and owner. |

## Shipped surfaces

- `steps/` is authoritative for actions, stop rules, state writes, and transitions.
- `data/` is authoritative for decision vocabularies, thresholds, sequences, and controls.
- `references/` is authoritative for contracts, evidence acquisition, and method boundaries.
- `templates/execution-state.json` is authoritative for persisted engagement state.
- `../../agents/` contains the evidence specialists invoked by cards.
- `../../scripts/` contains deterministic local processors and their command-line contract.

## Human moments

- Card 00: the owner provides their name and the local source path.
- Card 01: the active Space and its Reference Models are resolved. One model is selected silently;
  the owner chooses by name when several models are available.
- Card 02: the owner confirms the proposed object, operation, counted rows, written fields, loader and Application Programming Interface (API),
  and any applicable upsert or portal-role facts in one reply. For update or upsert, the customer runs the
  generated Salesforce Object Query Language (SOQL) query and saves its result locally.
- Card 05: the owner accepts or changes proposed actions and replacement checks, answers one combined
  incident-class question, then gives go or no-go with any stated risks.
- Card 06: the owner chooses whether to rehearse and accepts the evidence.

Each human decision records the person's name, decision, and date and time in `decisions_log` and in
the matching state block. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/now.py"` at each recorded
event and copy its host-clock Coordinated Universal Time (UTC) output. Copy timestamps supplied
by tools directly. The data-load owner is the sole human decider.

## Session contract

- Speak in customer language and define each acronym on first use.
- Speak to the owner only about their load. Record tool, connector, script, agent, brief, and review faults as internal notes in `decisions_log`. Reports, stories, and owner messages state only the load effect in plain words, without reviewer tags.
- Raw comma-separated value (CSV) rows, Salesforce Object Query Language (SOQL) results, and debug
  logs never enter model context. Only local script outputs with metadata names, aggregates, and
  counts may cross that boundary.
- Copy identifiers from tool responses programmatically; never retype them.
- Keep Elements internal identifiers in state and work files; use names in owner messages,
  reports, and stories.
- When `slots.space_id` is known, pass it as `teamId` with `refModelId` on every Elements
  model or metadata call.
- Follow each tool's paging and batching contract. Each `run_data_load_impact` call contains exactly
  one target.
- Write no MetaField or Elements content. Card 06 may create and remove only its own temporary
  sandbox trace flag and debug level and run the ratified small test load on a verified sandbox.
  The customer's team applies checklist metadata changes and runs the production load.
- On a terminal-state invocation, report the existing deliverables and stop without regenerating them.
