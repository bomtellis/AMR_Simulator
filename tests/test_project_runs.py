import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from amr_project import Project
from amr_project_runs import PreparedRun, validate_run_inputs, execute, finish_run, inspect_run, MANIFEST, read_json
from amr_results_investigation import load_investigation
from visualiser.project_checks import check_project
from tests.test_engineering_reference import reference_config

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from app import AMRGraphEditor
from models import JsonStore
from project_runs_panel import ProjectRunsPanel, RunChecksDialog
from amr_recovery import RecoveryStore


class ProjectRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = reference_config()
        self.config['tasks'] = [{'id': 'T', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box'}]
        self.project = Project()
        self.project.save(self.root / 'model.amrproj', self.config)

    def prepare(self):
        draft = PreparedRun(self.project, self.root / 'results')
        report = check_project(draft.config, base_path=draft.directory)
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(draft.config), report.to_dict())
        directory = draft.commit(report)
        return directory

    def run_reference(self):
        directory = self.prepare()
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        return directory

    def test_run_is_bound_to_revision_with_independent_nine_second_result(self):
        directory = self.run_reference()
        manifest = inspect_run(directory, self.project)
        report = load_investigation(directory)
        task = next(t for t in report['tasks'] if t['task_id'] == 'T')
        self.assertEqual(9, task['release_to_completion_seconds'])
        self.assertEqual('complete', manifest['status'])
        self.assertEqual(1, manifest['completed_tasks'])
        self.assertEqual(0, manifest['failed_tasks'])
        self.assertEqual(self.project.revisions[-1]['id'], report['project_binding']['revision_id'])
        self.assertEqual(manifest['run_key'], report['project_binding']['run_key'])
        self.assertEqual(manifest['software']['sha256'], report['software']['sha256'])

    def test_new_project_revision_does_not_change_existing_run(self):
        directory = self.run_reference()
        frozen = (directory / 'config.json').read_bytes()
        old_revision = self.project.revisions[-1]['id']
        self.config['amrs'][0]['speed_m_per_sec'] = 1
        self.project.save(self.project.path, self.config)
        manifest = inspect_run(directory, self.project)
        self.assertEqual(old_revision, manifest['project_binding']['revision_id'])
        self.assertNotEqual(old_revision, self.project.revisions[-1]['id'])
        self.assertEqual(frozen, (directory / 'config.json').read_bytes())

    def test_preparation_and_cancel_preserve_project_and_remove_only_draft(self):
        original = self.project.path.read_bytes()
        draft = PreparedRun(self.project, self.root / 'results')
        unrelated = self.root / 'results' / 'keep.txt'
        unrelated.write_text('keep')
        draft.discard()
        self.assertFalse(draft.directory.exists())
        self.assertEqual('keep', unrelated.read_text())
        self.assertEqual(original, self.project.path.read_bytes())

    def test_moved_run_relinks_by_identity_and_revision_not_folder_name(self):
        directory = self.run_reference()
        moved = self.root / 'renamed run'
        shutil.move(str(directory), moved)
        self.assertEqual('complete', inspect_run(moved, self.project)['status'])
        self.assertEqual(1, len(load_investigation(moved)['tasks']))
        unrelated = Project()
        unrelated.save(self.root / 'unrelated.amrproj', self.config)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            inspect_run(moved, unrelated)

    def test_drawing_copies_survive_source_removal_and_folder_move(self):
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'reference drawing')
        self.config['floor_dxf_files'] = [{'floor': 0, 'filepath': str(drawing)}]
        self.project.save(self.project.path, self.config)
        directory = self.prepare()
        drawing.unlink()
        moved = self.root / 'moved'
        shutil.move(str(directory), moved)
        manifest, _ = validate_run_inputs(moved)
        self.assertEqual(self.project.project_id, manifest['project_binding']['project_id'])
        next((moved / 'drawings').iterdir()).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'drawing checksum'):
            validate_run_inputs(moved)

    def test_changed_frozen_inputs_rejected_before_execution(self):
        directory = self.prepare()
        (directory / 'config.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'inputs have changed'):
            execute(directory)
        self.assertFalse((directory / 'simulation_steps.csv').exists())

    def test_changed_checks_or_software_rejected(self):
        directory = self.prepare()
        with patch('amr_project_runs.software_snapshot', return_value={'sha256': 'different'}):
            with self.assertRaisesRegex(ValueError, 'software changed'):
                validate_run_inputs(directory, require_current_software=True)
        (directory / 'project_checks.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checks have changed'):
            validate_run_inputs(directory)

    def test_every_fingerprinted_source_change_invalidates_prepared_execution(self):
        from amr_run_evidence import file_hash, software_snapshot
        directory = self.prepare()
        root = Path(__file__).resolve().parents[1]
        for name in software_snapshot()['files']:
            with self.subTest(source=name):
                changed_path = root / name
                def changed_hash(path):
                    return 'changed-source' if Path(path) == changed_path else file_hash(path)
                with patch('amr_run_evidence.file_hash', side_effect=changed_hash):
                    with self.assertRaisesRegex(ValueError, 'software changed'):
                        validate_run_inputs(directory, require_current_software=True)

    def test_stale_review_and_unacknowledged_warnings_cannot_commit(self):
        draft = PreparedRun(self.project, self.root / 'results')
        try:
            report = check_project(draft.config)
            if any(f.severity == 'warning' for f in report.findings):
                with self.assertRaisesRegex(ValueError, 'review'):
                    draft.commit(report)
            report.acknowledge_warnings()
            changed = dict(draft.config, example=42)
            (draft.directory / 'config.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'review'):
                draft.commit(report)
        finally:
            draft.discard()

    def test_completed_run_cannot_be_executed_again(self):
        directory = self.run_reference()
        before = (directory / 'simulation_steps.csv').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already started'):
            execute(directory)
        self.assertEqual(before, (directory / 'simulation_steps.csv').read_bytes())
        self.assertEqual('complete', read_json(directory / MANIFEST)['status'])

    def test_reordered_configuration_during_review_is_rejected(self):
        draft = PreparedRun(self.project, self.root / 'results')
        try:
            report = check_project(draft.config)
            report.acknowledge_warnings()
            reordered = dict(reversed(list(draft.config.items())))
            self.assertEqual(draft.config, reordered)
            (draft.directory / 'config.json').write_text(json.dumps(reordered, indent=2))
            with self.assertRaisesRegex(ValueError, 'review'):
                draft.commit(report)
        finally:
            draft.discard()

    def test_missing_or_swapped_evidence_cannot_claim_complete(self):
        first = self.run_reference()
        second = self.prepare()
        self.assertEqual('failed', finish_run(second, 0)['status'])
        shutil.copyfile(first / 'simulation_steps.csv', second / 'simulation_steps.csv')
        shutil.copyfile(first / 'simulation_steps.csv.run.json', second / 'simulation_steps.csv.run.json')
        self.assertEqual('failed', finish_run(second, 0)['status'])

    def test_cancelled_run_is_not_reported_as_complete(self):
        directory = self.prepare()
        self.assertEqual('cancelled', finish_run(directory, -1, cancelled=True)['status'])

    def test_source_changes_during_execution_do_not_produce_complete_evidence(self):
        directory = self.prepare()
        software = read_json(directory / MANIFEST)['software']
        with patch('amr_project_runs.software_snapshot', side_effect=[software, {'sha256': 'changed'}]):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'during execution'):
                execute(directory)
        self.assertFalse((directory / 'simulation_steps.csv.run.json').exists())

    def test_project_archive_never_collects_run_outputs(self):
        import zipfile
        self.run_reference()
        self.project.save(self.project.path, self.config)
        with zipfile.ZipFile(self.project.path) as archive:
            self.assertTrue(all(name == 'manifest.json' or name.startswith(('configs/', 'assets/')) for name in archive.namelist()))


class ProjectRunsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.editor = AMRGraphEditor()
        self.editor._recovery_store = RecoveryStore(self.root / 'recovery')
        self.config = reference_config()
        self.config['tasks'] = [{'id': 'T', 'pickup': 'A', 'dropoff': 'B', 'payload': 'Box'}]
        self.editor.store = JsonStore(self.config)
        self.editor.project = Project()
        self.editor.project.save(self.root / 'model.amrproj', self.editor.store.data)
        self.editor.current_json_path = str(self.editor.project.path)
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.editor._drawings_enabled = False
        self.editor.show_project_runs()
        self.panel = self.editor.project_runs_panel

    def tearDown(self):
        if self.panel.process is not None:
            self.panel.stop_run()
            self.panel.process.waitForFinished(5000)
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.temp.cleanup()

    def dialog(self, accepted=True, change=False):
        class AutomatedChecks(RunChecksDialog):
            def exec(dialog):
                if not accepted:
                    return QDialog.Rejected
                dialog.panel.acknowledge.setChecked(True)
                if change:
                    path = Path(dialog.panel.base_path_provider()) / 'config.json'
                    path.write_text('{}')
                return QDialog.Accepted
        return AutomatedChecks

    def test_check_cancellation_creates_no_run(self):
        with patch('project_runs_panel.RunChecksDialog', self.dialog(False)), patch.object(self.panel, 'start_process') as start:
            self.panel.start_run()
        start.assert_not_called()
        self.assertEqual([], list(self.panel.results_root().iterdir()))

    def test_editor_runs_reference_in_child_process_and_lists_bound_result(self):
        with patch('project_runs_panel.RunChecksDialog', self.dialog()):
            self.panel.start_run()
        self.assertIsNotNone(self.panel.process)
        # Main document can be edited while the subprocess uses its frozen copy.
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 99
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not self.panel.running() else None)
        timer.start()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(15000)
        loop.exec()
        timer.stop()
        timeout.stop()
        self.assertFalse(self.panel.running(), self.panel.log.toPlainText())
        self.assertEqual(1, self.panel.runs.count())
        manifest = inspect_run(self.panel.run_dir, self.editor.project)
        self.assertEqual('complete', manifest['status'], manifest.get('error'))
        result = load_investigation(self.panel.run_dir)
        self.assertEqual(9, next(t for t in result['tasks'] if t['task_id'] == 'T')['release_to_completion_seconds'])

    def test_run_blocks_close_until_finished(self):
        self.panel.process = object()
        try:
            with patch.object(QMessageBox, 'information'):
                self.assertFalse(self.editor._confirm_unsaved_changes())
        finally:
            self.panel.process = None

    def test_changed_inputs_during_review_create_no_committed_run(self):
        with patch('project_runs_panel.RunChecksDialog', self.dialog(change=True)), patch.object(self.panel, 'start_process') as start, patch.object(QMessageBox, 'critical'):
            self.panel.start_run()
        start.assert_not_called()
        self.assertEqual([], list(self.panel.results_root().iterdir()))

    def test_moved_run_can_be_linked_in_workspace(self):
        draft = PreparedRun(self.editor.project, self.panel.results_root())
        report = check_project(draft.config)
        report.acknowledge_warnings()
        path = draft.commit(report)
        moved = self.root / 'moved-run'
        shutil.move(str(path), moved)
        self.panel.refresh_runs()
        # Persistent references remain visible when the original folder moves.
        self.assertEqual(1, self.panel.runs.count())
        self.assertIn('missing or unavailable', self.panel.runs.item(0).text())
        self.panel.link_run(moved)
        self.assertEqual(1, self.panel.runs.count())
        self.panel.runs.setCurrentRow(0)
        self.assertIn(self.editor.project.project_id, self.panel.details.toPlainText())

    def test_stop_terminates_child_and_records_cancellation(self):
        with patch('project_runs_panel.RunChecksDialog', self.dialog()):
            self.panel.start_run()
        process = self.panel.process
        self.panel.stop_run()
        process.waitForFinished(5000)
        self.assertFalse(self.panel.running())
        self.assertEqual('cancelled', read_json(self.panel.run_dir / MANIFEST)['status'])

    def test_start_failure_is_recorded(self):
        from PySide6.QtCore import QProcess
        with patch('project_runs_panel.RunChecksDialog', self.dialog()), patch.object(QProcess, 'start'):
            self.panel.start_run()
        self.panel.process_error(QProcess.FailedToStart)
        self.assertFalse(self.panel.running())
        self.assertEqual('failed', read_json(self.panel.run_dir / MANIFEST)['status'])


if __name__ == '__main__':
    unittest.main()
