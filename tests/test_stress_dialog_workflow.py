"""Exercise study filenames, startup failures and complete dialog lifecycles."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_scenario_stress_ui as ui
from PySide6.QtCore import QEventLoop, QProcess, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from amr_project_runs import read_json, write_json
from amr_scenario_study import create_study, default_settings, study_lock


class StressDialogWorkflowTests(unittest.TestCase):
    setUp = ui.ScenarioStressUiTests.setUp
    close_windows = ui.ScenarioStressUiTests.close_windows
    load_study = ui.ScenarioStressUiTests.load_study

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_finished(self):
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not self.dialog.running() else None)
        timer.start()
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        timer.stop()
        self.assertFalse(self.dialog.running(), self.dialog.status.text() + self.dialog._output)

    def prepared(self, name='existing.stress.json'):
        self.dialog.budget.setValue(1)
        path = self.root / name
        state = create_study(self.editor.store.data, path, self.dialog.settings())
        self.dialog.path, self.dialog.study = path, state
        self.dialog.refresh()
        return path, state

    def test_confirmed_overwrite_runs_new_settings_and_retains_old_study(self):
        path, old = self.prepared("Owner's lift étude.stress.json")
        old_bytes = path.read_bytes()
        evidence = Path(old['root']) / 'preserved-evidence.txt'
        evidence.write_text('Previous evidence')
        write_json(path.with_suffix('.json.cancel'), {'cancel': True})
        self.dialog.seed.setValue(12)
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            self.dialog.new_button.click()
        self.assertTrue(self.dialog.running(), self.dialog.status.text())
        self.wait_finished()
        new = read_json(path)
        self.assertEqual('complete', new['status'], self.dialog.status.text())
        self.assertEqual(12, new['settings']['seed'])
        self.assertNotEqual(old['root'], new['root'])
        self.assertEqual(old_bytes, Path(new['previous_study']).read_bytes())
        self.assertEqual('Previous evidence', evidence.read_text())
        self.assertFalse(path.with_suffix('.json.cancel').exists())
        self.assertFalse(self.editor.project_editing_locked())

    def test_cancelled_file_picker_keeps_loaded_study(self):
        path, old = self.prepared()
        before = path.read_bytes()
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=('', '')):
            self.dialog.new_study()
        self.assertEqual(before, path.read_bytes())
        self.assertIs(old, self.dialog.study)
        self.assertFalse(self.dialog.running())

    def test_creation_failure_restores_idle_progress_and_retains_previous_study(self):
        path, old = self.prepared()
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(self.root / 'new.json'), '')):
            with patch('scenario_stress_panel.create_study', side_effect=OSError('Cannot write study')):
                self.dialog.new_study()
        self.assertEqual(path, self.dialog.path)
        self.assertIs(old, self.dialog.study)
        self.assertFalse(self.dialog.running())
        self.assertGreater(self.dialog.progress.maximum(), 0)
        self.assertIn('Cannot write study', self.dialog.status.text())
        self.assertFalse(self.editor.project_editing_locked())

    def test_malformed_open_does_not_replace_current_study(self):
        path, old = self.prepared()
        broken = self.root / 'broken.json'
        write_json(broken, dict(version=1, coverage={}, settings={}))
        with patch('scenario_stress_panel.QFileDialog.getOpenFileName', return_value=(str(broken), '')):
            self.dialog.open_study()
        self.assertEqual(path, self.dialog.path)
        self.assertIs(old, self.dialog.study)
        self.assertEqual(old['settings'], self.dialog.settings())

    def test_escape_cannot_hide_running_dialog(self):
        self.dialog.show()
        self.app.processEvents()
        self.dialog.process = object()
        try:
            QTest.keyClick(self.dialog, Qt.Key_Escape)
            self.assertTrue(self.dialog.isVisible())
        finally:
            self.dialog.process = None

    def test_external_cancel_is_not_displayed_as_complete(self):
        path, state = self.prepared()
        state['status'] = 'cancelled'
        write_json(path, state)
        self.dialog.process = QProcess(self.dialog)
        self.dialog.worker_finished(0)
        self.assertIn('stopped', self.dialog.status.text().lower())
        self.assertNotEqual(100, self.dialog.progress.value())
        self.assertEqual('cancelled', read_json(path)['status'])

    def test_complete_study_resume_opens_results_without_starting_worker(self):
        self.load_study()
        self.dialog.start()
        self.assertFalse(self.dialog.running())
        self.assertEqual(100, self.dialog.progress.value())
        self.assertGreater(self.dialog.trial_progress.maximum(), 0)
        self.assertEqual(2, self.dialog.tabs.currentIndex())

    def test_creation_process_events_cannot_start_another_study(self):
        self.dialog.budget.setValue(1)
        path = self.root / 'new.stress.json'
        calls = []
        def events():
            if not calls:
                calls.append(True)
                self.dialog.new_study()
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(path), '')) as picker:
            with patch('scenario_stress_panel.QApplication.processEvents', side_effect=events):
                with patch.object(self.dialog, 'start'):
                    self.dialog.new_study()
        self.assertEqual(1, picker.call_count)
        self.assertEqual(path.resolve(), self.dialog.path)

    def test_launch_failure_unlocks_editor_and_can_retry(self):
        self.prepared()
        with patch('scenario_stress_panel.sys._base_executable', str(self.root / 'missing-worker.exe')):
            self.dialog.start()
            self.wait_finished()
        self.assertEqual('failed', self.dialog.study['status'])
        self.assertFalse(self.editor.project_editing_locked())
        self.assertTrue(self.dialog.new_button.isEnabled())
        self.dialog.start()
        self.wait_finished()
        self.assertEqual('complete', self.dialog.study['status'], self.dialog.status.text())

    def test_large_saved_seed_and_ram_precision_round_trip(self):
        settings = default_settings(self.editor.store.data)
        settings.update(seed=2**40, ram_limit_gib=2.34567, reserve_ram_gib=1.23456)
        self.dialog.set_settings(settings)
        self.assertEqual(settings, self.dialog.settings())

    def test_invalid_effects_do_not_open_file_picker(self):
        self.dialog.availability.setText('100')
        self.dialog.speeds.setText('100')
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName') as picker:
            self.dialog.new_study()
        picker.assert_not_called()
        self.assertIn('outage or slowdown', self.dialog.status.text())

    def test_restore_settings_allows_resume_after_setup_edit(self):
        path, state = self.prepared()
        self.dialog.seed.setValue(37)
        self.dialog.start()
        self.assertFalse(self.dialog.running())
        self.assertIn('Restore', self.dialog.status.text())
        self.dialog.restore_settings_button.click()
        self.assertEqual(state['settings'], self.dialog.settings())
        self.dialog.workers.setValue(1)
        self.dialog.start()
        self.wait_finished()
        self.assertEqual('complete', read_json(path)['status'])
        self.assertEqual(1, read_json(path)['settings']['workers'])

    def test_open_completed_study_restores_settings_and_results(self):
        state = self.load_study()
        path = self.dialog.path
        self.dialog.seed.setValue(37)
        with patch('scenario_stress_panel.QFileDialog.getOpenFileName', return_value=(str(path), '')):
            self.dialog.open_study()
        self.assertEqual(state['settings'], self.dialog.settings())
        self.assertEqual(2, self.dialog.tabs.currentIndex())
        self.assertIn('complete', self.dialog.status.text())
        self.assertGreater(self.dialog.results.rowCount(), 0)

    def test_running_file_cannot_be_overwritten_or_resumed(self):
        path, state = self.prepared()
        before = path.read_bytes()
        with study_lock(path):
            with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                self.dialog.new_study()
            self.assertFalse(self.dialog.running())
            self.assertIn('already running', self.dialog.status.text())
            self.dialog.start()
            self.assertFalse(self.dialog.running())
            self.assertIn('already running', self.dialog.status.text())
            self.assertEqual(before, path.read_bytes())
        self.assertFalse(self.editor.project_editing_locked())

    def test_worker_failure_cannot_change_another_coordinators_state(self):
        path, state = self.prepared()
        state['status'] = 'running'
        write_json(path, state)
        before = path.read_bytes()
        self.dialog.process = QProcess(self.dialog)
        with study_lock(path):
            self.dialog.worker_finished(1)
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(self.dialog.running())
        self.assertIn('already running', self.dialog.status.text())

    def test_failed_study_startup_error_is_not_hidden_by_old_error(self):
        path, state = self.prepared()
        state.update(status='failed', error='Previous worker error')
        write_json(path, state)
        self.dialog.seed.setValue(37)
        self.dialog.start()
        self.assertIn('Restore', self.dialog.status.text())

    def test_replaced_file_requires_reopening_before_resume(self):
        path, state = self.prepared()
        replacement = create_study(self.editor.store.data, path, state['settings'], overwrite=True)
        before = path.read_bytes()
        self.dialog.start()
        self.assertFalse(self.dialog.running())
        self.assertIn('replaced', self.dialog.status.text())
        self.assertEqual(before, path.read_bytes())
        self.assertIs(state, self.dialog.study)

    def test_no_busy_indicator_before_first_run(self):
        self.assertGreater(self.dialog.trial_progress.maximum(), 0)
        self.assertEqual(0, self.dialog.progress.value())

    def test_stopped_study_resumes_without_repeating_completed_trials(self):
        ui.ScenarioStressUiTests.test_stop_retains_evidence_and_resume_rejects_changed_setup(self)
        completed = deepcopy(self.dialog.study['results'])
        manifests = {identity: (Path(record['directory']) / 'run_manifest.json').read_bytes()
                     for identity, record in completed.items()}
        self.dialog.restore_settings_button.click()
        self.dialog.start()
        self.wait_finished()
        self.assertEqual('complete', self.dialog.study['status'], self.dialog.status.text())
        for identity, record in completed.items():
            self.assertEqual(record, self.dialog.study['results'][identity])
            self.assertEqual(manifests[identity], (Path(record['directory']) / 'run_manifest.json').read_bytes())

    def test_corrupt_result_types_are_rejected_before_adopting_file(self):
        state = self.load_study()
        path = self.dialog.path
        malformed = deepcopy(state)
        record = next(r for r in malformed['results'].values() if r['events'])
        record['events'][0]['availability_percent'] = '50'
        broken = self.root / 'broken-results.stress.json'
        write_json(broken, malformed)
        with patch('scenario_stress_panel.QFileDialog.getOpenFileName', return_value=(str(broken), '')):
            self.dialog.open_study()
        self.assertEqual(path, self.dialog.path)
        self.assertIs(state, self.dialog.study)
        self.assertIn('not a valid', self.dialog.status.text())

    def test_stop_write_failure_still_schedules_worker_termination(self):
        from unittest.mock import Mock
        self.prepared()
        worker = Mock()
        self.dialog.process = worker
        try:
            with patch('scenario_stress_panel.write_json', side_effect=PermissionError('Read-only stop file')):
                with patch('scenario_stress_panel.QTimer.singleShot') as timeout:
                    self.dialog.cancel()
            self.assertTrue(self.dialog._cancelled)
            timeout.assert_called_once()
            timeout.call_args.args[1]()
            worker.kill.assert_called_once()
        finally:
            self.dialog.process = None

    def test_missing_study_after_worker_exit_resets_both_progress_bars(self):
        path, state = self.prepared()
        path.unlink()
        self.dialog.trial_progress.setRange(0, 0)
        self.dialog.process = QProcess(self.dialog)
        self.dialog.worker_finished(1)
        self.assertFalse(self.dialog.running())
        self.assertGreater(self.dialog.trial_progress.maximum(), 0)
        self.assertFalse(self.editor.project_editing_locked())

    def test_worker_exit_cannot_alter_replaced_study(self):
        path, state = self.prepared()
        create_study(self.editor.store.data, path, state['settings'], overwrite=True)
        before = path.read_bytes()
        self.dialog.process = QProcess(self.dialog)
        self.dialog.worker_finished(1)
        self.assertEqual(before, path.read_bytes())
        self.assertIn('replaced', self.dialog.status.text())

    def test_review_actions_lock_immediately_when_resume_starts(self):
        self.load_study()
        self.assertTrue(self.dialog.playback_button.isEnabled())
        self.dialog._preparing = True
        try:
            self.dialog.refresh()
            for button in (self.dialog.investigate_button, self.dialog.playback_button,
                           self.dialog.save_scenario_button):
                self.assertFalse(button.isEnabled(), button.text())
            with patch.object(self.editor, 'refresh_canvas') as refresh:
                self.dialog.corridors.setCurrentCell(0, 0)
            refresh.assert_not_called()
        finally:
            self.dialog._preparing = False
        self.dialog.refresh()
        self.assertTrue(self.dialog.playback_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
