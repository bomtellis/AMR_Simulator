"""Explicit human-study inputs. No defaults are written into ordinary projects."""
from copy import deepcopy
from datetime import datetime, timedelta
import math

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
        services = sorted(set(services) | {str((t.get('labels') or ['explicit'])[0]) for t in config['tasks']})
    staff = config.get('task_generation', {}).get('staff_config', {})
    payloads = [p['name'] for p in config.get('payloads', [])]
    return dict(schema_version=1, services=services, profiles={s: dict(
        payloads=payloads, capacity_count=0, capacity_kg=0.0,
        length_m=0.0, width_m=0.0, height_m=0.0, base='',
        empty_speed_mps=staff.get('walking_speed_m_per_sec', 1.2),
        loaded_speed_mps=staff.get('walking_speed_m_per_sec', 1.2),
        pickup_seconds=0.0, unload_seconds=0.0,
        handling_minutes=staff.get('default_handling_minutes', 15.0),
        route_profile=None) for s in services},
        shifts=dict(lengths_hours=[8.0], start_window=['00:00', '23:45'],
                    days=list(DAYS), grid_minutes=15, break_minutes=30,
                    break_after_hours=4.0, max_people=20, shared_base='', confirmed=False),
        buffer_percent=20.0, trial_budget=200, seed=0, max_round_tasks=8)


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
        for field in ('capacity_count', 'capacity_kg', 'length_m', 'width_m', 'height_m', 'empty_speed_mps', 'loaded_speed_mps'):
            positive(p.get(field), f'{name}: {field}', integer=field == 'capacity_count')
        for field in ('pickup_seconds', 'unload_seconds', 'handling_minutes'):
            positive(p.get(field), f'{name}: {field}', zero=True)
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
    if not r.get('lengths_hours'):
        errors.append('Enter allowed shift lengths.')
    for length in r.get('lengths_hours', []):
        positive(length, 'Shift length')
        if isinstance(length, (int, float)) and length > 24:
            errors.append('A shift cannot exceed 24 hours.')
    for field in ('grid_minutes', 'max_people'):
        positive(r.get(field), field, integer=True)
    for field in ('break_minutes', 'break_after_hours'):
        positive(r.get(field), field, zero=True)
    if not r.get('days') or not set(r['days']).issubset(DAYS):
        errors.append('Select valid active weekdays.')
    try:
        lo, hi = map(minute, r.get('start_window', []))
        if lo > hi:
            errors.append('Start window must be ordered within one calendar day; shifts may finish next day.')
    except (ValueError, TypeError) as exc:
        errors.append(str(exc))
    positive(s.get('buffer_percent'), 'Buffer percent', zero=True)
    positive(s.get('trial_budget'), 'Trial budget', integer=True)
    positive(s.get('max_round_tasks'), 'Round task limit', integer=True)
    if isinstance(s.get('max_round_tasks'), (int, float)) and s['max_round_tasks'] > 12:
        errors.append('Round task limit must be at most 12 to keep route search bounded.')
    positive(s.get('seed'), 'Seed', zero=True, integer=True)
    if errors:
        raise ValueError('\n'.join(errors))
    if r['break_minutes'] and any(r['break_after_hours']*60+r['break_minutes'] >= length*60 for length in r['lengths_hours']):
        raise ValueError('Each allowed shift must extend beyond its configured break.')
    return s


def shift_candidates(config, settings, arrangement):
    start = datetime.fromisoformat(config['simulation']['start_datetime'])
    horizon = simulation_horizon_seconds(config)
    end = start + timedelta(seconds=horizon)
    r = settings['shifts']
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    values = []
    pools = settings['services'] if arrangement == 'dedicated' else ['shared']
    while day <= end:
        if DAYS[day.weekday()] in r['days']:
            for offset in range(minute(r['start_window'][0]), minute(r['start_window'][1])+1, r['grid_minutes']):
                begin = (day + timedelta(minutes=offset)-start).total_seconds()
                if begin < 0 or begin > horizon:
                    continue
                for length in sorted(set(r['lengths_hours'])):
                    finish = begin+length*3600
                    breaks = ([[begin+r['break_after_hours']*3600,
                                begin+r['break_after_hours']*3600+r['break_minutes']*60]] if r['break_minutes'] else [])
                    for pool in pools:
                        values.append(dict(pool=pool, start=begin, end=finish, breaks=breaks,
                            base=r['shared_base'] if pool == 'shared' else settings['profiles'][pool]['base']))
        day += timedelta(days=1)
    if not values:
        raise ValueError('No allowed shift starts fall within the study period.')
    return values


def peak_people(roster):
    count = peak = 0
    for _, delta in sorted([(r['start'], 1) for r in roster] + [(r['end'], -1) for r in roster]):
        count += delta
        peak = max(peak, count)
    return peak
