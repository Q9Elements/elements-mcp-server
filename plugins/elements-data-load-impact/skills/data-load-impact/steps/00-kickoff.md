# 00 Start the engagement

State: `kickoff`

## Purpose

Establish the engagement boundary, name its owner, and make the local privacy rule explicit before any
load evidence is handled.

## Procedure

1. Use the session working directory as the engagement directory. Create `work/intake/`, `work/bundle-baseline/`, `work/bundle/`, `work/analysis/`, `work/narration/`, `work/source/`,
   `work/bypass/`, `work/package/`, `work/rehearsal/`, `report/`, and `stories/`. Copy
   `templates/execution-state.json` to `execution-state.json` in that directory.
2. Ask once for the data-load owner's name without suggesting a name from session context (git user
   or account name), and ask for the local data-source path. The source may be
   a comma-separated value (CSV) file or a Salesforce Object Query Language (SOQL) file. Set the engagement name to the source file name plus the current date, and record the start date and time.
3. State the privacy rule: raw CSV rows, SOQL results, and debug-log lines stay local. The model may
   read only local script outputs containing metadata names, aggregates, and counts. Record the rule in
   `decisions_log`.
   When the session has no local path to the source (the Claude app), tell the owner that an attached
   file may be read into the conversation, and that a file with real rows belongs in Claude Code or
   should be a copy holding only the columns the load writes.
4. Give the user `references/kickoff-checklist.md`. The named data-load owner is the only human
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
