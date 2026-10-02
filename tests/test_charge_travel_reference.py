"""Charging travel: 10 m / 2 m/s = 5 s; 720 W * 5 s = 0.001 kWh."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_engineering_reference import reference_config
from tests.test_multi_stop_route_rules import multi_lift_config
from tests.test_single_charge_atomicity import state


def config():
    cfg = reference_config()
    cfg['building'].update(edge_max_concurrency=1, amr_spacing_m=0,
                           node_clearance_time_sec=0, edge_slowdown_per_amr=0)
    cfg['corridors'] = dict(auto_connect=False, nodes=[],
        edges=[{'from':'A', 'to':'B', 'distance_m':10, 'width_m':0.8}])
    cfg['amrs'][0].update(quantity=2, motor_power_w=960, battery_soc_percent=50)
    return cfg


def prepare(cfg=None):
    sim = Simulation(cfg or config(), verbose=True)
    sim.charge_location_names = ['B']
    sim.charge_location_name = 'B'
    return sim


class ChargeTravelReferenceTests(unittest.TestCase):
    def test_review_project_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/charging-travel.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise):
                cfg = json.loads(path.read_text(encoding='utf-8'))
                if normalise:
                    cfg = JsonStore(cfg).data
                sim = Simulation(cfg, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                self.assertEqual(1, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                self.assertEqual(1, len(sim.charge_intervals))
                interval = sim.charge_intervals[0]
                self.assertEqual(125, interval['start_time'])
                self.assertAlmostEqual(9004.284, interval['duration_sec'])
                self.assertAlmostEqual(9129.284, interval['end_time'])
                self.assertEqual(100, sim.amrs[0].battery_soc_percent)

    def test_two_charging_trips_respect_single_corridor_capacity(self):
        sim = prepare()
        first, second = [sim._plan_return_to_charge(amr, sim.locations['A'], 0, reserve=True)
                         for amr in sim.amrs]
        self.assertEqual(5, first['finish_time'])
        self.assertEqual(10, second['finish_time'])
        self.assertEqual([(0, 5, sim.amrs[0].id), (5, 10, sim.amrs[1].id)],
                         sim.edge_reservations[sim._physical_edge_key('A', 'B')])

    def test_estimate_reports_energy_without_spending_it(self):
        sim = prepare()
        before = state(sim)
        plan = sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0)
        self.assertAlmostEqual(0.001, plan.get('amr_energy_kwh', 0))
        self.assertEqual(before, state(sim))

    def test_travel_energy_extends_charge_duration_and_reconciles_log(self):
        sim = prepare()
        amr = sim.amrs[0]
        self.assertTrue(sim._schedule_charge_cycle(amr, 0))
        self.assertAlmostEqual(49.99, amr.battery_soc_percent)
        self.assertAlmostEqual(0.001, amr.total_energy_used_kwh)
        self.assertAlmostEqual(9001.8, sim.charge_intervals[0]['duration_sec'])
        self.assertAlmostEqual(9006.8, amr.available_time)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        movement = [r for r in sim.verbose_rows if r['event_type'] == 'segment_corridor']
        charges = [r for r in sim.verbose_rows if r['event_type'] == 'segment_charge']
        self.assertAlmostEqual(0.001, sum(r['energy_kwh'] for r in movement))
        self.assertAlmostEqual(5.001, sum(r['energy_kwh'] for r in charges))
        self.assertEqual(100, amr.battery_soc_percent)

    def test_insufficient_battery_rejects_trip_without_spending_or_reserving(self):
        sim = prepare()
        sim.amrs[0].battery_soc_percent = 0.005  # 0.0005 kWh, half the travel need.
        before = state(sim)
        self.assertIsNone(sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True))
        self.assertEqual(before, state(sim))

    def test_failed_schedule_explains_insufficient_battery(self):
        sim = prepare()
        sim.amrs[0].battery_soc_percent = 0.005
        self.assertFalse(sim._schedule_charge_cycle(sim.amrs[0], 0))
        self.assertFalse(sim.failed_tasks)
        waiting = [r for r in sim.verbose_rows if r['event_type']=='charge_wait']
        self.assertIn('Insufficient battery energy', waiting[0]['details'])
        self.assertFalse(sim.charge_intervals)

    def test_energy_reachable_charger_is_chosen_even_with_a_longer_wait(self):
        cfg = config()
        cfg['locations'].append(dict(name='C', floor=0, x=0, y=5))
        cfg['corridors']['edges'].append({'from':'A', 'to':'C', 'distance_m':5, 'width_m':0.8})
        sim = prepare(cfg)
        sim.charge_location_names = ['B', 'C']
        sim.amrs[0].battery_soc_percent = 0.006
        sim._reserve_edge('A', 'C', 0, 20, 'OTHER')
        plan = sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True)
        self.assertEqual('C', plan['end_location'])
        self.assertEqual(22.5, plan['finish_time'])
        self.assertAlmostEqual(0.0005, plan['amr_energy_kwh'])

    def test_late_exception_restores_motor_energy_and_corridor_claims(self):
        sim = prepare()
        before = state(sim)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
            with self.assertRaisesRegex(RuntimeError, 'late failure'):
                sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True)
        self.assertEqual(before, state(sim))

    def test_charger_trip_can_use_reserve_but_not_more_than_available_energy(self):
        sim = prepare()
        sim.amrs[0].battery_soc_percent = 0.01  # Exactly 0.001 kWh.
        self.assertIsNotNone(sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True))
        self.assertAlmostEqual(0, sim.amrs[0].battery_soc_percent)

    def test_waiting_does_not_count_as_motor_travel(self):
        sim = prepare()
        sim._reserve_edge('A', 'B', 0, 20, 'OTHER')
        plan = sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True)
        self.assertEqual(25, plan['finish_time'])
        self.assertAlmostEqual(0.001, sim.amrs[0].total_energy_used_kwh)

    def test_cross_floor_charger_reserves_both_corridor_legs(self):
        cfg = multi_lift_config()
        cfg['lifts'] = cfg['lifts'][:1]
        cfg['corridors']['edges'] = [e for e in cfg['corridors']['edges']
                                     if 'L2' not in e['from'] + e['to']]
        cfg['building']['floor_height_m'] = 3
        cfg['lifts'][0].update(car_mass_kg=1000, counterweight_ratio=0,
                              travel_efficiency=1, standby_power_w=0, door_power_w=0)
        cfg['amrs'][0].update(motor_power_w=960, battery_soc_percent=50)
        sim = prepare(cfg)
        plan = sim._plan_return_to_charge(sim.amrs[0], sim.locations['A'], 0, reserve=True)
        self.assertEqual(2, plan['finish_time'])  # 0.5 s + 1 s + 0.5 s.
        self.assertTrue(sim.edge_reservations[sim._physical_edge_key('A', 'L1-F0')])
        self.assertTrue(sim.edge_reservations[sim._physical_edge_key('L1-F1', 'B')])
        self.assertAlmostEqual(0.0002, sim.amrs[0].total_energy_used_kwh)
        self.assertAlmostEqual(1000 * 9.81 * 3 / 3600000, plan.get('lift_energy_kwh', 0))
        self.assertAlmostEqual(plan['energy_kwh'], sum(s.get('energy_kwh', 0) for s in plan['segments']))

    def test_legacy_recharge_entry_point_completes_a_real_charge_cycle(self):
        sim = prepare()
        amr = sim.amrs[0]
        sim._schedule_recharge_for_amr(amr, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(100, amr.battery_soc_percent)
        self.assertAlmostEqual(9001.8, amr.total_charge_time)
        self.assertFalse(amr.is_charging)


if __name__ == '__main__':
    unittest.main()
