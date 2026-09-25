---
name: elements-org-diagnostic
description: Produce a broad baseline health report of a Salesforce org across all five Tier-1 dimensions (structure, automation, tech debt, compliance, and governance) by calling the Elements health tools and synthesising one ranked risk summary, optionally enriched with object-level analytics (field population + object dependency hotspots). Use when the user wants an overall health check, first-pass assessment, executive diagnostic, or "where should we look first", e.g. "run an org diagnostic", "check org health". Do NOT use for a single-dimension deep-dive; use elements-tech-debt (tech debt) or elements-change-briefing (recent changes) instead; for one specific node use elements-metadata.
---

# elements-org-diagnostic

Run a full org health diagnostic by calling the 5 Tier 1 health MCP tools one after another, synthesise findings into a structured report saved as `org-diagnostic.md`, then optionally enrich it with object-level analytics and drill into the worst slices conversationally.

> **Prerequisite:** the 5 Tier-1 tools and `get_analytic_drill_down` all require a **Pro Space with an Analytics Cloud license**; unlicensed tools are hidden from the tool list entirely, so if they appear missing, licensing is why.

## Inputs

- `refModelId`: provided by user, or discovered automatically
- `spaceId`: take `activeSpace.teamId` from `list_reference_models` for the selected space. Use that value for the `{spaceId}` cache placeholder and the tools' optional `teamId` argument. `get_active_space` only reports the session's default and ignores a `teamId` argument; if no space is active, choose one with `list_authorized_spaces` and `set_active_space` before listing reference models.

## Workspace cache

Skill artifacts live under `.elements/{spaceId}/{refModelId}/` at the **workspace root**; resolve the root with `git rev-parse --show-toplevel`, falling back to the current directory only if that fails (`{spaceId}` is the same value as the `teamId` passed to the tools). A wrong root misses existing caches and causes needless re-runs. Markdown artifacts written here must begin with a first line `generatedAt: <ISO8601 UTC>`, the single authoritative age source for freshness checks. Treat file mtime as unreliable (a clone/copy/worktree checkout resets it to "now"); if the header is genuinely absent and you fall back to mtime, say so and lean toward regenerating.

## Steps

1. **Resolve space and ref model.** Call `list_reference_models` for the selected space and take `spaceId` from its `activeSpace.teamId`. If the space is not selected, use `get_active_space` to find the session default; if none is active, choose one with `list_authorized_spaces` and `set_active_space`. For a different space, pass its `teamId` to `list_reference_models` and confirm `activeSpace {teamId, name}` in the response. If multiple ref models exist, present the list and ask the user to confirm which one to use.

2. **Check for cached report.** Look for `.elements/{spaceId}/{refModelId}/org-diagnostic.md` (root and age rule per Workspace cache above). If it exists and its `generatedAt` header is less than 24 hours old, ask the user: "A diagnostic from {generatedAt} already exists; re-run or use cached?" Proceed according to their answer.

