"""Finite charger bays: reservations, physical arrival and applied credits."""
import contextlib
import heapq
import io
import json
import tempfile
import unittest
from pathlib import Path

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_single_charge_atomicity import state
from report.amr_energy_evidence import read_energy_evidence
from visualiser.models import JsonStore
from amr_results_investigation import load_investigation


def config():
    cfg = reference_config()
    cfg['simulation']['enable_opportunity_charging'] = False
    cfg['building'].update(charge_location='C', amr_spacing_m=0,
        node_clearance_time_sec=0, edge_slowdown_per_amr=0)
    cfg['locations'] = [dict(name='A', floor=0, x=0, y=0),
        dict(name='C', floor=0, x=10, y=0, inventory_spaces=[dict(
            name='Charger', length_m=2, width_m=2, height_m=2,
            stores_amr=True, has_charger=True)])]
    cfg['corridors'] = dict(auto_connect=False, nodes=[], edges=[
        {'from':'A','to':'C','width_m':3,'distance_m':10}])
    cfg['amrs'][0].update(quantity=2, motor_power_w=960, battery_capacity_kwh=.01,
        battery_charge_rate_kw=3.6, battery_soc_percent=50, recharge_threshold_percent=0)
    return cfg


def prepared():
    sim = Simulation(config(), verbose=True)
    for amr in sim.amrs:
        sim._free_amr_inventory_space(amr)
        amr.location_name = 'A'
    return sim


