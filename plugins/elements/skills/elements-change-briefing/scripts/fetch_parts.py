#!/usr/bin/env python3
"""Acquire native newline-delimited JavaScript Object Notation (NDJSON) parts.

Usage: fetch_parts.py REPLY_JSON_OR_- CACHE_DIR [--capture-dir DIRECTORY]
Read one parsed, hydrated JavaScript Object Notation (JSON) reply from
list_metadata_changes, append it to the capture, then download unchanged part bytes. Standard library only; no tool calls.
Exit 0: run the printed merge command. Exit 3: make the printed continuation call.
Exit 2: repeat the same call for fresh links after a failed fetch.
Exit 1: correct the capture or reconcile verification/failure evidence, then retry.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import shlex
import re
import sys
from urllib.request import urlopen
from urllib.error import URLError

from merge_ndjson import capture_parts, nonnegative


def verify(data, part):
    if part['format'] != 'ndjson':
        raise ValueError('select format ndjson')
    if hashlib.sha256(data).hexdigest() != part['sha256'].lower():
        raise ValueError('sha256 mismatch')
    if len(data) != part['bytes']:
        raise ValueError('byte count mismatch')
    rows = [json.loads(line) for line in data.decode('utf-8').split('\n') if line.strip()]
    if len(rows) != part['rows']:
        raise ValueError('row count mismatch')
    if any(not isinstance(row, dict) for row in rows) or '$$__tp__' in data.decode('utf-8'):
        raise ValueError('invalid object rows or placeholder leakage')


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


def acquire(args):
    reply = json.loads(sys.stdin.read() if args.reply == '-' else Path(args.reply).read_text())
    directory = Path(args.capture_dir or args.cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    capture = directory / 'changes-capture.json'
    replies = json.loads(capture.read_text()) if capture.exists() else []
    if not re.fullmatch(r'[0-9a-fA-F]{64}', reply['resultId']):
        raise ValueError('resultId must be a 64-character hexadecimal computation identity')
    changed = bool(replies and replies[-1]['resultId'] != reply['resultId'])
    # Keep one coherent attempt, comparing content independently of refreshed links.
    held = {part['index']: part for segment in replies for part in segment.get('parts', [])}
    completed_at = next((segment['computedAt'] for segment in reversed(replies)
                         if segment.get('computedAt')), None)
    reset = (changed or bool(completed_at and reply.get('computedAt') and
                            completed_at != reply['computedAt']) or
             any(part['index'] in held and any(held[part['index']][key] != part[key]
                 for key in ('format', 'sha256', 'bytes', 'rows')) for part in reply.get('parts', [])))
    if reset:
        replies = []
        for held_file in directory.glob('changes-*-part-*.ndjson'):
            held_file.unlink()
    replies.append(reply)
    capture.write_text(json.dumps(replies, indent=2) + '\n', encoding='utf-8')
    if changed:
        for held in directory.glob('changes-*-part-*.ndjson'):
            held.unlink()
        if reply['status'] != 'failed':
            print('Identity changed; call list_metadata_changes with the same selection and partsFrom 0.')
            return 3
    downloads = [(part, f"part-{nonnegative(part['index'], 'index')}") for part in reply.get('parts', [])]
    if reply.get('failedFile'):
        downloads.append((reply['failedFile'], 'failed'))
    fetch_failed = False
    for part, suffix in downloads:
        target = directory / f"changes-{reply['resultId']}-{suffix}.ndjson"
        if target.exists():
            try:
                verify(target.read_bytes(), part)
                continue
            except ValueError:
                pass
        # Bound a stalled file read so the caller can refresh links and retain partial evidence.
        try:
            with urlopen(part['url'], timeout=60) as response:
                data = response.read()
        except (URLError, OSError, http.client.HTTPException):
            print('Fetch failed; repeat the same call and descriptor cursor for fresh links, then retry.')
            fetch_failed = True
            continue
        verify(data, part)
        target.write_bytes(data)
    if reply['status'] == 'failed':
        print(f"Failed job: {reply.get('error')}: {reply.get('message')}; follow instruction and retry guidance.")
        return 1
    if fetch_failed:
        return 2
    if reply.get('failed') or reply.get('failedTotal') or reply.get('failedFile'):
        print('Partial capture; reconcile failures and rowsWritten in isolated retries, then retry.')
        return 1
    if reply['status'] not in ('running', 'complete'):
        raise ValueError('unsupported status')
    if 'nextPartsFrom' in reply:
        cursor = nonnegative(reply['nextPartsFrom'], 'nextPartsFrom')
        if not reply['parts'] or cursor <= max(part['index'] for part in reply['parts']):
            raise ValueError('non-advancing descriptor cursor')
    if reply['status'] == 'running':
        nonnegative(reply['retryAfterSeconds'], 'retryAfterSeconds')
    if reply['status'] == 'running' or 'nextPartsFrom' in reply:
        delay = (f" after {reply['retryAfterSeconds']} seconds" if reply['status'] == 'running' else '')
        cursor = f" with partsFrom {reply['nextPartsFrom']}" if 'nextPartsFrom' in reply else ''
        print(f'Call list_metadata_changes again{delay}, keeping the selection fixed{cursor}.')
        return 3
    provenance = {str(part['index']): reply_provenance(segment)
                  for segment in replies for part in segment.get('parts', [])}
    unconfirmed = next((index for index in range(nonnegative(reply['partsTotal'], 'partsTotal'))
                        if not matches_completion({'provenance': provenance}, str(index), reply)), None)
    if unconfirmed is not None:
        print(f'Call list_metadata_changes with partsFrom {unconfirmed} to confirm completed descriptors, then retry.')
        return 3
    identity, descriptors, final = capture_parts(capture)
    total = 0
    for index, descriptor in descriptors.items():
        data = (directory / f'changes-{identity}-part-{index}.ndjson').read_bytes()
        verify(data, descriptor)
        total += descriptor['rows']
    if total != final['totalRows'] or total != final['totalItems']:
        raise ValueError('final counts disagree with verified parts')
    command = ['python3', str(Path(__file__).with_name('merge_ndjson.py')), str(directory),
               str(directory / 'changes-master.ndjson'), '--capture', str(capture),
               '--expected', str(reply['totalItems']), '--key', 'changeLogId']
    print('Complete; run: ' + shlex.join(command))
    return 0


class RecoveryParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f'{message}; run --help, correct arguments, then retry.\n')


def main():
    parser = RecoveryParser(description=__doc__)
    parser.add_argument('reply', help='hydrated reply JSON file, or - for standard input')
    parser.add_argument('cache_dir', help='main acquisition directory')
    parser.add_argument('--capture-dir', help='isolated directory for a narrowed acquisition')
    args = parser.parse_args()
    try:
        return acquire(args)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f'FAIL: {error}; correct the capture or reacquire verified parts, then retry.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
