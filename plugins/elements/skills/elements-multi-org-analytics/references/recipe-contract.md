# Recipe contract

What a multi-org recipe is, what it writes, and what makes its numbers trustworthy. Every template
in this skill obeys this contract, and so must any bespoke recipe built from a conversation.

A recipe has pull instructions (Model Context Protocol (MCP) calls to dated snapshot files)
and a render script (snapshot files to self-contained Hypertext Markup Language (HTML)).
For large pulls, analyze in a fresh session so pull payloads do not fill the analysis context.

---

## 1. The snapshot store

Plain files, organized by date. Per-org files make an interrupted pull resumable and
keep the recorded inputs auditable.

```
snapshots/
  raw/<YYYY-MM-DD>/
    list_reference_models.json          # the org list for this run, plus confirmedOrgs
    <org-slug>/
      manifest.json                     # provenance for this org's pull
      get_org_structure.json            # optional; only recipes that consume this tool
      get_tech_debt_summary.json
      types_present.json                # list_metadata_columns response; only when a presence probe was needed
      query_metadata/
        manifest__all_nodes.json        # manifest-mode counts, one file per query
        manifest__type__flow.json
        <query>.csv                     # row-level pulls, when a recipe needs rows
  derived/
    metrics.csv                         # tidy: date,org,metric,value
```

Render scripts only read raw files. A same-day refresh can replace that date's raw directory; other dated directories stay intact.

**Derived is regenerated, never edited.** `metrics.csv` is an output of the render script. If it is
ever hand-maintained the audit path is dead.

### Org slugs

`<implementation-name>--<org-name>`, lowercased, non-alphanumerics collapsed to `-`.

Slug on the org name alone and orgs will collide: one observed space has three separate orgs all
named "Production". The implementation prefix is what makes the slug unique.

**The pull checks for collisions and fails loudly.** Two orgs in the *same* implementation whose
names normalize identically (`QA 1` / `QA-1`, or two reference models sharing a display name) would
produce one directory and silently overwrite each other. Before writing any org directory, build
every confirmed org's slug and stop with a clear error naming both `refModelId`s if any two match.

### Storing raw responses

Store what the tool returned, in the format it was requested in. Summary tools are JSON. Row-level
`query_metadata` pulls are CSV. Do not re-shape, re-key, or merge payloads on the way to disk — the
provenance trace depends on the raw file still looking like the tool's answer.

Agent-driven pulls relay tool output into files. Preserve the response as received and record
each tool call in `manifest.json`, so a questioned number can be re-pulled and compared.

---

## 2. `manifest.json`

One per org per dated directory. This is the provenance anchor — the thing that makes a number in
an HTML page traceable.

```json
{
  "snapshotDate": "2026-08-13",
  "pulledAt": "2026-08-13T05:04:12Z",
  "teamId": "...",
  "spaceName": "Acme",
  "refModelId": "...",
  "orgName": "Org D",
  "orgSlug": "acme-sales--org-d",
  "implementationName": "Acme Sales",
  "syncStatus": "updated",
  "syncTime": "2026-08-13T03:58:41.000Z",
  "skillVersion": "<recorded skill version>",
  "mcpBaselineVersion": "<recorded baseline identifier>",
  "recipe": "multi-org-overview",
  "curatedTypes": ["Field", "Custom Object", "..."],
  "typesPresentCaptured": false,
  "files": {
    "get_org_structure.json": {
      "tool": "get_org_structure",
      "arguments": {"refModelId": "..."}
    }
  }
}
```

### When one directory serves several templates

Templates share a dated directory when one builds on another — Technical Debt Comparison needs the
Overview's counts as denominators, so both read the same pull. In that case:

- `files` grows to record every file in the directory and the call that produced each. It is the
  union, and it is what makes each file traceable.
- Every `files` entry must identify the file it describes: its `tool` matches the filename
  convention and `arguments.refModelId` equals the enclosing manifest's `refModelId`.
- `recipe` stays the name of the base pull the directory was built from, not a list. The
  artifact states which template rendered it in its own invitation line; putting a second recipe
  name in the provenance block puts two different answers to "what made this page?" on one page.

### Freshness fields — the rules that matter

- **`syncTime` is `lastSyncCompleted` copied verbatim.** Never reformatted, never rounded, never
  recomputed.
- `syncStatus` is carried alongside it. `failed` is an independent sync failing signal and
  `inProgress` a sync running signal. Neither makes recently synced data stale; an org may be
  sync failing, stale, both, or neither.
- `updatedAt` is forbidden as a freshness input. It means "record touched". On an org whose sync
  is failing it can read weeks newer than `lastSyncCompleted`; a recipe that read `updatedAt` would
  report that org as fresh.
- Staleness is elapsed days since `lastSyncCompleted`, computed at render time against an
  explicit as-of value the script is given — never `datetime.now()` buried in a helper, so renders
  stay reproducible.

---

## 3. The five guarantees

