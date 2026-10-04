"""Saved project → checked external simulation → results investigation."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QPlainTextEdit, QFileDialog, QMessageBox, QDialog
from project_checks_panel import RunChecksDialog
from amr_project_runs import PreparedRun, inspect_run, finish_run, read_json, MANIFEST, link_run


class ProjectRunsPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.process = None
        self.run_dir = None
        self.cancelled = False
        self.run_paths = []
        self.run_refs = []
        layout = QVBoxLayout(self)
        self.summary = QLabel("Save a project to start a revision-bound simulation.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Save, check and simulate")
        self.start_button.clicked.connect(self.start_run)
        self.stop_button = QPushButton("Stop run")
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        for control in (self.start_button, self.stop_button):
            buttons.addWidget(control)
        layout.addLayout(buttons)
        actions = QHBoxLayout()
        for title, handler in (("Refresh runs", self.refresh_runs), ("Results location…", self.choose_results_root),
                               ("Locate moved run…", self.relink_run), ("Investigate selected run", self.investigate),
                               ("Playback selected run", self.playback),
                               ("Report selected run", self.report)):
            button = QPushButton(title)
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.runs = QListWidget()
        self.runs.setAccessibleName("Runs belonging to this project's saved revisions")
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
        return self.process is not None

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

    def refresh_runs(self):
        self.runs.clear()
        self.run_paths = []
        self.run_refs = []
        self.details.clear()
        project = self.editor.project
        if project is None:
            self.summary.setText("Save as an AMR project to link simulations to saved revisions.")
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
        self.summary.setText(f"Results location: {root}\n{len(self.run_paths)} run reference(s); {missing} missing or unavailable. "
                             f"{rejected} unrelated or invalid folder(s) excluded. New runs, location choices and relinks are saved in the project; outputs stay external."
                             + discovery_error)

    def selected_path(self):
        row = self.runs.currentRow()
        return self.run_paths[row] if 0 <= row < len(self.run_paths) else None

    def show_selected(self, *_):
        path = self.selected_path()
        if path is None:
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
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.editor.sync_project_editing_lock()
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
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.refresh_runs()

    def stop_run(self):
        if self.process is not None:
            self.cancelled = True
            self.process.kill()

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
        row = self.runs.currentRow()
        expected = self.run_refs[row]['run_key'] if 0 <= row < len(self.run_refs) else None
        path = QFileDialog.getExistingDirectory(self, "Locate moved run folder")
        if path:
            try:
                self.link_run(path, expected_run_key=expected)
            except Exception as exc:
                QMessageBox.critical(self, "Run could not be linked", str(exc))

    def investigate(self):
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_results_investigation()
                self.editor.results_panel.load(str(path))
            except Exception as exc:
                QMessageBox.critical(self, "Run unavailable", str(exc))

    def playback(self):
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_project_playback(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Playback unavailable', str(exc))

    def report(self):
        path = self.selected_path()
        if path:
            try:
                inspect_run(path, self.editor.project, reference=self.run_refs[self.runs.currentRow()])
                self.editor.show_project_report(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Report unavailable', str(exc))
