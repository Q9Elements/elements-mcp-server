"""Deterministic diagnostic calculations over normalized collection envelopes."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pricing_common import now, read_json, table, valid_id, write_json
from query_specs import SPECS
from quote_line_diagnostics import (BASE_TOTALS, PARENT_OBJECTS, active_team_id, dictionaries, dropped_columns, element_files, fields_in, first,
                                    latest, metadata_hits, method, next_queries, reference_model, rows)


def lower(value):
    return str(value).lower() if value is not None else ''


def nz(value):
    return value is not None and value != 0


def matches(a, b):
    return a is not None and b is not None and abs(a - b) <= max(.01, .0001 * abs(b))


def recorded_price_matches(a, b):
    """Require numeric equality before assigning a recorded List Price source."""
    try:
        a, b = Decimal(str(a)), Decimal(str(b))
        return a.is_finite() and b.is_finite() and a == b
    except InvalidOperation:
        return False


def multiply(a, b):
    return None if a is None or b is None else a * b


def reduce_price(price, percent=None, amount=None):
    if price is None:
        return None
    return price * (1 - percent / 100) if percent is not None else price - (amount or 0)


def pick(*values):
    return next((v for v in values if v is not None), None)


def same(a, b):
    return bool(valid_id(a) and valid_id(a) == valid_id(b))


def timestamp(value):
    if not value:
        return None
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def iso(value):
    return timestamp(value).isoformat(timespec='milliseconds').replace('+00:00', 'Z') if value else None


def get_field(row, field):
    current = row
    for part in field.split('.'):
        if current is None:
            return True, None
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


SECTIONS = dict(P01='line', P02='log', P03='quote', P04='product', P05='priceWaterfall',
                P06='bundle.option', P07='bundle.parent', P08='line', P09='contractedPrice',
                P10='discounts', P11='discounts', P12='pricingMethod.block',
                P13='mdq', P14='pricingMethod.percentOfTotal', P15='mdq', P16='priceRules',
                P17='priceRules', P18='bundle.children', P19='priceRules.historySource', P20='priceRules')


class Calculation:
    def __init__(self, directory, empty=False):
        self.empty = empty
        self.directory = Path(directory)
        plan_path = self.directory / 'q/plan.json'
        self.plan = read_json(plan_path)['queries'] if plan_path.exists() and not empty else {q: dict(state='due', reason=None) for q in SPECS}
        self.envelopes = {q: None if empty else latest(directory, q) for q in SPECS}
        self.records = {q: [] if empty else rows(directory, q) for q in SPECS}
        self.sources = {}
        self.warning_rows = {r['code']: r for r in table('warning-codes')}
        self.warnings = []
        self.gaps = []

    def row(self, qid):
        return next(iter(self.records[qid]), {})

    def value(self, qid, field, path=None, row=None):
        field = field if field.startswith(('SBQQ__', 'Q9_QLM__')) or (field == 'UnitPrice' and qid == 'P05') or field in ('Id', 'Name', 'LastModifiedDate', 'CreatedDate', 'CurrencyIsoCode', 'IsActive', 'ProductCode', 'Family', 'StockKeepingUnit', 'OverageRate__c', 'Pricebook2.Name') else 'SBQQ__' + field + '__c'
        if path:
            self.sources.setdefault((qid, field), set()).add(path)
        return get_field(self.row(qid) if row is None else row, field)[1]

    def mapped(self, qid, section, mapping, row=None):
        return {key: self.value(qid, field, section + '.' + key, row) for key, field in mapping.items()}

    def state(self, qid):
        plan, envelope = self.plan[qid], self.envelopes[qid]
        if plan['state'] == 'not_applicable':
            return dict(status='not_applicable', statusReason=plan['reason'])
        if not envelope:
            return dict(status='query_failed', statusReason=qid + ' not run')
        if not envelope['ok']:
            return dict(status='not_readable' if envelope['error']['kind'] == 'object_not_readable' else 'query_failed',
                        statusReason=envelope['error']['message'])
        return dict(status='ok' if envelope['records'] else 'none', statusReason=None)

    def warning(self, code, paths):
        existing = next((w for w in self.warnings if w['code'] == code), None)
        if existing:
            existing['paths'] = sorted(set(existing['paths'] + paths))
        else:
            row = self.warning_rows[code]
            self.warnings.append(dict(code=code, severity=row['severity'], message=row['meaning'], paths=paths))

    def access_gaps(self):
        if self.empty:
            return
        permissions = table('required-access')
        for qid, spec in SPECS.items():
            envelope = self.envelopes[qid]
            losses = []
            for path in sorted((self.directory / 'q').glob(qid + '.a*.error.json')):
                error = read_json(path)['error']
                if error['kind'] in ('field_not_readable', 'relationship_not_readable', 'object_not_readable'):
                    losses.append((error.get('field'), error['kind'], error.get('object') or spec['object'], error['message']))
            if envelope and envelope['ok']:
                for field in fields_in(envelope['soql']):
                    if any(not get_field(row, field)[0] for row in envelope['records']):
                        losses.append((field, 'field_not_readable', spec['object'], 'Selected field omitted from returned record'))
                if qid in ('P06', 'P07', 'P09') and not envelope['records']:
                    losses.append((None, 'record_not_shared', spec['object'], 'Lookup is set but the record is not visible'))
            seen = set()
            for field, kind, obj, message in losses:
                affected_fields = dropped_columns(dict(kind=kind, field=field, object=obj), spec['fields'], spec['object'])
                if affected_fields and all(f in spec['optional'] for f in affected_fields) and kind == 'field_not_readable':
                    kind = 'optional_field_absent'
                if kind == 'relationship_not_readable':
                    obj = PARENT_OBJECTS.get(field, obj)
                key = (obj, field, kind)
                if key in seen:
                    continue
                seen.add(key)
                required = any(r['query_id'] == qid and r['object'] == obj and r['required'] == 'true' and
                    (r['field'] == field or (not r['field'] and kind == 'object_not_readable')) for r in permissions)
                paths = sorted({p for f in affected_fields for p in self.sources.get((qid, f), [])})
                self.gaps.append(dict(object=obj, field=field, kind=kind, query=qid, required=required,
                                      affects=paths or [SECTIONS[qid]], message=message))

    def outcome(self, failure=None):
        errors = [(q, e['error']) for q, e in self.envelopes.items() if e and not e['ok'] and q not in ('P19', 'P20')]
        pending = [q for q, state in self.plan.items() if state['state'] == 'due' and q not in ('P19', 'P20')]
        status = 'compute_error' if failure else 'built'
        if any(e['kind'] == 'transport' for q, e in errors):
            status = 'route_error'
        elif self.envelopes['P01'] and self.envelopes['P01']['ok'] and len(self.records['P01']) != 1:
            status = 'line_not_found'
        elif any(q in ('P01', 'P02', 'P03') and e['kind'] == 'object_not_readable' for q, e in errors):
            status = 'package_missing'
        elif any(g['required'] for g in self.gaps):
            status = 'access_gap'
        elif self.envelopes['P02'] and self.envelopes['P02']['ok'] and not self.records['P02']:
            status = 'no_log'
        elif pending or any(e['kind'] in ('incomplete', 'malformed', 'limit', 'unknown') for q, e in errors):
            status = 'query_error'
        messages = ([failure] if failure else []) + [q + ' not run' for q in pending] + [q + ': ' + e['message'] for q, e in errors]
        return status, '; '.join(messages) or None

    def build(self):
        v = self.value
        line = dict(self.state('P01'), **self.mapped('P01', 'line', dict(
            quantity='Quantity', effectiveQuantity='EffectiveQuantity', priorQuantity='PriorQuantity', number='Number',
            groupId='Group', isOptional='Optional', isExisting='Existing', isRenewal='Renewal',
            renewedSubscriptionId='RenewedSubscription', upgradedSubscriptionId='UpgradedSubscription',
            loggingEnabled='Q9_QLM__Quote_Line_Logging_Enabled__c')))
        line['groupName'] = v('P08', 'Name', 'line.groupName')
        line['totals'] = self.mapped('P01', 'line.totals', {key[0].lower() + key[1:] + 'Total': key + 'Total' for key in ('List', 'Regular', 'Customer', 'Net')})
        quote = dict(self.state('P03'), **self.mapped('P03', 'quote', dict(id='Id', name='Name', type='Type',
            priceBookId='PriceBook', priceBookName='SBQQ__PriceBook__r.Name', startDate='StartDate', endDate='EndDate',
            subscriptionTermMonths='SubscriptionTerm', additionalDiscountPercent='CustomerDiscount', partnerDiscountPercent='PartnerDiscount',
            distributorDiscountPercent='DistributorDiscount', firstSegmentTermEndDate='FirstSegmentTermEndDate')))
        quote['priceBookId'] = pick(quote['priceBookId'], v('P03', 'PricebookId', 'quote.priceBookId'))
        subscription = pick(v('P01', 'SubscriptionPricing', 'product.isSubscription'), v('P04', 'SubscriptionPricing', 'product.isSubscription'))
        is_subscription = lower(subscription) in ('fixed price', 'percent of total')
        product = dict(self.state('P04'), **self.mapped('P04', 'product', dict(id='Id', name='Name', code='ProductCode', family='Family', sku='StockKeepingUnit',
            isActive='IsActive', pricingMethod='PricingMethod', pricingMethodEditable='PricingMethodEditable', subscriptionPricing='SubscriptionPricing',
            subscriptionType='SubscriptionType', defaultSubscriptionTermMonths='SubscriptionTerm', nonDiscountable='NonDiscountable',
            nonPartnerDiscountable='NonPartnerDiscountable', termDiscountLevel='TermDiscountLevel', blockPricingField='BlockPricingField',
            discountScheduleId='DiscountSchedule', termDiscountScheduleId='TermDiscountSchedule')))
        product.update(isSubscription=is_subscription, name=pick(product['name'], v('P01', 'SBQQ__Product__r.Name', 'product.name')),
                       code=pick(product['code'], v('P01', 'SBQQ__Product__r.ProductCode', 'product.code')))
        pm_type = method(self.row('P01'))
        supported = lower(pm_type) in ('list', 'cost', 'block', 'percent of total', 'custom')
        flags = dict(pricingMethodType=pm_type, isSupportedPricingMethod=supported,
            isOption=v('P01', 'RequiredBy', 'flags.isOption') is not None,
            isBundleParent=v('P01', 'Bundle', 'flags.isBundleParent') is True,
            isMdq=v('P01', 'Dimension', 'flags.isMdq') is not None)
        flags['hasBundleContext'] = flags['isOption'] or flags['isBundleParent']
        flags['isBundledOption'] = flags['isOption'] and (v('P01', 'Bundled') is True or v('P06', 'Bundled') is True)
        pm = dict(self.state('P01'), type=pm_type, productMethod=product['pricingMethod'], isEditable=v('P01', 'PricingMethodEditable', 'pricingMethod.isEditable'),
                  originalPricingMethod=None, basePriceSource='Price Book', list=None, cost=None, block=None, percentOfTotal=None, custom=None)
        product_type = method(self.row('P04'))
        if pm['isEditable'] and lower(product_type) != lower(pm_type):
            pm['originalPricingMethod'] = product_type
        prices = {r['stage']: v('P01', r['sf_field'], 'priceWaterfall.stages') for r in table('waterfall-stages')}
        manual = v('P01', 'PriceEditable') is True and not matches(prices['list'], prices['original'])
        if lower(pm_type) == 'list':
            pm['list'] = dict(priceEditable=v('P01', 'PriceEditable', 'pricingMethod.list.priceEditable'), manualListEdit=manual)
        if lower(pm_type) == 'custom':
            pm['custom'] = dict(explainedStage='customer')
        proration = dict(self.state('P01'), applies=is_subscription, multiplier=1 if not is_subscription else v('P01', 'ProrateMultiplier'),
            **dict.fromkeys(('effectiveTermMonths', 'defaultTermMonths', 'defaultTermSource', 'effectiveStartDate', 'effectiveEndDate', 'startDateSource', 'endDateSource',
                             'termSource', 'expectedMultiplierFromTerm', 'multiplierExplainedBy', 'expectedProratedPrice', 'matchesProrated')))
        cp = dict(self.state('P09'), **self.mapped('P09', 'contractedPrice', dict(id='Id', name='Name', price='Price', discountPercent='Discount', effectiveDate='EffectiveDate',
            expirationDate='ExpirationDate', description='Description', discountScheduleId='DiscountSchedule', filterField='FilterField', filterValue='FilterValue', operator='Operator')),
            kind=None, isWithinDates=None, appliesToMethod=None, expectedSpecialPrice=None, matchesSpecial=None)
        if cp['status'] == 'none':
            cp.update(status='not_readable', statusReason='Contracted price lookup is set but record is not visible')
        discounts = dict(self.state('P01'), isDiscountable=not (v('P01', 'NonDiscountable') or product['nonDiscountable']),
            isPartnerDiscountable=not (v('P01', 'NonPartnerDiscountable') or product['nonPartnerDiscountable']),
            option={}, quantitySchedule={}, termSchedule={}, scheduleReconciliation={}, additional={}, partner={}, distributor={}, anyApplied=False, appliedList=[])
        bundle = dict(self.state('P01'), role='parent_and_option' if flags['isOption'] and flags['isBundleParent'] else 'option' if flags['isOption'] else 'parent' if flags['isBundleParent'] else 'standalone',
            option=None, parent=None, children=[], childrenTotals=dict(count=0, netTotalSum=0, bundledCount=0),
            bundledZeroing=dict(applies=flags['isBundledOption'], zeroedStages=[k for k in ('special', 'prorated', 'regular', 'customer', 'partner', 'net') if prices[k] == 0],
                               nonZeroContradiction=flags['isBundledOption'] and prices['net'] is not None and prices['net'] != 0))
        mdq = dict(self.state('P15'), currentSegmentIndex=v('P01', 'SegmentIndex'), currentSegmentLabel=v('P01', 'SegmentLabel'), currentDimensionType=None,
            segmentKey=v('P01', 'SegmentKey'), grouping='segmentKey' if v('P01', 'SegmentKey') is not None else 'dimension', segments=[], summary={})
        rules = dict(self.state('P16'), scope="Calculator price rules logged by QLM. Configurator-scope rules, actions targeting Quote Line Group or custom objects, and repeat firings within one event are not recorded.",
            passCount=0, passCountSource=None, rules=[], historySource=dict(status='no_reference_model', refModelId=None, refModelName=None, orgId=v('P19', 'Id')),
            rulesWithoutActions=[], quoteLineFieldsUpdated=[], quoteFieldsUpdated=[], directActionCount=0, indirectActionCount=0)
        rules['status'] = 'no_log' if not self.records['P02'] else 'no_rules_fired' if self.state('P16')['status'] in ('none', 'not_applicable') else self.state('P16')['status']
        log = dict(self.state('P02'), **self.mapped('P02', 'log', dict(id='Id', name='Name', modifiedAt='Q9_QLM__Modified_DateTime__c', createdAt='CreatedDate',
            modifiedBy='Q9_QLM__ModifiedBy__c', appSource='Q9_QLM__Quote_Line_Log_App_Source__c', diagramUrl='Q9_QLM__Diagram_Url__c')),
            lineLastModifiedAt=v('P01', 'LastModifiedDate'), lagSeconds=None, stale=False, staleRule='line saved more than 120 s after the log was written')
        waterfall = dict(self.state('P01'), currency=pick(v('P01', 'CurrencyIsoCode'), v('P03', 'CurrencyIsoCode')), stages=[],
            pricebookEntryPrice=v('P05', 'UnitPrice'), originalMatchesPricebook=matches(prices['original'], v('P05', 'UnitPrice')))
        self.diagnostic = dict(schemaVersion='2.0', meta=dict(generatedAt=now(), route=next((e['route'] for e in self.envelopes.values() if e), None),
            quoteLineId=v('P01', 'Id', 'meta.quoteLineId'), quoteLineName=v('P01', 'Name', 'meta.quoteLineName'), quoteId=quote['id'], quoteName=quote['name'], currencyIsoCode=waterfall['currency'],
            lineLastModifiedAt=v('P01', 'LastModifiedDate', 'meta.lineLastModifiedAt'), quoteLastCalculatedAt=v('P03', 'LastCalculatedOn', 'meta.quoteLastCalculatedAt'), quoteUncalculated=v('P03', 'Uncalculated', 'meta.quoteUncalculated')),
            flags=flags, line=line, quote=quote, product=product, priceWaterfall=waterfall, pricingMethod=pm, contractedPrice=cp, proration=proration,
            discounts=discounts, bundle=bundle, mdq=mdq, priceRules=rules, log=log, accessGaps=self.gaps, warnings=self.warnings)
        for container, keys in [(self.diagnostic['meta'], ('lineLastModifiedAt', 'quoteLastCalculatedAt')), (log, ('modifiedAt', 'createdAt', 'lineLastModifiedAt'))]:
            for key in keys:
                container[key] = iso(container[key])
        if log['modifiedAt'] and log['lineLastModifiedAt']:
            log['lagSeconds'] = (timestamp(log['lineLastModifiedAt']) - timestamp(log['modifiedAt'])).total_seconds()
            log['stale'] = log['lagSeconds'] > 120
        if log['stale']:
            self.warning('STALE_LOG', ['log.stale'])
        flags.update(isDiscounted=False, hasPriceRulesApplied=False, hasBlockPriceOverage=False, broadQuestionAgents=['pricing-method'])
        calculate_proration(self, proration, flags, prices)
        calculate_cost(self, pm, proration, prices)
        calculate_block(self, pm, flags, prices, quote, product)
        calculate_pot(self, pm, flags, prices)
        calculate_schedules(self, discounts, pm, flags, prices, proration, product)
        calculate_contracted(self, cp, pm, prices, quote)
        calculate_discounts(self, discounts, cp, flags, prices, proration)
        calculate_bundle(self, bundle, flags)
        calculate_mdq(self, mdq, flags)
        calculate_rules(self, rules, flags)
        direct_list_rule_write = any(action['impact'] == 'direct' and action['waterfallStage'] == 'list'
            and recorded_price_matches(action['valueAfterRule'], prices['list'])
            for rule in rules['rules'] for action in rule['actions'])
        matching_option_price = recorded_price_matches(v('P06', 'UnitPrice'), prices['list'])
        matching_book_price = recorded_price_matches(v('P05', 'UnitPrice'), prices['list'])
        list_source = 'Percent Of Total' if lower(pm_type) == 'percent of total' else 'Block Price' if pm['block'] and pm['block']['tier'] else 'Price Dimension' if flags['isMdq'] and any(r['isCurrent'] and r['dimensionUnitPrice'] is not None for r in mdq['segments']) else 'Price Rule' if direct_list_rule_write else 'Option Unit Price' if matching_option_price else 'Manual List Edit' if manual else 'Price Book' if matching_book_price else 'not determined from the recorded data'
        bundled_special = flags['isBundledOption'] and prices['special'] == 0
        special_source = 'Bundled' if bundled_special else v('P01', 'SpecialPriceType') or ('Cost Plus Markup' if lower(pm_type) == 'cost' and not matches(prices['special'], prices['list']) else 'Option Discount' if nz(discounts['option'].get('percent')) or nz(discounts['option'].get('amount')) else None if matches(prices['special'], prices['list']) else 'Unknown')
        pm['basePriceSource'] = 'Custom (Customer Price)' if lower(pm_type) == 'custom' else special_source or list_source
        previous = None
        for row in table('waterfall-stages'):
            stage, price = row['stage'], prices[row['stage']]
            source = 'Price Book' if stage == 'original' else list_source if stage == 'list' else special_source if stage == 'special' else 'Proration' if stage == 'prorated' and proration['multiplier'] != 1 else None
            if stage == 'regular':
                source = 'Bundled' if flags['isBundledOption'] and price == 0 and not bundled_special else 'Discount Schedule' if any(s['status'] in ('applied', 'price_tier') for s in (discounts['quantitySchedule'], discounts['termSchedule'])) else None
            if stage in ('customer', 'partner', 'net'):
                block = discounts[{'customer': 'additional', 'partner': 'partner', 'net': 'distributor'}[stage]]
                source = {'customer': 'Additional Discount', 'partner': 'Partner Discount', 'net': 'Distributor Discount'}[stage] if block['status'] == 'applied' else None
            waterfall['stages'].append(dict(stage=stage, label=row['label'], field=row['sf_field'], unitPrice=price, deltaFromPrevious=price - previous if price is not None and previous is not None else None,
                source=source, sourceDetail=v('P01', 'SpecialPriceDescription') if stage == 'special' else pm['block']['tier']['name'] if stage == 'list' and pm['block'] and pm['block']['tier'] else None, ownerAgent=row['owner_agent'], ruleWrites=[]))
            previous = price
        for stage in waterfall['stages']:
            stage['ruleWrites'] = [a['actionEvaluationId'] for r in rules['rules'] for a in r['actions'] if a['impact'] == 'direct' and a['waterfallStage'] == stage['stage']]
        # The routing table supplies the agent names and the gate vocabulary.
        gate_names = {r['flag']: r['gates_agent'].removesuffix(' gate') for r in table('routing-flags') if r['gates_agent'].endswith(' gate')}
        flags['broadQuestionAgents'] = ['pricing-method'] + [gate_names[f] for f in ('isDiscounted', 'hasBundleContext', 'isMdq') if flags[f]]
        self.access_gaps()
        return self.diagnostic


def compute(directory):
    directory = Path(directory)
    diagnostic, calculation, failure = None, None, None
    try:
        if (directory / 'q/plan.json').exists():
            plan = read_json(directory / 'q/plan.json')
            next_queries(directory, plan['line'])
        calculation = Calculation(directory)
        diagnostic = calculation.build()
    except Exception as error:
        failure = str(error)
        diagnostic = Calculation(directory, empty=True).build()
        for section in SECTIONS.values():
            name = section.split('.')[0]
            if name in diagnostic and isinstance(diagnostic[name], dict):
                diagnostic[name].update(status='query_failed', statusReason=failure)
        if calculation:
            calculation.access_gaps()
            diagnostic['accessGaps'] = calculation.gaps
            diagnostic['meta']['quoteLineId'] = calculation.row('P01').get('Id')
            diagnostic['meta']['quoteLineName'] = calculation.row('P01').get('Name')
    status, message = ('compute_error' if failure else 'built'), failure
    if calculation:
        status, message = calculation.outcome(failure)
    if status not in ('built', 'compute_error'):
        diagnostic['warnings'] = [warning for warning in diagnostic['warnings']
                                  if warning['code'] != 'HISTORY_UNAVAILABLE']
    if diagnostic:
        write_json(directory / 'diagnostic.json', diagnostic)

    write_json(directory / 'status.json', dict(status=status, warnings=diagnostic['warnings'] if diagnostic else [],
        quote_line_id=diagnostic['meta']['quoteLineId'] if diagnostic else None,
        log_modified_at=diagnostic['log']['modifiedAt'] if diagnostic else None,
        line_last_modified=diagnostic['meta']['lineLastModifiedAt'] if diagnostic else None,
        stale=diagnostic['log']['stale'] if diagnostic else None, message=message))
    return diagnostic


def calculate_proration(c, p, flags, prices):
    if not p['applies']:
        return
    v = c.value
    p.update(c.mapped('P01', 'proration', dict(multiplier='ProrateMultiplier', effectiveTermMonths='EffectiveSubscriptionTerm',
        effectiveStartDate='EffectiveStartDate', effectiveEndDate='EffectiveEndDate')))
    for qid, field, source in [('P01', 'DefaultSubscriptionTerm', 'Quote Line'), ('P04', 'SubscriptionTerm', 'Product')]:
        value = v(qid, field, 'proration.defaultTermMonths')
        if value is not None:
            p.update(defaultTermMonths=value, defaultTermSource=source)
            break
    else:
        p.update(defaultTermMonths=12, defaultTermSource='Default 12')
    p['startDateSource'] = 'Subscription Term'
    for qid, source in [('P01', 'Quote Line'), ('P08', 'Quote Line Group'), ('P03', 'Quote')]:
        if v(qid, 'StartDate', 'proration.startDateSource') is not None:
            p['startDateSource'] = source
            break
    p['endDateSource'] = 'Quote Subscription Term'
    for qid, field, source in [('P01', 'EndDate', 'Quote Line End Date'), ('P08', 'EndDate', 'Quote Line Group End Date'),
        ('P03', 'EndDate', 'Quote End Date'), ('P01', 'SubscriptionTerm', 'Quote Line Subscription Term'),
        ('P08', 'SubscriptionTerm', 'Quote Line Group Subscription Term')]:
        if v(qid, field, 'proration.endDateSource') is not None:
            p['endDateSource'] = source
            break
    p['termSource'] = 'dates' if 'End Date' in p['endDateSource'] else 'term'
    p['expectedMultiplierFromTerm'] = p['effectiveTermMonths'] / p['defaultTermMonths'] if p['effectiveTermMonths'] is not None and p['defaultTermMonths'] else None
    p['multiplierExplainedBy'] = 'term' if matches(p['expectedMultiplierFromTerm'], p['multiplier']) else 'dates' if p['termSource'] == 'dates' else 'unexplained'
    dimension = next((r for r in c.records['P13'] if same(r.get('Id'), v('P01', 'Dimension'))), {})
    multiplier = 1 if lower(dimension.get('SBQQ__Type__c')) == 'one-time' else p['multiplier']
    p['expectedProratedPrice'] = multiply(prices['special'], multiplier)
    p['matchesProrated'] = matches(p['expectedProratedPrice'], prices['prorated'])


def calculate_cost(c, pm, proration, prices):
    if lower(pm['type']) != 'cost':
        return
    cost = c.mapped('P01', 'pricingMethod.cost', dict(unitCost='UnitCost', originalUnitCost='OriginalUnitCost', costEditable='CostEditable', markupPercent='MarkupRate', markupAmount='MarkupAmount'))
    cost['status'] = 'not_readable' if any(not get_field(c.row('P01'), f'SBQQ__{f}__c')[0] for f in ('UnitCost', 'OriginalUnitCost', 'MarkupRate', 'MarkupAmount')) else 'ok'
    cost['statusReason'] = 'Cost or markup field is not readable' if cost['status'] == 'not_readable' else None
    cost['markupKind'] = 'percent' if cost['markupPercent'] is not None else 'amount' if cost['markupAmount'] is not None else 'none'
    unit = cost['unitCost']
    cost['expectedSpecialPrice'] = None if unit is None else unit * (1 + cost['markupPercent'] / 100) if cost['markupPercent'] is not None else unit + (cost['markupAmount'] or 0)
    cost['expectedProratedPrice'] = multiply(cost['expectedSpecialPrice'], proration['multiplier'])
    cost['matchesSpecial'] = matches(cost['expectedSpecialPrice'], prices['special'])
    pm['cost'] = cost


def calculate_block(c, pm, flags, prices, quote, product):
    if lower(pm['type']) != 'block':
        return
    v = c.value
    currency = pick(v('P01', 'CurrencyIsoCode'), v('P03', 'CurrencyIsoCode'))
    ladder = []
    for row in c.records['P12']:
        book = row.get('SBQQ__PriceBook2__c')
        if currency and row.get('CurrencyIsoCode') != currency:
            continue
        if book is not None and not same(book, quote['priceBookId']):
            continue
        entry = c.mapped('P12', 'pricingMethod.block.ladder', dict(id='Id', name='Name', lowerBound='LowerBound', upperBound='UpperBound', price='Price', overageRate='OverageRate__c'), row)
        entry['isCurrentTier'] = same(row.get('Id'), v('P01', 'BlockPrice'))
        ladder.append(entry)
    ladder.sort(key=lambda r: (r['lowerBound'] is not None, r['lowerBound'] or 0))
    tier = next((dict(r, upperBoundIsExclusive=True) for r in ladder if r['isCurrentTier']), None)
    if tier:
        tier.pop('isCurrentTier')
    quantity = v('P01', 'Quantity')
    overage = max(0, quantity - tier['lowerBound']) if tier and tier['overageRate'] is not None and tier['lowerBound'] is not None and quantity is not None else 0
    expected = tier['price'] + overage * (tier['overageRate'] or 0) if tier and tier['price'] is not None else None
    pm['block'] = dict(c.state('P12'), tier=tier, ladder=ladder, blockPricingField=product['blockPricingField'], overageQuantity=overage, expectedListPrice=expected, matchesList=matches(expected, prices['list']))
    if product['blockPricingField'] and lower(product['blockPricingField']) != 'quantity':
        c.warning('BLOCK_BASIS_NOT_QUANTITY', ['pricingMethod.block.blockPricingField'])
    flags['hasBlockPriceOverage'] = bool(tier and tier['overageRate'] is not None and quantity is not None and tier['lowerBound'] is not None and quantity > tier['lowerBound'])


def calculate_pot(c, pm, flags, prices):
    if lower(pm['type']) != 'percent of total':
        return
    v = c.value
    p = dict(c.state('P14'), **c.mapped('P04', 'pricingMethod.percentOfTotal', dict(category='SubscriptionCategory', target='SubscriptionTarget', constraint='DynamicPricingConstraint',
        includeFlag='IncludeInMaintenance', excludeFlag='ExcludeFromMaintenance')),
        percent=None, percentSource=None, baseField=None, baseFieldSource='not set', quoteLineScope=v('P01', 'SubscriptionScope'),
        bundleScope=pick(v('P06', 'SubscriptionScope'), v('P01', 'ComponentSubscriptionScope')), rows=[], totalBaseAmount=0, totalBaseAmountProrated=0,
        contributingCount=0, expectedListPrice=None, expectedListPriceProrated=None, baseThatMatches='neither', matchesList=False, hasCategoryWarning=False)
    for key, field in [('percent', 'SubscriptionPercent'), ('baseField', 'SubscriptionBase')]:
        for qid, source in [('P01', 'Quote Line'), ('P04', 'Product')]:
            value = v(qid, field, 'pricingMethod.percentOfTotal.' + key)
            if value is not None:
                p[key], p['percentSource' if key == 'percent' else 'baseFieldSource'] = value, source
                break
    p['hasCategoryWarning'] = p['category'] is None
    base = next((field for name, field in BASE_TOTALS.items() if lower(name) == lower(p['baseField'])), None)
    all_rows = c.records['P14'] + c.records['P01']
    by_id = {valid_id(r.get('Id')): r for r in all_rows}
    def root(row):
        key, seen = valid_id(row.get('Id')), set()
        while key and key not in seen:
            seen.add(key)
            parent = valid_id(by_id.get(key, {}).get('SBQQ__RequiredBy__c'))
            if not parent:
                return key
            key = parent
        return None
    parent = v('P01', 'RequiredBy')
    group = v('P01', 'Group')
    unreadable_base = False
    for row in c.records['P14']:
        subscription = row.get('SBQQ__SubscriptionPricing__c')
        sub = bool(subscription)
        pot = lower(subscription) == 'percent of total' or row.get('SBQQ__SubscriptionPercent__c') is not None
        in_scope, scope_reason = True, 'Quote'
        if lower(p['quoteLineScope']) == 'group' and group:
            in_scope, scope_reason = same(group, row.get('SBQQ__Group__c')), 'Group'
        if in_scope and parent and p['bundleScope']:
            scope_reason = p['bundleScope']
            package, components = same(row.get('Id'), parent), same(row.get('SBQQ__RequiredBy__c'), parent)
            scope = lower(p['bundleScope'])
            if scope in ('package', 'components', 'both', 'entire hierarchy'):
                in_scope = package if scope == 'package' else components if scope == 'components' else package or components if scope == 'both' else root(row) is not None and root(row) == root(c.row('P01'))
        category = get_field(row, 'SBQQ__Product__r.SBQQ__SubscriptionCategory__c')[1]
        category_matched = p['category'] is not None and category == p['category']
        include = get_field(row, 'SBQQ__Product__r.SBQQ__IncludeInMaintenance__c')[1]
        exclude = get_field(row, 'SBQQ__Product__r.SBQQ__ExcludeFromMaintenance__c')[1]
        included = False
        if not in_scope:
            reason = 'Outside Scope'
        elif row.get('SBQQ__Optional__c') is True:
            reason = 'Optional Line'
        elif pot:
            reason = 'PoT Product (Never Included)'
        elif p['category'] is not None and not category_matched:
            reason = 'Wrong Category'
        elif include:
            included, reason = True, 'Explicit Include'
        elif exclude:
            reason = 'Explicit Exclusion'
        elif not sub:
            included, reason = True, 'Default One-time'
        else:
            reason = 'Default Subscription'
        if base:
            c.sources.setdefault(('P14', base), set()).add('pricingMethod.percentOfTotal.rows')
            base_readable, prorated = get_field(row, base)
            unreadable_base |= included and not base_readable
        else:
            prorated = None
        contribution = prorated
        multiplier = row.get('SBQQ__ProrateMultiplier__c')
        if sub and prorated is not None:
            if multiplier:
                contribution = prorated / multiplier
            else:
                c.warning('POT_UNPRORATE_FAILED', ['pricingMethod.percentOfTotal.rows'])
        p['rows'].append(dict(quoteLineId=row.get('Id'), name=row.get('Name'), isSubscription=sub, isPercentOfTotal=pot,
            inScope=in_scope, scopeReason=scope_reason, isIncluded=included, reason=reason, categoryMatched=category_matched,
            contribution=contribution, contributionProrated=prorated))
        if included:
            p['contributingCount'] += 1
            p['totalBaseAmount'] += contribution or 0
            p['totalBaseAmountProrated'] += prorated or 0
    if base is None or unreadable_base:
        p['totalBaseAmount'] = p['totalBaseAmountProrated'] = None
    p['expectedListPrice'] = multiply(p['totalBaseAmount'], p['percent'] / 100 if p['percent'] is not None else None)
    p['expectedListPriceProrated'] = multiply(p['totalBaseAmountProrated'], p['percent'] / 100 if p['percent'] is not None else None)
    a, b = matches(p['expectedListPrice'], prices['list']), matches(p['expectedListPriceProrated'], prices['list'])
    p['matchesList'] = a or b
    p['baseThatMatches'] = 'both' if a and b else 'unprorated' if a else 'prorated' if b else 'neither'
    envelope = c.envelopes['P14']
    if envelope and envelope.get('incomplete'):
        c.warning('POT_SIBLINGS_TRUNCATED', ['pricingMethod.percentOfTotal.rows'])
    pm['percentOfTotal'] = p


def schedule_source(c, schedule):
    sid = schedule['originalScheduleId'] if schedule['isUserDefined'] else schedule['id']
    for qid, field, source in [('P09', 'DiscountSchedule', 'Contracted Price'), ('P06', 'DiscountSchedule', 'Product Option'),
        ('P06', 'SBQQ__Feature__r.SBQQ__DiscountSchedule__c', 'Feature'),
        ('P13', 'DiscountSchedule', 'Price Dimension'), ('P13', 'TermDiscountSchedule', 'Price Dimension'),
        ('P04', 'DiscountSchedule', 'Product'), ('P04', 'TermDiscountSchedule', 'Product')]:
        row = next((r for r in c.records['P13'] if same(r.get('Id'), c.value('P01', 'Dimension'))), {}) if qid == 'P13' else None
        if same(sid, c.value(qid, field, 'discounts', row)):
            return source
    return 'Unknown'


def calculate_schedule(c, term, product):
    v = c.value
    name = 'termSchedule' if term else 'quantitySchedule'
    prefix = 'discounts.' + name
    sid = v('P01', 'TermDiscountSchedule' if term else 'DiscountSchedule', prefix + '.id')
    row = next((r for r in c.records['P10'] if same(r.get('Id'), sid)), {})
    schedule = dict(c.state('P10'), **c.mapped('P10', prefix, dict(id='Id', name='Name', type='Type', discountUnit='DiscountUnit',
        isUserDefined='UserDefined', originalScheduleId='OriginalDiscountSchedule', originalScheduleName='SBQQ__OriginalDiscountSchedule__r.Name',
        aggregationScope='AggregationScope', crossProducts='CrossProducts', crossOrders='CrossOrders', includeBundledQuantities='IncludeBundledProducts', overrideBehavior='OverrideBehavior'), row),
        basis=None, basisSource=None, source=None, termDiscountLevel=product['termDiscountLevel'], tiers=[], recordedTierId=v('P01', 'TermDiscountTier' if term else 'DiscountTier'),
        recordedTierMatchesDerived=None, discountPercent=None, discountAmount=None, tierPrice=None, unitsCheck=None)
    schedule['id'] = sid
    if not sid:
        schedule.update(status='none', statusReason='No schedule lookup on line')
        return schedule
    if not row:
        return schedule
    if c.state('P11')['status'] in ('not_readable', 'query_failed'):
        schedule.update(c.state('P11'))
        return schedule
    basis, source = v('P01', 'Quantity', prefix + '.basis'), 'Quantity'
    if term:
        for qid, field in [('P01', 'EffectiveSubscriptionTerm'), ('P01', 'SubscriptionTerm'), ('P03', 'SubscriptionTerm')]:
            basis = v(qid, field, prefix + '.basis')
            if basis is not None:
                source = SPECS[qid]['object'] + '.SBQQ__' + field + '__c'
                break
    schedule.update(basis=basis, basisSource=source, source=schedule_source(c, schedule))
    tiers = [r for r in c.records['P11'] if same(r.get('SBQQ__Schedule__c'), sid)]
    tiers.sort(key=lambda r: (r.get('SBQQ__LowerBound__c') is not None, r.get('SBQQ__LowerBound__c') or 0))
    slab = lower(schedule['type']) == 'slab'
    derived = next((r.get('Id') for r in tiers if basis is not None and
        (r.get('SBQQ__LowerBound__c') or 0) <= basis and (r.get('SBQQ__UpperBound__c') is None or basis < r['SBQQ__UpperBound__c'])), None)
    recorded = schedule['recordedTierId']
    recorded_present = any(same(r.get('Id'), recorded) for r in tiers)
    chosen = recorded if recorded_present else derived
    if recorded and not slab:
        schedule['recordedTierMatchesDerived'] = same(recorded, derived)
    for row in tiers:
        t = c.mapped('P11', prefix + '.tiers', dict(id='Id', name='Name', lowerBound='LowerBound', upperBound='UpperBound',
            discountPercent='Discount', discountAmount='DiscountAmount', price='Price'), row)
        if slab and basis is not None:
            lower_bound = max(pick(t['lowerBound'], 1), 1)
            upper_bound = t['upperBound'] if t['upperBound'] is not None else float('inf')
            units = max(0, min(basis, upper_bound - 1) - (lower_bound - 1))
        else:
            units = basis if basis is not None and same(t['id'], chosen) else 0
        t.update(unitsInTier=units, isMatched=units > 0)
        schedule['tiers'].append(t)
    total_units = sum(t['unitsInTier'] for t in schedule['tiers'])
    schedule['unitsCheck'] = 'ok' if matches(total_units, basis) else 'tiers_do_not_cover_basis'
    schedule['status'] = 'no_tier_matched'
    if total_units > 0:
        unit = lower(schedule['discountUnit'])
        field = 'discountAmount' if unit == 'amount' else 'price' if unit == 'price' else 'discountPercent'
        used = [t for t in schedule['tiers'] if t['isMatched']]
        if used:
            field_name = 'Price' if unit == 'price' else 'DiscountAmount' if unit == 'amount' else 'Discount'
            raw_field = 'SBQQ__' + field_name + '__c'
            unreadable = any(not get_field(row, raw_field)[0] for row in tiers if any(same(row.get('Id'), t['id']) for t in used))
            if unreadable:
                schedule['status'] = 'not_readable'
                return schedule
            if any(t[field] is None for t in used):
                c.warning('TIER_VALUE_NULL', [prefix + '.tiers'])
            value = sum(t['unitsInTier'] * (t[field] or 0) for t in used) / total_units if slab else used[0][field] or 0
            schedule['tierPrice' if unit == 'price' else field] = value
            schedule['status'] = 'price_tier' if unit == 'price' else 'applied'
    return schedule


def calculate_schedules(c, discounts, pm, flags, prices, proration, product):
    schedules = [calculate_schedule(c, term, product) for term in (False, True)]
    discounts['quantitySchedule'], discounts['termSchedule'] = schedules
    expected = prices['prorated']
    for schedule in schedules:
        if schedule['status'] == 'not_readable':
            expected = None
        elif schedule['status'] == 'price_tier':
            expected = multiply(schedule['tierPrice'], proration['multiplier'])
        elif schedule['status'] == 'applied':
            expected = reduce_price(expected, schedule['discountPercent'], schedule['discountAmount'])
    if flags['isBundledOption'] and prices['regular'] == 0:
        expected = None
    causes = []
    if not matches(expected, prices['regular']) or any(s['recordedTierMatchesDerived'] is False for s in schedules):
        for s in schedules:
            for condition, cause in [(s['aggregationScope'] and lower(s['aggregationScope']) != 'none', 'aggregated quantity'),
                (s['crossProducts'], 'crossProducts'), (s['crossOrders'], 'crossOrders'), (s['includeBundledQuantities'], 'includeBundledQuantities'),
                (s['termDiscountLevel'] and lower(s['termDiscountLevel']) != 'line', 'termDiscountLevel'),
                (s['isUserDefined'], 'isUserDefined'), (s['overrideBehavior'], 'overrideBehavior'),
                (lower(pm['type']) == 'block' and lower(s['type']) == 'slab', 'Block method: slab used for overage')]:
                if condition and cause not in causes:
                    causes.append(cause)
    discounts['scheduleReconciliation'] = dict(expectedRegularPrice=expected, matchesRegular=matches(expected, prices['regular']), candidateCauses=causes)
    applied = [name for name, s in zip(('Quantity Discount Schedule', 'Term Discount Schedule'), schedules)
               if s['status'] == 'price_tier' or s['status'] == 'applied' and (nz(s['discountPercent']) or nz(s['discountAmount']))]
    discounts.update(anyApplied=bool(applied), appliedList=applied)
    flags['isDiscounted'] = discounts['anyApplied']
    if flags['isDiscounted'] and 'discount' not in flags['broadQuestionAgents']:
        flags['broadQuestionAgents'].append('discount')
    flags['hasBlockPriceOverage'] |= lower(pm['type']) == 'block' and lower(schedules[0]['type']) == 'slab' and schedules[0]['status'] == 'applied'


def calculate_contracted(c, cp, pm, prices, quote):
    if cp['status'] != 'ok':
        return
    cp['kind'] = 'price' if cp['price'] is not None else 'discount'
    cp['expectedSpecialPrice'] = cp['price'] if cp['kind'] == 'price' else reduce_price(prices['list'], cp['discountPercent'])
    reference = date.fromisoformat(quote['startDate']) if quote['startDate'] else datetime.now(timezone.utc).date()
    cp['isWithinDates'] = (not cp['effectiveDate'] or reference >= date.fromisoformat(cp['effectiveDate'])) and (not cp['expirationDate'] or reference <= date.fromisoformat(cp['expirationDate']))
    cp['appliesToMethod'] = lower(pm['type']) not in ('block', 'percent of total', 'custom', 'cost')
    cp['matchesSpecial'] = matches(cp['expectedSpecialPrice'], prices['special'])


def discount_status(value, allowed, readable=True):
    return 'not_readable' if not readable else 'blocked' if not allowed else 'applied' if nz(value) else 'zero'


def calculate_discounts(c, d, cp, flags, prices, proration):
    v = c.value
    def readable(*fields):
        return all(get_field(c.row('P01'), 'SBQQ__' + f + '__c')[0] for f in fields)
    percent, amount = v('P01', 'OptionDiscount', 'discounts.option.percent'), v('P01', 'OptionDiscountAmount', 'discounts.option.amount')
    option_value = percent if percent is not None else amount
    option_source = 'Product Option' if (percent is not None and percent == v('P06', 'Discount')) or (percent is None and amount is not None and amount == v('P06', 'DiscountAmount')) else 'Quote Line'
    expected = reduce_price(prices['list'], percent, amount)
    d['option'] = dict(status=discount_status(option_value, d['isDiscountable'], readable('OptionDiscount', 'OptionDiscountAmount')),
        statusReason=None, percent=percent, amount=amount, source=option_source, expectedSpecialPrice=expected, matchesSpecial=matches(expected, prices['special']))
    if d['option']['status'] == 'blocked':
        blockers = [label for qid, label in [('P01', 'Quote Line'), ('P04', 'Product')] if v(qid, 'NonDiscountable')]
        d['option']['statusReason'] = '; '.join(label + ' is not discountable (SBQQ__NonDiscountable__c is true)' for label in blockers)
    line_percent, amount = v('P01', 'Discount', 'discounts.additional.percent'), v('P01', 'AdditionalDiscountAmount', 'discounts.additional.amount')
    group, quote = v('P08', 'AdditionalDiscountRate'), v('P03', 'CustomerDiscount')
    source, kind, percent = 'Quote Line', 'percent', line_percent
    if line_percent is not None:
        if group is not None and line_percent == group:
            source = 'Quote Line Group'
        amount = None
    elif amount is not None:
        kind = 'amount'
    else:
        percent, source = (group, 'Quote Line Group') if group is not None else (quote, 'Quote')
    value = percent if kind == 'percent' else amount
    expected = reduce_price(prices['regular'], percent, amount)
    alternative = reduce_price(prices['regular'], amount=multiply(amount, proration['multiplier'])) if kind == 'amount' and proration['multiplier'] is not None else None
    d['additional'] = dict(status=discount_status(value, d['isDiscountable'], readable('Discount', 'AdditionalDiscountAmount')), statusReason=None,
        kind=kind, percent=percent, amount=amount, isSurcharge=value is not None and value < 0, source=source,
        unit='percent' if kind == 'percent' else 'per unit', expectedCustomerPrice=expected, expectedCustomerPriceIfProratedAmount=alternative,
        matchesCustomer=matches(expected, prices['customer']) or matches(alternative, prices['customer']))
    for name, stage, target in [('partner', 'customer', 'partner'), ('distributor', 'partner', 'net')]:
        field = name.title() + 'Discount'
        line_value, quote_value = v('P01', field, 'discounts.' + name + '.percent'), v('P03', field)
        percent = pick(line_value, quote_value)
        expected = reduce_price(prices[stage], percent)
        source = 'Quote' if line_value is None or line_value == quote_value else 'Quote Line'
        d[name] = dict(status=discount_status(percent, d['isPartnerDiscountable'], readable(field)), statusReason=None,
            percent=percent, source=source, isDiscountable=d['isPartnerDiscountable'])
        d[name]['expectedPartnerPrice' if name == 'partner' else 'expectedNetPrice'] = expected
        d[name]['matchesPartner' if name == 'partner' else 'matchesNet'] = matches(expected, prices[target])
    applied = list(d['appliedList'])
    for name, label in [('option', 'Option Discount'), ('additional', 'Additional Discount'), ('partner', 'Partner Discount'), ('distributor', 'Distributor Discount')]:
        if d[name]['status'] == 'applied':
            applied.append(label)
    if cp['kind'] == 'discount' and nz(cp['discountPercent']):
        applied.append('Contracted Price Discount')
    if not (flags['isBundledOption'] and prices['net'] == 0):
        if any(prices[a] is not None and prices[b] is not None and prices[b] < prices[a] and not matches(prices[a], prices[b])
               for a, b in [('prorated', 'regular'), ('regular', 'customer'), ('customer', 'partner'), ('partner', 'net')]):
            applied.append('Waterfall Reduction')
    d.update(anyApplied=bool(applied), appliedList=applied)
    flags['isDiscounted'] = d['anyApplied']
    if d['anyApplied'] and 'discount' not in flags['broadQuestionAgents']:
        flags['broadQuestionAgents'].append('discount')


def calculate_bundle(c, bundle, flags):
    v = c.value
    if flags['isOption'] and v('P01', 'ProductOption') is not None:
        option = dict(c.state('P06'), **c.mapped('P06', 'bundle.option', dict(type='Type', isBundledOnOption='Bundled', required='Required', quantity='Quantity',
            quantityEditable='QuantityEditable', minQuantity='MinQuantity', maxQuantity='MaxQuantity', optionUnitPrice='UnitPrice',
            optionDiscountPercent='Discount', optionDiscountAmount='DiscountAmount', discountedByPackage='DiscountedByPackage', featureName='SBQQ__Feature__r.Name')))
        option.update(productOptionId=v('P01', 'ProductOption'), isBundled=v('P01', 'Bundled'), optional=v('P01', 'Optional'),
                      bundledQuantity=v('P01', 'BundledQuantity'), hasOptionPriceOverride=recorded_price_matches(option['optionUnitPrice'], v('P01', 'ListPrice')))
        bundle['option'] = option
    if flags['isOption']:
        parent = dict(c.state('P07'), **c.mapped('P07', 'bundle.parent', dict(quoteLineId='Id', name='Name', productName='SBQQ__Product__r.Name', productCode='SBQQ__Product__r.ProductCode',
            pricingMethod='PricingMethod', isBundleParent='Bundle', requiredById='RequiredBy', quantity='Quantity', additionalDiscountPercent='Discount',
            additionalDiscountAmount='AdditionalDiscountAmount', discountScheduleId='DiscountSchedule', netPrice='NetPrice', netTotal='NetTotal')))
        parent.update(isSubscription=v('P07', 'SubscriptionPricing') is not None,
                      parentDiscountKind='percent' if parent['additionalDiscountPercent'] is not None else 'amount' if parent['additionalDiscountAmount'] is not None else None,
                      hasContractedPrice=v('P07', 'ContractedPrice') is not None, termMonths=pick(v('P07', 'EffectiveSubscriptionTerm'), v('P07', 'SubscriptionTerm')))
        bundle['parent'] = parent
    for row in c.records['P18']:
        bundle['children'].append(c.mapped('P18', 'bundle.children', dict(quoteLineId='Id', name='Name', productName='SBQQ__Product__r.Name', productCode='SBQQ__Product__r.ProductCode',
            optionType='OptionType', isBundled='Bundled', quantity='Quantity', listPrice='ListPrice', netPrice='NetPrice', netTotal='NetTotal', optionDiscountPercent='OptionDiscount',
            optionDiscountAmount='OptionDiscountAmount', pricingMethod='PricingMethod'), row))
    children = bundle['children']
    bundle['childrenTotals'] = dict(count=len(children), netTotalSum=sum(r['netTotal'] or 0 for r in children), bundledCount=sum(r['isBundled'] is True for r in children))
    if flags['hasBundleContext']:
        flags['broadQuestionAgents'].append('bundle-and-options')


def calculate_mdq(c, mdq, flags):
    dimensions = {valid_id(r.get('Id')): r for r in c.records['P13']}
    def sort_key(row):
        index, number = row.get('SBQQ__SegmentIndex__c'), row.get('SBQQ__Number__c')
        return (index is None, index or 0, number is None, number or 0)
    previous = None
    for row in sorted(c.records['P15'], key=sort_key):
        segment = c.mapped('P15', 'mdq.segments', dict(quoteLineId='Id', segmentIndex='SegmentIndex', segmentLabel='SegmentLabel',
            dimensionId='Dimension', startDate='StartDate', endDate='EndDate', quantity='Quantity', upliftPercent='Uplift', upliftAmount='UpliftAmount',
            prorateMultiplier='ProrateMultiplier', listPrice='ListPrice', specialPrice='SpecialPrice', proratedPrice='ProratedPrice', regularPrice='RegularPrice',
            customerPrice='CustomerPrice', netPrice='NetPrice', additionalDiscountPercent='Discount', additionalDiscountAmount='AdditionalDiscountAmount',
            listTotal='ListTotal', customerTotal='CustomerTotal', netTotal='NetTotal'), row)
        dimension = dimensions.get(valid_id(segment['dimensionId']), {})
        segment.update(isCurrent=same(segment['quoteLineId'], c.value('P01', 'Id')), dimensionName=dimension.get('Name'),
            dimensionType=dimension.get('SBQQ__Type__c'), dimensionUnitPrice=dimension.get('SBQQ__UnitPrice__c'),
            isOneTime=lower(dimension.get('SBQQ__Type__c')) == 'one-time', impliedUpliftPercent=None, upliftMatches=None)
        if not segment['isOneTime']:
            if previous is None:
                segment['upliftMatches'] = not nz(segment['upliftPercent'])
            elif all(nz(x) for x in (segment['regularPrice'], segment['prorateMultiplier'], previous['regularPrice'], previous['prorateMultiplier'])):
                implied = ((segment['regularPrice'] / segment['prorateMultiplier']) / (previous['regularPrice'] / previous['prorateMultiplier']) - 1) * 100
                segment['impliedUpliftPercent'] = implied
                segment['upliftMatches'] = segment['upliftPercent'] is not None and abs(implied - segment['upliftPercent']) <= .01
            previous = segment
        mdq['segments'].append(segment)
    segments = mdq['segments']
    current = next((s for s in segments if s['isCurrent']), None)
    dimension = dimensions.get(valid_id(c.value('P01', 'Dimension')), {})
    mdq['currentDimensionType'] = dimension.get('SBQQ__Type__c')
    if current:
        mdq['currentSegmentIndex'], mdq['currentSegmentLabel'] = current['segmentIndex'], current['segmentLabel']
    time_based = [s for s in segments if not s['isOneTime']]
    one_time = [s for s in segments if s['isOneTime']]
    indices = [s['segmentIndex'] for s in segments if s['segmentIndex'] is not None]
    multipliers = [s['prorateMultiplier'] for s in time_based[:-1] if s['prorateMultiplier'] is not None]
    mdq['summary'] = dict(numSegments=len(segments), numTimeBased=len(time_based), numOneTime=len(one_time),
        dimensionTypes=sorted({s['dimensionType'] for s in segments if s['dimensionType'] is not None}), hasUplift=any(nz(s['upliftPercent']) for s in segments),
        hasOneTimeSegment=bool(one_time), hasDuplicateIndex=len(indices) != len(set(indices)),
        hasPartialSegment=bool(multipliers and time_based[-1]['prorateMultiplier'] is not None and time_based[-1]['prorateMultiplier'] < min(multipliers)),
        totalNetTotal=sum(s['netTotal'] or 0 for s in segments), totalNetTotalTimeBased=sum(s['netTotal'] or 0 for s in time_based), totalNetTotalOneTime=sum(s['netTotal'] or 0 for s in one_time))
    if flags['isMdq']:
        flags['broadQuestionAgents'].append('mdq')


def history_for(c, record_id, path, source):
    h = dict(status=source['status'] if source['status'] != 'ok' else 'node_not_found', nodeId=None,
             lastChangedBy=None, lastChangedAt=None, lastChangeStatus=None, lastSyncedAt=None, entries=[], hasMore=False)
    key = valid_id(record_id)
    hits = metadata_hits(c.directory)
    if source['status'] == 'ok':
        failed = [e for e in element_files(c.directory, 'E02') if not e['ok'] and key in e['args']['queries']]
        if failed:
            h['status'] = 'query_failed'
        elif key in hits:
            h['nodeId'] = hits[key]
            h['status'] = 'query_failed'
            for envelope in element_files(c.directory, 'E03'):
                if h['nodeId'] not in envelope['args']['nodeIds'] or not envelope['ok']:
                    continue
                found = False
                # Supports node batches and flat log entries keyed by their node.
                for item in dictionaries(envelope['result']):
                    if (item.get('nodeId') or item.get('node')) != h['nodeId']:
                        continue
                    if 'items' in item:
                        entries = item['items']
                        h['hasMore'] |= bool(item.get('hasMore'))
                    elif '_id' in item:
                        entries = [item]
                    else:
                        continue
                    found = True
                    for entry in entries:
                        h['entries'].append(dict(changeLogId=entry.get('_id'), status=entry.get('status'), lastModifiedBy=entry.get('lastModifiedBy'),
                            lastModifiedDate=iso(entry.get('lastModifiedDate')), syncedAt=iso(entry.get('createdAt'))))
                if found:
                    h['status'] = 'ok'
                h['hasMore'] |= any(item.get('hasMore') is True for item in dictionaries(envelope['result']))
            h['entries'].sort(key=lambda e: (e['lastModifiedDate'] or '', e['syncedAt'] or ''), reverse=True)
            if h['entries']:
                entry = h['entries'][0]
                h.update(lastChangedBy=entry['lastModifiedBy'], lastChangedAt=entry['lastModifiedDate'], lastChangeStatus=entry['status'], lastSyncedAt=entry['syncedAt'])
    if h['status'] != 'ok':
        c.warning('HISTORY_UNAVAILABLE', [path])
    return h


def marker_passes(log, evaluations):
    """Map global evaluation sequences using the Microscope parser's token order.

    Begin markers clear duplicate-rule suppression for the stage. Initialization
    begin markers start passes, including passes with no rule evaluations.
    Return None when the string cannot corroborate the saved evaluations.
    """
    if not isinstance(log, str) or not log.strip():
        return None
    pass_count, stage, seen, ordered = 0, 'On Initialization', set(), {}
    for token in log.split('!'):
        if not token.strip():
            continue
        parts = token.strip().split(':')
        if len(parts) < 3:
            return None
        if parts[0] == 'MARKER':
            if len(parts) != 3 or parts[2] not in ('-1', '9999'):
                return None
            stage = parts[1]
            if parts[2] == '-1':
                seen.clear()
                if stage == 'On Initialization':
                    pass_count += 1
        else:
            rule_id = valid_id(parts[0])
            if not pass_count or not rule_id:
                return None
            if rule_id not in seen:
                ordered[len(ordered) + 1] = (pass_count, rule_id, stage, parts[2])
                seen.add(rule_id)
    if not pass_count:
        return None
    final = []
    sequences = set()
    for row in evaluations:
        sequence = row.get('Q9_QLM__Sequence__c')
        entry = ordered.get(sequence)
        if sequence in sequences or entry is None:
            return None
        sequences.add(sequence)
        number, rule_id, stage, order = entry
        if (valid_id(row.get('Q9_QLM__Price_Rule__c')) != rule_id
                or row.get('Q9_QLM__Evaluation_Event__c') != stage
                or str(row.get('Q9_QLM__Order__c')) != order):
            return None
        if number == pass_count:
            final.append(row)
    return pass_count, final


def calculate_rules(c, result, flags):
    """Use begin markers, then stage restarts, to select the last calculation.

    Ambiguous boundaries retain all evaluations, a null passCount and a warning.
    """
    if c.empty:
        result['historySource']['status'] = 'query_failed'
        return
    model = reference_model(c.directory)
    source = result['historySource']
    if model:
        source.update(status='ok', refModelId=model['id'], refModelName=model['name'])
    elif any(e['ok'] for e in element_files(c.directory, 'E01')):
        c.warning('HISTORY_UNAVAILABLE', ['priceRules.historySource'])
    for qid in ('P19', 'P20'):
        if c.plan[qid]['state'] in ('failed', 'due'):
            c.warning('HISTORY_UNAVAILABLE', ['priceRules.historySource' if qid == 'P19' else 'priceRules.rules.conditions'])
    for qid in ('E00', 'E01', 'E02', 'E03'):
        for e in element_files(c.directory, qid):
            if not e['ok']:
                c.warning('HISTORY_UNAVAILABLE', ['priceRules.historySource'])
    if any(e['ok'] for e in element_files(c.directory, 'E00')) and not active_team_id(c.directory):
        c.warning('HISTORY_UNAVAILABLE', ['priceRules.historySource'])
    mapping = {(r['target_object'], r['field_api_name']): r['waterfall_stage'] for r in table('field-stage-map') if r['waterfall_stage']}
    labels = {r['label']: r['field_api_name'] for r in table('price-action-field-labels')}
    # These mappings are explicit in the contract; the shipped tables omit them.
    labels.setdefault('Unit Price', 'SBQQ__UnitPrice__c')
    labels.setdefault('Discount (Amt)', 'SBQQ__AdditionalDiscountAmount__c')
    mapping.setdefault(('SBQQ__QuoteLine__c', 'SBQQ__UnitPrice__c'), 'list')
    sort_key = lambda r: (r.get('Q9_QLM__Sequence__c') is None, r.get('Q9_QLM__Sequence__c') or 0, r.get('Id') or '')
    evaluations = sorted(c.records['P16'], key=sort_key)
    stages = {stage: index for index, stage in enumerate(
        ('on initialization', 'before calculate', 'on calculate', 'after calculate'))}
    previous_stage, last_pass_start = None, 0
    result['passCount'] = int(bool(evaluations))
    result['passCountSource'] = 'stage_order'
    for index, row in enumerate(evaluations):
        stage = stages.get(lower(row.get('Q9_QLM__Evaluation_Event__c')))
        if stage is None:
            continue
        if previous_stage is not None and stage < previous_stage:
            result['passCount'] += 1
            last_pass_start = index
        previous_stage = stage
    has_special_type = False
    marked = marker_passes(c.row('P02').get('Q9_QLM__Quote_Line_Log_String__c'), evaluations)
    if marked is not None:
        result['passCount'], evaluations = marked
        result['passCountSource'] = 'markers'
        last_pass_start = 0
    else:
        sequences = [row.get('Q9_QLM__Sequence__c') for row in evaluations]
        known_stages = {lower(row.get('Q9_QLM__Evaluation_Event__c')) for row in evaluations} & stages.keys()
        if evaluations and (len(known_stages) < 2 or None in sequences or len(set(sequences)) != len(sequences)):
            result['passCount'], last_pass_start = None, 0
            c.warning('CALCULATION_PASSES_AMBIGUOUS', ['priceRules.passCount'])
    for row in evaluations[last_pass_start:]:
        rule = c.mapped('P16', 'priceRules.rules', dict(evaluationId='Id', ruleId='Q9_QLM__Price_Rule__c', ruleName='Q9_QLM__Price_Rule__r.Name',
            evaluationEvent='Q9_QLM__Evaluation_Event__c', evaluationOrder='Q9_QLM__Order__c', sequence='Q9_QLM__Sequence__c'), row)
        rule.update(hasActions=False, history=history_for(c, rule['ruleId'], 'priceRules.rules.history', source), conditions=[], actions=[])
        for condition in c.records['P20']:
            if same(condition.get('SBQQ__Rule__c'), rule['ruleId']):
                item = c.mapped('P20', 'priceRules.rules.conditions', dict(conditionId='Id', name='Name', index='Index'), condition)
                item['history'] = history_for(c, item['conditionId'], 'priceRules.rules.conditions.history', source)
                rule['conditions'].append(item)
        rule['conditions'].sort(key=lambda item: (item['index'] is None, item['index'] or 0))
        actions = [a for a in c.records['P17'] if same(a.get('Q9_QLM__Price_Rule_Evaluation__c'), rule['evaluationId'])]
        normalized = []
        for action in sorted(actions, key=sort_key):
            a = c.mapped('P17', 'priceRules.rules.actions', dict(actionEvaluationId='Id', priceActionId='Q9_QLM__Price_Action__c', sequence='Q9_QLM__Sequence__c',
                order='Q9_QLM__Order__c', targetObject='Q9_QLM__Target_Object__c', targetField='Q9_QLM__Target_Field__c', valueAfterRule='Q9_QLM__Value__c'), action)
            target = a['targetField']
            api = target if target and (target.endswith('__c') or target in ('Id', 'Name', 'CreatedDate', 'LastModifiedDate', 'CurrencyIsoCode', 'OwnerId', 'RecordTypeId')) else labels.get(target)
            stage = mapping.get(('SBQQ__QuoteLine__c', api)) if a['targetObject'] == 'Quote Line' else None
            a.update(targetFieldApiName=api or target, impact='direct' if stage else 'indirect', waterfallStage=stage, checks=[],
                history=history_for(c, a['priceActionId'], 'priceRules.rules.actions.history', source))
            if a['valueAfterRule'] is not None:
                a['valueAfterRule'] = str(a['valueAfterRule'])
            if api is None:
                c.warning('ACTION_FIELD_UNMAPPED', ['priceRules.rules.actions.targetFieldApiName'])
            normalized.append(a)
        rule_sets_type = any(a['targetObject'] == 'Quote Line' and a['targetFieldApiName'] == 'SBQQ__SpecialPriceType__c' for a in normalized)
        for a in normalized:
            api = a['targetFieldApiName']
            if a['targetObject'] == 'Quote Line':
                if api == 'SBQQ__SpecialPrice__c' and not has_special_type and not rule_sets_type and lower(c.value('P01', 'SpecialPriceType')) != 'custom':
                    a['checks'].append('SPECIAL_PRICE_WITHOUT_TYPE')
                if api in {f'SBQQ__{s}Price__c' for s in ('Regular', 'Customer', 'Partner', 'Net')} and lower(rule['evaluationEvent']) != 'after calculate':
                    a['checks'].append('PRORATED_FIELD_WRITE')
                if lower(rule['evaluationEvent']) == 'after calculate' and a['waterfallStage']:
                    a['checks'].append('AFTER_CALC_UNIT_PRICE_WRITE')
            result['directActionCount' if a['impact'] == 'direct' else 'indirectActionCount'] += 1
            field_list = 'quoteLineFieldsUpdated' if a['targetObject'] == 'Quote Line' else 'quoteFieldsUpdated' if a['targetObject'] == 'Quote' else None
            if field_list and api:
                result[field_list].append(api)
        has_special_type |= rule_sets_type
        rule['actions'] = normalized
        rule['hasActions'] = bool(normalized)
        if not normalized:
            result['rulesWithoutActions'].append(rule['ruleName'])
        result['rules'].append(rule)
    for key in ('quoteLineFieldsUpdated', 'quoteFieldsUpdated'):
        result[key] = sorted(set(result[key]))
    if result['rules']:
        result['status'] = 'rules_fired'
    if c.state('P17')['status'] in ('not_readable', 'query_failed'):
        result.update(c.state('P17'))
    flags['hasPriceRulesApplied'] = result['status'] == 'rules_fired' and any(r['hasActions'] for r in result['rules'])
