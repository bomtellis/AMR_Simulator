"""The A2 demonstration uses real project geometry and application symbols."""
import contextlib
import io
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent
from verification.cad_preview import reference_project
from simulator import Simulation
from cad_visual_style import icon


class CadConceptReferenceTests(unittest.TestCase):
    def test_sample_routes_have_independent_lengths_and_outcomes(self):
        config = reference_project()
        with contextlib.redirect_stdout(io.StringIO()):
            simulation = Simulation(config)
            simulation.run()
        self.assertFalse(simulation.failed_task_ids)
        rows = {r['task_id']: r for r in simulation.completed_task_records}
        # Stores to Ward: 2+1+8+8+1+2 = 22 m, at 2 m/s + 4 s handling.
        # Ward to Waste: 2+1+8+6+1+2 = 20 m, at 2 m/s + 4 s handling.
        self.assertAlmostEqual(15, rows['DELIVERY']['duration_sec'])
        self.assertAlmostEqual(14, rows['COLLECTION']['duration_sec'])
        self.assertEqual(2, len(rows))


class CadConceptIconTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def test_native_symbols_are_visible_at_toolbar_size_on_light_and_dark(self):
        for colour in ('#17335a', '#ffffff'):
            for name in ('save', 'undo', 'redo', 'select', 'corridor', 'node', 'location',
                         'door', 'project', 'configuration', 'checks', 'review', 'report',
                         'help', 'layout', 'simulate', 'fit', 'focus', 'properties', 'tree', 'more'):
                with self.subTest(name=name, colour=colour):
                    image = icon(name, colour).pixmap(24, 24).toImage()
                    visible = sum(image.pixelColor(x, y).alpha() > 100
                                  for x in range(24) for y in range(24))
                    self.assertGreater(visible, 8)
                    self.assertLess(visible, 450)


class CadConceptFramingTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        editing.CorridorEditingUiTests.tearDown(self)

    def test_fit_includes_real_outlines_and_uses_available_graph_space(self):
        editor = self.editor
        editor.store = editing.JsonStore(reference_project())
        editor.show_location_bounds_check.setChecked(True)
        editor.resize(1500, 900)
        editor.show()
        editor.refresh_canvas()
        self.app.processEvents()
        self.assertEqual((0, -8, 24, 8), editor._content_bounds(0))
        editor.fit_view()
        self.app.processEvents()
        viewport = editor.canvas.viewport().rect()
        top_left = editor.canvas.mapFromScene(editor.world_to_scene(0, 8))
        bottom_right = editor.canvas.mapFromScene(editor.world_to_scene(24, -8))
        self.assertTrue(viewport.contains(top_left))
        self.assertTrue(viewport.contains(bottom_right))
        self.assertGreater(bottom_right.y()-top_left.y(), viewport.height()*.6)
        editor.show_location_bounds_check.setChecked(False)
        self.assertEqual((4, -6, 20, 6), editor._content_bounds(0))


if __name__ == '__main__':
    unittest.main()
