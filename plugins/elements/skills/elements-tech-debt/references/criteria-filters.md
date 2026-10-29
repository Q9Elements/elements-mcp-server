# Criteria filters and projections

Read this before narrowing a cleanup view. Obtain types, column keys and `allowedOperators` from `describe_metadata_schema` for the selected reference model and metadata types.

Different filter columns combine with AND; filters on the same column combine with OR, including a view's stored predicates. Adding a filter on a column absent from the view narrows the selection. Adding a predicate on a column already filtered widens it.

To tighten an existing column, omit `view`, pass the returned `viewSpec.metadataList`, copy the other `viewSpec.filters`, then replace that column's predicate. For one inclusive interval use `range`, lower `value`, upper `secondValue`. Include filter columns in explicit `columns`.

Example: returned inactive-Flow filters include `active eq false` and a modification-date bound. Request `metadataList:["Flow"]` with those predicates and a tighter modification-date bound to return only the older inactive Flows. Adding the tighter date predicate alongside `view` would OR the date predicates.

Ad-hoc predicates use `{column,operator,value,secondValue?}`. Selection limits are 50 `metadataList` strings of at most 100 characters, 100 filters and 200 column keys of at most 200 characters. Use schema-provided operators; `startswith` on a string column requires at least four characters. `invalid_filter_operator` returns `invalid[].{column,operator,allowed}` for correction.

Resolve scalar `parent_object` by exact Salesforce application programming interface (API) name within the same reference model. A missing non-deleted object returns `parent_object_not_found`. Repeated same-operator predicates for this column, including duplicates contributed by a view, return `invalid_input`. `tags`, `optimization_status` and `parent_manage_package` are display-only; scalar `parent_object` is filterable when the schema allows it.

Project the `viewSpec.columns` keys from actual row paths. The candidate script contains the projection paths and screening policy. Reused files can omit selected projections or `identity`; absent values stay unknown. Canned-view date cutoffs are computed when the view is read; polling a reused completed file preserves that computation's cutoff.
