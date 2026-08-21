---
name: elements-package-uninstall
description: Plan the removal of an installed Salesforce managed package with the Elements plan_package_uninstall tool — it inventories every component the package owns, sweeps the org for incoming references, separates real uninstall blockers from package-internal edges that vanish with the package, flags the active automations to deactivate first, audits the Profiles/Permission Sets granting access, and returns a sequenced removal plan. Use when the user wants to remove or retire a managed package, e.g. "uninstall this managed package", "remove the X package", "can we get rid of this package", "what would it take to remove <package>", "package removal plan", "which packages are installed". Read-only: it plans the removal and evidences every blocker; it never executes an uninstall. Do NOT use to explore or explain a single node (use elements-metadata); do NOT use for general "what should we clean up first" tech-debt ranking across the whole org (use elements-tech-debt); do NOT use for a standalone permission/access audit of one node (use elements-access).
---

# elements-package-uninstall

Turn "we want to get rid of the Consensus package" into an evidenced, sequenced removal plan. Salesforce refuses to uninstall a managed package while other metadata still references its components, so the work is an exhaustive sweep plus a judgement on every incoming edge: which references genuinely block the uninstall, which are package-internal and disappear with the package, and which active automations should be switched off before anyone presses the button.

`plan_package_uninstall` does that sweep and that classification in one call. This skill is about feeding it the right package, reading its output correctly, paging its evidence, and closing the one gap it cannot close on its own — informal string references in code.

**Read-only.** Every tool here reads the Elements reference model. The skill produces a plan and the evidence behind it; it never edits Salesforce metadata and never triggers an uninstall. The removal itself is a human action in Salesforce, in the sequence the plan lays out.

**Licensing.** `plan_package_uninstall`, `list_managed_packages`, `get_dependencies`, `get_metadata_node` and `get_access` all require a **Pro** space and view access to the reference model. `code_search` (step 5) additionally requires **Enterprise + the Dependency Explorer licence**, an indexed org, and — to *start* a new search rather than read a cached one — **edit** access on the reference model. Unlicensed tools are hidden from the tool list entirely, so a missing tool means licensing, not a fault: degrade to what you have and say what was skipped.

## The tool: `plan_package_uninstall`

```
plan_package_uninstall({
  refModelId: "<id>",       // required: Elements reference model the package is installed in
  namespace:  "SBQQ",       // required: namespace PREFIX, not the product name (see step 2)
  mode:       "plan",       // optional: plan (default) | blockers | permissions
  limit:      50,           // optional: blockers/permissions page size (default 50, max 200)
  skip:       0,            // optional: blockers/permissions pagination offset (default 0, max 100000)
  format:     "json",       // optional: json (default) | ndjson | csv — blockers/permissions pages
  teamId:     "<space-id>"  // optional: Elements space id — see the multi-space note
})
```

The three modes read the same sweep from three angles:

| Mode | Returns | Use it for |
|---|---|---|
| `"plan"` (default) | package identity, classified `summary`, sequenced `plan`, `nextStep` | the headline answer — always start here |
| `"blockers"` | one page of external blockers, each with evidence | the actual work list; page until `hasMore` is false |
| `"permissions"` | one page of named Profiles/Permission Sets granting access | the permission cleanup list |

`mode:"permissions"` skips the dependency sweep, so it is the cheapest call; `"plan"` is the heaviest because it also counts outgoing references and summarises access.

**Multi-space note.** `teamId` (the Elements space id) is optional but becomes **required when the OAuth token is authorized for more than one space** and no active space resolves — the server returns `active_space_required`. Pass the target space's `teamId`, or set it once with `set_active_space` (`get_active_space` returns it as `activeTeamId`). The same applies to `list_reference_models`, `list_managed_packages`, `get_dependencies`, `get_metadata_node` and `get_access`.

## Workflow

### 1. Resolve the reference model

If you don't already have a `refModelId`, call `list_reference_models` (after `get_active_space` / `set_active_space` when the space is ambiguous) and pick the model for the target org.

```
list_reference_models()
--> {referenceModels: [{refModelId, name, orgId, role, ...}], count, nextStep}
```

### 2. Resolve the namespace prefix — do this before anything else

**`plan_package_uninstall` identifies a package by its namespace prefix, never by its product name.** The prefix is often unrelated to the marketing name (CPQ is `SBQQ`, Billing is `blng`, plenty are opaque like `dfsle`), so a guess silently plans the removal of the wrong package — or of nothing at all.

- If the user gave you an actual prefix (`Consensus`, `SBQQ`, `blng`), use it as-is.
- If the user gave a product or marketing name, resolve it against what is really installed:

