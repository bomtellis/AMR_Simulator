"""Read-only, revision-bound playback inside the project workspace."""
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot, Qt, QPointF
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QMainWindow, QScrollArea, QComboBox, QCheckBox, QSplitter, QToolButton,
    QMenu, QSizePolicy)

from amr_run_review import verified_inputs
from amr_run_evidence import file_hash
from amr_project_runs import OUTPUTS, read_json
from amr_sim_visualiser_pyside6 import (LayoutModel, SimulationLog, SimulationVisualizer,
    AuxiliaryTimelineWindow, LiftMonitorDialog)
from playback_timeline import PlaybackTimelineWidget


class PartialSimulationLog(SimulationLog):
    """Bound displayed activity while retaining original motion timing."""
    def bound(self, origin, termination):
        self.termination = dict(termination)
        self.stop_time = origin + timedelta(seconds=termination['stop_time_sec'])
        kept = []
        for event in self.events:
            if event.start_time > self.stop_time:
                continue
            row = dict(event.row)
            if (event.start_time == self.stop_time and event.end_time > event.start_time
                    and str(row.get('event_type', '')).startswith(('segment_', 'multi_stop_segment_'))):
                continue
            if event.end_time > self.stop_time:
                row['_partial_planned_end_time'] = event.end_time.isoformat()
                row['_partial_planned_duration_sec'] = row.get('duration_sec', '')
                row['status'] = 'partial'
                row['end_time'] = self.stop_time.isoformat(sep=' ')
                row['duration_sec'] = str(max(0, (self.stop_time-event.start_time).total_seconds()))
                event = replace(event, end_time=self.stop_time, row=row)
            kept.append(event)
        self.events = kept
        self._rebuild_event_index()
        self.start_time, self.end_time = origin, self.stop_time

    def state_at(self, current_time, layout):
        return super().state_at(min(current_time, self.stop_time) if current_time else current_time, layout)

    def _refresh_state_position(self, state, current_time):
        original = state.get('raw', {}).get('_partial_planned_end_time')
        end = state.get('end_time')
        if original:
            state['end_time'] = datetime.fromisoformat(original)
        try:
            super()._refresh_state_position(state, min(current_time, getattr(self, 'stop_time', current_time)))
        finally:
            state['end_time'] = end


def partial_notice(termination):
    return (f"Partial run — {termination['reason']} at {termination['stop_time_sec']:.9g} s: "
            f"{termination['message']} Playback ends at this stop; later planned activity is not executed evidence.")


def load_playback(directory):
    """Build data off the GUI thread, rejecting inputs changed during loading."""
    directory = Path(directory).resolve()
    names = ('run_manifest.json', 'config.json', 'project_configuration.json',
             'project_checks.json', OUTPUTS['steps_csv'], OUTPUTS['steps_csv'] + '.run.json')
    hashes = {name: file_hash(directory / name) for name in names}
    manifest, config, csv, _checksum = verified_inputs(directory, allow_partial=True)
    partial = manifest['status'] == 'partial'
    layout, log = LayoutModel(), PartialSimulationLog() if partial else SimulationLog()
    layout.load_data(config)
    log.load(str(csv), parallel=False)
    if partial:
        origin = layout.simulation_start_time
        if origin is None:
            raise ValueError('Partial playback requires a recorded simulation start time.')
        log.bound(origin, manifest['termination'])
    verified_inputs(directory, allow_partial=True)
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
        self.timeline_widget = PlaybackTimelineWidget(self)
        self.timeline_scroll.setWidget(self.timeline_widget)
        self.timeline_scroll.horizontalScrollBar().valueChanged.connect(self.timeline_widget.update)
        self.timeline_scroll.verticalScrollBar().valueChanged.connect(self.timeline_widget.update)

    def set_current_time(self, value):
        self.timeline_widget.set_current_time(value)

    def on_timeline_seek(self, new_time):
        self.set_current_time(new_time)
        self._send_event({'type': 'timeline_seek', 'time': new_time})

    def _send_event(self, message):
        if message['type'] == 'timeline_seek':
            if self.timeline_widget._pressed:
                self.viewer.queue_seek(message['time'])
            else:
                self.viewer.on_timeline_seek(message['time'])

    def finish_seek(self):
        self.viewer.flush_seek()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'viewer') and not getattr(self, '_fit_pending', False):
            self._fit_pending = True
            QTimer.singleShot(0, self._fit_after_resize)

    def _fit_after_resize(self):
        self._fit_pending = False
        if self.viewer.timeline_zoom_combo.currentText() == 'Fit':
            self.set_zoom_preset('Fit')

    def showEvent(self, event):
        QMainWindow.showEvent(self, event)

    def closeEvent(self, event):
        QMainWindow.closeEvent(self, event)


