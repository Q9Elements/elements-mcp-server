# Chart drill recipes

Read before the first `get_org_health_detail` call. Use returned item `detail` and one selected breakdown key, preserving labels exactly. A null detail is unavailable for drilling. For `changed_metadata`, use the selected week's breakdown `detail` as-is.

| Chart | Slice arguments |
|---|---|
| `tech_debt_severity` | `label`: `Extreme`, `Severe`, `High`, `Moderate`, `Acceptable`. |
| `tech_debt_summary` | `label`: returned category key. |
| `flows_fault`, `test_coverage`, `permission_controls`, other label charts | `label`: the chart's own breakdown key. `test_coverage` selects Apex classes/triggers. |
| `complexity` | `label` plus returned `sfType:"Apex Class"|"Flow"`. |
| `outdated_api_version` | Numeric `apiVersion` from item detail and `label` from one nonzero breakdown key. Only this recipe calls once per nonzero key. API means application programming interface. |
| `metadata_by_description` | `label` plus returned `dataType`. |
| `described_metadata`, `changes_by_type`, `metadata_by_type` | `label`, optional `fromDate`/`toDate`. |
| `changed_metadata` | Returned week's `fromDate`/`toDate`; pass only that window and common request arguments. |
| `object_analysis` | Returned `detail.nodeId`; nonempty `dependencies` of selected breakdown keys, each 2–128 characters. `limit` 25–100. |
| `field_population` | Returned `detail.nodeId` for a Standard or Custom object; `label` from `zero`, `below25`, `below50`, `below75`, `above75`. |

Use International Organization for Standardization (ISO) 8601 date strings. Time windows align to whole Coordinated Universal Time (UTC) days. Defaults use a server-selected end and a start 90 days earlier. Obtain caller-selected current dates with `date`.
Missing/incompatible arguments return `invalid_input`. Unknown labels generally return `invalid_input`; `metadata_by_type` can return an empty page. Follow returned `invalid`, message, or allowed values to correct the selected slice. Missing/non-object field-population targets return `not_found`/`invalid_node_type`; reselect from returned detail or report the failure.

## Requests and responses

Use the following call patterns with returned `refModelId` and `teamId`:

- Worst tech debt: `get_org_health_detail({refModelId,teamId,chartType:"tech_debt_severity",label:"Extreme",limit:200,skip:0,delivery:"file"})`.
- Flows with poor fault coverage: `get_org_health_detail({refModelId,teamId,chartType:"flows_fault",label:"Below 75%",limit:200,skip:0,delivery:"file"})`.
- Permission sets: `get_org_health_detail({refModelId,teamId,chartType:"permission_controls",label:"Permission Set",limit:200,skip:0,delivery:"file"})`.
- Object's Apex dependencies: `get_org_health_detail({refModelId,teamId,chartType:"object_analysis",nodeId,dependencies:["Apex Class"],limit:100,skip:0,delivery:"file"})`. Pass `detail:"full"` when expanded node data is needed.

Synthetic field-band input, with fabricated identifiers:

```json
{"refModelId":"aaaaaaaaaaaaaaaaaaaa0319","teamId":"cccccccccccccccccccc0321","chartType":"field_population","nodeId":"bbbbbbbbbbbbbbbbbbbb0320","label":"zero","limit":200,"skip":0,"delivery":"file"}
```

Default response example, after parsing the tool text and resolving files:

```json
{"chartType":"field_population","nodeId":"bbbbbbbbbbbbbbbbbbbb0320","label":"zero","items":[{"nodeId":"dddddddddddddddddddd0322","apiName":"Example__c.First__c","percentFilled":0}],"totalItems":1,"pageSize":200,"numPages":1,"skip":0,"hasMore":false}
```

## Acquisition and validation

Apply workflow step 3's file and row-paging rules through each slice's final page. A drill's `totalItems` can differ from its summary bucket; use the drill's own total. Keep slices and attempts in separate directories; save acquired `items` as newline-delimited JavaScript Object Notation (JSON), abbreviated NDJSON, pages. Run the merger for each slice:

```sh
python3 {skill-dir}/scripts/merge_ndjson.py {slice-dir} {slice-dir}/master.ndjson --expected {totalItems} --key nodeId
```

Apply the merger checks, exit-code actions, and manual fallback from workflow step 6's exhaustive-corpus resource. Fix and re-run until it passes. For an adoption gap, acquire `zero` and `below25` separately and add their drill totals only after each slice validates. Keep summary object rows separate from field rows.
For a cross-object or filtered field list, use `elements-metadata-query`.
