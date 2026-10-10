"""Consumable stock changes at confirmed replenishment, not request generation."""
import unittest
import contextlib
import io
import json
import csv
import tempfile
from pathlib import Path

from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def stock_config():
    config = grouped_config()
    config['simulation']['end_datetime'] = '2026-01-05T02:00:00'
    config['task_generation']['update_interval_sec'] = 3600
    config['task_generation']['categories']['stores'].update(generation_mode='threshold', scheduled_times=[],
        tracked_item_exchange=True, exchange_mode='top_up_only', requires_staff=False)
    config['payloads'][0].update(track_items=True, items={'Supply': {
        'max': 10, 'top_up_threshold': 2, 'consumption_per_day': 192}})
    return config


class TrackedStockReferenceTests(unittest.TestCase):
    def manager(self, config=None):
        return Simulation(config or stock_config()).task_generation_manager

    def quantities(self, manager):
        runtime = manager.generators[0].item_runtime['stores:D:group:G']
        return runtime['resource_quantities']['']

    def test_request_does_not_refill_stock_or_repeat_while_pending(self):
        manager = self.manager()
        first = manager.update_until(3600)
        self.assertEqual(1, len(first))
        self.assertAlmostEqual(2, self.quantities(manager)['Supply'])  # 10 - 192 / 24
        self.assertEqual([], manager.update_until(7200))
        self.assertEqual(0, self.quantities(manager)['Supply'])

    def test_confirmed_top_up_delivers_ordered_deficit_once(self):
        manager = self.manager()
        task = manager.update_until(3600)[0].task
        manager.task_state_changed(task, 'completed', event_time=4050)  # another unit used in 7.5 min
        self.assertAlmostEqual(9, self.quantities(manager)['Supply'])  # 1 remaining + 8 ordered
        manager.task_state_changed(task, 'completed', event_time=4050)
        self.assertAlmostEqual(9, self.quantities(manager)['Supply'])

    def test_failure_leaves_stock_depleted_and_allows_retry(self):
        manager = self.manager()
        task = manager.update_until(3600)[0].task
        manager.task_state_changed(task, 'failed', event_time=3600)
        self.assertAlmostEqual(2, self.quantities(manager)['Supply'])
        self.assertEqual(1, len(manager.update_until(4050)))
        self.assertAlmostEqual(1, self.quantities(manager)['Supply'])

    def test_closing_poll_retains_consumption_from_preceding_open_hour(self):
        config = stock_config()
        config['departments'][0].update(operating_start_time='00:00', operating_end_time='01:00')
        manager = self.manager(config)
        self.assertEqual([], manager.update_until(7200))
        self.assertAlmostEqual(2, self.quantities(manager)['Supply'])

    def test_category_inactive_dates_do_not_consume_stock(self):
        config = stock_config()
        config['simulation']['start_datetime'] = '2026-01-04T00:00:00'  # Sunday
        config['task_generation']['categories']['stores']['days_active'] = ['mon']
        manager = self.manager(config)
        self.assertEqual(1, len(manager.update_until(25 * 3600)))
        self.assertAlmostEqual(2, self.quantities(manager)['Supply'])

    def test_full_exchange_replaces_all_items_and_records_removed_stock(self):
        config = stock_config()
        config['task_generation']['categories']['stores']['exchange_mode'] = 'full_exchange'
        config['payloads'][0]['items']['Other'] = {'max': 20, 'top_up_threshold': 1, 'consumption_per_day': 24}
        manager = self.manager(config)
        task = manager.update_until(3600)[0].task
        manager.task_state_changed(task, 'completed', event_time=3600)
        self.assertEqual({'Supply': 10, 'Other': 20}, self.quantities(manager))
        rows = {row['item']: row for row in manager.tracked_item_balance()}
        self.assertAlmostEqual(2, rows['Supply']['removed'])
        self.assertAlmostEqual(19, rows['Other']['removed'])
        self.assertTrue(all(abs(row['difference']) < 1e-10 for row in rows.values()))

    def test_replace_empty_waits_until_zero_not_top_up_threshold(self):
        config = stock_config()
        config['task_generation']['categories']['stores']['exchange_mode'] = 'replace_empty'
        manager = self.manager(config)
        self.assertEqual([], manager.update_until(3600))
        task = manager.update_until(4500)[0].task
        self.assertEqual(0, self.quantities(manager)['Supply'])
        manager.task_state_changed(task, 'completed', event_time=4500)
        self.assertEqual(10, self.quantities(manager)['Supply'])

    def test_zone_arrival_does_not_refill_before_confirmed_staff_handoff(self):
        manager = self.manager()
        task = manager.update_until(3600)[0].task
        task.dropoff_zone = 'B'
        manager.task_state_changed(task, 'completed', event_time=3600)
        self.assertEqual(2, self.quantities(manager)['Supply'])
        manager.task_state_changed(task, 'tracked_items_delivered', event_time=4050)
        self.assertEqual(9, self.quantities(manager)['Supply'])

    def test_full_simulation_deliveries_conserve_stock_through_demand_horizon(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/tracked-stock.json'
        config = json.loads(path.read_text(encoding='utf-8'))
        for data in (config, JsonStore(config).data):
            sim = Simulation(data)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual(2, len(sim.completed_task_records))
            row, = sim.task_generation_manager.tracked_item_balance()
            self.assertAlmostEqual(16, row['consumed'])
            self.assertAlmostEqual(16, row['delivered'])
            self.assertAlmostEqual(10, row['remaining'])
            self.assertAlmostEqual(0, row['difference'])

    def test_full_simulation_failures_record_unmet_demand_without_phantom_supply(self):
        config = stock_config()
        config['task_generation']['update_interval_sec'] = 3600
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2, len(sim.failed_task_ids))
        row, = sim.task_generation_manager.tracked_item_balance()
        self.assertEqual(10, row['consumed'])
        self.assertEqual(6, row['unmet'])
        self.assertEqual(0, row['remaining'])
        self.assertEqual(0, row['delivered'])
        self.assertEqual(0, row['difference'])

    def test_invalid_item_quantities_and_exchange_mode_are_rejected(self):
        for field, value in [('max', 0), ('max', 'nan'), ('top_up_threshold', 11),
                             ('top_up_threshold', -1), ('consumption_per_day', True)]:
            config = stock_config()
            config['payloads'][0]['items']['Supply'][field] = value
            with self.assertRaisesRegex(ValueError, field):
                Simulation(config)
        config = stock_config()
        config['task_generation']['categories']['stores']['exchange_mode'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'exchange_mode'):
            Simulation(config)

    def test_ignored_usage_rate_label_has_visible_unsupported_finding(self):
        config = stock_config()
        config['payloads'][0]['items']['Supply']['usage_rate'] = 'sporadic'
        findings = check_project(config, include_legacy=False).findings
        self.assertTrue(any(f.code == 'GENERATION_UNSUPPORTED' and f.path.endswith('/usage_rate') for f in findings))

    def test_full_stock_at_equal_threshold_does_not_create_zero_quantity_request(self):
        config = stock_config()
        config['payloads'][0]['items']['Supply'].update(top_up_threshold=10, consumption_per_day=0)
        self.assertEqual([], self.manager(config).update_until(3600))

    def test_scheduled_top_ups_share_the_stock_balance_and_deduct_incoming_orders(self):
        config = stock_config()
        config['task_generation']['categories']['stores'].update(generation_mode='scheduled', scheduled_times=['01:00', '01:15'])
        manager = self.manager(config)
        first, = manager.update_until(3600)
        second, = manager.update_until(4500)
        self.assertEqual(8, first.task.tracked_items['Supply']['delivery_quantity'])
        self.assertEqual(2, second.task.tracked_items['Supply']['delivery_quantity'])
        manager.task_state_changed(first.task, 'completed', event_time=4500)
        manager.task_state_changed(second.task, 'completed', event_time=4500)
        self.assertEqual(10, self.quantities(manager)['Supply'])
        row, = manager.tracked_item_balance()
        self.assertEqual(10, row['consumed'])
        self.assertEqual(10, row['delivered'])
        self.assertEqual(0, row['difference'])

    def test_older_poll_does_not_move_consumption_watermark_backwards(self):
        manager = self.manager()
        task = manager.update_until(3600)[0].task
        manager.task_state_changed(task, 'completed', event_time=4050)
        manager.update_until(3600)
        manager.update_until(4500)
        self.assertAlmostEqual(8, self.quantities(manager)['Supply'])
        row, = manager.tracked_item_balance()
        self.assertAlmostEqual(10, row['consumed'])
        self.assertAlmostEqual(0, row['difference'])

    def test_final_stock_and_requests_are_saved_once_as_recorded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.csv'
            sim = Simulation(stock_config(), verbose=True, verbose_csv_path=str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            sim.write_verbose_csv()
            sim.write_verbose_csv()
            with path.open(encoding='utf-8-sig', newline='') as stream:
                records = list(csv.DictReader(stream))
            summaries = [json.loads(row['details']) for row in records if row['event_type'] == 'tracked_stock_balance_summary']
            requests = [json.loads(row['details']) for row in records if row['event_type'] == 'tracked_stock_request']
            self.assertEqual(1, len(summaries))
            self.assertEqual(2, len(requests))
            self.assertEqual({'delivered'}, {row['status'] for row in requests})
            self.assertAlmostEqual(16, sum(row['quantities']['Supply'] for row in requests))
            self.assertAlmostEqual(16, summaries[0]['delivered'])
            self.assertAlmostEqual(10, summaries[0]['remaining'])
            self.assertEqual(1, sum(row['event_type'] == 'tracked_stock_coverage' for row in records))

    def test_full_simulation_zone_handoff_confirms_supply(self):
        config = stock_config()
        config['task_generation']['update_interval_sec'] = 3600
        config['locations'].append(dict(name='Ward', floor=0, x=6, y=10))
        config['departments'][0]['task_generation_locations'] = {'stores': {
            'pickup_dropoff_locations': ['Ward'], 'dropoff_zone_locations': ['B']}}
        config['task_generation']['categories']['stores'].update(staff_handling_minutes=0, staff_collection_delay_minutes=0)
        for available, consumed, delivered, remaining, unmet in [(False, 10, 8, 8, 6), (True, 16, 16, 10, 0)]:
            with self.subTest(staff_available_during_demand=available):
                if available:
                    config['task_generation']['staff_config'] = {'enabled': False, 'default_handling_minutes': 0}
                sim = Simulation(config)
                with contextlib.redirect_stdout(io.StringIO()):
                    sim.run()
                row, = sim.task_generation_manager.tracked_item_balance()
                self.assertEqual('Ward', row['location'])
                self.assertAlmostEqual(consumed, row['consumed'])
                self.assertAlmostEqual(delivered, row['delivered'])
                self.assertAlmostEqual(remaining, row['remaining'])
                self.assertAlmostEqual(unmet, row['unmet'])
                self.assertAlmostEqual(0, row['difference'])


if __name__ == '__main__':
    unittest.main()