```
list_managed_packages(refModelId)
--> {totalItems, pageSize, numPages, skip, hasMore,
     packages: [{namespace, nodeId, displayName, fullPath, componentCounts, totalComponents}]}
```

`namespace` is the value you pass downstream; `displayName` is what the user probably said; `componentCounts` / `totalComponents` show how big each package is. The list is sorted by `namespace` and paginated (default 200 per page, max 500) — if `hasMore` is true, page with `skip` until it is false before deciding. `mode:"manifest"` returns just `{totalItems, pageSize, numPages}` when you only want the count first.

- If two installed packages could plausibly be what the user meant, show them and let the user pick. Never analyse an ambiguous prefix silently.

`namespace` must be 1–15 characters, starting with a letter and continuing with letters, digits or underscores. A prefix that isn't installed returns `not_found` with `allowedValues` — the sorted list of every installed namespace — so a wrong guess is recoverable in one round trip.

### 3. Run the plan

```
plan_package_uninstall(refModelId, namespace: "Consensus")
```

```
{
  package: {
    namespace, nodeId, displayName,
    componentCounts,             // per-type counts as Salesforce reports them for the package
    inventoriedComponents,       // components the sweep actually resolved in the reference model
    inventoryTruncated?, inventoryCap?   // present only when the 25000-component cap was hit
  },
  summary: {
    externalReferences: {items, references, byType},   // the blockers
    activeAutomations:  {items, byType},               // subset of the above: deactivate these first
    packageInternal:    {items, references, note},     // auto-removed with the package
    accessGrants:       {permissions, grants, byPermissionType,
                         topPermissions: [{type, label, grants, assignedUsers}]},
    outgoingReferences: {references, note}             // informational
  },
  plan: [{step, action, description, count?}],
  nextStep
}
```

The sweep covers both places a package's components live: nodes under the package's own namespace subtree, **and** managed components grafted onto core objects (a managed field the package added to `Account`, for example). It sees live components only — deleted nodes are excluded from the inventory, and dependers whose own status is `deleted` or `proposed` are dropped from the blocker set, so nothing in the output is a tombstone.

#### Reading the four classes

| Class | Field | What it means | Action |
|---|---|---|---|
| **External references** | `summary.externalReferences` | metadata outside the package that points at package components | **Real uninstall blockers.** Edit, repoint, or delete each one first. |
| **Active automations** | `summary.activeAutomations` | the subset of those external referencing items that are live automations | **Deactivate before the uninstall**, so nothing fires mid-removal. |
| **Package-internal** | `summary.packageInternal` | package components referencing each other | **No action.** Removed automatically with the package; reported so the reader sees they were checked. |
| **Outgoing references** | `summary.outgoingReferences` | package components referencing *your* metadata | **Informational.** These go away with the package; they never block it. |

The automation set covers Apex Triggers, Flows, Processes, Validation Rules, Workflow Rules, Approval Processes, Assignment Rules, Escalation Rules, Duplicate Rules and Auto-Response Rules. A referencing component with no recorded active flag counts as active, so this list errs toward flagging one automation too many rather than one too few — confirm any surprise with `get_metadata_node(refModelId, nodeId, detail:"full")` → `nodeDetails.active`.

**External includes other managed packages.** If a *different* installed package references the target, it lands in `externalReferences` — and that is the right place for it, because Salesforce rejects the uninstall over it just the same. It is a distinct kind of work, though: the other package has to be updated or uninstalled, not edited. Spot these on the blocker page by the `Managed Packages/<other-ns>/` segment in `path` or the `<other-ns>__` prefix on `apiName`, and report them as their own class.

#### Reading the plan steps

`plan` is a sequenced runbook. `deactivate_automations`, `remediate_external_references` and `clean_permission_assignments` appear only when there is something to do, so `step` numbers shift between packages — **key off `action`, never off the number**. `resync_and_verify` and `uninstall_package` are always present and always last.

| `action` | Emitted when |
|---|---|
| `deactivate_automations` | at least one active automation references the package |
| `remediate_external_references` | at least one external reference exists |
| `clean_permission_assignments` | at least one Profile/Permission Set grants access to package components |
| `resync_and_verify` | always |
| `uninstall_package` | always |

**Permission assignments are a blocker.** Salesforce will not uninstall a package while Profiles or Permission Sets still grant access to its components, so `clean_permission_assignments` is prerequisite work in exactly the way `remediate_external_references` is — report it as a blocker, and never present the uninstall as ready while permission holders remain. This is why the tool sequences it before `uninstall_package`.

