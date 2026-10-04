"""CAD selection geometry and production-canvas mouse-event acceptance."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QPainterPath, QPainterPathStroker
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import AMRGraphEditor
from cad_selection import rectangle_hits, point_hit, editor_paths
from amr_recovery import RecoveryStore


def rectangle(x, y, w, h):
    shape = QPainterPath()
    shape.addRect(QRectF(x, y, w, h))
    return shape


class CadSelectionGeometryTests(unittest.TestCase):
    def test_window_requires_full_object_and_crossing_accepts_partial(self):
        paths = {'inside': rectangle(2, 2, 2, 2), 'partial': rectangle(8, 2, 4, 2),
                 'outside': rectangle(20, 20, 2, 2)}
        self.assertEqual({'inside'}, rectangle_hits(paths, QPointF(0, 0), QPointF(10, 10)))
        self.assertEqual({'inside', 'partial'}, rectangle_hits(paths, QPointF(10, 0), QPointF(0, 10)))

    def test_crossing_uses_real_ellipse_not_its_bounding_rectangle(self):
        circle = QPainterPath()
        circle.addEllipse(QRectF(0, 0, 10, 10))
        self.assertEqual(set(), rectangle_hits({'circle': circle}, QPointF(1, 0), QPointF(0, 1)))
        self.assertEqual({'circle'}, rectangle_hits({'circle': circle}, QPointF(6, -1), QPointF(4, 1)))

    def test_window_cannot_select_marker_without_visible_location_footprint(self):
        shape = rectangle(4, 4, 1, 1).united(rectangle(1, 1, 8, 8))
        self.assertEqual(set(), rectangle_hits({'location': shape}, QPointF(3, 3), QPointF(6, 6)))
        self.assertEqual({'location'}, rectangle_hits({'location': shape}, QPointF(0, 0), QPointF(10, 10)))

    def test_crossing_selects_edge_even_with_both_endpoints_outside(self):
        line = QPainterPath()
        line.moveTo(-10, 5)
        line.lineTo(20, 5)
        stroke = QPainterPathStroker()
        stroke.setWidth(1)
        paths = {'edge': stroke.createStroke(line)}
        self.assertEqual({'edge'}, rectangle_hits(paths, QPointF(10, 0), QPointF(0, 10)))
        self.assertEqual(set(), rectangle_hits(paths, QPointF(0, 0), QPointF(10, 10)))

    def test_point_halo_is_six_pixels_and_points_precede_edges(self):
        paths = {('point', 'N'): rectangle(0, 0, 2, 2), ('edge', ('A', 'B')): rectangle(-20, 0, 40, 1)}
        self.assertEqual(('point', 'N'), point_hit(paths, QPointF(7, 1)))
        self.assertEqual(('edge', ('A', 'B')), point_hit(paths, QPointF(9, 1)))
        self.assertIsNone(point_hit(paths, QPointF(9, 9)))


class CadSelectionCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = AMRGraphEditor()
        self.editor._drawings_enabled = False
        self.editor._recovery_store = RecoveryStore(Path(self.temp.name) / 'recovery')
        self.editor.store.add_corridor_node('A', 0, 0, 0)
        self.editor.store.add_corridor_node('B', 0, 10, 0)
        self.editor.store.add_corridor_node('N', 0, 5, 3)
        self.editor.store.add_corridor_node('OtherFloor', 1, 5, 3)
        self.editor.store.add_edge('A', 'B')
        self.editor.refresh_canvas()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.editor.resize(1200, 850)
        self.editor.show()
        self.app.processEvents()
        self.editor.canvas.resetTransform()
        self.editor.canvas.scale(25, 25)
        self.editor.canvas.centerOn(5, -1)
        self.editor.snap_check.setChecked(False)
        self.app.processEvents()

    def tearDown(self):
        QTest.mouseRelease(self.editor.canvas.viewport(), Qt.LeftButton, Qt.NoModifier)
        QTest.keyClick(self.editor, Qt.Key_Shift, Qt.NoModifier)
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def pixel(self, x, y):
        return self.editor.canvas.mapFromScene(self.editor.world_to_scene(x, y))

    def move(self, end, modifiers=Qt.NoModifier):
        viewport = self.editor.canvas.viewport()
        event = QMouseEvent(QEvent.MouseMove, QPointF(end), QPointF(viewport.mapToGlobal(end)),
                            Qt.NoButton, Qt.LeftButton, modifiers)
        QApplication.sendEvent(viewport, event)

    def drag(self, start, end, modifiers=Qt.NoModifier):
        viewport = self.editor.canvas.viewport()
        QTest.mousePress(viewport, Qt.LeftButton, modifiers, start)
        self.move(end, modifiers)
        QTest.mouseRelease(viewport, Qt.LeftButton, modifiers, end)
        self.app.processEvents()

    def test_real_window_and_crossing_select_different_edge_geometry_without_undo(self):
        before = copy.deepcopy(self.editor.store.data)
        self.drag(self.pixel(4, -1), self.pixel(6, 4))
        self.assertEqual({'N'}, self.editor.selected_point_names)
        self.assertEqual(set(), self.editor.selected_edge_keys)
        self.drag(self.pixel(6, -1), self.pixel(4, 4))
        self.assertEqual({'N'}, self.editor.selected_point_names)
        self.assertEqual({('A', 'B')}, self.editor.selected_edge_keys)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.assertNotIn(('point', 'OtherFloor'), editor_paths(self.editor))

    def test_shift_and_control_click_and_window_toggle_preserve_prior_selection(self):
        viewport = self.editor.canvas.viewport()
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(0, 0))
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.ShiftModifier, self.pixel(5, 3))
        self.assertEqual({'A', 'N'}, self.editor.selected_point_names)
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.ControlModifier, self.pixel(0, 0))
        self.assertEqual({'N'}, self.editor.selected_point_names)
        self.drag(self.pixel(4, 2), self.pixel(6, 4), Qt.ShiftModifier)
        self.assertEqual(set(), self.editor.selected_point_names)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_escape_cancels_rubberband_and_restores_prior_selection(self):
        self.editor.selected_point_names = {'A'}
        self.editor.selected_point_name = 'A'
        self.editor.refresh_canvas()
        viewport = self.editor.canvas.viewport()
        QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(4, -1))
        self.move(self.pixel(6, 4))
        self.assertIsNotNone(self.editor.canvas._cad_selection_overlay)
        QTest.keyClick(self.editor.canvas, Qt.Key_Escape, Qt.NoModifier)
        self.app.processEvents()
        QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(6, 4))
        self.assertEqual({'A'}, self.editor.selected_point_names)
        self.assertIsNone(self.editor.canvas._cad_selection_overlay)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_mode_and_floor_changes_clear_transient_selection(self):
        viewport = self.editor.canvas.viewport()
        for change in (lambda: self.editor._set_edit_mode('corridor_node'), lambda: self.editor.floor_spin.setValue(1)):
            self.editor._set_edit_mode('select_move')
            QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(4, -1))
            self.move(self.pixel(6, 4))
            change()
            self.assertIsNone(self.editor._cad_selection_gesture)
            self.assertIsNone(self.editor.canvas._cad_selection_overlay)
            QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(6, 4))

    def test_point_drag_remains_one_undo_and_click_does_not_open_properties(self):
        self.assertTrue(self.editor.workspace.properties.isHidden())
        self.drag(self.pixel(5, 3), self.pixel(7, 4))
        self.assertTrue(self.editor.workspace.properties.isHidden())
        self.assertAlmostEqual(7, self.editor.store.all_points()['N']['x'], places=1)
        self.assertAlmostEqual(4, self.editor.store.all_points()['N']['y'], places=1)
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual((5, 3), (self.editor.store.all_points()['N']['x'], self.editor.store.all_points()['N']['y']))

    def test_selected_nodes_and_corridor_move_together_as_one_undo(self):
        editor = self.editor
        editor.selected_point_names = {'N', 'OtherFloor'}
        editor.selected_edge_keys = {('A', 'B')}
        before = copy.deepcopy(editor.store.data)
        self.drag(self.pixel(5, 3), self.pixel(7, 4))
        points = editor.store.all_points()
        self.assertAlmostEqual(7, points['N']['x'], places=1)
        dx, dy = points['N']['x'] - 5, points['N']['y'] - 3
        self.assertAlmostEqual(dx, points['A']['x'])
        self.assertAlmostEqual(dy, points['A']['y'])
        self.assertAlmostEqual(10 + dx, points['B']['x'])
        self.assertEqual((5, 3), (points['OtherFloor']['x'], points['OtherFloor']['y']))
        self.assertEqual(before['corridors']['edges'], editor.store.data['corridors']['edges'])
        self.assertEqual({'N', 'OtherFloor'}, editor.selected_point_names)
        self.assertEqual({('A', 'B')}, editor.selected_edge_keys)
        self.assertEqual(2, len(editor.edit_history.entries))
        after = copy.deepcopy(editor.store.data)
        self.assertTrue(editor.undo_edit())
        self.assertEqual(before, editor.store.data)
        self.assertTrue(editor.redo_edit())
        self.assertEqual(after, editor.store.data)

    def test_corridor_can_be_dragged_from_its_line(self):
        before = copy.deepcopy(self.editor.store.data)
        self.drag(self.pixel(5, 0), self.pixel(6, 2))
        points = self.editor.store.all_points()
        self.assertAlmostEqual(1, points['A']['x'], places=1)
        self.assertAlmostEqual(2, points['A']['y'], places=1)
        self.assertAlmostEqual(10, points['B']['x'] - points['A']['x'])
        self.assertEqual((5, 3), (points['N']['x'], points['N']['y']))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)

    def test_group_drag_escape_and_floor_change_restore_without_history(self):
        editor = self.editor
        viewport = editor.canvas.viewport()
        before = copy.deepcopy(editor.store.data)
        for cancel in (lambda: QTest.keyClick(viewport, Qt.Key_Escape),
                       lambda: editor.floor_spin.setValue(1)):
            editor.floor_spin.setValue(0)
            editor.selected_point_names = {'A', 'N'}
            QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(5, 3))
            self.move(self.pixel(7, 4))
            self.assertNotEqual(before, editor.store.data)
            cancel()
            QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(7, 4))
            self.assertEqual(before, editor.store.data)
            self.assertEqual(1, len(editor.edit_history.entries))
            self.assertFalse(editor.drag_mode_active)

    def test_group_grid_uses_anchor_offset_and_preserves_room_shape_and_precision(self):
        editor = self.editor
        editor.store.data['locations'].append({'name':'Room', 'floor':0, 'x':2.123456, 'y':8.654321,
            'bounding_box':[{'dx':-1,'dy':-1}, {'dx':1,'dy':-1}, {'dx':1,'dy':1}]})
        editor._reset_edit_history()
        editor.refresh_canvas()
        editor.selected_point_names = {'N', 'Room'}
        editor.snap_check.setChecked(True)
        editor.grid_spacing_spin.setValue(.5)
        shape = copy.deepcopy(editor.store.get_location('Room')['bounding_box'])
        self.drag(self.pixel(5, 3), self.pixel(6.6, 3.6))
        room = editor.store.get_location('Room')
        self.assertAlmostEqual(3.623456, room['x'])
        self.assertAlmostEqual(9.154321, room['y'])
        self.assertEqual(shape, room['bounding_box'])
        self.assertEqual(2, len(editor.edit_history.entries))

    def test_point_click_tolerance_is_constant_screen_distance_at_two_zooms(self):
        viewport = self.editor.canvas.viewport()
        for zoom in (10, 50):
            self.editor.canvas.resetTransform()
            self.editor.canvas.scale(zoom, zoom)
            self.editor.canvas.centerOn(5, -1)
            self.editor.clear_topology_selection()
            shape = editor_paths(self.editor)[('point', 'N')].boundingRect()
            near = QPointF(shape.right()+4, shape.center().y()).toPoint()
            QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, near)
            self.assertEqual({'N'}, self.editor.selected_point_names)
            self.editor.clear_topology_selection()
            far = QPointF(shape.right()+10, shape.center().y()).toPoint()
            QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, far)
            self.assertEqual(set(), self.editor.selected_point_names)

    def test_unregistered_underlay_geometry_cannot_be_selected(self):
        self.editor.scene.addRect(QRectF(3, -2, 4, 1))
        before = set(editor_paths(self.editor))
        self.drag(self.pixel(2, .5), self.pixel(8, 2.5))
        self.assertEqual(set(), self.editor.selected_point_names)
        self.assertEqual(set(), self.editor.selected_edge_keys)
        self.assertEqual(before, set(editor_paths(self.editor)))

    def test_visible_location_boundary_is_part_of_its_selection_geometry(self):
        self.editor.store.data['locations'].append({'name': 'Room', 'floor': 0, 'x': 5, 'y': 5,
            'bounding_box': [{'dx': -2, 'dy': -1}, {'dx': 2, 'dy': -1},
                             {'dx': 2, 'dy': 2}, {'dx': -2, 'dy': 2}]})
        self.editor.show_location_bounds_check.setChecked(True)
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.drag(self.pixel(2, 3), self.pixel(6, 8))
        self.assertNotIn('Room', self.editor.selected_point_names)
        self.drag(self.pixel(8, 3), self.pixel(6, 8))
        self.assertIn('Room', self.editor.selected_point_names)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_dragging_room_away_from_centre_preserves_anchor_and_one_undo(self):
        self.editor.store.data['locations'].append({'name': 'Room', 'floor': 0, 'x': 5, 'y': 5,
            'bounding_box': [{'dx': -2, 'dy': -1}, {'dx': 2, 'dy': -1},
                             {'dx': 2, 'dy': 2}, {'dx': -2, 'dy': 2}]})
        self.editor.show_location_bounds_check.setChecked(True)
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        original_outline = copy.deepcopy(self.editor.store.get_location('Room')['bounding_box'])
        self.drag(self.pixel(4, 6), self.pixel(5, 6))
        room = self.editor.store.get_location('Room')
        self.assertEqual((6, 5), (room['x'], room['y']))
        self.assertEqual(original_outline, room['bounding_box'])
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertIsNone(self.editor._cad_drag_offset)
        self.assertTrue(self.editor.undo_edit())
        room = self.editor.store.get_location('Room')
        self.assertEqual((5, 5), (room['x'], room['y']))
        self.editor.snap_check.setChecked(True)
        self.drag(self.pixel(4, 6), self.pixel(5.4, 6.2))
        room = self.editor.store.get_location('Room')
        self.assertEqual((6, 5), (room['x'], room['y']))
        self.assertEqual(2, len(self.editor.edit_history.entries))

    def test_mode_and_floor_changes_clear_point_drag_anchor(self):
        viewport = self.editor.canvas.viewport()
        for change in (lambda: self.editor._set_edit_mode('corridor_node'), lambda: self.editor.floor_spin.setValue(1)):
            self.editor._set_edit_mode('select_move')
            QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(5.2, 3))
            self.assertIsNotNone(self.editor._cad_drag_offset)
            change()
            self.assertIsNone(self.editor._cad_drag_offset)
            self.assertFalse(self.editor.drag_mode_active)
            self.assertIsNone(self.editor.dragging_point_name)
            QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, self.pixel(5.2, 3))


if __name__ == '__main__':
    unittest.main()
