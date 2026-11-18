"""Reconcile the frozen LTN input audit against reviewed source contracts."""
import json
import re
from collections import Counter
from pathlib import Path

from verification.inventory import ROOT, link_option_evidence, link_option_sources
from verification.simulation_audit_contracts import reviewed_fields


HERE = Path(__file__).resolve().parent
CATEGORY = 'task_generation.categories.*.'
SCOPED = (CATEGORY + 'department_groups[].payload.', CATEGORY + 'departments.*.')
STAFF = 'task_generation.staff_config.'
WEEKDAY = re.compile(r'(\.staff_working_hours\.)(mon|tue|wed|thu|fri|sat|sun)(?=\.|$)')
DEPARTMENT_MAP = re.compile(
    r'^(departments\[\]\.task_generation_location(?:s|_suffixes)\.)([^.]+)')
OLD_SHIFT_PATH = re.compile(r'^task_generation\.staff_config\.\*\.(none|four_on_four_off_12h)(?=\.|$)')
NESTED_LISTS = {'route_profiles.*.allowed_edges', 'tasks[].allowed_edges',
                'scenario_testing.stress_test.assets'}


def normalize_path(path):
    if path == STAFF + '*':
        return STAFF + 'shift_patterns'
    path = DEPARTMENT_MAP.sub(r'\g<1>*', path)
    path = WEEKDAY.sub(r'\g<1>*', path)
    return OLD_SHIFT_PATH.sub(STAFF + 'shift_patterns.*', path)


def resolve_path(path, contracts):
    normalized = normalize_path(path)
    if normalized in contracts:
        row = dict(contracts[normalized])
    elif normalized.endswith('[]'):
        parent = normalized.removesuffix('[]')
        base = parent.removesuffix('[]')
        if parent.endswith('[]') and base not in NESTED_LISTS:
            return None
        owner = resolve_path(parent, contracts)
        if not owner:
            return None
        row = dict(owner, classification='structural', units='list element',
                   runtime_default='Defined by the containing field',
                   meaning=f'An entry in the containing list. {owner["meaning"]}')
        normalized = owner['contract_path']
    elif any(normalized.startswith(prefix) for prefix in SCOPED):
        prefix = next(prefix for prefix in SCOPED if normalized.startswith(prefix))
        inherited = resolve_path(CATEGORY + normalized.removeprefix(prefix), contracts)
        if not inherited:
            return None
        row = dict(inherited)
        row['source_symbols'] = list(dict.fromkeys([
            *row.get('source_symbols', []), 'amr_sim_task_generation.py:DynamicCategoryTaskGenerator._merge_category_with_override',
        ]))
        if normalized.endswith('.dropoff_zone_capacity_policy'):
            row.update(classification='compatibility',
                       meaning='Retained override value is ignored. Runtime restores the category-wide policy.',
                       precedence='The category-wide value wins, with allow_temporary_overflow as its fallback.')
            row.pop('support_status', None)
        else:
            row['precedence'] = ('An explicit value at this scope overlays the category default during instance '
                                 f'construction. {row.get("precedence", "")}')
        normalized = inherited['contract_path']
    else:
        return None
    return dict(row, path=path, contract_path=normalized)


def build_simulation_audit(cases=(), *, root=ROOT):
    scope = json.loads((HERE / 'simulation_audit_scope.json').read_text(encoding='utf-8'))
    existing = json.loads((root / 'verification/field_contracts.json').read_text(encoding='utf-8'))
    contracts = {
        path: dict({'tests': [], 'meaning': 'See the existing field contract.'}, **row,
                   classification='existing_contract',
                   modes=row.get('modes', 'See the existing field contract and linked workflow evidence.'))
        for path, row in existing.items()
    }
    reviewed = reviewed_fields()
    # Keep support status and limitations established by earlier reviews.
    for path, row in reviewed.items():
        contracts[path] = {**contracts.get(path, {}), **row}

    rows = []
    unresolved = []
    for path, fixtures in sorted(scope['paths'].items()):
        row = resolve_path(path, contracts)
        if row:
            rows.append(dict(row, observed_in=fixtures, scope='historical_fixture_path'))
        else:
            unresolved.append(path)
    rows.extend(dict(row, path=path, contract_path=path, observed_in=[], scope='field_contract')
                for path, row in sorted(contracts.items()))
    outcomes = [{'id': case['id'], 'status': case['status']} for case in cases]
    rows = link_option_sources(link_option_evidence(rows, outcomes), root=root)
    broken_links = set()
    for row in rows:
        broken_links.update(f'{row["path"]}: unresolved source {source["reference"]}'
                            for source in row['source_evidence'] if not source['resolved'])
        if cases:
            broken_links.update(f'{row["path"]}: unmatched test {pattern}'
                                for pattern in row['unmatched_test_patterns'])

    historical = [row for row in rows if row['scope'] == 'historical_fixture_path']
    return {
        'origin': scope['origin'],
        'rollback_commit': scope['baseline_commit'],
        'fixtures': scope['fixtures'],
        'counts': {
            'historical_paths': len(scope['paths']),
            'classified_historical_paths': len(historical),
            'historical_dispositions': dict(sorted(Counter(row['classification'] for row in historical).items())),
            'existing_contracts': len(existing),
            'supplemental_contracts': len(reviewed.keys() - existing.keys()),
            'historical_rows_with_passing_linked_tests': sum(row['evidence_passed'] for row in historical),
        },
        'unclassified': unresolved,
        'broken_links': sorted(broken_links),
        'rows': rows,
    }
