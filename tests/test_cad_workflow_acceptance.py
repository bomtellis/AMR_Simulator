"""Production CAD interactions through edits and the portable project boundary."""
from copy import deepcopy
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from shiboken6 import isValid


class CadWorkflowAcceptanceTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        editing.CorridorEditingUiTests.tearDown(self)
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(self.editor))

    def test_draw_select_edit_undo_and_portable_save_reopen(self):
        editor = self.editor
        profiles = deepcopy(editor.store.data['route_profiles'])
        original_edges = deepcopy(editor.store.data['corridors']['edges'])
        editor.resize(1400, 900)
        editor.show()
        self.app.processEvents()
        editor.cad_toolbar.mode_actions['corridor_draw'].trigger()
        field = editor.cad_drawing_input.coordinate_edit
        for text in ('0,0', '@10,0', '@10<90'):
            field.setText(text)
            QTest.keyClick(field, Qt.Key_Return)
        endpoint = editor.corridor_draw_start
        QTest.keyClick(field, Qt.Key_Return)
        self.assertIsNone(editor.corridor_draw_start)
        edges = editor.store.data['corridors']['edges']
        self.assertEqual(original_edges, edges[:len(original_edges)])
        self.assertEqual(2, len(edges) - len(original_edges))
        for edge in edges[len(original_edges):]:
            a, b = (editor.store.all_points()[edge[key]] for key in ('from', 'to'))
            self.assertAlmostEqual(10, math.hypot(a['x']-b['x'], a['y']-b['y']))
        editor.cad_toolbar.mode_actions['select_move'].trigger()
        editor.fit_view()
        self.app.processEvents()
        editor.clear_topology_selection()
        pixel = editor.canvas.mapFromScene(editor.world_to_scene(10, 10))
        QTest.mouseClick(editor.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, pixel)
        self.assertEqual({endpoint}, editor.selected_point_names)
        self.assertTrue(editor.properties_panel.isHidden())
        editor.cad_toolbar.properties_action.trigger()
        self.assertFalse(editor.properties_panel.isHidden())
        panel = editor.properties_panel
        self.assertEqual(('points', (endpoint,)), panel.target)
        before = deepcopy(editor.store.data)
        count = len(editor.edit_history.entries)
        panel.fields['x'].setText('12')
        self.assertEqual(before, editor.store.data)
        self.assertTrue(panel.apply())
        self.assertEqual(count+1, len(editor.edit_history.entries))
        moved = editor.store.all_points()[endpoint]
        self.assertAlmostEqual(math.sqrt(104), math.hypot(moved['x']-10, moved['y']))
        editor.undo_action.trigger()
        self.assertEqual(before, editor.store.data)
        editor.redo_action.trigger()
        self.assertEqual(12, editor.store.all_points()[endpoint]['x'])
        self.assertEqual(profiles, editor.store.data['route_profiles'])
        expected = deepcopy(editor.store.data)
        path = Path(self.temp.name) / 'drawn-layout.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.assertTrue(editor.save_project())
        # Check findings are covered separately; no modal check review in this
        # drawing/storage workflow acceptance case.
        with patch.object(editing.JsonStore, 'validate', return_value=[]):
            self.assertTrue(editor.load_json_file(str(path), load_drawings=False))
        self.assertEqual(expected, editor.store.data)
        self.assertEqual(12, editor.store.all_points()[endpoint]['x'])
        self.assertFalse(editor.has_unsaved_changes())

    def test_view_commands_do_not_create_project_revisions_or_change_checks(self):
        editor = self.editor
        editor.validate_json()
        before = deepcopy(editor.store.data)
        count = len(editor.edit_history.entries)
        self.assertTrue(editor.checks_panel.current())
        for name in ('properties_action', 'project_action', 'more_action', 'focus_action'):
            action = getattr(editor.cad_toolbar, name)
            action.trigger()
            action.trigger()
        self.assertEqual(before, editor.store.data)
        self.assertEqual(count, len(editor.edit_history.entries))
        self.assertTrue(editor.checks_panel.current())
        self.assertFalse(editor.has_unsaved_changes())


if __name__ == '__main__':
    unittest.main()
