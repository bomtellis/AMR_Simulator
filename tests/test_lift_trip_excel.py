"""Combined trip table, live formulas and evidence-preserving export."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from amr_third_party_lift import export_lift_trips_xlsx, lift_trip_workbook_data, recorded_events
from tests import test_all_lifts_export as batch

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def saved_cells(path):
    with ZipFile(path) as archive:
        strings = ET.fromstring(archive.read('xl/sharedStrings.xml')) if 'xl/sharedStrings.xml' in archive.namelist() else None
        shared = [''.join(s.itertext()) for s in strings] if strings is not None else []
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        cells = {}
        for c in sheet.findall('.//m:sheetData/m:row/m:c', NS):
            value = c.find('m:v', NS)
            text = value.text if value is not None else ''
            if c.get('t') == 's':
                text = shared[int(text)]
            elif c.get('t') == 'inlineStr':
                text = ''.join(c.find('m:is', NS).itertext())
            cells[c.get('r')] = (text, c.findtext('m:f', default='', namespaces=NS), c.get('t'))
        tables = [ET.fromstring(archive.read(n)) for n in archive.namelist() if n.startswith('xl/tables/table') and n.endswith('.xml')]
    return cells, sheet, tables


class LiftTripExcelTests(unittest.TestCase):
    def source(self, folder, identities=('Lift-A', 'Lift-B', 'Unused')):
        return batch.AllLiftExportTests().source(folder, identities)

    def test_data_has_every_trip_full_detail_and_separate_import_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            config = json.loads(Path(str(source) + '.run.json').read_text())['frozen_inputs']
            frozen = Path(folder) / 'config.json'
            frozen.write_text(json.dumps(config))
            rows = list(recorded_events(source))
            for row in rows:
                row.update(duration_sec='17.5', amr_id='AMR-A', task_id='T1,T2', payload_weight_kg='125', amr_weight_kg='250')
            data = lift_trip_workbook_data(rows, config, frozen)
            self.assertEqual(3, len(data['rows']))
            self.assertEqual('concatenated', data['headers'][-1])
            self.assertEqual(30, len(data['headers']))
            self.assertEqual(['Lift-A', 'Lift-A', 'Lift-B'], [r[1] for r in data['rows']])
            self.assertEqual(['lift_reposition', 'lift_transfer', 'lift_transfer'], [r[2] for r in data['rows']])
            self.assertEqual([50, 3, 1, 1500, 60, '0,0', 2], data['rows'][0][22:])
            self.assertEqual([101, 1, 3, 1500, 60, '31,31', 2], data['rows'][1][22:])
            self.assertEqual([17.5, 125, 250], [data['rows'][1][i] for i in (9, 16, 17)])
            self.assertEqual(0, data['lifts'][-1]['trips'])

    def test_export_has_native_table_numeric_fields_and_formula_on_every_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            before = source.read_bytes()
            target = Path(folder) / 'trips.xlsx'
            self.assertEqual({'Lift-A': 2, 'Lift-B': 1, 'Unused': 0}, export_lift_trips_xlsx(source, target))
            cells, sheet, tables = saved_cells(target)
            table = next(t for t in tables if t.get('name') == 'LiftTrips')
            self.assertEqual('A5:AD8', table.get('ref'))
            self.assertIsNotNone(table.find('m:autoFilter', NS))
            self.assertEqual('concatenated', cells['AD5'][0])
            for row, expected in [(6, '50,3,1,1500,60,0,0,2'), (7, '101,1,3,1500,60,31,31,2'), (8, '102,1,3,1500,60,31,31,2')]:
                self.assertEqual(expected, cells[f'AD{row}'][0])
                self.assertIn(f'TEXT(W{row},"0")', cells[f'AD{row}'][1])
                self.assertIn(f'AB{row}', cells[f'AD{row}'][1])
                self.assertNotIn(cells[f'W{row}'][2], ('s', 'inlineStr'))
            self.assertIsNotNone(sheet.find('.//m:pane', NS))
            self.assertEqual(before, source.read_bytes())

    def test_empty_trips_still_exports_a_table_and_every_configured_lift(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            with patch('amr_third_party_lift.recorded_events', return_value=iter([])):
                target = Path(folder) / 'empty.xlsx'
                self.assertEqual({'Lift-A': 0, 'Lift-B': 0, 'Unused': 0}, export_lift_trips_xlsx(source, target))
            cells, _, tables = saved_cells(target)
            self.assertEqual('concatenated', cells['AD5'][0])
            self.assertEqual('A5:AD6', next(t for t in tables if t.get('name') == 'LiftTrips').get('ref'))
            self.assertFalse(cells.get('AD6', ('', ''))[1])

    def test_failed_writer_and_changed_evidence_retain_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'trips.xlsx'
            target.write_bytes(b'previous')
            with patch('amr_third_party_lift.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'writer failed')):
                with self.assertRaisesRegex(RuntimeError, 'writer failed'):
                    export_lift_trips_xlsx(source, target)
            self.assertEqual(b'previous', target.read_bytes())
            original = lift_trip_workbook_data
            def change(*args, **kwargs):
                result = original(*args, **kwargs)
                sidecar = Path(str(source) + '.run.json')
                sidecar.write_text(sidecar.read_text() + ' ')
                return result
            with patch('amr_third_party_lift.lift_trip_workbook_data', side_effect=change):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    export_lift_trips_xlsx(source, target)
            self.assertEqual(b'previous', target.read_bytes())
            self.assertEqual([], list(Path(folder).glob('.lift-trips-*')))

    def test_all_three_cli_entry_points_export_excel_without_pdf(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            for index, script in enumerate(('amr_app.py', 'amr_third_party_lift.py', 'report/amr_report_main.py')):
                target = Path(folder) / f'trips-{index}.xlsx'
                result = subprocess.run([sys.executable, str(root / script), str(source), '--third-party-lift-xlsx', str(target)], capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(target.is_file())
            self.assertEqual([], list(Path(folder).glob('*.pdf')))

    def test_rejects_mixed_outputs_and_unknown_lift(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'trips.xlsx'
            for extra in (['--lift-id', 'Lift-A'], ['--third-party-lift-csv', str(Path(folder) / 'trips.csv')], ['--third-party-lifts-dir', str(Path(folder) / 'all')]):
                result = subprocess.run([sys.executable, str(root / 'amr_app.py'), str(source), '--third-party-lift-xlsx', str(target), *extra], capture_output=True, text=True)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(target.exists())

    def test_fractional_transfer_times_negative_floors_and_datetime_remain_paired(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            config = json.loads(Path(str(source) + '.run.json').read_text())['frozen_inputs']
            frozen = Path(folder) / 'frozen.json'
            frozen.write_text(json.dumps(config))
            rows = list(recorded_events(source))
            detail = json.loads(rows[0]['details'])
            detail.update(entry_start_sec=110, entry_time_sec=.123456, exit_time_sec=2.5)
            detail['from'] = 'Lift-A-F-2'
            rows[0].update(details=json.dumps(detail), timestamp='2026-11-09 00:01:38', duration_sec='10')
            rows[1].update(timestamp='2026-11-09 00:01:39', duration_sec='12')
            rows[2].update(timestamp='2026-11-09 00:00:50', duration_sec='13')
            data = lift_trip_workbook_data(rows, config, frozen)
            self.assertEqual('datetime', data['time_kind'])
            self.assertEqual(['Lift-A', 'Lift-B', 'Lift-A'], [r[1] for r in data['rows']])
            self.assertEqual('2026-11-09T00:01:38', data['rows'][-1][5])
            self.assertEqual([110, -1, 3, 1500, 60, '0.123,2.5', 2], data['rows'][-1][22:])


class LiftTripExcelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_lift_integration_ui import LiftRoutingEditorTests
        LiftRoutingEditorTests.setUpClass.__func__(cls)

    def setUp(self):
        from tests.test_lift_integration_ui import LiftRoutingEditorTests
        LiftRoutingEditorTests.setUp(self)

    def tearDown(self):
        from tests.test_lift_integration_ui import LiftRoutingEditorTests
        LiftRoutingEditorTests.tearDown(self)

    @staticmethod
    def select_excel(dialog):
        from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog
        combo = dialog.findChild(QComboBox)
        for i in range(combo.count()):
            if '.xlsx' in combo.itemText(i):
                combo.setCurrentIndex(i)
                break
        include = dialog.findChild(QCheckBox)
        if not include.isChecked() or include.isEnabled():
            raise AssertionError('Excel must include all empty reposition trips.')
        return QDialog.Accepted

    def test_background_excel_uses_saved_run_and_opens_workbook(self):
        import contextlib
        import io
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QDialog, QFileDialog
        from amr_project import Project
        from amr_project_runs import PreparedRun, execute
        from tests.test_lift_integration import two_lifts
        from visualiser.project_checks import check_project
        from visualiser.project_report_panel import ProjectReportPanel
        from models import JsonStore
        cfg = two_lifts()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B3', payload='Box')]
        project = Project()
        project.save(Path(self.temp.name) / 'model.amrproj', cfg)
        prepared = PreparedRun(project, Path(self.temp.name) / 'results')
        checks = check_project(prepared.config)
        checks.acknowledge_warnings()
        directory = prepared.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        self.editor.project = project
        self.editor.store = JsonStore(cfg)
        panel = ProjectReportPanel(self.editor)
        panel.set_run(directory)
        self.editor.store.data['lifts'].clear()
        target = Path(self.temp.name) / 'gui-lifts.xlsx'
        with patch.object(QDialog, 'exec', new=self.select_excel), patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            panel.generate_third_party()
        self.assertTrue(panel.third_party_excel)
        self.assertFalse(panel.third_party_all)
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        panel.process.finished.connect(loop.quit)
        timer.start(30000)
        loop.exec()
        if panel.running():
            panel.cancel()
            panel.process.waitForFinished(3000)
            self.fail('Background Excel export did not finish.')
        self.assertEqual(target, panel.lift_csv, panel.log.toPlainText())
        self.assertEqual('Open lift Excel table', panel.open_lift_csv.text())
        cells, _, tables = saved_cells(target)
        self.assertIn('TEXT(W6', cells['AD6'][1])
        self.assertEqual([], self.editor.store.data['lifts'])
        with patch('visualiser.project_report_panel.QDesktopServices.openUrl') as opener:
            panel.open_csv_result()
        self.assertEqual(target, Path(opener.call_args[0][0].toLocalFile()))
        panel.close()
        panel.deleteLater()

    def test_cancel_excel_save_starts_no_worker(self):
        from PySide6.QtWidgets import QDialog, QFileDialog
        from tests.test_lift_integration import two_lifts
        from visualiser.project_report_panel import ProjectReportPanel
        directory = Path(self.temp.name) / 'cancel'
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps(two_lifts()))
        panel = ProjectReportPanel(self.editor)
        panel.run_dir = directory
        panel._requested_editor_project = self.editor.project
        with patch.object(QDialog, 'exec', new=self.select_excel), patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            panel.generate_third_party()
        self.assertFalse(panel.running())
        self.assertIsNone(panel.third_party_target)
        panel.close()
        panel.deleteLater()


if __name__ == '__main__':
    unittest.main()
