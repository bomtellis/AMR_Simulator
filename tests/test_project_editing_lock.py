"""Running project lock applies to commands as well as visible controls."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest


class ProjectEditingLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        if hasattr(self.editor, 'project_runs_panel'):
            del self.editor.project_runs_panel
        editing.CorridorEditingUiTests.tearDown(self)

    def lock(self):
        self.editor.project_runs_panel = SimpleNamespace(running=lambda: True)
        self.editor.sync_project_editing_lock()

    def test_command_and_shortcut_paths_cannot_mutate_or_open_edit_dialogs(self):
        self.editor._set_edit_mode('corridor_draw')
        self.editor.draw_next_corridor(20, 20, exact=True)
        self.editor.finish_corridor_drawing()
        self.editor.selected_point_names = {'A'}
        self.editor.selected_point_name = 'A'
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        self.lock()
        changed = deepcopy(before)
        changed['locations'][0]['x'] = 123
        calls = [lambda: self.editor.draw_next_corridor(30, 30),
                 lambda: self.editor.delete_selected(),
                 lambda: self.editor.move_selected_by(1, 2),
                 lambda: self.editor.apply_layout_properties(changed),
                 lambda: self.editor.undo_edit(), lambda: self.editor.redo_edit(),
                 lambda: self.editor.save_project(save_as=True), lambda: self.editor.save_json(),
                 lambda: self.editor.manage_simulation_settings(),
                 lambda: self.editor.on_left_click(self.event, 0, 0),
                 lambda: self.editor.on_double_click(self.event, 0, 0),
                 lambda: self.editor._begin_point_drag('A', 0, 0)]
        with patch('app.SimulationSettingsDialog', side_effect=AssertionError('Locked editor opened')):
            for call in calls:
                self.assertFalse(call())
                self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, self.editor.edit_history.entries)
        self.assertIn('locked', self.editor.status_label.text())
        self.assertFalse(self.editor.undo_action.isEnabled())

    def test_stage_navigation_view_controls_and_unlock(self):
        self.lock()
        self.assertFalse(self.editor.run_lock_label.isHidden())
        self.assertFalse(self.editor.workspace.properties.isEnabled())
        self.assertFalse(self.editor.ribbon_tabs.isEnabled())
        self.assertTrue(self.editor.cad_toolbar.fit_action.isEnabled())
        self.assertTrue(self.editor.floor_spin.isEnabled())
        self.editor.workspace.configuration()
        self.editor.workspace.show_page('layout', self.editor.canvas)
        self.assertTrue(all(not action.isEnabled() for action in self.editor.cad_toolbar.mode_actions.values()))
        self.editor.project_runs_panel.running = lambda: False
        self.editor.sync_project_editing_lock()
        self.assertTrue(self.editor.run_lock_label.isHidden())
        self.assertTrue(self.editor.workspace.properties.isEnabled())
        self.assertTrue(all(action.isEnabled() for action in self.editor.cad_toolbar.mode_actions.values()))
        self.editor._set_edit_mode('corridor_draw')
        self.assertTrue(self.editor.draw_next_corridor(20, 20, exact=True))

    def test_locked_native_canvas_accepts_pan_but_not_edit_presses(self):
        self.editor._set_edit_mode('pdf_underlay_align')
        self.lock()
        before = deepcopy(self.editor.store.data)
        left = QSignalSpy(self.editor.canvas.leftClicked)
        middle = QSignalSpy(self.editor.canvas.middleClicked)
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton)
        QTest.mouseDClick(self.editor.canvas.viewport(), Qt.LeftButton)
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton)
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.MiddleButton)
        self.assertEqual(0, left.count())
        self.assertEqual(1, middle.count())
        self.assertEqual(before, self.editor.store.data)

    def test_property_draft_survives_blocked_apply(self):
        panel = self.editor.properties_panel
        panel.pending = True
        self.lock()
        self.assertFalse(panel.apply())
        self.assertTrue(panel.pending)
        self.assertIn('locked', panel.note.text())
        panel.pending = False
