"""Rejected individual and charging routes retain their pre-plan resources."""
import contextlib
import copy
import io
import unittest
from unittest.mock import patch

from amr_sim_models import Task
from simulator import EMPTY_PAYLOAD_NAME, Simulation
from tests.test_route_reservation_atomicity import resource_state, storage_config


def state(sim):
    return copy.deepcopy(dict(resources=resource_state(sim),
                              amrs=[vars(a) for a in sim.amrs],
                              charge_intervals=sim.charge_intervals))


def charging_sim(*, lifts=False):
    config = storage_config(lifts=lifts)
    for location in config['locations']:
        location['inventory_spaces'] = [dict(name=location['name']+'-charger',
            length_m=2, width_m=2, height_m=2, stores_amr=True, has_charger=True)]
    sim = Simulation(config)
    # Start parked at A, then direct this trip to the other configured charger.
    sim.charge_location_names = ['B']
    sim.charge_location_name = 'B'
    sim.amrs[0].battery_soc_percent = 50
    return sim


class SingleChargeAtomicityTests(unittest.TestCase):
    def test_unreachable_post_delivery_wash_rolls_back_single_route(self):
        config = storage_config()
        config['locations'][1].update(wash_cycle_required=True, wash_location='Wash')
        config['locations'].append(dict(name='Wash', floor=0, x=100, y=100))
        sim = Simulation(config)
        task = Task('T1', 'A', 'B', 'Box')
        sim._queue_pending_task(task)
        before = state(sim)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertEqual(before, state(sim))
        self.assertEqual('', task.assigned_inventory_space)
        self.assertFalse(task.wash_cycle_required)
        self.assertIn('No route to wash', task.pending_reason)

    def test_late_single_failure_restores_lift_and_charge_state(self):
        for lifts in (False, True):
            with self.subTest(lifts=lifts):
                sim = Simulation(storage_config(lifts=lifts))
                task = Task('T1', 'A', 'B', 'Box')
                sim._queue_pending_task(task)
                sim.amrs[0].battery_soc_percent = 0
                before = state(sim)
                with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
                    with contextlib.redirect_stdout(io.StringIO()):
                        result = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
                self.assertIsNone(result)
                self.assertEqual(before, state(sim))
                self.assertEqual('', task.assigned_inventory_space)

    def test_failed_charge_schedule_retains_occupied_departure_bay(self):
        for method in ('_schedule_charge_cycle', '_schedule_recharge_for_amr'):
            with self.subTest(method=method):
                sim = charging_sim()
                self.assertEqual('A-charger', sim.amrs[0].inventory_space_name)
                before = state(sim)
                with patch.object(sim, '_select_charge_location_for_amr', return_value=None):
                    getattr(sim, method)(sim.amrs[0], 0)
                self.assertEqual(before, state(sim))
                self.assertFalse(any(e.event_type.endswith('_start') for e in sim.events))

    def test_charge_route_rejection_releases_new_claim_and_preserves_old_bay(self):
        sim = charging_sim()
        before = state(sim)
        with patch.object(sim, '_select_charge_location_for_amr', return_value=sim.locations['B']), \
             patch.object(sim, '_same_floor_segments', return_value=None):
            self.assertIsNone(sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True))
        self.assertEqual(before, state(sim))

    def test_charge_estimate_does_not_change_target_or_bay(self):
        sim = charging_sim()
        before = state(sim)
        self.assertIsNotNone(sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=False))
        self.assertEqual(before, state(sim))

    def test_charge_lift_exception_restores_claims_and_wear(self):
        sim = charging_sim(lifts=True)
        before = state(sim)
        original = sim._apply_lift_journey_wear
        def fail_after_wear(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('after lift wear')
        with patch.object(sim, '_apply_lift_journey_wear', side_effect=fail_after_wear):
            with self.assertRaisesRegex(RuntimeError, 'after lift wear'):
                sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True)
        self.assertEqual(before, state(sim))

    def test_successful_charge_releases_origin_and_keeps_destination_claim(self):
        for lifts in (False, True):
            with self.subTest(lifts=lifts):
                sim = charging_sim(lifts=lifts)
                self.assertTrue(sim._schedule_charge_cycle(sim.amrs[0], 0))
                origin = sim.inventory_spaces_by_location['A'][0]
                destination = sim.inventory_spaces_by_location['B'][0]
                self.assertFalse(origin['occupied'])
                self.assertEqual('', origin['amr_id'])
                self.assertEqual(sim.amrs[0].id, destination['reserved_by_amr'])
                self.assertEqual('B', sim.amrs[0].location_name)
                self.assertTrue(sim.amrs[0].is_charging)
                self.assertEqual(1, len(sim.charge_intervals))
                self.assertEqual({'charge_cycle_start', 'charge_cycle_arrive', 'charge_cycle_complete'},
                                 {e.event_type for e in sim.events})

    def test_successful_single_retains_charge_record_and_storage_claim(self):
        sim = Simulation(storage_config())
        task = Task('T1', 'A', 'B', 'Box')
        sim._queue_pending_task(task)
        sim.amrs[0].battery_soc_percent = 0
        result = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
        self.assertIsNotNone(result)
        self.assertEqual('T1', sim.inventory_spaces_by_location['B'][0]['reserved_by_task'])
        # 10 kWh at 2 kW takes 5 hours, independently of the route duration.
        self.assertEqual(18000, sim.charge_intervals[0]['duration_sec'])
        self.assertEqual(18000, sim.amrs[0].total_charge_time)
        self.assertGreater(sim.amrs[0].total_energy_used_kwh, 0)
        self.assertTrue(sim.edge_reservations)

    def test_failed_idle_return_restores_task_target_and_robot_bays(self):
        sim = charging_sim()
        amr = sim.amrs[0]
        task = Task('IDLE', 'A', 'A', EMPTY_PAYLOAD_NAME)
        task.is_idle_return = True
        task.amr_id = amr.id
        sim._queue_pending_task(task)
        before = state(sim)
        task_before = copy.deepcopy(vars(task))
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(amr, task, reserve=True))
        self.assertEqual(before, state(sim))
        self.assertEqual(task_before, vars(task))

    def test_failed_charger_selection_restores_stale_bay_cleanup(self):
        for marker in ({'occupied': True}, {'amr_id': 'REMOVED', 'occupied': True},
                       {'reserved_by_amr': 'REMOVED'}):
            with self.subTest(marker=marker):
                sim = charging_sim()
                sim.inventory_spaces_by_location['B'][0].update(marker)
                before = state(sim)
                with patch.object(sim, '_same_floor_segments', return_value=None):
                    self.assertIsNone(sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True))
                self.assertEqual(before, state(sim))


if __name__ == '__main__':
    unittest.main()
