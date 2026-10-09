# Reading the scan: scoreFactors & classification

Use the scan's factor contributions to explain rank, then classify the object from its signal fields.

## The score
`score` is a weighted sum of six normalized factors × 100 (so ~0–100, though factors rarely all max out).
Each object carries `scoreFactors`. In `detail:"summary"` (default) each factor is `{factor, contribution}`
(only the non-zero ones, biggest first: the one-line "why"); in `detail:"full"` each is
`{factor, weight, value, contribution, detail}` where `detail` is the human phrase (e.g. `"190058 records"`).

| factor | weight | what it measures | normalization |
|---|---|---|---|
| `unstructuredRatio` | 0.28 | free-text density: Text, Text/Long Text Area, Rich Text Area (HyperText Markup Language, HTML), and Encrypted Text fields ÷ classified fields; short Text fields inflate it, so finalists use the recomputed ratio below | the ratio itself (0–1) |
| `recordVolume` | 0.24 | how much data there is | log10(records+1) ÷ log10(100 000) |
| `automationGap` | 0.18 | inverse declarative/config automation density (from `sf.summaryInfoObjects`) | 1 − min(1, automations ÷ 20) |
| `recordVelocity` | 0.14 | net record growth over 30d (when snapshots exist) | log10(net+1) ÷ log10(10 000); 0 contribution when `dataAvailable:false` |
| `recency` | 0.10 | how recently records were touched | 0.5^(ageDays ÷ 90) from `lastModified`/`lastCreated` |
| `schemaComplexity` | 0.06 | field count (rich domain / cognitive load) | min(1, fields ÷ 150) |

`contribution = weight × value × 100`. To explain a rank, name the 1–2 biggest contributions and quote their
`detail` (full mode) or the matching signal field (summary mode). Example: *"EmailMessage scores 52.5 after the
free-text recompute (58.8 from the scan): 19,056 records (recordVolume 20.5), with human-readable body
fields HtmlBody and TextBody (free text 0.068 recomputed, 0.295 server)."*

## Recomputed free-text ratio (candidate objects)
The server's `unstructuredRatio` counts every Text field, so an object full of short String fields (email,
phone, postal code, country code) reads as prose-heavy. For each shortlisted object, SKILL.md Stage 2 pulls the
object's fields with `query_metadata` (filter `full_api_name startswith "<ObjectApiName>/"`, columns
`full_api_name`, `subtype`, `length`) and runs `scripts/free_text_ratio.py`:

- Free text = Long Text Area (subtype `Text area`, length over 255) + Rich Text Area (subtype `Rich text
  area`). Short Text Area (subtype `Text area`, length 255 or less) counts only with
  `--include-short-text-area`. String, Email, Phone, Url and Encrypted string fields are structured.
- Denominator = the scan row's `schema.fieldsTotal`, so the recompute corrects the numerator only.
- Recomputed score = `score − unstructuredRatio contribution + 28 × recomputedRatio`. Report both
  ratios side by side. One recompute costs one `query_metadata` call for an object with at most one page
  of fields; each additional page costs another call.
- Unavailable (query error, no page file exists, or no field rows): keep the server ratio and
  contribution, flagged "server ratio, unverified; may count short Text fields". The ranking stays
  unresolved when an unchecked row can enter the top 3.

Start with 3 to 5 candidates. Use recomputed scores for checked rows and server scores for unchecked
rows to find the next recompute set; this mixed ordering is provisional. Recompute every unchecked
top-3 row and every unchecked row whose server score reaches or exceeds the lowest of the current
top 3, then re-rank and repeat. Stop when the top 3 are all recomputed and no unchecked row
outranks or ties the lowest finalist. Mark every ranked row "recomputed" or "server ratio".
For example, four unchecked objects at 56.68, 56.44, 55.39, and 55.20 outrank an initial
recomputed shortlist at 52.67, 49.71, 48.83, and 46.94. Recompute those four in the next round;
their new scores determine whether another round is needed.

Illustrative values: a lead web-form staging object, server 0.571 (32 of 56), recomputes to 0.018
(1 of 56, `Comments__c`), so its unstructured contribution falls from 16.0 to 0.5; EmailMessage, server 0.295
(13 of 44), recomputes to 0.068 (3 of 44: HtmlBody, TextBody, Headers), so its contribution falls from 8.26 to
1.9 and its score from 58.84 to 52.48.

