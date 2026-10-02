"""Continuous drawing must create routable geometry without altering permissions."""
from copy import deepcopy
import contextlib
import io
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.corridor_editing import drawing_target
from simulator import Simulation


def empty_store():
    cfg = reference_config()
    cfg['corridors']['nodes'] = []
    cfg['corridors']['edges'] = []
    return JsonStore(cfg)


class CorridorDrawingTests(unittest.TestCase):
    def test_three_clicks_create_two_connected_segments_with_calculated_time(self):
        store = empty_store()
        start = store.draw_corridor_step(None, 0, 0, 0)['name']
        middle = store.draw_corridor_step(start, 0, 3, 4)['name']
        finish = store.draw_corridor_step(middle, 0, 6, 8)['name']
        self.assertEqual(('A', 'C0-1', 'B'), (start, middle, finish))
        self.assertEqual(1, len(store.data['corridors']['nodes']))
        self.assertEqual(2, len(store.data['corridors']['edges']))
        store.data['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(store.data)
            sim.run()
        self.assertFalse(sim.failed_tasks)
        self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])

    def test_direction_checkbox_controls_new_graph_connections(self):
        for both in (False, True):
            store = empty_store()
            store.draw_corridor_step('A', 0, 6, 8, bidirectional=both)
            sim = Simulation(store.data)
            self.assertAlmostEqual(10, sim._shortest_path_same_floor(0, 'A', 'B')['distance_m'])
            self.assertEqual(both, sim._shortest_path_same_floor(0, 'B', 'A') is not None)

    def test_grid_and_point_snapping_avoid_duplicates(self):
        store = empty_store()
        first = store.draw_corridor_step(None, 0, 10.2, 2.7)
        self.assertEqual((10, 3), (first['x'], first['y']))
        again = store.draw_corridor_step(first['name'], 0, 10.1, 3.2)
        self.assertEqual(first['name'], again['name'])
        self.assertEqual(1, len(store.data['corridors']['nodes']))
        self.assertFalse(store.data['corridors']['edges'])
        # Outside the point snap radius, but rounded onto the same grid point.
        again = store.draw_corridor_step(None, 0, 10.4, 3.4)
        self.assertEqual(first['name'], again['name'])

    def test_snap_disabled_preserves_millimetre_coordinates_and_collision_free_names(self):
        store = empty_store()
        store.data['locations'].append(dict(name='C0-1', floor=0, x=40, y=40))
        result = store.draw_corridor_step(None, 0, 10.2344, 5.6781, snap=False)
        self.assertEqual('C0-2', result['name'])
        self.assertEqual((10.234, 5.678), (result['x'], result['y']))

    def test_grid_rounded_point_on_edge_creates_connected_junction(self):
        store = empty_store()
        store.connect_corridor('A', 'B')
        # 0.56 m from the diagonal, outside its 0.45 m pick tolerance.
        target = store.draw_corridor_step(None, 0, 3.4, 3.6)
        self.assertEqual('edge', target['kind'])
        self.assertEqual((3, 4), (target['x'], target['y']))
        self.assertEqual(2, len(store.data['corridors']['edges']))
        sim = Simulation(store.data)
        self.assertAlmostEqual(10, sim._shortest_path_same_floor(0, 'A', 'B')['distance_m'])

    def test_branch_joins_edge_and_preserves_profile_without_permitting_new_branch(self):
        store = empty_store()
        store.connect_corridor('A', 'B', False)
        store.data['route_profiles'] = {'clean': {'allowed_edges': [['A', 'B']]}}
        root = store.draw_corridor_step(None, 0, 10, 0)['name']
        target = store.draw_corridor_step(root, 0, 3.08, 3.94)
        self.assertEqual('edge', target['kind'])
        self.assertAlmostEqual(3, target['x'])
        self.assertAlmostEqual(4, target['y'])
        n = target['name']
        self.assertEqual([['A', n], [n, 'B']], store.data['route_profiles']['clean']['allowed_edges'])
        self.assertEqual(3, len(store.data['corridors']['edges']))
        sim = Simulation(store.data)
        self.assertIsNotNone(sim._shortest_path_same_floor(0, root, 'B'))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))

    def test_drawing_along_existing_one_way_corridor_keeps_its_permissions(self):
        store = empty_store()
        store.connect_corridor('A', 'B', False)
        before = deepcopy(store.data)
        target = store.draw_corridor_step('B', 0, 0, 0, bidirectional=True)
        self.assertFalse(target['connected'])
        self.assertEqual(before, store.data)

    def test_invalid_connection_rolls_back_target_node_and_edge_split(self):
        store = empty_store()
        store.connect_corridor('A', 'B')
        root = store.draw_corridor_step(None, 0, 10, 0)['name']
        store.data['building']['default_corridor_width_m'] = -1
        before = deepcopy(store.data)
        for x, y in [(3, 4), (20, 20)]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                store.draw_corridor_step(root, 0, x, y)
            self.assertEqual(before, store.data)

    def test_cross_floor_deleted_anchor_nonfinite_and_department_rejected(self):
        store = empty_store()
        before = deepcopy(store.data)
        for start, floor, x, y in [('A', 1, 8, 8), ('gone', 0, 8, 8), ('A', 0, float('nan'), 8)]:
            with self.subTest(start=start, floor=floor), self.assertRaises(ValueError):
                store.draw_corridor_step(start, floor, x, y)
            self.assertEqual(before, store.data)
        points = store.all_points()
        points['D'] = dict(kind='department', floor=0, x=20, y=20)
        with self.assertRaisesRegex(ValueError, 'department'):
            drawing_target(points, [], 0, 20, 20)

    def test_crossing_line_is_not_automatically_a_junction(self):
        store = empty_store()
        store.connect_corridor('A', 'B')
        root = store.draw_corridor_step(None, 0, -4, 4)['name']
        store.draw_corridor_step(root, 0, 10, 4)
        self.assertEqual(2, len(store.data['corridors']['edges']))
        self.assertEqual(2, len(store.data['corridors']['nodes']))

    def test_connect_rejects_self_and_cross_floor_links_without_mutation(self):
        store = empty_store()
        before = deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.connect_corridor('A', 'A')
        self.assertEqual(before, store.data)
        store.data['locations'][1]['floor'] = 1
        before = deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.connect_corridor('A', 'B')
        self.assertEqual(before, store.data)

    def test_saved_drawn_reference_is_nine_seconds_with_no_reverse_route(self):
        import json
        from pathlib import Path
        config = json.loads((Path(__file__).resolve().parents[1] / 'verification/scenarios/corridor-drawn-one-way.json').read_text(encoding='utf-8'))
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config)
            sim.run()
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])
        self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))


class CorridorDrawingUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_each_click_is_one_undo_including_split_and_link(self):
        self.editor._set_edit_mode('corridor_draw')
        self.editor.on_left_click(self.event, 10, 0)
        before = deepcopy(self.editor.store.data)
        self.editor.on_left_click(self.event, 1.5, -2)
        after = deepcopy(self.editor.store.data)
        self.assertEqual(4, len(after['corridors']['edges']))
        self.assertEqual(3, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertIsNone(self.editor.corridor_draw_start)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)

    def test_preview_uses_same_target_and_changes_no_configuration_or_history(self):
        self.editor._set_edit_mode('corridor_draw')
        before = deepcopy(self.editor.store.data)
        self.editor.preview_corridor_drawing(1.58, -1.94)
        target = self.editor.corridor_draw_preview
        self.assertAlmostEqual(1.5, target['x'])
        self.assertAlmostEqual(2, target['y'])
        self.assertEqual('edge', target['kind'])
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.editor.draw_next_corridor(1.58, 1.94)
        point = self.editor.store.all_points()[self.editor.corridor_draw_start]
        self.assertEqual((target['x'], target['y']), (point['x'], point['y']))

    def test_finish_mode_floor_and_history_reset_clear_anchor(self):
        for finish in [lambda: self.editor.on_right_click(self.event, 0, 0),
                       lambda: self.editor.finish_route_action.trigger(),
                       lambda: self.editor._set_edit_mode('select_move'),
                       lambda: self.editor.floor_spin.setValue(1),
                       self.editor._reset_edit_history]:
            self.editor.floor_spin.setValue(0)
            self.editor._set_edit_mode('corridor_draw')
            self.editor.draw_next_corridor(0, 0)
            self.assertEqual('A', self.editor.corridor_draw_start)
            before = deepcopy(self.editor.store.data)
            finish()
            self.assertIsNone(self.editor.corridor_draw_start)
            self.assertEqual(before, self.editor.store.data)

    def test_connect_tool_unchecked_direction_is_one_way(self):
        self.editor.store = empty_store()
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor._set_edit_mode('edge')
        self.editor.bidirectional_check.setChecked(False)
        self.editor.on_left_click(self.event, 0, 0)
        self.editor.on_left_click(self.event, 6, -8)
        sim = Simulation(self.editor.store.data)
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B'))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))
        self.assertEqual(2, len(self.editor.edit_history.entries))

    def test_double_click_finishes_without_opening_point_dialog(self):
        self.editor._set_edit_mode('corridor_draw')
        self.editor.draw_next_corridor(0, 0)
        with patch('app.PointEditorDialog') as dialog:
            self.editor.on_double_click(self.event, 0, 0)
        dialog.assert_not_called()
        self.assertIsNone(self.editor.corridor_draw_start)
