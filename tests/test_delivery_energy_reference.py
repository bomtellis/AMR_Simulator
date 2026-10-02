"""Independent watt-second balances for delivery traction and lift supply."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_charge_travel_reference import config as corridor_config
from tests.test_multi_stop_route_rules import multi_lift_config, multi_route_config
from tests.test_single_charge_atomicity import state
from visualiser.models import JsonStore


def lift_config():
    cfg = multi_lift_config()
    cfg['lifts'] = cfg['lifts'][:1]
    cfg['corridors']['edges'] = [e for e in cfg['corridors']['edges']
                                if 'L2' not in e['from'] + e['to']]
    cfg['building']['floor_height_m'] = 3
    cfg['lifts'][0].update(car_mass_kg=1000, counterweight_ratio=0,
                          travel_efficiency=1, regen_efficiency=0,
                          standby_power_w=100, door_power_w=0, boarding_time_sec=2)
    cfg['amrs'][0].update(motor_power_w=960, battery_soc_percent=50)
    return cfg


class DeliveryEnergyReferenceTests(unittest.TestCase):
    def test_saved_project_and_editor_normalised_events_reconcile(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/delivery-energy.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise):
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                self.assertEqual(1, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                completion = next(r for r in sim.verbose_rows if r['event_type'] == 'task_complete')
                self.assertEqual('2026-01-05 00:00:10.000', completion['end_time'])
                rows = [r for r in sim.verbose_rows if r['event_type'].startswith('segment_')]
                motor = sum(r['energy_kwh'] for r in rows if r['segment_type'] == 'corridor')
                lift = sum(r['energy_kwh'] for r in rows if r['segment_type'].startswith('lift_'))
                self.assertAlmostEqual(.000276, motor)
                self.assertAlmostEqual((1010 * 9.81 * 3 + 400) / 3600000, lift)
                self.assertAlmostEqual(motor, sim.amrs[0].total_energy_used_kwh)
                self.assertTrue(all(json.loads(r['details'])['energy_source'] == 'amr_battery'
                                    for r in rows if r['segment_type'] == 'corridor'))

    def test_empty_lift_approach_uses_empty_mass_and_power(self):
        sim = Simulation(lift_config())
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'B', 'B', 'Box'), reserve=True)
        self.assertAlmostEqual(720 / 3600000, plan['amr_energy_kwh'])
        self.assertAlmostEqual((1000 * 9.81 * 3 + 400) / 3600000, plan['lift_energy_kwh'])
        self.assertAlmostEqual(plan['energy_kwh'], sum(s.get('energy_kwh', 0) for s in plan['segments']))

    def test_batch_events_record_shared_energy_once(self):
        cfg = lift_config()
        cfg['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        rows = [r for r in sim.verbose_rows if r['event_type'].startswith('multi_stop_segment_')]
        self.assertTrue(rows)
        self.assertEqual(2, len(sim.completed_task_records))
        motor = 960 * 1.07 / 3600000
        lift = (1020 * 9.81 * 3 + 400) / 3600000
        self.assertAlmostEqual(motor + lift, sum(r['energy_kwh'] for r in rows))
        self.assertAlmostEqual(motor, sim.amrs[0].total_energy_used_kwh)

    def test_late_failure_restores_energy_and_reservations(self):
        sim = Simulation(lift_config())
        before = state(sim)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertIsNone(plan)
        self.assertEqual(before, state(sim))

    def test_reposition_energy_is_counted_once(self):
        cfg = lift_config()
        cfg['lifts'][0]['start_floor'] = 1
        sim = Simulation(cfg)
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        expected = ((1000 + 1010) * 9.81 * 3 + 400) / 3600000
        self.assertAlmostEqual(expected, plan['lift_energy_kwh'])
        self.assertAlmostEqual(plan['energy_kwh'], sum(s.get('energy_kwh', 0) for s in plan['segments']))

    def test_local_manoeuvres_charge_empty_then_loaded_traction(self):
        sim = Simulation(corridor_config())
        sim.amrs[0].inventory_space_name = 'departure'
        # Isolate the energy contract from geometry: known 3-second departure.
        manoeuvre = ([dict(type='local_manoeuvre', duration=3, distance_m=6)], 3, 6)
        with patch.object(sim, '_local_manoeuvre_segments_from_inventory_space', return_value=manoeuvre):
            plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertAlmostEqual((720 * 3 + 960 * 1.035 * 5) / 3600000, plan['amr_energy_kwh'])

    def test_in_place_recharge_projection_matches_commit(self):
        cfg = corridor_config()
        cfg['amrs'][0]['battery_soc_percent'] = 1
        sim = Simulation(cfg)
        task = Task('T', 'A', 'B', 'Box')
        estimate = sim._estimate_task_for_amr(sim.amrs[0], task)
        plan = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
        self.assertAlmostEqual(100 - .00138 * 10, estimate['battery_soc_after'])
        self.assertAlmostEqual(estimate['battery_soc_after'], plan['battery_soc_after'])

    def test_waiting_is_not_traction_and_segments_reconcile(self):
        sim = Simulation(corridor_config())
        sim._reserve_edge('A', 'B', 0, 20, 'OTHER')
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertEqual(27, plan['finish_time'])
        expected = 960 * 1.035 * 5 / 3600000
        self.assertAlmostEqual(expected, sim.amrs[0].total_energy_used_kwh)
        self.assertAlmostEqual(expected, sum(s.get('energy_kwh', 0) for s in plan['segments']))

    def test_lift_supply_is_not_robot_battery_and_includes_boarding(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                sim = Simulation(lift_config())
                tasks = [Task('T1', 'A', 'B', 'Box')]
                if batch:
                    tasks.append(Task('T2', 'A', 'B', 'Box'))
                    plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=True)
                else:
                    plan = sim._estimate_task_for_amr(sim.amrs[0], tasks[0], reserve=True)
                motor = 960 * (1 + .035 * len(tasks)) / 3600000  # 2 m / 2 m/s
                lift = ((1000 + 10 * len(tasks)) * 9.81 * 3 + 100 * 4) / 3600000
                self.assertAlmostEqual(motor, sim.amrs[0].total_energy_used_kwh)
                self.assertAlmostEqual(lift, plan['lift_energy_kwh'])
                self.assertAlmostEqual(motor + lift, plan['energy_kwh'])
                self.assertAlmostEqual(50 - 100 * motor / 10, plan['battery_soc_after'])
                self.assertAlmostEqual(plan['energy_kwh'], sum(s.get('energy_kwh', 0) for s in plan['segments']))

    def test_batch_power_drops_after_first_delivery(self):
        cfg = multi_route_config()
        cfg['amrs'][0]['motor_power_w'] = 960
        cfg['locations'].append(dict(name='C', floor=0, x=16, y=8))
        cfg['corridors']['edges'].append({'from': 'B', 'to': 'C', 'width_m': 3, 'distance_m': 10})
        sim = Simulation(cfg)
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0],
            [Task('T1', 'A', 'B', 'Box'), Task('T2', 'A', 'C', 'Box')], reserve=True)
        self.assertAlmostEqual(960 * (1.07 * 5 + 1.035 * 5) / 3600000, plan['corridor_energy_kwh'])

    def test_estimate_is_pure_and_matches_uncontended_commit(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                sim = Simulation(lift_config())
                tasks = [Task('T1', 'A', 'B', 'Box'), Task('T2', 'A', 'B', 'Box')]
                planner = sim._estimate_multi_stop_for_amr if batch else sim._estimate_task_for_amr
                argument = tasks if batch else tasks[0]
                before = state(sim)
                estimate = planner(sim.amrs[0], argument)
                self.assertEqual(before, state(sim))
                commit = planner(sim.amrs[0], argument, reserve=True)
                self.assertAlmostEqual(estimate['energy_kwh'], commit['energy_kwh'])
                self.assertAlmostEqual(estimate['battery_soc_after'], commit['battery_soc_after'])

    def test_cross_floor_insufficient_motor_energy_rolls_back(self):
        cfg = lift_config()
        cfg['amrs'][0].update(battery_soc_percent=.001, recharge_threshold_percent=0)
        sim = Simulation(cfg)
        before = state(sim)
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertIsNone(plan)
        self.assertEqual(before, state(sim))


if __name__ == '__main__':
    unittest.main()
