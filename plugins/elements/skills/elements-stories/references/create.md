# Create stories and requirements

Read the schema with `describe_story_schema`, then save items with `create_stories`. Resolve the space as in [generate-from-diagram.md](generate-from-diagram.md) step 1 when needed.

## 1. Describe the schema

Call `describe_story_schema({type, teamId?, delivery: "file"})` with `type` `user_story` or `requirement`, and read the whole answer from the file: an inline answer can be trimmed (`_truncated`), which hides fields such as the custom fields; see [files-and-paging.md](files-and-paging.md). Call it before `create_stories`, `set_story_fields` or a list filter that needs a field key or id; use its keys and option ids as returned. The answer has:

- `fields`: each with:
  - `key`, `label`, `kind` (`standard` or `custom`), `dataType`, `requiredOnCreate`, `operators`, `filterable`, `editable`, `bulkEditable`
  - when present, `default`, `min`, `max`, `minLength`, `maxLength`, `references`, `options` (`optionId`, `label`) and `optionsTotal`
  - Custom field keys are `cf_<id>`; a picklist value is its `optionId`.
  - `readOnlyReason` is one of:
    - `system` (set by Elements, such as `storyId`, `reqId`, `createdDate`)
    - `unsupported_type` (a custom field type the tools cannot write)
    - `no_permission` (the caller lacks the requirements manager role)
- `workflow`:
  - `statuses` (`statusId`, `label`, `category` of `todo`, `in_progress` or `done`)
  - `initialStatuses` (the only statuses a new item takes)
  - `transitions` (`from`, `to`); a status changes only along these.
- `releases` (`releaseId`, `name`, `status`; a release with status `published` takes no new items)
- `assignableUsers` (`userId`, `name`, `email`) and `assignableUsersTotal`.
- When every field reads `editable: false` with `readOnlyReason: "no_permission"`, the user cannot write stories or requirements in this space: tell the user before attempting `create_stories` or `set_story_fields`.
- `configVersion`: changes whenever anything in the answer changes; compare it with a kept copy instead of rereading.

Option lists and `assignableUsers` stop at 200 entries; `optionsTotal` or `assignableUsersTotal` gives the full count. A requirement outside the first 200 `parentRequirementId` options has no id the tools return, so a story cannot be placed under it in that call: report that, and offer to create the story without a parent.

## 2. Show, confirm, then create

Show the user every item to be saved (type, summary, parent, status, release, assignee, custom fields, links) and obtain explicit confirmation. Then call `create_stories({items, draftKey?, teamId?})` with up to 100 items. One call can mix `user_story` and `requirement` items.

Item fields:

| Field | Rule |
|---|---|
| `clientRef` | Required, except on draft items (see below); unique within the call; echoed back |
| `type` | Required: `user_story` or `requirement` |
| `summary` | Required; 2 to 255 characters |
| `description` | Optional; a requirement keeps it as its details |
| `acceptanceCriteria` | Optional; stories only |
| `implementationDetails` | Optional; stories only; 2 to 32,000 characters |
| `risk` | Optional integer 1 to 3, or `null`; stories only |
| `priority`, `businessImpact`, `risks` | Optional integers 0 to 4, default 2; requirements only |
| `reqBy` | Optional date, `YYYY-MM-DD` or an ISO 8601 date-time, or `null`; requirements only; keeps the date as written |
| `solution` | Optional; requirements only; 2 to 32,000 characters |
| `reqReason` | Optional; requirements only; up to 256 characters |
| `parentRequirementId` | The `optionId` of the requirement in the `parentRequirementId` field options of `describe_story_schema` (a 24-character id); stories only; not together with `parentClientRef`; an unknown requirement fails with `not_found` |
| `parentClientRef` | The `clientRef` of a requirement in the same call; stories only. A requirement `clientRef` already used in this space within 24 hours resolves to that earlier requirement, so use a new one for each save |
| `status` | One of the `initialStatuses`; omit for the default |
| `assigneeId` | A `userId` from `assignableUsers` (a member of the space) |
| `releaseId` | A `releaseId` from `releases` whose status is not `published`; a published release is refused with `invalid_field` |
| `customFields` | Object of `cf_<id>` key (or the bare id) to value |
| `linkedNodeIds` | Up to 50 metadata node ids |
| `diagramLinks` | Up to 20 `{mapId, activityMxKey, diagramId?}`; send `diagramId` when the activity key sits on more than one level |
| `externalRef` | `{system, key, url}`: the same item in another tracker, saved as a link attachment |

