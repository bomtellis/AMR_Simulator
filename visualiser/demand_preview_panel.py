"""Demand planning workspace. Long-running construction stays off the UI thread."""
import copy
import json
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QPlainTextEdit, QFileDialog, QMessageBox)

from amr_demand_preview import build_demand_preview, filter_tasks, timetable
from visualiser.project_checks import config_fingerprint


def readable(value):
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, dict):
        return '; '.join(f"{k.replace('_', ' ')}: {readable(v)}" for k, v in value.items()) or '(none)'
    if isinstance(value, list):
        return ', '.join(readable(v) for v in value) or '(none)'
    return str(value) if value not in (None, '') else '(unspecified)'


def rule_explanation(rule):
    lines = [rule['explanation'], '', f"Rule: {rule['id']}", f"Department: {rule['department'] or 'Category default'}",
             f"Planned records: {rule['planned_records']}",
             'Total demand: ' + ('Unknown before simulation' if rule['total_demand'] is None else str(rule['total_demand'])),
             'Independent expected count: ' + ('Not assessed' if rule.get('expected_fixed_records') is None else str(rule['expected_fixed_records']))]
    if 'effective_pickups' in rule:
        lines.extend(['Effective pickups: ' + readable(rule['effective_pickups']),
                      'Effective dropoffs: ' + readable(rule['effective_dropoffs']),
                      'Final destinations: ' + readable(rule['final_destinations']), rule['location_precedence'], rule['returns']])
    lines.extend(['', 'Resolved rule settings (task-specific adjustments appear above when a task is selected):'])
    for key, value in rule['effective_config'].items():
        if key in {'departments', 'department_groups'}:
            continue
        source = rule.get('field_sources', {}).get(key, 'Stored setting')
        provenance = rule.get('field_provenance', {}).get(key)
        if provenance:
            source = provenance['source']
        elif 'category-wide' in source:
            source = 'Category-wide policy'
        elif '/department_groups/' in source:
            source = 'Group override'
        elif '/departments/' in source:
            source = 'Department override'
        elif source.startswith('/task_generation/categories/'):
            source = 'Category default'
        lines.append(f"{key.replace('_', ' ').capitalize()}: {readable(value)} [{source}]")
    lines.extend(['', 'Origin: ' + rule['path']])
    return '\n'.join(lines)


class PreviewSignals(QObject):
    finished = Signal(object, str)


