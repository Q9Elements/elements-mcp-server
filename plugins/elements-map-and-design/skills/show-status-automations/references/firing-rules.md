# Firing rules: reading when an automation runs

What the `automation-firing-reader` agent records per automation, and how
`status_automations.py report` turns it into a verdict per status box. The
agent judges the narrative once per automation; the script applies the
verdict to every box, so the same automation gets the same reading on every
record type's level.

## Contents

- [Ground rules](#ground-rules)
- [What the narrative can say, and the `fires` value it gives](#what-the-narrative-can-say-and-the-fires-value-it-gives)
- [The verdict per box (the script)](#the-verdict-per-box-the-script)
- [What an automation writes](#what-an-automation-writes)

## Ground rules

- What an automation does and when it fires comes only from
  `explain_metadata_components` (or, when no explanation can be generated, the
  component's own description, flagged as such), plus stored facts: the
  dependency rows and the attributes `list_metadata_by_criteria` reads. Never
  from a component's name, never from general Salesforce knowledge, never from
  definitions (`get_metadata_component` detail full is not used).
- When an explanation does not say something, it is unknown, not "no".
- Evidence quotations come from the narrative's prose values: chain
  `sections` (including nested `whenItRuns`), summary `purpose` and `text`,
  or plain text. `confidenceScore` and `chainRelationGroups` are context,
  not evidence for firing or writes. The checker normalises whitespace
  while preserving the words of each quotation.
- What an automation **writes** (the records it creates, updates or deletes) is
  the one exception to the first rule, because it can be read exactly: from the
  dependency graph's "using" rows and from the automation's own definition
  (`get_metadata_source`), never from its name. The explanation is only a
  fallback when neither exists, and is marked as such.

## What the narrative can say, and the `fires` value it gives

| The narrative says | `fires` | Other keys |
|---|---|---|
| It runs when the record is (or is set to) a value: "when the Stage is Closed Won", "when an Opportunity is moved to Suspended" | `value` | `statuses`: those values |
| It runs only on a change from one named value to another: "when the stage changes from Nurture to Marketing Qualified" | `transition` | `transitions`: `[{"from": "Nurture", "to": "Marketing Qualified"}]` |
| It runs when the record leaves a value, to any value: "when the stage changes from Suspended" | `transition` | `transitions`: `[{"from": "Suspended", "to": null}]` |
| It runs only when the record is created | `create` | `statuses`: the values it is created at, when named |
| It does not say when it runs, or names no value and no condition on the field | `unclear` | `unclearReason` |

A change **to** a value from any value ("when the stage changes to Closed Won")
is `value` at Closed Won: the record is at that value when it runs.

A value named only as an exception ("for any stage except Suspended", "unless
the stage is Closed Lost") goes in `excludedStatuses`, not in `statuses`.

`event` is whether it runs on create, on update or on both, from the narrative.
`timing` is before save or after save. Fast field updates and before-save
flows are `before_save`; actions and related records are `after_save` only
when the narrative says the record is saved first or names after save.

`recordTypes` lists only record types the narrative names as the ones it runs
for. Silence leaves it empty: the report then marks "record type not
verified", because silence does not mean it runs for all.

Validation rules are not steps. `fires` says at which values the rule applies
(`value` with `statuses`), and `condition` says in plain words what must be
true to save the record there ("a closed lost reason is filled in").

## The verdict per box (the script)

Before the narrative is read, the stored attributes rule some automations
out for every box: inactive (or deleted or proposed) ones; flows that are not
record-triggered (a screen flow or an autolaunched flow does not run on the
save); flows triggered on delete. A schedule-triggered flow is not a step of
the save: kept by the rules below, it is listed as scheduled at the status
instead of placed.

For one box at value V, with the level the dependency check found the
automation at (value, field or object):

1. `unclear`, or confidence Low with nothing naming V: **unverified**.
2. The box is split by record type: linked to that record type in the
   dependency graph passes; linked only to other record types drops it;
   `recordTypes` naming only others drops it; with neither, it is kept with the
   flag "record type not verified".
3. A first-status-only type (assignment, auto-response) on a box that is not
   the first status: dropped.
4. V in `excludedStatuses`: dropped.
5. `create`: kept as create on the first status only.
6. `transition`: V is a `from`: kept, with the `to` as its target. V is only a
   `to`: dropped, "arrives from A". Neither: dropped.
7. `value`: placed at the status that triggers it. V in `statuses`: kept.
   `statuses` naming only other values: dropped ("triggered at 'X', not at this
   status"), even with a value-level link, because the link alone does not make
   V the trigger. No status named at all: a value-level link keeps it with a
   flag; a field-level or object-level link drops it as "not tied to this
   status". An automation several statuses trigger is kept on each.
8. `event` create on a box that is not the first status: dropped.

Kept validation rules become the box's conditions, joined with AND. Kept
steps are ordered by Salesforce's order of execution: the save step of the
type (the stored trigger type sets a flow's before or after save, then the
narrative's `timing`), then, among flows of one save step, the stored trigger
order (1-1000 first, then none, then 1001-2000), then by name, which stands
for no real order and is flagged as arbitrary. Steps that run on the save that
leaves V (transitions from V) come after the steps of the save that brings
the record to V, on the same chain.

## What an automation writes

Used for the Object resources of the boxes ([`objects-on-boxes.md`](objects-on-boxes.md), "Objects behind each
status"). "Writes" means the automation creates, updates or deletes records of
the object. The script reads it in this order and never from a name:

1. **The dependency graph's "using" rows** of the automation (`get_dependencies`
   lookingFor `using`). Each row names one object or field the automation uses,
   with a `read` and a `write` flag and, in `relationshipDescription`, the flow
   elements that use it ("- Create Record 'Create Invoice'").
   - An **object row** whose write flag is set, or that names a Create, Update
     or Delete Record element, is written; the elements give the operations
     (create, update, delete). Apex rows say "Insert", "Update", "Upsert" or
     "Delete" instead of naming elements.
   - A **field row** counts as a write of the field's object only with its write
     flag: it also names the element when the field is just read there (a value
     copied into another record).
   - A row with only the read flag is **read**: not added.
   - The row for the Start element alone is the trigger object: not a write.
   - An object row with neither flag that names other elements is **unclear**:
     reported, not added.
2. **The automation's definition** (`get_metadata_source`).
   - A flow or Process Builder: every Create, Update and Delete Records element.
     Its object is the element's own `object`, or what its `inputReference`
     holds: `$Record` (the trigger object), a variable's object type, a Get
     Records element's object, or a called flow's output variable. A related
     record (`$Record.Partner__r`) is left to the graph; when the graph does not
     name that element either, the write is **unresolved**: reported, not added.
   - Apex: every DML statement (`insert`, `update`, `upsert`, `delete`, and the
     `Database.` forms). Its object is the type of `new X(...)` or of the
     variable's declaration, counted only when it is an object the code is known
     to use; otherwise unresolved.
3. **Called automations**: a "using" row of type Flow (a subflow) or Apex Class
   is followed, round after round, and what it writes counts for the caller,
   with "via subflow 'X':" or "via Apex class 'X':" in front of the evidence.
4. **The explanation**, only when an automation has neither rows nor a
   definition: the facts file's optional `writes`, each quoted from the
   narrative, marked "explanation (not checked against the definition)".
