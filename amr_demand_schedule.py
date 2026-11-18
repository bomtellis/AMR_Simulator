"""Draft-only adapters for the day schedule and the existing FM planning model."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
SCHEDULED = {'scheduled', 'scheduled_threshold', 'scheduled_sporadic'}


def minutes(value, *, end=False):
    parts = str(value).split(':')
    if len(parts) not in (2, 3):
        raise ValueError('Enter a time as HH:MM.')
    try:
        hour, minute = map(int, parts[:2])
    except (ValueError, TypeError):
        raise ValueError('Enter a time as HH:MM.') from None
    if end and hour == 24 and minute == 0:
        return 1440
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError('Use 00:00 to 23:59 (or 24:00 for a timeframe end).')
    return hour * 60 + minute


def clock(value, *, end=False):
    value = int(round(value))
    if end and value == 1440:
        return '24:00'
    value %= 1440
    return f'{value // 60:02d}:{value % 60:02d}'


def span(start, end):
    return (end - start) % 1440 or 1440


def segments(start, duration):
    """Visible pieces on a circular day; full-day bars retain their true handles."""
    start %= 1440
    stop = start + duration
    return [(start, min(stop, 1440))] + ([(0, stop - 1440)] if stop > 1440 else [])


@dataclass
class ScheduleRule:
    identity: tuple
    category: str
    label: str
    members: tuple
    settings: dict
    message: str = ''


def rules(generation, departments=()):
    names = {str(d.get('id') or d.get('name', '')): str(d.get('name') or d.get('id'))
             for d in departments}
    result = []
    for key, category in generation.get('categories', {}).items():
        if not isinstance(category, dict):
            continue
        covered = set()
        groups = category.get('department_groups', [])
        entries = []
        for group in groups:
            if not isinstance(group, dict) or not group.get('departments') or not isinstance(group.get('payload'), dict):
                continue
            members = tuple(group['departments'])
            covered.update(members)
            entries.append((('group', key, group.get('id')), str(group.get('id', 'Group')),
                            members, group['payload']))
        overrides = category.get('departments', {})
        for member, payload in overrides.items():
            if member not in covered and isinstance(payload, dict):
                entries.append((('department', key, member), names.get(member, member), (member,), payload))
        if not entries:
            entries.append((('category', key, ''), 'Category default', (), {}))
        for identity, label, members, payload in entries:
            settings = {**category, **payload}
            message = ''
            mode = settings.get('generation_mode', 'scheduled')
            if key == 'waste' and settings.get('uses_department_waste_streams', True):
                message = 'Waste stream timing is controlled in Departments → Waste streams.'
            elif mode not in SCHEDULED | {'timeframe'}:
                message = f'{mode.capitalize()} demand: release times depend on runtime conditions.'
            result.append(ScheduleRule(identity, key, label, members, settings, message))
    return result


def rule_times(rule):
    if rule.message:
        return []
    cfg = rule.settings
    if cfg.get('generation_mode') == 'timeframe':
        start = minutes(cfg.get('timeframe_start'))
        end = minutes(cfg.get('timeframe_end'), end=True)
        return [('window', start, span(start, end))]
    values = cfg.get('scheduled_times', cfg.get('schedule_times', []))
    if isinstance(values, str):
        values = [value.strip() for value in values.split(',') if value.strip()]
    return [(value, minutes(value), 0) for value in sorted(set(values))]


def edit_demand(generation, identity, token, start, duration=None, *, scheduled_times=None):
    """Return an independent draft, preserving group IDs and endpoint copies."""
    result = deepcopy(generation)
    rule = next((row for row in rules(result) if row.identity == identity), None)
    if rule is None or rule.message:
        raise ValueError('Open the existing settings editor for this demand rule.')
    category = result['categories'][rule.category]
    kind, _, key = identity
    before = deepcopy(category.get('department_groups', []))
    target = (next(group['payload'] for group in category['department_groups'] if group['id'] == key)
              if kind == 'group' else category['departments'][key] if kind == 'department' else category)
    if token == 'window':
        if duration is None or not 1 <= duration <= 1440:
            raise ValueError('A demand window must last between one minute and one day.')
        target['timeframe_start'] = clock(start)
        unwrapped = start % 1440 + duration
        target['timeframe_end'] = clock(unwrapped if unwrapped <= 1440 else unwrapped - 1440, end=True)
    else:
        values = [value for value, _, _ in rule_times(rule)]
        value = clock(start)
        if scheduled_times is None and value != token and value in values:
            raise ValueError('There is already a scheduled release at that time.')
        updated = list(scheduled_times) if scheduled_times is not None else [value if old == token else old for old in values]
        if len(set(updated)) != len(updated):
            raise ValueError('The move would place two scheduled releases at the same time.')
        target['scheduled_times'] = sorted(updated)
    if kind == 'group':
        from visualiser.configured_group_editor import apply_group_edits
        after = deepcopy(category['department_groups'])

        def compatibility(group, department):
            payload = deepcopy(group['payload'])
            old = category.get('departments', {}).get(department, {})
            endpoint = 'pickup' if payload.get('department_location_role') == 'pickup' else 'dropoff'
            for field in (endpoint + '_location', endpoint + '_locations'):
                if field in old:
                    payload[field] = deepcopy(old[field])
            return payload

        result['categories'][rule.category] = apply_group_edits(category, before, after, compatibility)
    return result


def edit_category_notes(generation, category, notes):
    result = deepcopy(generation)
    result['categories'][category]['notes'] = str(notes).strip()
    return result


def move_demand_selection(generation, selected, delta):
    """Shift all selected native items in one draft, including adjacent clock times."""
    result = deepcopy(generation)
    grouped = {}
    for identity, token in selected:
        grouped.setdefault(tuple(identity), set()).add(token)
    originals = {rule.identity: rule for rule in rules(generation)}
    for identity, tokens in grouped.items():
        rule = originals.get(identity)
        if rule is None or rule.message:
            raise ValueError('One selected schedule is no longer editable. Select the bars again.')
        times = rule_times(rule)
        if 'window' in tokens:
            _, start, duration = times[0]
            result = edit_demand(result, identity, 'window', (start+delta)%1440, duration)
        else:
            if not tokens <= {token for token,_,_ in times}:
                raise ValueError('One selected release no longer exists. Select the bars again.')
            values = [clock((start+delta)%1440) if token in tokens else token for token,start,_ in times]
            result = edit_demand(result, identity, next(iter(tokens)), 0, scheduled_times=values)
    return result


def move_fm_selection(plan, selected, delta):
    """A selected dispatch window carries its cohorts without moving them twice."""
    result = deepcopy(plan)
    windows = {(category, slot) for category, slot, cohort in selected if cohort is None}
    for category, slot in windows:
        window = plan['categories'][category]['slots'][slot]
        start = minutes(window['earliest'])
        result = edit_fm(result, category, slot, None, (start+delta)%1440,
                         span(start, minutes(window['deadline'])))
    for category, slot, cohort in selected:
        if cohort is None or (category,slot) in windows:
            continue
        window = plan['categories'][category]['slots'][slot]
        start = (minutes(window['earliest'])+window['offsets'][cohort]/60+delta)%1440
        result = edit_fm(result, category, slot, cohort, start)
    return result


def invalid_slots(generation):
    """Native slot keys must still identify a configured release or timeframe."""
    available = {}
    for rule in rules(generation):
        if rule.message:
            continue
        slots = available.setdefault(rule.category, set())
        cfg = rule.settings
        try:
            for token, start, duration in rule_times(rule):
                slots.add(f"timeframe/{cfg.get('timeframe_start')}/{cfg.get('timeframe_end')}"
                          if token == 'window' else clock(start))
                if duration:
                    slots.add('timeframe')
        except ValueError:
            continue
    return [(category, slot) for category, policy in generation.get('fm_logistics', {}).get('categories', {}).items()
            for slot in policy.get('slots', {}) if slot not in available.get(category, set())
            and not (category == 'waste' and generation.get('categories', {}).get(category, {}).get('uses_department_waste_streams', True))]


def edit_fm(plan, category, slot, cohort, start, duration=None):
    from amr_fm_logistics import validate_fm_settings
    result = deepcopy(plan)
    window = result['categories'][category]['slots'][slot]
    first = minutes(window['earliest'])
    if cohort is None:
        if duration is None or not 1 <= duration < 1440:
            raise ValueError('An FM dispatch window must be shorter than a full day.')
        window['earliest'] = clock(start)
        window['deadline'] = clock(start + duration)
    else:
        window['offsets'][cohort] = ((start - first) % 1440) * 60
    validate_fm_settings(result)
    return result


def arrangement(config, *, suggest=False):
    """Use the FM planner's existing ranking and all forecastable categories."""
    from amr_fm_forecast import native_demand, suggest_policy, compare, wave_slot, missing_demand_assignments
    if missing_demand_assignments(config):
        raise ValueError('Some demand assignments refer to missing departments. Open FM logistics planning → Planning settings to resolve them before suggesting an arrangement.')
    baseline = native_demand(config)
    start = datetime.fromisoformat(baseline['start_datetime'])
    plan = deepcopy(config.get('task_generation', {}).get('fm_logistics', {'categories': {}}))
    plan['enabled'] = True
    plan.setdefault('categories', {})
    if suggest:
        keys = sorted({row['category'] for row in baseline['tasks'] if wave_slot(row, start)})
        plan['categories'] = {key: dict(suggest_policy(config, baseline, key),
                                      hold_seconds=plan['categories'].get(key, {}).get('hold_seconds', 0))
                              for key in keys}
    invalid = invalid_slots(dict(config.get('task_generation', {}), fm_logistics=plan))
    if invalid:
        raise ValueError('Demand timings changed. Choose Suggest arrangement to regenerate FM windows, or disable the FM plan.')
    comparison = compare(config, plan, baseline)
    current = next(row for row in comparison['results'] if row['strategy'] == 'current')
    best = comparison['results'][0]
    score = lambda row: tuple(row['totals'].get(key, 0) for key in
                              ('unresolved', 'late', 'peak_lift_seconds', 'lift_wait_seconds'))
    selected = best['strategy'] if score(best) < score(current) else 'current'
    return {'baseline': baseline, 'comparison': comparison, 'selected': selected}


def validated_generation(config, plan, baseline):
    from amr_fm_forecast import validate_application
    generation = deepcopy(config.get('task_generation', {}))
    generation['fm_logistics'] = deepcopy(plan)
    if plan.get('enabled'):
        if invalid_slots(generation):
            raise ValueError('Demand timings changed. Regenerate or disable the FM plan before saving.')
        validate_application(config, plan, baseline)
    return generation
