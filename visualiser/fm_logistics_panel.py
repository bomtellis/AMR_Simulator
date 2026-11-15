"""FM planning workspace, using the editor's project and worker boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from amr_fm_forecast import actual_activity, compare, native_demand, suggest_policy, validate_application
from visualiser.project_checks import config_fingerprint


class JobSignals(QObject):
    finished = Signal(object, str)


class Job(QRunnable):
    def __init__(self, call):
        super().__init__()
        self.call = call
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.call(), "")
        except Exception as error:
            self.signals.finished.emit(None, str(error))


def table(columns, editable=False):
    widget = QTableWidget(0, len(columns))
    widget.setHorizontalHeaderLabels(columns)
    widget.setAlternatingRowColors(True)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    if not editable:
        widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    return widget


def fill(widget, rows):
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            widget.setItem(i, j, QTableWidgetItem("" if value is None else str(value)))


class FMLogisticsPanel(QWidget):
    def __init__(self, configuration, apply, parent=None):
        super().__init__(parent)
        self.configuration = configuration
        self.apply = apply
        self.job = None
        self.baseline = None
        self.comparison = None
        self.plan = {"enabled": True, "categories": {}}
        self.category_key = ""
        self.saved_plan = None
        self.actual = None
        self.refreshing = False

        layout = QVBoxLayout(self)
        intro = QLabel("Compare the full FM workload across shared lifts. Configure release waves and optional holds by category.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status = QLabel("Load demand to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        setup = QWidget()
        controls = QVBoxLayout(setup)
        actions = QHBoxLayout()
        self.load_button = QPushButton("Load demand")
        self.load_button.clicked.connect(self.load)
        self.suggest_button = QPushButton("Suggest cohorts and windows")
        self.suggest_button.clicked.connect(self.suggest)
        self.compare_button = QPushButton("Compare sequences")
        self.compare_button.clicked.connect(self.run_comparison)
        self.apply_button = QPushButton("Apply to project")
        self.apply_button.clicked.connect(self.apply_selected)
        for button in (self.load_button, self.suggest_button, self.compare_button, self.apply_button):
            actions.addWidget(button)
        controls.addLayout(actions)
        form = QFormLayout()
        self.enabled = QCheckBox("Use FM release planning in normal simulations")
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(self.invalidate)
        form.addRow(self.enabled)
        self.category = QComboBox()
        self.category.currentTextChanged.connect(self.select_category)
        form.addRow("Configure category", self.category)
        self.hold = QDoubleSpinBox()
        self.hold.setRange(0, 60)
        self.hold.setSuffix(" min")
        self.hold.setSpecialValueText("Off")
        self.hold.valueChanged.connect(self.invalidate)
        form.addRow("Maximum reactive hold", self.hold)
        controls.addLayout(form)
        self.cohorts = table(["Cohort", "Department IDs (comma-separated)"], True)
        self.windows = table(["Original slot", "Earliest dispatch", "Arrive by", "Wave offsets in minutes"], True)
        self.cohorts.itemChanged.connect(self.invalidate)
        self.windows.itemChanged.connect(self.invalidate)
        controls.addWidget(QLabel("Cohort row order sets the manual sequence. Use one offset per cohort in that order."))
        controls.addWidget(self.cohorts)
        controls.addWidget(self.windows)
        for label, widget in (("Cohort", self.cohorts), ("Window", self.windows)):
            line = QHBoxLayout()
            add, remove = QPushButton(f"Add {label.lower()}"), QPushButton(f"Remove {label.lower()}")
            add.clicked.connect(lambda checked=False, target=widget: self.add_row(target))
            remove.clicked.connect(lambda checked=False, target=widget: self.remove_row(target))
            line.addWidget(add)
            line.addWidget(remove)
            line.addStretch()
            controls.addLayout(line)
        self.tabs.addTab(setup, "Planning settings")

        forecast = QWidget()
        forecast_layout = QVBoxLayout(forecast)
        self.options = QComboBox()
        self.options.currentIndexChanged.connect(self.show_forecast)
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(self.show_forecast)
        filters = QFormLayout()
        filters.addRow("Compare option", self.options)
        filters.addRow("Show category", self.filter)
        self.forecast_page = QSpinBox()
        self.forecast_page.setMinimum(1)
        self.forecast_page.valueChanged.connect(self.show_forecast)
        filters.addRow("Page", self.forecast_page)
        forecast_layout.addLayout(filters)
        self.summary = table(["Sequence", "Tasks", "Payloads", "Late", "Unresolved", "Peak lift s / 5 min", "Lift wait s"])
        forecast_layout.addWidget(self.summary)
        self.breakdown = table(["Category", "Tasks", "Late", "Unresolved", "Delivery up/down/same",
                                "Return up/down/same", "Reposition up/down", "Lift wait s"])
        forecast_layout.addWidget(self.breakdown)
        self.forecast_rows = table(["Category", "Department", "Payload", "Cohort", "Native release", "Wave release",
                                    "Arrive by", "Estimated arrival", "Final destination"])
        forecast_layout.addWidget(self.forecast_rows, 2)
        self.unknown = QLabel()
        self.unknown.setWordWrap(True)
        forecast_layout.addWidget(self.unknown)
        self.tabs.addTab(forecast, "Forecast")

        actual = QWidget()
        actual_layout = QVBoxLayout(actual)
        self.open_run = QPushButton("Load normal run events…")
        self.open_run.clicked.connect(self.open_actual)
        actual_layout.addWidget(self.open_run)
        actual_filters = QFormLayout()
        self.actual_query = QLineEdit()
        self.actual_query.setPlaceholderText("Search task, category, department, payload or status")
        self.actual_query.textChanged.connect(self.filter_actual)
        actual_filters.addRow("Find task", self.actual_query)
        self.actual_page = QSpinBox()
        self.actual_page.setMinimum(1)
        self.actual_page.valueChanged.connect(self.filter_actual)
        actual_filters.addRow("Page", self.actual_page)
        actual_layout.addLayout(actual_filters)
        self.actual_summary = table(["Category", "Metric", "Value"])
        self.actual_rows = table(["Task", "Category", "Payload", "Quantity", "Cohort", "Original or ready (s)",
                                  "Planned release (s)", "Actual release (s)", "Arrive by (s)",
                                  "Actual arrival (s)", "Status", "Hold or bypass reason"])
        actual_layout.addWidget(self.actual_summary)
        actual_layout.addWidget(self.actual_rows, 2)
        self.tabs.addTab(actual, "Actual activity")
        self.refresh()

    def refresh(self):
        configured = self.configuration().get("task_generation", {}).get("fm_logistics")
        if self.saved_plan != configured:
            self.saved_plan = deepcopy(configured)
            self.plan = deepcopy(configured) if configured is not None else {"enabled": True, "categories": {}}
            self.refreshing = True
            self.enabled.setChecked(self.plan.get("enabled", False))
            self.refreshing = False
            self.show_category()
            self.invalidate()
        if self.baseline and self.baseline_hash != config_fingerprint(self.configuration()):
            self.baseline = None
            self.invalidate()
        self.buttons()

    def buttons(self):
        ready = self.job is None
        self.category.setEnabled(ready)
        self.enabled.setEnabled(ready)
        self.hold.setEnabled(ready)
        self.cohorts.setEnabled(ready)
        self.windows.setEnabled(ready)
        self.load_button.setEnabled(ready)
        self.suggest_button.setEnabled(ready and bool(self.baseline and self.category_key))
        self.compare_button.setEnabled(ready and bool(self.baseline))
        self.open_run.setEnabled(ready)
        selected = self.options.currentData()
        self.apply_button.setEnabled(ready and (bool(self.comparison and selected != "current")
                                                 or self.saved_plan is not None and not self.enabled.isChecked()))

    def invalidate(self, *_):
        if not self.refreshing:
            self.comparison = None
            self.status.setText("Settings changed. Compare sequences again before applying.")
            self.buttons()

    def add_row(self, widget):
        if self.job:
            return
        row = widget.rowCount()
        widget.insertRow(row)
        widget.setItem(row, 0, QTableWidgetItem(f"{self.category_key}-{row + 1}" if widget == self.cohorts else "08:00"))
        self.invalidate()

    def remove_row(self, widget):
        if not self.job and widget.currentRow() >= 0:
            widget.removeRow(widget.currentRow())
            self.invalidate()

    @staticmethod
    def cell(widget, row, column):
        item = widget.item(row, column)
        return item.text().strip() if item else ""

    def save_category(self):
        if not self.category_key:
            return
        groups = []
        for row in range(self.cohorts.rowCount()):
            name = self.cell(self.cohorts, row, 0)
            members = self.cell(self.cohorts, row, 1)
            groups.append({"id": name, "departments": [part.strip() for part in members.split(",") if part.strip()]})
        slots = {}
        for row in range(self.windows.rowCount()):
            slot, earliest, deadline, raw = [self.cell(self.windows, row, col) for col in range(4)]
            if slot in slots:
                raise ValueError(f"Duplicate slot {slot}")
            values = [float(value.strip()) * 60 for value in raw.split(",")] if raw else []
            if len(values) != len(groups):
                raise ValueError(f"{slot} needs one offset per cohort.")
            slots[slot] = {"earliest": earliest, "deadline": deadline,
                           "offsets": {group["id"]: value for group, value in zip(groups, values)}}
        self.plan["categories"][self.category_key] = dict(cohorts=groups, slots=slots, hold_seconds=self.hold.value() * 60)

    def show_category(self):
        policy = self.plan["categories"].get(self.category_key, {})
        groups = policy.get("cohorts", [])
        self.refreshing = True
        self.hold.setValue(policy.get("hold_seconds", 0) / 60)
        fill(self.cohorts, [(row["id"], ", ".join(row["departments"])) for row in groups])
        fill(self.windows, [(slot, row["earliest"], row["deadline"],
                             ", ".join(f"{row['offsets'].get(group['id'], 0) / 60:.8g}" for group in groups))
                            for slot, row in policy.get("slots", {}).items()])
        self.refreshing = False
        self.buttons()

    def select_category(self, category):
        if self.refreshing:
            return
        try:
            self.save_category()
        except ValueError as error:
            self.category.blockSignals(True)
            self.category.setCurrentText(self.category_key)
            self.category.blockSignals(False)
            self.status.setText(str(error))
            return
        self.category_key = category
        self.show_category()

    def work(self, title, call, done, *, check_project=True):
        if self.job:
            return
        fingerprint = config_fingerprint(self.configuration())
        self.status.setText(title)
        self.job = Job(call)
        self.job_context = fingerprint, check_project, done
        self.job.signals.finished.connect(self.finish_job, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(self.job)
        self.buttons()

    @Slot(object, str)
    def finish_job(self, value, error):
        fingerprint, check_project, done = self.job_context
        self.job = None
        self.job_context = None
        if error:
            self.status.setText(error)
        elif check_project and fingerprint != config_fingerprint(self.configuration()):
            self.status.setText("The project changed during calculation. Reload demand.")
        else:
            done(value)
        self.buttons()

    def load(self):
        config = deepcopy(self.configuration())

        def load_baseline():
            preview = native_demand(config)
            catering = None
            if 'catering' not in configured and any(row['category'] == 'catering' for row in preview['tasks']):
                catering = suggest_policy(config, preview, 'catering')
            return preview, catering

        configured = deepcopy(self.plan['categories'])

        def accept(result):
            preview, catering = result
            self.baseline = preview
            self.baseline_hash = config_fingerprint(config)
            self.comparison = None
            keys = sorted({row["category"] for row in preview["rules"]
                           if row["category"] not in {"Explicit tasks", "Legacy waste"}})
            self.refreshing = True
            self.category.clear()
            self.category.addItems(keys)
            self.category.setCurrentText("catering" if "catering" in keys else self.category.currentText())
            self.category_key = self.category.currentText()
            self.refreshing = False
            if catering is not None:
                self.plan["categories"]["catering"] = catering
            self.show_category()
            self.status.setText(f"{len(preview['tasks'])} forecastable task records loaded. Edit settings or compare sequences.")

        self.work("Resolving project demand…", load_baseline, accept)

    def suggest(self):
        if self.baseline:
            category, baseline = self.category_key, self.baseline
            config = deepcopy(self.configuration())

            def accept(policy):
                policy["hold_seconds"] = self.hold.value() * 60
                self.plan["categories"][category] = policy
                self.show_category()
                self.invalidate()

            self.work("Estimating department workloads…", lambda: suggest_policy(config, baseline, category), accept)

    def run_comparison(self):
        if not self.baseline:
            return
        config = deepcopy(self.configuration())
        if config_fingerprint(config) != self.baseline_hash:
            self.status.setText("Project settings changed. Load demand again.")
            return
        try:
            self.save_category()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.plan["enabled"] = self.enabled.isChecked()
        draft, baseline = deepcopy(self.plan), self.baseline

        def accept(result):
            self.comparison = result
            self.options.clear()
            for option in result["results"]:
                self.options.addItem(option["label"], option["strategy"])
            keys = sorted({row["category"] for row in baseline["tasks"]})
            self.filter.clear()
            self.filter.addItem("All categories", "")
            for key in keys:
                self.filter.addItem(key, key)
            self.show_forecast()
            self.tabs.setCurrentIndex(1)
            self.status.setText("Forecast complete. Review the suggested sequence before applying.")

        self.work("Comparing releases and shared lift bookings…", lambda: compare(config, draft, baseline), accept)

    def show_forecast(self, *_):
        if not self.comparison:
            return
        results = self.comparison["results"]
        fill(self.summary, [(option["label"], *(round(option["totals"].get(key, 0), 1)
                             for key in ("tasks", "payloads", "late", "unresolved", "peak_lift_seconds", "lift_wait_seconds")))
                            for option in results])
        selected = next((option for option in results if option["strategy"] == self.options.currentData()), results[0])
        category = self.filter.currentData()

        def directions(row, kind, keys):
            return " / ".join(str(row.get(f"{kind}_{key}", 0)) for key in keys)

        fill(self.breakdown, [(key, row.get("tasks", 0), row.get("late", 0), row.get("unresolved", 0),
                              directions(row, "outbound", ("up", "down", "same_floor")),
                              directions(row, "return", ("up", "down", "same_floor")),
                              directions(row, "reposition", ("up", "down")), round(row.get("lift_wait_seconds", 0), 1))
                             for key, row in sorted(selected["categories"].items()) if not category or key == category])
        start = datetime.fromisoformat(self.baseline["start_datetime"])

        def clock(seconds):
            return (start + timedelta(seconds=seconds)).isoformat(sep=" ", timespec="seconds") if seconds is not None else ""

        rows = [row for row in selected["rows"] if not category or row["category"] == category]
        page = self.page_slice(self.forecast_page, len(rows))
        fill(self.forecast_rows, [(row["category"], row["department"], row["payload"], row["cohort"],
                                  clock(row["release_seconds"]), clock(row["planned"]), clock(row["deadline"]),
                                  clock(row["estimated_arrival"]), row["final"]) for row in rows[page]])
        unknown = sorted({row["category"] for row in self.comparison["runtime"]})
        self.unknown.setText(f"{len(rows)} forecast tasks. "
                             f"Runtime-dependent demand: {', '.join(unknown) or 'none identified'}. "
                             "Lift estimates use loaded routes and projected returns. Fleet and staff queues are measured in normal runs.")
        self.buttons()

    def apply_selected(self):
        if not self.enabled.isChecked() and self.saved_plan is not None:
            plan = dict(self.saved_plan, enabled=False)
            if self.apply(plan):
                self.saved_plan = deepcopy(plan)
                self.status.setText("FM planning disabled in the project.")
            return
        if not self.comparison or not self.baseline:
            return
        config = deepcopy(self.configuration())
        if config_fingerprint(config) != self.comparison["config_hash"]:
            self.status.setText("Project settings changed. Load demand and compare again.")
            return
        selected = next(row for row in self.comparison["results"] if row["strategy"] == self.options.currentData())
        plan = deepcopy(selected["settings"])
        baseline = self.baseline

        def accept(_):
            if self.apply(plan):
                self.saved_plan = deepcopy(plan)
                self.plan = deepcopy(plan)
                self.baseline_hash = config_fingerprint(self.configuration())
                self.show_category()
                self.status.setText("FM sequence applied. Save the project and run the simulation to measure it.")

        self.work("Checking release windows against native calendars…",
                  lambda: validate_application(config, plan, baseline), accept)

    def open_actual(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open simulation events", "",
                                              "Simulation events (*.sqlite *.csv)")
        if path:
            self.work("Reading normal simulation evidence…", lambda: actual_activity(path), self.show_actual,
                      check_project=False)

    def show_actual(self, result):
        self.actual = result
        fill(self.actual_summary, [(category, key.replace("_", " "), round(value, 2))
                                   for category, metrics in [("Whole run", result["totals"]), *sorted(result["categories"].items())]
                                   for key, value in sorted(metrics.items())])
        self.filter_actual()

    @staticmethod
    def page_slice(widget, count):
        size = 500
        widget.blockSignals(True)
        widget.setMaximum(max(1, (count + size - 1) // size))
        widget.blockSignals(False)
        first = (widget.value() - 1) * size
        return slice(first, first + size)

    def filter_actual(self, *_):
        if self.actual is None:
            return
        query = self.actual_query.text().strip().casefold()
        rows = [row for row in self.actual["tasks"] if any(
            query in str(row.get(key) or "").casefold() for key in
            ("id", "category", "department", "payload", "status"))]
        page = self.page_slice(self.actual_page, len(rows))
        fill(self.actual_rows, [tuple(row.get(key) for key in
                                      ("id", "category", "payload", "quantity", "cohort", "original", "planned",
                                       "actual_release", "deadline", "arrival", "status", "hold_reason"))
                                for row in rows[page]])
        self.status.setText(f"{len(rows)} of {len(self.actual['tasks'])} tasks match. Totals cover the entire run.")
