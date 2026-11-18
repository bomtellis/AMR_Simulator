"""Run annotations follow identity; date ordering keeps all run actions aligned."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QPlainTextEdit
from amr_memory_runs import MemoryRuns
from amr_project import Project
from amr_project_runs import PreparedRun, inspect_run, link_run, MANIFEST
from amr_recovery import RecoveryStore
from amr_run_metadata import display_name, normalise_metadata, run_datetime
from app import AMRGraphEditor
from models import JsonStore
from tests.test_memory_runs import config
from visualiser.project_checks import check_project


class RunOrganisationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.project = Project()
        self.project.save(self.root / 'model.amrproj', config())
        self.pool = MemoryRuns()
        self.addCleanup(self.pool.clear)

    def saved_run(self, created):
        draft = PreparedRun(self.project, self.project.results_root())
        draft.manifest['created_at'] = created
        checks = check_project(draft.config)
        checks.acknowledge_warnings()
        return draft.commit(checks)

    def memory_run(self, created):
        run = self.pool.prepare(config(), self.root)
        checks = check_project(run.config, asset_refs=run.asset_refs)
        checks.acknowledge_warnings()
        run.accept_checks(checks)
        run.execute(self.pool.reserve(run))
        run.created = created
        self.pool.add(run)
        return run

    def panel(self):
        editor = AMRGraphEditor()
        editor._recovery_timer.stop()
        editor._recovery_store = RecoveryStore(self.root / 'recovery')
        editor._replace_document(JsonStore(config()), str(self.project.path), project=self.project, load_drawings=False)
        editor.show_project_runs()
        def close():
            with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                editor.close()
        self.addCleanup(close)
        return editor.project_runs_panel

    def test_annotations_survive_reopen_and_relink_without_rewriting_run(self):
        path = self.saved_run('2026-10-01T12:00:00+00:00')
        manifest = inspect_run(path, self.project)
        before = {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}
        revisions = deepcopy(self.project.revisions)
        self.project.set_run_metadata(manifest['run_key'], '  Baseline - 48 AMRs  ', 'First line\nSecond line')
        reopened = Project.open(self.project.path)
        ref = reopened.external_results['runs'][0]
        self.assertEqual('Baseline - 48 AMRs', ref['user_name'])
        self.assertEqual('First line\nSecond line', ref['note'])
        self.assertEqual(revisions, reopened.revisions)
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()})
        moved = self.root / 'moved'
        path.rename(moved)
        link_run(reopened, moved, expected_run_key=manifest['run_key'])
        again = Project.open(reopened.path).external_results['runs'][0]
        self.assertEqual(ref['user_name'], again['user_name'])
        self.assertEqual(ref['note'], again['note'])
        self.assertEqual(ref['created_at'], again['created_at'])

    def test_memory_annotations_carry_into_saved_project(self):
        run = self.memory_run('2026-11-18T09:00:00+00:00')
        run.set_metadata('Trial A', 'Three lifts\nUse for the comparison')
        frozen = run.config
        project, directory = run.publish(self.project)
        ref = Project.open(project.path).external_results['runs'][0]
        self.assertEqual(('Trial A', 'Three lifts\nUse for the comparison'), (ref['user_name'], ref['note']))
        self.assertEqual(run.key, inspect_run(directory, project)['run_key'])
        self.assertEqual(frozen, run.config)

    def test_saved_and_memory_rows_share_date_order_and_stable_selection(self):
        # Folder names reflect today's preparation time, deliberately unlike recorded dates.
        oldest = self.saved_run('2026-10-01T12:00:00+00:00')
        newest = self.saved_run('2026-11-18T10:00:00+00:00')
        middle = self.memory_run('2026-11-18T09:30:00+00:00')
        panel = self.panel()
        panel.memory.add(middle)
        panel.refresh_runs(select=middle)
        self.assertEqual([newest, None, oldest], panel.run_paths)
        self.assertIs(middle, panel.selected_memory_run())
        self.assertEqual('In memory', panel.runs.item(1, 2).text())
        panel.date_order.setCurrentIndex(1)
        self.assertEqual([oldest, None, newest], panel.run_paths)
        self.assertIs(middle, panel.selected_memory_run())
        panel.update_run_metadata('Middle trial', 'Capacity comparison')
        self.assertEqual('Middle trial', panel.runs.item(1).text())
        panel.runs.setCurrentRow(2)
        with patch.object(panel.editor, 'show_project_report') as show:
            panel.report()
        show.assert_called_once_with(newest)
        panel.date_order.setCurrentIndex(0)
        self.assertEqual(newest, panel.selected_path())
        # An annotation save must not mark current configuration edits as saved.
        panel.editor.store.data['amrs'][0]['speed_m_per_sec'] = 2.5
        panel.update_run_metadata('Newest trial', 'Keep current model edits')
        self.assertTrue(panel.editor.has_unsaved_changes())

    def test_missing_and_legacy_links_can_be_annotated(self):
        path = self.saved_run('2026-10-01T12:00:00+00:00')
        ref = self.project.external_results['runs'][0]
        for key in ('user_name', 'note', 'created_at'):
            ref.pop(key, None)
        self.project._write(self.project.path)
        path.rename(self.root / 'unlinked-location')
        panel = self.panel()
        self.assertIsNotNone(panel.run_rows[0]['datetime'])
        panel.update_run_metadata('Relocate this trial', 'Moved to another drive')
        self.assertIn('Relocate this trial', panel.runs.item(0).text())
        self.assertIn('Missing', panel.runs.item(0, 3).text())
        saved = Project.open(self.project.path).external_results['runs'][0]
        self.assertEqual('Moved to another drive', saved['note'])

    def test_editor_saves_multiline_notes_and_cancel_keeps_previous_values(self):
        self.saved_run('2026-11-18T09:30:00Z')
        panel = self.panel()
        def fill():
            dialog = QApplication.activeModalWidget()
            dialog.findChild(QLineEdit).setText('Morning baseline')
            dialog.findChild(QPlainTextEdit).setPlainText('48 AMRs\nAll lifts available')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        QTimer.singleShot(0, fill)
        panel.edit_run_metadata()
        ref = Project.open(self.project.path).external_results['runs'][0]
        self.assertEqual('Morning baseline', ref['user_name'])
        self.assertEqual('48 AMRs\nAll lifts available', ref['note'])
        before = self.project.path.read_bytes()
        def cancel():
            dialog = QApplication.activeModalWidget()
            dialog.findChild(QLineEdit).setText('Cancelled name')
            dialog.reject()
        QTimer.singleShot(0, cancel)
        panel.edit_run_metadata()
        self.assertEqual(before, self.project.path.read_bytes())

    def test_failed_annotation_save_keeps_last_valid_metadata(self):
        path = self.saved_run('2026-11-18T09:30:00Z')
        key = inspect_run(path, self.project)['run_key']
        self.project.set_run_metadata(key, 'Original name', 'Original note')
        previous = deepcopy(self.project.external_results)
        before = self.project.path.read_bytes()
        with patch.object(Project, '_write', side_effect=OSError('Cannot save project')):
            with self.assertRaises(OSError):
                self.project.set_run_metadata(key, 'Changed name', 'Changed note')
        self.assertEqual(previous, self.project.external_results)
        self.assertEqual(before, self.project.path.read_bytes())

    def test_discovered_run_is_linked_and_annotated_in_one_save(self):
        path = self.saved_run('2026-11-18T09:30:00Z')
        key = inspect_run(path, self.project)['run_key']
        self.project.external_results['runs'] = []
        self.project._write(self.project.path)
        panel = self.panel()
        panel.update_run_metadata('Discovered trial', 'Recovered from the results folder')
        reopened = Project.open(self.project.path)
        self.assertEqual(1, len(reopened.external_results['runs']))
        ref = reopened.external_results['runs'][0]
        self.assertEqual(key, ref['run_key'])
        self.assertEqual('Discovered trial', ref['user_name'])

    def test_validation_and_timezone_sort_dates(self):
        self.assertEqual(('Title', 'line 1\nline 2'), normalise_metadata(' Title ', 'line 1\nline 2'))
        for name, note in (('a\nb', ''), ('', '\x00'), ('x' * 201, ''), ('', 'x' * 10001)):
            with self.assertRaises(ValueError):
                normalise_metadata(name, note)
        self.assertEqual(run_datetime('2026-11-18T10:00:00+01:00'), run_datetime('2026-11-18T09:00:00Z'))
        self.assertIsNone(run_datetime('invalid', 'run_20269999_999999_bad'))
        self.assertEqual('48 clinical bays', display_name('', 'run_20261116_140114_7a3ff7978bcf-48-clinical-bays').replace('-', ' '))


if __name__ == '__main__':
    unittest.main()
