"""Failed editor operations restore the model instead of committing partial work."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from tests import test_cad_delete_and_drawing_history as drawings
from visualiser.edit_history import undoable


class EditTransactionTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_failed_rotation_restores_geometry_selection_history_and_drawing_cache(self):
        e = self.editor
        drawings.CadDeleteAndDrawingHistoryTests.drawings(self)
        e.selected_point_names = {'A','Door'}
        before = deepcopy(e.store.data)
        history = deepcopy(e.edit_history.entries)
        cached = dict(e._dxf_cache)
        original_refresh = e.refresh_canvas
        calls = 0
        def fail_once(*args,**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError('display interrupted')
            return original_refresh(*args,**kwargs)
        with patch.object(e,'refresh_canvas',side_effect=fail_once), self.assertRaisesRegex(RuntimeError,'display interrupted'):
            e.rotate_selected((0,0),90)
        self.assertEqual(before,e.store.data)
        self.assertEqual(history,e.edit_history.entries)
        self.assertEqual({'A','Door'},e.selected_point_names)
        self.assertEqual(0,e._edit_depth)
        for floor,source in cached.items():
            self.assertIs(source,e._dxf_cache[floor])
        self.assertIn('not applied',e.status_label.text())

    def test_nested_failure_rolls_back_every_change_and_retains_redo_branch(self):
        e = self.editor
        e.selected_point_names = {'A'}
        e.move_selected_by(2,0)
        after_move = deepcopy(e.store.data)
        e.undo_edit()
        before = deepcopy(e.store.data)
        history = deepcopy(e.edit_history.entries)
        @undoable('Inner edit')
        def inner(editor):
            editor.store.data['simulation']['duration'] = 123
            raise ValueError('rejected')
        @undoable('Combined edit')
        def outer(editor):
            editor.store.set_point_position('B',50,50)
            inner(editor)
        with self.assertRaisesRegex(ValueError,'rejected'):
            outer(e)
        self.assertEqual(before,e.store.data)
        self.assertEqual(history,e.edit_history.entries)
        self.assertTrue(e.redo_edit())
        self.assertEqual(after_move,e.store.data)

    def test_failed_drag_release_restores_pre_drag_configuration(self):
        e = self.editor
        before = deepcopy(e.store.data)
        e.on_left_click(self.event,0,0)
        p = e.world_to_scene(2,1)
        e.on_drag(self.event,p.x(),p.y())
        self.assertNotEqual(before,e.store.data)
        original_refresh = e.refresh_canvas
        with patch.object(e,'refresh_canvas',side_effect=[RuntimeError('release failed'),None]):
            with self.assertRaisesRegex(RuntimeError,'release failed'):
                e.on_left_release(self.event)
        original_refresh()
        self.assertEqual(before,e.store.data)
        self.assertEqual(1,len(e.edit_history.entries))
        self.assertFalse(e.drag_mode_active)
        self.assertFalse(e._drag_refresh_timer.isActive())

    def test_cleanup_failure_preserves_original_error_and_restored_model(self):
        e = self.editor
        before = deepcopy(e.store.data)
        e.selected_point_names = {'A'}
        with patch.object(e,'refresh_canvas',side_effect=RuntimeError('renderer failed')):
            with self.assertRaisesRegex(RuntimeError,'renderer failed') as caught:
                e.move_selected_by(1,2)
        self.assertEqual(before,e.store.data)
        self.assertEqual(1,len(e.edit_history.entries))
        self.assertIn('Model and history were restored',caught.exception.__notes__[0])

    def test_pending_changes_before_failed_command_are_retained(self):
        e = self.editor
        e.store.set_point_position('B',20,30)
        pending = deepcopy(e.store.data)
        @undoable('Failed configuration')
        def broken(editor):
            editor.store.data['locations'].clear()
            raise ValueError('bad edit')
        with self.assertRaises(ValueError):
            broken(e)
        self.assertEqual(pending,e.store.data)
        self.assertEqual(2,len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual((6,8),(e.store.get_location('B')['x'],e.store.get_location('B')['y']))

    def test_history_commit_failure_also_rolls_back_the_edit(self):
        e = self.editor
        e.selected_point_names = {'A'}
        before = deepcopy(e.store.data)
        record = e.edit_history.record
        def fail_changed(config,label):
            if config != before:
                raise ValueError('history storage failed')
            return record(config,label)
        with patch.object(e.edit_history,'record',side_effect=fail_changed):
            with self.assertRaisesRegex(ValueError,'history storage failed'):
                e.move_selected_by(1,2)
        self.assertEqual(before,e.store.data)
        self.assertEqual(1,len(e.edit_history.entries))
        self.assertEqual(0,e._edit_depth)
