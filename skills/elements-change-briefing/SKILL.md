---
name: elements-change-briefing
description: Produce a time-windowed change-log report of a Salesforce org (the list of every metadata node created or updated in a date window with its current status, a governance-derived deleted-event count, velocity and by-type breakdowns, anomaly highlights, and the Salesforce XML for the top movers fetched to disk for analysis). Use when the user asks what changed recently, this week, or in a period, whether there were unusual changes, wants a recurring sprint/weekly change report, or wants to see/diff the actual changed nodes and their XML, e.g. "what changed recently", "give me a change briefing", "list all changes this month and pull the XML". Do NOT use for a point-in-time org health snapshot rather than change-over-time; use elements-org-diagnostic instead.
---

# elements-change-briefing

Produce a change-log report of recent org changes: overall velocity, breakdown by metadata type, **the list of every node created or updated in the window** (with each node's current status), a governance-derived deleted-event count, anomaly highlights, and, for the top movers, the Salesforce metadata XML fetched to disk for analysis.

This is the org-wide equivalent of a "change log report": it enumerates the created/updated nodes (not just aggregate counts), lets you identify them, and pulls their XML. **Deleted nodes are not individually enumerable** — the drill-down chart excludes deletion-only changes, so report the deleted *count* from `get_governance_summary` (step 5) and say the individual deleted nodes can't be listed. See also the **XML diff limitation** note in step 6: the server returns the *latest* XML snapshot per node, not a before/after delta.

## Inputs

- `fromDate` / `toDate`: optional ISO 8601 dates; default to last 7 days
- `refModelId`: provided by user, or discovered automatically
- `spaceId`: from active space, or discovered automatically. `get_active_space` returns this value as **`activeTeamId`** (not `spaceId`/`teamId`); map that one value to the `{spaceId}` cache placeholder and to the tools' optional `teamId` argument.

## Prerequisites & licensing

`get_governance_summary` and `get_analytic_drill_down` require a **Pro Space with an Analytics Cloud license**; `get_node_change_history` and `get_metadata_node` are **Pro-gated**. Unlicensed tools are hidden from the tool list entirely; if any of these appear missing, licensing is why.

## Workspace cache

Skill artifacts live under `.elements/{spaceId}/{refModelId}/` at the **workspace root**; resolve the root with `git rev-parse --show-toplevel`, falling back to the current directory only if that fails (`{spaceId}` is the same value as the `teamId` passed to the tools). A wrong root misses existing caches and causes needless re-runs. Markdown artifacts written here must begin with a first line `generatedAt: <ISO8601 UTC>`, the single authoritative age source for freshness checks. Treat file mtime as unreliable (a clone/copy/worktree checkout resets it to "now"); if the header is genuinely absent and you fall back to mtime, say so and lean toward regenerating.

## Steps

1. **Resolve space and ref model.** If not already known, call `get_active_space` then `list_reference_models`. If multiple ref models exist, present the list and ask the user which to use.

2. **Establish date window.** If the user did not specify dates, set `fromDate` to 7 days ago and `toDate` to today (ISO 8601). Inform the user of the window. **Convert both to Unix epoch milliseconds**; the drill-down tool's `from`/`to` args are epoch ms (the governance tool takes the ISO dates).

3. **Velocity headline (aggregate).** Call `get_governance_summary` with `refModelId`, `fromDate`, `toDate`. This returns net change in metadata + by-type rollups + description coverage; use it for the velocity headline and the by-type table. It returns **no node IDs** (aggregates only); the changed-node list comes from step 4.

4. **Enumerate the changed nodes (the change log).** Call `get_analytic_drill_down` with `chartType:"changed-metadata"`, `label:"all"` (label is ignored for this chart), `from`, `to`, and `limit:200`. **Scope caveat:** this chart filters change-log events to `new` + `updated` only (server-side it slices the change-status enum to its first two entries), so it returns the nodes with a **create-or-update** in the window and **excludes deletion-only changes**. Its `totalItems` is therefore the new+updated node count, **not** an all-status change total — pull the deleted count from governance (step 3), not from here. Each item carries `_id` (the nodeId), `name`, `sfType`, `apiName`, `fullPath`, `status`, `lastModifiedDate`, `lastModifiedBy`; the item `status` is the node's *current* reference-model status, not the status of the matching historical change-log event. Read `totalItems` and `numPages` off the first page.

   **This tool has no `mode:"manifest"`**; page one's `totalItems`/`numPages` are your manifest.

   - **Small (one page covers it):** the first page is the whole change log. Use it inline.
   - **Large + the user wants the full corpus** (`numPages > 1` and they asked for everything, not just the top movers): **fan the pages out across parallel subagents: dispatch them concurrently in a single batch, ONE subagent per page**, ~5–8 in flight at a time (batch the rest if there are more pages). Each subagent calls `get_analytic_drill_down` with the same args plus `format:"ndjson"` and its own `skip = pageIndex × pageSize`, writes its returned `data` to `.elements/{spaceId}/{refModelId}/changes-page-{n}.ndjson` (zero-pad `n`, e.g. `page-00`), and returns **only the file path** (never the page contents). Do NOT loop the pages yourself in one agent; parallel subagents keep each page's raw data in a disposable context, out of yours, and cut wall-clock. (If your client has no subagent facility, page sequentially, but still write each page straight to its file.) Then merge **and verify** with the bundled script rather than a raw `cat`:

```
python3 <skill-dir>/scripts/merge_ndjson.py .elements/{spaceId}/{refModelId} \
        .elements/{spaceId}/{refModelId}/changes-master.ndjson --expected {totalItems} --key _id
```

   It concatenates the `*page*.ndjson` files in numeric order (defensively newline-joining), checks every line parses, `count == totalItems`, no `$$__tp__` leakage, and reports duplicates; exit 0/PASS only if the merge is intact. Then aggregate `changes-master.ndjson` with `jq`/`python`, surfacing **only the computed result**; do not read the whole file back into context. (Use `format:"ndjson"`, not `csv`, for multi-page fan-out; CSV repeats its header per page.)

5. **Change-type split.** Two different sources, don't confuse them:
   - **Deleted count — use `get_governance_summary` (step 3).** Its `governanceInfoForCharts` computes server-side deletion facets over the window (deleted totals merged into the general/status/type rollups), so it **does** give a confident **aggregate deleted-event count** for the period. What you *cannot* get is a unique *list* of deleted node IDs — the drill-down doesn't enumerate them (see below). Report the deleted count from governance; say the individual deleted nodes aren't enumerable.
   - **`get_analytic_drill_down` with `chartType:"changes-by-type"` does not honour the `label`** (`new`/`updated`/`deleted`): the label filter isn't applied server-side today, so every label returns the same set (effectively **new + updated**), and `deleted` nodes are **never enumerated** here — matching `changed-metadata`'s new+updated-only scope (step 4). Treat it only as a rough changed-set, not an authoritative bucket split. For an approximate new-vs-updated signal, read each node's own `status` field from step 4.

6. **Capture & diff the top movers (to disk).** Pick the top N changed nodes (default 5; by recency, or whatever the user names) from step 4. For each node, capture three artifacts as files (never inline the big payloads). **Know how the dispatcher size budget behaves before trusting any large result** (the budget is applied to every tool result): if the result **has a list**, one list is trimmed to fit and the result is flagged **`_truncated`** (`{field, returnedItems, totalItems, note}`, plus **`nextSkip`** when the tool paginates — the skip value to resume at). Which list gets trimmed is by *key priority*, not size: the first present of `items`, `objects`, `list`, `rows`, `nodes`, `deps`, and only if none of those exists does it fall back to the array with the most elements (element count, not bytes). So a result holding both a short `items` and a huge `changeLogs` trims `items` and leaves the big array whole. The backstop also rewrites `pageSize` to the number of rows actually returned and sets `hasMore`, so advancing by `pageSize`/`nextSkip` stays correct. This trimming happens whenever the result is over budget, so a big `changeLogs` array can come back short; check for it. If the result has **no list** to trim, it is returned intact but flagged **`_oversize`**, and **replaced by an `_oversize` refusal object carrying `refusedInline:true`** past the hard ceiling (a list result whose non-list remainder is still over the ceiling after emptying is likewise refused). A refusal object is **not** the node document — never save it as capture-succeeded; fall back to `as:"url"` XML retrieval (below). So: check `_truncated` (short list) and `_oversize` — write the value out, unless it carries `refusedInline:true`, which means capture failed.

   a) **Full node document**: `get_metadata_node({refModelId, nodeId, detail:"full"})` → write the returned object to `.elements/{spaceId}/{refModelId}/node/{nodeId}-document.json`. (Omit `detail` for just the lean summary; `detail:"full"` gives the sidebar-enriched node — all node fields except heavy blobs. Note: attachment *contents* are not included and `sfNode` is not fully expanded, so it is not a literal dump of the entire stored document.)

   b) **Change log + XML snapshots via URL (curl, not inline)**: `get_node_change_history({refModelId, nodeId, type:"changeLogs"})` for the entries (each has `_id`, `syncUUID`, `previousSyncUUID`, `status`, `lastModifiedBy`, `lastModifiedDate`, newest first). **The S3 keys `pathToXMLFile`/`pathToXMLFileBody` are stripped from every returned entry**, so you *cannot* tell from `changeLogs` which versions have a captured snapshot — try the entries in order and let the `auditLog` response tell you (a missing snapshot comes back as `{auditLog: {url: null, note: ...}}`). Keep the small `changeLogs` inline for the who/when/what. Then get the XML as a **download URL** and curl it; **never inline a large file**, because making the model re-emit a ~46KB `.cls` into a Write costs ~160s vs ~1s for curl:
      - `get_node_change_history({refModelId, nodeId, changeLogId: logs[0]._id, type:"auditLog", as:"url"})` → returns `{auditLog: {url, bodyUrl, ttlSeconds, note}}` (the fields are **nested under `auditLog`** — read `response.auditLog.url` / `response.auditLog.bodyUrl`). The URLs are **short-lived (~2 minutes)**; curl promptly (in the next action or two):
