"""Immutable lift bookings must retain floor continuity and reliability order."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_lift_repair_reference import config
from tests.test_single_charge_atomicity import state
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_results_investigation import load_investigation


def simulation(*, wear=0, threshold=0, repair=10):
    cfg = config()
    cfg['lifts'][0].update(health_loss_per_journey_percent=wear,
        mean_time_between_failures_hours=threshold / 3600,
        mean_time_to_repair_hours=repair / 3600)
    return Simulation(cfg)


def book(sim, arrival, origin, destination, owner):
    lift = sim.lifts[0]
    slot = sim._find_lift_journey_slot(lift, arrival, origin, destination)
    plan = dict(slot, lift=lift, destination_lift=lift.location_on_floor(destination))
    sim._reserve_lift_journey(plan, owner)
    sim._apply_lift_journey_wear(lift,
        slot['reposition_sec'] + slot['loaded_travel_sec'], slot['lift_finish'])
    return slot


def saved_config():
    cfg = config()
    cfg['lifts'][0].update(health_loss_per_journey_percent=10,
                          mean_time_between_failures_hours=0)
    slow = cfg['amrs'][0]
    slow.update(id='Slow', quantity=1, speed_m_per_sec=.01)
    slow.pop('payload_slots', None)
    fast = copy.deepcopy(slow)
    fast.update(id='Fast', speed_m_per_sec=2, payload_capacity_kg=5)
    cfg['amrs'].append(fast)
    cfg['payloads'].append(dict(cfg['payloads'][0], name='Light', weight_kg=1))
    cfg['locations'].extend([dict(name='C', floor=0, x=0, y=-1),
                             dict(name='D', floor=1, x=1, y=1)])
    cfg['corridors']['edges'].extend([
        dict(**{'from': a, 'to': b}, distance_m=1, width_m=3)
        for a, b in [('A', 'C'), ('C', 'L1-F0'), ('L1-F1', 'D')]])
    cfg['tasks'] = [dict(id='FIRST', pickup='A', dropoff='B', payload='Box'),
                    dict(id='SECOND', pickup='C', dropoff='D', payload='Light', release_time=60)]
    return cfg


class LiftReservationOrderTests(unittest.TestCase):
    def test_gap_cannot_introduce_an_unrecorded_reset_movement(self):
        sim = simulation()
        first = book(sim, 100, 0, 1, 'FIRST')
        frozen = copy.deepcopy(sim.lift_reservations['L1'])
        second = book(sim, 10, 0, 1, 'SECOND')
        # Existing service is 100..105 and starts at floor 0. An inserted
        # 0->1 trip would need an additional unrecorded return to floor 0.
        # Append instead: reposition 1 + board 2 + loaded 1 + alight 2.
        self.assertEqual(105, first['lift_finish'])
        self.assertEqual(105, second['lift_start'])
        self.assertEqual(111, second['lift_finish'])
        self.assertEqual(1, second['reposition_from_floor'])
        self.assertEqual(frozen[0], sim.lift_reservations['L1'][0])

    def test_closed_gap_with_no_reliability_effect_preserves_future_booking(self):
        sim = simulation()
        first = book(sim, 100, 0, 1, 'FIRST')
        frozen = copy.deepcopy(sim.lift_reservations['L1'])
        second = book(sim, 10, 1, 0, 'SECOND')
        # Reposition 0->1, carry 1->0: the original starting floor is restored
        # by the recorded journey itself, with no extra movement needed.
        self.assertEqual((10, 16), (second['lift_start'], second['lift_finish']))
        self.assertEqual(frozen[0], sim.lift_reservations['L1'][1])
        self.assertEqual(105, first['lift_finish'])
        self.assertEqual(1, sim.lifts[0].current_floor)
        self.assertEqual(105, sim.lifts[0].available_time)
        self.assertEqual(3, sim.lifts[0].operating_time_since_failure_sec)

    def test_wear_keeps_booked_health_in_chronological_order(self):
        sim = simulation(wear=10)
        first = book(sim, 100, 0, 1, 'FIRST')
        second = book(sim, 10, 1, 0, 'SECOND')
        self.assertEqual(1, first['loaded_travel_sec'])
        self.assertEqual(105, second['lift_start'])
        self.assertEqual(0, second['reposition_sec'])
        self.assertAlmostEqual(1 / .95, second['loaded_travel_sec'])
        self.assertAlmostEqual(109 + 1 / .95, second['lift_finish'])
        self.assertEqual(80, sim.lifts[0].health_percent)
        self.assertEqual(0, sim.lifts[0].current_floor)

    def test_failure_accumulator_and_repair_follow_booked_order(self):
        sim = simulation(threshold=2)
        first = book(sim, 100, 0, 1, 'FIRST')
        second = book(sim, 10, 1, 0, 'SECOND')
        self.assertEqual((100, 105), (first['lift_start'], first['lift_finish']))
        self.assertEqual((105, 110), (second['lift_start'], second['lift_finish']))
        self.assertEqual(120, sim.lifts[0].failed_until)
        third = book(sim, 10, 0, 1, 'THIRD')
        self.assertEqual((120, 125), (third['lift_start'], third['lift_finish']))
        self.assertEqual(1, sim.lifts[0].failures_count)
        self.assertEqual(1, sim.lifts[0].operating_time_since_failure_sec)

    def test_zero_repair_duration_still_preserves_failure_order(self):
        sim = simulation(threshold=2, repair=0)
        book(sim, 100, 0, 1, 'FIRST')
        second = book(sim, 10, 1, 0, 'SECOND')
        self.assertEqual((105, 110), (second['lift_start'], second['lift_finish']))
        self.assertEqual(110, sim.lifts[0].failed_until)
        self.assertEqual(1, sim.lifts[0].failures_count)

    def test_gap_exact_boundary_needs_no_extra_reset_allowance(self):
        sim = simulation()
        book(sim, 100, 0, 1, 'FIRST')
        slot = book(sim, 94, 1, 0, 'SECOND')
        self.assertEqual((94, 100), (slot['lift_start'], slot['lift_finish']))
        self.assertEqual(2, len(sim.lift_reservations['L1']))

    def test_gap_preserves_existing_empty_reposition_start_floor(self):
        sim = simulation()
        sim.lift_initial_floors['L1'] = 1
        sim.lifts[0].current_floor = 1
        first = book(sim, 100, 0, 1, 'FIRST')
        second = book(sim, 10, 0, 1, 'SECOND')
        self.assertEqual((100, 106), (first['lift_start'], first['lift_finish']))
        self.assertEqual((10, 16), (second['lift_start'], second['lift_finish']))
        self.assertEqual(1, first['reposition_from_floor'])
        self.assertEqual(1, second['reposition_from_floor'])
        self.assertEqual(1, sim.lifts[0].current_floor)

    def test_individual_routes_preserve_committed_segments_and_charge_energy(self):
        sim = simulation(wear=10)
        sim.amrs[0].available_time = 100
        first = sim._estimate_task_for_amr(sim.amrs[0], Task('FIRST', 'A', 'B', 'Box'), reserve=True)
        frozen = copy.deepcopy(first)
        second = sim._estimate_task_for_amr(sim.amrs[1], Task('SECOND', 'A', 'B', 'Box'), reserve=True)
        self.assertIsNotNone(second)
        self.assertEqual(110, first['finish_time'])
        self.assertEqual(frozen, first)
        # First service ends 107.5; second adds two 1/.95 vertical phases,
        # four handling seconds, .5 connector and two dropoff seconds.
        self.assertAlmostEqual(114 + 2 / .95, second['finish_time'])
        self.assertAlmostEqual(second['energy_kwh'],
                               sum(s.get('energy_kwh', 0) for s in second['segments']))
        self.assertEqual(2, len(sim.lift_reservations['L1']))

    def test_rejected_later_commit_restores_prior_booking_and_health(self):
        sim = simulation(wear=10, threshold=2)
        sim.amrs[0].available_time = 100
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], Task('FIRST', 'A', 'B', 'Box'), reserve=True))
        before = state(sim)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[1], Task('SECOND', 'A', 'B', 'Box'), reserve=True))
        self.assertEqual(before, state(sim))

    def test_batch_route_obeys_existing_booking_and_projected_wear(self):
        sim = simulation(wear=10)
        sim.amrs[0].available_time = 100
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], Task('FIRST', 'A', 'B', 'Box'), reserve=True))
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[1],
            [Task('SECOND', 'A', 'B', 'Box'), Task('THIRD', 'A', 'B', 'Box')], reserve=True)
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(116 + 2 / .95, plan['finish_time'])
        self.assertEqual(2, len(sim.lift_reservations['L1']))
        self.assertEqual(80, sim.lifts[0].health_percent)

    def test_charge_travel_obeys_existing_booking_and_projected_wear(self):
        sim = simulation(wear=10)
        sim.amrs[0].available_time = 100
        self.assertIsNotNone(sim._estimate_task_for_amr(sim.amrs[0], Task('FIRST', 'A', 'B', 'Box'), reserve=True))
        sim.charge_location_names = ['B']
        sim.charge_location_name = 'B'
        plan = sim._plan_return_to_charge(sim.amrs[1], sim.locations['A'], 0,
                                         reserve=True, destination_name='B')
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(112 + 2 / .95, plan['finish_time'])
        self.assertEqual(2, len(sim.lift_reservations['L1']))
        self.assertEqual(80, sim.lifts[0].health_percent)

    def test_saved_reference_and_editor_normalisation_reconcile(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/lift-reservation-order.json'
        for normalise in (False, True):
            with self.subTest(normalise=normalise), tempfile.TemporaryDirectory() as directory:
                cfg = json.loads(path.read_text(encoding='utf-8'))
                log = Path(directory) / 'steps.csv'
                sim = Simulation(JsonStore(cfg).data if normalise else cfg,
                                 verbose=True, verbose_csv_path=str(log))
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                    sim.write_verbose_csv()
                self.assertEqual(2, len(sim.completed_task_records))
                self.assertFalse(sim.failed_tasks)
                # Slow robot: 2 pickup + 100 approach + 5 lift + 100 exit + 2 dropoff.
                # Fast robot: lift at 107, then 2/.95 vertical + 4 handling,
                # .5 exit and 2 dropoff. Release at 60 does not alter the booking.
                self.assertAlmostEqual(209, sim.amrs[0].available_time)
                self.assertAlmostEqual(113.5 + 2 / .95, sim.amrs[1].available_time)
                self.assertEqual(80, sim.lifts[0].health_percent)
                inv = load_investigation(log)
                self.assertTrue(all(r['matches'] for r in inv['reconciliation']))
                self.assertTrue(all(r['matches'] for r in inv['energy']['battery']['records']))

    def test_project_checks_explain_lift_scheduling_scope(self):
        cfg = saved_config()
        before = copy.deepcopy(cfg)
        findings = [f for f in check_project(cfg, include_legacy=False).findings
                    if f.code == 'LIFT_MODEL_SCOPE']
        self.assertEqual(1, len(findings))
        self.assertEqual(('info', 'assumption', 'lifts'),
                         (findings[0].severity, findings[0].kind, findings[0].section))
        self.assertIn('commitment order', findings[0].message)
        self.assertIn('mid-journey', findings[0].consequence)
        self.assertEqual(before, cfg)


if __name__ == '__main__':
    unittest.main()
