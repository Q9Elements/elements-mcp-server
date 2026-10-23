# 01 Check prerequisites

State: `ready`

## Purpose

Prove that the playbook can obtain, process, and retain complete evidence before intake begins.

## Procedure

1. Require a host that can run the shipped local scripts, such as Claude Code or the Claude app. If
   the host cannot run the shipped Python scripts, stop with: "This playbook requires a host that can
   run its local scripts, such as Claude Code or the Claude app, so customer data stays local while
   the deterministic scripts run."
2. Confirm that these Elements Model Context Protocol (MCP) tools resolve:
   `run_data_load_impact`, `get_space_context`, `list_reference_models`,
   `list_metadata_by_criteria`, `search_metadata`, `get_metadata_component`,
   `get_metadata_source`, and `explain_metadata_components`. A tool hidden because the Space
   lacks the licence is a missing primitive.
3. From the engagement directory, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/now.py"`.
   Record any failure in `open_items`; if no other outcome applies, take the TR-06 default self-loop on `ready`.
4. Call `get_space_context` and use its authorized Space list. If `slots.space_id` is set, reuse
   that authorized Space and its saved name. Otherwise, take the only authorized Space without
   asking. If several are authorized, offer their names with the active Space first and ask the
   owner which Space to use. Record its name in `slots.space_name` and identifier in
   `slots.space_id` for tool calls. Call `list_reference_models` for the chosen Space and page
   through every result. If `slots.model_id` is set, reuse that model and refresh its saved name
   from the matching result. If one model is returned, take it without asking. If several are
   returned, show their names and ask the owner which Reference Model to use. Record its name in
   `slots.model_name` and identifier in `slots.model_id` for tool calls. State the chosen Space and
   Reference Model names once in this card's report to the owner. Map `orgId` to `sync.orgId`. The
   selected model is the analyzed org. Use its model name as the organization label. When the
   model name identifies a sandbox, state that once in the report and continue. Pass the chosen
   Space as `teamId` on every later model or metadata call. Never show an internal identifier.
5. Run the bundle-host reachability probe in `references/evidence-acquisition.md`. Any Hypertext
   Transfer Protocol (HTTP) response is reachable. On a Domain Name System (DNS) failure, connection
   refusal, or timeout, record the exact host in `open_items`; if no other outcome applies, take the TR-06 default self-loop on `ready`.

## Outcomes, in precedence order

The first condition that holds wins.

- **TR-03 — one or more required tools do not resolve.** Set `blocked` to
  `{"reason": "MISSING_PRIMITIVE", "owner": "Elements administrator", "entered_from": "01", "evidence": ["<missing tool>"]}`,
  record the facts in `decisions_log`, and write
  `{"current_state": "blocked", "current_step": "steps/08-blocked-recovery.md"}`. Next card:
  `steps/08-blocked-recovery.md`.
- **TR-05 — every tool resolves, the script check succeeds, and the bundle host is reachable.**
  Record "prerequisites confirmed" in `decisions_log`, then write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-intake-manifest.md"}`.
  Next card: `steps/02-intake-manifest.md`.

- **TR-06 — Otherwise.** `{"current_state": "ready", "current_step": "steps/01-check-prerequisites.md"}`. Next card: `steps/01-check-prerequisites.md`. Record the default call in `decisions_log` and tell the user. The report names the exact failure.

## Stop rule

After TR-05, dispatch card 02 in the same turn. Dispatch card 08 in the same turn after TR-03. Stop on TR-06.

## Failure

If a script fails, the bundle host is unreachable, no authorized Space is available, or the saved Reference Model is absent from its Space, record the exact failure in `open_items` and take TR-06, the default self-loop on `ready`. Do not invent a blocked reason outside `data/blocked-reasons.csv`.
