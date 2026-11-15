"""Compact execution is an exact representation change, not a model approximation."""
import contextlib
from copy import deepcopy
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from amr_event_store import EventStore
from amr_project import Project
from amr_project_runs import PreparedRun, execute, OUTPUTS, read_json
from amr_route_reservations import RouteReservationTransaction
from amr_run_exports import ensure_exports
from amr_run_review import verified_events
from amr_runtime_data import compile_runtime_inputs
from simulator import Simulation
from tests.test_scenario_study import config
from tests.test_route_reservation_atomicity import storage_config, resource_state
from tests.test_geometric_yielding import yielding_config
from visualiser.project_checks import check_project


def normalise(value, run_id):
    if isinstance(value, str):
        return value.replace(run_id, '<run>')
    if isinstance(value, dict):
        return {key: normalise(item, run_id) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise(item, run_id) for item in value]
    return value


class CompactExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_project(self, backend='compact'):
        project = Project()
        project.save(self.root / (backend + '.amrproj'), config())
        draft = PreparedRun(project, self.root / 'runs')
        checks = check_project(draft.config)
        checks.acknowledge_warnings()
        directory = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            simulation = execute(directory, runtime_backend=backend)
        return directory, simulation

    def test_source_is_owned_and_runtime_metadata_is_separate(self):
        source = config()
        source['description'] = 'Presentation only'
        source['payloads'][0]['notes'] = 'cold payload details'
        compiled = compile_runtime_inputs(source)
        source['payloads'][0]['weight_kg'] = 999
        runtime = compiled.execution_config()
        self.assertNotEqual(999, runtime['payloads'][0]['weight_kg'])
        self.assertNotIn('notes', runtime['payloads'][0])
        self.assertEqual('cold payload details', compiled.source['payloads'][0]['notes'])
        runtime['payloads'][0]['weight_kg'] = 123
        self.assertNotEqual(123, compiled.execution_config()['payloads'][0]['weight_kg'])
        with self.assertRaises(TypeError):
            compiled.definitions['payloads'][0]['weight_kg'] = 1
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, 'obsolete compiler version'):
            Simulation(compiled.source, runtime_inputs=replace(compiled, version=0))

    def test_reference_and_compact_runs_have_identical_operational_evidence(self):
        fixtures = [config(), yielding_config(), storage_config(2, lifts=True)]
        fixtures[-1]['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        for value in fixtures:
            with self.subTest(detailed=bool(value.get('geometry'))):
                with contextlib.redirect_stdout(io.StringIO()):
                    reference = Simulation(deepcopy(value), verbose=True, runtime_backend='reference')
                    compact = Simulation(deepcopy(value), verbose=True)
                    reference.run()
                    compact.run()
                self.assertEqual(reference.failed_task_ids, compact.failed_task_ids)
                self.assertEqual(reference.current_time, compact.current_time)
                self.assertEqual(resource_state(reference), resource_state(compact))
                self.assertEqual(normalise(list(reference.verbose_rows), reference.run_id),
                                 normalise(list(compact.verbose_rows), compact.run_id))
                compact.event_store.close()

    def test_canonical_completion_needs_no_expanded_outputs(self):
        directory, simulation = self.run_project()
        manifest, _, store, _ = verified_events(directory)
        self.assertEqual('complete', manifest['status'])
        self.assertEqual('.sqlite', store.suffix)
        self.assertEqual(1, manifest['completed_tasks'])
        self.assertFalse(any((directory / name).exists() for name in OUTPUTS.values()))
        self.assertTrue(simulation.event_store.closed)

    def test_all_exports_match_reference_and_cached_exports_are_not_rewritten(self):
        compact_dir, compact = self.run_project()
        reference_dir, reference = self.run_project('reference')
        ensure_exports(compact_dir, OUTPUTS)
        for key, name in OUTPUTS.items():
            with self.subTest(output=key):
                expected = (reference_dir / name).read_text(encoding='utf-8').replace(reference.run_id, '<run>')
                actual = (compact_dir / name).read_text(encoding='utf-8').replace(compact.run_id, '<run>')
                self.assertEqual(expected, actual)
        before = (compact_dir / OUTPUTS['steps_csv']).stat().st_mtime_ns
        ensure_exports(compact_dir)
        self.assertEqual(before, (compact_dir / OUTPUTS['steps_csv']).stat().st_mtime_ns)

    def test_cancelled_export_keeps_complete_canonical_evidence(self):
        directory, _ = self.run_project()
        original = verified_events(directory)[3]
        calls = []
        def cancelled():
            calls.append(1)
            return len(calls) >= 3
        with self.assertRaises(InterruptedError):
            ensure_exports(directory, cancel=cancelled)
        self.assertEqual(original, verified_events(directory)[3])
        self.assertEqual('complete', read_json(directory / 'run_manifest.json')['status'])
        self.assertFalse((directory / OUTPUTS['steps_csv']).exists())
        self.assertFalse(list(directory.glob('*.tmp')))

    def test_changed_export_or_canonical_data_is_rejected(self):
        directory, _ = self.run_project()
        ensure_exports(directory)
        (directory / OUTPUTS['steps_csv']).write_text('modified')
        with self.assertRaisesRegex(ValueError, 'export changed'):
            ensure_exports(directory)
        store = verified_events(directory)[2]
        with store.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            verified_events(directory)

    def test_sorted_rollback_restores_duplicate_intervals_and_missing_keys(self):
        sim = Simulation(config())
        existing = [(0, 2, 'OTHER'), (0, 2, 'OTHER'), (10, 20, 'OTHER')]
        key = sim._physical_edge_key('A', 'B')
        sim.edge_reservations[key] = list(existing)
        original = sim.edge_reservations[key]
        with RouteReservationTransaction(sim, sim.amrs[0], []):
            sim._reserve_edge('A', 'B', 0, 2, 'OTHER')
            sim._reserve_edge('A', 'B', 3, 4, 'R')
            sim._reserve_node('NEW', 1, 2, 'R')
        self.assertIs(original, sim.edge_reservations[key])
        self.assertEqual(existing, original)
        self.assertNotIn('NEW', sim.node_reservations)
        self.assertNotIn(('A', 'B'), sim.directed_edge_reservations)

    def test_nested_mutable_fallback_and_speculative_evidence_are_rolled_back(self):
        sim = Simulation(config(), verbose=True)
        value = {'nested': {'items': [1, 2]}}
        before = deepcopy(value)
        sequence = sim._evidence_sequence
        logs = list(sim.verbose_rows)
        with RouteReservationTransaction(sim, sim.amrs[0], []) as transaction:
            transaction.remember_dict(value)
            value['nested']['items'].append(3)
            sim.log_step(0, 'speculative_event', task_id='NOT-COMMITTED')
        self.assertEqual(before, value)
        self.assertEqual(sequence, sim._evidence_sequence)
        self.assertEqual(logs, list(sim.verbose_rows))
        sim.event_store.close()

    def test_sparse_store_preserves_presence_types_and_precision(self):
        path = self.root / 'events.sqlite'
        store = EventStore(path)
        rows = [dict(event_id='run:000000000001', event_type='A', sim_time_sec=1.00000001,
                     details='', task_id='T', value=False),
                dict(event_id='run:000000000002', event_type='A', sim_time_sec=1.00000002,
                     details='', task_id='T', value=0),
                dict(event_id='run:000000000003', event_type='B', sim_time_sec=2, value=None)]
        for row in rows:
            store.append(row)
        store.close()
        self.assertEqual(rows, list(store.iter_rows()))

    def test_compressed_events_preserve_unicode_types_precision_and_filters(self):
        from amr_event_store import iter_events
        path = self.root / 'compressed.sqlite'
        store = EventStore(path)
        rows = [dict(event_id=f'run:{i:012d}', event_type='move' if i % 2 else 'wait',
                     sim_time_sec=i, details=('Repeated ward → floor data ' * 100) + str(i),
                     value=False if i == 1 else 0, extra=None if i == 2 else '') for i in range(1, 5)]
        for i, row in enumerate(rows):
            store.append(row, precise_time=i + .000012345, playback=(i + 1) % 2 == 0)
        store.flush()
        self.assertIn('blob', {kind for kind, in store.connection.execute('SELECT typeof(data) FROM event_blocks')})
        store.close()
        self.assertEqual(rows, list(iter_events(path)))
        self.assertEqual(rows[1::2], list(iter_events(path, event_types=('wait',), playback_only=True)))
        self.assertEqual([i + .000012345 for i in range(4)],
                         [r['precise_time_sec'] for r in iter_events(path, ('precise_time_sec',))])
        self.assertEqual([], list(iter_events(path, event_types=('missing',))))

    def test_legacy_uncompressed_store_remains_readable(self):
        import json
        import sqlite3
        import zlib
        first = dict(event_id='run:000000000001', event_type='legacy', sim_time_sec=1,
                     task_id='A', details='', value=False)
        second = dict(first, event_id='run:000000000002', sim_time_sec=2, task_id='B',
                      details='Unicode ward →\n' * 100, value=0)
        changes = json.dumps([[2, 2], [3, {'s': 2}], [4, second['details']], [5, 0]])
        for version in (1, 2):
            path = self.root / f'legacy-{version}.sqlite'
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.executescript('''
                    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
                    CREATE TABLE layouts(id INTEGER PRIMARY KEY, keys TEXT, defaults TEXT);
                    CREATE TABLE symbols(id INTEGER PRIMARY KEY, value TEXT);
                    CREATE TABLE events(seq INTEGER PRIMARY KEY, sim_time REAL, layout INTEGER,
                                        data TEXT, kind INTEGER, playback INTEGER);
                ''')
                if version == 2:
                    db.execute('INSERT INTO metadata VALUES (?,?)', ('event_format_version', '2'))
                db.execute('INSERT INTO layouts VALUES (1,?,?)', (json.dumps(list(first)), json.dumps(list(first.values()))))
                db.executemany('INSERT INTO symbols VALUES (?,?)', [(1, 'legacy'), (2, 'B')])
                db.executemany('INSERT INTO events VALUES (?,?,1,?,1,1)',
                    [(1, 1, '[]'), (2, 2, changes if version == 1 else zlib.compress(changes.encode()))])
            reader = EventStore(path, readonly=True)
            try:
                self.assertEqual(version, reader.format_version)
                self.assertEqual([first, second], list(reader.iter_rows()))
            finally:
                reader.close()

    def test_compressed_speculative_rows_and_new_layouts_are_rolled_back(self):
        store = EventStore(self.root / 'rollback.sqlite')
        first = dict(event_id='run:000000000001', event_type='move', details='one')
        store.append(first)
        store.begin_stage()
        store.append(dict(event_id='run:000000000002', event_type='wait', details='two'))
        store.append(dict(event_id='run:000000000003', event_type='move', details='repeated ' * 1000))
        store.end_stage(False)
        last = dict(event_id='run:000000000002', event_type='wait', details='committed ' * 1000)
        store.append(last)
        store.close()
        self.assertEqual([first, last], list(store.iter_rows()))

    def test_compact_playback_and_investigation_create_no_csv_and_match_exports(self):
        from amr_results_investigation import load_investigation
        from visualiser.project_playback_panel import load_playback
        from visualiser.results_investigation_panel import load_review
        directory, _ = self.run_project()
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        direct = load_review(directory)
        _, _, _, playback = load_playback(directory)
        after = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(direct['complete_evidence'])
        exported = ensure_exports(directory)['steps_csv']
        expanded = load_investigation(exported)
        self.assertEqual(expanded['events'], direct['events'])
        self.assertEqual(expanded['tasks'], direct['tasks'])
        self.assertEqual(expanded['metrics'], direct['metrics'])
        from amr_sim_visualiser_pyside6 import SimulationLog
        legacy = SimulationLog()
        legacy.load(str(exported), parallel=False)
        self.assertEqual([e.row for e in legacy.events], [e.row for e in playback.events])

    def test_direct_compact_loading_honours_cancellation(self):
        from visualiser.project_playback_panel import load_playback
        from visualiser.results_investigation_panel import load_review
        directory, _ = self.run_project()
        for loader in (load_playback, load_review):
            with self.subTest(loader=loader.__name__), self.assertRaises(InterruptedError):
                loader(directory, cancel=lambda: True)
        self.assertFalse((directory / OUTPUTS['steps_csv']).exists())

    def test_compiled_cache_preserves_input_order_and_reuses_static_definitions(self):
        first = config()
        first['ordered_extension'] = dict(first=1, second=2)
        second = deepcopy(first)
        second['ordered_extension'] = dict(second=2, first=1)
        one, two = compile_runtime_inputs(first), compile_runtime_inputs(second)
        self.assertEqual(['second', 'first'], list(two.definitions['ordered_extension']))
        self.assertNotEqual(one.identity, two.identity)
        changed = deepcopy(first)
        changed['scenario_testing'] = dict(enabled=False, scenarios=[])
        three = compile_runtime_inputs(changed)
        self.assertIs(one.definitions['locations'], three.definitions['locations'])

    def test_entity_journal_restores_dynamic_attributes_and_commits_success(self):
        sim = Simulation(config())
        robot = sim.amrs[0]
        old = robot.available_time
        with RouteReservationTransaction(sim, robot, []):
            robot.available_time = 100
            robot.new_runtime_attribute = 'must disappear'
        self.assertEqual(old, robot.available_time)
        self.assertFalse(hasattr(robot, 'new_runtime_attribute'))
        self.assertFalse(hasattr(robot, '_reservation_journal'))
        with RouteReservationTransaction(sim, robot, []) as transaction:
            robot.available_time = 200
            transaction.committed = True
        self.assertEqual(200, robot.available_time)

    def test_geometric_append_rollback_preserves_history_object_identity(self):
        sim = Simulation(yielding_config())
        previous = dict(start=0, end=10, owner='other', envelope=(0, 0, 2, 2))
        sim.geometric_route_reservations[0] = [previous]
        history = sim.geometric_route_reservations[0]
        with RouteReservationTransaction(sim, sim.amrs[0], []) as transaction:
            transaction.remember_mapping_appends(sim.geometric_route_reservations, 0)
            history.append(dict(start=20, end=30, owner='tentative'))
        self.assertIs(history, sim.geometric_route_reservations[0])
        self.assertEqual([previous], history)
        self.assertIs(previous, history[0])

    def test_store_retains_committed_prefix_without_claiming_completion(self):
        path = self.root / 'prefix.sqlite'
        store = EventStore(path)
        for index in range(1001):
            store.append(dict(event_id=f'run:{index + 1:012d}', event_type='tick', sim_time_sec=index))
        store.connection.close()
        store.closed = True
        reader = EventStore(path, readonly=True)
        try:
            self.assertEqual(1000, len(reader))
        finally:
            reader.close()
        self.assertFalse(Path(str(path) + '.run.json').exists())

    def test_standalone_compact_evidence_exports_without_rerunning(self):
        path = self.root / 'cli.csv'
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config(), verbose=True, verbose_csv_path=str(path), defer_exports=True)
            sim.run()
            sim.write_verbose_csv()
        self.assertFalse(path.exists())
        with unittest.mock.patch.object(Simulation, 'run', side_effect=AssertionError('No rerun permitted')):
            outputs = ensure_exports(sim.event_store.path, ('steps_csv', 'transport_matrix_csv'))
        self.assertTrue(outputs['steps_csv'].exists())
        self.assertTrue(outputs['transport_matrix_csv'].exists())

    def test_background_expansion_has_progress_and_preserves_complete_run(self):
        from amr_export_execution import expand_in_process
        directory, _ = self.run_project()
        messages = []
        expand_in_process(directory, progress=messages.append)
        self.assertTrue(messages)
        self.assertTrue((directory / OUTPUTS['steps_csv']).exists())
        self.assertEqual('complete', read_json(directory / 'run_manifest.json')['status'])
        self.assertFalse((directory / '.exports.lock').exists())

    def test_cli_export_uses_contained_process_for_standalone_evidence(self):
        from amr_app import main
        path = self.root / 'cli.csv'
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config(), verbose=True, verbose_csv_path=str(path), defer_exports=True)
            sim.run()
            sim.write_verbose_csv()
            self.assertEqual(0, main(['--export-run', str(sim.event_store.path),
                                      '--outputs', 'steps_csv,transport_matrix_csv']))
        self.assertTrue(path.exists())
        self.assertTrue((self.root / 'cli_transport_matrix.csv').exists())
        self.assertFalse(list(self.root.glob('*.exports.lock')))
        from amr_export_execution import materialise_exports
        target = self.root / 'custom_steps.csv'
        outputs = materialise_exports(sim.event_store.path, ('steps_csv',),
                                      destinations={'steps_csv': target})
        self.assertEqual(target, outputs['steps_csv'])
        self.assertEqual(path.read_bytes(), target.read_bytes())
        self.assertTrue(Path(str(target) + '.run.json').exists())
        import json
        from simulator import main as simulator_main
        inputs = self.root / 'input.json'
        inputs.write_text(json.dumps(config()), encoding='utf-8')
        steps, matrix, playback = (self.root / name for name in ('command_steps.csv', 'transfers.csv', 'play.csv'))
        with unittest.mock.patch('sys.argv', ['simulator.py', '--config', str(inputs), '--verbose',
                '--verbose-csv', str(steps), '--transport-matrix-csv', str(matrix),
                '--visualiser-csv', str(playback)]), contextlib.redirect_stdout(io.StringIO()):
            simulator_main()
        self.assertTrue(all(output.exists() for output in (steps, matrix, playback)))
        self.assertTrue(Path(str(steps) + '.run.json').exists())

    def test_report_compatibility_reader_requests_contained_expansion(self):
        from amr_run_review import verified_inputs
        from amr_export_execution import expand_in_process
        directory, _ = self.run_project()
        with unittest.mock.patch('amr_export_execution.expand_in_process', wraps=expand_in_process) as expansion:
            _, _, path, _ = verified_inputs(directory)
        expansion.assert_called_once_with(directory, ('steps_csv',))
        self.assertTrue(path.exists())

    def test_cancellation_stops_expansion_process_and_removes_its_temporary_files(self):
        import json
        from amr_export_execution import expand_in_process
        from amr_stress_resources import process_alive
        from verification.benchmark_compact import configuration
        project = Project()
        project.save(self.root / 'long.amrproj', configuration('deliveries'))
        draft = PreparedRun(project, self.root / 'runs')
        checks = check_project(draft.config)
        checks.acknowledge_warnings()
        directory = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        stop, pids = [], []
        def feedback(message):
            for log in directory.glob('.export-*.log'):
                for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
                    if line.startswith('EXPORT '):
                        event = json.loads(line[7:])
                        if event.get('type') == 'ready':
                            pids.append(event['pid'])
            stop.append(True)
        with self.assertRaises(InterruptedError):
            expand_in_process(directory, cancel=lambda: bool(stop), progress=feedback)
        self.assertTrue(pids)
        self.assertTrue(all(not process_alive(pid) for pid in pids))
        self.assertFalse(list(directory.glob('*.tmp')))
        self.assertFalse((directory / '.exports.lock').exists())
        self.assertEqual('complete', verified_events(directory)[0]['status'])

    def test_compact_finalization_serializes_requested_verbose_csv_once(self):
        from amr_event_store import export_rows
        from amr_run_evidence import file_hash

        outputs = []
        for file_backed in (False, True):
            with self.subTest(file_backed=file_backed):
                csv_path = self.root / f'{file_backed}.csv'
                store = csv_path.with_suffix('.sqlite') if file_backed else None
                with contextlib.redirect_stdout(io.StringIO()):
                    sim = Simulation(config(), verbose=True, verbose_csv_path=str(csv_path), event_store_path=store)
                    sim.run()
                with patch('simulator.open', create=True, wraps=open) as opened, \
                        patch('amr_event_store.export_rows', wraps=export_rows) as exported:
                    sim.write_verbose_csv()
                direct_writes = [call for call in opened.call_args_list if call.args[:2] == (str(csv_path), 'w')]
                self.assertEqual(0 if file_backed else 1, len(direct_writes))
                self.assertEqual(1 if file_backed else 0, exported.call_count)
                sidecar = read_json(str(csv_path) + '.run.json')
                self.assertEqual(file_hash(csv_path), sidecar['log_sha256'])
                if not file_backed:
                    sim.event_store.close()
                outputs.append(csv_path.read_text(encoding='utf-8').replace(sim.run_id, '<run>'))
        self.assertEqual(*outputs)

    def test_detailed_completed_run_exports_all_reports(self):
        from tests.test_geometric_simulation import geometric_config
        project = Project()
        project.save(self.root / 'detailed.amrproj', geometric_config())
        draft = PreparedRun(project, self.root / 'runs')
        checks = check_project(draft.config)
        checks.acknowledge_warnings()
        directory = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        outputs = ensure_exports(directory, OUTPUTS)
        self.assertEqual(len(OUTPUTS), len(outputs))

    def test_exact_event_time_is_available_without_csv_rounding(self):
        from amr_event_store import iter_events
        path = self.root / 'precise.csv'
        value = config()
        value['tasks'][0]['release_time'] = .0002
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(value, verbose=True, verbose_csv_path=str(path), defer_exports=True)
            sim.run()
            sim.write_verbose_csv()
        released = list(iter_events(sim.event_store.path, ('precise_time_sec', 'sim_time_sec'),
                                    event_types=('task_released',)))
        self.assertEqual(.0002, released[0]['precise_time_sec'])
        self.assertEqual(0, released[0]['sim_time_sec'])


if __name__ == '__main__':
    unittest.main()
