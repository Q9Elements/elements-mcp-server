---
name: elements-metadata-query
description: Build filtered, ad-hoc lists of Salesforce metadata in an Elements reference model and optionally save them as named custom views. Use when the user wants a list defined by attribute criteria across a metadata type, e.g. "all screen flows", "every Apex class with low test coverage", "fields with population over 50% on Account", "list inactive validation rules", "build a view of …", "save this as a view". Drives the Elements "Custom views of metadata" feature (Enterprise). Do NOT use to find or explain a single named node (use elements-metadata); do NOT use for the canned tech-debt cleanup lists (use elements-tech-debt); do NOT use for permission/access audits (use elements-access); do NOT use to define or populate MetaFields (use elements-metafields).
---

# elements-metadata-query

Build an ad-hoc, attribute-filtered list of Salesforce metadata ("all screen flows on an old API version", "all fields with population > X on Account"), then optionally persist it as a named custom view. The columns you can filter on are dynamic per space, so always discover them first.

This is an Enterprise feature and requires view access to the reference model.

## Workflow

1. **Resolve the reference model.** If you don't already have a `refModelId`, call `list_reference_models` (after `get_active_space` / `set_active_space` if the space is ambiguous) and pick the model the user means. Note the model's `role` (`view` / `edit` / `manage`) from that response; it decides whether the user can save a *shared* view later (step 4). **Multi-space note:** `list_reference_models`, `list_metadata_columns`, `query_metadata`, and `save_metadata_view` all take an optional `teamId` (the Elements space id) that becomes **required when the OAuth token is authorized for more than one space** and none is active — the server returns `active_space_required`. Pass the target space's `teamId`, or set it with `set_active_space` (`get_active_space` returns it as `activeTeamId`).

2. **Discover columns (always before querying).**
   ```
   list_metadata_columns(refModelId, metadataList: ["Flow"])
   --> { columns: [ { value, displayValue, type, allowedOperators, filterable, displayable, options? } ] }
   ```
   Pass at most **50 types** in `metadataList`. `allNodes: true` is the alternative, not an addition — it **ignores `metadataList`** entirely, so don't send both and expect the types to narrow it. It returns the **union** of the columns of every metadata type (plus a few object-children columns), not the intersection: expect *more* columns than for any single type, and treat a column offered under `allNodes` as valid *somewhere* in the model, not necessarily for the types your query will hit.

   Use the returned `value` as the filter `column`, and pick an `operator` from that column's `allowedOperators`: an operator outside that set is refused with `invalid_filter_operator`, which names the valid ones. Enumerated columns return `options` as `{id, label}` pairs; filter with the `id`, including for MetaField picklists. MetaField columns also advertise `isExists`, the counting operator for nodes that do or do not hold a value. MetaField number and datetime columns get the full numeric/date operator sets (`gt`, `lt`, `gte`, `lte`, `range`), not just the string ones. Boolean columns take literal `true`/`false`; only the labels `yes`/`active`/`no`/`inactive` also coerce, so a boolean column that advertises `Applied`/`Not Applied` will **not** match a label — pass `true`/`false`. Don't invent column keys or metadata types: an unknown filter column returns `invalid_filter_column`, an unknown `metadataList` type returns `invalid_metadata_type`. **`query_metadata` validates types against its own allowlist, which uses singular labels (e.g. `Field`, `Approval Process`) — this is NOT the `list_supported_metadata_types` list (whose labels are often plural, e.g. `Approval Processes`); if a type is rejected, try the singular form.**

3. **Run the query.** Translate the user's request into `metadataList` + `filters` (each `{column, operator, value}`; use `secondValue` only for the `range` operator).

   **How filters combine.** Predicates on *different* columns are **AND**-ed. Two or more predicates on the **same** column are **OR**-ed — the engine collects them into a single `should` clause with `minimumShouldMatch: 1`, so a repeated column reads as an `IN` list. This is the Elements view-builder behaviour, not a defect. The consequence to remember: `api_version gte 60` + `api_version lte 63` is a **union, not an interval**. For a bounded range use one `range` filter with `secondValue`. To narrow *within* one column, use an excluding operator (`neq`, `doesnotcontain`) instead of stacking positive predicates.

   **Every filter column must also be a selected column.** This is an engine requirement, not a formatting rule: a MetaField filter is applied through the join that selecting its column creates, so a filter on a MetaField column that isn't selected is **silently ignored** — no error, no effect. Passing an explicit `columns` list is the safe shape, because the tool then rejects an unselected filter column and tells you to add it. Omitting `columns` switches that check off and relies on the default column set happening to contain your filter columns — true for a type's own MetaFields, **false under `allNodes`**.
   ```
   query_metadata(
     refModelId,
     metadataList: ["Flow"],
     filters: [
       {column: "subtype",      operator: "eq", value: "Screen flow"},
       {column: "api_version",  operator: "lt", value: 47}
     ],
     format: "ndjson"
   )
   --> { data, totalItems, viewSpec }
   ```
   Show the rows and `totalItems`. Keep the returned `viewSpec` — it round-trips into `save_metadata_view`, **provided it has at least 2 columns** (the save rejects a view with fewer as `invalid_view`). If you queried with 0–1 explicit `columns`, omit `columns` to get the default set, or add a second column before saving. Use `limit`/`skip` to page large results (`totalItems` tells you the full count). Set `allNodes: true` to query across every metadata type instead of `metadataList`.

   > **When you filter on a MetaField column, always pass that column in `columns`.** A MetaField predicate is applied through the join that selecting its column creates, so if the column is not selected the predicate is accepted and then silently dropped — no error, no flag. Passing `columns` explicitly also re-enables the server's own unselected-filter-column rejection, so a mistake becomes an error instead of a wrong answer.
   >
   > This bites hardest under `allNodes: true`, whose 17 default columns include **no** MetaField: the same `isExists` filter returns the whole model with `columns` omitted and the correct count with the column selected (measured on the shipping build: 27,706 versus 19). It is not an `allNodes` restriction — `allNodes` with a MetaField filter is fully supported *provided the column is selected*. Filters on built-in columns are unaffected either way, because those are not join-backed.