| Guarantee | What it means here |
|---|---|
| Traceable | An observation → its `metrics.csv` row → that org's `manifest.json` → the raw file. A derived value names its inputs on the page |
| Reproducible | Same dated snapshot in, same HTML out; raw read-only during render, derived regenerable, no wall-clock inside helpers |
| Honestly fresh | Per-org as-of stamps from `lastSyncCompleted`; separate stale and sync-failing signals and header counts |
| Fair comparison | Normalization tiers applied before any comparison; peer groups shown, not assumed |
| Typed claims | Unfootnoted text is observed fact; interpretation footnotes into the Evidence tab |

### Name stability is load-bearing

**Every metric name rendered on the page must match the `metric` column of `metrics.csv`
verbatim.** That equality is the entire mechanical audit path: a reader greps the CSV for the string
they saw. Renaming a metric silently breaks it — add a new metric instead of renaming an old one.

### Observations are traced; derived values name their inputs

**An observation** is a value read from a raw MCP response for one org — a count, a percentage
reported by a tool. Observations are rows in `metrics.csv`, and they carry the provenance trace.

**A derived value** is computed by the render script from observations — a peer median, a spread, an
observation count, an extreme, a rank, a stale total, elapsed days, an aggregate tile. Derived values
get no row. Instead they name their inputs on the page: "peer median of 3 observations:
org-a, org-b, org-c". The reader sees what went in without needing the formula, and follows those
orgs to their rows.

Where the inputs are named depends on how many there are. Naming inputs must not drown the value.

- Few inputs (up to 3) — name them inline, next to the value. A peer median over three orgs reads
  well in a sentence.
- Many inputs — state the derivation and the count inline, and name the orgs in the Evidence tab:
  "sum of `total_nodes` across 6 orgs — listed in Evidence". Evidence is on the page, so the
  provenance is present; it is just not competing with the number.
- The header as-of stamp names nothing. It stays one line, counts only, ending in
  "see Evidence". It is furniture, not a claim, and it must remain readable at a glance.

What is enforced: name stability for observations (a rendered observation name matches its CSV
`metric` verbatim), and a cheap non-adversarial check inside the render script that every observation
name it rendered appears in the CSV it wrote. Nothing walks the rendered HTML looking for numbers.

For a provenance check, ask "where does this number come from?" and
it quotes the CSV row, the manifest entry and the raw fragment — and can re-pull to verify.

### Zero is not a default

A recipe may only print `0` for a value it actually observed as zero. Everything else — a type the
org does not have, a type Elements does not sync, a presence probe that was skipped, a ratio with a
zero denominator — is blanked with a stated reason, in place, where the value would have been.
A positive `query_metadata` count is observed and always renders, even if
`list_supported_metadata_types` omits that type. Record that disagreement as a known unknown naming
the type and both sources; it is not store corruption.

Writing 0 for an unknown is the single easiest way to produce a confident falsehood, and it is the
failure this contract exists to prevent. In the derived layer the same rule appears as: **emit no
row at all** for an unobserved value. A missing row means "not observed"; there is no sentinel.

---

## 4. HTML output rules

**Self-contained, hard requirement.** The artifact must render correctly with no network access —
opened from an email attachment, on a plane, years later.

- All CSS inline in a `<style>` block. No `<link href>` to anything remote.
- All charts hand-written inline `<svg>`. No plotting library, no CDN script.
- No web fonts, no remote images, no `fetch`.
- Standard library Python only, so the script runs anywhere with `python3` and no install step.

Furniture (from the trust contract):

- A one-line header as-of stamp, always visible, never behind a tab:
  `Data as of <date> snapshot · N orgs · M stale · F sync failing — see Evidence`
- Report tabs stay clean — plain footnote markers only, no inline hedging.
- An Evidence tab carrying: footnote entries, the per-org freshness table, the provenance block
  (snapshot date, orgs pulled, skill + baseline version, recipe name, store path), known-unknown
  notices, and the invitation line
  `Generated by the <template> recipe · ask your assistant to customize or re-run it`.
- Omission notices render in place, where the blanked chart or org would have been — never
  collected into a footnote at the bottom and never silently dropped.

The structural floor: render code owns the header, the freshness table, the provenance block, and
all observed content. An agent that ignores every convention still degrades to *inference sitting
outside a measured table*, never inference inside one.

---

## 5. Refresh

One idempotent manual operation — "refresh the snapshot":

1. Pull today → write the dated directory.
2. Regenerate `metrics.csv` from raw.
3. Re-render the HTML.

Re-running a day overwrites only that day. Resume is free: files are per-org, so a run interrupted
at org 40 of 100 restarts by pulling only the orgs whose files are missing.

For large pulls, analyze in a fresh session from `manifest.json` and `metrics.csv`, so the
per-org payloads do not fill the analysis context.

Full re-pull every time. Incremental refresh is not available: there is no reliable change cursor
over MCP. Do not substitute a `last_modified_date` filter for one — that is the Salesforce clock,
not the Elements sync boundary, so it silently misses nodes that entered the Elements copy late
(backfill, post-failure catch-up, a newly included metadata type). It is a presentation device, never
a snapshot-completeness mechanism.

Scheduling is a per-surface upgrade over the same manual operation. Every scheduled run must write
the staleness check into the artifact, because scheduled pulls decay silently when org tokens expire
— the artifact is the only place that decay becomes visible.
