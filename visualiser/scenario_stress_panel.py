"""Setup, process progress and evidence-backed results for disruption studies."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import time

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QTabWidget, QWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QFileDialog, QPlainTextEdit, QProgressBar, QScrollArea, QStyle, QStyleOptionViewItem)

from amr_scenario_study import (default_settings, validated_settings, create_study, validate_study,
    input_identity, candidate_count, trial_counts)
from amr_scenario_study import search_settings, EXECUTION_SETTINGS, study_lock, validate_study_document
from amr_scenario_study import (amr_speed_sweep_settings, is_amr_speed_sweep,
                                speed_sweep_summary, speed_sweep_description)
from amr_project_runs import read_json, write_json, finish_run
from amr_run_review import verified_inputs


class _StressAssetTree(QTreeWidget):
    """Keep the row selection when clicking a selected row's checkbox."""

    def mousePressEvent(self, event):
        self._checkbox_selection = []
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier:
            index = self.indexAt(event.position().toPoint())
            item = self.itemFromIndex(index)
            if item is not None and item.isSelected():
                option = QStyleOptionViewItem()
                self.itemDelegate().initStyleOption(option, index)
                option.rect = self.visualRect(index)
                checkbox = self.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, self)
                if checkbox.contains(event.position().toPoint()):
                    self._checkbox_selection = self.selectedItems()
        super().mousePressEvent(event)
        for item in self._checkbox_selection:
            item.setSelected(True)

    def mouseReleaseEvent(self, event):
        selected = getattr(self, '_checkbox_selection', [])
        for item in selected:
            item.setSelected(True)
        super().mouseReleaseEvent(event)
        for item in selected:
            item.setSelected(True)
        self._checkbox_selection = []


