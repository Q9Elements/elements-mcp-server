---
name: elements-multi-org-analytics
description: 'Compose single-org Elements Model Context Protocol (MCP) tools into cross-org analytics for Salesforce orgs in one Space: discover orgs, repeat queries per org, save JavaScript Object Notation (JSON) snapshots, and render self-contained Hypertext Markup Language (HTML) with numbers traced to raw responses. Use when asked to "compare our orgs", work "across all our orgs", find "which org has the most X", compare a sandbox with production, or "give me an overview of our Salesforce orgs". Do NOT use for a single-org diagnostic, debt investigation or metadata explanation; use elements-org-diagnostic, elements-tech-debt or elements-metadata respectively.'
---

# elements-multi-org-analytics

Deliver a repeatable recipe: pull instructions, dated snapshots and a local, self-contained
Hypertext Markup Language (HTML) report. Every observed number traces to a raw response.
The plugin bundles the sibling skills needed to interpret individual metrics.

Criteria and schema reads require metadata read scope and reference-model view access; health summaries use event-log data.
Before discovery or classifying refusals, read [Tool contracts](references/tool-contracts.md);
blank only the affected dimension and name its reason.

## Concepts

- A Space (`teamId`) groups Salesforce connections and their synced reference models.
- `refModelId` addresses one reference model per data call; Salesforce `orgId` is display information.
- Discovery reveals only the caller's visible reference models; keep that visibility boundary.
- Implementation grouping is the default peer key. Show the grouping used on the report.
- Production/sandbox lineage is customer-declared; names alone do not establish pairing.

## Workflow

Run every command from the user's working directory, where `snapshots/` and the rendered report
live. Invoke scripts by their path, `<skill-dir>/scripts/<name>.py`; `<skill-dir>` means this
skill's installed folder. Check `python3 --version`; scripts need Python 3 and its standard library.
If unavailable, install Python 3 from https://www.python.org/downloads/ or use the manual fallback
below. Select the connected Elements server for the environment the user named; keep that server
throughout the pull. If ambiguous, resolve the environment before discovery.

1. Discover with `get_space_context({skip:0,pageSize:50})`, following the paging rule in Tool
   contracts. Then call `list_reference_models({teamId,delivery:"file"})` for the chosen Space.
   Pass `teamId` on each data call. Keep `set_active_space` out of the pull: it changes shared
   session state for other work using the token. If discovery is empty, check access or connected orgs.
2. Confirm the org list with the user and persist `confirmedOrgs` in `list_reference_models.json`.
   With one org, offer `elements-org-diagnostic`; render a single-org baseline only if requested.
3. Before creating org directories, run the [planner](scripts/plan_pull.py):
   `python3 <skill-dir>/scripts/plan_pull.py --discovery snapshots/raw/DATE/list_reference_models.json --template multi-org-overview > plan.json`.
   Add `--types "Field,Flow"` for a custom scope, `--with-tech-debt` for the debt extension,
   and `--space-pages N` with the actual discovery page count. Exit 0 produces ordered calls,
   arguments, slugs, paths, total calls and minutes. Exit 2 names the repair; fix and re-run.
   A collision names both reference model identifiers and stops the pull before files can be overwritten.
4. Pick a template: read [Overview card](templates/multi-org-overview/card.md), then follow
   [Overview pull spec](templates/multi-org-overview/pull-spec.md) literally. For cleanup comparisons,
   also read [Technical Debt card](templates/technical-debt-comparison/card.md) and follow
   [Technical Debt pull spec](templates/technical-debt-comparison/pull-spec.md). Validate the plan's
   types, columns and operators against returned schema before executing its count calls.
5. Execute sequentially. Classify refusals using Tool contracts; wait returned `retryAfter` on
   rate or capacity refusals and resume more slowly. Save per-org results as calls finish so an
   interrupted pull resumes from missing files. Narrow scope if the planner estimates over 30 minutes.
6. Before saving any file-backed reply, read [Recipe contract](references/recipe-contract.md#1-the-snapshot-store).
   Hydrate every file-backed value and save resolved payloads with original envelopes separately.
   Follow its manifest, freshness and zero-presence rules. Before a bespoke row query, read
   [Row pulls](references/row-pulls.md); shipped templates use manifest counts.
7. Run `python3 <skill-dir>/scripts/render_multi_org_overview.py --snapshots snapshots --date DATE --out overview.html`.
   Add `--as-of INSTANT` for an explicit comparison instant and `--peer-groups groups.json` for
   customer-declared groups. The renderer regenerates comma-separated values (CSV) in `derived/metrics.csv`.
   Its observation-name validator must pass: fix and re-run until it passes. Exit 0 means rendered;
   exit 2 names invalid input to repair. Open the local HTML and check Report and Evidence before delivery.

```text
- [ ] Discover the complete Space and reference-model list.
- [ ] Confirm orgs and save confirmedOrgs.
- [ ] Save a valid plan and resolve collisions.
- [ ] Read the selected card and pull spec; validate queries against schema.
- [ ] Execute sequentially and record refusals and partial coverage.
- [ ] Hydrate files; save resolved snapshots, originals and provenance.
- [ ] Render; fix validation failures and re-run; inspect Report and Evidence.
```

Manual fallback: build all directory slugs as `implementation--org`, lowercased with each run of
non-alphanumeric characters collapsed to `-`; stop if two confirmed orgs map to one directory.
Execute the pull spec in order and count its calls at the planning pace in Tool contracts.
If rendering cannot run, deliver the raw store with an explicit unrendered status; verify every
reported observation against its manifest and raw payload before describing any comparison.

## Guardrails and method

Never print 0 for an unobserved value. Apply the presence mechanics in Recipe contract.
Before designing a bespoke comparison, read [Comparison patterns](references/comparison-patterns.md)
for aggregation, peer extremes, ratio ranking, drift and the Architecture Scorecard.

Apply three tiers: within-org percentages; raw counts beside total size and custom share;
managed/custom split before comparison. The method reference holds the worked example.
Intentional difference earns observation wording; only good-direction ratios earn deficiency wording.
Metadata absence leaves a capability inference gap. Name every excluded org or dimension in place.
Stamp freshness per org and exclude unknown or stale inputs from trends. Peer statistics use
median and median absolute deviation (MAD) only with at least eight peers; smaller groups show extremes
and spread. The method reference defines grouping and refusal rules.

## Scale and templates

Use disk at every org count. Prefer manifest counts; most questions need no rows.
The planner counts discovery plus each org's printed calls; its minutes are a pacing estimate,
not a runtime guarantee. Full refresh and fresh-session analysis follow Recipe contract, section 5.
The workflow's live evaluation covers a single-digit org count; plan larger pulls conservatively.
Overview is an inventory baseline with trends once two dated snapshots exist. Technical Debt
builds on its denominators and has no renderer. Read its
[design reference](assets/deferred/render_technical_debt_comparison.py) only for design context.
For a catalog, use the cards and close with an invitation to customize the recipe.

## Interpretation and maintenance

Use `elements-tech-debt` for debt meaning, `elements-metadata` for a specific node and
`elements-change-briefing` for node-level changes. On Codex, invoke siblings explicitly by name,
for example `$elements-tech-debt`. Unfootnoted claims are observations; interpretation footnotes
into Evidence with its supporting inputs. Prescriptions require an explicit request.
Refuse a plausible falsehood the reader cannot detect; qualify true observations needing context.
The renderer imports [snapshot helpers](scripts/helpers.py); read that module when maintaining
snapshot validation.
