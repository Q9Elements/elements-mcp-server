#!/usr/bin/env python3
"""Usage: fetch_parts.py REPLY_JSON OUTPUT_DIRECTORY

Exit 0: verified; consume local evidence. Exit 1: incomplete; correct the
reported evidence gap and rerun. Exit 2: usage; correct arguments and rerun.
Exit 3: pending; repeat the tool call with the printed continuation and rerun.

JSON means JavaScript Object Notation; NDJSON means newline-delimited JSON.
HTTPS means Hypertext Transfer Protocol Secure; URL means uniform resource locator.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlparse
from urllib.request import urlopen


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(message + '; correct arguments using --help and rerun')


def page_list(value):
    """Select the page list using the server response budget's field priority."""
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return None
    for key in ('items', 'objects', 'list', 'rows', 'nodes', 'deps', 'chains',
                'workUnits', 'deleteOrder', 'risks', 'automations', 'schemaNodes'):
        if isinstance(value.get(key), list):
            return value[key]
    # The server falls back to the largest serialized array, with ties in key order.
    arrays = [rows for rows in value.values() if isinstance(rows, list)]
    return max(arrays, key=lambda rows: len(json.dumps(
        rows, ensure_ascii=False, separators=(',', ':')).encode('utf-16-le')), default=None)


def download(descriptor, output):
    if descriptor.get('expiresInSeconds', 0) <= 0:
        raise ValueError('Expired descriptor; repeat the same selection for a fresh link and rerun')
    if urlparse(descriptor['url']).scheme not in ('https', 'file'):
        raise ValueError('Unsupported URL scheme; obtain an HTTPS link or local file fixture and rerun')
    # Bound a stalled client read so the caller can refresh the returned link.
    try:
        with urlopen(descriptor['url'], timeout=60) as response:
            body = response.read()
    except http.client.HTTPException as error:
        raise OSError('Fetch failed; repeat the same selection for fresh links and rerun') from error
    if 'sha256' in descriptor and hashlib.sha256(body).hexdigest() != descriptor['sha256']:
        raise ValueError('Checksum mismatch; repeat the same selection for fresh links and rerun')
    if 'bytes' in descriptor and len(body) != descriptor['bytes']:
        raise ValueError('Byte count mismatch; repeat the same selection and rerun')
    if descriptor['format'] == 'json':
        value = json.loads(body)
        page = page_list(value)
        # Empty/no-list envelopes are serialized as one whole value by the server.
        rows = len(value) if isinstance(value, list) else len(page) if page else 1
    elif descriptor['format'] == 'ndjson':
        value = [json.loads(line) for line in body.split(b'\n') if line.strip()]
        rows = len(value)
        if any(not isinstance(row, dict) for row in value):
            raise ValueError('Part rows must be objects; obtain valid NDJSON and rerun')
    else:
        raise ValueError('Unsupported format; request ndjson or a JSON envelope and rerun')
    if 'rows' in descriptor and rows != descriptor['rows']:
        raise ValueError('Row count mismatch; repeat the same selection and rerun')
    # Content hashes provide safe local filenames for untrusted descriptors.
    path = output / ('download-%s.%s' % (hashlib.sha256(body).hexdigest(), descriptor['format']))
    path.write_bytes(body)
    return value, path


def hydrate(value, output):
    if isinstance(value, list):
        return [hydrate(item, output) for item in value]
    if not isinstance(value, dict):
        return value
    if isinstance(value.get('file'), dict) and value['file'].get('url'):
        hydrated, _ = download(value['file'], output)
        hydrated = hydrate(hydrated, output)
        publication_error = value.get('fileError') or value.get('_oversize', {}).get('fileError')
        if publication_error and isinstance(hydrated, dict):
            hydrated['fileError'] = publication_error
        return hydrated
    return {key: hydrate(item, output) for key, item in value.items()}


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


