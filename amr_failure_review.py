"""Read, explain and compare task outcomes from compact run evidence."""
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
import re

from amr_event_store import EventStore, iter_events
from amr_failure_evidence import CAPABILITY, blocker_from_reason
from amr_memory_runs import MemoryRun
from amr_project_runs import read_json
from amr_results_investigation import ASSIGNED, COMPLETED, MAX_LOG_BYTES, number, resolve_log, task_ids
from amr_run_evidence import config_hash, file_hash
from amr_run_review import verified_events


TERMINAL = COMPLETED | {'task_failed', 'task_pending_at_stop'}
DIAGNOSTIC = {'task_dispatch_committed', 'task_blocker_changed', 'task_failure_snapshot',
              'task_pending_snapshot', 'waste_spare_queued', 'waste_spare_prioritised'}
INDEX_KINDS = TERMINAL | ASSIGNED | DIAGNOSTIC | {'task_released', 'task_generated', 'stress_task_obligation',
    'waste_replacement_staged', 'location_payload_exit', 'location_payload_enter', 'task_geometry_unresolved'}
FIELDS = ('event_id', 'event_type', 'task_id', 'multi_stop_task_ids', 'precise_time_sec', 'sim_time_sec',
          'sim_datetime', 'task_release_time_sec', 'task_source', 'department_id', 'waste_stream',
          'from_location', 'to_location', 'payload', 'payload_instance_id', 'journey_id', 'lift_id', 'amr_id',
          'duration_sec', 'wait_time_sec', 'details', 'pending_reason', 'source_rule_path', 'route_profile',
          'inventory_space', 'status')
TIMINGS = ('Waiting for dispatch', 'Booked AMR not started', 'Lift wait', 'Travel and handling',
           'Waiting for bin or bay', 'Unknown')


def _cancelled(cancel):
    if cancel and cancel():
        raise InterruptedError('Investigation cancelled')


def _details(row):
    try:
        data = json.loads(row.get('details') or '{}')
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _time(row):
    precise = number(row.get('precise_time_sec'))
    return precise if precise is not None else number(row.get('sim_time_sec'))


