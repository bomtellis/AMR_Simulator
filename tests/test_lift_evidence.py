"""Independent lift-plan invariants, coverage boundaries and UI event links."""
import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from amr_lift_evidence import CAPABILITY, check_lift_movements
from amr_results_investigation import load_investigation
from amr_run_evidence import file_hash
from simulator import Simulation
from tests.test_lift_reservation_order import saved_config
from visualiser.results_investigation_panel import ResultsInvestigationPanel


def movement(identity, start, origin, destination, *, duration=5, lift='L', kind='transfer'):
    return {'id': identity, 'identity': 'native', 'type': 'segment_lift_' + kind,
            'time_seconds': start, 'duration_seconds': duration, 'lift_id': lift,
            'row': {'details': json.dumps({'from': f'{lift}-F{origin}', 'to': f'{lift}-F{destination}'}),
                    'from_location': 'Waiting node', 'to_location': 'Waiting node',
                    'start_floor': 99, 'end_floor': 99}}


def audit(events, *, initial=0, complete=True, expected=None, capabilities=(CAPABILITY,)):
    return check_lift_movements(events, {'lifts': [{'id': 'L', 'start_floor': initial}]},
        complete=complete, capabilities=capabilities,
        expected={'L': {'transfer': 2, 'reposition': 0}} if expected is None else expected)


class LiftEvidenceTests(unittest.TestCase):
    def test_continuous_floor_sequence_uses_explicit_lift_nodes(self):
        result = audit([movement('a', 0, -1, 2), movement('b', 5, 2, -1)], initial=-1)
        self.assertTrue(result['known'])
        self.assertEqual('Consistent', result['records'][0]['status'])
        self.assertEqual([], result['issues'])

    def test_first_and_later_floor_discontinuities_link_exact_events(self):
        result = audit([movement('a', 0, 1, 2), movement('b', 5, 0, 1)])
        self.assertTrue(result['known'])  # Complete evidence can prove a conflict.
        self.assertEqual('Conflict', result['records'][0]['status'])
        self.assertEqual([['a'], ['a', 'b']], [p['event_ids'] for p in result['issues']])
        self.assertTrue(all(p['kind'] == 'floor_discontinuity' for p in result['issues']))

    def test_nested_overlap_checks_longest_active_interval(self):
        result = audit([movement('a', 0, 0, 1, duration=30),
                        movement('b', 5, 0, 1), movement('c', 15, 0, 1)],
                       expected={'L': {'transfer': 3, 'reposition': 0}})
        overlaps = [p for p in result['issues'] if p['kind'] == 'overlap']
        self.assertEqual([['a', 'b'], ['a', 'c']], [p['event_ids'] for p in overlaps])

    def test_touching_and_rounding_tolerance_are_not_overlaps(self):
        for start, overlaps in ((5, 0), (4.999, 0), (4.997, 1)):
            with self.subTest(start=start):
                result = audit([movement('a', 0, 0, 1), movement('b', start, 1, 0)])
                self.assertEqual(overlaps, sum(p['kind'] == 'overlap' for p in result['issues']))

    def test_different_lifts_can_move_at_the_same_time(self):
        result = check_lift_movements([movement('a', 0, 0, 1), movement('b', 0, 0, 1, lift='Other')],
            {'lifts': [{'id': 'L'}, {'id': 'Other'}]}, complete=True, capabilities=[CAPABILITY],
            expected={name: {'transfer': 1, 'reposition': 0} for name in ('L', 'Other')})
        self.assertTrue(result['known'])
        self.assertEqual([], result['issues'])

    def test_missing_reposition_endpoints_do_not_use_waiting_robot_floor(self):
        event = movement('a', 0, 0, 1, kind='reposition')
        event['row']['details'] = '{"from_floor": 99, "to_floor": 99}'
        result = audit([event], expected={'L': {'transfer': 0, 'reposition': 1}})
        self.assertFalse(result['known'])
        self.assertEqual('Incomplete evidence', result['records'][0]['status'])
        self.assertEqual(['a'], result['issues'][0]['event_ids'])

    def test_malformed_movement_is_not_silently_bridged(self):
        events = [movement('a', 0, 0, 1), movement('b', 5, 1, 2), movement('c', 10, 2, 0)]
        events[1]['duration_seconds'] = float('nan')
        result = audit(events, expected={'L': {'transfer': 3, 'reposition': 0}})
        self.assertFalse(result['known'])
        self.assertFalse(any(p['kind'] == 'floor_discontinuity' for p in result['issues']))

    def test_invalid_and_zero_time_vertical_movements_are_incomplete(self):
        for duration in (-1, float('inf'), None, 0):
            with self.subTest(duration=duration):
                result = audit([movement('a', 0, 0, 1, duration=duration)],
                               expected={'L': {'transfer': 1, 'reposition': 0}})
                self.assertFalse(result['known'])

    def test_missing_or_inconsistent_booking_counts_never_prove_clean(self):
        for counts in ({}, {'L': {'transfer': True, 'reposition': 0}},
                       {'L': {'transfer': 1, 'reposition': 0}}):
            result = audit([], expected=counts)
            self.assertFalse(result['known'])
        self.assertEqual('Conflict', result['records'][0]['status'])
        self.assertEqual('count_mismatch', result['issues'][0]['kind'])

    def test_verified_no_activity_is_distinct_from_partial_no_activity(self):
        counts = {'L': {'transfer': 0, 'reposition': 0}}
        self.assertTrue(audit([], expected=counts)['known'])
        self.assertFalse(audit([], expected=counts, complete=False)['known'])
        self.assertFalse(audit([], expected=counts, capabilities=[])['known'])
        self.assertFalse(check_lift_movements([], complete=True, capabilities=[CAPABILITY], expected={})['known'])

    def test_legacy_observation_retains_conflict_without_full_coverage(self):
        events = [movement('a', 0, 0, 1), movement('b', 2, 0, 1)]
        for event in events:
            event['identity'] = 'legacy row identifier'
        result = audit(events, complete=False)
        self.assertFalse(result['known'])
        self.assertEqual('Conflict', result['records'][0]['status'])
        self.assertEqual(1, sum(p['kind'] == 'overlap' for p in result['issues']))

    def test_conflicting_endpoints_are_not_silently_preferred(self):
        event = movement('a', 0, 0, 1)
        event['row']['from_location'] = 'L-F2'
        result = audit([event], expected={'L': {'transfer': 1, 'reposition': 0}})
        self.assertFalse(result['known'])
        self.assertTrue(any('Conflicting' in p['reason'] for p in result['issues']))

    def test_undeclared_lift_prevents_known_coverage(self):
        result = audit([movement('a', 0, 0, 1, lift='Unknown')], expected={'L': {'transfer': 0, 'reposition': 0}})
        self.assertFalse(result['known'])
        unknown = next(r for r in result['records'] if r['lift_id'] == 'Unknown')
        self.assertEqual('Incomplete evidence', unknown['status'])


class LiftEvidenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'simulation_steps.csv'
        self.sim = Simulation(saved_config(), verbose=True, verbose_csv_path=str(self.path))
        with contextlib.redirect_stdout(io.StringIO()):
            self.sim.run()
            self.sim.write_verbose_csv()

    def rewrite_rows(self, rows):
        with self.path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        # Controlled corruption fixture: preserve original booking counts and
        # bind modified bytes so the semantic checker, not checksum rejection,
        # must detect the discrepancy.
        sidecar = Path(str(self.path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['log_sha256'] = file_hash(self.path)
        sidecar.write_text(json.dumps(data))

    def rows(self):
        with self.path.open(newline='', encoding='utf-8-sig') as stream:
            return list(csv.DictReader(stream))

    def test_real_bookings_reconcile_and_ui_links_to_recorded_movements(self):
        result = load_investigation(self.path)
        check = result['lift_checks']
        self.assertTrue(check['known'])
        self.assertEqual({'transfer': 2, 'reposition': 1}, check['records'][0]['expected'])
        self.assertEqual('Consistent', check['records'][0]['status'])
        panel = ResultsInvestigationPanel()
        try:
            panel.accept_result(result)
            panel.lift_checks.selectRow(0)
            self.assertEqual(3, panel.events.rowCount())
            self.assertIn('Initial floor from saved inputs: 0', panel.details.toPlainText())
            panel.events.selectRow(0)
            self.assertIn('Source row:', panel.details.toPlainText())
        finally:
            panel.close()

    def test_investigation_keeps_the_original_log_source_path(self):
        self.assertEqual(str(self.path), load_investigation(self.path)['source'])

    def test_duplicate_native_lift_record_is_counted_once(self):
        rows = self.rows()
        rows.append(next(r for r in rows if r['segment_type'] == 'lift_transfer'))
        self.rewrite_rows(rows)
        result = load_investigation(self.path)
        self.assertTrue(result['lift_checks']['known'])
        self.assertEqual({'transfer': 2, 'reposition': 1}, result['lift_checks']['records'][0]['observed'])

    def test_removed_movement_is_detected_against_bookings_and_links_conflicts(self):
        rows = [r for r in self.rows() if r['segment_type'] != 'lift_reposition']
        self.rewrite_rows(rows)
        result = load_investigation(self.path)
        record = result['lift_checks']['records'][0]
        self.assertFalse(record['known'])
        self.assertEqual('Conflict', record['status'])
        self.assertTrue(any(p['kind'] == 'count_mismatch' for p in record['issues']))
        panel = ResultsInvestigationPanel()
        try:
            panel.accept_result(result)
            panel.lift_checks.selectRow(0)
            self.assertEqual(2, panel.events.rowCount())
            self.assertIn('differ from recorded', panel.details.toPlainText())
        finally:
            panel.close()

    def test_older_bound_run_retains_observations_but_not_verified_zero(self):
        sidecar = Path(str(self.path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['event_capabilities'].remove(CAPABILITY)
        data['summary'].pop('lift_movement_counts')
        sidecar.write_text(json.dumps(data))
        result = load_investigation(self.path)
        self.assertFalse(result['lift_checks']['known'])
        metric = next(m for m in result['metrics'] if m['key'] == 'lift_overlap')
        self.assertIsNone(metric['value'])
        self.assertEqual(0, metric['observed_count'])


if __name__ == '__main__':
    unittest.main()
