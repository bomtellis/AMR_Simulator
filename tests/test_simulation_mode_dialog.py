"""Mode authoring preserves engineering data and commits one undoable edit."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import QCoreApplication, QEvent
from shiboken6 import isValid
from app import AMRGraphEditor
from dialogs import SimulationSettingsDialog
from amr_recovery import RecoveryStore
from tests.test_geometric_yielding import yielding_config


class SimulationModeDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._qt_widgets = []
        # Registered first, so disposal follows the ordinary close/temp cleanups.
        # close() only hides a QWidget. These headless tests have no event loop
        # to release native objects before later allocation triggers Python GC.
        self.addCleanup(self._dispose_qt_widgets)

    def _dispose_qt_widgets(self):
        for widget in self._qt_widgets:
            if isValid(widget):
                widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(any(isValid(widget) for widget in self._qt_widgets))
        self._qt_widgets.clear()

    def dialog(self, config):
        dialog = SimulationSettingsDialog(None, config.get('simulation'), full_config=config)
        self._qt_widgets.append(dialog)
        self.addCleanup(dialog.close)
        return dialog

    def select(self, dialog, mode):
        index = dialog.mode_combo.findData(mode)
        self.assertGreaterEqual(index, 0)
        dialog.mode_combo.setCurrentIndex(index)

    def test_simulation_only_legacy_caller_preserves_omission_precision_and_metadata(self):
        original = {'start_datetime': '2026-01-05T00:00:00.123456+02:00',
                    'generated_task_release_stagger_sec': .123456789,
                    'custom': {'source': 'imported'}}
        dialog = SimulationSettingsDialog(None, original)
        self._qt_widgets.append(dialog)
        self.addCleanup(dialog.close)
        self.assertEqual('simple', dialog.mode_combo.currentData())
        dialog.accept()
        self.assertEqual(original, dialog.result)
        self.assertNotIn('mode', dialog.result)
        self.assertNotIn('motion_model', dialog.result)

    def test_unchanged_historical_geometric_and_toggle_back_preserve_raw_input(self):
        original = yielding_config()
        dialog = self.dialog(original)
        self.assertEqual('geometric_compatibility', dialog.mode_combo.currentData())
        self.assertIn('Historical', dialog.mode_combo.currentText())
        self.select(dialog, 'detailed')
        self.select(dialog, 'simple')
        self.select(dialog, 'geometric_compatibility')
        self.assertIn('No mode changes', dialog.mode_preview_text.toPlainText())
        dialog.accept()
        self.assertEqual(original, dialog.project_result)
        self.assertEqual(original['simulation'], dialog.result)

    def test_incomplete_detailed_preview_is_reviewable_and_can_be_saved_without_invention(self):
        original = {'simulation': {'custom': 'retained'}, 'amrs': [{'id': 'R'}],
                    'geometry': {'notes': {'author': 'engineer'}, 'floors': []}}
        before = deepcopy(original)
        dialog = self.dialog(original)
        self.select(dialog, 'detailed')
        preview = dialog.mode_preview_text.toPlainText()
        self.assertIn('/simulation/mode', preview)
        self.assertIn('/geometry/traffic_model', preview)
        self.assertIn('Blocking readiness findings', preview)
        self.assertIn('save is allowed', dialog.mode_readiness_label.text())
        dialog.accept()
        self.assertEqual('detailed', dialog.result['mode'])
        self.assertEqual('geometric_v1', dialog.result['motion_model'])
        self.assertEqual('keep_right_v1', dialog.project_result['geometry']['traffic_model'])
        self.assertEqual(original['amrs'], dialog.project_result['amrs'])
        self.assertEqual([], dialog.project_result['geometry']['floors'])
        self.assertEqual(original['geometry']['notes'], dialog.project_result['geometry']['notes'])
        self.assertEqual(before, original)

    def test_simple_keeps_dormant_geometry_and_motion_settings(self):
        original = yielding_config()
        original['simulation'].update(mode='detailed', motion_model='geometric_v1')
        original['geometry']['traffic_model'] = 'keep_right_v1'
        dialog = self.dialog(original)
        self.select(dialog, 'simple')
        dialog.accept()
        self.assertEqual('simple', dialog.result['mode'])
        self.assertEqual('legacy', dialog.result['motion_model'])
        self.assertEqual(original['geometry'], dialog.project_result['geometry'])
        self.assertEqual(original['amrs'], dialog.project_result['amrs'])

    def test_toggle_back_simple_preserves_absent_representation(self):
        original = {'simulation': {'duration_hours': 2}, 'geometry': {'notes': 'dormant'}}
        dialog = self.dialog(original)
        self.select(dialog, 'detailed')
        self.select(dialog, 'simple')
        dialog.accept()
        self.assertEqual(original, dialog.project_result)

    def test_unknown_mode_or_model_remains_visible_and_requires_explicit_correction(self):
        for simulation in ({'mode': 'future'}, {'motion_model': 'unknown_model'}):
            with self.subTest(simulation=simulation):
                dialog = self.dialog({'simulation': simulation})
                self.assertEqual('invalid', dialog.mode_combo.currentData())
                self.assertIn(next(iter(simulation.values())), dialog.mode_combo.currentText())
                with patch.object(QMessageBox, 'warning') as warning:
                    dialog.accept()
                warning.assert_called_once()
                self.assertIsNone(dialog.result)
                self.select(dialog, 'simple')
                dialog.accept()
                self.assertEqual({'mode': 'simple', 'motion_model': 'legacy'}, dialog.result)

    def test_other_edited_run_settings_merge_with_mode_change(self):
        original = {'simulation': {'custom': {'version': 7}, 'max_assignments_per_tick': 50}}
        dialog = self.dialog(original)
        self.select(dialog, 'detailed')
        dialog.max_assignments_per_tick_spin.setValue(3)
        dialog.accept()
        self.assertEqual(3, dialog.result['max_assignments_per_tick'])
        self.assertEqual('detailed', dialog.result['mode'])
        self.assertEqual({'version': 7}, dialog.result['custom'])

    def editor(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        editor = AMRGraphEditor()
        self._qt_widgets.append(editor)
        editor._recovery_store = RecoveryStore(Path(temporary.name) / 'recovery')
        editor._drawings_enabled = False
        def close():
            with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                editor.close()
        self.addCleanup(close)
        return editor

    def test_cancelled_mode_selection_does_not_add_missing_simulation_or_history(self):
        editor = self.editor()
        editor.store.data.pop('simulation', None)
        editor._reset_edit_history()
        before = deepcopy(editor.store.data)
        def cancel(dialog):
            self.select(dialog, 'detailed')
            dialog.reject()
            return QDialog.Rejected
        with patch.object(SimulationSettingsDialog, 'exec', cancel):
            editor.manage_simulation_settings()
        self.assertEqual(before, editor.store.data)
        self.assertEqual(1, len(editor.edit_history.entries))

    def test_mode_and_geometry_save_undo_redo_as_one_edit(self):
        editor = self.editor()
        editor.store.data['geometry'] = {'notes': 'keep this data'}
        editor._reset_edit_history()
        before = deepcopy(editor.store.data)
        def save(dialog):
            self.select(dialog, 'detailed')
            dialog.max_assignments_per_tick_spin.setValue(3)
            dialog.accept()
            return QDialog.Accepted
        with patch.object(SimulationSettingsDialog, 'exec', save):
            editor.manage_simulation_settings()
        after = deepcopy(editor.store.data)
        self.assertEqual('detailed', after['simulation']['mode'])
        self.assertEqual('keep_right_v1', after['geometry']['traffic_model'])
        self.assertEqual('keep this data', after['geometry']['notes'])
        self.assertEqual(3, after['simulation']['max_assignments_per_tick'])
        self.assertEqual(2, len(editor.edit_history.entries))
        self.assertTrue(editor.undo_edit())
        self.assertEqual(before, editor.store.data)
        self.assertTrue(editor.redo_edit())
        self.assertEqual(after, editor.store.data)


if __name__ == '__main__':
    unittest.main()
