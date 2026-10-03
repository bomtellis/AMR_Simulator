"""User-facing project lifecycle, including cancellation and real portable saves."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch

from tests import test_corridor_editing as editing
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFileDialog, QMessageBox
from amr_project import Project
from models import JsonStore


class WorkbenchLifecycleTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_new_project_resets_document_selection_and_history(self):
        self.editor.floor_spin.setValue(4)
        self.editor._set_edit_mode('corridor_draw')
        self.editor.corridor_draw_start = 'A'
        self.editor.selected_for_edge = 'A'
        self.editor.selected_point_names = {'A'}
        self.editor.store.data['building']['floor_height_m'] = 7
        self.editor.capture_recovery()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard):
            self.editor.workbench.new_action.trigger()
        self.assertEqual(JsonStore().data, self.editor.store.data)
        self.assertIsNone(self.editor.project)
        self.assertIsNone(self.editor.current_json_path)
        self.assertIsNone(self.editor.selected_for_edge)
        self.assertIsNone(self.editor.corridor_draw_start)
        self.assertFalse(self.editor.selected_point_names)
        self.assertEqual(0, self.editor.floor_spin.value())
        self.assertEqual('layout', self.editor.workspace.stage)
        self.assertEqual('select_move', self.editor._current_edit_mode())
        self.assertFalse(self.editor.undo_action.isEnabled())
        self.assertFalse(self.editor.has_unsaved_changes())
        self.assertFalse(self.editor._recovery_store.snapshot_path.exists())
        self.assertEqual(QKeySequence.New, self.editor.workbench.new_action.shortcut())
        self.assertEqual(QKeySequence.SaveAs, self.editor.workbench.save_as_action.shortcut())

    def test_cancel_new_keeps_work_and_recovery(self):
        self.editor.store.data['building']['floor_height_m'] = 7
        self.editor.capture_recovery()
        before = deepcopy(self.editor.store.data)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Cancel):
            self.assertFalse(self.editor.new_project())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor._recovery_store.snapshot_path.exists())

    def test_save_then_new_preserves_original_portable_project(self):
        path = Path(self.temp.name) / 'before.amrproj'
        self.editor.store.data['building']['floor_height_m'] = 7
        before = deepcopy(self.editor.store.data)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Save), \
                patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')) as save:
            self.assertTrue(self.editor.new_project())
        self.assertIn('*.amrproj', save.call_args.args[-1])
        self.assertEqual(before, Project.open(path).configuration())
        self.assertIsNone(self.editor.project)
        self.assertFalse(self.editor.store.data['locations'])

    def test_cancel_save_prevents_new_and_failed_save_preserves_document(self):
        self.editor.store.data['building']['floor_height_m'] = 7
        before = deepcopy(self.editor.store.data)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Save), \
                patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(self.editor.new_project())
        path = Path(self.temp.name) / 'failed.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')), \
                patch.object(Project, 'save', side_effect=OSError('disk full')), \
                patch.object(QMessageBox, 'critical'):
            self.assertFalse(self.editor.save_json())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertIsNone(self.editor.project)
        self.assertFalse(path.exists())

    def test_new_is_blocked_while_simulation_or_report_is_running(self):
        before = deepcopy(self.editor.store.data)
        for name in ('project_runs_panel', 'report_panel'):
            with self.subTest(name=name), patch.object(self.editor, name, Mock(), create=True), \
                    patch.object(QMessageBox, 'information') as info:
                getattr(self.editor, name).running.return_value = True
                self.assertFalse(self.editor.new_project())
                info.assert_called_once()
                self.assertEqual(before, self.editor.store.data)

    def test_new_cannot_carry_graphical_editor_callbacks_into_another_document(self):
        before = deepcopy(self.editor.store.data)
        for name in ('route_profile_selection_active', 'department_location_placement_active'):
            with self.subTest(name=name), patch.object(self.editor, name, True), \
                    patch.object(QMessageBox, 'information') as info:
                self.assertFalse(self.editor.new_project())
                info.assert_called_once()
                self.assertEqual(before, self.editor.store.data)

    def test_fresh_save_reopens_portable_project_and_json_save_stays_json(self):
        path = Path(self.temp.name) / 'model.amrproj'
        before = deepcopy(self.editor.store.data)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.editor.save_json())
        self.assertEqual(before, Project.open(path).configuration())
        self.assertTrue(self.editor.new_project())
        self.assertTrue(self.editor.load_json_file(str(path), load_drawings=False))
        self.assertEqual(before, self.editor.store.data)
        exported = Path(self.temp.name) / 'legacy.json'
        exported.write_text(json.dumps(before), encoding='utf-8')
        self.assertTrue(self.editor.load_json_file(str(exported), load_drawings=False))
        self.editor.store.data['building']['floor_height_m'] = 9
        with patch.object(QFileDialog, 'getSaveFileName') as dialog:
            self.assertTrue(self.editor.save_json())
            dialog.assert_not_called()
        self.assertEqual(9, json.loads(exported.read_text())['building']['floor_height_m'])
        self.assertIsNone(self.editor.project)


class WorkbenchLaunchTests(unittest.TestCase):
    def test_help_runs_from_another_directory_without_launching_qt(self):
        root = Path(__file__).resolve().parents[1]
        for entry in ('amr_app.py', 'visualiser/amr_editor_main.py'):
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, str(root / entry), '--help'],
                                        cwd=root.parent, capture_output=True, text=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn('--without-drawings', result.stdout)
                self.assertIn('.amrproj', result.stdout)

    def test_native_startup_loads_project_and_exits_cleanly_from_another_directory(self):
        # Exercise the real Qt class: replacing its methods during construction
        # can interfere with PySide's native signal/slot registration.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'startup.amrproj'
            Project().save(path, editing.reference_config())
            script = textwrap.dedent(f'''
                import sys
                from PySide6.QtCore import QTimer, QStandardPaths
                from PySide6.QtWidgets import QApplication
                sys.path.insert(0, {str(root)!r})
                sys.path.insert(0, {str(root / 'visualiser')!r})
                import amr_app
                from app import AMRGraphEditor
                QStandardPaths.setTestModeEnabled(True)
                app = QApplication([])
                outcome = []
                def verify():
                    windows = [w for w in app.topLevelWidgets() if isinstance(w, AMRGraphEditor)]
                    if not windows or not getattr(windows[0], '_source_disk_hash', None):
                        return
                    timer.stop()
                    outcome.append(len(windows) == 1 and windows[0].current_json_path == {str(path)!r}
                                   and windows[0].project is not None and not windows[0]._drawings_enabled)
                    for window in windows:
                        window.close()
                    app.quit()
                timer = QTimer()
                timer.timeout.connect(verify)
                timer.start(100)
                QTimer.singleShot(10000, app.quit)
                code = amr_app.main([{str(path)!r}, '--without-drawings'])
                assert code == 0 and outcome == [True], (code, outcome)
            ''')
            result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script], cwd=folder,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_launch_passes_absolute_project_path_and_drawing_choice(self):
        import amr_app
        with patch('app.main', return_value=0) as launch:
            self.assertEqual(0, amr_app.main(['example.amrproj', '--without-drawings']))
        launch.assert_called_once_with(Path('example.amrproj').resolve(), load_drawings=False)
