---
name: elements-tech-debt
description: Investigate Salesforce tech debt with list_metadata_by_criteria, get_dependencies and change history; produce a ranked Markdown remediation report, managed versus unmanaged cleanup counts, and chart-slice records. Use when asked "investigate tech debt", "what should we fix or remove first", "show the inactive flows", "unused fields we can delete", or "list the records behind the Extreme tech-debt slice". Do NOT use for overall org health (elements-org-diagnostic), general filtered metadata lists (elements-metadata-query), or a single component's dependencies (elements-metadata).
---

# elements-tech-debt

Input: an Elements space, reference model and cleanup or chart-slice question. Output: local `tech-debt.md` with ranked candidates, incoming dependency-edge counts, recency, per-view coverage and evidence gaps. Refused calls and incomplete evidence stay unknown, never zero. This workflow reads Elements data and writes local files.

On any refusal, read [refusals](references/refusals.md) before continuing. Choose the Elements connector for the user's named environment; resolve ambiguity before calling tools, then retain that connector throughout.

## Requirements and workspace

Use available Model Context Protocol (MCP) tools. Ordinary metadata reads require reference model view access.
Code search uses indexed source; starting a new search requires edit access.
If criteria are unavailable, use available health findings or chart records and report the cleanup coverage gap.

Resolve the workspace root with `git rev-parse --show-toplevel`, using the current directory if that fails.
Store artifacts under `.elements/{spaceId}/{refModelId}/`; `spaceId` is the selected `teamId`.
Every Markdown artifact begins with `generatedAt:` followed by an International Organization for Standardization (ISO) 8601 timestamp in Coordinated Universal Time (UTC).
Obtain run timestamps with `date -u +%Y-%m-%dT%H:%M:%SZ`; show local time with `date` when reporting time to the user.
A missing or invalid header means regenerate.

Check `python3 --version` before running scripts. They require Python 3.9 or newer, available from python.org or the runtime's package manager, and use only the standard library. Commands below run from this skill directory, with paths resolved against the workspace root.

## Workflow

1. **Resolve space and reference model.** Read the [call inventory](references/tool-contracts.md) for argument names, identifiers and response paths.
   Use `get_space_context` when context is missing, then `list_reference_models` with selected `teamId` and `delivery:"file"`.
   Before consuming discovery files, read [file results](references/file-results.md).
   Confirm an ambiguous reference model with the user; for another space, confirm returned `activeSpace` matches the intended space.

2. **Read cached health findings.** If `org-diagnostic.md` has a valid `generatedAt` less than 24 hours old, reuse its tech-debt findings.
   Otherwise call `understand_org_health` with `area:"tech_debt"`. Keep unavailable items and non-additive totals explicit.
   In either branch, continue at step 3 to obtain candidates.

3. **Collect actionable records.** Run all ten cleanup views sequentially because summary categories overlap and cannot establish candidate coverage. Before the first criteria call, read [file results](references/file-results.md). For each view below, call `list_metadata_by_criteria` with selected `refModelId`, `teamId`, `view` and `mode:"manifest"` to read `viewSpec.columns`. Then request rows with the same selection, `mode:"page"`, `format:"ndjson"` and `columns` containing those keys plus `"type"`, deduplicated. Explicit `columns` replaces the view's projection; preserving its keys retains screening and display values, while `"type"` supplies `sf.type` for the candidate script. Keep these columns on polling and continuation calls.
   - `automation_review_inactive`
   - `rules_review_inactive`
   - `reports_review_stale`
   - `dashboards_review_stale`
   - `fields_assess_unused`
   - `record_types_assess_low_adoption`
   - `objects_assess_low_adoption`
   - `profiles_assess_unassigned`
   - `permission_sets_assess_unassigned`
   - `permission_set_groups_assess_unassigned`

   On `invalid_input`, inspect returned `allowedValues`; record unsupported categories as unavailable. To narrow a view, first read [criteria filters](references/criteria-filters.md). Preserve the actual selection in the report.

   Save each parsed reply as `reply-input.json`. Run [fetch_parts.py](scripts/fetch_parts.py) after every reply, using a dedicated directory per view: `python3 scripts/fetch_parts.py reply-input.json "$RUN/views/$VIEW"`.
   Follow its continuation action until verified.
   `$RUN` is the artifact directory above; `$VIEW` is the requested identifier.
   For a refused view, save its refusal in that directory as `unavailable.json`.

   Then run [cleanup_candidates.py](scripts/cleanup_candidates.py): `python3 scripts/cleanup_candidates.py "$RUN/views" "$RUN/candidates.json"`.
   Read its coverage counts, screening flags and ordered candidates; keep raw rows on disk. The script owns mechanical projection and conservative standard-component screening.
   Resolve `confirm_custom_profile` before removal advice.

   Both scripts document exit codes and next actions in `--help`.
   Fix recoverable failures and re-run until they pass.
   If access prevents recovery, carry the named gaps into the report and label coverage incomplete.
   If scripts cannot run, manually download and reconcile files under the file-results procedure; tally each view's managed/unmanaged rows, apply the screening rules in the candidate script, and retain uncertain fields as unknown.

   For a requested chart slice, call `get_org_health_detail` with `chartType`, `label` and `delivery:"file"` using the inventory's labels and row paging. For a slice-only question, return those records and coverage; perform steps 4–8 when ranking is requested.

   **Select a bounded shortlist.** Order eligible unmanaged candidates by step 6's category weight `S` descending, then by the order `cleanup_candidates.py` emits. The script already emits this order: inactive automation, inactive rules, then other views in `VIEWS` order, preserving row order within each view and the first occurrence of each `nodeId`. Use the first 25 candidates, or the size the user requests, taking all eligible candidates when fewer are available. For manually assembled or chart-slice candidates, apply the same unmanaged and standard-component screening, deduplicate `nodeId` values, and sort by `S` descending while preserving acquisition order within each weight. Retain full per-view coverage counts; only shortlisted candidates enter steps 4–6. Candidates outside the shortlist are not scored.

