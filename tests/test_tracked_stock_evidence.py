"""Saved stock accounting reconciles against requests, outcomes and arrivals."""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from simulator import Simulation
from amr_results_investigation import load_investigation
from amr_tracked_stock_evidence import summarize_tracked_stock
from tests.test_tracked_stock_reference import stock_config

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from visualiser.results_investigation_panel import ResultsInvestigationPanel

CAPABILITIES = ['tracked_stock_balance_v1', 'tracked_stock_delivery_v1']


class TrackedStockEvidenceTests(unittest.TestCase):
    def run_saved(self, config=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.csv'
            sim = Simulation(config or stock_config(), verbose=True, verbose_csv_path=str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            sim.write_verbose_csv()
            sim.write_verbose_csv()
            return load_investigation(path)

    def reconciled(self, result):
        stock = result['tracked_stock']
        self.assertTrue(stock['known'], stock['issues'])
        self.assertTrue(stock['matches'], stock['issues'])
        return stock['records']

    def test_saved_direct_deliveries_reconcile_independent_two_hour_balance(self):
        result = self.run_saved()
        row, = self.reconciled(result)
        for key, value in dict(initial=10, delivered=16, confirmed_delivered=16,
                               consumed=16, removed=0, remaining=10, unmet=0).items():
            self.assertAlmostEqual(value, row[key])
        metrics = {m['key']: m for m in result['metrics']}
        self.assertEqual('Reconciled', metrics['tracked_stock_reconciliation']['value'])
        types = {e['type'] for e in result['events'] if e['id'] in row['event_ids']}
        self.assertTrue({'tracked_stock_delivery_confirmed', 'task_generated', 'task_complete',
                         'location_payload_enter'}.issubset(types))
        self.assertEqual(2, sum(e['type'] == 'tracked_stock_delivery_confirmed' for e in result['events']))

    def test_failed_deliveries_reconcile_unmet_demand_without_supply(self):
        config = stock_config()
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        row, = self.reconciled(self.run_saved(config))
        self.assertEqual((10, 6, 0, 0), (row['consumed'], row['unmet'], row['remaining'], row['confirmed_delivered']))

    def test_staff_receipts_follow_handoff_including_after_demand_horizon(self):
        config = stock_config()
        config['locations'].append(dict(name='Ward', floor=0, x=6, y=10))
        config['departments'][0]['task_generation_locations'] = {'stores': {
            'pickup_dropoff_locations': ['Ward'], 'dropoff_zone_locations': ['B']}}
        config['task_generation']['categories']['stores'].update(staff_handling_minutes=0, staff_collection_delay_minutes=0)
        for available, expected in [(False, (10, 8, 8, 6)), (True, (16, 16, 10, 0))]:
            with self.subTest(staff_available=available):
                if available:
                    config['task_generation']['staff_config'] = {'enabled': False, 'default_handling_minutes': 0}
                result = self.run_saved(config)
                row, = self.reconciled(result)
                self.assertEqual(expected, tuple(row[k] for k in ['consumed', 'delivered', 'remaining', 'unmet']))
                receipts = [e for e in result['events'] if e['type'] == 'tracked_stock_delivery_confirmed']
                self.assertTrue(all(json.loads(e['row']['details'])['confirmation'] == 'tracked_items_delivered' for e in receipts))
                if not available:
                    self.assertGreater(receipts[0]['time_seconds'], 7200)

    def test_full_exchange_accounts_for_discarded_contents_separately(self):
        config = stock_config()
        config['simulation']['end_datetime'] = '2026-01-05T01:00:00'
        config['task_generation']['categories']['stores']['exchange_mode'] = 'full_exchange'
        config['payloads'][0]['items']['Other'] = {'max': 20, 'top_up_threshold': 1, 'consumption_per_day': 24}
        rows = {r['item']: r for r in self.reconciled(self.run_saved(config))}
        for item, remaining, removed in [('Supply', 10, 2), ('Other', 20, 19)]:
            self.assertEqual(remaining, rows[item]['remaining'])
            self.assertEqual(removed, rows[item]['confirmed_removed'])

    def test_missing_or_partial_receipt_evidence_is_unknown(self):
        for complete, capabilities in [(False, CAPABILITIES), (True, ['tracked_stock_balance_v1'])]:
            stock = summarize_tracked_stock([], complete=complete, capabilities=capabilities)
            self.assertFalse(stock['known'])
            self.assertIsNone(stock['matches'])
            self.assertEqual([], stock['records'])

    def test_metric_selection_shows_linked_receipts_and_balance(self):
        app = QApplication.instance() or QApplication([])
        result = self.run_saved()
        panel = ResultsInvestigationPanel()
        try:
            panel.accept_result(result)
            index = next(i for i, m in enumerate(result['metrics']) if m['key'] == 'tracked_stock_0_remaining')
            panel.metrics.selectRow(index)
            self.assertEqual(set(result['metrics'][index]['event_ids']), {e['id'] for e in panel.event_rows})
            self.assertIn('Initial 10 + supplied 16', panel.timeline_label.text())
        finally:
            panel.close()

    def test_new_run_without_stock_has_explicit_empty_coverage(self):
        config = stock_config()
        config['payloads'][0]['track_items'] = False
        config['task_generation']['categories']['stores']['tracked_item_exchange'] = False
        self.assertEqual([], self.reconciled(self.run_saved(config)))

    def test_inconsistent_records_cannot_reconcile(self):
        original = self.run_saved()['events']
        cases = [('tracked_stock_balance_summary', 'remaining', 123),
                 ('tracked_stock_delivery_confirmed', 'quantities', {'Supply': 9}),
                 ('tracked_stock_delivery_confirmed', 'removed', {'Supply': 1})]
        for kind, field, value in cases:
            with self.subTest(kind=kind, field=field):
                events = copy.deepcopy(original)
                event = next(e for e in events if e['type'] == kind)
                data = json.loads(event['row']['details']); data[field] = value
                event['row']['details'] = json.dumps(data)
                result = summarize_tracked_stock(events, complete=True, capabilities=CAPABILITIES)
                self.assertTrue(result['known'])
                self.assertFalse(result['matches'])
        events = copy.deepcopy(original)
        generated = next(e for e in events if e['type'] == 'task_generated')
        generated['row']['tracked_items'] = json.dumps({'Supply': {'delivery_quantity': 999}})
        self.assertFalse(summarize_tracked_stock(events, complete=True, capabilities=CAPABILITIES)['matches'])
        events = [e for e in original if e['type'] not in {'location_payload_enter', 'payload_service_arrival'}]
        self.assertFalse(summarize_tracked_stock(events, complete=True, capabilities=CAPABILITIES)['matches'])

    def test_wrong_outcome_receipt_time_and_late_arrivals_are_conflicts(self):
        original = self.run_saved()['events']
        for action in ['missing_completion', 'early_receipt', 'late_arrival', 'wrong_payload']:
            with self.subTest(action=action):
                events = copy.deepcopy(original)
                if action == 'missing_completion':
                    events = [e for e in events if e['type'] != 'task_complete']
                for event in events:
                    if action == 'early_receipt' and event['type'] == 'tracked_stock_delivery_confirmed':
                        event['time_seconds'] = 0
                    if event['type'] in {'location_payload_enter', 'payload_service_arrival'}:
                        if action == 'late_arrival':
                            event['time_seconds'] = 999999
                        elif action == 'wrong_payload':
                            event['payload_instance_id'] = 'different-payload'
                result = summarize_tracked_stock(events, complete=True, capabilities=CAPABILITIES)
                self.assertTrue(result['known'])
                self.assertFalse(result['matches'])

    def test_missing_duplicate_and_malformed_records_are_unknown(self):
        original = self.run_saved()['events']
        for action in ['missing_receipt', 'duplicate_receipt', 'malformed_balance', 'duplicate_balance']:
            with self.subTest(action=action):
                events = copy.deepcopy(original)
                kind = 'tracked_stock_delivery_confirmed' if 'receipt' in action else 'tracked_stock_balance_summary'
                event = next(e for e in events if e['type'] == kind)
                if action.startswith('missing'):
                    events.remove(event)
                elif action.startswith('duplicate'):
                    events.append(copy.deepcopy(event))
                else:
                    data = json.loads(event['row']['details']); data['remaining'] = True
                    event['row']['details'] = json.dumps(data)
                result = summarize_tracked_stock(events, complete=True, capabilities=CAPABILITIES)
                self.assertFalse(result['known'])
                self.assertIsNone(result['matches'])


if __name__ == '__main__':
    unittest.main()
