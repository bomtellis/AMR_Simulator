"""Return urgency, robot ownership and the evidence behind fleet rejections."""
import contextlib
from copy import deepcopy
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from amr_sim_models import Task
from amr_simulation_inputs import simulation_input_findings
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_generation_contracts import return_config
from tests.test_multi_stop_route_rules import multi_route_config
from tests import test_dropoff_zones


class ReturnDispatchTests(unittest.TestCase):
    def simulation(self, **settings):
        cfg = reference_config()
        cfg['simulation'].update(settings)
        return Simulation(cfg, verbose=True)

    def test_priority_release_and_insertion_win_over_shorter_journeys_in_both_modes(self):
        for detailed in (False, True):
            with self.subTest(detailed=detailed):
                sim = self.simulation()
                sim.geometric_traffic = detailed
                tasks = [Task('routine', 'A', 'B', 'Box', priority=50),
                         Task('return', 'A', 'B', 'Box', priority=35, is_return_task=True),
                         Task('urgent', 'A', 'B', 'Box', priority=30)]
                tasks[1].payload_instance_id = 'RETURN-BOX'
                sim.payload_instance_store.store('A', 'Box', 'RETURN-BOX')
                for task in tasks:
                    sim._queue_pending_task(task)
                times = {'routine': 1, 'return': 50, 'urgent': 100}
                with patch.object(sim, '_estimate_task_for_amr_cached',
                                  side_effect=lambda amr, task, reserve: dict(finish_time=times[task.id])):
                    for expected in ('urgent', 'return', 'routine'):
                        choice = sim._select_best_assignment()
                        self.assertEqual(expected, choice[1].id)
                        sim._remove_pending_task(choice[1])

    def test_available_robot_can_collect_ordinary_return_while_original_is_busy(self):
        cfg = reference_config()
        cfg['amrs'][0]['quantity'] = 2
        cfg['simulation'].update(service_return_amr_policy='any_compatible', dispatch_available_amrs_only=True)
        sim = Simulation(cfg)
        sim.amrs[0].available_time = 200
        returned = Task('RETURN', 'A', 'B', 'Box', priority=35, is_return_task=True)
        returned.payload_instance_id = 'RETURN-BOX'
        sim.payload_instance_store.store('A', 'Box', 'RETURN-BOX')
        sim._queue_pending_task(returned)
        choice = sim._select_best_assignment()
        self.assertEqual(sim.amrs[1].id, choice[0].id)
        self.assertEqual(200, sim.amrs[0].available_time)

    def test_multi_stop_preference_cannot_displace_higher_priority_return(self):
        sim = Simulation(multi_route_config())
        returned = Task('RETURN', 'A', 'B', 'Box', priority=35, is_return_task=True,
                        payload_instance_id='RETURN-BOX')
        sim.payload_instance_store.store('A', 'Box', 'RETURN-BOX')
        for task in (Task('ONE', 'A', 'B', 'Box', priority=50),
                     Task('TWO', 'A', 'B', 'Box', priority=50), returned):
            sim._queue_pending_task(task)
        with patch.object(sim, '_estimate_multi_stop_for_amr', return_value=dict(finish_time=2)), \
                patch.object(sim, '_estimate_task_for_amr_cached', return_value=dict(finish_time=100)):
            choice = sim._select_best_assignment()
            self.assertIs(choice[1], returned)
            sim._remove_pending_task(returned)
            self.assertIsInstance(sim._select_best_assignment()[1], list)

    def test_return_policy_preserves_physical_object_and_legacy_default(self):
        for policy in ('same_amr', 'any_compatible'):
            cfg = return_config()
            cfg['simulation']['service_return_amr_policy'] = policy
            cfg['task_generation']['categories']['stores'].update(requires_staff=False, return_priority=0)
            seen = []
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(cfg)
                queue = sim._queue_pending_task
                def observe(task):
                    if task.is_return_task:
                        seen.append(task)
                    return queue(task)
                with patch.object(sim, '_queue_pending_task', side_effect=observe):
                    sim.run()
            self.assertFalse(sim.failed_task_ids)
            self.assertEqual(1, len(seen))
            self.assertEqual(0, seen[0].priority)
            self.assertEqual(sim.completed_task_records[0]['payload_instance_id'], seen[0].payload_instance_id)
            self.assertEqual(sim.amrs[0].id if policy == 'same_amr' else '', seen[0].locked_amr_id)

    def test_later_exchange_does_not_overwrite_earlier_return_and_failure_releases_only_owner(self):
        sim = self.simulation()
        amr = sim.amrs[0]
        first = Task('RETURN-FIRST', 'A', 'B', 'Box', is_return_task=True)
        later = Task('RETURN-LATER', 'A', 'B', 'Box', is_return_task=True)
        sim._hold_exchange_work(amr, first, 100)
        sim._hold_exchange_work(amr, later, 200)
        sim.current_time = 150
        self.assertTrue(sim._task_allowed_for_amr(first, amr))
        self.assertFalse(sim._task_allowed_for_amr(Task('NEW', 'A', 'B', 'Box'), amr))
        sim._fail_task(first, 'test failure', now=150)
        self.assertEqual({later.id: 200}, amr.exchange_tasks)
        sim._finish_waste_bin_work(later)
        self.assertEqual({}, amr.exchange_tasks)
        self.assertEqual(0, amr.exchange_hold_until)

    def test_short_exchange_is_owned_from_delivery_admission_until_return_completion(self):
        cfg = test_dropoff_zones.DropoffZoneTests._config()
        cfg['simulation']['service_return_amr_policy'] = 'any_compatible'
        category = cfg['task_generation']['categories']['stores']['departments']['D1']
        category.update(tracked_item_exchange=True, return_enabled=True, return_payload='Trolley',
                        staff_handling_minutes=1, return_delay_minutes=0)
        cfg['payloads'][0].update(track_items=True, items={'Supply': dict(max=10, top_up_threshold=2,
            consumption_per_day=1, exchange_payload='Trolley', source_location='Store')})
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(cfg, verbose=True)
            with patch.object(sim, '_hold_exchange_work', wraps=sim._hold_exchange_work) as holds:
                sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertTrue(any(call.args[1].is_return_task for call in holds.call_args_list))
        self.assertTrue(any(not call.args[1].is_return_task for call in holds.call_args_list))
        self.assertFalse(sim.amrs[0].exchange_tasks)

    def test_capable_but_reserved_fleet_reports_availability_with_robot_evidence(self):
        sim = self.simulation()
        waiting = Task('WAIT', 'A', 'B', 'Box')
        held = Task('WASTE-CYCLE', 'A', 'B', 'Box')
        sim._hold_waste_bin_work(sim.amrs[0], held)
        sim._queue_pending_task(waiting)
        self.assertIsNone(sim._select_best_assignment())
        self.assertIn('Reserved for waste cycle', waiting.pending_reason)
        self.assertNotIn('No AMR has sufficient', waiting.pending_reason)
        sim._expire_task_deferral(waiting, 3600)
        snapshot = next(json.loads(row['details']) for row in sim.verbose_rows
                        if row['event_type'] == 'task_failure_snapshot')
        self.assertEqual('Dispatch', snapshot['blocker'])
        self.assertTrue(snapshot['amr_candidates'][0]['payload_compatible'])
        self.assertIn(held.id, snapshot['amr_candidates'][0]['dispatch_blocker'])

    def test_small_robot_rejection_does_not_mask_capable_robot(self):
        cfg = reference_config()
        small = deepcopy(cfg['amrs'][0])
        small.update(id='SMALL', payload_capacity_kg=1)
        cfg['amrs'].insert(0, small)
        sim = Simulation(cfg)
        task = Task('RETURN', 'A', 'B', 'Box', is_return_task=True)
        task.payload_instance_id = 'RETURN-BOX'
        sim.payload_instance_store.store('A', 'Box', 'RETURN-BOX')
        sim._queue_pending_task(task)
        choice = sim._select_best_assignment()
        self.assertEqual('R-1', choice[0].id)
        self.assertNotIn('No AMR has sufficient', task.pending_reason)

    def test_new_settings_validate_and_keep_legacy_defaults(self):
        sim = self.simulation()
        self.assertEqual('same_amr', sim.service_return_amr_policy)
        self.assertFalse(sim.dispatch_available_amrs_only)
        cfg = reference_config()
        cfg['simulation']['service_return_amr_policy'] = 'invalid'
        self.assertTrue(any('service_return_amr_policy' in path for path, _ in simulation_input_findings(cfg)))


if __name__ == '__main__':
    unittest.main()
