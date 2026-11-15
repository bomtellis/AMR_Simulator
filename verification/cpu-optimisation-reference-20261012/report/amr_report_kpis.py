"""Operational KPIs from request lifecycles and unique physical movements.

Missing evidence stays missing. Optional report_kpis inputs describe the same
observation period as the CSV; they are labelled as supplied assumptions.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict

import pandas as pd


GROUPS = ['Demand', 'Service', 'Capacity', 'Efficiency', 'Bottleneck',
          'Reliability', 'Resources', 'Cost/sustainability']
STREAMS = ['Catering', 'Linen', 'Waste', 'Pharmacy', 'Receipt and distribution']
REQUEST_EVENTS = {'task_generated', 'waste_task_generated', 'return_task_generated',
                  'task_released', 'task_release_deferred', 'task_assigned', 'multi_stop_task_assigned'}
COMPLETE_EVENTS = {'task_complete', 'task_completed', 'multi_stop_task_complete'}
FAIL_EVENTS = {'task_failed', 'task_cancelled', 'task_canceled', 'task_abandoned',
               'task_staff_completed'}


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def clean(value):
    return '' if value is None or pd.isna(value) else str(value).strip()


def details(value):
    try:
        parsed = json.loads(clean(value))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def union(intervals):
    merged = []
    for start, finish in sorted(intervals):
        if finish <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(finish, merged[-1][1]))
        else:
            merged.append((start, finish))
    return merged


def total(intervals):
    return sum(b - a for a, b in union(intervals))


def peak(intervals):
    changes = defaultdict(int)
    for a, b in intervals:
        if b > a:
            changes[a] += 1
            changes[b] -= 1
    active = highest = 0
    for t in sorted(changes):
        active += changes[t]
        highest = max(highest, active)
    return highest


def canonical_stream(value):
    key = re.sub(r'[^a-z0-9]+', '_', clean(value).lower()).strip('_')
    aliases = {'catering': STREAMS[0], 'linen': STREAMS[1], 'waste': STREAMS[2],
               'department_waste': STREAMS[2], 'pharmacy': STREAMS[3],
               'stores': STREAMS[4], 'receipt_and_distribution': STREAMS[4],
               'receipt_distribution': STREAMS[4], 'r_d': STREAMS[4]}
    return aliases.get(key)


def build_kpis(df, ctx, tasks, journeys, *, config=None, metadata=None,
               staff_summary=None, energy_evidence=None, target_util=.85):
    # Import lazily to support both package imports and the standalone report CLI.
    try:
        from .amr_report_analysis import is_physical_amr_id, split_payload_names
    except ImportError:
        from amr_report_analysis import is_physical_amr_id, split_payload_names

    config, metadata = config or {}, metadata or {}
    assumptions = config.get('report_kpis', {}) or {}
    rows, queue_rows, request_rows = [], [], []
    frame = df.copy()
    frame['_seconds'] = (frame[ctx.time_col].map(lambda x: pd.Timestamp(x).timestamp()
                          if pd.notna(x) else float('nan')) if ctx.has_datetime
                         else pd.to_numeric(frame[ctx.time_col], errors='coerce'))
    first, last = frame['_seconds'].min(), frame['_seconds'].max()
    # Segment plans can extend beyond the end of a partial run. Summary snapshots
    # mark the observed cut-off and must take precedence over those future plans.
    snapshots = frame[frame['_event_text'].isin(['scenario_summary', 'scenario_impact_summary', 'battery_balance_summary'])]
    if not snapshots.empty:
        last = snapshots['_seconds'].max()
    reduced_logging = any(info.get('scenario_mode') is True and info.get('enhanced_logging') is False
        for info in (details(value) for value in snapshots.get('details', pd.Series(dtype=str))))
    horizon = max(0., last - first)
    seconds_col = ctx.cols.get('seconds')
    valid_epoch = frame.dropna(subset=['_seconds', seconds_col]) if seconds_col else pd.DataFrame()
    epoch = (float(valid_epoch.iloc[0]['_seconds']) - float(valid_epoch.iloc[0][seconds_col])
             if not valid_epoch.empty else None)
    task_lookup = tasks.set_index('task_id').to_dict('index') if not tasks.empty else {}
    journey_lookup = journeys.set_index('task_id').to_dict('index') if not journeys.empty else {}
    # Dispatch waits may be fleet-level records rather than per-task rows.
    # Recover only explicit task identifiers; never assign another task's cause.
    recorded_wait_reasons = defaultdict(list)
    wait_records = frame[frame['_event_text'].str.contains('wait|defer', case=False) & (frame['_seconds'] <= last)]
    for _, event in wait_records.iterrows():
        raw_reason = clean(event.get('details'))
        info = details(raw_reason)
        cause = clean(info.get('reason')) or (raw_reason if not info else clean(event.get(ctx.cols.get('segment_type'))))
        ids = [name.strip() for name in clean(event.get(ctx.cols['task'])).split(',')]
        ids += info.get('pending_task_ids', []) if isinstance(info.get('pending_task_ids'), list) else []
        for name in ids:
            if name in task_lookup and cause:
                recorded_wait_reasons[name].append(cause)
        if clean(event.get('_event_text')) == 'task_wait':
            for part in raw_reason.removeprefix('At start of assignment wait: ').split(';'):
                name, separator, reason = part.strip().partition(':')
                if separator and name in task_lookup and reason.strip():
                    recorded_wait_reasons[name].append(reason.strip())
    stream_map = assumptions.get('task_streams', {}) or {}
    payload_map = assumptions.get('payload_streams', {}) or {}
    catalog = {clean(loc.get('name')): loc for loc in config.get('locations', [])}
    location_streams = defaultdict(set)
    from amr_department_inputs import department_location_names
    for department in config.get('departments', []):
        for category, settings in (department.get('task_generation_locations', {}) or {}).items():
            stream = canonical_stream(category)
            if stream:
                for name in department_location_names(settings) + department_location_names(settings, zones=True):
                    location_streams[name].add(stream)

    grouped = frame[frame[ctx.cols['task']].notna()].groupby(ctx.cols['task'], sort=False)
    for task_id, events in grouped:
        task_id = str(task_id)
        journey = journey_lookup.get(task_id)
        if ',' in task_id or journey and journey.get('journey_type') == 'Empty AMR return':
            continue
        names = events['_event_text'].str.lower()
        request = events[names.isin(REQUEST_EVENTS)]
        if request.empty:
            # Some legacy failed-task logs have only their terminal event.
            # Preserve those requests, explicitly flagging the missing release.
            request = events[names.isin(FAIL_EVENTS | COMPLETE_EVENTS)]
            if request.empty:
                continue
        # A synthetic no-load return is vehicle repositioning, not service demand.
        task = task_lookup.get(task_id, {})
        if task_id.startswith('RETURN-') and not split_payload_names(task.get('payload')):
            continue
        release_values = pd.to_numeric(events.get(ctx.cols.get('task_release'),
                                      pd.Series(dtype=float)), errors='coerce').dropna()
        raised = float(request['_seconds'].min())
        basis = 'Logged request event'
        if not release_values.empty and epoch is not None:
            raised = epoch + float(release_values.iloc[0])
            basis = 'Recorded request release time'
        elif not names.isin(REQUEST_EVENTS - {'task_assigned', 'multi_stop_task_assigned'}).any():
            basis = ('First assignment' if names.isin({'task_assigned', 'multi_stop_task_assigned'}).any()
                     else 'First recorded task event') + ' (request time unavailable)'
        if raised > last:
            continue
        assignment = events[names.isin({'task_assigned', 'multi_stop_task_assigned'})]
        completion = events[names.isin(COMPLETE_EVENTS) & (events['_seconds'] <= last)]
        failure = events[names.isin(FAIL_EVENTS) & (events['_seconds'] <= last)]
        finish = float(completion['_seconds'].max()) if not completion.empty else None
        failure_time = float(failure['_seconds'].max()) if not failure.empty else None
        outcome = 'completed' if finish is not None else 'failed' if failure_time is not None else 'incomplete'
        assigned = float(assignment['_seconds'].min()) if not assignment.empty else None
        if assigned is not None and assigned > last:
            assigned = None
        amrs = assignment[ctx.cols['amr']].dropna() if not assignment.empty else pd.Series(dtype=str)
        amr = str(amrs.iloc[0]) if not amrs.empty else ''
        terminal = finish if finish is not None else failure_time if failure_time is not None else last
        target = number(task.get('target_s'))
        elapsed = finish - raised if finish is not None and finish >= raised else None
        overdue = bool(target and terminal - raised > target)
        origin = journey.get('origin_location', task.get('origin', '')) if journey else task.get('origin', '')
        destination = journey.get('destination_location', task.get('destination', '')) if journey else task.get('destination', '')
        stream = canonical_stream(stream_map.get(task_id)) or canonical_stream(payload_map.get(task.get('payload')))
        for _, event in events.iterrows():
            if stream:
                break
            for key in ('task_category', 'category_key', 'staff_category_key', 'task_source'):
                stream = canonical_stream(event.get(key))
                if stream:
                    break
            match = re.search(r'(?:RETURN_)?GEN_([A-Z0-9]+)', task_id, re.I)
            stream = stream or (canonical_stream(match.group(1)) if match else None)
            match = re.search(r'Generated\s+(?:scheduled-threshold|scheduled|sporadic|threshold|timeframe)\s+(.+?)\s+task\b', clean(event.get('details')), re.I)
            stream = stream or (canonical_stream(match.group(1)) if match else None)
        if not stream:
            candidates = location_streams[origin] | location_streams[destination]
            stream = next(iter(candidates)) if len(candidates) == 1 else 'Unclassified'
        reasons = [clean(v) for v in events.get('pending_reason', pd.Series(dtype=str)) if clean(v)]
        wait_events = events[events['_event_text'].str.contains('fail|cancel|abandon', case=False)]
        reasons += [clean(v) for v in wait_events.get('details', pd.Series(dtype=str)) if clean(v)]
        reasons += recorded_wait_reasons[task_id]
        reason = '; '.join(dict.fromkeys(reasons)) or 'Reason not recorded'
        request_rows.append(dict(task_id=task_id, stream=stream, outcome=outcome, amr=amr,
            release_s=raised, assignment_s=assigned, finish_s=finish, terminal_s=terminal,
            request_time_basis=basis, delivery_time_s=elapsed, target_s=target,
            overdue=overdue, overdue_s=max(0., terminal - raised - target) if target else None,
            reason=reason, origin=origin, destination=destination))
        dispatch_finish = assigned if assigned is not None else terminal
        dispatch_wait = min(dispatch_finish, last) - max(raised, first)
        if dispatch_wait > 0:
            queue_rows.append(dict(location=origin or 'Unknown',
                cause='Dispatch queue (open)' if assigned is None and outcome == 'incomplete' else 'Dispatch queue',
                resource=task_id, wait_s=dispatch_wait))

    requests = pd.DataFrame(request_rows, columns=['task_id', 'stream', 'outcome', 'amr',
        'release_s', 'assignment_s', 'finish_s', 'terminal_s', 'request_time_basis',
        'delivery_time_s', 'target_s', 'overdue', 'overdue_s', 'reason', 'origin', 'destination'])
    requests['overdue'] = requests.overdue.astype(bool)
    for field in ('delivery_time_s', 'target_s', 'overdue_s'):
        requests[field] = pd.to_numeric(requests[field], errors='coerce')
    def display_time(value):
        if pd.isna(value):
            return ''
        return pd.Timestamp(value, unit='s').round('ms').isoformat(timespec='milliseconds') if ctx.has_datetime else f'{value:g}s'
    requests['request_time'] = requests.release_s.map(display_time)
    requests['completion_time'] = requests.finish_s.map(display_time)
    requests['deadline'] = (requests.release_s + requests.target_s).map(display_time)
    done = requests[requests.outcome.eq('completed')]
    completed_count = len(done)
    completed_ids = set(done.task_id)
    observed_amrs = {str(v) for v in frame[ctx.cols['amr']].dropna() if is_physical_amr_id(v)}
    quantities = [number(robot.get('quantity', 1)) for robot in config.get('amrs', [])]
    configured_fleet_known = bool(quantities and all(v is not None for v in quantities))
    fleet = sum(quantities) if configured_fleet_known else len(observed_amrs)
    fleet_basis = 'Configured fleet' if configured_fleet_known else 'Observed fleet only; idle unlogged vehicles unknown'
    busy, productive, charging, physical_activity = (defaultdict(list) for _ in range(4))
    for record in request_rows:
        if record['assignment_s'] is not None and is_physical_amr_id(record['amr']):
            a, b = max(first, record['assignment_s']), min(last, record['terminal_s'])
            if b > a:
                busy[record['amr']].append((a, b))

    segments = frame[frame['_event_text'].str.match(r'(?:multi_stop_)?segment_', case=False)].copy()
    # Shared routes are emitted once. Repeated event identifiers cannot add distance/time.
    if 'event_id' in segments:
        identified = segments['event_id'].map(clean).ne('')
        segments = pd.concat([segments[identified].drop_duplicates('event_id'), segments[~identified]])
    distance = empty_distance = unknown_distance = congestion = lift_wait = charger_wait = 0.
    unknown_productive_s = 0.
    has_charger_wait = any(details(value).get('charger_queue_intervals_complete') is True
        for value in snapshots.get('details', pd.Series(dtype=str)))
    has_congestion = False
    partial_distance = False
    route_distances = defaultdict(float)
    charge_locations = defaultdict(list)
    for _, event in segments.iterrows():
        amr = clean(event.get(ctx.cols['amr']))
        if not is_physical_amr_id(amr):
            continue
        kind = clean(event.get(ctx.cols.get('segment_type'))).lower()
        a = number(event.get('_seconds'))
        duration = number(event.get('_duration_s'))
        if a is None or duration is None or duration <= 0 or a >= last:
            continue
        b = min(last, a + duration)
        a = max(first, a)
        fraction = max(0., b - a) / duration
        info = details(event.get('details'))
        physical_activity[amr].append((a, b))
        if kind == 'charge':
            charging[amr].append((a, b))
            charge_locations[clean(event.get(ctx.cols.get('to'))) or 'Unknown'].append((a, b))
        wait = bool(re.search('wait|queue', kind)) or kind == 'lift_reposition'
        if wait:
            cause = clean(info.get('reason')) or kind
            location = clean(event.get(ctx.cols.get('from'))) or 'Unknown'
            queue_rows.append(dict(location=location, cause=cause, resource=amr, wait_s=b-a))
            if clean(event.get(ctx.cols.get('lift'))) or 'lift' in kind or info.get('lift_id'):
                lift_wait += b - a
            if 'charg' in kind:
                has_charger_wait = True
                charger_wait += b - a
        loaded = None
        if not reduced_logging and 'onboard_payloads' in event and clean(event.get('onboard_payloads')):
            try:
                onboard = json.loads(clean(event['onboard_payloads']))
                if isinstance(onboard, list):
                    loaded = any(split_payload_names(item.get('payload', '') if isinstance(item, dict) else item)
                                 for item in onboard)
            except ValueError:
                pass
        if not reduced_logging and loaded is None and ctx.cols.get('payload') and clean(event.get(ctx.cols['payload'])):
            loaded = bool(split_payload_names(event[ctx.cols['payload']]))
        if not wait and kind != 'charge' and (loaded or kind in {'pickup', 'dropoff'}):
            productive[amr].append((a, b))
        if loaded is None and kind in {'corridor', 'local_manoeuvre', 'lift_transfer'}:
            unknown_productive_s += b - a
        # Lift repositioning moves the lift without the AMR; exclude its distance.
        if kind in {'corridor', 'local_manoeuvre', 'lift_transfer'}:
            partial_distance |= fraction < 1
            travelled = (number(event.get('_distance_m')) or 0.) * fraction
            distance += travelled
            if loaded is False:
                empty_distance += travelled
            elif loaded is None:
                unknown_distance += travelled
            ids = clean(event.get(ctx.cols['task'])).split(',')
            real_ids = [i.strip() for i in ids if i.strip() in completed_ids]
            for task_id in real_ids:
                route_distances[task_id] += travelled / len(real_ids)
        # Only explicitly attributed congestion is defensible; reservation waits
        # are already counted above and should not be added a second time.
        explicit_congestion = number(info.get('congestion_delay_sec'))
        pedestrian_delay = number(event.get('people_delay_sec'))
        has_congestion |= explicit_congestion is not None or pedestrian_delay is not None
        congestion += (explicit_congestion or 0.) * fraction
        congestion += (pedestrian_delay or 0.) * fraction

    busy = {amr: union(intervals) for amr, intervals in busy.items()}
    busy_intervals = [i for intervals in busy.values() for i in intervals]
    busy_s = sum(total(i) for i in busy.values())
    productive_s = sum(total(i) for i in productive.values())
    charge_s = sum(total(i) for i in charging.values())
    vehicle_s = fleet * horizon
    busy_peak = peak(busy_intervals)
    occupied = {amr: union(busy.get(amr, []) + physical_activity.get(amr, []))
                for amr in set(busy) | set(physical_activity)}
    occupied_peak = peak([i for intervals in occupied.values() for i in intervals])
    spare_s = max(0., vehicle_s - sum(total(i) for i in occupied.values()))
    required = max(occupied_peak, math.ceil(sum(total(i) for i in occupied.values()) /
                   (horizon * max(.01, target_util)))) if horizon else None
    reserve = number(assumptions.get('vehicle_reserve_percent', 0)) or 0.
    required = math.ceil(required * (1 + reserve / 100)) if required is not None else None

    def add(group, metric, value, unit, explanation, status='Calculated'):
        rows.append(dict(group=group, metric=metric, value=value, unit=unit,
                         status=status if value is not None else 'Unavailable', basis=explanation))

    def ratio(numerator, denominator, factor=100.):
        return numerator / denominator * factor if denominator else None

    hourly_rows = []
    origin = math.floor(first / 3600) * 3600
    for start in range(int(origin), int(math.ceil(last / 3600) * 3600), 3600):
        finish = min(last, start + 3600)
        span = finish - max(first, start)
        if span <= 0:
            continue
        cohort = requests[(requests.release_s >= start) & (requests.release_s < finish)]
        # Include events exactly at the observed end in the final bucket.
        if finish == last:
            cohort = requests[(requests.release_s >= start) & (requests.release_s <= finish)]
        hour_busy = sum(total([(max(a, start), min(b, finish)) for a, b in intervals]) for intervals in busy.values())
        hourly_rows.append(dict(hour=pd.Timestamp(start, unit='s').strftime('%d/%m/%Y %H:%M') if ctx.has_datetime
                               else f'{start / 3600:g}-{(start + 3600) / 3600:g} h',
            observed_minutes=span/60, requests=len(cohort), tasks_per_hour=len(cohort)/span*3600,
            fleet_utilisation_pct=ratio(hour_busy, fleet*span)))
    hourly = pd.DataFrame(hourly_rows, columns=['hour', 'observed_minutes', 'requests', 'tasks_per_hour', 'fleet_utilisation_pct'])
    add('Demand', 'Task requests per hour', ratio(len(requests), horizon, 3600), 'tasks/h',
        'All service requests including collections and payload returns; hourly counts and partial-hour exposure below.')
    add('Demand', 'Peak concurrent demand', peak([(max(first, r['release_s']),
        math.nextafter(last, math.inf) if r['outcome'] == 'incomplete' else r['terminal_s']) for r in request_rows]), 'tasks',
        'Maximum outstanding requests from release to completion/failure, including unassigned and unfinished requests.')
    add('Demand', 'Demand by logistics stream', len(requests), 'tasks', 'Five requested streams plus unclassified requests; see stream breakdown.')
    add('Service', 'Request to delivery time', done.delivery_time_s.mean() if done.delivery_time_s.notna().any() else None, 's',
        'Mean release to payload task completion. First assignment is used only where release evidence is absent; see task export.')
    add('Service', '95th percentile delivery time', done.delivery_time_s.quantile(.95) if done.delivery_time_s.notna().any() else None, 's',
        'Linear-interpolated 95th percentile of completed request-to-delivery durations, also reported by stream.')
    eligible = requests[requests.target_s.notna() & (requests.target_s > 0)]
    assessed = eligible[eligible.outcome.isin(['completed', 'failed']) | eligible.overdue]
    compliant = assessed[assessed.outcome.eq('completed') & ~assessed.overdue]
    add('Service', 'Service level compliance', ratio(len(compliant), len(assessed)), '%',
        'Completed on time / SLA-assessed tasks. Failed and overdue unfinished tasks count as misses; unfinished tasks still within deadline are excluded.')
    overdue = requests[requests.overdue.eq(True)]
    add('Service', 'Overdue tasks', len(overdue) if len(eligible) else None, 'tasks',
        f'{ratio(len(overdue), len(eligible)) or 0:.1f}% of {len(eligible)} requests with a recorded deadline. Includes late completions and unresolved overdue work; reasons below.')
    add('Capacity', 'Fleet utilisation', ratio(busy_s, vehicle_s), '%',
        fleet_basis + '; assignment to completion/failure/end, merged per vehicle. Includes active-task travel, handling and waiting; charging excluded.')
    add('Capacity', 'Peak utilisation', ratio(busy_peak, fleet), '%', f'Maximum instantaneous task-active fleet: {busy_peak} vehicles. Hourly utilisation below.')
    add('Capacity', 'Spare capacity and headroom', max(0., fleet-occupied_peak) if fleet else None, 'vehicles',
        f'{spare_s/3600:.2f} residual vehicle-hours after tasks, charging and empty repositioning. Peak headroom is fleet minus peak occupied vehicles; cleaning, faults and unlogged downtime are not modelled.', 'Estimate')
    add('Efficiency', 'Productive utilisation', ratio(productive_s, vehicle_s) if not segments.empty and unknown_productive_s == 0 else None, '%',
        'Loaded movement plus pickup/dropoff segment time / configured vehicle time. Waiting, charging and empty movement excluded; segment plans clipped to observation end.', 'Recorded segment estimate')
    add('Efficiency', 'Empty running percentage', ratio(empty_distance, distance) if unknown_distance == 0 else None, '%',
        f'Unique physical movement distance with no onboard payload / all movement distance. {unknown_distance:.1f} m lacks load-state evidence; empty containers count as payloads.',
        'Partial-segment estimate' if partial_distance else 'Calculated')
    add('Efficiency', 'Distance per delivery', ratio(distance, completed_count, 1) if ctx.cols.get('distance') else None, 'm/task',
        'All unique AMR movement distance, including empty/recharge trips, divided by completed service tasks. Shared route distance allocated equally; partial segments prorated by elapsed time.',
        'Partial-segment estimate' if partial_distance else 'Calculated')
    add('Efficiency', 'Deliveries per hour', ratio(completed_count, busy_s, 3600), 'tasks/active vehicle-h',
        'Completed deliveries/collections divided by merged task-active vehicle hours; shared journeys counted once.')
    queues = pd.DataFrame(queue_rows, columns=['location', 'cause', 'resource', 'wait_s'])
    add('Bottleneck', 'Queue time', queues.wait_s.sum() if not queues.empty else 0., 's',
        'Sum of release-to-assignment dispatch waits and explicit vehicle wait segments; location/cause breakdown below.')
    add('Bottleneck', 'Lift waiting time', lift_wait if not segments.empty else None, 's',
        'AMR wait segments attributed to a lift, including time waiting while the lift repositions to collect the AMR.')
    add('Bottleneck', 'Congestion delay', congestion if has_congestion else None, 's',
        'Explicit congestion_delay_sec plus pedestrian delay on unique AMR segments. Other corridor, door and reservation delays need a free-flow baseline.', 'Partial evidence')
    add('Bottleneck', 'Charger wait time', charger_wait if has_charger_wait else None, 's',
        'Elapsed finite charger-bay contention, including waits open at the observation end. Legacy charge_wait state changes lack queue-exit timestamps, so their duration is unavailable.')
    reliability = assumptions.get('reliability', {}) or {}
    planned = number(reliability.get('planned_vehicle_hours'))
    unavailable = number(reliability.get('unavailable_vehicle_hours'))
    fms_planned = number(reliability.get('planned_fms_hours'))
    fms_unavailable = number(reliability.get('unavailable_fms_hours'))
    availability = (ratio(planned-unavailable, planned)
                    if planned and unavailable is not None and unavailable <= planned else None)
    fms_availability = (ratio(fms_planned-fms_unavailable, fms_planned)
                        if fms_planned and fms_unavailable is not None and fms_unavailable <= fms_planned else None)
    add('Reliability', 'Availability', availability, '%',
        'Supplied ready vehicle-hours / planned vehicle-hours. Unavailable vehicle-hours must include fleet-management-system outages, counting overlapping downtime once. '
        + (f'Separate system readiness: {fms_availability:.2f}%.' if fms_availability is not None else 'Separate system readiness unavailable.'), 'Supplied period inputs')
    add('Reliability', 'Failed task percentage', ratio(int(requests.outcome.eq('failed').sum()), len(requests)), '%',
        'Failed, cancelled, abandoned or staff-completed exception tasks / all raised requests. Unfinished work is reported separately.')
    failures = number(reliability.get('failure_count'))
    operating = number(reliability.get('operating_hours'))
    add('Reliability', 'Mean time between failures', ratio(operating, failures, 1) if operating is not None else None, 'h',
        'Supplied operating hours / service-affecting fault count. Task failures are not equipment faults; zero faults gives no finite MTBF.', 'Supplied period inputs')
    repairs = [number(v) for v in reliability.get('repair_durations_hours', [])]
    add('Reliability', 'Mean time to repair', sum(repairs)/len(repairs) if repairs and all(v is not None for v in repairs) else None, 'h',
        'Mean supplied reported-fault-to-service-restoration duration. Open repairs must be reviewed separately.', 'Supplied period inputs')
    staff_busy = None
    if staff_summary is not None and not staff_summary.empty and staff_summary.recorded_busy_time_s.notna().all():
        staff_busy = staff_summary.recorded_busy_time_s.sum()/3600
    support = number(assumptions.get('additional_staff_hours'))
    supplied_staff_total = number(assumptions.get('total_staff_hours'))
    staff_total = (supplied_staff_total if supplied_staff_total is not None else
                   staff_busy + (support or 0.) if staff_busy is not None else None)
    complete_staff_hours = supplied_staff_total is not None or (support is not None and staff_busy is not None)
    add('Resources', 'Staff hours required', staff_total, 'person-h',
        'Supplied total staff hours, or recorded handling plus additional loading, unloading, monitoring, support, exception and fault hours. Handling-only records omit unlogged support.',
        'Supplied period inputs' if supplied_staff_total is not None else 'Supplied + recorded' if support is not None else 'Handling only')
    add('Resources', 'Vehicles required', required, 'vehicles',
        f'Maximum of occupied peak and task, charging and repositioning workload at {target_util:.0%} utilisation, with {reserve:g}% supplied reserve for cleaning, servicing and faults. '
        + ('Unserved backlog needs a further sizing run.' if requests.outcome.eq('incomplete').any() else 'Rerun the candidate fleet to confirm service levels.'),
        'Lower-bound estimate' if requests.outcome.eq('incomplete').any() else 'Planning estimate')
    all_charges = [i for intervals in charging.values() for i in union(intervals)]
    charger_peak = peak(all_charges)
    charger_required = max(charger_peak, math.ceil(charge_s/(horizon*max(.01, target_util)))) + 1 if all_charges and horizon else None
    add('Resources', 'Charging infrastructure required', charger_required, 'chargers',
        'Observed charging peak/workload plus one spare charger; configured locations, bays and vehicle charge rates below. Zero recorded charging cannot establish required infrastructure.', 'Planning estimate')
    costs = assumptions.get('costs', {}) or {}
    currency = clean(costs.get('currency')) or 'currency units'
    labour = number(costs.get('labour_cost'))
    if labour is None and complete_staff_hours and staff_total is not None and number(costs.get('staff_hourly_rate')) is not None:
        labour = staff_total * number(costs['staff_hourly_rate'])
    operating_cost = number(costs.get('total_operating_cost'))
    if operating_cost is None:
        components = [labour] + [number(costs.get(k)) for k in ('energy_cost', 'maintenance_cost', 'software_cost', 'support_cost')]
        operating_cost = sum(components) if all(v is not None for v in components) else None
    add('Cost/sustainability', 'Cost per delivery', ratio(operating_cost, completed_count, 1) if operating_cost is not None else None,
        currency+'/task', 'Supplied total operating cost, or sum of all five supplied cost components, for this observation period / completed tasks.', 'Supplied period inputs')
    add('Cost/sustainability', 'Labour cost per delivery', ratio(labour, completed_count, 1) if labour is not None else None,
        currency+'/task', 'Supplied labour cost, or complete staff hours times supplied hourly rate, divided by completed tasks.', 'Supplied period inputs')
    energy = (energy_evidence or {}).get('total_kwh')
    add('Cost/sustainability', 'Energy per delivery', ratio(energy, completed_count, 1) if energy is not None else None, 'kWh/task',
        'Fully attributed planned AMR traction + lift supply / completed tasks. Excludes stationary auxiliaries and charger losses; not metered electricity.', 'Model energy estimate')

    stream_rows = []
    for stream in STREAMS + (['Unclassified'] if requests.stream.eq('Unclassified').any() else []):
        group = requests[requests.stream.eq(stream)]
        delivered = group[group.outcome.eq('completed')]
        e = group[group.target_s.notna() & (group.target_s > 0)]
        a = e[e.outcome.isin(['completed', 'failed']) | e.overdue]
        stream_rows.append(dict(stream=stream, requests=len(group), completed=len(delivered),
            mean_delivery_s=delivered.delivery_time_s.mean(), p95_delivery_s=delivered.delivery_time_s.quantile(.95),
            sla_assessed=len(a), compliance_pct=ratio(int((a.outcome.eq('completed') & ~a.overdue).sum()), len(a)),
            overdue=int(e.overdue.sum()), overdue_pct=ratio(int(e.overdue.sum()), len(e))))
    routes = done.copy()
    routes['allocated_distance_m'] = routes.task_id.map(route_distances).fillna(0.)
    route_summary = routes.groupby(['stream', 'origin', 'destination'], dropna=False).agg(
        completed=('task_id', 'count'), allocated_distance_m=('allocated_distance_m', 'sum')).reset_index()
    route_summary['distance_per_delivery_m'] = route_summary.allocated_distance_m / route_summary.completed
    queue_summary = queues.groupby(['location', 'cause'], dropna=False).agg(
        waits=('wait_s', 'count'), total_wait_s=('wait_s', 'sum'), mean_wait_s=('wait_s', 'mean'), max_wait_s=('wait_s', 'max')).reset_index()
    charger_rows = []
    from amr_inventory_inputs import inventory_space_is_amr
    for name in sorted(set(config.get('building', {}).get('charge_locations', [])) | set(charge_locations)):
        spaces = catalog.get(name, {}).get('inventory_spaces')
        count = sum(bool(s.get('has_charger')) and inventory_space_is_amr(s)
                    for s in spaces if isinstance(s, dict)) if isinstance(spaces, list) else None
        intervals = charge_locations[name]
        charger_rows.append(dict(location=name, configured_chargers=count,
            peak_charging=peak(intervals), charging_hours=sum(b-a for a,b in intervals)/3600,
            recommended_with_spare=peak(intervals)+1 if intervals else None,
            charger_type='Charger-equipped AMR bay' if count else 'Type/capacity not specified'))
    return dict(kpi_summary=pd.DataFrame(rows), kpi_hourly=hourly,
        kpi_streams=pd.DataFrame(stream_rows), kpi_requests=requests,
        kpi_overdue=overdue, kpi_queues=queue_summary, kpi_routes=route_summary,
        kpi_chargers=pd.DataFrame(charger_rows, columns=['location', 'configured_chargers', 'peak_charging',
            'charging_hours', 'recommended_with_spare', 'charger_type']),
        kpi_observation=dict(start=first, finish=last, horizon_s=horizon, fleet=fleet,
            completed=completed_count, request_time_fallbacks=int(requests.request_time_basis.str.contains('request time unavailable', regex=False).sum()),
            charge_rates_kw=[r.get('battery_charge_rate_kw') for r in config.get('amrs', [])]))
