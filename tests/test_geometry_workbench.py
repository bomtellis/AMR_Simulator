import copy
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from visualiser.geometry_workbench import GeometryWorkbench, EXAMPLE, validate_study


class GeometryWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = GeometryWorkbench()

    def tearDown(self):
        self.window.close()

    def test_reference_shares_geometry_timing_and_clearance(self):
        w = self.window
        self.assertAlmostEqual(8 + math.pi, w.trajectory.length_m)
        self.assertAlmostEqual(w.trajectory.length_m, w.trajectory.duration_sec)
        self.assertEqual('clear', w.clearance_result['status'])
        self.assertFalse(w.properties.isVisible())
        self.assertFalse(w.guide.isVisible())
        exported = w.export_data()
        self.assertEqual(w.trajectory.to_dict(), exported['trajectory'])
        self.assertIn('no traffic', exported['scope'])

    def test_draw_finish_undo_redo_is_one_operation(self):
        w = self.window
        w.begin_drawing('route')
        for point in [[0,0], [1,0], [1,1]]:
            w.add_point(point)
        self.assertEqual(EXAMPLE['points'], w.study['points'])
        w.finish_drawing()
        self.assertEqual([[0,0], [1,0], [1,1]], w.study['points'])
        self.assertIsNone(w.trajectory)
        self.assertIn('infeasible_route', w.statusBar().currentMessage())
        self.assertEqual(1, w.undo_stack.count())
        w.undo_stack.undo()
        self.assertEqual(EXAMPLE['points'], w.study['points'])
        w.undo_stack.redo()
        self.assertIsNone(w.trajectory)
        w.pivots.setChecked(True)
        self.assertAlmostEqual(4, w.trajectory.duration_sec)
        self.assertEqual(['line','pivot','line'], [m.kind for m in w.trajectory.motions])

    def test_escape_cancels_draft_without_mutating_saved_study(self):
        w = self.window
        before = w.export_data()
        w.begin_drawing('route')
        w.add_point([20,20])
        QTest.keyClick(w.canvas, Qt.Key_Escape)
        self.assertEqual(before, w.export_data())
        self.assertEqual(0, w.undo_stack.count())

    def test_typed_points_and_enter_finish(self):
        w = self.window
        w.begin_drawing('route')
        for text in ['0,0', '3,4']:
            w.position_input.setText(text)
            QTest.keyClick(w.position_input, Qt.Key_Return)
        QTest.keyClick(w.canvas, Qt.Key_Return)
        self.assertEqual([[0,0],[3,4]], w.study['points'])
        self.assertAlmostEqual(5, w.trajectory.length_m)

    def test_obstacle_edit_has_real_clearance_effect_and_undo(self):
        w = self.window
        w.begin_drawing('obstacle')
        w.add_point([1,-1])
        w.add_point([1.2,1])
        self.assertEqual('collision', w.clearance_result['status'])
        w.undo_stack.undo()
        self.assertEqual('clear', w.clearance_result['status'])

    def test_load_width_changes_opening_result_without_losing_original(self):
        w = self.window
        w.controls['payload_width_m'].setValue(1.01)
        w.apply_parameters()
        self.assertEqual('collision', w.clearance_result['status'])
        w.undo_stack.undo()
        self.assertEqual('clear', w.clearance_result['status'])

    def test_save_reopen_recomputes_evidence_and_retains_infeasible_study(self):
        w = self.window
        w.begin_drawing('route')
        for point in [[0,0],[1,0],[1,1]]:
            w.add_point(point)
        w.finish_drawing()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'study.json')
            with patch('visualiser.geometry_workbench.QFileDialog.getSaveFileName', return_value=(path,'')):
                w.save_study()
            value = json.loads(Path(path).read_text())
            self.assertIsNone(value['trajectory'])
            self.assertEqual(w.study, validate_study(value))
            w.load_example()
            # Supplied results are untrusted; only inputs are used on reopening.
            value['trajectory'] = {'length_m': 999}
            Path(path).write_text(json.dumps(value))
            with patch('visualiser.geometry_workbench.QFileDialog.getOpenFileName', return_value=(path,'')):
                w.open_study()
            self.assertIsNone(w.trajectory)
            self.assertIn('infeasible_route', w.statusBar().currentMessage())

    def test_invalid_import_does_not_replace_current_study(self):
        w = self.window
        before = copy.deepcopy(w.study)
        invalid = copy.deepcopy(EXAMPLE)
        invalid['parameters']['robot_width_m'] = -1
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'invalid.json')
            Path(path).write_text(json.dumps(invalid))
            with patch('visualiser.geometry_workbench.QFileDialog.getOpenFileName', return_value=(path,'')), \
                 patch('visualiser.geometry_workbench.QMessageBox.warning') as warning:
                w.open_study()
                warning.assert_called_once()
        self.assertEqual(before, w.study)


if __name__ == '__main__':
    unittest.main()
