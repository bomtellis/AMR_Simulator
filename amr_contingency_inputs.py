"""Explicit human-study inputs. No defaults are written into ordinary projects."""
from copy import deepcopy
from datetime import datetime, timedelta
from collections import Counter
from types import SimpleNamespace
import math
from amr_contingency_packing import OPERATOR_DEFAULTS

from amr_simulation_inputs import simulation_horizon_seconds

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def service_of(task):
    return (getattr(task, 'staff_category_key', '') or
            next((v for v in getattr(task, 'labels', []) if v not in ('return', 'dirty', 'clean')), '') or
            'explicit')


def default_settings(config):
    categories = config.get('task_generation', {}).get('categories', {})
    services = sorted(categories)
    if config.get('waste_streams') and config.get('departments'):
        services = sorted(set(services) | {'waste'})
    if config.get('tasks'):
        services = sorted(set(services) | {service_of(SimpleNamespace(**t)) for t in config['tasks']})
    generation = config.get('task_generation', {})
    staff = generation.get('staff_config', generation.get('staff', {}))
    inputs = _service_inputs(config, services)
    profiles = {}
    for service in services:
        source = inputs[service]
        profiles[service] = dict(
        payloads=sorted(source['payloads']), capacity_count=2,
        **OPERATOR_DEFAULTS,
        **carrying_estimate(config, source['payloads'], 2),
        base=source['bases'].most_common(1)[0][0] if source['bases'] else '',
        empty_speed_mps=staff.get('walking_speed_m_per_sec', 1.2),
        loaded_speed_mps=staff.get('walking_speed_m_per_sec', 1.2),
        pickup_seconds=config.get('building', {}).get('load_unload_time_sec', 20.0),
        unload_seconds=config.get('building', {}).get('load_unload_time_sec', 20.0),
        handling_minutes=categories.get(service, {}).get('staff_handling_minutes',
                            staff.get('default_handling_minutes', 15.0)),
        route_profile=None, shift_rules=None,
        release_policy=dict(version=1, mode='fixed', max_delay_minutes=120.0))
    patterns = staff.get('shift_patterns', {})
    lengths, days = set(), set()
    for pattern in patterns.values():
        if 'start_time' in pattern and 'end_time' in pattern:
            duration = (minute(pattern['end_time'])-minute(pattern['start_time'])) % 1440 or 1440
            lengths.add(duration/60)
            days.update(pattern.get('days_active', DAYS))
    bases = Counter(p['base'] for p in profiles.values() if p['base'])
    return dict(schema_version=1, services=[s for s in services if inputs[s]['active']], profiles=profiles,
        shifts=dict(lengths_hours=sorted(lengths) or [8.0], start_window=['00:00', '23:45'],
                    days=[day for day in DAYS if day in days] or list(DAYS), grid_minutes=15, periods=[], break_minutes=30,
                    break_after_hours=min(4.0, min(lengths or {8.0})/2), max_people=20,
                    shared_base=bases.most_common(1)[0][0] if bases else '', confirmed=False),
        buffer_percent=20.0, trial_budget=200, seed=0, max_round_tasks=8)


def carrying_estimate(config, payload_names, count):
    """Editable planning envelope: payloads in line and a 0.6 m operator space.

    The mass allowance represents the selected load, not an ergonomic limit.
    No AMR capacity is substituted for a person's carrying capacity.
    """
    from amr_payload_inputs import payload_dimensions
    rows = [p for p in config.get('payloads', []) if p['name'] in payload_names]
    sizes = [payload_dimensions(p) for p in rows]
    return dict(capacity_kg=max(1.0, count*max((float(p.get('weight_kg', 0)) for p in rows), default=0)),
                length_m=count*max((v[0] for v in sizes), default=0)+.6,
                width_m=max(.6, max((v[1] for v in sizes), default=0)),
                height_m=max(1.8, max((v[2] for v in sizes), default=0)))


