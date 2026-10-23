"""File-based command line adapter for the change-impact card scripts."""

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path


class SingleLineParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"error: {message}\n")


def _path(value, base):
    path = Path(value)
    if path.is_absolute():
        return path
    beside = base / path
    if beside.exists():
        return beside
    sibling = base.parent / path
    return sibling if sibling.exists() else beside


def _json(value, base):
    if isinstance(value, str):
        return json.loads(_path(value, base).read_text(encoding="utf-8"))
    return value


def _rows(value, base, filename=None):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    path = _path(value, base)
    if path.is_dir():
        if filename is None:
            raise ValueError(f"row filename required for {path}")
        path = path / filename
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix == ".ndjson":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"expected a row list in {path}")
    return data


def _bundles(payload):
    value = payload.get("bundles", payload.get("bundle", []))
    return value if isinstance(value, list) else [value]


def _dispositions(payload, base):
    value = payload.get("dispositions", payload.get("units", []))
    data = _json(value, base)
    return data.get("units", []) if isinstance(data, dict) else data


def _edges(value, base):
    if isinstance(value, list):
        if not value or isinstance(value[0], dict):
            return value
        return [row for source in value for row in _rows(source, base, "dependents.csv")]
    return _rows(value, base, "dependents.csv")


def _calculate(name, payload, base):
    module = importlib.import_module("fire_chain" if name.startswith("fire_chain_") else name)
    if name == "resolve_names":
        return module.resolve_names(_json(payload.get("targets", []), base),
                                    _rows(payload.get("hits", []), base),
                                    fields=_rows(payload.get("fields", []), base),
                                    entry_fields=_json(payload.get("entry_fields", []), base),
                                    written_fields=_json(payload.get("written_fields", []), base),
                                    mode=payload.get("mode", "resolve"))
    if name == "build_change_set":
        return module.build_change_set(_json(payload.get("targets", []), base),
                                       action=payload.get("action"), delta=payload.get("delta"),
                                       option=_json(payload["option"], base) if "option" in payload else None)
    if name == "candidate_digest":
        sources = _bundles(payload) or [payload.get("source")]
        filename = "dependents.csv" if payload.get("kind") == "automation" else "rows.ndjson"
        rows = [row for source in sources for row in _rows(source, base, filename)]
        fact_sources = payload.get("target_facts", [])
        if not isinstance(fact_sources, list) or (fact_sources and isinstance(fact_sources[0], dict)):
            fact_sources = [fact_sources]
        facts = [row for source in fact_sources for row in _rows(source, base, "nodes.ndjson")]
        return {"lines": module.candidate_digest(rows, kind=payload.get("kind", "schema"),
                                                 targets=payload.get("targets", []),
                                                 object_name=payload.get("object"), facts=facts)}
    if name == "definitions_digest":
        bundles = _bundles(payload)
        records = []
        for bundle in bundles:
            root = _path(bundle, base)
            index = root / "index.csv" if root.is_dir() else root
            records.extend(module.digest(index, root if root.is_dir() else root.parent,
                                         targets=payload.get("targets", [])))
        return {"records": records}
    if name == "ooe_screen":
        change = _json(payload["change"], base)
        peers = _rows(payload.get("peers", payload.get("inventory", [])), base, "dependents.csv")
        edge_input = payload.get("edges", [])
        edges = (edge_input if edge_input and isinstance(edge_input, list) and isinstance(edge_input[0], dict)
                 else [edge for value in (edge_input if isinstance(edge_input, list) else [edge_input])
                       for edge in _edges(value, base)])
        rows = module.screen(change, peers, deleted_ids=set(payload.get("deleted_ids", [])),
                             rules_path=_path(payload["rules"], base) if payload.get("rules") else None,
                             edges=edges)
        priority = {"blocking": 4, "insufficient evidence": 3, "manageable": 2,
                    "no shared field found": 1, "clear": 0}
        worst = max((row["status"] for row in rows), key=lambda status: priority.get(status, 0), default="manageable")
        return {"peers": rows, "worst_status": worst}
    if name == "dependents_digest":
        rows = [row for bundle in _bundles(payload) for row in _rows(bundle, base, "dependents.csv")]
        if not rows and "rows" in payload:
            rows = _rows(payload["rows"], base)
        change_set = _json(payload.get("change_set", {}), base)
        ids = {row.get("element", {}).get("nodeId") for row in change_set.get("elements", [])}
        return module.digest(rows, mode=payload["mode"], change_set=change_set, change_set_ids=ids,
                             rules_path=_path(payload["rules"], base) if payload.get("rules") else None)
    if name == "delete_order":
        change_set = _json(payload.get("change_set", {}), base)
        roots = [row["element"]["nodeId"] for row in change_set.get("elements", []) if row.get("action") == "delete"]
        references = payload.get("references", [])
        if isinstance(references, str):
            references = _edges(references, base)
        if references and isinstance(references[0], dict):
            references = [(row.get("nodeId"), row.get("inputNodeId")) if row.get("direction") == "incoming"
                          else (row.get("inputNodeId"), row.get("nodeId")) for row in references]
        return {"order": module.order(_dispositions(payload, base), roots, references=references)}
    if name == "plan_backlog":
        engagement = _path(payload["engagement"], base) if payload.get("engagement") else None
        delete_order = _json(payload.get("delete_order", []), base)
        if isinstance(delete_order, dict):
            delete_order = delete_order.get("order", [])
        return module.plan_backlog(_json(payload["change_set"], base), _dispositions(payload, base),
                                   delete_order=delete_order,
                                   findings=_json(payload.get("findings", []), base),
                                   answers=_json(payload.get("answers", []), base),
                                   requested_stories=_json(payload.get("requested_stories", []), base),
                                   engagement=engagement)
    if name == "finish_backlog":
        engagement = _path(payload["engagement"], base)
        if payload.get("incomplete"):
            incomplete = _json(payload["incomplete"], base)
            reason = incomplete.get("reason") if isinstance(incomplete, dict) else incomplete
            return module.incomplete_backlog(engagement, reason)
        return module.finish_backlog(_json(payload["plan"], base), _json(payload["drafts"], base),
                                     engagement, requirement=payload.get("requirement"),
                                     units=_dispositions(payload, base))
    if name == "option_evidence":
        candidate_name = "rows.ndjson" if payload["kind"] == "schema" else "dependents.csv"
        candidates = _rows(payload["candidate"], base, candidate_name)
        dependent_sources = payload.get("dependents", [])
        if not isinstance(dependent_sources, list):
            dependent_sources = [dependent_sources]
        dependents = [row for source in dependent_sources for row in _rows(source, base, "dependents.csv")]
        read_ids = set(payload.get("dependents_input_ids", []))
        for source in dependent_sources:
            if not isinstance(source, str):
                continue
            path = _path(source, base)
            manifest = (path if path.is_dir() else path.parent) / "manifest.json"
            if manifest.is_file():
                read_ids.update((json.loads(manifest.read_text(encoding="utf-8")).get("inputs") or {}).get("nodeIds") or [])
        fact_sources = payload.get("target_facts", [])
        if not isinstance(fact_sources, list) or (fact_sources and isinstance(fact_sources[0], dict)):
            fact_sources = [fact_sources]
        facts = [row for source in fact_sources for row in _rows(source, base, "nodes.ndjson")]
        return {"options": module.option_evidence(_json(payload["options"], base), candidates, dependents,
                                                   kind=payload["kind"], facts=facts,
                                                   dependents_gap=payload.get("dependents_gap"), read_ids=read_ids)}
    if name == "fire_chain_targets":
        fire = importlib.import_module("fire_chain")
        change_set = _json(payload["change_set"], base)
        edges = _edges(payload.get("write_edges", []), base)
        definitions = _json(payload.get("definitions", []), base)
        if isinstance(definitions, dict):
            definitions = definitions.get("records", [])
        return {"targets": fire.targets(change_set, edges, definitions)}
    if name == "fire_chain_digest":
        roots = [_path(bundle, base) for bundle in _bundles(payload)]
        statuses = payload.get("statuses", [])
        status = "partial" if "partial" in statuses else payload.get("status", "complete")
        return {"lines": module.digest(roots, status=status,
                                       touched_fields=set(payload.get("touched_fields", [])),
                                       change_set=_json(payload.get("change_set", {}), base))}
    raise ValueError(f"unknown command: {name}")


def main(name, argv=None):
    parser = SingleLineParser(description=__doc__)
    if name == "fire_chain":
        parser.add_argument("command", choices=("targets", "digest"))
    parser.add_argument("--in", dest="source", required=True, metavar="JSON")
    parser.add_argument("--out", required=True, metavar="JSON")
    args = parser.parse_args(argv)
    try:
        source = Path(args.source)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        command = name + "_" + args.command if name == "fire_chain" else name
        output = _calculate(command, payload, source.parent)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count = len(next((output[key] for key in ("forms", "options", "lines", "records", "entries", "targets", "units", "order", "elements", "peers", "stories")
                          if isinstance(output.get(key), list)), []))
        print(f"{count} results: {destination}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