3. **Call the 5 tools sequentially**, one call at a time. The server allows 60 requests per minute per token, and every session using the same token (another chat, a subagent, a teammate's script) draws on that one budget, so pace your own calls even when this run alone would stay under it:
   - `get_org_structure` with `refModelId` and `teamId`
   - `get_automation_health` with `refModelId` and `teamId`
   - `get_tech_debt_summary` with `refModelId` and `teamId`
   - `get_compliance_summary` with `refModelId` and `teamId`
   - `get_governance_summary` with `refModelId` and `teamId`

   Read each failure by its error:
   - **`rate_limited`** ("Rate limit exceeded: 60 requests/minute per token; the token is locked for 60 seconds"): a throttle, not a licensing signal, and it can come from another session on the same token. Wait the full `retryAfter` (60 seconds; retrying early fails), then retry the failed call and continue one call at a time with a few seconds between calls.
   - **Tools absent from the tool list, or rejected as unlicensed**: the space is not Pro + Analytics Cloud licensed; tell the user that plainly rather than retrying or guessing at a server fault.

4. **Synthesise findings.** For each of the 5 dimensions produce:
   - **Severity**: `high` / `medium` / `low` / `unknown`
   - **Top concerns**: 3–5 bullet points
   - **Summary**: one sentence

5. **Determine overall risk.** Based on the 5 severities, assign an overall risk level (`critical` / `high` / `medium` / `low`) with a 2–3 sentence narrative.

6. **Object analytics enrichment (best-effort).** Both tools **rank results and return the top page** (the hotspots); no manual summing needed. Optional: do not let a failure block the core report.
   - `get_field_population` with `refModelId`: objects ranked by `adoptionGap` (0%-filled + below-25% field counts) descending; the first page is the worst-populated objects. Pro-gated.
   - `get_object_dependency_analysis` with `refModelId`: objects ranked by `totalDependencies` descending; the first page is the complexity hotspots. **Enterprise-gated** (`isSpaceEnterprise`): on a non-Enterprise space it's rejected; catch that, skip the dependency half, and note "object dependency analysis requires an Enterprise space" rather than failing.

   Take the first (ranked) page from each:
   - **Adoption gaps**: top objects by `adoptionGap`, with their `filled` band counts.
   - **Complexity hotspots**: top objects by `totalDependencies`, with the dominant `bars` types.
   Each response carries `totalObjects` + `hasMore`; the default page is enough for the diagnostic. If both error/empty, skip this enrichment.

   **Exhaustive corpus (opt-in; only when the user wants ALL objects, not just hotspots):** call with `mode:"manifest"` to get `{totalObjects, pageSize, numPages}`; if `numPages > 1`, **fan the pages out across subagents, ONE subagent per page, at most 3 in flight at a time** (start the next page when one returns). Each page is one request against the token's shared 60-per-minute budget (step 3), so a wider fan-out buys little wall-clock and risks locking the token for every session on it; a subagent that gets `rate_limited` waits the full `retryAfter` and retries its one call. Each subagent calls the tool with `format:"ndjson"` and its own `skip = pageIndex × pageSize`, writes its returned `data` to `.elements/{spaceId}/{refModelId}/objdeps-page-{n}.ndjson` (zero-pad `n`, e.g. `page-00`), and returns **only the file path** (never the page contents). Do NOT loop the pages yourself in one agent; subagents keep each page's raw data in a disposable context, out of yours. (If your client has no subagent facility, page sequentially, but still write each page straight to its file.) Then merge **and verify** with the bundled script rather than a raw `cat`:

```
python3 <skill-dir>/scripts/merge_ndjson.py .elements/{spaceId}/{refModelId} \
        .elements/{spaceId}/{refModelId}/master.ndjson --expected {totalObjects} --key _id
```

It concatenates the `*page*.ndjson` files in numeric order (defensively newline-joining), checks every line parses, `count == totalObjects`, no `$$__tp__` leakage, and reports duplicates; exit 0/PASS only if the merge is intact. Then aggregate `master.ndjson` with `jq`/`python`, surfacing **only the computed result**; do not read the whole file back into context. (Use `format:"ndjson"`, not `csv`, for multi-page fan-out; CSV repeats its header per page.)

7. **Write artifact.** Create `.elements/{spaceId}/{refModelId}/org-diagnostic.md` (create parent directories if needed) with:
   - First line: `generatedAt: <ISO8601 UTC>` (see Workspace cache; this is what step 2 reads)
   - Ref model name and ID
   - Findings per dimension (severity, top concerns, summary)
   - Overall risk assessment
   - **Object analytics** section (only if step 6 produced data): the adoption-gap and complexity-hotspot lists, each with the object name and the relevant count. Note clearly if the dependency half was skipped (non-Enterprise space).

8. **Report to user.** Confirm the file path written, display the overall risk level and per-dimension severities as a summary table, and (if present) the top adoption gaps and complexity hotspots. Then offer to drill in: "Want me to drill into the worst slices to show you the actual items behind them?"

9. **Drill into slices conversationally (if user agrees).** Two complementary drill-down tools: no Chrome, no clicking, no separate skill. Pick the slices that drive the high-severity findings from steps 4–6, or drill whatever the user names. Summarise each result inline (top items + total count), and offer to keep drilling.

   **a) Health & analytics charts: `get_analytic_drill_down`.** `get_analytic_drill_down({refModelId, chartType, label, ...})` returns the named metadata items behind a chart slice (name, API name, status, type, created/modified dates). `chartType` must be one of the enum'd values; `label` is the slice within that chart. Add `sfType` for the `complexity` chart ("Apex Class" or "Flow"), and `from`/`to` (epoch ms) for the time-range/governance charts.

   Concrete examples:
   - Worst tech-debt nodes: `get_analytic_drill_down({refModelId, chartType: "tech-debt-severity", label: "Extreme"})`. The `tech-debt-severity` labels are the severity tiers `Extreme`, `Severe`, `High`, `Moderate`, `Acceptable`. The `techDebtSeverity` keys in step 3's `get_tech_debt_summary` response (`processBuilders`, `workflowRules`, `customProfiles`, `inactiveMetadata`, `fieldsDeletion`, `outdatedApi`) are categories, not tiers: drill them with `chartType: "tech-debt-summary"`. Passing a category key to `tech-debt-severity` returns a plausible item list without an error, so match the label to the chart type.
   - Flows with poor fault coverage: `get_analytic_drill_down({refModelId, chartType: "flows-fault", label: "Below 75%"})` (use `flows-fault` for Flows; `test-coverage` returns Apex classes/triggers, not Flows)
   - All permission sets: `get_analytic_drill_down({refModelId, chartType: "permission-controls", label: "Permission Set"})`

   **b) Object dependency hotspots: `get_object_dependency_drill_down`** (Enterprise-gated, pairs with step 6's `get_object_dependency_analysis`). To list the actual dependency nodes behind one object + metadata type: `get_object_dependency_drill_down({refModelId, objectId, dependencies, ...})` where `objectId` is the object's `_id` from the `get_object_dependency_analysis` result and `dependencies` is one or more bar keys (metadata type names, e.g. `["Apex Class", "Flow"]`). Returns lean nodes by default (name, API name, status, type, complexity, dates) with accurate `totalItems`/`hasMore`; pass `detail:"full"` for all fields. For a very large slice, the same `mode:"manifest"` + `format:"ndjson"` fan-out from step 6 applies. (Objects with a null `_id` from the analysis cannot be drilled.)

   Example (the Apex on the busiest object): `get_object_dependency_drill_down({refModelId, objectId: "<object._id>", dependencies: ["Apex Class"]})`

   **c) Under-populated fields**: `get_field_population` (step 6) reports counts only. To list the specific sparsely-populated fields on an object, use the `elements-metadata-query` skill / `query_metadata` with a population filter on that object; `get_field_population` does not itself return field names.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note, nextSkip}`, with **`nextSkip`** present inside
`_truncated` when the tool paginates. Resume the next call from `_truncated.nextSkip` rather than from
your own offset arithmetic. The outer response
envelope rewrites `pageSize`, `hasMore`, and `numPages` to match what was actually returned; those
fields are not inside `_truncated`. `_truncated.totalItems` is the size of the trimmed list before
trimming, not the envelope's own `totalItems` or `totalObjects`, which represent the whole corpus.
Which list gets trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`,
`deps`, `chains`), falling back to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`**. That is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Output

`org-diagnostic.md` written to `.elements/{spaceId}/{refModelId}/` at the workspace root.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "How healthy is this org overall?" / "where should we look first?" | Yes, 5-dimension baseline + ranked risks |
| "Which objects are complexity or adoption hotspots?" | Yes, step 6 enrichment (Pro/Enterprise gates apply) |
| "Show me the items behind that chart slice" | Yes, step 9 drill-down |
| "What should we clean up first?" (ranked remediation) | No, use `elements-tech-debt` |
| "What changed this week?" | No, use `elements-change-briefing` |
| "Explain this one flow/field" | No, use `elements-metadata` |

## Related skills

- `elements-metadata`: explore individual metadata nodes flagged in the diagnostic
- `elements-metadata-query`: list the specific under-populated fields behind a field-population adoption gap
- `elements-access`: investigate the permission and access controls surfaced by drill-down
- `elements-change-briefing`: see recent change velocity and anomalies
- `elements-tech-debt`: deep-dive the tech debt dimension
