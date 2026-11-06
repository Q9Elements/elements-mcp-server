# Link stories and requirements to metadata

Use `manage_story_links` to link existing stories and requirements to Salesforce metadata components (nodes), and `remove_story_links` to remove those links. Resolve the space as in [generate-from-diagram.md](generate-from-diagram.md) step 1 when needed.

## Identify items and nodes

`links` is a list of `{storyId, type?, nodeIds}` with at most 1000 story-node pairs per call, counted as sent.

- `storyId` is the 24-character id `create_stories` returns, or the item number from `list_stories_by_criteria` (`storyId`, or `reqId` with `type: "requirement"`). A number without `type` is a story number: story and requirement numbers both start at 1, so a requirement number sent without `type: "requirement"` names the story with that number.
- `nodeIds` come from `search_metadata` (see elements-metadata) or `list_metadata_by_criteria` (see elements-metadata-query), in the reference model the user means; a space can hold several, and `list_reference_models` lists them.
- Attaching a story to a diagram activity is done with elements-diagrams (`manage_diagram` story attachments).
- `targetKind` accepts only `metadata_node`, the default.

## Add links

Show the user the story-node pairs and obtain explicit confirmation, then call `manage_story_links({action: "add", links})`.

- The tool only adds links.
- The answer has one row per pair in input order, `pairs [{storyId, nodeId, status}]` and `counts {added, already_linked, failed}`.
- A failed row carries `error {code, message}` with code:
  - `not_found` (unknown node, or an org model not visible to the caller)
  - `no_access`
  - `invalid_input`
  - `deadline_exceeded`
  - `save_failed`
- A failed pair does not stop the others, and a pair sent twice is linked once.

## Remove links

`remove_story_links({links, confirm?})` previews first: without `confirm` nothing is removed.

1. Preview. Each pair answers:
   - `would_remove` with `loses` (the link note, outcome, status and groups, which adding the link again does not bring back)
   - `not_linked` (no such link, not an error)
   - `failed`

   The answer has `applied: false`, `pairs`, `counts {would_remove, not_linked, failed}` and a `next` instruction.
2. Show the preview to the user, including what each removal loses.
3. Repeat the same call with `confirm: true` only after the user agrees. The confirmed answer has `applied: true` and `counts {removed, not_linked, failed}`.

A failed removal row carries `error {code, message}` with code `not_found`, `no_access`, `invalid_input`, `deadline_exceeded` or `save_failed`.

Report per-pair results by story number and node id. After a partial failure:

- Resend only the pairs whose code is retryable, `deadline_exceeded` or `save_failed`.
- For removals, preview the resent pairs again before confirming.
- Never resend a pair that failed with `not_found`, `no_access` or `invalid_input`.

To link at creation time, use `linkedNodeIds` or `diagramLinks` in `create_stories` ([create.md](create.md)).
