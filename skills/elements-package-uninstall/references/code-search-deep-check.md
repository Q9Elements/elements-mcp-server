# Step 6 deep check — code_search details

Referenced from SKILL.md Step 6. `get_dependencies` (Step 2) can't see references buried in
Apex string literals, dynamic SOQL, or hardcoded IDs. If the Space is **Enterprise + Dependency
Explorer licensed** and the org is indexed, run `code_search` for the namespace prefix to catch
them:

```
code_search(refModelId, query: "Consensus__")
--> { status: "complete", metadataType: null, total, metadataTypesWhereFound, results: [{nodeId, name, type, referencesFound}] }
```

## Polling

`code_search` is asynchronous: if it returns `status: "indexing"`, wait ~30s and call again with
the same arguments until `status: "complete"`. If the license or the index is missing it errors —
skip gracefully and note in the report that the informal-reference deep check was not run.

## The `metadataType` filter

`code_search` accepts an optional `metadataType` filter (one of the labels in
`metadataTypesWhereFound`, e.g. `"Apex Class"`) that narrows `results`/`total` to a single type —
leave it off for the uninstall sweep: the goal is every informal reference to the prefix across
all types, and `metadataTypesWhereFound` already tells you which types they land in. Reach for the
filter only when drilling into one type's hits.

## Authorization

Starting a **new (uncached)** code search additionally requires **edit** access on the reference
model — kicking off indexing is a write-level action. A viewer-level role can only re-read results
already cached from a prior search. If you have only view access and no cached result exists, this
check will not run — skip gracefully and note it in the report, exactly as with a missing license.
