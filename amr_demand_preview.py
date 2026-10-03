"""Bounded planning preview using the simulator's own resolved generation rules.

No dispatch, completion, inventory consumption or return events are simulated.
Counts describe planned task records, never completed transport or AMR journeys.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

from amr_sim_task_generation import DynamicCategoryTaskGenerator, _scheduled_times_from_cfg, _instance_requires_staff
from amr_sim_time_utils import parse_release_time
from visualiser.project_checks import check_project, config_fingerprint

MAX_DAYS = 31
MAX_ROWS = 20000
MAX_POLL_EVALUATIONS = 100000
PRECEDENCE = [
    'Global task generation enabled gates all automatic generators.',
    'Category defaults are overlaid by a group payload or an individual department override.',
    'Membership in a group suppresses that department’s individual override, including disabled groups.',
    'Category-only service is suppressed when valid groups or department overrides exist.',
    'The category-wide drop-off zone capacity policy overrides ordinary department/group values.',
    'Waste stream defaults then department stream values override waste settings; derived thresholds are calculated afterward.',
    'Department category locations replace the selected pickup or dropoff side. A department drop-off zone replaces AMR dropoff and enables staff handoff and return.',
    'Global staff shift settings and operating hours affect timeframe releases; effective task fields are shown alongside resolved rule settings.',
]


def _guard_sizes(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'timeframe_payload_multiple', 'payload_multiple', 'quantity'} and float(child or 0) > MAX_ROWS:
                raise ValueError(f'{key} exceeds the preview limit of {MAX_ROWS}. Reduce the preview scenario.')
            _guard_sizes(child)
    elif isinstance(value, list):
        if len(value) > MAX_ROWS:
            raise ValueError('Input list exceeds the preview size limit.')
        for child in value:
            _guard_sizes(child)


def _id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _independent_schedule_count(instance, start, end):
    """Independent arithmetic for the deliberately bounded reference contract.

    More complex calendars/rotating destinations have no asserted expected count.
    This calculation does not emit tasks or call generator scheduling methods.
    """
    cfg, dept = instance['cfg'], instance.get('department', {})
    mode = cfg.get('generation_mode', 'scheduled')
    pickups, dropoffs = instance.get('pickup_locations', []), instance.get('dropoff_locations', [])
    if len(pickups) != 1 or len(dropoffs) != 1 or pickups[0] == dropoffs[0]:
        return None
    if dept and (dept.get('days_active') or dept.get('operating_start_time', '00:00') != '00:00'
                 or dept.get('operating_end_time', '24:00') != '24:00' or float(dept.get('hours_operated_per_day', 24)) != 24):
        return None
    sporadic_count = 0
    if mode in {'sporadic', 'scheduled_sporadic'}:
        if cfg.get('days_active') or cfg.get('run_every_fortnight'):
            return None
        accrued = (Decimal(str(cfg.get('frequency_per_day', 0))) *
                   Decimal(str((end - start).total_seconds())) / Decimal(86400))
        nearest = accrued.to_integral_value()
        sporadic_count = int(nearest if abs(accrued - nearest) <= Decimal('1e-10') else accrued)
        if dept and not dept.get('enabled', True):
            sporadic_count = 0
        if mode == 'sporadic':
            return sporadic_count
    if mode in {'scheduled', 'scheduled_sporadic'}:
        times = cfg.get('scheduled_times', cfg.get('schedule_times', []))
        if not isinstance(times, list):
            return None
        times = sorted(set(times))
        multiple = 1
    elif mode == 'timeframe' and not _instance_requires_staff(instance):
        if cfg.get('timeframe_end', '') <= cfg.get('timeframe_start', ''):
            return None
        times = [cfg.get('timeframe_start', '')]
        multiple = max(1, int(cfg.get('timeframe_payload_multiple', cfg.get('payload_multiple', 1))))
    else:
        return None
    if dept and not dept.get('enabled', True):
        return 0
    count = 0
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    while day <= end:
        for clock in times:
            try:
                hour, minute = map(int, clock.split(':'))
            except (ValueError, AttributeError):
                return None
            release = day + timedelta(hours=hour, minutes=minute)
            if not start <= release <= end:
                continue
            if cfg.get('days_active') and weekdays[release.weekday()] not in cfg['days_active']:
                continue
            if cfg.get('run_every_fortnight') and ((release.date() - start.date()).days // 7) % 2:
                continue
            if mode == 'timeframe':
                h, m = map(int, cfg['timeframe_end'].split(':'))
                if release >= day + timedelta(hours=h, minutes=m):
                    continue
            count += multiple
        day += timedelta(days=1)
    return count + sporadic_count


def _sporadic_plan(generator, instance, duration, interval):
    """Use the runtime's polling cadence without dispatching or completing tasks."""
    cfg = instance['cfg']
    mode = cfg.get('generation_mode')
    schedules = (generator._schedule_calendar(instance, duration)['entries']
                 if mode == 'scheduled_sporadic' else [])
    pairs = len(instance['pickup_locations']) * len(instance['dropoff_locations'])
    bound = (float(cfg.get('frequency_per_day', 0)) * duration / 86400 + len(schedules) + 1) * pairs
    if bound > MAX_ROWS:
        raise ValueError(f"Rule {instance['key']} exceeds the preview limit; shorten the period or reduce demand.")
    polls, now = {0.0}, 0.0
    while now < duration:
        now = min(now + interval, duration)
        polls.add(now)
    records = []
    for now in sorted(polls | {entry[0] for entry in schedules if 0 <= entry[0] <= duration}):
        records.extend(generator._schedule_records(instance, now))
        if now in polls:
            records.extend(generator._volume_records(instance, now))
    runtime = generator._runtime_for_volume_key(instance)
    key = instance['key']
    return records, {
        'accrued_events': runtime.get('sporadic_accrued_events', {}).get(key, 0),
        'emitted_events': runtime.get('sporadic_emitted_events', {}).get(key, 0),
        'retained_events': runtime.get('sporadic_accumulator', {}).get(key, 0),
        'poll_interval_seconds': interval,
        'basis': 'Deterministic occurrences per 24 eligible hours; each emitted occurrence uses the resolved route pairs. Fractions and whole events waiting for an open/valid poll are retained. These are generator decisions, not independent expected counts.'}


