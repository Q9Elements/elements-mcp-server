# Drawing protocol

What every drawing skill in this plugin does the same way. Each drawing skill's `SKILL.md` says which script it runs (`<script>` below: `scripts/layout_process.py`, `layout_data_model.py`, `layout_interaction.py`, `layout_capability.py` or `layout_architecture.py`), its plan options, the steps, actions and errors only it has, and what its drawing cannot do. Everything else is here.

`<plugin>` is the plugin's folder. Run scripts with `python3`, giving full paths.

Copy this checklist and tick it as the run goes:

```text
- [ ] 1. Work folder, validate, space
- [ ] 2. Plan; tell the user what will be drawn, each WARN and each GAP
- [ ] 3. Write loop: next, do, save, until done (section 4 for errors)
- [ ] 5. check, then the diagram-reviewer agent; save DIR/review.json
- [ ] 6. Report
```

## 1. Before planning

1. **Work folder.** One per run: the folder the calling skill names (map-process-from-data-model passes its `drawing.dir`); otherwise named as the drawing skill says, next to the model when there is one, otherwise in the working directory. Everything the run writes goes there. A new run gets a new folder. Within a run, planning again into the same folder is allowed until something is written to the map: the new plan reuses the map already created and runs the preflight again, so a fix made after the preflight leaves no empty map behind. Once a batch is written, the folder takes only the same plan (a resume), and a different plan needs a new folder. The data model and capability scripts refuse any folder that already holds a map.
2. **Validate**: `python3 <plugin>/scripts/validate.py MODEL --for <type>`.
   - Exit 1: stop and show the errors; the model goes back to whoever wrote it (a reader skill, the front door's generic route, or you, for an amendment).
   - Exit 2: a setup problem (a `SETUP` line); show it and stop.
   - Exit 0 with warnings: tell the user each warning in plain words and carry on.
   The plan step runs the same check and refuses a failing model (`REFUSED`), so a model that skipped this step still cannot be drawn.
3. **Space.** When more than one Elements server is connected, use the one for the environment the user named, and ask when they named none. Acquire all get_space_context pages, resolve the chosen space and reference model, and tell the user which space the map uses. Save `DIR/connection.json` as `{"server":"<selected-server>","teamId":"<selected-space>","refModelId":"<selected-reference-model>"}` when a reference model is selected; otherwise save server and teamId; every emitted eligible call then carries that teamId and names the same server. Copy this file into each drawing hand-off and validate it on resume. For a saved run without this file, explicitly call set_active_space for the selected space and verify get_space_context before resuming exact calls.

Metadata links carry `metadataType` whenever the source supplies the type, and the selected reference model as `refModelId`. Reader skills put these fields in the model; retain them through every drawing hand-off. At planning, every drawer fills a missing `refModelId` from the nearest run context, starting at the drawing folder, then the model's folder: `connection.json` `refModelId`, `execution-state.json` `slots.ref_model_id`, `scope.json` `metadata.refModelId`, or `trace.json` `refModelId`. Explicit attachment identifiers stay as supplied. A saved model without the field stays valid; planning fills the loaded copy. For a standalone model, record the selected reference model in the drawing's `connection.json`.

## 2. Plan, then tell the user

Run `<script> plan` (or `amend`) as the drawing skill says. An `ERROR` line names what is wrong and how to fix it, such as planning into a new folder. Read the summary and, before writing anything, tell the user in plain words:

- what will be drawn (the drawing skill lists what to mention);
- each `WARN` line: what it will look like and what would avoid it; let them choose to go on or change the model;
- each `GAP` line: what the model could not establish. Gaps are never drawn.

Offer `DIR/preview.svg` when the script writes one. `NOTHING TO CHANGE` (amendments) means the map already matches the model: tell the user and stop.

## 3. The write loop

Repeat: run `<script> next DIR`, do the one thing its JSON says, save what its `save` field says at `saveTo`, and run `next` again. Pass `arguments` to the tool exactly as given; never retype, reorder or edit the changes, `plan.json` or a saved result: `next` builds each later step from them, so an edit breaks the steps after it.

The common actions follow. The drawing skill lists the further actions its script uses, and any it uses in place of these:

| `action` | Do |
|---|---|
| `create-map` | Call `create_map` with `arguments`. |
| `read-level` | Call `get_diagram` with `arguments`: a child level that `add child` has just created, or the level after a batch. |
| `write-batch` | Send `manage_diagram` with `arguments` and `"dryRun": true`. If its `issues` hold no error, send it again without `dryRun`, and save from that real call. |
| `review-reads` | For each entry in `reads`, call `get_diagram` with its diagramId, selected teamId, include and `delivery: "file"` from the entry, and save the whole result at the entry's `saveTo`. |
| `review-read` | One level: call `get_diagram` with `arguments` and save the whole result at `saveTo`. |
| `copy-running` | Poll the returned map's outline to complete and read the current level before repeating the write. |
| `reconcile-write` | Read the level and outline; reconcile side effects and genuine ref associations before replay. |
| `stop` | Show `reason` and follow `how`. An unscoped metadata attachment requires starting that drawing again from the model in a new folder with the selected reference model. |
| `done` | Go to section 5. |

Save exactly the fields and local run values named by the step's `save` instruction for preflight and write records. Local planId, attempt and probeId belong to the plugin and never enter server arguments. Save every acquired diagram read whole, following [result acquisition](result-acquisition.md). A saved review read holds at least:

- `diagramId`, `diagramUrl`, `version` and `levelNumber`;
- `diagram.activities` and `diagram.lines`: each box with its `key`, `text` and `resources`, each line with its `key`, `from` and `to`;
- `diagram.boundary`: null on the top level; on a child level, the parent activity it drills down from, with its `inputs` and `outputs`;
- with `layout`, `x`, `y`, `w` and `h` on every box, and `diagram.canvas`;
- with `attachments`, each box's `attachments`.

A box with no resources or attachments has no such key. An answer that comes as a file link (`file.url`) is downloaded at once (the link lasts two minutes) and its data is hydrated into the original outer reply, preserving paging context; nested moved values are restored at their paths. Full reads request delivery file and accept small intact inline answers. An answer that comes inline, even when `delivery: "file"` was asked, is saved whole with a script, or by copying the file the host stored a long answer in; never by retyping a summary of it. `next` asks again for a review read that is not whole and says what it lacks under `refused`.

A batch with `"confirm": true` removes only what this run made moments earlier (throwaway boxes or cards, lines `add child` seeded) or what the user agreed to remove at the plan. Send it without asking again.

A running copy waits on the same map's complete outline. A verified unchanged no-op completes the intended operation with its current version. Advance only on a genuine saved result or verified no-op.

A run that stops resumes with `next`. Before emitting a call, every drawer checks the saved plan for metadata attachments missing `refModelId`; the capability loop also checks its cached batch. An unscoped payload stops with: "Saved plan has a metadata attachment without refModelId. Start this drawing again from the model." Start that drawing in a new folder with the selected reference model in `connection.json` or the run context. At planning, every drawer fills missing attachment scope from that selection, including for a model written by hand. A scoped saved plan continues at its first unfinished step using its saved preflight and write results. Keep `connection.json` with each drawing hand-off so a drawing folder outside the source run carries the selection.

## 4. Errors and warnings

When a dry run or a real call reports an error the drawing skill does not cover:

- `being_edited` warns during a dry run; `lock_held` refuses a real write while the level is open in edit mode. Ask the editor to leave edit mode before retrying.
- `version_conflict`: the level changed since it was read. For an amendment, read it again and plan again into a new folder; for a new map, stop and tell the user.
- `rate_limited` or `server_busy`: wait a minute (or `retryAfter` seconds), then send it again.
- `save_failed` or `partial_save`: read the level and outline and reconcile resource, attachment, child and header side effects before retrying. Keep genuine saved responses and unresolved ref/key associations explicit. After reconciliation, retry save_failed at most twice using retryAfter or a minute between attempts; stop on another failure.
- `metadata_ambiguous`: check the attachment has the selected `refModelId` and the source's `metadataType`. Resolve any remaining ambiguity within that model before drawing, or use the drawing skill's supported unresolved-link handling.
- `org_not_connected`, `metadata_not_found`, `metadata_no_access`: plan again with `--skip metadata`. When the script refuses the folder, plan into a new one and tell the user the map so far stays as it is.
- A timeout: read the level and outline to determine what exists. Recover the genuine saved response when available. Otherwise stop automatic replay until element associations and side effects are reconciled; a read cannot reconstruct the original idMap by ref.
- Anything else: stop and show the issue.

Warnings in a result (`overlap`, `resource_created`, `header_replaced`, `resource_type_differs` and the like) do not stop the run; collect them for the report. Boxes go in before their lines, so box batches warn `upn_activity_orphan`, `upn_level_no_input` and `upn_level_no_output`; ignore those until the level's line batch is saved, and report them only if the review reads still show them.

## 5. Check the result

1. Run `<script> check DIR`. It checks the saved review reads in `DIR/review/` against the plan and the layout rubric rows the drawing skill names, and writes `DIR/layout-check.json`. A review read that is missing or not whole gets an `ERROR` line naming the file and what it lacks, and no `layout-check.json` is written (an earlier one is moved aside to `layout-check.stale.json`): read that level again as the line says, save the whole result, and run `check` again.
Metadata readback names the first viewable reference model for the underlying item. The reviewer matches metadata attachments by API (application programming interface) name and metadata type when supplied; a differing readback `refModelId` is accepted.

2. Run the `diagram-reviewer` agent with `pluginRoot`, `model` (the model file), `diagramType`, `levels` (the files in `DIR/review/`) `drawingPlan` (`DIR/plan.json`) and `layoutCheck` (`DIR/layout-check.json`). For an amendment, tell it the diagram was amended. Save its verdict as `DIR/review.json`.

## 6. Report

Tell the user, in plain words:

- the map's name and a link to its top level (`diagramUrl` in `DIR/review/top.json`), and how many levels were drawn;
- for an amendment, what changed, and what was kept rather than removed;
- the reviewer's verdict, and each finding with its fix, grouped by level;
- the validator's warnings, the plan's warnings and gaps, and the warnings collected while writing;
- each name the run changed (`renamed` in the `done` step) and why, so a name such as "Contact (object)" reads as the Contact object;
- that the map is a draft: a person releases it in Elements;
- what the drawing cannot do, from the drawing skill, so the user is not surprised.