class PreviewJob(QRunnable):
    def __init__(self, config, end):
        super().__init__()
        self.config, self.end = config, end
        self.signals = PreviewSignals()

    def run(self):
        try:
            self.signals.finished.emit(build_demand_preview(self.config, end_datetime=self.end or None), '')
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class DemandPreviewPanel(QWidget):
    def __init__(self, config_provider, parent=None):
        super().__init__(parent)
        self.config_provider = config_provider
        self.preview = None
        self.rows = []
        self.job = None
        layout = QVBoxLayout(self)
        intro = QLabel('Inspect planned demand before simulation. Runtime-dependent demand and returns remain unknown; these are not completed movements.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        actions = QVBoxLayout()
        self.build_button = QPushButton('Build preview')
        self.build_button.clicked.connect(self.build)
        self.end = QLineEdit()
        self.end.setPlaceholderText('End date/time (blank uses project end or one day)')
        self.end.setAccessibleName('Preview end date and time, ISO format')
        self.end.textChanged.connect(self.check_staleness)
        self.export_button = QPushButton('Export preview…')
        self.export_button.clicked.connect(self.export)
        actions.addWidget(self.end)
        buttons = QHBoxLayout()
        buttons.addWidget(self.build_button)
        buttons.addWidget(self.export_button)
        actions.addLayout(buttons)
        layout.addLayout(actions)
        self.summary = QLabel('Build a preview to inspect demand. Maximum 31 days and 20,000 task records.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search tasks, routes, rules or destinations…')
        self.search.setAccessibleName('Search demand')
        self.search.textChanged.connect(self.populate)
        layout.addWidget(self.search)
        filters = QGridLayout()
        self.filters = {}
        for index, (key, title) in enumerate([('department', 'Department'), ('category', 'Category'), ('payload', 'Payload'), ('date', 'Date'), ('route_profile', 'Route profile')]):
            box = QComboBox()
            box.setAccessibleName(title)
            box.addItem('All ' + title.lower(), '')
            box.currentIndexChanged.connect(self.populate)
            box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(8)
            filters.addWidget(box, index // 3, index % 3)
            self.filters[key] = box
        layout.addLayout(filters)
        self.tabs = QTabWidget()
        self.tasks = self.table(['Planned release', 'Department', 'Category', 'Payload', 'Pickup', 'Dropoff', 'Route', 'Quantity', 'Timing'])
        self.hours = self.table(['Date / hour', 'Category', 'Department', 'Planned records'])
        self.rules = self.table(['Category', 'Department', 'Rule', 'Status', 'Planned records', 'Expected fixed records', 'Difference', 'Total demand'])
        self.tabs.addTab(self.tasks, 'Tasks')
        self.tabs.addTab(self.hours, 'Timetable')
        self.tabs.addTab(self.rules, 'Rules and reconciliation')
        provenance = QWidget()
        provenance_layout = QVBoxLayout(provenance)
        self.field_context = QLabel('Select a task or rule to inspect its resolved rule settings.')
        self.field_context.setWordWrap(True)
        provenance_layout.addWidget(self.field_context)
        self.field_search = QLineEdit()
        self.field_search.setPlaceholderText('Find a setting, value or source…')
        self.field_search.setAccessibleName('Search effective rule settings')
        provenance_layout.addWidget(self.field_search)
        self.fields = self.table(['Setting', 'Effective value', 'Winning source', 'Source setting'])
        provenance_layout.addWidget(self.fields)
        self.tabs.addTab(provenance, 'Effective settings')
        self.selected_rule = None
        self.field_rows = []
        self.field_search.textChanged.connect(self.populate_fields)
        self.fields.itemSelectionChanged.connect(self.field_details)
        self.tabs.currentChanged.connect(self.tab_details)
        layout.addWidget(self.tabs, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(210)
        self.details.setAccessibleName('Demand origin, effective values and precedence')
        layout.addWidget(self.details)
        self.tasks.itemSelectionChanged.connect(self.task_details)
        self.rules.itemSelectionChanged.connect(self.rule_details)
        self.timer = QTimer(self)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.check_staleness)
        self.timer.start()
        self._requested_end = ''
        self.check_staleness()

    @staticmethod
    def table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def fill(table, rows):
        table.blockSignals(True)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(i, j, item)
        table.blockSignals(False)

    def build(self):
        if self.job:
            return
        self._requested_end = self.end.text().strip()
        self.build_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.summary.setText('Building preview from a frozen copy of the project…')
        self.job = PreviewJob(copy.deepcopy(self.config_provider()), self._requested_end)
        self.job.signals.finished.connect(self.accept_preview)
        QThreadPool.globalInstance().start(self.job)

    def accept_preview(self, preview, error=''):
        self.job = None
        self.build_button.setEnabled(True)
        self.preview = preview
        if error:
            self.summary.setText('Preview could not complete: ' + error)
            self.rows = []
            for table in (self.tasks, self.hours, self.rules, self.fields):
                table.setRowCount(0)
            self.select_rule(None)
            self.details.clear()
            self.export_button.setEnabled(False)
            return
        for key, box in self.filters.items():
            box.blockSignals(True)
            while box.count() > 1:
                box.removeItem(1)
            values = sorted({t['release_datetime'][:10] if key == 'date' else t[key] for t in preview['tasks']})
            for value in values:
                box.addItem(value or '(Unspecified)', value or '__blank__')
            box.blockSignals(False)
        self.populate()
        self.check_staleness()

    def populate(self, *_):
        if not self.preview:
            return
        selected = {k: v.currentData() or '' for k, v in self.filters.items()}
        ordinary = {k: v for k, v in selected.items() if v != '__blank__'}
        self.rows = filter_tasks(self.preview, query=self.search.text(), **ordinary)
        self.rows = [t for t in self.rows if all(t[k] == '' for k, v in selected.items() if v == '__blank__')]
        self.fill(self.tasks, [[t[k] for k in ('release_datetime', 'department', 'category', 'payload', 'pickup', 'dropoff', 'route_profile', 'quantity', 'timing')] for t in self.rows])
        self.fill(self.hours, [[t[k] for k in ('hour', 'category', 'department', 'planned_records')] for t in timetable(self.rows)])
        self.fill(self.rules, [[r['category'], r['department'], r['id'], r['status'], r['planned_records'],
                               r.get('expected_fixed_records') if r.get('expected_fixed_records') is not None else 'Not assessed',
                               r['count_difference'] if r['count_difference'] is not None else 'Not assessed',
                               'Unknown' if r['total_demand'] is None else r['total_demand']] for r in self.preview['rules']])
        self.tasks.clearSelection()
        self.rules.clearSelection()
        self.select_rule(None)
        self.details.setPlainText('Rules and reconciliation always show the entire preview; task filters apply to Tasks and Timetable only.\n\n' + '\n'.join(self.preview['precedence']))
        self.check_staleness()

    def current(self):
        return bool(self.preview and self.preview['config_sha256'] == config_fingerprint(self.config_provider())
                    and self.end.text().strip() == self._requested_end)

    def check_staleness(self, *_):
        current = self.current()
        self.export_button.setEnabled(current and not self.job)
        if self.job or not self.preview:
            return
        totals = self.preview['totals']
        prefix = '' if current else 'STALE — inputs changed; rebuild before relying on this preview.\n'
        self.summary.setText(prefix + f"{len(self.rows)} shown / {totals['planned_task_records']} planned task records; "
                             f"{totals['runtime_dependent_rules']} rules have unknown total demand. "
                             f"Rule reconciliation: {totals['reconciled_rule_records']} records; independent counts: "
                             f"{totals['independently_reconciled_rules']} matched, {totals['count_mismatches']} mismatched (other rules not assessed).\n"
                             + self.preview['start_datetime'] + ' to ' + self.preview['end_datetime'] + ' (inclusive).')

    def task_details(self):
        index = self.tasks.currentRow()
        if 0 <= index < len(self.rows):
            task = self.rows[index]
            rule = next(r for r in self.preview['rules'] if r['id'] == task['rule_id'])
            self.select_rule(rule)
            effective = task['effective_task']
            lines = [task['explanation'], f"{task['release_datetime']} · {task['timing']}",
                     f"{task['payload']}: {task['pickup']} → {task['dropoff']}"]
            for key in ('priority', 'target_time', 'final_destination', 'requires_staff', 'staff_resource_name',
                        'return_enabled', 'return_payload', 'return_delay_minutes', 'dropoff_zone_capacity_policy'):
                if key in effective:
                    label = 'Target duration from release (seconds)' if key == 'target_time' else key.replace('_', ' ').capitalize()
                    lines.append(f"{label}: {readable(effective[key])}")
            self.details.setPlainText('\n'.join(lines) + '\n\n' + rule_explanation(rule))

    def rule_details(self):
        index = self.rules.currentRow()
        if self.preview and 0 <= index < len(self.preview['rules']):
            rule = self.preview['rules'][index]
            self.select_rule(rule)
            self.details.setPlainText(rule_explanation(rule) + '\n\nPrecedence:\n' + '\n'.join(self.preview['precedence']))

    def select_rule(self, rule):
        self.selected_rule = rule
        self.field_context.setText(
            f"{rule['category']} · {rule['department'] or 'Category default'} · {rule['id']}\n"
            'Resolved rule settings. Select a field for its ordered override history. Task-specific and runtime adjustments are separate.'
            if rule else 'Select a task or rule to inspect its resolved rule settings.')
        self.populate_fields()

    def populate_fields(self, *_):
        rule = self.selected_rule
        self.field_rows = []
        if rule:
            query = self.field_search.text().casefold()
            for key, value in sorted(rule['effective_config'].items()):
                if key in {'departments', 'department_groups'}:
                    continue
                entry = rule.get('field_provenance', {}).get(key)
                if entry is None:
                    # Older exports and inactive rules have no resolution history.
                    # Do not invent inheritance from matching values.
                    entry = {'value': value, 'source': 'Stored value; resolution history unavailable',
                             'path': '', 'history': []}
                if query in (key + ' ' + json.dumps(entry, ensure_ascii=False)).casefold():
                    self.field_rows.append((key, entry))
        self.fill(self.fields, [[key.replace('_', ' ').capitalize(), readable(entry['value']),
                                entry['source'], entry['path'] or 'Derived/default; see history']
                               for key, entry in self.field_rows])
        self.fields.clearSelection()
        if self.tabs.currentIndex() == 3:
            self.field_details()

    def field_details(self):
        index = self.fields.currentRow()
        if not self.fields.selectedItems() or not 0 <= index < len(self.field_rows):
            self.details.setPlainText('Select a setting to inspect its override history. Last assignment wins; equal values still retain their separate sources.')
            return
        key, entry = self.field_rows[index]
        lines = [key.replace('_', ' ').capitalize() + ': ' + readable(entry['value']), '',
                 'Assignment history (last assignment wins):']
        for i, step in enumerate(entry['history'], 1):
            lines.extend([f"{i}. {step['layer']}: {readable(step['value'])}",
                          step['path'] or 'No stored field: default, normalisation or derived value.',
                          step.get('explanation', ''), ''])
        if not entry['history']:
            lines.append('History unavailable for this stored rule or older preview; no resolved source is claimed.')
        self.details.setPlainText('\n'.join(lines))

    def tab_details(self, index):
        if index == 3:
            self.field_details()
        elif index == 0:
            self.task_details()
        elif index == 2:
            self.rule_details()
        else:
            self.details.setPlainText('Timetable groups the currently filtered planned task records by release hour, category and department.')

    def export(self):
        if not self.current() or self.job:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export complete demand preview', 'demand-preview.json', 'JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(self.preview, indent=2) + '\n', encoding='utf-8')
            except OSError as exc:
                QMessageBox.critical(self, 'Export failed', str(exc))
