"""Explicit IDs name one physical object across creation, transit and reuse."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_multi_stop_route_rules import multi_route_config
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def prepare():
    cfg = multi_route_config()
    cfg['simulation']['max_task_deferral_minutes'] = 1
    cfg['amrs'][0].update(quantity=2)
    sim = Simulation(cfg, verbose=True)
    return sim, [Task(f'T{i}', 'A', 'B', 'Box', payload_instance_id='BOX-1') for i in (1,2)]


class ExplicitPayloadIdentityTests(unittest.TestCase):
    def test_batch_cannot_create_one_explicit_id_twice(self):
        for reserve in (False, True):
            sim, tasks = prepare()
            for task in tasks:
                sim._prepare_task_payload_instance(task)
            self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve))

    def test_first_committed_creation_excludes_competing_journey(self):
        sim, tasks = prepare()
        for task in tasks:
            sim._prepare_task_payload_instance(task)
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[1], tasks[1], reserve=True))

    def test_stored_id_at_another_location_cannot_be_recreated(self):
        sim, tasks = prepare()
        sim.payload_instance_store.store('B', 'Box', 'BOX-1')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertTrue(sim.payload_instance_store.has_instance_at('B', 'BOX-1'))

    def test_id_in_transit_cannot_be_recreated_at_source(self):
        sim, tasks = prepare()
        sim._prepare_task_payload_instance(tasks[0])
        sim._process_payload_pickup(tasks[0], sim.payloads['Box'], 2)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[1], tasks[1], reserve=True))

    def test_direct_physical_pickup_does_not_teleport_stored_stock(self):
        sim, tasks = prepare()
        sim.payload_instance_store.store('B', 'Box', 'BOX-1')
        with self.assertRaises(RuntimeError):
            sim._process_payload_pickup(tasks[0], sim.payloads['Box'], 2)
        self.assertTrue(sim.payload_instance_store.has_instance_at('B', 'BOX-1'))

    def test_two_ordinary_tasks_one_id_complete_one_movement(self):
        sim, tasks = prepare()
        for task in tasks:
            sim.schedule_task_release(task)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({'T1'}, {r['task_id'] for r in sim.completed_task_records})
        self.assertEqual({'T2'}, sim.failed_task_ids)
        exits = [r for r in sim.verbose_rows if r['event_type']=='location_payload_exit']
        self.assertEqual(1, len(exits))

    def test_valid_ordinary_reuse_collects_stock_from_its_actual_location(self):
        sim, tasks = prepare()
        tasks[1].pickup, tasks[1].dropoff, tasks[1].release_time = 'B', 'A', 10
        for task in tasks:
            sim.schedule_task_release(task)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertEqual(['BOX-1'], [r.instance_id for r in sim.payload_instance_store.records_at('A')])
        self.assertEqual(1, len(sim.payload_instance_store._known_instances))

    def test_failed_commit_does_not_keep_a_creation_claim(self):
        sim, tasks = prepare()
        for task in tasks:
            sim._prepare_task_payload_instance(task)
        before = copy.deepcopy(vars(sim.payload_instance_store))
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual(before, vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[1], tasks[1], reserve=True))

    def test_failure_before_creation_releases_claim_to_next_task(self):
        sim, tasks = prepare()
        for task in tasks:
            sim._prepare_task_payload_instance(task)
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        sim._fail_task(tasks[0], 'Cancelled before pickup', now=0)
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[1], tasks[1], reserve=True))

    def test_failure_in_transit_does_not_allow_recreation(self):
        sim, tasks = prepare()
        sim._prepare_task_payload_instance(tasks[0])
        sim._process_payload_pickup(tasks[0], sim.payloads['Box'], 2)
        sim._fail_task(tasks[0], 'Failure in transit', now=3)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[1], tasks[1], reserve=True))

    def test_future_task_definition_does_not_prevent_earlier_creation(self):
        cfg = reference_config()
        cfg['tasks'] = [dict(id='LATER', pickup='B', dropoff='A', payload='Box',
                             payload_instance_id='BOX-1', release_time=10),
                        dict(id='FIRST', pickup='A', dropoff='B', payload='Box', payload_instance_id='BOX-1')]
        sim = Simulation(cfg)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(['FIRST','LATER'], [r['task_id'] for r in sim.completed_task_records])

    def test_estimate_does_not_claim_creation(self):
        sim, tasks = prepare()
        sim._prepare_task_payload_instance(tasks[0])
        before = copy.deepcopy(vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0]))
        self.assertEqual(before, vars(sim.payload_instance_store))

    def test_generated_id_does_not_collide_with_explicit_existing_id(self):
        sim, _ = prepare()
        sim.payload_instance_store.store('B', 'Box', 'Box-T1-000001')
        task = Task('T1', 'A', 'B', 'Box')
        sim._prepare_task_payload_instance(task)
        self.assertNotEqual('Box-T1-000001', task.payload_instance_id)

    def test_one_identity_cannot_change_payload_type(self):
        sim, tasks = prepare()
        sim.payload_instance_store.register_instance('Different', 'BOX-1')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))

    def test_project_check_rejects_conflicting_payload_types_for_one_id(self):
        cfg = reference_config()
        cfg['payloads'].append(dict(cfg['payloads'][0], name='Different'))
        cfg['tasks'] = [dict(id='T1', pickup='A', dropoff='B', payload='Box', payload_instance_id='BOX-1'),
                        dict(id='T2', pickup='B', dropoff='A', payload='Different', payload_instance_id='BOX-1')]
        report = check_project(cfg, include_legacy=False)
        conflicts = [f for f in report.findings if f.code == 'PAYLOAD_ID_TYPE']
        self.assertEqual(1, len(conflicts))
        self.assertEqual('/tasks/1/payload_instance_id', conflicts[0].path)
        self.assertEqual('error', conflicts[0].severity)
        report.acknowledge_warnings()
        self.assertFalse(report.can_run(cfg))

    def test_review_project_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/explicit-id-reuse.json'
        for normalise in (False, True):
            cfg = json.loads(path.read_text(encoding='utf-8'))
            sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual({'DELIVER', 'REUSE'}, {r['task_id'] for r in sim.completed_task_records})
            self.assertEqual({'DUPLICATE'}, sim.failed_task_ids)
            failures = [r for r in sim.verbose_rows if r['event_type']=='task_failed']
            self.assertEqual(11, failures[0]['sim_time_sec'])
            arrivals = [(r['to_location'], r['sim_time_sec']) for r in sim.verbose_rows
                        if r['event_type']=='location_payload_enter']
            self.assertEqual([('B',9), ('A',19)], arrivals)
            self.assertEqual(1, len(sim.payload_instance_store._issued_instances))
            self.assertFalse(sim.payload_instance_store._creation_claims)
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_empty_journey_ignores_physical_id_in_type_check(self):
        cfg = reference_config()
        cfg['tasks'] = [dict(id='T1', pickup='A', dropoff='B', payload='Box', payload_instance_id='BOX-1'),
                        dict(id='T2', pickup='B', dropoff='A', payload='__empty__', payload_instance_id='BOX-1')]
        self.assertFalse(any(f.code == 'PAYLOAD_ID_TYPE' for f in check_project(cfg).findings))


if __name__ == '__main__':
    unittest.main()
