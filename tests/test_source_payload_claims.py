"""A physical source container supports one committed pickup at a time."""
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
from tests.test_single_charge_atomicity import state
from tests.test_exchange_claims import exchange_config, task as exchange_task
from visualiser.models import JsonStore


def prepare(ids=('BOX-1',), anonymous=False):
    cfg = multi_route_config()
    cfg['simulation']['max_task_deferral_minutes'] = 1
    sim = Simulation(cfg, verbose=True)
    for instance_id in ids:
        sim.payload_instance_store.store('A', 'Box', instance_id)
    tasks = [Task(f'T{i}', 'A', 'B', 'Box', is_return_task=True,
                  payload_instance_id='' if anonymous else ids[0]) for i in (1, 2)]
    return sim, tasks


class SourcePayloadClaimTests(unittest.TestCase):
    def test_committed_source_cannot_be_promised_to_another_task(self):
        sim, tasks = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual('T1', sim.payload_instance_store.reservation_owner('BOX-1'))
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[1]))
        self.assertTrue(sim.payload_instance_store.has_instance_at('A', 'BOX-1'))

    def test_batch_cannot_collect_one_named_instance_twice(self):
        for reserve in (False, True):
            sim, tasks = prepare()
            self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve))
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_batch_requires_distinct_anonymous_source_instances(self):
        for reserve in (False, True):
            sim, tasks = prepare(anonymous=True)
            self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve))
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_batch_binds_distinct_sources_and_reverse_pickup_preserves_ownership(self):
        sim, tasks = prepare(('BOX-1', 'BOX-2'), anonymous=True)
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual({'BOX-1', 'BOX-2'}, {t.payload_instance_id for t in tasks})
        for task in reversed(tasks):
            self.assertEqual(task.id, sim.payload_instance_store.reservation_owner(task.payload_instance_id))
            sim._process_payload_pickup(task, sim.payloads['Box'], 2)
        self.assertFalse(sim.payload_instance_store.records_at('A'))
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_rejected_commit_restores_binding_claims_and_resources(self):
        for batch in (False, True):
            sim, tasks = prepare(('BOX-1', 'BOX-2'), anonymous=True)
            before = state(sim), copy.deepcopy(vars(sim.payload_instance_store))
            with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
                with contextlib.redirect_stdout(io.StringIO()):
                    plan = (sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True) if batch
                            else sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
            self.assertIsNone(plan)
            self.assertEqual(before, (state(sim), vars(sim.payload_instance_store)))
            self.assertEqual(['', ''], [t.payload_instance_id for t in tasks])

    def test_estimate_neither_binds_nor_reserves_source_stock(self):
        sim, tasks = prepare(('BOX-1', 'BOX-2'), anonymous=True)
        before = copy.deepcopy(vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks))
        self.assertEqual(before, vars(sim.payload_instance_store))
        self.assertEqual(['', ''], [t.payload_instance_id for t in tasks])

    def test_failure_releases_claim_and_allows_another_pickup(self):
        sim, tasks = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual('T1', sim.payload_instance_store.reservation_owner('BOX-1'))
        sim._fail_task(tasks[0], 'Cancelled before pickup', now=0)
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[1], reserve=True))
        self.assertEqual('T2', sim.payload_instance_store.reservation_owner('BOX-1'))

    def test_fixed_identity_takes_precedence_over_anonymous_selection(self):
        sim, tasks = prepare(('BOX-1', 'BOX-2'), anonymous=True)
        tasks[1].payload_instance_id = 'BOX-1'
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(['BOX-2', 'BOX-1'], [t.payload_instance_id for t in tasks])

    def test_empty_only_pickup_leaves_full_stock_for_unrestricted_pickup(self):
        sim, tasks = prepare(('BOX-1', 'BOX-2'), anonymous=True)
        sim.payload_instance_store._records['BOX-1'].metadata['container_state'] = 'empty'
        sim.payload_instance_store._records['BOX-2'].metadata['container_state'] = 'full'
        tasks[1].task_source = 'task_generation_return'
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(['BOX-2', 'BOX-1'], [t.payload_instance_id for t in tasks])

    def test_foreign_source_claim_is_not_stolen_or_removed_by_rejection(self):
        sim, tasks = prepare()
        sim.payload_instance_store.reserve_instance('BOX-1', 'OTHER')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual('OTHER', sim.payload_instance_store.reservation_owner('BOX-1'))

    def test_pickup_and_exchange_cannot_promise_the_same_empty(self):
        for reserve in (False, True):
            sim = Simulation(exchange_config())
            outbound = exchange_task(1)
            pickup = Task('COLLECT', 'B', 'A', 'Box', is_return_task=True)
            self.assertFalse(sim._plan_payload_claims([pickup, outbound], reserve=reserve))
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_flexible_pickup_preserves_an_empty_needed_for_exchange(self):
        sim = Simulation(exchange_config())
        empty = sim.payload_instance_store.records_at('B')[0].instance_id
        sim.payload_instance_store.store('B', 'Box', 'FULL', metadata={'container_state':'full'})
        outbound = exchange_task(1)
        pickup = Task('COLLECT', 'B', 'A', 'Box', is_return_task=True)
        self.assertTrue(sim._plan_payload_claims([pickup, outbound], reserve=True))
        self.assertEqual('FULL', pickup.payload_instance_id)
        self.assertEqual(empty, outbound.reserved_exchange_empty_id)

    def test_rejected_commit_preserves_a_preexisting_owned_source_claim(self):
        sim, tasks = prepare()
        sim.payload_instance_store.reserve_instance('BOX-1', 'T1')
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual('T1', sim.payload_instance_store.reservation_owner('BOX-1'))

    def test_two_robots_with_one_box_leave_second_task_waiting_until_deadline(self):
        for batch in (False, True):
            cfg = multi_route_config()
            cfg['simulation']['max_task_deferral_minutes'] = 1
            cfg['amrs'][0].update(quantity=2, multi_stop_enabled=batch)
            sim = Simulation(cfg, verbose=True)
            sim.payload_instance_store.store('A', 'Box', 'BOX-1')
            for number in (1, 2):
                sim.schedule_task_release(Task(f'T{number}', 'A', 'B', 'Box',
                    is_return_task=True, payload_instance_id='BOX-1'))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual({'T1'}, {r['task_id'] for r in sim.completed_task_records})
            self.assertEqual({'T2'}, sim.failed_task_ids)
            assigned = [r['task_id'] for r in sim.verbose_rows if r['event_type'] == 'task_assigned']
            self.assertEqual(['T1'], assigned)
            failed = [r for r in sim.verbose_rows if r['event_type'] == 'task_failed']
            self.assertEqual(60, failed[0]['sim_time_sec'])
            self.assertEqual(['BOX-1'], [r.instance_id for r in sim.payload_instance_store.records_at('B')])
            self.assertFalse(sim.payload_instance_store._reservations)

    def test_delivered_box_can_be_collected_again_and_reused(self):
        sim, _ = prepare()
        for task_id, pickup, dropoff, release in [('T1','A','B',0), ('T2','B','A',10), ('T3','A','B',25)]:
            sim.schedule_task_release(Task(task_id, pickup, dropoff, 'Box', release_time=release,
                is_return_task=True, payload_instance_id='BOX-1'))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        arrivals = [(r['to_location'], r['sim_time_sec']) for r in sim.verbose_rows
                    if r['event_type'] == 'location_payload_enter']
        self.assertEqual([('B',9), ('A',19), ('B',34)], arrivals)
        self.assertEqual(1, len(sim.payload_instance_store._known_instances))
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_review_project_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/source-one-box.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise):
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                self.assertEqual({'DELIVER', 'COLLECT'}, {r['task_id'] for r in sim.completed_task_records})
                self.assertEqual({'COMPETING-COLLECT'}, sim.failed_task_ids)
                failure = next(r for r in sim.verbose_rows if r['event_type'] == 'task_failed')
                self.assertEqual(70, failure['sim_time_sec'])
                self.assertFalse(any(r['event_type'] == 'task_assigned' and r['task_id'] == 'COMPETING-COLLECT'
                                     for r in sim.verbose_rows))
                self.assertEqual(['BOX-1'], [r.instance_id for r in sim.payload_instance_store.records_at('A')])
                self.assertEqual(1, len(sim.payload_instance_store._known_instances))
                self.assertFalse(sim.payload_instance_store._reservations)


if __name__ == '__main__':
    unittest.main()
