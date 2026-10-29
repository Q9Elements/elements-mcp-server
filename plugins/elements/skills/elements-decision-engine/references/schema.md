# Schema workflow

Use for creating or updating Salesforce objects, fields, and record types. Carry reference model
and space context through all calls and use the mission loop in SKILL.md.

1. Call `run_schema_inventory` with `request`, optional `objectApiName`, and optional `missionName`.
   Omit `missionId` for a new request. Resolve ambiguous field or record-type parents from returned
   candidates; retry with the clarified request or object in the same mission. Present
   `requestInterpretation`, `objectScope`, `schemaNodes`, and coverage. The inventory holds at most
   500 rows in ascending node identifier order. Verify named fields using [Targets](targets.md) and
   apply [Shared analysis](shared-analysis.md) for coverage and bounded fresh-mission handling.
2. Call `run_schema_recommendation` with the mission. On `outcome:"needs_selection"`, discuss options
   and rationale, then call again with the user's `selectedOptionId` only and poll for `acceptedOption`.
   Identifier errors follow [Results](results.md). Options carry labels and summaries; the accepted
   option supplies the routing `mode`. Describe a likely path before acceptance as an interpretation.
   For different options, incorporate feedback into a revised request and start a fresh schema inventory
   mission within the shared named-target rule.
3. Route on `acceptedOption.mode`:
   - `reuse` or `extend`: dependency scan, change impact, architecture risk, then backlog.
   - `create_new`: backlog directly. Mark dependency, impact, and risk stages as inapplicable because
     there is no existing target; claim no blast-radius or risk evidence.
   - Missing or unexpected mode: clarify before chaining tools.
   Preserve `acceptedOption.target` with object, field, and node identifiers; the scan consumes it from
   the mission. Accepted field updates default to update-field impact behavior.

Illustrative example: “Change Account's renewal-date field.” The user selects extension of the existing
field. The scan returns `totalItems:0`, `targetsTotalItems:1`, and a `change_target` row for that field.
Continue to impact using the accepted option; route later stages from its mode.