def _service_inputs(config, services):
    """Resolve native rules without generating tasks or constructing a simulation."""
    from amr_sim_task_generation import TaskGenerationManager
    from amr_sim_time_utils import SimulationClock
    locations = {v['name']: None for v in config.get('locations', [])}
    payloads = {v['name']: SimpleNamespace(**deepcopy(v)) for v in config.get('payloads', [])}
    rows = {name: dict(payloads=set(), bases=Counter(), active=False) for name in services}
    def add(service, cfg, bases, *, active=True):
        if service not in rows:
            return
        entry = rows[service]
        entry['active'] |= active
        for field in ('payload', 'return_payload'):
            name = cfg.get(field)
            if name in payloads:
                entry['payloads'].add(name)
                for item in getattr(payloads[name], 'items', {}).values():
                    if item.get('exchange_payload') in payloads:
                        entry['payloads'].add(item['exchange_payload'])
        entry['bases'].update(name for name in bases if name in locations)
    manager = TaskGenerationManager(deepcopy(config),
        SimulationClock(datetime.fromisoformat(config.get('simulation', {}).get('start_datetime', '2026-01-01'))),
        locations, payloads, prepare_runtime=False)
    for generator in manager.generators:
        for instance in getattr(generator, 'instances', []):
            side = 'dropoff_locations' if instance.get('department_location_role') == 'pickup' else 'pickup_locations'
            add(instance['category_key'], instance['cfg'], instance.get(side, []))
        if getattr(generator, 'generator_type', '') == 'department_waste':
            for instance in generator.container_instances():
                add('waste', instance['cfg'], instance.get('dropoff_locations', []))
    for task in config.get('tasks', []):
        add(service_of(SimpleNamespace(**task)), task, [task.get('pickup')])
    # Disabled categories can still be inspected and prepared for a later run.
    for name, entry in rows.items():
        if not entry['payloads']:
            cfg = config.get('task_generation', {}).get('categories', {}).get(name, {})
            add(name, cfg, [cfg.get('pickup_location')], active=False)
    return rows


def initial_settings(config):
    """Use saved edits, filling the blank setup produced by the original UI."""
    defaults = default_settings(config)
    saved = config.get('human_contingency', {}).get('settings')
    if not saved:
        return defaults
    result = deepcopy(saved)
    for name, default in defaults['profiles'].items():
        profile = result['profiles'].setdefault(name, deepcopy(default))
        legacy_blank = not profile.get('capacity_count') and not profile.get('length_m')
        for key, value in default.items():
            if key not in profile or (key in ('capacity_count', 'capacity_kg', 'length_m', 'width_m', 'height_m', 'base') and not profile[key]):
                profile[key] = deepcopy(value)
        if legacy_blank:
            profile['payloads'] = default['payloads']
            profile['pickup_seconds'] = default['pickup_seconds']
            profile['unload_seconds'] = default['unload_seconds']
            if name not in defaults['services'] and name in result['services']:
                result['services'].remove(name)
    if not result['shifts'].get('shared_base'):
        result['shifts']['shared_base'] = defaults['shifts']['shared_base']
    return result


def minute(value):
    try:
        h, m = map(int, value.split(':'))
        if not (0 <= h <= 24 and 0 <= m < 60 and (h < 24 or m == 0)):
            raise ValueError()
        return 60*h + m
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f'Invalid clock time: {value!r}; use HH:MM.') from None


