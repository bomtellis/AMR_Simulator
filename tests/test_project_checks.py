"""Independent preflight acceptance cases; checking must never repair inputs."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication, QDialog
from visualiser.project_checks import check_project, config_fingerprint
from visualiser.project_checks_panel import ProjectChecksPanel, RunChecksDialog
from test_engineering_reference import reference_config


class ProjectCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = reference_config()

    def codes(self, **kwargs):
        return {f.code for f in check_project(self.config, **kwargs).findings}

    def test_checker_is_non_mutating_and_ids_are_repeatable(self):
        before = copy.deepcopy(self.config)
        a, b = check_project(self.config), check_project(self.config)
        self.assertEqual(before, self.config)
        self.assertEqual([f.id for f in a.findings], [f.id for f in b.findings])
        self.assertEqual(a.config_hash, config_fingerprint(before))

    def test_shape_errors_block_without_crashing(self):
        for value in (None, [], {}, {'locations': 'bad'}, {**self.config, 'corridors': {'nodes': [None]}}):
            with self.subTest(value=value):
                report = check_project(value)
                report.acknowledge_warnings()
                self.assertFalse(report.can_run(value))
                self.assertTrue(any(f.severity == 'error' for f in report.findings))

    def test_duplicate_graph_names_and_missing_edges(self):
        self.config['corridors']['nodes'][0]['name'] = 'A'
        self.assertTrue({'DUPLICATE', 'REFERENCE'} <= self.codes())

    def test_invalid_numbers_detected_before_normalisation(self):
        for value in (-1, 0, True, float('nan'), float('inf'), 'fast'):
            with self.subTest(value=value):
                self.config['amrs'][0]['speed_m_per_sec'] = value
                self.assertIn('NUMBER', self.codes())

    def test_missing_engine_required_fields_block(self):
        del self.config['amrs'][0]['speed_m_per_sec']
        del self.config['payloads'][0]['weight_kg']
        paths = {f.path for f in check_project(self.config).findings if f.severity == 'error'}
        self.assertIn('/amrs/0/speed_m_per_sec', paths)
        self.assertIn('/payloads/0/weight_kg', paths)

    def test_dates_and_clock_boundaries(self):
        self.config['simulation']['end_datetime'] = '2025-01-01T00:00:00'
        self.config['task_generation']['timeframe_end'] = '24:00'
        self.assertIn('RUN_PERIOD', self.codes())
        self.assertNotIn('SCHEDULE', self.codes())
        self.config['task_generation']['scheduled_times'] = ['24:00']
        self.assertIn('SCHEDULE', self.codes())

    def test_unknown_task_profile_blocks_and_navigates_to_task(self):
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='typo')]
        report = check_project(self.config)
        finding = next(f for f in report.findings if f.path.endswith('/route_profile'))
        self.assertEqual(('error', 'tasks', 'T'), (finding.severity, finding.section, finding.target))
        report.acknowledge_warnings()
        self.assertFalse(report.can_run(self.config))

    def test_malformed_allowances_block(self):
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', allowed_nodes='A')]
        self.assertIn('REFERENCE', self.codes())

    def test_disconnected_task_is_acknowledgeable_constraint(self):
        self.config['corridors']['edges'] = []
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        report = check_project(self.config, include_legacy=False)
        self.assertIn('TASK_UNREACHABLE', {f.code for f in report.findings})
        self.assertFalse(report.can_run(self.config))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(self.config))
        self.config['locations'][0]['x'] = 1
        self.assertFalse(report.can_run(self.config))

    def test_one_way_profile_and_task_union(self):
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='p')]
        self.config['route_profiles'] = {'p': {'allowed_nodes': ['A', 'Door']}}
        self.assertIn('TASK_UNREACHABLE', self.codes(include_legacy=False))
        self.config['tasks'][0]['allowed_nodes'] = ['B']
        self.assertNotIn('TASK_UNREACHABLE', self.codes(include_legacy=False))
        self.config['corridors']['edges'][0] = {'from': 'Door', 'to': 'A', 'bidirectional': False}
        self.assertIn('TASK_UNREACHABLE', self.codes(include_legacy=False))

    def test_autoconnect_is_recognised(self):
        self.config['corridors']['edges'] = []
        self.config['corridors']['auto_connect'] = True
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        self.assertNotIn('TASK_UNREACHABLE', self.codes(include_legacy=False))
        self.assertNotIn('LOCATION_ISOLATED', self.codes(include_legacy=False))

    def test_payload_capacity_and_orientation(self):
        self.config['payloads'][0]['weight_kg'] = 101
        self.assertIn('PAYLOAD_NO_AMR', self.codes(include_legacy=False))
        self.config['payloads'][0].update(weight_kg=10, length_m=1.5, width_m=.5, allowed_carry_orientations=['sideways'])
        self.config['amrs'][0].update(payload_length_capacity_m=.5, payload_width_capacity_m=1.5)
        self.assertNotIn('PAYLOAD_NO_AMR', self.codes(include_legacy=False))

    def test_drawing_missing_is_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            self.config['floor_dxf_files'] = [{'floor': 0, 'filepath': 'missing.dxf'}]
            self.assertIn('DRAWING_MISSING', self.codes(base_path=folder))
            Path(folder, 'missing.dxf').write_text('placeholder')
            self.assertNotIn('DRAWING_MISSING', self.codes(base_path=folder))

    def test_clean_dirty_profile_policy_visible(self):
        self.config['route_profiles'] = {'clean': {}, 'dirty': {}}
        self.assertIn('PROFILE_POLICY', self.codes())

    def test_generation_references_remain_warnings_until_effective_rules_resolved(self):
        self.config['task_generation'] = {'categories': {'linen': {'department_groups': [
            {'id': 'g', 'payload': {'dropoff_location': 'missing', 'payload': 'Box'}}]}}}
        report = check_project(self.config, include_legacy=False)
        finding = next(f for f in report.findings if f.code == 'GENERATION_REFERENCE')
        self.assertEqual(('warning', 'task_generation', 'g'), (finding.severity, finding.section, finding.target))

    def test_ltn_checks_do_not_mutate_saved_project(self):
        path = Path(__file__).resolve().parents[1] / 'ltn.json'
        before = path.read_bytes()
        report = check_project(json.loads(before))
        self.assertFalse(any(f.severity == 'error' for f in report.findings))
        self.assertEqual(before, path.read_bytes())


class ProjectChecksUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.config = reference_config()
        self.config['corridors']['edges'] = []
        self.panel = ProjectChecksPanel(lambda: self.config)

    def tearDown(self):
        self.panel.timer.stop()
        self.panel.close()
        self.panel.deleteLater()

    def test_warning_acknowledgement_stale_and_recheck(self):
        self.assertFalse(self.panel.can_run())
        self.panel.acknowledge.setChecked(True)
        self.assertTrue(self.panel.can_run())
        self.config['locations'][0]['x'] = 99
        self.panel.check_staleness()
        self.assertIn('STALE', self.panel.summary.text())
        self.assertFalse(self.panel.acknowledge.isChecked())
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.can_run())
        self.panel.check_now()
        self.assertFalse(self.panel.can_run())

    def test_search_severity_and_navigation(self):
        self.panel.severity.setCurrentIndex(2)
        self.panel.search.setText('/locations/0')
        self.assertTrue(self.panel.visible_findings)
        self.assertTrue(all(f.severity == 'warning' for f in self.panel.visible_findings))
        found = []
        self.panel.navigate.connect(found.append)
        self.panel.navigate_selected()
        self.assertEqual('locations', found[0].section)
        self.assertEqual('A', found[0].target)

    def test_run_dialog_blocks_errors_even_after_acknowledgement(self):
        self.config['amrs'][0]['speed_m_per_sec'] = 0
        dialog = RunChecksDialog(lambda: self.config)
        try:
            dialog.panel.acknowledge.setChecked(True)
            dialog.accept_checked()
            self.assertFalse(dialog.run_button.isEnabled())
            self.assertNotEqual(QDialog.Accepted, dialog.result())
        finally:
            dialog.panel.timer.stop()
            dialog.close()

    def test_unavailable_input_disables_run_without_crashing(self):
        def unavailable():
            raise FileNotFoundError('Configuration moved')
        dialog = RunChecksDialog(unavailable)
        try:
            self.assertIn('Configuration moved', dialog.panel.summary.text())
            self.assertFalse(dialog.run_button.isEnabled())
        finally:
            dialog.panel.timer.stop()
            dialog.close()

    def test_editor_opens_modeless_checks_and_selects_affected_point(self):
        from app import AMRGraphEditor
        from models import JsonStore
        editor = AMRGraphEditor()
        try:
            editor.store = JsonStore(self.config)
            editor.validate_json()
            finding = next(f for f in editor.checks_panel.report.findings if f.code == 'LOCATION_ISOLATED')
            editor.navigate_check_finding(finding)
            self.assertEqual(finding.target, editor.selected_point_name)
            self.assertIs(editor.checks_dock.widget(), editor.checks_panel)
        finally:
            with patch.object(editor, "_confirm_unsaved_changes", return_value=True):
                editor.close()


class LauncherChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import amr_launcher as launcher
        self.launcher = launcher
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(launcher, name, root / child) for name, child in (
            ('LAUNCHER_CONFIG_DIR', 'configs'), ('LAUNCHER_CONFIG_ARCHIVE_DIR', 'configs/archive'), ('LAUNCHER_RUNS_DIR', 'runs'))]
        for p in self.patches:
            p.start()
        self.window = launcher.LauncherWindow()
        self.config = reference_config()
        self.path = root / 'input.json'
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        self.select = patch.object(self.window, 'selected_config_path', return_value=self.path)
        self.select.start()

    def tearDown(self):
        self.window.close()
        self.select.stop()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def accept(self, dialog):
        dialog.panel.acknowledge.setChecked(True)
        self.assertTrue(dialog.panel.can_run())
        return QDialog.Accepted

    def dialog_factory(self, action):
        # A real Qt subclass avoids replacing a Qt virtual with a Mock object.
        class AutomatedDialog(RunChecksDialog):
            def exec(self):
                return action(self)
        return AutomatedDialog

    def test_run_freezes_checked_inputs_findings_and_acknowledgements(self):
        with patch.object(self.launcher, 'RunChecksDialog', self.dialog_factory(self.accept)), patch.object(self.window, 'start_process') as start:
            self.window.run_selected_config()
        start.assert_called_once()
        folder = self.window.current_run_dir
        frozen = (folder / 'config.json').read_bytes()
        self.assertEqual(self.path.read_bytes(), frozen)
        report = json.loads((folder / 'project_checks.json').read_text())
        manifest = self.launcher.load_manifest(folder)
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), manifest['config_sha256'])
        self.assertEqual(config_fingerprint(json.loads(frozen)), report['config_sha256'])
        self.assertEqual({f['id'] for f in report['findings'] if f['severity'] == 'warning'}, set(report['acknowledged_warning_ids']))
        self.path.write_text('{}')
        self.assertEqual(frozen, (folder / 'config.json').read_bytes())

    def test_edit_during_review_cannot_start_run(self):
        def accept_then_change(dialog):
            self.accept(dialog)
            self.config['amrs'][0]['speed_m_per_sec'] = 0
            self.path.write_text(json.dumps(self.config))
            return QDialog.Accepted
        with patch.object(self.launcher, 'RunChecksDialog', self.dialog_factory(accept_then_change)), patch.object(self.window, 'start_process') as start, patch.object(self.launcher.QMessageBox, 'warning'):
            self.window.run_selected_config()
        start.assert_not_called()
        self.assertEqual([], list(self.launcher.LAUNCHER_RUNS_DIR.iterdir()))

    def test_cancel_creates_no_run(self):
        with patch.object(self.launcher, 'RunChecksDialog', self.dialog_factory(lambda _: QDialog.Rejected)), patch.object(self.window, 'start_process') as start:
            self.window.run_selected_config()
        start.assert_not_called()
        self.assertEqual([], list(self.launcher.LAUNCHER_RUNS_DIR.iterdir()))

    def test_busy_launcher_does_not_create_run_or_open_checks(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QProcess
        self.window.process = Mock()
        self.window.process.state.return_value = QProcess.Running
        try:
            with patch.object(self.launcher, 'RunChecksDialog') as dialog, patch.object(self.launcher.QMessageBox, 'warning'):
                self.window.run_selected_config()
            dialog.assert_not_called()
            self.assertEqual([], list(self.launcher.LAUNCHER_RUNS_DIR.iterdir()))
        finally:
            self.window.process = None


if __name__ == '__main__':
    unittest.main()
