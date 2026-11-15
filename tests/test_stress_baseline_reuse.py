"""A saved normal simulation must replace only an equivalent verified baseline."""
import contextlib
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from amr_project import Project
from amr_project_runs import PreparedRun, execute, read_json, write_json, link_run
from amr_run_evidence import config_hash
from amr_scenario_study import (create_study, evaluate, reusable_baseline, run_metrics,
                                scenario_config, validate_study, verify_trial_inputs)
from tests.test_scenario_study import config, event
from visualiser.project_checks import check_project


class StressBaselineReuseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = config()
        self.project = Project()
        self.project.save(self.root / 'design.amrproj', self.config)

    def normal_run(self, config=None, root=None):
        if config is not None:
            self.project.save(self.project.path, config)
        draft = PreparedRun(self.project, root or self.project.results_root())
        report = check_project(draft.config)
        report.acknowledge_warnings()
        directory = draft.commit(report)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        return directory

    def study(self, name='study', config=None):
        self.path = self.root / (name + '.stress.json')
        return create_study(config or self.config, self.path, {'trial_budget': 1}, project=self.project)

    def test_reuses_normal_run_without_launching_baseline_worker_and_preserves_evidence(self):
        directory = self.normal_run()
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        self.study()
        from amr_stress_execution import TrialPool
        start = TrialPool._start
        launched = []
        def track(pool, spec):
            launched.append(spec['id'])
            return start(pool, spec)
        messages = []
        with patch.object(TrialPool, '_start', track):
            state = evaluate(self.path, feedback=messages.append)
        baseline = state['results']['baseline']
        self.assertTrue(baseline['reused'])
        self.assertEqual(str(directory), baseline['directory'])
        self.assertEqual(run_metrics(directory), baseline['metrics'])
        self.assertNotIn('baseline', launched)
        self.assertTrue(launched)
        self.assertTrue(any('Reusing existing' in m['phase'] for m in messages))
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()})
        validate_study(state, self.config)
        resumed = evaluate(self.path)
        self.assertEqual(baseline, resumed['results']['baseline'])
        create_study(self.config, self.root / 'fresh.stress.json', {'trial_budget': 1})
        fresh = evaluate(self.root / 'fresh.stress.json')
        self.assertEqual(fresh['ranking'], state['ranking'])
        self.assertEqual(fresh['coverage'], state['coverage'])
        self.assertEqual(fresh['results']['baseline']['metrics']['obligations'], baseline['metrics']['obligations'])

    def test_linked_run_outside_results_root_is_found(self):
        directory = self.normal_run(root=self.root / 'external')
        link_run(self.project, directory)
        record = reusable_baseline(self.study())
        self.assertEqual(str(directory), record['directory'])

    def test_changed_inputs_are_not_reused(self):
        self.normal_run()
        changed = deepcopy(self.config)
        changed['amrs'][0]['speed_m_per_sec'] = 1
        self.assertIsNone(reusable_baseline(self.study(config=changed)))

    def change_recorded_sources(self, directory, names):
        path = directory / 'run_manifest.json'
        manifest = read_json(path)
        for name in names:
            manifest['software']['files'][name] = 'previous source digest'
        manifest['software']['sha256'] = config_hash(manifest['software']['files'])
        write_json(path, manifest)
        evidence_path = directory / (manifest.get('canonical_events', 'simulation_steps.csv') + '.run.json')
        evidence = read_json(evidence_path)
        evidence['software'] = deepcopy(manifest['software'])
        write_json(evidence_path, evidence)
        self.sync_recorded_software(manifest)

    def sync_recorded_software(self, manifest):
        settings = deepcopy(self.project.external_results)
        for reference in settings['runs']:
            if reference['run_key'] == manifest['run_key']:
                reference['software_sha256'] = manifest['software']['sha256']
        self.project._save_external_results(settings)

    def test_stress_only_source_changes_reuse_baseline_without_launching_it(self):
        directory = self.normal_run()
        self.change_recorded_sources(directory, ['amr_scenario_study.py', 'amr_stress_execution.py',
                                                'visualiser/scenario_stress_panel.py'])
        state = self.study()
        record = reusable_baseline(state)
        self.assertEqual(str(directory), record['directory'])
        verify_trial_inputs(state, record)
        from amr_stress_execution import TrialPool
        start = TrialPool._start
        launched = []
        def track(pool, spec):
            launched.append(spec['id'])
            return start(pool, spec)
        with patch.object(TrialPool, '_start', track):
            finished = evaluate(self.path)
        self.assertTrue(finished['results']['baseline']['reused'])
        self.assertNotIn('baseline', launched)
        validate_study(finished)

    def test_shared_source_changes_still_require_a_new_baseline(self):
        directory = self.normal_run()
        for name in ('simulator.py', 'amr_run_evidence.py', 'visualiser/models.py', 'amr_stress_resources.py'):
            with self.subTest(source=name):
                manifest = read_json(directory / 'run_manifest.json')
                evidence_path = directory / (manifest.get('canonical_events', 'simulation_steps.csv') + '.run.json')
                evidence = read_json(evidence_path)
                self.change_recorded_sources(directory, [name])
                self.assertIsNone(reusable_baseline(self.study(name)))
                write_json(directory / 'run_manifest.json', manifest)
                write_json(evidence_path, evidence)
                self.sync_recorded_software(manifest)

    def test_logging_and_stress_settings_do_not_prevent_reuse(self):
        self.normal_run()
        changed = deepcopy(self.config)
        changed['simulation'].update(parallel_routing=True, routing_worker_threads=8, scenario_enhanced_logging=True)
        changed['scenario_testing'] = dict(enabled=False, enhanced_logging=True,
            active_scenario='Unused', scenarios=[dict(name='Unused', events=[event()])], stress_test={'seed': 13})
        self.assertIsNotNone(reusable_baseline(self.study(config=changed)))

    def test_disrupted_simulation_is_not_reused(self):
        self.normal_run(config=scenario_config(self.study()['config'], [event()], 'Block'))
        self.assertIsNone(reusable_baseline(self.study('normal')))

    def test_incomplete_or_old_software_run_is_not_reused(self):
        directory = self.normal_run()
        state = self.study()
        path = directory / 'run_manifest.json'
        original = read_json(path)
        for status in ('prepared', 'running', 'failed', 'cancelled', 'partial'):
            manifest = deepcopy(original)
            manifest['status'] = status
            write_json(path, manifest)
            self.assertIsNone(reusable_baseline(state), status)
        manifest = deepcopy(original)
        manifest['software']['sha256'] = 'old'
        write_json(path, manifest)
        self.assertIsNone(reusable_baseline(state))

    def test_missing_precise_service_capability_is_not_reused(self):
        directory = self.normal_run()
        state = self.study()
        canonical = read_json(directory / 'run_manifest.json').get('canonical_events', 'simulation_steps.csv')
        path = directory / (canonical + '.run.json')
        evidence = read_json(path)
        evidence['event_capabilities'].remove('stress_task_obligations_v1')
        write_json(path, evidence)
        self.assertIsNone(reusable_baseline(state))

    def test_corrupt_log_is_not_reused_and_reused_evidence_is_rechecked(self):
        directory = self.normal_run()
        state = self.study()
        record = reusable_baseline(state)
        log = directory / read_json(directory / 'run_manifest.json').get('canonical_events', 'simulation_steps.csv')
        with log.open('a', encoding='utf-8') as stream:
            stream.write('changed\n')
        self.assertIsNone(reusable_baseline(state))
        with self.assertRaises(ValueError):
            verify_trial_inputs(state, record)

    def test_no_project_and_cancelled_discovery_fall_back(self):
        self.normal_run()
        state = self.study()
        self.assertIsNone(reusable_baseline(state, cancelled=lambda: True))
        state.pop('source_project')
        self.assertIsNone(reusable_baseline(state))

    def test_newest_invalid_run_falls_back_to_older_matching_run(self):
        matching = self.normal_run()
        changed = deepcopy(self.config)
        changed['amrs'][0]['speed_m_per_sec'] = 1
        self.normal_run(config=changed)
        self.assertEqual(str(matching), reusable_baseline(self.study())['directory'])

    def test_changed_or_corrupt_drawings_prevent_reuse(self):
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'drawing contents')
        self.config['floor_dxf_files'] = [dict(floor=0, filepath=str(drawing))]
        directory = self.normal_run(config=self.config)
        state = self.study()
        self.assertIsNotNone(reusable_baseline(state))
        frozen = next((directory / 'drawings').iterdir())
        original = frozen.read_bytes()
        frozen.write_bytes(b'corrupt')
        self.assertIsNone(reusable_baseline(state))
        frozen.write_bytes(original)
        drawing.write_bytes(b'new drawing contents')
        self.assertIsNone(reusable_baseline(self.study('changed-drawing')))

    def test_failed_service_baseline_is_reused_and_stops_disruption_trials(self):
        from tests.test_scenario_study import deferred_config
        self.config = deferred_config()
        directory = self.normal_run(config=self.config)
        self.study()
        with patch('amr_stress_execution.TrialPool._start') as start:
            with self.assertRaisesRegex(ValueError, 'Baseline has incomplete service'):
                evaluate(self.path)
        start.assert_not_called()
        state = read_json(self.path)
        self.assertEqual(['baseline'], list(state['results']))
        self.assertEqual(str(directory), state['results']['baseline']['directory'])
        self.assertTrue(state['results']['baseline']['reused'])


if __name__ == '__main__':
    unittest.main()
