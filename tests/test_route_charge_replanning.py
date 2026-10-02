"""Charging retries use fresh route times and restore the discarded attempt."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_delivery_energy_reference import lift_config
from tests.test_single_charge_atomicity import state
from tests.test_charge_travel_reference import config as corridor_config
from visualiser.models import JsonStore


def config():
    cfg = lift_config()
    cfg['amrs'][0].update(battery_capacity_kwh=.001, battery_soc_percent=10,
                         battery_charge_rate_kw=.036, recharge_threshold_percent=0)
    return cfg


class RouteChargeReplanningTests(unittest.TestCase):
    def test_saved_reference_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/route-charge-replanning.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise):
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                self.assertEqual(1, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                self.assertAlmostEqual(100, sim.amrs[0].available_time)
                self.assertAlmostEqual(72.4, sim.amrs[0].battery_soc_percent)

    def test_cross_floor_shortfall_charges_then_replans(self):
        sim = Simulation(config())
        task = Task('T', 'A', 'B', 'Box')
        plan = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
        self.assertIsNotNone(plan)
        # (.001 - .0001) kWh / .036 kW * 3600 = 90 seconds.
        self.assertAlmostEqual(0, plan['task_start_time'])
        self.assertAlmostEqual(100, plan['finish_time'])
        self.assertAlmostEqual(72.4, sim.amrs[0].battery_soc_percent)
        self.assertEqual(1, len(sim.charge_intervals))
        self.assertAlmostEqual(90, sim.amrs[0].total_charge_time)
        # The abandoned attempt must not leave a lift journey at t=2.5.
        self.assertEqual(1, len(sim.lift_reservations['L1']))
        self.assertAlmostEqual(92.5, sim.lift_reservations['L1'][0][0])

    def test_charge_estimate_does_not_change_resources(self):
        sim = Simulation(config())
        before = state(sim)
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'))
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(100, plan['finish_time'])
        self.assertAlmostEqual(72.4, plan['battery_soc_after'])
        self.assertEqual(before, state(sim))

    def test_beyond_full_battery_has_explicit_reason_and_no_charge(self):
        cfg = config()
        cfg['amrs'][0]['battery_capacity_kwh'] = .0002
        sim = Simulation(cfg)
        before = state(sim)
        task = Task('T', 'A', 'B', 'Box')
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertIn('exceeds usable full-battery energy', task.pending_reason)
        self.assertEqual(before, state(sim))

    def test_retry_failure_restores_the_original_state(self):
        sim = Simulation(config())
        before = state(sim)
        original = sim._nearest_compatible_lift_plan
        def fail_after_charge(now, *args, **kwargs):
            return None if now > 90 else original(now, *args, **kwargs)
        with patch.object(sim, '_nearest_compatible_lift_plan', side_effect=fail_after_charge):
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True))
        self.assertEqual(before, state(sim))

    def test_released_cross_floor_task_completes_after_required_charge(self):
        cfg = config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(1, len(sim.charge_intervals))
        self.assertAlmostEqual(100, sim.amrs[0].available_time)
        actions = [r for r in sim.verbose_rows if r['event_type'] in
                   ('location_payload_exit', 'location_payload_enter') and r['task_id'] == 'T']
        self.assertEqual([92, 100], [float(r['sim_time_sec']) for r in actions])

    def test_replanned_route_respects_lift_conflict_after_charging(self):
        sim = Simulation(config())
        sim.lift_reservations['L1'].append((90, 120, 0, 0, 'OTHER'))
        plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertAlmostEqual(127.5, plan['finish_time'])
        self.assertEqual(2, len(sim.lift_reservations['L1']))
        self.assertAlmostEqual(120, sim.lift_reservations['L1'][1][0])
        self.assertAlmostEqual(72.4, plan['battery_soc_after'])

    def test_local_dropoff_shortfall_retries_without_duplicate_bay_claim(self):
        cfg = config()
        cfg['amrs'][0].update(battery_capacity_kwh=.002, battery_soc_percent=15)
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Bay', length_m=2, width_m=2,
            height_m=2, payload_slots=[dict(payload='Box')])]
        sim = Simulation(cfg)
        manoeuvre = ([dict(type='local_manoeuvre', duration=3, distance_m=6)], 3, 6)
        with patch.object(sim, '_local_manoeuvre_segments_to_inventory_space', return_value=manoeuvre):
            plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(183, plan['finish_time'])
        self.assertAlmostEqual(44.8, plan['battery_soc_after'])
        self.assertEqual(1, len(sim.charge_intervals))
        self.assertEqual('T', sim.inventory_spaces_by_location['B'][0]['reserved_by_task'])

    def test_preliminary_same_floor_charge_uses_one_consistent_timeline(self):
        cfg = corridor_config()
        cfg['amrs'][0].update(quantity=1, battery_capacity_kwh=.002, battery_soc_percent=15,
                             battery_charge_rate_kw=.036, recharge_threshold_percent=0)
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        actions = [r for r in sim.verbose_rows if r['event_type'] in
                   ('location_payload_exit', 'location_payload_enter') and r['task_id'] == 'T']
        self.assertEqual([172, 179], [float(r['sim_time_sec']) for r in actions])
        charge = sim.charge_intervals[0]
        self.assertAlmostEqual(0, charge['start_time'])
        self.assertAlmostEqual(170, charge['end_time'])
        self.assertAlmostEqual(179, sim.amrs[0].total_busy_time)


if __name__ == '__main__':
    unittest.main()
