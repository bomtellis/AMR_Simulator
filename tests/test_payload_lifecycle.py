"""Population is physical stock across lifecycle states, not planned IDs."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_exchange_claims import exchange_config, task as exchange_task
import pandas as pd
from amr_results_investigation import load_investigation
from report.amr_report_analysis import build_payload_population_summary, build_payload_schedule, _completed_transport_movement_rows
from visualiser.models import JsonStore


class PayloadLifecycleTests(unittest.TestCase):
    def test_planned_task_ids_are_not_reported_as_issued_objects(self):
        sim = Simulation(reference_config(), verbose=True)
        task = Task('NEVER', 'A', 'B', 'Box', payload_instance_id='PLANNED')
        sim.schedule_task_release(task)
        sim._fail_task(task, 'Cancelled before pickup', now=0)
        sim._append_payload_population_summary_rows()
        row = next(r for r in sim.verbose_rows if r['event_type']=='payload_population_summary')
        self.assertEqual(0, row['payload_known_instances'])

    def test_two_in_transit_objects_count_towards_physical_population(self):
        sim = Simulation(reference_config())
        for number in (1,2):
            task = Task(f'T{number}', 'A', 'B', 'Box', payload_instance_id=f'BOX-{number}')
            sim._prepare_task_payload_instance(task)
            sim._process_payload_pickup(task, sim.payloads['Box'], 2)
        self.assertEqual(2, sim.payload_population_peak['Box'])
        self.assertFalse(sim.payload_instance_store.records_at('A'))
        self.assertFalse(sim.payload_instance_store.records_at('B'))

    def test_exchange_staging_remains_part_of_population(self):
        sim = Simulation(exchange_config())
        task = exchange_task(1)
        sim._prepare_task_payload_instance(task)
        sim._process_payload_pickup(task, sim.payloads['Box'], 2)
        sim._process_payload_dropoff(task, sim.payloads['Box'], 9)
        self.assertEqual(2, sim.payload_population_peak['Box'])
        self.assertEqual('staged', sim.payload_instance_store._known_instances[task.exchange_empty_payload_instance_id].status)

    def test_failure_after_pickup_keeps_an_unconfirmed_physical_object(self):
        sim = Simulation(reference_config())
        task = Task('T1', 'A', 'B', 'Box', payload_instance_id='BOX-1')
        sim._prepare_task_payload_instance(task)
        sim._process_payload_pickup(task, sim.payloads['Box'], 2)
        sim._fail_task(task, 'Failure in transit', now=3)
        self.assertEqual('unconfirmed', sim.payload_instance_store._known_instances['BOX-1'].status)
        self.assertEqual(1, sim.payload_population_peak['Box'])

    def test_report_counts_two_tasks_using_one_transported_object(self):
        movements = pd.DataFrame([dict(payload='Box', payload_instance_id='BOX-1', task_id=task)
                                  for task in ('T1','T2')])
        row = build_payload_schedule(pd.DataFrame(), {}, movements).iloc[0]
        self.assertEqual(1, row['unique_payloads_moved'])
        self.assertEqual(2, row['tasks'])

    def test_legacy_storage_peak_does_not_claim_physical_population(self):
        legacy = pd.DataFrame([dict(_event_text='payload_population_summary', payload='Box',
                                    payload_runtime_population=2, payload_known_instances=5)])
        row = build_payload_population_summary(legacy).iloc[0]
        self.assertTrue(pd.isna(row['total_runtime_payloads']))
        self.assertTrue(pd.isna(row['known_payload_instances']))

    def test_task_count_does_not_substitute_for_missing_identity_evidence(self):
        tasks = pd.DataFrame([dict(payload='Box', task_id='T1', outcome='completed')])
        row = build_payload_schedule(tasks, {}).iloc[0]
        self.assertTrue(pd.isna(row['unique_payloads_moved']))
        self.assertTrue(pd.isna(row['total_runtime_payloads']))

    def test_removed_bin_and_replacement_do_not_inflate_simultaneous_population(self):
        sim = Simulation(exchange_config())
        initial = sim.payload_instance_store.records_at('B')[0]
        initial.metadata['container_state'] = 'full'
        with contextlib.redirect_stdout(io.StringIO()):
            sim._execute_mass_collection_visit(sim.mass_collection_configs[0], 0, 'test')
        states = sim.payload_instance_store.lifecycle_counts()['Box']
        self.assertEqual(1, states['removed'])
        self.assertEqual(1, states['stored'])
        self.assertEqual(2, len(sim.payload_instance_store._issued_instances))
        self.assertEqual(1, sim.payload_population_peak['Box'])

    def test_repeated_snapshot_and_store_do_not_duplicate_identity_counts(self):
        sim = Simulation(reference_config())
        for _ in range(3):
            sim.payload_instance_store.store('A', 'Box', 'ONE')
            sim._record_payload_population_snapshot()
        sim.payload_instance_store.pickup('A', instance_id='ONE')
        sim.payload_instance_store.store('B', 'Box', 'ONE')
        self.assertEqual({'Box':1}, sim.payload_instance_store.active_counts())
        self.assertEqual(1, sim.payload_population_peak['Box'])
        self.assertEqual(1, len(sim.payload_instance_store._issued_instances))

    def test_missing_lifecycle_logs_are_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.csv'
            path.write_text('event_type,sim_time_sec,task_id\ntask_complete,9,T1\n')
            report = load_investigation(path)
        metrics = {m['key']:m for m in report['metrics']}
        self.assertIsNone(metrics['payload_final_staged']['value'])
        self.assertIsNone(metrics['payload_issued']['value'])

    def test_staged_failure_reference_raw_normalised_and_reported(self):
        source = Path(__file__).resolve().parents[1] / 'verification/scenarios/staged-return-failure.json'
        for normalise in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'simulation_steps.csv'
                cfg = json.loads(source.read_text(encoding='utf-8'))
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True, verbose_csv_path=str(path))
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                    sim.write_verbose_csv()
                self.assertEqual({'RETURN-T1-1'}, sim.failed_task_ids)
                self.assertEqual(1, len(sim.completed_task_records))
                states = sim.payload_instance_store.lifecycle_counts()['Box']
                self.assertEqual(1, states['stored'])
                self.assertEqual(1, states['staged'])
                report = load_investigation(path)
                metrics = {m['key']:m for m in report['metrics']}
                self.assertEqual(2, metrics['payload_issued']['value'])
                self.assertEqual(1, metrics['payload_final_staged']['value'])
                self.assertEqual(0, metrics['payload_final_unconfirmed']['value'])
                staged = next(r for r in sim.payload_instance_store.known_records() if r.status=='staged')
                self.assertEqual('B', staged.location)
                self.assertTrue(staged.metadata['recovery_required'])
                recovery = [e for e in report['events'] if e['type']=='payload_recovery_required']
                self.assertEqual(1, len(recovery))
                self.assertEqual(9, recovery[0]['time_seconds'])
                self.assertEqual(staged.instance_id, recovery[0]['payload_instance_id'])
                self.assertTrue(metrics['payload_final_staged']['event_ids'])
                rows = pd.read_csv(path)
                rows['_event_text'] = rows['event_type']
                population = build_payload_population_summary(rows).iloc[0]
                self.assertEqual(2, population['total_runtime_payloads'])
                self.assertEqual(2, population['known_payload_instances'])
                schedule = build_payload_schedule(pd.DataFrame(), {}, _completed_transport_movement_rows(rows),
                                                   build_payload_population_summary(rows)).iloc[0]
                self.assertEqual(1, schedule['unique_payloads_moved'])
                self.assertEqual(1, schedule['tasks'])

    def test_seeded_inventory_is_not_a_completed_transfer_but_service_arrival_is(self):
        rows = pd.DataFrame([
            dict(_event_text='location_payload_enter', payload='Box', payload_instance_id='SEED', to_location='B'),
            dict(_event_text='location_payload_exit', payload='Box', payload_instance_id='MOVED', from_location='A', task_id='T'),
            dict(_event_text='payload_service_arrival', payload='Box', payload_instance_id='MOVED', to_location='B', task_id='T')])
        moves = _completed_transport_movement_rows(rows)
        self.assertEqual(['MOVED'], list(moves['payload_instance_id']))

    def test_missing_movement_ids_do_not_count_as_unique_objects(self):
        movement = pd.DataFrame([dict(task_id='T1', payload='Box', payload_instance_id='')])
        row = build_payload_schedule(pd.DataFrame(), {}, movement).iloc[0]
        self.assertTrue(pd.isna(row['unique_payloads_moved']))
        self.assertEqual(1, row['tasks'])


if __name__ == '__main__':
    unittest.main()
