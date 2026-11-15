"""Report generation remains external and bound to the selected run."""
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import Qt, QProcess, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QPlainTextEdit, QMessageBox, QLineEdit, QFileDialog, QSpinBox, QFormLayout,
    QDialog, QDialogButtonBox, QComboBox)
from amr_project_runs import inspect_run, read_json, validate_run_inputs
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
        self.contingency_study = None
        self._stress_request = None
        self.third_party_target = None
        self.third_party_all = False
        self.third_party_excel = False
        self.lift_charts_target = None
        self.baseline_run = None
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
        self.export_third_party = QPushButton('Export third-party lifts…')
        self.export_third_party.setToolTip('Export all lift trips to an Excel table with a concatenation formula, or choose the existing CSV formats.')
        self.export_third_party.setEnabled(False)
        self.export_third_party.clicked.connect(self.generate_third_party)
        layout.addWidget(self.export_third_party)
        self.export_lift_charts = QPushButton('Export stacked lift charts (Excel)…')
        self.export_lift_charts.setToolTip('One editable stacked purpose chart per lift, with a day dropdown on each sheet. Uses this run’s saved events.')
        self.export_lift_charts.setEnabled(False)
        self.export_lift_charts.clicked.connect(self.generate_lift_charts)
        layout.addWidget(self.export_lift_charts)
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
        chart_controls = QHBoxLayout()
        self.lift_chart_day = QComboBox()
        self.lift_chart_day.setEditable(True)
        self.lift_chart_day.addItem('All days')
        self.lift_chart_day.setAccessibleName('Stacked lift chart day')
        self.lift_chart_day.setToolTip('All days combines counts in the overview and Excel. The daily PDF section shows each day separately. Choose a date to restrict PDF charts and set the initial Excel view.')
        self.lift_chart_interval = QComboBox()
        self.lift_chart_interval.setAccessibleName('Stacked lift chart interval')
        for minutes in (5,15,30,60):
            self.lift_chart_interval.addItem(f'{minutes} min',minutes)
        self.lift_chart_interval.setCurrentIndex(2)
        self.lift_chart_include = QCheckBox('Empty repositioning')
        self.lift_chart_include.setChecked(True)
        for control in (self.lift_chart_day,self.lift_chart_interval,self.lift_chart_include):
            chart_controls.addWidget(control)
        form.addRow('Stacked lift charts', chart_controls)
        self.lift_chart_pdf_lift = QComboBox()
        self.lift_chart_pdf_lift.addItem('All lifts',None)
        self.lift_chart_pdf_lift.setAccessibleName('PDF chart lift')
        self.lift_chart_pdf_lift.setToolTip('Choose all lifts or one lift for both PDF chart sections. Excel always retains every lift.')
        form.addRow('PDF chart lift',self.lift_chart_pdf_lift)
        baseline_row = QHBoxLayout()
        self.baseline_label = QLabel('No baseline selected')
        self.baseline_label.setWordWrap(True)
        self.choose_baseline = QPushButton('Choose baseline run…')
        self.choose_baseline.setEnabled(False)
        self.choose_baseline.setToolTip('Select the folder for a completed baseline run.')
        self.choose_baseline.clicked.connect(self.browse_baseline)
        baseline_row.addWidget(self.baseline_label, 1)
        baseline_row.addWidget(self.choose_baseline)
        form.addRow('Performance baseline', baseline_row)
        layout.addLayout(form)
        note = QLabel('Insert selected sections as a supplement with its own title, linked contents and numbering. Existing pages are reused; the combined PDF is saved as a new report.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.sections = QListWidget()
        self.sections.setAccessibleName('Report sections to include')
        for key, title in report_sections():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, key)
            if key == 'lift_movement_daily':
                item.setToolTip('One chart per lift per observation day. Use All days for every date, or choose one date. The PDF chart lift selector limits which lifts appear.')
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if key in ('stress_tests', 'human_contingency', 'lift_movement_stacks',
                'lift_movement_daily', 'lift_performance_comparison') else Qt.Checked)
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
        self.choose_contingency = QPushButton('Select human contingency study for PDF…')
        self.choose_contingency.clicked.connect(self.select_contingency)
        layout.addWidget(self.choose_contingency)
        self.drawings = QCheckBox('Include frozen drawing underlays in heatmaps')
        layout.addWidget(self.drawings)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)

    def select_contingency(self):
        if self.running():
            return
        name, _ = QFileDialog.getOpenFileName(self, 'Human contingency evidence', '', 'Study (*.json)')
        if name:
            from amr_contingency_study import load_study
            try:
                load_study(name)
                self.contingency_study = name
                self.choose_contingency.setText('Human contingency: ' + Path(name).name)
                for i in range(self.sections.count()):
                    if self.sections.item(i).data(Qt.UserRole) == 'human_contingency':
                        self.sections.item(i).setCheckState(Qt.Checked)
            except Exception as exc:
                self.log.setPlainText(str(exc))

    def running(self):
        return self.process is not None

    def lift_chart_arguments(self):
        arguments = ['--lift-chart-bin-minutes',str(self.lift_chart_interval.currentData())]
        day = self.lift_chart_day.currentText().strip()
        if day and day != 'All days':
            arguments += ['--lift-chart-day',day]
        if not self.lift_chart_include.isChecked():
            arguments.append('--lift-chart-exclude-reposition')
        return arguments

    @Slot()
    def generate_lift_charts(self):
        if self.running() or self.run_dir is None:
            return
        try:
            if self.editor.project is not self._requested_editor_project:
                raise ValueError('Select a run again after changing projects.')
            inspect_run(self.run_dir,self._run_project)
        except Exception as exc:
            QMessageBox.warning(self,'Run unavailable',str(exc))
            return
        target,_ = QFileDialog.getSaveFileName(self,'Export stacked lift charts',
            str(self.run_dir/'reports'/'lift-movement-charts.xlsx'),'Excel workbook (*.xlsx)')
        if not target:
            return
        if Path(target).suffix.lower() != '.xlsx':
            target += '.xlsx'
        self.lift_charts_target = Path(target).resolve()
        self.cancelled = False
        self.log.clear()
        self.log.appendPlainText('Exporting per-lift stacked purpose charts from the saved run…')
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(lambda code,_status:self.finished(code))
        self.process.errorOccurred.connect(self.process_error)
        for control in (self.start,self.choose_stress,self.export_lifts,self.export_third_party,self.export_lift_charts):
            control.setEnabled(False)
        self.stop.setEnabled(True)
        args = [str(self.run_dir),'--lift-charts-xlsx',str(self.lift_charts_target),*self.lift_chart_arguments()]
        if getattr(sys,'frozen',False):
            executable = str(Path(sys.executable).with_name('AMRSimulatorWorker.exe'))
        else:
            executable = sys.executable
            args = ['-u',str(Path(__file__).resolve().parents[1]/'amr_app.py'),*args]
        self.process.start(executable,args)

    def generate_third_party(self):
        if self.running() or self.run_dir is None:
            return
        try:
            if self.editor.project is not self._requested_editor_project:
                raise ValueError('Select a run again after changing projects.')
            config = read_json(self.run_dir / 'config.json')
            lifts = [row['id'] for row in config.get('lifts', [])]
            if not lifts:
                raise ValueError('This saved run has no configured lifts.')
        except Exception as exc:
            QMessageBox.warning(self, 'Run unavailable', str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Third-party lift export')
        form = QFormLayout(dialog)
        selector = QComboBox()
        for identity in lifts:
            selector.addItem(identity, identity)
        workbook_index = selector.count()
        selector.addItem('All lifts and trips — Excel table (.xlsx)', 'xlsx')
        selector.addItem('All lifts — separate CSV files', None)
        selector.setAccessibleName('Lift export format and scope')
        include = QCheckBox('Include empty reposition trips')
        def update_scope():
            excel = selector.currentIndex() == workbook_index
            include.setChecked(excel)
            include.setEnabled(not excel)
        selector.currentIndexChanged.connect(update_scope)
        update_scope()
        form.addRow('Export', selector)
        form.addRow(include)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        excel = selector.currentIndex() == workbook_index
        all_lifts = selector.currentData() is None and not excel
        if excel:
            target, _ = QFileDialog.getSaveFileName(self, 'Export all lift trips to Excel',
                str(self.run_dir / 'reports' / 'lift-trips.xlsx'), 'Excel workbook (*.xlsx)')
            if target and Path(target).suffix.lower() != '.xlsx':
                target += '.xlsx'
        elif all_lifts:
            folder = QFileDialog.getExistingDirectory(self, 'Choose folder for all third-party lift CSVs', str(self.run_dir))
            target = str(Path(folder) / ('third-party-lifts-' + uuid.uuid4().hex[:12])) if folder else ''
        else:
            target, _ = QFileDialog.getSaveFileName(self, 'Export third-party lift CSV',
                str(self.run_dir / 'reports' / 'third-party-lift.csv'), 'CSV (*.csv)')
        if not target:
            return
        self.third_party_target = Path(target).resolve()
        self.third_party_all = all_lifts
        self.third_party_excel = excel
        self.cancelled = False
        self.log.clear()
        self.log.appendPlainText('Exporting recorded lift movements using this run’s saved inputs…')
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(lambda code, _status: self.finished(code))
        self.process.errorOccurred.connect(self.process_error)
        self.start.setEnabled(False)
        self.choose_stress.setEnabled(False)
        self.export_lifts.setEnabled(False)
        self.export_third_party.setEnabled(False)
        self.export_lift_charts.setEnabled(False)
        self.stop.setEnabled(True)
        if excel:
            args = [str(self.run_dir), '--third-party-lift-xlsx', str(self.third_party_target)]
        elif all_lifts:
            args = [str(self.run_dir), '--third-party-lifts-dir', str(self.third_party_target)]
        else:
            args = [str(self.run_dir), '--third-party-lift-csv', str(self.third_party_target),
                    '--lift-id', selector.currentData()]
        if include.isChecked() and not excel:
            args.append('--include-lift-reposition')
        if getattr(sys, 'frozen', False):
            executable = str(Path(sys.executable).with_name('AMRSimulatorWorker.exe'))
        else:
            executable = sys.executable
            args = ['-u', str(Path(__file__).resolve().parents[1] / 'amr_app.py'), *args]
        self.process.start(executable, args)

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

    def browse_baseline(self):
        if self.running() or self.run_dir is None:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Select completed baseline run folder', str(self.run_dir.parent))
        if folder:
            try:
                self.set_baseline(folder)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, 'Baseline unavailable', str(error))

    def set_baseline(self, path):
        if path is not None:
            path = Path(path).resolve()
            if self.run_dir is None or path == self.run_dir:
                raise ValueError('Choose a different completed run as the baseline.')
            manifest, _ = validate_run_inputs(path, verify_drawings=False)
            if manifest['status'] != 'complete' or manifest['project_binding']['run_key'] == self.binding['run_key']:
                raise ValueError('Choose a different completed run as the baseline.')
        self.baseline_run = path
        self.baseline_label.setText(path.name if path else 'No baseline selected')
        self.baseline_label.setToolTip(str(path) if path else '')
        for index in range(self.sections.count()):
            item = self.sections.item(index)
            if item.data(Qt.UserRole) == 'lift_performance_comparison':
                item.setCheckState(Qt.Checked if path else Qt.Unchecked)
                break

    def set_run(self, path):
        if self.running():
            raise ValueError('Wait for this report to finish or stop it before selecting another run.')
        project=getattr(self,'_study_context',None) or self.editor.project
        self._study_context=None
        manifest = inspect_run(path, project)
        if manifest['status'] != 'complete':
            raise ValueError('Choose a completed run for report generation.')
        if getattr(self, '_run_project', None) is not project or self.baseline_run == Path(path).resolve():
            self.set_baseline(None)
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
        self.export_third_party.setEnabled(True)
        self.export_lift_charts.setEnabled(True)
        self.choose_baseline.setEnabled(True)
        config = read_json(self.run_dir/'config.json')
        self.lift_chart_pdf_lift.clear()
        self.lift_chart_pdf_lift.addItem('All lifts',None)
        for identity in sorted({str(lift['id']) for lift in config.get('lifts',[]) if lift.get('id')}):
            self.lift_chart_pdf_lift.addItem(identity,identity)
        self.lift_chart_day.clear()
        self.lift_chart_day.addItem('All days')
        from datetime import datetime,timedelta
        try:
            start = datetime.fromisoformat(config['simulation']['start_datetime']).date()
            end = datetime.fromisoformat(config['simulation']['end_datetime']).date()
            for i in range(min(3661,(end-start).days+1)):
                self.lift_chart_day.addItem((start+timedelta(days=i)).isoformat())
        except (KeyError,TypeError,ValueError):
            pass
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
        if 'human_contingency' in sections and not lift_cohorts_only and not self.contingency_study:
            self.log.setPlainText('Select a human contingency study for the PDF, or untick Human contingency staffing.')
            return
        if 'stress_tests' in sections and not lift_cohorts_only and not self.stress_selection:
            self.log.setPlainText('Choose trials using Select stress tests for PDF, or untick Stress-test comparison.')
            return
        if 'lift_performance_comparison' in sections and not lift_cohorts_only and self.baseline_run is None:
            self.log.setPlainText('Choose a baseline run, or untick Lift preference performance comparison.')
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
        self.choose_baseline.setEnabled(False)
        self.export_lifts.setEnabled(False)
        self.export_third_party.setEnabled(False)
        self.export_lift_charts.setEnabled(False)
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
        if 'lift_performance_comparison' in sections and not lift_cohorts_only:
            args.extend(['--comparison-baseline', str(self.baseline_run)])
        if {'lift_movement_stacks','lift_movement_daily'} & set(sections) and not lift_cohorts_only:
            args.extend(self.lift_chart_arguments())
            if self.lift_chart_pdf_lift.currentData() is not None:
                args.extend(['--lift-chart-lift-id',self.lift_chart_pdf_lift.currentData()])
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
        if 'human_contingency' in sections and not lift_cohorts_only:
            args.extend(['--contingency-study', self.contingency_study])
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
        self.choose_baseline.setEnabled(self.run_dir is not None)
        self.export_lifts.setEnabled(True)
        self.export_third_party.setEnabled(True)
        self.export_lift_charts.setEnabled(True)
        self.stop.setEnabled(False)
        if self.lift_charts_target is not None:
            target,self.lift_charts_target = self.lift_charts_target,None
            if code == 0 and not self.cancelled and target.is_file():
                self.lift_csv = target
                self.open_lift_csv.setText('Open lift chart workbook')
                self.open_lift_csv.setEnabled(True)
                self.log.appendPlainText(f'Lift chart workbook complete: {target}')
            else:
                self.log.appendPlainText('Lift chart export stopped or failed; existing completed output was retained.')
            return
        if self.third_party_target is not None:
            target, self.third_party_target = self.third_party_target, None
            all_lifts, self.third_party_all = self.third_party_all, False
            excel, self.third_party_excel = self.third_party_excel, False
            exists = target.is_dir() if all_lifts else target.is_file()
            if code == 0 and not self.cancelled and exists:
                self.lift_csv = target
                self.open_lift_csv.setText('Open lift Excel table' if excel else 'Open lift export folder' if all_lifts else 'Open lift CSV')
                self.open_lift_csv.setEnabled(True)
                self.log.appendPlainText(f'Third-party lift export complete: {target}')
            else:
                self.log.appendPlainText('Lift export stopped or failed; existing completed output was retained.')
            return
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
            self.open_lift_csv.setText('Open lift usage CSV')
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
