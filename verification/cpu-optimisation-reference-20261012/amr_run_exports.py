"""Verified, atomic, on-demand exports of completed compact runs."""
from dataclasses import fields, is_dataclass
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
import zlib

from amr_event_store import EventStore, export_rows
from amr_run_evidence import file_hash

REPORT_FIELDS = ('charge_intervals', 'charge_location_names', 'completed_task_records', 'current_time',
    'failed_tasks', 'floor_graphs', 'floor_height_m', 'floor_reverse_graphs', 'inventory_spaces_by_location',
    'lift_stop_names', 'lifts', 'locations', 'people_affected_segments', 'people_delay_sec',
    'scenario_affected_segments', 'scenario_delay_sec', 'scenario_description', 'scenario_enhanced_logging',
    'scenario_mode', 'scenario_name', 'wash_cycles_completed')


def encode(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        tags = ({'map'}, {'tuple'}, {'list'}, {'set'}, {'datetime'}, {'object'})
        if all(isinstance(key, str) for key in value) and set(value) not in tags:
            return {key: encode(item) for key, item in value.items()}
        return {'map': [[encode(key), encode(item)] for key, item in value.items()]}
    if isinstance(value, (tuple, list, set, frozenset)):
        kind = 'tuple' if isinstance(value, tuple) else 'set' if isinstance(value, (set, frozenset)) else 'list'
        return {kind: [encode(item) for item in value]}
    if isinstance(value, datetime):
        return {'datetime': value.isoformat()}
    if is_dataclass(value) and type(value).__module__.startswith('amr_'):
        values = vars(value) if hasattr(value, '__dict__') else {f.name: getattr(value, f.name) for f in fields(value)}
        return {'object': [type(value).__module__, type(value).__name__, encode(values)]}
    raise TypeError(f'Unsupported report-state value: {type(value).__name__}')


def decode(value):
    if not isinstance(value, dict):
        return value
    if set(value) == {'map'}:
        return {decode(key): decode(item) for key, item in value['map']}
    for kind, constructor in (('tuple', tuple), ('list', list), ('set', set)):
        if set(value) == {kind}:
            return constructor(decode(item) for item in value[kind])
    if set(value) == {'datetime'}:
        return datetime.fromisoformat(value['datetime'])
    if set(value) == {'object'}:
        module, name, attributes = value['object']
        # Data-only reconstruction of local dataclasses; never execute pickle.
        allowed = ('amr_sim_models', 'amr_geometry', 'amr_geometric_motion', 'amr_geometric_routing',
                   'amr_occupancy_ledger', 'amr_geometric_paths')
        if module not in allowed:
            raise ValueError('Unsupported report-state object module')
        cls = getattr(importlib.import_module(module), name)
        if not is_dataclass(cls):
            raise ValueError('Report-state objects must be dataclasses')
        obj = cls.__new__(cls)
        for key, item in decode(attributes).items():
            object.__setattr__(obj, key, item)
        return obj
    return {key: decode(item) for key, item in value.items()}


def save_report_state(simulation):
    state = {key: getattr(simulation, key) for key in REPORT_FIELDS if key != 'completed_task_records'}
    payload = zlib.compress(json.dumps(encode(state), ensure_ascii=False, separators=(',', ':'),
                                       allow_nan=False).encode('utf-8'), level=1)
    simulation.event_store.connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('report_state', payload))
    records = simulation.completed_task_records
    simulation.event_store.connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
        ('report_record_count', str(len(records))))
    for offset in range(0, len(records), 100):
        payload = zlib.compress(json.dumps(encode(records[offset:offset + 100]), ensure_ascii=False,
            separators=(',', ':'), allow_nan=False).encode('utf-8'), level=1)
        simulation.event_store.connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
            (f'report_records:{offset:012d}', payload))
    simulation.event_store.connection.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
        ('report_headers', json.dumps(dict(steps_csv=simulation._verbose_fieldnames(),
                                         visualiser_csv=simulation._visualiser_fieldnames()))))


class ReportRecords:
    def __init__(self, path):
        self.path = path
    def __len__(self):
        store = EventStore(self.path, readonly=True)
        try:
            return int(store.connection.execute("SELECT value FROM metadata WHERE key='report_record_count'").fetchone()[0])
        finally:
            store.close()
    def __iter__(self):
        store = EventStore(self.path, readonly=True)
        try:
            for (blob,) in store.connection.execute("SELECT value FROM metadata WHERE key LIKE 'report_records:%' ORDER BY key"):
                yield from decode(json.loads(zlib.decompress(blob)))
        finally:
            store.close()


