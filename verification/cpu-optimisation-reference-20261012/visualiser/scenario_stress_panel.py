"""Setup, process progress and evidence-backed results for disruption studies."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import time

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QTabWidget, QWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QPlainTextEdit, QProgressBar, QScrollArea)

from amr_scenario_study import (default_settings, validated_settings, create_study, validate_study,
    input_identity, candidate_count)
from amr_scenario_study import search_settings, EXECUTION_SETTINGS
from amr_project_runs import read_json, write_json, finish_run
from amr_run_review import verified_inputs


class ScenarioStressDialog(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.project_key = (getattr(editor.project, 'project_id', None), editor.current_json_path)
        self.study = None
        self.path = None
        self.process = None
        self._output = ''
        self._line = ''
        self._cancelled = False
        self._started = None
        self._phase = 'Preparing study'
        self._completed_trials = 0
        self._total_trials = 0
        self._eta = None
        self._process_group = None
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(500)
        self.heartbeat.timeout.connect(self.update_elapsed)
        self.setWindowTitle('Automated scenario stress test')
        self.resize(1080, 760)
        self.setModal(False)
        layout = QVBoxLayout(self)
        self.status = QLabel('Choose settings, then select New study and run… to start. '
            'To resume, open a saved study and select Run / resume study. Simple mode only.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        page = QWidget()
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setWidget(page)
        self.tabs.addTab(setup_scroll, 'Setup')
        setup = QVBoxLayout(page)
        self.assets = QTableWidget(0, 2)
        self.assets.setMinimumHeight(140)
        self.assets.setHorizontalHeaderLabels(['Eligible asset type', 'Asset'])
        self.assets.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        setup.addWidget(self.assets, 1)
        form = QFormLayout()
        self.durations = QLineEdit()
        self.availability = QLineEdit()
        self.speeds = QLineEdit()
        self.begin = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        self.spacing = QDoubleSpinBox()
        for spin in (self.begin, self.end, self.spacing):
            spin.setRange(0, 10000000)
            spin.setDecimals(3)
            spin.setSuffix(' min')
        self.max_events = QSpinBox()
        self.max_events.setRange(1, 8)
        self.budget = QSpinBox()
        self.budget.setRange(1, 100000)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        self.ram_limit = QDoubleSpinBox()
        self.ram_limit.setRange(.25, 1024)
        self.ram_limit.setSuffix(' GiB')
        self.ram_reserve = QDoubleSpinBox()
        self.ram_reserve.setRange(.25, 1024)
        self.ram_reserve.setSuffix(' GiB')
        self.ram_reserve.setToolTip('Reserve at least this much free system RAM or 20% of physical RAM, capped at half on small machines. Workers stop under memory pressure.')
        for label, widget in [('Durations (minutes, comma separated)', self.durations),
            ('Earliest event start after simulation start', self.begin), ('Latest event end after simulation start', self.end),
            ('Spacing between sampled starts', self.spacing), ('Availability choices (%)', self.availability),
            ('Speed choices (%)', self.speeds), ('Maximum simultaneous events', self.max_events),
            ('Combined trial budget', self.budget), ('Reproducible search seed', self.seed),
            ('Maximum concurrent CPU workers', self.workers), ('Study RAM limit', self.ram_limit),
            ('RAM reserved for other applications', self.ram_reserve)]:
            form.addRow(label, widget)
        setup.addLayout(form)
        note = QLabel('Every physical corridor is also tested individually for a full-period blockage, regardless of eligibility above. '
                      'Baseline and corridor trials are additional to the combined budget. Existing scenarios are retained. '
                      'Dated events are sampled within the chosen window; durations are clipped at its end. '
                      'All trials use the project-wide Maximum task deferral from Simulation settings → Run period '
                      '(60 minutes by default). Released work and required returns may finish after demand ends.')
        note.setWordWrap(True)
        setup.addWidget(note)
        row = QHBoxLayout()
        self.new_button = QPushButton('New study and run…')
        self.open_button = QPushButton('Open study…')
        self.save_settings_button = QPushButton('Save settings')
        self.new_button.clicked.connect(self.new_study)
        self.open_button.clicked.connect(self.open_study)
        self.save_settings_button.clicked.connect(self.save_settings)
        for button in (self.new_button, self.open_button, self.save_settings_button):
            row.addWidget(button)
        setup.addLayout(row)

        page = QWidget()
        self.tabs.addTab(page, 'Progress')
        progress_layout = QVBoxLayout(page)
        self.progress = QProgressBar()
        self.progress.setFormat('Overall study: %p%')
        progress_layout.addWidget(self.progress)
        self.trial_progress = QProgressBar()
        self.trial_progress.setRange(0, 0)
        progress_layout.addWidget(self.trial_progress)
        self.phase_label = QLabel('A matching completed simulation is reused as the baseline when available. Otherwise it runs with one worker. Disruption trials start after it passes.')
        self.phase_label.setWordWrap(True)
        progress_layout.addWidget(self.phase_label)
        self.elapsed_label = QLabel('Not started.')
        self.resource_label = QLabel('Default: up to 8 CPU workers, subject to available RAM.')
        self.resource_label.setWordWrap(True)
        progress_layout.addWidget(self.elapsed_label)
        progress_layout.addWidget(self.resource_label)
        self.active_trials = QTableWidget(0, 6)
        self.active_trials.setHorizontalHeaderLabels(['Active trial', 'Phase', 'Simulation time (s)', 'Completed / failed / pending', 'Elapsed (s)', 'RAM (MiB)'])
        self.active_trials.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.active_trials.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        progress_layout.addWidget(self.active_trials, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        progress_layout.addWidget(self.log, 1)

        page = QWidget()
        self.tabs.addTab(page, 'Results')
        results = QVBoxLayout(page)
        self.summary = QLabel('No study loaded.')
        self.summary.setWordWrap(True)
        results.addWidget(self.summary)
        self.results = QTableWidget(0, 7)
        self.results.setHorizontalHeaderLabels(['Trial', 'Outcome', 'Unmet', 'Failed / pending', 'Finished after demand end', 'Added delay (s)', 'Latest finish (s)'])
        self.results.horizontalHeaderItem(4).setToolTip('Informational: released tasks and returns may finish after demand ends. This does not fail a trial.')
        self.results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.results.currentCellChanged.connect(self.trial_selected)
        results.addWidget(self.results, 1)
        self.corridors = QTableWidget(0, 4)
        self.corridors.setHorizontalHeaderLabels(['Critical corridor (ranked)', 'Unmet obligations', 'Added delay (s)', 'Outcome'])
        self.corridors.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.corridors.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.corridors.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.corridors.currentCellChanged.connect(self.corridor_selected)
        results.addWidget(self.corridors, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(140)
        results.addWidget(self.details)
        row = QHBoxLayout()
        self.investigate_button = QPushButton('Investigate trial')
        self.playback_button = QPushButton('Play trial')
        self.save_scenario_button = QPushButton('Save as scenario')
        self.investigate_button.clicked.connect(self.investigate)
        self.playback_button.clicked.connect(self.playback)
        self.save_scenario_button.clicked.connect(self.save_scenario)
        for button in (self.investigate_button, self.playback_button, self.save_scenario_button):
            row.addWidget(button)
        results.addLayout(row)

        row = QHBoxLayout()
        self.start_button = QPushButton('Run / resume study')
        self.stop_button = QPushButton('Stop study')
        self.close_button = QPushButton('Close')
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.cancel)
        self.close_button.clicked.connect(self.close)
        for button in (self.start_button, self.stop_button, self.close_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.set_settings(editor.store.scenario_testing().get('stress_test', {}))
        self.refresh()

    def running(self):
        return self.process is not None

    def set_settings(self, settings):
        settings = {**default_settings(self.editor.store.data), **settings}
        # Spin boxes and compact numeric text round values for display. Preserve
        # loaded precision unless the user edits the control, especially when
        # reopening a study whose period is not a whole number of minutes.
        self._loaded_settings = deepcopy(settings)
        self._displayed_settings = {}
        self.assets.setRowCount(0)
        self._assets = default_settings(self.editor.store.data)['assets']
        for kind, identity in self._assets:
            n = self.assets.rowCount()
            self.assets.insertRow(n)
            item = QTableWidgetItem(dict(amr='AMR', lift='Lift', corridor='Corridor', corridor_node='Door')[kind])
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if [kind, identity] in settings['assets'] else Qt.Unchecked)
            self.assets.setItem(n, 0, item)
            label = QTableWidgetItem(identity)
            label.setFlags(Qt.ItemIsEnabled)
            self.assets.setItem(n, 1, label)
        for widget, key in [(self.durations, 'durations_minutes'), (self.availability, 'availability_percent'), (self.speeds, 'speed_percent')]:
            widget.setText(', '.join(f'{v:g}' for v in settings[key]))
            self._displayed_settings[key] = widget.text()
        for widget, key in [(self.begin, 'start_minute'), (self.end, 'end_minute'), (self.spacing, 'start_step_minutes'),
            (self.max_events, 'max_events'), (self.budget, 'trial_budget'), (self.seed, 'seed'),
            (self.workers, 'workers'), (self.ram_limit, 'ram_limit_gib'), (self.ram_reserve, 'reserve_ram_gib')]:
            widget.setValue(settings[key])
            self._displayed_settings[key] = widget.value()

    def settings(self):
        def numbers(widget, key):
            if widget.text() == self._displayed_settings[key]:
                return deepcopy(self._loaded_settings[key])
            return [float(v.strip()) for v in widget.text().split(',') if v.strip()]
        def value(widget, key):
            return self._loaded_settings[key] if widget.value() == self._displayed_settings[key] else widget.value()
        return validated_settings(self.editor.store.data, dict(assets=[asset for i, asset in enumerate(self._assets)
            if self.assets.item(i, 0).checkState() == Qt.Checked], durations_minutes=numbers(self.durations, 'durations_minutes'),
            availability_percent=numbers(self.availability, 'availability_percent'), speed_percent=numbers(self.speeds, 'speed_percent'),
            start_minute=value(self.begin, 'start_minute'), end_minute=value(self.end, 'end_minute'), start_step_minutes=value(self.spacing, 'start_step_minutes'),
            max_events=self.max_events.value(), trial_budget=self.budget.value(), seed=self.seed.value(),
            workers=self.workers.value(), ram_limit_gib=self.ram_limit.value(), reserve_ram_gib=self.ram_reserve.value()))

    def save_settings(self):
        try:
            self.editor.save_stress_settings(self.settings(), str(self.path) if self.path else None)
            self.status.setText('Stress-test settings saved in the project.')
        except Exception as exc:
            self.status.setText(str(exc))

    def new_study(self):
        if self.running() or not self.editor._project_editing_allowed():
            return
        try:
            settings = self.settings()
            candidate_count(settings)
            default = str(Path(self.editor.current_json_path).with_suffix('.stress.json')) if self.editor.current_json_path else 'scenario-stress.json'
            name, _ = QFileDialog.getSaveFileName(self, 'Create stress study', default, 'Stress study (*.stress.json)')
            if not name:
                return
            new_path = Path(name)
            self.status.setText('Freezing design inputs and copying study drawings…')
            self.tabs.setCurrentIndex(1)
            self.progress.setRange(0, 0)
            QApplication.processEvents()
            new_state = create_study(self.editor.store.data, new_path, settings, project=self.editor.project)
            self.path, self.study = new_path, new_state
            self.editor.save_stress_settings(settings, str(self.path))
            self.refresh()
            self.start()
        except Exception as exc:
            self.status.setText(str(exc))

    def open_study(self):
        if self.running():
            return
        name, _ = QFileDialog.getOpenFileName(self, 'Open stress study', '', 'Stress study (*.stress.json);;JSON (*.json)')
        if not name:
            return
        try:
            state = read_json(name)
            if state.get('version') != 1 or 'coverage' not in state:
                raise ValueError('This file is not a scenario stress study.')
            self.path = Path(name)
            self.study = state
            self.set_settings(state['settings'])
            self.refresh()
            self.tabs.setCurrentIndex(2)
        except Exception as exc:
            self.status.setText(str(exc))

    def stale(self):
        if not self.study:
            return False
        try:
            from amr_run_evidence import software_snapshot
            return (input_identity(self.editor.store.data) != self.study['source_identity']
                    or software_snapshot()['sha256'] != self.study['software_sha256'])
        except Exception:
            return True

    def start(self):
        if self.running() or not self.study or not self.editor._project_editing_allowed():
            return
        try:
            self._started = time.monotonic()
            self._completed_trials = len(self.study.get('results', {}))
            self._total_trials = self.study.get('expected_trials', 0)
            self._eta = None
            self._phase = 'Checking startup inputs'
            self.status.setText(self._phase)
            self.phase_label.setText('Starting background coordinator. It will look for a matching completed simulation and check the baseline before launching disruption trials.')
            self.trial_progress.setRange(0, 0)
            self.tabs.setCurrentIndex(1)
            self.progress.setRange(0, 0)
            self.update_elapsed()
            QApplication.processEvents()
            # UI setup changes never silently replace the frozen study grid.
            self.study = read_json(self.path)
            requested = self.settings()
            if search_settings(requested) != search_settings(self.study['settings']):
                raise ValueError('Setup differs from the frozen study. Restore its settings or create a new study.')
            # Full checksum/evidence validation runs in the coordinator, not on the GUI thread.
            if self.stale():
                raise ValueError('Study inputs or software changed; create a new study.')
            for key in EXECUTION_SETTINGS:
                self.study['settings'][key] = requested[key]
            project = self.editor.project
            if ('baseline' not in self.study['results'] and not self.study.get('source_project')
                    and project is not None and project.path is not None):
                self.study.update(source_project=str(project.path.resolve()), source_project_id=project.project_id)
            write_json(self.path, self.study)
            if self.study['status'] == 'complete':
                self.progress.setRange(0, 100)
                self.progress.setValue(100)
                self.status.setText('Study complete. Review results or create a new study with different bounds.')
                return
            self.path.with_suffix(self.path.suffix + '.cancel').unlink(missing_ok=True)
            self._cancelled = False
            self._output = self._line = ''
            self.process = QProcess(self)
            from amr_stress_resources import ProcessGroup, GIB, memory_status
            self._process_group = ProcessGroup(min(self.study['settings']['ram_limit_gib'] * GIB,
                                                  memory_status()['total'] * .5))
            self.process.started.connect(self.contain_coordinator)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            environment = QProcessEnvironment.systemEnvironment()
            environment.insert('PYTHONIOENCODING', 'utf-8')
            environment.insert('PYTHONUNBUFFERED', '1')
            self.process.setProcessEnvironment(environment)
            self.process.readyReadStandardOutput.connect(self.read_progress)
            self.process.finished.connect(self.worker_finished)
            self.process.errorOccurred.connect(self.worker_error)
            self.editor.sync_project_editing_lock()
            self.heartbeat.start()
            self.resource_label.setText('Launching coordinator; CPU and RAM readings will appear when it connects.')
            if getattr(sys, 'frozen', False):
                self.process.start(str(Path(sys.executable).with_name('AMRSimulatorWorker.exe')), ['--scenario-study', str(self.path.resolve())])
            else:
                environment.insert('PYTHONPATH', os.pathsep.join(value for value in sys.path if value))
                self.process.setProcessEnvironment(environment)
                self.process.start(getattr(sys, '_base_executable', sys.executable),
                    ['-u', str(Path(__file__).resolve().parents[1] / 'amr_scenario_study.py'), str(self.path.resolve())])
            self.tabs.setCurrentIndex(1)
            self.status.setText('Starting background stress-test coordinator…')
            self.refresh()
        except Exception as exc:
            if self.process is not None:
                self.process.kill()
                self.process.deleteLater()
                self.process = None
            if self._process_group:
                self._process_group.close()
                self._process_group = None
            self.editor.sync_project_editing_lock()
            self.heartbeat.stop()
            self.progress.setRange(0, 100)
            self.status.setText(str(exc))
            self.trial_progress.setRange(0, 100)
            self.trial_progress.setValue(0)
            self.phase_label.setText('Study did not start: ' + str(exc))
            self.log.appendPlainText('Study did not start: ' + str(exc))

    def contain_coordinator(self):
        try:
            self._process_group.assign(int(self.process.processId()))
        except Exception as exc:
            self._output = 'Cannot enforce study RAM and process containment: ' + str(exc)
            self.process.kill()

    def update_elapsed(self):
        if self._started is not None:
            elapsed = time.monotonic() - self._started
            text = f'Elapsed: {int(elapsed)} s · {self._completed_trials} / {self._total_trials or "—"} trials completed'
            if self._eta is not None and self.running():
                text += f' · Estimated remaining: {int(self._eta)} s (updates as trials finish)'
            self.elapsed_label.setText(text)

    def read_progress(self):
        if self.process is None:
            return
        text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._output = (self._output + text)[-8000:]
        self._line += text
        lines = self._line.split('\n')
        self._line = lines.pop()
        for line in lines:
            if line.startswith('STRESS '):
                try:
                    self.accept_progress(json.loads(line[7:]))
                except (ValueError, KeyError, TypeError) as exc:
                    self.log.appendPlainText('Progress message could not be read: ' + str(exc))
                continue
            self.log.appendPlainText(line)
            match = re.match(r'^(\d+)/(\d+):\s*(.+)', line)
            if match:
                self.progress.setValue(int(100 * (int(match[1]) - 1) / max(1, int(match[2]))))
                self.status.setText('Evaluating ' + match[3])

    def accept_progress(self, message):
        phase = message.get('phase', self._phase)
        if phase != self._phase:
            self._phase = phase
            self.log.appendPlainText(phase)
        self.status.setText(phase)
        if message.get('type') in ('progress', 'complete'):
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(message.get('fraction', 0) * 100)))
            self._completed_trials = message.get('completed_trials', self._completed_trials)
            self._total_trials = message.get('total_trials', self._total_trials)
            self._eta = message.get('eta_sec')
        if 'workers' in message:
            workers = message['workers']
            baseline = next((worker for worker in workers if worker['id'] == 'baseline'), None)
            if baseline:
                detail = baseline['phase']
                self.status.setText('Normal-operation baseline: ' + detail)
                self.phase_label.setText('One worker is checking normal operation and measuring RAM needs. '
                    'Disruption trials will use up to ' + str(message['requested_workers']) + ' workers after the baseline passes.')
            elif workers:
                self.phase_label.setText(f'{len(workers)} trials are running. New demand stops at the configured end; released work and returns finish under the same assignment deferral limit as normal operation.')
            else:
                self.phase_label.setText('No trial is running. Waiting for enough free RAM to preserve the configured reserve.')
            # A large study can stay below 1% overall throughout the baseline.
            # Show the active simulation separately, without changing search weights.
            simulated = [worker for worker in workers if 'sim_time_sec' in worker]
            if simulated:
                self.trial_progress.setRange(0, 1000)
                fractions = [min(1, worker['sim_time_sec'] / max(1, worker.get('horizon_sec', (self.study or {}).get('horizon_sec', 1))))
                             for worker in simulated]
                fraction = sum(fractions) / len(fractions)
                self.trial_progress.setValue(round(fraction * 1000))
                label = 'Baseline simulation' if baseline else 'Active simulations (average)'
                self.trial_progress.setFormat(f'{label}: {fraction:.1%} of configured period')
                if baseline:
                    self.phase_label.setText(self.phase_label.text() +
                        f" Completed: {baseline.get('completed', 0)}; failed: {baseline.get('failed', 0)}; pending: {baseline.get('pending', 0)}.")
            else:
                self.trial_progress.setRange(0, 0)
            self.resource_label.setText(f"{len(workers)} / {message['requested_workers']} CPU workers active · "
                f"Study RAM: {message['ram_bytes']/1024**3:.2f} / {message['ram_limit_bytes']/1024**3:.2f} GiB · "
                f"Free system RAM: {message['available_ram_bytes']/1024**3:.2f} GiB · Reserve: {message['reserve_ram_bytes']/1024**3:.2f} GiB")
            self.active_trials.setRowCount(len(workers))
            for row, worker in enumerate(workers):
                values = [worker['name'], worker['phase'], f"{worker.get('sim_time_sec', 0):.1f}",
                    f"{worker.get('completed', 0)} / {worker.get('failed', 0)} / {worker.get('pending', 0)}",
                    f"{worker['elapsed_sec']:.1f}", f"{worker['memory_bytes']/1024**2:.1f}"]
                for col, value in enumerate(values):
                    self.active_trials.setItem(row, col, QTableWidgetItem(str(value)))
        self.update_elapsed()
        if self._cancelled:
            self.status.setText('Stopping study…')

    def worker_error(self, error):
        if error == QProcess.FailedToStart:
            self._output = self.process.errorString()
            self.worker_finished(-1, QProcess.NormalExit)

    def worker_finished(self, code, exit_status=QProcess.NormalExit):
        if self.process is None:
            return
        self.read_progress()
        worker = self.process
        self.process = None
        worker.deleteLater()
        if self._process_group:
            self._process_group.close()
            self._process_group = None
        self.heartbeat.stop()
        self.progress.setRange(0, 100)
        self.active_trials.setRowCount(0)
        try:
            self.study = read_json(self.path)
            active = self.study.pop('active_run', None)
            if active and read_json(Path(active) / 'run_manifest.json')['status'] in ('prepared', 'running'):
                finish_run(active, -1, cancelled=self._cancelled, error='' if self._cancelled else self._output)
            for directory in self.study.pop('active_runs', {}).values():
                if read_json(Path(directory) / 'run_manifest.json')['status'] in ('prepared', 'running'):
                    finish_run(directory, -1, cancelled=self._cancelled, error='' if self._cancelled else self._output)
            if self._cancelled:
                self.study['status'] = 'cancelled'
                self.status.setText('Study stopped. Completed evidence is retained; Run / resume continues remaining trials.')
                self.phase_label.setText('Stopped. Completed trials are retained and all background workers have been stopped.')
            elif code != 0 or exit_status != QProcess.NormalExit:
                self.study.update(status='failed', error=self.study.get('error') or self._output.strip() or f'Worker exited with code {code}.')
                self.status.setText(self.study['error'])
                self.phase_label.setText(self.study['error'])
                self.log.appendPlainText(self.study['error'])
                baseline = self.study.get('results', {}).get('baseline')
                if baseline and not baseline['metrics']['passed']:
                    self.tabs.setCurrentIndex(2)
            else:
                self.status.setText('Study complete. Review the worst passing scenario found and critical corridors.')
                self.progress.setValue(100)
                self.tabs.setCurrentIndex(2)
                self.phase_label.setText('Study complete. All background workers have stopped.')
            self.resource_label.setText('No background workers are running. Completed trial evidence is retained.')
            self.trial_progress.setRange(0, 1000)
            self.trial_progress.setFormat('Active trials finished' if self.study['status'] == 'complete' else 'No active trials')
            self.trial_progress.setValue(1000 if self.study['status'] == 'complete' else 0)
            write_json(self.path, self.study)
        except Exception as exc:
            self.status.setText(str(exc))
        self.editor.sync_project_editing_lock()
        self.refresh()

    def cancel(self):
        if not self.process:
            return
        self._cancelled = True
        write_json(self.path.with_suffix(self.path.suffix + '.cancel'), {'cancel': True})
        self.status.setText('Stopping study…')
        worker = self.process
        # Give the worker a chance to finish the current trial; bound cancellation latency.
        def force_stop():
            if self.process is worker:
                if self._process_group:
                    self._process_group.close()
                    self._process_group = None
                worker.kill()
        QTimer.singleShot(5000, force_stop)

    def refresh(self):
        busy = self.running()
        for widget in (self.assets, self.durations, self.availability, self.speeds, self.begin, self.end,
                       self.spacing, self.max_events, self.budget, self.seed, self.new_button,
                       self.workers, self.ram_limit, self.ram_reserve,
                       self.open_button, self.save_settings_button, self.close_button):
            widget.setEnabled(not busy)
        self.start_button.setEnabled(bool(self.study) and not busy and not self.stale())
        self.stop_button.setEnabled(busy)
        if busy:
            return
        self.results.blockSignals(True)
        self.corridors.blockSignals(True)
        self.results.setRowCount(0)
        self.corridors.setRowCount(0)
        self._trial_rows = []
        self._corridor_rows = []
        if self.study:
            state = self.study
            if state['status'] == 'failed' and state.get('error'):
                self.status.setText(state['error'])
                self.phase_label.setText(state['error'])
            coverage = state['coverage']
            worst = state['results'].get(state.get('worst_passing'), {})
            self.summary.setText(f"{state['status']}: {coverage['tested_candidates']} / {coverage['candidate_count']} grid candidates tested; "
                f"{coverage['combined_trials']} combined trials; {coverage['corridor_trials']} individual corridors. "
                + ('Exhaustive grid coverage. ' if coverage['exhaustive'] else 'Bounded search; global worst case is not proven. ')
                + ('Worst passing scenario found: ' + worst['name'] if worst else 'No passing disruption found.')
                + (' Inputs changed; create a new study to run or save scenarios.' if self.stale() else ''))
            ranked = state.get('ranking', [])
            remaining = sorted(set(state['results']) - set(ranked))
            for identity in ranked + remaining:
                record = state['results'][identity]
                m = record['metrics']
                self._trial_rows.append(identity)
                row = self.results.rowCount()
                self.results.insertRow(row)
                for col, value in enumerate([record['name'], 'Pass' if m['passed'] else 'Does not pass', m['unmet_count'],
                    f"{m['failed']} / {m['pending']}", m['late'], f"{m['added_delay_sec']:.3f}", f"{m['latest_completion_sec']:.3f}"]):
                    self.results.setItem(row, col, QTableWidgetItem(str(value)))
            for identity in state.get('corridor_ranking', []):
                record = state['results'][identity]
                m = record['metrics']
                self._corridor_rows.append(identity)
                row = self.corridors.rowCount()
                self.corridors.insertRow(row)
                for col, value in enumerate([record['corridor'], m['unmet_count'], f"{m['added_delay_sec']:.3f}", 'Pass' if m['passed'] else 'Does not pass']):
                    self.corridors.setItem(row, col, QTableWidgetItem(str(value)))
            if self._trial_rows:
                self.results.setCurrentCell(0, 0)
        self.results.blockSignals(False)
        self.corridors.blockSignals(False)
        self.trial_selected()

    def selected_trial(self):
        n = self.results.currentRow()
        if not self.study or not 0 <= n < len(self._trial_rows):
            return None
        return self.study['results'][self._trial_rows[n]]

    def trial_selected(self, *_):
        record = self.selected_trial()
        self.investigate_button.setEnabled(bool(record) and not self.running())
        self.playback_button.setEnabled(bool(record) and not self.running())
        self.save_scenario_button.setEnabled(bool(record and record['events']) and not self.running() and not self.stale())
        if record:
            lines = []
            labels = dict(amr='AMR', lift='Lift', corridor='Corridor', corridor_node='Door')
            for event in record['events']:
                assets = ', '.join(event.get('resource_ids', []))
                start = event.get('start_datetime', event.get('start_time', '')).replace('T', ' ')
                end = event.get('end_datetime', event.get('end_time', '')).replace('T', ' ')
                lines.append(f"{labels.get(event['resource_type'], event['resource_type'])} {assets}: "
                    f"{event['availability_percent']:g}% availability, {event['speed_factor'] * 100:g}% speed; {start} to {end}.")
            if not lines:
                lines.append('Normal operation, with the configured demand and operating settings.')
            if record.get('reused'):
                lines.append('Baseline reused from existing simulation: ' + record['directory'])
            unmet = record['metrics']['unmet']
            lines.append(f"{record['metrics']['late']} tasks finished after demand ended (informational; allowed).")
            lines.append('Unmet service obligations: ' + (', '.join(unmet) if unmet else 'None.'))
            self.details.setPlainText('\n'.join(lines))
        else:
            self.details.clear()

    def corridor_selected(self, *_):
        n = self.corridors.currentRow()
        if not self.study or not 0 <= n < len(self._corridor_rows) or self.stale():
            return
        record = self.study['results'][self._corridor_rows[n]]
        a, b = record['corridor'].split(' -> ')
        self.editor.selected_edge_keys = {tuple(sorted((r['from'], r['to']))) for r in self.editor.store.data['corridors']['edges']
                                         if {r['from'], r['to']} == {a, b}}
        self.editor.selected_point_names = set()
        self.editor.selected_point_name = None
        self.editor.workspace.show_page('layout', self.editor.canvas)
        points = self.editor.store.all_points()
        if a in points:
            self.editor.floor_spin.setValue(points[a]['floor'])
        self.editor.refresh_canvas()
        self.editor.fit_selection()
        if record['id'] in self._trial_rows:
            self.results.setCurrentCell(self._trial_rows.index(record['id']), 0)

    def verified_selected(self):
        record = self.selected_trial()
        if record is None:
            raise ValueError('Select a trial first.')
        # Verify the selected record again before using its saved metrics or events.
        from amr_scenario_study import run_metrics, verify_trial_inputs
        verify_trial_inputs(self.study, record)
        baseline = None
        if record['kind'] != 'baseline':
            baseline_record = self.study['results']['baseline']
            baseline = run_metrics(baseline_record['directory'])
            if baseline != baseline_record['metrics']:
                raise ValueError('Baseline summary does not match its evidence.')
        if run_metrics(record['directory'], baseline) != record['metrics']:
            raise ValueError('Selected metrics do not match the trial evidence.')
        return record

    def investigate(self):
        try:
            record = self.selected_trial()
            if record is None:
                raise ValueError('Select a trial first.')
            self.editor.show_results_investigation()
            self.editor.results_panel._study_context = (self.study, record)
            self.editor.results_panel.load(record['directory'])
        except Exception as exc:
            self.status.setText(str(exc))

    def playback(self):
        try:
            from amr_project import Project
            record = self.verified_selected()
            self.editor.show_project_playback()
            self.editor.playback_panel._study_context = Project.open(record['project'])
            self.editor.playback_panel.load(record['directory'])
        except Exception as exc:
            self.status.setText(str(exc))

    def save_scenario(self):
        try:
            validate_study(self.study, self.editor.store.data)
            record = self.verified_selected()
            name = self.editor.save_stress_scenario(record['events'], record['name'])
            self.status.setText(f'Saved editable scenario: {name}. Open Scenario testing to review or enable it.')
            self.refresh()
        except Exception as exc:
            self.status.setText(str(exc))

    def closeEvent(self, event):
        if self.running():
            self.status.setText('Stop the study or wait for completion before closing.')
            event.ignore()
        else:
            super().closeEvent(event)
