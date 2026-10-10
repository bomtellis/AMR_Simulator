"""Task timelines and clickable metric evidence for saved simulation runs."""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox, QSplitter, QSpinBox)
from PySide6.QtCore import Qt

from amr_results_investigation import MAX_EVENTS, MAX_LOG_BYTES, load_investigation
from amr_run_review import verified_inputs
from amr_project_runs import read_json, OUTPUTS
from amr_run_evidence import file_hash
from visualiser.demand_preview_panel import DemandPreviewPanel


def display(value):
    if value is None:
        return 'Not recorded'
    if isinstance(value, float):
        return f'{value:.9g}'
    return str(value) if value != '' else '—'


def load_review(source):
    """Managed partial runs require the same bound evidence as project playback."""
    path = Path(source)
    directory = path if path.is_dir() else path.parent
    manifest_path = directory / 'run_manifest.json'
    manifest = None
    managed = path.is_dir() or path.name == OUTPUTS['steps_csv']
    if managed and manifest_path.is_file() and 'project_binding' in read_json(manifest_path):
        manifest_hash = file_hash(manifest_path)
        manifest, _config, _csv, _checksum = verified_inputs(directory, allow_partial=True)
    result = load_investigation(source)
    frozen=result.get('frozen_inputs')
    if isinstance(frozen,dict):
        from visualiser.project_checks import check_project
        result['route_checks_report']=check_project(frozen,base_path=directory,include_legacy=False).to_dict()
    if manifest and manifest['status'] == 'partial':
        _current, _config, _csv, checksum = verified_inputs(directory, allow_partial=True)
        if checksum != _checksum or file_hash(manifest_path) != manifest_hash:
            raise ValueError('Run evidence changed during investigation loading.')
        result['termination'] = manifest['termination']
        result['findings'].append('Stopped run: segment records are plans, including activity beyond the stop. '
                                  'Full-run aggregate metrics are withheld; use bounded playback to inspect the stop.')
        for metric in result['metrics']:
            metric.update(value=None, observed_count=None, coverage='Withheld for partial run')
        result['lift_checks']['records'] = []
    return result


class ResultSignals(QObject):
    finished = Signal(object, str)


