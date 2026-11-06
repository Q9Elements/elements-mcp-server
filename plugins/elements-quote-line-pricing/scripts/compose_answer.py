#!/usr/bin/env python3
"""Select pricing agents and compose their validated evidence-based answers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from pricing_common import read_json, table


def select(diagnostic, topics, full=False):
    diagnostic = read_json(diagnostic) if isinstance(diagnostic, (str, Path)) else diagnostic
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(',') if t.strip()]
    known = {r['topic'] for r in table('question-routing')}
    if not topics:
        raise ValueError('At least one topic is required')
    for topic in topics:
        if topic not in known:
            raise ValueError('Unknown topic: ' + topic)
    broad = full or 'broad' in topics
    agents = diagnostic['flags']['broadQuestionAgents'] if broad else topics
    agents = list(dict.fromkeys(agents))
    if any(s not in known - {'broad'} for s in agents):
        raise ValueError('Unknown agent in diagnostic broad flags')
    if broad:
        agents = [agent for agent in agents if agent != 'price-rules']
    return dict(agents=agents, mode='full' if full else 'single' if len(agents) == 1 else 'concise')


def diagnostic_value(diagnostic, path):
    path = path.removeprefix('$.')
    if not path or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.(?:\d+|[A-Za-z_][A-Za-z0-9_]*))*', path):
        raise ValueError('Unsupported evidence path')
    value = diagnostic
    for token in re.findall(r'[A-Za-z_][A-Za-z0-9_]*|\d+', path):
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def same_json_value(actual, observed):
    if isinstance(actual, bool) or isinstance(observed, bool):
        return isinstance(actual, bool) and isinstance(observed, bool) and actual == observed
    if isinstance(actual, dict) and isinstance(observed, dict):
        return actual.keys() == observed.keys() and all(same_json_value(actual[key], observed[key]) for key in actual)
    if isinstance(actual, list) and isinstance(observed, list):
        return len(actual) == len(observed) and all(same_json_value(a, b) for a, b in zip(actual, observed))
    return actual == observed


def validate_return(value, agent, diagnostic):
    """Validate core prose; record dropped evidence as gaps and stderr warnings."""
    if not isinstance(value, dict):
        raise ValueError('Return must be an object')
    if value.get('agent') != agent:
        raise ValueError('Agent does not match the return filename')
    if value.get('status') not in ('answered', 'not_applicable', 'cannot_answer'):
        raise ValueError('Invalid agent status')
    for field in ('summary', 'answer'):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(field + ' must be nonempty text')
    value = dict(value)
    gaps = []
    for item in value.get('gaps', []) if isinstance(value.get('gaps'), list) else []:
        if isinstance(item, dict) and all(isinstance(item.get(f), str) and item[f].strip() for f in ('what', 'reason')):
            gaps.append(item)
        else:
            gaps.append(dict(what='Dropped gap', reason='Gaps require what and reason text'))
    if not isinstance(value.get('gaps'), list):
        gaps.append(dict(what='Dropped gaps', reason='gaps must be an array'))
    valid, dropped = [], []
    evidence = value.get('evidence')
    if not isinstance(evidence, list):
        gaps.append(dict(what='Dropped evidence', reason='evidence must be an array'))
        dropped.append(dict(agent=agent, json_path='evidence'))
        evidence = []
    for index, item in enumerate(evidence):
        reason = None
        if not isinstance(item, dict) or not isinstance(item.get('json_path'), str) or 'value' not in item:
            reason = 'Evidence requires json_path and value'
        else:
            try:
                actual = diagnostic_value(diagnostic, item['json_path'])
            except (ValueError, KeyError, TypeError, IndexError):
                reason = 'Evidence path is unavailable: ' + item['json_path']
            else:
                if not same_json_value(actual, item['value']):
                    reason = 'Evidence value differs from diagnostic: ' + item['json_path']
        if reason:
            path = item.get('json_path', str(index)) if isinstance(item, dict) else str(index)
            gaps.append(dict(what='Dropped evidence: ' + str(path), reason=reason))
            dropped.append(dict(agent=agent, json_path=path))
        else:
            valid.append(item)
    value['evidence'], value['gaps'] = valid, gaps
    if dropped:
        print(json.dumps(dict(evidenceDropped=dropped)), file=sys.stderr)
    return value


def clean(text):
    return str(text).replace(chr(0x2014), ',')


def money(value):
    return 'unavailable' if value is None else f'{value:,.2f}'


def rule_lines(diagnostic, stages=None, indirect=False):
    """Group logged facts by rule, with calculator events and stored values."""
    labels = {row['field_api_name']: row['label'] for row in table('price-action-field-labels')}
    waterfall_fields = {row['sf_field']: row['label'] for row in table('waterfall-stages')}
    groups = {}
    for rule in diagnostic.get('priceRules', {}).get('rules', []):
        for action in rule['actions']:
            if (indirect and action['impact'] == 'indirect') or (not indirect and action['impact'] == 'direct' and action['waterfallStage'] in stages):
                name = rule.get('ruleName') or rule.get('ruleId') or 'Logged rule'
                key = rule.get('ruleId') or name
                group = groups.setdefault(key, dict(name=name, facts={}))
                api = action.get('targetFieldApiName') or action.get('targetField')
                field = waterfall_fields.get(api) or labels.get(api)
                if field is None and api:
                    field = re.sub(r'__c$', '', api)
                    field = field.split('__', 1)[-1]
                    field = re.sub(r'(?<=[a-z0-9])(?=[A-Z][a-z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', field).replace('_', ' ')
                field = field or 'unavailable field'
                value = action.get('valueAfterRule')
                if value is None:
                    rendered_value = 'unavailable'
                elif '%' in field:
                    try:
                        rendered_value = f'{float(value) * 100:g}% (stored as {value})'
                    except (TypeError, ValueError):
                        rendered_value = f'stored value: {value}'
                else:
                    rendered_value = f'stored value: {value}'
                fact = (api, field, rendered_value)
                events = group['facts'].setdefault(fact, [])
                event = rule.get('evaluationEvent') or 'unavailable event'
                if event not in events:
                    events.append(event)
    lines = []
    for group in groups.values():
        facts = [f"{field} ({value}) at {', '.join(events)}"
                 for (_, field, value), events in group['facts'].items()]
        lines.append(group['name'] + ': ' + '; '.join(facts) + '.')
    return '\n\n'.join(lines)


def rule_impact_summary(diagnostic):
    """Explain recorded impact tags without inferring a price difference."""
    price_rules = diagnostic.get('priceRules', {})
    if price_rules.get('status') != 'rules_fired':
        return ''
    actions = [action for rule in price_rules.get('rules', []) for action in rule['actions']]
    labels = {row['stage']: row['label'] for row in table('waterfall-stages')}
    labels['quantity'] = 'Quantity'
    field_labels = {row['field_api_name'] for row in table('price-action-field-labels')}
    unknown = [action for action in actions
               if action.get('targetObject') not in ('Quote', 'Quote Line')
               or not isinstance(action.get('targetFieldApiName') or action.get('targetField'), str)
               or (action.get('targetFieldApiName') or action.get('targetField')) not in field_labels
               or action.get('impact') not in ('direct', 'indirect')]
    if actions and not unknown and all(action['impact'] == 'indirect' for action in actions):
        return 'None of these rules changed a price: every action was indirect.'
    groups = {}
    for rule in price_rules.get('rules', []):
        name = rule.get('ruleName') or rule.get('ruleId') or 'Logged rule'
        key = rule.get('ruleId') or name
        for action in rule['actions']:
            if action.get('impact') == 'direct':
                group = groups.setdefault(key, dict(name=name, stages=[]))
                stage = labels.get(action.get('waterfallStage'), 'unavailable stage')
                if stage not in group['stages']:
                    group['stages'].append(stage)
    direct = ('Direct actions target price stages: ' + '; '.join(
        group['name'] + ' at ' + ', '.join(group['stages']) for group in groups.values()) + '.') if groups else ''
    if unknown:
        impact = f'The price impact of {len(unknown)} logged actions could not be determined from the recorded data.'
        return impact + ((' ' + direct) if direct else '')
    return direct


def rule_history_lines(diagnostic):
    """Render captured rule history once per fired rule, including unknown changers."""
    price_rules = diagnostic.get('priceRules', {})
    if price_rules.get('status') != 'rules_fired':
        return ''
    lines, seen = [], set()
    for rule in price_rules.get('rules', []):
        name = rule.get('ruleName') or rule.get('ruleId') or 'Logged rule'
        key = rule.get('ruleId') or name
        history = rule.get('history') or {}
        if key in seen or not history.get('entries'):
            continue
        seen.add(key)
        changer = history.get('lastChangedBy')
        changed_at = history.get('lastChangedAt') or 'not captured'
        try:
            timestamp = datetime.fromisoformat(str(changed_at).replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            changed_date = timestamp.astimezone(timezone.utc).date().isoformat()
        except ValueError:
            changed_date = 'not captured'
        if changer:
            lines.append(f'{name}: last changed by {changer} on {changed_date}.')
        else:
            lines.append(f'{name}: last changed on {changed_date}; who changed it was not captured.')
    return '\n\n'.join(lines)


def compose(diagnostic, returns, mode):
    """Assemble section facts and prose, explaining repeated passes before firing counts."""
    diagnostic = read_json(diagnostic) if isinstance(diagnostic, (str, Path)) else diagnostic
    if mode not in ('single', 'full', 'concise'):
        raise ValueError('Unknown composition mode')
    routes = {r['topic']: r['agent'] for r in table('question-routing') if r['topic'] != 'broad'}
    canned = {r['id']: r['text'] for r in table('canned-messages')}
    sections = sorted(table('report-sections'), key=lambda r: float(r['order']))
    answers, errors = {}, []
    for path in sorted(Path(returns).glob('*.json')):
        agent = path.stem.removesuffix('-agent')
        try:
            if agent not in routes:
                raise ValueError('Unknown agent filename')
            if agent in answers:
                raise ValueError('Duplicate agent return')
            answers[agent] = validate_return(read_json(path), agent, diagnostic)
        except (ValueError, OSError, TypeError) as error:
            errors.append(path.name + ': ' + str(error))
            if agent in routes:
                answers[agent] = None
    fallback = canned['FALLBACK']
    def answer(agent, needed=True):
        value = answers.get(agent)
        if value is None:
            if needed and agent not in answers:
                errors.append(agent + ': missing return')
            return fallback if needed else ''
        text = value['answer']
        for message_id in ('SCOPE-CALC-RULES', 'HISTORY-PER-SYNC'):
            text = text.replace(canned[message_id], '')
        return text.strip()
    flags = diagnostic['flags']
    price_rules = diagnostic.get('priceRules', {})
    fired_rules = price_rules.get('rules', [])
    distinct_rules = {
        rule.get('ruleId') or rule.get('ruleName') or 'Logged rule'
        for rule in fired_rules
    }
    if price_rules.get('status') in ('rules_fired', 'no_rules_fired'):
        firing_summary = (f"{len(fired_rules)} calculator price rule firings of "
                          f"{len(distinct_rules)} distinct rules were logged.")
    else:
        firing_summary = 'Calculator price rule firings could not be read.'
    pass_count = price_rules.get('passCount', 0)
    if pass_count is None:
        firing_summary = canned['CALCULATION-PASSES-AMBIGUOUS'] + '\n\n' + firing_summary
    elif pass_count > 1:
        firing_summary = (f"This line's log holds {pass_count} calculation passes from repeated recalculations; "
                          "the last pass is shown.\n\n" + firing_summary)
    paragraphs = []
    closing = None
    if mode in ('single', 'concise'):
        if not answers:
            paragraphs.append(fallback)
            errors.append('No agent returns')
        if mode == 'single' and len(answers) > 1:
            paragraphs.append(fallback)
            errors.append('Single mode requires one agent return')
        else:
            for agent in answers:
                text = answer(agent)
                paragraphs.append(text if mode == 'single' else f'### {routes[agent]}\n\n{text}')
    else:
        for section in sections:
            heading = section['section']
            order = section['order']
            content = ''
            if order == '1':
                net = next((s['unitPrice'] for s in diagnostic['priceWaterfall']['stages'] if s['stage'] == 'net'), None)
                currency = diagnostic['meta'].get('currencyIsoCode')
                content = f"{diagnostic['meta'].get('quoteLineName') or 'This quote line'}: Net Price: {money(net)}" + (' ' + currency if currency else '') + ' per unit.'
            elif order == '2':
                values = {s['stage']: s for s in diagnostic['priceWaterfall']['stages']}
                lines = ['| Stage | Unit price | Change | Source |', '| --- | ---: | ---: | --- |']
                for index, stage in enumerate(table('waterfall-stages')):
                    value = values.get(stage['stage'], {})
                    source = str(value.get('source') or '').replace('|', '\\|')
                    change = money(value.get('deltaFromPrevious')) if index else ''
                    lines.append(f"| {stage['label']} | {money(value.get('unitPrice'))} | {change} | {source} |")
                content = '\n'.join(lines)
            elif order == '3.1':
                content = answer('pricing-method')
                direct = rule_lines(diagnostic, {'original', 'list', 'special', 'prorated'})
                if direct:
                    content = (content + '\n\n' if content != fallback else '') + direct
            elif order == '3.2':
                direct = rule_lines(diagnostic, {'regular', 'customer', 'partner', 'net', 'quantity'})
                if flags.get('isDiscounted') or 'discount' in answers or direct:
                    content = answer('discount', needed=flags.get('isDiscounted') or 'discount' in answers)
                    if direct:
                        content = (content + '\n\n' if content != fallback else '') + direct
            elif order == '3.3':
                content = answer('bundle-and-options', flags.get('hasBundleContext') or 'bundle-and-options' in answers)
                if not content:
                    content = 'This line is standalone.'
            elif order == '3.4':
                if flags.get('isMdq') or 'mdq' in answers:
                    content = answer('mdq')
            elif order == '4':
                content = '\n\n'.join(filter(None, [
                    firing_summary,
                    answer('price-rules') if answers.get('price-rules') is not None else '',
                    rule_lines(diagnostic, indirect=True),
                    rule_impact_summary(diagnostic) if answers.get('price-rules') is None else '',
                    rule_history_lines(diagnostic),
                ]))
                if 'price-rules' in answers and answers.get('price-rules') is None and not content:
                    content = fallback
            elif order == '5':
                closing = f'### {heading}\n\nWhat else would you like to understand about this quote line?'
            if content:
                paragraphs.append(content if order == '1' else f'### {heading}\n\n{content}')
    for warning in diagnostic.get('warnings', []):
        row = next((r for r in table('warning-codes') if r['code'] == warning['code']), None)
        message_id = row['canned_message_id'] if row else ''
        message = canned.get(message_id) or warning['message']
        if not any(message in paragraph for paragraph in paragraphs):
            paragraphs.append(message)
    if diagnostic.get('contractedPrice', {}).get('status') == 'not_readable':
        paragraphs.append(canned['CONTRACTED-NOT-READABLE'])
    if 'price-rules' in answers or (mode == 'full' and diagnostic['priceRules'].get('rules')):
        paragraphs.append(canned['SCOPE-CALC-RULES'])
        if any(component.get('history', {}).get('status') == 'ok'
               for rule in fired_rules
               for component in [rule, *rule.get('conditions', []), *rule.get('actions', [])]):
            paragraphs.append(canned['HISTORY-PER-SYNC'])
    diagram = diagnostic.get('log', {}).get('diagramUrl')
    if diagram and urlparse(diagram).scheme in ('http', 'https'):
        url = diagram.replace(' ', '%20').replace('(', '%28').replace(')', '%29')
        paragraphs.append('[Quote Line Microscope diagram](' + url + ')')
    if closing:
        paragraphs.append(closing)
    return clean('\n\n'.join(paragraphs)) + '\n', errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    selection = commands.add_parser('select', help='Print the agent set and answer mode')
    selection.add_argument('--diagnostic', required=True)
    selection.add_argument('--topics', required=True)
    selection.add_argument('--full', action='store_true',
                           help='Use the broad agent set and full report for a first question or explicit full re-analysis')
    composition = commands.add_parser('compose', help='Print validated Markdown; validation errors and dropped evidence go to stderr')
    composition.add_argument('--diagnostic', required=True)
    composition.add_argument('--returns', required=True)
    composition.add_argument('--mode', required=True, choices=('single', 'full', 'concise'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'select':
            print(json.dumps(select(args.diagnostic, args.topics, full=args.full)))
        else:
            answer, errors = compose(args.diagnostic, args.returns, args.mode)
            print(answer, end='')
            if errors:
                print(json.dumps(dict(returnSchemaErrors=errors)), file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
