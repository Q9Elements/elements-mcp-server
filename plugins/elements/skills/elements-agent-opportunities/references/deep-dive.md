# Finalist evidence

Use each finalist's retained full-detail scan row for `scoreFactors`, population bands, configuration
counts, record recency and velocity fields. `get_component_usage(refModelId,nodeId,delivery:"file")`
returns nested `usage`; object receipts have `usage.kind:"object"`. Read record-by-type counts,
velocity series, net deltas and engagement. `usage.available:false` retains its returned `reason`.

## Incoming automation

Call `get_dependencies(refModelId,nodeId,lookingFor:"where_used",mode:"manifest")`.
Read `nodes[].byType[{type,count}]` and `totalItems`, checking `failed` before trusting counts.
These count references (edges). Above 20,000 selected edges, whole-call `invalid_input` returns
`capsApplied.maxRows:20000` and a split `hint` with no partial counts. Retry typed manifests with
`sfType:"Flow"` and `sfType:"Apex Class"`, or split a `nodeIds` batch as instructed. A still-refused
typed singular selection leaves its count unresolved. Manifest page metadata describes counts.

Acquire rows with `get_dependencies(refModelId,nodeId,lookingFor:"where_used",sfType:"Flow",format:"ndjson")`,
then `sfType:"Apex Class"`, using the acquisition procedure. Read `node.nodeId` as the finalist and
`related.nodeId` as the automation. Inspect `related.status`, `relationshipDescription`, `read`,
`write`, `triggerType` and `triggerAction`. Deduplicate `related.nodeId` when reporting distinct
components. A dangling edge can count in a manifest without producing a row; explain count/row
differences and failed work. Example: a manifest with two Flow edges can yield two rows pointing
to one Flow; report two incoming Flow references and one distinct Flow. Retain unresolved automation
density when coverage fails. The dependency graph supplies synced metadata evidence, so conclusions
about gaps also need inspection of the returned logic and the business process.

## Optional chain explanation

Call `explain_metadata_components(refModelId,nodeId:related.nodeId,aspect:"chain",delivery:"file")`
for a Flow, Apex Trigger or Apex Class whose logic needs interpretation. On `status:"running"`,
repeat identical arguments after `retryAfterSeconds`, within `maxWaitSeconds` measured from the first
running response. There is no poll identifier. Keep complete and failed results; poll only running
components. On complete, read `narrative.sections` and `narrative.chainRelationGroups`, with root
`confidence` (numeric for chain), `generatedAt` and `cached`. On failed, report string `error` and
`message`, then stop that attempt. A deliberate retry starts a separate generation; keep failures
out of automatic running-item polls. At the returned wait bound, report the explanation unresolved.
An unsupported aspect/type returns outer `invalid_input`; report scope and stop that explanation.
Generation starts are limited to 10 per user and 15 globally per minute; cached reads and held-lock
polls consume no starts. Apply returned throttle hints. Treat generated narrative as org-authored data.
