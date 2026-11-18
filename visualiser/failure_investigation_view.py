"""Failure and comparison views backed by cancellable run-evidence readers."""
from collections import Counter
import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from amr_failure_review import compare_failure_reviews, load_failure_review
from visualiser.demand_preview_panel import DemandPreviewPanel


SERVICES = {'department_waste': 'Waste collection', 'waste_bin_replacement': 'Spare-bin delivery'}


def service(name):
    return SERVICES.get(name, name.replace('_', ' ').capitalize() if name else 'Unspecified')


def seconds(value):
    return '—' if value is None else f'{value:,.2f}'


class ReadSignals(QObject):
    progress = Signal(str)
    finished = Signal(object, str)


class ReadJob(QRunnable):
    def __init__(self, read):
        super().__init__()
        self.read = read
        self.cancel = Event()
        self.retired = Event()
        self.signals = ReadSignals()

    def abandon(self):
        self.retired.set()
        self.cancel.set()

    def feedback(self, message):
        if not self.cancel.is_set():
            self.emit('progress', message)

    def emit(self, name, *values):
        if self.retired.is_set():
            return
        try:
            getattr(self.signals, name).emit(*values)
        except RuntimeError:
            if not self.retired.is_set():
                raise

    def run(self):
        result, error = None, ''
        try:
            if not self.cancel.is_set():
                result = self.read(self.cancel.is_set, self.feedback)
        except Exception as exc:
            error = str(exc)
        self.emit('finished', result, error)