def acquire(reply_path, output):
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'parts': {}}
    state['complete'] = False
    state_path.write_text(json.dumps(state))
    (output / 'rows.ndjson').unlink(missing_ok=True)
    reply = hydrate(json.loads(reply_path.read_text()), output)
    if not isinstance(reply, dict):
        raise ValueError('Expected a parsed reply object; save the tool payload as JSON and rerun')
    if isinstance(reply.get('failedFile'), dict):
        reply['failedFileRows'], _ = download(reply['failedFile'], output)
    (output / 'reply.json').write_text(json.dumps(reply))
    if reply.get('error') or reply.get('_oversize', {}).get('refusedInline'):
        raise ValueError('Tool refusal %s; read the refusal, correct the selection or access and rerun' % reply.get('error'))
    if 'resultId' not in reply:
        if reply.get('status') in ('running', 'failed'):
            if reply['status'] == 'failed':
                raise ValueError('Job failed; read reply.json, follow its instruction and rerun')
            return 3, 'Indexing; repeat the same query using returned retryAfterSeconds=%s and rerun' % reply.get('retryAfterSeconds', 'unknown')
        if reply.get('fileError') or reply.get('_oversize', {}).get('fileError'):
            raise ValueError('File publication failed; consume reply.json, recover missing evidence and rerun')
        meta = reply.get('pagination', reply)
        cursor = reply.get('_truncated', {}).get('nextSkip', meta.get('nextSkip'))
        if cursor is None and meta.get('hasMore'):
            page = page_list(reply)
            if page is not None:
                cursor = meta.get('skip', 0) + len(page)
        if cursor is not None:
            return 3, 'Consume this reply.json page, repeat the tool selection with skip=%s and rerun' % cursor
        if meta.get('hasMore'):
            raise ValueError('Missing row cursor; preserve this page and obtain supported continuation')
        if reply.get('_truncated'):
            raise ValueError('Unresolved truncation; recover omitted evidence and rerun')
        return 0, 'Hydrated; consume reply.json'
    parts_dir = output / 'parts'
    parts_dir.mkdir(exist_ok=True)
    if reply.get('status') not in ('running', 'complete', 'failed'):
        raise ValueError('Unknown native status; retrieve a valid tool reply and rerun')
    if (not re.fullmatch(r'[0-9a-fA-F]{64}', str(reply['resultId'])) or
            not isinstance(reply.get('parts'), list) or not isinstance(reply.get('failed'), list) or
            any(type(reply.get(key)) is not int or reply[key] < 0 for key in ('partsTotal', 'totalRows'))):
        raise ValueError('Invalid native job metadata; retrieve a complete tool reply and rerun')
    reset = (state.get('resultId') != reply['resultId'] or
             (state.get('computedAt') and reply.get('computedAt') and
              state['computedAt'] != reply['computedAt']) or
             len(state['parts']) > reply['partsTotal'] or
             (state.get('batchesDone', 0) > reply.get('batchesDone', 0)) or
             any(str(part['index']) in state['parts'] and
                 any(state['parts'][str(part['index'])].get(key) != part[key]
                     for key in ('format', 'sha256', 'bytes', 'rows'))
                 for part in reply['parts']))
    if reset:
        state = {'parts': {}}
        for path in parts_dir.glob('*.ndjson'):
            path.unlink()
    state.update(resultId=reply['resultId'], computedAt=reply.get('computedAt') or state.get('computedAt'),
                 batchesDone=reply.get('batchesDone', 0))
    state['complete'] = False
    state_path.write_text(json.dumps(state))
    (output / 'rows.ndjson').unlink(missing_ok=True)
    parts = state['parts']
    provenance = state.setdefault('provenance', {})
    for descriptor in reply['parts']:
        index = descriptor['index']
        if type(index) is not int or index < 0:
            raise ValueError('Invalid part index; retrieve valid descriptors and rerun')
        _, path = download(descriptor, output)
        shutil.copyfile(path, parts_dir / ('%06d.ndjson' % index))
        parts[str(index)] = {key: descriptor[key] for key in ('format', 'sha256', 'rows', 'bytes')}
        provenance[str(index)] = reply_provenance(reply)
    (output / 'reply.json').write_text(json.dumps(reply))
    state_path.write_text(json.dumps(state))
    if (reply.get('error') or reply.get('status') == 'failed' or reply.get('failed') or
            reply.get('failedTotal') or reply.get('fileError') or
            reply.get('_oversize', {}).get('fileError')):
        raise ValueError('Refusal or partial failure %s; read reply.json, resolve the failure and rerun' %
                         json.dumps({key: reply[key] for key in
                                     ('error', 'failed', 'failedTotal', 'fileError') if key in reply}))
    if 'nextPartsFrom' in reply:
        return 3, 'Repeat the same tool selection with partsFrom=%s and rerun' % reply['nextPartsFrom']
    if reply['status'] == 'running':
        return 3, 'Repeat the same selection after returned retryAfterSeconds=%s and rerun' % reply.get('retryAfterSeconds', 'unknown')
    if set(map(int, parts)) != set(range(reply['partsTotal'])):
        return 3, 'Repeat the same selection with partsFrom=0 to retrieve missing parts and rerun'
    unconfirmed = next((index for index in range(reply['partsTotal'])
                        if not matches_completion(state, str(index), reply)), None)
    if unconfirmed is not None:
        return 3, ('Repeat the same selection with partsFrom=%s to confirm completed descriptors and rerun'
                   % unconfirmed)
    if sum(part['rows'] for part in parts.values()) != reply['totalRows']:
        raise ValueError('Total row count mismatch; retrieve all part cursors and rerun')
    for index, part in parts.items():
        path = parts_dir / ('%06d.ndjson' % int(index))
        body = path.read_bytes()
        if (hashlib.sha256(body).hexdigest() != part['sha256'] or len(body) != part['bytes'] or
                len([json.loads(line) for line in body.split(b'\n') if line.strip()]) != part['rows']):
            raise ValueError('Held part changed on disk; retrieve that part again and rerun')
    with (output / 'rows.ndjson').open('wb') as merged:
        for index in sorted(map(int, parts)):
            with (parts_dir / ('%06d.ndjson' % index)).open('rb') as source:
                shutil.copyfileobj(source, merged)
    state['complete'] = True
    state_path.write_text(json.dumps(state))
    return 0, 'Verified; consume rows.ndjson'


def main():
    parser = ActionParser(description=__doc__)
    parser.add_argument('reply', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        code, message = acquire(args.reply, args.output)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print('Incomplete: %s. Correct the reply or repeat the tool selection and rerun.' % error, file=sys.stderr)
        return 1
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