```
curl -s "<auditLog.url>" -o .elements/{spaceId}/{refModelId}/xml/{nodeId}-current.xml
# Apex/components also have a body (the .cls / source); append it to reproduce the full auditLog:
[ -n "<auditLog.bodyUrl>" ] && curl -s "<auditLog.bodyUrl>" >> .elements/{spaceId}/{refModelId}/xml/{nodeId}-current.xml
```

   c) **Diff vs previous (default for top movers)**: `previous` = the next older changelog entry (`logs[1]`/`logs[i+1]`). Since `pathToXMLFile` is stripped (step 6b), you can't pre-filter for entries that have a snapshot — request the candidate's URL (`changeLogId: previous._id, as:"url"`) and, if its `auditLog.url` is `null`, step to the next older entry. Curl the resolved URL to `xml/{nodeId}-previous.xml` (append `auditLog.bodyUrl` if present). Then run the bundled diff script and surface only the delta (not the XML):

```
python3 <skill-dir>/scripts/diff_xml.py \
        --previous .elements/{spaceId}/{refModelId}/xml/{nodeId}-previous.xml \
        --current  .elements/{spaceId}/{refModelId}/xml/{nodeId}-current.xml
```

   It pretty-normalizes both XMLs (tolerant of Apex/non-XML bodies) and prints a unified diff + a `+N / -M` summary; if there is no previous version it reports the node is new in range.

   Run the per-node capture in parallel (one subagent per node for many nodes; same path-only discipline as step 4; each returns only the written file paths + the diff summary).

