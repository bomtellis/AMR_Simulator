"""Independent depletion/reuse expectations for optional runtime provisioning."""
import contextlib
import copy
import io
import unittest
from simulator import Simulation
from amr_sim_models import Task
from amr_simulation_inputs import resolved_simulation_settings, simulation_input_findings
from tests.test_multi_stop_route_rules import multi_route_config


class SourceReplenishmentTests(unittest.TestCase):
    def sim(self, enabled=True, verbose=True):
        cfg = multi_route_config()
        cfg['simulation']['spawn_payloads_when_empty'] = enabled
        cfg['simulation']['max_task_deferral_minutes'] = 1
        return Simulation(cfg, verbose=verbose)

    def task(self, name='T', pickup='A', dropoff='B', **kwargs):
        return Task(name, pickup, dropoff, 'Box', is_return_task=True, **kwargs)

    def test_default_and_boolean_contract(self):
        self.assertFalse(resolved_simulation_settings({})['spawn_payloads_when_empty'])
        self.assertTrue(simulation_input_findings({'simulation': {'spawn_payloads_when_empty': 'perhaps'}}))

    def test_disabled_shortage_blocks(self):
        sim = self.sim(False)
        self.assertFalse(sim._plan_payload_claims([self.task()], reserve=True))
        with self.assertRaises(RuntimeError):
            sim._pickup_payload_instance_for_task(self.task())
        self.assertFalse(sim.source_payload_additions)

    def test_estimates_and_commits_do_not_create_physical_stock(self):
        sim = self.sim()
        tasks = [self.task('T1'), self.task('T2')]
        before = copy.deepcopy(vars(sim.payload_instance_store))
        for reserve in (False, True):
            self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve))
            self.assertEqual(before, vars(sim.payload_instance_store))
            self.assertFalse(sim.source_payload_additions)
        for task in tasks:
            sim._pickup_payload_instance_for_task(task, 3)
        self.assertEqual(2, sim.source_payload_additions['Box'])
        self.assertEqual(2, len({t.payload_instance_id for t in tasks}))

    def test_stock_reused_first_and_reserved_stock_not_stolen(self):
        sim = self.sim()
        sim.payload_instance_store.store('A', 'Box', 'EXISTING')
        first, second = self.task('T1'), self.task('T2')
        self.assertTrue(sim._plan_payload_claims([first, second], reserve=True))
        sim._pickup_payload_instance_for_task(second, 2)
        self.assertTrue(sim.payload_instance_store.has_instance_at('A', 'EXISTING'))
        sim._pickup_payload_instance_for_task(first, 3)
        self.assertEqual('EXISTING', first.payload_instance_id)
        self.assertEqual(1, sim.source_payload_additions['Box'])

    def test_exact_identity_never_cloned(self):
        sim = self.sim()
        task = self.task(payload_instance_id='MISSING')
        self.assertFalse(sim._pickup_instance_available(task))
        self.assertFalse(sim._plan_payload_claims([task], reserve=True))

    def test_empty_return_does_not_reuse_full_bin(self):
        sim = self.sim()
        sim.payload_instance_store.store('A', 'Box', 'FULL', metadata={'container_state':'full'})
        task = self.task(task_source='task_generation_return')
        sim._pickup_payload_instance_for_task(task, 2)
        self.assertNotEqual('FULL', task.payload_instance_id)
        self.assertEqual('empty', sim.payload_instance_store._known_instances[task.payload_instance_id].metadata['container_state'])

    def test_run_reconciles_creation_and_reuse(self):
        sim = self.sim()
        for task in [self.task('T1'), self.task('T2', 'B', 'A', release_time=20),
                     self.task('T3', release_time=40)]:
            sim.schedule_task_release(task)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(3, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(1, sim.source_payload_additions['Box'])
        rows = [r for r in sim.verbose_rows if r['event_type'] == 'payload_source_spawned']
        self.assertEqual(1, len(rows))
        self.assertEqual('A', rows[0]['from_location'])
        sim._append_payload_population_summary_rows()
        summary = next(r for r in sim.verbose_rows if r['event_type']=='payload_population_summary' and r['payload']=='Box')
        self.assertEqual(1, summary['payload_source_additions'])
        self.assertEqual(1, summary['payload_runtime_population'])
        self.assertEqual(1, summary['payload_known_instances'])

    def test_nonverbose_retains_addition_counts(self):
        sim = self.sim(verbose=False)
        sim._pickup_payload_instance_for_task(self.task(), 0)
        self.assertEqual(1, sim.source_payload_additions['Box'])

    def test_settings_roundtrip(self):
        import os
        import sys
        from pathlib import Path
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        # Match the desktop entry point without depending on another UI test
        # having bootstrapped its flat visualiser module imports first.
        visualiser = str(Path(__file__).resolve().parents[1] / 'visualiser')
        if visualiser not in sys.path:
            sys.path.insert(0, visualiser)
        from PySide6.QtWidgets import QApplication
        from visualiser.dialogs import SimulationSettingsDialog
        app = QApplication.instance() or QApplication([])
        dialog = SimulationSettingsDialog(None, {})
        try:
            self.assertFalse(dialog.spawn_payloads_when_empty_check.isChecked())
            dialog.spawn_payloads_when_empty_check.setChecked(True)
            dialog.accept()
            self.assertTrue(dialog.result['spawn_payloads_when_empty'])
        finally:
            dialog.close()

    def test_failed_route_commit_creates_no_payload(self):
        from unittest.mock import patch
        sim = self.sim()
        task = self.task()
        before = copy.deepcopy(vars(sim.payload_instance_store))
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertEqual(before, vars(sim.payload_instance_store))
        self.assertFalse(sim.source_payload_additions)
        self.assertFalse(task.payload_instance_id)