Create takes only the fields in this table. Set other editable fields, such as `devProject`, `affectedRoles` and `tags`, with `set_story_fields` after the save; see [update.md](update.md).

Custom field values by type. Each field's `maxLength`, `min` and `max` come from its `describe_story_schema` entry. A field with `requiredOnCreate: true` needs a value on every item; omission, `null`, an empty or blank string, or an empty array fails that item with `invalid_field`.

| Field type | Send | Notes |
|---|---|---|
| `text` and `longtext` | a string | up to the field's `maxLength` |
| `number` | a number or numeric string | within `min` and `max` |
| `date` | `YYYY-MM-DD` or an International Organization for Standardization (ISO) 8601 date-time | stored as the calendar date |
| `list` | one option value or `optionId` | |
| `tags` | an array of known tag names | without duplicates |
| | `null` | clears; refused for a required field |

A wrong type or unknown value fails that item with `invalid_field` and `field` `customFields.cf_<id>`. [update.md](update.md) applies the same rules.

To save items of a `run_backlog_draft` result (see elements-decision-engine):

- Pass the chosen entries of its `backlogDraft` unchanged in `items` (their `id` included) (required, as for any call), together with its `draftKey`.
- Each item keeps its `draftId` (`draft-requirement` or `draft-story-<n>`), which sets its `type`.
- The call sets `clientRef` to `draftKey:draftId` unless the item carries its own.
- Only keys the draft has may be changed, plus `customFields`, which a space with required custom fields needs on each item:

  | Item | Keys the draft has |
  |---|---|
  | story | `summary`, `description`, `acceptanceCriteria`, `implementationDetails`, `risk`, `tags` |
  | requirement | `summary`, `details`, `solution`, `priority`, `businessImpact`, `risks`, `tags` |

- `status`, `assigneeId` and `releaseId` are not draft keys.
- A draft story is saved under the draft's requirement, so send the requirement item in the same call, or after it was saved under the same `draftKey`; otherwise the story fails with `invalid_input`.

Example call:

```
create_stories({
  draftKey: "draft-abc123",
  items: [
    {id: "requirement-0", draftId: "draft-requirement", summary: "Automate renewal quotes"},
    {id: "story-1", draftId: "draft-story-1", summary: "Create the renewal quote on close", customFields: {cf_aaaa0000bbbb1111cccc2222: "Sales"}}
  ]
})
```

## 3. Read the result

The answer has one result per item in input order plus `createdCount`, `existingCount` and `failedCount`. An item that fails does not stop the others.

- `created`: `storyId` is a 24-character id, not the item number, and `url` can be `null`. Read the numbers back with `list_stories_by_criteria` (for example `text` on the summary, or `createdFromDate`) before reporting them or linking by number.
- `existing`: the same `clientRef` sent again within 24 hours answers the earlier item and saves nothing. The same `clientRef` with different content answers `existing` with a `warning`; use a new `clientRef` for a new item.
- `failed`: `error {code, message, field?}`; codes include `invalid_field` (missing summary, unknown field, read-only field, wrong custom field value, published release), `invalid_transition` (a status that is not an initial status), `lock_held`, `save_failed` and `deadline_exceeded`.
- `failedLinks`: a link that could not be made does not fail the item; each entry lists `nodeId` and a `reason` (`not_found`, `no_access`, `invalid_input`, `deadline_exceeded` or `save_failed`). Make a missing link later with `manage_story_links` ([link.md](link.md)).

Report per-item results by `clientRef`. After a partial failure:

- Resend only the failed items with their original `clientRef`, within the 24-hour repeat window, and only when the code is `lock_held`, `save_failed` or `deadline_exceeded`; saved items answer `existing`.
- Wait about a minute on `lock_held` or `save_failed`.
- Never resend an item that failed with `invalid_field`, `invalid_transition` or `invalid_input` without correcting it.
- Do not send two calls with the same `clientRef` at once.
- A call with `diagramLinks` can answer `server_busy`; wait the returned `retryAfter` seconds and resend.
