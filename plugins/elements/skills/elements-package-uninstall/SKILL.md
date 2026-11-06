---
name: elements-package-uninstall
description: >-
  Plan the removal of an installed Salesforce managed package with the Elements plan_package_uninstall
  tool: inventory components, classify uninstall blockers, identify active automations, audit permission
  holders, and produce a sequenced removal plan with file evidence. Use when the user says "uninstall
  this managed package", "remove the X package", "can we get rid of this package", "what would it take
  to remove this package", "package removal plan", or "which packages are installed". Read-only:
  it plans and evidences removal; the user performs Salesforce changes. Do NOT use to explain a single
  node (use elements-metadata), rank org-wide tech debt (use elements-tech-debt), or audit access to
  one node (use elements-access).
---

# elements-package-uninstall

Input: a selected Elements reference model and installed namespace prefix. Output: a sequenced removal plan, full evidence files and explicit coverage limits. The Model Context Protocol (MCP) tools read synced metadata; the user performs Salesforce changes.

Read [access and refusals](references/access-and-refusals.md) for prerequisites before the first call and for the next action on any refusal. Choose the connected server for the user's named environment and keep it throughout. Quote actual returned refusal details; their parsing rules live in the response reference at step 1.

```text
- [ ] 1. Resolve the reference model and space.
- [ ] 2. Resolve one installed namespace prefix.
- [ ] 3. Interpret the plan and inventory coverage.
- [ ] 4. Consume every blocker and permission page.
- [ ] 5. Search informal references and record confirmation coverage.
- [ ] 6. Expand findings that need more evidence.
- [ ] 7. Deliver the ordered plan, evidence and coverage limits.
```

## 1. Resolve the reference model

Call `list_reference_models({teamId,delivery:"file"})` and select the target org from `referenceModels`. Carry `referenceModels[].refModelId`, not Salesforce `orgId`, and optional space `teamId` on every data call. This discovery is unpaged. Reference model, space and node example identifiers below are fabricated 24-character hexadecimal placeholders.

Before interpreting any reply, read [response and file handling](references/response-and-file-handling.md), including hydration of moved content. A small reply stays inline. Resolve an ambiguous space through `elements-spaces` before selecting the reference model.

## 2. Resolve the namespace prefix

Use an actual prefix such as `acme` directly. Resolve a product name with `list_managed_packages({refModelId,teamId,delivery:"file"})`; consume all `packages` pages before choosing. Carry `packages[].namespace`; `displayName` identifies the product. The list is sorted by namespace, with default page size 200 and maximum 500. `mode:"manifest"` returns `totalItems,pageSize,numPages` for counts; omit `delivery` for that count call.

If multiple installed packages fit the name, show them and ask the user to pick: choosing silently risks planning the wrong package. A namespace starts with a letter, then letters, digits or underscores, with length 1–15. An uninstalled prefix returns `not_found` and sorted `allowedValues`; resolve against that list.

## 3. Run and interpret the plan

Read [plan output](references/plan-output.md) before interpreting the fields. Start with:

```js
plan_package_uninstall({refModelId:"aaaaaaaaaaaaaaaaaaaa0319", namespace:"acme", delivery:"file"})
```

| Class | Field | What it means | Action |
|---|---|---|---|
| External references | `summary.externalReferences` | Metadata outside the package pointing at its components; standard polymorphic lookups are excluded | Remediate the real blockers by editing, repointing or deleting them |
| Active automations | `summary.activeAutomations` | The active automation subset of external references | Deactivate before uninstall so nothing fires during removal |
| Package-internal | `summary.packageInternal` | Package components referencing each other | Checked and clear; removed with the package |
| Outgoing references | `summary.outgoingReferences` | Package components referencing org metadata | Informational; removed with the package |

Key the returned runbook by `plan[].action`; conditional steps change the step numbers. Follow its order. The inventory stops at 25,000 components; `package.inventoryTruncated:true` makes the blocker count a lower bound. Report the returned `inventoryCap` and `inventoriedComponents`. Synthetic example: a plan with 12 external items and a truncated inventory establishes at least 12 blockers, not a complete total.

