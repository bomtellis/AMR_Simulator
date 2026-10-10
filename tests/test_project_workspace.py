"""Shared project workflow, frozen report inputs and central panel integration."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests import test_project_runs as runs
from amr_project_report import verified_inputs, generate, report_sections
from amr_project_runs import read_json, OUTPUTS


class ProjectReportTests(unittest.TestCase):
    setUp = runs.ProjectRunTests.setUp
    prepare = runs.ProjectRunTests.prepare
    run_reference = runs.ProjectRunTests.run_reference

    def test_accepts_only_matching_complete_event_evidence(self):
        directory = self.run_reference()
        manifest, config, csv, checksum = verified_inputs(directory)
        self.assertEqual('complete', manifest['status'])
        self.assertEqual(self.config, config)
        self.assertEqual(directory / OUTPUTS['steps_csv'], csv)
        self.assertEqual(64, len(checksum))
        with csv.open('a') as stream:
            stream.write('\nchanged')
        with self.assertRaisesRegex(ValueError, 'complete event evidence'):
            verified_inputs(directory)

    def test_prepared_and_reduced_runs_are_not_reportable(self):
        with self.assertRaisesRegex(ValueError, 'completed project run'):
            verified_inputs(self.prepare())
        directory = self.run_reference()
        evidence = directory / (OUTPUTS['steps_csv'] + '.run.json')
        body = read_json(evidence)
        body['reduced_logging'] = True
        evidence.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, 'complete event evidence'):
            verified_inputs(directory)

    def test_changed_frozen_config_rejected_before_output_creation(self):
        directory = self.run_reference()
        (directory / 'config.json').write_text('{}')
        output = self.root / 'report'
        with self.assertRaises(ValueError):
            generate(directory, output, ['front_summary'])
        self.assertFalse(output.exists())

    def test_unknown_and_empty_sections_leave_output_absent(self):
        directory = self.run_reference()
        for sections in [[], ['unsupported'], ['method', 'method']]:
            with self.subTest(sections=sections), self.assertRaises(ValueError):
                generate(directory, self.root / 'report', sections)
        self.assertFalse((self.root / 'report').exists())

    def test_output_never_overwrites_existing_folder(self):
        directory = self.run_reference()
        output = self.root / 'report'
        output.mkdir()
        marker = output / 'keep.txt'
        marker.write_text('keep')
        with self.assertRaises(FileExistsError):
            generate(directory, output, ['method'])
        self.assertEqual('keep', marker.read_text())

    def test_report_failure_records_failure_and_preserves_run(self):
        directory = self.run_reference()
        originals = {name: (directory / name).read_bytes() for name in ('config.json', 'run_manifest.json', OUTPUTS['steps_csv'])}
        report_sections()
        with patch('amr_report_main.generate_report_from_paths', side_effect=ValueError('Reference failure')):
            with self.assertRaisesRegex(ValueError, 'Reference failure'):
                generate(directory, self.root / 'report', ['method'])
        self.assertEqual('failed', read_json(self.root / 'report/report_manifest.json')['status'])
        for name, data in originals.items():
            self.assertEqual(data, (directory / name).read_bytes())

    def test_source_changes_during_report_cannot_be_marked_complete(self):
        directory = self.run_reference()
        report_sections()
        def changed(_csv, output, **_kwargs):
            output.write_bytes(b'%PDF-placeholder')
            # A display-name-only mutation does not break input validation, but
            # still changes the source record during report generation.
            path = directory / 'run_manifest.json'
            body = read_json(path)
            body['name'] = 'changed while generating'
            path.write_text(json.dumps(body))
        with patch('amr_report_main.generate_report_from_paths', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'changed during generation'):
                generate(directory, self.root / 'report', ['method'])
        self.assertEqual('failed', read_json(self.root / 'report/report_manifest.json')['status'])

    def test_actual_pdf_uses_saved_revision_and_external_output(self):
        directory = self.run_reference()
        frozen = (directory / 'config.json').read_bytes()
        archive = self.project.path.read_bytes()
        self.config['amrs'][0]['speed_m_per_sec'] = .1
        with contextlib.redirect_stdout(io.StringIO()):
            pdf = generate(directory, self.root / 'report', ['front_summary', 'method', 'task_detail'])
        from pypdf import PdfReader
        reader = PdfReader(pdf)
        self.assertGreater(len(reader.pages), 0)
        self.assertIn('AMR', ''.join(page.extract_text() or '' for page in reader.pages))
        manifest = read_json(pdf.parent / 'report_manifest.json')
        self.assertEqual('complete', manifest['status'])
        self.assertEqual(self.project.revisions[-1]['id'], manifest['project_binding']['revision_id'])
        self.assertEqual(2, read_json(pdf.parent / 'report_configuration.json')['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(frozen, (directory / 'config.json').read_bytes())
        self.assertEqual(archive, self.project.path.read_bytes())
        self.assertTrue((pdf.parent / 'report_lift_cohorts.csv').exists())

    def test_lift_cohort_export_is_verified_and_does_not_build_pdf(self):
        directory = self.run_reference()
        frozen = (directory / 'config.json').read_bytes()
        report_sections()
        with patch('amr_report_main.generate_report_from_paths', side_effect=AssertionError('CSV must not regenerate PDF')):
            with contextlib.redirect_stdout(io.StringIO()):
                path = generate(directory, self.root / 'csv-export', [], lift_cohorts_only=True)
        import pandas as pd
        from amr_run_evidence import file_hash
        frame = pd.read_csv(path)
        self.assertIn('transfer_trips', frame.columns)
        self.assertIn('travel_time_s', frame.columns)
        metadata = read_json(path.parent / 'report_manifest.json')
        self.assertEqual('complete', metadata['status'])
        self.assertEqual('lift_cohorts_csv', metadata['kind'])
        self.assertEqual(file_hash(path), metadata['lift_cohorts_sha256'])
        self.assertFalse((path.parent / 'report.pdf').exists())
        self.assertEqual(frozen, (directory / 'config.json').read_bytes())


class ProjectWorkspaceUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_all_seven_stages_share_one_central_workspace_without_editing(self):
        from project_workspace import STAGES
        before = deepcopy(self.editor.store.data)
        workspace = self.editor.workspace
        for key, _title in STAGES:
            workspace.activate(key)
            self.assertEqual(key, workspace.stage)
            self.assertIs(workspace.pages[key], workspace.stack.currentWidget())
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_checks_and_preview_read_current_store_after_undo(self):
        self.editor.validate_json()
        checks = self.editor.checks_panel
        self.editor.show_demand_preview()
        demand = self.editor.demand_panel
        self.editor._set_edit_mode('corridor_draw')
        self.editor.draw_next_corridor(20, 20)
        self.assertIs(checks.config_provider(), self.editor.store.data)
        self.assertIs(demand.config_provider(), self.editor.store.data)
        self.assertFalse(checks.current())
        self.editor.undo_edit()
        self.assertTrue(checks.current())
        self.editor.validate_json()
        self.assertIs(checks, self.editor.checks_panel)

    def test_floor_navigation_selects_layout_and_correct_floor(self):
        from PySide6.QtCore import Qt
        self.editor.store.add_corridor_node('UP', 1, 1, 1)
        self.editor.workspace.refresh()
        self.editor.show_results_investigation()
        floor = self.editor.workspace.items['layout'].child(1)
        self.assertEqual(('floor', 1), floor.data(0, Qt.UserRole))
        self.editor.workspace.selected(floor, None)
        self.assertEqual(1, self.editor.floor_spin.value())
        self.assertEqual('layout', self.editor.workspace.stage)

    def test_layout_context_assigns_dxf_to_clicked_floor_and_supports_undo(self):
        from PySide6.QtWidgets import QFileDialog
        self.editor.store.add_corridor_node('UP', 1, 1, 1)
        self.editor._reset_edit_history()
        workspace = self.editor.workspace
        workspace.refresh()
        self.editor.show_results_investigation()
        menu = workspace.layout_context_menu(workspace.object_items[('group', 1, 'location')])
        add = next(action for action in menu.actions() if action.text() == 'Add DXF…')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('upper.dxf', '')), \
                patch.object(self.editor, '_queue_all_floor_dxf_loads'), \
                patch.object(self.editor, 'ensure_floor_dxf_loaded', return_value=True):
            add.trigger()
            self.assertEqual(1, self.editor.floor_spin.value())
            self.assertEqual('layout', workspace.stage)
            self.assertEqual('upper.dxf', self.editor.get_floor_dxf_path(1))
            self.assertIsNone(self.editor.get_floor_dxf_path(0))
            self.editor.undo_edit()
            self.assertIsNone(self.editor.get_floor_dxf_path(1))
        menu.deleteLater()

    def test_drawing_only_floors_appear_and_update_without_model_points(self):
        workspace = self.editor.workspace
        self.editor.store.data['floor_dxf_files'] = [{'floor': 4, 'filepath': 'four.dxf'}]
        self.editor.store.data['floor_pdf_underlays'] = [{'floor': 5, 'filepath': 'five.pdf'}]
        workspace.refresh()
        self.assertIn(('floor', 4), workspace.object_items)
        self.assertIn(('floor', 5), workspace.object_items)
        self.editor.store.data['floor_dxf_files'] = [{'floor': 6, 'filepath': 'six.dxf'}]
        workspace.refresh()
        self.assertNotIn(('floor', 4), workspace.object_items)
        self.assertIn(('floor', 6), workspace.object_items)

    def test_manage_dxf_clears_clicked_floor_preserving_other_mappings(self):
        from PySide6.QtWidgets import QMessageBox
        workspace = self.editor.workspace
        self.editor.store.data['floor_dxf_files'] = [
            {'floor': 0, 'filepath': 'ground.dxf'}, {'floor': 4, 'filepath': 'four.dxf'}]
        self.editor._reset_edit_history()
        workspace.refresh()
        menu = workspace.layout_context_menu(workspace.object_items[('floor', 4)])
        manage = next(action.menu() for action in menu.actions() if action.text() == 'Manage DXF')
        clear = next(action for action in manage.actions() if action.text() == 'Clear floor DXF')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                patch.object(self.editor, '_queue_all_floor_dxf_loads'), \
                patch.object(self.editor, 'ensure_floor_dxf_loaded', return_value=True):
            clear.trigger()
            self.assertIsNone(self.editor.get_floor_dxf_path(4))
            self.assertEqual('ground.dxf', self.editor.get_floor_dxf_path(0))
            self.editor.undo_edit()
            self.assertEqual('four.dxf', self.editor.get_floor_dxf_path(4))
        menu.deleteLater()

    def test_layout_context_respects_editing_lock_and_ignores_other_stages(self):
        workspace = self.editor.workspace
        self.assertIsNone(workspace.layout_context_menu(workspace.items['configuration']))
        self.assertIsNone(workspace.layout_context_menu(None))
        with patch.object(self.editor, 'project_editing_locked', return_value=True), \
                patch.object(self.editor, 'load_dxf') as load:
            menu = workspace.layout_context_menu(workspace.items['layout'])
            add = next(action for action in menu.actions() if action.text() == 'Add DXF…')
            self.assertFalse(add.isEnabled())
            add.trigger()
            load.assert_not_called()
            menu.deleteLater()

    def test_leaving_layout_finishes_route_without_discarding_placed_nodes(self):
        self.editor._set_edit_mode('corridor_draw')
        self.editor.draw_next_corridor(20, 20)
        before = deepcopy(self.editor.store.data)
        self.editor.workspace.activate('configuration')
        self.assertIsNone(self.editor.corridor_draw_start)
        self.assertEqual(before, self.editor.store.data)
        self.editor.workspace.step(1)
        self.assertEqual('checks', self.editor.workspace.stage)

    def test_report_page_does_not_start_without_selected_run_or_sections(self):
        self.editor.show_project_report()
        panel = self.editor.report_panel
        self.assertFalse(panel.start.isEnabled())
        panel.generate()
        self.assertIsNone(panel.process)

    def test_active_report_blocks_project_switch_and_close(self):
        from PySide6.QtWidgets import QMessageBox
        self.editor.show_project_report()
        with patch.object(self.editor.report_panel, 'running', return_value=True), patch.object(QMessageBox, 'information') as info:
            self.assertFalse(self.editor._confirm_unsaved_changes())
        self.assertIn('Report running', info.call_args.args)

    def test_themed_workspace_keeps_main_window_size_and_visible_navigation(self):
        from ui_theme import polish_dialog
        from PySide6.QtWidgets import QLabel
        self.editor.resize(1200, 850)
        self.editor._update_unsaved_indicator()
        polish_dialog(self.editor)
        self.assertEqual(1200, self.editor.width())
        self.assertEqual(850, self.editor.height())
        self.assertIsNone(self.editor.findChild(QLabel, 'dialogIntro'))
        self.assertEqual(1, self.editor.workspace.tree.columnCount())
        self.assertEqual(['Project', 'Layout', 'Configuration', 'Check', 'Simulate', 'Review', 'Report'],
                         [self.editor.workspace.tree.topLevelItem(i).text(0) for i in range(7)])

    def test_reading_missing_drawing_lists_does_not_dirty_project(self):
        self.editor.store.data.pop('floor_dxf_files', None)
        self.editor.store.data.pop('floor_pdf_underlays', None)
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.assertIsNone(self.editor.get_floor_dxf_path(0))
        self.assertIsNone(self.editor.get_floor_pdf_underlay(0))
        self.assertFalse(self.editor.has_unsaved_changes())
        self.editor._commit_history()
        self.assertEqual(1, len(self.editor.edit_history.entries))


class ProjectReportUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = runs.ProjectRunsUiTests.setUp

    def tearDown(self):
        report = getattr(self.editor, 'report_panel', None)
        if report and report.process is not None:
            process = report.process
            report.cancel()
            process.waitForFinished(5000)
        runs.ProjectRunsUiTests.tearDown(self)

    def completed(self):
        from amr_project_runs import PreparedRun, execute
        from visualiser.project_checks import check_project
        draft = PreparedRun(self.editor.project, self.panel.results_root())
        report = check_project(draft.config, base_path=draft.directory)
        report.acknowledge_warnings()
        directory = draft.commit(report)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        self.panel.refresh_runs()
        self.panel.runs.setCurrentRow(0)
        self.panel.report()
        return directory

    def test_report_subprocess_finishes_and_keeps_current_edits(self):
        from PySide6.QtCore import Qt, QEventLoop, QTimer
        directory = self.completed()
        report = self.editor.report_panel
        self.assertEqual('report', self.editor.workspace.stage)
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 99
        for i in range(report.sections.count()):
            item = report.sections.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in {'front_summary', 'task_detail'} else Qt.Unchecked)
        report.generate()
        self.assertTrue(report.running())
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if not report.running() else None)
        poll.start(20)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(20000)
        loop.exec()
        poll.stop()
        timeout.stop()
        self.assertFalse(report.running(), report.log.toPlainText())
        self.assertTrue(report.open_pdf.isEnabled(), report.log.toPlainText())
        self.assertTrue(report.pdf.is_relative_to(directory / 'reports'))
        self.assertEqual(2, read_json(report.pdf.parent / 'report_configuration.json')['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(99, self.editor.store.data['amrs'][0]['speed_m_per_sec'])
        self.assertTrue(self.editor.has_unsaved_changes())

    def test_report_cancel_is_recorded_and_partial_output_cannot_be_opened(self):
        self.completed()
        report = self.editor.report_panel
        report.generate()
        process = report.process
        report.cancel()
        process.waitForFinished(5000)
        self.assertFalse(report.running())
        self.assertFalse(report.open_pdf.isEnabled())
        self.assertEqual('cancelled', read_json(report.output / 'report_manifest.json')['status'])

    def test_report_page_exports_lift_csv_with_no_sections_selected(self):
        from PySide6.QtCore import Qt, QEventLoop, QTimer
        self.completed()
        panel = self.editor.report_panel
        for i in range(panel.sections.count()):
            panel.sections.item(i).setCheckState(Qt.Unchecked)
        panel.existing_pdf.setText('unused.pdf')
        self.assertTrue(panel.export_lifts.isEnabled())
        panel.export_lifts.click()
        self.assertTrue(panel.running())
        self.assertFalse(panel.export_lifts.isEnabled())
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if not panel.running() else None)
        poll.start(20)
        QTimer.singleShot(20000, loop.quit)
        loop.exec()
        poll.stop()
        self.assertFalse(panel.running(), panel.log.toPlainText())
        self.assertTrue(panel.open_lift_csv.isEnabled(), panel.log.toPlainText())
        self.assertTrue(panel.lift_csv.exists())
        self.assertFalse((panel.output / 'report.pdf').exists())

    def test_packaged_worker_forwards_lift_export_mode(self):
        import amr_app
        with patch('amr_project_report.main') as worker:
            amr_app.main(['--generate-report', 'run', 'output', '--lift-cohorts-only'])
        self.assertIn('--lift-cohorts-only', worker.call_args.args[0])

    def test_next_from_selected_run_opens_its_investigation_then_report(self):
        self.completed()
        self.editor.workspace.show_page('simulate', self.panel)
        with patch.object(self.editor, 'show_results_investigation') as open_review:
            from unittest.mock import Mock
            self.editor.results_panel = Mock()
            self.editor.workspace.step(1)
            open_review.assert_called_once()
            self.editor.results_panel.load.assert_called_once_with(str(self.panel.selected_path()))
        # Restore an actual panel; report selection must survive stage changes.
        del self.editor.results_panel
        self.editor.show_results_investigation()
        self.editor.workspace.step(1)
        self.assertEqual('report', self.editor.workspace.stage)
        self.assertEqual(self.panel.selected_path(), self.editor.report_panel.run_dir)
