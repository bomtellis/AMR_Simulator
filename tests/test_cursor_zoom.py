"""Wheel events anchor the graph without relying on prior mouse movement."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QGraphicsScene
from app import AMRGraphEditor, EditorGraphicsView
from amr_sim_visualiser_pyside6 import GraphicsView


class CursorZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wheel(self, view, position, delta):
        event = QWheelEvent(position, QPointF(view.viewport().mapToGlobal(position.toPoint())),
                            QPoint(), delta, Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        QApplication.sendEvent(view.viewport(), event)

    def test_editor_and_playback_anchor_actual_event_position_in_both_directions(self):
        for kind in ('editor', 'playback'):
            for small_scene in (False, True):
                with self.subTest(kind=kind, small_scene=small_scene):
                    view = (EditorGraphicsView() if kind == 'editor'
                            else GraphicsView(use_opengl=False))
                    if kind == 'editor':
                        # Exercise the editor's real connected wheel handler.
                        editor = SimpleNamespace(canvas=view)
                        view.mouseWheelScrolled.connect(
                            lambda event, editor=editor: AMRGraphEditor.on_mousewheel(editor, event))
                    scene = QGraphicsScene(view)
                    item = scene.addRect(-50, -30, 100, 60)
                    if small_scene:
                        scene.setSceneRect(-50, -30, 100, 60)
                    else:
                        scene.setSceneRect(-5000, -5000, 10000, 10000)
                    view.setScene(scene)
                    view.resize(800, 600)
                    view.show()
                    self.app.processEvents()
                    try:
                        for position, delta in ((QPointF(115.25, 95.75), 120),
                                                (QPointF(685.75, 475.25), -120),
                                                (QPointF(40, 40), 120),
                                                (QPointF(740, 530), -120)):
                            inverse, _ = view.viewportTransform().inverted()
                            target = inverse.map(position)
                            scale = view.transform().m11()
                            # No mouse move is sent; the last hover must be irrelevant.
                            self.wheel(view, position, QPoint(0, delta))
                            actual = view.viewportTransform().map(target)
                            self.assertLessEqual(abs(actual.x() - position.x()), 1.1)
                            self.assertLessEqual(abs(actual.y() - position.y()), 1.1)
                            self.assertAlmostEqual(scale * (1.1 if delta > 0 else .9),
                                                   view.transform().m11())
                        self.assertEqual([item], scene.items())
                    finally:
                        view.close()
                        view.deleteLater()
                        self.app.processEvents()

    def test_horizontal_wheel_does_not_zoom_or_notify_playback(self):
        view = GraphicsView(use_opengl=False)
        view.setScene(QGraphicsScene(view))
        callbacks = []
        view.set_callbacks(zoom_callback=lambda: callbacks.append(True))
        before = view.transform()
        self.wheel(view, QPointF(100, 100), QPoint(120, 0))
        self.assertEqual(before, view.transform())
        self.assertEqual([], callbacks)
        self.wheel(view, QPointF(100, 100), QPoint(0, 120))
        self.assertEqual([True], callbacks)
        view.deleteLater()
