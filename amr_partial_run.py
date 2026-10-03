"""Executed-prefix evidence for a stopped run, separate from committed plans.

The caller supplies the bound full event rows and frozen inputs. Recorded segment
status and battery/accounting snapshots are not proof of elapsed execution.
Geometric progress follows saved profiles; charging credits remain separately
labelled accounting evidence, never inferred physical charging progress.
"""
import hashlib
import json
import math
from datetime import datetime

from amr_simulation_inputs import DEFAULTS
from amr_trajectories import trajectory_from_dict


class PartialRunError(ValueError):
    reason = 'invalid_evidence'


def _number(value, label, *, nonnegative=True):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise PartialRunError(f'{label} must be finite numeric evidence.') from None
    if isinstance(value, bool) or not math.isfinite(result) or (nonnegative and result < 0):
        raise PartialRunError(f'{label} must be finite {"nonnegative " if nonnegative else ""}numeric evidence.')
    return result


def _present(value):
    return value is not None and value != ''


def _seconds(value, origin, label):
    if isinstance(value, str):
        try:
            return _number(value, label)
        except PartialRunError:
            try:
                result = (datetime.fromisoformat(value) - origin).total_seconds()
            except (TypeError, ValueError, OverflowError):
                raise PartialRunError(f'{label} is not a valid simulation time.') from None
            return _number(result, label)
    return _number(value, label)


def _details(row):
    value = row.get('details')
    if not _present(value):
        return {}
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
    except (ValueError, TypeError):
        # Human-readable details are valid but do not prove numeric energy.
        return {}
    return result if isinstance(result, dict) else {}


def _tasks(row):
    values = {s.strip() for s in str(row.get('task_id') or '').split(',') if s.strip()}
    extra = row.get('multi_stop_task_ids')
    if _present(extra):
        try:
            extra = json.loads(extra) if isinstance(extra, str) else extra
        except (ValueError, TypeError):
            raise PartialRunError('Malformed multi-stop task identifiers.') from None
        if not isinstance(extra, list) or any(not isinstance(v, str) or not v for v in extra):
            raise PartialRunError('Multi-stop task identifiers must be a list of strings.')
        values.update(extra)
    return sorted(values)


def _pose(pose):
    return {'x': pose.x, 'y': pose.y, 'heading_rad': pose.heading}


def _static_pose(row):
    fields = ('start_x', 'start_y', 'amr_rotation_start_deg')
    if not all(_present(row.get(key)) for key in fields):
        return None
    x, y, heading = (_number(row[key], key, nonnegative=False) for key in fields)
    for key, actual in (('end_x', x), ('end_y', y)):
        if _present(row.get(key)) and not math.isclose(_number(row[key], key, nonnegative=False), actual, rel_tol=0, abs_tol=1e-8):
            raise PartialRunError('A stationary segment changes position without trajectory evidence.')
    if _present(row.get('amr_rotation_end_deg')):
        end = _number(row['amr_rotation_end_deg'], 'end heading', nonnegative=False)
        if abs(math.remainder(math.radians(end - heading), 2 * math.pi)) > 1e-8:
            raise PartialRunError('A stationary segment rotates without trajectory evidence.')
    return {'x': x, 'y': y, 'heading_rad': math.radians(heading)}


def _elapsed_geometry(path, elapsed):
    distance, rotation, remaining = 0., 0., elapsed
    for motion in path.motions:
        fraction = motion.fraction_at_time(min(remaining, motion.duration_sec))
        distance += motion.length_m * fraction
        rotation += abs(motion.sweep_rad) * fraction
        remaining -= min(remaining, motion.duration_sec)
        if remaining <= 0:
            break
    return distance, rotation, _pose(path.pose_at_time(elapsed))


def _energy(row, detail, source):
    """Exact attributed segment/accounting energy, or missing, never a guess."""
    if detail.get('energy_source') != source or not _present(detail.get('energy_kwh')):
        return None
    exact = _number(detail['energy_kwh'], 'Attributed energy')
    if _present(row.get('energy_kwh')):
        recorded = _number(row['energy_kwh'], 'Recorded energy')
        if not math.isclose(exact, recorded, rel_tol=1e-9, abs_tol=1e-12):
            raise PartialRunError('Energy column disagrees with attributed segment evidence.')
    return exact


