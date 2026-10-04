"""Independent event arithmetic, old-log adapters and real simulator evidence."""
import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from amr_results_investigation import load_investigation
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_generation_reference import grouped_config
from visualiser.results_investigation_panel import ResultsInvestigationPanel


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def log(self, rows, name='legacy.csv'):
        path = self.root / name
        keys = sorted(set().union(*(row.keys() for row in rows))) if rows else ['event_type', 'sim_time_sec', 'task_id']
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def event(self, kind, seconds=0, task='T', **values):
        return {'event_type': kind, 'sim_time_sec': seconds, 'task_id': task, **values}

    def run_reference(self, config=None):
        config = config or reference_config()
        if not config.get('tasks') and not config.get('task_generation', {}).get('enabled'):
            config['tasks'] = [{'id': 'T', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box'}]
        path = self.root / 'simulation_steps.csv'
        sim = Simulation(config, verbose=True, verbose_csv_path=str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        return sim, path

    def metric(self, report, name):
        return next(m for m in report['metrics'] if m['key'] == name)

    def test_real_delivery_has_nine_second_timeline_and_bound_inputs(self):
        sim, path = self.run_reference()
        report = load_investigation(path)
        task = next(t for t in report['tasks'] if t['task_id'] == 'T')
        self.assertEqual('completed', task['outcome'])
        self.assertEqual(9, task['release_to_completion_seconds'])
        self.assertEqual(0, task['assignment_delay_seconds'])
        self.assertTrue(report['complete_evidence'])
        self.assertEqual('/tasks/0', task['source_rule_path'])
        self.assertTrue(all(r['matches'] for r in report['reconciliation']))
        self.assertEqual(1, self.metric(report, 'payload_moves')['value'])
        self.assertEqual(1, self.metric(report, 'journeys')['value'])
        self.assertEqual(0, self.metric(report, 'failed')['value'])
        self.assertEqual(sim.run_id, report['run_id'])

    def test_energy_blocked_task_has_explicit_pending_snapshot_and_reconciliation(self):
        config = reference_config()
        config['amrs'][0]['battery_capacity_kwh'] = .000001
        sim, path = self.run_reference(config)
        report = load_investigation(path)
        task = next(t for t in report['tasks'] if t['task_id'] == 'T')
        self.assertEqual('pending at stop', task['outcome'])
        self.assertEqual(1, self.metric(report, 'pending_at_stop')['value'])
        self.assertEqual(0, self.metric(report, 'unknown_outcome')['value'])
        self.assertEqual(0, self.metric(report, 'failed')['value'])
        check = next(r for r in report['reconciliation'] if r['outcome'] == 'pending at stop')
        self.assertTrue(check['matches'])
        snapshot = next(e for e in report['events'] if e['type'] == 'task_pending_at_stop')
        self.assertIn('Last recorded candidate reason:', snapshot['explanation'])
        self.assertIn('Run status: finished', snapshot['row']['details'])
        self.assertIn(snapshot['id'], task['reason_event_ids'])
        self.assertIsNone(task['completion_seconds'])
        before = snapshot['id']
        with contextlib.redirect_stdout(io.StringIO()):
            sim.write_verbose_csv()
        repeated = [e for e in load_investigation(path)['events'] if e['type'] == 'task_pending_at_stop']
        self.assertEqual([before], [e['id'] for e in repeated])

    def test_pending_snapshot_mismatch_is_reported(self):
        config = reference_config()
        config['amrs'][0]['battery_capacity_kwh'] = .000001
        _, path = self.run_reference(config)
        sidecar = Path(str(path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['summary']['pending_task_ids'] = []
        sidecar.write_text(json.dumps(data))
        check = next(r for r in load_investigation(path)['reconciliation'] if r['outcome'] == 'pending at stop')
        self.assertFalse(check['matches'])
        self.assertEqual(['T'], check['missing_from_summary'])

    def test_cancelled_run_records_pending_without_claiming_full_coverage(self):
        config = reference_config()
        config['amrs'][0]['battery_capacity_kwh'] = .000001
        config['tasks'] = [dict(id='T',pickup='A',dropoff='B',payload='Box')]
        path = self.root / 'cancelled.csv'
        sim = Simulation(config, verbose=True, verbose_csv_path=str(path))
        sim.request_stop()
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        report = load_investigation(path)
        self.assertFalse(report['complete_evidence'])
        self.assertEqual('pending at stop', report['tasks'][0]['outcome'])
        self.assertIn('Run status: cancelled', report['tasks'][0]['stop_snapshot'])
        self.assertEqual(1,self.metric(report, 'pending_at_stop')['observed_count'])

    def test_no_pending_reason_is_explicit_and_removed_tasks_are_excluded(self):
        from amr_pending_evidence import record_pending_at_stop
        from amr_sim_models import Task
        config = reference_config()
        config['tasks'] = []
        sim = Simulation(config, verbose=True)
        keep, removed = Task('Waiting','A','B','Box'), Task('Removed','A','B','Box')
        sim._queue_pending_task(keep)
        sim._queue_pending_task(removed)
        sim._remove_pending_task(removed)
        record_pending_at_stop(sim)
        self.assertEqual(['Waiting'],sim._evidence_pending_task_ids)
        row = next(r for r in sim.verbose_rows if r['event_type'] == 'task_pending_at_stop')
        self.assertEqual('No candidate-specific reason was recorded.',row['pending_reason'])

    def test_legacy_release_does_not_invent_pending_outcome(self):
        report = load_investigation(self.log([self.event('task_released')]))
        self.assertEqual('outcome not recorded', report['tasks'][0]['outcome'])
        self.assertIsNone(self.metric(report, 'pending_at_stop')['value'])

    def test_continued_task_can_complete_after_an_earlier_pending_snapshot(self):
        report = load_investigation(self.log([self.event('task_pending_at_stop', 1),
                                             self.event('task_complete', 9)]))
        self.assertEqual('completed', report['tasks'][0]['outcome'])
        report = load_investigation(self.log([self.event('task_complete', 1),
                                             self.event('task_pending_at_stop', 9)]))
        self.assertEqual('conflicting outcomes', report['tasks'][0]['outcome'])

    def test_legacy_source_fingerprint_remains_readable_with_scope_warning(self):
        _, path = self.run_reference()
        sidecar = Path(str(path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['software'].pop('scope_version')
        sidecar.write_text(json.dumps(data))
        report = load_investigation(path)
        self.assertEqual('completed', report['tasks'][0]['outcome'])
        self.assertTrue(any('fingerprint scope' in finding for finding in report['findings']))

    def test_stable_native_identifiers_survive_playback_export(self):
        sim, path = self.run_reference()
        original = load_investigation(path)
        playback_path = self.root / 'playback.csv'
        sim.write_visualiser_csv(str(playback_path))
        full = load_investigation(path)
        playback = load_investigation(playback_path)
        self.assertTrue({e['id'] for e in original['events']} <= {e['id'] for e in full['events']})
        self.assertTrue({e['id'] for e in playback['events']} <= {e['id'] for e in full['events']})
        self.assertFalse(playback['complete_evidence'])
        self.assertTrue(any('filtered' in finding for finding in playback['findings']))
        ids = [e['id'] for e in full['events']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_frozen_inputs_survive_later_config_edits(self):
        sim, path = self.run_reference()
        sim.config['locations'][0]['x'] = 900
        sim.write_verbose_csv()
        report = load_investigation(path)
        self.assertEqual(0, report['frozen_inputs']['locations'][0]['x'])

    def test_generated_rule_provenance_is_saved(self):
        config = grouped_config()
        config['task_generation']['update_interval_sec'] = 60
        _sim, path = self.run_reference(config)
        report = load_investigation(path)
        generated = next(e for e in report['events'] if e['type'] == 'task_generated')
        self.assertEqual('stores:D:group:G', generated['row']['source_rule_id'])
        self.assertIn('/department_groups/0/payload', generated['row']['source_rule_path'])

    def test_separate_runs_have_distinct_native_ids(self):
        a, _path = self.run_reference()
        b, _path = self.run_reference()
        self.assertNotEqual(a.run_id, b.run_id)

    def test_shared_native_journey_is_kept_for_each_member(self):
        from amr_sim_models import Task
        sim = Simulation(reference_config(), verbose=True)
        tasks = [Task(t, 'A', 'B', 'Box') for t in ('T1', 'T2')]
        sim._register_evidence_journey(tasks)
        for task in tasks:
            sim.log_step(0, event_type='multi_stop_task_assigned', task_id=task.id, amr_id='R')
        path = self.log(sim.verbose_rows)
        report = load_investigation(path)
        self.assertEqual(2, self.metric(report, 'tasks')['value'])
        self.assertEqual(1, self.metric(report, 'journeys')['value'])
        self.assertEqual(['T1', 'T2'], report['journeys'][0]['task_ids'])

    def test_live_file_change_is_rejected(self):
        from unittest.mock import patch
        path = self.log([self.event('task_released')])
        with patch('amr_results_investigation.file_hash', side_effect=['before', 'after']):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                load_investigation(path)

    def test_summary_only_export_does_not_claim_zero_tasks(self):
        path = self.root / 'summary-only.csv'
        sim = Simulation(reference_config(), verbose=False, verbose_csv_path=str(path))
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
            sim.write_verbose_csv()
        result = load_investigation(path)
        self.assertFalse(result['complete_evidence'])
        self.assertIsNone(self.metric(result, 'tasks')['value'])

    def test_width_failure_has_recorded_reason(self):
        config = reference_config()
        config['payloads'][0]['width_m'] = .9
        _sim, path = self.run_reference(config)
        report = load_investigation(path)
        self.assertEqual(1, self.metric(report, 'failed')['value'])
        self.assertTrue(any('width' in e['explanation'] for e in report['events'] if e['type'] == 'task_failed'))

    def test_log_tampering_invalidates_bound_context(self):
        _sim, path = self.run_reference()
        with path.open('a') as stream:
            stream.write('\n')
        report = load_investigation(path)
        self.assertFalse(report['complete_evidence'])
        self.assertIsNone(report['frozen_inputs'])
        self.assertTrue(any('checksum' in f for f in report['findings']))

    def test_input_tampering_invalidates_bound_context(self):
        _sim, path = self.run_reference()
        sidecar = Path(str(path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['frozen_inputs']['locations'][0]['x'] = 999
        sidecar.write_text(json.dumps(data))
        report = load_investigation(path)
        self.assertFalse(report['complete_evidence'])
        self.assertIsNone(report['frozen_inputs'])

    def test_run_folder_can_move_with_its_evidence(self):
        _sim, path = self.run_reference()
        destination = self.root / 'moved'
        destination.mkdir()
        shutil.move(str(path), destination / path.name)
        sidecar = Path(str(path) + '.run.json')
        shutil.move(str(sidecar), destination / sidecar.name)
        self.assertTrue(load_investigation(destination)['complete_evidence'])

    def test_legacy_delay_arithmetic_and_unknown_reasons(self):
        path = self.log([self.event('task_released', 10), self.event('task_assigned', 25, amr_id='R'), self.event('task_complete', 55)])
        report = load_investigation(path)
        task = report['tasks'][0]
        self.assertEqual(15, task['assignment_delay_seconds'])
        self.assertEqual(45, task['release_to_completion_seconds'])
        self.assertEqual('No delay reason recorded.', task['delay_explanation'])
        self.assertEqual(2, len(task['assignment_delay_evidence']))
        self.assertIsNone(self.metric(report, 'failed')['value'])

    def test_missing_assignment_is_not_zero_delay(self):
        report = load_investigation(self.log([self.event('task_released'), self.event('task_complete', 9)]))
        self.assertIsNone(report['tasks'][0]['assignment_delay_seconds'])
        self.assertIn('assignment', report['tasks'][0]['missing_evidence'])

    def test_empty_legacy_log_has_unknown_not_zero_activity(self):
        report = load_investigation(self.log([]))
        self.assertTrue(all(m['value'] is None for m in report['metrics']))

    def test_planned_segment_does_not_prove_completion(self):
        report = load_investigation(self.log([self.event('segment_corridor', duration_sec=5, status='completed')]))
        self.assertEqual('outcome not recorded', report['tasks'][0]['outcome'])
        self.assertEqual('planned segment', report['events'][0]['evidence_kind'])

    def test_conflicting_terminal_outcomes_are_flagged(self):
        report = load_investigation(self.log([self.event('task_complete', 9), self.event('task_failed', 10)]))
        self.assertEqual('conflicting outcomes', report['tasks'][0]['outcome'])
        self.assertEqual(0, self.metric(report, 'completed')['observed_count'])

    def test_shared_journey_and_lift_do_not_multiply_by_task_count(self):
        rows = [self.event('multi_stop_task_assigned', task=t, amr_id='R', details='batch=T1,T2') for t in ('T1', 'T2')]
        rows.append(self.event('multi_stop_segment_lift_transfer', 5, task='T1,T2', lift_id='L', duration_sec=10))
        report = load_investigation(self.log(rows))
        self.assertEqual(2, self.metric(report, 'tasks')['value'])
        self.assertEqual(1, self.metric(report, 'journeys')['value'])
        self.assertEqual(1, self.metric(report, 'lift_segments')['value'])
        self.assertEqual(1, len(self.metric(report, 'lift_segments')['event_ids']))

    def test_payload_exit_entry_pair_is_one_transfer(self):
        rows = [self.event('location_payload_enter', task='', payload_instance_id='P', to_location='A'),
                self.event('location_payload_exit', 2, payload_instance_id='P', from_location='A'),
                self.event('location_payload_enter', 8, payload_instance_id='P', to_location='B')]
        report = load_investigation(self.log(rows))
        self.assertEqual(1, self.metric(report, 'payload_moves')['value'])
        self.assertEqual(('A', 'B'), (report['payload_movements'][0]['origin'], report['payload_movements'][0]['destination']))
        self.assertEqual(2, len(self.metric(report, 'payload_moves')['event_ids']))

    def test_repeated_payload_exits_are_linked_as_conflicting_evidence(self):
        rows = [self.event('location_payload_exit', t, payload_instance_id='P', from_location='A') for t in (2, 3)]
        rows.append(self.event('location_payload_enter', 8, payload_instance_id='P', to_location='B'))
        report = load_investigation(self.log(rows))
        self.assertEqual(1, self.metric(report, 'payload_tracking_conflicts')['value'])
        self.assertEqual(2, len(self.metric(report, 'payload_tracking_conflicts')['event_ids']))
        self.assertEqual(0, self.metric(report, 'payload_unpaired_exits')['observed_count'])
        self.assertIn('partial', self.metric(report, 'payload_moves')['coverage'])

    def test_duplicate_native_event_is_counted_once(self):
        event = self.event('task_complete', 9, event_id='run:1')
        report = load_investigation(self.log([event, event]))
        self.assertEqual(1, len(report['events']))
        self.assertTrue(any('Duplicate' in f for f in report['findings']))

    def test_conflicting_native_event_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting records'):
            load_investigation(self.log([self.event('task_complete', 9, event_id='run:1'), self.event('task_failed', 9, event_id='run:1')]))

    def test_legacy_ids_are_stable_for_same_file(self):
        path = self.log([self.event('task_released')])
        self.assertEqual(load_investigation(path)['events'], load_investigation(path)['events'])

    def test_waits_retain_reasons_without_summing_overlaps(self):
        report = load_investigation(self.log([self.event('task_released'), self.event('segment_wait', 2, wait_time_sec=8, pending_reason='Lift occupied'),
                                              self.event('segment_wait', 3, wait_time_sec=5, pending_reason='Door reservation')]))
        task = report['tasks'][0]
        self.assertEqual(2, len(task['reason_event_ids']))
        self.assertTrue(any('overlap' in s for s in report['limitations']))

    def test_summary_reconciliation_detects_different_task_set(self):
        _sim, path = self.run_reference()
        sidecar = Path(str(path) + '.run.json')
        data = json.loads(sidecar.read_text())
        data['summary']['completed_task_ids'] = ['Different']
        sidecar.write_text(json.dumps(data))
        report = load_investigation(path)
        result = next(r for r in report['reconciliation'] if r['outcome'] == 'completed')
        self.assertFalse(result['matches'])
        self.assertEqual(['Different'], result['missing_from_events'])


class InvestigationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_pending_filter_and_stop_explanation_are_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            path.write_text('event_type,sim_time_sec,task_id,details\n'
                            'task_pending_at_stop,1,T,Run status: finished. No candidate-specific reason was recorded.\n'
                            'task_complete,2,Done,Completed\n')
            panel = ResultsInvestigationPanel()
            try:
                panel.accept_result(load_investigation(path))
                panel.outcome.setCurrentText('pending at stop')
                self.assertEqual(1,panel.tasks.rowCount())
                panel.tasks.selectRow(0)
                self.assertIn('Pending-state snapshot:',panel.details.toPlainText())
                self.assertIn('No candidate-specific reason',panel.details.toPlainText())
                self.assertEqual('T',panel.task_rows[0]['task_id'])
            finally:
                panel.deleteLater()
                self.app.processEvents()

    def test_large_timeline_pages_preserve_every_event_and_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            path.write_text('event_type,sim_time_sec,task_id,details\n' + ''.join(
                f'segment_wait,{i},T,Wait {i}\n' for i in range(1201)))
            panel = ResultsInvestigationPanel()
            try:
                panel.accept_result(load_investigation(path))
                panel.tasks.selectRow(0)
                self.assertEqual(500, panel.events.rowCount())
                self.assertEqual(1201, len(panel.event_rows))
                self.assertEqual(3, panel.event_page.maximum())
                self.assertFalse(panel.previous_events.isEnabled())
                self.assertTrue(panel.next_events.isEnabled())
                panel.next_events.click()
                panel.events.selectRow(0)
                self.assertIn('Source row: 502', panel.details.toPlainText())
                self.assertIn('Wait 500', panel.details.toPlainText())
                panel.event_page.setValue(3)
                self.assertEqual('', panel.details.toPlainText())
                self.assertEqual(201, panel.events.rowCount())
                self.assertFalse(panel.next_events.isEnabled())
                self.assertIn('1,001', panel.event_range.text())
                panel.events.selectRow(200)
                self.assertIn('Source row: 1202', panel.details.toPlainText())
                self.assertEqual(1201, len(panel.result['events']))
                panel.search.setText('No matching task')
                self.assertEqual(0, panel.events.rowCount())
                self.assertEqual('No events', panel.event_range.text())
                self.assertFalse(panel.event_page.isEnabled())
                self.assertEqual('', panel.details.toPlainText())
                panel.search.clear()
                panel.tasks.selectRow(0)
                self.assertEqual(1, panel.event_page.value())
                self.assertEqual(500, panel.events.rowCount())
                panel.accept_result(None, 'Unreadable log')
                self.assertEqual([], panel.event_rows)
                self.assertEqual([], panel.task_rows)
                self.assertEqual({}, panel.events_by_id)
                self.assertFalse(panel.next_events.isEnabled())
            finally:
                panel.close()

    def test_task_and_metric_selection_show_contributing_events(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.csv'
            path.write_text('event_type,sim_time_sec,task_id\ntask_released,0,T\ntask_complete,9,T\n')
            panel = ResultsInvestigationPanel()
            try:
                panel.accept_result(load_investigation(path))
                panel.tasks.selectRow(0)
                self.assertEqual(2, panel.events.rowCount())
                index = next(i for i, m in enumerate(panel.result['metrics']) if m['key'] == 'completed')
                panel.metrics.selectRow(index)
                self.assertEqual(1, panel.events.rowCount())
                panel.events.selectRow(0)
                self.assertIn('Source row: 3', panel.details.toPlainText())
                self.assertIn('Legacy', panel.evidence.toPlainText())
            finally:
                panel.close()

    def test_editor_opens_investigation_without_using_current_project(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from app import AMRGraphEditor
        editor = AMRGraphEditor()
        try:
            editor.show_results_investigation()
            self.assertIsNone(editor.results_panel.result)
            self.assertIs(editor.workspace.stack.currentWidget(), editor.results_panel)
        finally:
            editor.close()


if __name__ == '__main__':
    unittest.main()
