"""Report generation remains external and bound to the selected run."""
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import Qt, QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QPlainTextEdit, QMessageBox, QLineEdit, QFileDialog, QSpinBox, QFormLayout)
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
        self.export_only = False
        self.lift_csv = None
        self.stress_selection = []
        self._stress_request = None
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
        csv_controls = QHBoxLayout()
        self.export_lifts = QPushButton('Export 5-minute lift usage CSV')
        self.export_lifts.setToolTip('Export the existing five-minute and hourly per-lift trip and travel tables without generating a PDF.')
        self.export_lifts.setEnabled(False)
        self.export_lifts.clicked.connect(lambda: self.generate(lift_cohorts_only=True))
        self.open_lift_csv = QPushButton('Open lift usage CSV')
        self.open_lift_csv.setEnabled(False)
        self.open_lift_csv.clicked.connect(self.open_csv_result)
        csv_controls.addWidget(self.export_lifts)
        csv_controls.addWidget(self.open_lift_csv)
        csv_controls.addStretch(1)
        layout.addLayout(csv_controls)
        form = QFormLayout()
        self.report_title = QLineEdit()
        self.report_title.setPlaceholderText('Default report title')
        form.addRow('Report title', self.report_title)
        self.existing_pdf = QLineEdit()
        self.existing_pdf.setPlaceholderText('Optional existing PDF to insert into')
        insert_row = QHBoxLayout()
        insert_row.addWidget(self.existing_pdf, 1)
        browse = QPushButton('Browse PDF...')
        def choose_existing():
            filename, _ = QFileDialog.getOpenFileName(self, 'Existing report PDF', self.existing_pdf.text(), 'PDF files (*.pdf)')
            if filename:
                self.existing_pdf.setText(filename)
        browse.clicked.connect(choose_existing)
        insert_row.addWidget(browse)
        form.addRow('Existing PDF', insert_row)
        self.insert_page = QSpinBox()
        self.insert_page.setRange(-1, 1000000)
        self.insert_page.setSpecialValueText('Append to end')
        self.insert_page.setValue(-1)
        form.addRow('Insert after page (0 = before first)', self.insert_page)
        layout.addLayout(form)
        note = QLabel('Insert selected sections as a supplement with its own title, linked contents and numbering. Existing pages are reused; the combined PDF is saved as a new report.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.sections = QListWidget()
        self.sections.setAccessibleName('Report sections to include')
        for key, title in report_sections():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if key == 'stress_tests' else Qt.Checked)
            self.sections.addItem(item)
        layout.addWidget(self.sections, 1)
        stress_controls = QHBoxLayout()
        self.choose_stress = QPushButton('Select stress tests for PDF…')
        self.choose_stress.clicked.connect(lambda: self.select_stress_tests())
        self.stress_summary = QLabel('No stress tests selected.')
        self.stress_summary.setWordWrap(True)
        stress_controls.addWidget(self.choose_stress)
        stress_controls.addWidget(self.stress_summary, 1)
        layout.addLayout(stress_controls)
        self.drawings = QCheckBox('Include frozen drawing underlays in heatmaps')
        layout.addWidget(self.drawings)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)

    def running(self):
        return self.process is not None

    def set_stress_selection(self, selection):
        if self.running():
            raise ValueError('Wait for report generation to finish before changing stress-test selections.')
        from amr_stress_report import normalise_selection
        self.stress_selection = normalise_selection(selection) if selection else []
        count = sum(len(item['trial_ids']) for item in self.stress_selection)
        self.stress_summary.setText(f'{count} trials from {len(self.stress_selection)} studies; baselines included.'
                                    if count else 'No stress tests selected.')
        for index in range(self.sections.count()):
            item = self.sections.item(index)
            if item.data(Qt.UserRole) == 'stress_tests':
                item.setCheckState(Qt.Checked if count else Qt.Unchecked)

    def select_stress_tests(self, known=()):
        if self.running():
            return
        from stress_report_selection import StressReportSelectionDialog
        dialog = StressReportSelectionDialog(self.editor, self.stress_selection, known, parent=self)
        if dialog.exec() == dialog.Accepted:
            self.set_stress_selection(dialog.selection())
        dialog.deleteLater()

    def set_run(self, path):
        if self.running():
            raise ValueError('Wait for this report to finish or stop it before selecting another run.')
        project=getattr(self,'_study_context',None) or self.editor.project
        self._study_context=None
        manifest = inspect_run(path, project)
        if manifest['status'] != 'complete':
            raise ValueError('Choose a completed run for report generation.')
        if getattr(self, '_requested_editor_project', self.editor.project) is not self.editor.project:
            self.set_stress_selection([])
        self.run_dir = Path(path).resolve()
        self.binding = manifest['project_binding']
        self._run_project=project;self._requested_editor_project=self.editor.project
        self.pdf = None
        self.lift_csv = None
        self.open_pdf.setEnabled(False)
        self.open_lift_csv.setEnabled(False)
        self.start.setEnabled(True)
        self.export_lifts.setEnabled(True)
        self.summary.setText(f"Run: {self.run_dir.name}\nRevision: {manifest['project_binding']['revision_id']}\n"
                             'Uses frozen inputs and recorded events. Outputs are saved under this run’s external reports folder.')

    def generate(self, lift_cohorts_only=False):
        if self.running() or self.run_dir is None:
            return
        sections = [self.sections.item(i).data(Qt.UserRole) for i in range(self.sections.count())
                    if self.sections.item(i).checkState() == Qt.Checked]
        if not sections and not lift_cohorts_only:
            self.log.setPlainText('Select at least one report section.')
            return
        if 'stress_tests' in sections and not lift_cohorts_only and not self.stress_selection:
            self.log.setPlainText('Choose trials using Select stress tests for PDF, or untick Stress-test comparison.')
            return
        try:
            if self.editor.project is not self._requested_editor_project:raise ValueError('Select a run again after changing projects.')
            inspect_run(self.run_dir, self._run_project)
        except Exception as exc:
            QMessageBox.warning(self, 'Run unavailable', str(exc))
            return
        self.output = self.run_dir / 'reports' / ('report_' + uuid.uuid4().hex[:12])
        self._stress_request = None
        if 'stress_tests' in sections and not lift_cohorts_only:
            from amr_project_runs import write_json
            try:
                self.output.parent.mkdir(parents=True, exist_ok=True)
                self._stress_request = self.output.with_suffix('.stress-selection.json')
                write_json(self._stress_request, self.stress_selection)
            except (OSError, ValueError) as exc:
                self.log.setPlainText('Could not save the stress-test selection: ' + str(exc))
                return
        self.export_only = lift_cohorts_only
        self.cancelled = False
        self.pdf = None
        self.open_pdf.setEnabled(False)
        self.lift_csv = None
        self.open_lift_csv.setEnabled(False)
        self.log.clear()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(lambda code, _status: self.finished(code))
        self.process.errorOccurred.connect(self.process_error)
        self.start.setEnabled(False)
        self.choose_stress.setEnabled(False)
        self.export_lifts.setEnabled(False)
        self.stop.setEnabled(True)
        if getattr(sys, 'frozen', False):
            executable = str(Path(sys.executable).with_name('AMRSimulatorWorker.exe'))
            args = ['--generate-report', str(self.run_dir), str(self.output), '--sections', ','.join(sections)]
        else:
            executable = sys.executable
            args = ['-u', str(Path(__file__).resolve().parents[1] / 'amr_project_report.py'),
                    str(self.run_dir), str(self.output), '--sections', ','.join(sections)]
        if lift_cohorts_only:
            args.append('--lift-cohorts-only')
        if self.drawings.isChecked() and not lift_cohorts_only:
            args.append('--drawings')
        if self.existing_pdf.text().strip() and not lift_cohorts_only:
            args.extend(['--existing-pdf', self.existing_pdf.text().strip()])
            if self.insert_page.value() >= 0:
                args.extend(['--insert-after-page', str(self.insert_page.value())])
        if self.report_title.text().strip() and not lift_cohorts_only:
            args.extend(['--report-title', self.report_title.text().strip()])
        if self._stress_request is not None and not lift_cohorts_only:
            args.extend(['--stress-selection', str(self._stress_request)])
        self.process.start(executable, args)

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
        self.choose_stress.setEnabled(True)
        self.export_lifts.setEnabled(True)
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
            csv_path = self.output / 'report_lift_cohorts.csv'
            if file_hash(csv_path) != manifest['lift_cohorts_sha256']:
                raise ValueError('Lift usage CSV does not match its recorded checksum.')
            self.lift_csv = csv_path
            self.open_lift_csv.setEnabled(True)
            self.log.appendPlainText(f'Five-minute and hourly lift usage CSV complete: {csv_path}')
            if self.export_only:
                return
            path = self.output / 'report.pdf'
            if file_hash(path) != manifest['pdf_sha256']:
                raise ValueError('Report file does not match its recorded checksum.')
            self.pdf = path
            self.open_pdf.setEnabled(True)
            self.log.appendPlainText(f'Report complete: {path}')
        except Exception as exc:
            self.log.appendPlainText(f'Report not complete: {exc}')
        finally:
            if self._stress_request is not None:
                try:
                    self._stress_request.unlink(missing_ok=True)
                except OSError as exc:
                    self.log.appendPlainText('Could not remove the temporary selection file: ' + str(exc))
                self._stress_request = None

    def cancel(self):
        if self.process is not None:
            self.cancelled = True
            self.process.kill()

    def open_result(self):
        if self.pdf is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pdf)))

    def open_csv_result(self):
        if self.lift_csv is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.lift_csv)))
