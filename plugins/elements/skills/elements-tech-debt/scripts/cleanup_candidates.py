#!/usr/bin/env python3
"""Usage: cleanup_candidates.py VIEWS_DIRECTORY OUTPUT_JSON

Exit 0: validated; read coverage and candidates. Exit 1: evidence gap; fix the
reported view or field and rerun. Exit 2: usage; correct arguments and rerun.
Missing sf.type: request list_metadata_by_criteria for the named view with its
viewSpec.columns plus "type" in columns, then rerun fetch_parts.py and this script.
JSON means JavaScript Object Notation.
"""
import argparse
import json
from pathlib import Path
import re
import sys


# Ordering is the investigation policy: inactive automation, rules, then assessment views.
VIEWS = (
    'automation_review_inactive', 'rules_review_inactive', 'reports_review_stale',
    'dashboards_review_stale', 'fields_assess_unused', 'record_types_assess_low_adoption',
    'objects_assess_low_adoption', 'profiles_assess_unassigned',
    'permission_sets_assess_unassigned', 'permission_set_groups_assess_unassigned',
)
# Local hold policy for recognized profile labels, independent of server classification.
PROFILE_HOLDS = frozenset({
    'System Administrator', 'Standard User', 'Minimum Access - Salesforce',
    'Marketing User', 'Chatter Free User', 'Solution Manager', 'Identity User',
})
# Column paths preserve the custom-view projection; lifted keys take precedence.
COLUMN_PATHS = {
    'api_name': 'sf.apiName', 'type': 'sf.type', 'manage_package': 'nodeDetails.isManaged',
    'active': 'nodeDetails.active', 'subtype': 'nodeDetails.subtype', 'full_path': 'sf.fullPath',
    'assigned_users': 'assignedUsers', 'last_modified_date': 'lastModifiedDate',
    'last_modified_by': 'lastModifiedBy', 'last_used': 'lastUsed',
    'last_created_record_date': 'lastCreatedRecordDate', 'last_modified_record_date': 'lastModifiedRecordDate',
    'last_refreshed_date': 'nodeDetails.dashboardRefreshedDate',
}


class ActionParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(message + '; correct arguments using --help and rerun')


def screen(row):
    kind = at_path(row, 'sf.type')
    if kind == 'Profile' and row['name'] in PROFILE_HOLDS:
        return True, []
    if kind == 'Permission Set Group' and at_path(row, 'sf.apiName').startswith('force__'):
        return True, []
    return False, ['confirm_custom_profile'] if kind == 'Profile' else []


def at_path(row, path):
    value = row
    for segment in path.split('.'):
        value = value.get(segment) if isinstance(value, dict) else None
    return value


def project(root):
    coverage, candidates, gaps = {}, {}, []
    for view in VIEWS:
        directory = root / view
        try:
            if (directory / 'unavailable.json').exists():
                raise ValueError('Unavailable: ' + (directory / 'unavailable.json').read_text())
            reply = json.loads((directory / 'reply.json').read_text())
            state = json.loads((directory / 'state.json').read_text())
            rows = [json.loads(line) for line in (directory / 'rows.ndjson').read_text().split('\n') if line.strip()]
            if (not state['complete'] or reply['status'] != 'complete' or reply.get('failed') or
                    reply.get('failedTotal') or reply.get('failedFileRows') or reply.get('fileError') or
                    len(rows) != reply['totalRows'] or len(rows) != reply['totalItems']):
                raise ValueError('Incomplete acquisition or row totals; finish fetch_parts.py and rerun')
        except (OSError, ValueError, KeyError, TypeError) as error:
            coverage[view] = {'status': 'incomplete', 'all': None}
            gaps.append('%s: %s' % (view, error))
            continue
        counts = dict(status='complete', all=len(rows), managed=0, unmanaged=0, excluded_standard=0)
        for row in rows:
            required = ('nodeId', 'name', 'sf.type', 'sf.apiName')
            missing = [path for path in required if not isinstance(at_path(row, path), str) or not at_path(row, path)]
            if (missing or not re.fullmatch(r'[0-9a-fA-F]{24}', row['nodeId']) or
                    type(at_path(row, 'nodeDetails.isManaged')) is not bool):
                counts['status'] = 'incomplete'
                recovery = ('request list_metadata_by_criteria for this view with its viewSpec.columns plus '
                            '"type" in columns, then rerun fetch_parts.py and cleanup_candidates.py'
                            if 'sf.type' in missing else 'recover fields and rerun')
                gaps.append('%s: missing or invalid identity/managed fields %s; %s' % (view, missing, recovery))
                continue
            if row['nodeDetails']['isManaged']:
                counts['managed'] += 1
                continue
            counts['unmanaged'] += 1
            excluded, flags = screen(row)
            if excluded:
                counts['excluded_standard'] += 1
                continue
            display = {}
            for column in reply['viewSpec']['columns']:
                key = column if isinstance(column, str) else column['value']
                path = COLUMN_PATHS.get(key, key) if isinstance(column, str) else column.get('path', key)
                display[key] = row.get(key, at_path(row, path))
            if row['nodeId'] in candidates:
                candidates[row['nodeId']]['views'].append(view)
                candidates[row['nodeId']]['display'].update(display)
            else:
                candidates[row['nodeId']] = {key: row.get(key) for key in
                                            ('nodeId', 'name', 'sf', 'nodeDetails', 'lastModifiedDate')} | {
                                                'views': [view], 'display': display, 'flags': flags}
        coverage[view] = counts
    return {'coverage': coverage, 'candidates': list(candidates.values()), 'gaps': gaps}


def main():
    parser = ActionParser(description=__doc__)
    parser.add_argument('views', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        result = project(args.views)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Evidence gap: %s. Fix the affected view or field and rerun.' % error, file=sys.stderr)
        return 1
    print(json.dumps(result['coverage'], indent=2))
    if result['gaps']:
        print('Evidence gaps: %s. Fix the affected views and rerun.' % '; '.join(result['gaps']), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
