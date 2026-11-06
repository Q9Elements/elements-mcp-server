# Snapshot selection and comparison

## Candidate selection

Group the main corpus by `nodeId`, retaining in-window `changeLogId` values. Deleted and proposed events stay in counts; select new or updated events for snapshots.
Build a candidate pool across changed types. Prefer types observed to carry snapshots (Profile, Data Transform), then remaining types by record count, with Report last.
If manifest types do not resolve, call `describe_metadata_schema({refModelId,teamId,delivery:"file"})`, resolve `types[].{name,salesforceName,aliases}` and use canonical `name` values. If discovery is refused, use returned change-row types and disclose the limit.
When columns are returned, `tags,optimization_status,parent_manage_package` are display-only (`filterable:false`); scalar `parent_object` filtering is supported.
For extra candidates, repeat record acquisition with `metadataTypes:[type],status:["new","updated"]` and the same window, using `--capture-dir "$CACHE/candidates/TYPE"` with a safe directory name for the chosen type.

## Capture procedure

1. **Locate the version and baseline.** Call `get_component_change_history({refModelId,teamId,nodeId,historyType:"change_logs",limit:200,skip:0,delivery:"file"})`.
   Resolve `changeLogs` and locate the chosen event by `_id == changeLogId`. Entries retain `_id,syncUUID,previousSyncUUID,status,lastModifiedBy,lastModifiedDate` and optional `summaryContext.skippedReason:"no_changes"`.
   Continue through `hasMore,nextSkip` as needed, including outside the report window. A complete page file uses its full-page cursor; an inline-only trim uses `_truncated.nextSkip`. Stop at exhausted history or a captured baseline. Non-advancing cursors or the 100000 skip ceiling with outstanding entries mean partial history.
   History pages accept `limit` 1 to 200 and `skip` 0 to 100000. File-storage keys are stripped, so availability comes from the snapshot read.
2. **Resolve the selected snapshot.** Call `get_component_change_history({refModelId,teamId,nodeId,changeLogId,historyType:"audit_log",as:"url",delivery:"file"})` for the in-window event.
   Resolve `auditLog.{url,bodyUrl,ttlSeconds,note}` before inspecting its uniform resource locator (URL). Null `url` means unavailable with `note`; try another eligible in-window event for that component and retain its identifier.
3. **Download both versions.** Use the immediately older history entry's `_id` for a second snapshot call. If its URL is null, walk older entries to the nearest available captured version and label skipped baselines.
   Download immediately within returned `auditLog.ttlSeconds`; repeat the same snapshot read for fresh links on expiry or failure. Set `ext` from the URL object path: `xml` for classic metadata, `json` for Data Cloud. Both formats go under `xml/`.
   For each side (`current`, then `previous`), bind `AUDIT_URL`, optional `BODY_URL`, `NODE_ID`, `SIDE` and `EXT` to the resolved values. Run exactly:

   ```sh
   (
     set -e
     mkdir -p "$CACHE/xml"
     curl --fail --silent --show-error "$AUDIT_URL" -o "$CACHE/xml/$NODE_ID-$SIDE.$EXT.tmp"
     if [ -n "${BODY_URL:-}" ]; then
       curl --fail --silent --show-error "$BODY_URL" -o "$CACHE/xml/$NODE_ID-$SIDE.body.tmp"
       cat "$CACHE/xml/$NODE_ID-$SIDE.body.tmp" >> "$CACHE/xml/$NODE_ID-$SIDE.$EXT.tmp"
     fi
     mv "$CACHE/xml/$NODE_ID-$SIDE.$EXT.tmp" "$CACHE/xml/$NODE_ID-$SIDE.$EXT"
   )
   ```

   The subshell stops on a failed command and publishes the file only after all downloads succeed; a failed body download makes that side incomplete. Without shell execution, use the runtime's download facility and append body bytes after primary bytes before publishing the snapshot file.
4. **Compare captured files.** Set `PREVIOUS` and `CURRENT` to the completed paths. Run:

   ```sh
   python3 "$SKILL_DIR/scripts/diff_xml.py" --previous "$PREVIOUS" --current "$CURRENT"
   ```

   The script sorts JavaScript Object Notation (JSON) keys while preserving source number text, pretty-prints Extensible Markup Language (XML), and compares mixed metadata/body or other content as raw text. Show the unified delta and `+N / -M` summary.
   Omit `--previous` only for a confirmed creation with exhausted older history. An unavailable baseline is a coverage limit. A normalized `+0 / -0` diff means skip the candidate; a history `no_changes` hint guides selection, while the downloaded diff establishes content changes.
   Without scripts, compare only fully downloaded files using the runtime's text comparison and state that normalization is unavailable.
5. **Continue selection.** Walk the pool until the requested count has nonempty diffs or candidates are exhausted. List skipped nodes with unavailable snapshot/baseline, no changes or download failure. For user-named nodes capture available files and explain each limit.
6. **Capture requested documents.** After snapshot selection, only when the user asks for documents, call `get_metadata_component({refModelId,teamId,nodeId,detail:"full",delivery:"file"})`.
   Save the resolved result as `node/{nodeId}-document.json` under the cache. It is a raw current sidebar-enriched document plus `_untrusted` and can retain `_id`; attachment bodies and full `sfNode` expansion are outside this capture. Report a document refusal separately from snapshot success.
