"""Opt-in transport release flexibility; native demand clocks are unchanged."""
from bisect import bisect_right

DEFAULT_RELEASE_POLICY = dict(version=1, mode='fixed', max_delay_minutes=120.0)


def release_allowance(task, profile):
    policy = profile.get('release_policy', DEFAULT_RELEASE_POLICY)
    if policy['mode'] != 'staff_aligned':
        return 0.0, 'Fixed category timing'
    labels = {str(v).lower() for v in (getattr(task, 'labels', []) or [])}
    if 'scheduled' in labels or getattr(task, 'generator_direct_volume_component', '') == 'scheduled':
        return 0.0, 'Fixed scheduled task'
    if not getattr(task, 'created_during_runtime', False):
        return 0.0, 'Fixed explicit task'
    return policy['max_delay_minutes']*60, 'Flexible category timing'


def staffed_intervals(roster, service):
    """Union of eligible shift intervals, with each person's breaks removed."""
    intervals = []
    for person in roster:
        if person['pool'] not in ('shared', service):
            continue
        cursor = person['start']
        for start, end in sorted(person['breaks']):
            if cursor < min(start, person['end']):
                intervals.append((cursor, min(start, person['end'])))
            cursor = max(cursor, end)
        if cursor < person['end']:
            intervals.append((cursor, person['end']))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged, [end for _, end in merged]


def aligned_release(ready, latest, intervals, next_open=lambda at: at):
    """Earliest staffed, open instant in the allowed window, or no solution.

    This uses only the task being released and the declared roster. It does not
    inspect future random tasks or change the generator's consumption schedule.
    """
    if ready > latest:
        return None
    periods, ends = intervals
    for start, end in periods[bisect_right(ends, ready):]:
        at = max(start, ready)
        if at > latest:
            break
        at = next_open(at)
        if at is not None and at <= latest and at < end:
            return at
    return None
