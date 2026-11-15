"""Check section totals and the Report panel's saved-run generation path."""
import json
import unittest

import pandas as pd
from pypdf import PdfReader
from PySide6.QtCore import QEventLoop, QTimer, Qt

from report.amr_report_analysis import build_lift_movements_by_level
from tests import test_lift_movement_charts_ui as charts_ui


class LiftMovementLevelTests(unittest.TestCase):
    def test_crossings_count_in_both_directions_and_keep_zero_activity_levels(self):
        movements = pd.DataFrame([
            ('L-01', 'L02'), ('L02', 'L00'), ('L00', 'L01'),
            ('L-01', 'Unknown'), ('L01', 'L01'),
        ], columns=['origin_level', 'destination_level'])
        levels, excluded = build_lift_movements_by_level(movements, {'building': {'floor_count': 4}})
        self.assertEqual([
            ('L03', 0, 0, 0, 0),
            ('L02', 1, 1, 0, 2),
            ('L01', 1, 0, 2, 3),
            ('L00', 1, 1, 1, 3),
            ('L-01', 0, 1, 0, 1),
        ], list(levels.itertuples(index=False, name=None)))
        self.assertEqual(2, excluded)


class LiftMovementLevelReportTests(unittest.TestCase):
    setUpClass = classmethod(charts_ui.LiftMovementChartUiTests.setUpClass.__func__)
    setUp = charts_ui.LiftMovementChartUiTests.setUp
    tearDown = charts_ui.LiftMovementChartUiTests.tearDown
    panel = charts_ui.LiftMovementChartUiTests.panel

    def test_report_panel_defaults_to_checked_and_generates_from_the_selected_run(self):
        panel = self.panel()
        self.editor.store.data['lifts'] = []
        section_id = 'lift_movements_by_level'
        for index in range(panel.sections.count()):
            item = panel.sections.item(index)
            if item.data(Qt.UserRole) == section_id:
                self.assertEqual('Lift movements by level', item.text())
                self.assertEqual(Qt.Checked, item.checkState())
            else:
                item.setCheckState(Qt.Unchecked)

        panel.generate()
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if not panel.running() else None)
        timer.start(20)
        QTimer.singleShot(60000, loop.quit)
        loop.exec()
        timer.stop()
        if panel.running():
            panel.cancel()
            self.fail('PDF generation did not complete within one minute.')
        self.assertIsNotNone(panel.pdf, panel.log.toPlainText())
        manifest = json.loads((panel.output / 'report_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual('complete', manifest['status'])
        self.assertEqual([section_id], manifest['sections'])
        reader = PdfReader(panel.pdf)
        self.assertEqual(3, len(reader.pages))
        page = reader.pages[-1].extract_text()
        self.assertIn('Lift movements by level', page)
        self.assertIn('Total movements', page)
        self.assertIn('L01\n0\n0\n1\n1', page)
