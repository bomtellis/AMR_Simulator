from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QInputDialog, QMainWindow, QDialog
from app import AMRGraphEditor
from models import JsonStore
from edit_history import EditHistory, undoable
from amr_recovery import RecoveryStore


class EditHistoryTests(unittest.TestCase):
    def test_undo_preserves_generation_category_order(self):
        history = EditHistory({'categories': {'waste': {}, 'stores': {}, 'linen': {}}})
        history.record({'categories': {'linen': {}, 'stores': {}, 'waste': {}}}, 'Reorder')
        self.assertEqual(['waste', 'stores', 'linen'], list(history.undo()['categories']))
        self.assertEqual(['linen', 'stores', 'waste'], list(history.redo()['categories']))

    def test_undo_redo_and_new_branch(self):
        history = EditHistory({'x': 1})
        history.record({'x': 2}, 'Move')
        history.record({'x': 3}, 'Move again')
        self.assertEqual({'x': 2}, history.undo())
        self.assertEqual({'x': 1}, history.undo())
        self.assertIsNone(history.undo())
        self.assertEqual({'x': 2}, history.redo())
        history.record({'x': 4}, 'New direction')
        self.assertIsNone(history.redo())
        self.assertEqual({'x': 2}, history.undo())

    def test_noop_retains_redo_and_snapshots_do_not_alias(self):
        value = {'nested': [1]}
        history = EditHistory(value)
        value['nested'].append(2)
        history.record(value, 'Append')
        result = history.undo()
        self.assertFalse(history.record(result, 'No change'))
        result['nested'].append(999)
        self.assertEqual({'nested': [1, 2]}, history.redo())

    def test_count_and_memory_limits_keep_current_configuration(self):
        history = EditHistory({'x': 0}, max_steps=2)
        for x in range(1, 5):
            history.record({'x': x}, str(x))
        self.assertEqual(3, len(history.entries))
        self.assertTrue(history.trimmed)
        self.assertEqual({'x': 3}, history.undo())
        self.assertEqual({'x': 2}, history.undo())
        self.assertIsNone(history.undo())
        bounded = EditHistory({'x': 0}, max_bytes=1)
        bounded.record({'x': 1}, 'Change')
        self.assertEqual(1, len(bounded.entries))
        self.assertEqual({'x': 1}, bounded.unpack(bounded.entries[0]))

    def test_rebase_drawing_paths_preserves_cursor_and_changes(self):
        history = EditHistory({'value': 1, 'floor_dxf_files': [{'filepath': 'old.dxf'}]})
        history.record({'value': 2, 'floor_dxf_files': [{'filepath': 'old.dxf'}]}, 'Edit')
        history.remap_drawings({'old.dxf': 'cached.dxf'})
        before = history.undo()
        self.assertEqual(1, before['value'])
        self.assertEqual('cached.dxf', before['floor_dxf_files'][0]['filepath'])
        self.assertEqual(2, history.redo()['value'])


class EditHistoryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.editor = AMRGraphEditor()
        self.editor._recovery_store = RecoveryStore(self.root / 'recovery')
        self.editor._drawings_enabled = False
        self.editor.store.add_corridor_node('A', 0, 0, 0)
        self.editor.store.add_corridor_node('B', 0, 10, 0)
        self.editor.store.add_edge('A', 'B')
        self.editor.refresh_canvas()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.event = Mock()
        self.event.modifiers.return_value = Qt.NoModifier

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.temp.cleanup()

    def test_drag_is_one_step_and_restores_coordinates(self):
        self.editor._set_edit_mode('select_move')
        self.editor.on_left_click(self.event, 0, 0)
        for coordinate in (2, 4, 6):
            self.editor.on_drag(self.event, coordinate, -coordinate)
            self.editor._update_unsaved_indicator()
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.editor.on_left_release(self.event)
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertEqual(6, self.editor.store.all_points()['A']['x'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(0, self.editor.store.all_points()['A']['x'])
        self.assertEqual(0, self.editor.store.all_points()['A']['y'])
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(6, self.editor.store.all_points()['A']['x'])

    def test_delete_restores_node_and_incident_edges_together(self):
        before = deepcopy(self.editor.store.data)
        self.editor._set_edit_mode('delete')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.editor.on_left_click(self.event, 0, 0)
        self.assertNotIn('A', self.editor.store.all_points())
        self.assertEqual([], self.editor.store.data['corridors']['edges'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertNotIn('A', self.editor.store.all_points())

    def test_door_width_and_profile_edits_undo_independently(self):
        self.editor.selected_point_names = {'A'}
        with patch.object(QInputDialog, 'getDouble', return_value=(1.25, True)):
            self.editor.mark_selected_nodes_as_doors()
        self.editor._save_route_profiles({'Clean': {'allowed_nodes': ['A']}})
        self.assertTrue(self.editor.undo_edit())
        self.assertNotIn('Clean', self.editor.store.data['route_profiles'])
        node = next(n for n in self.editor.store.data['corridors']['nodes'] if n['name'] == 'A')
        self.assertEqual(1.25, node['door_clear_width_m'])
        self.assertTrue(self.editor.undo_edit())
        node = next(n for n in self.editor.store.data['corridors']['nodes'] if n['name'] == 'A')
        self.assertFalse(node.get('has_door', False))

    def test_cancelled_dialog_and_view_changes_do_not_create_history(self):
        self.editor.selected_point_names = {'A'}
        with patch.object(QInputDialog, 'getDouble', return_value=(1.25, False)):
            self.editor.mark_selected_nodes_as_doors()
        self.editor.floor_spin.setValue(1)
        self.editor.show_labels_check.setChecked(False)
        self.editor._update_unsaved_indicator()
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_modal_settings_restore_all_changed_values(self):
        original = deepcopy(self.editor.store.data['simulation'])
        changed = dict(original, end_datetime='2026-10-03 17:00:00', random_seed=123)
        dialog = Mock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.result = changed
        with patch('app.SimulationSettingsDialog', return_value=dialog):
            self.editor.manage_simulation_settings()
        self.assertEqual(changed, self.editor.store.data['simulation'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(original, self.editor.store.data['simulation'])

    def test_nested_callbacks_are_one_operation_and_failure_rolls_back_without_losing_redo(self):
        before = deepcopy(self.editor.store.data)
        @undoable('Combined configuration edit')
        def combined(editor):
            editor._save_route_profiles({'Dirty': {'allowed_nodes': ['B']}})
            editor._save_tasks([{'id': 'T-1'}])
        combined(self.editor)
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        @undoable('Interrupted change')
        def broken(editor):
            editor.store.data['example'] = 42
            raise ValueError('interrupted')
        with self.assertRaises(ValueError):
            broken(self.editor)
        self.assertNotIn('example', self.editor.store.data)
        self.assertEqual(before,self.editor.store.data)
        self.assertEqual(0,self.editor.edit_history.position)
        self.assertEqual('Combined configuration edit',self.editor.edit_history.redo_label)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual([{'id':'T-1'}],self.editor.store.data['tasks'])

    def test_save_keeps_history_and_undo_back_to_saved_values_is_clean(self):
        path = self.root / 'saved.json'
        self.editor.current_json_path = str(path)
        self.assertTrue(self.editor.save_json())
        self.editor._save_route_profiles({'Clean': {'allowed_nodes': ['A']}})
        self.assertTrue(self.editor.has_unsaved_changes())
        self.editor.undo_edit()
        self.assertFalse(self.editor.has_unsaved_changes())
        self.editor.redo_edit()
        self.assertTrue(self.editor.save_json())
        saved = path.read_bytes()
        self.editor.undo_edit()
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertEqual(saved, path.read_bytes())

    def test_packaging_drawings_keeps_undo_usable_without_original_file(self):
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'underlay')
        self.editor.set_floor_dxf_path(0, str(drawing))
        self.editor._save_route_profiles({'Clean': {'allowed_nodes': ['A']}})
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.root / 'project.amrproj'), '')):
            self.assertTrue(self.editor.save_project())
        drawing.unlink()
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual({'default': {'allowed_edges': [], 'allowed_lifts': [], 'allowed_nodes': []}}, self.editor.store.data['route_profiles'])
        self.assertTrue(Path(self.editor.store.data['floor_dxf_files'][0]['filepath']).exists())

    def test_open_resets_history_instead_of_crossing_project_boundary(self):
        self.editor._save_route_profiles({'Clean': {}})
        path = self.root / 'other.json'
        path.write_text(json.dumps(JsonStore().data))
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard), patch.object(JsonStore, 'validate', return_value=[]):
            self.assertTrue(self.editor.load_json_file(str(path), load_drawings=False))
        self.assertIsNone(self.editor.edit_history.undo_label)
        self.assertFalse(self.editor.undo_edit())

    def test_recovered_json_undo_keeps_exported_drawings_after_cache_removal(self):
        cache = tempfile.TemporaryDirectory()
        self.editor._project_cache = [cache]
        drawing = Path(cache.name) / 'temporary.dxf'
        drawing.write_bytes(b'recovered underlay')
        self.editor.set_floor_dxf_path(0, str(drawing))
        self.editor._reset_edit_history()
        self.editor._recovered_work = True
        self.editor._save_tasks([{'id': 'T1'}])
        path = self.root / 'recovered.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(self.editor.save_json())
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual([], self.editor.store.data['tasks'])
        self.assertTrue(self.editor.save_json())
        self.editor.close()
        config = json.loads(path.read_text())
        self.assertEqual(b'recovered underlay', Path(config['floor_dxf_files'][0]['filepath']).read_bytes())

    def test_live_modeless_editor_blocks_undo_until_closed(self):
        self.editor._save_tasks([{'id': 'T1'}])
        window = QMainWindow(self.editor)
        window.show()
        try:
            self.assertFalse(self.editor.undo_edit())
            self.assertEqual('T1', self.editor.store.data['tasks'][0]['id'])
        finally:
            window.close()
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual([], self.editor.store.data['tasks'])

    def test_pending_direct_change_is_captured_before_undo(self):
        self.editor.store.data['building']['floor_height_m'] = 99
        self.assertTrue(self.editor.undo_edit())
        self.assertNotEqual(99, self.editor.store.data['building']['floor_height_m'])
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(99, self.editor.store.data['building']['floor_height_m'])

    def test_keyboard_shortcuts_undo_and_redo_completed_edit(self):
        self.editor.show()
        self.app.processEvents()
        self.editor._save_tasks([{'id': 'T1'}])
        try:
            QTest.keyClick(self.editor, Qt.Key_Z, Qt.ControlModifier)
            self.assertEqual([], self.editor.store.data['tasks'])
            QTest.keyClick(self.editor, Qt.Key_Y, Qt.ControlModifier)
            self.assertEqual([{'id': 'T1'}], self.editor.store.data['tasks'])
        finally:
            # Offscreen Qt retains the last synthetic modifier flags until the
            # next key event; don't leak Ctrl into later table-selection tests.
            QTest.keyClick(self.editor, Qt.Key_Escape, Qt.NoModifier)
        self.assertEqual(Qt.NoModifier, QApplication.keyboardModifiers())

    def test_open_and_revision_restore_blocked_while_task_window_is_open(self):
        window = QMainWindow(self.editor)
        window.show()
        try:
            with patch.object(QMessageBox, 'information'):
                self.assertFalse(self.editor.load_json_file(str(self.root / 'other.json')))
                self.editor.show_project_revisions()
                self.editor.project_history_panel.restore()
            self.assertEqual(1, len(self.editor.edit_history.entries))
        finally:
            window.close()

    def test_undo_immediately_invalidates_checks_and_acknowledgements(self):
        self.editor._save_route_profiles({'Clean': {}})
        self.editor.validate_json()
        self.assertTrue(self.editor.checks_panel.current())
        self.editor.undo_edit()
        self.assertFalse(self.editor.checks_panel.current())
        self.assertIn('STALE', self.editor.checks_panel.summary.text())

    def test_recovery_captures_current_undone_state(self):
        self.editor._save_tasks([{'id': 'T1'}])
        self.editor._save_route_profiles({'Clean': {}})
        self.editor.undo_edit()
        self.assertTrue(self.editor.capture_recovery())
        body = self.editor._recovery_store.read(self.editor._recovery_store.snapshot_path)
        self.assertEqual([{'id': 'T1'}], body['config']['tasks'])
        self.assertEqual({'default': {'allowed_edges': [], 'allowed_lifts': [], 'allowed_nodes': []}}, body['config']['route_profiles'])


if __name__ == '__main__':
    unittest.main()
