"""Lift configuration transactions, validation, duplication and result displays."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QWidget
from amr_project import Project
from building_settings import BuildingSettingsDialog
from models import JsonStore
from visualiser.dialogs import LiftEditorDialog, LiftListDialog
from tests import test_building_settings as building
from tests.test_bed_lifts import config, ALL_DAY


class BedLiftDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_lift_roundtrip_cancel_and_disabled_fm_controls(self):
        parent = QWidget()
        parent.store = JsonStore(config())
        self.addCleanup(parent.close)
        bed = parent.store.data['lifts'][1]
        dialog = LiftEditorDialog(parent, bed)
        self.addCleanup(dialog.close)
        self.assertEqual('bed_fallback', dialog.bed_lift_settings.mode.currentData())
        self.assertTrue(dialog.bed_lift_settings.all_day.isChecked())
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_not_called()
        listing = LiftListDialog(parent, parent.store, lambda: None)
        self.addCleanup(listing.close)
        listing.save_result(dialog.result, old_id='Bed')
        saved = parent.store.data['lifts'][1]
        self.assertEqual(ALL_DAY, saved['amr_access_windows'])
        reopened = LiftEditorDialog(parent, saved)
        self.addCleanup(reopened.close)
        reopened.bed_lift_settings.mode.setCurrentIndex(0)
        self.assertFalse(reopened.bed_lift_settings.all_day.isEnabled())
        self.assertFalse(reopened.bed_lift_settings.windows.isEnabled())
        reopened.reject()
        self.assertEqual('bed_fallback', saved['usage_mode'])

    def test_invalid_windows_cannot_save_and_keyboard_mode_selection_works(self):
        dialog = LiftEditorDialog(None, config()['lifts'][0])
        self.addCleanup(dialog.close)
        controls = dialog.bed_lift_settings
        controls.mode.setFocus()
        QTest.keyClick(controls.mode, Qt.Key_Down)
        self.assertEqual('bed_fallback', controls.mode.currentData())
        self.assertTrue(controls.windows.isEnabled())
        controls.add_window({'start': '23:00', 'end': '02:00'})
        controls.add_window({'start': '01:00', 'end': '03:00'})
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.result)
        controls.all_day.setChecked(True)
        dialog.accept()
        self.assertEqual(ALL_DAY, dialog.result['amr_access_windows'])

    def test_copy_retains_independent_windows(self):
        parent = QWidget()
        parent.store = JsonStore(config())
        self.addCleanup(parent.close)
        dialog = LiftEditorDialog(parent, parent.store.data['lifts'][1])
        self.addCleanup(dialog.close)
        dialog.id_edit.setText('Bed-copy')
        dialog.accept()
        listing = LiftListDialog(parent, parent.store, lambda: None)
        self.addCleanup(listing.close)
        listing.save_result(dialog.result)
        clone = next(l for l in parent.store.data['lifts'] if l['id'] == 'Bed-copy')
        self.assertEqual('bed_fallback', clone['usage_mode'])
        self.assertEqual(ALL_DAY, clone['amr_access_windows'])
        clone['amr_access_windows'][0]['end'] = '23:00'
        self.assertEqual(ALL_DAY, parent.store.data['lifts'][1]['amr_access_windows'])


class BedLiftTransactionTests(unittest.TestCase):
    setUpClass = classmethod(building.BuildingSettingsUiTests.setUpClass.__func__)
    setUp = building.BuildingSettingsUiTests.setUp
    tearDown = building.BuildingSettingsUiTests.tearDown

    def test_lift_canvas_edit_undo_redo_save_reopen(self):
        self.editor.store = JsonStore(config(speed=True))
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        dialog = LiftEditorDialog(self.editor, before['lifts'][0])
        dialog.bed_lift_settings.mode.setCurrentIndex(1)
        dialog.bed_lift_settings.all_day.setChecked(True)
        dialog.accept()
        self.assertIsNotNone(dialog.result)
        self.editor._save_lift_result(dialog.result, 'L')
        dialog.close()
        after = deepcopy(self.editor.store.data)
        self.assertEqual('bed_fallback', after['lifts'][0]['usage_mode'])
        self.assertEqual('speed_based', after['lifts'][0]['transfer_timing_mode'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)
        target = Path(self.temp.name) / 'bed.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after, Project.open(target).configuration())

    def test_building_limit_default_save_undo_redo(self):
        self.editor.store = JsonStore(config())
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        unchanged = BuildingSettingsDialog(None, before)
        self.addCleanup(unchanged.close)
        self.assertEqual(5, unchanged.bed_lift_wait.value())
        unchanged.accept()
        self.assertEqual(before, unchanged.result)

        def save(dialog):
            dialog.bed_lift_wait.setValue(2)
            dialog.accept()
            return QDialog.Accepted

        with patch.object(BuildingSettingsDialog, 'exec', new=save):
            self.editor.manage_building_settings()
        self.assertEqual(120, self.editor.store.data['building']['bed_lift_fallback_wait_sec'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        reopened = BuildingSettingsDialog(None, self.editor.store.data)
        self.addCleanup(reopened.close)
        self.assertEqual(2, reopened.bed_lift_wait.value())
