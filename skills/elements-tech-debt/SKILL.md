---
name: elements-tech-debt
description: Deep-dive on the tech-debt dimension of a Salesforce org; resolve flagged nodes, check each one's dependency blast radius and recency, and produce a ranked remediation list. Use when the user wants to decide what to fix or remove first, investigate inactive or outdated metadata, or turn diagnostic findings into an actionable cleanup plan, e.g. "investigate tech debt", "show me what to fix first". Do NOT use for a broad multi-dimension health check; use elements-org-diagnostic instead.
---

# elements-tech-debt

Deep-dive tech debt investigation for a Salesforce org. Resolves specific flagged nodes, checks blast radius, and determines recency to produce a prioritised remediation list.

## Prerequisites & licensing

- The 10 quick clean-up views (`run_quick_cleanup_view`, step 3) require an **Enterprise Space**.
- `get_tech_debt_summary` and `get_analytic_drill_down` require a **Pro Space with an Analytics Cloud license**; `get_dependencies` and `get_node_change_history` are **Pro-gated**.
- Unlicensed tools are **hidden from the tool list entirely** (visibility filtering); if one of these tools appears to be missing, licensing is why, not a server fault.
- **Degrade gracefully:** if `run_quick_cleanup_view` is unavailable (non-Enterprise space), note "the quick clean-up views require an Enterprise space" rather than failing, skip step 3's per-record lists, and base the investigation on what `get_tech_debt_summary` provides (severity dimensions + counts), drilling slices via `get_analytic_drill_down` where possible.

## Workspace cache

Skill artifacts live under `.elements/{spaceId}/{refModelId}/` at the **workspace root**; resolve the root with `git rev-parse --show-toplevel`, falling back to the current directory only if that fails (`{spaceId}` is the same value as the `teamId` passed to the tools). A wrong root misses existing caches and causes needless re-runs. Markdown artifacts written here must begin with a first line `generatedAt: <ISO8601 UTC>`, the single authoritative age source for freshness checks. Treat file mtime as unreliable (a clone/copy/worktree checkout resets it to "now"); if the header is genuinely absent and you fall back to mtime, say so and lean toward regenerating.

## Steps

1. **Resolve space and ref model.** If not already known, call `get_active_space` then `list_reference_models`. If multiple ref models exist, present the list and ask the user to confirm which to use.

2. **Check workspace for cached data.** Look for `.elements/{spaceId}/{refModelId}/org-diagnostic.md` (root and age rule per Workspace cache above). If it exists and its `generatedAt` header is less than 24 hours old, extract the tech debt dimension's findings (severity, top concerns, summary) from it and skip to step 4. Otherwise call `get_tech_debt_summary` with `refModelId`; this is the high-level severity overview that tells you which dimensions are worst.

3. **Pull the actionable lists from quick clean-up views; always run ALL 10.** The severity summary is the overview; the actual records to fix come from `run_quick_cleanup_view`. **Run every one of the 10 views** (batch the calls in parallel) with `refModelId` + `viewName`; do not pre-filter to a couple based on the summary, because the summary's counts are misleading (e.g. it can show low "inactive metadata" while a view surfaces hundreds of stale reports). Each returns `{viewName, totalItems, pageSize, numPages, skip, hasMore}` plus a `list` of already-resolved metadata nodes (no re-search needed to recover node IDs). The 10 views, in rough tech-debt priority:
   - `automation-review-inactive`: inactive flows/automation (silently broken logic)
   - `rules-review-inactive`: inactive validation/workflow rules
   - `reports-review-stale`, `dashboards-review-stale`: unused > 1 year (reports are frequently the single biggest pile)
   - `fields-assess-unused`: custom fields, low impact + low population
   - `record-types-assess-low-adoption`, `objects-assess-low-adoption`
   - `profiles-assess-unassigned`, `permission-sets-assess-unassigned`, `permission-set-groups-assess-unassigned`

   > **Filter to unmanaged before ranking.** Raw `totalItems` is misleading; most hits in `fields-assess-unused`, `permission-sets-assess-unassigned`, `objects-assess-low-adoption` are **managed-package** metadata (`nodeDetails.isManaged === "Yes"`) that the customer cannot delete, and `profiles-assess-unassigned` returns **standard** profiles that cannot be deleted either. Count managed vs unmanaged per view and base the actionable list on the **unmanaged** items. Report the managed share so the headline number isn't mistaken for removable debt.

   > **Large views can exceed the client's tool-output limit.** High-volume views (reports, fields, permission sets, objects can each be 50–230 KB). Some clients spill oversized tool results to a file path instead of returning them inline (e.g. a `tool-results/*.txt` path). When that happens, extract a compact projection (name, `sf.type`, `nodeDetails.isManaged`, `assignedUsers`/`recordCount`/population, `lastModifiedDate`) with a `python3` slice or a subagent; never read the raw file back into context. If your client truncates instead of spilling, re-call the view with `limit`/`skip` pages and project each page the same way.

   From the combined unmanaged results, select the top items to investigate further (favour inactive automation, then inactive rules, then the largest stale/unused piles such as reports, then the remaining assessment views).

   > **Drilling a specific tech-debt chart slice.** If the user wants the records behind one particular tech-debt chart slice (e.g. "Extreme" severity, "Below 75%" coverage), call the `get_analytic_drill_down` tool directly with `chartType` + `label`. No UI click and no separate drill-down skill is needed; drill-down is now just this tool.

4. **Dependency check.** Each item from step 3 already carries its node ID. For each one, call `get_dependencies` with `lookingFor: "incoming"` to understand blast radius (how many other components reference this node).

5. **Recency check.** For each item's node ID, call `get_node_change_history` with `type: 'changeLogs'` to determine when it was last modified. A node untouched for 12+ months is a stronger removal candidate than one edited recently.

6. **Synthesise and rank.** Score each item by combining:
   - **Severity**: type weight (inactive automation > inactive rules > stale/unused assessment views)
   - **Blast radius**: dependency count from step 4
   - **Recency**: months since last change from step 5
   Produce a ranked list (highest score first). For each item write one paragraph: what it is, why it's risky, its blast radius, when it was last touched, and a recommended action.

7. **Write artifact.** Save the ranked list to `.elements/{spaceId}/{refModelId}/tech-debt.md` (root per Workspace cache; create parent directories if needed). Include:
   - First line: `generatedAt: <ISO8601 UTC>`
   - Ref model name and ID
   - Ranked items with scores and paragraphs
   - A short executive summary (3–5 bullets)

8. **Report to user.** Confirm the file path written and display the top 5 items as a summary table with columns: Rank, Name, Type, Blast Radius, Last Changed, Recommended Action.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note}`, plus **`nextSkip`** when the tool paginates —
resume the next call from `nextSkip` rather than from your own offset arithmetic, since the backstop
also rewrites `pageSize` and sets `hasMore` to stay consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Output

`tech-debt.md` written to `.elements/{spaceId}/{refModelId}/` at the workspace root.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "What should we fix or remove first?" | Yes, ranked remediation list with blast radius + recency |
| "How much of this debt is actually removable?" | Yes, managed vs unmanaged split per view |
| "Show me the records behind one tech-debt chart slice" | Yes, `get_analytic_drill_down` with `chartType` + `label` |
| "How healthy is the org overall?" | No, use `elements-org-diagnostic` |
| "Build me a custom filtered list of metadata" | No, use `elements-metadata-query` |

## Related skills

- `elements-org-diagnostic`: run a full org health check first to populate cached tech debt data
- `elements-metadata`: explore individual flagged nodes in detail
