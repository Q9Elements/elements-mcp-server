# Find and review stories and requirements

Use `list_stories_by_criteria` to read user stories or requirements, count them, or check generation status. Read [access and refusals](access-and-refusals.md) on any refusal and [Files and paging](files-and-paging.md) before a paged sweep. Resolve the space as in [generate-from-diagram.md](generate-from-diagram.md) step 1 when needed.

## Call

`type` is required: `user_story` or `requirement`. Every other filter narrows the result; filters combine with AND. Call `describe_story_schema` ([create.md](create.md)) first when a filter needs a field key, option id, status id, user id, release id or operator; never guess them.

| Input | Meaning |
|---|---|
| `storyIds` | Item numbers, up to 200: `storyId` for stories, `reqId` for requirements |
| `text` | Case-insensitive text in the summary, description or acceptance criteria (requirements: summary, details or solution) |
| `parentRequirementId` | Stories under this requirement: its `optionId` from the `parentRequirementId` field options in `describe_story_schema` (a 24-character id); stories only, otherwise `invalid_input` |
| `diagramId` | Items linked to this diagram |
| `nodeIds` | Items linked to any of these metadata node ids, up to 100 per call |
| `externalKeys` | Jira or Azure DevOps keys of synced items |
| `statuses`, `assigneeIds`, `releaseIds` | Id lists, up to 200, from the schema |
| `createdFromDate`, `createdToDate`, `updatedFromDate`, `updatedToDate` | dates in International Organization for Standardization (ISO) 8601 format in Coordinated Universal Time (UTC); a date without a time covers that whole day |
| `filters` | Up to 20 conditions `{field, operator, value, secondValue?}` on any field, custom fields included; operator `range` needs `secondValue`; picklist values are `optionId`; empty or blank `eq` finds absent, null or empty values, and `neq` finds values present, for every field type; `contains`, `startswith` and `doesnotcontain` require text, otherwise `invalid_input` points to `eq ""` and `neq ""` |
| `sortBy` | `updatedDate` (default) and `createdDate` sort newest first; `summary` sorts A to Z |
| `limit`, `skip` | Page size (default 50, maximum 200) and rows to skip |
| `detail` | `summary` (default) or `full`, which adds text, custom fields and links |
| `mode` | `page` (default) or `manifest` |
| `format` | `json` (default), `ndjson` or `csv`; the last two return the page as text in `data` |

`updatedDate` is the last recorded change (creation, a status change or a risk change); an edit of the text alone does not move it.

## Result shapes

- **Page:**
  - Page keys: `totalItems`, `pageSize`, `numPages`, `page`, `skip`, `hasMore`, `items`.
  - Row keys: the number (`storyId` for stories, `reqId` for requirements), `type`, `summary`, `status {statusId, label}`, `assignee {userId, name}`, `release {releaseId, name}`, `externalRef`, `createdDate`, `updatedDate`, `url`, `linkCounts {nodes, diagrams}`, and for stories `parentRequirementId` (the parent requirement's id, or null).
  - `detail: "full"` adds:
    - `description` and `acceptanceCriteria` (requirements: `details` and `solution`)
    - `customFields` keyed by `cf_<id>`
    - `links` (`nodes` entries `{nodeId, apiName, type}`, and `diagrams`)
  - A read-back `nodeId` can belong to another reference model of the space for the same Salesforce item, so match links by `apiName` and `type`; the `nodeIds` filter and the link tools accept the ids from the metadata tools.
- **Manifest:** `totalItems`, `pageSize`, `numPages`, `byStatus`, `byRelease`, `byAssignee`, each a list of `{<id>, label or name, count}`; unassigned and unreleased items group under a null id. Run a manifest before a large sweep to size it.
- **Generation status:** with `type: "user_story"` and `diagramId`, the answer carries `generation {status, total, completed, failed}`; `status` is `running`, `complete` or `failed`. [generate-from-diagram.md](generate-from-diagram.md) polls it.
- The list output does not return requirement scores (`priority`, `businessImpact`, `risks`) or story `risk`. Verify a score with an `eq` filter on that field.

## Review

For **review**, resolve space as in step 1 of [generate-from-diagram.md](generate-from-diagram.md) when needed, then call `list_stories_by_criteria` with `type: "user_story"`, `delivery: "file"`, `limit: 100`, and optional `diagramId`. Read all pages using [Files and paging](files-and-paging.md); show the returned stories and counts. For requirements, use `type: "requirement"`.

To answer "what is in release 3", "which stories touch the Account object" or "what is still open under this requirement", combine `releaseIds`, `nodeIds` (from `search_metadata` or `list_metadata_by_criteria`) or `parentRequirementId` with `statuses`.
