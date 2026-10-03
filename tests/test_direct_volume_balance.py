"""Direct scheduled/sporadic volumes reconcile without becoming pool stock."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simulator import Simulation
from tests.test_sporadic_preview import sporadic_config
from tests.test_hybrid_generation import hybrid_config
from amr_results_investigation import load_investigation
from amr_direct_volume_evidence import summarize_direct_volume


def direct_config():
    config = sporadic_config()
    config['simulation']['end_datetime'] = '2026-01-05T01:00:00'
    config['task_generation']['categories']['stores']['frequency_per_day'] = 48
    return config


class DirectVolumeBalanceTests(unittest.TestCase):
    def row(self, manager):
        row, = manager.direct_volume_balance()
        self.assertAlmostEqual(0, row['difference_m3'], delta=1e-10)
        return row

    def test_generated_requests_are_pending_not_completed_volume(self):
        manager = Simulation(direct_config()).task_generation_manager
        tasks = manager.update_until(3600)
        self.assertEqual(2, len(tasks))
        row = self.row(manager)
        self.assertAlmostEqual(0.4, row['requested_m3'])
        self.assertAlmostEqual(0.4, row['pending_m3'])
        self.assertEqual(0, row['completed_m3'])
        self.assertEqual([], manager.waste_volume_balance())

    def test_failure_phases_and_duplicate_return_notifications_preserve_volume(self):
        manager = Simulation(direct_config()).task_generation_manager
        first, second = [r.task for r in manager.update_until(3600)]
        manager.task_state_changed(first, 'failed')
        manager.task_state_changed(first, 'failed')
        second.payload_instance_picked_up = True
        manager.task_state_changed(second, 'failed')
        returned = copy.deepcopy(second); returned.is_return_task = True
        manager.task_state_changed(returned, 'completed')
        row = self.row(manager)
        self.assertAlmostEqual(0.2, row['failed_before_pickup_m3'])
        self.assertAlmostEqual(0.2, row['unconfirmed_m3'])
        self.assertEqual(0, row['pending_m3'])
        self.assertEqual([], manager.update_until(3601))  # failure is an outcome, not fresh demand

    def test_hybrid_direct_event_and_threshold_pool_have_distinct_allocations(self):
        manager = Simulation(hybrid_config()).task_generation_manager
        records = manager.update_until(3600)
        self.assertEqual(2, len(records))
        direct = self.row(manager)
        pool, = manager.waste_volume_balance()
        self.assertAlmostEqual(0.4, direct['requested_m3'])
        self.assertAlmostEqual(0.4, pool['accrued_m3'])
        self.assertTrue({r['task_id'] for r in direct['requests']}.isdisjoint(r['task_id'] for r in pool['collections']))

    def run_saved(self, config=None, fail_after_pickup=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.csv'
            sim = Simulation(config or direct_config(), verbose=True, verbose_csv_path=str(path))
            original = sim._handle_event
            def handle(event):
                original(event)
                if fail_after_pickup and event.event_type == 'payload_pickup':
                    sim._fail_task(event.payload['task'], 'Injected failure immediately after physical pickup', now=event.time)
            with patch.object(sim, '_handle_event', side_effect=handle), contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            sim.write_verbose_csv(); sim.write_verbose_csv()
            return sim, load_investigation(path)

    def test_saved_success_reconciles_volumes_and_links_to_task_outcomes(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/direct-event-volume.json'
        sim, result = self.run_saved(json.loads(path.read_text(encoding='utf-8')))
        row = self.row(sim.task_generation_manager)
        self.assertAlmostEqual(0.4, row['completed_m3'])
        direct = result['direct_event_volume']
        self.assertTrue(direct['known'], direct['issues'])
        self.assertTrue(direct['matches'], direct['issues'])
        self.assertAlmostEqual(0.4, direct['totals']['completed_m3'])
        metric = next(m for m in result['metrics'] if m['key'] == 'direct_event_volume_balance')
        self.assertEqual('Reconciled', metric['value'])
        types = {e['type'] for e in result['events'] if e['id'] in metric['event_ids']}
        self.assertTrue({'task_generated', 'task_complete', 'direct_event_volume_request'}.issubset(types))
        self.assertEqual(1, sum(e['type'] == 'direct_event_volume_coverage' for e in result['events']))

    def test_saved_blocked_route_keeps_failed_volume_separate_from_completed(self):
        config = direct_config()
        config['corridors']['nodes'][0]['door_clear_width_m'] = 0.5
        sim, result = self.run_saved(config)
        self.assertAlmostEqual(0.4, self.row(sim.task_generation_manager)['failed_before_pickup_m3'])
        direct = result['direct_event_volume']
        self.assertTrue(direct['matches'], direct['issues'])
        self.assertEqual(0, direct['totals']['completed_m3'])

    def test_saved_post_pickup_failure_requires_physical_pickup_evidence(self):
        sim, result = self.run_saved(fail_after_pickup=True)
        self.assertAlmostEqual(0.4, self.row(sim.task_generation_manager)['unconfirmed_m3'])
        self.assertEqual(0, len(sim.completed_task_records))
        direct = result['direct_event_volume']
        self.assertTrue(direct['matches'], direct['issues'])
        events = [e for e in result['events'] if e['type'] != 'location_payload_exit']
        check = summarize_direct_volume(events, complete=True, capabilities=['direct_event_volume_v1'])
        self.assertFalse(check['matches'])

    def test_configured_zero_volume_is_known_and_requests_remain_visible(self):
        config = direct_config()
        config['task_generation']['categories']['stores']['volume_per_event_m3'] = 0
        _, result = self.run_saved(config)
        self.assertTrue(result['direct_event_volume']['matches'])
        self.assertEqual(0, result['direct_event_volume']['totals']['requested_m3'])
        self.assertEqual(2, sum(e['type'] == 'direct_event_volume_request' for e in result['events']))

    def test_route_pair_multiplicity_is_counted_as_distinct_requested_volume(self):
        config = direct_config()
        config['locations'].append(dict(name='C', floor=0, x=0, y=10))
        category = config['task_generation']['categories']['stores']
        category.update(department_groups=[], dropoff_locations=['B', 'C'])
        manager = Simulation(config).task_generation_manager
        self.assertEqual(4, len(manager.update_until(3600)))
        self.assertAlmostEqual(0.8, self.row(manager)['requested_m3'])

    def test_scheduled_waste_is_direct_volume_but_scheduled_threshold_is_pool_fill(self):
        for mode in ['scheduled', 'scheduled_threshold']:
            with self.subTest(mode=mode):
                config = hybrid_config()
                config['task_generation']['categories']['waste'].update(generation_mode=mode,
                    base_daily_volume_m3=0, frequency_per_day=0, scheduled_times=['00:30'])
                sim, result = self.run_saved(config)
                if mode == 'scheduled':
                    row = self.row(sim.task_generation_manager)
                    self.assertEqual('scheduled', row['component'])
                    self.assertAlmostEqual(0.4, row['requested_m3'])
                else:
                    self.assertEqual([], sim.task_generation_manager.direct_volume_balance())
                    self.assertEqual(0, result['direct_event_volume']['totals']['requested_m3'])
                self.assertTrue(result['direct_event_volume']['matches'], result['direct_event_volume']['issues'])

    def test_missing_and_partial_older_evidence_is_unknown(self):
        for complete, capabilities in [(False, ['direct_event_volume_v1']), (True, [])]:
            result = summarize_direct_volume([], complete=complete, capabilities=capabilities)
            self.assertFalse(result['known'])
            self.assertIsNone(result['totals']['requested_m3'])

    def test_bad_totals_wrong_generated_volume_and_pool_overlap_conflict(self):
        _, result = self.run_saved()
        for mutation in ['summary', 'generated', 'pool_overlap']:
            with self.subTest(mutation=mutation):
                events = copy.deepcopy(result['events'])
                if mutation == 'summary':
                    event = next(e for e in events if e['type'] == 'direct_event_volume_summary')
                    row = json.loads(event['row']['details']); row['completed_m3'] = 9
                    event['row']['details'] = json.dumps(row)
                else:
                    event = next(e for e in events if e['type'] == 'task_generated')
                    if mutation == 'generated':
                        event['row']['waste_volume_m3'] = '9'
                    else:
                        duplicate = copy.deepcopy(event); duplicate.update(type='waste_volume_allocation', id='OVERLAP')
                        events.append(duplicate)
                check = summarize_direct_volume(events, complete=True, capabilities=['direct_event_volume_v1'])
                self.assertTrue(check['known'])
                self.assertFalse(check['matches'])

    def test_missing_duplicate_and_malformed_requests_cannot_reconcile(self):
        _, result = self.run_saved()
        for mutation in ['missing', 'duplicate', 'malformed']:
            with self.subTest(mutation=mutation):
                events = copy.deepcopy(result['events'])
                event = next(e for e in events if e['type'] == 'direct_event_volume_request')
                if mutation == 'missing':
                    events.remove(event)
                elif mutation == 'duplicate':
                    events.append(copy.deepcopy(event))
                else:
                    row = json.loads(event['row']['details']); row['volume_m3'] = True
                    event['row']['details'] = json.dumps(row)
                check = summarize_direct_volume(events, complete=True, capabilities=['direct_event_volume_v1'])
                self.assertFalse(check['known'])
                self.assertIsNone(check['matches'])

    def test_empty_manifest_cannot_hide_existing_direct_demand(self):
        _, result = self.run_saved()
        events = copy.deepcopy(result['events'])
        events = [e for e in events if e['type'] not in {'direct_event_volume_summary', 'direct_event_volume_request'}]
        coverage = next(e for e in events if e['type'] == 'direct_event_volume_coverage')
        row = json.loads(coverage['row']['details']); row.update(group_count=0, request_count=0)
        coverage['row']['details'] = json.dumps(row)
        check = summarize_direct_volume(events, complete=True, capabilities=['direct_event_volume_v1'])
        self.assertTrue(check['known'])
        self.assertFalse(check['matches'])


if __name__ == '__main__':
    unittest.main()
