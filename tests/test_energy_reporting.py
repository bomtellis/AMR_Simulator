"""Shared journeys are counted once; missing attribution is not zero energy."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from simulator import Simulation
from tests.test_delivery_energy_reference import lift_config
from amr_results_investigation import load_investigation
from report.amr_energy_evidence import CAPABILITY, summarize_energy, read_energy_evidence
from report.amr_report_analysis import analyse
from visualiser.results_investigation_panel import display
from visualiser.models import JsonStore


class EnergyReportingTests(unittest.TestCase):
    def row(self, event_id='E1', source='amr_battery', energy=.002):
        kind = 'corridor' if source == 'amr_battery' else 'lift_transfer'
        return dict(event_id=event_id, event_type='multi_stop_segment_' + kind,
                    segment_type=kind, energy_kwh=str(energy), journey_id='J1', lift_id='L1',
                    task_id='T1,T2', details=json.dumps(dict(energy_kwh=energy, energy_source=source)))

    def run_batch(self, directory, cfg=None):
        if cfg is None:
            cfg = lift_config()
            cfg['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        path = Path(directory) / 'simulation_steps.csv'
        sim = Simulation(cfg, verbose=True, verbose_csv_path=str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        return sim, path

    def test_saved_reference_raw_and_editor_normalised(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/shared-journey-energy.json'
        for normalise in (False, True):
            with self.subTest(editor_normalised=normalise), tempfile.TemporaryDirectory() as directory:
                cfg = json.loads(path.read_text(encoding='utf-8'))
                sim, log = self.run_batch(directory, JsonStore(cfg).data if normalise else cfg)
                self.assertEqual(2, len(sim.completed_task_records))
                self.assertAlmostEqual((960 * 1.07 + 1020 * 9.81 * 3 + 400) / 3600000,
                                       read_energy_evidence(log)['total_kwh'])

    def test_task_records_do_not_repeat_shared_journey_energy_as_task_energy(self):
        with tempfile.TemporaryDirectory() as directory:
            sim, _path = self.run_batch(directory)
            self.assertEqual(2, len(sim.completed_task_records))
            expected = (960 * 1.07 + 1020 * 9.81 * 3 + 400) / 3600000
            for record in sim.completed_task_records:
                self.assertIsNone(record['energy_kwh'])
                self.assertEqual('shared_journey_not_allocated', record['energy_basis'])
                self.assertAlmostEqual(expected, record['journey_energy_kwh'])
            matrix = Path(directory) / 'transport.csv'
            sim.write_transport_matrix_csv(str(matrix))
            with matrix.open(newline='', encoding='utf-8') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual('2', row['trips'])
            self.assertEqual('', row['total_energy_kwh'])
            self.assertEqual('shared_journey_not_allocated', row['energy_basis'])

    def test_shared_event_is_counted_once_and_charge_input_is_excluded(self):
        row = self.row()
        charge = dict(self.row('CHARGE'), event_type='segment_charge', segment_type='charge', energy_kwh='50')
        ledger = summarize_energy([row, row.copy(), self.row('LIFT', 'lift_supply', .01), charge],
                                  complete=True, capabilities=[CAPABILITY])
        self.assertAlmostEqual(.012, ledger['total_kwh'])
        self.assertEqual(['E1'], ledger['sources']['amr_battery']['event_ids'])
        self.assertEqual(['E1', 'LIFT'], ledger['journeys']['J1']['event_ids'])

    def test_conflicting_duplicate_energy_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting energy'):
            summarize_energy([self.row(), self.row(energy=.003)])

    def test_missing_attribution_is_not_zero(self):
        row = self.row()
        row['details'] = '{}'
        ledger = summarize_energy([row], complete=True, capabilities=[CAPABILITY])
        self.assertIsNone(ledger['sources']['amr_battery']['value_kwh'])
        self.assertEqual(['E1'], ledger['sources']['amr_battery']['missing_event_ids'])

    def test_incomplete_and_legacy_logs_do_not_claim_complete_energy(self):
        for complete, capabilities in [(False, [CAPABILITY]), (True, [])]:
            with self.subTest(complete=complete):
                ledger = summarize_energy([self.row()], complete=complete, capabilities=capabilities)
                self.assertIsNone(ledger['total_kwh'])
                self.assertIsNone(ledger['sources']['amr_battery']['value_kwh'])
                self.assertEqual(.002, ledger['sources']['amr_battery']['observed_kwh'])

    def test_zero_is_only_known_with_complete_capability_evidence(self):
        self.assertEqual(0, summarize_energy([], complete=True, capabilities=[CAPABILITY])['total_kwh'])
        self.assertIsNone(summarize_energy([], complete=True)['total_kwh'])

    def test_mismatched_negative_and_nonfinite_energy_is_unknown(self):
        for value in ('-1', 'nan', 'inf', '0.003', ''):
            with self.subTest(value=value):
                row = self.row()
                row['energy_kwh'] = value
                self.assertIsNone(summarize_energy([row], complete=True,
                    capabilities=[CAPABILITY])['sources']['amr_battery']['value_kwh'])

    def test_independent_batch_balance_matches_investigation_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            sim, path = self.run_batch(directory)
            motor = 960 * 1.07 / 3600000
            lift = (1020 * 9.81 * 3 + 400) / 3600000
            investigation = load_investigation(path)
            ledger = investigation['energy']
            self.assertAlmostEqual(motor + lift, ledger['total_kwh'])
            self.assertAlmostEqual(sim.amrs[0].total_energy_used_kwh, ledger['sources']['amr_battery']['value_kwh'])
            metrics = {m['key']: m for m in investigation['metrics']}
            self.assertAlmostEqual(motor, metrics['amr_battery_energy_kwh']['value'])
            self.assertAlmostEqual(lift, metrics['lift_supply_energy_kwh']['value'])
            self.assertEqual(1, len(ledger['journeys']))
            with contextlib.redirect_stdout(io.StringIO()):
                report = analyse(path, .8, .8)
            self.assertAlmostEqual(motor + lift, report['energy_summary']['planned_kwh'].sum())
            self.assertAlmostEqual(lift, report['lift_summary']['lift_energy_kwh'].sum())
            self.assertEqual(ledger, report['energy_evidence'])

    def test_legacy_report_does_not_turn_missing_lift_energy_into_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_batch(directory)
            Path(str(path) + '.run.json').unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                report = analyse(path, .8, .8)
            self.assertTrue(report['energy_summary']['planned_kwh'].isna().all())
            self.assertTrue(report['lift_summary']['lift_energy_kwh'].isna().all())

    def test_small_energy_is_visible_in_investigation(self):
        self.assertEqual('0.000276', display(.000276))

    def test_modified_csv_invalidates_complete_energy_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            _sim, path = self.run_batch(directory)
            with path.open('a', encoding='utf-8') as stream:
                stream.write('\n')
            self.assertIsNone(read_energy_evidence(path)['total_kwh'])


if __name__ == '__main__':
    unittest.main()
