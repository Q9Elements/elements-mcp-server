#!/usr/bin/env python3
"""Collect and calculate one quote line's pricing evidence using read-only queries.

Run next, save, and compute for hosted collection, or gather for the Salesforce
command-line route. All results use the same per-attempt file contract.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from pricing_common import literal, now, read_json, sfid, valid_id, write_json
from query_specs import SPECS

BASE_TOTALS = {name: f'SBQQ__{name}Total__c' for name in ('List', 'Regular', 'Customer', 'Net')}
STAGES = [1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 2, 1, 4]


def latest(directory, qid):
    paths = list((Path(directory) / 'q').glob(qid + '.a*.json'))
    return read_json(max(paths, key=lambda p: int(re.search(r'\.a(\d+)\.', p.name)[1]))) if paths else None


def rows(directory, qid):
    value = latest(directory, qid)
    return value['records'] if value and value['ok'] else []


def first(directory, qid):
    return next(iter(rows(directory, qid)), {})


def fields_in(soql):
    return soql.split('SELECT ', 1)[1].split(' FROM ', 1)[0].split(', ')


def queried_ids(soql, field='Id'):
    """Read an identity constraint from the query issued by next."""
    where = soql.partition(' WHERE ')[2]
    match = re.match(re.escape(field) + r"\s*(?:=\s*('[^']+')|IN\s*\(([^)]+)\))", where)
    return {sfid(value) for value in re.findall(r"'([^']+)'", match[1] or match[2])} if match else None


def method(row):
    return 'Percent Of Total' if str(row.get('SBQQ__SubscriptionPricing__c')).lower() == 'percent of total' else row.get('SBQQ__PricingMethod__c')


def make_query(qid, line, row, log, quote, rules):
    """Return columns and a suffix, or an explicit inapplicability reason."""
    f = list(SPECS[qid]['fields'])
    obj = SPECS[qid]['object']
    ql = valid_id(row.get('Id'))
    product = valid_id(row.get('SBQQ__Product__c'))
    quote_id = valid_id(row.get('SBQQ__Quote__c'))
    currency = row.get('CurrencyIsoCode') or quote.get('CurrencyIsoCode')
    limit = 1
    order = ''
    where = ''
    reason = None
    if qid == 'P01':
        where = ('Id = ' + literal(valid_id(line))) if valid_id(line) else 'Name = ' + literal(line)
        limit = 2
    elif qid == 'P19':
        pass
    elif not ql:
        return None, 'P01 did not resolve one readable quote line'
    elif qid == 'P02':
        where = 'Q9_QLM__Quote_Line__c = ' + literal(ql)
        order = 'Q9_QLM__Modified_DateTime__c DESC NULLS LAST, CreatedDate DESC'
    elif qid in ('P03', 'P04', 'P05', 'P06', 'P07', 'P08', 'P09'):
        link = {'P03': 'SBQQ__Quote__c', 'P04': 'SBQQ__Product__c',
                'P05': 'SBQQ__PricebookEntryId__c', 'P06': 'SBQQ__ProductOption__c',
                'P07': 'SBQQ__RequiredBy__c', 'P08': 'SBQQ__Group__c', 'P09': 'SBQQ__ContractedPrice__c'}[qid]
        value = valid_id(row.get(link))
        if not value:
            reason = 'no valid ' + link + ' on line'
        else:
            where = 'Id = ' + literal(value)
    elif qid in ('P10', 'P11'):
        schedules = sorted({valid_id(row.get(k)) for k in ('SBQQ__DiscountSchedule__c', 'SBQQ__TermDiscountSchedule__c')} - {None})
        if not schedules:
            reason = 'no discount schedule on line'
        else:
            where = ('Id' if qid == 'P10' else 'SBQQ__Schedule__c') + ' IN (' + ','.join(map(literal, schedules)) + ')'
            limit = 2 if qid == 'P10' else 200
            if qid == 'P11':
                order = 'SBQQ__Schedule__c, SBQQ__LowerBound__c ASC NULLS FIRST'
    elif qid in ('P12', 'P13'):
        if qid == 'P12' and str(method(row)).lower() != 'block':
            reason = 'pricing method is not Block'
        elif qid == 'P13' and not valid_id(row.get('SBQQ__Dimension__c')):
            reason = 'no SBQQ__Dimension__c on line'
        elif not product:
            reason = 'no valid SBQQ__Product__c on line'
        else:
            where = 'SBQQ__Product__c = ' + literal(product)
            if currency:
                where += ' AND CurrencyIsoCode = ' + literal(currency)
            limit = 200 if qid == 'P12' else 50
            if qid == 'P12':
                order = 'SBQQ__LowerBound__c ASC NULLS FIRST'
    elif qid == 'P14':
        if str(method(row)).lower() != 'percent of total' or not quote_id:
            reason = 'pricing method is not Percent Of Total or quote Id is unavailable'
        else:
            base = row.get('SBQQ__SubscriptionBase__c')
            base_field = next((v for k, v in BASE_TOTALS.items() if k.lower() == str(base).lower()), None)
            f.extend([base_field] if base_field else BASE_TOTALS.values())
            where = 'SBQQ__Quote__c = ' + literal(quote_id) + ' AND Id != ' + literal(ql)
            order = 'SBQQ__Number__c ASC NULLS LAST'
            limit = 2000
    elif qid == 'P15':
        dimension = valid_id(row.get('SBQQ__Dimension__c'))
        if not dimension or not quote_id:
            reason = 'no valid dimension or quote Id on line'
        else:
            key = row.get('SBQQ__SegmentKey__c')
            where = 'SBQQ__Quote__c = ' + literal(quote_id) + ' AND ' + (
                'SBQQ__SegmentKey__c = ' + literal(key) if key is not None else 'SBQQ__Dimension__c = ' + literal(dimension))
            order = 'SBQQ__SegmentIndex__c ASC NULLS LAST, SBQQ__Number__c ASC'
            limit = 200
    elif qid in ('P16', 'P17'):
        log_id = valid_id(log.get('Id'))
        if not log_id:
            reason = 'P02 returned no readable log'
        else:
            where = ('Q9_QLM__Quote_Line_Log__c' if qid == 'P16' else
                     'Q9_QLM__Price_Rule_Evaluation__r.Q9_QLM__Quote_Line_Log__c') + ' = ' + literal(log_id)
            order = 'Q9_QLM__Sequence__c ASC'
            limit = 500 if qid == 'P16' else 2000
    elif qid == 'P18':
        if row.get('SBQQ__Bundle__c') is not True:
            reason = 'line is not a bundle parent'
        else:
            where = 'SBQQ__RequiredBy__c = ' + literal(ql)
            order = 'SBQQ__Number__c ASC NULLS LAST'
            limit = 200
    elif qid == 'P20':
        ids = sorted({valid_id(r.get('Q9_QLM__Price_Rule__c')) for r in rules} - {None})
        if not ids:
            reason = 'P16 returned no valid price rule Ids'
        else:
            where = 'SBQQ__Rule__c IN (' + ','.join(map(literal, ids)) + ')'
            order = 'SBQQ__Rule__c, SBQQ__Index__c ASC NULLS LAST'
            limit = 500
    if reason:
        return None, reason
    suffix = ' FROM ' + obj + (' WHERE ' + where if where else '')
    suffix += (' ORDER BY ' + order if order else '') + ' LIMIT ' + str(limit)
    return (f, suffix), None


PARENT_OBJECTS = {
    'SBQQ__Product__r': 'Product2', 'SBQQ__Feature__r': 'SBQQ__ProductFeature__c',
    'SBQQ__PriceBook__r': 'Pricebook2', 'Pricebook2': 'Pricebook2',
    'Q9_QLM__Price_Rule__r': 'SBQQ__PriceRule__c',
    'SBQQ__OriginalDiscountSchedule__r': 'SBQQ__DiscountSchedule__c',
}


def dropped_columns(error, columns, source_object=None):
    field = error.get('field')
    if error.get('kind') == 'relationship_not_readable':
        return [f for f in columns if f.startswith(str(field) + '.')]
    if error.get('kind') == 'field_not_readable':
        if source_object and error.get('object') != source_object:
            parent = [f for f in columns if '.' in f and PARENT_OBJECTS.get(f.split('.')[0]) == error.get('object') and f.split('.')[-1] == field]
            if parent:
                return parent
        exact = [f for f in columns if f == field]
        return exact or [f for f in columns if f.split('.')[-1] == field]
    return []


def next_queries(directory, line):
    directory = Path(directory)
    path = directory / 'q/plan.json'
    if path.exists() and read_json(path).get('line') != line:
        raise ValueError('Run directory belongs to a different quote line')
    row = first(directory, 'P01') if len(rows(directory, 'P01')) == 1 else {}
    queries = {}
    for qid, spec in SPECS.items():
        definition, reason = make_query(qid, line, row, first(directory, 'P02'),
                                        first(directory, 'P03'), rows(directory, 'P16'))
        state = dict(state='not_applicable' if reason else 'due', reason=reason,
                     attempt=1, droppedFields=[], soql=None)
        if definition:
            columns, suffix = definition
            # Earlier attempt files are immutable evidence of each field loss.
            for file in sorted((directory / 'q').glob(qid + '.a*.error.json'),
                               key=lambda p: int(re.search(r'\.a(\d+)\.', p.name)[1])):
                old = read_json(file)
                for field in dropped_columns(old['error'], columns, spec['object']):
                    if field not in state['droppedFields']:
                        state['droppedFields'].append(field)
            columns = [f for f in columns if f not in state['droppedFields']]
            if state['droppedFields'] and ' ORDER BY ' in suffix:
                prefix, ordered = suffix.split(' ORDER BY ', 1)
                order_by, limit = ordered.split(' LIMIT ', 1)
                for field in state['droppedFields']:
                    order_by = re.sub(r'(?:^|,\s*)' + re.escape(field) +
                                      r'\s+(?:ASC|DESC)(?:\s+NULLS\s+(?:FIRST|LAST))?', '', order_by)
                order_by = order_by.strip(' ,')
                suffix = prefix + ((' ORDER BY ' + order_by) if order_by else '') + ' LIMIT ' + limit
            value = latest(directory, qid)
            if value:
                state['attempt'] = value['attempt']
                if value['ok']:
                    state['state'] = 'done'
                elif (value['attempt'] < 25 and columns and
                      dropped_columns(value['error'], fields_in(value['soql']), spec['object'])):
                    state['attempt'] += 1
                else:
                    state['state'] = 'failed'
            state['soql'] = 'SELECT ' + ', '.join(columns) + suffix
        queries[qid] = state
    write_json(path, dict(line=line, queries=queries))
    due = [dict(id=qid, attempt=s['attempt'], soql=s['soql']) for qid, s in queries.items() if s['state'] == 'due']
    if due:
        stage = min(STAGES[int(q['id'][1:]) - 1] for q in due)
        return [q for q in due if STAGES[int(q['id'][1:]) - 1] == stage and not (
            q['id'] in ('P12', 'P13') and not row.get('CurrencyIsoCode') and queries['P03']['state'] == 'due')]
    return elements_next(directory)


def unwrap(payload):
    """Accept JSON objects and Model Context Protocol text/structured wrappers."""
    if isinstance(payload, (str, bytes)):
        payload = payload.decode('utf-8') if isinstance(payload, bytes) else payload
        marked = re.fullmatch(r'\s*\[TOOL DATA START\]\s*(.*?)\s*\[TOOL DATA END\]\s*', payload, re.S)
        if marked:
            payload = marked.group(1)
        payload = json.loads(payload)
    if isinstance(payload, dict):
        if 'structuredContent' in payload:
            return unwrap(payload['structuredContent'])
        if 'content' in payload and isinstance(payload['content'], list):
            texts = [c['text'] for c in payload['content'] if c.get('type') == 'text']
            if payload.get('isError'):
                return {'errorCode': 'TOOL_ERROR', 'message': '\n'.join(texts)}
            return unwrap('\n'.join(texts))
        if 'result' in payload and isinstance(payload['result'], (dict, list)) and not payload.get('status'):
            return unwrap(payload['result'])
        if 'data' in payload and isinstance(payload['data'], (dict, list)):
            return unwrap(payload['data'])
    return payload


def strip_attributes(value):
    if isinstance(value, dict):
        return {k: strip_attributes(v) for k, v in value.items() if k != 'attributes'}
    if isinstance(value, list):
        return [strip_attributes(v) for v in value]
    return value


def classify(code, message, obj=None):
    kind, field = 'unknown', None
    match = re.search(r"No such column '([^']+)' on entity '([^']+)'", message, re.I)
    relationship = re.search(r"Didn't understand relationship '([^']+)'", message, re.I)
    if code == 'INVALID_FIELD' and match:
        kind, field, obj = 'field_not_readable', match[1], match[2]
    elif code == 'INVALID_FIELD' and relationship:
        kind, field = 'relationship_not_readable', relationship[1]
    elif code == 'INVALID_TYPE':
        kind = 'object_not_readable'
        match = re.search(r"sObject type '([^']+)'", message, re.I)
        if match:
            obj = match[1]
    elif code == 'MALFORMED_QUERY':
        kind = 'malformed'
    elif code in ('REQUEST_LIMIT_EXCEEDED', 'QUERY_TIMEOUT'):
        kind = 'limit'
    elif code in ('TRANSPORT', 'TOOL_ERROR') or re.search(r'auth|session.*expir|INVALID_SESSION|not.*authoriz|tool.*(?:missing|not found)|ENOENT|ECONN', code + ' ' + message, re.I):
        kind = 'transport'
    return dict(code=code, message=message, kind=kind, object=obj, field=field)


def save_response(directory, qid, payload, *, attempt=None, batch=None, route=None):
    directory = Path(directory)
    if not re.fullmatch(r'P(?:0[1-9]|1[0-9]|20)|E0[0-3]', qid):
        raise ValueError('Unknown query or Elements call Id')
    if qid.startswith('E'):
        if attempt is not None:
            raise ValueError('Elements save requires --batch')
        return save_elements(directory, qid, payload, batch)
    if batch is not None or not isinstance(attempt, int) or not 1 <= attempt <= 25:
        raise ValueError('Salesforce save requires --attempt from 1 to 25')
    plan = read_json(directory / 'q/plan.json')
    state = plan['queries'][qid]
    if state['state'] != 'due' or state['attempt'] != attempt:
        raise ValueError('Save must match the attempt issued by next')
    soql = state['soql']
    try:
        outer = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    except ValueError:
        outer = None
    envelope = dict(id=qid, attempt=attempt, route=route or ('sf-cli' if isinstance(outer, dict) and 'status' in outer else 'hosted-mcp'),
                    soql=soql, savedAt=now(), ok=False, totalSize=None, done=None, records=[], error=None)
    try:
        value = unwrap(payload)
        if isinstance(value, list) and value and isinstance(value[0], dict) and ('errorCode' in value[0] or 'message' in value[0]):
            value = value[0]
        if not isinstance(value, dict):
            raise ValueError('Expected a query response object')
        if 'records' not in value:
            code = str(value.get('errorCode') or value.get('name') or value.get('code') or 'UNKNOWN')
            message = str(value.get('message') or value.get('error') or 'Query response has no records')
            envelope['error'] = classify(code, message, SPECS[qid]['object'])
        else:
            records = value['records']
            complete = (isinstance(records, list) and all(isinstance(r, dict) for r in records) and
                        value.get('done') is True and not value.get('nextRecordsUrl') and
                        type(value.get('totalSize')) is int and len(records) == value['totalSize'])
            if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
                raise AssertionError('Records must be a list of objects')
            echo = True
            expected_ids = queried_ids(soql)
            for row in records:
                if expected_ids is not None:
                    echo &= valid_id(row.get('Id')) in expected_ids
                if qid == 'P01' and not valid_id(plan['line']):
                    echo &= row.get('Name') == plan['line']
                elif qid == 'P02':
                    echo &= valid_id(row.get('Q9_QLM__Quote_Line__c')) in queried_ids(soql, 'Q9_QLM__Quote_Line__c')
            if (not complete and qid != 'P14') or not echo:
                envelope['error'] = dict(code='ASSERTION_FAILED', message='Completeness or echo assertion failed for ' + qid,
                                         kind='incomplete', object=SPECS[qid]['object'], field=None)
            else:
                envelope.update(ok=True, records=strip_attributes(records), totalSize=value.get('totalSize'),
                                done=value.get('done'), nextRecordsUrl=value.get('nextRecordsUrl'), incomplete=not complete)
    except AssertionError as error:
        envelope['error'] = dict(code='ASSERTION_FAILED', message=str(error), kind='incomplete', object=SPECS[qid]['object'], field=None)
    except (ValueError, TypeError, KeyError) as error:
        envelope['error'] = classify('TRANSPORT', str(error), SPECS[qid]['object'])
    stem = directory / 'q' / f'{qid}.a{attempt}'
    success, failure = Path(str(stem) + '.json'), Path(str(stem) + '.error.json')
    destination, obsolete = (success, failure) if envelope['ok'] else (failure, success)
    write_json(destination, envelope)
    obsolete.unlink(missing_ok=True)
    return envelope


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def element_files(directory, qid):
    result = []
    for path in sorted((Path(directory) / 'e').glob(qid + '*.json')):
        if path.name != 'plan.json':
            result.append(read_json(path))
    return result


def active_team_id(directory):
    for envelope in element_files(directory, 'E00'):
        if envelope['ok'] and isinstance(envelope['result'], dict):
            active = envelope['result'].get('active')
            if isinstance(active, dict) and active.get('teamId'):
                return active['teamId']
    return None


def authorized_team_ids(directory):
    """Search the active space first, then E00's remaining authorized spaces."""
    teams = [active_team_id(directory)] if active_team_id(directory) else []
    for envelope in element_files(directory, 'E00'):
        if envelope['ok'] and isinstance(envelope['result'], dict):
            for space in envelope['result'].get('authorized', []):
                team = space.get('teamId')
                if team and team not in teams:
                    teams.append(team)
    return teams


