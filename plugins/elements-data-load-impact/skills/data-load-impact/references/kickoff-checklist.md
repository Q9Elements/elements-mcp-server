# Kickoff checklist

The data-load owner supplies these items before analysis:

1. The data-load owner's name and a local path to the planned comma-separated value (CSV) file or
   Salesforce Object Query Language (SOQL) file. Raw rows and query results stay local and are read
   only by the shipped scripts. When the session has no local path to the source, supply a
   header-only CSV attachment and an approximate positive row count. Source attachments contain
   only the header; any parent-count results contain only grouped lookup values and counts.
2. The owner confirms each target object's operation, written fields, counted volume, and loader
   in one reply. For a header-only chat attachment or a query-defined load without a file, the
   confirmation uses the owner's approximate volume. A counted load file uses its row count.
   An upsert also
   needs its external-identifier match field and expected insert share.

At card 06, the owner chooses whether to rehearse. A chosen rehearsal uses a full-copy sandbox.
The Salesforce command-line interface (sf CLI) may run the batch when signed in to that sandbox
and able to match the ratified parameters. On the manual path, the customer supplies debug logs
and the loader success and error files from one job. The model receives only automation names,
types, counts, and completeness status emitted by `scripts/rehearsal_fired.py`.

The data-load owner is the only human decider. This playbook changes no Salesforce metadata and does
not execute the production load. For an exact CLI match, it runs the small sandbox batch and removes
its own temporary logging records.
