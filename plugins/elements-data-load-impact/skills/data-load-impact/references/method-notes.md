# Method reference

The deliverable is a ratified pre-load safety package, an optional full-copy-sandbox rehearsal, and
an ordered backlog for the customer's team. Each load-incident class has a named control, an owner
not-applicable ruling, an accepted rehearsal result, or a stated risk when the owner skips rehearsal;
zero incidents is the outcome target. The playbook analyzes and plans but does
not execute the production load or change metadata. It runs the small rehearsal load through the
customer's Salesforce command-line interface (sf CLI) when the owner chooses rehearsal and a
verified sandbox with exact parameter mapping is available. On a chosen manual path, the customer
runs the batch.

## Scope boundary

- The engagement starts from a load manifest. It does not depend on a metadata-change assessment.
- The customer executes every story and owns the production load window.
- The playbook ends when the backlog and final report are generated.
- A no-go ruling ends with a final report and no backlog.
- Card 06 recommends the sandbox rehearsal and records the owner's choice. A skip carries the
  unconfirmed points into the final report as stated risks. Sandbox freshness is outside rehearsal acceptance.
- The customer applies the ratified checklist in the sandbox. The playbook may create and remove its
  own load-user debug level and trace flag there, load the small batch, and capture same-job evidence.
  It never deletes test records; the success file supplies created identifiers for customer cleanup.
- The data-load owner is the sole human decider.

## Design rules

- Raw comma-separated value (CSV) rows, Salesforce Object Query Language (SOQL) results, and debug
  logs remain local. The large language model (LLM) receives only metadata names, aggregates, counts,
  and script completeness status.
- Each `run_data_load_impact` call contains one object and operation. Per-argument caching then
  isolates recomputation when one target changes.
- The server-reported skew threshold is used as returned. The playbook never asks for a threshold and
  never re-flags skew locally.
- Upsert insert share and unresolved relationship columns remain local. The impact report names every
  unresolved column and its generated SOQL, and coverage remains incomplete until resolved.
- Lock analysis is additive. Bundle lock rows and `data/uncatalogued-lock-rows.csv` are both applied.
- Parallel is the default. Group child rows by parent identifier first. Bulk Application Programming
  Interface (API) 1.0 serial mode is used for a named operation, an applicable Group Table row
  (`data/uncatalogued-lock-rows.csv`), or persistent `UNABLE_TO_LOCK_ROW` after regrouping. Bulk API 2.0 has no serial mode.
  Persistent lock errors after serial mode go to the owner as a known risk; a go records the accepted
  count, and a later rehearsal blocks only above that count.
- Card 03 names active duplicate rules on each target object. The customer de-duplicates the
  source; a chosen rehearsal measures `DUPLICATES_DETECTED` rows in the loader error file. Measured
  duplicate counts are reported beside the rule names and do not block rehearsal.
- A bypass ruling uses an existing hook within its evidenced user or org-wide scope. An absent hook leads to deactivation or
  leave-on for the current run; the final report recommends adding hooks for future runs.
- Narration-only automations join the bypass audit after comparison by name or label. The auditor
  verifies activation from metadata before a firing claim. Inactive additions stay recorded as
  not firing, outside load risks; unverified activation stays a named coverage risk. Checklist,
  reports and stories state their origin as named in the order-of-execution explanation and absent
  from the Elements load analysis.
- Email senders are proposed for deactivation or bypass; an owner `leave-on` ruling becomes the
  named risk "<automation> may send email during the load". Assignment rules remain opt-in. Every disabled
  validation rule has a replacement data-quality check.
- At card 05, one question lists every owner-rulable uncontrolled incident class. The owner rules each as applies,
  may apply, or does not apply. A may-apply class is evaluated from the card 06 debug logs. A measured
  queued email or governor limit at or above the published threshold returns to card 05 for a control;
  missing measurement is stated once as `not measurable for <name>` at rehearsal acceptance.
  Unpredicted automation is checked directly by the rehearsal; a skip carries automation outside
  the expected fire chain as a stated risk.
- Success and error files are exported within seven days. Rollback deletes created rows from the
  success file with Recycle Bin recovery. For upsert, updated rows are restored from the pre-load
  export; hard delete is prohibited.
- No card calls a MetaField tool or writes an engagement ruling into Elements.

## Evidence limits

Absence is evidence only when every server branch is complete and no unresolved local residue remains.
A truncated debug log never supports a clean rehearsal. An unknown bypass verdict stays visible in the
safety package and final report.
