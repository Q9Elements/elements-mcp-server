"""Order reference removals and deletes with consumers first."""

import json
import sys
from pathlib import Path

from cli_common import SingleLineParser, _dispositions, _edges, _json


def _record(value):
    if isinstance(value, str):
        return {"nodeId": value, "name": value}
    return {"nodeId": value["nodeId"], "name": value.get("name") or value.get("apiName") or value["nodeId"]}


def order(units, roots, *, references=()):
    by_id = {}
    for row in [*units, *roots]:
        record = _record(row)
        by_id[record["nodeId"]] = record
    updates = [row["nodeId"] for row in units if row.get("disposition") == "UPDATE"]
    candidates = [row["nodeId"] for row in units if row.get("disposition") == "DELETE_CANDIDATE"]
    deletes = list(dict.fromkeys([*candidates, *(_record(root)["nodeId"] for root in roots)]))
    edges = {(consumer, referenced) for consumer, referenced in references if consumer in deletes and referenced in deletes}
    result = list(dict.fromkeys(updates))
    pending = set(deletes)
    while pending:
        ready = [node for node in deletes if node in pending and not any(consumer in pending for consumer, referenced in edges if referenced == node)]
        if not ready:
            raise ValueError("delete references contain a cycle")
        result.extend(ready)
        pending.difference_update(ready)
    return [{**by_id[node], "action": "update" if node in updates else "delete"} for node in result]


def main(argv=None):
    parser = SingleLineParser(description=__doc__)
    parser.add_argument("--in", dest="source", required=True, metavar="JSON")
    parser.add_argument("--out", required=True, metavar="JSON")
    args = parser.parse_args(argv)
    try:
        source = Path(args.source)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        change_set = _json(payload.get("change_set", {}), source.parent)
        roots = [row["element"] for row in change_set.get("elements", []) if row.get("action") == "delete"]
        references = payload.get("references", [])
        if isinstance(references, str):
            references = _edges(references, source.parent)
        if references and isinstance(references[0], dict):
            references = [(row.get("nodeId"), row.get("inputNodeId")) if row.get("direction") == "incoming"
                          else (row.get("inputNodeId"), row.get("nodeId")) for row in references]
        result = {"order": order(_dispositions(payload, source.parent), roots, references=references)}
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(result['order'])} results: {destination}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
