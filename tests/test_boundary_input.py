"""Exact polygon entry shares mouse drafts and commits only at completion."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests import test_corridor_editing as editing


class BoundaryInputTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def start(self):
        self.assertTrue(self.editor.start_location_bounding_box_draw('A'))
        self.assertFalse(self.editor.boundary_input.isHidden())
        return self.editor.boundary_input

    def enter(self, bar, text):
        bar.coordinate.setText(text)
        QTest.keyClick(bar.coordinate, Qt.Key_Return)

    def test_absolute_relative_and_polar_entry_are_exact_and_one_undo(self):
        e = self.editor
        before = deepcopy(e.store.data)
        e.grid_spacing_spin.setValue(10)
        bar = self.start()
        self.enter(bar, '0.1234567,0.25')
        self.enter(bar, '@4,0')
        bar.coordinate.setText('@3<90')
        self.assertIn('Segment 3 m', bar.feedback.text())
        self.assertEqual(2, len(e.bounding_box_points))
        QTest.keyClick(bar.coordinate, Qt.Key_Return)
        self.assertEqual(before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))
        self.enter(bar, '')
        self.assertTrue(bar.isHidden())
        expected = [(0.1234567, .25), (4.1234567, .25), (4.1234567, 3.25)]
        for p, (x, y) in zip(e.store.get_location_bounding_box_points('A'), expected):
            self.assertAlmostEqual(x, p['x'])
            self.assertAlmostEqual(y, p['y'])
        self.assertEqual(2, len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(before, e.store.data)

    def test_mouse_vertices_are_relative_anchors_and_undo_point_is_draft_only(self):
        e = self.editor
        before = deepcopy(e.store.data)
        bar = self.start()
        p = e.world_to_scene(10, 10)
        e.on_left_click(self.event, p.x(), p.y())
        self.enter(bar, '@4,0')
        self.assertEqual([dict(x=10, y=10), dict(x=14, y=10)], e.bounding_box_points)
        bar.remove_button.click()
        self.assertEqual([dict(x=10, y=10)], e.bounding_box_points)
        self.enter(bar, '@0,3')
        self.assertEqual(dict(x=10, y=13), e.bounding_box_points[-1])
        QTest.keyClick(bar.coordinate, Qt.Key_Escape)
        self.assertTrue(bar.isHidden())
        self.assertEqual(before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))

    def test_invalid_input_and_early_finish_retain_draft(self):
        bar = self.start()
        for text in ('@2,3', 'nan,2', '1,', '1e309,0'):
            self.enter(bar, text)
            self.assertFalse(bar.add_button.isEnabled())
            self.assertEqual([], self.editor.bounding_box_points)
        self.enter(bar, '1,1')
        self.enter(bar, '@0,0')
        self.assertEqual(1, len(self.editor.bounding_box_points))
        self.enter(bar, '')
        self.assertIn('at least three', bar.feedback.text())
        self.assertFalse(bar.isHidden())

    def test_stale_location_rejects_coordinate_and_point_removal(self):
        bar = self.start()
        self.enter(bar, '1,1')
        self.editor.store.set_point_position('A', 5, 5)
        self.enter(bar, '@3,0')
        bar.remove_last()
        self.assertEqual([dict(x=1, y=1)], self.editor.bounding_box_points)
        self.assertIn('Location changed', bar.feedback.text())

    def test_floor_change_hides_and_clears_entry(self):
        bar = self.start()
        bar.coordinate.setText('10,20')
        self.editor.floor_spin.setValue(1)
        self.assertTrue(bar.isHidden())
        self.assertEqual('', bar.coordinate.text())
        bar.submit()
        self.assertEqual([], self.editor.bounding_box_points)

    def test_corner_drag_and_run_lock_block_inline_mutations(self):
        bar = self.start()
        self.enter(bar, '1,1')
        p = self.editor.world_to_scene(1, 1)
        self.editor.on_left_click(self.event, p.x(), p.y())
        self.enter(bar, '@2,0')
        bar.remove_last()
        self.assertEqual([dict(x=1, y=1)], self.editor.bounding_box_points)
        self.editor.on_left_release(self.event)
        self.assertTrue(bar.add_button.isEnabled())
        with patch.object(self.editor, 'project_editing_locked', return_value=True):
            bar.submit()
            bar.remove_last()
            bar.finish()
        self.assertEqual([dict(x=1, y=1)], self.editor.bounding_box_points)