## 4. Page the evidence

Page blockers and permissions to `hasMore:false`, consuming each page's files before advancing, using [response and file handling](references/response-and-file-handling.md).

```js
plan_package_uninstall({refModelId,namespace:"acme",mode:"blockers",limit:200,skip:0,teamId,delivery:"file"})
plan_package_uninstall({refModelId,namespace:"acme",mode:"permissions",limit:200,skip:0,teamId,delivery:"file"})
```

Keep each blocker's `dependerId` and evidence, separate `mustDeactivate` rows, and attach the full list. Cross-package blockers form their own group: another namespace's `Managed Packages/other/` path or `other__` application programming interface (API) name prefix is ownership evidence. Confirm uncertain ownership before recommending an update or removal of that other package. Report `summary.standardPolymorphicLookups.items` as a separate checked-and-clear count, with its `references` edge count when useful.

If the permissions page lists a Permission Set or Permission Set Group, read [package permission sets](references/package-permission-sets.md) to identify target-package assignments. Keep permission cleanup as the returned plan's prerequisite work; use sandbox verification to establish Salesforce readiness.

## 5. Check informal references

Before searching, read [code-search deep check](references/code-search-deep-check.md). Call `run_code_search({refModelId,query:"acme__",teamId})` with the resolved prefix. Acquire the full search file result, then apply that reference's bounded confirmation rule. Report confirmed actionable references separately from unconfirmed string matches, including counts by type. A search that runs but is partly confirmed has partial confirmation coverage.

For each native file job, run the validator from the skill directory after each saved response:

```sh
python3 --version
python3 scripts/fetch_parts.py response.json --output evidence/code-search
```

Use a dedicated output directory per selection. Install Python 3 from python.org or the runtime's package manager if unavailable and installation is supported. Fix and re-run until acquisition exits 0; its failure report still determines evidence coverage. Without script execution, manually acquire and verify parts, follow cursors and waits, and reconcile completion and failures using the shared file-handling reference. Use the same command for dependency, criteria and access jobs at their steps.

## 6. Drill down when needed

When a sample hides a blocker's full component list, an active flag is surprising, or one component's holders need inspection, read [drill-down](references/drill-down.md). It gives the manifest-to-rows dependency comparison and one-component reads. Hand deeper access analysis to `elements-access`.

## 7. Deliver the removal plan

Use this default report structure; attach full evidence files and name top items by type in prose:

1. Blockers: external item and edge counts, cross-package group, and full work list keyed by stable identifier.
2. Deactivations: the `mustDeactivate` work before uninstall.
3. Permission cleanup: named holders and target-package set assignment findings. Remove package access from org-owned holders; propose deleting a holder only when its owner confirms it serves solely this package.
4. Checked and clear: polymorphic lookup items, package-internal items and outgoing edges.
5. Execution order for the user: remediate and clean permissions; re-sync Elements and re-run the plan until external references are zero; dry-run uninstall in a sandbox; repeat verification against the production reference model before production uninstall through Setup → Installed Packages. After removal, re-sync and re-run: namespace `not_found` confirms absence from the synced reference model; a returned plan means it remains inventoried.
6. Coverage: inventory cap/lower bound; pages or downloads missing; file or node failures; unavailable licence, access, types or sync evidence; search performed or unavailable; confirmed and unconfirmed match counts by type. A zero structured count supports readiness only within this coverage. Ask owners to check external integrations that read package objects or fields through the API; they are outside the synced dependency graph.

`assignedUsers` semantics and evidence field definitions live in plan output. When delivery-ready work is requested, write cleanup items with acceptance criteria; `elements-stories` generates stories from a process diagram.

| Request | Route |
|---|---|
| Package removal, installed package inventory, package permission cleanup | This skill |
| One component's dependencies or explanation | `elements-metadata` |
| Org-wide cleanup ranking | `elements-tech-debt` |
| One component's permission-level audit | `elements-access` |
