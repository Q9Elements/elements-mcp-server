# How the chain walk works

The plugin's `scripts/trace_chain.py` walks an automation chain through Elements' dependency graph. This page explains what it does and why, so the checkpoint table and the final diagram can be explained to the person.

## Automations chain through data, not through calls

A few automations call each other directly: a flow runs a subflow or an invocable Apex action, a trigger calls its handler class. Most chains are indirect: one automation **saves a record**, and every record-triggered flow, Apex trigger, workflow rule and Process Builder on that object runs; or it **publishes a platform event**, and the event's subscribers run. So the walk goes automation → object or event → automation, and only automations become cards.

The dependency graph says what each element does with what it names. `get_dependencies` gives, for every item, a relation description such as:

```
Referenced 3 time(s):
- Start
- Record Lookup 'Get Related Invoice'
- Update Record 'Update Invoice Record'
```

The plugin's `data/chain-relations.csv` turns each line into a relation:

| Line | Relation | Meaning for the chain |
|---|---|---|
| `Start` | trigger | The automation runs when this object is saved or this event is published |
| `Create Record ...`, `Update Record ...`, `Delete Record ...` | create, update, delete | It saves this object (on an event: it publishes it) |
| `Record Lookup ...` | read | It reads it: recorded, never followed |
| anything else (Decision, Formula, Assignment...) | reference | Read only |
| no line at all | unstated | Apex, and some platform event subscribers: see below |

The canonical row's `write: true` also establishes a write. When it names no
create, update or delete operation, the line says "Changes <object>". An object
name alone establishes a reference; it does not establish a write.

## The walk

1. **The root** (the automation the person picked) is looked up both ways: what it uses (`using`) and what uses it (`where_used`).
2. **Downstream** (what happens next): what the automation calls joins the chain whatever its name. Each object it saves and each event it publishes is looked up (`where_used`), and the automations that start on it join the chain when they are on topic (below).
3. **Upstream** (what leads to it): the automations that call it, and the automations that save the object it starts on (or publish its event), join when they are on topic.
4. Every automation that joins is followed the same way, until the depth limits in the plugin's `data/trace-limits.csv` (`down_depth` 3 and `up_depth` 2 by default; a card at the limit is drawn but not followed, and a gap says so).
5. **Describe:** at the end, every automation found is described in one `get_metadata_component` call per 50 (active or not, trigger type, managed package). An inactive automation in scope becomes a candidate.

## On topic: the keywords

An object like Invoice can start ten automations, of which two are about commission. So automations that join through data must match one of the run's **keywords** in their name, API name or description. The skill writes the keywords from the person's question: the main nouns and their variants ("commission", "commissionable", "payable"). Automations that do not match become **candidates**: listed at the checkpoint, not followed, and recorded as a gap if left out. An automation that is called directly by one in scope needs no keyword: it runs whenever its caller does.

Other limits make candidates too: more than `max_automations` in scope (25), or more than `max_fanout` (8) joining through one object. A managed-package automation on topic is drawn as one card and not followed (its code is not visible); off topic, it is a candidate like any other.

Keywords match descriptions, so a broad automation can come in on one sentence: "Opportunity Closed Won Create Renewal Opportunity" mentions "assigning commission types payable" and joins because a commission flow updates the Opportunity, although its entry conditions would never fire on that update. That is what the checkpoint is for.

## Statuses

| Status | Meaning |
|---|---|
| root | The automation the person picked |
| in-scope | On the chain and followed (or drawn but stopped at a limit, with the reason) |
| candidate | Joins the chain but was not followed: off topic, inactive, or over a limit. The person can include it |
| excluded | The person took it out. The automations that were in the chain only because it called them go back to candidates ("only called by ..., out of the chain"). Each excluded automation and candidate has its own left-out gap with its stored reason |

## Blind spots, recorded as gaps

- **Apex:** a Create, Update or Delete dependency relation, or `write: true`, establishes a write. If that evidence matches a saved inferred link, the link becomes confirmed. A row with `read: true` and no write evidence is read only. An object reference with neither kind of evidence stays inferred, is not followed as a save, and becomes a gap saying whether it writes is unconfirmed. An Apex trigger is inferred to start on the object its name contains; check that trigger at the checkpoint.
- **Platform event subscribers** sometimes have no `Start` line; a flow that names an event without saying what it does is taken to subscribe to it (inferred).
- **Coverage:** retain native failed records and failedFile coverage as gaps, including partially read nodes. Expand only after terminal acquisition.
- **Entry criteria** are not evaluated: an automation that starts on Invoice is on the chain even if its conditions would not be met by the saving automation. Supplement entry conditions with component or source evidence; unavailable identity/condition facts remain explicit gaps.
- **Expired links:** follow expiresInSeconds (1800 seconds for dependency parts, 120 for generic results). Repeat identical requests for fresh links or stop with an explicit download gap.
- **Recursion:** an automation with an established write to the object it runs on can run again. The drawing does not loop it back to itself; a gap says so. Inferred writes, including those in a saved trace being resumed, become uncertainty gaps and cannot produce write lines or recursion gaps.

## From the walk to the chain level

`assemble` keeps the automations in scope that join the root through the chain, and writes the chain level:

- **Cards:** one per automation, with its kind ("Record-triggered flow: after save"), what it starts on, its entry fields, and its description as the footer.
- **Hubs:** an object or event becomes its own card only where at least `hub_writers` (2) automations in scope save it and `hub_triggered` (2) start on it. Otherwise it is folded into the line label: "Updates Invoice/Credit Note", "Publishes Calculate Commission Line Item".
- **Lines:** numbered in reading order from `START`. The chain starts where the root starts ("Invoice/Credit Note saved (Stage__c = Approved or Paid)"). A line out of a hub card says only when it starts ("When Type = Stripe"), since the card names the object; a call reads "Runs it as a subflow". Each automation that leads nowhere further ends with what it leaves behind, what it creates first ("Creates Commission Line Items (+1)").
- **links.json** records what each line is about, so each automation's logic level can say which of its steps causes it.
