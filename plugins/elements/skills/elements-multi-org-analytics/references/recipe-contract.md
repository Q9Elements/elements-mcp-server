# Recipe contract

## Contents

- [1. The snapshot store](#1-the-snapshot-store)
- [2. `manifest.json`](#2-manifestjson)
- [3. The five guarantees](#3-the-five-guarantees)
- [4. HTML output rules](#4-html-output-rules)
- [5. Refresh](#5-refresh)

What a multi-org recipe is, what it writes, and what makes its numbers trustworthy. Every template
in this skill obeys this contract, and so must any bespoke recipe built from a conversation.

A recipe has pull instructions (Model Context Protocol (MCP) calls to dated snapshot files)
and a render script (snapshot files to self-contained Hypertext Markup Language (HTML)).

---

## 1. The snapshot store

The snapshot store is rooted in the user's working directory, where the recipe writes its outputs.
It contains plain files organized by date. Per-org files make an interrupted pull resumable and
keep the recorded inputs auditable; the rendered report is written there too.

```
snapshots/
  raw/<YYYY-MM-DD>/
    list_reference_models.json          # the org list for this run, plus confirmedOrgs
    describe_metadata_schema.json      # accepted types; call recorded in discoveryCalls
    <org-slug>/
      manifest.json                     # provenance for this org's pull
      understand_org_health__structure.json            # freshness dataAsOf and optional structure dimensions
      understand_org_health__tech_debt.json
      types_present.json                # per-org query schema and type enumeration
      list_metadata_by_criteria/
        manifest__all_nodes.json        # manifest-mode counts, one file per query
        manifest__type__flow.json
        <query>__part_<index>.ndjson                     # row-level pulls, when a recipe needs rows
  derived/
    metrics.csv                         # tidy: date,org,metric,value
```

Render scripts only read raw files. A same-day refresh can replace that date's raw directory; other dated directories stay intact.

**Derived is regenerated, never edited.** `metrics.csv` is an output of the render script. If it is
ever hand-maintained the audit path is dead.

### Org directories

Run the planner in workflow step 3 before creating directories. Its slug and collision check
owns directory identity; use the printed paths.

### Storing raw responses

Parse successful Model Context Protocol (MCP) text framing and classify refusals using
[Tool contracts](tool-contracts.md#access-and-failure-classification). Store resolved JavaScript
Object Notation (JSON) payloads at the normal snapshot paths; retain the received envelopes and
original downloads separately with their tool arguments.

An absent output file blanks only its dependent dimension. Record the actual refusal or missing-tool
reason; absence alone does not establish a licensing failure. Invalid JSON, missing provenance or
conflicting directory identity stops rendering: repair that raw input before re-running.

A dispatcher `file:{url,format,rows,bytes,sha256,expiresInSeconds}` can hold the whole result
or the complete page. For every call requesting `delivery:"file"`, read rows from the reply as
follows:

- A reply within the size budget is inline, with no `file` and no `fileError`; read its rows inline.
- An oversized reply carries `file`. Download it at once using `url` and `expiresInSeconds`, verify
  `sha256` (Secure Hash Algorithm 256-bit, SHA-256) and `rows` when supplied, and read the rows from disk.
- A reply with `fileError` could not write the file. Its rows, or a trimmed page, are inline; read
  them and continue with the paging fields in the reply.
- In every case, continue the tool's own paging. Follow `_truncated.nextSkip` or the tool's
  `hasMore`/`nextSkip` until it reports no more pages. A file covers only the result or page it
  describes, so do not treat one file as the complete result when more pages remain.

Retain both the envelope and downloaded file in provenance. Lifetime metadata applies to its own
link, not other links nested inside the downloaded payload.

Request `delivery:"file"` for `describe_metadata_schema` calls with `allNodes:true`; the dynamic
column inventory can exceed one reply. Apply the response and paging rule above. A schema call has
no paging cursor, so use complete inline data or report incomplete coverage when its reply is
trimmed.

Inspect `_oversize.movedToFile`: a field such as `columns`, `referenceModels` or an item breakdown
can itself be `{file:{...}}`. Download and parse that value into its original position before
reading it as an array. Keep each original file and its enclosing response; record each local
filename in provenance. The renderers consume the resolved payload at the normal snapshot path,
with envelopes and downloaded originals stored separately. `helpers._read_json` refuses unresolved
file descriptors, truncated payloads and inline refusals, so they cannot masquerade as no data.

For `_truncated.inFile:true`, consume the full file before continuing. For space pages use the
returned `_truncated.nextSkip`, then `nextSkip` if supplied, else current skip plus the actual
number of consumed `authorized` entries. Stop only at `pagination.hasMore:false`. Request
`delivery:"file"` from the start for eligible reference model, schema and health reads that can be trimmed.
Read budget-fit replies inline and resolve returned complete files before use. An unpaged reference model
list, schema or health summary has no skip continuation: hydrate the returned whole-result file,
or report incomplete coverage if no complete response is available. `list_reference_models`,
`describe_metadata_schema`, and `understand_org_health` accept this delivery argument. Do not
invent a skip argument or treat a trimmed list as complete. A file-write error keeps a complete
inline response usable; otherwise report incomplete coverage.
Criteria page mode uses `nextPartsFrom`, not a row offset. Inline preview rows and file rows are
the same page, so consume one complete representation, not both.

On an expired dispatcher link or failed download, repeat the same tool call with its original
arguments and recover a complete response. Native part-job refresh rules live in
[Row pulls](row-pulls.md). Read each link's returned lifetime independently. A Python download
handler catches `OSError`, `urllib.error.URLError` and `http.client.HTTPException` (including
`IncompleteRead`) and repeats acquisition; partial bytes never become snapshot data.

`_oversize.refusedInline:true`, an unrecovered trimmed response or missing moved values requires
an explicit incomplete-coverage report. `fileError` alone does not establish a gap when the complete
payload remains inline. The loader rejects any `_truncated` marker: for `_truncated.inFile:true`,
write the downloaded original payload, not the trimmed delivery envelope with its marker. The server
serializes the original payload before adding that annotation. Retain annotations with the envelope.

Agent-driven pulls relay tool output into files. Preserve the response as received and record
each tool call in `manifest.json`, so a questioned number can be re-pulled and compared.

---

## 2. `manifest.json`

One per org per dated directory. This is the provenance anchor: the thing that makes a number in
an HTML page traceable.

```json
{
  "snapshotDate": "2026-08-13",
  "pulledAt": "2026-08-13T05:04:12Z",
  "teamId": "bbbbbbbbbbbbbbbbbbbbbbbb",
  "spaceName": "Acme",
  "refModelId": "aaaaaaaaaaaaaaaaaaaaaaaa",
  "orgName": "Org D",
  "orgSlug": "acme-sales--org-d",
  "implementationName": "Acme Sales",
  "syncStatus": "unknown",
  "syncTime": "2026-08-13T03:58:41.000Z",
  "syncTimeSource": "understand_org_health__structure.json#dataAsOf",
  "skillVersion": "<recorded skill version>",
  "mcpBaselineVersion": "<recorded baseline identifier>",
  "recipe": "multi-org-overview",
  "curatedTypes": ["Field", "Custom Object", "..."],
  "typesPresentCaptured": false,
  "typeOptionsAreOrgInventory": false,
  "files": {
    "understand_org_health__structure.json": {
      "tool": "understand_org_health",
      "arguments": {"refModelId": "aaaaaaaaaaaaaaaaaaaaaaaa", "teamId": "bbbbbbbbbbbbbbbbbbbbbbbb", "area": "structure"}
    }
  }
}
```

### When one directory serves several templates

Templates share a dated directory when one builds on another. Technical Debt Comparison needs the
Overview's counts as denominators, so both read the same pull. In that case:

- `files` grows to record every file in the directory and the call that produced each. It is the
  union, and it is what makes each file traceable.
- Every `files` entry must identify the file it describes: its `tool` matches the filename
  convention (health files also require matching `arguments.area`) and `arguments.refModelId` equals the enclosing manifest's `refModelId`.
- `recipe` stays the name of the base pull the directory was built from, not a list. The
  artifact states which template rendered it in its own invitation line; putting a second recipe
  name in the provenance block puts two different answers to "what made this page?" on one page.

### Freshness fields: the rules that matter

Capture `understand_org_health` with `area:"structure"` per org, recording its arguments and file.
A snapshot is stale after seven elapsed days from its sync instant. Health `dataAsOf` is the
last completed sync; discovery `status` describes the reference model, not its latest sync attempt.

- `syncTime` copies health `dataAsOf` verbatim and `syncTimeSource` names the raw file and field.
  A null value yields unknown freshness and excludes that org from trend calculations.
- These tools provide data age; set `syncStatus:"unknown"` and label the sync signal accordingly.
  If an external source supplies sync signals, record that source in the manifest.
- Staleness uses elapsed days from the sync instant at render time against the explicit as-of
  instant. `updatedAt` describes record updates and serves as display information only.

## 3. The five guarantees

| Guarantee | What it means here |
|---|---|
| Traceable | An observation → its `metrics.csv` row → that org's `manifest.json` → the raw file. A derived value names its inputs on the page |
| Reproducible | Same dated snapshot in, same HTML out; raw read-only during render, derived regenerable, no wall-clock inside helpers |
| Honestly fresh | Per-org as-of stamps from health `dataAsOf`; data-age labels and an unknown sync signal; external signals require a recorded source |
| Fair comparison | Normalization tiers applied before any comparison; peer groups shown, not assumed |
| Typed claims | Unfootnoted text is observed fact; interpretation footnotes into the Evidence tab |

### Name stability is load-bearing

**Every metric name rendered on the page must match the `metric` column of `metrics.csv`
verbatim.** That equality is the entire mechanical audit path: a reader greps the comma-separated values (CSV) file for the string
they saw. Renaming a metric silently breaks it; add a new metric instead of renaming an old one.

### Observations are traced; derived values name their inputs

**An observation** is a value read from a raw MCP response for one org; a count, a percentage
reported by a tool. Observations are rows in `metrics.csv`, and they carry the provenance trace.

**A derived value** is computed by the render script from observations; a peer median, a spread, an
observation count, an extreme, a rank, a stale total, elapsed days, an aggregate tile. Derived values
get no row. Instead they name their inputs on the page: "peer median of 3 observations:
org-a, org-b, org-c". The reader sees what went in without needing the formula, and follows those
orgs to their rows.

Where the inputs are named depends on how many there are. Naming inputs must not drown the value.

- Few inputs (up to 3): name them inline, next to the value. A peer median over three orgs reads
  well in a sentence.
- Many inputs: state the derivation and the count inline, and name the orgs in the Evidence tab:
  "sum of `total_nodes` across 6 orgs: listed in Evidence". Evidence is on the page, so the
  provenance is present; it is just not competing with the number.
- The header as-of stamp names nothing. It stays one line, counts only, ending in
  "see Evidence". It is furniture, not a claim, and it must remain readable at a glance.

What is enforced: name stability for observations (a rendered observation name matches its CSV
`metric` verbatim), and a cheap non-adversarial check inside the render script that every observation
name it rendered appears in the CSV it wrote. Nothing walks the rendered HTML looking for numbers.

For a provenance check, ask "where does this number come from?" and
it quotes the CSV row, the manifest entry and the raw fragment, and can re-pull to verify.

### Zero is not a default

A recipe prints `0` only for an observed zero. Missing observations emit no `metrics.csv` row.
A ratio with a zero or unknown denominator is blank, with its reason where the value belongs.

Capture each org's `describe_metadata_schema({refModelId,teamId,allNodes:true,delivery:"file"})`
as `types_present.json`. `types` is the accepted registry; dynamic `columns` may include
`type.options`, an enumeration. Set `typeOptionsAreOrgInventory:true` only when a customer-supplied
inventory for that org confirms these options' inventory meaning; record that inventory's source
in `typePresenceSource`. Otherwise keep the flag false. With confirmed inventory, both option
identifiers and labels count as presence.

| Condition | Typed as | Rendered as |
|---|---|---|
| Count 0 and type absent from accepted registry | not synced by Elements | blank, with reason |
| Supported, absent from confirmed org inventory | not present in this org | `n/a`, with reason |
| Present in confirmed inventory, count 0 | observed zero | `0` |
| Supported, inventory semantics unconfirmed | unknown presence | blank, with reason |

A positive criteria count always renders, even when the accepted registry omits that type.
Record a Known unknown naming the type and both disagreeing sources; this disagreement is not
store corruption. Missing schema or options leaves presence unknown.

---

## 4. HTML output rules

**Self-contained, hard requirement.** The artifact must render correctly with no network access,
opened from an email attachment, on a plane, years later.

- All Cascading Style Sheets (CSS) inline in a `<style>` block. No `<link href>` to anything remote.
- All charts hand-written inline Scalable Vector Graphics (SVG), using `<svg>`. No plotting library, no content delivery network (CDN) script.
- No web fonts, no remote images, no `fetch`.
- Standard library Python only, so the script runs anywhere with `python3` and no install step.

Furniture (from the trust contract):

- A one-line header as-of stamp, always visible, never behind a tab:
  `Data as of <date> snapshot · N orgs · M stale · U sync signal unknown: see Evidence`.
  Include sync-failure counts only when failures are recorded; an unknown signal supplies no zero.
- Report tabs stay clean: plain footnote markers only, no inline hedging.
- An Evidence tab carrying: footnote entries, the per-org freshness table, the provenance block
  (snapshot date, orgs pulled, skill + baseline version, recipe name, store path), known-unknown
  notices, and the invitation line
  `Generated by the <template> recipe · ask your assistant to customize or re-run it`.
- Omission notices render in place, where the blanked chart or org would have been; never
  collected into a footnote at the bottom and never silently dropped.


---

## 5. Refresh

One idempotent manual operation; "refresh the snapshot":

1. Pull today → write the dated directory.
2. Regenerate `metrics.csv` from raw.
3. Re-render the HTML.

Re-running a day overwrites only that day. Resume is free: files are per-org, so a run interrupted
at org 40 of 100 restarts by pulling only the orgs whose files are missing.

For large pulls, analyze in a fresh session from `manifest.json` and `metrics.csv`, so the
per-org payloads do not fill the analysis context.

Full re-pull every time. Incremental refresh is not available: there is no reliable change cursor
over MCP. Do not substitute a `last_modified_date` filter for one: that is the Salesforce clock,
not the Elements sync boundary, so it silently misses nodes that entered the Elements copy late
(backfill, post-failure catch-up, a newly included metadata type). It is a presentation device, never
a snapshot-completeness mechanism.

Scheduling is a per-surface upgrade over the same manual operation. Every scheduled run must write
the staleness check into the artifact, because scheduled pulls decay silently when org tokens expire;
the artifact is the only place that decay becomes visible.
