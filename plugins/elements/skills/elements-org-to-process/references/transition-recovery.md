# Transition recovery from an export

Use this procedure when hydrated result files still cannot supply all transitions.
Read `_truncated.field`, `returnedItems`, `pageItems`, `inFile`, and `totalKnown` when present.
This fabricated marker describes 13 preview rows from a page of 26 transitions:

```json
{"_truncated":{"field":"transitions","returnedItems":13,"pageItems":26,"totalItems":null,"totalKnown":false,"inFile":true}}
```

`metadata.transitionCount` supplies the expected total. An unknown `_truncated.totalItems` is unavailable, not zero.

1. Use the `mapId` retained with the target `diagramId`. If missing, call
   `list_process_maps({teamId, mode:"page", format:"json", delivery:"file"})` and match `diagrams[].diagramId`.
   Follow the main reference's [Paging](org-to-process.md#paging) until found or exhausted.
   If exhausted, report the unresolved identifier.
2. When a list row exists, require `canExport:true` (`myRole:"manage"`). With a retained `mapId`,
   let the export tool enforce authorization. The main reference's
   [Access and refusals](org-to-process.md#access-and-refusals) governs export access gaps.
3. Call `export_diagram({mapId, teamId})`; hydrate its response, then download the ZIP archive from
   `downloadUrl` using the main reference's [Tool replies](org-to-process.md#tool-replies).
   The archive contains `map.json` plus a JavaScript Object Notation (JSON) file per level;
   the org-to-process top level is `1.json`. Export subtypes retain their stored spelling.
4. From the skill directory, run exactly this command, replacing `26` with the returned metadata count:

   ```sh
   python3 scripts/rebuild_transitions.py export.zip --expected 26 --output transitions.json
   ```

   An extracted `1.json` can replace `export.zip`. On exit 1, recover the complete export and re-run;
   on exit 2, correct the named input/output path and re-run. Use output only after exit 0.
   Preserve the process map's warnings alongside recovered evidence.
5. Add `--transitions transitions.json` to the validation/build commands in SKILL.md.
   If counts still disagree, report incomplete evidence and withhold the rubric for this diagram.

For a runtime without script execution, open `1.json` with the available archive reader and
build one transition per `flowlines[]` entry using this table, then perform the same count check.

| Transition field | Export flowline |
|---|---|
| `id` | `"transition:" + mxKey` |
| `fromActivityId` | `"activity:" + srcId` when `srcId` matches an exported `activities[].mxKey`, else `null` |
| `toActivityId` | `"activity:" + tgtId` when `tgtId` matches an exported `activities[].mxKey`, else `null` |
| `label` | Decode entities; space `<br>` variants and opening `<div>` tags; strip tags; collapse whitespace; remove leading `AND`; replace double-quoted phrases with single quotes |

For example, a fabricated flowline with `mxKey:"aaaaaaaaaaaaaaaaaaaa0319"`,
`srcId:"aaaaaaaaaaaaaaaaaaaa0320"` present in exported activities, and a target absent from activities becomes
`id:"transition:aaaaaaaaaaaaaaaaaaaa0319"`, `fromActivityId:"activity:aaaaaaaaaaaaaaaaaaaa0320"`, and `toActivityId:null`.
Activity identifiers use the same prefix and key as the compact process map; retain them for joins.
If extraction is unavailable, request a readable level file or report blocked recovery.
