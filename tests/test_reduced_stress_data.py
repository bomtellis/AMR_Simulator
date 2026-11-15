"""Reduced trials reconstruct full evidence and history survives dialog sessions."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest
import zlib

from amr_event_store import EventStore, iter_events
from amr_event_delta import difference, restore, report_blob, read_report_blob, packed
from amr_project import Project
from amr_project_runs import PreparedRun, execute
from amr_run_exports import ensure_exports, load_report_state
from amr_run_review import verified_events
from amr_scenario_study import create_study, default_settings, evaluate, scenario_config, run_metrics, validate_study
from amr_stress_history import discover_studies, remember_study
from tests.test_compact_execution import normalise
from tests.test_scenario_study import config, event
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class ReducedStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_typed_nested_patches_preserve_values_and_order(self):
        cases = [(1, True), (1.0, 1), (-0.0, 0.0), ([True], [1]),
                 ({'x': [1, 2], 'y': 'unchanged' * 100}, {'x': [1, 3], 'y': 'unchanged' * 100}),
                 ({'b': 2, 'a': 1}, {'a': 1, 'b': 2}), (None, ''), ('', None)]
        for value, original in cases:
            self.assertEqual(packed(value), packed(restore(difference(value, original), original)))

    def fixture(self):
        randomizer = random.Random(42)
        baseline = self.root / 'baseline.sqlite'
        rows = [dict(event_id=f'base:{i:06d}', event_type='move', sim_time_sec=i / 3,
                     task_id=f'T{i}', details=''.join(randomizer.choices('abcdef0123456789', k=1500)),
                     nested={'values': [i, True, 'ward → "A"']}) for i in range(1, 301)]
        store = EventStore(baseline)
        for row in rows:
            store.append(row)
        payload = {'common': [dict(id=i, value=row['details']) for i, row in enumerate(rows)]}
        store.connection.execute('INSERT INTO metadata VALUES (?,?)', ('report_state', report_blob(store, 'report_state', payload)))
        store.close()
        return baseline, rows, payload

    def test_inserted_events_rollback_filters_and_size(self):
        baseline, rows, payload = self.fixture()
        delta = EventStore(self.root / 'delta.sqlite', baseline=baseline)
        full = EventStore(self.root / 'full.sqlite')
        expected, times, playback = [], [], []
        for i, original in enumerate(rows):
            if i == 70:
                delta.begin_stage()
                delta.append(dict(original, event_id='trial:999999', details='rolled back'))
                delta.begin_stage()
                delta.append(dict(original, event_id='trial:999998'))
                delta.end_stage(True)
                delta.end_stage(False)
            additions = [dict(event_id='ignored', event_type='scenario', sim_time_sec=0, details='disruption')] if i % 17 == 0 else []
            additions.append(dict(original))
            for row in additions:
                seq = 3 * (len(expected) + 1)
                row['event_id'] = f'trial:{seq:06d}'
                if row['event_type'] == 'move' and i % 13 == 0:
                    row['sim_time_sec'] += .5
                    row['nested'] = {'values': [i, 1, 'changed']}
                exact, play = float(seq) + .00000001, seq % 2 == 0
                for store in (full, delta):
                    store.append(row, precise_time=exact, playback=play)
                expected.append(row)
                times.append(exact)
                playback.append(play)
        self.assertEqual(expected, list(delta.iter_rows()))
        for store in (full, delta):
            store.flush()
        patches = [entry[1] for blob, in delta.connection.execute('SELECT data FROM event_blocks')
                   for entry in json.loads(zlib.decompress(blob))]
        self.assertGreater(sum(isinstance(value, dict) for value in patches), 250)
        updated = deepcopy(payload)
        updated['common'][150]['value'] = 'changed'
        blob = report_blob(delta, 'report_state', updated)
        self.assertTrue(blob.startswith(b'AMRD1'))
        self.assertEqual(updated, read_report_blob(delta, 'report_state', blob))
        delta.close()
        full.close()
        self.assertLess(delta.path.stat().st_size, full.path.stat().st_size / 3)
        self.assertEqual(expected, list(iter_events(delta.path)))
        self.assertEqual([dict(precise_time_sec=t) for t in times], list(iter_events(delta.path, ['precise_time_sec'])))
        self.assertEqual([row for row, play in zip(expected, playback) if play], list(iter_events(delta.path, playback_only=True)))
        self.assertEqual([row for row in expected if row['event_type'] == 'move'], list(iter_events(delta.path, event_types=['move'])))
        changed = next(iter_events(delta.path))
        changed['details'] = 'mutated'
        self.assertEqual(expected, list(iter_events(delta.path)))

    def test_baseline_integrity_portability_and_chain_rejection(self):
        baseline, rows, _ = self.fixture()
        trial_dir = self.root / 'trial'
        trial_dir.mkdir()
        path = trial_dir / 'events.sqlite'
        store = EventStore(path, baseline=baseline)
        for row in rows:
            store.append(dict(row, event_id=row['event_id'].replace('base:', 'trial:')))
        store.close()
        with self.assertRaisesRegex(ValueError, 'full baseline'):
            EventStore(self.root / 'chain.sqlite', baseline=path)
        relocated = self.root / 'relocated'
        relocated.mkdir()
        shutil.copy2(baseline, relocated / baseline.name)
        shutil.copytree(trial_dir, relocated / 'trial')
        self.assertEqual(list(iter_events(path)), list(iter_events(relocated / 'trial' / path.name)))
        baseline.rename(baseline.with_suffix('.missing'))
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            list(iter_events(path))
        baseline.with_suffix('.missing').rename(baseline)
        with baseline.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum changed'):
            list(iter_events(path))

    def run_project(self, cfg, label, baseline=None):
        project = Project()
        project.save(self.root / (label + '.amrproj'), cfg)
        draft = PreparedRun(project, self.root / 'runs')
        checks = check_project(draft.config)
        checks.acknowledge_warnings()
        directory = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            sim = execute(directory, event_baseline=baseline)
        return directory, sim

    def test_real_disruption_matches_full_events_exports_reports_and_metrics(self):
        cfg = JsonStore(config()).data
        base_dir, base = self.run_project(scenario_config(cfg, [], 'Normal operation'), 'base')
        disrupted = scenario_config(cfg, [event(end=30)], 'Disruption')
        full_dir, full = self.run_project(disrupted, 'full')
        delta_dir, delta = self.run_project(disrupted, 'delta', base.event_store.path)
        self.assertEqual(4, delta.event_store.format_version)
        verified_events(delta_dir, allow_partial=True)
        self.assertEqual(normalise(list(full.verbose_rows), full.run_id), normalise(list(delta.verbose_rows), delta.run_id))
        baseline_metrics = run_metrics(base_dir)
        full_metrics, delta_metrics = run_metrics(full_dir, baseline_metrics), run_metrics(delta_dir, baseline_metrics)
        full_metrics.pop('run_key')
        delta_metrics.pop('run_key')
        self.assertEqual(full_metrics, delta_metrics)
        for output in ('steps_csv', 'visualiser_csv', 'transport_matrix_csv', 'route_lengths_csv', 'scenario_impact_csv'):
            left = ensure_exports(full_dir, (output,))[output].read_text(encoding='utf-8')
            right = ensure_exports(delta_dir, (output,))[output].read_text(encoding='utf-8')
            self.assertEqual(normalise(left, full.run_id), normalise(right, delta.run_id))
        self.assertEqual(list(load_report_state(full.event_store.path).completed_task_records),
                         list(load_report_state(delta.event_store.path).completed_task_records))

    def test_reduced_parallel_study_resumes_and_preserves_full_baseline(self):
        cfg = config()
        path = self.root / 'reduced.stress.json'
        settings = {**default_settings(cfg), 'data_mode': 'reduced', 'trial_budget': 1, 'workers': 2}
        create_study(cfg, path, settings)
        with contextlib.redirect_stdout(io.StringIO()):
            state = evaluate(path)
        self.assertEqual('complete', state['status'], state.get('error'))
        for record in state['results'].values():
            events = verified_events(record['directory'], allow_partial=True)[2]
            store = EventStore(events, readonly=True)
            self.assertEqual(3 if record['kind'] == 'baseline' else 4, store.format_version)
            store.close()
        validate_study(state)
        with contextlib.redirect_stdout(io.StringIO()):
            resumed = evaluate(path)
        self.assertEqual(state['results'], resumed['results'])

    def test_reduced_study_reuses_existing_normal_run(self):
        from amr_project_runs import link_run
        directory, simulation = self.run_project(config(), 'existing')
        project = Project.open(self.root / 'existing.amrproj')
        link_run(project, directory)
        before = simulation.event_store.path.read_bytes()
        path = self.root / 'reuse.stress.json'
        create_study(config(), path, {'data_mode': 'reduced', 'trial_budget': 1}, project=project)
        with contextlib.redirect_stdout(io.StringIO()):
            state = evaluate(path)
        self.assertEqual('complete', state['status'], state.get('error'))
        self.assertTrue(state['results']['baseline']['reused'])
        self.assertEqual(str(directory), state['results']['baseline']['directory'])
        self.assertEqual(before, simulation.event_store.path.read_bytes())
        validate_study(state)


class StressHistoryTests(unittest.TestCase):
    setUp = ReducedStorageTests.setUp

    def test_discovers_legacy_backups_and_external_studies_after_reopen(self):
        source = self.root / 'design.amrproj'
        project = Project()
        project.save(source, config())
        path = self.root / 'design.stress.json'
        first = create_study(config(), path, project=project)
        second = create_study(config(), path, project=project, overwrite=True)
        external = self.root / 'elsewhere' / 'external.stress.json'
        create_study(config(), external, project=project)
        legacy = self.root / 'legacy.stress.json'
        create_study(config(), legacy)
        unrelated = Project()
        unrelated.save(self.root / 'other.amrproj', config())
        create_study(config(), self.root / 'other.stress.json', project=unrelated)
        entries = discover_studies(source, project_id=project.project_id)
        paths = {item['path'] for item in entries}
        self.assertEqual({path, Path(second['previous_study']), external, legacy}, paths)
        self.assertNotEqual(first['root'], second['root'])
        missing = self.root / 'missing.stress.json'
        remember_study(source, missing)
        self.assertEqual('Missing or unreadable', next(item['status'] for item in
            discover_studies(source, project_id=project.project_id) if item['path'] == missing))

    def test_legacy_settings_remain_valid_and_openable(self):
        from amr_scenario_study import search_settings, config_hash, validate_study_document
        path = self.root / 'old.stress.json'
        state = create_study(config(), path)
        state['settings'].pop('data_mode')
        state['settings_sha256'] = config_hash(search_settings(state['settings']))
        validate_study_document(state)
        validate_study(state)


class ReducedStressUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.setUpClass()
        cls.app = ScenarioStressUiTests.app

    def setUp(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.setUp(self)

    def close_windows(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.close_windows(self)

    def test_mode_persists_and_previous_study_opens_without_picker(self):
        self.editor.current_json_path = str(self.root / 'design.json')
        self.dialog.data_mode.setCurrentIndex(self.dialog.data_mode.findData('reduced'))
        self.dialog.save_settings()
        self.assertEqual('reduced', self.editor.store.scenario_testing()['stress_test']['data_mode'])
        path = self.root / 'old.stress.json'
        state = create_study(self.editor.store.data, path, self.dialog.settings())
        self.dialog.refresh_history()
        self.assertEqual(1, self.dialog.history.rowCount())
        self.dialog.open_previous_study()
        self.assertEqual(path, self.dialog.path)
        self.assertEqual(state['root'], self.dialog.study['root'])
        self.assertEqual('reduced', self.dialog.data_mode.currentData())
        self.assertEqual(2, self.dialog.tabs.currentIndex())
        self.dialog.process = object()
        try:
            self.dialog.refresh()
            self.assertFalse(self.dialog.open_history_button.isEnabled())
            self.assertFalse(self.dialog.data_mode.isEnabled())
        finally:
            self.dialog.process = None
