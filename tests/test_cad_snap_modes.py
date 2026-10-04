"""Independent snap targets and production drawing/undo integration."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing
from visualiser.corridor_editing import drawing_target


class SnapModeGeometryTests(unittest.TestCase):
    def setUp(self):
        self.points = {'A': dict(x=0, y=0, floor=0), 'B': dict(x=6, y=8, floor=0)}
        self.edges = [{'from': 'A', 'to': 'B'}]

    def target(self, x, y, mode, **kwargs):
        return drawing_target(self.points, self.edges, 0, x, y, snap=False,
                              snap_mode=mode, **kwargs)

    def test_endpoint_and_midpoint_modes_have_independent_targets(self):
        midpoint = self.target(3.2, 4.1, 'midpoints')
        self.assertEqual(('edge', .5, 3, 4, 'midpoint'),
                         tuple(midpoint[k] for k in ('kind','fraction','x','y','snap_label')))
        endpoint = self.target(.2, .1, 'endpoints')
        self.assertEqual(('point', 'A'), (endpoint['kind'], endpoint['name']))
        self.assertEqual('new', self.target(3.2, 4.1, 'endpoints')['kind'])
        self.assertEqual('new', self.target(.2, .1, 'midpoints')['kind'])
        self.assertEqual('new', self.target(3.2, 4.1, 'midpoints', object_snap=False)['kind'])
        self.assertEqual('new', self.target(3.5, 4.5, 'midpoints')['kind'])

    def test_exact_topology_and_floor_boundaries_remain_enforced(self):
        for mode in ('nearest', 'endpoints', 'midpoints'):
            self.assertEqual('point', self.target(0, 0, mode)['kind'])
            self.assertEqual('edge', self.target(1.5, 2, mode)['kind'])
        self.points['B']['floor'] = 1
        self.assertEqual('new', self.target(3, 4, 'midpoints')['kind'])
        with self.assertRaises(ValueError):
            self.target(3, 4, 'unknown')

    def test_midpoint_cannot_deflect_orthogonal_constraint(self):
        target = self.target(3.2, 4.1, 'midpoints', anchor=(0, 4.1), angle_step=90)
        self.assertAlmostEqual(4.1, target['y'])
        self.assertNotEqual('midpoint', target.get('snap_label'))


class SnapModeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_typed_midpoint_preview_matches_split_and_undo(self):
        self.editor._set_edit_mode('corridor_draw')
        self.editor.object_snap_mode.setCurrentIndex(self.editor.object_snap_mode.findData('midpoints'))
        before = deepcopy(self.editor.store.data)
        points = self.editor.store.all_points()
        edge = self.editor.store.data['corridors']['edges'][0]
        a, b = points[edge['from']], points[edge['to']]
        x, y = (a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2
        self.editor.cad_drawing_input.coordinate_edit.setText(f'{x+.1},{y+.1}')
        target = self.editor.corridor_draw_preview
        self.assertEqual((x, y, 'midpoint'), (target['x'], target['y'], target['snap_label']))
        self.assertIn('midpoint', self.editor.cad_drawing_input.feedback_label.text())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.submit_corridor_coordinate())
        node = self.editor.store.all_points()[self.editor.corridor_draw_start]
        self.assertEqual((x, y), (node['x'], node['y']))
        self.editor.finish_corridor_drawing()
        self.editor.undo_edit()
        self.assertEqual(before, self.editor.store.data)

    def test_mode_change_refreshes_preview_without_changing_project(self):
        self.editor._set_edit_mode('corridor_draw')
        before = deepcopy(self.editor.store.data)
        self.editor.cad_drawing_input.coordinate_edit.setText('1.6,2.1')
        self.editor.object_snap_mode.setCurrentIndex(self.editor.object_snap_mode.findData('endpoints'))
        self.assertEqual('new', self.editor.corridor_draw_preview['kind'])
        self.editor.object_snap_check.setChecked(False)
        self.assertFalse(self.editor.object_snap_mode.isEnabled())
        self.assertEqual(before, self.editor.store.data)

    def test_node_and_door_mouse_placement_use_midpoint_and_one_undo(self):
        self.editor.object_snap_mode.setCurrentIndex(self.editor.object_snap_mode.findData('midpoints'))
        before = deepcopy(self.editor.store.data)
        for mode in ('corridor_node', 'door'):
            with self.subTest(mode=mode):
                self.editor._set_edit_mode(mode)
                scene = self.editor.world_to_scene(1.6, 2.1)
                self.editor.on_left_click(self.event, scene.x(), scene.y())
                nodes = self.editor.store.data['corridors']['nodes']
                inserted = [n for n in nodes if (n['x'], n['y']) == (1.5, 2)]
                self.assertEqual(1, len(inserted))
                self.assertEqual(mode == 'door', inserted[0]['has_door'])
                self.assertEqual(2, len(self.editor.edit_history.entries))
                self.assertTrue(self.editor.undo_edit())
                self.assertEqual(before, self.editor.store.data)
