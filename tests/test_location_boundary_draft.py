"""Boundary drafting cancellation, invalid input and stale-edit acceptance cases."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing


class BoundaryDraftTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def begin(self):
        e = self.editor
        e.store.set_location_bounding_box('A', [dict(x=-2, y=-2), dict(x=2, y=-2),
                                              dict(x=2, y=2), dict(x=-2, y=2)])
        e._reset_edit_history()
        self.before = deepcopy(e.store.data)
        self.assertTrue(e.start_location_bounding_box_draw('A', keep_existing=True))
        return e

    def drag(self, e):
        p = e.world_to_scene(-2, -2)
        e.on_left_click(self.event, p.x(), p.y())
        self.assertEqual(0, e.dragging_bounding_box_point_index)
        p = e.world_to_scene(-4, -3)
        e.on_drag(self.event, p.x(), p.y())
        self.assertEqual(dict(x=-4, y=-3), e.bounding_box_points[0])

    def test_escape_during_drag_restores_draft_then_cancels_boundary(self):
        e = self.begin()
        original = deepcopy(e.bounding_box_points)
        self.drag(e)
        self.assertTrue(e.cancel_cad_command())
        self.assertEqual(original, e.bounding_box_points)
        self.assertEqual('A', e.bounding_box_location_name)
        self.assertIsNone(e.dragging_bounding_box_point_index)
        e.on_left_release(self.event)
        self.assertTrue(e.cancel_cad_command())
        self.assertIsNone(e.bounding_box_location_name)
        self.assertEqual(self.before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))

    def test_released_corner_is_draft_until_finish_and_one_undo(self):
        e = self.begin()
        self.drag(e)
        e.on_left_release(self.event)
        self.assertEqual(self.before, e.store.data)
        self.assertTrue(e.finish_location_bounding_box_draw())
        self.assertEqual(dict(x=-4, y=-3), e.store.get_location_bounding_box_points('A')[0])
        after = deepcopy(e.store.data)
        self.assertEqual(2, len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(self.before, e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(after, e.store.data)

    def test_invalid_and_incomplete_drafts_preserve_original_and_remain_editable(self):
        e = self.begin()
        for points in ([dict(x=0, y=0)],
                       [dict(x=0, y=0), dict(x=float('inf'), y=0), dict(x=0, y=2)]):
            e.bounding_box_points = points
            self.assertFalse(e.finish_location_bounding_box_draw())
            self.assertEqual('A', e.bounding_box_location_name)
            self.assertEqual(self.before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))

    def test_changed_location_cannot_be_overwritten_by_old_draft(self):
        e = self.begin()
        e.store.set_point_position('A', 10, 20)
        changed = deepcopy(e.store.data)
        self.assertFalse(e.finish_location_bounding_box_draw())
        self.assertIn('Location changed', e.status_label.text())
        self.assertEqual(changed, e.store.data)

    def test_escape_after_release_cancels_whole_draft(self):
        e = self.begin()
        self.drag(e)
        e.on_left_release(self.event)
        self.assertTrue(e.cancel_cad_command())
        self.assertIsNone(e.bounding_box_location_name)
        self.assertEqual(self.before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))

    def test_leaving_layout_discards_draft_without_committing(self):
        e = self.begin()
        self.drag(e)
        e.workspace.activate('configuration')
        self.assertIsNone(e.bounding_box_location_name)
        self.assertIsNone(e.dragging_bounding_box_point_index)
        self.assertFalse(e.finish_location_bounding_box_draw())
        self.assertEqual(self.before, e.store.data)

    def test_floor_and_tool_changes_cancel_draft(self):
        e = self.begin()
        self.drag(e)
        e.floor_spin.setValue(1)
        self.assertIsNone(e.bounding_box_location_name)
        self.assertIsNone(e.dragging_bounding_box_point_index)
        self.assertFalse(e.finish_location_bounding_box_draw())
        self.assertFalse(e.start_location_bounding_box_draw('A'))
        e.floor_spin.setValue(0)
        self.assertTrue(e.start_location_bounding_box_draw('A', keep_existing=True))
        e._set_edit_mode('select_move')
        self.assertIsNone(e.bounding_box_location_name)
        self.assertEqual(self.before, e.store.data)
