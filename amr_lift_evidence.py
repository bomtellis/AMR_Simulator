"""Check recorded lift plans against frozen inputs and final booking counts.

This is a model invariant check, not evidence that a physical lift executed a
journey. Legacy/filtered logs retain observed conflicts without claiming that
an absence of observations proves consistency.
"""
import json
import math
import re
from collections import defaultdict

CAPABILITY = 'lift_movement_counts_v1'
TIME_TOLERANCE_SEC = .002  # CSV start and duration values are rounded to ms.
KINDS = {'segment_lift_transfer': 'transfer', 'segment_lift_reposition': 'reposition'}


def booked_movement_counts(simulation):
    """Derive expected movements from bookings, independently of logged rows."""
    counts = {}
    for lift in simulation.lifts:
        floor = simulation.lift_initial_floors[lift.id]
        transfer = reposition = 0
        for _start, _finish, origin, destination, _owner in sorted(simulation.lift_reservations.get(lift.id, [])):
            transfer += 1
            reposition += int(floor != origin)
            floor = destination
        counts[lift.id] = {'transfer': transfer, 'reposition': reposition}
    return counts


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _floor(value, lift_id):
    match = re.fullmatch(re.escape(lift_id) + r'-F(-?\d+)', str(value or ''))
    return int(match[1]) if match else None


def check_lift_movements(events, frozen=None, *, complete=False, capabilities=(), expected=None):
    configured = {}
    input_valid = isinstance(frozen, dict) and isinstance(frozen.get('lifts'), list)
    if input_valid:
        for lift in frozen['lifts']:
            if not isinstance(lift, dict) or not isinstance(lift.get('id'), str) or not lift['id'] or lift['id'] in configured:
                input_valid = False
                continue
            initial = _number(lift.get('start_floor', 0))
            if initial is None or not initial.is_integer() or isinstance(lift.get('start_floor'), bool):
                input_valid = False
                initial = None
            configured[lift['id']] = int(initial) if initial is not None else None

    grouped = defaultdict(list)
    for event in events:
        if event['type'] in KINDS:
            grouped[str(event.get('lift_id') or '')].append(event)
    expected_valid = isinstance(expected, dict) and set(expected) == set(configured)
    coverage = bool(complete and input_valid and CAPABILITY in capabilities and expected_valid)
    records, issues = [], []
    for lift_id in sorted(set(configured) | set(grouped) | (set(expected) if isinstance(expected, dict) else set())):
        source = grouped[lift_id]
        moves, problems = [], []

        def issue(kind, reason, event_ids=()):
            problem = {'lift_id': lift_id, 'kind': kind, 'reason': reason, 'event_ids': list(event_ids)}
            problems.append(problem)
            return problem

        if not lift_id or lift_id not in configured:
            issue('missing_evidence', 'Lift identity or its bound initial-floor definition is unavailable.', [e['id'] for e in source])
        observed = {'transfer': 0, 'reposition': 0}
        for event in source:
            kind = KINDS[event['type']]
            observed[kind] += 1
            row = event['row']
            try:
                detail = json.loads(row.get('details') or '{}')
            except (ValueError, TypeError):
                detail = {}
            detail = detail if isinstance(detail, dict) else {}
            endpoints = []
            for key in ('from', 'to'):
                primary = _floor(detail.get(key), lift_id) if lift_id else None
                fallback = _floor(row.get(key + '_location'), lift_id) if lift_id else None
                # Reposition row coordinates can describe the waiting robot;
                # only actual lift node names establish its endpoints.
                endpoints.append(primary if primary is not None else fallback)
                if primary is not None and fallback is not None and primary != fallback:
                    issue('missing_evidence', 'Conflicting recorded lift endpoints.', [event['id']])
                    endpoints[-1] = None
            start = _number(event.get('time_seconds'))
            duration = _number(event.get('duration_seconds'))
            valid_time = start is not None and start >= 0 and duration is not None and duration >= 0
            if valid_time and not math.isfinite(start + duration):
                valid_time = False
            valid_endpoints = all(floor is not None for floor in endpoints)
            if duration == 0 and valid_endpoints and endpoints[0] != endpoints[1]:
                valid_time = False
            if not valid_time or not valid_endpoints or not event.get('lift_id'):
                issue('missing_evidence', 'A lift movement lacks finite non-negative timing, lift identity or explicit floor endpoints.', [event['id']])
            if event.get('identity') != 'native':
                issue('missing_evidence', 'Legacy row identity cannot establish native movement coverage.', [event['id']])
            if valid_time and valid_endpoints:
                moves.append({'id': event['id'], 'start': start, 'finish': start + duration,
                              'origin': endpoints[0], 'destination': endpoints[1], 'kind': kind})
        counts = expected.get(lift_id) if isinstance(expected, dict) else None
        valid_counts = isinstance(counts, dict) and all(
            isinstance(counts.get(kind), int) and not isinstance(counts[kind], bool) and counts[kind] >= 0
            for kind in ('transfer', 'reposition'))
        counts_match = observed == counts if valid_counts else None
        if not valid_counts:
            issue('missing_evidence', 'Final booking-derived movement counts are unavailable.', [e['id'] for e in source])
        elif not counts_match:
            issue('count_mismatch', f'Booked movements {counts} differ from recorded movements {observed}.', [e['id'] for e in source])

        previous = None
        initial = configured.get(lift_id)
        # A malformed movement can sit anywhere in the sequence; do not bridge
        # over it and invent floor continuity. Valid intervals can still prove
        # an overlapping plan, even when other evidence is missing.
        floor_sequence_known = len(moves) == len(source)
        for movement in sorted(moves, key=lambda m: (m['start'], m['finish'], m['id'])):
            overlap = (previous is not None and movement['finish'] > movement['start']
                       and movement['start'] < previous['finish'] - TIME_TOLERANCE_SEC)
            if overlap:
                issue('overlap', f"Movement starts at {movement['start']:g} s before the lift is free at {previous['finish']:g} s.",
                      [previous['id'], movement['id']])
            elif floor_sequence_known:
                floor = previous['destination'] if previous else initial
                if floor is not None and movement['origin'] != floor:
                    issue('floor_discontinuity', f"Recorded lift starts on floor {movement['origin']}, but the preceding destination or bound initial floor is {floor}.",
                          ([previous['id']] if previous else []) + [movement['id']])
            # Retain the longest occupied interval to catch nested overlaps.
            if previous is None or movement['finish'] >= previous['finish']:
                previous = movement
        known = coverage and lift_id in configured and counts_match is True and not any(
            p['kind'] == 'missing_evidence' for p in problems)
        conflicts = [p for p in problems if p['kind'] in ('overlap', 'floor_discontinuity', 'count_mismatch')]
        records.append({'lift_id': lift_id, 'known': known,
                        'status': 'Conflict' if conflicts else 'Consistent' if known else 'Incomplete evidence',
                        'initial_floor': initial, 'observed': observed, 'expected': counts if valid_counts else None,
                        'counts_match': counts_match, 'issues': problems,
                        'event_ids': [e['id'] for e in source]})
        issues.extend(problems)
    known = coverage and all(r['known'] for r in records)
    return {'known': known, 'records': records, 'issues': issues,
            'time_tolerance_seconds': TIME_TOLERANCE_SEC,
            'scope': 'Recorded planned movements and final booking counts; not physical execution or reliability certification.'}