def validate_settings(config, settings):
    s = deepcopy(settings)
    errors = []
    def positive(value, label, zero=False, integer=False):
        if (isinstance(value, bool) or not isinstance(value, (float, int)) or
            not math.isfinite(value) or value < 0 or (not zero and value == 0) or
            (integer and int(value) != value)):
            errors.append(f'{label}: enter a {"non-negative" if zero else "positive"} {"integer" if integer else "number"}.')
    if s.get('schema_version') != 1:
        errors.append('Unsupported human contingency settings version.')
    services = s.get('services', [])
    if not services or len(set(services)) != len(services):
        errors.append('Select at least one distinct service.')
    locations = {v['name'] for v in config.get('locations', [])}
    payloads = {v['name'] for v in config.get('payloads', [])}
    for name in services:
        p = s.get('profiles', {}).get(name, {})
        policy = p.get('release_policy', dict(version=1, mode='fixed', max_delay_minutes=120.0))
        if not isinstance(policy, dict) or policy.get('version') != 1 or policy.get('mode') not in ('fixed', 'staff_aligned'):
            errors.append(f'{name}: select a supported task timing policy.')
        else:
            positive(policy.get('max_delay_minutes'), f'{name}: maximum release/deadline delay (minutes)',
                     zero=policy['mode'] == 'fixed')
        for field in ('capacity_count', 'capacity_kg', 'length_m', 'width_m', 'height_m', 'empty_speed_mps', 'loaded_speed_mps'):
            positive(p.get(field), f'{name}: {field}', integer=field == 'capacity_count')
        for field in ('pickup_seconds', 'unload_seconds', 'handling_minutes'):
            positive(p.get(field), f'{name}: {field}', zero=True)
        for field,default in OPERATOR_DEFAULTS.items():
            positive(p.get(field,default), f'{name}: {field}')
        if p.get('base') not in locations:
            errors.append(f'{name}: select a valid base.')
        if not p.get('payloads') or not set(p['payloads']).issubset(payloads):
            errors.append(f'{name}: select known permitted payloads.')
        if p.get('route_profile') is not None and p['route_profile'] not in config.get('route_profiles', {}):
            errors.append(f'{name}: contingency route override does not exist.')
    r = s.get('shifts', {})
    if not r.get('confirmed'):
        errors.append('Review and confirm operational shift and break rules before running.')
    if r.get('shared_base') not in locations:
        errors.append('Select a shared-team base.')
    for pool in ['shared', *services]:
        override = s.get('profiles', {}).get(pool, {}).get('shift_rules') if pool != 'shared' else None
        if override is not None and not isinstance(override, dict):
            errors.append(f'{pool}: invalid independent shift rules.')
            continue
        rules = shift_rules(s, pool)
        lengths = rules.get('lengths_hours', [])
        periods = rules.get('periods', [])
        if not isinstance(periods, list):
            errors.append(f'{pool}: shift periods must be a list of start and finish times.')
            periods = []
        if periods:
            lengths = []
            for period in periods:
                try:
                    begin, end = minute(period['start']), minute(period['end'])
                    if begin >= 1440:raise ValueError('Shift start must be before 24:00.')
                    lengths.append(((end-begin) % 1440 or 1440)/60)
                except (ValueError, TypeError, KeyError) as exc:
                    errors.append(f'{pool}: invalid shift period: {exc}')
        else:
            if not lengths:errors.append(f'{pool}: enter allowed shift lengths.')
            try:
                lo, hi = map(minute, rules.get('start_window', []))
                if lo > hi or hi >= 1440:
                    errors.append(f'{pool}: start window must be ordered within one calendar day; shifts may finish next day.')
            except (ValueError, TypeError) as exc:
                errors.append(f'{pool}: {exc}')
        for length in lengths:
            positive(length, f'{pool}: shift length')
            if isinstance(length, (int, float)) and length > 24:
                errors.append(f'{pool}: a shift cannot exceed 24 hours.')
        for field in ('grid_minutes', 'max_people'):
            positive(rules.get(field), f'{pool}: {field}', integer=True)
        for field in ('break_minutes', 'break_after_hours'):
            positive(rules.get(field), f'{pool}: {field}', zero=True)
        if not rules.get('days') or not set(rules['days']).issubset(DAYS):
            errors.append(f'{pool}: select valid active weekdays.')
        if all(isinstance(rules.get(k), (int, float)) for k in ('break_minutes', 'break_after_hours')):
            if rules['break_minutes'] and any(isinstance(length, (int, float)) and
                    rules['break_after_hours']*60+rules['break_minutes'] >= length*60 for length in lengths):
                errors.append(f'{pool}: each allowed shift must extend beyond its configured break.')
    positive(s.get('buffer_percent'), 'Buffer percent', zero=True)
    positive(s.get('trial_budget'), 'Trial budget', integer=True)
    positive(s.get('max_round_tasks'), 'Round task limit', integer=True)
    if isinstance(s.get('max_round_tasks'), (int, float)) and s['max_round_tasks'] > 12:
        errors.append('Round task limit must be at most 12 to keep route search bounded.')
    positive(s.get('seed'), 'Seed', zero=True, integer=True)
    if errors:
        raise ValueError('\n'.join(errors))
    # Give CLI-created studies the same complete representation as the UI so
    # opening/resuming them does not look like an input edit.
    s['shifts'].setdefault('periods', [])
    for name,p in s.get('profiles', {}).items():
        p.setdefault('release_policy',dict(version=1,mode='fixed',max_delay_minutes=120.0))
        p.setdefault('shift_rules',None)
        if isinstance(p['shift_rules'],dict):
            rules=shift_rules(s,name)
            p['shift_rules']={key:deepcopy(rules[key]) for key in SHIFT_RULE_FIELDS}
    return s


