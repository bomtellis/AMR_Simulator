"""Legacy collection failures must not destroy or duplicate accrued waste."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from simulator import Simulation
from tests.test_waste_conservation import legacy_config
from amr_results_investigation import load_investigation
from amr_waste_evidence import summarize_waste_volume
from tests.test_waste_volume_balance import volume_config


def legacy_balance_config():
    config = legacy_config()
    config['simulation'].update(start_datetime='2026-01-05T09:00:00', end_datetime='2026-01-05T10:00:00')
    config['departments'][0]['operating_end_time'] = '12:00'
    config['task_generation']['update_interval_sec'] = 3600
    config['waste_streams'][0]['full_threshold_fraction'] = 0.6
    return config


class LegacyWasteBalanceTests(unittest.TestCase):
    def manager(self):
        return Simulation(legacy_balance_config()).task_generation_manager

    def balance(self, manager):
        row, = manager.waste_volume_balance()
        self.assertAlmostEqual(0, row['difference_m3'], delta=1e-10)
        return row

    def test_pre_pickup_failure_restores_fill_once_and_allows_retry(self):
        manager = self.manager()
        record, = manager.update_until(3600)
        manager.task_state_changed(record.task, 'failed')
        manager.task_state_changed(record.task, 'failed')
        runtime = manager.generators[0].runtime['D']['General']
        self.assertAlmostEqual(0.6, runtime['fill_m3'])
        retried = manager.update_until(3601)
        self.assertEqual(1, len(retried))
        row = self.balance(manager)
        self.assertAlmostEqual(0.6, row['pending_m3'])
        self.assertAlmostEqual(0.6, row['restored_after_failure_m3'])
        self.assertAlmostEqual(0.6 / 3600, row['residual_m3'])

    def test_pending_collection_has_explicit_allocation(self):
        manager = self.manager()
        record, = manager.update_until(3600)
        row = self.balance(manager)
        self.assertEqual('department_waste', row['generator_type'])
        self.assertAlmostEqual(0.6, row['accrued_m3'])
        self.assertAlmostEqual(0.6, row['pending_m3'])
        self.assertEqual(record.task.id, row['collections'][0]['task_id'])
        self.assertEqual([], manager.update_until(3600))

    def test_failure_after_pickup_stays_unconfirmed_and_is_not_retried(self):
        manager = self.manager()
        record, = manager.update_until(3600)
        record.task.payload_instance_picked_up = True
        manager.task_state_changed(record.task, 'failed')
        manager.task_state_changed(record.task, 'failed')
        row = self.balance(manager)
        self.assertAlmostEqual(0.6, row['unconfirmed_m3'])
        self.assertEqual(0, row['residual_m3'])
        self.assertEqual([], manager.update_until(3601))

    def test_completion_and_return_callbacks_cannot_count_volume_twice(self):
        manager = self.manager()
        record, = manager.update_until(3600)
        manager.task_state_changed(record.task, 'completed')
        manager.task_state_changed(record.task, 'completed')
        returned = copy.deepcopy(record.task)
        returned.is_return_task = True
        manager.task_state_changed(returned, 'failed')
        row = self.balance(manager)
        self.assertAlmostEqual(0.6, row['completed_m3'])
        self.assertEqual(0, row['residual_m3'])
        self.assertEqual(0, row['unconfirmed_m3'])

    def run_saved(self, config):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.csv'
            sim = Simulation(config, verbose=True, verbose_csv_path=str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            sim.write_verbose_csv()
            sim.write_verbose_csv()
            return sim, load_investigation(path)

    def test_saved_success_reconciles_legacy_generated_event(self):
        scenario = Path(__file__).resolve().parents[1] / 'verification/scenarios/legacy-waste-balance.json'
        sim, result = self.run_saved(json.loads(scenario.read_text(encoding='utf-8')))
        row = self.balance(sim.task_generation_manager)
        self.assertAlmostEqual(0.6, row['completed_m3'])
        metric = next(m for m in result['metrics'] if m['key'] == 'waste_volume_balance')
        self.assertEqual('Reconciled', metric['value'], result['findings'])
        types = {e['type'] for e in result['events'] if e['id'] in metric['event_ids']}
        self.assertIn('waste_task_generated', types)

    def test_saved_blocked_route_retains_all_accrued_volume(self):
        config = legacy_balance_config()
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim, result = self.run_saved(config)
        row = self.balance(sim.task_generation_manager)
        self.assertAlmostEqual(0.6, row['residual_m3'])
        self.assertAlmostEqual(0.6, row['restored_after_failure_m3'])
        self.assertEqual(0, row['completed_m3'])
        self.assertEqual('Reconciled', next(m['value'] for m in result['metrics'] if m['key'] == 'waste_volume_balance'))

    def test_repeated_failed_attempts_do_not_inflate_accrued_volume(self):
        config = legacy_balance_config()
        config['simulation']['end_datetime'] = '2026-01-05T11:00:00'
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim, result = self.run_saved(config)
        row = self.balance(sim.task_generation_manager)
        self.assertAlmostEqual(1.2, row['accrued_m3'])
        self.assertAlmostEqual(1.2, row['residual_m3'])
        self.assertAlmostEqual(1.8, row['restored_after_failure_m3'])
        self.assertEqual(3, len(row['collections']))
        self.assertEqual('Reconciled', next(m['value'] for m in result['metrics'] if m['key'] == 'waste_volume_balance'))

    def test_older_dynamic_evidence_retains_its_original_scope(self):
        _, result = self.run_saved(volume_config())
        events = copy.deepcopy(result['events'])
        for event in events:
            if event['type'] == 'waste_volume_balance_coverage':
                data = json.loads(event['row']['details'])
                data.update(schema_version=1, scope='dynamic_accumulated_waste_only')
                event['row']['details'] = json.dumps(data)
            elif event['type'] == 'waste_volume_balance_summary':
                data = json.loads(event['row']['details']); data.pop('generator_type')
                event['row']['details'] = json.dumps(data)
        old = summarize_waste_volume(events, complete=True, capabilities=['waste_volume_balance_v1'])
        self.assertTrue(old['known'])
        self.assertTrue(old['matches'], old['issues'])
        self.assertEqual('dynamic_accumulated_waste_only', old['scope'])
        self.assertAlmostEqual(1, old['totals']['accrued_m3'])
        wrong = summarize_waste_volume(events, complete=True, capabilities=['waste_volume_balance_v2'])
        self.assertFalse(wrong['known'])

    def test_legacy_evidence_requires_identified_generator_and_generated_record(self):
        _, result = self.run_saved(legacy_balance_config())
        events = copy.deepcopy(result['events'])
        missing = [e for e in events if e['type'] != 'waste_task_generated']
        stock = summarize_waste_volume(missing, complete=True, capabilities=['waste_volume_balance_v2'])
        self.assertTrue(stock['known'])
        self.assertFalse(stock['matches'])
        summary = next(e for e in events if e['type'] == 'waste_volume_balance_summary')
        data = json.loads(summary['row']['details']); data.pop('generator_type')
        summary['row']['details'] = json.dumps(data)
        stock = summarize_waste_volume(events, complete=True, capabilities=['waste_volume_balance_v2'])
        self.assertFalse(stock['known'])
        self.assertIsNone(stock['totals']['accrued_m3'])

    def test_inactive_department_has_explicit_zero_balance(self):
        config = legacy_balance_config()
        config['departments'][0]['enabled'] = False
        manager = Simulation(config).task_generation_manager
        self.assertEqual([], manager.update_until(3600))
        row = self.balance(manager)
        self.assertEqual(0, row['accrued_m3'])
        self.assertEqual([], row['collections'])


if __name__ == '__main__':
    unittest.main()
