# Process Map Workflow

## Contents

- [Generating a process map](#generating-a-process-map)
- [Reading an existing diagram](#reading-an-existing-diagram)
- [Paged discovery](#paged-discovery)
- [Read and create refusals](#read-and-create-refusals)
- [Interpreting a process result](#interpreting-a-get_process_map-result)

Generate a Universal Process Notation (UPN) process map from a text description, transcript, or uploaded images, or read an existing map by diagram identifier (ID). Choose the creation path in [SKILL.md](../SKILL.md#workflow). `list_map_templates` accepts `templateSpaceId`, `category`, `type` and `search`; omission of space uses the first available template space (Public Templates when available). Results expose template `mapId`, `type`, `categories`, `description` and preview image. Copy with `templateMapId` and `templateSpaceId`. A template copy retains levels/content but omits comments, data table records, linked stories, requirements, metadata and links to diagrams outside the map. Apply the Model Context Protocol (MCP) [result handling](../SKILL.md#read-tool-results) before reading fields or paging.

## Generating a Process Map

### Inputs

- `name` (required): map name, 2–80 characters
- `source` (required): `"text"` when generating from guidance, or `"images"` when generating from uploaded images
- `guidance` (required for `source: "text"`; optional for `source: "images"`): description, transcript, or generation instructions, max 20,000 characters
- `images` (required for `source: "images"`): up to 4 images uploaded via `upload_process_map_image`
- `teamId` (optional): space ID; defaults to active space
- `folderId` (optional): folder within the space
- `theme` (optional): theme ID

### Workflow

1. Resolve the target space using [Space and identifiers](../SKILL.md#space-and-identifiers).
2. For generation from source images, upload each one first with `upload_process_map_image` (see below).
3. Call `generate_process_map` with `source: "text"` and nonempty `guidance`, or `source: "images"` and the uploaded `images`, along with `name`.
4. Generation is asynchronous. The response contains `diagrams`, with one `{mapId, mapName, diagramId}` entry per generated map. Report that generation has started and keep each `diagramId`.
5. Poll each returned diagram with `get_process_map`, preserving its `diagramId` and `teamId`. Follow the shared wait/failure rules. Stop at `status: "complete"`, including `empty: true`, and explain an empty result.
6. When complete, report from the retained entry identifiers and the result content below.

```text
- [ ] Resolve space and upload source images if needed
- [ ] Start generation and retain each returned entry
- [ ] Poll each diagram to completion, accounting for failure/empty results
- [ ] Report content with retained map and diagram identifiers
```

For lanes, follow [Adding Swimlanes](editing-guide.md#adding-swimlanes).

### Uploading Images

`upload_process_map_image` supplies an `imageKey` for `generate_process_map` only and accepts no `mapId`. No MCP tool adds a new image to an existing map's canvas; tell the user to add it in the Elements user interface (UI).

1. For a local file, call `upload_process_map_image` with its exact byte size as `contentLength` and `contentType` (`image/png`, `image/jpeg`, or `image/gif`). Maximum 5 megabytes (MB), 5,242,880 bytes, per image.
2. Immediately upload the bytes to the returned `uploadUrl` with a Hypertext Transfer Protocol (HTTP) PUT. Send the matching `Content-Type` and exact `Content-Length`. For an expired/failed upload, request another link and retain its new `imageKey`.
3. If the image is already base64, pass `imageData` and `contentType` instead; this uploads directly. Transfer large base64 bodies outside conversation context to avoid exhausting it.
4. After each upload succeeds, carry its returned `imageKey` and `fileType` into an object in `generate_process_map.images`. These storage keys belong to the selected space; do not construct them or reuse another space's keys. Upload every image before generating.

---

## Reading an Existing Diagram

If the user provides a `diagramId` (or a map and a level) and wants to review or analyse it:

1. Call `get_diagram` with the `diagramId`, or with `mapId` and `levelNumber` or `title`, and request `delivery: "file"` for the full read. If it returns `status: "running"`, follow [the copying branch](../SKILL.md#copying-template-branch). If it returns `candidates`, ask which level the user means. `detail: "summary"` reads titles only. Layout fields are in the [one-level read step](change-one-level.md#six-steps).
2. Keep root `diagramId`, `mapId`, `version`, and `subtype`; content is inside `diagram`. Answer from `diagram.activities` (key, number, text, resources with Responsible, Accountable, Supporting, Consulted and Informed (RASCI) assignments, `drilldown`), `diagram.lines`
   (`from`/`to` is an activity key, a terminator, an `offPage` diagram, `null` for a free input or
   output, or `unknown` for a connection the format does not describe; on a child level, `parentLine` is the parent
   line a boundary line is linked to), `diagram.texts`, `diagram.notes`, and `diagram.boundary` (the parent activity and its lines). Anything listed under
   `diagram.unmodelled` exists on the canvas but is not described; say so rather than ignoring it. On an architecture level a
   card also has `footerText`, `attributes` and a `role` on each resource, and a line `startShape` and `endShape`
   ([architecture.md](architecture.md)). With `include`,
   each activity lists the attachment kinds asked for: `"metadata"` (`apiName` with `refModelId` and `nodeId` for the
   metadata tools; `unresolved` when its org or the item is gone, `restricted` when only reference models the user may not view
   have it), `"stories"` (`storyId`, `summary`, workflow `status`) and `"requirements"` (`reqId`, `summary`, `status`;
   `storyId`, `reqId` and `status` are null when the item is gone), `"links"` (Uniform Resource Locator (URL)
   library entries too) and `"notes"` (plain `text`, `null` when it cannot be read, `textTruncated` past 2,000
   characters); `"attachments"` is metadata, stories, links and notes, `"all"` every attachment kind. Not with `detail: "summary"`.
   `unmodelled` counts only what was not read. An element with
   `hiddenText: true` (an activity, line, resource, attribute, text box, note, attachment, or the level itself for its title or description)
   had text styled out of sight: mention it to the user. A `boundary` with `activity: null` means the parent level or
   its drill-down to this level was not found.

For lifecycle states and automations of an org-to-process map, use `get_process_map` (below).

`get_process_map` returns `status: "complete"` with `metadata`, `activities`, `transitions`, and `warnings` (plus `lifecycleStates` and `automations`, see below) when content exists. An empty terminal result is `status: "complete", empty: true`: it can mean an empty diagram or generation that did not finish. Stop polling and explain it. Empty running and complete replies include `diagramId`, `mapId`, and `diagramUrl`; complete replies with content omit them, so carry identifiers over from `generate_process_map` or an earlier poll.

## Paged discovery

Keep space and filters fixed across offset pages; parse serialized rows before counting. Use returned `nextSkip` (including `_truncated.nextSkip`); otherwise advance returned `skip` by consumed rows. With `_truncated.inFile: true`, consume the complete file page once without recounting its inline prefix. Without a file, count returned rows only. Stop at `hasMore: false`; an empty page with more results or a nonadvancing offset is incomplete. `totalItems` is the query total; array length and `file.rows` describe delivery. On `fileError`, keep the prior page size and returned offsets after consuming all usable evidence. A file covers only its requested page.

| Tool | Rows and pagination | Limits and termination |
|---|---|---|
| `get_space_context` | `authorized`; metadata under `pagination` | Keep inline; `pageSize` defaults to 50, maximum 100; stop at `pagination.hasMore: false` |
| `list_process_maps` | `diagrams`; root `skip`, `hasMore`, `totalItems` | Use `delivery: "file"` and `limit: 100`; `mode: "manifest"` is counts only; stop at `hasMore: false` |
| `list_map_templates` | `items`; root `skip`, `hasMore`, `totalItems`; also `templateSpaces`, `categories` | Use `delivery: "file"` and `limit: 100`; page each chosen `templateSpaceId` until `hasMore: false`; `category` is an array of returned names or identifiers |
| `get_process_map_outline` | `items`; root `skip`, `hasMore`, `totalItems` | Poll copying first, then use `delivery: "file"` and `limit: 200` for each page until `hasMore: false` |
| `search_metadata` | `nodes`; root `skip`, `hasMore`, `totalItems`; `count` is page length | Required `refModelId`, normalized `queries` (below); use `delivery: "file"` and `limit: 200`; stop at `hasMore: false` |
| `list_stories` | `stories`; root `skip`, `hasMore`, `totalItems` | Use `delivery: "file"` and `limit: 100`; optional `diagramId`; `mode: "manifest"` is counts only; stop at `hasMore: false` |
| `list_reference_models` | `referenceModels`, `count`, `activeSpace` | Unpaged; request `delivery: "file"`, consume the actual inline or file result, and select the returned `refModelId` |

`list_process_maps` and `list_stories` default to `format: "json"`, meaning JavaScript Object Notation (JSON). Row formats are newline-delimited JSON (`format: "ndjson"`) and comma-separated values (CSV, `format: "csv"`); both serialize rows in `data`. A CSV header is not a row. A manifest has no rows by design. For example, a synthetic search reply with `skip: 0`, three `nodes`, `count: 3`, `totalItems: 7`, and `hasMore: true` continues at `skip: 3`, unless a returned continuation says otherwise. Seven is the query total, not the number delivered on that page.

Before `search_metadata`, keep 1–20 queries; trim whitespace from each term and retain terms 2–256 characters long. Trim generated variants before deduplicating them; drop or replace any variant outside that range. If no usable term remains, ask the user for a keyword. One invalid term refuses the whole call with `invalid_input`; `details` identifies the `queries.<index>` field, but the refusal is not guaranteed to echo the term. For example, from candidates `" Id "`, `" I "`, and `"Account"`, trim `" Id "` to `"Id"`, drop the one-character `"I"`, then call with `queries: ["Id", "Account"]`.

---

## Read and create refusals

Shared access requirements are in [SKILL.md](../SKILL.md#access). Quote returned messages exactly. The reference-model refusal below preserves the source wording.

| Code/condition | Returned message and next action |
|---|---|
| `feature_not_enabled`, MCP | `Elements MCP is not enabled for this space`; follow any switch hint |
| `feature_not_enabled`, plan eligibility | `Requires a Pro Plus space`; it means the Space needs a Core or Advanced Metadata Management plan |
| `feature_not_enabled`, `licenseFlags.orgToDiagram` | `Requires Org 2 Process add-on`; contact the Elements representative, who can match the message to the plan. |
| `feature_not_enabled`, `elementsGPTEnabled` | `Elements GPT cannot be used in this space (not enabled for it, not on a plan that includes it, or a personal space), so a generated map cannot be created.`; resolve usable generation space |
| `access_denied`, create-space role | `You don't have permission to create maps in this space.`; obtain Editor or Author access |
| `access_denied`, reference model edit | `Requires edit access to org model <refModelId>.`; obtain reference model edit access |
| `not_found`, map | `Map not found or you don't have access to it.`; confirm target/space |
| `not_found`, diagram | `Diagram not found or you don't have access to it.`; confirm target/space |
| `invalid_input`, selectors | Use `diagramId` alone, or `mapId` plus exactly one `levelNumber` or trimmed nonempty `title`; correct arguments and retry |
| `invalid_input`, include with summary | `include can't be combined with summary mode.`; request full detail |

## Interpreting a `get_process_map` Result

- `metadata`: map name, description, subtype, state, activity and transition counts
- `activities`: process steps with text, resources, and Salesforce source attachments. Lifecycle state is not on the activity itself; cross-reference `lifecycleStates[].activityIds`.
- `transitions`: directed links between activities with optional labels
- `lifecycleStates`: lifecycle/status values and their associated activity IDs. Present only when the diagram's `metadata.subtype` is exactly `upn` (other reply subtypes include `customer_journey`, `agent_instruction`, and `whiteboard`).
- `automations`: automation activities: flows, assignment rules, auto-response rules, global actions, and system- or industry-resourced steps. Present only under the same `upn`-subtype condition as `lifecycleStates`.
- `warnings`: serializer warnings (e.g. visual connectors that could not be mapped to activities)

Prefer business-language answers. Mention `mxKey` or internal IDs only when diagnosing diagram structure.

**Process questions:** start from `activities` and `transitions`. Describe the flow in plain language.

**Automation questions:** use `automations`. Include source attachment type and name when present.

**Lifecycle questions:** use `lifecycleStates` to identify status values, then trace related `activities`.

**Completeness questions:** include counts from `metadata` and summarise any `warnings`.
