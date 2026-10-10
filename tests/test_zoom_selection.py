"""Selection extents exclude underlays and preserve editing state."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QWheelEvent


class ZoomSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        if hasattr(self.editor, 'project_runs_panel'):
            del self.editor.project_runs_panel
        editing.CorridorEditingUiTests.tearDown(self)

    def test_edges_include_active_floor_endpoints_with_world_to_scene_y_flip(self):
        self.editor.selected_edge_keys = {('A','Door')}
        self.assertEqual(QRectF(-1,-5,5,6), self.editor.selection_view_rect())
        self.editor.store.data['corridors']['nodes'].append(dict(name='Other', floor=1, x=10000, y=10000))
        self.editor.selected_point_names = {'Other', 'Missing'}
        self.assertEqual(QRectF(-1,-5,5,6), self.editor.selection_view_rect())

    def test_location_boundary_and_single_point_extents_are_finite(self):
        self.editor.selected_point_name = 'A'
        self.assertEqual(QRectF(-1,-1,2,2), self.editor.selection_view_rect())
        self.editor.store.set_location_bounding_box('A',
            [dict(x=-3,y=-2),dict(x=5,y=-2),dict(x=5,y=4),dict(x=-3,y=4)])
        self.assertEqual(QRectF(-4,-5,10,8), self.editor.selection_view_rect())

    def test_zoom_is_view_only_without_scene_rebuild_or_underlay_load(self):
        self.editor.selected_point_name = 'A'
        self.editor.scene.addRect(-10000,-10000,20000,20000)
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        self.editor.project_runs_panel = SimpleNamespace(running=lambda: True)
        with patch.object(self.editor, 'refresh_canvas', side_effect=AssertionError('Scene rebuilt')), \
             patch.object(self.editor, 'ensure_floor_dxf_loaded', side_effect=AssertionError('Underlay loaded')):
            self.assertTrue(self.editor.fit_selection())
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, self.editor.edit_history.entries)
        self.assertEqual('A', self.editor.selected_point_name)
        self.assertGreater(self.editor.canvas.transform().m11(), 1)

    def test_empty_stale_and_invalid_selection_leave_view_unchanged(self):
        before = self.editor.canvas.transform()
        for selected in (None, 'Missing'):
            self.editor.selected_point_name = selected
            self.assertFalse(self.editor.fit_selection())
        self.editor.selected_point_name = 'A'
        self.editor.store.get_location('A')['x'] = float('nan')
        self.assertFalse(self.editor.fit_selection())
        self.assertIn('finite', self.editor.status_label.text())
        self.assertEqual(before, self.editor.canvas.transform())
        self.editor.store.get_location('A')['x'] = 0

    def test_cursor_wheel_zoom_preserves_model_selection_and_history(self):
        self.editor.resize(1280, 900)
        self.editor.show()
        self.app.processEvents()
        self.editor.selected_point_name = 'A'
        self.editor.fit_view()
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        view = self.editor.canvas
        position = QPointF(view.viewport().width() * .75, view.viewport().height() * .25)
        inverse, _ = view.viewportTransform().inverted()
        target = inverse.map(position)
        event = QWheelEvent(position, QPointF(view.viewport().mapToGlobal(position.toPoint())),
                            QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        with patch.object(self.editor, 'refresh_canvas', side_effect=AssertionError('Scene rebuilt')), \
             patch.object(self.editor, 'ensure_floor_dxf_loaded', side_effect=AssertionError('Underlay loaded')):
            self.app.sendEvent(view.viewport(), event)
        actual = view.viewportTransform().map(target)
        self.assertLessEqual(abs(actual.x() - position.x()), 1.1)
        self.assertLessEqual(abs(actual.y() - position.y()), 1.1)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, self.editor.edit_history.entries)
        self.assertEqual('A', self.editor.selected_point_name)