class ScenarioStressDialog(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.project_key = (getattr(editor.project, 'project_id', None), editor.current_json_path)
        self.study = None
        self.path = None
        self.process = None
        self._preparing = False
        self._output = ''
        self._line = ''
        self._cancelled = False
        self._started = None
        self._phase = 'Preparing study'
        self._completed_trials = 0
        self._total_trials = 0
        self._eta = None
        self._process_group = None
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(500)
        self.heartbeat.timeout.connect(self.update_elapsed)
        self.setWindowTitle('Automated scenario stress test')
        self.resize(1080, 760)
        self.setModal(False)
        layout = QVBoxLayout(self)
        self.status = QLabel('Choose settings, then select New study and run… to start. '
            'To resume, open a saved study and select Run / resume study. Simple mode only.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.history_shortcut = QPushButton('Previous studies')
        self.history_shortcut.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        layout.addWidget(self.history_shortcut)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        page = QWidget()
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setWidget(page)
        self.tabs.addTab(setup_scroll, 'Setup')
        setup = QVBoxLayout(page)
        self.test_mode = QComboBox()
        self.test_mode.addItem('Disruption combinations', 'combinations')
        self.test_mode.addItem('All-AMR speed sweep (5% steps)', 'amr_speed_sweep')
        setup.addWidget(QLabel('Test type'))
        setup.addWidget(self.test_mode)
        self.speed_help = QLabel('Tests the whole fleet together: 100% normal operation, then 95%, 90%, ... 5% of each '
            'AMR\'s configured travel speed. Runs independent levels within the worker and RAM limits, including after failures. '
            'The speed limit stays active throughout the run, including work after demand ends. '
            'Results show the lowest tested passing speed; lift speeds and handling times retain their configured values.')
        self.speed_help.setWordWrap(True)
        setup.addWidget(self.speed_help)
        self.assets = _StressAssetTree()
        self.assets.setMinimumHeight(180)
        self.assets.setColumnCount(1)
        self.assets.setHeaderLabel('Eligible assets for combined trials')
        self.assets.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.assets.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.assets.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.assets.header().setSectionResizeMode(QHeaderView.Stretch)
        self._asset_items = {}
        self._asset_groups = []
        setup.addWidget(self.assets, 1)
        self.assets_empty = QLabel('No eligible assets in the current project. '
                                  'Load a project or add lifts, corridors or AMRs.')
        self.assets_empty.setWordWrap(True)
        setup.addWidget(self.assets_empty)
        asset_actions = QHBoxLayout()
        self.include_assets_button = QPushButton('Include selected')
        self.exclude_assets_button = QPushButton('Exclude selected')
        self.include_all_assets_button = QPushButton('Include all')
        self.clear_assets_button = QPushButton('Clear all')
        self.include_assets_button.clicked.connect(lambda: self.set_selected_assets_checked(Qt.Checked))
        self.exclude_assets_button.clicked.connect(lambda: self.set_selected_assets_checked(Qt.Unchecked))
        self.include_all_assets_button.clicked.connect(lambda: self._set_asset_check_state(self._asset_groups, Qt.Checked))
        self.clear_assets_button.clicked.connect(lambda: self._set_asset_check_state(self._asset_groups, Qt.Unchecked))
        asset_actions.addWidget(self.include_assets_button)
        asset_actions.addWidget(self.exclude_assets_button)
        asset_actions.addWidget(self.include_all_assets_button)
        asset_actions.addWidget(self.clear_assets_button)
        asset_actions.addStretch(1)
        setup.addLayout(asset_actions)
        asset_help = QLabel('Only checked assets are included. New setups start with no assets checked. '
                            'Use Clear all to reset saved choices. Expand a category to see its assets. Use Ctrl/Shift to select multiple rows, '
                            'then Include / Exclude selected or change a selected checkbox. '
                            'A category checkbox toggles every asset in that category.')
        asset_help.setWordWrap(True)
        self.asset_help = asset_help
        setup.addWidget(asset_help)
        self.trial_plan = QLabel()
        self.trial_plan.setWordWrap(True)
        setup.addWidget(self.trial_plan)
        self.assets.itemChanged.connect(self._asset_check_changed)
        self.assets.itemSelectionChanged.connect(self._update_asset_selection_actions)
        form = QFormLayout()
        self.setup_form = form
        self.corridor_scope = QComboBox()
        self.corridor_scope.addItem('Checked corridors only', 'selected')
        self.corridor_scope.addItem('All project corridors', 'all')
        form.addRow('Individual corridor blockage tests', self.corridor_scope)
        self.data_mode = QComboBox()
        self.data_mode.addItem('Full data (independent trial files)', 'full')
        self.data_mode.addItem('Reduced data (differences from normal operation)', 'reduced')
        self.data_mode.setToolTip('Keeps one full normal-operation baseline. Trial events and report data reuse unchanged baseline data. '
                                 'Keep the baseline with the study for playback, investigation and exports.')
        form.addRow('Saved data', self.data_mode)
        self.durations = QLineEdit()
        self.availability = QLineEdit()
        self.speeds = QLineEdit()
        self.begin = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        self.spacing = QDoubleSpinBox()
        for spin in (self.begin, self.end, self.spacing):
            spin.setRange(0, 10000000)
            spin.setDecimals(3)
            spin.setSuffix(' min')
        self.max_events = QSpinBox()
        self.max_events.setRange(1, 8)
        self.budget = QSpinBox()
        self.budget.setRange(1, 100000)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        self.ram_limit = QDoubleSpinBox()
        self.ram_limit.setRange(.25, 1024)
        self.ram_limit.setSuffix(' GiB')
        self.ram_reserve = QDoubleSpinBox()
        self.ram_reserve.setRange(.25, 1024)
        self.ram_reserve.setSuffix(' GiB')
        self.ram_reserve.setToolTip('Reserve at least this much free system RAM or 20% of physical RAM, capped at half on small machines. Workers stop under memory pressure.')
        for label, widget in [('Durations (minutes, comma separated)', self.durations),
            ('Earliest event start after simulation start', self.begin), ('Latest event end after simulation start', self.end),
            ('Spacing between sampled starts', self.spacing), ('Availability choices (%)', self.availability),
            ('Speed choices (%)', self.speeds), ('Maximum simultaneous events', self.max_events),
            ('Combined trial budget', self.budget), ('Reproducible search seed', self.seed),
            ('Maximum concurrent CPU workers', self.workers), ('Study RAM limit', self.ram_limit),
            ('RAM reserved for other applications', self.ram_reserve)]:
            form.addRow(label, widget)
        setup.addLayout(form)
        self.plan_timer = QTimer(self)
        self.plan_timer.setSingleShot(True)
        self.plan_timer.timeout.connect(self._update_trial_plan)
        note = QLabel('Individual full-period corridor blockages use checked corridors unless All project corridors is selected. '
                      'Baseline and corridor trials are additional to the combined budget. Existing scenarios are retained. '
                      'The combined budget is a cap: unticking assets changes the combinations, but may leave the trial count at that cap. '
                      'Dated events are sampled within the chosen window; durations are clipped at its end. '
                      'All trials use the project-wide Maximum task deferral from Simulation settings → Run period '
                      '(60 minutes by default). Released work and required returns may finish after demand ends.')
        note.setWordWrap(True)
        self.combination_note = note
        setup.addWidget(note)
        row = QHBoxLayout()
        self.new_button = QPushButton('New study and run…')
        self.open_button = QPushButton('Open study…')
        self.save_settings_button = QPushButton('Save settings')
        self.restore_settings_button = QPushButton('Restore study settings')
        self.new_button.clicked.connect(self.new_study)
        self.open_button.clicked.connect(self.open_study)
        self.save_settings_button.clicked.connect(self.save_settings)
        self.restore_settings_button.clicked.connect(self.restore_settings)
        for button in (self.new_button, self.open_button, self.save_settings_button, self.restore_settings_button):
            row.addWidget(button)
        setup.addLayout(row)
        setup.addStretch(1)

        page = QWidget()
        self.tabs.addTab(page, 'Progress')
        progress_layout = QVBoxLayout(page)
        self.progress = QProgressBar()
        self.progress.setFormat('Overall study: %p%')
        self.progress.setValue(0)
        progress_layout.addWidget(self.progress)
        self.trial_progress = QProgressBar()
        self.trial_progress.setRange(0, 100)
        self.trial_progress.setValue(0)
        self.trial_progress.setFormat('Not running')
        progress_layout.addWidget(self.trial_progress)
        self.phase_label = QLabel('A matching completed simulation is reused as the baseline when available. Otherwise it runs with one worker. Disruption trials start after it passes.')
        self.phase_label.setWordWrap(True)
        progress_layout.addWidget(self.phase_label)
        self.elapsed_label = QLabel('Not started.')
        self.resource_label = QLabel('Default: up to 8 CPU workers, subject to available RAM.')
        self.resource_label.setWordWrap(True)
        progress_layout.addWidget(self.elapsed_label)
        progress_layout.addWidget(self.resource_label)
        self.active_trials = QTableWidget(0, 6)
        self.active_trials.setHorizontalHeaderLabels(['Active trial', 'Phase', 'Simulation time (s)', 'Completed / failed / pending', 'Elapsed (s)', 'RAM (MiB)'])
        self.active_trials.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.active_trials.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        progress_layout.addWidget(self.active_trials, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        progress_layout.addWidget(self.log, 1)

        page = QWidget()
        self.tabs.addTab(page, 'Results')
        results = QVBoxLayout(page)
        self.summary = QLabel('No study loaded.')
        self.summary.setWordWrap(True)
        results.addWidget(self.summary)
        self.results = QTableWidget(0, 7)
        self.results.setHorizontalHeaderLabels(['Trial', 'Outcome', 'Unmet', 'Failed / pending', 'Finished after demand end', 'Added delay (s)', 'Latest finish (s)'])
        self.results.horizontalHeaderItem(4).setToolTip('Informational: released tasks and returns may finish after demand ends. This does not fail a trial.')
        self.results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.results.currentCellChanged.connect(self.trial_selected)
        results.addWidget(self.results, 1)
        self.corridors = QTableWidget(0, 4)
        self.corridors.setHorizontalHeaderLabels(['Critical corridor (ranked)', 'Unmet obligations', 'Added delay (s)', 'Outcome'])
        self.corridors.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.corridors.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.corridors.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.corridors.currentCellChanged.connect(self.corridor_selected)
        results.addWidget(self.corridors, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(140)
        results.addWidget(self.details)
        row = QHBoxLayout()
        self.investigate_button = QPushButton('Investigate trial')
        self.playback_button = QPushButton('Play trial')
        self.save_scenario_button = QPushButton('Save as scenario')
        self.report_button = QPushButton('Report stress tests…')
        self.report_button.clicked.connect(self.report_stress_tests)
        self.investigate_button.clicked.connect(self.investigate)
        self.playback_button.clicked.connect(self.playback)
        self.save_scenario_button.clicked.connect(self.save_scenario)
        for button in (self.investigate_button, self.playback_button, self.save_scenario_button, self.report_button):
            row.addWidget(button)
        results.addLayout(row)

        history_page = QWidget()
        self.tabs.addTab(history_page, 'Previous studies')
        history_layout = QVBoxLayout(history_page)
        history_note = QLabel('Saved studies and previous versions are listed below. Older studies remain available for review; '
                             'changed inputs or software require a new study to run again.')
        history_note.setWordWrap(True)
        history_layout.addWidget(history_note)
        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(['Study', 'Status', 'Saved trials', 'Data', 'Updated', 'Location'])
        self.history.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history.cellDoubleClicked.connect(lambda _row, _col: self.open_previous_study())
        history_layout.addWidget(self.history, 1)
        history_actions = QHBoxLayout()
        self.open_history_button = QPushButton('Open selected study')
        self.refresh_history_button = QPushButton('Refresh history')
        self.open_history_button.clicked.connect(self.open_previous_study)
        self.refresh_history_button.clicked.connect(self.refresh_history)
        history_actions.addWidget(self.open_history_button)
        history_actions.addWidget(self.refresh_history_button)
        history_layout.addLayout(history_actions)

        row = QHBoxLayout()
        self.start_button = QPushButton('Run / resume study')
        self.stop_button = QPushButton('Stop study')
        self.close_button = QPushButton('Close')
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.cancel)
        self.close_button.clicked.connect(self.close)
        for button in (self.start_button, self.stop_button, self.close_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.set_settings(editor.store.scenario_testing().get('stress_test', {}))
        for widget in (self.durations, self.availability, self.speeds):
            widget.textChanged.connect(lambda _text: self.plan_timer.start(0))
        for widget in (self.begin, self.end, self.spacing, self.max_events, self.budget):
            widget.valueChanged.connect(lambda _value: self.plan_timer.start(0))
        self.corridor_scope.currentIndexChanged.connect(lambda _index: self.plan_timer.start(0))
        self.test_mode.currentIndexChanged.connect(self._test_mode_changed)
        self.refresh()
        self.refresh_history()
        # Polish before the first show. Show-time polishing reparents the setup
        # into a scroll area and can leave the tree's first layout incomplete.
        from ui_theme import polish_dialog
        polish_dialog(self)

    def running(self):
        return self.process is not None or self._preparing

    def set_settings(self, settings):
        settings = {**default_settings(self.editor.store.data), 'assets': [], **settings}
        blocked = self.test_mode.blockSignals(True)
        self.test_mode.setCurrentIndex(self.test_mode.findData(settings.get('test_mode', 'combinations')))
        self.test_mode.blockSignals(blocked)
        # Spin boxes and compact numeric text round values for display. Preserve
        # loaded precision unless the user edits the control, especially when
        # reopening a study whose period is not a whole number of minutes.
        self._loaded_settings = deepcopy(settings)
        self._displayed_settings = {}
        self._populate_assets(default_settings(self.editor.store.data)['assets'], settings['assets'])
        for widget, key in [(self.durations, 'durations_minutes'), (self.availability, 'availability_percent'), (self.speeds, 'speed_percent')]:
            widget.setText(', '.join(f'{v:g}' for v in settings[key]))
            self._displayed_settings[key] = widget.text()
        for widget, key in [(self.begin, 'start_minute'), (self.end, 'end_minute'), (self.spacing, 'start_step_minutes'),
            (self.max_events, 'max_events'), (self.budget, 'trial_budget'), (self.seed, 'seed'),
            (self.workers, 'workers'), (self.ram_limit, 'ram_limit_gib'), (self.ram_reserve, 'reserve_ram_gib')]:
            widget.setValue(max(widget.minimum(), min(widget.maximum(), settings[key])))
            self._displayed_settings[key] = widget.value()
        self.corridor_scope.setCurrentIndex(self.corridor_scope.findData(settings['corridor_sweep_scope']))
        self.data_mode.setCurrentIndex(self.data_mode.findData(settings['data_mode']))
        self._update_mode_controls()
        self._update_trial_plan()

    def _test_mode_changed(self, *_):
        if self.test_mode.currentData() == 'amr_speed_sweep':
            self.set_settings(amr_speed_sweep_settings(self.editor.store.data,
                dict(data_mode='reduced', ram_limit_gib=self.ram_limit.value(), reserve_ram_gib=self.ram_reserve.value())))
        self._update_mode_controls()
        self._update_trial_plan()

    def _update_mode_controls(self):
        sweep = self.test_mode.currentData() == 'amr_speed_sweep'
        self.speed_help.setVisible(sweep)
        for widget in (self.assets, self.asset_help, self.combination_note, self.include_assets_button,
                       self.exclude_assets_button, self.include_all_assets_button, self.clear_assets_button):
            widget.setVisible(not sweep)
        self.assets_empty.setVisible(not sweep and not self._assets)
        for widget in (self.assets, self.corridor_scope, self.durations, self.availability, self.speeds,
                       self.begin, self.end, self.spacing, self.max_events, self.budget, self.seed):
            widget.setEnabled(not self.running() and not sweep)
            if widget is not self.assets:
                self.setup_form.setRowVisible(widget, not sweep)
        self.workers.setEnabled(not self.running())
        self.setup_form.setRowVisible(self.workers, True)
        self._update_asset_selection_actions()

    def _populate_assets(self, assets, selected, *, expanded=None, selected_rows=()):
        self._assets = assets
        selected = {tuple(asset) for asset in selected}
        expanded = expanded or {}
        blocked = self.assets.blockSignals(True)
        try:
            self.assets._checkbox_selection = []
            self.assets.clear()
            self._asset_items = {}
            self._asset_groups = []
            for kind, category in (('lift', 'Lifts'), ('corridor', 'Corridors'),
                                   ('amr', 'AMRs'), ('corridor_node', 'Doors')):
                members = [asset for asset in self._assets if asset[0] == kind]
                if not members:
                    continue
                group = QTreeWidgetItem([f'{category} ({len(members)})'])
                group.setData(0, Qt.UserRole, kind)
                group.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                font = group.font(0)
                font.setBold(True)
                group.setFont(0, font)
                self.assets.addTopLevelItem(group)
                group.setSelected(kind in selected_rows)
                self._asset_groups.append(group)
                for asset in members:
                    item = QTreeWidgetItem([asset[1]])
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    item.setData(0, Qt.UserRole, tuple(asset))
                    item.setCheckState(0, Qt.Checked if tuple(asset) in selected else Qt.Unchecked)
                    group.addChild(item)
                    item.setSelected(tuple(asset) in selected_rows)
                    self._asset_items[tuple(asset)] = item
                # Large categories stay compact so the other resource types
                # remain visible when opening a real project such as LTN.
                group.setExpanded(expanded.get(kind, len(members) <= 3))
            self._update_asset_groups()
        finally:
            self.assets.blockSignals(blocked)
        self.assets_empty.setVisible(not assets)
        self.assets.doItemsLayout()
        self._update_asset_selection_actions()

    def _sync_asset_catalog(self):
        if self.running():
            return
        assets = default_settings(self.editor.store.data)['assets']
        if assets == self._assets and (not assets or self.assets.topLevelItemCount()):
            self.assets.doItemsLayout()
            return
        from shiboken6 import isValid
        loaded = {tuple(asset) for asset in self._loaded_settings['assets']}
        checked = {asset: item.checkState(0) == Qt.Checked
                   for asset, item in self._asset_items.items() if isValid(item)}
        selected = [asset for asset in assets if checked.get(tuple(asset), tuple(asset) in loaded)]
        expanded = {group.data(0, Qt.UserRole): group.isExpanded()
                    for group in self._asset_groups if isValid(group)}
        selected_rows = {key for key, item in self._asset_items.items()
                         if isValid(item) and item.isSelected()}
        selected_rows.update(group.data(0, Qt.UserRole) for group in self._asset_groups
                             if isValid(group) and group.isSelected())
        self._populate_assets(assets, selected, expanded=expanded, selected_rows=selected_rows)

    def showEvent(self, event):
        self._sync_asset_catalog()
        self.refresh_history()
        super().showEvent(event)
        QTimer.singleShot(0, self._finish_first_layout)

    def _finish_first_layout(self):
        from shiboken6 import isValid
        if not isValid(self):
            return
        self._sync_asset_catalog()
        self.assets.doItemsLayout()
        self.assets.viewport().update()

    def _update_trial_plan(self):
        try:
            settings = self.settings()
            counts = trial_counts(self.editor.store.data, settings)
            if is_amr_speed_sweep(settings):
                self.trial_plan.setText(f"Planned trials: 1 normal-operation baseline (100%) + 19 speed levels = 20 total. "
                    f"All {len(settings['assets'])} AMR configurations are included, with every quantity instance. "
                    '95%, 90%, ... 5%; independent full-fleet trials; no lift or corridor disruptions.')
                return
            self.trial_plan.setText(f"Planned trials: 1 baseline + {counts['corridors']} individual corridor tests "
                f"+ up to {counts['combined']} combined trials = up to {counts['total']} total. "
                f"{len(settings['assets'])} assets checked for combinations.")
        except (ValueError, KeyError, RuntimeError) as exc:
            self.trial_plan.setText(f'Trial plan: {exc}')

    def settings(self):
        if self.test_mode.currentData() == 'amr_speed_sweep':
            return validated_settings(self.editor.store.data, amr_speed_sweep_settings(self.editor.store.data,
                dict(data_mode=self.data_mode.currentData(), ram_limit_gib=self.ram_limit.value(),
                     reserve_ram_gib=self.ram_reserve.value())))
        def numbers(widget, key):
            if widget.text() == self._displayed_settings[key]:
                return deepcopy(self._loaded_settings[key])
            return [float(v.strip()) for v in widget.text().split(',') if v.strip()]
        def value(widget, key):
            return self._loaded_settings[key] if widget.value() == self._displayed_settings[key] else widget.value()
        return validated_settings(self.editor.store.data, dict(assets=[asset for asset in self._assets
            if self._asset_items[tuple(asset)].checkState(0) == Qt.Checked], durations_minutes=numbers(self.durations, 'durations_minutes'),
            availability_percent=numbers(self.availability, 'availability_percent'), speed_percent=numbers(self.speeds, 'speed_percent'),
            start_minute=value(self.begin, 'start_minute'), end_minute=value(self.end, 'end_minute'), start_step_minutes=value(self.spacing, 'start_step_minutes'),
            max_events=value(self.max_events, 'max_events'), trial_budget=value(self.budget, 'trial_budget'), seed=value(self.seed, 'seed'),
            workers=value(self.workers, 'workers'), ram_limit_gib=value(self.ram_limit, 'ram_limit_gib'), reserve_ram_gib=value(self.ram_reserve, 'reserve_ram_gib'),
            corridor_sweep_scope=self.corridor_scope.currentData(), data_mode=self.data_mode.currentData()))

    def _asset_leaves(self, items):
        leaves = {}
        for item in items:
            children = [item.child(i) for i in range(item.childCount())] if item.parent() is None else [item]
            for child in children:
                leaves[id(child)] = child
        return list(leaves.values())

    def _update_asset_groups(self):
        # Update parent summaries explicitly. Automatic tristate propagation
        # would make a child's summary change look like another user bulk action.
        for group in self._asset_groups:
            checked = sum(group.child(i).checkState(0) == Qt.Checked for i in range(group.childCount()))
            state = Qt.Checked if checked == group.childCount() else Qt.PartiallyChecked if checked else Qt.Unchecked
            group.setCheckState(0, state)
            group.setToolTip(0, f'{checked} of {group.childCount()} assets included')
        included = sum(item.checkState(0) == Qt.Checked for item in self._asset_items.values())
        self.assets.setHeaderLabel(f'Included assets: {included} / {len(self._asset_items)} (checked boxes)')

    def _set_asset_check_state(self, items, state):
        if self.running():
            return
        blocked = self.assets.blockSignals(True)
        try:
            for item in self._asset_leaves(items):
                item.setCheckState(0, state)
            self._update_asset_groups()
        finally:
            self.assets.blockSignals(blocked)
        self._update_asset_selection_actions()

    def _asset_check_changed(self, item, column):
        if column != 0 or item.checkState(0) == Qt.PartiallyChecked:
            return
        items = self.assets.selectedItems() if item.isSelected() else [item]
        self._set_asset_check_state(items, item.checkState(0))

    def set_selected_assets_checked(self, state):
        self._set_asset_check_state(self.assets.selectedItems(), state)

    def _update_asset_selection_actions(self):
        selected = self._asset_leaves(self.assets.selectedItems())
        editable = not self.running() and self.test_mode.currentData() != 'amr_speed_sweep'
        self.include_all_assets_button.setEnabled(editable and any(item.checkState(0) != Qt.Checked for item in self._asset_items.values()))
        self.clear_assets_button.setEnabled(editable and any(item.checkState(0) == Qt.Checked for item in self._asset_items.values()))
        self.include_assets_button.setEnabled(editable and any(item.checkState(0) != Qt.Checked for item in selected))
        self.exclude_assets_button.setEnabled(editable and any(item.checkState(0) == Qt.Checked for item in selected))
        if hasattr(self, 'plan_timer'):
            self.plan_timer.start(0)

    def save_settings(self):
        try:
            self.editor.save_stress_settings(self.settings(), str(self.path) if self.path else None)
            self.status.setText('Stress-test settings updated. Save the project to keep them after closing.')
        except Exception as exc:
            self.status.setText(str(exc))

    def restore_settings(self):
        if self.running() or not self.study:
            return
        self.set_settings({**self.study['settings'],
                           'corridor_sweep_scope': self.study['settings'].get('corridor_sweep_scope', 'all')})
        self.status.setText('Restored the saved study settings. Run / resume continues this study.')

    def startup_error(self, message):
        self.heartbeat.stop()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.trial_progress.setRange(0, 100)
        self.trial_progress.setValue(0)
        self.trial_progress.setFormat('Not running')
        self.active_trials.setRowCount(0)
        self.status.setText(message)
        self.phase_label.setText('Study did not start: ' + message)
        self.resource_label.setText('No background workers are running.')
        self.log.appendPlainText('Study did not start: ' + message)

    def new_study(self):
        if self.running() or not self.editor._project_editing_allowed():
            return
        created = False
        try:
            settings = self.settings()
            candidate_count(settings)
            self._preparing = True
            self.refresh()
            self.editor.sync_project_editing_lock()
            default = str(Path(self.editor.current_json_path).with_suffix('.stress.json')) if self.editor.current_json_path else 'scenario-stress.json'
            name, _ = QFileDialog.getSaveFileName(self, 'Create stress study', default, 'Stress study (*.stress.json)')
            if not name:
                return
            new_path = Path(name).resolve()
            if not new_path.suffix:
                new_path = new_path.with_suffix('.stress.json')
            self.status.setText('Freezing design inputs and copying study drawings…')
            self.tabs.setCurrentIndex(1)
            self.progress.setRange(0, 0)
            QApplication.processEvents()
            # QFileDialog has already confirmed replacement of this filename.
            new_state = create_study(self.editor.store.data, new_path, settings,
                                     project=self.editor.project, overwrite=new_path.exists())
            self.path, self.study = new_path, new_state
            created = True
            if new_state.get('previous_study'):
                self.log.appendPlainText('Previous study retained at: ' + new_state['previous_study'])
        except Exception as exc:
            self.startup_error(str(exc))
        finally:
            self._preparing = False
            self.editor.sync_project_editing_lock()
            self.refresh()
        if created:
            self.editor.save_stress_settings(settings, str(self.path))
            self.remember_current_study()
            self.refresh_history()
            self.start()

    def open_study(self):
        if self.running():
            return
        name, _ = QFileDialog.getOpenFileName(self, 'Open stress study', '', 'Stress study (*.stress.json);;JSON (*.json)')
        if not name:
            return
        self.load_study(name)

    def history_source(self):
        project = self.editor.project
        return getattr(project, 'path', None) or self.editor.current_json_path

    def remember_current_study(self):
        source = self.history_source()
        if source and self.path:
            from amr_stress_history import remember_study
            try:
                remember_study(source, self.path)
            except (OSError, ValueError) as exc:
                self.log.appendPlainText('Could not update study history: ' + str(exc))

    def refresh_history(self):
        from amr_stress_history import discover_studies
        project = self.editor.project
        root = project.results_root() if project is not None and project.path else None
        saved = self.editor.store.scenario_testing().get('stress_test', {}).get('study_path')
        self._history_rows = discover_studies(self.history_source(), project_id=getattr(project, 'project_id', None),
                                             known=(self.path, saved), results_root=root)
        self.history.setRowCount(len(self._history_rows))
        for row, item in enumerate(self._history_rows):
            for column, value in enumerate((item['path'].name, item['status'], item['trials'], item['mode'],
                                            item['updated'], str(item['path']))):
                self.history.setItem(row, column, QTableWidgetItem(str(value)))
        if self._history_rows:
            self.history.setCurrentCell(0, 0)
        self.history_shortcut.setText(f'Previous studies ({len(self._history_rows)})')
        self.open_history_button.setEnabled(bool(self._history_rows) and not self.running())

    def open_previous_study(self):
        row = self.history.currentRow()
        if not self.running() and 0 <= row < len(self._history_rows):
            self.load_study(self._history_rows[row]['path'])

    def load_study(self, name):
        if self.running():
            return
        try:
            state = read_json(name)
            validate_study_document(state)
            self.path = Path(name).resolve()
            self.study = state
            self.remember_current_study()
            self.refresh_history()
            self.set_settings({**state['settings'],
                               'corridor_sweep_scope': state['settings'].get('corridor_sweep_scope', 'all')})
            self.refresh()
            self.tabs.setCurrentIndex(2)
            self.status.setText(('Study inputs or software changed. Review its results or create a new study.'
                                if self.stale() else f"Opened {self.path.name}. " +
                                ('Study complete; review its results.' if state['status'] == 'complete'
                                 else (state.get('error', '') + ' ' if state['status'] == 'failed' else '')
                                 + 'Select Run / resume study to continue.')))
        except Exception as exc:
            self.status.setText(str(exc))

    def stale(self):
        if not self.study:
            return False
        try:
            from amr_run_evidence import software_snapshot
            return (input_identity(self.editor.store.data) != self.study['source_identity']
                    or software_snapshot()['sha256'] != self.study['software_sha256'])
        except Exception:
            return True

    def start(self):
        if self.running() or not self.study or not self.editor._project_editing_allowed():
            return
        try:
            self._preparing = True
            self.refresh()
            self.editor.sync_project_editing_lock()
            self._started = time.monotonic()
            self._completed_trials = len(self.study.get('results', {}))
            self._total_trials = self.study.get('expected_trials', 0)
            self._eta = None
            self._phase = 'Checking startup inputs'
            self.status.setText(self._phase)
            self.phase_label.setText('Starting background coordinator. It will look for a matching completed simulation and check the baseline before launching disruption trials.')
            self.trial_progress.setRange(0, 0)
            self.tabs.setCurrentIndex(1)
            self.progress.setRange(0, 0)
            self.update_elapsed()
            QApplication.processEvents()
            # UI setup changes never silently replace the frozen study grid.
            with study_lock(self.path):
                state = read_json(self.path)
                validate_study_document(state)
                if state['root'] != self.study['root']:
                    raise ValueError('This study file was replaced. Open it again before running it.')
                self.study = state
                requested = self.settings()
                frozen_search = search_settings(self.study['settings'])
                frozen_search.setdefault('corridor_sweep_scope', 'all')
                frozen_search.setdefault('data_mode', 'full')
                if search_settings(requested) != frozen_search:
                    raise ValueError('Setup differs from the frozen study. Restore its settings or create a new study.')
                # Full evidence validation runs in the coordinator, not on the GUI thread.
                if self.stale():
                    raise ValueError('Study inputs or software changed; create a new study.')
                for key in EXECUTION_SETTINGS:
                    self.study['settings'][key] = requested[key]
                project = self.editor.project
                if ('baseline' not in self.study['results'] and not self.study.get('source_project')
                        and project is not None and project.path is not None):
                    self.study.update(source_project=str(project.path.resolve()), source_project_id=project.project_id)
                self.path.with_suffix(self.path.suffix + '.cancel').unlink(missing_ok=True)
                write_json(self.path, self.study)
            if self.study['status'] == 'complete':
                self.progress.setRange(0, 100)
                self.progress.setValue(100)
                self.status.setText('Study complete. Review results or create a new study with different bounds.')
                self.trial_progress.setRange(0, 100)
                self.trial_progress.setValue(100)
                self.trial_progress.setFormat('Study complete')
                self.phase_label.setText('Study complete. No background workers are running.')
                self.tabs.setCurrentIndex(2)
                return
            self._cancelled = False
            self._output = self._line = ''
            self.process = QProcess(self)
            from amr_stress_resources import ProcessGroup, GIB, memory_status
            self._process_group = ProcessGroup(min(self.study['settings']['ram_limit_gib'] * GIB,
                                                  memory_status()['total'] * .5))
            self.process.started.connect(self.contain_coordinator)
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            environment = QProcessEnvironment.systemEnvironment()
            environment.insert('PYTHONIOENCODING', 'utf-8')
            environment.insert('PYTHONUNBUFFERED', '1')
            self.process.setProcessEnvironment(environment)
            self.process.readyReadStandardOutput.connect(self.read_progress)
            self.process.finished.connect(self.worker_finished)
            self.process.errorOccurred.connect(self.worker_error)
            self.editor.sync_project_editing_lock()
            self.heartbeat.start()
            self.resource_label.setText('Launching coordinator; CPU and RAM readings will appear when it connects.')
            if getattr(sys, 'frozen', False):
                self.process.start(str(Path(sys.executable).with_name('AMRSimulatorWorker.exe')), ['--scenario-study', str(self.path.resolve())])
            else:
                environment.insert('PYTHONPATH', os.pathsep.join(value for value in sys.path if value))
                self.process.setProcessEnvironment(environment)
                self.process.start(getattr(sys, '_base_executable', sys.executable),
                    ['-u', str(Path(__file__).resolve().parents[1] / 'amr_scenario_study.py'), str(self.path.resolve())])
            self.tabs.setCurrentIndex(1)
            self.status.setText('Starting background stress-test coordinator…')
            self.refresh()
        except Exception as exc:
            if self.process is not None:
                self.process.kill()
                self.process.deleteLater()
                self.process = None
            if self._process_group:
                self._process_group.close()
                self._process_group = None
            self.editor.sync_project_editing_lock()
            self.startup_error(str(exc))
        finally:
            self._preparing = False
            self.editor.sync_project_editing_lock()
            self.refresh()

    def contain_coordinator(self):
        try:
            self._process_group.assign(int(self.process.processId()))
        except Exception as exc:
            self._output = 'Cannot enforce study RAM and process containment: ' + str(exc)
            self.process.kill()

    def update_elapsed(self):
        if self._started is not None:
            elapsed = time.monotonic() - self._started
            text = f'Elapsed: {int(elapsed)} s · {self._completed_trials} / {self._total_trials or "—"} trials completed'
            if self._eta is not None and self.running():
                text += f' · Estimated remaining: {int(self._eta)} s (updates as trials finish)'
            self.elapsed_label.setText(text)

    def read_progress(self):
        if self.process is None:
            return
        text = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._output = (self._output + text)[-8000:]
        self._line += text
        lines = self._line.split('\n')
        self._line = lines.pop()
        for line in lines:
            if line.startswith('STRESS '):
                try:
                    self.accept_progress(json.loads(line[7:]))
                except (ValueError, KeyError, TypeError) as exc:
                    self.log.appendPlainText('Progress message could not be read: ' + str(exc))
                continue
            self.log.appendPlainText(line)
            match = re.match(r'^(\d+)/(\d+):\s*(.+)', line)
            if match:
                self.progress.setValue(int(100 * (int(match[1]) - 1) / max(1, int(match[2]))))
                self.status.setText('Evaluating ' + match[3])

    def accept_progress(self, message):
        phase = message.get('phase', self._phase)
        if phase != self._phase:
            self._phase = phase
            self.log.appendPlainText(phase)
        self.status.setText(phase)
        if message.get('type') in ('progress', 'complete'):
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(message.get('fraction', 0) * 100)))
            self._completed_trials = message.get('completed_trials', self._completed_trials)
            self._total_trials = message.get('total_trials', self._total_trials)
            self._eta = message.get('eta_sec')
        if 'workers' in message:
            workers = message['workers']
            baseline = next((worker for worker in workers if worker['id'] == 'baseline'), None)
            if baseline:
                detail = baseline['phase']
                self.status.setText('Normal-operation baseline: ' + detail)
                self.phase_label.setText('One worker is checking normal operation and measuring RAM needs. '
                    'Disruption trials will use up to ' + str(message['requested_workers']) + ' workers after the baseline passes.')
            elif workers:
                self.phase_label.setText(f'{len(workers)} trials are running. New demand stops at the configured end; released work and returns finish under the same assignment deferral limit as normal operation.')
            else:
                self.phase_label.setText('No trial is running. Waiting for enough free RAM to preserve the configured reserve.')
            # A large study can stay below 1% overall throughout the baseline.
            # Show the active simulation separately, without changing search weights.
            simulated = [worker for worker in workers if 'sim_time_sec' in worker]
            if simulated:
                self.trial_progress.setRange(0, 1000)
                fractions = [min(1, worker['sim_time_sec'] / max(1, worker.get('horizon_sec', (self.study or {}).get('horizon_sec', 1))))
                             for worker in simulated]
                fraction = sum(fractions) / len(fractions)
                self.trial_progress.setValue(round(fraction * 1000))
                label = 'Baseline simulation' if baseline else 'Active simulations (average)'
                self.trial_progress.setFormat(f'{label}: {fraction:.1%} of configured period')
                if baseline:
                    self.phase_label.setText(self.phase_label.text() +
                        f" Completed: {baseline.get('completed', 0)}; failed: {baseline.get('failed', 0)}; pending: {baseline.get('pending', 0)}.")
            else:
                self.trial_progress.setRange(0, 0)
            self.resource_label.setText(f"{len(workers)} / {message['requested_workers']} CPU workers active · "
                f"Study RAM: {message['ram_bytes']/1024**3:.2f} / {message['ram_limit_bytes']/1024**3:.2f} GiB · "
                f"Free system RAM: {message['available_ram_bytes']/1024**3:.2f} GiB · Reserve: {message['reserve_ram_bytes']/1024**3:.2f} GiB")
            self.active_trials.setRowCount(len(workers))
            for row, worker in enumerate(workers):
                values = [worker['name'], worker['phase'], f"{worker.get('sim_time_sec', 0):.1f}",
                    f"{worker.get('completed', 0)} / {worker.get('failed', 0)} / {worker.get('pending', 0)}",
                    f"{worker['elapsed_sec']:.1f}", f"{worker['memory_bytes']/1024**2:.1f}"]
                for col, value in enumerate(values):
                    self.active_trials.setItem(row, col, QTableWidgetItem(str(value)))
        self.update_elapsed()
        if self._cancelled:
            self.status.setText('Stopping study…')

    def worker_error(self, error):
        if error == QProcess.FailedToStart and self.process is not None:
            self._output = self.process.errorString()
            self.worker_finished(-1, QProcess.NormalExit)

    def worker_finished(self, code, exit_status=QProcess.NormalExit):
        if self.process is None:
            return
        self.read_progress()
        worker = self.process
        self.process = None
        worker.deleteLater()
        if self._process_group:
            self._process_group.close()
            self._process_group = None
        self.heartbeat.stop()
        self.progress.setRange(0, 100)
        self.active_trials.setRowCount(0)
        self.trial_progress.setRange(0, 100)
        self.trial_progress.setValue(0)
        self.trial_progress.setFormat('No active trials')
        try:
            with study_lock(self.path):
                self._finish_study(code, exit_status)
        except Exception as exc:
            self.startup_error(str(exc))
        self.editor.sync_project_editing_lock()
        self.refresh()

    def _finish_study(self, code, exit_status):
        try:
            state = read_json(self.path)
            if state['root'] != self.study['root']:
                raise ValueError('This study file was replaced. Open it again to review its results.')
            self.study = state
            active = self.study.pop('active_run', None)
            if active and read_json(Path(active) / 'run_manifest.json')['status'] in ('prepared', 'running'):
                finish_run(active, -1, cancelled=self._cancelled, error='' if self._cancelled else self._output)
            for directory in self.study.pop('active_runs', {}).values():
                if read_json(Path(directory) / 'run_manifest.json')['status'] in ('prepared', 'running'):
                    finish_run(directory, -1, cancelled=self._cancelled, error='' if self._cancelled else self._output)
            if self._cancelled or self.study['status'] == 'cancelled':
                self.study['status'] = 'cancelled'
                self.status.setText('Study stopped. Completed evidence is retained; Run / resume continues remaining trials.')
                self.phase_label.setText('Stopped. Completed trials are retained and all background workers have been stopped.')
            elif code != 0 or exit_status != QProcess.NormalExit or self.study['status'] != 'complete':
                self.study.update(status='failed', error=self.study.get('error') or self._output.strip() or f'Worker exited with code {code}.')
                self.status.setText(self.study['error'])
                self.phase_label.setText(self.study['error'])
                self.log.appendPlainText(self.study['error'])
                baseline = self.study.get('results', {}).get('baseline')
                if baseline and not baseline['metrics']['passed']:
                    self.tabs.setCurrentIndex(2)
            else:
                self.status.setText('Study complete. Review the worst passing scenario found and critical corridors.')
                self.progress.setValue(100)
                self.tabs.setCurrentIndex(2)
                self.phase_label.setText('Study complete. All background workers have stopped.')
            self.resource_label.setText('No background workers are running. Completed trial evidence is retained.')
            self.trial_progress.setRange(0, 1000)
            self.trial_progress.setFormat('Active trials finished' if self.study['status'] == 'complete' else 'No active trials')
            self.trial_progress.setValue(1000 if self.study['status'] == 'complete' else 0)
            write_json(self.path, self.study)
        except Exception as exc:
            self.status.setText(str(exc))

    def cancel(self):
        if not self.process:
            return
        self._cancelled = True
        try:
            write_json(self.path.with_suffix(self.path.suffix + '.cancel'), {'cancel': True})
        except OSError as exc:
            self.log.appendPlainText(f'Could not save the stop request ({exc}). Workers will be stopped within five seconds.')
        self.status.setText('Stopping study…')
        worker = self.process
        # Give the worker a chance to finish the current trial; bound cancellation latency.
        def force_stop():
            if self.process is worker:
                if self._process_group:
                    self._process_group.close()
                    self._process_group = None
                worker.kill()
        QTimer.singleShot(5000, force_stop)

    def refresh(self):
        busy = self.running()
        if not busy:
            self._sync_asset_catalog()
        for widget in (self.test_mode, self.assets, self.corridor_scope, self.data_mode, self.durations, self.availability, self.speeds, self.begin, self.end,
                       self.spacing, self.max_events, self.budget, self.seed, self.new_button,
                       self.workers, self.ram_limit, self.ram_reserve,
                       self.open_button, self.save_settings_button, self.close_button, self.open_history_button,
                       self.refresh_history_button):
            widget.setEnabled(not busy)
        self._update_asset_selection_actions()
        self._update_mode_controls()
        self.restore_settings_button.setEnabled(bool(self.study) and not busy)
        self.start_button.setEnabled(bool(self.study) and not busy and not self.stale())
        self.report_button.setEnabled(not busy and bool(self.study and self.study['results'].get('baseline')))
        self.stop_button.setEnabled(self.process is not None)
        if busy:
            for button in (self.investigate_button, self.playback_button, self.save_scenario_button):
                button.setEnabled(False)
            return
        self.results.blockSignals(True)
        self.corridors.blockSignals(True)
        self.results.setRowCount(0)
        self.corridors.setRowCount(0)
        self._trial_rows = []
        self._corridor_rows = []
        if self.study:
            state = self.study
            coverage = state['coverage']
            worst = state['results'].get(state.get('worst_passing'), {})
            self.summary.setText(f"{state['status']}: {coverage['tested_candidates']} / {coverage['candidate_count']} grid candidates tested; "
                f"{coverage['combined_trials']} combined trials; {coverage['corridor_trials']} individual corridors. "
                + ('Exhaustive grid coverage. ' if coverage['exhaustive'] else 'Bounded search; global worst case is not proven. ')
                + ('Worst passing scenario found: ' + worst['name'] if worst else 'No passing disruption found.')
                + (' Inputs changed; create a new study to run or save scenarios.' if self.stale() else ''))
            ranked = state.get('ranking', [])
            remaining = sorted(set(state['results']) - set(ranked))
            if is_amr_speed_sweep(state['settings']):
                self.summary.setText(state['status'] + ': ' + speed_sweep_description(speed_sweep_summary(
                    [r for r in state['results'].values() if r['kind'] != 'baseline'], state['results'].get('baseline')))
                    + (' Inputs changed; create a new study to run or save scenarios.' if self.stale() else ''))
                ranked = sorted(state['results'], key=lambda key: -(state['results'][key]['events'][0]['speed_factor']
                    if state['results'][key]['events'] else 1))
                remaining = []
            for identity in ranked + remaining:
                record = state['results'][identity]
                m = record['metrics']
                self._trial_rows.append(identity)
                row = self.results.rowCount()
                self.results.insertRow(row)
                for col, value in enumerate([record['name'], 'Pass' if m['passed'] else 'Does not pass', m['unmet_count'],
                    f"{m['failed']} / {m['pending']}", m['late'], f"{m['added_delay_sec']:.3f}", f"{m['latest_completion_sec']:.3f}"]):
                    self.results.setItem(row, col, QTableWidgetItem(str(value)))
            for identity in state.get('corridor_ranking', []):
                record = state['results'][identity]
                m = record['metrics']
                self._corridor_rows.append(identity)
                row = self.corridors.rowCount()
                self.corridors.insertRow(row)
                for col, value in enumerate([record['corridor'], m['unmet_count'], f"{m['added_delay_sec']:.3f}", 'Pass' if m['passed'] else 'Does not pass']):
                    self.corridors.setItem(row, col, QTableWidgetItem(str(value)))
            if self._trial_rows:
                self.results.setCurrentCell(0, 0)
        self.results.blockSignals(False)
        self.corridors.blockSignals(False)
        self.trial_selected()
        self.refresh_history()

    def selected_trial(self):
        n = self.results.currentRow()
        if not self.study or not 0 <= n < len(self._trial_rows):
            return None
        return self.study['results'][self._trial_rows[n]]

    def report_stress_tests(self):
        if self.running() or not self.study or 'baseline' not in self.study['results']:
            return
        try:
            from amr_project import Project
            self.editor.show_project_report()
            panel = self.editor.report_panel
            if panel.running():
                raise ValueError('Wait for the current report to finish before selecting stress tests.')
            baseline = self.study['results']['baseline']
            panel._study_context = Project.open(baseline['project'])
            panel.set_run(baseline['directory'])
            panel.select_stress_tests(known=(str(self.path),))
        except Exception as exc:
            self.status.setText(str(exc))

    def trial_selected(self, *_):
        record = self.selected_trial()
        self.investigate_button.setEnabled(bool(record) and not self.running())
        self.playback_button.setEnabled(bool(record) and not self.running())
        self.save_scenario_button.setEnabled(bool(record and record['events']) and not self.running() and not self.stale())
        if record:
            lines = []
            labels = dict(amr='AMR', lift='Lift', corridor='Corridor', corridor_node='Door')
            for event in record['events']:
                assets = ', '.join(event.get('resource_ids', []))
                start = event.get('start_datetime', event.get('start_time', '')).replace('T', ' ')
                end = event.get('end_datetime', event.get('end_time', '')).replace('T', ' ')
                lines.append(f"{labels.get(event['resource_type'], event['resource_type'])} {assets}: "
                    f"{event['availability_percent']:g}% availability, {event['speed_factor'] * 100:g}% speed; {start} to {end}.")
                if is_amr_speed_sweep(self.study['settings']):
                    lines.append('All day, every day, including work completing after demand ends. All instances are included.')
            if not lines:
                lines.append('Normal operation, with the configured demand and operating settings.')
            if record.get('reused'):
                lines.append('Baseline reused from existing simulation: ' + record['directory'])
            unmet = record['metrics']['unmet']
            lines.append(f"{record['metrics']['late']} tasks finished after demand ended (informational; allowed).")
            lines.append('Unmet service obligations: ' + (', '.join(unmet) if unmet else 'None.'))
            self.details.setPlainText('\n'.join(lines))
        else:
            self.details.clear()

    def corridor_selected(self, *_):
        n = self.corridors.currentRow()
        if self.running() or not self.study or not 0 <= n < len(self._corridor_rows) or self.stale():
            return
        record = self.study['results'][self._corridor_rows[n]]
        a, b = record['corridor'].split(' -> ')
        self.editor.selected_edge_keys = {tuple(sorted((r['from'], r['to']))) for r in self.editor.store.data['corridors']['edges']
                                         if {r['from'], r['to']} == {a, b}}
        self.editor.selected_point_names = set()
        self.editor.selected_point_name = None
        self.editor.workspace.show_page('layout', self.editor.canvas)
        points = self.editor.store.all_points()
        if a in points:
            self.editor.floor_spin.setValue(points[a]['floor'])
        self.editor.refresh_canvas()
        self.editor.fit_selection()
        if record['id'] in self._trial_rows:
            self.results.setCurrentCell(self._trial_rows.index(record['id']), 0)

    def verified_selected(self):
        record = self.selected_trial()
        if record is None:
            raise ValueError('Select a trial first.')
        # Verify the selected record again before using its saved metrics or events.
        from amr_scenario_study import run_metrics, verify_trial_inputs
        verify_trial_inputs(self.study, record)
        baseline = None
        if record['kind'] != 'baseline':
            baseline_record = self.study['results']['baseline']
            baseline = run_metrics(baseline_record['directory'])
            if baseline != baseline_record['metrics']:
                raise ValueError('Baseline summary does not match its evidence.')
        if run_metrics(record['directory'], baseline) != record['metrics']:
            raise ValueError('Selected metrics do not match the trial evidence.')
        return record

    def investigate(self):
        try:
            record = self.selected_trial()
            if record is None:
                raise ValueError('Select a trial first.')
            self.editor.show_results_investigation()
            self.editor.results_panel._study_context = (self.study, record)
            self.editor.results_panel.load(record['directory'])
        except Exception as exc:
            self.status.setText(str(exc))

    def playback(self):
        try:
            from amr_project import Project
            record = self.verified_selected()
            self.editor.show_project_playback()
            self.editor.playback_panel._study_context = Project.open(record['project'])
            self.editor.playback_panel.load(record['directory'])
        except Exception as exc:
            self.status.setText(str(exc))

    def save_scenario(self):
        try:
            validate_study(self.study, self.editor.store.data)
            record = self.verified_selected()
            name = self.editor.save_stress_scenario(record['events'], record['name'])
            self.status.setText(f'Saved editable scenario: {name}. Open Scenario testing to review or enable it.')
            self.refresh()
        except Exception as exc:
            self.status.setText(str(exc))

    def closeEvent(self, event):
        if self.running():
            self.status.setText('Stop the study or wait for completion before closing.')
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self.running():
            self.status.setText('Stop the study or wait for completion before closing.')
            return
        super().reject()
