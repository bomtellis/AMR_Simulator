"""CAD coordinate references and atomic, keyboard-driven corridor drawing."""
from copy import deepcopy
import math
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
from shiboken6 import isValid
from app import AMRGraphEditor
from cad_drawing_input import parse_coordinate
from amr_recovery import RecoveryStore


class CoordinateReferenceTests(unittest.TestCase):
    def test_absolute_relative_and_polar_independent_coordinates(self):
        self.assertEqual((1.123456789, -2.5), parse_coordinate('1.123456789,-2.5'))
        self.assertEqual((13, 24), parse_coordinate('@3,4', (10, 20)))
        for text, expected in (('@10<0', (20,20)), ('@10<90', (10,30)),
                               ('@10<-90', (10,10)), ('@10<180', (0,20))):
            with self.subTest(text=text):
                actual = parse_coordinate(text, (10,20))
                self.assertAlmostEqual(expected[0], actual[0])
                self.assertAlmostEqual(expected[1], actual[1])
        self.assertIsNone(parse_coordinate('  '))

    def test_incomplete_nonfinite_negative_polar_and_expressions_are_rejected(self):
        for text in ('1,', '@', '@10<', '1,2,3', 'nan,2', '1,inf', '@-1<90',
                     '@0<0', '10<45', '1+2,3', '__import__("os"),2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_coordinate(text, (0,0))
        with self.assertRaises(ValueError): parse_coordinate('@1,2')
        with self.assertRaises(ValueError): parse_coordinate('@1e308,0', (1e308,0))


class CadDrawingInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.editor = AMRGraphEditor()
        self.editor._recovery_store = RecoveryStore(Path(self.temporary.name)/'recovery')
        self.editor._drawings_enabled = False
        self.editor.store.data['corridors'] = {'nodes': [], 'edges': [], 'auto_connect': False}
        self.editor.store.data['locations'] = []
        self.editor._reset_edit_history()
        self.editor._set_edit_mode('corridor_draw')
        self.widget = self.editor.ensure_cad_drawing_input()

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(self.editor))
        self.temporary.cleanup()

    def enter(self, text):
        self.widget.coordinate_edit.setText(text)
        QTest.keyClick(self.widget.coordinate_edit, Qt.Key_Return)

    def test_two_ten_metre_links_and_each_step_undo_redo(self):
        self.enter('0,0')
        first = deepcopy(self.editor.store.data)
        self.enter('@10,0')
        second = deepcopy(self.editor.store.data)
        self.enter('@10<90')
        third = deepcopy(self.editor.store.data)
        points = self.editor.store.all_points()
        edges = third['corridors']['edges']
        self.assertEqual(2, len(edges))
        for edge in edges:
            a,b = points[edge['from']],points[edge['to']]
            self.assertAlmostEqual(10, math.hypot(a['x']-b['x'], a['y']-b['y']))
        self.assertEqual(4, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(second, self.editor.store.data)
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(first, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(second, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(third, self.editor.store.data)

    def test_invalid_draft_is_inline_and_never_changes_project_or_history(self):
        self.enter('0,0')
        before = deepcopy(self.editor.store.data)
        history = len(self.editor.edit_history.entries)
        for text in ('@10<', 'nan,0', '@-1<0'):
            with self.subTest(text=text):
                self.enter(text)
                self.assertEqual(text, self.widget.coordinate_edit.text())
                self.assertIn('Input error:', self.widget.feedback_label.text())
                self.assertEqual(before, self.editor.store.data)
                self.assertEqual(history, len(self.editor.edit_history.entries))

    def test_typed_precision_bypasses_grid_and_existing_click_rounding_stays(self):
        self.editor.snap_check.setChecked(True)
        self.enter('1.123456789,2.987654321')
        point = self.editor.store.all_points()[self.editor.corridor_draw_start]
        self.assertEqual((1.123456789,2.987654321), (point['x'], point['y']))
        self.assertIn('grid bypassed', self.widget.feedback_label.text())
        self.editor.finish_corridor_drawing()
        self.editor.draw_next_corridor(10.2,10.7)
        point = self.editor.store.all_points()[self.editor.corridor_draw_start]
        self.assertEqual((10,11), (point['x'],point['y']))

    def test_point_and_edge_object_snaps_are_visible_before_atomic_commit(self):
        self.editor.store.add_corridor_node('A',0,0,0)
        self.editor.store.add_corridor_node('B',0,10,0)
        self.editor.store.add_edge('A','B')
        edge = self.editor.store.data['corridors']['edges'][0]
        edge.update(width_m=1.7,bidirectional=False,route_note='preserve')
        self.editor._reset_edit_history()
        self.widget.coordinate_edit.setText('.1,.1')
        self.assertIn('Object snap: existing point',self.widget.feedback_label.text())
        self.assertIn('X 0, Y 0',self.widget.feedback_label.text())
        self.enter('.1,.1')
        self.assertEqual('A',self.editor.corridor_draw_start)
        before = deepcopy(self.editor.store.data)
        self.widget.coordinate_edit.setText('5,.1')
        self.assertIn('Object snap: corridor split',self.widget.feedback_label.text())
        self.assertIn('X 5, Y 0',self.widget.feedback_label.text())
        self.enter('5,.1')
        self.assertEqual(2,len(self.editor.store.data['corridors']['edges']))
        for segment in self.editor.store.data['corridors']['edges']:
            self.assertEqual(1.7,segment['width_m'])
            self.assertFalse(segment['bidirectional'])
            self.assertEqual('preserve',segment['route_note'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before,self.editor.store.data)

    def test_escape_cancels_only_uncommitted_state_and_blank_enter_finishes(self):
        self.enter('0,0')
        self.enter('@10,0')
        before = deepcopy(self.editor.store.data)
        history = len(self.editor.edit_history.entries)
        self.widget.coordinate_edit.setText('@10<90')
        self.assertIsNotNone(self.editor.corridor_draw_preview)
        QTest.keyClick(self.widget.coordinate_edit,Qt.Key_Escape)
        self.assertEqual('',self.widget.coordinate_edit.text())
        self.assertIsNone(self.editor.corridor_draw_preview)
        self.assertIsNone(self.editor.corridor_draw_start)
        self.assertEqual(before,self.editor.store.data)
        self.assertEqual(history,len(self.editor.edit_history.entries))
        self.enter('10,0')
        self.assertIsNotNone(self.editor.corridor_draw_start)
        self.enter('')
        self.assertIsNone(self.editor.corridor_draw_start)
        self.assertEqual(before,self.editor.store.data)

    def test_pointer_feedback_reports_world_length_angle_and_does_not_overwrite_typed_preview(self):
        self.enter('0,0')
        self.editor.preview_corridor_drawing(0,-10)
        self.assertIn('10 m at 90',self.widget.feedback_label.text())
        self.widget.coordinate_edit.setText('@10,0')
        self.editor.preview_corridor_drawing(0,-20)
        self.assertEqual(10,self.editor.corridor_draw_preview['x'])
        self.assertEqual(0,self.editor.corridor_draw_preview['y'])

    def test_switching_modes_hides_row_and_clears_only_draft(self):
        self.enter('0,0')
        before = deepcopy(self.editor.store.data)
        self.widget.coordinate_edit.setText('@10,0')
        self.editor._set_edit_mode('select_move')
        self.assertTrue(self.widget.isHidden())
        self.assertEqual('',self.widget.coordinate_edit.text())
        self.assertIsNone(self.editor.corridor_draw_preview)
        self.assertEqual(before,self.editor.store.data)

    def test_focused_escape_runs_one_handler_and_click_replaces_typed_draft(self):
        self.editor.show()
        QApplication.processEvents()
        self.enter('0,0')
        self.widget.coordinate_edit.setText('@10,0')
        self.editor.draw_next_corridor(0,10)
        self.assertEqual('',self.widget.coordinate_edit.text())
        self.widget.coordinate_edit.setText('@5,0')
        self.widget.coordinate_edit.setFocus()
        with patch.object(self.editor, 'finish_corridor_drawing',
                          wraps=self.editor.finish_corridor_drawing) as finish:
            QTest.keyClick(self.widget.coordinate_edit, Qt.Key_Escape)
        self.assertEqual(1,finish.call_count)
        self.assertIsNone(self.editor.corridor_draw_start)


if __name__ == '__main__': unittest.main()
