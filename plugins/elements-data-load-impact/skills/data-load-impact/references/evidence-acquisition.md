# Evidence acquisition

Elements supplies configuration evidence. Customer files remain on the customer's machine. In a
verified rehearsal sandbox, the playbook may create temporary load-user logging records, run the
ratified small test batch through the customer's Salesforce command-line interface (sf CLI), and
remove its own logging records. It does not change Salesforce metadata or Elements content.

## Bundle host reachability

The instance is the Elements host used by the Model Context Protocol (MCP) connector. Select the
bundle host below. The host in the tool's signed Uniform Resource Locator (URL) is authoritative when
a complete response arrives, but the URL itself is never persisted.

| Instance | Connector host | Bundle host |
|---|---|---|
| European Union production | `app.q9elements.com` | `production-elements-content-668783629007-eu-west-1.s3.eu-west-1.amazonaws.com` |
| United States production | `us.elements.cloud` | `production-elements-content-448905033567-us-east-2.s3.us-east-2.amazonaws.com` |
| Other | Any other connector host | Ask Elements support for the bundle host. |

Run from the environment that downloads bundles:

`curl -sS -o /dev/null --max-time 10 -w '%{http_code}' https://<host>/`

Any Hypertext Transfer Protocol (HTTP) status means the host is reachable. Amazon Web Services (AWS)
Simple Storage Service (S3) commonly returns 403 to an unsigned request. Curl exit 6, 7, or 28 means a
Domain Name System (DNS) failure, connection refusal, or timeout. Record the exact host in
`open_items` and take TR-06, the default self-loop on `ready`; wait until the same probe succeeds.

## Complete analysis bundles

Each `run_data_load_impact` call contains one target and runs serially. Poll a `running` response
with identical arguments after `retryAfterSeconds`. For `fire_chain_analyses_at_capacity` or
`server_busy` refusals, wait `retryAfter` and retry within the poll cap; refusal replies use
`retryAfter`, while running or retryable failed replies use `retryAfterSeconds`. Retry a failed
reply with `retryAfterSeconds` using the identical arguments. If transport fails without a tool
reply, wait 60 seconds and retry the identical call within the poll cap. A `complete` response
provides a URL valid for 120 seconds and a 256-bit Secure Hash Algorithm (SHA-256) digest. Download
immediately, verify the digest, save the response envelope without the URL, and unpack all files.
On expiry, repeat the identical call for a fresh URL. A partial or digest-mismatched bundle is not
evidence. Do not retry `bundle_too_large`; record an internal open item and take the card's default
outcome.

## Customer-side evidence

`load_input_prep.py` reads local CSV or SOQL-result files and emits aggregate-only JavaScript Object
Notation (JSON). Its `slice` command also writes the first 200 source rows to a local rehearsal
batch file; only the header names, written row count, and output line ending reach the model.
`rehearsal_fired.py` reads local debug logs and same-job success and error CSV files,
compares their row counts with the loaded batch count, and emits only automation names, types, fire
counts, processed-log count, completeness, and aggregate result counts.
Card 06 checks local parameter fidelity before asking for an alias. It selects the sf CLI path only
after confirming the alias is a sandbox and its Bulk API 2.0
command matches the ratified API, operation, server-managed batch size, and parallel concurrency.
Parent grouping sorts the sliced batch and works on either path. Before each load it names the checklist actions and the authenticated CLI user
every load-user bypass must cover, then waits for the customer's `applied` reply. It stores fetched
same-job results and load-user logs under `work/rehearsal/`, then removes only the trace flag and
debug level it created. A failed removal reports the leftover record identifier. On the manual path,
the customer supplies those same-job files. The orchestrator reads paths and aggregate script output,
never raw logs or result
files. The success file lists created identifiers for the customer's test-record cleanup.
Card 02 makes one `list_metadata_by_criteria` Field call per target object, with one
`parent_object eq` filter, and joins the saved replies with `part_files.py join`. The exporter reads
those files. Card 03 calls `list_metadata_by_criteria` with `metadataList: ["Duplicate Rule"]`,
joins its saved replies with `part_files.py join`, and retains active rules on target objects by
`parentObject` and `nodeDetails.active`. While either criteria call is `running`, poll after
`retryAfterSeconds`. A refusal uses `retryAfter`, not `retryAfterSeconds`; wait that returned
duration and retry within `poll_cap`. This includes `at_capacity`, `rate_limited`,
`too_many_concurrent_requests`, and server-level `server_busy` refusals. Run all analysis and
criteria calls serially. Save each reply as
`{"savedAt": "<International Organization for Standardization (ISO) 8601 date and time in Coordinated Universal Time (UTC)>", "reply": <tool reply>}`. Follow `nextPartsFrom` until the result
has no more parts. For managed-trigger receipts, card 03 calls `search_metadata` by trigger name
and Apex Trigger type, then records each managed namespace from the result path under its target
object. The orchestrator never opens source files.
