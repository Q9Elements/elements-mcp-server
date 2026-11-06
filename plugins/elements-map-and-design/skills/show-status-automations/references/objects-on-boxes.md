# Objects on boxes: show-status-automations

Which Object resources and notes `next` gives the status boxes, the automation boxes and the record-type boxes, after every child level is drawn.

## Objects behind each status

- **A status box with automations** shows the lifecycle object (the Opportunity)
  plus the objects its automations **write**: create, update or delete. These
  replace its data-model objects. Objects the automations only read (look up)
  are not added.
- **A status box without automations** keeps its data-model objects: nothing
  changes there.
- **Each automation box** on the child level shows, after its Flow (or System)
  resource, the objects that automation writes.
- **Each record-type box** on the split level (the level above the lifecycles)
  shows the lifecycle object plus the objects written most often across its
  statuses: the number of its status boxes whose automations write each.
  `boxes.json` `objectsRollup` sets it: `written` (the default), `level` (rank by how many of its status boxes show each object after
  this change, data-model objects of the boxes without automations included)
  or `off`.

**What counts as written by an automation.** What it writes itself, plus what
the subflows and Apex classes it calls write (a subflow of a subflow too), shown
as "via subflow 'Create Invoice'". Every automation on the box's child level
counts, including the save that moves the record on from the status.

**At most seven resources a box.** No box carries more than 7
resources, people included: `max_resources_on_box` in the plugin's
`data/style-process.csv`, the one value every skill that draws boxes reads.
Nothing is lost: every written object stays listed in the box's note, which adds
one line naming those not shown as resources ("Not shown as resources (a box
carries at most 7): ..."). The record-type roll-up on the split level is a
summary and keeps five a box.

**One note a box.**
- **Status box:** its "About this step" note (written by map-process-from-data-model)
  keeps What happens, Why and Stage value word for word; only its "Objects used"
  part is rewritten. A box with no
  "About this step" note gets one holding just this part.
- **Record-type box:** its note "Objects written by automations in this
  lifecycle" (the only box that keeps a separate note, since its "About this
  step" describes the record type, not one status). The note lists objects beyond
  the lifecycle object. When that list is empty, the box carries no roll-up note.

**Overlaps.** A box grows 24 px for each resource and never shrinks when
resources are removed, so a status box can grow into the box below it. The server reports it (`overlap`), `next`
lists those in its `done` action, and the skill moves nothing: the person moves the box in the editor.

**Objects with no records.** When the run is on the usage basis (the run's
`scope.json` `metadata.basis` is `usage`, or `onlyWithRecords` is true), an
object an automation writes but the org holds no records of is still shown, and
the note flags it: "Invoice/Credit Note: created by <automation>, but the org
holds no Invoice/Credit Note records, so this automation may never run in
practice". On the configuration basis nothing is flagged. A record count that is
missing or unavailable is never read as zero.

**Library names.** Missing Object resources are added to the space library
(`createResources`). Before the first write the skill checks every new
name with a dry run: a name the library already holds as a person or system
(a Human called "Customer", the label of the object `Customer_Account__c`)
would draw that person, so the object is drawn under the name the drawing gives
it (`object_rename` in the plugin's `scripts/layout_engine/write_loop.py`): its
API name when that differs and the library does not hold it as another type
too, else "<label> (object)", else "<label> (object, <API name>)". Each such
name gets the same dry run. The note says "Customer (shown as
Customer_Account__c)", or "Contact (shown as Contact (object))" for the object
`Contact`, whose API name is its label. A level that already shows the object
under one of these names keeps it; an object whose every name the library holds
as another type is named only in the note.

**When it runs.** After every child level is drawn, `next` reads each level
afresh (status levels, child levels, the split level), changes only Object
resources and the notes named above, and records what it gave each level in
`draw/objects-<diagramId>.json`, so a rerun changes nothing unless the report
changed.

The script shortens object descriptions to names when a complete note approaches 2000 characters, retaining every written object and the Not shown as resources line. What happens, Why and Stage value remain verbatim. If the complete names and protected text still exceed 2000 characters, it stops with the box key and asks for agreed shorter names or prose before writing.
