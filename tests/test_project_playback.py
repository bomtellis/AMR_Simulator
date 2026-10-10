"""Independent playback positions and frozen-run/UI lifecycle acceptance."""
from copy import deepcopy
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from tests import test_project_runs as runs
from PySide6.QtCore import QEventLoop, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget
from project_playback_panel import load_playback, BoundVisualizer, ProjectPlaybackPanel
from amr_sim_visualiser_pyside6 import SimulationLog, LayoutModel
from amr_project_runs import OUTPUTS, read_json
from app import AMRGraphEditor
from models import JsonStore


class PlaybackDataTests(unittest.TestCase):
    setUp = runs.ProjectRunTests.setUp
    prepare = runs.ProjectRunTests.prepare
    run_reference = runs.ProjectRunTests.run_reference

    def test_independent_position_and_reverse_seek_preserve_native_event_id(self):
        _, _, layout, log = load_playback(self.run_reference())
        # Load for 2 s, then traverse (0,0)->(3,4), 5 m at 2 m/s.
        for sec, x, y in [(3, 1.2, 1.6), (4, 2.4, 3.2), (3, 1.2, 1.6)]:
            states, _ = log.state_at(log.start_time + timedelta(seconds=sec), layout)
            robot = states['R-1']
            self.assertAlmostEqual(x, robot['x'])
            self.assertAlmostEqual(y, robot['y'])
            self.assertEqual('T', robot['task_id'])
            self.assertTrue(robot['raw']['event_id'])
            self.assertIn(robot['raw']['event_id'], [e.row['event_id'] for e in log.events])

    def test_loading_writes_nothing_and_matches_standalone_parser(self):
        directory = self.run_reference()
        before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        _, _, _, log = load_playback(directory)
        after = {p.relative_to(directory): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        standalone = SimulationLog()
        standalone.load(str(directory / OUTPUTS['steps_csv']))
        self.assertEqual([e.row for e in standalone.events], [e.row for e in log.events])

    def test_current_edits_and_caller_mutations_cannot_change_frozen_layout(self):
        directory = self.run_reference()
        self.config['amrs'][0]['speed_m_per_sec'] = 99
        _, _, layout, _ = load_playback(directory)
        self.assertEqual(2, layout.data['amrs'][0]['speed_m_per_sec'])
        model = LayoutModel()
        model.load_data(self.config)
        self.config['locations'][0]['x'] = 999
        self.assertNotEqual(999, model.data['locations'][0]['x'])

    def test_incomplete_and_modified_evidence_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'completed project run'):
            # Prepared runs have no CSV, so verify the shared boundary directly.
            from amr_run_review import verified_inputs
            verified_inputs(self.prepare())
        directory = self.run_reference()
        csv = directory / OUTPUTS['steps_csv']
        csv.write_bytes(csv.read_bytes() + b'\nchanged')
        with self.assertRaisesRegex(ValueError, 'complete event evidence'):
            load_playback(directory)

    def test_frozen_configuration_changes_are_rejected(self):
        directory = self.run_reference()
        (directory / 'config.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'inputs have changed'):
            load_playback(directory)

    def test_changes_during_loading_are_rejected_even_if_metadata_remains_valid(self):
        directory = self.run_reference()
        original = SimulationLog.load
        def changed(log, path, **kwargs):
            original(log, path, **kwargs)
            target = directory / 'run_manifest.json'
            body = read_json(target)
            body['name'] = 'changed during load'
            target.write_text(json.dumps(body))
        with patch.object(SimulationLog, 'load', changed):
            with self.assertRaisesRegex(ValueError, 'changed during playback loading'):
                load_playback(directory)


class PlaybackUiTests(unittest.TestCase):
    prepare = runs.ProjectRunTests.prepare
    run_reference = runs.ProjectRunTests.run_reference

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        runs.ProjectRunTests.setUp(self)
        self.editor = AMRGraphEditor()
        self.editor.store = JsonStore(deepcopy(self.config))
        self.editor.project = self.project
        self.editor._reset_edit_history()
        self.editor._mark_saved()
        self.addCleanup(self.close_editor)
        self.directory = self.run_reference()
        self.data = load_playback(self.directory)
        self.editor.show_project_playback()
        self.panel = self.editor.playback_panel

    def close_editor(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()

    def adopt(self):
        self.panel.requested_project = self.project
        self.panel.requested_binding = self.data[1]['project_binding']
        self.panel.loaded(self.panel.token, self.data, '')
        self.assertIsNotNone(self.panel.viewer, self.panel.summary.text())
        return self.panel.viewer

    def test_embedded_timeline_seek_and_zoom_without_auxiliary_process(self):
        with patch('amr_sim_visualiser_pyside6.mp.get_context', side_effect=AssertionError('No process allowed')):
            viewer = self.adopt()
            when = viewer.sim_log.start_time + timedelta(seconds=3)
            viewer.local_timeline.on_timeline_seek(when)
            self.assertEqual(when, viewer.current_time)
            self.assertEqual(when, viewer.local_timeline.timeline_widget.current_time)
            viewer.on_timeline_zoom_changed('15 min')
            old = viewer.local_timeline.timeline_widget.seconds_per_pixel
            viewer.zoom_timeline(2)
            self.assertAlmostEqual(old * 2, viewer.local_timeline.timeline_widget.seconds_per_pixel)
            self.assertIsNone(viewer._aux_gui_process)
            self.assertEqual('raster', viewer.view.graphics_backend)

    def test_playback_cannot_open_unbound_files_or_drawings(self):
        viewer = self.adopt()
        for action in viewer.project_ribbon.actions():
            if action.text() in {'Open JSON', 'Open Simulation', 'Open DXF', 'Reload DXF'}:
                self.assertFalse(action.isVisible())
                self.assertFalse(action.isEnabled())
        self.assertFalse(viewer.show_dxf_check.isEnabled())
        self.assertFalse(viewer.live_waste_fill_check.isChecked())
        self.assertIn('R-1', [viewer.follow_combo.itemText(i) for i in range(viewer.follow_combo.count())])

    def test_embedded_graph_wheel_keeps_cursor_anchor_after_dynamic_redraw(self):
        viewer = self.adopt()
        self.editor.resize(1280, 800)
        self.editor.show()
        self.app.processEvents()
        viewer.fit_view()
        view = viewer.view
        position = QPointF(view.viewport().width() * .8, view.viewport().height() * .2)
        inverse, _ = view.viewportTransform().inverted()
        target = inverse.map(position)
        when = viewer.current_time
        for delta in (120, -120):
            event = QWheelEvent(position, QPointF(view.viewport().mapToGlobal(position.toPoint())),
                                QPoint(), QPoint(0, delta), Qt.NoButton, Qt.NoModifier,
                                Qt.NoScrollPhase, False)
            with patch.object(viewer, 'refresh_dynamic_scene', wraps=viewer.refresh_dynamic_scene) as refresh:
                self.app.sendEvent(view.viewport(), event)
                refresh.assert_called_once()
            self.app.processEvents()
            actual = view.viewportTransform().map(target)
            self.assertLessEqual(abs(actual.x() - position.x()), 2)
            self.assertLessEqual(abs(actual.y() - position.y()), 2)
            self.assertEqual(when, viewer.current_time)

    def test_display_menu_retains_controls_and_floor_change_reuses_timeline(self):
        viewer = self.adopt()
        action = next(a for a in viewer.display_button.menu().actions() if a.text() == 'Show labels')
        with patch.object(viewer, 'build_amr_timeline_data', wraps=viewer.build_amr_timeline_data) as build:
            action.setChecked(False)
            self.assertFalse(viewer.show_labels_check.isChecked())
            viewer.floor_spin.setValue(1)
            build.assert_not_called()

    def test_drag_seeks_are_coalesced_and_release_applies_final_position(self):
        viewer = self.adopt()
        first = viewer.sim_log.start_time + timedelta(seconds=3)
        last = viewer.sim_log.start_time + timedelta(seconds=4)
        with patch.object(viewer, 'refresh_dynamic_scene', wraps=viewer.refresh_dynamic_scene) as refresh:
            viewer.queue_seek(first)
            viewer.queue_seek(last)
            refresh.assert_not_called()
            viewer.flush_seek()
            refresh.assert_called_once()
        self.assertEqual(last, viewer.current_time)
        self.assertEqual(last, viewer.local_timeline.timeline_widget.current_time)
        states, _ = viewer.sim_log.state_at(last, viewer.layout_model)
        self.assertAlmostEqual(2.4, states['R-1']['x'])
        self.assertAlmostEqual(3.2, states['R-1']['y'])
        self.assertFalse(viewer.seek_timer.isActive())
        viewer.queue_seek(first)
        viewer.pause()
        self.assertFalse(viewer.seek_timer.isActive())
        self.assertIsNone(viewer._pending_seek)

    def test_controls_and_timeline_fit_desktop_window(self):
        viewer = self.adopt()
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            QApplication.processEvents()
        self.assertLessEqual(self.editor.height(), 800)
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertGreaterEqual(viewer.local_timeline.timeline_scroll.viewport().height(), 90)
        self.assertEqual(Qt.Vertical, viewer.main_splitter.orientation())
        self.assertGreaterEqual(viewer.view.width(), viewer.width() * .95)
        self.assertGreaterEqual(viewer.view.height(), 200)
        self.assertFalse(viewer.playback_controls.isHidden())
        self.assertTrue(viewer.file_label.isHidden() or not viewer.file_label.isVisible())
        viewer.on_timeline_zoom_changed('Fit')
        end_x = viewer.local_timeline.timeline_widget._time_to_x(viewer.sim_log.end_time)
        self.assertLess(end_x, viewer.local_timeline.timeline_scroll.viewport().width())
        self.editor.resize(1024, 768)
        for _ in range(4):
            QApplication.processEvents()
        self.assertLessEqual(self.editor.width(), 1024)
        self.assertLessEqual(self.editor.height(), 768)
        self.assertGreaterEqual(viewer.local_timeline.timeline_scroll.viewport().height(), 90)
        end_x = viewer.local_timeline.timeline_widget._time_to_x(viewer.sim_log.end_time)
        self.assertLess(end_x, viewer.local_timeline.timeline_scroll.viewport().width())
        self.assertLess(viewer.time_label.geometry().right(), viewer.slider.geometry().left())
        self.assertLess(viewer.follow_combo.geometry().right(), viewer.route_choice.geometry().left())

    def test_new_selection_ignores_previous_worker_completion(self):
        self.panel.requested_project = self.project
        self.panel.requested_binding = self.data[1]['project_binding']
        old = self.panel.token
        self.panel.token += 1
        self.panel.loaded(old, self.data, '')
        self.assertIsNone(self.panel.viewer)
        self.panel.loaded(self.panel.token, self.data, '')
        self.assertIsNotNone(self.panel.viewer)

    def test_playback_is_read_only_and_does_not_block_editor_history(self):
        before = deepcopy(self.editor.store.data)
        viewer = self.adopt()
        self.editor.show()
        QApplication.processEvents()
        self.assertFalse(self.editor._history_busy())
        self.assertTrue(self.editor._confirm_unsaved_changes())
        viewer.on_slider_change(100)
        self.assertEqual(before, self.editor.store.data)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_leaving_workspace_pauses_and_closes_monitors(self):
        viewer = self.adopt()
        viewer.toggle_play()
        self.assertTrue(viewer.play_timer.isActive())
        from PySide6.QtWidgets import QDialog
        monitor = QDialog(viewer)
        monitor.show()
        self.editor.workspace.activate('configuration')
        self.assertFalse(viewer.is_playing)
        self.assertFalse(viewer.play_timer.isActive())
        self.assertFalse(monitor.isVisible())

    def test_reset_invalidates_late_results_and_stops_playback(self):
        viewer = self.adopt()
        viewer.toggle_play()
        old_token = self.panel.token
        self.panel.reset()
        self.panel.loaded(old_token, self.data, '')
        self.assertIsNone(self.panel.viewer)
        self.assertIsNone(self.panel.directory)
        self.assertFalse(viewer.play_timer.isActive())

    def test_failed_load_leaves_no_old_viewer_under_new_title(self):
        self.adopt()
        self.panel.reset()
        self.panel.loaded(self.panel.token, None, 'Reference failure')
        self.assertIsNone(self.panel.viewer)
        self.assertIn('Reference failure', self.panel.summary.text())

    def test_another_project_and_wrong_revision_content_are_rejected(self):
        self.panel.requested_project = self.project
        self.panel.requested_binding = self.data[1]['project_binding']
        self.editor.project = None
        self.panel.loaded(self.panel.token, self.data, '')
        self.assertIsNone(self.panel.viewer)
        self.editor.project = self.project
        self.project.revisions[-1]['config'] = 'wrong'
        self.panel.loaded(self.panel.token, self.data, '')
        self.assertIsNone(self.panel.viewer)
        self.assertIn('does not belong', self.panel.summary.text())

    def test_background_load_completes_with_gui_event_loop(self):
        self.panel.load(self.directory)
        loop = QEventLoop()
        job = self.panel.jobs[self.panel.token]
        job.signals.finished.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        self.assertIsNotNone(self.panel.viewer, self.panel.summary.text())
        self.assertFalse(self.panel.jobs)

    def test_opening_project_clears_playback_and_close_stops_timers(self):
        viewer = self.adopt()
        viewer.toggle_play()
        self.assertTrue(self.editor.load_json_file(str(self.project.path), load_drawings=False, check_unsaved=False))
        self.assertIsNone(self.panel.viewer)
        self.assertFalse(viewer.play_timer.isActive())
        self.project = self.editor.project
        viewer = self.adopt()
        viewer.toggle_play()
        self.close_editor()
        self.assertFalse(viewer.play_timer.isActive())

    def test_next_report_uses_played_run(self):
        self.adopt()
        with patch.object(self.editor, 'show_project_report') as report:
            self.editor.workspace.step(1)
            report.assert_called_once_with(self.directory)
