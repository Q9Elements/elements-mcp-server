# ZIP round trip

## Contents

- [Path A: obtain an export](#path-a-obtain-an-export)
- [Path B: edit a local archive](#path-b-edit-a-local-archive)
- [Core rules](#core-rules)
- [Release in Elements](#release-in-elements)

ZIP names the diagram archive format. Use this path for whole-map archive edits, including swimlanes. Follow [SKILL.md](../SKILL.md#read-tool-results) for Model Context Protocol (MCP) result/file handling and [editing-guide.md](editing-guide.md) for stored JavaScript Object Notation (JSON) fields.

## Path A: obtain an export

### A1. Select the map

Call `list_process_maps`, optionally with `query`, following [paged discovery](map-generation.md#paged-discovery). Show `myRole`, `canEdit`, `canExport`, `canRelease`, `governanceMode`; ask which `mapId` to edit. `canEdit: false` means import will be refused. A true value still requires the import space role in the [access table](../SKILL.md#access).

### A2. Export and transfer

Check the matching row's `myRole: "manage"` (the direct map role reflected by `canExport`). Edit access alone does not establish export access. A visible map without manage returns `access_denied`, `Requires manage access to map <mapId>.`; a missing/invisible map uses the [read refusal](map-generation.md#read-and-create-refusals). Import map-edit denial is `Requires edit access to map <mapId>.` Space-role refusals are also in that reference.

Call `export_diagram` with the confirmed map. Retain parsed `mapId`, `downloadUrl`, `uploadUrl`, `s3Key`, `bundleBytes`, `expiresInSeconds`; keep map/key paired. Signed links transfer bytes outside conversation context.

Check `command -v curl unzip zip` before shell transfers. Install missing commands with the runtime's system package manager; Python 3's standard-library `zipfile` can extract/repack when the archive utilities are unavailable. Replace response placeholders below with returned values.

```bash
WORK_DIR=$(mktemp -d)
curl -fsSL -o "$WORK_DIR/diagram.zip" "<downloadUrl from response>"
unzip -q "$WORK_DIR/diagram.zip" -d "$WORK_DIR"
ls "$WORK_DIR"
```

For expired/failed export transfers, call `export_diagram` again for fresh links/key, retaining the edited archive locally. Upload it to the new upload link and import using the matching new key. Continue with Path B step 2 after extraction.

## Path B: edit a local archive

1. **Extract**, if the user supplied a local archive:

   ```bash
   WORK_DIR=$(mktemp -d)
   unzip -q "<zip-path>" -d "$WORK_DIR"
   ls "$WORK_DIR"
   ```

2. **Understand it.** Read `map.json` and every level (`1.json`, `1.1.json`, ...). Preserve [stored subtype spellings](diagram-types.md). Summarise level number/name/subtype, activities (mxKey, number, text, drilldowns), flowlines (mxKey, endpoints, text), swimlines (mxKey, text) and highest element key. Announce this structure before changes.
3. **Confirm the plan.** Write a local plan naming files/elements and before/after values; get user agreement before editing. Compare level filenames with the original export: import behavior for added/omitted levels is in [child-level rules](editing-guide.md#filling-a-drilldown-child-level). Create/remove child levels through the one-level workflow, then export again.
4. **Edit** using the [editing guide](editing-guide.md) and [schema](schema.json). Repack from the extraction directory:

   ```bash
   cd "$WORK_DIR" && zip -qr modified.zip . --exclude "*.zip"
   ```

5. **Validate.** Set `SKILL_DIR` to this installed skill's absolute directory, then run its validator:

   ```bash
   python3 "$SKILL_DIR/scripts/validate.py" "$WORK_DIR/modified.zip"
   ```

   Fix every reported error and re-run until `VALIDATION PASSED`. Exit 0 means valid: proceed to import preview; exit 1 means fix archive errors and re-run; exit 2 means pass one archive path. Every exit message names the next action. This checks local structure, not server permission or every server limit. The import preview does not run the server's per-element draw checks, so `validate.py` must pass before a confirmed import. A confirmed import can still fail with `Diagram draw validation failed` after a clean preview. Copy a new note or text element's full `position` shape from an exported element of the same type. Without script execution, prepare the archive using the manual checks in [SKILL.md](../SKILL.md#workflow), then run the validator in an environment with Python 3 before a confirmed import.
6. **Deliver or import.** For a local-only request with no connected server:

   ```bash
   cp "$WORK_DIR/modified.zip" "<original-dir>/<original-name>-modified.zip"
   ```

   Give the path and changes. To import, obtain an export session for the confirmed destination if needed (Path A2); keep the edited local archive as the upload source. The archive limit is 6 megabytes (MB), 6,291,456 bytes, including signed-link uploads.

   ```bash
   curl -fsSL -T "$WORK_DIR/modified.zip" -H "Content-Type: application/zip" "<uploadUrl from export response>"
   ```

   Call `import_diagram` with returned `mapId`, `s3Key` and fixed `teamId`, without `confirm`. The preview has `applied: false` and `preview`: show replaced/skipped levels and counts, then ask whether to apply. On agreement, repeat with `confirm: true`. Keep the uploaded object unchanged between preview and confirmation; changed bytes require upload and preview again.

   Report success only from `success: true`, naming `processedLevels` and `skippedLevels`. `import_failed_partially_applied` means some levels changed: report them, reread affected levels, fix the archive and preview before another confirmed import. Other failures do not establish success.

   On `Diagram draw validation failed`, re-read the affected diagram with `get_diagram`: the server rolls back the failing level, while earlier processed levels can remain changed. Fix the archive's element positions using the per-type [schema](schema.json), run `validate.py` until it passes, then upload and preview again before a confirmed import.

```text
- [ ] Confirm destination and access; obtain/export or extract archive
- [ ] Read every level and write the change plan
- [ ] Confirm plan and edit; preserve structural fields
- [ ] Compare level inventory with original; validate until passed
- [ ] Upload, show import preview and obtain replacement confirmation
- [ ] Apply unchanged upload and report processed/skipped/partial outcome
```

## Core rules

### mxKey uniqueness

Canvas mxKeys are integers, globally unique within one level across activities, flowlines, swimlines, texts, notes and images; valid range is 0–1,000,000. For each new element, find the maximum across all types, assign maximum + 1 and increment. Attribute keys use the card-local rules in [architecture.md](architecture.md#changes).

### Drilldown levels

Child filenames follow `parentLevelNumber.activityNumber`: activity number 3 on level 1 owns `1.3.json` with `levelNumber: "1.3"`. The drilldown title is display-only. Preserve the activity number to keep this structural relationship.

### Structural fields

Preserve each level's `subtype`: the importer validates it against map type and throws on mismatch. Preserve `levelNumber` and `topLevel`; the validator checks filename/number agreement and requires only `1.json` to be top-level.

New elements need no `_id`, `id`, `createdAt` or `updatedAt`: import creates database records. The [importer allowlist](editing-guide.md#importer-allowlist) names accepted element fields; nested position objects reject unknown fields according to the per-type schema.

### Canvas images

Keep exported images and their stored references unchanged. The MCP import reads `map.json` and level JSON files; it does not upload image files from the ZIP. No MCP tool adds a new image to an existing map's canvas. Tell the user to add it in the Elements user interface (UI). `upload_process_map_image` accepts no `mapId` and supplies an `imageKey` for `generate_process_map` only.

## Release in Elements

Import writes the DRAFT. Releasing to an approved READY version requires a person and production password re-confirmation in the Elements UI. If a versioned snapshot is requested, suggest release only when `list_process_maps.canRelease: true`: release before import to preserve the current draft, or after import to approve the result.