def reference_model(directory):
    org = valid_id(first(directory, 'P19').get('Id'))
    teams = authorized_team_ids(directory)
    for envelope in element_files(directory, 'E01'):
        if envelope['ok'] and (not teams or envelope['args'].get('teamId') in teams):
            for item in dictionaries(envelope['result']):
                if org and valid_id(item.get('orgId')) == org:
                    model_id = item.get('refModelId') or item.get('id') or item.get('_id')
                    if model_id:
                        return dict(id=model_id, name=item.get('name'), teamId=envelope['args'].get('teamId'))
    return None


def metadata_hits(directory):
    result = {}
    for envelope in element_files(directory, 'E02'):
        if envelope['ok']:
            requested = envelope['args']['queries']
            for hit in dictionaries(envelope['result']):
                key = valid_id(hit.get('apiName'))
                if key and key in requested and hit.get('nodeId'):
                    result[key] = hit['nodeId']
    return result


def elements_next(directory):
    from pricing_compute import Calculation
    directory = Path(directory)
    calls = []
    calculation = Calculation(directory)
    calculation.access_gaps()
    if calculation.outcome()[0] == 'built' and valid_id(first(directory, 'P19').get('Id')):
        teams = authorized_team_ids(directory)
        if not element_files(directory, 'E00'):
            calls = [dict(id='E00', batch='b1', tool='get_space_context', args={})]
        elif teams:
            model = reference_model(directory)
            if not model:
                saved = {e['args'].get('teamId') for e in element_files(directory, 'E01')}
                calls = next(([dict(id='E01', batch=f'b{i + 1}', tool='list_reference_models', args=dict(teamId=team, delivery='file'))]
                    for i, team in enumerate(teams) if team not in saved), [])
            if model:
                ids = sorted({valid_id(r.get(field)) for qid, field in (
                    ('P16', 'Q9_QLM__Price_Rule__c'), ('P17', 'Q9_QLM__Price_Action__c'),
                    ('P20', 'Id')) for r in rows(directory, qid)} - {None})
                args = dict(refModelId=model['id'], sfType='Record', delivery='file')
                if model['teamId']:
                    args['teamId'] = model['teamId']
                all_calls = [dict(id='E02', batch=f'b{i // 20 + 1}', tool='search_metadata',
                                  args=dict(args, queries=ids[i:i + 20])) for i in range(0, len(ids), 20)]
                saved = {e['batch'] for e in element_files(directory, 'E02')}
                calls = [c for c in all_calls if c['batch'] not in saved]
                if not calls:
                    nodes = sorted(set(metadata_hits(directory).values()))
                    args = dict(refModelId=model['id'], historyType='change_logs', limit=5, delivery='file')
                    if model['teamId']:
                        args['teamId'] = model['teamId']
                    saved = {e['batch'] for e in element_files(directory, 'E03')}
                    calls = [dict(id='E03', batch=f'b{i // 50 + 1}', tool='get_component_change_history',
                                  args=dict(args, nodeIds=nodes[i:i + 50])) for i in range(0, len(nodes), 50)
                             if f'b{i // 50 + 1}' not in saved]
    write_json(directory / 'e/plan.json', calls)
    return calls


