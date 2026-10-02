"""Task timelines and clickable metric evidence for saved simulation runs."""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox, QSplitter)
from PySide6.QtCore import Qt

from amr_results_investigation import load_investigation
from visualiser.demand_preview_panel import DemandPreviewPanel


def display(value):
    if value is None:
        return 'Not recorded'
    if isinstance(value, float):
        return f'{value:.9g}'
    return str(value) if value != '' else '—'


class ResultSignals(QObject):
    finished = Signal(object, str)


class ResultJob(QRunnable):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.signals = ResultSignals()

    def run(self):
        try:
            self.signals.finished.emit(load_investigation(self.source), '')
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class ResultsInvestigationPanel(QWidget):
    table = staticmethod(DemandPreviewPanel.table)
    fill = staticmethod(DemandPreviewPanel.fill)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.job = None
        self.task_rows, self.event_rows = [], []
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.open_button = QPushButton('Open event CSV…')
        self.open_button.clicked.connect(self.open_csv)
        folder = QPushButton('Open run folder…')
        folder.clicked.connect(self.open_folder)
        self.export_button = QPushButton('Export investigation…')
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        controls.addWidget(self.open_button)
        controls.addWidget(folder)
        controls.addStretch()
        controls.addWidget(self.export_button)
        layout.addLayout(controls)
        self.summary = QLabel('Open a saved run to investigate recorded events. Planned segments and confirmed task outcomes are separate evidence.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a task or route profile…')
        self.search.setAccessibleName('Filter result tasks')
        self.search.textChanged.connect(self.populate_tasks)
        self.outcome = QComboBox()
        self.outcome.addItems(['All outcomes', 'completed', 'failed', 'outcome not recorded', 'conflicting outcomes'])
        self.outcome.currentIndexChanged.connect(self.populate_tasks)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.outcome)
        layout.addLayout(search_row)
        split = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.tasks = self.table(['Task', 'Outcome', 'Released (s)', 'Assigned (s)', 'Completed (s)', 'Assignment delay (s)', 'Route profile'])
        self.metrics = self.table(['Metric', 'Value', 'Observed value', 'Coverage'])
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        self.tabs.addTab(self.tasks, 'Tasks')
        self.tabs.addTab(self.metrics, 'Metrics')
        self.tabs.addTab(self.evidence, 'Run evidence')
        split.addWidget(self.tabs)
        timeline = QWidget()
        timeline_layout = QVBoxLayout(timeline)
        self.timeline_label = QLabel('Select a task or metric to see its supporting events.')
        self.timeline_label.setWordWrap(True)
        self.timeline_label.setMinimumHeight(self.fontMetrics().lineSpacing() * 4)
        timeline_layout.addWidget(self.timeline_label)
        self.events = self.table(['Time (s)', 'Event', 'Evidence', 'AMR', 'Lift', 'Duration (s)', 'Wait (s)', 'Source row'])
        timeline_layout.addWidget(self.events)
        split.addWidget(timeline)
        split.setSizes([300, 260])
        layout.addWidget(split, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        self.details.setAccessibleName('Selected event explanation and evidence identity')
        layout.addWidget(self.details)
        self.tasks.itemSelectionChanged.connect(self.select_task)
        self.metrics.itemSelectionChanged.connect(self.select_metric)
        self.events.itemSelectionChanged.connect(self.select_event)

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open full simulation event log', '', 'CSV (*.csv)')
        if path:
            self.load(path)

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Open saved run folder')
        if path:
            self.load(path)

    def load(self, source):
        if self.job:
            return
        self.summary.setText('Reading saved run evidence…')
        self.export_button.setEnabled(False)
        self.job = ResultJob(source)
        self.job.signals.finished.connect(self.accept_result)
        QThreadPool.globalInstance().start(self.job)

    def accept_result(self, result, error=''):
        self.job = None
        self.result = result
        self.events.setRowCount(0)
        self.details.clear()
        self.export_button.setEnabled(bool(result))
        if error:
            self.summary.setText('Investigation could not open: ' + error)
            self.tasks.setRowCount(0)
            self.metrics.setRowCount(0)
            self.evidence.clear()
            return
        coverage = 'Full saved log verified against its run evidence' if result['complete_evidence'] else 'Partial or legacy evidence — missing activity is not zero'
        self.summary.setText(f"{coverage}\n{len(result['tasks'])} tasks · {len(result['events'])} events · {len(result['findings'])} evidence findings · {result['source']}")
        self.events_by_id = {e['id']: e for e in result['events']}
        self.populate_tasks()
        self.fill(self.metrics, [[m['title'], display(m['value']), m['observed_count'], m['coverage']] for m in result['metrics']])
        reconciliation = []
        for r in result['reconciliation']:
            reconciliation.append(f"{r['outcome'].capitalize()}: recorded summary {r['recorded_summary_count']}, events {r['event_count']} — "
                                  + ('matched' if r['matches'] else 'MISMATCH: ' + json.dumps(r)))
        software = result.get('software') or {}
        binding = result.get('project_binding') or {}
        self.evidence.setPlainText('\n'.join([
            'Run: ' + (result['run_id'] or 'Legacy; no native run identity'),
            'Project revision: ' + (binding.get('revision_id') or 'Not recorded'),
            'Project identity: ' + (binding.get('project_id') or 'Not recorded'),
            'Input snapshot: ' + ('Available from saved evidence' if result['frozen_inputs'] else 'Unavailable; current editor inputs are not used'),
            'Software source fingerprint: ' + (software.get('sha256') or 'Not recorded'),
            'Log checksum: ' + result['log_sha256'], '', 'Summary reconciliation:',
            *(reconciliation or ['No bound final summary is available for reconciliation.']),
            '', 'Findings:', *(result['findings'] or ['No evidence integrity findings.']),
            '', 'Scope:', *result['limitations']]))

    def populate_tasks(self, *_):
        if not self.result:
            return
        query = self.search.text().casefold()
        outcome = self.outcome.currentText()
        self.task_rows = [t for t in self.result['tasks'] if query in (t['task_id'] + ' ' + t['route_profile']).casefold()
                          and (outcome == 'All outcomes' or t['outcome'] == outcome)]
        self.fill(self.tasks, [[display(t[k]) for k in ('task_id', 'outcome', 'release_seconds', 'assignment_seconds',
                                                       'completion_seconds', 'assignment_delay_seconds', 'route_profile')] for t in self.task_rows])
        self.events.setRowCount(0)
        self.timeline_label.setText('Select a task or metric to see its supporting events.')

    def show_events(self, ids):
        self.event_rows = sorted([self.events_by_id[eid] for eid in set(ids) if eid in self.events_by_id],
                                 key=lambda e: (e['time_seconds'] is None, e['time_seconds'] or 0, e['source_line']))
        self.fill(self.events, [[e[k].replace('_', ' ') if k == 'type' else display(e[k]) for k in ('time_seconds', 'type', 'evidence_kind', 'amr_id', 'lift_id',
                                                        'duration_seconds', 'wait_seconds', 'source_line')] for e in self.event_rows])

    def select_task(self):
        index = self.tasks.currentRow()
        if 0 <= index < len(self.task_rows):
            task = self.task_rows[index]
            self.timeline_label.setText(f"{task['task_id']} · {task['outcome']} · release to completion: {display(task['release_to_completion_seconds'])} s\n"
                                        + task['delay_explanation'])
            self.show_events(task['event_ids'])
            self.details.setPlainText('Missing evidence: ' + (', '.join(task['missing_evidence']) or 'None of the principal lifecycle events')
                                      + '\nOrigin: ' + (task['source_rule_path'] or 'Not recorded')
                                      + '\nSelect a timeline event for recorded reasons, route restrictions and source identity.')
            if task['profile_definition'] is not None:
                profile = task['profile_definition']
                lines = ['\nProfile restrictions from saved inputs (task allowances can extend these):']
                for key in ('allowed_nodes', 'allowed_lifts', 'allowed_edges'):
                    values = profile.get(key, [])
                    text = ', '.join(' → '.join(v) if isinstance(v, list) else str(v) for v in values)
                    lines.append(key.replace('_', ' ').capitalize() + ': ' + (text or 'Unrestricted'))
                self.details.appendPlainText('\n'.join(lines))

    def select_metric(self):
        index = self.metrics.currentRow()
        if self.result and 0 <= index < len(self.result['metrics']):
            metric = self.result['metrics'][index]
            self.timeline_label.setText(metric['title'] + ': ' + display(metric['value']) + '\n' + metric['definition'])
            self.show_events(metric['event_ids'])
            self.details.setPlainText(metric['coverage'] + '\nEach event below contributes to this metric. Shared task lists do not multiply segment counts.')

    def select_event(self):
        index = self.events.currentRow()
        if 0 <= index < len(self.event_rows):
            e = self.event_rows[index]
            row = e['row']
            self.details.setPlainText('\n'.join([
                e['explanation'], '', 'Evidence: ' + e['evidence_kind'],
                'Tasks: ' + ', '.join(e['task_ids']),
                'Route: ' + (row.get('from_location') or row.get('start_node') or '?') + ' → ' + (row.get('to_location') or row.get('end_node') or '?'),
                'Profile: ' + (row.get('route_profile') or 'Not recorded'),
                'Payload instance: ' + (e['payload_instance_id'] or 'Not recorded'),
                'Event identity: ' + e['id'], 'Source row: ' + str(e['source_line']),
                '', 'Original recorded detail:', row.get('details') or 'No detail recorded.']))

    def export(self):
        if not self.result or self.job:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export investigation', 'results-investigation.json', 'JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(self.result, indent=2) + '\n', encoding='utf-8')
            except OSError as exc:
                QMessageBox.critical(self, 'Export failed', str(exc))
