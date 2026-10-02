"""Read-only, revision-bound playback inside the project workspace."""
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog, QMainWindow, QDockWidget, QScrollArea

from amr_run_review import verified_inputs
from amr_run_evidence import file_hash
from amr_project_runs import OUTPUTS, read_json
from amr_sim_visualiser_pyside6 import (LayoutModel, SimulationLog, SimulationVisualizer,
    AuxiliaryTimelineWindow, LiftMonitorDialog)


def load_playback(directory):
    """Build data off the GUI thread, rejecting inputs changed during loading."""
    directory = Path(directory).resolve()
    names = ('run_manifest.json', 'config.json', 'project_configuration.json',
             'project_checks.json', OUTPUTS['steps_csv'], OUTPUTS['steps_csv'] + '.run.json')
    hashes = {name: file_hash(directory / name) for name in names}
    manifest, config, csv, _checksum = verified_inputs(directory)
    layout, log = LayoutModel(), SimulationLog()
    layout.load_data(config)
    log.load(str(csv), parallel=False)
    verified_inputs(directory)
    if any(file_hash(directory / name) != value for name, value in hashes.items()):
        raise ValueError('Run inputs changed during playback loading. Select the run again.')
    return directory, manifest, layout, log


class LoadSignals(QObject):
    finished = Signal(int, object, str)


class LoadPlayback(QRunnable):
    def __init__(self, token, directory):
        super().__init__()
        self.token, self.directory = token, directory
        self.signals = LoadSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.token, load_playback(self.directory), '')
        except Exception as exc:
            self.signals.finished.emit(self.token, None, str(exc))


class LocalTimeline(AuxiliaryTimelineWindow):
    """Reuse timeline drawing/zoom without a native window or auxiliary process."""
    def __init__(self, viewer):
        super().__init__(None)
        self.viewer = viewer
        self.setParent(viewer, Qt.Widget)
        self.setProperty('amrEmbeddedPlayback', True)
        self.setProperty('amrProjectWorkspace', True)
        self.timeline_widget.min_lane_width = 300

    def _send_event(self, message):
        if message['type'] == 'timeline_seek':
            self.viewer.on_timeline_seek(message['time'])

    def showEvent(self, event):
        QMainWindow.showEvent(self, event)

    def closeEvent(self, event):
        QMainWindow.closeEvent(self, event)


class BoundVisualizer(SimulationVisualizer):
    embedded = True

    def __init__(self, parent):
        self.local_timeline = None
        self.local_lift = None
        self.latest_lifts = []
        self.first_show = True
        super().__init__()
        self.setParent(parent, Qt.Widget)
        self.setProperty('amrEmbeddedPlayback', True)
        self.setProperty('amrProjectWorkspace', True)
        for action in self.project_ribbon.actions():
            if action.text() in {'Open JSON', 'Open DXF', 'Reload DXF', 'Open Simulation'}:
                action.setVisible(False)
                action.setEnabled(False)
        self.project_ribbon.setMovable(False)
        self.project_ribbon.setFloatable(False)
        self.timeline_dock.setFeatures(QDockWidget.DockWidgetClosable)
        # The standalone viewer's long control column must not force a tall
        # desktop window or squeeze the embedded timeline down to its header.
        side = self.main_splitter.widget(0)
        side.setParent(None)
        self.controls_scroll = QScrollArea(self)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setWidget(side)
        self.controls_scroll.setMinimumWidth(270)
        self.controls_scroll.setMaximumWidth(430)
        self.main_splitter.insertWidget(0, self.controls_scroll)
        controls = QWidget(self)
        controls.setLayout(self.timeline_panel_layout.takeAt(0).layout())
        controls_scroll = QScrollArea(self)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setWidget(controls)
        controls_scroll.setFixedHeight(72)
        self.timeline_panel_layout.insertWidget(0, controls_scroll)
        self.timeline_dock.setMinimumHeight(240)
        self.timeline_process_note.hide()
        self.local_timeline = LocalTimeline(self)
        self.timeline_panel_layout.addWidget(self.local_timeline, 1)
        self.show_dxf_check.setChecked(False)
        self.show_dxf_check.setEnabled(False)
        self.show_dxf_check.setToolTip('Project playback currently shows model geometry. Drawing underlays remain available in Layout.')
        self.live_waste_fill_check.setChecked(False)
        self.live_waste_fill_check.setText('Estimate waste fill from saved rules')
        self.live_waste_fill_check.setToolTip('Optional calculation from frozen configuration; this is not recorded inventory evidence.')

    def _content_bounds(self):
        bounds = super()._content_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            margin = max(2.0, max(x2 - x1, y2 - y1) * .12)
            return x1 - margin, y1 - margin, x2 + margin, y2 + margin
        return bounds

    def showEvent(self, event):
        super().showEvent(event)
        if self.first_show:
            self.first_show = False
            QTimer.singleShot(0, self.fit_view)
            QTimer.singleShot(0, self._fit_timeline)

    def _fit_timeline(self):
        self.on_timeline_zoom_changed(self.timeline_zoom_combo.currentText())

    def _send_aux_gui_command(self, message):
        kind = message['type']
        timeline = self.local_timeline
        if kind == 'lift_states':
            self.latest_lifts = message['states']
            if self.local_lift is not None:
                self.local_lift.update_states(self.latest_lifts)
        elif kind == 'show_lift':
            if self.local_lift is None:
                self.local_lift = LiftMonitorDialog(self)
                self.local_lift.finished.connect(self._lift_closed)
            self.local_lift.set_lifts(self.latest_lifts)
            self.local_lift.show()
        elif timeline is not None:
            if kind == 'timeline_data':
                timeline.set_timeline_data(message)
            elif kind == 'timeline_time':
                timeline.set_current_time(message.get('time'))
            elif kind == 'timeline_center':
                timeline.center_on_time(message.get('time'))
            elif kind == 'timeline_zoom':
                timeline.set_zoom_preset(message.get('preset'))
            elif kind == 'timeline_zoom_factor':
                timeline.timeline_widget.zoom_by_factor(message['factor'], message.get('anchor_time'))
            elif kind == 'show_timeline':
                timeline.show()
        return True

    def _lift_closed(self, *_):
        self._aux_lift_monitor_visible = False

    def pause(self):
        if self.is_playing:
            self.toggle_play()
        self.play_timer.stop()
        self.zoom_redraw_timer.stop()
        self.pan_redraw_timer.stop()
        for dialog in self.findChildren(QDialog):
            dialog.close()

    def adopt(self, data):
        directory, _manifest, self.layout_model, self.sim_log = data
        self.current_json_path = str(directory / 'config.json')
        self.current_csv_path = str(directory / OUTPUTS['steps_csv'])
        self.current_time = None
        self._invalidate_runtime_caches()
        floors = self.layout_model.floors()
        self.floor_spin.setValue(int(floors[0]) if floors else 0)
        self.update_loaded_files()
        self.update_follow_amr_options()
        self._sync_timeline_from_layout_and_csv()
        self.refresh_all()
        self.fit_view()
        self.timeline_zoom_combo.setCurrentText('Fit')

    def closeEvent(self, event):
        self.pause()
        super().closeEvent(event)


class ProjectPlaybackPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.token = 0
        self.jobs = {}
        self.viewer = None
        self.directory = None
        self.requested_project = None
        self.requested_binding = None
        self.layout = QVBoxLayout(self)
        self.summary = QLabel('Select a completed run in Simulate, then choose Playback selected run.')
        self.summary.setWordWrap(True)
        self.layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        for title, callback in [('Select run', editor.show_project_runs), ('Investigate this run', self.investigate)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        self.layout.addLayout(buttons)

    def load(self, directory):
        self.reset()
        self.requested_project = self.editor.project
        self.requested_binding = read_json(Path(directory) / 'run_manifest.json')['project_binding']
        self.summary.setText('Loading and checking saved run inputs and events…')
        job = LoadPlayback(self.token, directory)
        self.jobs[self.token] = job
        job.signals.finished.connect(self.loaded)
        QThreadPool.globalInstance().start(job)

    @Slot(int, object, str)
    def loaded(self, token, data, error):
        self.jobs.pop(token, None)
        if token != self.token or self.editor.project is not self.requested_project:
            return
        if error:
            self.summary.setText('Playback unavailable: ' + error)
            return
        directory, manifest, _layout, log = data
        binding = manifest['project_binding']
        project = self.editor.project
        if project is None or binding != self.requested_binding or binding['project_id'] != project.project_id or not any(
                r['id'] == binding['revision_id'] and r['config'] == binding['revision_config_sha256'] for r in project.revisions):
            self.summary.setText('Playback unavailable: this run does not belong to this project’s saved revisions.')
            return
        viewer = None
        try:
            viewer = BoundVisualizer(self)
            viewer.adopt(data)
        except Exception as exc:
            if viewer is not None:
                viewer.close()
                viewer.deleteLater()
            self.summary.setText('Playback unavailable: ' + str(exc))
            return
        self.directory = directory
        self.viewer = viewer
        self.layout.addWidget(viewer, 1)
        self.summary.setText(f"{manifest['name']} | revision {binding['revision_id'][:8]} | {len(log.events):,} recorded events\n"
            'Saved run geometry and events; current edits do not affect playback. Positions are interpolated, not verified swept paths. Drawing underlays are not shown.')

    def pause(self):
        if self.viewer is not None:
            self.viewer.pause()

    def reset(self):
        self.token += 1
        self.pause()
        if self.viewer is not None:
            self.layout.removeWidget(self.viewer)
            self.viewer.close()
            self.viewer.deleteLater()
            self.viewer = None
        self.directory = None
        self.summary.setText('Select a completed run in Simulate, then choose Playback selected run.')

    def investigate(self):
        if self.directory is not None:
            self.editor.show_results_investigation()
            self.editor.results_panel.load(str(self.directory))
