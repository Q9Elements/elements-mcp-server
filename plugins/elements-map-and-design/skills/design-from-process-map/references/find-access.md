# Finding the access each step needs

The method the `access-deriver` follows. First as a **process analyst**: what each step's verb and handoffs say about creating, reading, updating and deleting data. Then as a **technical architect**: which permission controller grants it, reusing what the target system already has.

## Phase 1: CRUD per step (the process analyst)

Read `model.json` (activities with their roles and `uses`), `inventory.json` and `derive/data-model.json`.

1. **One row per step, resource and entity** the step uses. The resource is the person, team, AI agent or system on the step (its roles); a step done by a system is a row for that system.
2. **CRUD from the verb:** look the step's verb up in `data/crud-verbs.csv`; it gives the default letters. Adjust from the step's outcome lines: "Account, contact and opportunity created from lead" means create on those three and update on the lead. Say in `evidence` why a row differs from the verb's default.
3. **Handoffs:** a line from a step done by one resource to a step done by another passes a record between them; the receiving resource needs at least read on it. A handoff between systems means an integration user on the receiving system (`integrationUser: true`).
4. **Fields:** list fields only where the process or the data model names them (a status set, a score written). Object level is the default.

## Phase 2: permission controllers (the technical architect)

On the org route, read the access evidence: for each `access-<n>` pull and the `permission-holders` pull in `evidence/pulls.json`, only the part files it records (`evidence/<pull>-<index>.ndjson` for each `index` in its `parts`). A part file that `pulls.json` does not record is left from an earlier pull and is not evidence. The access pulls show which profiles, permission sets and groups already grant each object; `permission-holders` shows the permission sets and groups that exist.

1. **One controller per persona and need**, following the target system's practice. For Salesforce: a permission set per persona's job, grouped in a permission set group when a persona needs several; profiles only for what permission sets cannot grant; an integration user with its own permission set per integration.
2. **Reuse, extend or create:** `reuse` an existing controller that already grants exactly what the rows need; `extend` one that grants most of it (name it in `existing`); `create` otherwise. On the documentation route every controller is `create`.

## What a good result looks like

- The letters follow the verbs, and every exception says why.
- Controllers are few and named for jobs ("Sales User", "Marketing User"), not for steps.

Every native pull retains terminal status, resultId, final counts, completed parts, failedTotal and all failed records (including failedFile coverage). Part hashes and row counts prove the files; terminal state and failures prove the coverage. Keep each result attempt separate and report source-row availability reasons as source gaps. See the shared result-acquisition contract.
