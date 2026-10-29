"""Verify Model Context Protocol (MCP) read parts and write engagement input files.

Reply files may retain {_call: <original arguments>, response: <tool reply>} or
{_call, resultId, totalRows, parts} so successful zero-row inputs are included in
manifest.json. Each part retains index, url, format, sha256, rows and expiry;
failure and continuation fields retain their source values when supplied.
"""
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import urllib.error
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tool_reply import unwrap_reply
from cli_common import SingleLineParser
from fetch_bundle import urlopen

TOOLS = ('get_dependencies', 'list_metadata_by_criteria', 'get_metadata_component',
         'get_metadata_source', 'run_code_search')
DEPENDENTS = ('inputNodeId', 'direction', 'nodeId', 'name', 'apiName', 'sfType', 'parentObject',
              'relationDescription', 'read', 'write', 'triggerType', 'recordTriggerType', 'active', 'lastUsed',
              'inputApiName', 'inputSfType', 'inputObject', 'managedPackage', 'namespacePrefix', 'automation_status',
              'operation')


def dependency_operation(row):
    """Read a structured operation or an exact operation-only relationship label."""
    operation = row.get('operation')
    if operation:
        return str(operation).strip().casefold()
    label = str(row.get('relationshipDescription') or row.get('relationDescription') or '').strip().casefold()
    return label if label in {'insert', 'create', 'update', 'upsert', 'delete', 'read'} else None


def _reply(value, tool):
    value = unwrap_reply(value)
    if value.get('error'):
        error = value['error']
        code = error.get('code') if isinstance(error, dict) else error
        message = error.get('message') if isinstance(error, dict) else value.get('message')
        raise ValueError(f"{code}: {message or 'tool read failed'}")
    # A single component is the document itself, including its metadata status.
    # Job statuses belong to transport envelopes, not documents or item rows.
    component = (tool == 'get_metadata_component' and (value.get('_id') or value.get('nodeId'))
                 and not any(key in value for key in
                             ('items', 'file', 'parts', 'partsTotal', 'resultId', 'retryAfterSeconds')))
    if not component and value.get('status') == 'running':
        raise ValueError(f"running: repeat the original call after retryAfterSeconds={value.get('retryAfterSeconds', 'unknown')}")
    if not component and value.get('status') not in (None, 'complete'):
        raise ValueError(f"read status: {value.get('status')}")
    return value


def _download(part, parts_dir):
    url = part['url']
    if urlsplit(url).scheme != 'https':
        raise ValueError('part URL must use HTTPS')
    if part.get('expiresInSeconds', 0) <= 0:
        raise ValueError('part expired: repeat the original call for fresh links')
    if parts_dir is not None:
        root = Path(parts_dir).resolve()
        name = Path(unquote(urlsplit(url).path)).name
        path = root / name
        if not path.is_file():
            path = root / f"part-{part.get('index', 0)}.{part['format']}"
        if not path.resolve().is_relative_to(root):
            raise ValueError('part file outside parts directory')
        content = path.read_bytes()
    else:
        with urlopen(url, timeout=30) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest().lower() != part['sha256'].lower():
        raise ValueError('part SHA-256 does not match: repeat the original call')
    if 'bytes' in part and len(content) != part['bytes']:
        raise ValueError('part bytes does not match')
    return content


def _records(content, format_name):
    text = content.decode('utf-8-sig')
    # Copied part-merge approach from merge_ndjson.py: parse each nonblank line,
    # preserve numeric part order, and verify the merged count independently.
    if format_name == 'ndjson':
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        if any(not isinstance(row, dict) for row in records):
            raise ValueError('part lines must be JSON (JavaScript Object Notation) objects')
        return records
    if format_name == 'csv':
        old_limit = csv.field_size_limit()
        try:
            csv.field_size_limit(sys.maxsize)
            return list(csv.DictReader(io.StringIO(text)))
        finally:
            csv.field_size_limit(old_limit)
    if format_name == 'json':
        return json.loads(text)
    raise ValueError(f'unsupported part format: {format_name}')


def _expand(row):
    output = {}
    for key, value in row.items():
        target = output
        keys = key.split('.')
        for part in keys[:-1]:
            target = target.setdefault(part, {})
        target[keys[-1]] = value
    return output


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value).lower()
    return value