def save_elements(directory, qid, payload, batch):
    if isinstance(batch, int) or (isinstance(batch, str) and batch.isdigit()):
        batch = 'b' + str(batch)
    if not isinstance(batch, str) or not re.fullmatch(r'b[1-9][0-9]*', batch):
        raise ValueError('Elements save requires --batch b1, b2, ...')
    calls = read_json(directory / 'e/plan.json')
    call = next((c for c in calls if c['id'] == qid and c['batch'] == batch), None)
    if not call:
        raise ValueError('Save must match an Elements call issued by next')
    envelope = dict(call, savedAt=now(), ok=False, result=None, error=None)
    try:
        value = unwrap(payload)
        if not isinstance(value, (dict, list)):
            raise ValueError('Expected an Elements response object or list')
        if isinstance(value, dict) and (value.get('error') or value.get('errorCode') or value.get('isError') or value.get('status') in ('error', 'failed')):
            raise ValueError(str(value.get('message') or value.get('error') or 'Elements call failed'))
        envelope.update(ok=True, result=value)
    except (ValueError, TypeError) as error:
        envelope['error'] = classify('TRANSPORT', str(error))
    if envelope['ok'] and qid in ('E01', 'E02', 'E03') and isinstance(value, dict):
        file = value.get('file')
        fields = {'E01': ('referenceModels',), 'E02': ('nodes', 'results'), 'E03': ('items', 'nodes')}
        if isinstance(file, dict) and file.get('url') and not any(value.get(key) for key in fields[qid]):
            raise ValueError('Reply contains a download link: download file.url and pass the downloaded file with --from')
    name = qid if qid == 'E00' or qid == 'E01' and batch == 'b1' else qid + '.' + batch
    success, failure = directory / 'e' / (name + '.json'), directory / 'e' / (name + '.error.json')
    destination, obsolete = (success, failure) if envelope['ok'] else (failure, success)
    write_json(destination, envelope)
    obsolete.unlink(missing_ok=True)
    return envelope


