# 05 Ratify the safety package

State: `bypass-audited`

## Purpose

Turn the impact evidence and bypass verdicts into a complete set of controls and execution parameters,
then put every judgment in the data-load owner's hands.

## Procedure

If the owner declares no-go at any point, take TR-17 and list any unruled items in the final report.

1. Establish serial-mode evidence. For a User insert or upsert target, pass
   `--named-serial-operation create-users`. User-role, role-reparent and territory cases come from
   the written fields (`checklist.py` derives them). On every return from
   rehearsal, including TR-22 and TR-24 through card 04, preserve ladder changes in
   `rehearsal.ladderChanges`. When serial
   mode still produces lock errors, tell the owner the persistent count as a known risk and propose
   no further lock mitigation. If `manifest.loader` cannot run serial mode, state the indicated serial
   mitigation as an unavailable control and present that known risk for the owner's go or no-go.
   Keep the loader confirmed at card 02.
2. From the engagement directory, write the draft package:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" work/bundle/<object>-<operation> [more bundle directories] --loader <manifest.loader> --confirmed-api <manifest.api> --tool-targets work/intake/tool-targets.json --bypass-verdicts work/bypass/verdicts.csv --source-manifest work/source/manifest.json --managed-packages work/analysis/managed-packages.json --duplicate-rules work/rehearsal/duplicate-rules.json --checklist-out work/package/checklist.draft.csv --parameters-out work/package/parameters.draft.json [--prior-parameters work/package/parameters.json] [--named-serial-operation <reason>] [--target-fact User:<operation>=role_based_portal_user ...] [--unpredicted-automations work/rehearsal/unpredicted.json]`

   Include each `--target-fact` in `manifest.targetFacts`. Include `--unpredicted-automations` only
   when that file exists. On every return from rehearsal, pass `--prior-parameters`. Set
   `package.draftChecklistFile` and
   `package.draftParametersFile`.
3. Show the draft checklist as a short table with automation, type, proposed action, and reason;
   use each `proposed_disposition` as the recommendation in that table. If later evidence changes
   an action, regenerate the draft before presenting it.
   With zero rows, state that no automation fires for this load and keep the owner checklist
   header-only. Ratify the parameters, owner steps, incident controls, and go or no-go decision.
   Show parameters with name, proposed value, and reason. When `checklist.owner.csv` matches the
   current draft, reuse its recorded rulings and ask only for what remains unruled. Otherwise ask
   exactly: "Accept all proposed actions, or change any?" In the same
   exchange ask for a replacement data-quality check for each validation rule proposed or ruled
   `deactivate`. From the answer, write `checklist.owner.csv` and
   `parameters.owner.json`: copy all proposed actions and parameters for "accept all", then apply
   named changes. Record each owner answer that adds or changes a step in
   `parameters.owner.json.ownerSteps` as `{story, step, ruledOn}`. Use `story` values `pre-load`,
   `load`, `export-and-reconcile`, `re-enable`, or `rollback`, and the answer's time for `ruledOn`.
   When an owner step relies on an export taken before the load, also record that export as a
   pre-load `ownerSteps` entry. Put its restore procedure in `rollback`.
   Preserve recorded steps on each return and replace a changed step with the owner's current
   instruction and ruling time. Record the incident-class replies in `package.incidentClassRulings` and apply
   them to `parameters.owner.json` before finalization as described in step 5. On every return from rehearsal, show the carried lock parameter values in the
   table; accepting all keeps them. Include `groupByParentId`, `parentSortField`, `concurrencyMode`,
   `api`, `batchSize`, and `serialModeEvidence`. Record `ratifiedBy`, `ratifiedOn`, and `changedOn` in `parameters.owner.json`, using the time of the owner's answer for
   `changedOn`; record `knownRisksAcceptedOn` there at the owner's go-risk acceptance time;
   leave `goNoGo` unset until review is recorded. Copy normalized `not-applicable` and
   `measured-in-rehearsal` rulings from `package.incidentClassRulings` into
   `parameters.owner.json.incidentClassRulings`. For persistent errors after serial mode or when
   the recorded loader cannot run serial mode, ask
   the owner to include the measured lock count in the later go or no-go ruling. The owner never edits a file. Set `package.ownerChecklistFile` and
   `package.ownerParametersFile`.
4. Finalize the package:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/checklist.py" --finalize --draft-checklist work/package/checklist.draft.csv --draft-parameters work/package/parameters.draft.json --owner-checklist work/package/checklist.owner.csv --owner-parameters work/package/parameters.owner.json --checklist-out work/package/checklist.csv --parameters-out work/package/parameters.json [--prior-parameters work/package/parameters.json]`

   If finalization rejects a ruling, including conflicting rulings for the same managed-package
   namespace across targets, explain the error in one line, correct it from the owner's recorded
   decision, and rerun. On every return from rehearsal, pass `--prior-parameters`.
