"""Explicit intersection snapping connects every coincident corridor atomically."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from itertools import combinations
from tests import test_corridor_editing as editing
from tests.test_crossing_junction import crossing
from visualiser.models import JsonStore
from visualiser.corridor_editing import drawing_target, draw_step


class IntersectionSnapTests(unittest.TestCase):
    def test_preview_and_shared_split_preserve_independent_references(self):
        config = crossing()
        points = JsonStore(config).all_points()
        before = deepcopy(config)
        preview = drawing_target(points, config['corridors']['edges'], 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual(('junction', 4, 0), (preview['kind'], preview['x'], preview['y']))
        updated, target = draw_step(config, points, None, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual(before, config)
        self.assertEqual(1, len(updated['corridors']['nodes']))
        self.assertEqual([8, 12, 9, 21], [e['distance_m'] for e in updated['corridors']['edges']])
        self.assertEqual([False, False, True, True], [e['bidirectional'] for e in updated['corridors']['edges']])
        name = target['name']
        self.assertEqual([['A', name], [name, 'B']], updated['route_profiles']['clean']['allowed_edges'])
        self.assertEqual({'C', 'D', name}, set(updated['route_profiles']['dirty']['allowed_nodes']))

    def test_three_way_crossing_and_existing_door_use_one_identity(self):
        config = crossing()
        config['locations'] += [dict(name='E', floor=0, x=1, y=-3), dict(name='F', floor=0, x=7, y=3)]
        config['corridors']['edges'].append({'from':'E', 'to':'F', 'width_m':2})
        config['corridors']['nodes'] = [dict(name='Door', floor=0, x=4, y=0, has_door=True, door_clear_width_m=.7)]
        updated, target = draw_step(config, JsonStore(config).all_points(), None, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual('Door', target['name'])
        self.assertEqual(config['corridors']['nodes'], updated['corridors']['nodes'])
        self.assertEqual(6, len(updated['corridors']['edges']))
        self.assertTrue(all('Door' in (e['from'], e['to']) for e in updated['corridors']['edges']))
        again, target = draw_step(updated, JsonStore(updated).all_points(), None, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual(updated, again)
        self.assertEqual('point', target['kind'])

    def test_t_junction_reuses_branch_endpoint(self):
        config = crossing()
        config['locations'][2]['y'] = 0
        updated, target = draw_step(config, JsonStore(config).all_points(), None, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual('C', target['name'])
        self.assertEqual([], updated['corridors']['nodes'])
        self.assertEqual(config['corridors']['edges'][1], updated['corridors']['edges'][-1])

    def test_no_attraction_across_floors_outside_tolerance_or_when_disabled(self):
        config = crossing()
        edges = config['corridors']['edges']
        points = JsonStore(config).all_points()
        for x, y, enabled in [(4.4, .4, True), (4.1, .1, False)]:
            target = drawing_target(points, edges, 0, x, y, snap=False, object_snap=enabled, snap_mode='intersections')
            self.assertEqual('new', target['kind'])
        for name in ('C', 'D'):
            points[name]['floor'] = 1
        self.assertEqual('new', drawing_target(points, edges, 0, 4.1, .1, snap=False, snap_mode='intersections')['kind'])

    def test_ambiguous_existing_points_rejected_without_mutation(self):
        config = crossing()
        config['corridors']['nodes'] = [dict(name=n, floor=0, x=4, y=0) for n in ('X', 'Y')]
        before = deepcopy(config)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            draw_step(config, JsonStore(config).all_points(), None, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual(before, config)

    def test_distant_corridors_are_removed_before_pair_search(self):
        config = crossing()
        points = JsonStore(config).all_points()
        edges = deepcopy(config['corridors']['edges'])
        for i in range(10000):
            a, b = f'X{i}', f'Y{i}'
            points[a] = dict(floor=0, x=100+i, y=100)
            points[b] = dict(floor=0, x=100+i, y=110)
            edges.append({'from':a, 'to':b})
        counts = []
        def measured_pairs(items, size):
            items = list(items)
            counts.append(len(items))
            return combinations(items, size)
        with patch('visualiser.corridor_editing.combinations', side_effect=measured_pairs):
            target = drawing_target(points, edges, 0, 4.1, .1, snap_mode='intersections')
        self.assertEqual('junction', target['kind'])
        self.assertEqual([2], counts)

    def test_intersection_respects_constraints_and_connects_route_anchor(self):
        config = crossing()
        config['locations'].append(dict(name='Start', floor=0, x=0, y=2))
        points = JsonStore(config).all_points()
        target = drawing_target(points, config['corridors']['edges'], 0, 4.1, .1,
                                snap=False, snap_mode='intersections', anchor=(0, 2), angle_step=90)
        self.assertNotEqual('junction', target['kind'])
        self.assertEqual(2, target['y'])
        updated, target = draw_step(config, points, 'Start', 0, 4.1, .1, snap_mode='intersections')
        self.assertTrue(target['connected'])
        self.assertEqual(('Start', target['name']),
                         (updated['corridors']['edges'][-1]['from'], updated['corridors']['edges'][-1]['to']))


class IntersectionSnapUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_door_intersection_mouse_placement_and_undo(self):
        self.editor.store = JsonStore(crossing())
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        self.editor._set_edit_mode('door')
        self.editor.object_snap_mode.setCurrentIndex(self.editor.object_snap_mode.findData('intersections'))
        scene = self.editor.world_to_scene(4.1, .1)
        self.editor.on_left_click(self.event, scene.x(), scene.y())
        self.assertEqual(4, len(self.editor.store.data['corridors']['edges']))
        nodes = self.editor.store.data['corridors']['nodes']
        self.assertEqual(1, len(nodes))
        self.assertTrue(nodes[0]['has_door'])
        self.assertEqual((4, 0), (nodes[0]['x'], nodes[0]['y']))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)

    def test_typed_intersection_preview_places_junction_in_one_undo(self):
        self.editor.store = JsonStore(crossing())
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        self.editor._set_edit_mode('corridor_draw')
        self.editor.object_snap_mode.setCurrentIndex(self.editor.object_snap_mode.findData('intersections'))
        self.editor.cad_drawing_input.coordinate_edit.setText('4.1,.1')
        self.assertEqual('junction', self.editor.corridor_draw_preview['kind'])
        self.assertIn('connect junction', self.editor.cad_drawing_input.feedback_label.text())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.submit_corridor_coordinate())
        self.assertEqual(4, len(self.editor.store.data['corridors']['edges']))
        self.editor.finish_corridor_drawing()
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
