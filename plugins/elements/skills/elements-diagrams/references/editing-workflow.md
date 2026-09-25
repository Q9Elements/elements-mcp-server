# Diagram Editing Workflow

Export, edit, validate, and import an Elements diagram. Two entry paths depending on whether a local ZIP is available.

---

## Path A: No local ZIP (MCP round-trip)

Use when the user describes a diagram to edit but provides no file.

### A1: Find the diagram

Call `list_diagrams` (optionally with a `query` fragment). Show results, including each diagram's access fields (`myRole`, `canEdit`, `canRelease`, `governanceMode`), and ask the user to confirm which `mapId` to edit. `canEdit: true` predicts whether `import_diagram` will succeed on this diagram; it does not predict `export_diagram` — that needs `myRole: "manage"` specifically (see A2). If the user picks a diagram with `canEdit: false`, tell them they lack edit access before going further.

### A2: Export

`export_diagram` requires `myRole: "manage"` on the diagram (stricter than `canEdit`, which reflects edit-level access) and a Pro-plan space; there is no partial or read-only result on denial — the call throws a permission error and returns nothing. Before calling it, confirm from A1's `list_diagrams` result that `myRole` is `"manage"`; if it's only `"edit"` or `"view"`, tell the user they lack export access to this diagram rather than attempting the call.

Call `export_diagram` with the confirmed `mapId`. The response contains `downloadUrl`, `uploadUrl`, and `s3Key`. **Do not use the `zip` field**; passing a large base64 string through Claude's context will silently truncate.

```bash
WORK_DIR=$(mktemp -d)
curl -fsSL -o "$WORK_DIR/diagram.zip" "<downloadUrl from response>"
unzip -q "$WORK_DIR/diagram.zip" -d "$WORK_DIR"
ls "$WORK_DIR"
```

Note the `mapId` and `s3Key` from the response (needed for the import step). Then continue from **step 2** of Path B.

---

## Path B: Local ZIP provided

### 1: Extract

```bash
WORK_DIR=$(mktemp -d)
unzip -q "<zip-path>" -d "$WORK_DIR"
ls "$WORK_DIR"
```

### 2: Understand the diagram

Read `map.json`, then every level file (`1.json`, `1.1.json`, …).

For each level, summarise:
- Level number, name, subtype
- Activities: mxKey, number, text, whether drilldowns exist
- Flowlines: mxKey, srcId → tgtId, text
- Swimlines: mxKey, text
- Highest mxKey in use across all element types

Announce the structure before making any changes.

### 3: Confirm the plan

State exactly what will change: which files, which elements, before/after values. Wait for user confirmation.

### 4: Edit

Apply changes following the rules in `references/editing-guide.md` (loaded as a supporting reference from SKILL.md).

Re-zip when done:
```bash
cd "$WORK_DIR" && zip -qr modified.zip . --exclude "*.zip"
```

### 5: Validate

```bash
python3 ~/.claude/skills/elements-diagrams/scripts/validate.py "$WORK_DIR/modified.zip"
```

Fix every reported error and re-run until output is `VALIDATION PASSED`.

### 6: Deliver / Import

**If no MCP server is connected** (local ZIP only):
```bash
cp "$WORK_DIR/modified.zip" "<original-dir>/<original-name>-modified.zip"
```
Tell the user the output path and summarise the changes.

**If an Elements MCP server is connected** (Path A or user wants to import):

Ask the user: "The diagram is ready. Do you want to (1) overwrite the existing DRAFT now, or (2) snapshot the current DRAFT to READY ('ready for release') first, then import the edits as a fresh DRAFT?"

- **Option 1 (Overwrite DRAFT):**
  ```bash
  curl -fsSL -T "$WORK_DIR/modified.zip" -H "Content-Type: application/zip" "<uploadUrl from export response>"
  ```
  Then call `import_diagram` with `mapId` and `s3Key`.

- **Option 2 (Snapshot DRAFT → READY first (human step), then import):**
  If the user wants to preserve the current DRAFT as a versioned snapshot before your
  import overwrites it, they must release it **in the Elements UI** (see SKILL.md —
  releasing is not available over MCP). Only suggest this when `canRelease: true` from
  `list_diagrams`; otherwise go straight to Option 1.
  1. Ask the user to open the diagram in Elements and release the DRAFT ("ready for
     release"), including child levels if it has drilldowns.
  2. Once they confirm, upload and import as in Option 1.

Report success and summarise what changed. If the user wants the *imported* result
released as an approved version too, that's the same human step in the Elements UI.

---

## Core Rules

### mxKey uniqueness

mxKeys are **globally unique integers within a single level**, shared across activities, flowlines, swimlines, texts, notes, and images. Valid range: `0` to `1,000,000`.

When adding any element:
1. Find `max(all mxKeys across all element types in this level)`.
2. Assign `max + 1` and increment for each additional new element.

### Drilldown levels

A child level's filename is determined by `parentLevelNumber.activityNumber`:
- Activity with `number: 3` in level `1` → child file is `1.3.json` with `"levelNumber": "1.3"`
- The `drilldowns[].title` field is display-only; the mapping is purely structural.

### One field never to change: `subtype`

Don't modify `subtype` on any level file. The importer validates it against the map type and throws on mismatch. `levelNumber` and `topLevel` are equally critical; the validator catches accidental changes to those.

### Importer allowlist

New elements do not need `_id`, `id`, `createdAt`, or `updatedAt`; the importer generates fresh DB records. Unknown fields are silently ignored. See `references/editing-guide.md` for the full per-element field allowlist.