4. **Measure dependency blast radius.** Use only the shortlist's distinct `nodeId` values. Call `get_dependencies` with batches of at most 1,000 identifiers, `lookingFor:"where_used"` and `mode:"manifest"`. Hydrate returned files before reading counts.
   - Match `nodes[].count` and `byType` to each requested node. Missing or `failed` nodes have unknown blast radius. Root `totalItems` counts edges across the selection, including repeated components and potentially dangling relationships.
   - Above 20,000 matching edges, the whole call returns `invalid_input` with `capsApplied.maxRows` and a split hint. Split the batch and retry. For an oversized single node, discover types with `describe_metadata_schema` and follow the hint's `sfType` selection. Sum only disjoint, exhaustive type partitions; absent coverage of linked reference model groups leaves the full count unknown.
   - Zero incoming edges establishes neither exhaustive metadata analysis nor safe deletion. For requested referencing rows, use `mode:"page"` and `format:"ndjson"`; run the downloader as at step 3. Dangling related nodes can make row totals differ from manifest counts.
   - Before removal advice for a code-bearing candidate (Apex Class, Apex Trigger or Flow) with zero incoming edges, run `run_code_search` using its returned `sf.apiName` (Salesforce application programming interface name). Search other types when source references affect the decision. Missing names or unavailable searches leave code coverage unknown. Matches supplement graph evidence.

5. **Check recency.** Call `get_component_change_history` for each shortlisted `nodeId` with `historyType:"change_logs"` and `delivery:"file"`. Follow its inventory paging and file-results procedure. Use the newest valid dated entry; unavailable or undated history leaves recency unknown. Calculate age against the run timestamp.

6. **Rank the shortlist with a declared policy.** Score only shortlisted candidates. Use this default heuristic, recording any user-requested replacement: `score = 10*S + B + R`.
   - `S`: 3 for inactive automation, 2 for inactive rules, 1 for other views; use the highest applicable category.
   - `B`: 2 for at least 10 incoming edges, 1 for 1–9, 0 for zero. Higher dependency counts prioritize investigation and controlled refactoring.
   - `R`: 1 when the newest change is at least 12 calendar months old, otherwise 0. Unknown `B` or `R` yields an unknown score in a separate evidence-follow-up list.
   Sort known scores descending, then incoming edges descending, then `nodeId` ascending. For each shortlisted candidate explain risk, evidence, last change and next action. The evidence-follow-up list contains shortlisted candidates with unknown scores. Recommend review, repair or controlled refactoring; removal remains subject to business-use confirmation and complete graph/code evidence.

7. **Write the report.** Save `tech-debt.md` using this default structure: `generatedAt`, reference model name/identifier, executive summary (3–5 bullets), per-view coverage table, shortlist scope, ranked shortlisted candidates with scores and explanations, evidence-follow-up list, and provenance/gaps. Coverage includes each view's total (`all`), managed, unmanaged, excluded-standard and eligible candidate counts (`unmanaged - excluded_standard`); unavailable counts stay unknown. State the shortlist limit, actual shortlist size, total distinct eligible candidate count, selection order and count outside the shortlist. Explicitly state that candidates outside the shortlist are not scored. Record tool, selection, result identity, file coverage and failure details. Validate coverage against `candidates.json` and the checklist below before delivery.

   Fabricated example: node `aaaaaaaaaaaaaaaaaaaa0319`, an inactive Flow with 3 incoming edges and a newest change 18 calendar months ago, scores `10*3 + 1 + 1 = 32`. Its report action is to confirm business use and inspect the three incoming edges before changing it. A failed manifest makes blast radius and score unknown.

8. **Report results.** Link the written file and show up to 5 known-score candidates from the scored shortlist in ranked order: Rank, Name, Type, Blast Radius, Last Changed, Recommended Action. Include the shortlist size, evidence-follow-up count and coverage limitations, stating that candidates outside the shortlist are not scored. For a cleanup-list question, show the requested view's counts and records; for a chart slice, show its records and coverage.

## Completion checklist

```text
- [ ] Intended connector, space and reference model resolved
- [ ] Cached health findings or health call recorded
- [ ] Ten views reconciled or individually marked unavailable
- [ ] Downloader and candidate checks pass, or named blockers remain explicit
- [ ] Shortlist follows category weight and emitted order, with default limit 25 or the user's requested size
- [ ] Dependency checks, history and scoring cover only shortlisted candidates
- [ ] Requested nodes reconciled with manifest successes and failures
- [ ] Required code searches and history completed, or unknown evidence recorded
- [ ] Scoring, ties, exclusions and follow-up list agree with evidence
- [ ] Report per-view totals match candidates.json; shortlist size and unscored remainder stated
- [ ] Top 5 table comes from known scores in the shortlist; timestamp and provenance present
```

## Related skills

Use `elements-org-diagnostic` for overall health, `elements-metadata-query` for general filtered lists, and `elements-metadata` to explore an individual flagged component.
