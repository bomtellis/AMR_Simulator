"""Saved project → checked external simulation → results investigation."""
from copy import deepcopy
import gc
from pathlib import Path
import sys
from threading import Event

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QComboBox
from project_checks_panel import RunChecksDialog
from amr_memory_runs import MemoryRuns
from amr_project_runs import PreparedRun, inspect_run, finish_run, read_json, MANIFEST, link_run


class MemoryJobSignals(QObject):
    progress = Signal(object)
    finished = Signal(object, str)


class MemoryJob(QRunnable):
    def __init__(self, kind, run, action):
        super().__init__()
        self.kind, self.run_data, self.action = kind, run, action
        self.cancelled = Event()
        self.signals = MemoryJobSignals()

    def run(self):
        result, error = None, ''
        try:
            result = self.action(self.cancelled.is_set, self.signals.progress.emit)
        except Exception as exc:
            error = str(exc)
        self.action = None
        if self.kind in ('run', 'save'):
            # Collect transient objects after the worker's action and any
            # exception traceback have gone out of scope.
            gc.collect()
        self.signals.finished.emit(result, error)


class ProjectRunsPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.process = None
        self.run_dir = None
        self.cancelled = False
        self.run_paths = []
        self.run_refs = []
        self.memory = MemoryRuns()
        self.memory_rows = {}
        self.memory_job = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("Save a project to start a revision-bound simulation.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        storage_label = QLabel('Run storage')
        self.storage = QComboBox()
        self.storage.addItems(['Save to disk', 'Memory only'])
        self.storage.setAccessibleName('Run storage')
        self.storage.setToolTip('Memory only uses current edits. Runs remain here until saved, discarded, or the document closes.')
        storage_label.setBuddy(self.storage)
        buttons.addWidget(storage_label)
        buttons.addWidget(self.storage)
        self.start_button = QPushButton("Save, check and simulate")
        self.start_button.clicked.connect(self.start_run)
        self.stop_button = QPushButton("Stop run")
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        for control in (self.start_button, self.stop_button):
            buttons.addWidget(control)
        layout.addLayout(buttons)
        self.storage.currentIndexChanged.connect(self.update_start_controls)
        management = QHBoxLayout()
        review = QHBoxLayout()
        self.saved_actions = []
        for title, handler in (("Refresh runs", self.refresh_runs), ("Results location…", self.choose_results_root),
                               ("Locate moved run…", self.relink_run), ("Investigate selected run", self.investigate),
                               ("Playback selected run", self.playback),
                               ("Analyse lifts and routes", self.analyse_routes),
                               ("Report selected run", self.report)):
            button = QPushButton(title)
            button.clicked.connect(handler)
            row = management if handler in (self.refresh_runs, self.choose_results_root, self.relink_run) else review
            row.addWidget(button)
            if handler in (self.relink_run, self.analyse_routes, self.report):
                self.saved_actions.append(button)
        self.save_run_button = QPushButton('Save run')
        self.save_run_button.clicked.connect(self.save_memory_run)
        self.discard_run_button = QPushButton('Discard run')
        self.discard_run_button.clicked.connect(self.discard_memory_run)
        for control in (self.save_run_button, self.discard_run_button):
            management.addWidget(control)
        management.addStretch(1)
        review.addStretch(1)
        layout.addLayout(management)
        layout.addLayout(review)
        self.workflow_help = QLabel(
            'If a run folder moves, select its missing entry and choose Locate moved run. '
            'Playback opens recorded evidence read-only. Choose Report selected run, then Generate report '
            'to export from the run’s frozen inputs.')
        self.workflow_help.setWordWrap(True)
        layout.addWidget(self.workflow_help)
        self.runs = QListWidget()
        self.runs.setAccessibleName('Simulation runs for this document')
        self.runs.currentRowChanged.connect(self.show_selected)
        layout.addWidget(self.runs)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(160)
        layout.addWidget(self.log)
        self.refresh_runs()

    def running(self):
        return self.process is not None or self.memory_job is not None

    def update_start_controls(self, *_):
        self.start_button.setText('Check and simulate' if self.storage.currentIndex() else 'Save, check and simulate')
        self.start_button.setEnabled(not self.running())
        self.storage.setEnabled(not self.running())
        self.stop_button.setEnabled(self.process is not None or (
            self.memory_job is not None and self.memory_job.kind != 'save' and not self.memory_job.cancelled.is_set()))

    def selected_memory_run(self):
        return self.memory_rows.get(self.runs.currentRow())

    def _update_selection_actions(self):
        selected = self.selected_memory_run() is not None
        for button in self.saved_actions:
            button.setEnabled(not selected)
        self.save_run_button.setEnabled(selected and not self.running())
        self.discard_run_button.setEnabled(selected and not self.running())

    def confirm_memory_loss(self):
        count = len(self.memory.runs)
        if not count:
            return True
        return QMessageBox.warning(self, 'Runs still in memory',
            f'{count} run(s) will be discarded if you leave this document. '
            'Choose Cancel to return to Simulate and save the runs you want to keep.',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard

    def _release_memory_run(self, run):
        playback = getattr(self.editor, 'playback_panel', None)
        if playback is not None and playback.requested_memory is run:
            playback.reset()
        results = getattr(self.editor, 'results_panel', None)
        if results is not None:
            results.clear_memory_run(run)
        self.memory.discard(run)

    def clear_memory_runs(self):
        for run in self.memory.runs[:]:
            self._release_memory_run(run)

    def results_root(self):
        project = self.editor.project
        if project is None:
            return None
        return project.results_root()

    def sync_metadata_hash(self):
        # Metadata saves must not mark unsaved layout/configuration edits saved.
        self.editor._source_disk_hash = self.editor.project._disk_hash
        self.editor._recovery_last_state = None

    def choose_results_root(self):
        if not self.editor._project_editing_allowed():
            return
        if self.editor.project is None:
            QMessageBox.information(self, "Save a project first", "Save as an AMR project before selecting its results location.")
            return
        selected = QFileDialog.getExistingDirectory(self, "External results location", str(self.results_root()))
        if selected:
            try:
                self.editor.project.set_results_root(selected)
                self.sync_metadata_hash()
                self.refresh_runs()
            except Exception as exc:
                QMessageBox.critical(self, "Results location was not saved", str(exc))

    def refresh_runs(self, *, select=None):
        previous = select or self.selected_memory_run() or self.selected_path()
        self.runs.clear()
        self.run_paths = []
        self.run_refs = []
        self.memory_rows = {}
        self.details.clear()
        project = self.editor.project
        if project is None:
            self.summary.setText('Choose Memory only to simulate current edits, or save as an AMR project for disk runs.')
            self._append_memory_rows(previous)
            return
        root = self.results_root()
        stored = {project.resolve_results_location(ref['location']): ref for ref in project.external_results['runs']}
        discovery_error = ''
        try:
            discovered = {p.parent.resolve() for p in root.glob("*/" + MANIFEST)} if root.exists() else set()
        except OSError as exc:
            discovered = set()
            discovery_error = f" Results folder could not be read: {exc}"
        candidates = set(stored) | discovered
        rejected = 0
        missing = 0
        saved_keys = {ref['run_key'] for ref in stored.values()}
        for directory in sorted(candidates, reverse=True):
            ref = stored.get(directory)
            try:
                manifest = inspect_run(directory, project, reference=ref)
            except Exception as exc:
                if ref is None:
                    rejected += 1
                    continue
                self.run_paths.append(directory)
                self.run_refs.append(ref)
                self.runs.addItem(f"{ref['name']} | missing or unavailable — locate run | revision {ref['revision_id'][:8]}")
                missing += 1
                continue
            if ref is None and manifest['run_key'] in saved_keys:
                continue  # A relocated/copy folder must explicitly replace its saved link.
            self.run_paths.append(directory)
            self.run_refs.append(ref or {**manifest['project_binding'], 'software_sha256': manifest['software']['sha256']})
            status = manifest['status']
            if status == 'prepared' and self.run_dir == directory and self.running():
                status = 'starting'
            if status == 'running' and (self.run_dir != directory or not self.running()):
                status = 'unfinished — process state unknown'
            self.runs.addItem(f"{manifest['name']} | {status} | revision {manifest['project_binding']['revision_id'][:8]}")
        self.summary.setText(f"Results location: {root}\n{len(self.run_paths)} saved run reference(s); {missing} missing or unavailable. "
                             f"{rejected} unrelated or invalid folder(s) excluded."
                             + discovery_error)
        self._append_memory_rows(previous)

    def _append_memory_rows(self, previous):
        for run in self.memory.runs:
            row = self.runs.count()
            self.memory_rows[row] = run
            self.runs.addItem(f'{run.name} | In memory | {run.status}')
        if self.memory.runs:
            used = self.memory.usage() / 1024 ** 2
            self.summary.setText(self.summary.text() +
                f'\n{len(self.memory.runs)} in memory · {used:.1f} MiB of {self.memory.budget / 1024 ** 2:g} MiB')
        if previous in self.run_paths:
            self.runs.setCurrentRow(self.run_paths.index(previous))
        elif previous in self.memory.runs:
            self.runs.setCurrentRow(next(row for row, run in self.memory_rows.items() if run is previous))
        self._update_selection_actions()

    def selected_path(self):
        row = self.runs.currentRow()
        return self.run_paths[row] if 0 <= row < len(self.run_paths) else None

    def show_selected(self, *_):
        self._update_selection_actions()
        run = self.selected_memory_run()
        if run is not None:
            summary = run.evidence['summary']
            self.details.setPlainText(f'In memory · {run.status}\nFrozen inputs from the editor at run start\n'
                f"Completed tasks: {len(summary['completed_task_ids'])}\nFailed tasks: {len(summary['failed_task_ids'])}\n"
                'Use Playback or Investigation to review. Save this run to keep it or generate reports.')
            return
        path = self.selected_path()
        if path is None:
            self.details.clear()
            return
        try:
            manifest = inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
            binding = manifest['project_binding']
            self.details.setPlainText(f"Run folder: {path}\nProject: {binding['project_id']}\nRevision: {binding['revision_id']}\n"
                f"Status: {manifest['status']}\nCompleted tasks: {manifest.get('completed_tasks', 'Not recorded')}\n"
                f"Failed tasks: {manifest.get('failed_tasks', 'Not recorded')}\n"
                f"Software fingerprint: {manifest['software']['sha256']}\n{manifest.get('error', '')}")
        except Exception as exc:
            ref = self.run_refs[self.runs.currentRow()]
            reason = ("The run folder or a required run file is missing." if isinstance(exc, FileNotFoundError)
                      else "The run folder cannot be read. Check its access permissions." if isinstance(exc, PermissionError)
                      else str(exc))
            self.details.setPlainText(f"Run unavailable: {reason}\nSaved folder: {path}\nSaved run identity: {ref['run_key']}\n"
                f"Saved revision: {ref['revision_id']}\nSaved software fingerprint: {ref['software_sha256']}\n"
                "Select Locate moved run to find this run's external folder. Project links do not contain the result files.")

    def start_run(self):
        if self.running():
            return
        if self.editor._history_busy():
            QMessageBox.information(self, "Finish editing first", "Finish or close active editing windows before preparing a run.")
            return
        if self.storage.currentIndex() == 1:
            self.start_memory_run()
            return
        if not self.editor.save_project():
            return
        draft = None
        checks = None
        try:
            draft = PreparedRun(self.editor.project, self.results_root())
            checks = RunChecksDialog(lambda: read_json(draft.directory / 'config.json'), self,
                                     lambda: draft.directory)
            if checks.exec() != QDialog.Accepted:
                return
            directory = draft.commit(checks.panel.report)
            self.sync_metadata_hash()
            self.start_process(directory)
        except Exception as exc:
            QMessageBox.critical(self, "Simulation could not start", str(exc))
        finally:
            if checks is not None:
                checks.panel.timer.stop()
                checks.deleteLater()
            if draft is not None:
                draft.discard()
            self.refresh_runs()

    def _source_base(self):
        return Path(self.editor.current_json_path).parent if self.editor.current_json_path else Path.cwd()

    def start_memory_run(self):
        if not self.editor._finish_property_draft():
            return
        self.editor._commit_history()
        config = deepcopy(self.editor.store.data)
        base, project = self._source_base(), self.editor.project

        def prepare(cancel, progress):
            progress(dict(phase='Freezing current inputs and drawings in memory'))
            return self.memory.prepare(config, base, project, cancel=cancel)

        self._start_memory_job(MemoryJob('prepare', None, prepare))

    def _check_memory_run(self, draft):
        checks = None
        try:
            checks = RunChecksDialog(lambda: draft.config, self, asset_refs=draft.asset_refs)
            if checks.exec() != QDialog.Accepted:
                draft.dispose()
                self.log.appendPlainText('Run checks cancelled.')
                return
            draft.accept_checks(checks.panel.report)
            remaining = self.memory.reserve(draft)
            self._start_memory_job(MemoryJob('run', draft,
                lambda cancel, progress: draft.execute(remaining, cancel=cancel, progress=progress)))
        except Exception as exc:
            draft.dispose()
            QMessageBox.critical(self, 'Simulation could not start', str(exc))
        finally:
            if checks is not None:
                checks.panel.timer.stop()
                checks.deleteLater()

    def _start_memory_job(self, job):
        self.memory_job = job
        self.log.clear()
        job.signals.progress.connect(self._memory_progress)
        job.signals.finished.connect(self._memory_finished)
        self.update_start_controls()
        self._update_selection_actions()
        self.editor.sync_project_editing_lock()
        QThreadPool.globalInstance().start(job)

    @Slot(object)
    def _memory_progress(self, message):
        phase = message.get('phase', '')
        if 'sim_time_sec' in message:
            phase += (f" · {message['sim_time_sec']:,.0f} simulated seconds · "
                      f"{message['completed']:,} complete · {message['failed']:,} failed")
        self.log.appendPlainText(phase)

    @Slot(object, str)
    def _memory_finished(self, result, error):
        job, self.memory_job = self.memory_job, None
        if job is None:
            return
        run = job.run_data
        select = run
        self.update_start_controls()
        self.editor.sync_project_editing_lock()
        if job.kind == 'prepare':
            if job.cancelled.is_set():
                if result is not None:
                    result.dispose()
                self.log.appendPlainText('Memory run cancelled.')
            elif result is None:
                self.log.appendPlainText('Simulation could not start: ' + error)
            else:
                self._check_memory_run(result)
        elif job.kind == 'run':
            if job.cancelled.is_set() or result is None:
                run.dispose()
                self.log.appendPlainText('Memory run cancelled.' if job.cancelled.is_set() else f'Memory run failed: {error}')
            else:
                self.memory.add(run)
                self.log.appendPlainText(f'Run {run.status}. Results held in memory.')
        elif result is None:
            self.log.appendPlainText('Save failed: ' + error)
            QMessageBox.critical(self, 'Run was not saved', error)
        else:
            project, select, same_inputs, original_base = result
            self.editor.adopt_memory_run_project(project, same_inputs, original_base)
            self._release_memory_run(run)
            self.log.appendPlainText(f'Saved run: {select}')
        self.refresh_runs(select=select)

    def save_memory_run(self):
        run = self.selected_memory_run()
        if run is None or self.running() or not self.editor._project_editing_allowed():
            return
        project = self.editor.project
        path = None
        base = self._source_base()
        current_inputs = None
        if project is None:
            suggestion = str(Path(self.editor.current_json_path).with_suffix('.amrproj')) if self.editor.current_json_path else 'project.amrproj'
            path, _ = QFileDialog.getSaveFileName(self, 'Save run in a new AMR project', suggestion, 'AMR projects (*.amrproj)')
            if not path:
                return
            current_inputs = deepcopy(self.editor.store.data)

        def publish(_cancel, progress):
            same_inputs = current_inputs is not None and run.matches_source(current_inputs, base)
            return (*run.publish(project, path, progress=progress), same_inputs, base)

        self._start_memory_job(MemoryJob('save', run, publish))

    def discard_memory_run(self):
        run = self.selected_memory_run()
        if run is not None and not self.running():
            self._release_memory_run(run)
            self.refresh_runs()

    def start_process(self, directory):
        self.run_dir = Path(directory)
        self.cancelled = False
        self.log.clear()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.setWorkingDirectory(str(directory))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(lambda code, _status: self.finished(code))
        self.process.errorOccurred.connect(self.process_error)
        self.update_start_controls()
        self._update_selection_actions()
        self.editor.sync_project_editing_lock()
        if getattr(sys, 'frozen', False):
            worker = Path(sys.executable).with_name('AMRSimulatorWorker.exe')
            self.process.start(str(worker), ['--run-project', str(directory)])
        else:
            self.process.start(sys.executable, ['-u', str(Path(__file__).resolve().parents[1] / 'amr_project_runs.py'), str(directory)])

    def read_output(self):
        if self.process is not None:
            text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
            self.log.appendPlainText(text.rstrip())
            try:
                with (self.run_dir / 'process.log').open('a', encoding='utf-8') as stream:
                    stream.write(text)
            except OSError as exc:
                self.log.appendPlainText(f"Could not save process output: {exc}")

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.finished(-1, 'Simulation process could not start')

    def finished(self, code, error=''):
        if self.process is None:
            return
        self.read_output()
        process, self.process = self.process, None
        try:
            manifest = finish_run(self.run_dir, code, cancelled=self.cancelled, error=error)
            self.log.appendPlainText(f"Run {manifest['status']}. " + manifest.get('error', ''))
        except Exception as exc:
            self.log.appendPlainText(f"Could not record final run status: {exc}")
        process.deleteLater()
        self.editor.sync_project_editing_lock()
        self.update_start_controls()
        self.refresh_runs()

    def stop_run(self):
        if self.process is not None:
            self.cancelled = True
            self.process.kill()
        elif self.memory_job is not None and self.memory_job.kind != 'save':
            self.memory_job.cancelled.set()
            self.log.appendPlainText('Stopping simulation…')
            self.update_start_controls()

    def link_run(self, path, *, expected_run_key=None):
        if not self.editor._project_editing_allowed():
            return False
        if self.editor.project is None:
            raise ValueError("Open the saved project first")
        directory = Path(path).resolve()
        link_run(self.editor.project, directory, expected_run_key=expected_run_key)
        self.sync_metadata_hash()
        self.refresh_runs()

    def relink_run(self):
        if self.selected_memory_run() is not None:
            return
        row = self.runs.currentRow()
        expected = self.run_refs[row]['run_key'] if 0 <= row < len(self.run_refs) else None
        path = QFileDialog.getExistingDirectory(self, "Locate moved run folder")
        if path:
            try:
                self.link_run(path, expected_run_key=expected)
            except Exception as exc:
                QMessageBox.critical(self, "Run could not be linked", str(exc))

    def investigate(self):
        run = self.selected_memory_run()
        if run is not None:
            self.editor.show_results_investigation()
            self.editor.results_panel.load(run)
            return
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_results_investigation()
                self.editor.results_panel.load(str(path))
            except Exception as exc:
                QMessageBox.critical(self, "Run unavailable", str(exc))

    def playback(self):
        run = self.selected_memory_run()
        if run is not None:
            self.editor.show_project_playback(run)
            return
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_project_playback(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Playback unavailable', str(exc))

    def analyse_routes(self):
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_route_analysis(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Run unavailable', str(exc))

    def report(self):
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_project_report(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Report unavailable', str(exc))
