# 00 Start the engagement

State: `kickoff`

## Purpose

Establish the engagement boundary, name its owner, and make the local privacy rule explicit before any
load evidence is handled.

## Procedure

1. Start your first reply to the owner with this block, verbatim, before anything else in that reply:

   > **Data-load impact engagement: how your data is handled**
   >
   > **On your computer (Claude Code or Codex CLI):** the playbook's scripts read your load file, query results and debug logs on your computer. The large language model (LLM) sees only counts, field names and other summaries, never your record rows. Working files are saved in the engagement folder on your computer.
   >
   > **In a chat app (the Claude app, or any tool where you attach files to the conversation):** an attached file is likely to be read into the LLM context, including its rows.
   >
   > **To keep your rows out of the LLM context in a chat app:** attach a file that holds only the header line, and tell us the approximate number of rows. For parent-heavy loads we may also ask for a count per parent record, which we give you the query for. Rehearsal files (loader success and error files, debug logs) belong in Claude Code or Codex CLI.
   >
   > Nothing in this engagement changes your Salesforce org.

   In the block, CLI is command-line interface, and LLM is large language model.

2. Use the session working directory as the engagement directory. Create `work/intake/`, `work/bundle-baseline/`, `work/bundle/`, `work/analysis/`, `work/narration/`, `work/source/`,
   `work/bypass/`, `work/package/`, `work/rehearsal/`, `report/`, and `stories/`. Copy
   `templates/execution-state.json` to `execution-state.json` in that directory. Set
   `engagement.playbook_version` from `version` in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`.
3. Ask once for the data-load owner's name without suggesting a name from session context (git user
   or account name), and ask for the local data-source path. The source may be
   a comma-separated value (CSV) file or a Salesforce Object Query Language (SOQL) file. Set the engagement name to the source file name plus the current date, and record the start date and time.
4. State the privacy rule: raw CSV rows, SOQL results, and debug-log lines stay local. The model may
   read only local script outputs containing metadata names, aggregates, and counts. Record the rule in
   `decisions_log`.
5. Give the user `references/kickoff-checklist.md`. The named data-load owner is the only human
   decider in this playbook.

## Outcomes

- **TR-01 — the owner, source path, and privacy rule are recorded.** Write
  `{"current_state": "ready", "current_step": "steps/01-check-prerequisites.md"}`. Next card:
  `steps/01-check-prerequisites.md`.

- **TR-02 — Otherwise.** `{"current_state": "kickoff", "current_step": "steps/00-kickoff.md"}`. Next card: `steps/00-kickoff.md`. Record the default call in `decisions_log` and tell the user. The report names the missing item.

## Stop rule

After TR-01, report the recorded source path and owner without opening the source file, and dispatch card 01 in the same turn. Stop after TR-02.

## Failure

If a required slot is unknown, record it in `open_items`; TR-02 takes the default self-loop and names the missing item. Never open the source file to infer a missing slot.
