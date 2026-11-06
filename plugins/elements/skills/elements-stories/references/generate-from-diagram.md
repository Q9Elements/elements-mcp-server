# Generate stories from a diagram

Generate draft user stories from the activities of a process map's top-level diagram with `generate_stories_from_diagram`. Resolve the space first (step 1), then follow the steps in order. Read [access and refusals](access-and-refusals.md) when a call is refused; read [Files and paging](files-and-paging.md) before any paged read.

For **generation**, follow these numbered steps:

1. **Resolve space when needed.** On `active_space_required` or a user-named space, call `get_space_context`. Read `active`; page through `authorized` using returned pagination if a choice is needed. Resolve the intended authorized space with the user, announce the selection, and call `set_active_space({teamId})`. Carry that `teamId` through subsequent calls. If the user questions the resolved data space, call `list_reference_models({teamId, delivery: "file"})` and inspect `activeSpace`.
2. **Find the map.** Call `list_process_maps` with a case-insensitive name-fragment `query`, `delivery: "file"`, and `limit: 100`; page through matches. On a name collision, show each `mapId` and `folderId` and ask which to use. Carry its `mapId` and top-level `diagramId` from the response.
3. **Read the activities.** Call `get_diagram({diagramId, teamId, include: ["stories"], delivery: "file"})` with the top-level identifier and default full detail. Generation targets only the map's top-level draft; stop for child-level requests or a missing top-level identifier and explain the prerequisite.
   A reply with `status: "running"` means copying: preserve its `mapId`, optional `diagramId`, and verbatim `message`; wait for content.
   Poll `get_process_map_outline` for that same `mapId` and space until `complete`, then resume the diagram read.
   A `not_found` after `running` means the copy failed: report it and stop before generation.
4. **Get an explicit selection.** Show `diagram.activities` keys and descriptions. Each activity's `key` is its numeric `mxKey`; obtain the user's selection before writing. Send those keys as `activityMxKeys`; omitting them selects every top-level activity.
5. **Check existing stories and record the baseline.** Call `list_stories_by_criteria({type: "user_story", diagramId, teamId, delivery: "file", limit: 100})`; read every page using [Files and paging](files-and-paging.md), saving `totalItems` and existing row identifiers. Match rows by `storyId` to each selected activity's `attachments` with `type: "story"` from step 3; count distinct stories per activity. If the sweep or matching is incomplete, report the gap and stop before generation. If any selected activity has stories, show its key, description, story count and story summaries; ask whether to generate more for those activities, skip them, or stop. Wait for the answer and retain only confirmed activities in `activityMxKeys`; stop if none remain.
6. **Queue generation.** Call `generate_stories_from_diagram` with string `mapId`, the confirmed nonempty numeric `activityMxKeys` array, and the intended `teamId`. Optional `requirementId` links generated stories to a parent requirement. Omit `delivery`: the response is a job receipt. Handle these branches:
   - `required_story_fields`: a pre-queue refusal. Show the returned message naming required field titles and its hint: `Generate the stories from the diagram editor in Elements, or ask a space admin to make these fields optional.` Stop; no job exists.
   - `status: "complete"`, `outcome: "nothing_queued"`: report no eligible stories and stop.
   - `status: "running"`: retain the queued `total` and returned `diagramId` for polling.
7. **Poll.** Call `list_stories_by_criteria` with `type: "user_story"`, the returned `diagramId`, same space and filters, `delivery: "file"`, and `limit: 100`. Read `generation.status`, `total`, `completed`, and `failed` when present. Calculate new stories as current `totalItems` minus baseline; `items.length` counts only this page. Check new row identifiers against the baseline across the complete result.
8. **Judge and report.** Apply Judge outcomes below, then show counters, new stories and any unresolved evidence. Report counts per job; story rows do not name their source activity.

```text
- [ ] Resolve the intended space if needed
- [ ] Select the map and read its top-level activities after copying completes
- [ ] Show activities and obtain explicit selection
- [ ] Save baseline counts and row identifiers
- [ ] Match existing stories to selected activities; if any exist, obtain a generate-more, skip or stop decision and retain only confirmed activities
- [ ] Queue generation and handle its receipt or refusal
- [ ] Poll, reconcile new rows, and report the outcome
```

## Generation rules

Each eligible activity generates one story per human resource, or, when it has no human resource, one per system resource. Activities need both incoming and outgoing flowlines and at least one resource. Ineligible activities are excluded from the queued total, which can differ from the number selected. Stories contain a headline, description and acceptance criteria.

## Judge outcomes

`running` is nonterminal; `complete` and `failed` are terminal. Apply delivery evidence before a status label:

- **Delivered:** terminal status, `completed == total`, `failed == 0`, and verified new rows equal `completed`. A `failed` status with these counts is a server status anomaly; report delivery and preserve the returned error as the anomaly.
- **Partly failed:** terminal with `failed > 0` and some new rows. Report successful rows and failed counts.
- **Pending:** `running`, or absent `generation` before any terminal observation. Continue within a bounded polling window; if it ends, report the unresolved evidence.
- **Failed:** terminal failure evidence, such as failed items or a returned error, with no new rows. Preserve that evidence.
- **Unsettled:** after a terminal observation, report `total - completed - failed` when positive, plus any counter/row mismatch. Stop polling terminal jobs.

Generation status can expire or be unavailable. When `generation` is absent after a terminal observation or the polling bound, compare verified new rows with queued `total`: full coverage establishes delivery with counters unavailable; otherwise report observed rows and uncertainty.

### Synthetic count example

Fabricated input: baseline `totalItems: 12`, queued `total: 3`. Output: terminal `completed: 3`, `failed: 0`, `totalItems: 15`, with three verified new rows. `15 - 12 = 3`: Delivered. The same evidence with `status: "failed"` is Delivered with a server status anomaly.
