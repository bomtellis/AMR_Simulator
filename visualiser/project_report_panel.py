"""Report generation remains external and bound to the selected run."""
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import Qt, QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QPlainTextEdit, QMessageBox)
from amr_project_runs import inspect_run, read_json
from amr_project_report import report_sections


class ProjectReportPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.run_dir = None
        self.output = None
        self.process = None
        self.pdf = None
        self.cancelled = False
        self.binding = None
        layout = QVBoxLayout(self)
        self.summary = QLabel('Select a completed run in Simulate, then choose Report selected run. Reports use its frozen inputs, not current edits.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        controls = QHBoxLayout()
        choose = QPushButton('Choose run in Simulate')
        choose.clicked.connect(editor.show_project_runs)
        self.start = QPushButton('Generate report')
        self.start.clicked.connect(self.generate)
        self.start.setEnabled(False)
        self.stop = QPushButton('Stop generation')
        self.stop.clicked.connect(self.cancel)
        self.stop.setEnabled(False)
        self.open_pdf = QPushButton('Open generated PDF')
        self.open_pdf.clicked.connect(self.open_result)
        self.open_pdf.setEnabled(False)
        for button in (choose, self.start, self.stop, self.open_pdf):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.sections = QListWidget()
        self.sections.setAccessibleName('Report sections to include')
        for key, title in report_sections():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.sections.addItem(item)
        layout.addWidget(self.sections, 1)
        self.drawings = QCheckBox('Include frozen drawing underlays in heatmaps')
        layout.addWidget(self.drawings)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)

    def running(self):
        return self.process is not None

    def set_run(self, path):
        if self.running():
            raise ValueError('Wait for this report to finish or stop it before selecting another run.')
        manifest = inspect_run(path, self.editor.project)
        if manifest['status'] != 'complete':
            raise ValueError('Choose a completed run for report generation.')
        self.run_dir = Path(path).resolve()
        self.binding = manifest['project_binding']
        self.pdf = None
        self.open_pdf.setEnabled(False)
        self.start.setEnabled(True)
        self.summary.setText(f"Run: {self.run_dir.name}\nRevision: {manifest['project_binding']['revision_id']}\n"
                             'Uses frozen inputs and recorded events. Outputs are saved under this run’s external reports folder.')

    def generate(self):
        if self.running() or self.run_dir is None:
            return
        sections = [self.sections.item(i).data(Qt.UserRole) for i in range(self.sections.count())
                    if self.sections.item(i).checkState() == Qt.Checked]
        if not sections:
            self.log.setPlainText('Select at least one report section.')
            return
        try:
            inspect_run(self.run_dir, self.editor.project)
        except Exception as exc:
            QMessageBox.warning(self, 'Run unavailable', str(exc))
            return
        self.output = self.run_dir / 'reports' / ('report_' + uuid.uuid4().hex[:12])
        self.cancelled = False
        self.pdf = None
        self.open_pdf.setEnabled(False)
        self.log.clear()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(lambda code, _status: self.finished(code))
        self.process.errorOccurred.connect(self.process_error)
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        args = ['-u', str(Path(__file__).resolve().parents[1] / 'amr_project_report.py'),
                str(self.run_dir), str(self.output), '--sections', ','.join(sections)]
        if self.drawings.isChecked():
            args.append('--drawings')
        self.process.start(sys.executable, args)

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.finished(-1)

    def read_output(self):
        if self.process is not None:
            self.log.appendPlainText(bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace').rstrip())

    def finished(self, code):
        if self.process is None:
            return
        self.read_output()
        process, self.process = self.process, None
        process.deleteLater()
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        try:
            from amr_project_runs import write_json, timestamp
            if not (self.output / 'report_manifest.json').exists():
                self.output.mkdir(parents=True, exist_ok=True)
                write_json(self.output / 'report_manifest.json', dict(status='cancelled' if self.cancelled else 'failed',
                    project_binding=self.binding, completed_at=timestamp(), error='Generation ended before a report was produced.'))
            (self.output / 'process.log').write_text(self.log.toPlainText(), encoding='utf-8')
            manifest = read_json(self.output / 'report_manifest.json')
            if code != 0 or self.cancelled or manifest['status'] != 'complete':
                if manifest['status'] != 'complete':
                    manifest.update(status='cancelled' if self.cancelled else 'failed', completed_at=timestamp())
                    write_json(self.output / 'report_manifest.json', manifest)
                raise ValueError('Generation stopped or failed. Partial files are not a completed report.')
            from amr_run_evidence import file_hash
            path = self.output / 'report.pdf'
            if file_hash(path) != manifest['pdf_sha256']:
                raise ValueError('Report file does not match its recorded checksum.')
            self.pdf = path
            self.open_pdf.setEnabled(True)
            self.log.appendPlainText(f'Report complete: {path}')
        except Exception as exc:
            self.log.appendPlainText(f'Report not complete: {exc}')

    def cancel(self):
        if self.process is not None:
            self.cancelled = True
            self.process.kill()

    def open_result(self):
        if self.pdf is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pdf)))
