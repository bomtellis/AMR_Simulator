"""New lift settings persist through the existing editor transactions."""
from copy import deepcopy
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import Qt
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QWidget
from building_settings import BuildingSettingsDialog
from visualiser.dialogs import AMREditorDialog, LiftEditorDialog, LiftListDialog
from models import JsonStore
from amr_project import Project
from tests import test_corridor_editing as editing
from tests.test_lift_integration import direct_config


class LiftIntegrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_amr_entry_exit_speed_save_reopen_and_legacy_absence(self):
        cfg = direct_config()
        dialog = AMREditorDialog(None, ['A', 'B3'], cfg['amrs'][0])
        dialog.lift_entry_speed.setValue(.2)
        dialog.lift_exit_speed.setValue(.35)
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_not_called()
        result = dialog.result
        self.assertEqual(.2, result['lift_entry_speed_m_per_sec'])
        reopened = AMREditorDialog(None, ['A', 'B3'], result)
        self.assertEqual(.35, reopened.lift_exit_speed.value())
        dialog.close()
        reopened.close()
        legacy = AMREditorDialog(None, ['A'], cfg['amrs'][0])
        legacy.accept()
        self.assertNotIn('lift_entry_speed_m_per_sec', legacy.result)
        legacy.close()

    def test_lift_mode_uses_graph_without_manual_distances(self):
        parent = QWidget()
        parent.store = JsonStore(direct_config(True))
        lift = parent.store.data['lifts'][0]
        dialog = LiftEditorDialog(parent, lift)
        self.assertEqual('speed_based', dialog.transfer_mode.currentData())
        self.assertFalse(dialog.board_edit.isEnabled())
        self.assertFalse(hasattr(dialog, 'entry_distance'))
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_not_called()
        listing = LiftListDialog(parent, parent.store, lambda: None)
        listing.save_result(dialog.result, old_id=lift['id'])
        self.assertEqual('speed_based', parent.store.data['lifts'][0]['transfer_timing_mode'])
        self.assertNotIn('entry_distance_m', parent.store.data['lifts'][0])
        dialog.close()
        listing.close()
        parent.close()

    def test_missing_amr_speeds_prevent_enabling_speed_based_lift(self):
        parent = QWidget()
        parent.store = JsonStore(direct_config())
        dialog = LiftEditorDialog(parent, parent.store.data['lifts'][0])
        dialog.transfer_mode.setCurrentIndex(dialog.transfer_mode.findData('speed_based'))
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.result)
        dialog.close()
        parent.close()


class LiftRoutingEditorTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_floor_policy_save_undo_redo_reopen(self):
        cfg = direct_config()
        cfg['building'].pop('lift_transfer_floor')
        cfg['building'].pop('destination_side_lift_floors')
        self.editor.store = JsonStore(cfg)
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)

        def save(dialog):
            dialog.transfer_floor.setCurrentIndex(dialog.transfer_floor.findData(2))
            for index in range(dialog.destination_floors.count()):
                item = dialog.destination_floors.item(index)
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) == 2 else Qt.Unchecked)
            dialog.accept()
            return QDialog.Accepted

        with patch.object(BuildingSettingsDialog, 'exec', new=save):
            self.editor.manage_building_settings()
        after = deepcopy(self.editor.store.data)
        self.assertEqual(2, after['building']['lift_transfer_floor'])
        self.assertEqual([2], after['building']['destination_side_lift_floors'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)
        target = Path(self.temp.name) / 'lift-routing.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after, Project.open(target).configuration())

    def test_background_csv_export_uses_frozen_run_not_editor_changes(self):
        from amr_project_runs import PreparedRun, execute
        from visualiser.project_checks import check_project
        from visualiser.project_report_panel import ProjectReportPanel
        import csv
        cfg = direct_config(True)
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B3', payload='Box')]
        project = Project()
        project.save(Path(self.temp.name) / 'model.amrproj', cfg)
        prepared = PreparedRun(project, Path(self.temp.name) / 'results')
        checks = check_project(prepared.config)
        checks.acknowledge_warnings()
        directory = prepared.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        self.editor.project = project
        self.editor.store = JsonStore(cfg)
        panel = ProjectReportPanel(self.editor)
        panel.set_run(directory)
        self.editor.store.data['amrs'][0]['lift_entry_speed_m_per_sec'] = 99
        target = Path(self.temp.name) / 'gui-lift.csv'
        with patch.object(QDialog, 'exec', return_value=QDialog.Accepted), patch.object(
                QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            panel.generate_third_party()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        panel.process.finished.connect(loop.quit)
        timer.start(15000)
        loop.exec()
        self.assertFalse(panel.running(), panel.log.toPlainText())
        self.assertEqual(target, panel.lift_csv, panel.log.toPlainText())
        with target.open(newline='') as stream:
            self.assertEqual('4,8', next(csv.DictReader(stream))['Transfer times'])
        self.assertEqual(99, self.editor.store.data['amrs'][0]['lift_entry_speed_m_per_sec'])
        panel.close()
        panel.deleteLater()


if __name__ == '__main__':
    unittest.main()