def sf_runner(command):
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.stdout or completed.stderr


def gather(directory, target_org, line, runner=sf_runner):
    while True:
        due = next_queries(directory, line)
        if not due or due[0]['id'].startswith('E'):
            return due
        for query in due:
            command = ['sf', 'data', 'query', '--json', '--target-org', target_org, '--query', query['soql']]
            try:
                payload = runner(command)
            except (OSError, subprocess.SubprocessError) as error:
                payload = dict(errorCode='TRANSPORT', message=str(error))
            save_response(directory, query['id'], payload, attempt=query['attempt'], route='sf-cli')


def compute(directory):
    from pricing_compute import compute as calculate
    return calculate(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('next', help='Print due queries and Elements calls')
    plan.add_argument('--line', required=True)
    plan.add_argument('--dir', required=True)
    collection = commands.add_parser('gather', help='Collect Salesforce results using sf')
    collection.add_argument('--target-org', required=True)
    collection.add_argument('--line', required=True)
    collection.add_argument('--dir', required=True)
    save = commands.add_parser('save', help='Normalize a response from stdin or a file')
    save.add_argument('--dir', required=True)
    save.add_argument('--id', required=True)
    group = save.add_mutually_exclusive_group(required=True)
    group.add_argument('--attempt', type=int)
    group.add_argument('--batch')
    save.add_argument('--from', dest='source')
    calculation = commands.add_parser('compute', help='Write diagnostic.json and status.json')
    calculation.add_argument('--dir', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'next':
            result = next_queries(args.dir, args.line)
        elif args.command == 'gather':
            result = gather(args.dir, args.target_org, args.line)
        elif args.command == 'save':
            payload = Path(args.source).read_text(encoding='utf-8') if args.source else sys.stdin.read()
            result = save_response(args.dir, args.id, payload, attempt=args.attempt, batch=args.batch)
        else:
            compute(args.dir)
            result = read_json(Path(args.dir) / 'status.json')
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
