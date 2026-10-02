"""One physical empty bin can support only one outstanding exchange."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_route_reservation_atomicity import storage_config
from tests.test_single_charge_atomicity import state


def exchange_config(bays=1):
    config = storage_config(bays)
    config['simulation']['max_task_deferral_minutes'] = 1
    config['mass_collections'] = [dict(id='Rotation', location='B', payloads=['Box'],
        scheduled_times=[], capacity_trigger_count=0)]
    return config


def task(number):
    return Task(f'T{number}', 'A', 'B', 'Box', waste_stream='Clinical',
                return_enabled=True, return_payload='Box')


def prepare(bays=1):
    sim = Simulation(exchange_config(bays))
    tasks = [task(1), task(2)]
    for item in tasks:
        sim._queue_pending_task(item)
    return sim, tasks


class ExchangeClaimTests(unittest.TestCase):
    def test_review_projects_raw_and_editor_normalised(self):
        for name, completed, failed in [('exchange-one-empty', 2, 1), ('exchange-two-empties', 4, 0)]:
            for normalise in (False, True):
                with self.subTest(project=name, editor_normalised=normalise):
                    path = Path(__file__).resolve().parents[1] / 'verification/scenarios' / f'{name}.json'
                    cfg = json.loads(path.read_text(encoding='utf-8'))
                    if normalise:
                        cfg = JsonStore(cfg).data
                    sim = Simulation(cfg, verbose=True)
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim.run()
                    self.assertEqual(completed, len(sim.completed_task_records))
                    self.assertEqual(failed, len(sim.failed_task_ids))
                    self.assertFalse(sim.payload_instance_store._reservations)

    def test_batch_cannot_promise_one_empty_bin_to_two_deliveries(self):
        for reserve in (False, True):
            with self.subTest(reserve=reserve):
                sim, tasks = prepare()
                self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve))

    def test_individual_commit_claim_prevents_another_delivery_using_same_empty(self):
        sim, tasks = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertFalse(sim._task_can_exchange_with_store_empty(tasks[1], sim.payloads['Box']))
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[1], reserve=False))

    def test_successful_batch_reserves_distinct_existing_instances(self):
        sim, tasks = prepare(2)
        seeded = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual({'T1','T2'}, {sim.payload_instance_store.reservation_owner(i) for i in seeded})
        self.assertEqual(seeded, {r.instance_id for r in sim.payload_instance_store.records_at('B')})

    def test_failed_plan_releases_exchange_claims(self):
        sim, tasks = prepare(2)
        before = state(sim)
        reservations = copy.deepcopy(sim.payload_instance_store._reservations)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        self.assertEqual(before, state(sim))
        self.assertEqual(reservations, sim.payload_instance_store._reservations)

    def test_task_failure_releases_unconsumed_exchange_claim(self):
        sim, tasks = prepare()
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        sim._fail_task(tasks[0], 'Cancelled before pickup', now=0)
        self.assertTrue(sim._task_can_exchange_with_store_empty(tasks[1], sim.payloads['Box']))

    def test_reverse_arrival_order_consumes_each_tasks_own_claim(self):
        sim, tasks = prepare(2)
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True))
        claimed = {item.id: item.reserved_exchange_empty_id for item in tasks}
        for item in reversed(tasks):
            sim._process_payload_pickup(item, sim.payloads['Box'], 2)
            self.assertEqual(claimed[item.id], item.reserved_exchange_empty_id)
            sim._process_payload_dropoff(item, sim.payloads['Box'], 9)
            self.assertEqual(claimed[item.id], item.exchange_empty_payload_instance_id)
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_estimate_does_not_claim_or_remove_bins(self):
        sim, tasks = prepare(2)
        before = copy.deepcopy(vars(sim.payload_instance_store))
        self.assertIsNotNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=False))
        self.assertEqual(before, vars(sim.payload_instance_store))
        self.assertFalse(any(getattr(item, 'reserved_exchange_empty_id', '') for item in tasks))

    def test_rejected_single_commit_restores_physical_claim(self):
        sim, tasks = prepare()
        before = copy.deepcopy(sim.payload_instance_store._reservations)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual(before, sim.payload_instance_store._reservations)
        self.assertFalse(getattr(tasks[0], 'reserved_exchange_empty_id', ''))

    def test_same_bin_service_does_not_claim_exchange_stock(self):
        sim, tasks = prepare()
        tasks[0].return_same_payload_instance = True
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_external_pickup_claim_is_not_stolen(self):
        sim, tasks = prepare()
        instance = sim.payload_instance_store.records_at('B')[0].instance_id
        sim.payload_instance_store.reserve_instance(instance, 'OTHER')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True))
        self.assertEqual('OTHER', sim.payload_instance_store.reservation_owner(instance))

    def test_two_robots_do_not_pick_up_a_second_full_bin_without_an_empty(self):
        cfg = exchange_config()
        cfg['amrs'][0].update(quantity=2, multi_stop_enabled=False)
        sim = Simulation(cfg, verbose=True)
        for number in (1, 2):
            sim.schedule_task_release(task(number))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        failure = next(r for r in sim.verbose_rows if r['event_type'] == 'task_failed')
        self.assertEqual(60, failure['sim_time_sec'])
        self.assertEqual('T2', failure['task_id'])
        self.assertFalse(any(r['event_type'] == 'task_assigned' and r['task_id'] == 'T2'
                             for r in sim.verbose_rows))
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_two_empty_bins_support_two_complete_cycles_and_four_physical_bins(self):
        sim = Simulation(exchange_config(2), verbose=True)
        seeded = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        for number in (1, 2):
            sim.schedule_task_release(task(number))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertEqual(seeded, {r.instance_id for r in sim.payload_instance_store.records_at('A')})
        self.assertEqual(2, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(4, len(sim.payload_instance_store._known_instances))
        self.assertFalse(sim.payload_instance_store._reservations)

    def test_one_empty_bin_completes_only_one_exchange_cycle(self):
        sim = Simulation(exchange_config(), verbose=True)
        for number in (1, 2):
            sim.schedule_task_release(task(number))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({'T2'}, sim.failed_task_ids)
        self.assertEqual({'T1', 'RETURN-T1-1'}, {r['task_id'] for r in sim.completed_task_records})
        self.assertEqual(1, len(sim.payload_instance_store.records_at('B')))
        self.assertEqual(1, len(sim.payload_instance_store.records_at('A')))


if __name__ == '__main__':
    unittest.main()
