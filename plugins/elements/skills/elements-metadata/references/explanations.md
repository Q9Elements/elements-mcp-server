# Reading explanations

A singular response has `{_untrusted,nodeId,aspect,status,narrative,confidence,generatedAt,cached}`. On completion, hydrate and read the full `narrative` using the entrypoint's reading resource. Running and failed responses have `narrative:null`, `confidence:null`, `generatedAt:null`, `cached:false`.

| Aspect | Narrative fields | Root confidence |
|---|---|---|
| `chain` | `sections` with `purpose`, `whenItRuns`, `whatItTouchesOrInvokes`, `largerProcess`, `whyItsRisky`, `confidenceScore`; plus `chainRelationGroups` | `sections.confidenceScore.score` or null |
| `summary` | `purpose`, `text` when present | Stored confidence normalized to `High`, `Medium`, `Low`, or null |
| `purpose` | `workToDate`, `whyBuilt`, `whereItFits`, `driftNotes` when present, or no-evidence `text` | Supplied confidence, default `Low` |
| `data_lineage` / `order_of_execution` | The aspect's payload | null |

`generatedAt` is at the response root. `cached` is true when that timestamp precedes call start. With no linked story or requirement as evidence, purpose completes without generation, with `confidence:"Low"`, `generatedAt:null`, `cached:false`. Its exact narrative is:

> No tickets are associated with this metadata, so there is no record of the historical context and intent behind it. You can start associating tickets now to build that history going forward. It makes impact assessment and agentic org analysis done with Elements richer for your agents.

## Limits and failures

Generation starts are limited to 10 per user and 15 globally in a one-minute window. Cached reads and polls under held locks consume no additional start. An outer `rate_limited` refusal supplies `retryAfter`; use the entrypoint's refusal handling before a later attempt.

A node type unsupported by the selected aspect returns outer `invalid_input`; report its message and `allowedValues`. A missing node or one outside the reference model is a refusal. `missing_automation_summary` means automation relationships have not been processed. It can appear as a failed-generation string `error` or an outer pre-generation refusal. Report its state/message; waiting alone schedules no processing batch.

For a flow explanation, search a keyword from its actual name with `sfType:"Flow"`. For a field, search with `sfType:"Field"` and choose the aspect for the question. A parsed node identifier from an available `get_org_health_detail` result or dependency `related.nodeId` is also usable after checking reference model membership.
