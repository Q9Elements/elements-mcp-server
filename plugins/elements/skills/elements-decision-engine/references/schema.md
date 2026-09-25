# Schema workflow

Use for creating or updating Salesforce objects, fields, and record types. Carry the reference-model
and space context through every call and apply the execution contract in `SKILL.md`.

1. Call `run_schema_inventory` with `request`, optional `objectApiName`, and optional `missionName`.
   Omit `missionId` for a new request. Resolve ambiguous field or record-type parents from the returned
   candidates and retry with the clarified request or object in the same mission. Present
   `requestInterpretation`, `objectScope`, `schemaNodes`, and coverage. The inventory returns at most 500
   rows in stable ascending node identifier order; a named field may be absent from it. Verify named
   fields with `metadata_search` or `get_metadata_node`. `coverage.reviewedNodes` is an integer count of the
   recommender's shortlist; the response does not identify shortlist members. Check named fields
   against `schemaNodes[]` inventory rows and tell the user that shortlist membership is not returned.
2. Call `run_schema_recommendation` with the mission. On `needs_selection`, discuss the options and
   rationale, then call again with the user's `selectedOptionId` only and poll for `acceptedOption`.
   Options have no accepted `mode`; describe a likely `reuse`, `extend`, or `create_new` path only as a
   reading of each label or summary. The accepted mode determines routing.
   For different options, incorporate the user's feedback into a revised request and start a fresh
   schema inventory mission. This client convention provides revision through the inventory request;
   the recommendation tool exposes generation and selection. If a named field is outside
   the inventory, start at most one fresh inventory mission for the same named targets, unless the field
   sorts after the last returned row. A field beyond that limit cannot be reached by rewording the
   request; tell the user that the inventory limit prevents reaching it instead of starting a fresh
   mission. After the fresh mission, tell the user which named targets remain uncovered and continue
   with covered targets, or stop if none are covered. Without an accepted option covering an unreachable
   field, no backlog can be drafted for it. Offer the field-change recipe's dependency scan and impact
   analysis on that field as the available analysis.
3. Route using `acceptedOption.mode`:
   - `reuse` or `extend`: dependency scan, change impact, architecture risk, then backlog.
   - `create_new`: backlog directly. Present the dependency, impact, and risk stages as not
     applicable because there is no existing target; claim no blast-radius or risk evidence.
   - Missing or unexpected mode: clarify the result before chaining more tools.
   Preserve `acceptedOption.target` with its object, field, and node identifiers. The scan consumes
   this target from the mission. Its `analysisTargets` includes the target itself with
   `inclusionReason:"change_target"`. Accepted field updates default to update-field impact behavior.

Worked example (illustrative counts): "Change Account's renewal-date field." The user selects an
extension to the existing field. A scan returns `totalItems:0`, `targetsTotalItems:1`, and one
`analysisTargets` row for the changed field (`inclusionReason:"change_target"`). Continue to impact
analysis, which seeds from the accepted option, then route later stages from the accepted mode.

If the user chooses an existing field outside the returned options, confirm it with `metadata_search` or
`get_metadata_node`, run a standalone dependency scan and impact analysis on that field, and state that a
delivery draft needs an accepted option. A standalone `no_draft` does not answer the requested work.
