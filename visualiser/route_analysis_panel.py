"""Independent Lift & Route Analysis workspace; no report-generation dependency."""
from datetime import datetime
from pathlib import Path
import json
import threading

from PySide6.QtCore import (Qt, QObject, QRunnable, QThreadPool, Signal, QAbstractTableModel, QModelIndex)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QDoubleSpinBox, QTabWidget, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableView, QHeaderView, QAbstractItemView, QPlainTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QScrollArea)

from amr_route_analysis import (load_analysis, compare_runs, export_comparison, Filters,
    CONFIRMED, PLANNED, SATISFIED, VIOLATION, UNKNOWN, DISABLED, route_group_values)
from visualiser.route_analysis_views import RouteMap, LiftHeatmap, LiftTimeline, fmt


class TableModel(QAbstractTableModel):
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers, self.rows = headers, []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in (Qt.DisplayRole, Qt.ToolTipRole):
            return fmt(self.rows[index.row()][index.column()])
        if index.isValid() and role == Qt.TextAlignmentRole and isinstance(self.rows[index.row()][index.column()], (int,float)):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.headers[section] if orientation == Qt.Horizontal else section + 1

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class PagedTable(QWidget):
    selected = Signal(object)
    activated = Signal(object)
    PAGE_SIZE = 250

    def __init__(self, name, headers, parent=None):
        super().__init__(parent)
        self.records, self.values, self.page = [], [], 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QTableView()
        self.view.setAccessibleName(name)
        self.model = TableModel(headers, self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.horizontalHeader().setDefaultSectionSize(145)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.selectionModel().currentRowChanged.connect(self._selected)
        self.view.doubleClicked.connect(lambda index: self._emit(index, self.activated))
        self.view.activated.connect(lambda index: self._emit(index, self.activated))
        layout.addWidget(self.view)
        bar = QHBoxLayout()
        self.previous = QPushButton('Previous page')
        self.next = QPushButton('Next page')
        self.previous.clicked.connect(lambda: self.change_page(-1))
        self.next.clicked.connect(lambda: self.change_page(1))
        self.count = QLabel('0 rows')
        for item in (self.previous, self.count, self.next):
            bar.addWidget(item)
        bar.addStretch()
        layout.addLayout(bar)

    def _emit(self, index, signal):
        row = self.page * self.PAGE_SIZE + index.row()
        if index.isValid() and row < len(self.records):
            signal.emit(self.records[row])

    def _selected(self, index, previous):
        self._emit(index, self.selected)

    def set_records(self, records, values):
        self.records, self.values, self.page = list(records), list(values), 0
        self.render()

    def change_page(self, delta):
        self.page = max(0, min(self.page + delta, max(0, (len(self.records)-1)//self.PAGE_SIZE)))
        self.render()

    def render(self):
        start = self.page * self.PAGE_SIZE
        finish = min(start + self.PAGE_SIZE, len(self.records))
        self.model.set_rows(self.values[start:finish])
        self.count.setText(f'{start+1 if self.records else 0:,}–{finish:,} of {len(self.records):,}')
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(finish < len(self.records))


class AnalysisSignals(QObject):
    finished = Signal(str, int, object, str)
    progress = Signal(str, int, str)


class AnalysisJob(QRunnable):
    def __init__(self, slot, token, operation):
        super().__init__()
        self.slot, self.token, self.operation = slot, token, operation
        self.cancelled = threading.Event()
        self.signals = AnalysisSignals()

    def run(self):
        try:
            result = self.operation(self.cancelled.is_set,
                lambda message: self.signals.progress.emit(self.slot, self.token, message))
            if self.cancelled.is_set():
                raise InterruptedError('Analysis cancelled; previous results retained.')
            self.signals.finished.emit(self.slot, self.token, result, '')
        except Exception as exc:
            self.signals.finished.emit(self.slot, self.token, None, str(exc))


class RouteAnalysisPanel(QWidget):
    def __init__(self, editor=None):
        super().__init__(editor)
        self.editor = editor
        self.runs = {'A': None, 'B': None}
        self.result = None
        self.tokens = {'A': 0, 'B': 0, 'compare': 0, 'export': 0}
        self.jobs = {}
        self.active_jobs = set()
        self.selected_legs = {'A': None, 'B': None}
        self.chart_pair = (None, None)
        root = QVBoxLayout(self)
        title = QLabel('Lift & Route Analysis')
        title.setProperty('sectionHeading', True)
        root.addWidget(title)
        self.sources, self.source_status = {}, {}
        selectors = QHBoxLayout()
        for label in ('A', 'B'):
            box = QGroupBox(f'Run {label}' + (' · baseline' if label == 'A' else ' · comparison (optional)'))
            layout = QVBoxLayout(box)
            choice = QComboBox()
            choice.setEditable(True)
            choice.setInsertPolicy(QComboBox.NoInsert)
            choice.setAccessibleName(f'Run {label} source')
            choice.setMinimumContentsLength(18)
            self.sources[label] = choice
            layout.addWidget(choice)
            bar = QHBoxLayout()
            for text, callback in [('Run folder…', lambda _=False, s=label: self.choose(s, True)),
                                   ('Event log…', lambda _=False, s=label: self.choose(s, False)),
                                   ('Load', lambda _=False, s=label: self.load(s, self.selected_source(s)))]:
                button = QPushButton(text)
                button.clicked.connect(callback)
                bar.addWidget(button)
            if label == 'B':
                clear = QPushButton('Clear B')
                clear.clicked.connect(self.clear_b)
                bar.addWidget(clear)
            layout.addLayout(bar)
            status = QLabel('No run selected')
            status.setWordWrap(True)
            self.source_status[label] = status
            layout.addWidget(status)
            selectors.addWidget(box)
        root.addLayout(selectors)
        filters_box = QGroupBox('Shared filters · elapsed seconds')
        grid = QGridLayout(filters_box)
        self.start, self.end = QDoubleSpinBox(), QDoubleSpinBox()
        for spin, name in ((self.start, 'Window start seconds'), (self.end, 'Window end seconds')):
            spin.setRange(0, 1e12)
            spin.setDecimals(3)
            spin.setAccessibleName(name)
        self.end.setValue(1)
        grid.addWidget(QLabel('From (s)'), 0, 0)
        grid.addWidget(self.start, 0, 1)
        grid.addWidget(QLabel('To (s)'), 0, 2)
        grid.addWidget(self.end, 0, 3)
        reset = QPushButton('Reset filters / shared window')
        reset.clicked.connect(self.reset_filters)
        grid.addWidget(reset, 0, 4, 1, 2)
        self.filters = {}
        for index, (key, name) in enumerate((('floor', 'Floor'), ('lift', 'Lift'), ('amr', 'AMR'),
                ('purpose', 'Purpose'), ('profile', 'Route profile'), ('origin', 'Origin'),
                ('destination', 'Destination'), ('evidence', 'Evidence'), ('compliance', 'Forced-floor result'))):
            row, col = 1+index//3, (index%3)*2
            combo = QComboBox()
            combo.setAccessibleName(name + ' filter')
            combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.addItem('All', None if key == 'floor' else '')
            self.filters[key] = combo
            grid.addWidget(QLabel(name), row, col)
            grid.addWidget(combo, row, col+1)
        root.addWidget(filters_box)
        filters_box.hide()
        actions = QHBoxLayout()
        toggle_filters = QPushButton('Filters / time window')
        toggle_filters.setCheckable(True)
        toggle_filters.toggled.connect(filters_box.setVisible)
        actions.addWidget(toggle_filters)
        self.apply_button = QPushButton('Apply filters')
        self.apply_button.clicked.connect(self.refresh_comparison)
        self.apply_button.setEnabled(False)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton('Export comparison…')
        self.export_button.setToolTip('Export all filtered tables, journeys, source events and saved input evidence.')
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        self.chart_label = QLabel('')
        clear_chart = QPushButton('Clear chart selection')
        clear_chart.clicked.connect(self.clear_chart)
        for item in (self.apply_button, self.cancel_button, self.export_button, clear_chart, self.chart_label):
            actions.addWidget(item)
        actions.addStretch()
        root.addLayout(actions)
        self.status = QLabel('Open a saved run. General route analysis works with forced-floor routing on or off.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._overview()
        self._routes()
        self._inspector()
        self._lifts()
        self._compliance()
        self.refresh_sources()

    def _add_tab(self, page, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)

    def _overview(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel('A and B share an elapsed-time window. Distance and lift totals describe recorded plans. '
                      'Journey-time averages require confirmed complete legs. Workload counts use the full run within this window.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.metrics = PagedTable('A B metric comparison', ['Metric', 'Run A', 'Run B', 'B − A', 'Change (%)'])
        self.metrics.view.horizontalHeader().setStretchLastSection(False)
        self.metrics.view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for column in range(1,5):
            self.metrics.view.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        layout.addWidget(self.metrics, 2)
        self.context = QPlainTextEdit()
        self.context.setReadOnly(True)
        self.context.setAccessibleName('Saved settings differences and evidence coverage')
        layout.addWidget(self.context, 1)
        self._add_tab(page, 'Overview')

    def _routes(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel('Expand an origin–destination group to compare recorded path variants. Select journeys independently below; '
                      'double-click a journey to inspect its route. Counts are movement legs, not payload task counts.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter(Qt.Vertical)
        self.route_tree = QTreeWidget()
        self.route_tree.setAccessibleName('Route groups and recorded variants')
        self.route_tree.setHeaderLabels(['Origin → destination / variant', 'Purpose', 'Profile', 'A legs', 'B legs', 'Δ legs',
            'A mean m', 'B mean m', 'A mean journey s', 'B mean journey s', 'A mean lift wait s', 'B mean lift wait s'])
        self.route_tree.setColumnWidth(0, 330)
        self.route_tree.currentItemChanged.connect(self.select_group)
        split.addWidget(self.route_tree)
        trips = QSplitter()
        self.trips = {}
        for label in ('A', 'B'):
            box = QGroupBox(f'Run {label} · individual journeys')
            box_layout = QVBoxLayout(box)
            table = PagedTable(f'Run {label} journeys', ['Start (s)', 'AMR', 'Origin', 'Destination', 'Distance (m)', 'Lift wait (s)', 'Evidence', 'Forced floor'])
            table.selected.connect(lambda leg, side=label: self.select_leg(side, leg))
            table.activated.connect(lambda leg, side=label: self.open_leg(side, leg))
            self.trips[label] = table
            box_layout.addWidget(table)
            trips.addWidget(box)
        split.addWidget(trips)
        split.setSizes([250, 250])
        layout.addWidget(split)
        self._add_tab(page, 'AMR routes')

    def _inspector(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter()
        self.maps = {}
        for label in ('A', 'B'):
            self.maps[label] = RouteMap(label)
            split.addWidget(self.maps[label])
        layout.addWidget(split, 2)
        show_events = QPushButton('Show source events')
        show_events.setCheckable(True)
        layout.addWidget(show_events)
        self.evidence = PagedTable('Selected journeys source event evidence', ['Run', 'Event', 'Type', 'From', 'To', 'Start (s)', 'End (s)', 'Lift', 'Details'])
        layout.addWidget(self.evidence, 1)
        self.evidence.hide()
        show_events.toggled.connect(self.evidence.setVisible)
        self._add_tab(page, 'Route inspector')

    def _lifts(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.lift_consistency = QLabel('Lift consistency checks use saved bookings and recorded movements.')
        self.lift_consistency.setWordWrap(True)
        layout.addWidget(self.lift_consistency)
        self.lift_mode = QComboBox()
        self.lift_mode.addItems(['Transfers and empty repositioning', 'Transfers only', 'Empty repositioning only'])
        self.lift_mode.setAccessibleName('Lift chart movement type')
        self.lift_mode.currentIndexChanged.connect(self.render_lifts)
        layout.addWidget(self.lift_mode)
        maps = QHBoxLayout()
        self.heatmaps = {}
        for label in ('A', 'B'):
            box = QGroupBox(f'Run {label} · floor-to-floor movements')
            box_layout = QVBoxLayout(box)
            heatmap = LiftHeatmap(label)
            heatmap.selectedPair.connect(self.select_pair)
            self.heatmaps[label] = heatmap
            box_layout.addWidget(heatmap)
            maps.addWidget(box)
        layout.addLayout(maps, 1)
        self.timeline = LiftTimeline()
        self.timeline.selectedLift.connect(self.select_lift)
        layout.addWidget(self.timeline, 1)
        self.lift_table = PagedTable('Recorded lift movements', ['Run', 'Lift', 'Movement', 'From floor', 'To floor', 'Start (s)', 'End (s)', 'AMR', 'Event', 'Fallback reason', 'Bed lifts', 'Predicted FM wait (s)', 'Estimated saving (s)'])
        layout.addWidget(self.lift_table, 1)
        self._add_tab(page, 'Lifts')

    def _compliance(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.compliance_summary = QLabel('Load a run to check its saved forced-floor policy.')
        self.compliance_summary.setWordWrap(True)
        layout.addWidget(self.compliance_summary)
        self.checks = PagedTable('Forced-floor checks and exceptions', ['Run', 'Result', 'Origin', 'Destination', 'AMR', 'Start (s)', 'Evidence', 'Reason'])
        self.checks.activated.connect(lambda record: self.open_leg(*record))
        self.checks.selected.connect(lambda record: self.select_leg(*record))
        layout.addWidget(self.checks)
        self._add_tab(page, 'Forced-floor checks')

    def refresh_sources(self):
        project = getattr(self.editor, 'project', None)
        if project is None:
            return
        choices = []
        for ref in project.external_results.get('runs', []):
            try:
                choices.append((ref.get('name') or ref['run_key'], str(project.resolve_results_location(ref['location']))))
            except (KeyError, ValueError):
                continue
        for combo in self.sources.values():
            old = combo.currentText()
            combo.clear()
            combo.addItem('', '')
            for title, path in choices:
                combo.addItem(title, path)
            combo.setEditText(old)

    def choose(self, label, folder):
        source = (QFileDialog.getExistingDirectory(self, f'Open run {label} folder') if folder else
                  QFileDialog.getOpenFileName(self, f'Open run {label} event log', '', 'Simulation events (*.csv *.sqlite)')[0])
        if source:
            self.load(label, source)

    def selected_source(self, label):
        combo = self.sources[label]
        if combo.currentText() == combo.itemText(combo.currentIndex()):
            return combo.currentData() or combo.currentText()
        return combo.currentText()

    def _start(self, slot, operation):
        old = self.jobs.get(slot)
        if old:
            old.cancelled.set()
        self.tokens[slot] += 1
        job = AnalysisJob(slot, self.tokens[slot], operation)
        self.jobs[slot] = job
        self.active_jobs.add(job)
        job.signals.progress.connect(self._progress)
        job.signals.finished.connect(self._finished)
        self.cancel_button.setEnabled(True)
        QThreadPool.globalInstance().start(job)

    def load(self, label, source):
        if not source:
            return
        if label not in self.runs:
            raise ValueError('Run must be A or B')
        self.sources[label].setEditText(str(source))
        self.source_status[label].setText('Loading saved evidence…')
        self._invalidate_comparison()
        self._start(label, lambda cancel, progress: load_analysis(source, cancel=cancel, progress=progress))

    def _invalidate_comparison(self):
        job = self.jobs.get('compare')
        if job:
            job.cancelled.set()
        self.tokens['compare'] += 1
        self.export_button.setEnabled(False)

    def _progress(self, slot, token, message):
        if token == self.tokens[slot]:
            self.status.setText(f'{slot}: {message}')

    def _finished(self, slot, token, result, error):
        for job in list(self.active_jobs):
            if job.slot == slot and job.token == token:
                self.active_jobs.remove(job)
                if self.jobs.get(slot) is job:
                    self.jobs.pop(slot)
        self.cancel_button.setEnabled(bool(self.jobs))
        if token != self.tokens[slot]:
            return
        if error:
            self.status.setText(error + ' Previous valid views are retained.')
            if slot in self.runs:
                self.source_status[slot].setText('Load failed or cancelled · previous run retained')
            return
        if slot in self.runs:
            self.runs[slot] = result
            self.source_status[slot].setText(f'{len(result.legs):,} route legs · {len(result.movements):,} lift movements · '
                + ('full saved evidence' if result.complete else 'limited / partial evidence'))
            self.populate_filters()
            self.reset_filters()
        elif slot == 'compare':
            self.result = result
            self.render()
        elif slot == 'export':
            self.status.setText(f'Exported comparison and source evidence to {result}')
            self.export_button.setEnabled(self.result is not None)

    def cancel(self):
        for job in self.jobs.values():
            job.cancelled.set()
        self.status.setText('Cancelling… Previous valid views will be retained.')

    def shutdown(self):
        for slot in self.tokens:
            self.tokens[slot] += 1
        self.cancel()

    def clear_b(self):
        self.tokens['B'] += 1
        if self.jobs.get('B'):
            self.jobs['B'].cancelled.set()
        self.runs['B'] = None
        self.sources['B'].setEditText('')
        self.source_status['B'].setText('No run selected')
        self.populate_filters()
        self.reset_filters()

    def populate_filters(self):
        legs = [leg for run in self.runs.values() if run for leg in run.legs]
        for key, combo in self.filters.items():
            old = combo.currentData()
            if key == 'floor':
                values = sorted({floor for leg in legs for floor in leg.floors})
            elif key == 'lift':
                values = sorted({s.lift for run in self.runs.values() if run for s in run.movements if s.lift})
            else:
                values = sorted({getattr(leg, key) for leg in legs if getattr(leg, key)})
            combo.clear()
            combo.addItem('All', None if key == 'floor' else '')
            for value in values:
                combo.addItem(fmt(value), value)
            index = combo.findData(old)
            combo.setCurrentIndex(max(0, index))

    def reset_filters(self):
        loaded = [run for run in self.runs.values() if run]
        self.start.setValue(0)
        self.end.setValue(min((run.duration for run in loaded), default=1))
        for combo in self.filters.values():
            combo.setCurrentIndex(0)
        self.chart_pair = (None, None)
        self.chart_label.clear()
        self.refresh_comparison()

    def filter_value(self):
        return Filters(start=self.start.value(), end=self.end.value(),
                       **{key: combo.currentData() for key, combo in self.filters.items()},
                       lift_origin_floor=self.chart_pair[0], lift_destination_floor=self.chart_pair[1])

    def refresh_comparison(self):
        self.apply_button.setEnabled(self.runs['A'] is not None)
        if not self.runs['A']:
            return
        a, b, filters = self.runs['A'], self.runs['B'], self.filter_value()
        self.export_button.setEnabled(False)
        self.status.setText('Updating comparison… Previous views remain visible until complete.')
        self._start('compare', lambda cancel, progress: compare_runs(a, b, filters, cancel=cancel))

    def render(self):
        result = self.result
        self.metrics.set_records(result['metrics'], [[r[k] for k in ('metric','a','b','delta','percent')] for r in result['metrics']])
        messages = []
        for label, side in zip(('A','B'), result['sides']):
            if not side:
                continue
            run = side['run']
            building = run.config.get('building', {})
            policy = ('ON · required floor ' + str(building.get('force_via_floor'))) if building.get('force_via_floor_enabled') is True else 'OFF' if run.config else 'Unknown'
            messages.extend([f'Run {label}: {run.source}', f'Forced floor: {policy}; saved horizon {fmt(run.duration)} s',
                             'Route profiles: ' + ', '.join(run.config.get('route_profiles', {})), *run.warnings, ''])
        if result['differences']:
            messages.append('Saved configuration sections differ: ' + ', '.join(result['differences']) + '. These are observed differences, not proof of a causal effect.')
            a, b = (side['run'].config for side in result['sides'])
            for section, identity in (('locations', 'name'), ('lifts', 'id')):
                aa, bb = ({row[identity]: row for row in config.get(section, []) if identity in row} for config in (a,b))
                messages.append(f'{section}: A only {sorted(set(aa)-set(bb))}; B only {sorted(set(bb)-set(aa))}; '
                                f'changed definitions {sorted(k for k in set(aa)&set(bb) if aa[k]!=bb[k])}')
            for section in ('building', 'simulation', 'route_profiles'):
                aa, bb = a.get(section, {}), b.get(section, {})
                for key in sorted(set(aa) | set(bb)):
                    if aa.get(key) != bb.get(key):
                        messages.append(f'{section}.{key}: A = {json.dumps(aa.get(key),ensure_ascii=False)}; '
                                        f'B = {json.dumps(bb.get(key),ensure_ascii=False)}')
            messages.append(f"Configured robots: A {len(a.get('amrs',[]))} definitions; B {len(b.get('amrs',[]))}. "
                            f"Configured tasks: A {len(a.get('tasks',[]))}; B {len(b.get('tasks',[]))}. "
                            'Generated workload is shown in the metric table; full frozen inputs are included in the evidence export.')
        self.context.setPlainText('\n'.join(messages))
        self.route_tree.clear()
        self.group_lookup = {}
        for index, group in enumerate(result['groups']):
            origin, destination, purpose, profile = group['key']
            a, b = group['a'], group['b']
            def values(title, left, right):
                av,bv = (route_group_values(legs,side,result['filters'].end)
                         for legs,side in zip((left,right),result['sides']))
                delta = bv['count']-av['count'] if bv['count'] is not None and av['count'] is not None else None
                return [title,purpose,profile or 'Default',fmt(av['count']),fmt(bv['count']),fmt(delta),
                        fmt(av['distance']),fmt(bv['distance']),fmt(av['duration']),fmt(bv['duration']),fmt(av['wait']),fmt(bv['wait'])]
            item = QTreeWidgetItem(values(f'{origin} → {destination}', a, b))
            item.setData(0, Qt.UserRole, (index, -1))
            self.group_lookup[(index, -1)] = (a,b)
            self.route_tree.addTopLevelItem(item)
            for variant_index, (variant, sides) in enumerate(group['variants'].items()):
                sequence = ' → '.join([variant[0][1]] + [entry[2] for entry in variant])
                lifts = list(dict.fromkeys(entry[3] for entry in variant if entry[3]))
                title = f'Path {variant_index+1} · ' + (', '.join(lifts) if lifts else 'Corridors only')
                child = QTreeWidgetItem(values(title, *sides))
                child.setToolTip(0, sequence)
                child.setData(0, Qt.UserRole, (index, variant_index))
                self.group_lookup[(index, variant_index)] = sides
                item.addChild(child)
        for label, side in zip(('A','B'), result['sides']):
            self.show_trips(label, side['legs'] if side else [])
            self.selected_legs[label] = None
            self.maps[label].set_leg(None, None)
        self.evidence.set_records([], [])
        self.render_lifts()
        checks = [(label, leg) for label, side in zip(('A','B'), result['sides']) if side for leg in side['legs']]
        checks.sort(key=lambda pair: ({VIOLATION:0, UNKNOWN:1, SATISFIED:2, DISABLED:3}.get(pair[1].compliance,4), pair[1].time or 0))
        self.checks.set_records(checks, [[label,leg.compliance,leg.origin,leg.destination,leg.amr,leg.time,leg.evidence,leg.reason] for label,leg in checks])
        summary = []
        for label, side in zip(('A','B'), result['sides']):
            if side:
                summary.append(f"Run {label}: " + ' · '.join(f'{name}: {side["compliance"].get(name,0):,}' for name in (SATISFIED,VIOLATION,UNKNOWN,DISABLED)))
        self.compliance_summary.setText('\n'.join(summary) + '\nA recorded plan satisfying the rule is distinct from a confirmed simulation outcome. Double-click a row to inspect evidence.')
        self.status.setText(f'Comparison ready · {fmt(result["sides"][0]["start"])}–{fmt(result["sides"][0]["end"])} elapsed seconds · '
                            f'{len(result["groups"]):,} route groups. Unknown values are not zero.')
        self.export_button.setEnabled(True)

    def show_trips(self, label, legs):
        self.trips[label].set_records(legs, [[l.time,l.amr,l.origin,l.destination,l.distance,l.wait,l.evidence,l.compliance] for l in legs])

    def select_group(self, item, previous=None):
        if item is None:
            return
        pair = self.group_lookup.get(item.data(0, Qt.UserRole))
        if pair:
            for label, legs in zip(('A','B'), pair):
                self.show_trips(label, legs)

    def select_leg(self, label, leg):
        self.selected_legs[label] = leg
        run = self.result['sides'][0 if label == 'A' else 1]['run']
        self.maps[label].set_leg(run, leg)
        records, values = [], []
        for side, chosen in self.selected_legs.items():
            if chosen:
                for s in chosen.segments:
                    records.append((side, s))
                    values.append([side,s.id,s.kind,s.origin,s.destination,s.time,s.end,s.lift,json.dumps(s.detail,ensure_ascii=False)])
        self.evidence.set_records(records, values)

    def open_leg(self, label, leg):
        self.select_leg(label, leg)
        self.tabs.setCurrentIndex(2)

    def render_lifts(self, *_):
        if self.result is None:
            return
        mode = self.lift_mode.currentIndex()
        sides, records, values = [], [], []
        consistency = []
        for label, side in zip(('A','B'), self.result['sides']):
            movements = [s for s in side['movements'] if mode == 0 or (s.kind == 'lift_transfer') == (mode == 1)] if side else []
            if side:
                checks = side['run'].lift_checks
                consistency.append(f'Run {label} lift consistency: ' + ('reconciled with saved bookings' if checks.get('known') else 'incomplete or conflicting evidence'))
                consistency.append(f"Run {label} bed-lift fallback journeys: {fmt(side['metrics'].get('Bed-lift fallback journeys'))}")
            sides.append(dict(side, movements=movements) if side else None)
            for s in movements:
                records.append((label,s))
                reason = {'fm_wait_limit': 'FM wait above limit', 'no_usable_fm_route': 'No usable FM route'}.get(s.detail.get('bed_fallback_reason'), '')
                values.append([label,s.lift,s.kind,s.start[2],s.finish[2],s.time,s.end,s.amr,s.id,
                    reason, ', '.join(s.detail.get('bed_fallback_lift_ids', [])),
                    (s.detail.get('predicted_fm_wait_sec') if s.detail.get('predicted_fm_wait_sec') is not None else 'Unavailable') if reason else '',
                    (s.detail.get('estimated_time_saved_sec') if s.detail.get('estimated_time_saved_sec') is not None else 'Unavailable') if reason else ''])
        from collections import Counter
        floors = sorted({floor for side in sides if side for s in side['run'].movements
                         for floor in (s.start[2],s.finish[2]) if floor is not None})
        maximum = max([1] + [count for side in sides if side for count in Counter(
            (s.start[2],s.finish[2]) for s in side['movements']).values()])
        for label, side in zip(('A','B'),sides):
            self.heatmaps[label].set_movements(side['movements'] if side else [], floors=floors,
                maximum=maximum, complete=bool(side and side['run'].complete))
        self.lift_table.set_records(records,values)
        self.lift_consistency.setText(' · '.join(consistency))
        self.lift_consistency.setToolTip('\n'.join(f"{label}: {issue['lift_id']} · {issue['reason']}"
            for label, side in zip(('A','B'),sides) if side for issue in side['run'].lift_checks.get('issues',[])))
        self.timeline.set_result(dict(self.result,sides=sides))

    def select_pair(self, origin, destination):
        self.chart_pair = origin, destination
        self.chart_label.setText(f'Lift movements F{fmt(origin)} → F{fmt(destination)}')
        self.refresh_comparison()

    def select_lift(self, lift):
        self.filters['lift'].setCurrentIndex(max(0,self.filters['lift'].findData(lift)))
        self.refresh_comparison()

    def clear_chart(self):
        self.chart_pair = (None,None)
        self.chart_label.clear()
        self.filters['lift'].setCurrentIndex(0)
        self.refresh_comparison()

    def export(self):
        if self.result is None:
            return
        parent = QFileDialog.getExistingDirectory(self, 'Choose export destination outside the source runs')
        if parent:
            target = Path(parent) / ('lift-route-analysis-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            result = self.result
            self.export_button.setEnabled(False)
            self._start('export', lambda cancel, progress: export_comparison(result, target, cancel=cancel))
