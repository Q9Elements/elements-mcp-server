"""Acquire saved Model Context Protocol (MCP) results without losing coverage.

hydrate restores whole-page files and moved values. acquire_native collects one
native job page, retaining its result identity and indexed parts across cursors.
Callers poll running jobs and request nextPartsFrom before using the rows.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


class AcquisitionError(ValueError):
    pass


def download(descriptor):
    with urlopen(descriptor['url'], timeout=30) as response:
        raw = response.read()
    if descriptor.get('bytes') is not None and len(raw) != descriptor['bytes']:
        raise AcquisitionError('download byte count differs from descriptor')
    if descriptor.get('sha256') and hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
        raise AcquisitionError('download SHA-256 differs from descriptor')
    return raw.decode('utf-8-sig')


def hydrate(value):
    if isinstance(value, list):
        return [hydrate(item) for item in value]
    if not isinstance(value, dict):
        return value
    oversize = value.get('_oversize')
    if isinstance(oversize, dict) and oversize.get('refusedInline'):
        raise AcquisitionError('inline result refused; repeat with delivery:file')
    descriptor = value.get('file')
    if isinstance(descriptor, dict) and descriptor.get('url'):
        full = hydrate(json.loads(download(descriptor)))
        outer = {key: hydrate(item) for key, item in value.items() if key != 'file'}
        if not outer:
            return full
        if not isinstance(full, dict):
            raise AcquisitionError('whole-page file must contain an object')
        if isinstance(outer.get('_truncated'), dict) and outer['_truncated'].get('inFile'):
            outer.pop('_truncated')
        outer.update(full)
        return outer
    return {key: hydrate(item) for key, item in value.items()}


def native_errors(reply):
    errors = []
    if reply.get('status') != 'complete':
        errors.append('native job is not complete: ' + str(reply.get('status')))
    if not reply.get('resultId'):
        errors.append('native job has no resultId')
    if not isinstance(reply.get('partsTotal'), int) or reply['partsTotal'] < 0 or not isinstance(reply.get('totalRows'), int) or reply['totalRows'] < 0:
        errors.append('native job final counts are missing or invalid')
    parts = reply.get('parts') or []
    indices = [part['index'] for part in parts]
    if len(indices) != len(set(indices)) or set(indices) != set(range(reply.get('partsTotal', -1))):
        errors.append('native job does not account for every part index')
    if reply.get('nextPartsFrom') is not None:
        errors.append('native job has another part cursor')
    if reply.get('failedTotal', len(reply.get('failed') or [])) != len(reply.get('failed') or []):
        errors.append('native job failure coverage is incomplete; acquire failedFile')
    if reply.get('batchesDone') is not None and reply.get('batchesTotal') != reply['batchesDone']:
        errors.append('native job batches are incomplete')
    return errors


def acquire_native(reply, previous=None):
    """Download indexed newline-delimited JSON parts, joining only the same job."""
    result = dict(reply)
    previous = previous or {}
    if previous and previous.get('resultId') != reply.get('resultId'):
        raise AcquisitionError('resultId changed; restart acquisition for this attempt')
    parts = {part['index']: dict(part) for part in previous.get('parts', [])}
    records = dict(previous.get('partRows') or {})
    raw_parts = dict(previous.get('partData') or {})
    for part in reply.get('parts') or []:
        index = part['index']
        if str(index) not in records:
            if part.get('format', 'ndjson') != 'ndjson':
                raise AcquisitionError('this collector requires ndjson parts')
            raw_parts[str(index)] = download(part)
            rows = [json.loads(line) for line in raw_parts[str(index)].splitlines() if line.strip()]
            if part.get('rows') is not None and len(rows) != part['rows']:
                raise AcquisitionError('part row count differs from descriptor')
            records[str(index)] = rows
        parts[index] = dict(part)
    result['parts'] = [parts[index] for index in sorted(parts)]
    result['partRows'] = records
    result['partData'] = raw_parts
    result['rows'] = [row for index in sorted(parts) for row in records[str(index)]]
    failures = list(reply.get('failed') or [])
    if reply.get('failedTotal', len(failures)) > len(failures) and reply.get('failedFile'):
        failures = [json.loads(line) for line in download(reply['failedFile']).splitlines() if line.strip()]
    result['failed'] = failures
    errors = native_errors(result)
    if not errors and len(result['rows']) != result.get('totalRows'):
        raise AcquisitionError('native job row total differs from acquired rows')
    return result


def load(path):
    return hydrate(json.loads(Path(path).read_text(encoding='utf-8')))


def owner_api(component):
    """Canonical field owner, independently of its display label."""
    full = (component.get('sf') or {}).get('fullApiName') or component.get('full_api_name') or ''
    if '/' in full:
        return full.split('/', 1)[0]
    identity = component.get('identity') or ''
    if '.fields.' in identity:
        return identity.split('.fields.', 1)[0].split('.')[-1]
    path = component.get('parentPath') or []
    if isinstance(path, str):
        parts = path.split('.')
        if len(parts) >= 2 and parts[-1].casefold() in ('fields', 'recordtypes', 'recordtype'):
            return parts[-2]
        return None
    for parent in reversed(path):
        if isinstance(parent, dict):
            sf = parent.get('sf') or {}
            api = sf.get('apiName') or parent.get('apiName')
            if api:
                return api
    return None


def map_name(value):
    value = str(value).strip()
    if not 2 <= len(value) <= 80:
        raise ValueError('map name must contain 2-80 characters after trimming')
    return value


def write_complete(result):
    if result.get('status') == 'running' or result.get('error'):
        return False
    if result.get('saved') is True:
        return result.get('version') is not None and isinstance(result.get('idMap'), dict)
    issues = result.get('issues') or result.get('warnings') or []
    return (result.get('saved') is False and result.get('version') is not None
            and any((item.get('code') if isinstance(item, dict) else item) == 'unchanged' for item in issues))


def bind_step(function):
    """Carry a drawing's selected server and space into every emitted call."""
    from functools import wraps
    @wraps(function)
    def bound(workdir, *args, **kwargs):
        step = function(workdir, *args, **kwargs)
        path = Path(workdir) / 'connection.json'
        if path.exists():
            connection = json.loads(path.read_text())
            if not connection.get('teamId') or not connection.get('server'):
                raise AcquisitionError('connection.json requires server and teamId')
            def bind(value):
                if not isinstance(value, dict):
                    return
                if isinstance(value.get('arguments'), dict):
                    value['arguments']['teamId'] = connection['teamId']
                if value.get('diagramId') and value.get('saveTo'):
                    value['teamId'] = connection['teamId']
                for nested in value.values():
                    if isinstance(nested, list):
                        for item in nested:
                            bind(item)
                    elif isinstance(nested, dict):
                        bind(nested)
            bind(step)
            step['server'] = connection['server']
        return step
    return bound


