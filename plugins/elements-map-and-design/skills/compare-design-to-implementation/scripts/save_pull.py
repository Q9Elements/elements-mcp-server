"""Acquire a native result page and record its status, parts and failure coverage.

    python3 save_pull.py ENG PULL TOOL --reply REPLY.json

Repeat with the same resultId after polling or requesting nextPartsFrom. Each
part is saved once as evidence/<PULL>-<INDEX>.ndjson. Exit 0 means complete
acquisition, 1 means pending or incomplete coverage, and 2 means setup failure.
The register preserves failed records as explicit evidence gaps.
"""
import argparse
import sys
from pathlib import Path

import common
from common import write_json
from mcp_result import acquire_native, native_errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('eng', type=Path)
    parser.add_argument('pull')
    parser.add_argument('tool')
    parser.add_argument('--reply', required=True, type=Path)
    args = parser.parse_args(argv)
    pulls = common.load_pulls(args.eng)
    import json
    reply = json.loads(args.reply.read_text())
    previous = pulls.get(args.pull)
    result = acquire_native(reply, previous)
    result['tool'] = args.tool
    for index, rows in result['partRows'].items():
        path = args.eng / 'evidence' / f'{args.pull}-{index}.ndjson'
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        path.write_text(result['partData'][str(index)], encoding='utf-8')
        # The saved bytes preserve the verified descriptor digest.
        part = next(part for part in result['parts'] if str(part['index']) == index)
        part['sha256'] = common.sha256(path)
        part['rows'] = len(rows)
    pulls[args.pull] = result
    write_json(args.eng / 'evidence/pulls.json', pulls)
    errors = native_errors(result)
    if errors:
        print('PENDING ' + '; '.join(errors))
        if result.get('nextPartsFrom') is not None:
            print(f"NEXT partsFrom {result['nextPartsFrom']}")
        return 1
    print(f"SAVED {args.pull}: {result['totalRows']} rows; {len(result['failed'])} failure gap(s)")
    return 0


if __name__ == '__main__':
    common.run(main)
