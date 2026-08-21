---
name: elements-access
description: Audit permission-level access to a Salesforce metadata node with the Elements get_access tool (which Profiles, Permission Sets, Permission Set Groups and Groups grant read/edit and to how many users, plus a per-user "why do they have access" lookup). Use when the user asks "who has access to this object/field", "audit access", "what does this profile/permission set grant", "who can edit this field and why". Read-only and permission-level only; it does NOT enumerate individual users by name (counts only, plus a per-user reason when a Salesforce user id is supplied). Do NOT use for free-form metadata search; use elements-metadata instead.
---

# elements-access

Audit permission-level access to a single Salesforce metadata node using the Elements `get_access` tool. Answers "who can access this object/field and why" at the level of Profiles, Permission Sets, Permission Set Groups and Groups, with assigned-user counts and an optional per-user reason.

**Read-only.** **Does not list individual users by name**; user enumeration is intentionally out of scope. You get counts, plus a "why does this one user have access" lookup when you already hold a specific Salesforce user id.

**Requires a Pro Space**; `get_access` is **Pro-gated**. Unlicensed tools are hidden from the tool list entirely; if `get_access` doesn't appear, licensing is why. A call against a non-Pro space is also refused at execution time.

## The tool: `get_access`

```
get_access({
  refModelId: "<id>",          // required: Elements reference model
  nodeId:     "<id>",          // required: the metadata node to inspect
  type:       "profile",       // optional: profile|permissionSet|permissionSetGroup|group
  userId:     "<sf-user-id>",  // optional: Salesforce user id ("why does this user have access")
  skip:       0,               // optional pagination (default 0)
  limit:      50,              // optional pagination (default 50, max 100)
  teamId:     "<space-id>"     // optional: Elements space id — see the multi-space note below
})
```

**Multi-space note.** `teamId` (the Elements space id) is optional but becomes **required when your OAuth token is authorized for more than one space** and no active/default space resolves: the server then returns `active_space_required` and asks for it. Pass the target space's `teamId` on the call, or set it once with `set_active_space`. `get_active_space` returns this id as `activeTeamId`. The same optional `teamId` applies to `list_reference_models`, `metadata_search`, and `get_metadata_node`.

Behaviour depends on which optional inputs you supply:

- **Omit `type` and `userId`** → grouped result across all holder types:
  ```
  {profiles, permissionSets, permissionSetGroups, groups}
  ```
  Each group is `{data, count}`. Each item in `data` has:
  - `name`: the profile / perm-set / group name
  - `access`: flag string describing the granted access (e.g. `"read edit"`, `"read"`)
  - `assignedUsers`: a **count** of users (not a user list)
  - `type`, `refModelNode`, `externalUrl`, `lightningExternalUrl`: the holder's type label, its own reference-model node id, and Salesforce Setup deep links

- **`type` given** → just that one group (`{data, count}`), same item shape.

- **`userId` given** → "why does this user have access": the specific permissions that grant *this* user access to the node. The `type` filter is ignored when `userId` is set.

## Resolve the node first

`get_access` needs a `nodeId`. Resolve it with the metadata chain from `elements-metadata`:

```
list_reference_models   -->  pick refModelId
        |
        v
metadata_search          -->  find the object/field by keyword, get a nodeId
        |
        v
get_metadata_node        -->  confirm it's the right node (optional)
        |
        v
get_access               -->  permission-level access for that node
```

Pass multiple casing/spacing variants to `metadata_search` (see `elements-metadata`) and narrow with `sfType: "Field"` or `"Custom Object"` when auditing a specific field or object.

## What it answers well, and what it does not

| Question | This tool? |
|---|---|
| "Which profiles/permsets can edit this field?" | Yes, grouped, with `access` flags |
| "How many users does each grant reach?" | Yes, `assignedUsers` count per item |
| "Why can user 005xxx edit this field?" | Yes, pass `userId`, returns granting permissions |
| "List every user who can see this object by name" | **No**, user enumeration is out of scope; counts only |
| "Find metadata matching a keyword" | No, use `elements-metadata` |

It is great for bounded, permission-level audits ("who can access X and why"). It deliberately does not produce a roster of named individual users, only counts, plus the per-user `userId` "why" lookup when you already know the user.

## Example

User: "Who can edit the `Account.Credit_Limit__c` field, and how many people does each grant reach?"

```
1. list_reference_models()
   --> refModelId = "rm_abc"

2. metadata_search({refModelId: "rm_abc",
                    queries: ["Credit_Limit", "credit limit", "creditlimit"],
                    sfType: "Field"})
   --> {nodes: [{nodeId: "n_789", name: "Credit_Limit__c", sfType: "Field"}]}

3. get_access({refModelId: "rm_abc", nodeId: "n_789"})
   --> {
         mode: "all",
         profiles: {
           data: [
             {name: "System Administrator", access: "read edit", assignedUsers: 12},
             {name: "Sales Manager",         access: "read edit", assignedUsers: 34},
             {name: "Sales Rep",             access: "read",      assignedUsers: 210}
           ],
           count: 3
         },
         permissionSets:      {data: [{name: "Credit Override", access: "read edit", assignedUsers: 5}], count: 1},
         permissionSetGroups: {data: [], count: 0},
         groups:              {data: [], count: 0}
       }
```

Read-only edit access here comes from the *System Administrator* and *Sales Manager* profiles (12 + 34 users) and the *Credit Override* permission set (5 users); *Sales Rep* (210 users) is read-only.

To explain a single user, e.g. why user `005xx00000ABCDE` can edit it:

```
get_access({refModelId: "rm_abc", nodeId: "n_789", userId: "005xx00000ABCDE"})
   --> {mode: "user", userId: "005xx00000ABCDE", ...granting permissions...}
```

## Related skills

- `elements-metadata`: resolve the `refModelId` and `nodeId` first, or do free-form metadata search and dependency tracing
