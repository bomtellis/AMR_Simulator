"""Read-only route reconstruction and two-run comparison of recorded evidence.

Segments are route plans even when their CSV status says 'completed'. Only a
separate terminal event can confirm the enclosing simulation outcome. No route
search, simulation, export expansion or report generation occurs here.
"""
from __future__ import annotations

from collections import Counter, defaultdict, OrderedDict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from tempfile import TemporaryDirectory

from amr_event_store import iter_event_text
from amr_run_evidence import config_hash, file_hash, verified_simulation_mode
from amr_run_review import verified_events
from amr_sim_payload_instances import is_empty_payload_name

TOLERANCE = .002
SATISFIED = 'Satisfied'
VIOLATION = 'Violation'
DISABLED = 'Not applicable / disabled'
UNKNOWN = 'Insufficient evidence'
CONFIRMED = 'Confirmed simulation outcome'
PLANNED = 'Planned movement'
MOVE_TYPES = {'corridor', 'lift_transfer', 'travel', 'move', 'geometric_move', 'free_move'}
BOUNDARIES = {'pickup', 'dropoff', 'charge', 'wash', 'payload_service', 'wait_for_exchange'}
COMPLETIONS = {'task_complete', 'multi_stop_task_complete', 'charge_cycle_arrive',
               'geometric_yield_complete', 'payload_service_arrival'}
_DRAWING_CACHE = OrderedDict()
_DRAWING_CACHE_LOCK = threading.Lock()


