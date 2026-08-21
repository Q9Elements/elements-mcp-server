# Reading the scan: scoreFactors & classification

How `scan_agentic_opportunities` scores objects, and how to turn a signal vector into a classification + a
"why" that quotes real numbers. This mirrors the server's scoring config so your judgment is consistent
across runs.

## The score
`score` is a weighted sum of six normalized factors × 100 (so ~0–100, though factors rarely all max out).
Each object carries `scoreFactors`. In `detail:"summary"` (default) each factor is `{factor, contribution}`
(only the non-zero ones, biggest first: the one-line "why"); in `detail:"full"` each is
`{factor, weight, value, contribution, detail}` where `detail` is the human phrase (e.g. `"190058 records"`).

| factor | weight | what it measures | normalization |
|---|---|---|---|
| `unstructuredRatio` | 0.28 | free-text density — Text, Text/Long Text Area, Rich Text Area (HTML), and Encrypted Text fields ÷ classified fields | the ratio itself (0–1) |
| `recordVolume` | 0.24 | how much data there is | log10(records+1) ÷ log10(100 000) |
| `automationGap` | 0.18 | *inverse* **declarative/config** automation density (from `sf.summaryInfoObjects`); see caveat below | 1 − min(1, automations ÷ 20) |
| `recordVelocity` | 0.14 | net record growth over 30d (when snapshots exist) | log10(net+1) ÷ log10(10 000); 0 contribution when `dataAvailable:false` |
| `recency` | 0.10 | how recently records were touched | 0.5^(ageDays ÷ 90) from `lastModified`/`lastCreated` |
| `schemaComplexity` | 0.06 | field count (rich domain / cognitive load) | min(1, fields ÷ 150) |

`contribution = weight × value × 100`. To explain a rank, name the 1–2 biggest contributions and quote their
`detail` (full mode) or the matching signal field (summary mode). Example: *"Contact ranks #3: 183,927
records (recordVolume 24) with 43 of 133 fields free-text (unstructuredRatio 0.32 → 9.0)."*

## Signal fields

Annotated `(full)` where `detail:"full"` is required; everything else is in both modes.
- `records.total`, `records.byRecordType` (full), `records.lastModified` / `lastCreated`
- `schema.unstructured` / `structured` / `unstructuredRatio` / `custom` / `fieldsTotal`
- `automation.totalDependencies` (+ `automation.byType` in full). **Caveat (read before using automationGap):** these counts come from `sf.summaryInfoObjects`, which covers *declarative/config* metadata (CustomFields, ValidationRules, WorkflowRules, ProcessBuilderWorkflows, ApprovalProcesses, DuplicateRules, MatchingRules, RecordTypes, PageLayouts, ListViews, Buttons/Links, SharingRules, …). It does **NOT** include record-triggered **Flows**, **Apex classes/triggers**, or **Global Actions**, so `totalDependencies` undercounts real automation (e.g. an object with 48 Flows can show a low count). `automationGap` is therefore a *declarative-automation-density* signal, not a true "no automation" signal.
- `velocity.net7` / `net30` / `trend` / `dataAvailable` / `basis` — the same flat shape in both
  `summary` and `full`. `net7`/`net30` are net record deltas from daily snapshot subtraction
  (`basis: "netRecordDelta"`), not a created/updated/deleted split, and are `null` when unavailable.
  `mode:"manifest"` skips the velocity aggregation entirely and returns `velocityDataAvailable: null`
  with a `velocityNote` — there, null means unknown, not unavailable; request a page to compute it.
- `population.adoptionGap` / `dataAvailable` (+ full `bands: {zero,below25,below50,below75,above75}`)
- `engagement.views30d` / `available`

## Classification heuristics (apply in Stage 2)
Read the vector, not just the score; the score ranks *interest*, the classification names the *kind* of
opportunity:

- **Conversational agent / AI-workflow**: `unstructuredRatio` high (≳0.25) AND `records.total` meaningful
  (humans are reading & writing prose at volume). The strongest agent story: an agent that reads/writes the
  free text. Cite the unstructured field count + volume.
- **Deterministic-automation gap**: `records.total` high + `unstructuredRatio` low + `automation.totalDependencies`
  low. The work is structured and repetitive but under-automated. **MUST confirm in Stage 3** with
  `get_object_dependency_analysis` / `get_dependencies` before asserting: `automation.totalDependencies` counts
  only *declarative/config* metadata and misses record-triggered Flows + Apex (see caveat above), so an object
  can look under-automated in the scan yet be heavily automated in reality. Only call it a gap once dependencies
  confirm little/no automation logic.
- **Well-automated / no clear agent gap**: `records.total` high + already many automations (confirmed via
  dependencies) + moderate/low `unstructuredRatio`. The common case for mature standard objects: structured,
  busy, and already governed. Not an agent opportunity on its own; note it and move on (don't force it into
  another bucket).
- **Cognitive-overload**: `schema.fieldsTotal` high + population skewed to `zero`/`below25` bands (many
  fields barely filled). Agent-assisted data entry, or cleanup. Only assert when `population.dataAvailable`.
- **Assistant / deflection**: `engagement.views30d` high + few automations on the hot path. Only when
  `engagement.available` on the object (NOT merely `summary.eventLogsAvailable`; see sanity rules).
- **Cleanup (not an agent)**: `records.total` at/near 0 or stale `lastModified`, regardless of schema.
  Route to `elements-tech-debt`.

## Sanity rules
- **Never assert "automation gap" from the scan alone.** `automation.totalDependencies` excludes Flows and Apex;
  a low count is only a *hint*. Confirm with `get_object_dependency_analysis` / `get_dependencies` in Stage 3
  before telling the customer an object is under-automated (a Salesforce architect in the room will know if it
  isn't).
- **`summary.eventLogsAvailable: true` but every object has `engagement.available: false`** means the space is
  *licensed* for Event Monitoring but has no synced event-log data. Treat engagement as unavailable, say so, and
  do not use the assistant/deflection lane; do not promise view/user counts you can't produce.
- A high score with `unstructuredRatio: 0` is a **deterministic-automation** or **cleanup** candidate, not a
  conversational agent; don't oversell it as an AI/chat opportunity.
- `velocity.trend: "falling"` on a high-volume object is itself a story (records being archived/deleted);
  worth a mention, but confirm with `get_object_usage`'s series before asserting a cause.
- If most factors are 0 and only `recordVolume` carries the score, say so plainly; it's a big table, which
  is a weak agent signal on its own.
