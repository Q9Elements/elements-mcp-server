"""Carry a write plan through bounded requests using genuine intermediate results.

    python3 manage_batches.py next PLAN.json [--result FINAL.saved.json]

Save each real response at saveTo and repeat. The final record includes every
batch response, merged idMap, children, diff and the actual final version.
Receipts are scoped by a hash of the complete plan, including its base version.
Preview and real calls both identify their batch number.
Uncertain outcomes stop for reconciliation; they never create a saved marker.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from mcp_result import write_complete


def split_changes(changes):
    for kind, cap in [('activity', 150), ('line', 300)]:
        if sum(c.get('op') == 'add' and c.get('kind') == kind for c in changes) > cap:
            raise ValueError(f'plan exceeds supported level growth: {cap} {kind} additions; split the level')
    batches, current, names = [], [], set()
    for change in changes:
        name = change.get('name') if change.get('op') == 'add' and change.get('kind') == 'resource' else None
        if current and (len(current) == 100 or (name and name not in names and len(names) == 10)):
            batches.append(current)
            current, names = [], set()
        current.append(change)
        if name:
            names.add(name)
    if current:
        batches.append(current)
    return batches


def next_batch(path, final=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    identity = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    batches = plan.get('batches') or split_changes(plan['changes'])
    results, keys, children = [], {}, []
    version = plan['baseVersion']
    for number, changes in enumerate(batches, 1):
        saved = path.parent / '.batches' / path.stem / identity / f'{number}.json'
        if saved.exists():
            result = json.loads(saved.read_text())
            if not write_complete(result):
                return {'action': 'reconcile-write', 'result': str(saved), 'diagramId': plan['diagramId'],
                        'how': 'Poll copy-running on this map; read the level and outline for uncertain saves, reconcile side effects and genuine ref associations before replay.'}
            results.append(result)
            keys.update(result.get('idMap') or {})
            children.extend(result.get('children') or [])
            version = result['version']
            continue
        if plan.get('dryRunFirst'):
            dry = saved.with_name(saved.stem + '.dry.json')
            if not dry.exists():
                args = {key: copy.deepcopy(plan[key]) for key in ('teamId', 'diagramId', 'createResources', 'confirm') if key in plan}
                args.update(baseVersion=version, dryRun=True, changes=changes)
                def resolve_dry(value, field=None):
                    if isinstance(value, dict):
                        return {key: resolve_dry(item, key) for key, item in value.items()}
                    if isinstance(value, list):
                        return [resolve_dry(item, field) for item in value]
                    return keys.get(value, value) if isinstance(value, str) and field in ('activity', 'from', 'to', 'key') else value
                args['changes'] = resolve_dry(changes)
                if any(change.get('op') == 'remove' for change in changes):
                    args['confirm'] = True
                dry.parent.mkdir(parents=True, exist_ok=True)
                return {'action': 'call', 'tool': 'manage_diagram', 'batch': number, 'of': len(batches),
                        'arguments': args, 'saveTo': str(dry),
                        'save': 'the complete dry-run response'}
            preview = json.loads(dry.read_text())
            if preview.get('error') or preview.get('status') == 'running' or any(issue.get('severity') == 'error' for issue in preview.get('issues', [])):
                return {'action': 'stop', 'why': 'batch preflight is incomplete or failed', 'result': str(dry)}
        own = {change['ref'] for change in changes if change.get('ref')}
        def resolve(value, field=None):
            if isinstance(value, list):
                return [resolve(item, field) for item in value]
            if isinstance(value, dict):
                return {key: resolve(item, key) for key, item in value.items()}
            if field in ('activity', 'from', 'to', 'key') and isinstance(value, str) and value not in own:
                if value in keys:
                    return keys[value]
                raise ValueError(f'unresolved ref {value}; retain genuine idMap from the preceding batch')
            return value
        args = {key: copy.deepcopy(plan[key]) for key in ('teamId', 'diagramId', 'createResources', 'dryRun', 'confirm') if key in plan}
        args.update(baseVersion=version, changes=resolve(changes))
        if any(change.get('op') == 'remove' for change in changes):
            args['confirm'] = True
        saved.parent.mkdir(parents=True, exist_ok=True)
        return {'action': 'call', 'tool': 'manage_diagram', 'batch': number, 'of': len(batches),
                'arguments': args, 'saveTo': str(saved), 'save': 'the genuine whole real response, including saved, version, idMap, children, diff, warnings and issues'}
    combined = {'saved': all(write_complete(result) for result in results), 'version': version,
                'idMap': keys, 'children': children, 'batchResults': results,
                'issues': [issue for result in results for issue in result.get('issues', [])],
                'diff': {key: [item for result in results for item in (result.get('diff') or {}).get(key, [])]
                         for key in ('added', 'updated', 'removed')}}
    if final:
        Path(final).parent.mkdir(parents=True, exist_ok=True)
        Path(final).write_text(json.dumps(combined, indent=2) + '\n')
    return {'action': 'done', 'result': combined}


def bounded_plan(plan):
    batches = split_changes(plan['changes'])
    if len(batches) > 1:
        plan = dict(plan, changes=batches[0], batches=batches)
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('command', choices=['next'])
    parser.add_argument('plan', type=Path)
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(next_batch(args.plan, args.result), indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print('ERROR ' + str(exc))
        raise SystemExit(1)
