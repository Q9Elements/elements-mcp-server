# Informal code references

Structured dependency evidence needs a separate literal search for namespace strings in dynamic queries, Apex literals and hardcoded identifiers:

```js
run_code_search({refModelId,query:"acme__",teamId})
```

Bind the namespace from discovery. The trimmed literal query accepts 2–512 characters and matches case-insensitively. An indexing-only reply can be `{status:"running",query,refModelId,retryAfterSeconds,message}` without a result identifier or parts. Wait the returned interval and repeat the same selection. Availability and access refusals use [access and refusals](access-and-refusals.md).

For native file replies, apply [response and file handling](response-and-file-handling.md) and run its validator. Rows use newline-delimited JavaScript Object Notation (JSON), abbreviated NDJSON, and contain `nodeId,name,type,referencesFound`. `totalRows` counts matching components; `referencesFound` counts matches within one component. A complete, failure-free search with zero rows has no hits.

## Bounded confirmation

Group every downloaded hit by `type`. Confirm the ten highest `referencesFound` rows overall, breaking ties by `nodeId`, plus every Apex Trigger and Flow hit. Deduplicate that union by `nodeId`. This is a sampling policy, not a server limit. If the selected union exceeds the available call budget, confirm in descending `referencesFound` order and report the remainder as unconfirmed. Stop when the available budget is reached; retain the full match file.

For each selected row, call `get_metadata_component({refModelId,nodeId,detail:"full",teamId,delivery:"file"})` and hydrate the source before judging it. A comment or inert string is a confirmed non-actionable match. A source-backed runtime reference is a confirmed actionable reference. Missing source, a refused read or an unexamined row remains an unconfirmed string match; search output alone does not establish an uninstall blocker.

Report matching components, confirmed actionable components, confirmed non-actionable components and unconfirmed components, each by type. Include the unconfirmed total in the report's coverage line. Synthetic example: 40 component hits with 10 confirmed actionable, 5 confirmed inert and 25 unconfirmed establish 10 actionable references and 25 unconfirmed string matches. Match-occurrence totals are a separate measure.

When licensing, indexing, sync activity or access prevents the search, report the informal-reference check as unavailable and retain the structured findings with that coverage limit.