class BoundVisualizer(SimulationVisualizer):
    embedded = True

    def refresh_timeline(self):
        if self.local_timeline is None:
            return
        signature = (id(self.sim_log), len(self.sim_log.events), self.sim_log.start_time,
                     self.sim_log.end_time, self.layout_model.simulation_start_time,
                     self.layout_model.simulation_end_time)
        if signature != getattr(self, '_timeline_signature', None):
            super().refresh_timeline()
            self._timeline_signature = signature
        else:
            self.local_timeline.set_current_time(self.current_time)

    def _sync_timeline_from_layout_and_csv(self):
        if isinstance(self.sim_log, PartialSimulationLog):
            original_end = self.layout_model.simulation_end_time
            self.layout_model.simulation_end_time = self.sim_log.stop_time
            try:
                super()._sync_timeline_from_layout_and_csv()
            finally:
                self.layout_model.simulation_end_time = original_end
        else:
            super()._sync_timeline_from_layout_and_csv()

    def update_time_display(self):
        if isinstance(self.sim_log, PartialSimulationLog) and self.current_time:
            self.current_time = min(self.current_time, self.sim_log.stop_time)
        if not self.current_time:
            return
        fraction = self.sim_log.time_to_fraction(self.current_time) if self.sim_log.start_time else 0
        self.slider.blockSignals(True)
        self.slider.setValue(int(fraction * 1000))
        self.slider.blockSignals(False)
        text = self.current_time.strftime('%H:%M:%S')
        if self.time_label.text() != text:
            self.time_label.setText(text)
            self.time_label.setToolTip(f'Current: {self.current_time}\n'
                f'Start: {self.sim_log.start_time}\nEnd: {self.sim_log.end_time}')
        if not self.is_playing or self._timeline_playhead_update_due():
            self._send_aux_gui_command({'type': 'timeline_time', 'time': self.current_time})
        self.update_lift_monitor_dialog()
        self.update_amr_payload_monitor_dialog()

    def __init__(self, parent):
        self.local_timeline = None
        self.show_legend = False
        self.local_lift = None
        self.latest_lifts = []
        self.first_show = True
        super().__init__()
        self._pending_seek = None
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.setInterval(33)
        self.seek_timer.timeout.connect(self.flush_seek)
        self.slider.sliderReleased.connect(self.flush_seek)
        self.setParent(parent, Qt.Widget)
        self.setProperty('amrEmbeddedPlayback', True)
        self.setProperty('amrProjectWorkspace', True)
        for action in self.project_ribbon.actions():
            if action.text() in {'Open JSON', 'Open DXF', 'Reload DXF', 'Open Simulation'}:
                action.setVisible(False)
                action.setEnabled(False)
        self.project_ribbon.setMovable(False)
        self.project_ribbon.setFloatable(False)
        side = self.main_splitter.widget(0)
        self.timeline_process_note.hide()
        self.local_timeline = LocalTimeline(self)
        self.timeline_panel_layout.addWidget(self.local_timeline, 1)
        self.show_dxf_check.setChecked(False)
        self.show_dxf_check.setEnabled(False)
        self.show_dxf_check.setToolTip('Project playback currently shows model geometry. Drawing underlays remain available in Layout.')
        self.live_waste_fill_check.setChecked(False)
        self.live_waste_fill_check.setText('Estimate waste fill from saved rules')
        self.live_waste_fill_check.setToolTip('Optional calculation from frozen configuration; this is not recorded inventory evidence.')
        from appearance import controller
        from route_display import styles_for, SCOPE
        self.route_styles = styles_for(controller())
        self.route_model = None
        self.route_error = ''
        self.route_choice = QComboBox()
        self.route_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.route_choice.setMinimumContentsLength(20)
        self.route_choice.setAccessibleName('Frozen run route profile display')
        self.route_labels = QCheckBox('Show profile labels')
        self.route_labels.setChecked(True)
        self.route_note = QLabel('Profile access from frozen inputs. ' + SCOPE)
        self.route_note.setWordWrap(True)
        for widget in (self.route_note, self.route_choice, self.route_labels):
            side.layout().addWidget(widget)
        self.route_choice.currentIndexChanged.connect(self.refresh_static_scene)
        self.route_labels.toggled.connect(self.refresh_static_scene)
        self.route_styles.changed.connect(self.refresh_static_scene)
        controller().changed.connect(self.refresh_static_scene)
        self._transpose_controls(side)

    def _transpose_controls(self, side):
        """Reuse playback commands in compact rows above a full-width map."""
        old_splitter = self.main_splitter
        self.view.setParent(None)
        side.setParent(self)
        side.hide()  # Keep legacy status/checkbox objects alive for shared handlers.
        old_splitter.setParent(None)
        old_splitter.deleteLater()
        self.removeDockWidget(self.timeline_dock)
        self.timeline_panel.setParent(None)
        self.timeline_dock.hide()
        self.timeline_dock.setWidget(None)
        controls = self.timeline_panel_layout.takeAt(0).layout()
        controls_host = QWidget(self)
        controls_host.setLayout(controls)
        controls_host.hide()
        self.project_ribbon.hide()

        root = self.centralWidget()
        content = QWidget(root)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        root.layout().addWidget(content)
        self.playback_controls = QWidget(content)
        rows = QVBoxLayout(self.playback_controls)
        rows.setContentsMargins(4, 2, 4, 2)
        rows.setSpacing(4)
        navigation = QHBoxLayout()
        navigation.setSpacing(5)

        def button(text, callback, row, tooltip=''):
            control = QPushButton(text)
            control.setToolTip(tooltip)
            control.clicked.connect(callback)
            row.addWidget(control)
            return control

        for text, callback in [('|<', self.jump_start), ('−10 s', lambda: self.step_seconds(-10))]:
            button(text, callback, navigation)
        navigation.addWidget(self.play_btn)
        button('+10 s', lambda: self.step_seconds(10), navigation)
        button('>|', self.jump_end, navigation)
        navigation.addWidget(QLabel('Speed'))
        self.speed_combo.setToolTip('Simulation seconds per real second')
        self.speed_combo.setMaximumWidth(80)
        navigation.addWidget(self.speed_combo)
        self.time_label.setWordWrap(False)
        self.time_label.setMinimumWidth(90)
        self.time_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        navigation.addWidget(self.time_label)
        self.slider.setMinimumWidth(80)
        navigation.addWidget(self.slider, 1)
        rows.addLayout(navigation)

        options = QHBoxLayout()
        options.setSpacing(5)
        options.addWidget(QLabel('Floor'))
        self.floor_spin.setMaximumWidth(65)
        options.addWidget(self.floor_spin)
        button('Fit', self.fit_view, options, 'Fit the current floor to the map view')
        self.display_button = QToolButton()
        self.display_button.setText('Display')
        self.display_button.setPopupMode(QToolButton.InstantPopup)
        display = QMenu(self.display_button)
        legend = display.addAction('Show legend')
        legend.setCheckable(True)
        legend.toggled.connect(self._set_legend)
        for checkbox in (self.show_labels_check, self.show_amr_box_check,
                         self.show_amr_charge_state_check, self.show_seeded_waste_containers_check,
                         self.show_room_payloads_check, self.show_staff_handoffs_check,
                         self.live_waste_fill_check, self.route_labels, self.follow_time_check):
            action = display.addAction(checkbox.text())
            action.setCheckable(True)
            action.setChecked(checkbox.isChecked())
            action.setToolTip(checkbox.toolTip())
            action.toggled.connect(checkbox.setChecked)
            checkbox.toggled.connect(action.setChecked)
        self.display_button.setMenu(display)
        options.addWidget(self.display_button)
        self.follow_enabled_check.setText('Follow')
        self.follow_enabled_check.setAccessibleName('Follow selected AMR')
        options.addWidget(self.follow_enabled_check)
        self.follow_combo.setMinimumContentsLength(3)
        self.follow_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.follow_combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.follow_combo.setMinimumWidth(70)
        self.follow_combo.setMaximumWidth(140)
        options.addWidget(self.follow_combo)
        self.route_choice.setMinimumContentsLength(7)
        self.route_choice.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.route_choice.setMinimumWidth(90)
        self.route_choice.setMaximumWidth(180)
        self.route_choice.setToolTip(self.route_note.text())
        options.addWidget(self.route_choice)
        tools = QToolButton()
        tools.setText('Inspect')
        tools.setPopupMode(QToolButton.InstantPopup)
        tools_menu = QMenu(tools)
        for text, callback in [('Jump to task', self.open_task_jump_dialog),
                               ('Failed tasks', self.open_failed_tasks_dialog),
                               ('Tasks by location / department', self.open_tasks_by_location_department_dialog),
                               ('Lift monitor', self.open_lift_monitor_dialog),
                               ('AMR payload monitor', self.open_amr_payload_monitor_dialog),
                               ('First movement', self.jump_first_travel)]:
            tools_menu.addAction(text).triggered.connect(callback)
        tools.setMenu(tools_menu)
        options.addWidget(tools)
        options.addStretch(1)
        rows.addLayout(options)
        layout.addWidget(self.playback_controls)

        timeline_row = QHBoxLayout()
        timeline_row.setContentsMargins(4, 0, 4, 0)
        timeline_row.addWidget(QLabel('Timeline'))
        timeline_row.addWidget(self.timeline_zoom_combo)
        button('−', lambda: self.zoom_timeline(1.35), timeline_row, 'Zoom timeline out')
        button('+', lambda: self.zoom_timeline(1 / 1.35), timeline_row, 'Zoom timeline in')
        button('Centre on current time', lambda: self._send_aux_gui_command(
            {'type': 'timeline_center', 'time': self.current_time}), timeline_row)
        jump = QToolButton()
        jump.setText('Skip')
        jump.setPopupMode(QToolButton.InstantPopup)
        jump_menu = QMenu(jump)
        for text, callback in [('Previous day', lambda: self.skip_timeline_days(-1)),
                               ('Back 6 hours', lambda: self.skip_timeline_hours(-6)),
                               ('Start of current day', self.jump_timeline_to_current_day_start),
                               ('Forward 6 hours', lambda: self.skip_timeline_hours(6)),
                               ('Next day', lambda: self.skip_timeline_days(1))]:
            jump_menu.addAction(text).triggered.connect(callback)
        jump.setMenu(jump_menu)
        timeline_row.addWidget(jump)
        timeline_row.addStretch(1)
        self.timeline_panel_layout.insertLayout(0, timeline_row)
        self.timeline_panel.setMinimumHeight(160)
        self.main_splitter = QSplitter(Qt.Vertical, content)
        self.main_splitter.setChildrenCollapsible(False)
        self.view.setMinimumHeight(200)
        self.view.setMinimumWidth(0)
        self.main_splitter.addWidget(self.view)
        self.main_splitter.addWidget(self.timeline_panel)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([650, 170])
        layout.addWidget(self.main_splitter, 1)
        self.local_timeline.setMinimumSize(0, 0)
        self.local_timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def open_timeline_window(self):
        self.timeline_panel.show()

    def _set_legend(self, visible):
        self.show_legend = visible
        self.view.viewport().update()

    def draw_overlay_panels(self, painter, viewport_rect):
        if self.show_legend:
            super().draw_overlay_panels(painter, viewport_rect)
        else:
            self._draw_text_overlay_records(painter, viewport_rect)
            lines = self._follow_overlay_lines()
            if lines:
                self._draw_overlay_box(painter, viewport_rect.width() - 332, 12,
                                       320, lines, '#ff9f1c', '#ffe2b3')

    def update_loaded_files(self):
        # The surrounding saved-run panel already identifies the playback source.
        pass

    def queue_seek(self, when):
        self._pending_seek = when
        if not self.seek_timer.isActive():
            self.seek_timer.start()

    def flush_seek(self):
        self.seek_timer.stop()
        when, self._pending_seek = self._pending_seek, None
        if when is not None:
            self.on_timeline_seek(when)

    def on_slider_change(self, value):
        if self.sim_log.start_time and self.slider.isSliderDown():
            self.queue_seek(self.sim_log.fraction_to_time(value / 1000.0))
        else:
            super().on_slider_change(value)

    def draw_layout_qt(self, floor):
        self.layout_edge_colour = '#505050' if hasattr(self, 'route_choice') and self.route_choice.currentData() is not None else '#5f8dd3'
        super().draw_layout_qt(floor)
        if not hasattr(self, 'route_choice'):
            return
        from route_display import draw_access
        selected = self.route_choice.currentData()
        if selected is None or self.route_model is None:
            return
        points, sections, _rules = self.route_model
        items = draw_access(self.graphics_scene, points, sections, floor, selected, self.route_styles,
                            lambda x, y: QPointF(*self.world_to_scene(x, y)),
                            self.route_styles.appearance.value.map_font_size, self.route_labels.isChecked())
        self.static_items.extend(item for item, _section in items)

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
        self.seek_timer.stop()
        self._pending_seek = None
        if self.is_playing:
            self.toggle_play()
        self.play_timer.stop()
        self.zoom_redraw_timer.stop()
        self.pan_redraw_timer.stop()
        for dialog in self.findChildren(QDialog):
            dialog.close()

    def adopt(self, data):
        directory, _manifest, self.layout_model, self.sim_log = data
        from route_display import access_preview, populate_choices, SCOPE
        populate_choices(self.route_choice, self.layout_model.data)
        try:
            self.route_model = access_preview(self.layout_model.data)
            self.route_error = ''
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.route_model = None
            self.route_error = 'Profile preview unavailable: ' + str(exc)
        self.route_note.setText(self.route_error or 'Profile access from frozen inputs. ' + SCOPE)
        self.route_choice.setToolTip(self.route_note.text())
        self.current_json_path = str(directory / 'config.json')
        self.current_csv_path = str(directory / OUTPUTS['steps_csv'])
        self.current_time = None
        self._invalidate_runtime_caches()
        floors = self.layout_model.floors()
        self.floor_spin.setValue(int(floors[0]) if floors else 0)
        self.update_loaded_files()
        self.update_follow_amr_options()
        self.time_label.setToolTip(f'Start: {self.sim_log.start_time}\nEnd: {self.sim_log.end_time}')
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
        self.layout.setContentsMargins(4, 2, 4, 2)
        self.layout.setSpacing(4)
        self.summary = QLabel('Select a completed or stopped run in Simulate, then choose Playback selected run.')
        self.summary.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.summary, 1)
        for title, callback in [('Select run', editor.show_project_runs), ('Investigate this run', self.investigate)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.layout.addLayout(buttons)

    def load(self, directory):
        self.reset()
        self.requested_project = self.editor.project
        self.requested_evidence_project = getattr(self,'_study_context',None) or self.editor.project
        self._study_context=None
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
        project = getattr(self,'requested_evidence_project',None) or self.editor.project
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
        self.summary.setText(f"{manifest['name']} · {len(log.events):,} events"
            + ('\n' + partial_notice(manifest['termination']) if manifest['status']=='partial' else ''))
        self.summary.setToolTip(f"Saved revision {binding['revision_id']}\n"
            'Read-only geometry and recorded motion from this run. Drawing underlays are available in Layout.')

    def pause(self):
        if self.viewer is not None:
            self.viewer.pause()

    def reset(self):
        self.token += 1
        self.requested_evidence_project=None
        self.pause()
        if self.viewer is not None:
            self.layout.removeWidget(self.viewer)
            self.viewer.close()
            self.viewer.deleteLater()
            self.viewer = None
        self.directory = None
        self.summary.setText('Select a completed or stopped run in Simulate, then choose Playback selected run.')

    def investigate(self):
        if self.directory is not None:
            self.editor.show_results_investigation()
            self.editor.results_panel.load(str(self.directory))