**Component cap.** The inventory stops at 25000 components. When `package.inventoryTruncated` is `true` the sweep covered `inventoryCap` components out of a larger package, so the blocker list is a **lower bound** — say so explicitly in the report rather than presenting the result as exhaustive. Compare `package.componentCounts` against `inventoriedComponents` for a sense of the shortfall.

### 4. Page the evidence

**Blockers** — the actual work list:

```
plan_package_uninstall(refModelId, namespace: "Consensus", mode: "blockers", limit: 200, skip: 0)
--> {totalItems, pageSize, numPages, skip, hasMore,
     blockers: [{
       dependerId, sfType, name, apiName, path,   // the referencing item
       references,          // how many edges it has into the package
       componentsReferenced,// how many distinct package components it touches
       components: [{name, apiName, sfType}],     // sample of up to 20 of them
       active, mustDeactivate
     }]}
```

Rows are sorted by type then name. Page with `skip` (increment by `pageSize`) until `hasMore` is false — the missed-dependency failure mode is exactly the page nobody pulled. `components` is a **sample of at most 20**; `componentsReferenced` is the true count, so use that number in any report and drill in with `get_dependencies` when the reader needs the full list. Rows with `mustDeactivate: true` are the automations behind the `deactivate_automations` step.

When you read the page, standard polymorphic lookups (`WhatId`, `WhoId`, `RelatedToId`, `RecordId` on Task, Event, EmailMessage and friends) are platform relationship artifacts, not references anyone can remove. Note them and move on; do not write them up as work.

For large packages, `format:"ndjson"` returns each page as a newline-delimited string in `data` that concatenates cleanly across pages — useful when you want to collect everything to a file and analyse it outside the context window. `format:"csv"` is fine for a single page but repeats its header, so it does not concatenate.

**Permissions** — the access grants that must be removed before the uninstall will run:

```
plan_package_uninstall(refModelId, namespace: "Consensus", mode: "permissions", limit: 200, skip: 0)
--> {totalItems, pageSize, numPages, skip, hasMore,
     permissions: [{type, label, grants, assignedUsers}]}
```

`type` is `Profile`, `Permission Set`, `Permission Set Group` or `Group`; `grants` is how many package components that permission grants access to; `assignedUsers` is a **count** of users, never a roster, and is `null` when Elements has no figure. Rows are ordered by `grants` descending, so page 1 already holds the heaviest holders. `summary.accessGrants.topPermissions` in plan mode is the same data capped at 10 — page this mode when you need the full named list.

#### The one permission class the plan tool cannot separate

`mode:"permissions"` lists every permission that grants access to package components, but carries no
field distinguishing a Profile your org built from a Permission Set the package itself shipped. The
difference matters: a package-owned Permission Set or Permission Set Group is normally removed with
the package, but Salesforce can refuse the uninstall while one still carries an active user
assignment. Check those directly, and unassign every user before the uninstall will succeed:

```
query_metadata(
  refModelId,
  metadataList: ["Permission Set", "Permission Set Group"],
  filters: [{column: "manage_package", operator: "eq", value: true}],
  columns: ["name", "manage_package", "assigned_users"]
)
```

Every column you filter on must also appear in `columns` — `query_metadata` rejects a filter on an
unselected column rather than silently dropping it, so omitting `manage_package` from `columns`
fails with `invalid_filter_column`. The rows come back with the response field `assignedUsers`
(not the `assigned_users` column key). Keep only rows in the target namespace, then flag every row
with `assignedUsers > 0`. Enterprise Space required.

### 5. Catch informal references with `code_search`

The dependency graph records structured references. It cannot see a namespace baked into an Apex string literal, dynamic SOQL, or a hardcoded ID — and those break just as loudly after an uninstall. Close that gap with a literal search for the prefix:

```
code_search(refModelId, query: "Consensus__")
--> {status: "complete", query, refModelId, total, metadataTypesWhereFound,
     results: [{nodeId, name, type, referencesFound}]}
```

Search the `<namespace>__` form, which is how the prefix appears inside source. `code_search` is asynchronous: a first, uncached search returns `status: "indexing"` — wait ~30s and call again with identical arguments until `status: "complete"` (`total: 0` is a valid complete result). Treat every hit as a candidate blocker and confirm it by opening the node, because a literal match can also land in a comment.

This step is skippable, not optional to *mention*. Without the Enterprise + Dependency Explorer licence, without an indexed org (`code_search_not_indexed`), or with only view access and no cached result, the call will not run — degrade gracefully and state in the report that the informal-reference check was not performed, so nobody reads a clean structured sweep as a clean bill of health.

### 6. Drill down where the plan needs more than a row

The plan tool answers the package-level question. Reach for these when a specific finding needs more depth:

