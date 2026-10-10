"""Production canvas acceptance for atomic door placement and conversion."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import AMRGraphEditor
from amr_recovery import RecoveryStore


class CadDoorToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = AMRGraphEditor()
        self.editor._drawings_enabled = False
        self.editor._recovery_store = RecoveryStore(Path(self.temp.name) / 'recovery')
        self.editor.store.data['building']['default_door_clear_width_m'] = 1.15
        self.editor.store.add_corridor_node('A', 0, 0, 0)
        self.editor.store.add_corridor_node('B', 0, 10, 0)
        self.editor.store.add_corridor_node('OtherFloor', 1, 5, 3)
        self.editor.store.data['corridors']['edges'] = [
            dict(zip(('from', 'to'), ('A', 'B')), bidirectional=False,
                 width_m=2.5, distance_m=20, custom={'proof': [7]}),
            dict(zip(('from', 'to'), ('B', 'A')), bidirectional=False,
                 width_m=3.5, distance_m=30)]
        self.editor.store.data['route_profiles'] = {
            'clean': {'allowed_nodes': ['A', 'B'], 'allowed_edges': [['A', 'B']]}}
        self.editor.store.data['scenario_testing'] = {'proof': [
            {'resource_type': 'corridor', 'resource_id': 'B -> A'}]}
        self.editor.refresh_canvas()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.editor.resize(1400, 900)
        self.editor.show()
        self.app.processEvents()
        self.editor.canvas.resetTransform()
        self.editor.canvas.scale(25, 25)
        self.editor.canvas.centerOn(5, -1)
        self.editor.snap_check.setChecked(False)
        self.editor._set_edit_mode('door')
        self.app.processEvents()

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def click(self, x, y):
        self.assertEqual('door', self.editor._current_edit_mode())
        position = self.editor.canvas.mapFromScene(self.editor.world_to_scene(x, y))
        with patch('app.QInputDialog.getDouble', side_effect=AssertionError('Unexpected width modal')):
            QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, Qt.NoModifier, position)
        self.app.processEvents()

    def nodes(self):
        return self.editor.store.data['corridors']['nodes']

    def baseline(self):
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        return copy.deepcopy(self.editor.store.data)

    def test_toolbar_door_action_selects_real_placement_mode(self):
        self.editor._set_edit_mode('select_move')
        action = self.editor.cad_toolbar.mode_actions['door']
        action.trigger()
        self.assertTrue(action.isChecked())
        self.click(5, 3)
        self.assertTrue(next(n for n in self.nodes() if n['floor'] == 0 and n['x'] == 5)['has_door'])

    def test_split_is_one_undo_and_preserves_directed_attributes_and_references(self):
        original = copy.deepcopy(self.editor.store.data)
        self.click(5, 0)
        node = next(n for n in self.nodes() if n['name'] not in {'A', 'B', 'OtherFloor'})
        name = node['name']
        self.assertEqual((5, 0, True, 1.15), (node['x'], node['y'], node['has_door'], node['door_clear_width_m']))
        edges = self.editor.store.data['corridors']['edges']
        self.assertEqual([('A', name), (name, 'B'), ('B', name), (name, 'A')],
                         [(e['from'], e['to']) for e in edges])
        self.assertEqual([10, 10, 15, 15], [e['distance_m'] for e in edges])
        self.assertEqual([2.5, 2.5, 3.5, 3.5], [e['width_m'] for e in edges])
        self.assertTrue(all(not e['bidirectional'] for e in edges))
        self.assertEqual({'proof': [7]}, edges[0]['custom'])
        self.assertEqual([['A', name], [name, 'B']], self.editor.store.data['route_profiles']['clean']['allowed_edges'])
        self.assertEqual(['A', 'B', name], self.editor.store.data['route_profiles']['clean']['allowed_nodes'])
        self.assertEqual([f'B -> {name}', f'{name} -> A'],
                         self.editor.store.data['scenario_testing']['proof'][0]['resource_ids'])
        result = copy.deepcopy(self.editor.store.data)
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.editor.undo_edit()
        self.assertEqual(original, self.editor.store.data)
        self.editor.redo_edit()
        self.assertEqual(result, self.editor.store.data)

    def test_existing_node_conversion_retains_name_width_precision_and_custom_data(self):
        self.nodes()[0].update(door_clear_width_m=1.23456789, custom={'asset': 'door-future'})
        original = self.baseline()
        self.click(0, 0)
        expected = copy.deepcopy(original)
        expected['corridors']['nodes'][0]['has_door'] = True
        self.assertEqual(expected, self.editor.store.data)
        self.assertEqual({'A'}, self.editor.selected_point_names)
        self.click(0, 0)
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.editor.undo_edit()
        self.assertEqual(original, self.editor.store.data)

    def test_free_placement_snaps_on_current_floor_without_fabricating_links(self):
        self.editor.snap_check.setChecked(True)
        original_edges = copy.deepcopy(self.editor.store.data['corridors']['edges'])
        self.click(5.1, 3.1)
        node = next(n for n in self.nodes() if n['name'] not in {'A', 'B', 'OtherFloor'})
        self.assertEqual((0, 5, 3, True), (node['floor'], node['x'], node['y'], node['has_door']))
        self.assertEqual(original_edges, self.editor.store.data['corridors']['edges'])
        self.assertFalse(next(n for n in self.nodes() if n['name'] == 'OtherFloor')['has_door'])

    def test_existing_non_corridor_points_are_not_converted_or_duplicated(self):
        self.editor.store.add_location('Room', 0, 3, 3)
        self.editor.store.data['lifts'] = [{'id': 'Lift-1', 'floor_locations': {'0': {'x': 5, 'y': 3}}}]
        self.editor.store.data['departments'] = [{'id': 'D', 'name': 'Department', 'floor': 0, 'x': 7, 'y': 3}]
        original = self.baseline()
        for x in (3, 5, 7):
            self.click(x, 3)
            self.assertEqual(original, self.editor.store.data)
            self.assertIn('Door was not placed', self.editor.status_label.text())
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_failed_split_does_not_leave_partial_door_or_rewritten_references(self):
        self.editor.store.data['corridors']['edges'][0]['distance_m'] = -1
        original = self.baseline()
        self.click(5, 0)
        self.assertEqual(original, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.assertIn('Door was not placed', self.editor.status_label.text())

    def test_invalid_existing_width_rejects_without_mutation(self):
        self.nodes()[0]['door_clear_width_m'] = -1
        original = self.baseline()
        self.click(0, 0)
        self.assertEqual(original, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_omitted_width_uses_configured_default_without_other_node_changes(self):
        self.nodes()[0].pop('door_clear_width_m')
        original = self.baseline()
        self.click(0, 0)
        expected = copy.deepcopy(original)
        expected['corridors']['nodes'][0].update(has_door=True, door_clear_width_m=1.15)
        self.assertEqual(expected, self.editor.store.data)


if __name__ == '__main__':
    unittest.main()
