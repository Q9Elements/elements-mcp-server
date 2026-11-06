#!/usr/bin/env python3
"""Usage: python3 scripts/fetch_parts.py RESPONSE_JSON OUTPUT_DIR

Download and verify newline-delimited JavaScript Object Notation (NDJSON) parts.
Exit 0: complete and verified; read saved parts and report accounted failures.
Exit 1: invalid input, verification failure or failed job; fix/re-run or follow its instruction.
Exit 2: fetch failure; repeat the same tool call for fresh links and re-run.
Exit 3: pending acquisition; follow the printed cursor or wait and repeat the call.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen


def verify(data, descriptor):
    if descriptor['format'] != 'ndjson':
        raise ValueError('select format ndjson in the tool call')
    if len(data) != descriptor['bytes']:
        raise ValueError('byte count mismatch')
    if hashlib.sha256(data).hexdigest() != descriptor['sha256']:
        raise ValueError('sha256 mismatch')
    rows = [json.loads(line) for line in data.decode('utf-8').split('\n') if line.strip()]
    if len(rows) != descriptor['rows']:
        raise ValueError('row count mismatch')
    return rows


def download(descriptor, target):
    if target.exists():
        data = target.read_bytes()
        # A refreshed failure file can change independently of the row parts.
        if hashlib.sha256(data).hexdigest() == descriptor['sha256']:
            return verify(data, descriptor)
    try:
        # A local fetch bound prevents an unreachable host from hanging the command.
        with urlopen(descriptor['url'], timeout=60) as stream:
            data = stream.read()
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError(f'{exc}; repeat the same call for fresh links and re-run.') from exc
    rows = verify(data, descriptor)
    target.write_bytes(data)
    return rows


class FetchError(Exception):
    pass


def nonnegative(value):
    return type(value) is int and value >= 0


def validate(reply):
    if not isinstance(reply, dict) or reply.get('status') not in ('running', 'complete', 'failed'):
        raise ValueError('save the parsed, hydrated native response object')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', reply.get('resultId', '')):
        raise ValueError('resultId must be a 64-hex file identifier')
    if reply['status'] == 'failed':
        return
    for key in ('totalRows', 'partsTotal'):
        if not nonnegative(reply.get(key)):
            raise ValueError(f'{key} must be a nonnegative integer')
    if not isinstance(reply.get('parts'), list) or not isinstance(reply.get('failed'), list):
        raise ValueError('hydrate parts and failed as arrays')
    if any(not isinstance(f, dict) for f in reply['failed']):
        raise ValueError('failed entries must be objects')
    total = reply.get('failedTotal', len(reply['failed']))
    if not nonnegative(total) or total < len(reply['failed']):
        raise ValueError('failedTotal contradicts inline failures')
    if 'nextPartsFrom' in reply and not nonnegative(reply['nextPartsFrom']):
        raise ValueError('nextPartsFrom must be a nonnegative integer')
    for part in reply['parts']:
        if not isinstance(part, dict) or not nonnegative(part.get('index')):
            raise ValueError('part index must be a nonnegative integer')
        if part['index'] >= reply['partsTotal']:
            raise ValueError('part index exceeds partsTotal')
    for part in reply['parts'] + ([reply['failedFile']] if reply.get('failedFile') else []):
        if not isinstance(part, dict) or any(not nonnegative(part.get(k)) for k in ('bytes', 'rows')):
            raise ValueError('part bytes and rows must be nonnegative integers')
        if not isinstance(part.get('url'), str) or not re.fullmatch(r'[a-f0-9]{64}', part.get('sha256', '')):
            raise ValueError('part needs its returned url and sha256')
        if part.get('format') != 'ndjson':
            raise ValueError('select format ndjson in the tool call')
        if not isinstance(part.get('expiresInSeconds'), (int, float)):
            raise ValueError('part needs its returned expiresInSeconds')
        if part['expiresInSeconds'] <= 0:
            raise FetchError('Expired link; repeat the same call for fresh links and re-run.')


def reply_provenance(reply):
    """Keep the identity of the reply that verified a part's descriptor."""
    return {key: reply.get(key) for key in ('resultId', 'status', 'computedAt')}


