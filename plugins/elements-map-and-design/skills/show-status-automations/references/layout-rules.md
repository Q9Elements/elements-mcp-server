# Layout rules: show-status-automations

How `next` lays out the child level of a status box.

## Layout rules

The layout is in `child_changes` in the script and nowhere else; change it
there when the layout changes.

- One child level per status box with steps, validation rules or a scheduled
  flow, created with `add child` on the box. The level is read first (`get_diagram` include layout) for its
  canvas, version and boundary stubs. The parent read supplies every incoming and
  outgoing line's exact label and key. When a chain is drawn, its incoming lines
  enter the first activity and its outgoing lines leave the last activity, using
  those labels and `parentLine` keys. A scheduled-only child keeps its stubs.
  Automation trigger and outcome text appears in the child notes and internal
  lines. A validation failure ends at an internal terminator.
- **Validation rules are one check box in the chain**, "Check the
  <object> can be saved at 'V'", after the before-save steps and before the
  after-save ones, because Salesforce checks them all together there. It
  carries the library's Validation Rule resource (System; `createResources`
  adds it the first time, and the hand-off names it), a metadata link to
  every rule with the run's selected `refModelId`, and an "About this check" note with the conditions joined with
  AND.
- Every automation metadata link carries the run's selected `refModelId` from `boxes.json`.
- The first child level is dry-run first; every write is all or nothing, so a
  later write with an error changes nothing.
