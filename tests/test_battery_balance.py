"""Independent stored-battery balances, distinct from planned charge input."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simulator import Simulation
from tests.test_route_charge_replanning import config as in_place_config
from tests.test_required_charge_dispatch import config as dispatch_config
from amr_sim_models import Task
from amr_results_investigation import load_investigation
from report.amr_energy_evidence import read_energy_evidence, summarize_energy, CAPABILITY, BATTERY_CAPABILITY
from report.amr_report_analysis import analyse
from visualiser.models import JsonStore


class BatteryBalanceTests(unittest.TestCase):
    def test_saved_reference_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/required-charge-dispatch.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise), tempfile.TemporaryDirectory() as directory:
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim, log = self.run_case(JsonStore(cfg).data if normalise else cfg, directory)
                battery = read_energy_evidence(log)['battery']
                self.assertEqual(2, len(sim.completed_task_records))
                self.assertTrue(battery['records'][0]['matches'])
                self.assertAlmostEqual(.001438, battery['applied_charge_kwh'])
                investigation = load_investigation(log)
                metric = next(m for m in investigation['metrics'] if m['key']=='battery_charge_applied_kwh')
                with log.open(newline='', encoding='utf-8-sig') as stream:
                    credits = [r['event_id'] for r in csv.DictReader(stream) if r['event_type']=='battery_charge_applied']
                self.assertEqual(credits, metric['event_ids'])

    def run_case(self, cfg, directory):
        path = Path(directory) / 'simulation_steps.csv'
        sim = Simulation(cfg, verbose=True, verbose_csv_path=str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        return sim, path

    def test_in_place_charging_records_its_energy_input(self):
        cfg = in_place_config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        with tempfile.TemporaryDirectory() as directory:
            sim, path = self.run_case(cfg, directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                charges = [r for r in csv.DictReader(stream) if r['event_type']=='segment_charge']
            self.assertEqual(1, len(charges))
            self.assertAlmostEqual(.0009, float(charges[0]['energy_kwh']))

    def test_applied_balances_for_in_place_and_dispatched_charging(self):
        for cfg, initial, credited, used, final in [
            (in_place_config(), .0001, .0009, .000276, .000724),
            (dispatch_config(), .0008, .001438, .001718, .00052)]:
            if not cfg['tasks']:
                cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as directory:
                sim, path = self.run_case(cfg, directory)
                ledger = read_energy_evidence(path)['battery']
                self.assertTrue(ledger['known'])
                row = ledger['records'][0]
                self.assertTrue(row['matches'])
                for key, value in [('initial_kwh', initial), ('applied_charge_kwh', credited),
                                   ('planned_traction_kwh', used), ('final_kwh', final)]:
                    self.assertAlmostEqual(value, row[key])
                self.assertAlmostEqual(credited, sim.amrs[0].total_energy_charged_kwh)
                self.assertEqual(ledger, load_investigation(path)['energy']['battery'])
                with contextlib.redirect_stdout(io.StringIO()):
                    report = analyse(path, .8, .8)
                self.assertTrue(report['battery_balance'].iloc[0]['matches'])
                self.assertAlmostEqual(credited, report['recharge_summary'].iloc[0]['recharge_energy_kwh'])
                self.assertAlmostEqual(credited, report['amr_summary'].iloc[0]['recharge_energy_kwh'])

    def test_idle_fleet_has_known_zero_charging(self):
        cfg = in_place_config()
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(cfg, directory)
            battery = read_energy_evidence(path)['battery']
            self.assertTrue(battery['known'])
            self.assertEqual(0, battery['applied_charge_kwh'])
            self.assertTrue(battery['records'][0]['matches'])

    def test_cancelled_charge_has_no_applied_credit_and_unknown_full_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'steps.csv'
            sim = Simulation(in_place_config(), verbose=True, verbose_csv_path=str(path))
            self.assertTrue(sim._schedule_charge_cycle(sim.amrs[0], 0))
            sim._handle_event(next(e for e in sim.events if e.event_type=='charge_cycle_start'))
            sim.stop_requested = True
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
                sim.write_verbose_csv()
            battery = read_energy_evidence(path)['battery']
            self.assertFalse(battery['known'])
            self.assertIsNone(battery['applied_charge_kwh'])
            self.assertEqual(0, battery['observed_applied_charge_kwh'])
            self.assertTrue(battery['records'][0]['charge_in_progress'])

    def test_failed_route_commit_does_not_credit_charging(self):
        sim = Simulation(in_place_config(), verbose=True)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('fail')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True))
        self.assertEqual(0, sim.amrs[0].total_energy_charged_kwh)
        self.assertFalse(any(r['event_type']=='battery_charge_applied' for r in sim.verbose_rows))

    def test_missing_credit_produces_mismatch_not_a_balanced_result(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(dispatch_config(), directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = [r for r in csv.DictReader(stream) if r['event_type']!='battery_charge_applied']
            result = summarize_energy(rows, complete=True, capabilities=[CAPABILITY, BATTERY_CAPABILITY], expected_amrs=['R-1'])
            self.assertTrue(result['battery']['known'])
            self.assertFalse(result['battery']['records'][0]['matches'])

    def test_missing_robot_summary_makes_coverage_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(dispatch_config(), directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = [r for r in csv.DictReader(stream) if r['event_type']!='battery_balance_summary']
            result = summarize_energy(rows, complete=True, capabilities=[CAPABILITY, BATTERY_CAPABILITY], expected_amrs=['R-1'])
            self.assertFalse(result['battery']['known'])
            self.assertIsNone(result['battery']['records'][0]['matches'])

    def test_duplicate_credit_and_repeated_export_do_not_double_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            sim, path = self.run_case(dispatch_config(), directory)
            sim.write_verbose_csv()
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(1, sum(r['event_type']=='battery_balance_summary' for r in rows))
            rows += [r.copy() for r in rows if r['event_type']=='battery_charge_applied']
            result = summarize_energy(rows, complete=True, capabilities=[CAPABILITY, BATTERY_CAPABILITY], expected_amrs=['R-1'])
            self.assertAlmostEqual(.001438, result['battery']['applied_charge_kwh'])
            self.assertTrue(result['battery']['records'][0]['matches'])

    def test_legacy_or_incomplete_evidence_does_not_claim_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(dispatch_config(), directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            for complete, caps, fleet in [(True, [CAPABILITY], ['R-1']),
                    (False, [CAPABILITY, BATTERY_CAPABILITY], ['R-1']),
                    (True, [CAPABILITY, BATTERY_CAPABILITY], None),
                    (True, [CAPABILITY, BATTERY_CAPABILITY], ['R-1', 'missing'])]:
                with self.subTest(complete=complete, capabilities=caps, fleet=fleet):
                    result = summarize_energy(rows, complete=complete, capabilities=caps, expected_amrs=fleet)['battery']
                    self.assertFalse(result['known'])
                    self.assertIsNone(result['applied_charge_kwh'])
                    self.assertAlmostEqual(.001438, result['observed_applied_charge_kwh'])

    def test_changed_final_state_is_a_reported_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(dispatch_config(), directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            summary = next(r for r in rows if r['event_type']=='battery_balance_summary')
            detail = json.loads(summary['details'])
            detail['final_kwh'] += .0001
            summary['details'] = json.dumps(detail)
            result = summarize_energy(rows, complete=True, capabilities=[CAPABILITY, BATTERY_CAPABILITY], expected_amrs=['R-1'])['battery']
            self.assertTrue(result['known'])
            self.assertFalse(result['records'][0]['matches'])
            self.assertAlmostEqual(-.0001, result['records'][0]['residual_kwh'])

    def test_conflicting_credit_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_case(dispatch_config(), directory)
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            changed = dict(next(r for r in rows if r['event_type']=='battery_charge_applied'), energy_kwh='1')
            with self.assertRaisesRegex(ValueError, 'Conflicting battery'):
                summarize_energy(rows + [changed])


if __name__ == '__main__':
    unittest.main()
