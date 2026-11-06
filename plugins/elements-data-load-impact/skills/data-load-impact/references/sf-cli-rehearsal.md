# Salesforce CLI rehearsal

## Verified sandbox

Card 06 checks the selected alias with `sf data query --target-org <alias> --query "SELECT Id, IsSandbox FROM Organization" --json`. Continue here only after that query returns exactly one row with `IsSandbox: true` and an org identifier matching the selected alias in `sf org list`.

## Load and evidence capture

When the mapping matches, set `rehearsal.capturePath` to `sf-cli`. The authenticated CLI user
   is the load user. Take its username from the selected `sf org list` entry and get exactly one
   Id with `sf data query --target-org <alias> --query "SELECT Id FROM User WHERE Username = '<username>'" --json`.
   If the username or unique Id is unavailable, use the manual path before creating anything.
   Before each sf load, including a reload after TR-23 or a return from card 05, send one
   message naming every ratified checklist action the customer must put in place in `<alias>`:
   deactivations, bypasses, replacement data-quality checks, and source-preparation controls that
   apply. Name `<username>` as the sf CLI user that every load-user bypass must cover. Ask for
   the exact reply `applied`; wait for that reply before creating logging records or loading. One
   reply covers one load only. If the checklist changes, name its current actions in the next
   message. Record the reply with the person's name and `now.py` time in `decisions_log` and
   this run's `appliedBy` and `appliedOn` fields.

   Use `now.py` output such as `YYYY-MM-DDTHH:MM:SS+00:00` to form a unique debug-level
   `DeveloperName` as `DLI_YYYYMMDD_HHMMSS`: remove the `+00:00` suffix, remove date hyphens
   and time colons, and replace `T` with `_`. Use that name for `MasterLabel` too. Use the host clock for a trace start
   time, and an expiration time one hour later (within the 24-hour trace-flag limit). Use a local
   date calculation, not mental arithmetic. Create a Tooling API debug level with
   `sf data create record --target-org <alias> --use-tooling-api --sobject DebugLevel --values
   "DeveloperName=<name> MasterLabel=<name> ApexCode=FINE ApexProfiling=FINE
   Callout=INFO Database=INFO System=INFO Validation=FINE
   Visualforce=INFO Workflow=FINE" --json`. Before creating it, append a `rehearsal.cliRuns`
   entry with `target: {"object": "<confirmed object>", "operation": "<confirmed operation>"}`,
   `loadUserUsername`, `loadUserId`, `appliedBy`, `appliedOn`,
   and null `debugLevelId`, `traceFlagId`, `jobId`, `loadStartedOn`, `loadEndedOn`,
   `successFile`, and `errorFile`; start `logFiles` as `[]` and `cleanupStatus` as
   `{"traceFlag": "not-created", "debugLevel": "not-created"}`. If the debug-level create fails
   specifically because `DeveloperName` already exists,
   wait one second, run `now.py` again, rebuild both names, and retry that create once within the
   same `rehearsal.cliRuns` entry. If the retry fails, or the first failure has another cause, do
   not retry. On a successful create, extract the returned Id programmatically into `debugLevelId`
   immediately and set `cleanupStatus.debugLevel` to `pending`. Create the load-user trace flag with
   `sf data create record --target-org <alias> --use-tooling-api --sobject TraceFlag --values
   "TracedEntityId=<load-user-id> LogType=USER_DEBUG DebugLevelId=<created-debug-level-id>
   StartDate=<start-UTC> ExpirationDate=<end-UTC>" --json`; extract its returned Id into
   `traceFlagId` immediately and set `cleanupStatus.traceFlag` to `pending`. If either create
   fails, do not load; clean up only the record
   created by this run and use the manual path.

   Use `sf data import bulk` for insert, `sf data update bulk` for update, or
   `sf data upsert bulk --external-id <manifest.targets[0].upsert.matchField>` for upsert.
   Supply `--file work/rehearsal/batch.csv --sobject <object> --target-org <alias> --wait 30 --json`
   and `--line-ending <lineEnding from slice JSON>` (`LF` or `CRLF`). Never use a delete or
   hard-delete operation. Record `loadStartedOn` immediately before the matching bulk command
   and its returned job Id in `jobId` immediately after it starts. Keep the CLI's JSON output
   local under `work/rehearsal/`; read
   only the job Id and status, never record rows. A nonzero CLI exit with a job Id can represent
   rejected rows, so still fetch that job's results. Wait for completion of that same job. If the
   command times out, poll its status with
   `sf api request rest /services/data/v64.0/jobs/ingest/<job-id> --target-org <alias> --method GET --json`
   until `JobComplete`, `Failed`, or `Aborted`. Record `loadEndedOn` after the terminal status.
   From `work/rehearsal/`, run
   `sf data bulk results --job-id <job-id> --target-org <alias> --json`; it writes
   `<job-id>-success-records.csv` and, when failures exist, `<job-id>-failed-records.csv` there.
   If it reports zero failures and writes no failed file, create a header-only
   `<job-id>-failed-records.csv` with `sf__Id,sf__Created,sf__Error` as its header. Record both
   paths as `successFile` and `errorFile` in the run and report the success-file path to the
   customer; its `sf__Created` column
   identifies the newly created record identifiers for their later cleanup. Never delete test
   records. A failed or aborted job, or
   an unprocessed-records file, is incomplete evidence under TR-21.

   Use `YYYY-MM-DDTHH:MM:SSZ` for the locally calculated Coordinated Universal Time (UTC) window.
   Set `<trace-start-UTC>` to the trace-flag start and `<query-time-UTC>` to the time of this query,
   so asynchronous work after the load is included. Query only this load user's log identifiers with
   `sf data query --target-org <alias> --use-tooling-api --query "SELECT Id FROM ApexLog WHERE LogUserId = '<load-user-id>' AND StartTime >= <trace-start-UTC> AND StartTime <= <query-time-UTC>" --json`.
   For each returned Id run
   `sf apex get log --log-id <log-id> --output-dir work/rehearsal --target-org <alias>`.
   Record the downloaded paths in `logFiles`; retry an empty download. The orchestrator never opens
   a downloaded log, success file, or failed file. In all cases, including a failed load or fetch,
   delete only this run's recorded trace flag and debug level with
   `sf data delete record --target-org <alias> --use-tooling-api --sobject TraceFlag --record-id <created-trace-flag-id> --json`
   and the same command with `--sobject DebugLevel --record-id <created-debug-level-id>`, in that
   order. Record each attempted delete as `deleted` or `failed` in the matching `cleanupStatus`
   key; if a delete fails, retain its Id and report
   the exact remaining record and Id for the customer's optional cleanup. Continue with the next
   rehearsal when it is due.