SHIFT_RULE_FIELDS = ('lengths_hours', 'start_window', 'days', 'grid_minutes', 'periods',
                     'break_minutes', 'break_after_hours', 'max_people')


def shift_rules(settings, pool):
    rules = dict(settings['shifts'])
    if pool != 'shared':
        override = settings['profiles'][pool].get('shift_rules') or {}
        rules.update({k:v for k,v in override.items() if k in SHIFT_RULE_FIELDS})
    return rules


def roster_within_limits(roster, settings):
    return all(peak_people([r for r in roster if r['pool']==pool]) <= shift_rules(settings, pool)['max_people']
               for pool in {r['pool'] for r in roster})


def shift_candidates(config, settings, arrangement):
    start = datetime.fromisoformat(config['simulation']['start_datetime'])
    horizon = simulation_horizon_seconds(config)
    end = start + timedelta(seconds=horizon)
    values = []
    pools = settings['services'] if arrangement == 'dedicated' else ['shared']
    for pool in pools:
        r = shift_rules(settings, pool)
        periods = r.get('periods', [])
        starts = ([(minute(p['start']), ((minute(p['end'])-minute(p['start'])) % 1440 or 1440)/60) for p in periods]
                  if periods else [(offset, length) for offset in range(minute(r['start_window'][0]),
                    minute(r['start_window'][1])+1, r['grid_minutes']) for length in sorted(set(r['lengths_hours']))])
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if periods:day -= timedelta(days=1)
        pool_values = []
        while day <= end:
            if DAYS[day.weekday()] in r['days']:
                for offset, length in sorted(set(starts)):
                    begin = (day + timedelta(minutes=offset)-start).total_seconds()
                    finish = begin+length*3600
                    if (begin < 0 and (not periods or finish <= 0)) or begin > horizon:
                        continue
                    breaks = ([[begin+r['break_after_hours']*3600,
                                begin+r['break_after_hours']*3600+r['break_minutes']*60]] if r['break_minutes'] else [])
                    pool_values.append(dict(pool=pool, start=begin, end=finish, breaks=breaks,
                            base=r['shared_base'] if pool == 'shared' else settings['profiles'][pool]['base']))
            day += timedelta(days=1)
        if not pool_values:
            raise ValueError(f'{pool}: no allowed shift starts fall within the study period.')
        values.extend(pool_values)
    return sorted(values, key=lambda v:(v['start'], v['end'], v['pool']))


def peak_people(roster):
    count = peak = 0
    for _, delta in sorted([(r['start'], 1) for r in roster] + [(r['end'], -1) for r in roster]):
        count += delta
        peak = max(peak, count)
    return peak