7. **Synthesise the report.** Produce:
   - **Overall velocity**: total changes in the window (from step 4's `totalItems`), daily average, trend vs. prior period if `get_governance_summary` provides it.
   - **By metadata type**: table of top types by change count (from governance rollups and/or aggregating step 4's `sfType`).
   - **New / updated / deleted**: the counts from step 5 (or derived), flagging net deletions and new-automation bursts.
   - **Changed nodes**: a table of the changed nodes (name, type, status, lastModifiedDate, lastModifiedBy); for a large corpus, the `jq`-aggregated summary from step 4 plus the master file path.
   - **Top movers**: one row per node captured in step 6: its change-log summary (who/when/status), the `+N / -M` diff summary vs the previous version, and links to its files on disk (`node/…-document.json`, `xml/…-current.xml`, `xml/…-previous.xml`).
   - **Anomalies**: unusual spikes, deletion waves, automation bursts.

8. **Write artifact.** Filename from the window, e.g. `change-briefing-2026-06-17-to-2026-06-24.md`. Write to `.elements/{spaceId}/{refModelId}/` (root per Workspace cache; create parents as needed), first line `generatedAt: <ISO8601 UTC>`. Reference the changes master file and the per-node XML files by path rather than inlining them.

9. **Report to user.** Confirm the artifact path, display the velocity headline + new/updated/deleted counts + anomaly highlights inline, and list the XML files written. Offer to drill further: pull XML for more nodes, widen the window, or diff a specific node manually from its XML.

## Output

`change-briefing-{fromDate}-to-{toDate}.md` written to `.elements/{spaceId}/{refModelId}/`, alongside `changes-master.ndjson` (large windows) and, per top mover, `node/{nodeId}-document.json` (full document) + `xml/{nodeId}-current.xml` / `xml/{nodeId}-previous.xml` (the diffed snapshots).

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "What changed this week / this month?" | Yes: full changed-node list + velocity |
| "Show me the actual XML of what changed / diff it" | Yes: top movers captured and diffed on disk |
| "Were there unusual changes?" | Yes: anomaly highlights |
| "How many were deleted?" | **Aggregate count yes, node list no**: `get_governance_summary` gives a confident deleted-event count for the window (step 5); the drill-down can't enumerate the individual deleted nodes |
| "How healthy is the org right now?" (point-in-time) | No; use `elements-org-diagnostic` |
| "Explain one changed flow in depth" | No; use `elements-metadata` |

## Notes on the tools

- `get_analytic_drill_down` is the change-log enumerator: `changed-metadata` (nodes with a **new/updated** change in the window — deletion-only changes are excluded, step 4) and `changes-by-type` (label filter not applied server-side, so it returns the same new+updated set regardless of `new`/`updated`/`deleted`, step 5). Neither enumerates deleted nodes — get the deleted **count** from `get_governance_summary`. Both take `from`/`to` as **epoch ms** and support `limit`/`skip`/`detail`/`format`, but **not** `mode:"manifest"`; use page one for counts.
- `get_governance_summary` is aggregate-only (velocity + by-type), no node IDs.
- `get_node_change_history` returns `changeLogs` + `auditLog`. By default `auditLog` is the **latest** snapshot; pass **`changeLogId`** (a `changeLogs[]._id`) for **that specific version**: current `_id` + previous `_id` ⇒ a two-version diff. **Any time you're retrieving the file, pass `as:"url"`** to get short-lived presigned download URLs (`url` + `bodyUrl`, ~2 minute TTL) and **curl them to disk** instead of inlining: a large `.cls` re-emitted through a Write costs ~160s; curl is ~1s. (Default `as:"xml"` inlines the body, fine only for tiny files.)
- `get_metadata_node` returns an 8-field summary by default (incl. `status`, which flags `"deleted"` change-tracking tombstones); pass **`detail:"full"`** for the **sidebar-enriched** node document — all node fields plus the GDPR/tag enrichment, but **not** a literal dump of everything stored: attachment *contents* are replaced with empty arrays and `sfNode` is not fully expanded. It is a **Mongo document, not an S3 file**, so there is no download URL; it returns inline JSON (large ones carry an `_oversize` flag, or are refused outright above ~1 MB — see step 6); write it with the Write tool. Only S3-backed files (the `auditLog` XML/`.cls`) support `as:"url"`.
- `scripts/diff_xml.py` diffs two captured XML files (previous vs current) and prints only the delta.

## Related skills

- `elements-org-diagnostic`: full 5-dimension org health snapshot
- `elements-metadata`: explore an individual changed node in detail
- `elements-metadata-query`: filter metadata by `lastModifiedDate` as an alternative enumeration path
