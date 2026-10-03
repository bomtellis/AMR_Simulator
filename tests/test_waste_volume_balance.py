"""One cubic metre must remain accounted for across collection outcomes."""
import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path
import unittest

from simulator import Simulation
from tests.test_waste_conservation import dynamic_config
from amr_results_investigation import load_investigation
from amr_waste_evidence import summarize_waste_volume


def volume_config():
    config = dynamic_config()
    config['simulation']['end_datetime'] = '2026-01-05T01:00:00'
    config['task_generation']['update_interval_sec'] = 3600
    config['building']['edge_slowdown_per_amr'] = 0
    return config


class WasteVolumeBalanceTests(unittest.TestCase):
    def balance(self, manager):
        row, = manager.waste_volume_balance()
        self.assertAlmostEqual(0, row['difference_m3'], delta=1e-10)
        return row

    def test_pending_collections_and_residual_reconcile_one_hour_of_accrual(self):
        sim = Simulation(volume_config())
        records = sim.task_generation_manager.update_until(3600)
        self.assertEqual(2, len(records))
        row = self.balance(sim.task_generation_manager)
        self.assertAlmostEqual(1, row['accrued_m3'])
        self.assertAlmostEqual(0.8, row['pending_m3'])
        self.assertAlmostEqual(0.2, row['residual_m3'])
        self.assertEqual({r.task.id for r in records}, {r['task_id'] for r in row['collections']})

    def test_multiple_route_pairs_do_not_multiply_the_same_pool_volume(self):
        config = volume_config()
        config['locations'].append(dict(name='C', floor=0, x=0, y=10))
        config['task_generation']['categories']['waste']['dropoff_locations'] = ['C']
        records = Simulation(config).task_generation_manager.update_until(3600)
        self.assertEqual(2, len(records))
        self.assertEqual(['B', 'C'], [r.task.dropoff for r in records])
        self.assertAlmostEqual(0.8, sum(r.task.waste_volume_m3 for r in records))

    def test_failed_before_pickup_restores_volume_once_and_can_retry(self):
        manager = Simulation(volume_config()).task_generation_manager
        failed = manager.update_until(3600)[0].task
        manager.task_state_changed(failed, 'failed')
        manager.task_state_changed(failed, 'failed')
        self.assertAlmostEqual(0.6, manager.generators[0].runtime['department:D:General']['volume'])
        row = self.balance(manager)
        self.assertAlmostEqual(0.4, row['pending_m3'])
        self.assertAlmostEqual(0.4, row['restored_after_failure_m3'])
        self.assertEqual(4, len(manager.update_until(7200)))  # 0.6 residual + 1 newly accrued
        row = self.balance(manager)
        self.assertAlmostEqual(2, row['pending_m3'])
        self.assertAlmostEqual(2, row['accrued_m3'])

    def test_failure_after_pickup_is_unconfirmed_not_restored_or_delivered(self):
        manager = Simulation(volume_config()).task_generation_manager
        failed = manager.update_until(3600)[0].task
        failed.payload_instance_picked_up = True
        manager.task_state_changed(failed, 'failed')
        row = self.balance(manager)
        self.assertAlmostEqual(0.4, row['unconfirmed_m3'])
        self.assertAlmostEqual(0.4, row['pending_m3'])
        self.assertAlmostEqual(0.2, row['residual_m3'])
        self.assertEqual(0, row['completed_m3'])

    def test_completed_and_failed_return_notifications_do_not_duplicate_volume(self):
        manager = Simulation(volume_config()).task_generation_manager
        task = manager.update_until(3600)[0].task
        manager.task_state_changed(task, 'completed')
        manager.task_state_changed(task, 'completed')
        returned = copy.deepcopy(task); returned.id = 'RETURN'; returned.is_return_task = True
        manager.task_state_changed(returned, 'failed')
        row = self.balance(manager)
        self.assertAlmostEqual(0.4, row['completed_m3'])
        self.assertAlmostEqual(0.4, row['pending_m3'])
        self.assertEqual(0, row['unconfirmed_m3'])

    def test_full_simulation_success_reconciles_delivered_and_residual(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/waste-volume-balance.json'
        sim = Simulation(json.loads(path.read_text(encoding='utf-8')))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        row = self.balance(sim.task_generation_manager)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertAlmostEqual(0.8, row['completed_m3'])
        self.assertAlmostEqual(0.2, row['residual_m3'])
        self.assertEqual(0, row['pending_m3'])

    def test_full_simulation_failed_outbound_restores_all_accrued_volume(self):
        config = volume_config()
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim = Simulation(config)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(2, len(sim.failed_task_ids))
        self.assertAlmostEqual(1, sim.task_generation_manager.generators[0].runtime['department:D:General']['volume'])
        row = self.balance(sim.task_generation_manager)
        self.assertAlmostEqual(1, row['residual_m3'])
        self.assertEqual(0, row['pending_m3'])
        self.assertEqual(0, row['completed_m3'])

    def test_shared_contributors_reconcile_one_combined_accrual(self):
        config = volume_config()
        config['task_generation']['categories']['waste']['base_daily_volume_m3'] = 7.2
        config['waste_streams'][0].update(container_capacity_m3=1, full_threshold_fraction=0.5)
        config['departments'][0]['waste_streams'][0]['shared_container_group'] = 'BIN'
        other = copy.deepcopy(config['departments'][0]); other['id'] = 'E'
        config['departments'].append(other)
        config['task_generation']['categories']['waste']['department_groups'][0]['departments'].append('E')
        manager = Simulation(config).task_generation_manager
        self.assertEqual(1, len(manager.update_until(3600)))
        row = self.balance(manager)
        self.assertAlmostEqual(0.6, row['accrued_m3'])  # two contributors, each .3
        self.assertAlmostEqual(0.5, row['pending_m3'])
        self.assertAlmostEqual(0.1, row['residual_m3'])

    def test_scheduled_threshold_fill_is_accrued_once(self):
        config = volume_config()
        config['task_generation']['categories']['waste'].update(generation_mode='scheduled_threshold',
            scheduled_times=['00:01', '00:02'], volume_per_event_m3=0.3, base_daily_volume_m3=0)
        manager = Simulation(config).task_generation_manager
        records = manager.update_until(3600)
        self.assertEqual(1, len(records))
        row = self.balance(manager)
        self.assertAlmostEqual(0.6, row['accrued_m3'])
        self.assertAlmostEqual(0.4, row['pending_m3'])
        self.assertAlmostEqual(0.2, row['residual_m3'])

    def test_saved_results_metrics_reconcile_and_link_to_contributing_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.csv'
            sim = Simulation(volume_config(), verbose=True, verbose_csv_path=str(path))
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            sim.write_verbose_csv()
            sim.write_verbose_csv()  # repeated flush cannot duplicate the summary
            result = load_investigation(path)
            metrics = {m['key']: m for m in result['metrics']}
            self.assertEqual('Reconciled', metrics['waste_volume_balance']['value'])
            self.assertAlmostEqual(1, metrics['waste_accrued_m3']['value'])
            self.assertAlmostEqual(0.8, metrics['waste_completed_m3']['value'])
            self.assertAlmostEqual(0.2, metrics['waste_residual_m3']['value'])
            self.assertGreaterEqual(len(metrics['waste_volume_balance']['event_ids']), 5)

    def test_missing_volume_evidence_is_unknown(self):
        result = summarize_waste_volume([], complete=True, capabilities=[])
        self.assertFalse(result['known'])
        self.assertIsNone(result['totals']['accrued_m3'])

    def test_inconsistent_or_malformed_summary_is_not_presented_as_reconciled(self):
        manager = Simulation(volume_config()).task_generation_manager
        manager.update_until(3600)
        groups = manager.waste_volume_balance()
        groups[0]['pending_m3'] = 9
        coverage = dict(type='waste_volume_balance_coverage', id='COVERAGE', task_ids=[],
                        row={'details': json.dumps(dict(schema_version=1, scope='dynamic_accumulated_waste_only', group_count=1, allocation_count=2))})
        allocations = [dict(type='waste_volume_allocation', id=str(index), task_ids=[row['task_id']],
                            row={'details': json.dumps({'group': groups[0]['group'], **row})})
                       for index, row in enumerate(groups[0].pop('collections'))]
        event = dict(type='waste_volume_balance_summary', id='SUMMARY', task_ids=[],
                     row={'details': json.dumps(groups[0])})
        result = summarize_waste_volume([coverage, event, *allocations], complete=True, capabilities=['waste_volume_balance_v1'])
        self.assertTrue(result['known'])
        self.assertFalse(result['matches'])
        groups[0]['accrued_m3'] = 'not a number'
        event['row']['details'] = json.dumps(groups[0])
        result = summarize_waste_volume([coverage, event, *allocations], complete=True, capabilities=['waste_volume_balance_v1'])
        self.assertFalse(result['known'])
        self.assertIsNone(result['totals']['accrued_m3'])

    def test_coverage_count_detects_missing_allocation_records(self):
        event = dict(type='waste_volume_balance_coverage', id='COVERAGE', task_ids=[],
                     row={'details': json.dumps(dict(schema_version=1, scope='dynamic_accumulated_waste_only',
                                                     group_count=0, allocation_count=1))})
        result = summarize_waste_volume([event], complete=True, capabilities=['waste_volume_balance_v1'])
        self.assertFalse(result['known'])
        self.assertIsNone(result['matches'])


if __name__ == '__main__':
    unittest.main()
