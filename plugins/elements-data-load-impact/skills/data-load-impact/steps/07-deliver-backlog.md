# 07 Deliver the ordered backlog

State: `rehearsal-closed`

## Purpose

Turn the ratified package into the ordered stories the customer's team executes and
close the playbook without running the production load.

## Procedure

1. Use `work/rehearsal/duplicate-rules.json` written at card 03. Read `rehearsal.choice` from the
   state file and run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stories.py" --checklist work/package/checklist.csv --parameters work/package/parameters.json --duplicate-rules work/rehearsal/duplicate-rules.json --rehearsal-choice <rehearsal.choice> --org-context work/intake/org-context.json --tool-targets work/intake/tool-targets.json --bundle work/bundle/<object>-<operation> [repeat --bundle for each target] --out-dir stories/`

   Do not hand-edit generated stories; correct inputs and regenerate.
   Tell the owner the stories written: the five core stories by name, plus each extra review story and why it exists.
   A finalized package ratified for go produces all five core stories with a zero-row checklist.
   Checklist-driven criteria are absent; an otherwise empty setup or re-enable story carries a
   criterion to confirm again against the org that no automation fires before loading.
2. Write `report/final-report.md` with the owner-confirmed manifest and every persisted manifest
   evidence path, complete impact, narration, and lock evidence. Name the active Space,
   selected Reference Model, and automations by their names; keep Elements internal identifiers
   in state and work files only. Include the
   ratified checklist and parameters, incident-class controls and exceptions, active duplicate rule
   names by object, every current `knownRisks` entry including each email sender ruled `leave-on`, and
   story paths. For each narration-only checklist row, state "named in the order-of-execution
   explanation; not in the Elements load analysis" and its audited firing status. Render a plain
   coverage statement, including "activation could not be verified" for unresolved activation;
   retain raw lookup and tool evidence in work files.
   Retain each entry's object, type, and application programming interface (API) name when carrying
   activation evidence into the report and stories. Record `non_firing`
   rows as not firing, outside load risks and future-hook recommendations. Group `bypass` rows with `bypass_scope: user` under "Bypass for the load user" and
   all other `bypass` rows under "Bypass for every user while the switch is off"; name each
   `bypass_switch` and its `blast_radius`. State "parent grouping was not rehearsed" as a risk when
   `groupByParentId` is true and `parentSortField` is null, or the batch could not be sorted by
   that field. If an accepted rehearsal established the sandbox, omit any "sandbox not yet established"
   risk from stories and this report. When `rehearsal.choice` is `rehearse`, include rehearsal
   reconciliation with the observed and summary paths and the measured duplicate count. For this
   path, state that each incident class has a named control, an owner not-applicable ruling, or an
   accepted rehearsal result including any not-measurable line. When `rehearsal.choice` is `skip`,
   state that the owner
   skipped the rehearsal, name `rehearsal.choiceBy` and `rehearsal.choiceOn`, and list every saved
   `rehearsal.reasonsToRehearse` line as a named stated risk that remains unconfirmed. Do not read
   or cite `rehearsal.observedFile`, `rehearsal.reconciliationFile`, `rehearsal.summaryFile`, or
   `rehearsal.duplicatesDetected` on this path. For this path, state that each incident class has
   a named control, an owner not-applicable ruling, or a stated unmeasured risk. State that zero
   incidents is the outcome target. Show lock contention as a named stated risk on this path,
   never as a named control from a ladder that was not run.
   Keep reviewer tags and internal tool, script, agent, and brief faults in `decisions_log`; reports
   and stories name only their effect on this load.
   State in one line when the analyzed Reference Model is a
   sandbox. For an sf CLI rehearsal, include this known limit once: "The rehearsal ran as sf CLI
   user <username>, not the production load user; production-user sharing and user-specific bypass
   were not exercised." List every firing or activation-unverified automation whose bypass verdict is `absent` or
   `unknown`; the final report recommends adding hooks (a bypass hook is a check inside the automation
   that lets it skip work within the hook's scope) and a dedicated migration user before future loads.
   State: "Run this playbook again after Elements re-syncs the org."
3. Set `backlog.storiesDir`, `backlog.storyFiles`, and `backlog.generatedOn`. Present the generated backlog and final report to the data-load owner.

## Outcomes

- **TR-26 — all required script-generated stories and `report/final-report.md` exist.**
  Record "backlog delivered" in `decisions_log` and write
  `{"current_state": "backlog-delivered", "current_step": null}`. Terminal.

- **TR-27 — Otherwise.** `{"current_state": "rehearsal-closed", "current_step": "steps/07-deliver-backlog.md"}`. Next card: `steps/07-deliver-backlog.md`. Record the default call in `decisions_log` and tell the user. Regenerate from package inputs; never hand-patch generated stories.

## Stop rule

After TR-26, report `report/final-report.md` and every file under `stories/`. After TR-27, report the gap. Stop after either outcome.

## Failure

If story generation fails or a required section is absent, record the gap in `open_items` and take TR-27, the default self-loop on `rehearsal-closed`. Correct package inputs and regenerate; never hand-patch generated stories.
