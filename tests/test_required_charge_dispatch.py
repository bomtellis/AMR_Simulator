"""A route energy shortfall can trigger reachable charging above the reserve."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from copy import copy
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_single_charge_atomicity import state
from visualiser.models import JsonStore


def config():
    cfg = reference_config()
    cfg['building'].update(charge_location='C', edge_slowdown_per_amr=0,
                           amr_spacing_m=0, node_clearance_time_sec=0)
    cfg['simulation'].update(enable_opportunity_charging=False, task_release_stagger_sec=0)
    cfg['locations'] = [dict(name=n, floor=0, x=x, y=0) for n, x in [('C', 0), ('A', 1), ('B', 11)]]
    cfg['corridors'] = dict(auto_connect=False, nodes=[], edges=[
        {'from':'C', 'to':'A', 'distance_m':1, 'width_m':3},
        {'from':'A', 'to':'B', 'distance_m':10, 'width_m':3}])
    cfg['amrs'][0].update(motor_power_w=960, battery_capacity_kwh=.002,
                         battery_soc_percent=40, battery_charge_rate_kw=.036,
                         recharge_threshold_percent=1)
    cfg['tasks'] = [dict(id='FIRST', pickup='C', dropoff='A', payload='Box'),
                    dict(id='LONG', pickup='A', dropoff='B', payload='Box', release_time=10)]
    return cfg


def prepared():
    cfg = config()
    cfg['tasks'] = []
    sim = Simulation(cfg, verbose=True)
    sim.amrs[0].location_name = 'A'
    sim.amrs[0].battery_soc_percent = 33.1  # After the first delivery.
    task = Task('LONG', 'A', 'B', 'Box')
    sim._queue_pending_task(task)
    return sim, task


class RequiredChargeDispatchTests(unittest.TestCase):
    def test_saved_reference_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/required-charge-dispatch.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise):
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                self.assertEqual(2, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                requests = [r for r in sim.verbose_rows if r['event_type']=='route_charge_required']
                self.assertEqual(1, len(requests))
                self.assertEqual('LONG', requests[0]['task_id'])
                detail = json.loads(requests[0]['details'])
                self.assertAlmostEqual(.00138, detail['required_traction_kwh'])
                self.assertAlmostEqual(.000662, detail['available_battery_kwh'])
                actions = [r for r in sim.verbose_rows if r['task_id']=='LONG'
                           and r['event_type'] in ('location_payload_exit','location_payload_enter')]
                self.assertEqual([156.8, 163.8], [float(r['sim_time_sec']) for r in actions])

    def test_above_reserve_robot_charges_and_finishes_both_tasks(self):
        sim = Simulation(config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(1, len(sim.charge_intervals))
        interval = sim.charge_intervals[0]
        self.assertEqual('route_energy', interval['reason'])
        self.assertAlmostEqual(10.5, interval['start_time'])
        self.assertAlmostEqual(154.3, interval['end_time'])
        self.assertAlmostEqual(163.8, sim.amrs[0].available_time)
        self.assertAlmostEqual(26, sim.amrs[0].battery_soc_percent)

    def test_selecting_a_charge_request_does_not_spend_or_reserve(self):
        sim, task = prepared()
        before = state(sim)
        choice = sim._select_best_assignment()
        self.assertIsNotNone(choice)
        self.assertTrue(choice[2].get('_requires_route_charge'))
        self.assertEqual(before, state(sim))
        self.assertFalse(sim.events)

    def test_unreachable_charger_leaves_task_pending_without_failure_spam(self):
        sim, task = prepared()
        sim.amrs[0].battery_soc_percent = 3  # .00006 kWh cannot cover .0001.
        before = state(sim)
        for _ in range(3):
            self.assertIsNone(sim._select_best_assignment())
        self.assertEqual(before, state(sim))
        self.assertFalse(sim.failed_tasks)
        self.assertIn('charger', task.pending_reason.lower())

    def test_available_delivery_is_selected_before_a_charge_detour(self):
        sim, task = prepared()
        small = Task('SHORT', 'A', 'A', 'Box')
        sim._queue_pending_task(small)
        choice = sim._select_best_assignment()
        self.assertEqual('SHORT', choice[1].id)
        self.assertFalse(choice[2].get('_requires_route_charge'))

    def test_full_battery_cannot_fit_trip_does_not_dispatch_charging(self):
        sim, task = prepared()
        sim.amrs[0].battery_capacity_kwh = .001
        self.assertIsNone(sim._select_best_assignment())
        self.assertFalse(sim.charge_intervals)
        self.assertIn('full-battery', task.pending_reason)

    def test_busy_robot_is_not_sent_to_charge_before_its_work_finishes(self):
        sim, task = prepared()
        sim.amrs[0].available_time = 100
        self.assertIsNone(sim._select_best_assignment())
        self.assertFalse(sim.charge_intervals)

    def test_future_or_other_robot_locked_task_does_not_trigger_charge(self):
        for field, value in [('release_time', 100), ('locked_amr_id', 'OTHER')]:
            with self.subTest(field=field):
                sim, task = prepared()
                setattr(task, field, value)
                self.assertIsNone(sim._select_best_assignment())
                self.assertFalse(sim.charge_intervals)

    def test_charger_must_allow_onward_task_and_selected_destination_is_retained(self):
        cfg = config()
        cfg['tasks'] = []
        cfg['locations'].append(dict(name='D', floor=0, x=-1, y=0))
        cfg['corridors']['edges'][0] = {'from':'A', 'to':'C', 'distance_m':1,
                                       'width_m':3, 'bidirectional':False}
        cfg['corridors']['edges'].append({'from':'A', 'to':'D', 'distance_m':2, 'width_m':3})
        sim = Simulation(cfg, verbose=True)
        sim.charge_location_names = ['C', 'D']
        amr = sim.amrs[0]
        amr.location_name = 'A'
        amr.battery_soc_percent = 33.1
        task = Task('LONG', 'A', 'B', 'Box')
        sim._queue_pending_task(task)
        choice = sim._select_best_assignment()
        self.assertEqual('D', choice[2]['charge_location'])
        self.assertTrue(sim._dispatch_required_route_charge(amr, task, choice[2]))
        self.assertEqual('D', amr.location_name)
        self.assertEqual('D', sim.charge_intervals[0]['location'])

    def test_commit_only_bay_movement_shortfall_defers_without_leaking_claims(self):
        sim, task = prepared()
        amr = sim.amrs[0]
        amr.battery_capacity_kwh = .003
        amr.battery_soc_percent = 50
        sim.inventory_spaces_by_location['B'] = [dict(name='Bay', length_m=2, width_m=2,
            height_m=2, payload_slots=[dict(payload='Box')])]
        manoeuvre = ([dict(type='local_manoeuvre', duration=3, distance_m=6)], 3, 6)
        with patch.object(sim, '_local_manoeuvre_segments_to_inventory_space', return_value=manoeuvre):
            sim._try_assign_tasks(0)
        self.assertTrue(amr.is_charging)
        self.assertFalse(sim.failed_tasks)
        self.assertFalse(sim.inventory_spaces_by_location['B'][0].get('reserved_by_task'))
        self.assertEqual(1, len(sim.charge_intervals))

    def test_intermediate_charger_can_split_an_approach_longer_than_full_range(self):
        cfg = config()
        cfg['tasks'] = []
        cfg['locations'].append(dict(name='S', floor=0, x=-5, y=0))
        cfg['corridors']['edges'][0]['distance_m'] = 5
        cfg['corridors']['edges'].append({'from':'S', 'to':'C', 'distance_m':5, 'width_m':3})
        sim = Simulation(cfg)
        sim.amrs[0].location_name = 'S'
        sim.amrs[0].battery_soc_percent = 33.1
        sim._queue_pending_task(Task('LONG', 'A', 'B', 'Box'))
        choice = sim._select_best_assignment()
        self.assertIsNotNone(choice)
        self.assertEqual('C', choice[2]['charge_location'])
        self.assertTrue(choice[2]['exceeds_full_energy'])
        # Direct approach+task .00238 kWh exceeds .002, but after C only .00188.
        self.assertAlmostEqual(.00238, choice[2]['required_energy_kwh'])

    def test_occupied_charger_bay_is_not_taken_by_a_charge_request(self):
        sim, task = prepared()
        other = copy(sim.amrs[0])
        other.id = 'OTHER'
        other.location_name = 'C'
        other.inventory_space_name = 'Charger'
        other.is_charging = True
        sim.amrs.append(other)
        sim.inventory_spaces_by_location['C'] = [dict(name='Charger', stores_amr=True,
            has_charger=True, length_m=2, width_m=2, height_m=2, occupied=True, amr_id='OTHER')]
        before = state(sim)
        self.assertIsNone(sim._select_best_assignment())
        self.assertEqual(before, state(sim))
        self.assertFalse(sim.failed_tasks)

    def test_stale_bay_inspection_is_pure_until_actual_charge_reservation(self):
        sim, task = prepared()
        sim.inventory_spaces_by_location['C'] = [dict(name='Charger', stores_amr=True,
            has_charger=True, length_m=2, width_m=2, height_m=2,
            occupied=True, amr_id='GONE', reserved_by_amr='GONE')]
        before = state(sim)
        choice = sim._select_best_assignment()
        self.assertIsNotNone(choice)
        self.assertEqual(before, state(sim))
        self.assertTrue(sim._dispatch_required_route_charge(sim.amrs[0], task, choice[2]))
        bay = sim.inventory_spaces_by_location['C'][0]
        self.assertEqual('', bay['amr_id'])
        self.assertEqual(sim.amrs[0].id, bay['reserved_by_amr'])


if __name__ == '__main__':
    unittest.main()