def load_report_state(path):
    from simulator import Simulation
    store = EventStore(path, readonly=True)
    try:
        result = store.connection.execute("SELECT value FROM metadata WHERE key='report_state'").fetchone()
        if result is None:
            raise ValueError('Compact evidence has no reporting state')
        state = decode(json.loads(zlib.decompress(result[0])))
    finally:
        store.close()
    simulation = Simulation.__new__(Simulation)
    for key, value in state.items():
        setattr(simulation, key, value)
    simulation.route_cache = {}
    simulation.route_cache_lock = threading.Lock()
    simulation.completed_task_records = ReportRecords(path)
    return simulation


def ensure_exports(directory, outputs=('steps_csv',), *, cancel=None, progress=None):
    from amr_project_runs import OUTPUTS, read_json, write_json
    from amr_run_review import verified_events, verified_standalone_events
    from simulator import Simulation
    directory = Path(directory).resolve()
    requested = tuple(dict.fromkeys(outputs))
    if any(key not in OUTPUTS for key in requested):
        raise ValueError('Unknown simulation output requested')
    standalone = directory.is_file()
    filenames = OUTPUTS
    if standalone:
        manifest, config, canonical, checksum = verified_standalone_events(directory)
        directory = canonical.parent
        prefix = canonical.name.removesuffix('.sqlite').removesuffix('.csv')
        filenames = {key: prefix + '_' + name for key, name in OUTPUTS.items()}
        filenames['steps_csv'] = prefix + '.csv'
    else:
        manifest, config, canonical, checksum = verified_events(directory, allow_partial=True)
    if canonical.suffix != '.sqlite':
        return {key: directory / OUTPUTS[key] for key in requested}
    lock = directory / (canonical.name + '.exports.lock' if standalone else '.exports.lock')
    deadline = time.monotonic() + 120
    while True:
        if cancel and cancel():
            raise InterruptedError('Export cancelled')
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, str(os.getpid()).encode())
            os.close(descriptor)
            break
        except FileExistsError:
            from amr_stress_resources import process_alive
            try:
                if not process_alive(int(lock.read_text())):
                    lock.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise TimeoutError('Another export is still running; completed evidence is retained')
            time.sleep(.1)
    try:
        registry_path = directory / (canonical.name + '.exports.json' if standalone else 'exports.json')
        registry = read_json(registry_path) if registry_path.exists() else {}
        evidence = read_json(str(canonical) + '.run.json')
        report_simulation = None
        for key in requested:
            if cancel and cancel():
                raise InterruptedError('Export cancelled; simulation evidence is retained')
            target = directory / filenames[key]
            cached = registry.get(key)
            if cached and cached.get('source_sha256') == checksum and target.exists():
                if file_hash(target) != cached['sha256']:
                    raise ValueError('Cached export changed; its evidence no longer matches')
                sidecar = Path(str(target) + '.run.json')
                if cached.get('sidecar_sha256') and (not sidecar.exists() or file_hash(sidecar) != cached['sidecar_sha256']):
                    raise ValueError('Cached export evidence changed')
                continue
            if progress:
                progress(dict(phase='Expanding ' + OUTPUTS[key]))
            if key in ('steps_csv', 'visualiser_csv'):
                viewer = Simulation.__new__(Simulation)
                store = EventStore(canonical, readonly=True)
                try:
                    names = json.loads(store.connection.execute("SELECT value FROM metadata WHERE key='report_headers'").fetchone()[0])[key]
                finally:
                    store.close()
                export_rows(canonical, target, names,
                    None, cancel, progress, playback_only=key == 'visualiser_csv')
                metadata = dict(evidence, schema_version=1, log_sha256=file_hash(target),
                    log_kind='full' if key == 'steps_csv' else 'playback', canonical_sha256=checksum)
                metadata.pop('storage', None)
                write_json(str(target) + '.run.json', metadata)
            else:
                if report_simulation is None:
                    report_simulation = load_report_state(canonical)
                temporary = target.with_name(target.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    getattr(report_simulation, 'write_' + key)(str(temporary))
                    if cancel and cancel():
                        raise InterruptedError('Export cancelled')
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            record = dict(source_sha256=checksum, sha256=file_hash(target))
            if key in ('steps_csv', 'visualiser_csv'):
                record['sidecar_sha256'] = file_hash(str(target) + '.run.json')
            registry[key] = record
            write_json(registry_path, registry)
        if file_hash(canonical) != checksum:
            raise ValueError('Canonical simulation evidence changed during export')
        return {key: directory / filenames[key] for key in requested}
    finally:
        lock.unlink(missing_ok=True)
