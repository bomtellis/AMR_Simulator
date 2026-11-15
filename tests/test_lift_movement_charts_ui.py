"""Background exports and PDF controls use a selected run's frozen inputs."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from tests import test_lift_integration_ui as ui
from tests.test_lift_integration import direct_config
from amr_project import Project
from amr_project_runs import PreparedRun,execute
from visualiser.project_checks import check_project
from visualiser.project_report_panel import ProjectReportPanel
from PySide6.QtCore import Qt,QEventLoop,QTimer
from PySide6.QtWidgets import QFileDialog
from models import JsonStore


class LiftMovementChartUiTests(unittest.TestCase):
    setUpClass=classmethod(ui.LiftRoutingEditorTests.setUpClass.__func__)
    setUp=ui.LiftRoutingEditorTests.setUp
    tearDown=ui.LiftRoutingEditorTests.tearDown

    def panel(self):
        cfg=direct_config();cfg['tasks']=[dict(id='GEN_CATERING_T1',pickup='A',dropoff='B3',payload='Box')]
        project=Project();project.save(Path(self.temp.name)/'chart-project.amrproj',cfg)
        prepared=PreparedRun(project,Path(self.temp.name)/'runs')
        checks=check_project(prepared.config);checks.acknowledge_warnings();directory=prepared.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):execute(directory)
        self.editor.project=project;self.editor.store=JsonStore(cfg)
        panel=ProjectReportPanel(self.editor);panel.set_run(directory)
        return panel

    def test_export_runs_in_background_and_uses_frozen_run(self):
        panel=self.panel();target=Path(self.temp.name)/'charts.xlsx'
        self.editor.store.data['lifts']=[]
        panel.lift_chart_day.setCurrentText('2026-01-05')
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
            panel.generate_lift_charts()
        self.assertTrue(panel.running());self.assertFalse(panel.export_lift_charts.isEnabled())
        loop=QEventLoop();timer=QTimer();timer.setInterval(20)
        timer.timeout.connect(lambda:loop.quit() if not panel.running() else None)
        timer.start();QTimer.singleShot(60000,loop.quit);loop.exec();timer.stop()
        if panel.running():panel.cancel();self.fail('Chart export did not complete within one minute.')
        self.assertTrue(target.exists(),panel.log.toPlainText())
        self.assertEqual(target,panel.lift_csv);self.assertTrue(panel.open_lift_csv.isEnabled())
        self.assertTrue(panel.export_lift_charts.isEnabled())
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(1,len([n for n in archive.namelist() if '/charts/chart' in n and n.endswith('.xml')]))

    def test_cancelled_file_choice_starts_no_worker(self):
        panel=self.panel()
        with patch.object(QFileDialog,'getSaveFileName',return_value=('','')):
            panel.generate_lift_charts()
        self.assertFalse(panel.running());self.assertIsNone(panel.lift_charts_target)

    def test_cancelled_worker_retains_existing_output(self):
        panel=self.panel();target=Path(self.temp.name)/'charts.xlsx'
        target.write_bytes(b'previous completed workbook')
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
            panel.generate_lift_charts()
        panel.cancel()
        loop=QEventLoop();timer=QTimer();timer.setInterval(20)
        timer.timeout.connect(lambda:loop.quit() if not panel.running() else None)
        timer.start();QTimer.singleShot(10000,loop.quit);loop.exec();timer.stop()
        self.assertFalse(panel.running());self.assertIsNone(panel.lift_charts_target)
        self.assertEqual(b'previous completed workbook',target.read_bytes())
        self.assertIn('stopped or failed',panel.log.toPlainText())
        self.assertFalse(panel.open_lift_csv.isEnabled())

    def test_pdf_option_is_opt_in_and_filter_settings_reach_worker(self):
        panel=self.panel()
        for index in range(panel.sections.count()):
            item=panel.sections.item(index)
            if item.data(Qt.UserRole)=='lift_movement_stacks':self.assertEqual(Qt.Unchecked,item.checkState())
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole)=='lift_movement_stacks' else Qt.Unchecked)
        panel.lift_chart_day.setCurrentText('2026-01-05')
        panel.lift_chart_interval.setCurrentIndex(panel.lift_chart_interval.findData(60))
        panel.lift_chart_include.setChecked(False)
        with patch('visualiser.project_report_panel.QProcess') as process:
            panel.generate()
            args=process.return_value.start.call_args.args[1]
            self.assertIn('lift_movement_stacks',args)
            self.assertEqual('2026-01-05',args[args.index('--lift-chart-day')+1])
            self.assertEqual('60',args[args.index('--lift-chart-bin-minutes')+1])
            self.assertIn('--lift-chart-exclude-reposition',args)
        panel.process=None


if __name__=='__main__':unittest.main()