class FailureInvestigationView(QWidget):
    review_ready = Signal(object)
    PAGE_SIZE = 500
    table = staticmethod(DemandPreviewPanel.table)
    fill = staticmethod(DemandPreviewPanel.fill)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.compare_source = None
        self.review = self.compared = None
        self.jobs = {}
        self.sources = []
        self.failure_rows, self.pairs, self.event_rows, self.period_rows = [], [], [], []
        self.detail_data = None
        layout = QVBoxLayout(self)
        self.status = QLabel('Select a run to investigate failures.')
        self.status.setWordWrap(True)
        self.stop = QPushButton('Cancel reading')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel_reads)
        layout.addLayout(self.bar(self.status, self.stop))
        self.panes = QTabWidget()
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.panes)
        splitter.addWidget(self.make_evidence())
        splitter.setSizes([340, 390])
        layout.addWidget(splitter, 1)
        self.panes.addTab(self.make_failures(), 'Failures')
        self.panes.addTab(self.make_comparison(), 'Compare runs')
        self.panes.currentChanged.connect(lambda _: self.reset_detail())
        jobs = self.jobs

        def abandon_reads():
            for job in jobs.values():
                job.abandon()
            jobs.clear()

        self.destroyed.connect(abandon_reads)

    @staticmethod
    def bar(*widgets):
        row = QHBoxLayout()
        for widget in widgets:
            row.addWidget(widget, int(isinstance(widget, (QLabel, QLineEdit, QComboBox))))
        if not any(row.stretch(index) for index in range(row.count())):
            row.addStretch()
        return row

    def make_failures(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find a task, location, payload, AMR or lift…')
        self.search.setAccessibleName('Filter failures by task, location, payload, AMR or lift')
        self.search.textChanged.connect(self.show_failures)
        self.outcome = QComboBox()
        self.outcome.setAccessibleName('Filter failure status')
        self.outcome.addItems(['All shown outcomes', 'Failed', 'Pending at stop', 'Conflicting outcomes'])
        self.outcome.currentIndexChanged.connect(self.show_failures)
        layout.addLayout(self.bar(self.search, self.outcome))
        self.groups = self.table(['Location', 'Service', 'Blocker', 'Outcome', 'Count'])
        self.groups.setAccessibleName('Counts grouped by location, service and blocker')
        self.groups.setMaximumHeight(112)
        layout.addWidget(self.groups)
        self.failures = self.table(['Task', 'Outcome', 'Location', 'Service', 'Payload', 'Blocker', 'Time (s)'])
        self.failures.setAccessibleName('Failed and pending tasks')
        self.failures.itemSelectionChanged.connect(self.choose_failure)
        layout.addWidget(self.failures, 1)
        return page

    def make_comparison(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.choice = QComboBox()
        self.choice.setAccessibleName('Comparison run')
        self.choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.choice.setMinimumContentsLength(16)
        self.compare_button = QPushButton('Compare')
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self.compare_selected)
        self.compare_folder = QPushButton('Choose saved run…')
        self.compare_folder.setEnabled(False)
        self.compare_folder.clicked.connect(self.compare_from_folder)
        self.choice.currentIndexChanged.connect(self.update_compare_button)
        layout.addLayout(self.bar(self.choice, self.compare_button, self.compare_folder))
        self.comparison_status = QLabel('Choose a second run to compare with the selected run.')
        self.comparison_status.setWordWrap(True)
        layout.addWidget(self.comparison_status)
        self.comparison_groups = self.table(['Location', 'Service', 'Blocker', 'Before', 'After', 'Change',
                                              'Before mean (s)', 'After mean (s)'])
        self.comparison_groups.setToolTip('Mean seconds from release to failure. Parentheses show the measured task count.')
        self.comparison_groups.setMaximumHeight(112)
        layout.addWidget(self.comparison_groups)
        self.comparison_tasks = self.table(['Outcome change', 'Before task', 'After task', 'Location',
                                             'Before elapsed (s)', 'After elapsed (s)'])
        self.comparison_tasks.itemSelectionChanged.connect(self.update_evidence_buttons)
        layout.addWidget(self.comparison_tasks, 1)
        self.before_evidence = QPushButton('Open before evidence')
        self.after_evidence = QPushButton('Open after evidence')
        self.before_evidence.clicked.connect(lambda: self.open_pair('before'))
        self.after_evidence.clicked.connect(lambda: self.open_pair('after'))
        layout.addLayout(self.bar(self.before_evidence, self.after_evidence))
        self.update_evidence_buttons()
        return page

    def make_evidence(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.detail_label = QLabel('Select a task to see linked evidence.')
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        self.periods = self.table(['Time spent', 'Start (s)', 'End (s)', 'Duration (s)'])
        self.periods.setAccessibleName('Non-overlapping time intervals and their evidence')
        self.periods.setMaximumHeight(105)
        self.periods.cellActivated.connect(self.follow_period)
        self.all_events = QPushButton('All linked events')
        self.all_events.clicked.connect(self.show_all_events)
        self.page = QSpinBox()
        self.page.setAccessibleName('Failure evidence page')
        self.page.setPrefix('Page ')
        self.page.setRange(1, 1)
        self.page.valueChanged.connect(self.fill_event_page)
        self.page_count = QLabel()
        layout.addWidget(self.periods)
        layout.addLayout(self.bar(self.all_events, self.page, self.page_count))
        self.events = self.table(['Time (s)', 'Event', 'Task', 'Relationship', 'AMR', 'Lift', 'Location', 'Evidence ID'])
        self.events.setAccessibleName('Failure timeline and linked events')
        self.events.itemSelectionChanged.connect(self.show_event)
        layout.addWidget(self.events, 1)
        self.event_detail = QPlainTextEdit()
        self.event_detail.setAccessibleName('Selected failure event evidence')
        self.event_detail.setReadOnly(True)
        self.event_detail.setMaximumHeight(100)
        layout.addWidget(self.event_detail)
        self.reset_detail()
        return page

    def set_sources(self, sources):
        self.sources = sources
        self.choice.clear()
        self.choice.addItem('Choose a run…')
        self.choices = [source for _, source in sources if not self.same_source(source, self.source)]
        self.choice.addItems([name for name, source in sources if not self.same_source(source, self.source)])
        self.update_compare_button()

    @staticmethod
    def same_source(left, right):
        if isinstance(left, (str, Path)) and isinstance(right, (str, Path)):
            return Path(left).resolve() == Path(right).resolve()
        return left is right

    def update_compare_button(self):
        self.compare_button.setEnabled(self.review is not None and self.choice.currentIndex() > 0)
        self.compare_folder.setEnabled(self.review is not None)

    def run_job(self, key, read, done):
        prior = self.jobs.pop(key, None)
        if prior:
            prior.abandon()
        job = ReadJob(read)
        self.jobs[key] = job

        def finish(result, error):
            if self.jobs.get(key) is not job:
                return
            self.jobs.pop(key)
            self.stop.setEnabled(bool(self.jobs))
            done(result, 'Reading cancelled.' if job.cancel.is_set() else error)

        job.signals.finished.connect(finish)
        job.signals.progress.connect(lambda message: self.status.setText(message) if self.jobs.get(key) is job else None)
        self.stop.setEnabled(True)
        QThreadPool.globalInstance().start(job)

    def cancel_reads(self):
        for job in self.jobs.values():
            job.cancel.set()

    def clear(self):
        for job in self.jobs.values():
            job.abandon()
        self.jobs.clear()
        self.stop.setEnabled(False)
        self.source, self.review = None, None
        self.clear_comparison()
        self.reset_detail()
        self.show_failures()
        self.update_compare_button()

    def clear_comparison(self):
        job = self.jobs.pop('comparison', None)
        if job:
            job.abandon()
        self.compare_source, self.compared = None, None
        self.pairs = []
        self.comparison_groups.setRowCount(0)
        self.comparison_tasks.setRowCount(0)
        self.comparison_status.setText('Choose a second run to compare with the selected run.')
        self.update_evidence_buttons()
        self.stop.setEnabled(bool(self.jobs))

    def forget_memory(self, run):
        if self.source is run:
            self.clear()
            self.status.setText('The memory run has been closed.')
        elif self.compare_source is run:
            self.clear_comparison()
            self.reset_detail()
        self.set_sources([(name, source) for name, source in self.sources if source is not run])

    def load(self, source):
        self.clear()
        self.source = source
        self.set_sources(self.sources)
        self.panes.setCurrentIndex(0)
        self.status.setText('Reading failure evidence…')
        self.run_job('review', lambda cancel, feedback: load_failure_review(source, cancel=cancel,
                     progress=lambda msg: feedback(msg['phase'])), self.accept_review)

    def accept_review(self, result, error):
        self.review = result
        self.set_sources(self.sources)
        self.show_failures()
        if error:
            self.status.setText(error)
        elif result:
            self.review_ready.emit(result)

    @staticmethod
    def run_summary(review):
        counts = Counter(task['service'] for task in review.failures if task['outcome'] == 'Failed')
        failed = sum(counts.values())
        pending = sum(task['outcome'] == 'Pending at stop' for task in review.failures)
        demand = sum(t['released'] and t['service'] != 'waste_bin_replacement' and not t['id'].startswith('IDLE-')
                     for t in review.tasks.values())
        coverage = 'full event coverage' if review.complete and not review.reconciliation else 'partial or unverified event coverage'
        return (f'{review.name} · {review.storage} · {coverage}\n'
                f'{demand:,} recorded service requests · {failed:,} failed · {pending:,} pending at stop · '
                f'{counts["department_waste"]:,} failed waste collections · '
                f'{counts["waste_bin_replacement"]:,} failed spare deliveries')

    def show_failures(self, *_):
        query, outcome = self.search.text().strip().casefold(), self.outcome.currentText()
        self.failure_rows = []
        if self.review:
            for task in self.review.failures:
                related = self.review.filter_resources.get(task['id'], {})
                fields = [task[k] for k in ('id', 'location', 'destination', 'payload', 'department', 'blocker')]
                fields.extend(value for values in related.values() for value in values)
                if (not query or query in ' '.join(fields).casefold()) and outcome in ('All shown outcomes', task['outcome']):
                    self.failure_rows.append(task)
            self.status.setText(self.run_summary(self.review) + ('\n' + '\n'.join(self.review.reconciliation)
                                                                if self.review.reconciliation else ''))
        self.failures.blockSignals(True)
        self.failures.clearSelection()
        self.failures.setCurrentCell(-1, -1)
        self.fill(self.failures, [[t['id'], t['outcome'], t['location'], service(t['service']),
                                  t['payload'], t['blocker'], seconds(t['end'])] for t in self.failure_rows])
        self.failures.blockSignals(False)
        counts = Counter((t['location'], service(t['service']), t['blocker'], t['outcome']) for t in self.failure_rows)
        self.fill(self.groups, [list(key) + [value] for key, value in sorted(counts.items())])
        if self.panes.currentIndex() == 0:
            self.reset_detail()

    def choose_failure(self):
        row = self.failures.currentRow()
        if self.review and 0 <= row < len(self.failure_rows):
            self.read_detail(self.review, self.failure_rows[row]['id'])

    def compare_selected(self):
        index = self.choice.currentIndex() - 1
        if 0 <= index < len(self.choices):
            self.compare_with(self.choices[index])

    def compare_from_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose saved comparison run')
        if path:
            self.compare_with(path)

    def compare_with(self, source):
        if self.review is None or self.same_source(source, self.source):
            return
        self.clear_comparison()
        self.reset_detail()
        self.compare_source = source
        self.comparison_status.setText('Reading comparison run…')
        base = self.review

        def read(cancel, feedback):
            candidate = load_failure_review(source, cancel=cancel, progress=lambda msg: feedback(msg['phase']))
            return candidate, compare_failure_reviews(base, candidate, cancel=cancel)

        self.run_job('comparison', read, self.accept_comparison)

    def accept_comparison(self, result, error):
        if error:
            self.comparison_status.setText(error)
            return
        self.compared, comparison = result
        self.status.setText(self.run_summary(self.review))
        self.comparison_status.setText('Before · ' + self.run_summary(self.review) + '\nAfter · ' + self.run_summary(self.compared))
        self.fill(self.comparison_groups, [[g['location'], service(g['service']), g['blocker'], g['before'], g['after'],
            f"{g['after'] - g['before']:+d}", seconds(g['before_wait']) + f" ({g['before_measured']})",
            seconds(g['after_wait']) + f" ({g['after_measured']})"] for g in comparison['groups']])
        self.pairs = comparison['requests'] + comparison['unmatched']
        self.fill(self.comparison_tasks, [self.pair_cells(pair) for pair in self.pairs])
        self.update_evidence_buttons()

    @staticmethod
    def pair_cells(pair):
        sides = [pair[k] for k in ('before', 'after')]
        representative = (sides[0] or sides[1])[0]
        elapsed = [seconds(group[0]['end'] - group[0]['release'])
                   if len(group) == 1 and group[0]['end'] is not None and group[0]['release'] is not None else '—'
                   for group in sides]
        return [pair['status'], *(', '.join(t['id'] for t in group) for group in sides), representative['location'], *elapsed]

    def update_evidence_buttons(self):
        index = self.comparison_tasks.currentRow()
        pair = self.pairs[index] if 0 <= index < len(self.pairs) else None
        self.before_evidence.setEnabled(bool(pair and pair['before']))
        self.after_evidence.setEnabled(bool(pair and pair['after']))

    def open_pair(self, side):
        index = self.comparison_tasks.currentRow()
        if self.compared is None or not 0 <= index < len(self.pairs):
            return
        choices = [task['id'] for task in self.pairs[index][side]]
        if not choices:
            return
        if len(choices) == 1:
            key = choices[0]
        else:
            from PySide6.QtWidgets import QInputDialog
            key, chosen = QInputDialog.getItem(self, 'Choose a request', 'Task', choices, editable=False)
            if not chosen:
                return
        self.read_detail(self.review if side == 'before' else self.compared, key)

    def reset_detail(self):
        prior = self.jobs.pop('detail', None)
        if prior:
            prior.abandon()
            self.stop.setEnabled(bool(self.jobs))
        self.detail_data = None
        self.period_rows = []
        self.periods.setRowCount(0)
        self.detail_label.setText('Select a task to see linked evidence.')
        self.set_events([])

    def read_detail(self, review, key):
        self.reset_detail()
        self.detail_label.setText('Reading linked events…')
        self.run_job('detail', lambda cancel, _: review.detail(key, cancel=cancel),
                     lambda detail, error: self.accept_detail(review, detail, error))

    def accept_detail(self, review, detail, error):
        if error:
            self.detail_label.setText(error)
            return
        self.detail_data = detail
        task = detail['task']
        timings = ' · '.join(f'{name} {seconds(value)} s' for name, value in detail['totals'].items() if value)
        timeline = f"Release {seconds(task['release'])} s · deadline {seconds(task['deadline'])} s · " \
                   f"commit {seconds(task['dispatch'])} s · planned start {seconds(task['planned_start'])} s"
        lines = [f"{task['id']} · {task['outcome']} · {review.name}", timeline]
        if task['reason']:
            lines.append(task['reason'])
        snapshot = task['snapshot']
        stock, bays = snapshot.get('stock'), snapshot.get('bays')
        if stock:
            holders = ', '.join(claim['task_id'] for claim in stock['reserved'])
            lines.append(f"{stock['location']} · {stock['available']} available of {stock['empty']} empty bins"
                         + (f' · held by {holders}' if holders else ''))
        if bays:
            lines.append(f"{bays['location']} · {bays['free']} of {bays['compatible']} compatible bays free · "
                         f"{bays['occupied']} occupied · {bays['reserved']} reserved")
        for spare in snapshot.get('spares', ())[:3]:
            state = 'staged' if spare['staged'] else 'assigned' if spare['amr_id'] else 'unassigned'
            lines.append(f"Spare {spare['task_id']} · {state}"
                         + (f" · claimed by {spare['claimed_by']}" if spare['claimed_by'] else ''))
        if timings:
            lines.append(timings)
        if not review.structured:
            lines.append('This run predates structured reservation and blocker evidence. Nearby trips are context only.')
        self.detail_label.setText('\n'.join(lines))
        self.period_rows = detail['periods']
        self.fill(self.periods, [[p['category'], seconds(p['start']), seconds(p['end']), seconds(p['end'] - p['start'])]
                                 for p in self.period_rows])
        self.show_all_events()

    def follow_period(self, row, _column):
        if self.detail_data and 0 <= row < len(self.period_rows):
            identities = set(self.period_rows[row]['event_ids'])
            self.set_events([event for event in self.detail_data['rows'] if event.get('event_id') in identities])

    def show_all_events(self):
        self.set_events(self.detail_data['rows'] if self.detail_data else [])

    def set_events(self, rows):
        self.event_rows = rows
        self.page.blockSignals(True)
        self.page.setRange(1, max(1, (len(rows) + self.PAGE_SIZE - 1) // self.PAGE_SIZE))
        self.page.setValue(1)
        self.page.setEnabled(bool(rows))
        self.page.blockSignals(False)
        self.all_events.setEnabled(self.detail_data is not None and bool(rows))
        self.fill_event_page()

    def fill_event_page(self, *_):
        begin = (self.page.value() - 1) * self.PAGE_SIZE
        page = self.event_rows[begin:begin + self.PAGE_SIZE]
        related = self.detail_data['related'] if self.detail_data else {}
        self.events.blockSignals(True)
        self.events.clearSelection()
        self.events.setCurrentCell(-1, -1)
        self.fill(self.events, [[r.get('sim_time_sec'), r['event_type'].replace('_', ' '), r.get('task_id', ''),
            related.get(r.get('task_id'), 'Linked journey'), r.get('amr_id', ''), r.get('lift_id', ''),
            r.get('from_location') or r.get('to_location', ''), r.get('event_id', '')] for r in page])
        self.events.blockSignals(False)
        self.event_detail.clear()
        self.page_count.setText(f'{begin + 1:,}–{begin + len(page):,} of {len(self.event_rows):,} events' if page else 'No events')

    def show_event(self):
        index = (self.page.value() - 1) * self.PAGE_SIZE + self.events.currentRow()
        if self.events.currentRow() < 0 or not 0 <= index < len(self.event_rows):
            return
        row = self.event_rows[index]
        kind = row['event_type']
        label = ('Planned movement' if 'segment_' in kind or kind.endswith('_assigned') else
                 'Confirmed in simulation' if kind in ('location_payload_exit', 'location_payload_enter',
                 'waste_replacement_staged', 'task_complete', 'multi_stop_task_complete') else 'Recorded event')
        description = row.get('details') or ''
        if description.startswith('{'):
            try:
                description = json.dumps(json.loads(description), indent=2, ensure_ascii=False)
            except ValueError:
                pass
        self.event_detail.setPlainText('\n'.join(filter(None, (label, row.get('sim_datetime'), row.get('event_id'),
            row.get('from_location'), row.get('to_location'), row.get('pending_reason'), description))))
