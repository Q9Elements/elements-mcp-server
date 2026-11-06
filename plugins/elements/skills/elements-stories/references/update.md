# Update story and requirement fields

Use `set_story_fields` to change fields on existing stories or requirements, item by item or one value set across many. Resolve the space as in [generate-from-diagram.md](generate-from-diagram.md) step 1 when needed.

## Steps

1. Call `describe_story_schema` ([create.md](create.md)) for the type: field keys, option ids, `bulkEditable` flags and `workflow.transitions`.
2. Preview: call `set_story_fields` without `confirm`. Nothing is written.
3. Show the user each change (`from`, `to`) and obtain explicit agreement. Edits overwrite text and cannot be undone.
4. Confirm: repeat the call with `confirm: true`, passing each previewed `version` as `ifVersion` on `updates` items; `bulk` confirms without versions.
5. Report per-item results by number.

## Input

- `type`: `user_story` or `requirement`.
- Exactly one of `updates` (up to 100 entries `{storyId, ifVersion?, fields}`) or `bulk` (`{storyIds, fields}`, up to 200 numbers, the same fields on each). For requirements, `storyId` is the requirement number. Each number appears once per call. `fields` names at least one field.
- `fields` maps a field key to a new value; omitted fields stay as they are; `null` clears a field except `status` and required custom fields, which cannot be cleared; `null`, an empty string or a blank string for a required custom field fails that item with `invalid_field`. A date field keeps the date as written. Ids and option ids are strings.
- Custom field values follow the rules in [create.md](create.md) (custom field values by type); `null` clears an optional field. `bulk` refuses fields that are not `bulkEditable`.
- `bulk` accepts only fields with `bulkEditable: true` (for example `status`, `release`, `assignee`, `tags`, `risk`, `priority`; list and tag custom fields).
  - A text, number or date custom field, or a text standard field, is refused with `invalid_input` ("bulk cannot set cf_..."); change it item by item with `updates`.
  - `bulk` carries no version, so it does not detect edits made after the preview.

## Result shapes

- Preview: `applied: false`, `results` each `would_update` (with `changes [{key, from, to}]` and `version`), `unchanged` or `failed`; `counts {wouldUpdate, unchanged, failed}`.
- Confirmed: `applied` is true when at least one item was updated, `results` each `updated`, `unchanged` or `failed`; `counts {updated, unchanged, failed}`. When every previewed item failed, fix the items before confirming; the preview still names `confirm: true` as the next step.
Item errors `error {code, message, field?}`: `field` names the field that caused the error, `status` included.

| Code | Meaning | What to do |
|---|---|---|
| `invalid_field` | naming the field, for a custom field `cf_<id>`, the key as sent | |
| `invalid_transition` | the message lists the allowed statuses | |
| `field_read_only` | for example `createdDate` | |
| `version_conflict` | with `currentVersion` | preview that item again |
| `deadline_exceeded` | not started | retry those items |
| `partial_save` | | read the item before redoing it |

- A number absent from the space fails that item with the message `No <type> <number> in this space.`
- A call-level `invalid_input` (unknown field key, repeated number, both or neither of `updates` and `bulk`) refuses the whole call.
- A published release takes no new items: setting `release` to one fails that item.

After a partial failure, preview and retry only the failed items. Never repeat a confirmed call blindly.