def number(value):
    try:
        result = float(value)
        return result if not isinstance(value, bool) and math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def obj(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {} if default is None else default


def base_node(name):
    return str(name or '').split('::local::')[0]


def task_ids(row):
    return tuple(sorted(set(str(row.get('task_id') or '').split(',')) - {''}))


def _check(cancel):
    if cancel and cancel():
        raise InterruptedError('Analysis cancelled; previous results retained.')


def _hash(path, cancel=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            _check(cancel)
            digest.update(chunk)
    return digest.hexdigest()


def _seconds(value, config):
    result = number(value)
    if result is not None:
        return result
    try:
        origin = config['simulation']['start_datetime']
        return (datetime.fromisoformat(value) - datetime.fromisoformat(origin)).total_seconds()
    except (ValueError, TypeError, KeyError):
        return None


def points_from_config(config):
    points = {p['name']: dict(p) for p in config.get('locations', []) if 'name' in p}
    points.update({p['name']: dict(p) for p in config.get('corridors', {}).get('nodes', []) if 'name' in p})
    for lift in config.get('lifts', []):
        for floor, point in lift.get('floor_locations', {}).items():
            points[f"{lift['id']}-F{floor}"] = dict(point, floor=int(floor), kind='lift')
    return points


def recorded_segment_points(segment):
    """Decode movement in world metres using the same evidence as the route inspector."""
    if segment.trajectory:
        from amr_trajectories import trajectory_from_dict

        try:
            trajectory = trajectory_from_dict(segment.trajectory)
            points = []
            for motion in trajectory.motions:
                steps = 24 if motion.kind == 'arc' else 1
                for index in range(steps + 1):
                    pose = motion.pose_at(index / steps)
                    points.append((pose.x, pose.y))
            return points
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            return []
    if None in (*segment.start[:2], *segment.finish[:2]):
        return []
    return [segment.start[:2], segment.finish[:2]]


@dataclass(slots=True)
class Segment:
    id: str
    order: int
    kind: str
    time: float | None
    end: float | None
    amr: str
    journey: str
    tasks: tuple
    origin: str
    destination: str
    start: tuple
    finish: tuple
    distance: float | None
    lift: str
    payload: str
    profile: str
    detail: dict
    trajectory: dict
    native: bool

    @property
    def duration(self):
        return None if self.time is None or self.end is None else self.end - self.time


@dataclass(slots=True)
class Leg:
    id: str
    amr: str
    journey: str
    tasks: tuple
    origin: str
    destination: str
    purpose: str
    profile: str
    segments: list
    time: float | None
    end: float | None
    distance: float | None
    wait: float
    evidence: str
    complete_path: bool
    compliance: str = UNKNOWN
    reason: str = ''
    confirmation_ids: tuple = ()
    variant: tuple = ()

    @property
    def key(self):
        return self.origin, self.destination, self.purpose, self.profile

    @property
    def floors(self):
        return {v for s in self.segments if s.kind != 'lift_reposition' for v in (s.start[2], s.finish[2]) if v is not None}

    @property
    def lifts(self):
        return {s.lift for s in self.segments if s.lift}


@dataclass
class RunAnalysis:
    source: str
    fingerprint: str
    config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    legs: list = field(default_factory=list)
    movements: list = field(default_factory=list)
    task_events: list = field(default_factory=list)
    duration: float = 0
    complete: bool = False
    stop: float | None = None
    event_count: int = 0
    drawings: dict = field(default_factory=dict)
    pdf_drawings: dict = field(default_factory=dict)
    points: dict = field(default_factory=dict)
    lift_checks: dict = field(default_factory=dict)


def _source_context(source, cancel, progress):
    source = Path(source).resolve()
    directory = source if source.is_dir() else source.parent
    manifest_path = directory / 'run_manifest.json'
    manifest = obj(manifest_path.read_text(encoding='utf-8-sig')) if manifest_path.is_file() else {}
    managed = bool(manifest.get('project_binding'))
    hashes = {}
    if progress:
        progress('Verifying saved run evidence')
    _check(cancel)
    if managed:
        _manifest, config, canonical, digest = verified_events(directory, allow_partial=True)
        if source.is_dir():
            source = canonical
        elif source != canonical.resolve():
            side = Path(str(source) + '.run.json')
            exported = obj(side.read_text(encoding='utf-8')) if side.is_file() else {}
            if exported.get('canonical_sha256') != digest or exported.get('log_sha256') != _hash(source, cancel):
                raise ValueError('Selected export does not match this saved run.')
        for name in ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json'):
            path = directory / name
            if path.is_file():
                hashes[path] = _hash(path, cancel)
    elif source.is_dir():
        choices = [manifest.get('canonical_events', ''), 'events.sqlite', 'simulation_steps.csv', 'verbose.csv', 'visualiser_steps.csv']
        source = next((directory / name for name in choices if name and Path(name).name == name and (directory / name).is_file()), None)
        if source is None:
            raise ValueError('No event log found. Select a saved run folder, event CSV or SQLite log.')
    if source.suffix.lower() not in ('.csv', '.sqlite'):
        raise ValueError('Select an event CSV or SQLite log, not a report table.')
    digest = _hash(source, cancel)
    hashes[source] = digest
    side = Path(str(source) + '.run.json')
    metadata, config, warnings = {}, {}, []
    if side.is_file():
        hashes[side] = _hash(side, cancel)
        metadata = json.loads(side.read_text(encoding='utf-8-sig'))
        if (metadata.get('log_sha256') != digest or
                metadata.get('config_sha256') != config_hash(metadata.get('frozen_inputs'))):
            raise ValueError('Event log or saved configuration differs from its run evidence.')
        if metadata.get('schema_version') != (2 if source.suffix == '.sqlite' else 1):
            raise ValueError('Unsupported run-evidence version.')
        config = metadata.get('frozen_inputs') or {}
        verified_simulation_mode(metadata, config)
        if source.suffix == '.sqlite':
            from amr_event_store import EventStore
            store = EventStore(source, readonly=True)
            try:
                expected = dict(format='sqlite_sparse_events', version=store.format_version, event_count=len(store))
                if metadata.get('storage') != expected:
                    raise ValueError('SQLite event count does not match the saved evidence.')
            finally:
                store.close()
        if metadata.get('termination'):
            from amr_project_runs import verified_termination
            verified_termination(metadata, source)
    else:
        warnings.append('Unverified legacy log: saved inputs and complete coverage are unavailable.')
    full = (metadata.get('log_kind') == 'full' and metadata.get('logging_enabled') is True
            and metadata.get('reduced_logging') is False)
    complete = bool(full and metadata.get('run_status') == 'finished' and not metadata.get('termination'))
    if not complete:
        warnings.append('Incomplete coverage: counts are observed plans; absence is not proof of zero activity or compliance.')
    stop = number((metadata.get('termination') or {}).get('stop_time_sec'))
    if stop is not None:
        warnings.append(f'Stopped at {stop:g} s. Future route plans remain inspectable but cannot establish completion.')
    run = RunAnalysis(str(source), digest, config, metadata, warnings, complete=complete, stop=stop)
    run.points = points_from_config(config)
    return run, hashes, managed


def _segment(row, order, config, points):
    detail = obj(row.get('details'))
    detail = detail if isinstance(detail, dict) else {}
    kind = row.get('segment_type') or str(row.get('event_type', '')).removeprefix('multi_stop_').removeprefix('segment_')
    kind = str(kind).lower()
    origin = str(detail.get('from') or row.get('start_node') or row.get('from_location') or '')
    destination = str(detail.get('to') or row.get('end_node') or row.get('to_location') or '')
    lift = str(row.get('lift_id') or detail.get('lift_id') or '')

    def point(node, prefix, side):
        saved = points.get(base_node(node), {})
        coords = []
        for axis in ('x', 'y', 'floor'):
            val = number(detail.get(f'{side}_{axis}'))
            if val is None:
                val = number(row.get(f'{prefix}_{axis}'))
            if val is None:
                val = number(saved.get(axis))
            coords.append(val)
        if kind in ('lift_transfer', 'lift_reposition') and lift:
            match = re.fullmatch(re.escape(lift) + r'-F(-?\d+)', node)
            if match:
                coords[2] = int(match[1])
            elif kind == 'lift_reposition':
                # Reposition row coordinates may describe the waiting AMR.
                coords[2] = number(detail.get(side + '_floor'))
        return tuple(coords)

    start = _seconds(row.get('sim_time_sec'), config)
    if start is None:
        start = _seconds(row.get('start_time'), config)
    duration = number(row.get('duration_sec'))
    if duration is None:
        duration = number(detail.get('duration'))
    if duration is not None and duration < 0:
        duration = None
    end = start + duration if start is not None and duration is not None else None
    distance = number(row.get('distance_m'))
    if distance is not None and distance < 0:
        distance = None
    trajectory = obj(row.get('trajectory_json'))
    # Retain only semantic details required by the inspector; discard redundant
    # large JSON fields rather than keeping a second copy of every input row.
    keep = ('required_floor', 'required_floor_visited', 'lift_selection_reason',
            'destination_walking_distance_m', 'entry_start_sec', 'entry_time_sec',
            'exit_time_sec', 'entry_edge', 'exit_edge', 'purpose', 'location', 'fm_lift',
            'bed_fallback_reason', 'bed_fallback_lift_ids', 'predicted_fm_wait_sec',
            'estimated_time_saved_sec', 'bed_fallback_wait_limit_sec', 'bed_fallback_decision', 'bed_fallback_start_sec')
    return Segment(str(row.get('event_id') or f'row:{order}'), order, kind, start, end,
                   str(row.get('amr_id') or ''), str(row.get('journey_id') or ''), task_ids(row),
                   origin, destination, point(origin, 'start', 'from'), point(destination, 'end', 'to'),
                   distance, lift, str(row.get('payload') or ''), str(row.get('route_profile') or ''),
                   {k: detail[k] for k in keep if k in detail}, trajectory if isinstance(trajectory, dict) else {},
                   bool(row.get('event_id')))


def load_analysis(source, *, cancel=None, progress=None, drawings=True):
    run, hashes, managed = _source_context(source, cancel, progress)
    rows_by_robot, terminals, tasks, seen = defaultdict(list), defaultdict(list), {}, {}
    duplicates = 0
    with closing(iter_event_text(run.source)) as rows:
        for order, row in enumerate(rows, 1):
            if order % 1000 == 0:
                _check(cancel)
                if progress:
                    progress(f'Reading recorded events: {order:,}')
            if None in row:
                raise ValueError(f'Malformed event row {order}.')
            if not row.get('event_type') and not row.get('segment_type'):
                raise ValueError('This file is not an event log: event_type or segment_type is required.')
            identity = row.get('event_id')
            if identity:
                signature = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).digest()
                if identity in seen:
                    if seen[identity] != signature:
                        raise ValueError(f'Conflicting event identifier: {identity}')
                    duplicates += 1
                    continue
                seen[identity] = signature
            if run.metadata and row.get('run_id') != run.metadata.get('run_id'):
                raise ValueError(f'Event {order} has a different or missing run identity.')
            run.event_count += 1
            kind = str(row.get('event_type') or '')
            normalized = kind.removeprefix('multi_stop_')
            time = _seconds(row.get('sim_time_sec'), run.config)
            ids = task_ids(row)
            for tid in ids:
                task = tasks.setdefault(tid, {})
                for key in ('route_profile', 'task_source', 'source_rule_path', 'generation_component'):
                    if row.get(key):
                        task[key] = row[key]
                if kind == 'return_task_generated':
                    task['return'] = True
                if row.get('task_source') == 'idle_return' or 'idle_charge_return' in str(row.get('details', '')):
                    task['idle'] = True
            if normalized in ('task_released', 'task_assigned', 'task_complete', 'task_failed', 'task_generated', 'return_task_generated'):
                run.task_events.append((normalized, time, ids))
            if kind in COMPLETIONS:
                terminals[str(row.get('amr_id') or '')].append(dict(
                    kind=kind, time=time, tasks=ids, journey=str(row.get('journey_id') or ''),
                    destination=base_node(row.get('to_location') or row.get('amr_location_after')),
                    id=identity or f'row:{order}'))
            if normalized.startswith('segment_'):
                segment = _segment(row, order, run.config, run.points)
                if segment.kind in ('lift_transfer', 'lift_reposition'):
                    run.movements.append(segment)
                if segment.amr:
                    rows_by_robot[segment.amr].append(segment)
    if duplicates:
        run.warnings.append(f'{duplicates:,} identical duplicate events counted once.')
    from amr_lift_evidence import check_lift_movements
    lift_events = [dict(id=s.id, type='segment_'+s.kind, identity='native' if s.native else 'legacy',
                       lift_id=s.lift, time_seconds=s.time, duration_seconds=s.duration,
                       row=dict(from_location=s.origin, to_location=s.destination,
                                details=json.dumps(dict(**{'from':s.origin,'to':s.destination}))))
                   for s in run.movements]
    run.lift_checks = check_lift_movements(lift_events, run.config, complete=run.complete,
        capabilities=run.metadata.get('event_capabilities', []),
        expected=run.metadata.get('summary', {}).get('lift_movement_counts'))
    conflicts = [issue for issue in run.lift_checks['issues'] if issue['kind'] != 'missing_evidence']
    if conflicts:
        run.warnings.append(f'{len(conflicts)} lift booking/count/continuity conflicts; consult lift consistency details.')
    if any(issue['kind']=='count_mismatch' for issue in conflicts):
        run.complete = False
        run.warnings.append('Lift count reconciliation failed; complete movement coverage is not established.')
    _check(cancel)
    if progress:
        progress('Reconstructing location-to-location movement legs')
    for robot, segments in rows_by_robot.items():
        _check(cancel)
        _build_legs(run, robot, segments, terminals[robot], tasks)
    observed = max([0] + [s.end or s.time or 0 for values in rows_by_robot.values() for s in values]
                   + [e[1] or 0 for e in run.task_events])
    sim = run.config.get('simulation', {})
    horizon = _seconds(sim.get('end_datetime'), run.config)
    run.duration = run.stop if run.stop is not None else horizon if horizon is not None and horizon > 0 else observed
    if drawings:
        _load_drawings(run, managed, cancel, progress)
    for path, digest in hashes.items():
        if _hash(path, cancel) != digest:
            raise ValueError('Run evidence changed during loading. Select the run again.')
    run.warnings.append('Distances, routes and lift activity describe recorded plans; separate outcome events confirm completion in the simulation.')
    return run


def _load_drawings(run, managed, cancel, progress):
    from visualiser.dxf_scene import DXFScene
    directory = Path(run.source).parent
    for entry in run.config.get('floor_dxf_files', []):
        _check(cancel)
        path = Path(entry.get('filepath', ''))
        if not path.is_absolute():
            path = directory / path
        floor = entry.get('floor')
        if progress:
            progress(f'Loading saved floor drawing: {floor}')
        try:
            if managed and _hash(path, cancel) != path.stem:
                raise ValueError('saved drawing checksum mismatch')
            before = _hash(path, cancel)
            with _DRAWING_CACHE_LOCK:
                content = _DRAWING_CACHE.get(before)
            if content is None:
                content = DXFScene.load_content(str(path))
            if _hash(path, cancel) != before:
                raise ValueError('drawing changed while loading')
            with _DRAWING_CACHE_LOCK:
                _DRAWING_CACHE[before] = content
                _DRAWING_CACHE.move_to_end(before)
                while len(_DRAWING_CACHE) > 12:
                    _DRAWING_CACHE.popitem(last=False)
            run.drawings[int(floor)] = dict(content, path=str(path), sha256=before)
            if not managed:
                run.warnings.append(f'Floor {floor}: external drawing is context only; historical drawing bytes are not bound to this log.')
        except InterruptedError:
            raise
        except Exception as exc:
            run.warnings.append(f'Floor {floor}: drawing unavailable ({exc}); saved route geometry remains visible.')
    for entry in run.config.get('floor_pdf_underlays', []):
        _check(cancel)
        path = Path(entry.get('filepath', ''))
        if not path.is_absolute():
            path = directory / path
        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtCore import QSize
            if managed and _hash(path, cancel) != path.stem:
                raise ValueError('saved drawing checksum mismatch')
            before = _hash(path, cancel)
            document = QPdfDocument()
            document.load(str(path))
            page = max(0, int(entry.get('page', 1)) - 1)
            size = document.pagePointSize(page)
            scale = 1800 / max(size.width(), size.height(), 1)
            image = document.render(page, QSize(max(1, int(size.width()*scale)), max(1, int(size.height()*scale))))
            document.close()
            if image.isNull() or _hash(path, cancel) != before:
                raise ValueError('PDF unavailable or changed while loading')
            run.pdf_drawings[int(entry['floor'])] = (
                image, dict(entry, filepath=str(path), sha256=before, page_width_pt=size.width(),
                            page_height_pt=size.height()))
            if not managed:
                run.warnings.append(f"Floor {entry['floor']}: external PDF is context only; historical drawing bytes are not bound to this log.")
        except InterruptedError:
            raise
        except Exception as exc:
            run.warnings.append(f"Floor {entry.get('floor')}: PDF unavailable ({exc}).")


def _build_legs(run, robot, segments, terminals, tasks):
    segments.sort(key=lambda s: (s.time is None, s.time or 0, s.order))
    current = []
    context = None
    terminals.sort(key=lambda t: (t['time'] is None, t['time'] or 0))

    def flush(next_boundary=None):
        nonlocal current
        movements = [s for s in current if s.kind in MOVE_TYPES]
        if not movements or not any(s.origin != s.destination or (s.distance or 0) > 0 for s in movements):
            current = []
            return
        first, last = movements[0], movements[-1]
        origin = base_node((first.detail.get('entry_edge') or {}).get('from') or first.origin)
        destination = base_node((last.detail.get('exit_edge') or {}).get('to') or last.destination)
        ids = tuple(sorted({tid for s in current for tid in s.tasks}))
        profile = next((s.profile for s in current if s.profile), '') or next(
            (tasks[t].get('route_profile', '') for t in ids if tasks.get(t, {}).get('route_profile')), '')
        loaded = any(not is_empty_payload_name(s.payload) for s in movements)
        if any(tasks.get(t, {}).get('idle') for t in ids) or any(t.startswith(f'RETURN-{robot}-') for t in ids):
            purpose = 'Parking / idle return'
        elif not ids and next_boundary and next_boundary.kind == 'charge':
            purpose = 'Charging travel'
        elif not loaded and ids:
            purpose = 'Empty approach'
        elif any(tasks.get(t, {}).get('return') for t in ids):
            purpose = 'Return'
        elif loaded:
            purpose = 'Delivery'
        else:
            purpose = 'Empty travel'
        start = current[0].time
        finish = last.end
        path_known = bool(origin and destination and run.config and all(s.time is not None and s.end is not None and s.native for s in current))
        for a, b in zip(movements, movements[1:]):
            # Graph-timed lift entry/exit connectors are included within the
            # transfer, so their graph endpoints replace the landing for continuity.
            a_end = base_node((a.detail.get('exit_edge') or {}).get('to') or a.destination)
            b_start = base_node((b.detail.get('entry_edge') or {}).get('from') or b.origin)
            if a_end != b_start or (a.end is not None and b.time is not None and b.time < a.end - TOLERANCE):
                path_known = False
        # A reconstructed fragment ending at a corridor node is not a whole leg.
        locations = {p.get('name') for p in run.config.get('locations', [])}
        path_known = path_known and origin in locations and destination in locations
        confirms = []
        for terminal in terminals:
            if finish is None or terminal['time'] is None or terminal['time'] < finish - TOLERANCE:
                continue
            if run.stop is not None and terminal['time'] > run.stop + TOLERANCE:
                continue
            same_journey = first.journey and first.journey == terminal['journey']
            same_tasks = ids and set(ids).issubset(terminal['tasks'])
            if (same_journey or same_tasks) and terminal['kind'] in ('task_complete', 'multi_stop_task_complete', 'payload_service_arrival'):
                confirms.append(terminal['id'])
                break
            if (not ids and terminal['kind'] == 'charge_cycle_arrive' and destination == terminal['destination']
                    and abs(terminal['time'] - finish) <= .01):
                confirms.append(terminal['id'])
                purpose = 'Charging travel'
                break
        evidence = CONFIRMED if confirms and path_known and run.metadata else PLANNED
        distance = sum(s.distance for s in movements) if all(s.distance is not None for s in movements) else None
        leg = Leg(f'{robot}:{first.id}', robot, first.journey, ids, origin, destination, purpose, profile,
                  current, start, finish, distance,
                  sum(s.duration or 0 for s in current if s.kind == 'wait_for_lift'), evidence,
                  bool(path_known), confirmation_ids=tuple(confirms))
        leg.variant = tuple((s.kind, s.origin, s.destination, s.lift) for s in movements)
        leg.compliance, leg.reason = check_forced_floor(leg, run)
        run.legs.append(leg)
        current = []

    for segment in segments:
        # A task journey may hold several physical legs. Actions delimit legs;
        # lift stops and corridor nodes deliberately do not.
        key = segment.journey or (('tasks', segment.tasks) if segment.tasks else ('unassigned', robot))
        if context is not None and key != context:
            flush()
        context = key
        if segment.kind in BOUNDARIES:
            flush(segment)
        elif segment.kind in MOVE_TYPES or segment.kind.startswith('wait') or segment.kind == 'lift_reposition':
            current.append(segment)
        elif segment.kind == 'local_manoeuvre':
            # Local bay motions are not independent policy journeys. Stowing is
            # a recorded boundary; unstowing before a route is ignored.
            if segment.detail.get('purpose') in ('amr_stow', 'payload_stow'):
                flush(segment)
        # Empty lift repositioning is a separate physical lift movement, never
        # a floor visit by the waiting AMR.
    flush()


def check_forced_floor(leg, run):
    building = run.config.get('building', {})
    if not run.config:
        return UNKNOWN, 'Saved routing policy is unavailable.'
    if building.get('force_via_floor_enabled') is not True:
        return DISABLED, 'Forced-floor routing was disabled in this run.'
    required = number(building.get('force_via_floor'))
    if required is None:
        return UNKNOWN, 'Required floor is missing from the saved inputs.'
    movement = [s for s in leg.segments if s.kind in MOVE_TYPES]
    if not movement:
        return DISABLED, 'No location-to-location movement.'
    if not leg.complete_path:
        return UNKNOWN, 'The recorded leg has missing endpoints, continuity, identity or timing.'
    origin_floor, destination_floor = movement[0].start[2], movement[-1].finish[2]
    if origin_floor is None or destination_floor is None:
        return UNKNOWN, 'A route endpoint floor is missing.'
    visited = origin_floor == required
    annotation_conflict = False
    uncertain_exit = False
    for s in movement:
        if s.kind == 'lift_transfer':
            if s.finish[2] == required:
                # Explicit transfer exit timing is preferred. Legacy fixed
                # transfers encode alighting in their saved boarding allowance.
                exit_time = number(s.detail.get('exit_time_sec'))
                lift = next((l for l in run.config.get('lifts', []) if l.get('id') == s.lift), {})
                if exit_time is not None and exit_time >= 0:
                    visited = True
                elif lift.get('transfer_timing_mode', 'fixed') == 'fixed' and number(lift.get('boarding_time_sec')) is not None:
                    visited = True
                else:
                    uncertain_exit = True
            if 'required_floor' in s.detail and number(s.detail['required_floor']) != required:
                annotation_conflict = True
            if 'required_floor_visited' in s.detail and s.detail['required_floor_visited'] is not visited:
                annotation_conflict = True
    if annotation_conflict:
        return UNKNOWN, 'Routing annotation conflicts with the independently reconstructed floor visits.'
    if visited:
        return SATISFIED, f'Recorded route starts on or includes an exit at required floor {required:g}. Basis: {leg.evidence.lower()}.'
    if uncertain_exit:
        return UNKNOWN, f'Arrival at floor {required:g} is recorded, but exit evidence is missing.'
    if not run.complete:
        return UNKNOWN, 'No required-floor visit is visible, but complete route coverage is not established.'
    return VIOLATION, f'Complete recorded route does not visit required floor {required:g}. Basis: {leg.evidence.lower()}.'


@dataclass(frozen=True)
class Filters:
    start: float = 0
    end: float | None = None
    floor: float | None = None
    lift: str = ''
    amr: str = ''
    purpose: str = ''
    profile: str = ''
    origin: str = ''
    destination: str = ''
    evidence: str = ''
    compliance: str = ''
    lift_origin_floor: float | None = None
    lift_destination_floor: float | None = None


def matches(leg, filters):
    pair = (filters.lift_origin_floor, filters.lift_destination_floor)
    return (pair == (None, None) or any(
        s.kind == 'lift_transfer' and (pair[0] is None or s.start[2] == pair[0])
        and (pair[1] is None or s.finish[2] == pair[1]) for s in leg.segments)) and (
        not filters.amr or leg.amr == filters.amr) and (
        not filters.lift or filters.lift in leg.lifts) and (
        filters.floor is None or filters.floor in leg.floors) and all(
        not getattr(filters, key) or getattr(leg, key) == getattr(filters, key)
        for key in ('purpose', 'profile', 'origin', 'destination', 'evidence', 'compliance'))


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarize(run, filters, *, cancel=None):
    end = run.duration if filters.end is None else min(filters.end, run.duration)
    start = filters.start
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError('Select a nonempty elapsed-time window within the run.')
    selected = []
    context_legs = []
    for index, leg in enumerate(run.legs):
        if index % 500 == 0:
            _check(cancel)
        if matches(leg, filters):
            context_legs.append(leg)
            if leg.time is not None and start <= leg.time < end:
                selected.append(leg)
    by_segment = {s.id: leg for leg in context_legs for s in leg.segments}
    related_filters = any((filters.purpose, filters.profile, filters.origin, filters.destination, filters.evidence, filters.compliance))
    movements = []
    busy = 0
    for s in run.movements:
        if filters.lift and filters.lift != s.lift or filters.amr and filters.amr != s.amr:
            continue
        if filters.floor is not None and filters.floor not in (s.start[2], s.finish[2]):
            continue
        if filters.lift_origin_floor is not None and s.start[2] != filters.lift_origin_floor:
            continue
        if filters.lift_destination_floor is not None and s.finish[2] != filters.lift_destination_floor:
            continue
        if related_filters and s.id not in by_segment:
            continue
        if s.time is not None and s.end is not None:
            busy += max(0, min(s.end, end) - max(s.time, start))
        if s.time is not None and start <= s.time < end:
            movements.append(s)
    complete = [leg for leg in selected if leg.evidence == CONFIRMED and leg.end is not None and leg.end <= end + TOLERANCE]
    durations = [leg.end - leg.time for leg in complete]
    distances = [leg.distance for leg in selected]
    metrics = {
        'Recorded AMR legs': len(selected),
        'Confirmed complete legs': len(complete),
        'Excluded from journey duration': len(selected) - len(complete),
        'Recorded travel distance (m)': sum(distances) if all(d is not None for d in distances) else None,
        'Mean distance per leg (m)': _mean(distances),
        'Mean confirmed journey time (s)': _mean(durations),
        'Recorded lift waiting (s)': sum(leg.wait for leg in selected),
        'Mean lift waiting per leg (s)': _mean([leg.wait for leg in selected]),
        'Lift transfers': sum(s.kind == 'lift_transfer' for s in movements),
        'Bed-lift fallback journeys': len({(s.amr, s.detail['bed_fallback_start_sec']) for s in movements
                                          if 'bed_fallback_start_sec' in s.detail}),
        'Bed-lift fallback transfers': sum(s.kind == 'lift_transfer' and s.lift in s.detail.get('bed_fallback_lift_ids', []) for s in movements),
        'Empty lift repositioning': sum(s.kind == 'lift_reposition' for s in movements),
        'Lift movements per hour': len(movements) * 3600 / (end - start),
        'Lift busy time in window (s)': busy,
    }
    # Workload counts intentionally remain run-wide for the chosen time window,
    # so filtering a robot cannot silently redefine the demand denominator.
    for label, kinds in (('Run workload: released / generated tasks', {'task_released', 'task_generated', 'return_task_generated'}),
                         ('Run workload: completed tasks', {'task_complete'}),
                         ('Run workload: failed tasks', {'task_failed'})):
        metrics[label] = len({tid for kind, t, ids in run.task_events if kind in kinds and t is not None and start <= t < end for tid in ids})
    if not run.complete:
        for key, value in list(metrics.items()):
            if value == 0:
                metrics[key] = None
    groups = defaultdict(list)
    for leg in selected:
        groups[leg.key].append(leg)
    compliance = Counter(leg.compliance for leg in selected)
    return dict(run=run, legs=selected, groups=dict(groups), movements=movements,
                metrics=metrics, compliance=dict(compliance), start=start, end=end)


def compare_runs(a, b=None, filters=None, *, cancel=None):
    filters = filters or Filters(end=min(a.duration, b.duration) if b else a.duration)
    if filters.end is None:
        filters = Filters(**{**filters.__dict__, 'end': min(a.duration, b.duration) if b else a.duration})
    else:
        filters = Filters(**{**filters.__dict__, 'end': min(filters.end, a.duration, b.duration if b else a.duration)})
    sides = [summarize(run, filters, cancel=cancel) if run else None for run in (a, b)]
    rows = []
    for key, av in sides[0]['metrics'].items():
        bv = sides[1]['metrics'][key] if sides[1] else None
        delta = bv - av if av is not None and bv is not None else None
        rows.append(dict(metric=key, a=av, b=bv, delta=delta,
                         percent=delta * 100 / av if delta is not None and av != 0 else None))
    groups = []
    keys = set(sides[0]['groups']) | (set(sides[1]['groups']) if sides[1] else set())
    for key in sorted(keys):
        legs_a = sides[0]['groups'].get(key, [])
        legs_b = sides[1]['groups'].get(key, []) if sides[1] else []
        variants = defaultdict(lambda: [[], []])
        for side, legs in enumerate((legs_a, legs_b)):
            for leg in legs:
                variants[leg.variant][side].append(leg)
        groups.append(dict(key=key, a=legs_a, b=legs_b, variants=dict(variants)))
    differences = []
    if b:
        for key in ('building', 'simulation', 'route_profiles', 'tasks', 'task_generation', 'amrs', 'lifts', 'locations', 'corridors'):
            if a.config.get(key) != b.config.get(key):
                differences.append(key)
    return dict(sides=sides, metrics=rows, groups=groups, filters=filters,
                differences=differences)


def route_group_values(legs, side, end):
    """Shared arithmetic for route-group tables and exported comparisons."""
    if side is None:
        return dict(count=None, distance=None, duration=None, wait=None)
    return dict(count=len(legs) if legs or side['run'].complete else None,
                distance=_mean([l.distance for l in legs]),
                duration=_mean([l.end-l.time for l in legs if l.evidence == CONFIRMED
                                and l.end is not None and l.end <= end+TOLERANCE]),
                wait=_mean([l.wait for l in legs]))


def export_comparison(result, directory, *, cancel=None):
    """Export every filtered row, never just the current UI table page."""
    directory = Path(directory).resolve()
    for side in result['sides']:
        if side and (directory == Path(side['run'].source).parent or Path(side['run'].source).parent in directory.parents):
            raise ValueError('Choose an export folder outside the source run.')
    if directory.exists():
        raise FileExistsError('Choose a new export folder; existing exports are preserved.')
    _check(cancel)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.route-analysis-', dir=directory.parent) as scratch:
        staged = Path(scratch) / 'export'
        _write_comparison(result, staged, cancel)
        _check(cancel)
        staged.rename(directory)
    return directory


def _write_comparison(result, directory, cancel):
    directory.mkdir(parents=True, exist_ok=False)

    def write(name, fields, rows):
        with (directory / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index, row in enumerate(rows):
                if index % 250 == 0:
                    _check(cancel)
                writer.writerow(row)

    write('comparison.csv', ['metric', 'a', 'b', 'delta', 'percent'], result['metrics'])
    group_rows, variant_rows = [], []
    def group_row(key, a, b):
        av, bv = (route_group_values(legs, side, result['filters'].end)
                  for legs, side in zip((a,b),result['sides']))
        values = dict(zip(('origin','destination','purpose','profile'),key))
        for label, summary in (('a',av),('b',bv)):
            values.update({f'{label}_{name}': value for name,value in summary.items()})
        values['delta_count'] = bv['count']-av['count'] if bv['count'] is not None and av['count'] is not None else None
        return values
    for group in result['groups']:
        _check(cancel)
        group_rows.append(group_row(group['key'],group['a'],group['b']))
        for index, (variant, sides) in enumerate(group['variants'].items(),1):
            variant_rows.append(dict(group_row(group['key'],*sides),variant=index,
                                     recorded_path=json.dumps(variant,ensure_ascii=False)))
    group_fields = ['origin','destination','purpose','profile','a_count','b_count','delta_count',
                    'a_distance','b_distance','a_duration','b_duration','a_wait','b_wait']
    write('route-comparison.csv',group_fields,group_rows)
    write('route-variants.csv',group_fields+['variant','recorded_path'],variant_rows)
    legs, evidence, lift_rows = [], [], []
    provenance = dict(filters=result['filters'].__dict__, differences=result['differences'], runs={})
    for label, side in zip(('A', 'B'), result['sides']):
        if not side:
            continue
        run = side['run']
        provenance['runs'][label] = dict(source=run.source, sha256=run.fingerprint,
                                       run_id=run.metadata.get('run_id'), warnings=run.warnings,
                                       configuration=run.config)
        for leg in side['legs']:
            _check(cancel)
            legs.append(dict(run=label, leg=leg.id, origin=leg.origin, destination=leg.destination,
                             purpose=leg.purpose, profile=leg.profile, amr=leg.amr,
                             journey=leg.journey, tasks=';'.join(leg.tasks), start_s=leg.time,
                             end_s=leg.end, distance_m=leg.distance, lift_wait_s=leg.wait,
                             evidence=leg.evidence, compliance=leg.compliance, reason=leg.reason,
                             confirmation_events=';'.join(leg.confirmation_ids)))
            for s in leg.segments:
                evidence.append(dict(run=label, leg=leg.id, event=s.id, source_row=s.order,
                                     kind=s.kind, origin=s.origin, destination=s.destination,
                                     start_s=s.time, end_s=s.end, distance_m=s.distance, lift=s.lift,
                                     detail=json.dumps(s.detail, ensure_ascii=False)))
        for s in side['movements']:
            lift_rows.append(dict(run=label, event=s.id, lift=s.lift, kind=s.kind,
                                  origin_floor=s.start[2], destination_floor=s.finish[2],
                                  start_s=s.time, end_s=s.end, amr=s.amr, journey=s.journey))
    write('journeys.csv', ['run','leg','origin','destination','purpose','profile','amr','journey','tasks','start_s','end_s','distance_m','lift_wait_s','evidence','compliance','reason','confirmation_events'], legs)
    write('journey-evidence.csv', ['run','leg','event','source_row','kind','origin','destination','start_s','end_s','distance_m','lift','detail'], evidence)
    write('lift-movements.csv', ['run','event','lift','kind','origin_floor','destination_floor','start_s','end_s','amr','journey'], lift_rows)
    (directory / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding='utf-8')
    return directory
