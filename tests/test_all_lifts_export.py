"""Batch exports keep every per-lift import contract and publish as a complete set."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from amr_third_party_lift import (COLUMNS, export_all_lifts_csv, export_lift_csv,
                                  grouped_movement_rows, recorded_events)
from tests import test_lift_integration as integration


class AllLiftExportTests(unittest.TestCase):
    def source(self, folder, identities=('Lift-A', 'Lift-B', 'Unused'), invalid=False):
        fixture = integration.ThirdPartyLiftExportTests()
        config = dict(lifts=[dict(id=identity, boarding_time_sec=31, door_time_sec=2) for identity in identities])
        events = []
        for index, identity in enumerate(identities[:2]):
            detail = dict(**{'from': identity + '-F0', 'to': identity + '-F2'},
                entry_start_sec=100.5 + index, entry_time_sec=31, exit_time_sec=31)
            if invalid and index == 1:
                detail.pop('to')
            events.append(dict(segment_type='lift_transfer', lift_id=identity, sim_time_sec=98 + index,
                               details=json.dumps(detail)))
        if identities:
            events.append(dict(segment_type='lift_reposition', lift_id=identities[0], sim_time_sec=50,
                details=json.dumps(dict(**{'from': identities[0] + '-F2', 'to': identities[0] + '-F0'}, amr_wait_node='A'))))
        with patch.object(fixture, 'config', return_value=config):
            source = fixture.source(folder, events or [dict(segment_type='corridor', sim_time_sec=0)])
        return source

    def read_batch(self, directory):
        manifest = json.loads((directory / 'export-manifest.json').read_text(encoding='utf-8'))
        result = {}
        for entry in manifest['lifts']:
            with (directory / entry['filename']).open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(list(COLUMNS), reader.fieldnames)
                result[entry['lift_id']] = list(reader)
        return manifest, result

    def test_all_lifts_get_separate_files_including_unused(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'all-lifts'
            self.assertEqual({'Lift-A': 1, 'Lift-B': 1, 'Unused': 0}, export_all_lifts_csv(source, target))
            manifest, rows = self.read_batch(target)
            self.assertEqual(3, len(manifest['lifts']))
            self.assertEqual('101,1,3,1500,60,31,31,2', rows['Lift-A'][0]['concatenated'])
            self.assertEqual('102,1,3,1500,60,31,31,2', rows['Lift-B'][0]['concatenated'])
            self.assertEqual([], rows['Unused'])
            for entry in manifest['lifts']:
                single = Path(folder) / 'single.csv'
                export_lift_csv(source, single, entry['lift_id'])
                self.assertEqual(single.read_bytes(), (target / entry['filename']).read_bytes())

    def test_reposition_toggle_applies_to_each_lift(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'all-lifts'
            self.assertEqual({'Lift-A': 2, 'Lift-B': 1, 'Unused': 0}, export_all_lifts_csv(source, target, True))
            manifest, rows = self.read_batch(target)
            self.assertTrue(manifest['include_reposition'])
            self.assertEqual('50,3,1,1500,60,0,0,2', rows['Lift-A'][0]['concatenated'])

    def test_event_evidence_is_scanned_once(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            with patch('amr_third_party_lift.recorded_events', wraps=recorded_events) as reader:
                export_all_lifts_csv(source, Path(folder) / 'all-lifts')
            reader.assert_called_once()

    def test_lift_names_cannot_escape_folder_or_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, identities=('../A/B', '..\\A:B', 'CON', 'con', 'A?B'))
            target = Path(folder) / 'all-lifts'
            export_all_lifts_csv(source, target)
            manifest, rows = self.read_batch(target)
            names = [entry['filename'] for entry in manifest['lifts']]
            self.assertEqual(len(names), len(set(name.casefold() for name in names)))
            for name in names:
                self.assertEqual(name, Path(name).name)
                self.assertNotIn('\\', name)
                self.assertNotIn(':', name)
                self.assertTrue((target / name).resolve().is_relative_to(target.resolve()))

    def test_bad_movement_leaves_no_partial_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, invalid=True)
            target = Path(folder) / 'all-lifts'
            with self.assertRaisesRegex(ValueError, 'floor evidence'):
                export_all_lifts_csv(source, target)
            self.assertFalse(target.exists())
            self.assertEqual([], list(Path(folder).glob('.third-party-lifts-*')))

    def test_existing_folder_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'previous-export'
            target.mkdir()
            marker = target / 'keep.txt'
            marker.write_text('original')
            with self.assertRaisesRegex(ValueError, 'new output folder'):
                export_all_lifts_csv(source, target)
            self.assertEqual('original', marker.read_text())
            self.assertEqual([marker], list(target.iterdir()))

    def test_changed_evidence_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'all-lifts'

            def change_source(*args, **kwargs):
                rows = grouped_movement_rows(*args, **kwargs)
                sidecar = Path(str(source) + '.run.json')
                sidecar.write_text(sidecar.read_text() + ' ')
                return rows

            with patch('amr_third_party_lift.grouped_movement_rows', side_effect=change_source), self.assertRaisesRegex(ValueError, 'changed'):
                export_all_lifts_csv(source, target)
            self.assertFalse(target.exists())
            self.assertEqual([], list(Path(folder).glob('.third-party-lifts-*')))

    def test_no_lifts_reports_clear_error(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder, identities=())
            with self.assertRaisesRegex(ValueError, 'no configured lifts'):
                export_all_lifts_csv(source, Path(folder) / 'all-lifts')

    def test_cli_and_report_cli_export_all_without_pdf(self):
        root = Path(__file__).resolve().parents[1]
        scripts = [root / 'amr_app.py', root / 'amr_third_party_lift.py', root / 'report/amr_report_main.py']
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            for index, script in enumerate(scripts):
                target = Path(folder) / f'all-{index}'
                result = subprocess.run([sys.executable, str(script), str(source), '--third-party-lifts-dir',
                    str(target), '--include-lift-reposition'], capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                _, rows = self.read_batch(target)
                self.assertEqual(2, len(rows['Lift-A']))
            self.assertEqual([], list(Path(folder).rglob('*.pdf')))

    def test_cli_rejects_mixed_single_and_all_selection(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'out'
            result = subprocess.run([sys.executable, str(root / 'amr_app.py'), str(source),
                '--third-party-lifts-dir', str(target), '--lift-id', 'Lift-A'], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(target.exists())


class AllLiftsExportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_lift_integration_ui as ui
        ui.LiftRoutingEditorTests.setUpClass.__func__(cls)

    def setUp(self):
        from tests import test_lift_integration_ui as ui
        ui.LiftRoutingEditorTests.setUp(self)

    def tearDown(self):
        from tests import test_lift_integration_ui as ui
        ui.LiftRoutingEditorTests.tearDown(self)

    @staticmethod
    def select_all(dialog):
        from PySide6.QtWidgets import QComboBox, QDialog
        selector = dialog.findChild(QComboBox)
        selector.setCurrentIndex(selector.count() - 1)
        return QDialog.Accepted

    def test_all_lifts_export_runs_in_background_and_opens_folder(self):
        import contextlib
        import io
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QDialog, QFileDialog
        from amr_project import Project
        from amr_project_runs import PreparedRun, execute
        from amr_run_review import verified_events
        from visualiser.project_checks import check_project
        from visualiser.project_report_panel import ProjectReportPanel
        from models import JsonStore

        cfg = integration.two_lifts()
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
        with patch.object(QDialog, 'exec', new=self.select_all), patch.object(
                QFileDialog, 'getExistingDirectory', return_value=self.temp.name):
            panel.generate_third_party()
        target = panel.third_party_target
        self.assertTrue(panel.third_party_all)
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        panel.process.finished.connect(loop.quit)
        timer.start(15000)
        loop.exec()
        if panel.running():
            panel.cancel()
            panel.process.waitForFinished(3000)
            self.fail('Background all-lifts export did not finish.')
        self.assertEqual(target, panel.lift_csv, panel.log.toPlainText())
        self.assertTrue(target.is_dir())
        self.assertEqual('Open lift export folder', panel.open_lift_csv.text())
        manifest = json.loads((target / 'export-manifest.json').read_text())
        self.assertEqual(2, len(manifest['lifts']))
        self.assertEqual(1, sum(entry['movements'] for entry in manifest['lifts']))
        self.assertTrue(any(entry['movements'] == 0 for entry in manifest['lifts']))
        _, _, events, _ = verified_events(directory)
        counts = export_all_lifts_csv(events, Path(self.temp.name) / 'standalone-compact')
        self.assertEqual(2, len(counts))
        with patch('visualiser.project_report_panel.QDesktopServices.openUrl') as opener:
            panel.open_csv_result()
        self.assertEqual(target, Path(opener.call_args[0][0].toLocalFile()))
        panel.close()
        panel.deleteLater()

    def test_cancel_all_lifts_folder_selection_starts_no_worker(self):
        from PySide6.QtWidgets import QDialog, QFileDialog
        from visualiser.project_report_panel import ProjectReportPanel
        directory = Path(self.temp.name) / 'cancelled-selection'
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps(integration.two_lifts()))
        panel = ProjectReportPanel(self.editor)
        panel.run_dir = directory
        panel._requested_editor_project = self.editor.project
        with patch.object(QDialog, 'exec', new=self.select_all), patch.object(
                QFileDialog, 'getExistingDirectory', return_value=''):
            panel.generate_third_party()
        self.assertFalse(panel.running())
        self.assertIsNone(panel.third_party_target)
        self.assertEqual([], list(directory.glob('third-party-lifts-*')))
        panel.close()
        panel.deleteLater()


if __name__ == '__main__':
    unittest.main()