4. **Offer to save.** After showing results, ask: *"Want me to save this as a named view?"* Only if the user says yes:
   - Get a **name** (2–40 chars).
   - Decide **shared or private** using the model `role` from step 1: only offer **shared** (visible to everyone in the space) when `role` is `edit` or `manage`. If `role` is `view`, don't offer shared; save **private** (personal; needs the `metadata:write` scope but only *view* model-role — no edit/manage rights) and tell the user a shared view would need edit/manage rights. Private views are capped at 5 per user per model, so reserve them for views the user actually wants to keep.
   ```
   save_metadata_view(refModelId, name: "Old-API screen flows", viewSpec, private: false)
   --> { viewId, name, private }
   ```
   Pass the `viewSpec` from step 3 **as-is** — it round-trips cleanly (the server excludes its
   own injected not-deleted default from the echoed spec, so the saved view matches what a
   UI-created view would be). The save requires the default column **`name`** in `columns`
   (a view without it is rejected with `default_columns_missing`). If saving a shared view fails for lack of rights, offer to save it private instead. A model holds at most 50 shared views (private views don't count toward that cap). **A view whose filters use `isExists` on a MetaField column cannot be saved** (`unsupported_operator_for_column`): the Elements view builder does not offer that operator on MetaFields, so a saved view carrying it would render wrong in the UI. Query with it freely (it is the counting operator for populated values); just drop or replace that filter before saving. `query_metadata` tells you when this applies — the response sets `meta.viewSpecNote` naming the filters to remove before calling `save_metadata_view`.

## Notes

- Discover → query → (offer) save is the contract: do not call `query_metadata` with column keys you haven't seen in `list_metadata_columns` for the same type(s).
- MetaField `isExists` filters work in any position — the server normalises their order, and two or more `isExists: false` MetaField predicates are resolved as separate branches and intersected server-side. Only that multi-predicate path is size-capped: a branch resolving over 10,000 nodes is refused with `filter_branch_too_large`. A **single** `isExists: false` predicate skips branch resolution, so it is never capped and never refused however large the population — size it yourself with a manifest count first.
- Defining MetaFields or populating their values belongs to `elements-metafields`; this skill only queries their columns.
- Numeric operators (`gt`, `gte`, `lt`, `lte`, `range`) are what answer "more/less than X" questions like population or API version; string operators include `contains`, `startswith`, `eq`.
- **`startswith` requires a prefix of at least 4 characters** (shorter is refused with `invalid_filter_value`) and matches true prefixes exactly, in rows and counts.
- **Prefer `format: "ndjson"`** when reading rows: the page arrives as newline-delimited JSON in `data`, alongside the same `totalItems`/`viewSpec` metadata. Know the trade-off under the response-size budget, because neither format fails silently in the way the other does. A `json` page gets **trimmed**: the result carries `_truncated {field, returnedItems, totalItems, nextSkip, note}`, so it is visibly short and `nextSkip` tells you exactly where to resume. An `ndjson` page is a single string with no list to trim, so it comes back whole but flagged `_oversize`, and the very largest are **refused outright** with `refusedInline: true` — a refusal object, never data. So use `ndjson` with a `limit` small enough to stay in budget, and check for `_oversize`; when row size is unknown, `json` plus `nextSkip` is the safer loop.
- **A MetaField whose key collides with a built-in column** is returned under `<key>_metafield` in the row, so the built-in column keeps its own key. Read the MetaField's value from the suffixed key.
- **A MetaField titled "status" suppresses the default not-deleted filter.** That default is injected only when nothing named `status` is ambiguous; if the Space defines a MetaField called `status`, no default is added and deleted (change-tracked) nodes appear unless you filter them out yourself.
- **A value left over from a deleted picklist option reads as absent**, not as a raw id — option purges are asynchronous, so this renders the post-cleanup state rather than leaking a dangling ObjectId.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "All screen flows on an old API version" / any attribute-filtered list | Yes, discover columns, then `query_metadata` |
| "Save this list as a view for the team" | Yes, `save_metadata_view` (shared needs edit/manage role) |
| "Show me the `Credit_Limit__c` field" (a single named node) | No, use `elements-metadata` |
| "What should we clean up?" (ready-made cleanup lists) | No, use `elements-tech-debt` |
| "Who can access this field?" | No, use `elements-access` |
