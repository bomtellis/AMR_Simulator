"""Dense drawing name filters change presentation without changing the project."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from tests import test_corridor_editing as editing


class ObjectLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        if hasattr(self.editor, 'project_runs_panel'):
            del self.editor.project_runs_panel
        editing.CorridorEditingUiTests.tearDown(self)

    def test_key_names_hide_plain_nodes_but_include_selected_corridor_endpoints(self):
        self.editor.store.data['corridors']['nodes'].append(dict(name='Plain', floor=0, x=20, y=20))
        self.editor.store.data['corridors']['nodes'].append(dict(name='Other floor', floor=1, x=20, y=20))
        before = deepcopy(self.editor.store.data)
        self.editor.workbench.object_label_actions[1].trigger()
        self.assertEqual({'A','B','Door'}, set(self.editor._point_name_labels))
        self.editor.selected_edge_keys = {('A', 'Plain')}
        self.editor.refresh_canvas()
        self.assertIn('Plain', self.editor._point_name_labels)
        self.editor.workbench.object_label_actions[2].trigger()
        self.assertEqual({'A','Plain'}, set(self.editor._point_name_labels))
        self.assertEqual(before, self.editor.store.data)

    def test_hidden_names_leave_graph_and_door_symbols_and_history_unchanged(self):
        self.editor.refresh_canvas()
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        names = set(self.editor._point_item_lookup)
        self.editor.workbench.object_label_actions[-1].trigger()
        self.assertEqual({}, self.editor._point_name_labels)
        self.assertEqual(names, set(self.editor._point_item_lookup))
        self.assertTrue(any(getattr(item, 'text', lambda: '')() == 'D' for item in self.editor.scene.items()))
        self.assertFalse(self.editor.object_label_mode.isEnabled())
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, self.editor.edit_history.entries)
        self.editor.show_labels_check.setChecked(True)
        self.assertTrue(self.editor.workbench.object_label_actions[0].isChecked())
        self.assertEqual(names, set(self.editor._point_name_labels))

    def test_view_menu_remains_usable_during_simulation_lock(self):
        self.editor.project_runs_panel = SimpleNamespace(running=lambda: True)
        self.editor.sync_project_editing_lock()
        self.editor.selected_point_name = 'B'
        before = deepcopy(self.editor.store.data)
        self.editor.workbench.object_label_actions[2].trigger()
        self.assertEqual({'B'}, set(self.editor._point_name_labels))
        self.assertEqual(before, self.editor.store.data)

    def test_route_selection_and_font_size_remain_available(self):
        self.editor.route_profile_selection_active = True
        self.editor.route_profile_selected_nodes = {'Door'}
        self.editor.workbench.object_label_actions[2].trigger()
        self.assertEqual({'Door'}, set(self.editor._point_name_labels))
        text = self.editor._point_name_labels['Door']
        self.assertEqual(self.editor.appearance.value.map_font_size, text.font().pixelSize())
        self.editor.route_profile_selection_active = False