## Signal fields

Annotated `(full)` where `detail:"full"` is required; everything else is in both modes.
- `records.total`, `records.lastModified`, `records.byRecordType` (full), `records.lastCreated` (full)
- `schema.unstructured` / `structured` / `unstructuredRatio` / `custom` / `fieldsTotal`
- `automation.totalDependencies` (+ `automation.byType` in full). These counts come from
  `sf.summaryInfoObjects` and cover declarative/config metadata. They omit record-triggered Flows,
  Apex classes/triggers, and Global Actions, so confirm automation density with `get_dependencies`
  before classifying an object as under-automated.
- `velocity.net30` / `trend` / `dataAvailable`, plus `velocity.net7` (full) and `velocity.basis` (full).
  `net7`/`net30` are net record deltas from daily snapshot subtraction (`basis: "netRecordDelta"`), not a
  created/updated/deleted split, and are `null` when unavailable.
  `mode:"manifest"` skips the velocity aggregation entirely and returns `velocityDataAvailable: null`
  with a `velocityNote` — there, null means unknown, not unavailable; request a page to compute it.
- `population.adoptionGap` / `dataAvailable` (+ full `bands: {zero,below25,below50,below75,above75}`)
- `engagement.views30d` / `available`

## Classification heuristics (apply in Stage 2)
Read the vector, not just the score; the score ranks *interest*, the classification names the *kind* of
opportunity:

- Conversational agent / artificial intelligence (AI) workflow: meaningful `records.total` plus two or more populated
  long-form fields carrying content people write or read (message bodies, request details, case notes).
  Use the recomputed ratio and field list to screen, then check each field's purpose and population
  before assigning the lane. Machine-written or integration content does not count: log payloads,
  stack traces, limits dumps, id lists, and integration or queue buffers. `Integration_Log__c` has
  `Payload__c`, `Stack_Trace__c`, and `Limits_Snapshot__c` as Apex-written logs and does
  not qualify. `Support_Request__c` has `Request_Details__c`, `Steps_Taken__c`, and
  `Additional_Information__c`; `EmailMessage` has `HtmlBody` and `TextBody`. Both qualify when at
  least two named content fields are populated. One auxiliary comments field on an otherwise
  structured table (0.018 above) does not qualify. Use the server ratio with the unverified flag
  if recomputation is unavailable; neither ratio proves field purpose or population. Cite the
  qualifying field names and record volume.
- Deterministic-automation gap: `records.total` high + fewer than two long-form fields carrying the record's main content + `automation.totalDependencies`
  low. Confirm in Stage 3 with
  `get_dependencies` for incoming Flows and Apex classes before asserting: `automation.totalDependencies` counts
  only declarative/config metadata and misses record-triggered Flows + Apex, so an object
  can look under-automated in the scan yet be heavily automated in reality. Only call it a gap once dependencies
  confirm little/no automation logic.
- Well-automated / no clear agent gap: `records.total` high + already many automations (confirmed via
  dependencies) + fewer than two long-form fields carrying the record's main content. The common case for mature standard objects: structured,
  busy, and already governed. Not an agent opportunity on its own; note it and move on (don't force it into
  another bucket).
- Cognitive-overload: `schema.fieldsTotal` high + population skewed to `zero`/`below25` bands (many
  fields barely filled). Agent-assisted data entry, or cleanup. Only assert when `population.dataAvailable`.
- Assistant / deflection: `engagement.views30d` high + few automations on the hot path. Require
  `engagement.available` on the object; the summary flag alone does not establish object coverage.
- Cleanup: `records.total` at/near 0 or stale `lastModified`, regardless of schema.
  Route to `elements-tech-debt`.

## Interpretation checks
- `Web_Lead__c` has one auxiliary `Comments__c` field (recomputed ratio 0.018), so its
  confirmed automation density determines its structured lane.
- `velocity.trend: "falling"` on a high-volume object is itself a story (records being archived/deleted);
  worth a mention, but confirm with `get_object_usage`'s series before asserting a cause.
- If most factors are 0 and only `recordVolume` carries the score, say so plainly; it's a big table, which
  is a weak agent signal on its own.
