"""Mode claims must describe immutable run inputs, including old/partial runs."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from amr_project import Project
from amr_project_runs import (MANIFEST, OUTPUTS, PreparedRun, execute, finish_run,
                              read_json, validate_run_inputs, write_json)
from amr_results_investigation import load_investigation
from amr_run_evidence import config_hash, verified_simulation_mode, write_run_evidence
from amr_run_review import verified_inputs
from amr_simulation_modes import resolve_simulation_mode
from report.amr_energy_evidence import read_energy_evidence
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_motion_dynamics_simulation import dynamics_config
from visualiser.project_checks import check_project


class SimulationModeEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = Project()

    def run_case(self, *, geometric=False, partial=False, explicit_mode=None):
        config = dynamics_config() if geometric else reference_config()
        config['tasks'] = [{'id': 'T', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box'}]
        if explicit_mode is not None:
            config['simulation']['mode'] = explicit_mode
            config['simulation']['motion_model'] = 'geometric_v1' if explicit_mode == 'detailed' else 'legacy'
        if explicit_mode == 'detailed':
            config['geometry']['clearances'] = dict(wall_m=0., robot_m=.1)
            config['geometry']['initial_placements'] = [dict(amr_id='R-1', location='A', heading_deg=0.)]
            movement = config['amrs'][0]['movement']
            movement['schema_version'] = 2
            for state in ('empty', 'loaded'):
                movement[state]['reverse_allowed'] = True
            config['amrs'][0]['manoeuvring']['reference_point'] = dict(longitudinal_mm=0., lateral_mm=0.,
                timing_reference='turning_reference_point', pivot_axis='body_centre')
        self.project.save(self.root/'model.amrproj', config)
        draft = PreparedRun(self.project, self.root/'results')
        checks = check_project(draft.config, base_path=draft.directory)
        checks.acknowledge_warnings()
        self.assertTrue(checks.can_run(draft.config), checks.to_dict())
        directory = draft.commit(checks)
        original = Simulation._handle_event

        def handle(sim, event):
            if event.event_type == 'mode_test_stop':
                termination = dict(schema_version=1, reason='blocked', stop_time_sec=event.time,
                    message='Controlled partial stop', amr_ids=['R-1'], task_ids=['T'])
                termination['event_id'] = sim.log_step(event_time=event.time,
                    event_type='geometric_simulation_stopped', start_time=event.time,
                    end_time=event.time, status='blocked', details=json.dumps(termination, sort_keys=True))
                sim.geometric_termination = termination
                return
            original(sim, event)
            if partial and event.event_type == 'task_release':
                sim.push_event(3, 'mode_test_stop', {})

        with patch.object(Simulation, '_handle_event', handle), contextlib.redirect_stdout(io.StringIO()):
            simulation = execute(directory)
        return directory, simulation

    @staticmethod
    def evidence_path(directory):
        return directory/(OUTPUTS['steps_csv']+'.run.json')

    def test_mode_is_recorded_in_manifest_evidence_and_investigation(self):
        directory, sim = self.run_case()
        expected = resolve_simulation_mode(sim._evidence_inputs)
        self.assertEqual('simple', expected['mode'])
        self.assertEqual(expected, read_json(directory/MANIFEST)['simulation_mode'])
        self.assertEqual(expected, read_json(self.evidence_path(directory))['simulation_mode'])
        self.assertEqual(expected, verified_inputs(directory)[0]['simulation_mode'])
        self.assertEqual(expected, load_investigation(directory)['simulation_mode'])

    def test_explicit_simple_and_detailed_modes_are_preserved(self):
        for mode in ('simple', 'detailed'):
            with self.subTest(mode=mode):
                directory, sim = self.run_case(geometric=mode == 'detailed', explicit_mode=mode)
                expected = resolve_simulation_mode(sim._evidence_inputs)
                self.assertEqual(mode, expected['mode'])
                self.assertEqual('explicit', expected['selection'])
                self.assertEqual(expected, verified_inputs(directory)[0]['simulation_mode'])
                self.assertEqual(expected, load_investigation(directory)['simulation_mode'])

    def test_project_and_runtime_edits_do_not_relabel_finished_run(self):
        directory, sim = self.run_case()
        expected = resolve_simulation_mode(sim._evidence_inputs)
        changed = dynamics_config()
        self.project.save(self.project.path, changed)
        sim.config['simulation']['motion_model'] = 'geometric_v1'
        write_run_evidence(sim, directory/OUTPUTS['steps_csv'])
        self.assertEqual(expected, read_json(self.evidence_path(directory))['simulation_mode'])
        self.assertEqual(expected, verified_inputs(directory)[0]['simulation_mode'])
        self.assertEqual(expected, load_investigation(directory)['simulation_mode'])

    def test_omitted_old_fields_derive_compatibility_without_changing_bytes(self):
        directory, sim = self.run_case(geometric=True)
        expected = resolve_simulation_mode(sim._evidence_inputs)
        self.assertEqual('geometric_compatibility', expected['mode'])
        for target in (directory/MANIFEST, self.evidence_path(directory)):
            data = read_json(target)
            data.pop('simulation_mode')
            write_json(target, data)
        before = {p: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        self.assertEqual(expected, verified_inputs(directory)[0]['simulation_mode'])
        self.assertEqual(expected, load_investigation(directory)['simulation_mode'])
        read_energy_evidence(directory/OUTPUTS['steps_csv'])
        self.assertEqual(before, {p: p.read_bytes() for p in directory.iterdir() if p.is_file()})

    def test_manifest_contradiction_is_rejected_at_managed_boundary(self):
        directory, _ = self.run_case()
        manifest = read_json(directory/MANIFEST)
        manifest['simulation_mode']['mode'] = 'detailed'
        write_json(directory/MANIFEST, manifest)
        for loader in (validate_run_inputs, verified_inputs):
            with self.subTest(loader=loader.__name__), self.assertRaisesRegex(ValueError, 'simulation mode'):
                loader(directory)

    def test_evidence_contradiction_is_rejected_in_review_and_raw_reporting(self):
        directory, _ = self.run_case()
        evidence = read_json(self.evidence_path(directory))
        evidence['simulation_mode']['mode'] = 'detailed'
        write_json(self.evidence_path(directory), evidence)
        for loader, source in ((verified_inputs, directory), (load_investigation, directory),
                               (read_energy_evidence, directory/OUTPUTS['steps_csv'])):
            with self.subTest(loader=loader.__name__), self.assertRaisesRegex(ValueError, 'simulation mode'):
                loader(source)
        self.assertEqual('failed', finish_run(directory, 0)['status'])

    def test_partial_run_has_same_frozen_mode_checks(self):
        directory, sim = self.run_case(geometric=True, partial=True, explicit_mode='detailed')
        expected = resolve_simulation_mode(sim._evidence_inputs)
        manifest = verified_inputs(directory, allow_partial=True)[0]
        self.assertEqual('partial', manifest['status'])
        self.assertEqual(expected, manifest['simulation_mode'])
        self.assertEqual(expected, load_investigation(directory)['simulation_mode'])
        evidence = read_json(self.evidence_path(directory))
        evidence['simulation_mode']['traffic_model'] = 'whole_route_v1'
        write_json(self.evidence_path(directory), evidence)
        with self.assertRaisesRegex(ValueError, 'simulation mode'):
            verified_inputs(directory, allow_partial=True)

    def test_strict_record_comparison_rejects_malformed_types_and_extra_claims(self):
        config = reference_config()
        original = copy.deepcopy(config)
        expected = resolve_simulation_mode(config)
        cases = [None, 'simple', dict(expected, schema_version=True),
                 dict(expected, selection='explicit'), dict(expected, certified=True)]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                verified_simulation_mode({'simulation_mode': value}, config)
        metadata = {}
        self.assertEqual(expected, verified_simulation_mode(metadata, config))
        self.assertEqual({}, metadata)
        self.assertEqual(original, config)

    def test_unknown_legacy_mode_is_readable_but_not_trusted(self):
        directory, _ = self.run_case()
        evidence = read_json(self.evidence_path(directory))
        evidence.pop('simulation_mode')
        evidence['frozen_inputs']['simulation']['motion_model'] = 'unknown_legacy_model'
        evidence['config_sha256'] = config_hash(evidence['frozen_inputs'])
        write_json(self.evidence_path(directory), evidence)
        review = load_investigation(directory/OUTPUTS['steps_csv'])
        self.assertIsNone(review['simulation_mode'])
        self.assertFalse(review['complete_evidence'])
        self.assertIsNone(review['frozen_inputs'])
        energy = read_energy_evidence(directory/OUTPUTS['steps_csv'])
        self.assertFalse(energy['sources']['amr_battery']['known'])


if __name__ == '__main__':
    unittest.main()
