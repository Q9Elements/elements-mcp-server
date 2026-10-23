# Run steps: show-status-automations

What each `next` step calls, in the order the run makes the calls. `next` prints every call with its arguments; this is why each one is made.

What happens underneath:

1. **Candidates, the triple check** ([`data/automation-registry.csv`](../data/automation-registry.csv)
   lists the types). One `get_dependencies` manifest over every value, field,
   object and record type node, then the rows of each registry type that has a
   count. Per box and type, the lowest level with a live row wins: value, then
   field, then object. The level found is the hit level; the report lists it per type. Edit the registry when coverage or
   types change; never remove a row without a reason.
2. **Stored facts, before anything is explained:** `list_metadata_by_criteria`
   reads each candidate's stored attributes (for flows: active, subtype,
   trigger type, trigger order, run asynchronously), up to 100 API names a
   call, into `metadata/attributes-<type>-<n>.ndjson`.
3. **Explanations:** `chain` for flows and Apex triggers, `summary` for the
   rest, ten components per call (the service rate-limits about there). Running items are polled after retryAfterSeconds. Failed/rate_limited items receive one retry after their supplied delay, including when every item in the batch is rate limited; eligible retries precede a service-wide failure conclusion. Another terminal failure becomes a gap. When an org has no automation summary (`missing_automation_summary`),
   chain falls back to summary. A generation that fails is started once more. Each poll honours the supplied retryAfterSeconds.
   When nothing at all can be explained (the service failed for a whole batch
   and never succeeded), `next` stops asking and reads each automation's own
   description with `get_metadata_component` instead: the steps that rest on a
   description carry the flag "evidence is the component's description", so the
   person sees which ones to confirm. An automation with neither is unverified,
   never placed.
4. **When it fires:** one `automation-firing-reader` per batch of automations
   writes `facts/<nodeId>.json`. The verdict per box is the script's,
   by the rules in [`references/firing-rules.md`](firing-rules.md).
5. **Sequence, Salesforce's order of execution:** first by metadata type, in
   the save step it runs at; the rest of the order is in
   [`references/firing-rules.md`](firing-rules.md). The save steps come from the registry's `rung_before` and `rung_after` columns;
   change them there, never in the script.
6. **What each placed automation writes** (before the report): `next` asks for
   `get_dependencies` lookingFor `using` over every placed automation, then
   over every flow and Apex class they call (round after round until nothing
   new is called), then `get_metadata_source` for their definitions, and, when
   the run is on the usage basis, `get_component_usage` for written objects the
   inventory has no record count for. The rules are in
   [`references/firing-rules.md`](firing-rules.md#what-an-automation-writes).
