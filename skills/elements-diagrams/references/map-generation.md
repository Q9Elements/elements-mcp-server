# Process Map Workflow

Generate a UPN process map from a text description, transcript, or uploaded images, or read an existing map by diagram ID.

## Generating a Process Map

### Inputs

- `name` (required): map name, 2–80 characters
- `guidance` (optional): description, transcript, or generation instructions, max 20,000 characters
- `images` (optional): up to 4 images uploaded via `upload_process_map_image`
- `teamId` (optional): space ID; defaults to active space
- `folderId` (optional): folder within the space
- `theme` (optional): theme ID

### Workflow

1. Call `get_active_space`. Resolve space if needed (see Space Context in SKILL.md).
2. If the user wants to include images, upload each one first with `upload_process_map_image` (see below).
3. Call `generate_process_map` with `name`, and `guidance` and/or `images` as available.
4. Generation is async. Report that generation has started and keep the `diagramId`.
5. Poll with `get_process_map` using the `diagramId` in 30-second increments until `status: "complete"`.
6. When complete, report using the `mapId`, `mapName`, and `diagramId` already captured from `generate_process_map`'s response — `get_process_map`'s `status: "complete"` result does not repeat them (see below).

### Uploading Images

1. Encode the image as base64 if not already encoded.
2. Call `upload_process_map_image` with `imageData` (base64 string) and `contentType` (`image/png`, `image/jpeg`, or `image/gif`).
3. The tool returns `imageKey` and `fileType`; pass these as objects in the `images` array to `generate_process_map`.
4. Upload all images before calling `generate_process_map`. Maximum 4 images per map.

---

## Reading an Existing Process Map

If the user provides a `diagramId` and wants to review or analyse a map:

1. Call `get_active_space`. Resolve space if needed.
2. Call `get_process_map` with the `diagramId`.
3. Interpret and answer using the returned fields (see below).

`get_process_map` returns `status: "running"` (with `diagramId`, `mapId`, and `diagramUrl`) while the map is still generating, or `status: "complete"` with `metadata`, `activities`, `transitions`, `warnings` (plus `lifecycleStates` and `automations`, see below) when ready. The complete response does not repeat `mapId`, `diagramId`, or a diagram URL — carry those over from `generate_process_map`'s response or an earlier `running` poll if you need to report them alongside the result.

---

## Interpreting Results

- `metadata`: map name, description, subtype, state, activity and transition counts
- `activities`: process steps with text, resources, and Salesforce source attachments. Lifecycle state is not on the activity itself — cross-reference `lifecycleStates[].activityIds`.
- `transitions`: directed links between activities with optional labels
- `lifecycleStates`: lifecycle/status values and their associated activity IDs. Present only when the diagram's `subtype` is exactly `upn` (not `customerJourney`, `agentInstruction`, or `whiteboard`).
- `automations`: automation activities: flows, assignment rules, auto-response rules, global actions, and system- or industry-resourced steps. Present only under the same `upn`-subtype condition as `lifecycleStates`.
- `warnings`: serializer caveats (e.g. visual connectors that could not be mapped to activities)

Prefer business-language answers. Mention `mxKey` or internal IDs only when diagnosing diagram structure.

**Process questions:** start from `activities` and `transitions`. Describe the flow in plain language.

**Automation questions:** use `automations`. Include source attachment type and name when present.

**Lifecycle questions:** use `lifecycleStates` to identify status values, then trace related `activities`.

**Completeness questions:** include counts from `metadata` and summarise any `warnings`.