def contention_config():
    cfg = config()
    # The second robot starts at the location node under the legacy fallback.
    # Centre the one bay on that node to isolate capacity from local geometry.
    for bay in cfg['locations'][1]['inventory_spaces']:
        bay['points'] = [dict(dx=x,dy=y) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    cfg['locations'].append(dict(name='B', floor=0, x=-40, y=0))
    cfg['corridors']['edges'].append({'from':'A','to':'B','width_m':3,'distance_m':40})
    cfg['simulation']['task_release_stagger_sec'] = 0
    cfg['tasks'] = [dict(id=f'FIRST{i}', pickup='C', dropoff='A', payload='Box') for i in (1,2)]
    cfg['tasks'] += [dict(id=f'LONG{i}', pickup='A', dropoff='B', payload='Box', release_time=10) for i in (1,2)]
    return cfg


def handle(sim, kind):
    event = next(e for e in sim.events if e.event_type==kind)
    sim.events.remove(event)
    heapq.heapify(sim.events)
    sim.current_time = event.time
    with contextlib.redirect_stdout(io.StringIO()):
        sim._handle_event(event)
    return event


class ChargerContentionTests(unittest.TestCase):
    def test_idle_return_completion_preserves_a_new_charge_reservation(self):
        sim = prepared()
        amr = sim.amrs[0]
        task = sim._create_idle_return_task(amr, 0)
        self.assertIsNotNone(task)
        sim._queue_pending_task(task)
        sim._try_assign_tasks(0)
        completion = next(e for e in sim.events if e.event_type=='task_complete')
        sim.current_time = completion.time
        self.assertTrue(sim._schedule_charge_cycle(amr, completion.time))
        bay = sim.inventory_spaces_by_location['C'][0]
        self.assertEqual(amr.id, bay['reserved_by_amr'])
        handle(sim, 'task_complete')
        self.assertEqual(amr.id, bay['reserved_by_amr'])
        self.assertTrue(amr.is_charging)
        self.assertEqual(1, len(sim.completed_task_records))

    def test_identical_bay_pose_has_no_invented_local_movement(self):
        sim = Simulation(contention_config())
        amr = sim.amrs[0]
        bay = sim.inventory_spaces_by_location['C'][0]
        self.assertEqual(([],0.0,0.0), sim._local_manoeuvre_segments_to_inventory_space(amr,'C',bay,0))

    def test_bay_is_reserved_until_physical_arrival(self):
        sim = prepared()
        amr = sim.amrs[0]
        self.assertTrue(sim._schedule_charge_cycle(amr, 0))
        bay = sim.inventory_spaces_by_location['C'][0]
        self.assertEqual(amr.id, bay['reserved_by_amr'])
        handle(sim, 'charge_cycle_start')
        self.assertFalse(bay.get('amr_id'))
        self.assertEqual(amr.id, bay['reserved_by_amr'])

    def test_busy_charger_is_waiting_not_a_failed_delivery(self):
        sim = prepared()
        self.assertTrue(sim._schedule_charge_cycle(sim.amrs[0], 0))
        before = state(sim)
        self.assertFalse(sim._schedule_charge_cycle(sim.amrs[1], 0))
        self.assertEqual(before, state(sim))
        self.assertFalse(sim.failed_tasks)
        self.assertIn('bay available', next(r['details'] for r in sim.verbose_rows if r['event_type']=='charge_wait'))

    def test_baseline_simultaneous_completion_case_cannot_share_one_bay(self):
        path = Path(__file__).resolve().parents[1]/'verification/baseline/charger-contention-interactions-before.json'
        cfg = json.loads(path.read_text(encoding='utf-8'))['simultaneous_completion_case']['config']
        sim = Simulation(cfg, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(2, len(sim.charge_intervals))
        first, second = sorted(sim.charge_intervals, key=lambda i:i['start_time'])
        self.assertLessEqual(first['end_time'], second['start_time'])
        self.assertTrue(all(i['status']=='completed' for i in sim.charge_intervals))

    def test_arrival_and_completion_apply_known_energy_once(self):
        sim = prepared()
        amr = sim.amrs[0]
        self.assertTrue(sim._schedule_charge_cycle(amr, 0))
        start = handle(sim, 'charge_cycle_start')
        arrival = handle(sim, 'charge_cycle_arrive')
        self.assertEqual(5, arrival.time)
        self.assertEqual(amr.id, sim.inventory_spaces_by_location['C'][0]['amr_id'])
        self.assertAlmostEqual(.004, amr.battery_energy_kwh())
        self.assertEqual(0, amr.total_energy_charged_kwh)
        completion = handle(sim, 'charge_cycle_complete')
        self.assertAlmostEqual(11, completion.time)
        self.assertAlmostEqual(.006, amr.total_energy_charged_kwh)
        before = state(sim)
        for event in (start, arrival, completion):
            sim._handle_event(event)
        self.assertEqual(before, state(sim))
        self.assertEqual(1, sum(r['event_type']=='battery_charge_applied' for r in sim.verbose_rows))

    def test_lost_charger_at_arrival_cannot_credit_energy(self):
        sim = prepared()
        amr = sim.amrs[0]
        sim._schedule_charge_cycle(amr, 0)
        handle(sim, 'charge_cycle_start')
        sim.inventory_spaces_by_location['C'][0]['has_charger'] = False
        handle(sim, 'charge_cycle_arrive')
        handle(sim, 'charge_cycle_complete')  # obsolete completion must be inert
        self.assertEqual(0, amr.total_energy_charged_kwh)
        self.assertAlmostEqual(.004, amr.battery_energy_kwh())
        self.assertFalse(amr.is_charging)
        self.assertEqual(5, amr.available_time)
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(1, sum(r['event_type']=='charge_cycle_failed' for r in sim.verbose_rows))
        self.assertEqual(0, sim.charger_estimate_summary()['charge_cycles'])

    def test_invalid_bay_at_completion_does_not_report_full_charge(self):
        sim = prepared()
        amr = sim.amrs[0]
        sim._schedule_charge_cycle(amr, 0)
        handle(sim, 'charge_cycle_start')
        handle(sim, 'charge_cycle_arrive')
        sim.inventory_spaces_by_location['C'][0]['has_charger'] = False
        handle(sim, 'charge_cycle_complete')
        self.assertEqual(0, amr.total_energy_charged_kwh)
        self.assertAlmostEqual(6, amr.total_charge_time)
        self.assertEqual('failed', sim.charge_intervals[0]['status'])
        self.assertFalse(any(r['event_type']=='charge_cycle_complete' for r in sim.verbose_rows))

    def test_wait_is_deduplicated_and_free_bay_can_be_reused(self):
        sim = prepared()
        first, second = sim.amrs
        sim._schedule_charge_cycle(first, 0)
        for _ in range(3):
            self.assertFalse(sim._schedule_charge_cycle(second, 0))
        self.assertEqual(1, sum(r['event_type']=='charge_wait' for r in sim.verbose_rows))
        handle(sim, 'charge_cycle_start')
        handle(sim, 'charge_cycle_arrive')
        handle(sim, 'charge_cycle_complete')
        # Full charge does not vacate a physically occupied bay.
        self.assertFalse(sim._schedule_charge_cycle(second, 11))
        sim._free_amr_inventory_space(first)
        first.location_name = 'A'
        self.assertTrue(sim._schedule_charge_cycle(second, 11))
        handle(sim, 'charge_cycle_start')
        handle(sim, 'charge_cycle_arrive')
        handle(sim, 'charge_cycle_complete')
        self.assertEqual([5,16], [i['start_time'] for i in sim.charge_intervals])
        self.assertEqual([11,22], [i['end_time'] for i in sim.charge_intervals])
        self.assertEqual(1, sim.charger_estimate_summary()['required_peak_concurrent_chargers'])

    def test_old_completion_cannot_finish_a_new_cycle(self):
        sim = prepared()
        amr = sim.amrs[0]
        sim._schedule_charge_cycle(amr, 0)
        old_completion = next(e for e in sim.events if e.event_type=='charge_cycle_complete')
        handle(sim, 'charge_cycle_start')
        bay = sim.inventory_spaces_by_location['C'][0]
        bay['has_charger'] = False
        handle(sim, 'charge_cycle_arrive')
        bay['has_charger'] = True
        self.assertTrue(sim._schedule_charge_cycle(amr, 5))
        handle(sim, 'charge_cycle_start')
        handle(sim, 'charge_cycle_arrive')
        before = state(sim)
        sim._handle_event(old_completion)
        self.assertEqual(before, state(sim))
        self.assertTrue(amr.is_charging)

    def test_zero_duration_cycle_keeps_event_order(self):
        cfg = config()
        cfg['amrs'][0].update(quantity=1, battery_soc_percent=100)
        sim = Simulation(cfg, verbose=True)
        amr = sim.amrs[0]
        self.assertTrue(sim._schedule_charge_cycle(amr, 0))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(amr.is_charging)
        self.assertEqual('completed', amr._charge_cycle_phase)
        self.assertEqual(0, amr.total_energy_charged_kwh)

    def test_two_robot_reference_finishes_with_one_charger(self):
        sim = Simulation(contention_config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(4, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertEqual(2, len(sim.charge_intervals))
        self.assertTrue(all(i['status']=='completed' for i in sim.charge_intervals))
        self.assertEqual(1, sim.charger_estimate_summary()['required_peak_concurrent_chargers'])
        for interval, start, end in zip(sim.charge_intervals, (15,27.38), (22.38,34.76)):
            self.assertAlmostEqual(start, interval['start_time'])
            self.assertAlmostEqual(end, interval['end_time'])
        self.assertEqual([51.38,63.76], [round(a.available_time,2) for a in sim.amrs])

    def test_saved_reference_raw_and_editor_normalised_has_bound_balances(self):
        path = Path(__file__).resolve().parents[1]/'verification/scenarios/charger-contention.json'
        for normalise in (False, True):
            with self.subTest(normalise=normalise), tempfile.TemporaryDirectory() as directory:
                cfg = json.loads(path.read_text(encoding='utf-8'))
                log = Path(directory)/'steps.csv'
                sim = Simulation(JsonStore(cfg).data if normalise else cfg, verbose=True, verbose_csv_path=str(log))
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                    sim.write_verbose_csv()
                self.assertEqual(4, len(sim.completed_task_records))
                battery = read_energy_evidence(log)['battery']
                self.assertTrue(battery['known'])
                self.assertTrue(all(r['matches'] for r in battery['records']))
                self.assertAlmostEqual(.01476, battery['applied_charge_kwh'])
                investigation = load_investigation(log)
                failures = next(m for m in investigation['metrics'] if m['key']=='charge_cycle_failed')
                self.assertEqual(0, failures['value'])
                self.assertTrue(all(r['matches'] for r in investigation['reconciliation']))


if __name__ == '__main__':
    unittest.main()
