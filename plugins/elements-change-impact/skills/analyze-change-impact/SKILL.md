---
name: analyze-change-impact
description: "Produce an impact report and draft delivery backlog for a proposed Salesforce automation or schema change. Use when a runner asks to assess, compare approaches for, or resume an in-progress change-impact assessment. Do NOT use to implement the change, remove an unnamed Apex class, or uninstall a managed package."
---

# Analyze Change Impact

## What this delivers

An engagement produces `impact-report.html`, `backlog.md` and `backlog.json`, plus `impact-report.json` as the report record. The assessment describes a proposed change; the customer implements it. A blocking finding leads the full report and holds the backlog as "not drafted" with its text until the runner changes the request, re-picks, or says to plan it anyway; that reply re-traces the confirmed change and the draft carries every blocking finding as a flag with the reply verbatim on the change story.

## How this playbook runs

1. Probe the required Elements Model Context Protocol (MCP) tools and authentication before starting. If a required tool is unavailable, stop before creating an engagement, except for `explain_metadata_components`; card 01 handles its absence as an automation-summary prerequisite stop.
2. Locate the engagement's `execution-state.json`. Its directory holds all run files. For a new engagement, create the directory, copy `templates/execution-state.json` and put the runner's sentence in `change_request.sentence`.
3. Read `current_state`, open its card in the dispatch table and follow it. The orchestrator alone writes the state file. Write `current_state` and `current_step` together at each transition and report where the engagement stands.

## State dispatch

| `current_state` | Card |
|---|---|
| `change-requested` | `steps/01-understand-change.md` |
| `delete-loss-open` | `steps/02-choose-approach.md` |
| `approach-open` | `steps/02-choose-approach.md` |
| `change-set-fixed` | `steps/03-trace-impact.md` |
| `impact-traced` | `steps/04-deliver.md` |
| `blocked` | `steps/05-recover.md` |
| `delivered` | Terminal: report the deliverables and stop. |

The card's final outcome applies when no earlier condition holds. Record the reason in `decisions_log` and tell the runner. An unrecognized state stops with "this state file does not match this playbook". On a later reply after delivery, write `{"current_state":"change-requested","current_step":"steps/01-understand-change.md"}` together and dispatch card 01. A reply to card 02's pending pick or `delete-loss-open` question stays on card 02.

## Shipped surfaces

- `steps/` owns procedures, runner stops and transitions.
- `data/` owns relation dispositions, order-of-execution rules and blocked causes.
- `references/method-notes.md` owns stated limits.
- `templates/` owns engagement state and report record shapes.
- `../../scripts/` owns bulk evidence processing, assertions, backlog files and rendering, including `existing_jobs.py` for existing-automation fit and delete-loss checks. Scripts keep bundle rows out of the main context; there are no evidence agents.
- Most JavaScript Object Notation (JSON) card scripts take `--in <json> --out <json>`. `existing_jobs.py` uses `shortlist` and `check` with named file arguments: `--change-set`, `--dependents` and `--out`; `shortlist` also accepts `--objects` and held `--definitions`, and `check` takes `--shortlist`, `--summaries` and `--judgements`. Command forms and input fields are listed in `../../scripts/README.md`.

## Human moments

- Card 01 confirms the runner's understanding and resolves applicable ambiguity in one message.
- Card 02 asks one delete-loss question for lost jobs and uncovered parts of partial jobs. The pending answer stays in `delete-loss-open`; re-entry uses saved evidence. A plain delete with nothing to ask or a `delete_anyway` answer advances to tracing. A `move` answer feeds the uncovered jobs into the normal option pick.
- Card 02 presents option evidence and asks the runner to pick when an approach needs choosing.

Generated automation summaries are required for automation checks. Card 01 confirms the summary read for one automation on the target object; a prerequisite failure keeps the run on card 01 until the automation summaries finish. The runner says retry to re-enter card 01; the stop produces no report or backlog.

## Session contract

Use customer language in chat, report and backlog. Record every runner choice and orchestrator default in `decisions_log` with `who`, `what`, `evidence` and `date`. Copy node identifiers from tool rows; never retype them. Pass `teamId` from `get_space_context` on every later Elements call and use the chosen completed-sync model's `refModelId`; do not switch the active space. Read every `authorized` page. Batch set reads to each tool's input maximum: `get_dependencies` 1,000 node ids, `get_metadata_source` 5,000, `get_metadata_component` 50 and `search_metadata` 20 queries.

For set reads, poll `running` and wait `retryAfterSeconds` before polling again. On `complete`, download each part before its `expiresInSeconds` expires, check its `sha256` (Secure Hash Algorithm, 256-bit digest) checksum and confirm the downloaded row count matches `totalRows`. Save each reply as `{"_call":{"nodeIds":[...]},"response":<reply>}` for calls with `nodeIds`, or `{"_call":{"nodeId":"..."},"response":<reply>}` for a single-node call. Then pass the reply and parts list to `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/normalize_reads.py" <tool> <reply.json> [...] --work <work dir>`. Use the printed folder containing the normalized tool files (`dependents.csv`, `rows.ndjson`, `nodes.ndjson`, `index.csv` and `definitions/`) and `manifest.json`. Continue with `partsFrom: nextPartsFrom`. If a part link is stale, make one identical re-call to refresh it. If `resultId` changes between replies, discard held parts and restart with the new result. Never pass `limit`, `skip`, `format:"json"` or `delivery` to a files-only call. A refusal has `isError:true` and a JSON `error` code; read the code first. A failed job has `status:"failed"` and its code at `error.code`. Re-read `failed[]` nodes marked `retryable` using only their ids. Read totals from `totalRows` and the synthesized `manifest.json`; read fire-chain coverage from `coverage.json` and other failed-node coverage from `failed[]`. Retry a transient failed read once; `data/blocked-causes.csv` controls recovery. When a card resumes from card 05 and its required read succeeds, clear `blocked` before advancing; if it fails, preserve `blocked.retried=true` so recovery delivers incomplete. Every card 03 entry reruns that whole card. A script assertion failure is repaired before advancing.
