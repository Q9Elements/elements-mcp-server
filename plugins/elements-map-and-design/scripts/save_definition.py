"""Save an automation's acquired stored source with availability and sync provenance.

    python3 save_definition.py --rows SOURCE.ndjson --node-id ID --type TYPE --out-dir DIR [--component NAME]

TYPE is a local automation type key in data/automation-types.csv. Acquire the
complete get_metadata_source job before running this command. Source gaps are
recorded in source.json for the logic reader and the report.
"""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def save_definition(row, out, kind, component=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {'producer': 'get_metadata_source', 'nodeId': row.get('nodeId'),
              'status': row.get('status'), 'reason': row.get('reason'),
              'sourceVersion': {key: value for key, value in row.items() if key not in ('xml', 'body')},
              'gaps': [], 'files': {}}
    if row.get('status') != 'ok' or row.get('reason'):
        result['gaps'].append(row.get('reason') or row.get('status') or 'no_stored_definition')
    xml = row.get('xml')
    if kind in ('apex-class', 'apex-trigger'):
        if xml:
            (out / 'metadata.xml').write_text(xml)
            result['files']['metadata'] = 'metadata.xml'
        body = row.get('body')
        if body:
            name = 'definition.cls' if kind == 'apex-class' else 'definition.trigger'
            (out / name).write_text(body)
            result['files']['definition'] = name
        elif 'managed_code_hidden' not in result['gaps']:
            result['gaps'].append('no_stored_definition')
    elif xml:
        if row.get('xmlScope') == 'object':
            tag = {'workflow-rule': 'rules', 'validation-rule': 'validationRules',
                   'assignment-rule': 'assignmentRule', 'auto-response-rule': 'autoResponseRule',
                   'escalation-rule': 'escalationRule'}.get(kind)
            root = ET.fromstring(xml)
            matches = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == tag and any(
                child.tag.rsplit('}', 1)[-1] == 'fullName' and child.text == component for child in node)]
            if len(matches) != 1:
                result['gaps'].append('whole-object source requires one confirmed component name')
                xml = None
            else:
                xml = ET.tostring(matches[0], encoding='unicode')
        if xml:
            name = ('definition.flow-meta.xml' if kind in ('flow', 'process-builder') else
                    'definition.json' if row.get('xmlFormat') == 'json' else 'definition.xml')
            (out / name).write_text(xml)
            result['files']['definition'] = name
    else:
        result['gaps'].append('no_stored_definition')
    result['gaps'] = list(dict.fromkeys(result['gaps']))
    (out / 'source.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--rows', type=Path, required=True)
    parser.add_argument('--node-id', required=True)
    parser.add_argument('--type', required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--component')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.rows.read_text().splitlines() if line.strip()]
    found = [row for row in rows if row.get('nodeId') == args.node_id]
    if len(found) != 1:
        parser.error('source must contain one row for the chosen node; report the source gap')
    print(json.dumps(save_definition(found[0], args.out_dir, args.type, args.component), indent=2))


if __name__ == '__main__':
    main()
