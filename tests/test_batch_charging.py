"""Independent shared-journey charge, timeline and reservation references."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_multi_stop_route_rules import multi_route_config
from tests.test_single_charge_atomicity import state
from report.amr_energy_evidence import read_energy_evidence
from tests.test_required_charge_dispatch import config as single_dispatch_config
from tests.test_delivery_energy_reference import lift_config
from visualiser.models import JsonStore
from report.amr_report_analysis import analyse
from amr_results_investigation import load_investigation


def config():
    cfg = multi_route_config()
    cfg['simulation']['enable_opportunity_charging'] = False
    cfg['building'].update(amr_spacing_m=0, node_clearance_time_sec=0)
    cfg['amrs'][0].update(motor_power_w=960, battery_capacity_kwh=.003,
        battery_soc_percent=20, battery_charge_rate_kw=.036, recharge_threshold_percent=0)
    cfg['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
    return cfg


def tasks():
    return [Task(f'T{i}', 'A', 'B', 'Box') for i in (1, 2)]


def dispatch_config():
    cfg = single_dispatch_config()
    robot = config()['amrs'][0]
    cfg['amrs'][0].update(multi_stop_enabled=True, payload_slots=robot['payload_slots'])
    cfg['tasks'] = cfg['tasks'][:1] + [dict(t, release_time=10) for t in config()['tasks']]
    return cfg


class BatchChargingTests(unittest.TestCase):
    def run_case(self, cfg, directory):
        path = Path(directory) / 'steps.csv'
        sim = Simulation(cfg, verbose=True, verbose_csv_path=str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        with path.open(newline='', encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        return sim, path, rows

    def test_in_place_charge_retains_shared_journey(self):
        sim = Simulation(config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2, len(sim.completed_task_records))
        assigned = [r for r in sim.verbose_rows if r['event_type']=='multi_stop_task_assigned']
        self.assertEqual(2, len(assigned))
        self.assertEqual(1, len({r['journey_id'] for r in assigned}))
        # 240 s charge + 2 s shared pickup + 10/2 s travel + two 2 s dropoffs.
        self.assertAlmostEqual(251, sim.amrs[0].available_time)
        self.assertAlmostEqual(.0024, sim.amrs[0].total_energy_charged_kwh)
        self.assertAlmostEqual(960 * 1.07 * 5 / 3600000, sim.amrs[0].total_energy_used_kwh)

    def test_estimate_is_pure_and_replans_reservations_after_charging(self):
        sim = Simulation(config())
        before = state(sim)
        estimate = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks())
        self.assertEqual(before, state(sim))
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True)
        self.assertAlmostEqual(251, plan['finish_time'])
        self.assertAlmostEqual(estimate['battery_soc_after'], plan['battery_soc_after'])
        self.assertEqual(1, len(sim.charge_intervals))
        # The discarded attempt must leave no edge reservation before charging.
        reserved = [r for entries in sim.edge_reservations.values() for r in entries]
        self.assertTrue(reserved)
        self.assertTrue(all(r[0] >= 242 for r in reserved))

    def test_late_failed_replan_restores_resources_and_charge(self):
        sim = Simulation(config())
        before = state(sim)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('late failure')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True))
        self.assertEqual(before, state(sim))

    def test_full_battery_cannot_fit_batch_and_does_not_create_charge(self):
        cfg = config()
        cfg['amrs'][0]['battery_capacity_kwh'] = .001
        sim = Simulation(cfg)
        batch = tasks()
        before = state(sim)
        self.assertIsNone(sim._estimate_multi_stop_for_amr(sim.amrs[0], batch, reserve=True))
        self.assertEqual(before, state(sim))
        self.assertTrue(all('usable full-battery' in t.pending_reason for t in batch))

    def test_batch_charge_obeys_restricted_onboard_routes(self):
        cfg = config()
        cfg['amrs'][0]['battery_capacity_kwh'] = .004
        sim = Simulation(cfg)
        batch = tasks()
        batch[1].allowed_edges = [['A','Y'], ['Y','B']]
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], batch, reserve=True)
        self.assertEqual([('A','Y'), ('Y','B')],
            [(s['from'],s['to']) for s in plan['segments'] if s['type']=='corridor'])
        self.assertAlmostEqual(336, plan['finish_time'])  # 320 charge + 2 pickup + 10 travel + 4 dropoff
        self.assertAlmostEqual(960 * 1.07 * 10 / 3600000, plan['amr_energy_kwh'])

    def test_lift_reservation_is_recomputed_after_charge(self):
        cfg = lift_config()
        cfg['amrs'][0].update(battery_capacity_kwh=.001, battery_soc_percent=10,
            battery_charge_rate_kw=.036, recharge_threshold_percent=0)
        sim = Simulation(cfg)
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True)
        # 90 charge + 2 pickup + 1 corridor + 4 boarding + 1 lift + 4 dropoffs.
        self.assertAlmostEqual(102, plan['finish_time'])
        self.assertEqual(1, len(sim.lift_reservations['L1']))
        self.assertAlmostEqual(92.5, sim.lift_reservations['L1'][0][0])
        self.assertAlmostEqual(960 * 1.07 / 3600000, plan['amr_energy_kwh'])

    def test_dispatched_charge_keeps_batch_pending_and_completes_one_journey(self):
        with tempfile.TemporaryDirectory() as directory:
            sim, path, rows = self.run_case(dispatch_config(), directory)
            requests = [r for r in rows if r['event_type']=='route_charge_required']
            self.assertEqual(1, len(requests))
            self.assertEqual({'T1','T2'}, set(requests[0]['task_id'].split(',')))
            assigned = [r for r in rows if r['event_type']=='multi_stop_task_assigned']
            self.assertEqual(2, len(assigned))
            self.assertEqual(1, len({r['journey_id'] for r in assigned}))
            self.assertEqual(3, len(sim.completed_task_records))
            self.assertAlmostEqual(165.8, sim.amrs[0].available_time)
            battery = read_energy_evidence(path)['battery']
            self.assertTrue(battery['records'][0]['matches'])
            self.assertAlmostEqual(.001438, battery['applied_charge_kwh'])
            self.assertAlmostEqual(.0017646666666666667, sim.amrs[0].total_energy_used_kwh)

    def test_charge_request_does_not_spend_battery_or_reserve_resources(self):
        sim = Simulation(dispatch_config())
        sim.amrs[0].location_name = 'A'
        sim.amrs[0].battery_soc_percent = 33.1
        before = state(sim)
        request = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True, return_charge_request=True)
        self.assertTrue(request['_requires_route_charge'])
        self.assertEqual(before, state(sim))
        option = sim._required_route_charge_option(sim.amrs[0], tasks(), request)
        self.assertIsNotNone(option)
        self.assertEqual('C', option['charge_location'])
        self.assertEqual(before, state(sim))

    def test_unreachable_charger_cannot_create_batch_credit(self):
        sim = Simulation(dispatch_config())
        sim.amrs[0].location_name = 'A'
        sim.amrs[0].battery_soc_percent = 3
        before = state(sim)
        batch = tasks()
        request = sim._estimate_multi_stop_for_amr(sim.amrs[0], batch, return_charge_request=True)
        self.assertTrue(request['_requires_route_charge'])
        self.assertFalse(sim._dispatch_required_route_charge(sim.amrs[0], batch, request))
        self.assertEqual(before, state(sim))

    def test_feasible_single_delivery_is_not_delayed_for_batch_charging(self):
        cfg = dispatch_config()
        cfg['tasks'] = []
        sim = Simulation(cfg)
        sim.amrs[0].location_name = 'A'
        sim.amrs[0].battery_soc_percent = 70  # .0014 fits single .00138 with .00002 reserve, not batch
        for task in tasks():
            sim._queue_pending_task(task)
        _amr, selected, estimate = sim._select_best_assignment()
        self.assertIsInstance(selected, Task)
        self.assertFalse(estimate.get('_requires_route_charge'))

    def test_applied_charge_and_physical_events_share_the_charged_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            sim, path, rows = self.run_case(config(), directory)
            credits = [r for r in rows if r['event_type']=='battery_charge_applied']
            self.assertEqual(1, len(credits))
            self.assertEqual({'T1','T2'}, set(credits[0]['task_id'].split(',')))
            self.assertAlmostEqual(.0024, float(credits[0]['energy_kwh']))
            pickups = [float(r['sim_time_sec']) for r in rows if r['event_type']=='location_payload_exit']
            dropoffs = [float(r['sim_time_sec']) for r in rows if r['event_type']=='location_payload_enter']
            self.assertEqual([242,242], pickups)
            self.assertEqual([249,251], dropoffs)
            self.assertTrue(read_energy_evidence(path)['battery']['records'][0]['matches'])
            with contextlib.redirect_stdout(io.StringIO()):
                report = analyse(path, .8, .8)
            self.assertEqual(1, report['recharge_summary'].iloc[0]['recharges'])
            self.assertAlmostEqual(.0024, report['recharge_summary'].iloc[0]['recharge_energy_kwh'])
            investigation = load_investigation(path)
            self.assertTrue(all(r['matches'] for r in investigation['reconciliation']))
            self.assertEqual(1, len(investigation['energy']['battery']['charge_event_ids']))

    def test_saved_references_raw_and_editor_normalised(self):
        root = Path(__file__).resolve().parents[1] / 'verification/scenarios'
        for name, completed, finish in [('batch-charging', 2, 251), ('batch-charge-dispatch', 3, 165.8)]:
            for normalise in (False, True):
                with self.subTest(case=name, normalise=normalise), tempfile.TemporaryDirectory() as directory:
                    cfg = json.loads((root/(name+'.json')).read_text(encoding='utf-8'))
                    sim, path, rows = self.run_case(JsonStore(cfg).data if normalise else cfg, directory)
                    self.assertEqual(completed, len(sim.completed_task_records))
                    self.assertFalse(sim.failed_tasks)
                    self.assertAlmostEqual(finish, sim.amrs[0].available_time)
                    self.assertTrue(read_energy_evidence(path)['battery']['records'][0]['matches'])
                    self.assertEqual(2, sum(r['event_type']=='multi_stop_task_assigned' for r in rows))

    def test_sufficient_battery_needs_no_charge(self):
        cfg = config()
        cfg['amrs'][0]['battery_soc_percent'] = 100
        sim = Simulation(cfg)
        plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True)
        self.assertAlmostEqual(11, plan['finish_time'])
        self.assertFalse(sim.charge_intervals)
        self.assertEqual(0, sim.amrs[0].total_energy_charged_kwh)

    def test_reserve_boundary_fits_exactly_and_shortfall_recharges(self):
        motor = 960 * 1.07 * 5 / 3600000
        for shortfall in (0, .000001):
            cfg = config()
            cfg['amrs'][0].update(recharge_threshold_percent=10,
                battery_soc_percent=(motor + .0003 - shortfall) / .003 * 100)
            sim = Simulation(cfg)
            plan = sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks(), reserve=True)
            self.assertIsNotNone(plan)
            self.assertEqual(bool(shortfall), bool(sim.charge_intervals))
            self.assertGreaterEqual(sim.amrs[0].battery_energy_kwh(), .0003 - 1e-12)

    def test_serial_charge_rechecks_charger_availability(self):
        sim = Simulation(dispatch_config())
        sim.amrs[0].location_name = 'A'
        sim.amrs[0].battery_soc_percent = 33.1
        batch = tasks()
        request = sim._estimate_multi_stop_for_amr(sim.amrs[0], batch, return_charge_request=True)
        option = sim._required_route_charge_option(sim.amrs[0], batch, request)
        self.assertIsNotNone(option)
        before = state(sim)
        with patch.object(sim, '_charge_location_candidates', return_value=[]):
            self.assertFalse(sim._dispatch_required_route_charge(sim.amrs[0], batch, option))
        self.assertEqual(before, state(sim))


if __name__ == '__main__':
    unittest.main()
