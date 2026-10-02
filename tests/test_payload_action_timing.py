"""Physical stock changes at pickup/dropoff, and only configured exchanges remove empties."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_exchange_claims import exchange_config, task
from tests.test_engineering_reference import reference_config


class PayloadActionTimingTests(unittest.TestCase):
    def test_review_projects_raw_and_editor_normalised(self):
        for name in ('payload-before-wash-completion', 'no-return-keeps-empty-stock'):
            for normalise in (False, True):
                with self.subTest(project=name, editor_normalised=normalise):
                    path = Path(__file__).resolve().parents[1] / 'verification/scenarios' / f'{name}.json'
                    cfg = json.loads(path.read_text(encoding='utf-8'))
                    if normalise:
                        cfg = JsonStore(cfg).data
                    sim = Simulation(cfg, verbose=True)
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim.run()
                    if name == 'payload-before-wash-completion':
                        self.assertFalse(sim.failed_tasks)
                        self.assertEqual(2, len(sim.completed_task_records))
                        assigned = {r['task_id']:r['sim_time_sec'] for r in sim.verbose_rows if r['event_type']=='task_assigned'}
                        self.assertEqual(10, assigned['COLLECT'])
                        arrivals = [r for r in sim.verbose_rows if r['event_type']=='location_payload_enter']
                        self.assertEqual([('B',9),('A',24)],[(r['to_location'],r['sim_time_sec']) for r in arrivals])
                        completions = {r['task_id']:r['sim_time_sec'] for r in sim.verbose_rows if r['event_type']=='task_complete'}
                        self.assertEqual({'DELIVER':69,'COLLECT':89},completions)
                    else:
                        self.assertFalse(sim.completed_task_records)
                        self.assertEqual({'DELIVER'},sim.failed_task_ids)
                        self.assertEqual('empty',sim.payload_instance_store.records_at('B')[0].metadata['container_state'])

    def observe(self, sim, seconds):
        observations = {}
        original = sim._handle_event
        def handle(event):
            if event.event_type == 'observe':
                observations[event.time] = {location: {r.instance_id for r in sim.payload_instance_store.records_at(location)}
                                           for location in ('A','B')}
            else:
                original(event)
        for second in seconds:
            sim.push_event(second, 'observe', {})
        with patch.object(sim, '_handle_event', side_effect=handle), contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return observations

    def test_source_is_empty_after_pickup_and_before_arrival(self):
        sim = Simulation(reference_config())
        sim.payload_instance_store.store('A','Box','PHYSICAL')
        delivery = Task('T1','A','B','Box',payload_instance_id='PHYSICAL')
        delivery.requires_existing_payload_instance = True
        sim.schedule_task_release(delivery)
        observed = self.observe(sim, [1,3,10])
        self.assertEqual({'PHYSICAL'}, observed[1]['A'])
        self.assertEqual(set(), observed[3]['A'])
        self.assertEqual(set(), observed[3]['B'])
        self.assertEqual({'PHYSICAL'}, observed[10]['B'])

    def test_delivery_stock_is_available_before_post_delivery_wash_finishes(self):
        cfg = reference_config()
        cfg['locations'][1].update(wash_cycle_required=True, wash_cycle_duration_sec=60)
        sim = Simulation(cfg)
        sim.schedule_task_release(Task('T1','A','B','Box'))
        observed = self.observe(sim, [10,70])
        self.assertEqual(1, len(observed[10]['B']))
        self.assertEqual(observed[10]['B'], observed[70]['B'])

    def test_no_return_does_not_remove_empty_stock_to_make_room(self):
        sim = Simulation(exchange_config(), verbose=True)
        seeded = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        delivery = task(1)
        delivery.return_enabled = False
        sim.schedule_task_release(delivery)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({'T1'}, sim.failed_task_ids)
        self.assertFalse(sim.completed_task_records)
        self.assertEqual(seeded, {r.instance_id for r in sim.payload_instance_store.records_at('B')})

    def test_no_return_uses_a_free_bay_without_consuming_an_empty(self):
        cfg = exchange_config(2)
        sim = Simulation(cfg)
        removed = sim.payload_instance_store.records_at('B')[1]
        sim.payload_instance_store.pickup('B', instance_id=removed.instance_id)
        sim._remove_payload_record_from_inventory('B', removed.instance_id)
        seeded = sim.payload_instance_store.records_at('B')[0].instance_id
        delivery = task(1)
        delivery.return_enabled = False
        sim.schedule_task_release(delivery)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(2, len(sim.payload_instance_store.records_at('B')))
        self.assertTrue(sim.payload_instance_store.has_instance_at('B', seeded))

    def test_empty_exchange_stock_stays_in_its_bay_until_arrival(self):
        sim = Simulation(exchange_config())
        seeded = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        delivery = task(1)
        delivery.return_delay_minutes = 1
        sim.schedule_task_release(delivery)
        observed = self.observe(sim, [3,10])
        self.assertEqual(seeded, observed[3]['B'])
        self.assertEqual(1, len(observed[10]['B']))
        self.assertFalse(seeded & observed[10]['B'])

    def test_failure_after_pickup_preserves_empty_stock_and_marks_unconfirmed_arrival(self):
        sim = Simulation(exchange_config(), verbose=True)
        seeded = {r.instance_id for r in sim.payload_instance_store.records_at('B')}
        sim.payload_instance_store.store('A', 'Box', 'FULL-BIN')
        delivery = task(1)
        delivery.payload_instance_id = 'FULL-BIN'
        delivery.requires_existing_payload_instance = True
        sim.schedule_task_release(delivery)
        sim.push_event(3, 'inject_failure', {})
        original = sim._handle_event
        def handle(event):
            if event.event_type == 'inject_failure':
                sim._fail_task(delivery, 'Injected failure in transit', now=3)
            else:
                original(event)
        with patch.object(sim, '_handle_event', side_effect=handle), contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertEqual({'T1'}, sim.failed_task_ids)
        self.assertFalse(sim.payload_instance_store.records_at('A'))
        self.assertEqual(seeded, {r.instance_id for r in sim.payload_instance_store.records_at('B')})
        self.assertFalse(sim.payload_instance_store._reservations)
        self.assertEqual(2, len(sim.payload_instance_store._known_instances))
        unresolved = [r for r in sim.verbose_rows if r['event_type'] == 'payload_arrival_unconfirmed']
        self.assertEqual(1, len(unresolved))
        self.assertEqual('FULL-BIN', unresolved[0]['payload_instance_id'])
        self.assertFalse(any(r['event_type'] == 'location_payload_enter' and r['payload_instance_id'] == 'FULL-BIN'
                             for r in sim.verbose_rows))

    def test_completion_fallback_does_not_duplicate_physical_movements(self):
        sim = Simulation(reference_config(), verbose=True)
        sim.schedule_task_release(Task('T1','A','B','Box'))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(1, sum(r['event_type'] == 'location_payload_exit' for r in sim.verbose_rows))
        self.assertEqual(1, sum(r['event_type'] == 'location_payload_enter' for r in sim.verbose_rows))

    def test_batch_delivery_is_stored_before_the_final_stop(self):
        from tests.test_multi_stop_route_rules import multi_route_config
        cfg = multi_route_config()
        cfg['locations'].append(dict(name='C',floor=0,x=16,y=8))
        cfg['corridors']['edges'].append({'from':'B','to':'C','distance_m':10,'width_m':3})
        sim = Simulation(cfg)
        sim.schedule_task_release(Task('T1','A','B','Box'))
        sim.schedule_task_release(Task('T2','A','C','Box'))
        observed = self.observe(sim, [10])
        self.assertEqual(1, len(observed[10]['B']))
        self.assertEqual(2, len(sim.completed_task_records))

    def test_failed_batch_member_cannot_later_complete_or_store_its_payload(self):
        from tests.test_multi_stop_route_rules import multi_route_config
        sim = Simulation(multi_route_config(), verbose=True)
        tasks = [Task(f'T{i}', 'A', 'B', 'Box') for i in (1,2)]
        for item in tasks:
            sim.schedule_task_release(item)
        sim.push_event(3, 'inject_failure', {})
        original = sim._handle_event
        def handle(event):
            if event.event_type == 'inject_failure':
                sim._fail_task(tasks[0], 'Injected failure in transit', now=3)
            else:
                original(event)
        with patch.object(sim, '_handle_event', side_effect=handle), contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual({'T1'}, sim.failed_task_ids)
        self.assertEqual(['T2'], [r['task_id'] for r in sim.completed_task_records])
        self.assertEqual({tasks[1].payload_instance_id}, {r.instance_id for r in sim.payload_instance_store.records_at('B')})


if __name__ == '__main__':
    unittest.main()
