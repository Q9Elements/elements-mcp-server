---
name: design-from-process-map
description: "Derives the solution design a business process map in Elements implies (process-led design), for a target system the solution architect chooses: a data model diagram and a system architecture diagram in Elements, a data access (CRUD) matrix as a CSV, and a solution overview document in Word, all traced back to the map. Use for \"what does this process need from Salesforce?\", deriving a data model, integrations or access matrix from a process map, or resuming a design. Not for drawing, fixing or improving the process map itself."
---

# Process-led design

Follow [result acquisition](../../references/result-acquisition.md) for complete reads, native jobs, failure evidence and write outcomes.

## What this delivers

From a business process map in Elements, a solution design for a target system the solution architect chooses (a Salesforce cloud with or without a connected org, or another vendor's system): a data model diagram and a system architecture diagram as drafts in Elements, a data access matrix as a CSV, and a solution overview document in Word that pictures and links them: for each process area, its part of the source map, the data it uses and the integrations that serve it, each pictured and summed up. The document sums up the access matrix and points to its file rather than listing it. Every deliverable links back to the source map. Nothing in Salesforce or in the source map changes. Capability maps, UI and experience design, and improving the process map itself are outside it.

## How this playbook runs

Paths: this file's folder is `$SKILL`; the plugin folder (`$PLUGIN`) is two levels up. Resolve both to absolute paths and pass `$PLUGIN` to every agent as `pluginRoot`.

1. **Probe the tooling first.** Run `python3 "$SKILL/scripts/common.py" probe`; it ends `READY` or `NOT READY`. On `NOT READY`, stop and say what to install, as its `MISSING` and `NEEDS` lines name it. Without LibreOffice and Pillow the document links to the diagrams without pictures. Say so and go on. Card 01's first call checks the Elements tools answer.
2. **New or resume.** Find `execution-state.json`: in the folder the solution architect names, else in a `*-design-from-process-map/` folder in the working directory. Look nowhere else: not in this plugin's own folder, not across the rest of the disk. On a resume with none there, say so plainly and ask where the folder is, or offer a new run. When several exist and the request does not say which, ask which one, listing each folder's map and state. Its folder is the **engagement directory** (`$ENG`); everything the run saves goes there. For a new design, start at card 01, which creates `$ENG` once the map is known.
3. **Dispatch one card.** Read `current_state`, open the card the table below names, and do what it says. Each card ends by writing `current_state` and `current_step` together, in one edit, and telling the solution architect where the engagement stands.
4. **The orchestrator writes state; agents return evidence.** Agents write only the one evidence file their brief names and run its check; they never write `execution-state.json`, anything in Elements or anything in Salesforce.

## State dispatch table

| `current_state` | Card |
|---|---|
| `not-started` | [steps/01-scope-the-run.md](steps/01-scope-the-run.md) |
| `scoped` | [steps/02-read-and-check-the-map.md](steps/02-read-and-check-the-map.md) |
| `check-failed` | [steps/03-decide-on-a-failed-check.md](steps/03-decide-on-a-failed-check.md) |
| `map-checked` | [steps/04-gather-target-evidence.md](steps/04-gather-target-evidence.md) |
| `evidence-gathered` | [steps/05-derive-data-model-and-integrations.md](steps/05-derive-data-model-and-integrations.md) |
| `structure-derived` | [steps/06-derive-the-access-matrix.md](steps/06-derive-the-access-matrix.md) |
| `design-derived` | [steps/07-review-the-design.md](steps/07-review-the-design.md) |
| `design-approved` | [steps/08-draw-the-diagrams.md](steps/08-draw-the-diagrams.md) |
| `diagrams-drawn` | [steps/09-assemble-the-solution-overview.md](steps/09-assemble-the-solution-overview.md) |
| `delivered` | terminal; report the deliverables and stop |
| `blocked` | [steps/10-blocked-recovery.md](steps/10-blocked-recovery.md) |

A situation that matches no other outcome on the current card takes that card's default outcome (its last bullet), recorded in `decisions_log` and told to the solution architect. A `current_state` that matches no row stops with "this state file does not match this playbook".

## Shipped surfaces

- `steps/`: the cards, the only authority for what each state does and where it goes next.
- `data/`: the decision definitions, each held once: [`derivability-rubric.csv`](data/derivability-rubric.csv) (the checks a level is scored on and the pass mark), [`crud-verbs.csv`](data/crud-verbs.csv) (verbs to create, read, update, delete), [`integration-evidence-types.csv`](data/integration-evidence-types.csv) (the org metadata that shows an existing integration), [`solution-overview-sections.csv`](data/solution-overview-sections.csv) (the document's sections and where each one's content comes from).
- `schemas/`: the files the agents write: [wording findings](schemas/wording.schema.json), the [data model](schemas/data-model-section.schema.json) and [integration](schemas/integrations-section.schema.json) sections, the [access matrix](schemas/access.schema.json), the [document's prose](schemas/prose.schema.json).
- `references/`: the derivation method each agent follows ([`find-entities.md`](references/find-entities.md), [`find-integrations.md`](references/find-integrations.md), [`find-access.md`](references/find-access.md)) and the engagement directory's file list ([`engagement-files.md`](references/engagement-files.md)).
- `scripts/`: the run's checks and builders; each card names the command it runs. `lint.py` checks the package itself.
- `templates/`: [`execution-state.json`](templates/execution-state.json) and the document template [`solution-overview.docx`](templates/solution-overview.docx).
- `assets/`: the Elements.cloud logo for the document's first page, `elements-logo.png` ([`assets/README.md`](assets/README.md)).
- Plugin root: the shared model and `validate.py`, the `draw-data-model` and `draw-system-architecture` skills, and the `system-doc-reader`, `diagram-reviewer`, `process-quality-assessor`, `data-model-deriver`, `integration-deriver`, `access-deriver` and `solution-overview-writer` agents.

## Human moments

The one decision role is **the solution architect**: the person running the playbook.

| Moment | Card |
|---|---|
| Kickoff: the source map, the target system, the source of reference, and optionally the customer's name and logo | 01 |
| A level fails the derivability check: continue at lower confidence, fix the map and resume, or stop | 03 |
| The checkpoint: approve the derived design, or correct it | 07 |
| Final answer: the deliverables at `delivered` | terminal |

## Session contract

- Speak the solution architect's language: entities, systems, integrations, access, not file or field names; they approve the design, not the files that hold it.
- Record every decision in `decisions_log` as `{"who", "what", "evidence", "date"}`: the solution architect's choices and the orchestrator's default calls alike. The solution overview's decisions section is built from it, so an unrecorded call is missing from the document. Calls the derivation made (standard, custom or proposed; existing or proposed; pattern; permission controller) are shown at the checkpoint.
- Elements list tools answer with NDJSON part files: call again with identical arguments while `status` is `running`, download every part within its expiry, and follow `nextPartsFrom` until every part is saved. A missing part is never read as an empty list.
- When more than one Elements server is connected, use the one for the environment the solution architect named, and ask when they named none; the space, map and reference model ids belong to that server, so keep it for the whole run.
- Pass `teamId` (`slots.space_id`) on every Elements call; a token authorized for several spaces needs it to reach the right one.
- Copy ids (map, level, reference model, node ids) from tool answers and files; a retyped id reads or links the wrong record.
- At `delivered`, a new request on this engagement repeats the final report (card 09 says what it holds, from the run's files); a new design starts a new engagement directory at card 01.
