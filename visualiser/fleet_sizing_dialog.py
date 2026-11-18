"""Find a passing fleet boundary without saving trials or changing the editor."""
from copy import deepcopy
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QProgressBar, QTableWidgetItem)

from amr_fleet_sizing import search_fleet
from visualiser.demand_preview_panel import DemandPreviewPanel
from visualiser.project_checks_panel import RunChecksDialog


class SizingSignals(QObject):
    progress = Signal(object)
    finished = Signal(object, str)


class SizingJob(QRunnable):
    def __init__(self, kind, action):
        super().__init__()
        self.kind, self.action = kind, action
        self.cancelled = Event()
        self.signals = SizingSignals()

    def run(self):
        result, error = None, ''
        try:
            result = self.action(self.cancelled.is_set, self.signals.progress.emit)
        except Exception as exc:
            error = str(exc)
        self.action = None
        self.signals.finished.emit(result, error)


class FleetSizingDialog(QDialog):
    def __init__(self, config, base_dir, project, memory, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Find AMR fleet size')
        self.resize(860, 620)
        self.config = deepcopy(config)
        self.base_dir, self.project, self.memory = base_dir, project, memory
        self.job = None
        self.draft = None
        self.result_data = None
        self.close_when_stopped = False
        layout = QVBoxLayout(self)
        intro = QLabel('Find the smallest passing count for one AMR type. Other AMR types stay at their current quantities.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.amr_type = QComboBox()
        self.amr_type.setAccessibleName('AMR type to size')
        for robot in config.get('amrs', []):
            self.amr_type.addItem(robot['id'])
        form.addRow('AMR &type', self.amr_type)
        self.target = QDoubleSpinBox()
        self.target.setRange(.1, 100)
        self.target.setDecimals(1)
        self.target.setSuffix(' %')
        self.target.setValue(75)
        self.target.setAccessibleName('AMR target utilisation percentage')
        self.target.setToolTip('Reference only. The recommendation uses task failures, regardless of utilisation.')
        form.addRow('Target &utilisation (reference)', self.target)
        self.start_count = QSpinBox()
        self.start_count.setRange(0, 100000)
        self.start_count.setAccessibleName('Starting AMR count')
        form.addRow('&Starting count', self.start_count)
        self.max_count = QSpinBox()
        self.max_count.setRange(0, 100000)
        self.max_count.setAccessibleName('Maximum AMR count to try')
        form.addRow('&Maximum count to try', self.max_count)
        layout.addLayout(form)
        self.fixed = QLabel()
        self.fixed.setWordWrap(True)
        layout.addWidget(self.fixed)
        help_text = QLabel('Each trial runs in memory and stops immediately at its first task failure. '
            'A passing count is reduced one at a time until a task fails. If the starting count fails, '
            'counts increase one at a time up to the maximum. Utilisation is shown for reference; '
            'the smallest passing tested count is recommended regardless of the target.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.status = QLabel('Ready. Trials use the current editor inputs and configured simulation period.')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Fleet search status and recommendation')
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName('Fleet size search progress')
        self.progress.hide()
        layout.addWidget(self.progress)
        self.table = DemandPreviewPanel.table(['Type count', 'Total fleet', 'Outcome', 'Completed',
            'Failed', 'Type utilisation (%)', 'First failure / stop reason'])
        self.table.setAccessibleName('Fleet size trials')
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table, 1)
        basis = QLabel('Utilisation includes recorded movement, handling, waiting and charging over the full run window. '
            'Failed trials have no full-run utilisation. Trials are discarded after their summary is collected. '
            'The result applies to the tested type, workload and adjacent failure boundary; smaller counts beyond that boundary are not tested.')
        basis.setWordWrap(True)
        layout.addWidget(basis)
        buttons = QHBoxLayout()
        self.start = QPushButton('Find fleet size')
        self.start.setDefault(True)
        self.start.clicked.connect(self.start_search)
        self.stop = QPushButton('Cancel search')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel_search)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.start)
        buttons.addWidget(self.stop)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.amr_type.currentIndexChanged.connect(self.type_changed)
        self.start_count.valueChanged.connect(lambda value: self.max_count.setMinimum(value))
        for signal in (self.amr_type.currentIndexChanged, self.target.valueChanged,
                       self.start_count.valueChanged, self.max_count.valueChanged):
            signal.connect(self.invalidate_result)
        self.type_changed()

    def invalidate_result(self, *_):
        if self.result_data is not None:
            self.result_data = None
            self.table.setRowCount(0)
            self.status.setText('Settings changed. Find fleet size again to test these settings.')

    def type_changed(self, *_):
        selected = self.amr_type.currentText()
        robot = next((row for row in self.config.get('amrs', []) if row['id'] == selected), None)
        count = int(robot.get('quantity', 1)) if robot else 0
        self.max_count.setMaximum(max(100000, count))
        self.start_count.setMaximum(max(100000, count))
        self.start_count.setValue(count)
        self.max_count.setValue(max(100, count * 2))
        fixed = [f"{row['id']}: {int(row.get('quantity', 1))}" for row in self.config.get('amrs', []) if row['id'] != selected]
        self.fixed.setText('Fixed quantities: ' + (', '.join(fixed) if fixed else 'No other AMR types'))
        self.start.setEnabled(robot is not None)

    def set_busy(self, busy):
        for control in (self.amr_type, self.target, self.start_count, self.max_count, self.start):
            control.setEnabled(not busy)
        self.stop.setEnabled(busy)
        self.progress.setVisible(busy)

    def launch(self, job):
        self.job = job
        self.set_busy(True)
        job.signals.progress.connect(self.show_progress)
        job.signals.finished.connect(self.finished_job)
        QThreadPool.globalInstance().start(job)

    def start_search(self):
        if self.job is not None or not self.amr_type.currentText():
            return
        self.table.setRowCount(0)
        self.result_data = None
        self.settings = (self.amr_type.currentText(), self.start_count.value(), self.max_count.value(), self.target.value())
        inputs = deepcopy(self.config)
        next(row for row in inputs['amrs'] if row['id'] == self.settings[0])['quantity'] = self.settings[1]
        self.status.setText('Preparing current inputs and drawings in memory…')
        self.launch(SizingJob('prepare', lambda cancel, progress:
            self.memory.prepare(inputs, self.base_dir, self.project, cancel=cancel)))

    @Slot(object, str)
    def finished_job(self, result, error):
        job, self.job = self.job, None
        self.set_busy(False)
        if job.kind == 'prepare':
            if job.cancelled.is_set() or result is None:
                if result is not None:
                    result.dispose()
                self.status.setText('Search cancelled.' if job.cancelled.is_set() else 'Search could not start: ' + error)
            else:
                self.draft = result
                checks = None
                try:
                    checks = RunChecksDialog(lambda: self.draft.config, self, asset_refs=self.draft.asset_refs)
                    if checks.exec() == QDialog.Accepted:
                        self.draft.accept_checks(checks.panel.report)
                        budget = self.memory.reserve(self.draft)
                        frozen = self.draft.config
                        type_id, start, maximum, target = self.settings
                        self.launch(SizingJob('search', lambda cancel, progress:
                            search_fleet(frozen, type_id, start, maximum, target,
                                         memory_limit=budget, cancel=cancel, progress=progress)))
                        return
                    self.status.setText('Search cancelled at input checks.')
                except Exception as exc:
                    self.status.setText('Search could not start: ' + str(exc))
                finally:
                    if checks is not None:
                        checks.panel.timer.stop()
                        checks.deleteLater()
                    if self.job is None:
                        self.release_draft()
        else:
            self.release_draft()
            if result is None:
                self.status.setText('Search cancelled.' if job.cancelled.is_set() else 'Search stopped: ' + error)
            else:
                self.result_data = result
                self.show_result(result)
        if self.close_when_stopped:
            super().done(QDialog.Rejected)

    def release_draft(self):
        if self.draft is not None:
            self.draft.dispose()
            self.draft = None

    def cancel_search(self):
        if self.job is not None:
            self.job.cancelled.set()
            self.stop.setEnabled(False)
            self.status.setText('Cancelling search and releasing the current trial…')

    def done(self, code):
        if self.job is not None:
            self.close_when_stopped = True
            self.cancel_search()
            return
        self.release_draft()
        super().done(code)

    def closeEvent(self, event):
        if self.job is not None:
            event.ignore()
            self.done(QDialog.Rejected)
        else:
            super().closeEvent(event)

    @Slot(object)
    def show_progress(self, message):
        if self.job is None or self.job.cancelled.is_set():
            return
        kind = message.get('kind')
        if kind == 'trial_start':
            self.status.setText(message['label'])
        elif kind == 'trial_result':
            self.add_trial(message['trial'])
        elif 'sim_time_sec' in message:
            self.status.setText(f"Testing {self.settings[0]}: {message['count']} AMRs · "
                f"{message['sim_time_sec']:,.0f} simulated seconds · {message['completed']:,} complete")

    def add_trial(self, trial):
        row = self.table.rowCount()
        self.table.insertRow(row)
        failure = trial['first_failure']
        reason = (f"{failure['task_id']} at {failure['sim_time_sec']:,.3f} s: {failure['reason']}" if failure else
                  f"{trial['pending']} tasks pending at stop" if trial['status'] == 'incomplete' else
                  'No tasks completed; sizing is inconclusive' if trial['status'] == 'no_work' else '')
        values = (trial['count'], trial['total'], trial['status'].replace('_', ' ').title(),
                  trial['completed'], trial['failed'],
                  round(trial['utilisation_pct'], 2) if trial['utilisation_pct'] is not None else None, reason)
        for column, value in enumerate(values):
            item = QTableWidgetItem('—' if value is None else str(value))
            if value is not None:
                item.setData(Qt.DisplayRole, value)
            item.setToolTip(str(value) if value is not None else 'Not calculated for this trial')
            self.table.setItem(row, column, item)
        self.table.scrollToBottom()

    def show_result(self, result):
        # Rebuild from the authoritative summary, including cancellation races.
        self.table.setRowCount(0)
        for trial in result['trials']:
            self.add_trial(trial)
        count = result['recommendation']
        if count is not None:
            trial = next(row for row in result['trials'] if row['count'] == count)
            utilisation = trial['utilisation_pct']
            reference = (f"Measured type utilisation: {utilisation:.1f}% · target {result['target_pct']:.1f}% (reference only)."
                         if utilisation is not None else 'No active AMRs of this type in the passing trial.')
            boundary = (f"First failing count: {result['first_failing_count']}." if result['first_failing_count'] is not None
                        else 'Zero of this type passed; no lower count is possible.')
            self.status.setText(f"Recommended {result['type_id']} count: {count} · total fleet {trial['total']}. "
                f"Smallest passing tested count. {boundary}\n{reference}")
        else:
            messages = dict(cancelled='Search cancelled. No recommendation was established.',
                limit='No passing fleet found within the maximum count. Review the first failure reasons or increase the maximum.',
                incomplete='A trial stopped with unfinished work. No fleet recommendation can be established.',
                no_work='No tasks completed. Check the demand and simulation period before sizing the fleet.')
            self.status.setText(messages.get(result['status'], 'Search stopped without a recommendation.'))