5. After first finalization, list each `uncontrolledIncidentClasses` entry without a recorded
   ruling or named go risk, using `plain_wording` from `data/incident-classes.csv`, and ask
   one combined question. Record one entry per class in
   `package.incidentClassRulings`: `{incidentClass, answer, ruling, answeredBy, answeredOn}`.
   Each `parameters.owner.json.incidentClassRulings` entry has `{incidentClass, ruling}`. Put only normalized "does not apply" as `not-applicable`
   and "may apply" as `measured-in-rehearsal` in
   `parameters.owner.json.incidentClassRulings`; neither needs a reason. An "applies" answer
   receives a control from existing package data where possible. Otherwise put its named risk
   in `parameters.owner.json.knownRisks` for the existing go or no-go decision. Finalize once
   with those rulings and risks. Classes already controlled do not enter this question.
6. When `package.reviewRoundsUsed` is below two, give the **safety-package-reviewer** agent the finalized checklist and parameters, every bundle
   directory, `work/bypass/verdicts.csv`, the manifest, and
   `${CLAUDE_PLUGIN_ROOT}/skills/data-load-impact/data/incident-classes.csv` plus each cited data file.
   Record its `BLOCKS`, `DISCRETION`, and stated-risk findings in `package.reviewFindings` and
   increment `package.reviewRoundsUsed`. Fix a
   `BLOCKS` finding from the files already held and rerun the reviewer once when needed, within
   the two-round engagement limit. On a return after round two, use the recorded findings and the
   current package files without another reviewer call. Every finding is resolved from held files or
   presented as a named risk in plain words within the go or no-go question. Record reviewer wording
   and any tool or script fault as an internal note in `decisions_log`; show the owner only the load
   effect. Include every named email sender `leave-on` risk in that question. Reviewer findings
   never generate another owner question or evidence request. Treat a sandbox Reference Model as
   the analyzed org and state that status once as a fact, outside `knownRisks`. Ask the owner for go or no-go.
   A no-go can be declared while rulings remain open; list those
   entries in the final report. For a go, require every checklist row and parameter to be ruled
   and every owner-rulable open class to have a ruling or stated risk. For a go, write that decision to `parameters.owner.json.goNoGo`, and run finalization
   again so the final parameter file carries the decision. Set
   `package.checklistFile`, `package.parametersFile`, `package.ratifiedBy`, `package.ratifiedOn`, and
   `package.goNoGo` from the finalized artifacts. If the owner declares go with persistent lock
   errors after serial mode ran or when the recorded loader cannot run serial mode, and the five
   lock parameters are unchanged from the prior finalized values, set
   `rehearsal.lockErrorsAccepted` to the measured count and record the risk and acceptance in
   `decisions_log`. A changed lock parameter leaves that count cleared until another rehearsal.
7. Write `report/05-safety-package.md` with the confirmed manifest, fire-chain and lock findings,
   checklist rulings, parameters, incident-class controls and exceptions, the load effects of open
   reviewer findings as named risks, and the
   owner's go or no-go, including any accepted persistent lock count and known risk. State the
   business outcome: each incident class has a named control, an owner not-applicable ruling, or
   a pending choice to rehearse or carry its unmeasured risk; zero load incidents is the target.
   Group `bypass` rows with `bypass_scope: user` under "Bypass for the load user" and all other
   `bypass` rows under "Bypass for every user while the switch is off". Use each row's
   `bypass_switch` and `blast_radius` in its instruction.

## Outcomes, in precedence order

The first condition that holds wins.

- **TR-15 — every checklist row and parameter is ruled, each owner-rulable open class has a ruling or stated risk, and the data-load owner declares go with the stated risks, including any persistent lock risk.**
  Record the owner's name, decision, and date and time in `decisions_log`, then write
  `{"current_state": "package-ratified", "current_step": "steps/06-rehearse.md"}`. Next card:
  `steps/06-rehearse.md`.
- **TR-16 — the data-load owner changes any manifest target.** Record the change and its author and
  date and time in `decisions_log`, reset the analysis, bypass, package, rehearsal, and backlog blocks to their template values,
  except keep `package.reviewRoundsUsed` (the review cap is per engagement) and `package.reviewFindings`. Empty
  `work/bundle*/`, `work/narration/`, `work/source/`, `work/bypass/`, `work/package/`, and
  `work/rehearsal/`, then write
  `{"current_state": "prerequisites-confirmed", "current_step": "steps/02-intake-manifest.md"}`.
  Next card: `steps/02-intake-manifest.md`.
- **TR-17 — the data-load owner declares no-go.** Write the
  decision and any unruled items to `report/final-report.md` and `decisions_log`, then write
  `{"current_state": "no-go", "current_step": null}`. Terminal.

- **TR-18 — Otherwise.** `{"current_state": "bypass-audited", "current_step": "steps/05-ratify-safety-package.md"}`. Next card: `steps/05-ratify-safety-package.md`. Record the default call in `decisions_log` and tell the user. The report lists what is still unruled; keep rulings already made; the default never infers go or no-go.

## Stop rule

After TR-15, dispatch card 06 in the same turn. Stop on a question to the owner, a self-loop, or a terminal state.

## Failure

If an owner ruling, validation replacement, owner identity, or date and time is missing, record the gap in `open_items` and take TR-18, the default self-loop on `bypass-audited`. Keep rulings already made; a reviewer finding that the playbook cannot fix from its files is a stated risk at go or no-go.