def _file_stamp(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


class FailureReview:
    def __init__(self, source):
        self.source = source
        if isinstance(source, MemoryRun):
            self.metadata = source.require_reviewable()
            self.name = source.name
            self.storage = 'In memory'
            self.path = None
        else:
            path = Path(source).resolve()
            folder = path if path.is_dir() else path.parent
            manifest_path = folder / 'run_manifest.json'
            manifest = read_json(manifest_path) if manifest_path.is_file() else {}
            canonical_name = manifest.get('canonical_events', 'simulation_steps.csv')
            if manifest.get('project_binding') and (path.is_dir() or path.name == canonical_name):
                manifest, _, self.path, expected = verified_events(folder, allow_partial=True)
                self.metadata = read_json(str(self.path) + '.run.json')
                if self.metadata.get('log_sha256') != expected:
                    raise ValueError('Run evidence changed during verification.')
            else:
                self.path = resolve_log(path)
                sidecar = Path(str(self.path) + '.run.json')
                data = read_json(sidecar) if sidecar.is_file() else {}
                self.metadata = data if (data.get('log_sha256') == file_hash(self.path)
                    and data.get('config_sha256') == config_hash(data.get('frozen_inputs'))) else {}
            self.stamp = _file_stamp(self.path)
            if self.path.suffix != '.sqlite' and self.stamp[0] > MAX_LOG_BYTES:
                raise ValueError('This CSV exceeds the investigation limit. Open its compact run folder.')
            self.name = manifest.get('name') or path.name
            self.storage = 'Saved'
        self.frozen = self.metadata.get('frozen_inputs') or {}
        self.complete = (self.metadata.get('run_status') == 'finished' and self.metadata.get('logging_enabled')
                         and not self.metadata.get('reduced_logging') and self.metadata.get('log_kind') == 'full')
        self.structured = CAPABILITY in self.metadata.get('event_capabilities', ())
        self.tasks = {}
        self.failures = []
        self.index = defaultdict(list)
        self.payload_moves = defaultdict(list)
        self.pickups = defaultdict(list)
        self.reconciliation = []
        self.filter_resources = {}

    @contextmanager
    def rows(self, kinds=None, *, cancel=None, time_range=None):
        _cancelled(cancel)
        if self.path is None:
            with self.source.using_store(cancel) as store:
                iterator = store.iter_rows(FIELDS, event_types=kinds, time_range=time_range)
                try:
                    yield iterator
                finally:
                    iterator.close()
            self.source.require_reviewable()
        else:
            if _file_stamp(self.path) != self.stamp:
                raise ValueError('The event log changed. Reopen the run to review it.')
            iterator = iter_events(self.path, FIELDS, event_types=kinds, time_range=time_range)
            try:
                yield iterator
            finally:
                iterator.close()
            if _file_stamp(self.path) != self.stamp:
                raise ValueError('The event log changed during investigation.')
        _cancelled(cancel)

    def build(self, cancel=None, progress=None):
        _cancelled(cancel)
        if progress:
            progress(dict(phase='Reading task outcomes and failure evidence'))
        captures = defaultdict(list)
        with self.rows(INDEX_KINDS, cancel=cancel) as rows:
            for index, row in enumerate(rows):
                if index % 512 == 0:
                    _cancelled(cancel)
                kind = row['event_type']
                if kind in ('location_payload_exit', 'location_payload_enter') and row.get('payload_instance_id'):
                    self.payload_moves[row['payload_instance_id']].append(row)
                if kind == 'location_payload_exit' and row.get('task_id'):
                    self.pickups[(row.get('from_location', ''), row.get('payload', ''))].append(row)
                if kind in INDEX_KINDS:
                    for task_id in task_ids(row):
                        captures[task_id].append(row)
        for task_id, rows in captures.items():
            _cancelled(cancel)
            task = _task(task_id, rows)
            if task is None:
                continue
            self.tasks[task_id] = task
            self.index[task_id] = rows
            if task['outcome'] in ('Failed', 'Pending at stop', 'Conflicting outcomes'):
                self.failures.append(task)
        self.failures.sort(key=lambda task: (task['end'] is None, task['end'] or 0, task['id']))
        self.reconciliation = self._reconcile()
        if self.failures:
            if progress:
                progress(dict(phase='Linking resources to failed tasks'))
            self._index_resources(cancel)
        return self

    def _reconcile(self):
        findings = []
        summary = self.metadata.get('summary') or {}
        for outcome, name in (('Failed', 'failed_task_ids'), ('Completed', 'completed_task_ids'),
                              ('Pending at stop', 'pending_task_ids')):
            expected = summary.get(name)
            if expected is not None and set(expected) != {key for key, task in self.tasks.items() if task['outcome'] == outcome}:
                findings.append(f'{outcome} event identities differ from the run summary.')
        return findings

    def _index_resources(self, cancel):
        watched = defaultdict(set)
        for task in self.failures:
            self.filter_resources[task['id']] = {'amr_id': set(), 'lift_id': set()}
            for task_id in self.related_ids(task):
                watched[task_id].add(task['id'])
        if not watched:
            return
        kinds = {'segment_wait', 'segment_lift_transfer', 'multi_stop_segment_wait',
                 'multi_stop_segment_lift_transfer', 'task_dispatch_committed', 'task_assigned',
                 'multi_stop_task_assigned', 'task_geometry_unresolved'}
        with self.rows(kinds, cancel=cancel) as rows:
            for index, row in enumerate(rows):
                if index % 512 == 0:
                    _cancelled(cancel)
                for key in task_ids(row):
                    for failure in watched.get(key, ()):
                        for field in ('amr_id', 'lift_id'):
                            if row.get(field):
                                self.filter_resources[failure][field].add(row[field])

    def related_ids(self, task):
        related = {task['id']: 'Selected task'}
        for row in self.index[task['id']]:
            if row['event_type'] not in DIAGNOSTIC:
                continue
            data = _details(row)
            for claim in data.get('stock', {}).get('reserved', ()):
                label = 'Collection holding the working bin' if data.get('swap_key') else 'Task holding pickup stock'
                _relate(related, claim.get('task_id'), label)
                self.follow_payload_exit(related, claim.get('payload_id'), task['location'], _time(row))
            for spare in data.get('spares', ()):
                _relate(related, spare.get('task_id'), 'Recorded spare trip')
                _relate(related, spare.get('claimed_by'), 'Collection holding the spare')
            for claim in data.get('bays', {}).get('holders', ()):
                _relate(related, claim.get('task_id'), 'Task holding a compatible bay')
                self.follow_payload_exit(related, claim.get('payload_id'), task['destination'], _time(row))
            _relate(related, data.get('spare_task_id'), 'Spare committed to this collection')
            _relate(related, data.get('follows_task_id'), 'Collection that triggered replenishment')
            _relate(related, data.get('collection_task_id'), 'Collection that requested priority')
        for key in list(related):
            for row in self.index.get(key, ()):
                if row['event_type'] != 'task_dispatch_committed':
                    continue
                for earlier in (_details(row).get('previous_work') or {}).get('tasks', ()):
                    _relate(related, earlier, 'Earlier AMR booking')
        if not self.structured and task['service'] == 'department_waste' and task['outcome'] == 'Failed':
            # Historical logs can show nearby spare arrivals, but cannot bind the
            # spare to a particular waiting collection or recover a past claim.
            candidate = [t for t in self.tasks.values() if t['service'] == 'waste_bin_replacement'
                         and t['destination'] == task['location'] and t['payload'] == task['payload']
                         and t['end'] is not None and task['release'] is not None and task['end'] is not None
                         and task['release'] <= t['end'] <= task['end'] + 10800]
            for spare in sorted(candidate, key=lambda t: t['end'])[:3]:
                _relate(related, spare['id'], 'Nearby spare trip · link unconfirmed')
            if task['end'] is not None and task['blocker'] == 'Pickup stock':
                later = [row for row in self.pickups[(task['location'], task['payload'])]
                         if _time(row) is not None and task['end'] <= _time(row) <= task['end'] + 10800]
                if later:
                    pickup = min(later, key=_time)
                    _relate(related, pickup['task_id'], 'Later pickup at the same room · link unconfirmed')
        return related

    def follow_payload_exit(self, related, payload_id, location, after):
        if after is None:
            return
        for event in sorted(self.payload_moves.get(payload_id, ()), key=lambda row: _time(row) or 0):
            if (event['event_type'] == 'location_payload_exit' and event.get('from_location') == location
                    and _time(event) is not None and _time(event) >= after):
                _relate(related, event.get('task_id'), 'Later pickup freed the payload position')
                return

    def detail(self, task_id, *, cancel=None):
        task = self.tasks[task_id]
        related = self.related_ids(task)
        linked_rows = [row for key in related for row in self.index.get(key, ())]
        times = [t for row in linked_rows if (t := _time(row)) is not None]
        selected_events = []
        with self.rows(cancel=cancel, time_range=(min(times), max(times)) if times else None) as rows:
            for index, row in enumerate(rows):
                if index % 512 == 0:
                    _cancelled(cancel)
                if related.keys().isdisjoint(task_ids(row)):
                    continue
                selected_events.append(row)
        selected_events.sort(key=lambda row: (_time(row) is None, _time(row) or 0, row.get('event_id', '')))
        periods = _breakdown(task, selected_events, related, self.structured)
        self.add_lift_bookings(selected_events, related, periods, cancel)
        return dict(task=task, related=related, rows=selected_events, periods=periods,
                    totals={name: sum(p['end'] - p['start'] for p in periods if p['category'] == name)
                            for name in TIMINGS})

    def add_lift_bookings(self, events, related, periods, cancel):
        windows = defaultdict(list)
        for period in periods:
            if period['category'] == 'Lift wait':
                for evidence in period['event_ids']:
                    windows[evidence].append(period)
        waits = defaultdict(list)
        for event in events:
            if event['event_type'].endswith('segment_wait') and event.get('lift_id'):
                waits[event['lift_id']].extend((period, event.get('amr_id', ''))
                                              for period in windows.get(event.get('event_id'), ()))
        waits = {lift: intervals for lift, intervals in waits.items() if intervals}
        if not waits:
            return
        end = max(period['end'] for intervals in waits.values() for period, _ in intervals)
        seen = {row.get('event_id') for row in events if row.get('event_id')}
        kinds = {'segment_lift_transfer', 'segment_lift_reposition', 'multi_stop_segment_lift_transfer',
                 'multi_stop_segment_lift_reposition'}
        with self.rows(kinds, cancel=cancel, time_range=(0, end)) as rows:
            for index, row in enumerate(rows):
                if index % 512 == 0:
                    _cancelled(cancel)
                start, duration = _time(row), number(row.get('duration_sec'))
                if start is None or not duration:
                    continue
                event_id = row.get('event_id')
                for period, amr in waits.get(row.get('lift_id'), ()):
                    if (amr != row.get('amr_id') and period['start'] < start + duration and start < period['end']):
                        if event_id not in seen:
                            events.append(row)
                            seen.add(event_id)
                            _relate(related, row.get('task_id'), 'Overlapping planned lift booking')
                        if event_id and event_id not in period['event_ids']:
                            period['event_ids'] += (event_id,)
        events.sort(key=lambda row: (_time(row) is None, _time(row) or 0, row.get('event_id', '')))


def _relate(related, task_id, label):
    if task_id:
        related.setdefault(task_id, label)


def _task(task_id, rows):
    ordered = sorted(rows, key=lambda row: (_time(row) is None, _time(row) or 0, row.get('event_id', '')))
    by_kind = defaultdict(list)
    for row in ordered:
        by_kind[row['event_type']].append(row)
    releases = by_kind['task_released']
    obligations = by_kind['stress_task_obligation']
    terminal = [row for row in ordered if row['event_type'] in TERMINAL]
    if not (releases or obligations or terminal or by_kind['task_dispatch_committed']):
        return None
    final = terminal[-1] if terminal else {}
    anchor = (releases or by_kind['task_generated'] or terminal or obligations or ordered)[0]
    seen = {row['event_type'] for row in terminal}
    if 'task_failed' in seen and seen & COMPLETED or final.get('event_type') == 'task_pending_at_stop' and seen & (COMPLETED | {'task_failed'}):
        outcome = 'Conflicting outcomes'
    else:
        outcome = {'task_failed': 'Failed', 'task_pending_at_stop': 'Pending at stop'}.get(final.get('event_type'),
                    'Completed' if terminal else 'Outcome unavailable')
    snapshots = by_kind['task_pending_snapshot' if outcome == 'Pending at stop' else 'task_failure_snapshot']
    snapshot = _details(snapshots[-1]) if snapshots else {}
    release = number(anchor.get('task_release_time_sec'))
    if release is None:
        release = number(snapshot.get('release'))
    if release is None and releases:
        release = _time(anchor)
    reason = final.get('pending_reason') or final.get('details') or ''
    commit = by_kind['task_dispatch_committed']
    dispatch = _details(commit[0]) if commit else {}
    deadline = snapshot.get('deadline', dispatch.get('deadline'))
    if deadline is None and release is not None:
        limit = re.search(r'Task deferral limit exceeded \(([0-9.]+) min\)', reason)
        minutes = number(limit.group(1)) if limit else None
        if minutes is not None:
            deadline = release + minutes * 60
    assigned = next((row for row in ordered if row['event_type'] in ASSIGNED), {})
    return dict(id=task_id, outcome=outcome, end=_time(final), release=release,
        original=number(_details(anchor).get('original')),
        quantity=_details(anchor).get('quantity', 1), rule=anchor.get('source_rule_path') or final.get('source_rule_path', ''),
        service=anchor.get('task_source') or final.get('task_source', ''),
        department=anchor.get('department_id') or final.get('department_id', ''),
        stream=anchor.get('waste_stream') or final.get('waste_stream', ''),
        location=final.get('from_location') or anchor.get('from_location', ''),
        destination=final.get('to_location') or anchor.get('to_location', ''),
        payload=anchor.get('payload') or final.get('payload', ''), reason=reason,
        blocker=snapshot.get('blocker') or blocker_from_reason(reason), deadline=deadline,
        dispatch=number(dispatch.get('committed')), planned_start=number(dispatch.get('start')) if commit else _time(assigned),
        snapshot=snapshot, released=bool(releases or obligations), end_id=final.get('event_id', ''))


def load_failure_review(source, *, cancel=None, progress=None):
    _cancelled(cancel)
    return FailureReview(source).build(cancel, progress)


def _breakdown(task, rows, related, structured):
    start, end = task['release'], task['end']
    if start is None or end is None or end <= start:
        return []
    dispatch, staging, state_changes, segments = {}, {}, [], defaultdict(list)
    boundaries = {start, end}
    for row in rows:
        timestamp = _time(row)
        if timestamp is None:
            continue
        kind, key = row['event_type'], row.get('task_id', '')
        if kind == 'task_dispatch_committed':
            data = _details(row)
            dispatch[key] = (timestamp, number(data.get('start')), row.get('event_id', ''))
            boundaries.update(value for value in dispatch[key][:2] if value is not None and start < value < end)
        elif kind == 'waste_replacement_staged':
            staging[key] = timestamp
            if start < timestamp < end:
                boundaries.add(timestamp)
        elif kind == 'task_blocker_changed' and key == task['id']:
            state_changes.append((timestamp, _details(row), row.get('event_id', '')))
            if start < timestamp < end:
                boundaries.add(timestamp)
        elif 'segment_' in kind:
            duration = number(row.get('duration_sec'))
            if duration is None or duration <= 0 or timestamp >= end or timestamp + duration <= start:
                continue
            if kind.endswith('segment_lift_reposition'):
                continue  # The AMR's waiting segment covers the empty lift move.
            category = ('Lift wait' if kind.endswith('segment_wait') and row.get('lift_id') else
                        'Unknown' if 'wait' in kind else 'Travel and handling')
            for member in task_ids(row):
                if member in related:
                    segments[member].append((timestamp, timestamp + duration, category, row.get('event_id', '')))
            boundaries.update((max(start, timestamp), min(end, timestamp + duration)))

    def classify_trip(key, point, base):
        booking = dispatch.get(key)
        if booking is None or point < booking[0]:
            return 'Waiting for dispatch', base
        evidence = base + (booking[2],)
        if booking[1] is not None and point < booking[1]:
            return 'Booked AMR not started', evidence
        matches = [(category, event) for a, b, category, event in segments[key] if a <= point < b]
        if matches:
            category, event = min(matches, key=lambda pair: (pair[0] != 'Lift wait', pair[0] == 'Unknown'))
            return category, evidence + (event,)
        return 'Unknown', evidence

    completed = []
    state_index = 0
    current_state = {}
    state_id = ''
    basis = (task['end_id'],)
    ordered = sorted(boundaries)
    for left, right in zip(ordered, ordered[1:]):
        while state_index < len(state_changes) and state_changes[state_index][0] <= left:
            _, current_state, state_id = state_changes[state_index]
            state_index += 1
        point = (left + right) / 2
        evidence = basis + (state_id,)
        if structured and task['id'] in dispatch and point >= dispatch[task['id']][0]:
            category, evidence = classify_trip(task['id'], point, evidence)
        elif current_state.get('blocker') == 'Spare bin':
            spares = [spare['task_id'] for spare in current_state.get('spares', ()) if not spare.get('claimed_by')]
            if len(spares) == 1 and point < staging.get(spares[0], float('inf')):
                category, evidence = classify_trip(spares[0], point, evidence)
            else:
                category = 'Waiting for bin or bay'
        elif current_state.get('blocker') in ('Pickup stock', 'Inventory bays', 'Return pickup'):
            category = 'Waiting for bin or bay'
        elif structured and (state_id or 'deferral limit' in task['reason'].casefold()):
            category = 'Waiting for dispatch'
        else:
            category = 'Unknown'
        ids = tuple(dict.fromkeys(eid for eid in evidence if eid))
        if completed and completed[-1]['category'] == category and completed[-1]['event_ids'] == ids:
            completed[-1]['end'] = right
        else:
            completed.append(dict(category=category, start=left, end=right, event_ids=ids))
    return completed


def _service_key(review, task):
    if task['service'] == 'waste_bin_replacement' or task['id'].startswith('IDLE-'):
        return None
    original = task['original'] if task['original'] is not None else task['release']
    try:
        origin = datetime.fromisoformat(review.frozen['simulation']['start_datetime'])
        timestamp = (origin + timedelta(seconds=original)).isoformat(timespec='milliseconds')
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    rule = task['rule']
    if rule.startswith('/tasks/'):
        rule = 'configured task ' + task['id']
    if not rule:
        return None
    return (rule, task['service'], task['department'], task['stream'], task['location'],
            task['destination'], task['payload'], str(task['quantity']), timestamp)


def compare_failure_reviews(before, after, *, cancel=None):
    left, right = defaultdict(list), defaultdict(list)
    unmatched = []
    for review, target, side in ((before, left, 'Before'), (after, right, 'After')):
        for task in review.tasks.values():
            _cancelled(cancel)
            key = _service_key(review, task)
            if key is not None:
                target[key].append(task)
            elif task['outcome'] in ('Failed', 'Pending at stop', 'Conflicting outcomes'):
                unmatched.append(dict(status='Request identity unavailable',
                                      before=[task] if side == 'Before' else [], after=[task] if side == 'After' else []))

    requests = []
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key, []), right.get(key, [])
        if len(a) != 1 or len(b) != 1:
            status = 'Ambiguous request' if len(a) > 1 or len(b) > 1 else 'Before only' if a else 'After only'
            unmatched.append(dict(status=status, before=a, after=b))
            continue
        if a[0]['outcome'] == b[0]['outcome'] == 'Completed':
            continue
        status = a[0]['outcome'] + ' → ' + b[0]['outcome']
        requests.append(dict(status=status, before=a, after=b))

    def grouped(review):
        counts = Counter()
        waits = defaultdict(list)
        for task in review.failures:
            if task['outcome'] != 'Failed':
                continue
            key = (task['location'], task['service'], task['blocker'])
            counts[key] += 1
            if task['release'] is not None and task['end'] is not None and task['end'] >= task['release']:
                waits[key].append(task['end'] - task['release'])
        return counts, waits

    before_groups, before_wait = grouped(before)
    after_groups, after_wait = grouped(after)
    groups = []
    for key in sorted(before_groups.keys() | after_groups.keys()):
        a, b = before_wait[key], after_wait[key]
        groups.append(dict(location=key[0], service=key[1], blocker=key[2], before=before_groups[key],
                           after=after_groups[key], before_wait=sum(a) / len(a) if a else None,
                           after_wait=sum(b) / len(b) if b else None, before_measured=len(a), after_measured=len(b)))
    return dict(requests=requests, unmatched=unmatched, groups=groups)
