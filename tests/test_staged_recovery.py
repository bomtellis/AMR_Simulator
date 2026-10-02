"""Explicit recovery must move known staged stock using normal route capacity."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_exchange_claims import exchange_config, task as delivery_task
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_results_investigation import load_investigation
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication, QMessageBox
from visualiser.advanced_dialogs import TaskFormDialog


def prepare():
    sim = Simulation(exchange_config())
    outbound = delivery_task(1)
    sim._prepare_task_payload_instance(outbound)
    sim._process_payload_pickup(outbound, sim.payloads['Box'], 2)
    sim._process_payload_dropoff(outbound, sim.payloads['Box'], 9)
    identity = outbound.exchange_empty_payload_instance_id
    failed_return = Task('FAILED-RETURN', 'B', 'A', 'Box', payload_instance_id=identity, is_return_task=True)
    failed_return.creates_new_payload_instance = True
    sim._fail_task(failed_return, 'No feasible return route', now=9)
    recovery = Task('RECOVER', 'B', 'A', 'Box', payload_instance_id=identity)
    recovery.recover_staged_payload = True
    return sim, recovery, identity


class StagedRecoveryTests(unittest.TestCase):
    def test_explicit_recovery_can_claim_failed_return_stock(self):
        sim, task, identity = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertEqual(task.id, sim.payload_instance_store.reservation_owner(identity))
        self.assertEqual('staged', sim.payload_instance_store._known_instances[identity].status)

    def test_recovery_moves_original_empty_without_freeing_the_full_bin_bay(self):
        sim, task, identity = prepare()
        original = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        sim._process_payload_pickup(task, sim.payloads['Box'], 16)
        sim._process_payload_dropoff(task, sim.payloads['Box'], 23)
        self.assertEqual(original, {r.instance_id for r in sim.payload_instance_store.records_at('B')})
        self.assertTrue(sim.inventory_spaces_by_location['B'][0]['occupied'])
        self.assertTrue(sim.payload_instance_store.has_instance_at('A', identity))
        self.assertEqual('empty', sim.payload_instance_store._records[identity].metadata['container_state'])
        self.assertEqual(2, len(sim.payload_instance_store._issued_instances))

    def test_failed_route_rolls_back_claim_and_keeps_staged_stock(self):
        sim, task, identity = prepare()
        before = copy.deepcopy(vars(sim.payload_instance_store))
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertEqual(before, vars(sim.payload_instance_store))

    def test_recovery_does_not_accept_unconfirmed_arrival_or_wrong_location(self):
        for state, location in [('unconfirmed','B'), ('staged','A')]:
            sim, task, identity = prepare()
            sim.payload_instance_store.transition('Box', identity, state, location)
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))

    def test_two_recovery_tasks_cannot_claim_one_container(self):
        sim, task, identity = prepare()
        other = copy.deepcopy(task)
        other.id = 'OTHER'
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], other, reserve=True))
        self.assertEqual('RECOVER', sim.payload_instance_store.reservation_owner(identity))

    def test_batch_cannot_collect_one_staged_container_twice(self):
        sim, task, identity = prepare()
        other = copy.deepcopy(task)
        other.id = 'OTHER'
        for reserve in (False, True):
            self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], [task, other], reserve=reserve))
            self.assertFalse(sim.payload_instance_store.reservation_owner(identity))

    def test_recovery_cannot_bypass_route_profile_or_destination_capacity(self):
        for blocked_by in ('profile','storage'):
            sim, task, identity = prepare()
            if blocked_by == 'profile':
                task.allowed_nodes = ['B']
            else:
                sim.inventory_spaces_by_location['A'] = [dict(name='Full', length_m=2, width_m=2, height_m=2,
                    payload_slots=[dict(payload='Box')], occupied=True, payload='Box', payload_instance_id='OTHER')]
                sim.payload_instance_store.store('A', 'Box', 'OTHER')
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
            self.assertFalse(sim.payload_instance_store.reservation_owner(identity))
            self.assertEqual('staged', sim.payload_instance_store._known_instances[identity].status)

    def test_estimate_is_read_only_and_failure_before_pickup_releases_claim(self):
        sim, task, identity = prepare()
        before = copy.deepcopy(vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task))
        self.assertEqual(before, vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        sim._fail_task(task, 'Cancelled before pickup', now=10)
        self.assertFalse(sim.payload_instance_store.reservation_owner(identity))
        self.assertEqual('staged', sim.payload_instance_store._known_instances[identity].status)
        self.assertTrue(sim.payload_instance_store._known_instances[identity].metadata['recovery_required'])

    def test_failure_during_recovery_leaves_unconfirmed_arrival(self):
        sim, task, identity = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        sim._process_payload_pickup(task, sim.payloads['Box'], 16)
        sim._fail_task(task, 'Recovery failed in transit', now=17)
        self.assertEqual('unconfirmed', sim.payload_instance_store._known_instances[identity].status)
        self.assertFalse(sim.payload_instance_store.has_instance_at('A', identity))

    def test_recovery_does_not_collect_staging_before_a_failure(self):
        sim, task, identity = prepare()
        sim.payload_instance_store._known_instances[identity].metadata.pop('recovery_required')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))

    def test_review_project_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-recovery.json'
        for normalise in (False, True):
            cfg = json.loads(path.read_text(encoding='utf-8'))
            sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual({'T1','RECOVER'}, {r['task_id'] for r in sim.completed_task_records})
            self.assertEqual({'RETURN-T1-1'}, sim.failed_task_ids)
            events = [(r['event_type'],r['sim_time_sec']) for r in sim.verbose_rows
                      if r['event_type'] in {'payload_recovery_started','payload_recovery_completed'}]
            self.assertEqual([('payload_recovery_started',12), ('payload_recovery_completed',19)], events)
            self.assertTrue(sim.payload_instance_store.has_instance_at('A','Box-Rotation_initial_empty-000002'))
            self.assertEqual(2, sim.payload_instance_store.lifecycle_counts()['Box']['stored'])
            self.assertEqual(2, len(sim.payload_instance_store._issued_instances))
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_malformed_recovery_is_blocked_before_running(self):
        source = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-recovery.json'
        for changes in ({'payload_instance_id':''}, {'recover_staged_payload':'false'}, {'return_enabled':True}):
            cfg = json.loads(source.read_text(encoding='utf-8'))
            cfg['tasks'][-1].update(changes)
            report = check_project(cfg, include_legacy=False)
            self.assertTrue(any(f.code=='RECOVERY_INPUT' and f.severity=='error' for f in report.findings))
            with self.assertRaises(ValueError):
                Simulation(cfg)

    def test_early_recovery_waits_for_failed_return_state(self):
        source = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-recovery.json'
        cfg = json.loads(source.read_text(encoding='utf-8'))
        cfg['tasks'][-1]['release_datetime'] = '2026-01-05T00:00:00'
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        events = [(r['event_type'],r['sim_time_sec']) for r in sim.verbose_rows
                  if r['event_type'] in {'payload_recovery_started','payload_recovery_completed'}]
        self.assertEqual([('payload_recovery_started',11),('payload_recovery_completed',18)], events)

    def test_investigation_distinguishes_resolved_recovery_from_original_failure(self):
        source = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-recovery.json'
        cfg = json.loads(source.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'simulation_steps.csv'
            sim = Simulation(cfg, verbose=True, verbose_csv_path=str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            report = load_investigation(path)
        metrics = {m['key']:m for m in report['metrics']}
        self.assertEqual(0, metrics['payload_recovery_outstanding']['value'])
        self.assertEqual(1, metrics['payload_recovery_completed']['value'])
        self.assertEqual(2, metrics['payload_final_stored']['value'])
        self.assertEqual(0, metrics['payload_final_staged']['value'])
        self.assertEqual(2, metrics['payload_moves']['value'])
        self.assertEqual(1, metrics['failed']['value'])
        self.assertTrue(metrics['payload_recovery_completed']['event_ids'])
        self.assertFalse(any('awaiting recovery' in finding for finding in report['findings']))


class RecoveryTaskEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_form_retains_identity_recovery_and_other_settings(self):
        seed = dict(id='RECOVER', pickup='B', dropoff='A', payload='Box', payload_instance_id='STAGED',
                    recover_staged_payload=True, release_datetime='2026-01-05T00:00:10', allowed_nodes=['B','A'], quantity=1)
        dialog = TaskFormDialog(None, ['A','B'], ['Box'], [''], seed=seed)
        dialog.accept()
        self.assertTrue(dialog.result['recover_staged_payload'])
        self.assertEqual('STAGED', dialog.result['payload_instance_id'])
        self.assertEqual(['B','A'], dialog.result['allowed_nodes'])
        self.assertTrue(dialog.result['manual_task'])
        # Editor-emitted manual flags and recovery options are accepted by Task.
        data = dict(dialog.result)
        data.pop('release_datetime')
        Task(**data)
        dialog.deleteLater()

    def test_form_requires_an_exact_container_id_for_recovery(self):
        dialog = TaskFormDialog(None, ['A','B'], ['Box'], [''],
                                seed=dict(id='RECOVER', pickup='B', dropoff='A', payload='Box'))
        dialog.recovery_check.setChecked(True)
        with patch.object(QMessageBox, 'critical') as error:
            dialog.accept()
        error.assert_called_once()
        self.assertIsNone(dialog.result)
        dialog.deleteLater()

    def test_editor_saved_recovery_runs_with_existing_manual_task_flags(self):
        source = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-recovery.json'
        cfg = json.loads(source.read_text(encoding='utf-8'))
        dialog = TaskFormDialog(None, ['A','B'], ['Box'], ['','NoReturn'], seed=cfg['tasks'][-1])
        dialog.accept()
        cfg['tasks'][-1] = dialog.result
        sim = Simulation(JsonStore(cfg).data)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({'T1','RECOVER'}, {r['task_id'] for r in sim.completed_task_records})
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
