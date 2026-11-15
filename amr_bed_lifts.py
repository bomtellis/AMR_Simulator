"""FM-first AMR routing and recurring bed-lift access allowances.

Windows reserve time for AMRs; they do not simulate individual bed movements.
Planning evaluates private alternatives and never changes live bookings.
"""
from copy import deepcopy
from datetime import timedelta
import math
import re


def minute(value, *, end=False):
    if end and value == '24:00':
        return 1440
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Use HH:MM times (24:00 is allowed only as an end time).')
    hours, minutes = map(int, value.split(':'))
    return hours * 60 + minutes


def window_intervals(windows):
    """Validate and return minute intervals on a cyclic day, unsplit overnight."""
    if not isinstance(windows, list):
        raise ValueError('AMR access windows must be a list.')
    intervals, pieces = [], []
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError('Each AMR access window needs start and end times.')
        start, end = minute(window.get('start')), minute(window.get('end'), end=True)
        if start == end:
            raise ValueError('Access window start and end must differ; use 00:00 to 24:00 for all day.')
        if end < start:
            end += 1440
        intervals.append((start, end))
        pieces.append((start, min(end, 1440)))
        if end > 1440:
            pieces.append((0, end - 1440))
    pieces.sort()
    if any(b[0] < a[1] for a, b in zip(pieces, pieces[1:])):
        raise ValueError('AMR access windows must not overlap, including across midnight.')
    return sorted(intervals)


def bed_lift_input_findings(config):
    building = config.get('building', {})
    if isinstance(building, dict):
        value = building.get('bed_lift_fallback_wait_sec', 300)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            yield '/building/bed_lift_fallback_wait_sec', 'FM waiting limit must be a finite non-negative number of seconds.'
    lifts = config.get('lifts', [])
    if not isinstance(lifts, list):
        return
    for index, lift in enumerate(lifts):
        if not isinstance(lift, dict):
            continue
        if lift.get('usage_mode', 'fm') not in ('fm', 'bed_fallback'):
            yield f'/lifts/{index}/usage_mode', 'Choose FM lift or Bed lift — AMR fallback.'
        try:
            window_intervals(lift.get('amr_access_windows', []))
        except ValueError as error:
            yield f'/lifts/{index}/amr_access_windows', str(error)


def policy_key(config):
    beds = tuple((lift['id'], tuple((w['start'], w['end']) for w in lift.get('amr_access_windows', [])))
                 for lift in config.get('lifts', []) if lift.get('usage_mode') == 'bed_fallback')
    return (('bed_fallback', config.get('building', {}).get('bed_lift_fallback_wait_sec', 300), beds),) if beds else ()


def fm_rules(sim, rules):
    result = deepcopy(rules or sim._empty_route_rules())
    ids = {lift.id for lift in sim.lifts if lift.usage_mode != 'bed_fallback'}
    if result.get('allowed_lifts'):
        ids &= set(result['allowed_lifts'])
    result['allowed_lifts'] = ids
    if not ids:
        result['blocked_route_dimensions'] = set(result.get('blocked_route_dimensions', ())) | {'allowed_lifts'}
    return result


def boarding_wait(leg):
    return max(0.0, leg['entry_start_sec'] - leg['arrival_at_lift'])


def select_plan(sim, planner, ready_time, amr, start, finish, payload, rules, orientation, collect_segments):
    from amr_floor_routing import lift_plan_journeys
    args = sim, ready_time, amr, start, finish, payload
    if not any(lift.usage_mode == 'bed_fallback' for lift in sim.lifts):
        return planner(*args, rules, orientation, collect_segments)
    primary = planner(*args, fm_rules(sim, rules), orientation, collect_segments)
    waiting = sum(map(boarding_wait, lift_plan_journeys(primary))) if primary else None
    limit = sim.config.get('building', {}).get('bed_lift_fallback_wait_sec', 300)
    if primary is not None and waiting <= limit + 1e-9:
        return primary
    if sim.stop_requested:
        return None
    alternative_rules = dict(rules or sim._empty_route_rules(), bed_fallback_search=True)
    finish_before = primary['final_finish'] - 1e-9 if primary else math.inf
    alternative = planner(*args, alternative_rules, orientation, collect_segments,
                          finish_before=finish_before)
    if alternative is None or (primary is not None and alternative['final_finish'] >= primary['final_finish'] - 1e-9):
        return primary
    legs = lift_plan_journeys(alternative)
    beds = list(dict.fromkeys(leg['lift'].id for leg in legs if leg['lift'].usage_mode == 'bed_fallback'))
    if not beds:
        # A quicker FM-only alternative is preferable to invoking a bed lift.
        return alternative
    evidence = dict(bed_fallback_reason='fm_wait_limit' if primary else 'no_usable_fm_route',
                    bed_fallback_start_sec=ready_time,
                    bed_fallback_lift_ids=beds, predicted_fm_wait_sec=waiting,
                    estimated_time_saved_sec=primary['final_finish'] - alternative['final_finish'] if primary else None,
                    bed_fallback_wait_limit_sec=limit)
    # Cached candidate dictionaries must not acquire decision-specific evidence.
    annotated = tuple(dict(leg, **evidence, bed_fallback_decision=(index == 0)) for index, leg in enumerate(legs))
    if 'journeys' in alternative:
        return dict(alternative, journeys=annotated, **evidence)
    return annotated[0]


def access_intervals(sim, lift, requested):
    """Yield continuous permitted intervals clipped to the simulation horizon."""
    intervals = window_intervals(lift.amr_access_windows)
    horizon = sim.task_generation_horizon_sec
    if not intervals or not math.isfinite(requested) or requested >= horizon:
        return
    origin = sim.clock.start_datetime
    # Include yesterday's overnight interval when the run starts within it.
    midnight = sim.clock.sim_seconds_to_datetime(requested).replace(hour=0, minute=0, second=0, microsecond=0)
    day = midnight - timedelta(days=1)
    end_day = sim.clock.sim_seconds_to_datetime(horizon)
    pending = None
    while day <= end_day:
        offset = (day - origin).total_seconds()
        for start, end in intervals:
            a, b = max(0.0, offset + start * 60), min(horizon, offset + end * 60)
            if b <= requested or a >= b:
                continue
            if pending is not None and a <= pending[1]:
                pending = pending[0], max(b, pending[1])
            else:
                if pending is not None:
                    yield pending
                pending = a, b
        day += timedelta(days=1)
    if pending is not None:
        yield pending


def access_slot(sim, lift, requested, origin, destination, **options):
    find = sim._find_unrestricted_lift_journey_slot
    if lift.usage_mode != 'bed_fallback':
        return find(lift, requested, origin, destination, **options)
    for start, end in access_intervals(sim, lift, requested):
        sim._check_run_cancelled()
        if sim.stop_requested:
            break
        slot = find(lift, max(requested, start), origin, destination, **options)
        if slot['lift_start'] >= start and slot['lift_finish'] <= end + 1e-9:
            return slot
    return {'lift_finish': math.inf, 'lift_start': math.inf}
