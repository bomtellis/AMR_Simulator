"""Base/destination picking uses the existing move/copy transactions."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing


class CanvasDisplacementTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def start(self, copy=False):
        self.editor.selected_point_names = {'B'}
        (self.editor.show_selection_copy if copy else self.editor.show_selection_move)()
        bar = self.editor.cad_copy_input if copy else self.editor.cad_move_input
        bar.pick_button.click()
        return bar

    def click(self, x,y):
        pos = self.editor.world_to_scene(x,y)
        self.editor.on_left_click(self.event,pos.x(),pos.y())
        self.editor.on_left_release(self.event)

    def check_commit(self, copy=False):
        e = self.editor
        bar = self.start(copy)
        before = deepcopy(e.store.data)
        self.click(10,10)
        self.assertEqual({'B'},e.selected_point_names)
        pos = e.world_to_scene(20,10)
        bar.pointer_moved(pos.x(),pos.y())
        self.assertTrue(bar.mouse_timer.isActive())
        self.assertIsNone(bar.preview_store)
        bar.mouse_timer.stop()
        bar._update_mouse_preview()
        preview = deepcopy(bar.preview_store.data)
        self.assertEqual(before,e.store.data)
        self.click(20,10)
        self.assertEqual(preview,e.store.data)
        name = next(iter(e.selected_point_names))
        self.assertEqual((16,8),(e.store.all_points()[name]['x'],e.store.all_points()[name]['y']))
        if copy:
            self.assertNotEqual('B',name)
            self.assertEqual((6,8),(e.store.all_points()['B']['x'],e.store.all_points()['B']['y']))
        self.assertTrue(bar.isHidden())
        self.assertIsNone(bar.mouse_stage)
        self.assertIsNone(bar.preview_store)
        self.assertEqual(2,len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(before,e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(preview,e.store.data)

    def test_move_matches_preview_and_has_one_undo(self):
        self.check_commit()

    def test_copy_matches_preview_preserves_original_and_has_one_undo(self):
        self.check_commit(copy=True)

    def test_copy_collision_rejected_and_right_click_cancels(self):
        e = self.editor
        bar = self.start(copy=True)
        before = deepcopy(e.store.data)
        self.click(6,8)
        self.click(0,0)
        self.assertFalse(bar.apply_button.isEnabled())
        self.assertEqual('target',bar.mouse_stage)
        self.assertEqual(before,e.store.data)
        e.on_right_click(self.event,0,0)
        self.assertIsNone(e._active_canvas_transform())
        self.assertIsNone(bar.preview_store)
        self.assertFalse(bar.mouse_timer.isActive())
        self.assertEqual(1,len(e.edit_history.entries))

    def test_zero_move_does_not_commit_and_floor_change_cancels(self):
        e = self.editor
        bar = self.start()
        before = deepcopy(e.store.data)
        self.click(0,0)
        self.click(0,0)
        self.assertFalse(bar.apply_button.isEnabled())
        self.assertEqual(before,e.store.data)
        e.floor_spin.setValue(1)
        self.assertIsNone(bar.mouse_stage)
        self.assertFalse(bar.mouse_timer.isActive())

    def test_reopening_command_resets_picks_and_locked_layer_prevents_gesture(self):
        e = self.editor
        bar = self.start()
        self.click(0,0)
        e.show_selection_move()
        self.assertIsNone(bar.mouse_stage)
        e.update_model_layer('Default',locked=True)
        e.show_selection_move()
        bar.begin_mouse()
        self.assertIsNone(bar.mouse_stage)
