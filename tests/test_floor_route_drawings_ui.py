"""The floor drawing command uses the chosen run and applied filters."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialogButtonBox

from amr_route_analysis import Filters, RunAnalysis
from visualiser.route_analysis_panel import RouteAnalysisPanel


class FloorDrawingDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_export_dialog_uses_run_b_and_current_applied_window(self):
        panel = RouteAnalysisPanel()
        self.addCleanup(panel.close)
        run_a = RunAnalysis('a.sqlite', 'a', metadata={'run_id': 'Baseline'})
        run_b = RunAnalysis('b.sqlite', 'b', metadata={'run_id': 'Comparison'})
        filters = Filters(start=10, end=50, floor=2, amr='AMR-1')
        panel.result = {'sides': [{'run': run_a}, {'run': run_b}], 'filters': filters}
        defaults = []

        def pick_run_b():
            dialog = QApplication.activeModalWidget()
            run = dialog.findChild(QComboBox)
            run.setCurrentIndex(1)
            pick = {checkbox.text(): checkbox for checkbox in dialog.findChildren(QCheckBox)}
            defaults.extend((checkbox.text(), checkbox.isChecked()) for checkbox in pick.values())
            pick['Include recorded plans'].setChecked(True)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()

        with TemporaryDirectory() as output, patch.object(panel, '_start') as start, patch(
            'visualiser.route_analysis_panel.QFileDialog.getExistingDirectory', return_value=output
        ), patch('visualiser.floor_route_export.export_floor_route_drawings') as export:
            QTimer.singleShot(0, pick_run_b)
            panel.export_floor_drawings()
            self.assertEqual([('PDF · one scaled A1 sheet per floor', True), ('DXF · editable layers by payload type', True),
                              ('Include recorded plans', False)], defaults)
            start.assert_called_once()
            slot, operation = start.call_args.args
            self.assertEqual('floor drawings', slot)
            operation(None, None)
            selected, applied, destination = export.call_args.args
            self.assertIs(selected, run_b)
            self.assertEqual(filters, applied)
            self.assertEqual(Path(output), destination.parent)
            self.assertTrue(export.call_args.kwargs['include_plans'])