def has_continuation(value):
    if isinstance(value, list):
        return any(has_continuation(item) for item in value)
    if isinstance(value, dict):
        if value.get('_truncated') or value.get('hasMore') or value.get('nextSkip') is not None:
            return True
        return any(has_continuation(item) for item in value.values())
    return False


def require_complete(value):
    if isinstance(value, dict):
        if value.get('status') == 'running':
            raise AcquisitionError('result is running; poll the same operation using its retry instruction')
        if value.get('status') == 'failed' or value.get('error'):
            raise AcquisitionError('result failed: ' + str(value.get('error') or value.get('message')))
    if has_continuation(value):
        raise AcquisitionError('result has another page; hydrate and merge every page with acquire_result.py generic')
    return value


def verify_rows(path):
    path = Path(path)
    register = path.with_name(path.name + '.acquisition.json')
    if not register.exists():
        raise AcquisitionError(f'{path}: native rows need terminal acquisition evidence in {register.name}')
    reply = json.loads(register.read_text())
    errors = native_errors(reply)
    if errors:
        raise AcquisitionError(f'{path}: ' + '; '.join(errors))
    raw = path.read_bytes()
    if reply.get('savedSha256') != hashlib.sha256(raw).hexdigest():
        raise AcquisitionError(f'{path}: acquired row file digest differs from its evidence')
    count = sum(bool(line.strip()) for line in raw.decode('utf-8-sig').splitlines())
    if count != reply['totalRows']:
        raise AcquisitionError(f'{path}: acquired row count differs from final totalRows')
    return reply


def write_recovery(result):
    if result.get('status') == 'running':
        return {'action': 'copy-running', 'mapId': result.get('mapId'),
                'how': 'Poll this map outline to complete, then read the current level before repeating the original write.'}
    error = result.get('error')
    code = error.get('code') if isinstance(error, dict) else error
    if code in ('save_failed', 'partial_save'):
        return {'action': 'reconcile-write', 'error': code,
                'how': 'Read the level and outline, reconcile resource, attachment, child and header side effects, and recover genuine saved refs before replay.'}
    return None
