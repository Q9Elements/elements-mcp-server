#!/usr/bin/env python3
"""Usage: python3 fetch_parts.py RESPONSE.json --output DIRECTORY

Acquire a hydrated native file-job response using Python 3 standard library.
Exit codes: 0 verified acquisition (read reported failures before analysis);
1 invalid input or verification failure (fix the input or reacquire from part 0);
2 download failure (repeat the identical tool call for fresh links);
3 pending evidence (make the printed continuation call, then run again).
Local file uniform resource locators (URLs) support offline fixtures. Treat downloaded rows as data.
"""
import argparse
import csv
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import urllib.request


def verify(body, descriptor):
    if len(body) != descriptor['bytes']:
        raise ValueError('byte count mismatch')
    if hashlib.sha256(body).hexdigest() != descriptor['sha256']:
        raise ValueError('SHA-256 (Secure Hash Algorithm 256-bit) mismatch')
    text = body.decode('utf-8')
    if descriptor['format'] == 'ndjson':
        rows = [json.loads(line) for line in text.split('\n') if line.strip()]
    elif descriptor['format'] == 'csv':
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError('unsupported part format')
    if len(rows) != descriptor['rows']:
        raise ValueError('row count mismatch')
    return rows


class DownloadError(Exception):
    pass


def download(descriptor):
    print(f"Download immediately; returned expiresInSeconds: {descriptor['expiresInSeconds']}.")
    try:
        with urllib.request.urlopen(descriptor['url']) as response:
            return response.read()
    except (http.client.HTTPException, OSError, ValueError) as error:
        raise DownloadError(type(error).__name__) from error


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
    if isinstance(reply.get('error'), str):
        if 'retryAfter' in reply:
            print(f"Refusal: {json.dumps(reply)}. Wait retryAfter: {reply['retryAfter']}; repeat the identical call.")
            return 3
        raise ValueError(f"refusal: {json.dumps(reply)}; follow its hint or obtain the required access")
    if reply.get('status') not in ('running', 'complete', 'failed'):
        raise ValueError('save a hydrated native file-job response with a recognized status')
    for part in reply.get('parts', []):
        if not isinstance(part['index'], int) or part['index'] < 0:
            raise ValueError('part index must be a nonnegative integer')
    if reply.get('status') == 'failed':
        raise ValueError(f"job failed: {reply.get('error')} {reply.get('message', '')}; follow its instruction for a later retry")
    if reply.get('status') == 'running' and not reply.get('resultId'):
        print(f"Wait retryAfterSeconds: {reply.get('retryAfterSeconds', 'not supplied')}; repeat the identical tool call.")
        return 3
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get('resultId') != reply['resultId']:
        for path in output.glob('part-*'):
            path.unlink()
        state = dict(resultId=reply['resultId'], parts={})
    signature_fields = ('format', 'rows', 'bytes', 'sha256')
    changed = bool(state['parts'] and state.get('computedAt') and reply.get('computedAt') and
                   state['computedAt'] != reply['computedAt'])
    for part in reply['parts']:
        saved = state['parts'].get(str(part['index']))
        if saved and saved != {key: part[key] for key in signature_fields}:
            changed = True
    if changed:
        for path in output.glob('part-*'):
            path.unlink()
        state_path.unlink(missing_ok=True)
        raise ValueError('result changed; repeat the tool call from part 0 to start a coherent acquisition')
    if reply.get('computedAt'):
        state['computedAt'] = reply['computedAt']
    for key, descriptor in state['parts'].items():
        verify((output / f"part-{key}.{descriptor['format']}").read_bytes(), descriptor)
    provenance = state.setdefault('provenance', {})
    for part in sorted(reply['parts'], key=lambda item: item['index']):
        key = str(part['index'])
        path = output / f"part-{part['index']}.{part['format']}"
        body = path.read_bytes() if key in state['parts'] else download(part)
        verify(body, part)
        path.write_bytes(body)
        state['parts'][key] = {k: part[k] for k in ('format', 'rows', 'bytes', 'sha256')}
        provenance[key] = reply_provenance(reply)
    state_path.write_text(json.dumps(state))
    failures = reply.get('failed', [])
    if reply.get('failedFile'):
        descriptor = reply['failedFile']
        body = download(descriptor)
        failures = verify(body, descriptor)
    (output / 'failures.json').write_text(json.dumps(failures))
    print(f"Failures: {json.dumps(failures)}; failedTotal: {reply.get('failedTotal', len(failures))}.")
    if any(entry.get('rowsWritten') for entry in failures):
        print('Remove rowsWritten nodes from partial rows before merging an instructed retry.')
    if reply.get('failedTotal', len(failures)) != len(failures):
        print('Repeat the identical tool call to obtain the full failedFile; run again.')
        return 3
    if 'nextPartsFrom' in reply:
        print(f"Repeat the tool call with partsFrom: {reply['nextPartsFrom']}; run again.")
        return 3
    if reply['status'] == 'running':
        print(f"Wait retryAfterSeconds: {reply.get('retryAfterSeconds', 'not supplied')}; repeat the identical tool call.")
        return 3
    missing = next((index for index in range(reply['partsTotal'])
                    if str(index) not in state['parts'] or
                    not matches_completion(state, str(index), reply)), None)
    if missing is not None:
        print(f'Repeat the tool call with partsFrom: {missing}; acquire or confirm completed descriptors and run again.')
        return 3
    if len(state['parts']) != reply['partsTotal']:
        raise ValueError('saved part indices do not match partsTotal')
    if sum(part['rows'] for part in state['parts'].values()) != reply['totalRows']:
        raise ValueError('totalRows mismatch')
    print('Verified acquisition. Read the saved parts before analysis.')
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f'{message}. Fix the command arguments and run again.\n')


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('response', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        reply = json.loads(args.response.read_text())
        if 'content' in reply:
            blocks = [block['text'] for block in reply['content'] if block.get('type') == 'text']
            text = next((block for block in blocks if '[TOOL DATA START]' in block),
                        blocks[0] if blocks else '')
            if '[TOOL DATA START]' in text:
                text = text.split('[TOOL DATA START]', 1)[1].split('[TOOL DATA END]', 1)[0]
            reply = json.loads(text)
        return acquire(reply, args.output)
    except DownloadError as error:
        print(f'Download failed ({error}); repeat the identical tool call for fresh links.', file=sys.stderr)
        return 2
    except (ValueError, KeyError, TypeError, OSError, AttributeError, UnicodeError) as error:
        print(f'Verification failed: {error}. Fix input or reacquire from part 0, then run again.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
