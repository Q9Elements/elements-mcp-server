# Report values and replay

Use `values.json`, a JavaScript Object Notation (JSON) object, with one value per template token
plus `DIGEST`. Values are text or finite numbers. Plain values are escaped for HyperText Markup
Language (HTML); keys ending `_HTML` contain locally constructed markup, with org text escaped.
Use explicit unavailable reasons for missing evidence. For fewer than three finalists, leave an
unused `F2_NAME` or `F3_NAME` empty (tab stays disabled) and fill its other values with “Unavailable:
no finalist.” The report filler validates all keys before writing either output; exit 2 means fix
all named missing, unknown, empty or leftover tokens and rerun. Exit 0 means open the report.

| Keys | Meaning |
|---|---|
| `REFMODEL_NAME`, `SCANNED_COUNT` | Selected reference model name; summary `objectsScanned` |
| `EXEC_NARRATIVE`, `N_CANDIDATES` | Summary judgment; summary `objectsWithSignal` |
| `N_CONV`, `N_DET`, `N_WELL`, `N_CLEANUP` | Primary Conversational, automation-gap, well-automated and Cleanup counts |
| `N_OVERLOAD`, `N_ASSIST` | Primary or secondary Cognitive-overload and Assistant / deflection counts |
| `COVERAGE_STATEMENT`, `RANKING_STATUS` | Available and unavailable signals; verified or unresolved ranking with reason |
| `TOP_FINALISTS_HTML`, `RANKED_ROWS_HTML` | Summary list items; one table row per acquired object, including score, source, lane and evidence |
| `F1_NAME`, `F1_CLASS`, `F1_NARRATIVE` | Finalist name, primary lane and evidence-backed narrative |
| `F1_RECORDS`, `F1_UNSTR` | Record count; recomputed/server ratios or explicit unverified status |
| `F1_VELOCITY`, `F1_WINDOW_DAYS` | Usage net delta and its reported snapshot window |
| `F1_FLOWS`, `F1_APEX`, `F1_CONFIG` | Manifest incoming Flow references (edges), Apex Class references (edges), and scan configuration-item count |
| `F1_CONTENT_FIELDS` | Qualifying human-content fields and their field-level population |
| `F1_AUTOMATION`, `F1_RECOMMENDATION` | Current automation map; recommended agent shape and expected-impact framing |
| Corresponding `F2_` and `F3_` keys | Same meanings and tab contents for each other finalist |
| `DIGEST` | Coverage line, ranking status, and one paragraph per finalist with score, one-line receipts and limits |

Record each object once in its primary lane. Secondary opportunities can make lane totals exceed
the candidate total. A completed file corpus is required for a complete ranked table. Script output
uses `agent-opportunities.html` and `agent-opportunities.md` in the selected output directory.
The digest begins with `generatedAt: YYYY-MM-DDTHH:MM:SSZ` in Coordinated Universal Time (UTC),
from the system clock. For manual rendering, obtain it with `date -u +%Y-%m-%dT%H:%M:%SZ`.
Use `.elements/{teamId}/{refModelId}/` at the workspace top as the output directory.

Reuse a cached digest less than 24 hours old, measured from that first-line header against the
system clock; explicit re-scan requests bypass it. An absent, malformed, future or stale header
requires re-scan. On replay, present the cached coverage, ranking status and finalist paragraphs,
identify the cached `generatedAt`, and link the saved HTML. Replay calls no scan tool.