def derive_partial_run(rows, frozen_inputs, *, stop_time):
    """Project full recorded plans onto an explicit nonnegative stop time.

    Start/end CSV timestamps have millisecond precision. Exact trajectory and
    detail durations supersede rounded duration columns, with agreement checked
    within 1.1ms. An exact start_time_sec field, if present, takes precedence.
    Elapsed model traction scales with time, as the simulator's constant-power
    model requires; acceleration changes distance progress, not this power model.
    """
    cutoff = _number(stop_time, 'stop_time')
    if not isinstance(rows, (list, tuple)) or not isinstance(frozen_inputs, dict):
        raise PartialRunError('Provide full event rows and a frozen configuration object.')
    try:
        encoded = json.dumps(frozen_inputs, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        origin = datetime.fromisoformat(frozen_inputs.get('simulation', {}).get('start_datetime', DEFAULTS['start_datetime']))
    except (TypeError, ValueError, OverflowError):
        raise PartialRunError('Frozen inputs or simulation origin are malformed.') from None
    known_robots = set()
    for robot in frozen_inputs.get('amrs', []):
        try:
            quantity = _number(robot.get('quantity', 1), 'Frozen robot quantity')
            if quantity != int(quantity) or not isinstance(robot['id'], str):
                raise ValueError
            known_robots.update(f"{robot['id']}-{i+1}" for i in range(int(quantity)))
        except (TypeError, KeyError, AttributeError, ValueError):
            raise PartialRunError('Frozen robot identities/quantities are malformed.') from None
    activities, charges, seen, tasks, findings = [], [], {}, {}, []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PartialRunError(f'Row {index+1} is not an object.')
        native = row.get('event_id')
        if _present(native) and not isinstance(native, str):
            raise PartialRunError('Event identifiers must be strings.')
        identity = native or f'legacy-row:{index+1}'
        if identity in seen:
            if seen[identity] != row:
                raise PartialRunError(f'Conflicting records share event identifier {identity}.')
            continue
        seen[identity] = row
        kind = str(row.get('event_type') or '').removeprefix('multi_stop_')
        if kind == 'task_released':
            kind = 'task_release'
        is_segment = kind.startswith('segment_')
        if not is_segment and kind not in ('task_release', 'task_assigned', 'task_complete', 'task_failed',
                                           'battery_charge_applied'):
            continue
        detail = _details(row)
        ids = _tasks(row)
        event_value = row.get('sim_time_sec')
        if not _present(event_value):
            event_value = row.get('start_time_sec', row.get('start_time'))
        event_time = _seconds(event_value, origin, f'{identity} event time')
        robot = row.get('amr_id') or ''
        if robot and robot not in known_robots:
            raise PartialRunError(f'{identity}: robot {robot!r} is absent from frozen inputs.')
        for task_id in ids:
            task = tasks.setdefault(task_id, {'task_id': task_id, 'outcome': 'not_established',
                'release_time_sec': None, 'assignment_time_sec': None,
                'completion_time_sec': None, 'failure_time_sec': None,
                'actual_event_ids': [], 'future_event_ids': [], 'activity_event_ids': []})
            if is_segment:
                task['activity_event_ids'].append(identity)
            elif kind.startswith('task_'):
                if event_time > cutoff:
                    task['future_event_ids'].append(identity)
                else:
                    task['actual_event_ids'].append(identity)
                    field = {'task_release': 'release_time_sec', 'task_assigned': 'assignment_time_sec',
                             'task_complete': 'completion_time_sec', 'task_failed': 'failure_time_sec'}[kind]
                    previous = task[field]
                    task[field] = event_time if previous is None else min(previous, event_time)
        if kind == 'battery_charge_applied':
            amount = _energy(row, detail, 'battery_charge_input')
            charges.append({'event_id': identity, 'amr_id': robot, 'time_sec': event_time,
                'state': 'recorded' if event_time <= cutoff else 'future', 'accounting_credit_kwh': amount,
                'basis': detail.get('basis'), 'physical_charge_energy_kwh': None})
            continue
        if not is_segment:
            continue
        segment = row.get('segment_type') or kind.removeprefix('segment_')
        start_value = row.get('start_time_sec')
        if not _present(start_value):
            start_value = row.get('start_time') if _present(row.get('start_time')) else event_time
        start = _seconds(start_value, origin, f'{identity} start')
        if abs(start - event_time) > .0011:
            raise PartialRunError(f'{identity}: segment event time disagrees with its start.')
        path = None
        geometric = row.get('motion_model') == 'geometric_v1' or _present(row.get('trajectory_json'))
        if geometric:
            if _present(row.get('motion_model')) and row['motion_model'] != 'geometric_v1':
                raise PartialRunError(f'{identity}: unsupported geometric motion model.')
            try:
                raw = row.get('trajectory_json')
                data = json.loads(raw) if isinstance(raw, str) else raw
                path = trajectory_from_dict(data)
            except (TypeError, ValueError, OverflowError) as exc:
                raise PartialRunError(f'{identity}: malformed trajectory: {exc}') from None
            duration = path.duration_sec
            if segment != 'corridor':
                raise PartialRunError(f'{identity}: geometric trajectory is attached to unsupported segment {segment!r}.')
        else:
            value = detail.get('duration') if _present(detail.get('duration')) else row.get('duration_sec')
            duration = _number(value, f'{identity} duration')
        end = start + duration
        if not math.isfinite(end):
            raise PartialRunError(f'{identity}: segment end overflowed.')
        if _present(row.get('duration_sec')) and abs(_number(row['duration_sec'], 'duration_sec') - duration) > .0011:
            raise PartialRunError(f'{identity}: duration column disagrees with exact evidence.')
        end_value = row.get('end_time_sec') if _present(row.get('end_time_sec')) else row.get('end_time')
        if _present(end_value) and abs(_seconds(end_value, origin, 'end_time') - end) > .0011:
            raise PartialRunError(f'{identity}: end time disagrees with exact duration.')
        elapsed = max(0., min(duration, cutoff - start))
        state = 'executed' if end <= cutoff else 'partial' if start < cutoff else 'planned'
        record = {'event_id': identity, 'identity': 'native' if native else 'legacy_row',
            'journey_id': row.get('journey_id') or '', 'amr_id': robot, 'task_ids': ids,
            'segment_type': segment, 'state': state,
            'planned_start_time_sec': start, 'planned_end_time_sec': end,
            'executed_start_time_sec': start if state != 'planned' else None,
            'executed_end_time_sec': start + elapsed if state != 'planned' else None,
            'elapsed_duration_sec': elapsed, 'planned_duration_sec': duration,
            'elapsed_distance_m': None, 'elapsed_rotation_rad': None, 'pose_at_cutoff': None,
            'planned_start_pose': None, 'planned_end_pose': None,
            'planned_model_energy_kwh': None, 'elapsed_model_energy_kwh': None,
            'energy_basis': None, 'missing_evidence': [],
            'handling_state': ('completed' if state == 'executed' else 'interrupted' if state == 'partial' else 'planned')
                              if segment in ('pickup', 'dropoff') else None}
        if path is not None:
            distance, rotation, pose = _elapsed_geometry(path, elapsed)
            record.update(elapsed_distance_m=distance, elapsed_rotation_rad=rotation,
                          pose_at_cutoff=pose if state != 'planned' else None,
                          planned_distance_m=path.length_m,
                          planned_start_pose=_pose(path.motions[0].start),
                          planned_end_pose=_pose(path.motions[-1].end))
            energy = _energy(row, detail, 'amr_battery')
            record['planned_model_energy_kwh'] = energy
            if energy is None:
                record['missing_evidence'].append('Attributed geometric traction energy is missing.')
            else:
                record['elapsed_model_energy_kwh'] = energy * (elapsed / duration)
                record['energy_basis'] = 'elapsed_constant_power_model; not committed battery snapshot'
        elif segment in ('pickup', 'dropoff', 'charge', 'wash', 'wash_cycle', 'wait') or str(segment).startswith('wait_'):
            pose = _static_pose(row)
            record.update(elapsed_distance_m=0., elapsed_rotation_rad=0., planned_distance_m=0.,
                          pose_at_cutoff=pose if state != 'planned' else None,
                          planned_start_pose=pose, planned_end_pose=pose)
            if pose is None:
                record['missing_evidence'].append('Stationary pose/heading evidence is missing.')
            record['missing_evidence'].append('Elapsed charging energy is not established by a plan or accounting credit.'
                                              if segment == 'charge' else 'Stationary auxiliary energy is not modelled.')
        else:
            record['planned_distance_m'] = None
            record['missing_evidence'].append('No supported geometric trajectory; movement is not reconstructed.')
        activities.append(record)
    for task in tasks.values():
        if task['completion_time_sec'] is not None and task['failure_time_sec'] is not None:
            raise PartialRunError(f"Task {task['task_id']} has conflicting actual completion/failure evidence.")
        task['outcome'] = ('completed' if task['completion_time_sec'] is not None else
                           'failed' if task['failure_time_sec'] is not None else
                           'assigned_unfinished' if task['assignment_time_sec'] is not None else
                           'released_unfinished' if task['release_time_sec'] is not None else 'not_established')
    activities.sort(key=lambda item: (item['planned_start_time_sec'], item['event_id']))
    result = {'schema_version': 1, 'stop_time_sec': cutoff,
        'frozen_inputs_sha256': hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
        'time_resolution_sec': .001, 'activities': activities,
        'task_outcomes': [tasks[key] for key in sorted(tasks)], 'applied_charge_records': charges,
        'findings': findings + ['Elapsed activity is reconstructed from saved plans up to the explicit stop time.',
                               'Committed battery/stock counters are not reconstructed as elapsed physical state.']}
    try:
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        raise PartialRunError('Derived evidence contains a nonfinite or non-JSON value.') from None
    return result