def matches_completion(state, key, reply):
    """Require a completed descriptor, with identity for reuse across replies."""
    origin = state.get('provenance', {}).get(key, {})
    if origin.get('status') != 'complete' or origin.get('resultId') != reply.get('resultId'):
        return False
    if reply.get('computedAt'):
        return origin.get('computedAt') == reply['computedAt']
    # Without a completion identity, only this reply can attest its own parts.
    return any(str(part['index']) == key for part in reply['parts'])


def acquire(reply, output):
    validate(reply)
    output.mkdir(parents=True, exist_ok=True)
    if reply['status'] == 'failed':
        print(f"Failed: {reply.get('error')} {reply.get('message', '')}; "
              f"stop this attempt and follow: {reply.get('instruction', 'report the failure')}.")
        return 1
    state_path = output / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'parts': {}}
    if any(not index.isdecimal() for index in state['parts']):
        raise ValueError('invalid saved state; use a fresh output directory')
    changed = state.get('resultId') != reply['resultId'] or (
        state.get('computedAt') and reply.get('computedAt') and
        state['computedAt'] != reply['computedAt'])
    changed = changed or any(
        str(p['index']) in state['parts'] and
        any(state['parts'][str(p['index'])][key] != p[key]
            for key in ('sha256', 'bytes', 'rows', 'format')) for p in reply['parts'])
    if changed:
        for index in state['parts']:
            (output / f'part-{index}.ndjson').unlink(missing_ok=True)
        (output / 'failed.ndjson').unlink(missing_ok=True)
        state = {'parts': {}}
    state['resultId'] = reply['resultId']
    if reply.get('computedAt'):
        state['computedAt'] = reply['computedAt']
    provenance = state.setdefault('provenance', {})
    for part in reply['parts']:
        target = output / f"part-{part['index']}.ndjson"
        download(part, target)
        state['parts'][str(part['index'])] = part
        provenance[str(part['index'])] = reply_provenance(reply)
        state_path.write_text(json.dumps(state))
    state_path.write_text(json.dumps(state))
    failures = reply['failed']
    if reply.get('failedFile'):
        failures = download(reply['failedFile'], output / 'failed.ndjson')
        if any(f not in failures for f in reply['failed']):
            raise ValueError('failedFile disagrees with inline failures')
    (output / 'failures.json').write_text(json.dumps(failures))
    if len(failures) > reply.get('failedTotal', len(failures)):
        raise ValueError('failedTotal contradicts failedFile')
    if len(failures) != reply.get('failedTotal', len(failures)):
        print('Incomplete failure list; repeat the same call for failedFile and re-run.')
        return 3
    if 'nextPartsFrom' in reply:
        print(f"Repeat the call with partsFrom:{reply['nextPartsFrom']}; re-run.")
        return 3
    if reply['status'] == 'running':
        # The native helper's polling hint defaults to 30 seconds.
        print(f"wait {reply.get('retryAfterSeconds', 30)} seconds; repeat the same call and re-run.")
        return 3
    indices = set(range(reply['partsTotal']))
    held = {int(index) for index in state['parts']}
    if held - indices:
        raise ValueError('unexpected part index; use a fresh output directory')
    unconfirmed = {int(key) for key in state['parts']
                   if not matches_completion(state, key, reply)}
    if (indices - held) | unconfirmed:
        print(f'Repeat the call with partsFrom:{min((indices - held) | unconfirmed)}; '
              'acquire or confirm completed descriptors and re-run.')
        return 3
    rows = 0
    for index, part in state['parts'].items():
        rows += len(verify((output / f'part-{index}.ndjson').read_bytes(), part))
    if rows != reply['totalRows']:
        raise ValueError('totalRows mismatch')
    print(f'Complete and verified; {len(failures)} failed nodes. Read saved parts and report failures.json.')
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f'{message}; supply RESPONSE_JSON and OUTPUT_DIR, then re-run.\n')


def main():
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('response_json', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    try:
        return acquire(json.loads(args.response_json.read_text()), args.output_dir)
    except FetchError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f'{exc}; correct the input and re-run.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
