# Universal Process Notation (UPN) modelling

How a UPN level (stored/exported subtype `upn`, `customerJourney`, `agentInstruction`, or no subtype set) should read.
Use the [subtype table](diagram-types.md) for read-tool spellings. Follow these rules
when you add to or change a level with `manage_diagram`, and when you draft a map. Stored diagrams often break them:
change only what the user asked for, and suggest a fix for the rest instead of making it.

- **Activity text is a verb and a noun**: "Approve proposal", "Send invoice", not "Approval" or "Invoice". Keep it
  short; the detail goes into a child level, a note or an attachment.
- **Every activity has a resource**: the role or system that does it, from the space library (`resource_not_found`
  follows the [resource issue action](change-one-level.md#issue-actions)). Add one
  when you add an activity, if the user named who does it; otherwise ask. The server
  warns `upn_activity_no_resource` on an activity the change adds, or takes the last resource from, without one.
- **Every line has a label** naming what it carries from one activity to the next: "signed contract", "approved",
  "rejected". The server warns `upn_line_unlabelled` on a line the change adds or changes without one.
- **Every activity is connected**: a line in, a line out, or both. The server warns `upn_activity_orphan` on an
  activity the change adds, or takes the last line from, without one.
- **A decision is an activity** ("Check budget") with one labelled line out per outcome; there is no decision shape.
- **The level has an input and an output**: a line coming in from outside the level (a free start, a terminator or
  an off-page link) and one going out (a free end, a terminator or an off-page link), so the reader sees what starts
  the process and what it produces. The server warns `upn_level_no_input` or `upn_level_no_output` when a change that
  adds an activity or a line leaves the level without one.
- **About 10 activities per level at most.** More than that, propose a child level for a group of steps, and once
  the user agrees, move them with `manage_diagram` ([add child with activities](change-one-level.md#child-levels)). Child levels
  are changed like any other level, by their `diagramId`. The server warns `upn_level_too_many_activities` when a
  change adds an activity to a level that then has more than 10.
- **A child level continues its parent activity**: its lines coming in and going out match the parent activity's
  lines in and out. Follow [child linking](change-one-level.md#child-levels) and its `boundary_unmatched` issue action.

These server checks are warnings: the save goes ahead, and only errors, such as a missing element or an unknown
resource, block it. Verb and noun text and decisions are not checked: they are yours to follow. Mention a stored break
of any rule to the user rather than fixing it unasked.
