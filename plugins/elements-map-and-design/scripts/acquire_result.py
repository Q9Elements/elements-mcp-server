"""Acquire saved Model Context Protocol results and retain continuation evidence.

    python3 acquire_result.py generic --input REPLY.json --out COMPLETE.json [--append] [--node-ids ID,ID]
    python3 acquire_result.py native --input REPLY.json --out ROWS.ndjson

Generic mode restores moved values and merges nested list pages by component
nodeId and path. Nested cursors keep acquisition incomplete. Exit 1 prints the
continuation until a terminal page arrives. Native mode saves indexed parts
and failure coverage beside ROWS.ndjson as ROWS.ndjson.acquisition.json. Poll
running and follow nextPartsFrom with identical arguments and the same resultId.
"""
import argparse
import json
import hashlib
from pathlib import Path
from mcp_result import acquire_native, hydrate, native_errors, require_complete


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def merge_pages(previous, current):
    """Join paged lists at their original paths, using the current page's cursors."""
    if isinstance(previous, dict) and isinstance(current, dict):
        result = {key: value for key, value in previous.items()
                  if key not in ('_truncated', 'hasMore', 'nextSkip')}
        for key, value in current.items():
            result[key] = merge_pages(previous.get(key), value)
        return result
    if isinstance(previous, list) and isinstance(current, list):
        result = list(previous)
        nodes = {item['nodeId']: i for i, item in enumerate(result)
                 if isinstance(item, dict) and item.get('nodeId')}
        for item in current:
            node = item.get('nodeId') if isinstance(item, dict) else None
            if node in nodes:
                result[nodes[node]] = merge_pages(result[nodes[node]], item)
            elif item not in result:
                if node:
                    nodes[node] = len(result)
                result.append(item)
        return result
    return current


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('mode', choices=('generic', 'native'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--append', action='store_true')
    parser.add_argument('--node-ids')
    args = parser.parse_args(argv)
    reply = hydrate(json.loads(args.input.read_text()))
    if args.mode == 'native':
        register = args.out.with_name(args.out.name + '.acquisition.json')
        previous = json.loads(register.read_text()) if register.exists() else None
        result = acquire_native(reply, previous)
        save(register, result)
        errors = native_errors(result)
        if errors:
            print('PENDING ' + '; '.join(errors))
            print('CONTINUATION ' + json.dumps({k: result[k] for k in ('nextPartsFrom', 'retryAfterSeconds', 'failedFile') if k in result}))
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(''.join(json.dumps(row) + '\n' for row in result['rows']))
        result['savedSha256'] = hashlib.sha256(args.out.read_bytes()).hexdigest()
        save(register, result)
        print(f"COMPLETE {len(result['rows'])} rows; failure gaps: {json.dumps(result['failed'])}")
        return 0
    if args.append and args.out.exists():
        previous = json.loads(args.out.read_text())
        reply = merge_pages(previous, reply)
    # A final page clears continuation markers belonging to the earlier page.
    save(args.out, reply)
    require_complete(reply)
    items = reply.get('items') or []
    gaps = [item for item in items if item.get('error') or item.get('status') == 'failed']
    if args.node_ids:
        seen = {item.get('nodeId') for item in items}
        missing = set(args.node_ids.split(',')) - seen
        if missing:
            raise ValueError('missing requested node IDs: ' + ', '.join(sorted(missing)))
    print('COMPLETE; item gaps: ' + json.dumps(gaps))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        print('ACQUISITION ' + str(exc))
        raise SystemExit(1)