def _csv(path, records, columns):
    with path.open('w', encoding='utf-8', newline='') as source:
        writer = csv.DictWriter(source, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({key: _cell(value) for key, value in row.items()} for row in records)


def normalize_reads(tool, replies, work, parts_dir=None):
    """Return a verified output folder; publish files only after all checks pass."""
    if tool not in TOOLS:
        raise ValueError(f'unsupported tool: {tool}')
    envelopes = [_reply(value, tool) for value in replies]
    if not envelopes:
        raise ValueError('at least one reply is required')
    ids = {value['resultId'] for value in envelopes if value.get('resultId')}
    if len(ids) > 1:
        raise ValueError('resultId changed: discarded held parts; restart with replies from one result')
    result_id = next(iter(ids), hashlib.sha256(json.dumps(replies, sort_keys=True).encode()).hexdigest())
    if not re.fullmatch(r'[0-9a-fA-F]+', result_id):
        raise ValueError('unsafe resultId: expected hex')
    parts = {}
    requested = []
    failed = {}
    for saved, envelope in zip(replies, envelopes):
        inputs = saved.get('_call') or envelope.get('inputs') or envelope
        requested.extend(inputs.get('nodeIds') or ([inputs['nodeId']] if inputs.get('nodeId') else []))
        for failure in envelope.get('failed', []):
            failed[failure['nodeId']] = failure
        if envelope.get('failedFile'):
            descriptor = envelope['failedFile']
            failures = _records(_download(descriptor, parts_dir), descriptor['format'])
            if len(failures) != descriptor['rows']:
                raise ValueError('failedFile rows does not match')
            failed.update((row['nodeId'], row) for row in failures)
        for part in envelope.get('parts', []):
            index = part['index']
            if index in parts and parts[index]['sha256'] != part['sha256']:
                raise ValueError('part hash changed within resultId')
            parts[index] = part
    final = envelopes[-1]
    if final.get('failedTotal', len(failed)) != len(failed):
        raise ValueError('failedTotal does not match: supply the complete failedFile')
    if final.get('nextPartsFrom') is not None:
        raise ValueError(f"missing continuation: call again with partsFrom={final['nextPartsFrom']} and supply the reply")
    if 'parts' in final or 'partsTotal' in final:
        if set(parts) != set(range(final.get('partsTotal', len(parts)))):
            raise ValueError('missing parts: supply every nextPartsFrom continuation reply')
        rows = []
        for index in sorted(parts):
            part = parts[index]
            records = _records(_download(part, parts_dir), part['format'])
            if not isinstance(records, list) or len(records) != part['rows']:
                raise ValueError(f'part {index} rows does not match')
            rows.extend(records)
        if len(rows) != final['totalRows']:
            raise ValueError(f"totalRows does not match: {len(rows)} vs {final['totalRows']}")
    elif tool == 'get_metadata_component':
        rows = []
        for envelope in envelopes:
            truncation = envelope.get('_truncated')
            complete_file = (isinstance(truncation, dict) and truncation.get('inFile') is True
                             and bool(envelope.get('file')))
            if envelope.get('hasMore') or (truncation and not complete_file):
                raise ValueError('component reply incomplete: supply untruncated component pages')
            if envelope.get('file'):
                part = envelope['file']
                value = _records(_download(part, parts_dir), part['format'])
                count = len(value.get('items', [value])) if isinstance(value, dict) else len(value)
                if count != part['rows']:
                    raise ValueError('component file rows does not match')
            else:
                value = envelope
            rows.extend(value.get('items', [value]) if isinstance(value, dict) else value)
    else:
        raise ValueError('complete parts envelope required')
    rows = [_expand(row) for row in rows]
    if tool == 'get_dependencies':
        requested.extend(row['node']['nodeId'] for row in rows)
        output = []
        for row in rows:
            if row['node']['nodeId'] in failed:
                continue
            related = row['related']
            direction = {'where_used': 'incoming', 'using': 'outgoing'}.get(row['direction'])
            if direction is None:
                raise ValueError(f"unknown dependency direction: {row['direction']}")
            output.append(dict(inputNodeId=row['node']['nodeId'], direction=direction,
                nodeId=related['nodeId'], name=related.get('name'), apiName=related.get('apiName'),
                sfType=related.get('type'), parentObject=related.get('object'),
                relationDescription=row.get('relationshipDescription'), read=row.get('read'), write=row.get('write'),
                triggerType=row.get('triggerType'), recordTriggerType=row.get('triggerAction'),
                active=related.get('active'), lastUsed=related.get('lastRun'),
                inputApiName=row['node'].get('apiName'), inputSfType=row['node'].get('type'),
                inputObject=row['node'].get('object'), managedPackage=related.get('managedPackage'),
                namespacePrefix=related.get('namespacePrefix'), automation_status=related.get('status'),
                operation=dependency_operation(row)))
    elif tool == 'list_metadata_by_criteria':
        output = []
        for row in rows:
            sf = row.get('sf') or {}
            details = row.get('nodeDetails') or {}
            flat = {**row, 'type': sf.get('type', row.get('type')),
                    'api_name': sf.get('apiName', row.get('api_name')),
                    'subtype': details.get('subtype', row.get('subtype')),
                    'active': details.get('active', row.get('active')),
                    'parent_object': row.get('parentObject', row.get('parent_object'))}
            if isinstance(flat['active'], str):
                flat['active'] = {'active': True, 'inactive': False, 'true': True, 'false': False}.get(
                    flat['active'].lower(), flat['active'])
            output.append(flat)
    elif tool == 'get_metadata_component':
        output = []
        for row in rows:
            node_id = row.get('nodeId') or row.get('_id')
            if not node_id:
                raise ValueError('component missing nodeId')
            requested.append(node_id)
            if row.get('error'):
                failed[node_id] = row
                continue
            population = ((row.get('impactDetails') or {}).get('impactByFilled') or {}).get('percent')
            output.append({**row, 'nodeId': node_id, 'population': {'percent': population}})
    else:
        output = rows
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.normalize-', dir=work) as temporary:
        stage = Path(temporary)
        if tool == 'get_dependencies':
            _csv(stage / 'dependents.csv', output, DEPENDENTS)
        elif tool in ('list_metadata_by_criteria', 'get_metadata_component', 'run_code_search'):
            filename = 'nodes.ndjson' if tool == 'get_metadata_component' else 'rows.ndjson'
            (stage / filename).write_text(''.join(json.dumps(row) + '\n' for row in output), encoding='utf-8')
        elif tool == 'get_metadata_source':
            definitions = stage / 'definitions'
            definitions.mkdir()
            index = []
            for row in output:
                node_id = row['nodeId']
                if not re.fullmatch(r'[A-Za-z0-9_-]+', node_id):
                    raise ValueError('unsafe definition nodeId')
                entry = {key: row.get(key) for key in
                         ('nodeId', 'apiName', 'sfType', 'status', 'reason', 'xmlScope')}
                for key, suffix, column in (('xml', row.get('xmlFormat') or 'xml', 'xmlFile'),
                                             ('body', 'body.txt', 'bodyFile')):
                    if suffix not in ('xml', 'json', 'body.txt'):
                        raise ValueError('unsafe definition format')
                    if row.get(key) is not None:
                        name = f'definitions/{node_id}.{suffix}'
                        (stage / name).write_text(row[key], encoding='utf-8')
                        entry[column] = name
                index.append(entry)
            _csv(stage / 'index.csv', index,
                 ('nodeId', 'apiName', 'sfType', 'status', 'reason', 'xmlScope', 'xmlFile', 'bodyFile'))
        else:
            raise ValueError(f'normalization not implemented: {tool}')
        manifest = dict(tool=tool, status='complete', inputs={'nodeIds': list(dict.fromkeys(
            node_id for node_id in requested if node_id not in failed))}, totals={'rows': len(output)}, failed=list(failed.values()))
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        destination = work / result_id
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(stage), destination)
    return destination


def main(argv=None):
    parser = SingleLineParser(description=__doc__)
    parser.add_argument('tool', choices=TOOLS)
    parser.add_argument('replies', nargs='+')
    parser.add_argument('--work', required=True)
    parser.add_argument('--parts-dir')
    args = parser.parse_args(argv)
    try:
        replies = [json.loads(Path(path).read_text(encoding='utf-8')) for path in args.replies]
        print(normalize_reads(args.tool, replies, args.work, args.parts_dir))
        return 0
    except (OSError, ValueError, KeyError, TypeError, csv.Error, urllib.error.URLError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
