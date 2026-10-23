# 04 Audit bypass readiness

State: `impact-analyzed`

## Purpose

Give every predicted automation a quoted, evidence-backed verdict on whether an existing hook can
bypass it, including whether its scope is the load user or every user.

## Procedure

1. Build the complete automation set from every bundle's `automations.csv` and
   `fire-chain-digest.csv`. Include direct and transitive automations once by application programming
   interface (API) name and type. Include each namespace in `analysis.managedPackages`, each active
   duplicate rule in `analysis.duplicateRules`, and each name in `rehearsal.unpredicted` once.
   Rehearsal observations carry evidence stating "Observed in rehearsal, not in the fire chain."
2. Write `work/source/targets.json` from the bundle automation rows and fire-chain digest. Include
   each source-backed automation that fires for the confirmed operation once by node identifier, as
   `{ "nodeId": "...", "apiName": "...", "type": "..." }`. Use the `apiName` column, not the
   display label. Include direct and transitive firing automations; exclude rows proved non-firing by
   bundle trigger-event evidence. Fetch source for uncertain entry conditions. Keep managed namespaces
   and active duplicate rules in the verdict set even when they have no downloadable source.

   Call `get_metadata_source` with every target `nodeId`, `refModelId: slots.model_id`, and
   `teamId: slots.space_id`. While the reply status is `running`, repeat the identical call after
   `retryAfterSeconds`, up to `poll_cap` in `data/thresholds.csv`. Follow `nextPartsFrom` by passing
   it as `partsFrom` on the identical call until no more parts remain; this applies to the helper
   round too. Save each reply in call order as
   `work/source/replies/<n>.json` using
   `{ "savedAt": "<International Organization for Standardization (ISO) 8601 date and time in Coordinated Universal Time (UTC)>", "reply": <complete tool reply> }`. Set
   `savedAt` with the current Coordinated Universal Time (UTC), formatted under International
   Organization for Standardization (ISO) 8601. Run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_files.py" fetch --replies work/source/replies --root work/source --sync-date <sync.timestamp>`

   Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/source_files.py" scan --root work/source`.
   The scan extracts plausible helper names from Apex bodies and Apex Flow actions, excluding
   declared variables, comments, strings, local classes, platform types, known schema names, and
   package namespaces evidenced by schema references.
   Resolve each `missingCalledClasses` name with `search_metadata` using
   `sfType: "Apex Class"`; pass up to 20 names per call and keep only exact `apiName` matches.
   Ignore names with no exact match. Save the resolved node identifiers as helper targets, call
   `get_metadata_source` once for those helpers with the same Space and model, and save the replies
   under `work/source/helper-replies/<n>.json` in the same saved-reply format. Fetch them into
   `work/source` with `source_files.py fetch` and scan once more. Stop after this helper level.

   For source calls, retry a refusal after its `retryAfter` within `poll_cap`. Retry `at_capacity`
   like `server_busy`. A `source_files.py fetch` exit 3 means a part expired; repeat the identical
   tool call and save its replies before fetching again. Exit 0 completes the fetch. Map other fetch
   exits and scan errors to TR-14.
3. After both source rounds, call `list_metadata_by_criteria` once for `Custom Permission`, once
   for `Custom Metadata`, and once for custom settings. The custom settings call uses
   `metadataList: ["Custom Object"]` and two `eq` filters on `custom_settings_type`, one for
   `Hierarchy` and one for `List`; the filters combine as OR. Use `refModelId: slots.model_id` and
   `teamId: slots.space_id` for every call. Save each call's replies in its own folder:
   `work/bypass/switch-replies/custom-permission/`,
   `work/bypass/switch-replies/custom-metadata/`, or
   `work/bypass/switch-replies/custom-settings/`, using the saved-reply format from step 2. Poll
   `running` after `retryAfterSeconds` within `poll_cap`; retry refusals after `retryAfter`,
   including `at_capacity` like `server_busy`. Follow `nextPartsFrom` by passing it as `partsFrom`
   on the identical call until no more parts remain. Save each reply in call order before fetching
   or joining. Then run `part_files.py join` for each call, writing to its own file:
   `work/bypass/switch-rows-custom-permission.ndjson`,
   `work/bypass/switch-rows-custom-metadata.ndjson`, or
   `work/bypass/switch-rows-custom-settings.ndjson`. If a join exits 3, repeat the identical
   criteria call and save its replies. Exit 0 completes a join; map other join exits to TR-14.
4. Give the **bypass-readiness-auditor** agent the complete verdict set, confirmed manifest, Space identifier,
   Reference Model identifier, `data/bypass-mechanisms.csv`,
   `work/source/manifest.json`, the source files listed by that manifest, and
   the `work/bypass/switch-rows-*.ndjson` files. It returns exactly one verdict per automation: `present`,
   `absent`, or `unknown`, with one quoted source line per evidence field and the source date.
   Each `present` verdict includes the exact `switch` and `scope` (`user` or `org-wide`). Source
   text stays in local files; the orchestrator receives only quoted evidence lines and verdicts.
5. Write each auditor `couldNotCover` entry as an `unknown` verdict with the tool error as evidence.
   Write `work/bypass/verdicts.csv` with columns `apiName`, `verdict`, `scope`, `switch`, `evidence`, `nonFiring`, and
   `nonFiringEvidence`. Verify every automation appears exactly once and set `bypass.verdictsFile`.
   The playbook plans from current org evidence.
6. Regenerate the impact report with the audited firing evidence. Run:

   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/impact_report.py" work/bundle/<object>-<operation> [more bundle directories] --residue work/intake/residue.json --duplicate-rules work/rehearsal/duplicate-rules.json --managed-packages work/analysis/managed-packages.json --narration work/narration/<object>.json [more narration files] --bypass-verdicts work/bypass/verdicts.csv [--unpredicted-automations work/rehearsal/unpredicted.json] --out report/03-impact.md`

   Include `--unpredicted-automations` when that file exists. Card 03 is not rerun.

## Outcomes

Each transition (TR) number identifies one outcome.

- **TR-13 — every predicted automation has exactly one bypass verdict with evidence or an explicit
  coverage reason.** Record "bypass audit complete" in `decisions_log` and write
  `{"current_state": "bypass-audited", "current_step": "steps/05-ratify-safety-package.md"}`.
  Next card: `steps/05-ratify-safety-package.md`.
- **TR-14 — Otherwise.** `{"current_state": "impact-analyzed", "current_step": "steps/04-audit-bypass.md"}`.
  Next card: `steps/04-audit-bypass.md`. Record the default call in `decisions_log` and tell the user.
  Report failed automation names without node identifiers.

## Stop rule

After TR-13, dispatch card 05 in the same turn. Stop on TR-14.

## Failure

If a source fetch, scan, criteria call, join, auditor result, or report fails, record the aggregate-safe
error in `open_items` and take TR-14. Keep only the three published verdicts; add no blocked reason
or owner question.
