"""Toolbar and canvas acceptance for connecting existing graph points."""
from copy import deepcopy
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests import test_corridor_editing as editing


class CadEdgeToolTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    tearDown = editing.CorridorEditingUiTests.tearDown

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.editor.store.data['locations'] = []
        self.editor.store.data['departments'] = []
        self.editor.store.data['corridors'] = {'nodes': [], 'edges': [], 'auto_connect': False}
        for name, x in [('A', 0), ('B', 10), ('C', 20)]:
            self.editor.store.add_corridor_node(name, 0, x, 0)
        self.editor._reset_edit_history()
        self.editor.refresh_canvas()
        self.editor.resize(1400, 900)
        self.editor.show()
        self.app.processEvents()
        self.editor.canvas.resetTransform()
        self.editor.canvas.scale(20, 20)
        self.editor.canvas.centerOn(10, 0)
        action = self.editor.cad_toolbar.mode_actions['edge']
        QTest.mouseClick(self.editor.cad_toolbar.widgetForAction(action), Qt.LeftButton)
        self.app.processEvents()

    def click(self, x, y=0):
        position = self.editor.canvas.mapFromScene(self.editor.world_to_scene(x, y))
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, position)
        self.app.processEvents()

    def test_toolbar_draws_chained_edges_with_undo_and_redo(self):
        action = self.editor.cad_toolbar.mode_actions['edge']
        self.assertTrue(action.isChecked())
        self.assertFalse(action.icon().isNull())
        self.assertEqual('edge', self.editor._current_edit_mode())
        self.assertTrue(self.editor.ribbon_tabs.isHidden())
        before = deepcopy(self.editor.store.data)
        self.click(0)
        self.assertEqual('A', self.editor.selected_for_edge)
        self.assertEqual(before, self.editor.store.data)
        self.click(10)
        first = deepcopy(self.editor.store.data)
        self.click(20)
        after = deepcopy(self.editor.store.data)
        edges = after['corridors']['edges']
        self.assertEqual([('A', 'B'), ('B', 'C')], [(e['from'], e['to']) for e in edges])
        self.assertTrue(all(e['bidirectional'] for e in edges))
        self.assertEqual(3, len(after['corridors']['nodes']))
        self.assertEqual(3, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(first, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)

    def test_one_way_nonchained_and_duplicate_edges_preserve_direction(self):
        self.editor.bidirectional_check.setChecked(False)
        self.editor.chain_edges_check.setChecked(False)
        self.click(0)
        self.click(10)
        self.assertIsNone(self.editor.selected_for_edge)
        self.assertFalse(self.editor.store.data['corridors']['edges'][0]['bidirectional'])
        before = deepcopy(self.editor.store.data)
        history = len(self.editor.edit_history.entries)
        self.click(10)
        self.click(0)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, len(self.editor.edit_history.entries))

    def test_escape_clears_creation_and_deletion_drafts_without_removing_edges(self):
        self.click(0)
        self.click(10)
        before = deepcopy(self.editor.store.data)
        history = len(self.editor.edit_history.entries)
        self.editor.edge_delete_start = 'A'
        self.editor.canvas.setFocus()
        QTest.keyClick(self.editor.canvas, Qt.Key_Escape)
        self.assertIsNone(self.editor.selected_for_edge)
        self.assertIsNone(self.editor.edge_delete_start)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, len(self.editor.edit_history.entries))
        self.click(20)
        self.assertEqual('C', self.editor.selected_for_edge)
        self.assertEqual(before, self.editor.store.data)

    def test_empty_space_and_same_point_do_not_create_edges(self):
        before = deepcopy(self.editor.store.data)
        self.click(5, 5)
        self.assertIsNone(self.editor.selected_for_edge)
        self.click(0)
        self.click(0)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.assertIn('Choose a different point', self.editor.status_label.text())


if __name__ == '__main__':
    unittest.main()
