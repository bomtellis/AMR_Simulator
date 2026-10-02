"""Reusable modeless checks workspace and launcher preflight dialog."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QTabWidget,
)

try:
    from .project_checks import check_project
    from .check_dependencies import input_names
except ImportError:
    from project_checks import check_project
    from check_dependencies import input_names


class ProjectChecksPanel(QWidget):
    navigate = Signal(object)
    readiness_changed = Signal()

    def __init__(self, config_provider, parent=None, base_path_provider=None):
        super().__init__(parent)
        self.config_provider = config_provider
        self.base_path_provider = base_path_provider or (lambda: None)
        self.report = None
        self._checked_base_path = None
        self.visible_findings = []
        self._finding_changes = {}
        self._group_states = {}
        self.setWindowTitle("Project checks")
        layout = QVBoxLayout(self)
        intro = QLabel("Check inputs before running. Errors need correction; warnings can describe an intentional constraint study.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.summary = QLabel("Not checked")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.coverage = QLabel('')
        self.coverage.setWordWrap(True)
        layout.addWidget(self.coverage)
        row = QHBoxLayout()
        self.refresh_button = QPushButton("Run checks")
        self.refresh_button.clicked.connect(self.check_now)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find an object, setting or issue…")
        self.search.setAccessibleName("Filter project findings")
        self.search.textChanged.connect(self.populate)
        self.severity = QComboBox()
        self.severity.addItems(["All findings", "Errors", "Warnings", "Information"])
        self.severity.currentIndexChanged.connect(self.populate)
        row.addWidget(self.refresh_button)
        row.addWidget(self.search, 1)
        row.addWidget(self.severity)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Severity", "Object", "Finding", "Input status"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.cellDoubleClicked.connect(lambda *_: self.navigate_selected())
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, 'Findings')
        self.groups_table = QTableWidget(0, 4)
        self.groups_table.setHorizontalHeaderLabels(['Check group', 'Execution', 'Input status', 'Changed inputs'])
        self.groups_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.groups_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.groups_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.groups_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.groups_table.verticalHeader().hide()
        self.groups_table.itemSelectionChanged.connect(self.show_details)
        self.tabs.addTab(self.groups_table, 'Check coverage')
        layout.addWidget(self.tabs, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Finding explanation and suggested action")
        self.details.setMaximumHeight(180)
        layout.addWidget(self.details)
        actions = QVBoxLayout()
        self.navigate_button = QPushButton("Go to affected settings")
        self.navigate_button.clicked.connect(self.navigate_selected)
        self.export_button = QPushButton("Export findings…")
        self.export_button.clicked.connect(self.export_findings)
        actions.addWidget(self.navigate_button)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        self.acknowledge = QCheckBox("Warnings reviewed")
        self.acknowledge.setAccessibleName('I have reviewed the warnings for this configuration')
        self.acknowledge.setToolTip('Acknowledge the warnings for this checked configuration. Changes require a fresh review.')
        self.acknowledge.toggled.connect(self.set_acknowledgement)
        layout.addWidget(self.acknowledge)
        self.tabs.currentChanged.connect(self.show_details)
        self.timer = QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.check_staleness)
        self.timer.start()
        self.check_now()

    def current(self):
        try:
            return (self.report is not None and not self.report.is_stale(self.config_provider())
                    and self._checked_base_path == self.base_path_provider())
        except (OSError, ValueError, TypeError):
            return False

    def can_run(self):
        try:
            return self.current() and self.report.can_run(self.config_provider())
        except (OSError, ValueError, TypeError):
            return False

    def finding_current(self, finding):
        try:
            return (finding is not None and self.report is not None and
                    any(f.id == finding.id for f in self.report.findings) and
                    self._checked_base_path == self.base_path_provider() and
                    not self.report.changed_inputs(finding, self.config_provider()))
        except (OSError, ValueError, TypeError):
            return False

    def check_now(self):
        try:
            config = self.config_provider()
            self._checked_base_path = self.base_path_provider()
            self.report = check_project(config, base_path=self._checked_base_path)
        except (OSError, ValueError, TypeError) as exc:
            self.report = None
            self.summary.setText(f"Checks could not complete: {exc}")
            self.table.setRowCount(0)
            self.details.clear()
            self.coverage.clear()
            self.groups_table.setRowCount(0)
            self._group_states = {}
            self.visible_findings = []
            self.check_staleness()
            return
        self.acknowledge.blockSignals(True)
        self.acknowledge.setChecked(False)
        self.acknowledge.blockSignals(False)
        self.populate()
        self.check_staleness()

    def populate(self, *_):
        if self.report is None:
            return
        severity = {1: "error", 2: "warning", 3: "info"}.get(self.severity.currentIndex())
        query = self.search.text().casefold()
        self.visible_findings = [f for f in self.report.findings if (not severity or f.severity == severity)
                                 and query in " ".join((f.object_name, f.message, f.path, f.code, f.consequence)).casefold()]
        self.table.setRowCount(len(self.visible_findings))
        for row, finding in enumerate(self.visible_findings):
            for column, value in enumerate((finding.severity.title(), finding.object_name, finding.message, '')):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        if self.visible_findings:
            self.table.selectRow(0)
        else:
            self.details.clear()
        self.show_details()
        self.check_staleness()

    def selected(self):
        row = self.table.currentRow()
        return self.visible_findings[row] if 0 <= row < len(self.visible_findings) else None

    def show_details(self):
        if self.tabs.currentIndex() == 1:
            self.navigate_button.setEnabled(False)
            row = self.groups_table.currentRow()
            groups = list(self._group_states.values())
            if 0 <= row < len(groups):
                group = groups[row]
                self.details.setPlainText(group['label'] + '\n\nExecution: ' + group['execution'] +
                    '\nChanged inputs: ' + (input_names(group['changed_inputs']) or 'none') +
                    '\n\nCompleted means this check stage was evaluated, not that every finding passed. '
                    'Not run means the stage was skipped or could not finish. Unchanged inputs do not grant run readiness after a project edit. '
                    'Whole-project tracking is retained where a more precise dependency has not been established.')
            else:
                self.details.clear()
            return
        finding = self.selected()
        self.navigate_button.setEnabled(self.finding_current(finding))
        if finding:
            changes = self._finding_changes.get(finding.id, [])
            status = 'Changed inputs: ' + input_names(changes) if changes else 'Inputs for this finding are unchanged. A changed project still needs a full recheck before running.'
            self.details.setPlainText(f"{finding.message}\n\nConsequence: {finding.consequence}\n\nNext action: {finding.action}\n\nSetting: {finding.path}\nCheck: {finding.code}\n\n{status}")
        else:
            self.details.clear()

    def navigate_selected(self):
        if self.tabs.currentIndex() == 0 and self.finding_current(self.selected()):
            self.navigate.emit(self.selected())

    def set_acknowledgement(self, checked):
        if self.report:
            if checked and self.current():
                self.report.acknowledge_warnings()
            else:
                self.report.acknowledged.clear()
        self.readiness_changed.emit()

    def check_staleness(self):
        current = self.current()
        if self.report:
            try:
                config = self.config_provider()
                self._finding_changes = self.report.finding_states(config)
                groups = self.report.group_states(config)
                if self._checked_base_path != self.base_path_provider():
                    self._finding_changes = {f.id: ['project folder'] for f in self.report.findings}
                    for group in groups.values():
                        group['changed_inputs'].append('project folder')
                self._group_states = groups
                self.coverage.setText(f"Check groups: {sum(v['execution'] == 'completed' for v in groups.values())} evaluated · "
                    f"{sum(v['execution'] != 'completed' for v in groups.values())} not run · "
                    f"{sum(bool(v['changed_inputs']) for v in groups.values())} with changed inputs. See Check coverage for details.")
                self.groups_table.setRowCount(len(groups))
                for row, value in enumerate(groups.values()):
                    state = 'Needs recheck' if value['changed_inputs'] else 'Unchanged inputs'
                    for column, text in enumerate((value['label'], value['execution'].replace('_', ' '), state,
                                                   input_names(value['changed_inputs']) or 'None')):
                        self.groups_table.setItem(row, column, QTableWidgetItem(text))
            except (OSError, ValueError, TypeError):
                self._finding_changes = {f.id: ['inputs unavailable'] for f in self.report.findings}
                self.coverage.setText('Current inputs unavailable; run checks again when the project can be read.')
                for row, group in enumerate(self._group_states.values()):
                    group['changed_inputs'] = ['inputs unavailable']
                    self.groups_table.setItem(row, 2, QTableWidgetItem('Inputs unavailable'))
                    self.groups_table.setItem(row, 3, QTableWidgetItem('Inputs unavailable'))
            for row, finding in enumerate(self.visible_findings):
                item = self.table.item(row, 3)
                if item is not None:
                    item.setText('Current' if current else 'Needs recheck' if self._finding_changes.get(finding.id) else 'Unchanged inputs')
            if not current:
                self.report.acknowledged.clear()
                self.acknowledge.blockSignals(True)
                self.acknowledge.setChecked(False)
                self.acknowledge.blockSignals(False)
                self.summary.setText("STALE — inputs or drawing availability changed. Run checks again before relying on these findings.")
            else:
                counts = {level: sum(f.severity == level for f in self.report.findings) for level in ("error", "warning", "info")}
                self.summary.setText(f"Current checks: {counts['error']} errors · {counts['warning']} warnings · {counts['info']} information.\nThese checks cover selected rules; they do not certify all simulator behaviour.")
        self.export_button.setEnabled(current)
        self.acknowledge.setEnabled(current and any(f.severity == "warning" for f in self.report.findings))
        self.show_details()
        self.readiness_changed.emit()

    def export_findings(self):
        if not self.current():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export project checks", "project-checks.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(json.dumps(self.report.to_dict(), indent=2) + "\n", encoding="utf-8")
            except OSError as exc:
                QMessageBox.critical(self, "Export failed", str(exc))


class RunChecksDialog(QDialog):
    def __init__(self, config_provider, parent=None, base_path_provider=None):
        super().__init__(parent)
        self.setWindowTitle("Project checks before simulation")
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        self.panel = ProjectChecksPanel(config_provider, self, base_path_provider)
        # Navigation is provided by the editor workspace, not a detached launcher.
        self.panel.navigate_button.hide()
        layout.addWidget(self.panel)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.run_button = QPushButton("Run this checked configuration")
        self.run_button.clicked.connect(self.accept_checked)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self.run_button)
        layout.addLayout(buttons)
        self.panel.readiness_changed.connect(self.update_readiness)
        self.update_readiness()

    def update_readiness(self):
        self.run_button.setEnabled(self.panel.can_run())

    def accept_checked(self):
        if self.panel.can_run():
            self.accept()