- `get_dependencies(refModelId, nodeId, lookingFor: "incoming")` — the full edge list for one blocker or one package component, beyond the 20-component sample. Read `count`, not `deps.length`; see `elements-metadata` for its pagination contract.
- `get_metadata_node(refModelId, nodeId, detail: "full")` — confirm what a blocker actually is, including `nodeDetails.active` for an automation whose status you want to double-check.
- `get_access(refModelId, nodeId)` — which permissions grant access to **one** specific package component, with per-grant access flags. `mode:"permissions"` tells you *which* permissions are involved; `get_access` tells you what one of them grants on a given node. Hand deeper access work to `elements-access`.

### 7. Deliver the removal plan

Report in the tool's own order, with the evidence attached:

1. **Blockers** — every external reference, each named with what it references (`name`/`apiName`/`path` → `components`). Call out cross-package references as their own class: the other package must be updated or uninstalled, not edited.
2. **Deactivations** — the `mustDeactivate` rows, listed before the uninstall.
3. **Permission removals** — the permission holders from `mode:"permissions"`. These block the uninstall: Salesforce refuses while a Profile or Permission Set still grants access to package components. Remove the package permissions from an org-owned Profile/Permission Set; unassign-then-delete only a permission set that exists solely to grant the package.
4. **Checked and clear** — package-internal and outgoing references, listed so the reader can see they were examined and dismissed.
5. **Sandbox dry run** — run the uninstall in a sandbox before production. It is the only check that catches what no sweep can see.
6. **Production uninstall** — Setup → Installed Packages, once 1–3 are done.
7. **Post-removal verification** — **re-sync the org in Elements first** (these tools read the Elements reference model, not Salesforce directly, so a re-run before the sync proves nothing), then re-run `plan_package_uninstall` and confirm the external reference count is zero. A `not_found` for the namespace, or a clean plan with no external references, is the signal you want.

Frame each blocker and cleanup item as a user story with acceptance criteria when the user wants delivery-ready work; `elements-stories` turns a process diagram into stories if the plan needs to land in a backlog.

## Short lists: check `_truncated`

Every tool result passes through a size backstop, so a list can come back **short even though the
call succeeded**. When a result is over budget the backstop trims one list and adds
`_truncated {field, returnedItems, totalItems, note}`, plus **`nextSkip`** when the tool paginates —
resume the next call from `nextSkip` rather than from your own offset arithmetic, since the backstop
also rewrites `pageSize` and sets `hasMore` to stay consistent with what it returned. Which list gets
trimmed is decided by key priority (`items`, `objects`, `list`, `rows`, `nodes`, `deps`), falling back
to the array with the most elements.

A result with no list to trim comes back whole but flagged **`_oversize`**. The very largest are
replaced by an `_oversize` object carrying **`refusedInline: true`** — that is a refusal, not data:
never write it to a file or report it as a result. Read a `_truncated` or `_oversize` flag before
stating any count or declaring a sweep complete.

## Honesty rails

- **The component cap is a real ceiling.** `inventoryTruncated: true` means the answer is a lower bound. Say so.
- **Informal references need step 5.** If `code_search` didn't run, the sweep covers structured dependencies only — report that limit rather than implying completeness.
- **Unsynced types are invisible, not clean.** `list_supported_metadata_types` shows what Elements syncs; a component type absent from that list cannot appear in any sweep. Say "not synced", never "none found".
- **External automation is out of reach.** Elements cannot see a Make/Zapier/MuleSoft/middleware integration reading package fields over the API. Name it as a known limit and recommend the owner check integrations that touch the package's objects and fields.
- **`assignedUsers` is a count.** No named users come out of any of this, and `null` means unknown rather than zero.
- **Read-only, always.** The tool plans and evidences. It never uninstalls anything, in any mode.

## What it answers well, and what it does not

| Question | This skill? |
|---|---|
| "What would it take to remove the Consensus package?" | Yes — one `plan_package_uninstall` call, then page the evidence |
| "Can we get rid of this package?" | Yes — separates real blockers from what disappears on its own |
| "Which packages are even installed here?" | Yes — `list_managed_packages` |
| "Which permission sets grant access to this package?" | Yes — `mode:"permissions"` |
| "What depends on this one field?" (a single node) | No — use `elements-metadata` |
| "What should we clean up across the whole org?" | No — use `elements-tech-debt` |
| "Who can access this object, and why?" (standalone audit) | No — use `elements-access` |

## Related skills

- `elements-metadata`: resolve or explain an individual node, and the `get_dependencies` pagination contract
- `elements-access`: deeper permission-level audits of a specific node
- `elements-tech-debt`: org-wide "what should we remove first" ranking
- `elements-stories`: turn the resulting work into tracked user stories
