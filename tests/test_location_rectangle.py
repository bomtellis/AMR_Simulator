"""Two-corner footprint geometry and nonmutating CAD drafts."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing
from visualiser.location_drawing import rectangle_points


class RectangleGeometryTests(unittest.TestCase):
    def test_opposite_corner_order_preserves_known_rectangle(self):
        expected = [dict(x=-2,y=-1),dict(x=3,y=-1),dict(x=3,y=4),dict(x=-2,y=4)]
        for first, second in [((-2,-1),(3,4)), ((3,4),(-2,-1)), ((-2,4),(3,-1))]:
            self.assertEqual(expected, rectangle_points(first, second))

    def test_degenerate_and_nonfinite_corners_rejected(self):
        for second in [(0,3),(3,0),(float('nan'),2),(float('inf'),2)]:
            with self.assertRaises(ValueError):
                rectangle_points((0,0), second)


class RectangleUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_preview_and_first_corner_leave_model_unchanged_then_commit_one_undo(self):
        before = deepcopy(self.editor.store.data)
        self.assertTrue(self.editor.start_location_rectangle('A'))
        self.assertTrue(self.editor.place_location_rectangle_corner(-2,-1))
        scene = self.editor.world_to_scene(3,4)
        self.editor.preview_location_rectangle(scene.x(), scene.y())
        self.assertEqual((3,4), self.editor._rectangle_draft['second'])
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.place_location_rectangle_corner(3,4))
        self.assertEqual(rectangle_points((-2,-1),(3,4)), self.editor.store.get_location_bounding_box_points('A'))
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertEqual('select_move', self.editor._current_edit_mode())
        after = deepcopy(self.editor.store.data)
        self.editor.undo_edit()
        self.assertEqual(before, self.editor.store.data)
        self.editor.redo_edit()
        self.assertEqual(after, self.editor.store.data)

    def test_replacement_cancel_and_zero_width_retain_existing_outline(self):
        self.editor.store.set_location_bounding_box('A', rectangle_points((-1,-1),(1,1)))
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        for cancel in [self.editor.cancel_cad_command, lambda: self.editor.on_right_click(self.event,0,0),
                       lambda: self.editor.floor_spin.setValue(1), lambda: self.editor._set_edit_mode('location')]:
            self.editor.floor_spin.setValue(0)
            self.editor.start_location_rectangle('A')
            self.editor.place_location_rectangle_corner(-2,-2)
            self.assertFalse(self.editor.place_location_rectangle_corner(-2,4))
            cancel()
            self.assertIsNone(self.editor._rectangle_draft)
            self.assertEqual(before, self.editor.store.data)
            self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_stale_location_and_other_floor_are_rejected(self):
        self.editor.start_location_rectangle('A')
        self.editor.place_location_rectangle_corner(-2,-2)
        self.editor.store.get_location('A')['x'] = 9
        before = deepcopy(self.editor.store.data)
        self.assertFalse(self.editor.place_location_rectangle_corner(4,4))
        self.assertEqual(before, self.editor.store.data)
        self.assertIsNone(self.editor._rectangle_draft)
        self.editor.floor_spin.setValue(1)
        self.assertFalse(self.editor.start_location_rectangle('A'))

    def test_grid_and_location_relative_storage_are_preserved(self):
        self.editor.grid_spacing_spin.setValue(.5)
        self.editor.start_location_rectangle('B')
        self.editor.place_location_rectangle_corner(4.13,6.13)
        self.editor.place_location_rectangle_corner(8.13,10.13)
        box = self.editor.store.get_location('B')['bounding_box']
        self.assertTrue(all('dx' in p and 'dy' in p and 'x' not in p for p in box))
        self.assertEqual(rectangle_points((4,6),(8,10)), self.editor.store.get_location_bounding_box_points('B'))
