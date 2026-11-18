"""Saved project → checked external simulation → results investigation."""
from copy import deepcopy
import gc
import json
from pathlib import Path
import sys
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QComboBox, QProgressBar, QFormLayout, QLineEdit, QDialogButtonBox
from project_checks_panel import RunChecksDialog
from amr_memory_runs import MemoryRuns
from amr_run_metadata import display_name, run_datetime
from run_table import RunTable
from amr_project_runs import PreparedRun, inspect_run, finish_run, read_json, MANIFEST, link_run
from amr_simulation_progress import PREFIX, ProgressEstimate, format_remaining, sample


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
        self.run_rows = []
        self.memory_job = None
        self.fleet_dialog = None
        self.utilisation_cache = {}
        self.progress_estimate = ProgressEstimate()
        self.output_buffer = b''
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
        self.fleet_button = QPushButton('Find AMR fleet size…')
        self.fleet_button.setAccessibleName('Find AMR fleet size in memory')
        self.fleet_button.clicked.connect(self.find_fleet_size)
        buttons.addWidget(self.fleet_button)
        layout.addLayout(buttons)
        self.run_progress_text = QLabel()
        self.run_progress_text.setWordWrap(True)
        self.run_progress_text.setAccessibleName('Simulation phase and estimated time remaining')
        self.run_progress_text.hide()
        layout.addWidget(self.run_progress_text)
        self.run_progress = QProgressBar()
        self.run_progress.setAccessibleName('Simulation progress')
        self.run_progress.hide()
        layout.addWidget(self.run_progress)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(500)
        self.progress_timer.timeout.connect(self._refresh_progress)
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
            if handler == self.report:
                self.report_button = button
            if handler in (self.relink_run, self.analyse_routes):
                self.saved_actions.append(button)
        self.save_run_button = QPushButton('Save run')
        self.save_run_button.clicked.connect(self.save_memory_run)
        self.discard_run_button = QPushButton('Discard run')
        self.discard_run_button.clicked.connect(self.discard_memory_run)
        for control in (self.save_run_button, self.discard_run_button):
            management.addWidget(control)
        management.addStretch(1)
        self.utilisation_button = QPushButton('View utilisation')
        self.utilisation_button.setAccessibleName('View AMR and lift utilisation for the selected memory run')
        self.utilisation_button.clicked.connect(self.view_utilisation)
        review.insertWidget(0, self.utilisation_button)
        review.addStretch(1)
        layout.addLayout(management)
        layout.addLayout(review)
        self.workflow_help = QLabel(
            'If a run folder moves, select its missing entry and choose Locate moved run. '
            'Playback opens recorded evidence read-only. Choose Report selected run, then Generate report '
            'to export from the run’s frozen inputs.')
        self.workflow_help.setWordWrap(True)
        layout.addWidget(self.workflow_help)
        run_header = QHBoxLayout()
        run_header.addWidget(QLabel('Runs'))
        run_header.addStretch(1)
        order_label = QLabel('Date order')
        self.date_order = QComboBox()
        self.date_order.addItems(['Newest first', 'Oldest first'])
        self.date_order.setAccessibleName('Run date order')
        order_label.setBuddy(self.date_order)
        run_header.addWidget(order_label)
        run_header.addWidget(self.date_order)
        self.edit_metadata_button = QPushButton('Edit name and note...')
        self.edit_metadata_button.clicked.connect(self.edit_run_metadata)
        run_header.addWidget(self.edit_metadata_button)
        layout.addLayout(run_header)
        self.runs = RunTable()
        self.runs.setAccessibleName('Simulation runs ordered by date')
        self.runs.currentRowChanged.connect(self.show_selected)
        self.runs.cellDoubleClicked.connect(lambda *_: self.edit_run_metadata())
        self.date_order.currentIndexChanged.connect(self._change_date_order)
        layout.addWidget(self.runs, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(96)
        layout.addWidget(self.log)
        self.refresh_runs()

    def running(self):
        return self.process is not None or self.memory_job is not None or self.fleet_dialog is not None

    def update_start_controls(self, *_):
        self.start_button.setText('Check and simulate' if self.storage.currentIndex() else 'Save, check and simulate')
        self.start_button.setEnabled(not self.running())
        self.storage.setEnabled(not self.running())
        self.fleet_button.setEnabled(not self.running())
        self.stop_button.setEnabled(self.process is not None or (
            self.memory_job is not None and self.memory_job.kind != 'save' and not self.memory_job.cancelled.is_set()))

    def selected_memory_run(self):
        return self.memory_rows.get(self.runs.currentRow())

    def _update_selection_actions(self):
        run = self.selected_memory_run()
        selected = run is not None
        available = selected and run.status == 'complete' and not self.running()
        row = self.runs.currentRow()
        self.edit_metadata_button.setEnabled(0 <= row < len(self.run_rows) and not self.running())
        self.report_button.setEnabled(available if selected else not self.running())
        self.utilisation_button.setEnabled(available)
        self.utilisation_button.setToolTip(
            'Review AMR and lift busy time without saving or exporting the run.' if available else
            'Select a completed memory run to view AMR and lift utilisation.')
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
        self.utilisation_cache.pop(run.key, None)
        playback = getattr(self.editor, 'playback_panel', None)
        if playback is not None and playback.requested_memory is run:
            playback.reset()
        results = getattr(self.editor, 'results_panel', None)
        if results is not None:
            results.clear_memory_run(run)
        report = getattr(self.editor, 'report_panel', None)
        if report is not None:
            report.clear_memory_run(run)
        self.memory.discard(run)

    def clear_memory_runs(self):
        results = getattr(self.editor, 'results_panel', None)
        if results is not None:
            results.clear_document()
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
        self.run_rows = []
        project = self.editor.project
        rejected = missing = saved_count = 0
        discovery_error = ''
        if project is None:
            self.summary.setText('Choose Memory only to simulate current edits, or save as an AMR project for disk runs.')
        else:
            root = self.results_root()
            stored = {project.resolve_results_location(ref['location']): ref for ref in project.external_results['runs']}
            try:
                discovered = {p.parent.resolve() for p in root.glob('*/' + MANIFEST)} if root.exists() else set()
            except OSError as exc:
                discovered = set()
                discovery_error = f' Results folder could not be read: {exc}'
            saved_keys = {ref['run_key'] for ref in stored.values()}
            for directory in sorted(set(stored) | discovered):
                ref = stored.get(directory)
                try:
                    manifest = inspect_run(directory, project, reference=ref)
                except Exception:
                    if ref is None:
                        rejected += 1
                        continue
                    missing += 1
                    self.run_rows.append(dict(path=directory, memory=None, reference=ref,
                        folder_name=ref['name'], created_at=ref.get('created_at'),
                        user_name=ref.get('user_name', ''), note=ref.get('note', ''),
                        status='Missing or unavailable', unavailable=True))
                    continue
                if ref is None and manifest['run_key'] in saved_keys:
                    continue
                status = manifest['status']
                if status == 'prepared' and self.run_dir == directory and self.running():
                    status = 'starting'
                if status == 'running' and (self.run_dir != directory or not self.running()):
                    status = 'unfinished - process state unknown'
                reference = ref or {**manifest['project_binding'], 'software_sha256': manifest['software']['sha256'],
                    'name': manifest['name'], 'created_at': manifest.get('created_at', ''),
                    'user_name': manifest.get('user_name', ''), 'note': manifest.get('note', '')}
                self.run_rows.append(dict(path=directory, memory=None, reference=reference,
                    folder_name=manifest['name'], created_at=manifest.get('created_at'),
                    user_name=reference.get('user_name', ''), note=reference.get('note', ''),
                    status=status.replace('_', ' ').capitalize(), unavailable=False))
            saved_count = len(self.run_rows)
            self.summary.setText(f'Results location: {root}\n{saved_count} saved run reference(s); '
                f'{missing} missing or unavailable. {rejected} unrelated or invalid folder(s) excluded.' + discovery_error)
        for run in self.memory.runs:
            self.run_rows.append(dict(path=None, memory=run, reference=None, folder_name=run.name,
                created_at=run.created, user_name=run.user_name, note=run.note,
                status=run.status.capitalize(), unavailable=False))
        if self.memory.runs:
            used = self.memory.usage() / 1024 ** 2
            self.summary.setText(self.summary.text() +
                f'\n{len(self.memory.runs)} in memory - {used:.1f} MiB of {self.memory.budget / 1024 ** 2:g} MiB')
        self._render_run_rows(previous)

    def _change_date_order(self, *_):
        self._render_run_rows(self.selected_memory_run() or self.selected_path())

    def _render_run_rows(self, previous):
        for row in self.run_rows:
            row['datetime'] = run_datetime(row['created_at'], row['folder_name'])
        # Unknown dates stay last in both directions. Stable identity breaks ties.
        known = [row for row in self.run_rows if row['datetime'] is not None]
        unknown = [row for row in self.run_rows if row['datetime'] is None]
        known.sort(key=lambda row: (row['datetime'].timestamp(), row['folder_name']),
                   reverse=self.date_order.currentIndex() == 0)
        self.run_rows = known + sorted(unknown, key=lambda row: row['folder_name'])
        self.runs.blockSignals(True)
        try:
            self.runs.clear()
            self.run_paths = []
            self.run_refs = []
            self.memory_rows = {}
            selected_row = -1
            for index, row in enumerate(self.run_rows):
                run, path = row['memory'], row['path']
                self.run_paths.append(path)
                self.run_refs.append(row['reference'])
                if run is not None:
                    self.memory_rows[index] = run
                title = display_name(row['user_name'], row['folder_name'])
                if row['unavailable']:
                    title += ' (missing or unavailable)'
                date = row['datetime'].astimezone().strftime('%d %b %Y %H:%M:%S') if row['datetime'] else 'Date unavailable'
                storage = 'In memory' if run is not None else 'Saved'
                note = ' '.join(row['note'].splitlines())
                tooltip = f"{row['folder_name']}\n{path or 'In memory'}\n{row['note']}"
                self.runs.append_run((title, date, storage, row['status'], note), tooltip)
                self.runs.item(index, 4).setToolTip(row['note'])
                if (run is not None and run is previous) or (path is not None and path == previous):
                    selected_row = index
            self.runs.setCurrentRow(selected_row if selected_row >= 0 else (0 if self.run_rows else -1))
        finally:
            self.runs.blockSignals(False)
        self.show_selected()

    def update_run_metadata(self, user_name, note):
        if self.running() or not self.editor._project_editing_allowed():
            return False
        run = self.selected_memory_run()
        if run is not None:
            run.set_metadata(user_name, note)
            selection = run
        else:
            path = self.selected_path()
            if path is None:
                raise ValueError('Select a run to edit its name and note.')
            reference = self.run_refs[self.runs.currentRow()]
            self.editor.project.set_run_metadata(reference['run_key'], user_name, note, directory=path)
            self.sync_metadata_hash()
            selection = path
        self.refresh_runs(select=selection)
        return True

    def edit_run_metadata(self):
        row = self.runs.currentRow()
        if (not 0 <= row < len(self.run_rows) or self.running()
                or not self.editor._project_editing_allowed()):
            return
        entry = self.run_rows[row]
        dialog = QDialog(self)
        dialog.setWindowTitle('Edit run name and note')
        dialog.resize(520, 300)
        form = QFormLayout(dialog)
        name = QLineEdit(entry['user_name'])
        name.setMaxLength(200)
        name.setPlaceholderText(display_name('', entry['folder_name']))
        name.setAccessibleName('Run name')
        note = QPlainTextEdit(entry['note'])
        note.setAccessibleName('Run note')
        form.addRow('Name', name)
        form.addRow('Note', note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        def save():
            try:
                if self.update_run_metadata(name.text(), note.toPlainText()):
                    dialog.accept()
            except Exception as exc:
                QMessageBox.warning(dialog, 'Run details were not saved', str(exc))
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        name.setFocus()
        dialog.exec()
        dialog.deleteLater()

    def selected_path(self):
        row = self.runs.currentRow()
        return self.run_paths[row] if 0 <= row < len(self.run_paths) else None

    def show_selected(self, *_):
        self._update_selection_actions()
        run = self.selected_memory_run()
        row = self.runs.currentRow()
        entry = self.run_rows[row] if 0 <= row < len(self.run_rows) else None
        annotation = (f"Name: {display_name(entry['user_name'], entry['folder_name'])}\n"
            + (f"Note: {entry['note']}\n" if entry['note'] else '') + '\n') if entry else ''
        if run is not None:
            summary = run.evidence['summary']
            self.details.setPlainText(annotation + f'In memory · {run.status}\nFrozen inputs from the editor at run start\n'
                f"Completed tasks: {len(summary['completed_task_ids'])}\nFailed tasks: {len(summary['failed_task_ids'])}\n"
                'Use View utilisation, Playback or Investigation to review. Generate a report directly, or save this run to keep it.')
            return
        path = self.selected_path()
        if path is None:
            self.details.clear()
            return
        try:
            manifest = inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
            binding = manifest['project_binding']
            self.details.setPlainText(annotation + f"Run folder: {path}\nProject: {binding['project_id']}\nRevision: {binding['revision_id']}\n"
                f"Status: {manifest['status']}\nCompleted tasks: {manifest.get('completed_tasks', 'Not recorded')}\n"
                f"Failed tasks: {manifest.get('failed_tasks', 'Not recorded')}\n"
                f"Software fingerprint: {manifest['software']['sha256']}\n{manifest.get('error', '')}")
        except Exception as exc:
            ref = self.run_refs[self.runs.currentRow()]
            reason = ("The run folder or a required run file is missing." if isinstance(exc, FileNotFoundError)
                      else "The run folder cannot be read. Check its access permissions." if isinstance(exc, PermissionError)
                      else str(exc))
            self.details.setPlainText(annotation + f"Run unavailable: {reason}\nSaved folder: {path}\nSaved run identity: {ref['run_key']}\n"
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

    def find_fleet_size(self):
        if self.running():
            return
        if self.editor._history_busy():
            QMessageBox.information(self, 'Finish editing first', 'Finish or close active editing windows before sizing the fleet.')
            return
        if not self.editor._finish_property_draft():
            return
        self.editor._commit_history()
        from visualiser.fleet_sizing_dialog import FleetSizingDialog
        try:
            dialog = FleetSizingDialog(deepcopy(self.editor.store.data), self._source_base(),
                                       self.editor.project, self.memory, self)
        except Exception as exc:
            QMessageBox.critical(self, 'Fleet search could not start', str(exc))
            return
        self.fleet_dialog = dialog
        self.update_start_controls()
        self._update_selection_actions()
        self.editor.sync_project_editing_lock()
        try:
            dialog.exec()
        finally:
            self.fleet_dialog = None
            self.editor.sync_project_editing_lock()
            self.update_start_controls()
            self._update_selection_actions()
            dialog.deleteLater()

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
        if job.kind in ('run', 'prepare'):
            self._start_progress('Preparing simulation')
        self.log.clear()
        job.signals.progress.connect(self._memory_progress)
        job.signals.finished.connect(self._memory_finished)
        self.update_start_controls()
        self._update_selection_actions()
        self.editor.sync_project_editing_lock()
        QThreadPool.globalInstance().start(job)

    @Slot(object)
    def _memory_progress(self, message):
        job = self.memory_job
        if job is None or (self.sender() is not None and self.sender() is not job.signals):
            return
        if job.kind != 'save' and not job.cancelled.is_set():
            self._update_progress(message)
        phase = message.get('phase', '')
        if 'sim_time_sec' in message:
            phase += (f" · {message['sim_time_sec']:,.0f} simulated seconds · "
                      f"{message['completed']:,} complete · {message['failed']:,} failed")
        self.log.appendPlainText(phase)

    def _start_progress(self, label):
        self.progress_estimate = ProgressEstimate()
        self.run_progress.show()
        self.run_progress_text.show()
        self._update_progress(sample('preparing', label))
        self.progress_timer.start()

    def _update_progress(self, message):
        self.progress_estimate.update(message, monotonic())
        self._refresh_progress()

    def _refresh_progress(self):
        percent, remaining, status = self.progress_estimate.display(monotonic())
        self.run_progress.setRange(0, 0 if percent is None else 100)
        if percent is not None:
            self.run_progress.setValue(percent)
        estimate = f'About {format_remaining(remaining)} remaining' if remaining is not None else status
        self.run_progress_text.setText(f'{self.progress_estimate.label} · {estimate}')

    def _end_progress(self, outcome):
        self.progress_timer.stop()
        self.run_progress.setRange(0, 100)
        self.run_progress.setValue(100 if outcome == 'complete' else 0)
        self.run_progress.setVisible(outcome == 'complete')
        self.run_progress_text.setText({'complete': 'Simulation complete', 'partial': 'Simulation stopped — partial results',
                                       'cancelled': 'Simulation cancelled', 'failed': 'Simulation failed'}[outcome])

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
                self._end_progress('cancelled')
                if result is not None:
                    result.dispose()
                self.log.appendPlainText('Memory run cancelled.')
            elif result is None:
                self._end_progress('failed')
                self.log.appendPlainText('Simulation could not start: ' + error)
            else:
                self.progress_timer.stop()
                self.run_progress.hide()
                self.run_progress_text.hide()
                self._check_memory_run(result)
        elif job.kind == 'run':
            if job.cancelled.is_set() or result is None:
                self._end_progress('cancelled' if job.cancelled.is_set() else 'failed')
                run.dispose()
                self.log.appendPlainText('Memory run cancelled.' if job.cancelled.is_set() else f'Memory run failed: {error}')
            else:
                self.memory.add(run)
                self._end_progress(run.status)
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
        self.output_buffer = b''
        self.log.clear()
        self._start_progress('Starting simulation')
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
            self.process.start(str(worker), ['--run-project', str(directory), '--progress-json'])
        else:
            self.process.start(sys.executable, ['-u', str(Path(__file__).resolve().parents[1] / 'amr_project_runs.py'),
                                                str(directory), '--progress-json'])

    def read_output(self, *, final=False):
        if self.process is not None:
            chunk = bytes(self.process.readAllStandardOutput())
            lines = (self.output_buffer + chunk).split(b'\n')
            self.output_buffer = b'' if final else lines.pop()
            output = []
            for raw in lines:
                line = raw.decode('utf-8', errors='replace').rstrip('\r')
                if line.startswith(PREFIX):
                    try:
                        message = json.loads(line[len(PREFIX):])
                        if not isinstance(message, dict) or not isinstance(message.get('phase'), str):
                            raise ValueError('Invalid progress message')
                    except ValueError:
                        output.append(line)
                    else:
                        if not self.cancelled:
                            self._update_progress(message)
                else:
                    output.append(line)
            if output:
                self.log.appendPlainText('\n'.join(output))
            try:
                if chunk:
                    with (self.run_dir / 'process.log').open('ab') as stream:
                        stream.write(chunk)
            except OSError as exc:
                self.log.appendPlainText(f"Could not save process output: {exc}")

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.finished(-1, 'Simulation process could not start')

    def finished(self, code, error=''):
        if self.process is None:
            return
        self.read_output(final=True)
        process, self.process = self.process, None
        try:
            manifest = finish_run(self.run_dir, code, cancelled=self.cancelled, error=error)
            self._end_progress(manifest['status'] if manifest['status'] in ('complete', 'partial', 'cancelled') else 'failed')
            self.log.appendPlainText(f"Run {manifest['status']}. " + manifest.get('error', ''))
        except Exception as exc:
            self._end_progress('failed')
            self.log.appendPlainText(f"Could not record final run status: {exc}")
        process.deleteLater()
        self.editor.sync_project_editing_lock()
        self.update_start_controls()
        self.refresh_runs()

    def stop_run(self):
        if self.fleet_dialog is not None:
            self.fleet_dialog.cancel_search()
        elif self.process is not None:
            self.cancelled = True
            self._update_progress(sample('stopping', 'Stopping simulation'))
            self.process.kill()
        elif self.memory_job is not None and self.memory_job.kind != 'save':
            self.memory_job.cancelled.set()
            self._update_progress(sample('stopping', 'Stopping simulation'))
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
            self.set_investigation_sources()
            self.editor.results_panel.load(run)
            return
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_results_investigation()
                self.set_investigation_sources()
                self.editor.results_panel.load(str(path))
            except Exception as exc:
                QMessageBox.critical(self, "Run unavailable", str(exc))

    def view_utilisation(self):
        run = self.selected_memory_run()
        if run is None or run.status != 'complete' or self.running():
            return
        from visualiser.run_utilisation_dialog import RunUtilisationDialog
        dialog = RunUtilisationDialog(run, self, cached=self.utilisation_cache.get(run.key))
        dialog.exec()
        if dialog.result_data is not None and run in self.memory.runs:
            self.utilisation_cache[run.key] = dialog.result_data
        dialog.deleteLater()

    def set_investigation_sources(self):
        sources = [(f'{display_name(run.user_name, run.name)} · In memory', run)
                   for run in reversed(self.memory.runs)]
        for path in self.run_paths:
            if path is None:
                continue
            try:
                manifest = read_json(path / MANIFEST)
            except (OSError, ValueError):
                continue
            if manifest.get('status') in ('complete', 'partial'):
                reference = next((ref for ref in self.run_refs if ref and ref['run_key'] == manifest['run_key']), {})
                title = display_name(reference.get('user_name', ''), manifest['name'])
                sources.append((f'{title} · Saved', path))
        self.editor.results_panel.set_comparison_sources(sources)

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
        run = self.selected_memory_run()
        if run is not None:
            try:
                self.editor.show_project_report(run)
            except Exception as exc:
                QMessageBox.critical(self, 'Report unavailable', str(exc))
            return
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_project_report(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Report unavailable', str(exc))