def build_demand_preview(config, *, end_datetime=None):
    """Return a JSON-serialisable snapshot. End is inclusive, matching generation.

    Scheduled/timeframe components use daily sweeps; sporadic modes use the
    configured generation polls. Release times precede runtime staggering,
    dispatch and completion.
    Runtime-dependent components have unknown totals, not zero totals.
    """
    frozen = copy.deepcopy(config)
    checks = check_project(frozen)
    errors = [f for f in checks.findings if f.severity == 'error']
    if errors:
        raise ValueError('Correct Project checks errors first: ' + '; '.join(f.message for f in errors[:4]))
    _guard_sizes(frozen)
    start = datetime.fromisoformat(frozen['simulation']['start_datetime'])
    end = datetime.fromisoformat(end_datetime or frozen['simulation'].get('end_datetime') or (start + timedelta(days=1)).isoformat())
    duration = (end - start).total_seconds()
    if not 0 < duration <= MAX_DAYS * 86400:
        raise ValueError(f'Preview must cover more than zero and at most {MAX_DAYS} days from simulation start.')

    # Use the actual input adapters and generator setup. Construction does not run
    # the simulation. Route precomputation is unnecessary for demand inspection.
    from simulator import Simulation
    runtime_input = copy.deepcopy(frozen)
    runtime_input['simulation']['precompute_static_routes'] = False
    runtime_input.setdefault('lifts', [])
    simulation = Simulation(runtime_input)
    rules, tasks = [], []
    poll_evaluations = 0

    def row(task, rule, reason, *, deferred=False, static=False):
        release = float(task['release_time'])
        if release < 0 or release > duration:
            return
        task = copy.deepcopy(task)
        tasks.append({
            'preview_id': _id([checks.config_hash, rule['id'], task]),
            'task_id': task.get('id', ''), 'rule_id': rule['id'], 'rule_path': rule['path'],
            'release_seconds': release, 'release_datetime': (start + timedelta(seconds=release)).isoformat(),
            'department': task.get('department_id', rule.get('department', '')),
            'category': rule['category'], 'payload': task.get('payload', ''),
            'pickup': task.get('pickup', ''), 'dropoff': task.get('dropoff_zone') or task.get('dropoff', ''),
            'route_profile': task.get('route_profile') or ('dirty' if 'dirty' in task.get('labels', []) else ''),
            'quantity': task.get('quantity', 1),
            'timing': 'Conditional: awaits preceding return pickup' if deferred else 'Configured' if static else 'Planned release',
            'explanation': reason, 'effective_task': task,
        })
        if len(tasks) > MAX_ROWS:
            raise ValueError(f'Preview exceeds {MAX_ROWS} task records; shorten the period.')

    for index, source in enumerate(frozen.get('tasks', [])):
        rule = {'id': f'static:{index}', 'path': f'/tasks/{index}', 'category': 'Explicit tasks',
                'department': source.get('department_id', ''), 'status': 'planned',
                'explanation': 'Explicit task entry. Quantity is shown separately from record count.',
                'unknown_additional_demand': bool(source.get('return_enabled') or source.get('dropoff_zone')),
                'effective_config': source, 'field_sources': {k: f'/tasks/{index}' for k in source}}
        rules.append(rule)
        task = {**source, 'release_time': parse_release_time(source, start)}
        row(task, rule, rule['explanation'], static=True)

    active_paths = set()
    for generator in simulation.task_generation_manager.generators:
        if not isinstance(generator, DynamicCategoryTaskGenerator):
            rules.append({'id': generator.generator_type, 'path': '/departments', 'category': 'Legacy waste',
                          'department': '', 'status': 'runtime-dependent',
                          'explanation': 'Waste accumulation and collection depend on runtime state; no fixed total is claimed.',
                          'effective_config': {}, 'field_sources': {}})
            continue
        for instance in generator.instances:
            cfg = {k: copy.deepcopy(v) for k, v in instance['cfg'].items() if k not in {'department_groups', 'departments'}}
            mode = cfg.get('generation_mode', 'scheduled')
            path = instance.get('rule_path', '')
            active_paths.add(path)
            runtime_dependent = mode not in {'scheduled', 'timeframe', 'sporadic', 'scheduled_sporadic'} or bool(cfg.get('tracked_item_exchange'))
            rule = {'id': instance['key'], 'path': path, 'category': instance['category_key'],
                    'department': instance.get('department_id', ''), 'status': 'runtime-dependent' if runtime_dependent else 'planned',
                    'explanation': '', 'effective_config': cfg, 'field_sources': instance.get('field_sources', {}),
                    'field_provenance': copy.deepcopy(instance.get('field_provenance', {})),
                    'effective_pickups': instance.get('pickup_locations', []),
                    'effective_dropoffs': instance.get('dropoff_locations', []),
                    'final_destinations': instance.get('final_destination_locations', []),
                    'location_precedence': 'Department assignments replace the selected side when present; department zones take priority for AMR dropoff.',
                    'returns': 'Return tasks depend on outbound progress and are not counted in this preview.' if cfg.get('return_enabled') else 'No configured return.',
                    'unknown_additional_demand': runtime_dependent or bool(cfg.get('return_enabled') or instance.get('dropoff_zone_locations'))}
            rule['expected_fixed_records'] = _independent_schedule_count(instance, start, end)
            rule['reconciliation_basis'] = ('Independent schedule/rate arithmetic for one distinct route pair and unrestricted department hours; sporadic rate arithmetic additionally requires unrestricted category dates.'
                                           if rule['expected_fixed_records'] is not None else
                                           'No independent count claimed for this mode/calendar; inspect resolved settings and the reference tests.')
            rules.append(rule)
            valid_pickups = [x for x in rule['effective_pickups'] if x in simulation.locations]
            valid_dropoffs = [x for x in rule['effective_dropoffs'] if x in simulation.locations]
            if cfg.get('payload') not in simulation.payloads:
                rule.update(status='no-work', unknown_additional_demand=False, explanation='Effective payload does not exist.')
                continue
            if not any(a != b for a in valid_pickups for b in valid_dropoffs):
                rule.update(status='no-work', unknown_additional_demand=False, explanation='No valid distinct pickup/dropoff pair after department location resolution.')
                continue
            if mode in {'sporadic', 'scheduled_sporadic'}:
                interval = max(60.0, simulation.task_generation_interval_sec)
                poll_evaluations += int(duration / interval) + 2
                if poll_evaluations > MAX_POLL_EVALUATIONS:
                    raise ValueError('Sporadic polling exceeds the preview limit; shorten the period or increase the update interval.')
                records, accounting = _sporadic_plan(generator, instance, duration, interval)
                for record in records:
                    row(vars(record.task), rule, record.details, deferred=record.deferred)
                rule['sporadic_accounting'] = accounting
                rule['explanation'] = (f"Deterministic sporadic demand: {accounting['accrued_events']:g} events accrued, "
                    f"{accounting['emitted_events']} emitted and {accounting['retained_events']:g} retained. "
                    'There is no random arrival sampling. Planned releases follow generation polls, including the final partial interval. '
                    + ('Clock-scheduled records are also shown. ' if mode == 'scheduled_sporadic' else '')
                    + ('Additional tracked-stock demand remains runtime-dependent. ' if runtime_dependent else '')
                    + 'Dispatch, physical availability and returns are not simulated.')
                if not records and not runtime_dependent:
                    rule['status'] = 'no-work'
                continue
            # Threshold collections and tracked-item replenishment stay unknown.
            fixed = mode in {'scheduled', 'timeframe'}
            if not fixed:
                rule['explanation'] = ('Continuous mode accumulates volume but does not trigger volume collections by itself. '
                                       'Tracked-item exchange, when enabled, uses separate consumption rules. '
                                       'Use threshold or hybrid mode for volume-triggered collections.' if mode == 'continuous' else
                                       f'{mode}: demand depends on accumulation, inventory or runtime events. Total is unknown before simulation.')
                continue
            times = _scheduled_times_from_cfg(cfg) if mode != 'timeframe' else []
            if mode != 'timeframe' and not times:
                rule['explanation'] = 'No scheduled times. Other runtime-dependent components may still generate work.' if runtime_dependent else 'No scheduled times are configured.'
                if not runtime_dependent:
                    rule['status'] = 'no-work'
                continue
            multiplier = max(1, int(cfg.get('timeframe_payload_multiple', cfg.get('payload_multiple', 1)))) if mode == 'timeframe' else len(times)
            upper_bound = (int(duration / 86400) + 2) * multiplier * len(valid_pickups) * len(valid_dropoffs)
            if upper_bound > MAX_ROWS:
                raise ValueError(f"Rule {instance['key']} exceeds the preview limit; shorten the period or reduce demand.")
            before = len(tasks)
            no_work_reasons = set()
            day = start.replace(hour=0, minute=0, second=0, microsecond=0)
            while day <= end:
                sweep = min(end, day + timedelta(days=1) - timedelta(microseconds=1))
                now = (sweep - start).total_seconds()
                records = (generator._timeframe_records(instance, now, diagnostics=no_work_reasons) if mode == 'timeframe'
                           else generator._schedule_records(instance, now))
                for record in records:
                    row(vars(record.task), rule, record.details, deferred=record.deferred)
                day += timedelta(days=1)
            rule['explanation'] = ('Fixed schedule component shown; additional runtime demand remains unknown.' if runtime_dependent
                                   else 'Planned releases from the resolved schedule/timeframe, active days and department hours.')
            if mode == 'timeframe':
                slots = []
                day = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                nominal_days = []
                while day <= end:
                    nominal_days.append(day)
                    day += timedelta(days=1)
                # A final read-only pass uses the full preview horizon. Earlier
                # daily sweeps can temporarily see future slots as out of range.
                generator._timeframe_records(instance, duration, wake_times=set(),
                                             base_days=nominal_days, slot_audit=slots)
                dispositions = Counter(slot['disposition'] for slot in slots)
                eligible = dispositions.pop('eligible', 0)
                rule['timeframe_slots'] = slots
                rule['timeframe_slot_accounting'] = {
                    'candidate_records': len(slots), 'eligible_records': eligible,
                    'excluded_records': sum(dispositions.values()),
                    'exclusions': dict(sorted(dispositions.items())),
                    'emitted_records': len(tasks) - before,
                    'count_difference': len(tasks) - before - eligible,
                    'basis': 'Generator slot decisions for nominal timeframes intersecting the preview; not an independent expectation or staffing-capacity check.'}
                if dispositions:
                    rule['explanation'] += (f' {sum(dispositions.values())} of {len(slots)} candidate timeframe '
                                            'slots were excluded; see calendar slot accounting for the reasons.')
            if len(tasks) == before and not runtime_dependent:
                rule.update(status='no-work', no_work_reasons=sorted(no_work_reasons),
                            explanation=(' '.join(sorted(no_work_reasons)) if no_work_reasons else
                                         'No release matched this period, active days, department opening hours and timeframe deadline.'))

    # Inventory stored rules that never became instances, including suppressed
    # defaults and overrides. These must not disappear from an empty preview.
    generation = frozen.get('task_generation', {})
    globally_enabled = generation.get('enabled', True)
    known_departments = {str(d.get('id') or d.get('name', '')) for d in frozen.get('departments', [])}
    for category, cfg in generation.get('categories', {}).items():
        base = '/task_generation/categories/' + category.replace('~', '~0').replace('/', '~1')
        candidates = [(base, cfg, '', 'Category defaults are disabled or suppressed by department/group rules.')]
        covered = set()
        for i, group in enumerate(cfg.get('department_groups', [])):
            departments = group.get('departments', [])
            if isinstance(group.get('payload'), dict) and departments:
                covered.update(departments)
            reason = ('No known departments are assigned to the group.' if not any(d in known_departments for d in departments)
                      else 'Group is disabled or has no valid resolved waste stream.')
            candidates.append((f'{base}/department_groups/{i}/payload', group.get('payload', {}), ', '.join(departments), reason))
            for missing in (d for d in departments if d not in known_departments):
                rules.append({'id': f'inactive:{base}:group:{i}:missing:{missing}',
                              'path': f'{base}/department_groups/{i}/departments', 'category': category,
                              'department': missing, 'status': 'no-work', 'explanation': 'Assigned department does not exist.',
                              'effective_config': {}, 'field_sources': {}})
        for department, override in cfg.get('departments', {}).items():
            reason = ('Suppressed by group membership.' if department in covered else
                      'Department does not exist.' if department not in known_departments else
                      'Department override is disabled or has no valid resolved waste stream.')
            candidates.append((base + '/departments/' + department.replace('~', '~0').replace('/', '~1'), override, department, reason))
        for path, settings, department, reason in candidates:
            if path not in active_paths:
                rules.append({'id': 'inactive:' + path, 'path': path, 'category': category, 'department': department,
                              'status': 'no-work', 'explanation': reason if globally_enabled else 'Global task generation is disabled.',
                              'effective_config': settings, 'field_sources': {}})

    tasks.sort(key=lambda t: (t['release_seconds'], t['rule_id'], t['preview_id']))
    counts = Counter(t['rule_id'] for t in tasks)
    out_of_hours = Counter(t['rule_id'] for t in tasks if t['effective_task'].get('staff_out_of_hours_required'))
    for rule in rules:
        rule['planned_records'] = counts[rule['id']]
        rule['out_of_hours_records'] = out_of_hours[rule['id']]
        if rule['out_of_hours_records']:
            rule['explanation'] += (f" {rule['out_of_hours_records']} planned releases have no overlapping "
                                    'staff/department working window. Runtime staff hours still apply; '
                                    'handling may miss the timeframe deadline.')
        rule['total_demand'] = None if rule.get('unknown_additional_demand') or rule['status'] == 'runtime-dependent' else counts[rule['id']]
        if rule['id'].startswith('static:') and not rule['planned_records']:
            rule.update(status='no-work', explanation='Explicit release falls outside the preview period.')
        expected = rule.get('expected_fixed_records')
        rule['count_difference'] = None if expected is None else rule['planned_records'] - expected
    return {'schema_version': 1, 'config_sha256': config_fingerprint(frozen), 'frozen_inputs': frozen,
            'start_datetime': start.isoformat(), 'end_datetime': end.isoformat(),
            'period_convention': 'Inclusive start and end; planned releases, not dispatch or completion.',
            'provenance_schema_version': 1,
            'precedence': PRECEDENCE, 'tasks': tasks, 'rules': rules,
            'totals': {'planned_task_records': len(tasks),
                       'out_of_hours_records': sum(out_of_hours.values()),
                       'configured_quantity_units': sum(float(t['quantity']) for t in tasks),
                       'conditional_release_records': sum(t['timing'].startswith('Conditional') for t in tasks),
                       'runtime_dependent_rules': sum(r['total_demand'] is None for r in rules),
                       'independently_reconciled_rules': sum(r['count_difference'] == 0 for r in rules),
                       'count_mismatches': sum(r['count_difference'] not in (None, 0) for r in rules),
                       'reconciled_rule_records': sum(r['planned_records'] for r in rules)},
            'limitations': ['Returns, inventory-triggered work, legacy waste and mass collections are not fixed task totals.',
                            'Effective releases before simulation start are excluded; department opening hours may defer a schedule into the run.',
                            'Scheduled and timeframe releases have exact calendar events. Resource waits, staff handoffs and configured staggering can delay actual assignment; accumulation remains polled.',
                            'Preview IDs are stable for these frozen inputs and are not simulation event IDs.',
                            'No routing, assignment, resource contention or completion is simulated.']}


def filter_tasks(preview, *, query='', department='', category='', payload='', date='', route_profile=''):
    filters = {'department': department, 'category': category, 'payload': payload, 'route_profile': route_profile}
    return [task for task in preview['tasks']
            if all(not value or task[key] == value for key, value in filters.items())
            and (not date or task['release_datetime'].startswith(date))
            and query.casefold() in json.dumps(task, ensure_ascii=False).casefold()]


def timetable(tasks):
    counts = Counter((t['release_datetime'][:13], t['category'], t['department']) for t in tasks)
    return [{'hour': hour + ':00', 'category': category, 'department': department, 'planned_records': count}
            for (hour, category, department), count in sorted(counts.items())]


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--end', dest='end_datetime')
    args = parser.parse_args()
    result = build_demand_preview(json.loads(args.config.read_text(encoding='utf-8-sig')), end_datetime=args.end_datetime)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['totals']))