class ResultJob(QRunnable):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.signals = ResultSignals()

    def run(self):
        try:
            self.signals.finished.emit(load_review(self.source), '')
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class ResultsInvestigationPanel(QWidget):
    EVENT_PAGE_SIZE = 500
    table = staticmethod(DemandPreviewPanel.table)
    fill = staticmethod(DemandPreviewPanel.fill)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.job = None
        self.task_rows, self.event_rows = [], []
        self.selected_evidence = None
        self.related_choices = []
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.open_button = QPushButton('Open event CSV…')
        self.open_button.clicked.connect(self.open_csv)
        folder = QPushButton('Open run folder…')
        folder.clicked.connect(self.open_folder)
        self.export_button = QPushButton('Export investigation…')
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        self.export_selected_button = QPushButton('Export selected evidence…')
        self.export_selected_button.setAccessibleName('Export all evidence for the selected task, metric or lift')
        self.export_selected_button.setToolTip('Exports every event in the selected timeline, including events on other pages.')
        self.export_selected_button.clicked.connect(self.export_selected)
        self.export_selected_button.setEnabled(False)
        controls.addWidget(self.open_button)
        controls.addWidget(folder)
        if hasattr(parent, 'show_lift_planner'):
            lift_study = QPushButton('Lift studies…')
            lift_study.clicked.connect(parent.show_lift_planner)
            controls.addWidget(lift_study)
        controls.addStretch()
        controls.addWidget(self.export_selected_button)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)
        self.summary = QLabel('Open a saved run to investigate recorded events. Planned segments and confirmed task outcomes are separate evidence.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.limits_label = QLabel(
            f'Log limit: {MAX_EVENTS:,} events and {MAX_LOG_BYTES // (1024 * 1024)} MiB. '
            f'Timelines show {self.EVENT_PAGE_SIZE:,} events per page; selected-evidence export includes every page. '
            'Files above either limit are rejected without truncation.')
        self.limits_label.setWordWrap(True)
        self.limits_label.setAccessibleName('Investigation log and event page limits')
        layout.addWidget(self.limits_label)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a task or route profile…')
        self.search.setAccessibleName('Filter result tasks')
        self.search.textChanged.connect(self.populate_tasks)
        self.outcome = QComboBox()
        self.outcome.addItems(['All outcomes', 'completed', 'failed', 'pending at stop', 'outcome not recorded', 'conflicting outcomes'])
        self.outcome.currentIndexChanged.connect(self.populate_tasks)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.outcome)
        layout.addLayout(search_row)
        split = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.tasks = self.table(['Task', 'Outcome', 'Released (s)', 'Assigned (s)', 'Completed (s)', 'Assignment delay (s)', 'Route profile'])
        self.metrics = self.table(['Metric', 'Value', 'Observed value', 'Coverage'])
        self.lift_checks = self.table(['Lift', 'Check result', 'Transfers recorded', 'Repositions recorded', 'Transfers booked', 'Repositions booked', 'Coverage'])
        self.lift_checks.setAccessibleName('Lift movement consistency checks')
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        self.tabs.addTab(self.tasks, 'Tasks')
        self.tabs.addTab(self.metrics, 'Metrics')
        self.tabs.addTab(self.lift_checks, 'Lift checks')
        self.tabs.addTab(self.evidence, 'Run evidence')
        from route_checks_view import RouteChecksView
        self.route_checks_view=RouteChecksView(self)
        self.tabs.addTab(self.route_checks_view,'Route checks')
        split.addWidget(self.tabs)
        timeline = QWidget()
        self.timeline_widget=timeline
        timeline_layout = QVBoxLayout(timeline)
        self.timeline_label = QLabel('Select a task or metric to see its supporting events.')
        self.timeline_label.setWordWrap(True)
        self.timeline_label.setMinimumHeight(self.fontMetrics().lineSpacing() * 3)
        timeline_layout.addWidget(self.timeline_label)
        self.follow = QComboBox()
        self.follow.setAccessibleName('Follow task, payload, journey or lift evidence')
        self.follow.setToolTip('Choose an identity linked to this task to inspect every matching record in the saved log.')
        self.follow.currentIndexChanged.connect(self.follow_related)
        self.follow.setEnabled(False)
        timeline_layout.addWidget(self.follow)
        pages = QHBoxLayout()
        self.previous_events = QPushButton('Previous page')
        self.next_events = QPushButton('Next page')
        self.event_page = QSpinBox()
        self.event_page.setRange(1, 1)
        self.event_page.setPrefix('Page ')
        self.event_page.setAccessibleName('Timeline event page')
        self.event_range = QLabel('No events')
        self.previous_events.clicked.connect(lambda: self.event_page.setValue(self.event_page.value() - 1))
        self.next_events.clicked.connect(lambda: self.event_page.setValue(self.event_page.value() + 1))
        self.event_page.valueChanged.connect(self.populate_event_page)
        pages.addWidget(self.previous_events)
        pages.addWidget(self.event_page)
        pages.addWidget(self.next_events)
        pages.addWidget(self.event_range)
        pages.addStretch()
        timeline_layout.addLayout(pages)
        self.events = self.table(['Time (s)', 'Event', 'Evidence', 'AMR', 'Lift', 'Duration (s)', 'Wait (s)', 'Source row'])
        timeline_layout.addWidget(self.events)
        split.addWidget(timeline)
        split.setSizes([260, 300])
        layout.addWidget(split, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(125)
        self.details.setAccessibleName('Selected event explanation and evidence identity')
        layout.addWidget(self.details)
        self.tasks.itemSelectionChanged.connect(self.select_task)
        self.metrics.itemSelectionChanged.connect(self.select_metric)
        self.lift_checks.itemSelectionChanged.connect(self.select_lift)
        self.events.itemSelectionChanged.connect(self.select_event)
        self.tabs.currentChanged.connect(self.select_active_tab)
        self.clear_events()

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
        self.summary.setToolTip('')
        self.export_button.setEnabled(False)
        self.export_selected_button.setEnabled(False)
        self.job = ResultJob(source)
        self.job.signals.finished.connect(self.accept_result)
        QThreadPool.globalInstance().start(self.job)

    def accept_result(self, result, error=''):
        self.route_checks_view.set_report((result or {}).get('route_checks_report'),
            'Saved run input snapshot — independent of current project edits.' if (result or {}).get('route_checks_report') else
            'Route coverage unavailable: no checked saved-run input snapshot. Current project inputs are not substituted.')
        self.job = None
        self.result = result
        self.clear_events()
        self.details.clear()
        self.export_button.setEnabled(bool(result))
        if error:
            self.task_rows, self.lift_rows = [], []
            self.summary.setText('Investigation could not open: ' + error)
            self.tasks.setRowCount(0)
            self.metrics.setRowCount(0)
            self.lift_checks.setRowCount(0)
            self.evidence.clear()
            return
        coverage = 'Full saved log verified against its run evidence' if result['complete_evidence'] else 'Partial or legacy evidence — missing activity is not zero'
        if result.get('termination'):
            stop = result['termination']
            coverage = f"Verified partial run — {stop['reason']} at {stop['stop_time_sec']:.9g} s: {stop['message']}"
        self.summary.setText(f"{coverage}\n{len(result['tasks'])} tasks · {len(result['events'])} events · "
                             f"{len(result['findings'])} evidence findings · {Path(result['source']).name}")
        self.summary.setToolTip(result['source'])
        self.events_by_id = {e['id']: e for e in result['events']}
        self.populate_tasks()
        self.fill(self.metrics, [[m['title'], display(m['value']), m['observed_count'], m['coverage']] for m in result['metrics']])
        self.lift_rows = result.get('lift_checks', {}).get('records', [])
        self.fill(self.lift_checks, [[r['lift_id'] or 'Unidentified lift', r['status'],
            r['observed']['transfer'], r['observed']['reposition'],
            display((r['expected'] or {}).get('transfer')), display((r['expected'] or {}).get('reposition')),
            'Full bound planned movements' if r['known'] else 'Incomplete evidence'] for r in self.lift_rows])
        reconciliation = []
        for r in result['reconciliation']:
            reconciliation.append(f"{r['outcome'].capitalize()}: recorded summary {r['recorded_summary_count']}, events {r['event_count']} — "
                                  + ('matched' if r['matches'] else 'MISMATCH: ' + json.dumps(r)))
        software = result.get('software') or {}
        binding = result.get('project_binding') or {}
        mode = result.get('simulation_mode') or {}
        mode_name = {'simple': 'Simple', 'detailed': 'Detailed',
                     'geometric_compatibility': 'Historical geometric comparison'}.get(mode.get('mode'))
        mode_text = (mode_name + ('; explicitly selected in frozen inputs' if mode.get('selection') == 'explicit'
                                  else '; derived from frozen legacy inputs')) if mode_name else 'Unknown; no verified mode evidence'
        self.evidence.setPlainText('\n'.join([
            'Run: ' + (result['run_id'] or 'Legacy; no native run identity'),
            'Simulation mode: ' + mode_text,
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
        self.clear_events()
        self.timeline_label.setText('Select a task or metric to see its supporting events.')

    def clear_events(self):
        self.event_rows = []
        self.selected_evidence = None
        self.export_selected_button.setEnabled(False)
        self.related_choices = []
        self.follow.blockSignals(True)
        self.follow.clear()
        self.follow.blockSignals(False)
        self.follow.setEnabled(False)
        self.events_by_id = {} if not self.result else getattr(self, 'events_by_id', {})
        self.reset_event_pages()

    def reset_event_pages(self):
        self.event_page.blockSignals(True)
        self.event_page.setRange(1, max(1, (len(self.event_rows) + self.EVENT_PAGE_SIZE - 1) // self.EVENT_PAGE_SIZE))
        self.event_page.setValue(1)
        self.event_page.blockSignals(False)
        self.populate_event_page()

    def show_events(self, ids):
        self.event_rows = sorted([self.events_by_id[eid] for eid in set(ids) if eid in self.events_by_id],
                                 key=lambda e: (e['time_seconds'] is None, e['time_seconds'] or 0, e['source_line']))
        self.reset_event_pages()

    def populate_event_page(self, *_):
        start = (self.event_page.value() - 1) * self.EVENT_PAGE_SIZE
        end = min(start + self.EVENT_PAGE_SIZE, len(self.event_rows))
        self.events.blockSignals(True)
        self.events.clearSelection()
        self.events.setCurrentCell(-1, -1)
        self.events.blockSignals(False)
        self.details.clear()
        self.fill(self.events, [[e[k].replace('_', ' ') if k == 'type' else display(e[k]) for k in ('time_seconds', 'type', 'evidence_kind', 'amr_id', 'lift_id',
                                                        'duration_seconds', 'wait_seconds', 'source_line')] for e in self.event_rows[start:end]])
        self.previous_events.setEnabled(start > 0)
        self.next_events.setEnabled(end < len(self.event_rows))
        self.event_page.setEnabled(bool(self.event_rows))
        self.event_range.setText(f'Events {start + 1:,}–{end:,} of {len(self.event_rows):,}' if self.event_rows else 'No events')

    def select_task(self):
        index = self.tasks.currentRow()
        if 0 <= index < len(self.task_rows):
            task = self.task_rows[index]
            linked = [self.events_by_id[eid] for eid in task['event_ids'] if eid in self.events_by_id]
            self.related_choices = [('task', task['task_id'])]
            self.follow.blockSignals(True)
            self.follow.clear()
            self.follow.addItem(f"Task {task['task_id']} · linked records")
            for kind, field in (('payload', 'payload_instance_id'), ('journey', 'journey_id'), ('lift', 'lift_id')):
                for identity in sorted({e[field] for e in linked if e[field]}):
                    self.related_choices.append((kind, identity))
                    self.follow.addItem(f'{kind.capitalize()} {identity} · all matching run records')
            self.follow.setCurrentIndex(0)
            self.follow.blockSignals(False)
            self.follow.setEnabled(len(self.related_choices) > 1)
            self._show_task(task)

    def _show_task(self, task):
        self.selected_evidence = ('task', task)
        self.export_selected_button.setEnabled(True)
        self.timeline_label.setText(f"{task['task_id']} · {task['outcome']} · release to completion: {display(task['release_to_completion_seconds'])} s\n"
                                    + task['delay_explanation'])
        self.show_events(task['event_ids'])
        self.details.setPlainText('Missing evidence: ' + (', '.join(task['missing_evidence']) or 'None of the principal lifecycle events')
                                  + '\nOrigin: ' + (task['source_rule_path'] or 'Not recorded')
                                  + '\nSelect a timeline event for recorded reasons, route restrictions and source identity.')
        if task.get('stop_snapshot'):
            self.details.appendPlainText('\nPending-state snapshot: ' + task['stop_snapshot'])
        if task['profile_definition'] is not None:
            profile = task['profile_definition']
            lines = ['\nProfile restrictions from saved inputs (task allowances can extend these):']
            for key in ('allowed_nodes', 'allowed_lifts', 'allowed_edges'):
                values = profile.get(key, [])
                text = ', '.join(' → '.join(v) if isinstance(v, list) else str(v) for v in values)
                lines.append(key.replace('_', ' ').capitalize() + ': ' + (text or 'Unrestricted'))
            self.details.appendPlainText('\n'.join(lines))

    def select_active_tab(self, index):
        route_tab=self.tabs.widget(index) is self.route_checks_view
        self.timeline_widget.setVisible(not route_tab)
        self.details.setVisible(not route_tab)
        if route_tab:
            self.clear_events()
            return
        self.follow.setVisible(index == 0)
        if index == 0:
            if self.tasks.currentRow() >= 0:
                self.select_task()
            else:
                self.clear_events()
        elif index == 1:
            if self.metrics.currentRow() >= 0:
                self.select_metric()
            else:
                self.clear_events()
        elif index == 2:
            if self.lift_checks.currentRow() >= 0:
                self.select_lift()
            else:
                self.clear_events()
        if index in (0, 1, 2) and self.selected_evidence is None:
            self.timeline_label.setText('Select a task, metric or lift to see its supporting events.')
            self.details.clear()

    def follow_related(self, index):
        if not self.result or not 0 <= index < len(self.related_choices):
            return
        kind, identity = self.related_choices[index]
        if kind == 'task':
            task = next((t for t in self.task_rows if t['task_id'] == identity), None)
            if task:
                self._show_task(task)
            return
        field = {'payload': 'payload_instance_id', 'journey': 'journey_id', 'lift': 'lift_id'}[kind]
        records = [e for e in self.result['events'] if e[field] == identity]
        origin = self.related_choices[0][1]
        record = {field: identity, 'origin_task_id': origin, 'event_ids': [e['id'] for e in records]}
        self.selected_evidence = (kind, record)
        self.export_selected_button.setEnabled(True)
        self.timeline_label.setText(
            f'{kind.capitalize()} {identity} · {len(records):,} matching records across this run.\n'
            f'Followed from task {origin}; other tasks may share this identity. '
            'Only recorded IDs are linked; planned segments do not prove execution.')
        self.show_events(record['event_ids'])
        self.details.setPlainText(
            f'Run-wide {kind} timeline for {identity}. Select an event for its recorded reason and source row. '
            'The selected-evidence export contains this displayed identity timeline.')

    def select_metric(self):
        index = self.metrics.currentRow()
        if self.result and 0 <= index < len(self.result['metrics']):
            metric = self.result['metrics'][index]
            self.selected_evidence = ('metric', metric)
            self.export_selected_button.setEnabled(True)
            self.timeline_label.setText(metric['title'] + ': ' + display(metric['value']) + '\n' + metric['definition'])
            self.show_events(metric['event_ids'])
            self.details.setPlainText(metric['coverage'] + '\nEach event below contributes to this metric. Shared task lists do not multiply segment counts.')

    def select_lift(self):
        index = self.lift_checks.currentRow()
        if not self.result or not 0 <= index < len(getattr(self, 'lift_rows', [])):
            return
        record = self.lift_rows[index]
        self.selected_evidence = ('lift', record)
        self.export_selected_button.setEnabled(True)
        self.timeline_label.setText(f"{record['lift_id'] or 'Unidentified lift'} · {record['status']}\n"
                                   'Recorded plans checked against frozen initial floors and final bookings; not confirmation of physical execution.')
        related = [eid for p in record['issues'] for eid in p['event_ids']]
        self.show_events(record['event_ids'] + related)
        self.details.setPlainText('\n'.join([
            'Initial floor from saved inputs: ' + display(record['initial_floor']),
            'Recorded movement counts: ' + json.dumps(record['observed']),
            'Final booking counts: ' + (json.dumps(record['expected']) if record['expected'] is not None else 'Not recorded'),
            'Timing tolerance: 0.002 seconds for rounded CSV timestamps.',
            *([p['reason'] for p in record['issues']] or ['No conflicts found in the available records.']),
            'Coverage: ' + ('full bound planned movements' if record['known'] else 'incomplete; absence of a conflict does not prove consistency')]))

    def select_event(self):
        row_index = self.events.currentRow()
        index = (self.event_page.value() - 1) * self.EVENT_PAGE_SIZE + row_index
        if row_index >= 0 and 0 <= index < len(self.event_rows):
            e = self.event_rows[index]
            row = e['row']
            self.details.setPlainText('\n'.join([
                e['explanation'], '', 'Evidence: ' + e['evidence_kind'],
                'Tasks: ' + ', '.join(e['task_ids']),
                'Route: ' + (row.get('from_location') or row.get('start_node') or '?') + ' → ' + (row.get('to_location') or row.get('end_node') or '?'),
                'Profile: ' + (row.get('route_profile') or 'Not recorded'),
                'Payload instance: ' + (e['payload_instance_id'] or 'Not recorded'),
                'Journey: ' + (e['journey_id'] or 'Not recorded'),
                'Lift: ' + (e['lift_id'] or 'Not recorded'),
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

    def export_selected(self):
        if not self.result or self.job or self.selected_evidence is None:
            return
        kind, record = self.selected_evidence
        identity = {'task': 'task_id', 'metric': 'key', 'lift': 'lift_id',
                    'payload': 'payload_instance_id', 'journey': 'journey_id'}[kind]
        payload = {
            'schema_version': 1,
            'kind': 'selected_run_evidence',
            'source': self.result['source'],
            'log_sha256': self.result['log_sha256'],
            'run_id': self.result['run_id'],
            'complete_evidence': self.result['complete_evidence'],
            'project_binding': self.result.get('project_binding'),
            'findings': self.result['findings'],
            'limitations': self.result['limitations'],
            'selection': {'kind': kind, 'identity': record.get(identity), 'record': record},
            'event_count': len(self.event_rows),
            'events': self.event_rows,
        }
        if self.result.get('termination'):
            payload['termination'] = self.result['termination']
        path, _ = QFileDialog.getSaveFileName(self, 'Export selected timeline evidence',
                                              'selected-run-evidence.json', 'JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
            except OSError as exc:
                QMessageBox.critical(self, 'Export failed', str(exc))
