import json
from typing import Any, List, Optional

from advanced_dialogs import MultiSelectPicker

from PySide6.QtCore import Qt, QPointF, QRectF, QTime
from PySide6.QtGui import QColor, QBrush, QPen, QPolygonF, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPolygonItem,
    QGraphicsSimpleTextItem,
    QGraphicsItem,
    QMenu,
    QGraphicsPathItem,
    QTimeEdit,
)


class ScheduledTimesDialog(QDialog):
    def __init__(self, parent, times=None):
        super().__init__(parent)
        self.setWindowTitle("Scheduled times")
        self.resize(520, 520)

        self.result = None
        self.times = sorted(set(times or []))

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Scheduled task times over a 24 hour day"))

        add_row = QHBoxLayout()
        layout.addLayout(add_row)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(8, 0))

        add_btn = QPushButton("Add time")
        add_btn.clicked.connect(self.add_time)

        add_row.addWidget(self.time_edit)
        add_row.addWidget(add_btn)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        layout.addLayout(btn_row)

        remove_btn = QPushButton("Remove selected")
        clear_btn = QPushButton("Clear all")
        sort_btn = QPushButton("Sort")

        remove_btn.clicked.connect(self.remove_selected)
        clear_btn.clicked.connect(self.clear_all)
        sort_btn.clicked.connect(self.refresh)

        btn_row.addWidget(remove_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(sort_btn)
        btn_row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh()

    def add_time(self):
        value = self.time_edit.time().toString("HH:mm")
        if value not in self.times:
            self.times.append(value)
            self.times.sort()
        self.refresh()

    def remove_selected(self):
        rows = sorted(
            {index.row() for index in self.list_widget.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            if 0 <= row < len(self.times):
                del self.times[row]
        self.refresh()

    def clear_all(self):
        self.times = []
        self.refresh()

    def refresh(self):
        self.times = sorted(set(self.times))
        self.list_widget.clear()

        for hour in range(24):
            hour_times = [t for t in self.times if t.startswith(f"{hour:02d}:")]
            if not hour_times:
                continue

            header = QListWidgetItem(f"{hour:02d}:00")
            header.setFlags(Qt.ItemIsEnabled)
            self.list_widget.addItem(header)

            for value in hour_times:
                item = QListWidgetItem(f"    {value}")
                item.setData(Qt.UserRole, value)
                self.list_widget.addItem(item)

    def accept(self):
        self.result = sorted(set(self.times))
        super().accept()


class TaskGenerationSettingsDialog(QDialog):
    """Editor for top-level task_generation logistics parameters."""

    DAYS = [
        ("mon", "Mon"),
        ("tue", "Tue"),
        ("wed", "Wed"),
        ("thu", "Thu"),
        ("fri", "Fri"),
        ("sat", "Sat"),
        ("sun", "Sun"),
    ]

    CATEGORY_LABELS = [
        ("catering", "Catering"),
        ("pharmacy", "Pharmacy"),
        ("linen", "Linen"),
        ("waste", "Waste"),
        ("stores", "Stores"),
        ("ssd", "SSD"),
    ]

    MODES = [
        "scheduled",
        "threshold",
        "continuous",
        "sporadic",
        "hybrid",
        "scheduled_threshold",
        "scheduled_sporadic",
    ]

    def __init__(
        self,
        parent,
        task_generation,
        location_names,
        payload_names,
        profile_names,
        departments,
        on_save,
    ):
        super().__init__(parent)
        self.setWindowTitle("Task generation parameters")
        self.resize(1060, 720)
        self.location_names = sorted(location_names)
        self.payload_names = sorted(payload_names)
        self.profile_names = list(profile_names)
        self.departments = [dict(x) for x in (departments or [])]
        self.current_department_id = None
        self.on_save = on_save
        self.current_key = None
        self.selected_dropoffs = []
        self._loading = False
        self.config = self._normalise_config(task_generation)

        layout = QVBoxLayout(self)

        self.global_enabled = QCheckBox("Enable automatic task generation")
        self.global_enabled.setChecked(bool(self.config.get("enabled", True)))
        layout.addWidget(self.global_enabled)

        body = QHBoxLayout()
        layout.addLayout(body, 1)

        left = QVBoxLayout()
        body.addLayout(left, 0)

        lists_row = QHBoxLayout()
        left.addLayout(lists_row, 1)

        category_col = QVBoxLayout()
        lists_row.addLayout(category_col)

        category_col.addWidget(QLabel("Categories"))
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(190)
        category_col.addWidget(self.category_list, 1)

        department_col = QVBoxLayout()
        lists_row.addLayout(department_col)

        department_col.addWidget(QLabel("Departments"))
        self.department_list = QListWidget()
        self.department_list.setFixedWidth(230)
        department_col.addWidget(self.department_list, 1)

        self.department_hint = QLabel(
            "Select a department to override category defaults"
        )
        self.department_hint.setWordWrap(True)
        department_col.addWidget(self.department_hint)

        category_buttons = QHBoxLayout()
        left.addLayout(category_buttons)
        add_category_btn = QPushButton("Add")
        delete_category_btn = QPushButton("Delete")
        add_category_btn.clicked.connect(self.add_category)
        delete_category_btn.clicked.connect(self.delete_current_category)
        category_buttons.addWidget(add_category_btn)
        category_buttons.addWidget(delete_category_btn)

        right = QScrollArea()
        right.setWidgetResizable(True)
        body.addWidget(right, 1)
        container = QWidget()
        right.setWidget(container)
        form = QFormLayout(container)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.enabled_check = QCheckBox("Enabled")
        self.display_name_edit = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.priority_edit = QLineEdit()

        self.pickup_combo = QComboBox()
        self.pickup_combo.addItems([""] + self.location_names)

        self.dropoff_summary = QLabel("None selected")
        self.dropoff_summary.setWordWrap(True)
        dropoff_row = QHBoxLayout()
        dropoff_row.addWidget(self.dropoff_summary, 1)
        self.pick_dropoffs_btn = QPushButton("Select...")
        self.pick_dropoffs_btn.clicked.connect(self.pick_dropoff_locations)
        self.clear_dropoffs_btn = QPushButton("Clear")
        self.clear_dropoffs_btn.clicked.connect(self.clear_dropoff_locations)
        dropoff_row.addWidget(self.pick_dropoffs_btn)
        dropoff_row.addWidget(self.clear_dropoffs_btn)

        self.payload_combo = QComboBox()
        self.payload_combo.addItems([""] + self.payload_names)
        self.route_profile_combo = QComboBox()
        self.route_profile_combo.addItems([""] + self.profile_names)

        self.return_enabled_check = QCheckBox("Generate return / exchange task")
        self.return_payload_combo = QComboBox()
        self.return_payload_combo.addItems([""] + self.payload_names)

        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        self.day_checks = {}
        for key, label in self.DAYS:
            chk = QCheckBox(label)
            self.day_checks[key] = chk
            days_layout.addWidget(chk)
        days_layout.addStretch(1)

        self.scheduled_times = []

        schedule_row = QHBoxLayout()
        self.schedule_summary = QLabel("No times selected")
        self.schedule_summary.setWordWrap(True)

        schedule_btn = QPushButton("Edit times...")
        schedule_btn.clicked.connect(self.edit_scheduled_times)

        clear_schedule_btn = QPushButton("Clear")
        clear_schedule_btn.clicked.connect(self.clear_scheduled_times)

        schedule_row.addWidget(self.schedule_summary, 1)
        schedule_row.addWidget(schedule_btn)
        schedule_row.addWidget(clear_schedule_btn)

        self.schedule_button = schedule_btn
        self.clear_schedule_button = clear_schedule_btn

        self.frequency_edit = QLineEdit()
        self.volume_per_event_edit = QLineEdit()
        self.threshold_volume_edit = QLineEdit()
        self.base_daily_volume_edit = QLineEdit()
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(90)

        form.addRow("Category enabled", self.enabled_check)
        form.addRow("Display name", self.display_name_edit)
        form.addRow("Generation mode", self.mode_combo)
        form.addRow("Priority", self.priority_edit)
        form.addRow("Pickup / source location", self.pickup_combo)
        form.addRow("Drop-off destinations", dropoff_row)
        form.addRow("Payload", self.payload_combo)
        form.addRow("Route profile", self.route_profile_combo)
        form.addRow("Return task", self.return_enabled_check)
        form.addRow("Return payload", self.return_payload_combo)
        form.addRow("Days active", days_widget)

        form.addRow("Scheduled times", schedule_row)

        form.addRow("Frequency per day", self.frequency_edit)
        form.addRow("Volume per event m³", self.volume_per_event_edit)
        form.addRow("Threshold volume m³", self.threshold_volume_edit)
        form.addRow("Base daily volume m³", self.base_daily_volume_edit)
        form.addRow("Notes", self.notes_edit)

        help_label = QLabel(
            "Schedule times are comma-separated HH:MM values. "
            "Drop-off destinations can contain multiple locations; the first is also saved as "
            "dropoff_location for compatibility with existing generators. "
            "The Waste category also keeps the legacy department_waste settings in step."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.mode_combo.currentTextChanged.connect(self._update_mode_field_state)
        self.return_enabled_check.toggled.connect(self._update_mode_field_state)

        self.category_list.currentItemChanged.connect(self._on_category_changed)
        self.department_list.currentItemChanged.connect(self._on_department_changed)

        self._refresh_category_list()

        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)
            current = self.category_list.currentItem()
            if current is not None:
                self.current_key = current.data(Qt.UserRole)

        self.current_department_id = ""

        self._loading = True
        self._refresh_department_list(select_dept_id="")
        if self.current_key:
            self._load_category(self.current_key)
        self._loading = False

        self._refresh_schedule_summary()

    def _department_label(self, dept):
        name = str(dept.get("name", "")).strip()
        dept_id = str(dept.get("id", "")).strip()
        enabled = bool(dept.get("enabled", True))

        label = name or dept_id or "Department"
        if dept_id and dept_id != label:
            label = f"{label} ({dept_id})"

        if not enabled:
            label += " [disabled]"

        return label

    def _refresh_department_list(self, select_dept_id=None):
        current_dept_id = select_dept_id or self.current_department_id

        self.department_list.blockSignals(True)
        self.department_list.clear()

        selected_row = 0
        row_index = 0

        valid_departments = []

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                dept_id = str(dept.get("name", "")).strip()

            if not dept_id:
                continue

            valid_departments.append((dept_id, dept))

        if not valid_departments:
            item = QListWidgetItem("Category defaults")
            item.setData(Qt.UserRole, "")
            self.department_list.addItem(item)
        else:
            for dept_id, dept in valid_departments:
                item = QListWidgetItem(self._department_label(dept))
                item.setData(Qt.UserRole, dept_id)
                self.department_list.addItem(item)

                if dept_id == current_dept_id:
                    selected_row = row_index

                row_index += 1

        self.department_list.blockSignals(False)

        if self.department_list.count() > 0:
            self.department_list.setCurrentRow(selected_row)
            current = self.department_list.currentItem()
            self.current_department_id = current.data(Qt.UserRole) if current else ""
            self.current_department_id = self.current_department_id or ""

    def _on_department_changed(self, current, previous):
        if self._loading:
            return

        if previous is not None and self.current_key:
            previous_dept_id = previous.data(Qt.UserRole) or ""
            try:
                self._store_category(
                    self.current_key,
                    list_item=self.category_list.currentItem(),
                    department_id=previous_dept_id,
                )
            except Exception as exc:
                self._loading = True
                self.department_list.setCurrentItem(previous)
                self._loading = False
                QMessageBox.critical(self, "Invalid department settings", str(exc))
                return

        self.current_department_id = current.data(Qt.UserRole) if current else ""
        self.current_department_id = self.current_department_id or ""

        if self.current_key:
            self._loading = True
            self._load_category(self.current_key)
            self._loading = False

    def _department_overrides_for_category(self, category_key):
        category = self.config.setdefault("categories", {}).setdefault(category_key, {})
        overrides = category.setdefault("departments", {})

        if not isinstance(overrides, dict):
            overrides = {}
            category["departments"] = overrides

        return overrides

    def _effective_category_item(self, category_key, department_id=None):
        category = dict(self.config.get("categories", {}).get(category_key, {}))

        if department_id:
            overrides = self._department_overrides_for_category(category_key)
            dept_cfg = overrides.get(department_id, {})
            if isinstance(dept_cfg, dict):
                merged = dict(category)
                merged.update(dept_cfg)
                merged["departments"] = category.get("departments", {})
                return merged

        return category

    def edit_scheduled_times(self):
        dialog = ScheduledTimesDialog(self, self.scheduled_times)
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.scheduled_times = list(dialog.result)
            self._refresh_schedule_summary()

    def clear_scheduled_times(self):
        self.scheduled_times = []
        self._refresh_schedule_summary()

    def _refresh_schedule_summary(self):
        if not self.scheduled_times:
            self.schedule_summary.setText("No times selected")
        elif len(self.scheduled_times) <= 8:
            self.schedule_summary.setText(", ".join(self.scheduled_times))
        else:
            self.schedule_summary.setText(
                f"{len(self.scheduled_times)} times selected: "
                + ", ".join(self.scheduled_times[:8])
                + "..."
            )

    def _category_label_pairs(self):
        labels = {key: label for key, label in self.CATEGORY_LABELS}
        pairs = []
        for key, item in self.config.get("categories", {}).items():
            display = str(item.get("display_name", "")).strip() or labels.get(
                key, key.title()
            )
            pairs.append((key, display))
        return sorted(pairs, key=lambda pair: pair[1].lower())

    def _refresh_category_list(self, select_key=None):
        current_key = select_key or self.current_key
        self.category_list.blockSignals(True)
        self.category_list.clear()
        selected_row = 0
        for row, (key, label) in enumerate(self._category_label_pairs()):
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.category_list.addItem(item)
            if key == current_key:
                selected_row = row
        self.category_list.blockSignals(False)
        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(selected_row)
            current = self.category_list.currentItem()
            if current is not None:
                self.current_key = current.data(Qt.UserRole)
                self._load_category(self.current_key)

    def _slugify_category_key(self, value):
        text = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value).strip())
        text = "_".join(part for part in text.split("_") if part)
        return text or "category"

    def add_category(self):
        try:
            self._store_current_category()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid current category", str(exc))
            return

        name, ok = QInputDialog.getText(
            self, "New logistics category", "Category name:"
        )
        if not ok or not name.strip():
            return

        base_key = self._slugify_category_key(name)
        key = base_key
        counter = 2
        while key in self.config.setdefault("categories", {}):
            key = f"{base_key}_{counter}"
            counter += 1

        self.config["categories"][key] = self._default_category(key, name.strip())
        self.current_key = key
        self._refresh_category_list(select_key=key)

    def delete_current_category(self):
        item = self.category_list.currentItem()
        if item is None:
            return
        key = item.data(Qt.UserRole)
        label = item.text()
        if key == "waste":
            QMessageBox.critical(
                self,
                "Delete category",
                "The Waste category cannot be deleted because it is used by the current department waste generator.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Delete category",
                f"Delete logistics category '{label}'?",
            )
            != QMessageBox.Yes
        ):
            return
        self.config.setdefault("categories", {}).pop(key, None)
        self.current_key = None
        self._refresh_category_list()

    def pick_dropoff_locations(self):
        picker = MultiSelectPicker(
            self,
            "Select drop-off destinations",
            self.location_names,
            selected=self.selected_dropoffs,
            group_resolver=lambda item: "Locations",
        )
        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_dropoffs = sorted(picker.result)
            self._refresh_dropoff_summary()

    def clear_dropoff_locations(self):
        self.selected_dropoffs = []
        self._refresh_dropoff_summary()

    def _refresh_dropoff_summary(self):
        if not self.selected_dropoffs:
            self.dropoff_summary.setText("None selected")
        elif len(self.selected_dropoffs) <= 4:
            self.dropoff_summary.setText(", ".join(self.selected_dropoffs))
        else:
            self.dropoff_summary.setText(f"{len(self.selected_dropoffs)} selected")

    def _default_category(self, key, label):
        return {
            "enabled": key == "waste",
            "display_name": label,
            "generation_mode": (
                "threshold" if key in {"waste", "linen"} else "scheduled"
            ),
            "priority": {
                "catering": 40,
                "pharmacy": 30,
                "linen": 55,
                "waste": 60,
                "stores": 70,
                "ssd": 35,
            }.get(key, 100),
            "pickup_location": "",
            "dropoff_location": "",
            "dropoff_locations": [],
            "payload": "",
            "return_enabled": key in {"catering", "linen", "waste", "ssd"},
            "return_payload": "",
            "route_profile": "",
            "days_active": ["mon", "tue", "wed", "thu", "fri"],
            "schedule_times": {
                "catering": ["07:30", "11:45", "16:45"],
                "pharmacy": ["10:00", "15:00"],
                "stores": ["09:30", "14:30"],
                "ssd": ["08:00", "12:00", "17:00"],
            }.get(key, []),
            "frequency_per_day": 0.0,
            "volume_per_event_m3": 0.0,
            "threshold_volume_m3": 0.24 if key == "waste" else 0.0,
            "base_daily_volume_m3": 0.0,
            "notes": "",
        }

    def _normalise_config(self, task_generation):
        source = dict(task_generation or {})
        result = {"enabled": bool(source.get("enabled", True)), "categories": {}}
        incoming_categories = (
            source.get("categories", {})
            if isinstance(source.get("categories", {}), dict)
            else {}
        )
        for key, label in self.CATEGORY_LABELS:
            item = self._default_category(key, label)
            if isinstance(incoming_categories.get(key), dict):
                item.update(incoming_categories[key])
            if isinstance(source.get(key), dict):
                item.update(source[key])
            self._normalise_category_dropoffs(item)
            result["categories"][key] = item

        for key, incoming in incoming_categories.items():
            if key in result["categories"] or not isinstance(incoming, dict):
                continue
            item = self._default_category(
                key, str(incoming.get("display_name", key.title()))
            )
            item.update(incoming)
            self._normalise_category_dropoffs(item)
            result["categories"][key] = item

        department_waste = dict(source.get("department_waste", {}) or {})
        if department_waste:
            result["categories"]["waste"]["enabled"] = bool(
                department_waste.get(
                    "enabled", result["categories"]["waste"].get("enabled", True)
                )
            )
            result["categories"]["waste"]["priority"] = int(
                float(
                    department_waste.get(
                        "priority", result["categories"]["waste"].get("priority", 60)
                    )
                )
            )
        result["department_waste"] = {
            "enabled": bool(result["categories"]["waste"].get("enabled", True)),
            "priority": int(float(result["categories"]["waste"].get("priority", 60))),
        }
        return result

    def _normalise_category_dropoffs(self, item):
        selected = item.get("dropoff_locations")
        if isinstance(selected, list):
            locations = [str(x).strip() for x in selected if str(x).strip()]
        else:
            locations = []
        legacy = str(item.get("dropoff_location", "")).strip()
        if legacy and legacy not in locations:
            locations.insert(0, legacy)
        item["dropoff_locations"] = locations
        item["dropoff_location"] = locations[0] if locations else legacy

    def _on_category_changed(self, current, previous):
        if self._loading:
            return

        # currentItemChanged is emitted after QListWidget has already moved the
        # selection.  Using currentItem() inside the save routine therefore
        # renames the newly selected list row with the previous category name.
        # Save the form into the previous category key and update the previous
        # list item only.
        if previous is not None:
            previous_key = previous.data(Qt.UserRole)
            try:
                self._store_category(
                    previous_key,
                    list_item=previous,
                    department_id=self.current_department_id or "",
                )
            except Exception as exc:
                self._loading = True
                self.category_list.setCurrentItem(previous)
                self._loading = False
                QMessageBox.critical(self, "Invalid category", str(exc))
                return

        if current is None:
            self.current_key = None
            return

        self.current_key = current.data(Qt.UserRole)
        self.current_department_id = ""
        self._loading = True
        self._refresh_department_list(select_dept_id="")
        self._load_category(self.current_key)
        self._loading = False

    def _load_category(self, key):
        was_loading = self._loading
        self._loading = True
        item = self._effective_category_item(key, self.current_department_id)
        self._normalise_category_dropoffs(item)
        self.selected_dropoffs = list(item.get("dropoff_locations", []))
        self.enabled_check.setChecked(bool(item.get("enabled", False)))
        self.display_name_edit.setText(str(item.get("display_name", key.title())))
        if self.current_department_id:
            self.display_name_edit.setEnabled(False)
        else:
            self.display_name_edit.setEnabled(True)
        self.mode_combo.setCurrentText(str(item.get("generation_mode", "scheduled")))
        self.priority_edit.setText(str(item.get("priority", 100)))
        self.pickup_combo.setCurrentText(str(item.get("pickup_location", "")))
        self._refresh_dropoff_summary()
        self.payload_combo.setCurrentText(str(item.get("payload", "")))
        self.route_profile_combo.setCurrentText(str(item.get("route_profile", "")))
        self.return_enabled_check.setChecked(bool(item.get("return_enabled", False)))
        self.return_payload_combo.setCurrentText(str(item.get("return_payload", "")))
        days = set(item.get("days_active", []))
        for day_key, _label in self.DAYS:
            self.day_checks[day_key].setChecked(day_key in days)
        self.scheduled_times = list(item.get("scheduled_times", []))

        legacy_schedule = str(item.get("schedule", "")).strip()
        if legacy_schedule and not self.scheduled_times:
            self.scheduled_times = [
                x.strip() for x in legacy_schedule.split(",") if x.strip()
            ]

        self._refresh_schedule_summary()
        self.frequency_edit.setText(str(item.get("frequency_per_day", 0.0)))
        self.volume_per_event_edit.setText(str(item.get("volume_per_event_m3", 0.0)))
        self.threshold_volume_edit.setText(str(item.get("threshold_volume_m3", 0.0)))
        self.base_daily_volume_edit.setText(str(item.get("base_daily_volume_m3", 0.0)))
        self.notes_edit.setPlainText(str(item.get("notes", "")))
        self._loading = was_loading
        self._update_mode_field_state()

    def _set_widget_enabled(self, widget, enabled):
        widget.setEnabled(bool(enabled))

    def _update_mode_field_state(self, *_):
        mode = self.mode_combo.currentText().strip()

        uses_schedule = mode in {
            "scheduled",
            "scheduled_threshold",
            "scheduled_sporadic",
        }

        uses_threshold = mode in {
            "threshold",
            "hybrid",
            "scheduled_threshold",
        }

        uses_continuous = mode in {
            "continuous",
            "hybrid",
        }

        uses_sporadic = mode in {
            "sporadic",
            "hybrid",
            "scheduled_sporadic",
        }

        self.schedule_summary.setEnabled(uses_schedule)
        self.schedule_button.setEnabled(uses_schedule)
        self.clear_schedule_button.setEnabled(uses_schedule)

        self.threshold_volume_edit.setEnabled(uses_threshold)

        self.base_daily_volume_edit.setEnabled(uses_continuous or uses_threshold)

        self.frequency_edit.setEnabled(uses_sporadic)

        self.volume_per_event_edit.setEnabled(uses_sporadic)

        self.return_payload_combo.setEnabled(self.return_enabled_check.isChecked())

    def _store_current_category(self):
        if not self.current_key:
            return

        self._store_category(
            self.current_key,
            list_item=self.category_list.currentItem(),
            department_id=self.current_department_id or "",
        )

    def _store_category(self, category_key, list_item=None, department_id=""):
        if not category_key:
            return

        days_active = [
            key for key, _label in self.DAYS if self.day_checks[key].isChecked()
        ]
        if not days_active:
            raise ValueError("Select at least one active day")

        display_name = (
            self.display_name_edit.text().strip() or str(category_key).title()
        )
        dropoff_locations = [
            str(x).strip() for x in self.selected_dropoffs if str(x).strip()
        ]
        payload = {
            "enabled": self.enabled_check.isChecked(),
            "display_name": display_name,
            "generation_mode": self.mode_combo.currentText().strip(),
            "priority": int(float(self.priority_edit.text() or 100)),
            "pickup_location": self.pickup_combo.currentText().strip(),
            "dropoff_location": dropoff_locations[0] if dropoff_locations else "",
            "dropoff_locations": dropoff_locations,
            "payload": self.payload_combo.currentText().strip(),
            "return_enabled": self.return_enabled_check.isChecked(),
            "return_payload": self.return_payload_combo.currentText().strip(),
            "route_profile": self.route_profile_combo.currentText().strip(),
            "days_active": days_active,
            "scheduled_times": list(self.scheduled_times),
            "frequency_per_day": float(self.frequency_edit.text() or 0.0),
            "volume_per_event_m3": float(self.volume_per_event_edit.text() or 0.0),
            "threshold_volume_m3": float(self.threshold_volume_edit.text() or 0.0),
            "base_daily_volume_m3": float(self.base_daily_volume_edit.text() or 0.0),
            "notes": self.notes_edit.toPlainText().strip(),
        }

        if department_id:
            # Store only the selected department override under this category.
            category = self.config.setdefault("categories", {}).setdefault(
                category_key, {}
            )
            overrides = category.setdefault("departments", {})
            payload.pop("display_name", None)
            payload.pop("departments", None)
            overrides[department_id] = payload
        else:
            # Store category defaults.
            existing_departments = (
                self.config.setdefault("categories", {})
                .setdefault(category_key, {})
                .get("departments", {})
            )
            payload["departments"] = existing_departments
            self.config["categories"][category_key] = payload

        if list_item is not None and not department_id:
            list_item.setText(display_name)

    def accept(self):
        try:
            self._store_current_category()
            self.config["enabled"] = self.global_enabled.isChecked()
            waste = self.config["categories"].get("waste", {})
            self.config["department_waste"] = {
                "enabled": bool(waste.get("enabled", True)),
                "priority": int(float(waste.get("priority", 60))),
            }
            self.on_save(self.config)
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid task generation settings", str(exc))


class PointEditorDialog(QDialog):
    def __init__(self, parent, title, point_name, point):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.point_name = point_name
        self.point = point
        self.result = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_edit = QLineEdit(str(point_name))
        self.x_edit = QLineEdit(str(point["x"]))
        self.y_edit = QLineEdit(str(point["y"]))
        form.addRow("Name", self.name_edit)
        form.addRow("X", self.x_edit)
        form.addRow("Y", self.y_edit)
        form.addRow("Floor", QLabel(str(point["floor"])))
        form.addRow("Kind", QLabel(str(point.get("kind", ""))))
        if point.get("kind") == "location":
            metrics = {}
            parent_obj = self.parent()
            if parent_obj and hasattr(parent_obj, "store"):
                metrics = parent_obj.store.location_bounding_box_metrics(point_name)

            length = float(metrics.get("length", 0.0))
            width = float(metrics.get("width", 0.0))
            area = float(metrics.get("area", 0.0))

            form.addRow("Bounding length", QLabel(f"{length:.3f} m"))
            form.addRow("Bounding width", QLabel(f"{width:.3f} m"))
            form.addRow("Bounding area", QLabel(f"{area:.3f} m²"))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            x = float(self.x_edit.text())
            y = float(self.y_edit.text())
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Name is required")
            self.result = {"name": name, "x": x, "y": y}
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid value", str(exc))


class EdgeConnectionsDialog(QDialog):
    columns = [
        ("from", "From", 180),
        ("from_floor", "From floor", 90),
        ("to", "To", 180),
        ("to_floor", "To floor", 90),
        ("cross_floor", "Cross-floor", 90),
    ]

    def __init__(self, parent, point_name, edges, on_delete):
        super().__init__(parent)
        self.setWindowTitle(f"Edge Connections - {point_name}")
        self.resize(760, 420)
        self.point_name = point_name
        self.edges = list(edges)
        self.on_delete = on_delete

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [heading for _key, heading, _width in self.columns]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        layout.addLayout(button_row)
        self.delete_btn = QPushButton("Delete selected")
        close_btn = QPushButton("Close")
        button_row.addWidget(self.delete_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)

        self.delete_btn.clicked.connect(self.delete_selected)
        close_btn.clicked.connect(self.accept)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for edge in self.edges:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                edge.get("from", ""),
                edge.get("from_floor", ""),
                edge.get("to", ""),
                edge.get("to_floor", ""),
                "Yes" if edge.get("cross_floor") else "No",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        count = len(self.edges)
        if count == 0:
            self.summary_label.setText(f"No edge connections for {self.point_name}")
            self.delete_btn.setEnabled(False)
        else:
            cross_count = sum(1 for edge in self.edges if edge.get("cross_floor"))
            self.summary_label.setText(
                f"{count} connection(s) for {self.point_name} ({cross_count} cross-floor)"
            )
            self.delete_btn.setEnabled(True)

    def delete_selected(self):
        rows = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )
        if not rows:
            QMessageBox.information(
                self, "Delete edges", "Select one or more edge connections first."
            )
            return
        selected_edges = [self.edges[row] for row in rows]
        if (
            QMessageBox.question(
                self,
                "Delete edges",
                f"Delete {len(selected_edges)} selected edge connection(s)?",
            )
            != QMessageBox.Yes
        ):
            return
        self.on_delete(selected_edges)
        for row in reversed(rows):
            del self.edges[row]
        self._refresh_table()


class LiftEditorDialog(QDialog):
    def __init__(
        self, parent, lift=None, default_floor=0, default_x=0.0, default_y=0.0
    ):
        super().__init__(parent)
        self.setWindowTitle("Lift Editor")
        self.result = None
        self.lift = lift or {}
        self.default_floor = int(default_floor)
        self.default_x = float(default_x)
        self.default_y = float(default_y)

        floors = self.lift.get("served_floors", [self.default_floor])
        self.existing_floor_locations = self._normalise_floor_locations(
            self.lift.get("floor_locations", {})
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        default_lift_id = self._suggest_next_lift_id()
        self.id_edit = QLineEdit(self.lift.get("id", default_lift_id))
        self.floors_edit = QLineEdit(", ".join(str(x) for x in floors))
        self.speed_edit = QLineEdit(str(self.lift.get("speed_floors_per_sec", 0.45)))
        self.door_edit = QLineEdit(str(self.lift.get("door_time_sec", 4)))
        self.board_edit = QLineEdit(str(self.lift.get("boarding_time_sec", 6)))
        self.capacity_length_edit = QLineEdit(
            str(self.lift.get("capacity_length_m", 1.0))
        )
        self.capacity_width_edit = QLineEdit(
            str(self.lift.get("capacity_width_m", 1.0))
        )
        self.capacity_height_edit = QLineEdit(
            str(self.lift.get("capacity_height_m", 2.0))
        )
        self.health_edit = QLineEdit(str(self.lift.get("health_percent", 100.0)))
        self.health_loss_edit = QLineEdit(
            str(self.lift.get("health_loss_per_journey_percent", 0.05))
        )
        self.mtbf_edit = QLineEdit(
            str(self.lift.get("mean_time_between_failures_hours", 720.0))
        )
        self.mttr_edit = QLineEdit(str(self.lift.get("mean_time_to_repair_hours", 4.0)))
        self.start_floor_edit = QLineEdit(
            str(self.lift.get("start_floor", self.default_floor))
        )

        self.positions_edit = QPlainTextEdit()
        self.positions_edit.setReadOnly(True)
        self.positions_edit.setToolTip(
            "Automatically generated from served floors. "
            "New floors use the clicked lift position."
        )

        form.addRow("Lift ID", self.id_edit)
        form.addRow("Served floors", self.floors_edit)
        form.addRow("Speed floors/sec", self.speed_edit)
        form.addRow("Door time sec", self.door_edit)
        form.addRow("Boarding time sec", self.board_edit)
        form.addRow("Capacity length m", self.capacity_length_edit)
        form.addRow("Capacity width m", self.capacity_width_edit)
        form.addRow("Capacity height m", self.capacity_height_edit)
        form.addRow("Health %", self.health_edit)
        form.addRow("Health loss per journey %", self.health_loss_edit)
        form.addRow("MTBF hours", self.mtbf_edit)
        form.addRow("MTTR hours", self.mttr_edit)
        form.addRow("Start floor", self.start_floor_edit)
        form.addRow("Auto per-floor positions", self.positions_edit)
        form.addRow(
            "",
            QLabel(
                "Generated automatically. Existing floor positions are kept; "
                "new floors use the clicked X/Y."
            ),
        )

        self.floors_edit.textChanged.connect(self._refresh_positions_preview)
        self._refresh_positions_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(520, 520)

    def _normalise_floor_locations(self, floor_locations):
        normalised = {}
        for key, value in (floor_locations or {}).items():
            try:
                floor = int(key)
                if isinstance(value, dict):
                    x = float(value.get("x", self.default_x))
                    y = float(value.get("y", self.default_y))
                else:
                    x = float(value[0])
                    y = float(value[1])
                normalised[floor] = (x, y)
            except Exception:
                continue
        return normalised

    def _parse_floors(self):
        floors = [
            int(x.strip()) for x in self.floors_edit.text().split(",") if x.strip()
        ]
        if not floors:
            raise ValueError("At least one served floor is required")
        return sorted(set(floors))

    def _build_floor_locations(self, floors):
        positions = {}
        for floor in floors:
            x, y = self.existing_floor_locations.get(
                floor,
                (self.default_x, self.default_y),
            )
            positions[floor] = (float(x), float(y))
        return positions

    def _refresh_positions_preview(self):
        try:
            floors = self._parse_floors()
            positions = self._build_floor_locations(floors)
            preview = {
                floor: [round(pos[0], 3), round(pos[1], 3)]
                for floor, pos in positions.items()
            }
            self.positions_edit.setPlainText(json.dumps(preview, indent=2))
        except Exception as exc:
            self.positions_edit.setPlainText(f"Invalid served floors: {exc}")

    def _suggest_next_lift_id(self):
        existing_ids = set()

        parent = self.parent()
        if parent and hasattr(parent, "store"):
            for lift in parent.store.data.get("lifts", []):
                lift_id = str(lift.get("id", "")).strip()
                if lift_id:
                    existing_ids.add(lift_id)

        nums = []
        for lift_id in existing_ids:
            upper = lift_id.upper()

            if upper.startswith("LIFT-"):
                tail = lift_id[5:]
            elif upper.startswith("LIFT"):
                tail = lift_id[4:]
            else:
                continue

            tail = tail.strip()

            if tail.isdigit():
                nums.append(int(tail))

        next_num = max(nums, default=0) + 1
        return f"Lift-{next_num}"

    def accept(self):
        try:
            lift_id = self.id_edit.text().strip()
            if not lift_id:
                raise ValueError("Lift ID is required")

            floors = self._parse_floors()
            start_floor = int(self.start_floor_edit.text())
            if start_floor not in floors:
                raise ValueError("Start floor must be one of the served floors")

            positions = self._build_floor_locations(floors)

            self.result = {
                "id": lift_id,
                "served_floors": floors,
                "speed_floors_per_sec": float(self.speed_edit.text()),
                "door_time_sec": float(self.door_edit.text()),
                "boarding_time_sec": float(self.board_edit.text()),
                "capacity_length_m": float(self.capacity_length_edit.text()),
                "capacity_width_m": float(self.capacity_width_edit.text()),
                "capacity_height_m": float(self.capacity_height_edit.text()),
                "health_percent": float(self.health_edit.text()),
                "health_loss_per_journey_percent": float(self.health_loss_edit.text()),
                "mean_time_between_failures_hours": float(self.mtbf_edit.text()),
                "mean_time_to_repair_hours": float(self.mttr_edit.text()),
                "start_floor": start_floor,
                "floor_locations": positions,
            }
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid lift", str(exc))


class AMREditorDialog(QDialog):
    def __init__(self, parent, location_names, seed=None, default_amr_id="AMR-1"):
        super().__init__(parent)
        self.setWindowTitle("AMR")
        self.result = None
        self.seed = seed or {}
        self.location_names = sorted(location_names)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.id_edit = QLineEdit(str(self.seed.get("id", default_amr_id)))
        self.quantity_edit = QLineEdit(str(self.seed.get("quantity", 1)))
        self.payload_capacity_edit = QLineEdit(
            str(self.seed.get("payload_capacity_kg", 100))
        )
        self.payload_length_edit = QLineEdit(
            str(self.seed.get("payload_length_capacity_m", 1.0))
        )
        self.payload_width_edit = QLineEdit(
            str(self.seed.get("payload_width_capacity_m", 1.0))
        )
        self.payload_height_edit = QLineEdit(
            str(self.seed.get("payload_height_capacity_m", 1.0))
        )
        self.amr_length_edit = QLineEdit(str(self.seed.get("length_m", 0.8)))
        self.amr_width_edit = QLineEdit(str(self.seed.get("width_m", 0.6)))
        self.amr_height_edit = QLineEdit(str(self.seed.get("height_m", 1.2)))
        self.speed_edit = QLineEdit(str(self.seed.get("speed_m_per_sec", 1.0)))
        self.motor_power_edit = QLineEdit(str(self.seed.get("motor_power_w", 250)))
        self.battery_capacity_edit = QLineEdit(
            str(self.seed.get("battery_capacity_kwh", 1.0))
        )
        self.charge_rate_edit = QLineEdit(
            str(self.seed.get("battery_charge_rate_kw", 0.5))
        )
        self.recharge_threshold_edit = QLineEdit(
            str(self.seed.get("recharge_threshold_percent", 20))
        )
        self.battery_soc_edit = QLineEdit(
            str(self.seed.get("battery_soc_percent", 100))
        )

        self.start_location_combo = QComboBox()
        self.start_location_combo.addItems([""] + self.location_names)
        self.start_location_combo.setCurrentText(
            str(self.seed.get("start_location", ""))
        )

        form.addRow("AMR ID", self.id_edit)
        form.addRow("Quantity", self.quantity_edit)
        form.addRow("Payload capacity kg", self.payload_capacity_edit)
        form.addRow("Payload length capacity m", self.payload_length_edit)
        form.addRow("Payload width capacity m", self.payload_width_edit)
        form.addRow("Payload height capacity m", self.payload_height_edit)
        form.addRow("AMR length m", self.amr_length_edit)
        form.addRow("AMR width m", self.amr_width_edit)
        form.addRow("AMR height m", self.amr_height_edit)
        form.addRow("Speed m/sec", self.speed_edit)
        form.addRow("Motor power W", self.motor_power_edit)
        form.addRow("Battery capacity kWh", self.battery_capacity_edit)
        form.addRow("Battery charge rate kW", self.charge_rate_edit)
        form.addRow("Recharge threshold %", self.recharge_threshold_edit)
        form.addRow("Battery SOC %", self.battery_soc_edit)
        form.addRow("Start location", self.start_location_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(520, 420)

    def accept(self):
        try:
            amr_id = self.id_edit.text().strip()
            if not amr_id:
                raise ValueError("AMR ID is required")

            self.result = {
                "id": amr_id,
                "quantity": int(float(self.quantity_edit.text())),
                "payload_capacity_kg": float(self.payload_capacity_edit.text()),
                "payload_length_capacity_m": float(self.payload_length_edit.text()),
                "payload_width_capacity_m": float(self.payload_width_edit.text()),
                "payload_height_capacity_m": float(self.payload_height_edit.text()),
                "length_m": float(self.amr_length_edit.text()),
                "width_m": float(self.amr_width_edit.text()),
                "height_m": float(self.amr_height_edit.text()),
                "speed_m_per_sec": float(self.speed_edit.text()),
                "motor_power_w": float(self.motor_power_edit.text()),
                "battery_capacity_kwh": float(self.battery_capacity_edit.text()),
                "battery_charge_rate_kw": float(self.charge_rate_edit.text()),
                "recharge_threshold_percent": float(
                    self.recharge_threshold_edit.text()
                ),
                "battery_soc_percent": float(self.battery_soc_edit.text()),
                "start_location": self.start_location_combo.currentText().strip(),
            }
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid AMR", str(exc))


class AMRListDialog(QDialog):
    columns = [
        ("id", "ID", 120),
        ("quantity", "Qty", 70),
        ("payload_capacity_kg", "Payload kg", 100),
        ("payload_length_capacity_m", "Length cap. m", 110),
        ("payload_width_capacity_m", "Width cap. m", 110),
        ("payload_height_capacity_m", "Height cap. m", 110),
        ("speed_m_per_sec", "Speed", 80),
        ("motor_power_w", "Motor W", 90),
        ("battery_capacity_kwh", "Battery kWh", 100),
        ("battery_charge_rate_kw", "Charge kW", 100),
        ("recharge_threshold_percent", "Recharge %", 100),
        ("battery_soc_percent", "SOC %", 80),
        ("start_location", "Start location", 160),
    ]

    def __init__(self, parent, items, location_names, on_save):
        super().__init__(parent)
        self.setWindowTitle("AMRs")
        self.resize(1200, 520)
        self.items = [dict(x) for x in items]
        self.location_names = list(location_names)
        self.on_save = on_save

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [heading for _key, heading, _width in self.columns]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.edit_item())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)

        layout.addWidget(self.table)

        row = QHBoxLayout()
        layout.addLayout(row)

        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        delete_btn = QPushButton("Delete")
        save_btn = QPushButton("Save")

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        delete_btn.clicked.connect(self.delete_item)
        save_btn.clicked.connect(self.save_items)

        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(delete_btn)
        row.addStretch(1)
        row.addWidget(save_btn)

        self._refresh_table()

    def _suggest_next_amr_id(self):
        nums = []
        for item in self.items:
            value = str(item.get("id", "")).strip().upper()
            if value.startswith("AMR-") and value[4:].isdigit():
                nums.append(int(value[4:]))
            elif value.startswith("AMR") and value[3:].isdigit():
                nums.append(int(value[3:]))
        return f"AMR-{max(nums, default=0) + 1}"

    def _refresh_table(self):
        self.table.setRowCount(0)
        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, (key, _heading, _width) in enumerate(self.columns):
                self.table.setItem(row, col, QTableWidgetItem(str(item.get(key, ""))))

    def add_item(self):
        dialog = AMREditorDialog(
            self,
            self.location_names,
            default_amr_id=self._suggest_next_amr_id(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            if any(x.get("id") == dialog.result["id"] for x in self.items):
                QMessageBox.critical(self, "Duplicate", "AMR ID already exists")
                return
            self.items.append(dialog.result)
            self._refresh_table()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return

        dialog = AMREditorDialog(self, self.location_names, seed=self.items[row])
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_id = dialog.result["id"]
            for idx, item in enumerate(self.items):
                if idx != row and item.get("id") == new_id:
                    QMessageBox.critical(self, "Duplicate", "AMR ID already exists")
                    return
            self.items[row] = dialog.result
            self._refresh_table()
            self.table.selectRow(row)

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        del self.items[row]
        self._refresh_table()

    def save_items(self):
        self.on_save(self.items)
        self.accept()


class TableListEditor(QMainWindow):
    def __init__(self, master, title, columns, items, on_save):
        super().__init__(master)
        self.setWindowTitle(title)
        self.resize(1100, 500)
        self.columns = columns
        self.items = items
        self.on_save = on_save

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([c[1] for c in columns])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for idx, (_, _, width) in enumerate(columns):
            self.table.setColumnWidth(idx, width)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        layout.addLayout(button_row)
        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        delete_btn = QPushButton("Delete")
        save_btn = QPushButton("Save")
        button_row.addWidget(add_btn)
        button_row.addWidget(edit_btn)
        button_row.addWidget(delete_btn)
        button_row.addStretch(1)
        button_row.addWidget(save_btn)

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        delete_btn.clicked.connect(self.delete_item)
        save_btn.clicked.connect(self.save)

        self._refresh_table()
        self.show()

    @staticmethod
    def stringify(value: Any) -> str:
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value)

    def parse_value(self, value: str):
        value = value.strip()
        if value.startswith("[") or value.startswith("{"):
            return json.loads(value)
        if value == "":
            return ""
        try:
            if "." in value:
                return float(value)
            return int(value)
        except Exception:
            return value

    def prompt_item(self, seed=None):
        seed = seed or {}
        result = {}
        for key, heading, _ in self.columns:
            value, ok = QInputDialog.getText(
                self,
                self.windowTitle(),
                heading,
                text=self.stringify(seed.get(key, "")),
            )
            if not ok:
                return None
            result[key] = self.parse_value(value)
        return result

    def _refresh_table(self):
        self.table.setRowCount(0)
        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, (key, _heading, _width) in enumerate(self.columns):
                self.table.setItem(
                    row, col, QTableWidgetItem(self.stringify(item.get(key, "")))
                )

    def add_item(self):
        item = self.prompt_item()
        if item is None:
            return
        self.items.append(item)
        self._refresh_table()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        updated = self.prompt_item(self.items[row])
        if updated is None:
            return
        self.items[row] = updated
        self._refresh_table()
        self.table.selectRow(row)

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        del self.items[row]
        self._refresh_table()

    def save(self):
        self.on_save(self.items)
        self.close()


class RouteProfilesEditor(QDialog):
    def __init__(self, master, profiles, point_names, lift_ids, on_save):
        super().__init__(master)
        QMessageBox.information(
            self,
            "Route Profiles",
            "This legacy editor is not used by the main window. Use RouteProfilesEditorV2 instead.",
        )
        self.on_save = on_save
        self.profiles = profiles


class WasteStreamEditorDialog(QDialog):
    def __init__(self, parent, payload_names, seed=None):
        super().__init__(parent)
        self.setWindowTitle("Waste Stream")
        self.result = None
        self.seed = seed or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_edit = QLineEdit(self.seed.get("name", "clinical"))
        self.payload_combo = QComboBox()
        self.payload_combo.addItems([""] + list(payload_names))
        self.payload_combo.setCurrentText(self.seed.get("payload", ""))

        self.container_capacity_edit = QLineEdit(
            str(self.seed.get("container_capacity_m3", 0.24))
        )
        self.full_threshold_edit = QLineEdit(
            str(self.seed.get("full_threshold_fraction", 0.8))
        )

        form.addRow("Waste stream name", self.name_edit)
        form.addRow("Container payload", self.payload_combo)
        form.addRow("Container capacity m3", self.container_capacity_edit)
        form.addRow("Full threshold", self.full_threshold_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Waste stream name is required")

            payload = self.payload_combo.currentText().strip()
            if not payload:
                raise ValueError("Container payload is required")

            container_capacity = float(self.container_capacity_edit.text())
            if container_capacity <= 0:
                raise ValueError("Container capacity must be greater than 0")

            threshold = float(self.full_threshold_edit.text())
            if not (0.0 < threshold <= 1.0):
                raise ValueError("Full threshold must be between 0 and 1")

            self.result = {
                "name": name,
                "payload": payload,
                "container_capacity_m3": container_capacity,
                "full_threshold_fraction": threshold,
            }
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid waste stream", str(exc))


class WasteStreamListDialog(QDialog):
    def __init__(self, parent, payload_names, items, on_save):
        super().__init__(parent)
        self.setWindowTitle("Waste Streams")
        self.resize(760, 420)
        self.payload_names = list(payload_names)
        self.items = [dict(x) for x in items]
        self.on_save = on_save

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                "Name",
                "Container payload",
                "Capacity m3",
                "Full threshold",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        layout.addLayout(row)

        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        del_btn = QPushButton("Delete")
        save_btn = QPushButton("Save")

        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        row.addWidget(save_btn)

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        del_btn.clicked.connect(self.delete_item)
        save_btn.clicked.connect(self.save_items)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("name", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("payload", ""))))
            self.table.setItem(
                row,
                2,
                QTableWidgetItem(str(item.get("container_capacity_m3", ""))),
            )
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(str(item.get("full_threshold_fraction", ""))),
            )

    def add_item(self):
        dialog = WasteStreamEditorDialog(self, self.payload_names)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            name = dialog.result["name"]
            if any(str(x.get("name", "")).strip() == name for x in self.items):
                QMessageBox.critical(self, "Duplicate", "Waste stream already exists")
                return
            self.items.append(dialog.result)
            self._refresh_table()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        dialog = WasteStreamEditorDialog(self, self.payload_names, self.items[row])
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_name = dialog.result["name"]
            for idx, item in enumerate(self.items):
                if idx != row and str(item.get("name", "")).strip() == new_name:
                    QMessageBox.critical(
                        self, "Duplicate", "Waste stream already exists"
                    )
                    return
            self.items[row] = dialog.result
            self._refresh_table()
            self.table.selectRow(row)

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        del self.items[row]
        self._refresh_table()

    def save_items(self):
        self.on_save(self.items)
        self.accept()


class DepartmentWasteStreamSettingsDialog(QDialog):
    MODES = [
        "scheduled",
        "threshold",
        "continuous",
        "sporadic",
        "hybrid",
        "scheduled_threshold",
        "scheduled_sporadic",
    ]

    def __init__(self, parent, waste_stream_names, items=None):
        super().__init__(parent)
        self.setWindowTitle("Department waste stream generation")
        self.resize(900, 520)

        self.waste_stream_names = list(waste_stream_names)
        self.items = [dict(x) for x in (items or [])]
        self.result = None

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Stream",
                "Mode",
                "Frequency/day",
                "Volume/event m³",
                "Threshold m³",
                "Base daily m³",
                "Scheduled times",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        layout.addLayout(row)

        add_btn = QPushButton("Add stream")
        edit_btn = QPushButton("Edit selected")
        delete_btn = QPushButton("Delete selected")

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        delete_btn.clicked.connect(self.delete_item)

        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(delete_btn)
        row.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh()

    def refresh(self):
        self.table.setRowCount(0)

        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                item.get("name", ""),
                item.get("generation_mode", "threshold"),
                item.get("frequency_per_day", 0.0),
                item.get("volume_per_event_m3", 0.0),
                item.get("threshold_volume_m3", 0.0),
                item.get("base_daily_volume_m3", 0.0),
                ", ".join(item.get("scheduled_times", [])),
            ]

            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def add_item(self):
        dialog = DepartmentWasteStreamItemDialog(
            self,
            self.waste_stream_names,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            name = dialog.result["name"]
            if any(x.get("name") == name for x in self.items):
                QMessageBox.critical(
                    self,
                    "Duplicate",
                    "This waste stream is already assigned to the department.",
                )
                return
            self.items.append(dialog.result)
            self.refresh()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return

        dialog = DepartmentWasteStreamItemDialog(
            self,
            self.waste_stream_names,
            seed=self.items[row],
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_name = dialog.result["name"]

            for idx, item in enumerate(self.items):
                if idx != row and item.get("name") == new_name:
                    QMessageBox.critical(
                        self,
                        "Duplicate",
                        "This waste stream is already assigned to the department.",
                    )
                    return

            self.items[row] = dialog.result
            self.refresh()
            self.table.selectRow(row)

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        del self.items[row]
        self.refresh()

    def accept(self):
        self.result = [dict(x) for x in self.items]
        super().accept()


class DepartmentWasteStreamItemDialog(QDialog):
    MODES = [
        "scheduled",
        "threshold",
        "continuous",
        "sporadic",
        "hybrid",
        "scheduled_threshold",
        "scheduled_sporadic",
    ]

    def __init__(self, parent, waste_stream_names, seed=None):
        super().__init__(parent)
        self.setWindowTitle("Waste stream generation settings")
        self.resize(520, 420)

        self.seed = seed or {}
        self.result = None
        self.scheduled_times = list(self.seed.get("scheduled_times", []))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_combo = QComboBox()
        self.name_combo.addItems([""] + list(waste_stream_names))
        self.name_combo.setCurrentText(str(self.seed.get("name", "")))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.mode_combo.setCurrentText(
            str(self.seed.get("generation_mode", "threshold"))
        )

        self.frequency_edit = QLineEdit(str(self.seed.get("frequency_per_day", 0.0)))
        self.volume_edit = QLineEdit(str(self.seed.get("volume_per_event_m3", 0.0)))
        self.threshold_edit = QLineEdit(str(self.seed.get("threshold_volume_m3", 0.0)))
        self.base_daily_edit = QLineEdit(
            str(self.seed.get("base_daily_volume_m3", 0.0))
        )

        schedule_row = QHBoxLayout()
        self.schedule_summary = QLabel()
        self.schedule_summary.setWordWrap(True)

        edit_times_btn = QPushButton("Edit times...")
        clear_times_btn = QPushButton("Clear")

        edit_times_btn.clicked.connect(self.edit_times)
        clear_times_btn.clicked.connect(self.clear_times)

        self.edit_times_btn = edit_times_btn
        self.clear_times_btn = clear_times_btn

        schedule_row.addWidget(self.schedule_summary, 1)
        schedule_row.addWidget(edit_times_btn)
        schedule_row.addWidget(clear_times_btn)

        form.addRow("Waste stream", self.name_combo)
        form.addRow("Generation mode", self.mode_combo)
        form.addRow("Frequency per day", self.frequency_edit)
        form.addRow("Volume per event m³", self.volume_edit)
        form.addRow("Threshold volume m³", self.threshold_edit)
        form.addRow("Base daily volume m³", self.base_daily_edit)
        form.addRow("Scheduled times", schedule_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.mode_combo.currentTextChanged.connect(self.update_field_state)

        self.refresh_schedule_summary()
        self.update_field_state()

    def edit_times(self):
        dialog = ScheduledTimesDialog(self, self.scheduled_times)
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.scheduled_times = list(dialog.result)
            self.refresh_schedule_summary()

    def clear_times(self):
        self.scheduled_times = []
        self.refresh_schedule_summary()

    def refresh_schedule_summary(self):
        if not self.scheduled_times:
            self.schedule_summary.setText("No times selected")
        elif len(self.scheduled_times) <= 6:
            self.schedule_summary.setText(", ".join(self.scheduled_times))
        else:
            self.schedule_summary.setText(f"{len(self.scheduled_times)} times selected")

    def update_field_state(self):
        mode = self.mode_combo.currentText().strip()

        uses_schedule = mode in {
            "scheduled",
            "scheduled_threshold",
            "scheduled_sporadic",
        }
        uses_threshold = mode in {
            "threshold",
            "hybrid",
            "scheduled_threshold",
        }
        uses_continuous = mode in {
            "continuous",
            "hybrid",
        }
        uses_sporadic = mode in {
            "sporadic",
            "hybrid",
            "scheduled_sporadic",
        }

        self.schedule_summary.setEnabled(uses_schedule)
        self.edit_times_btn.setEnabled(uses_schedule)
        self.clear_times_btn.setEnabled(uses_schedule)

        self.threshold_edit.setEnabled(uses_threshold)
        self.base_daily_edit.setEnabled(uses_continuous or uses_threshold)
        self.frequency_edit.setEnabled(uses_sporadic)
        self.volume_edit.setEnabled(uses_sporadic)

    def accept(self):
        try:
            name = self.name_combo.currentText().strip()
            if not name:
                raise ValueError("Waste stream is required")

            self.result = {
                "name": name,
                "generation_mode": self.mode_combo.currentText().strip(),
                "frequency_per_day": float(self.frequency_edit.text() or 0.0),
                "volume_per_event_m3": float(self.volume_edit.text() or 0.0),
                "threshold_volume_m3": float(self.threshold_edit.text() or 0.0),
                "base_daily_volume_m3": float(self.base_daily_edit.text() or 0.0),
                "scheduled_times": list(self.scheduled_times),
            }

            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid waste stream settings", str(exc))


class DepartmentEditorDialog(QDialog):
    DAYS = [
        ("mon", "Mon"),
        ("tue", "Tue"),
        ("wed", "Wed"),
        ("thu", "Thu"),
        ("fri", "Fri"),
        ("sat", "Sat"),
        ("sun", "Sun"),
    ]

    def __init__(
        self,
        parent,
        location_names,
        waste_stream_names,
        current_floor=0,
        seed=None,
        default_department_id="D1",
        group_resolver=None,
        default_x=0.0,
        default_y=0.0,
        task_generation_categories=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Department")
        self.result = None
        self.seed = seed or {}
        self.location_names = sorted(location_names)
        self.waste_stream_names = sorted(waste_stream_names)
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.task_generation_categories = list(task_generation_categories or [])
        self.category_location_selections = self._normalise_task_generation_locations()
        self.category_location_summaries = {}
        self.category_suffix_edits = {}
        self.category_place_location_buttons = {}
        self.category_pending_locations = {}

        self.selected_waste_streams = self._normalise_department_waste_streams(
            self.seed.get("waste_streams", [])
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.id_edit = QLineEdit(self.seed.get("id", default_department_id))
        self.name_edit = QLineEdit(self.seed.get("name", ""))
        self.floor_label = QLabel(str(int(self.seed.get("floor", current_floor))))
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(bool(self.seed.get("enabled", True)))

        self.bed_count_edit = QLineEdit(str(self.seed.get("bed_count", 0)))
        self.turnover_edit = QLineEdit(str(self.seed.get("patient_turnover", 0.0)))
        self.staff_count_edit = QLineEdit(str(self.seed.get("staff_count", 0)))
        self.hours_edit = QLineEdit(str(self.seed.get("hours_operated_per_day", 24)))

        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        active_days = set(
            self.seed.get("days_active", ["mon", "tue", "wed", "thu", "fri"])
        )
        self.day_checks = {}
        for key, label in self.DAYS:
            chk = QCheckBox(label)
            chk.setChecked(key in active_days)
            self.day_checks[key] = chk
            days_layout.addWidget(chk)

        waste_row = QHBoxLayout()
        self.waste_summary = QLabel("None selected")
        self.waste_summary.setWordWrap(True)
        waste_btn = QPushButton("Select...")
        waste_btn.clicked.connect(self._pick_waste_streams)
        waste_row.addWidget(self.waste_summary, 1)
        waste_row.addWidget(waste_btn)

        self.x_edit = QLineEdit(str(self.seed.get("x", default_x)))
        self.y_edit = QLineEdit(str(self.seed.get("y", default_y)))

        form.addRow("Department ID", self.id_edit)
        form.addRow("Department name", self.name_edit)
        form.addRow("Floor", self.floor_label)
        form.addRow("Status", self.enabled_check)
        form.addRow("Bed count", self.bed_count_edit)
        form.addRow("Patient turnover", self.turnover_edit)
        form.addRow("Staff count", self.staff_count_edit)
        form.addRow("Hours operated/day", self.hours_edit)
        form.addRow("Days active", days_widget)
        form.addRow("Assigned waste streams", waste_row)

        for (
            category_key,
            category_label,
            default_suffix,
        ) in self.task_generation_categories:
            row = QHBoxLayout()

            summary = QLabel("None selected")
            summary.setWordWrap(True)

            select_btn = QPushButton("Select...")
            select_btn.clicked.connect(
                lambda _=False, key=category_key: self._pick_category_locations(key)
            )

            suffix_edit = QLineEdit(
                str(
                    self.seed.get("task_generation_location_suffixes", {}).get(
                        category_key, default_suffix
                    )
                )
            )
            suffix_edit.setFixedWidth(90)

            place_btn = QPushButton("Place...")
            place_btn.setToolTip("Place location on the DXF/editor scene")
            place_btn.clicked.connect(
                lambda _=False, key=category_key: self._place_category_location(key)
            )

            row.addWidget(summary, 1)
            row.addWidget(select_btn)
            row.addWidget(QLabel("Suffix"))
            row.addWidget(suffix_edit)
            row.addWidget(place_btn)

            self.category_location_summaries[category_key] = summary
            self.category_suffix_edits[category_key] = suffix_edit
            self.category_place_location_buttons[category_key] = place_btn

            form.addRow(f"{category_label} pickup / drop-off", row)

        form.addRow("X", self.x_edit)
        form.addRow("Y", self.y_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_all_category_location_summaries()
        self._refresh_waste_summary()

    def _place_category_location(self, category_key):
        parent = self.parent()

        if parent is None or not hasattr(parent, "start_department_location_placement"):
            QMessageBox.critical(
                self,
                "Placement unavailable",
                "The editor does not support graphical location placement.",
            )
            return

        dept_id = self.id_edit.text().strip()
        if not dept_id:
            QMessageBox.critical(
                self, "Missing department ID", "Enter a department ID first."
            )
            return

        suffix = self.category_suffix_edits[category_key].text().strip()
        location_name = self._next_category_location_name(category_key)

        self.hide()

        parent.start_department_location_placement(
            location_name=location_name,
            category_key=category_key,
            callback=self._finish_category_location_placement,
            return_dialog=self,
        )

    def _finish_category_location_placement(self, category_key, location_payload):
        location_name = str(location_payload.get("name", "")).strip()
        if not location_name:
            self.show()
            self.raise_()
            self.activateWindow()
            return

        selected = self.category_location_selections.setdefault(category_key, [])
        if location_name not in selected:
            selected.append(location_name)
            selected.sort()

        if location_name not in self.location_names:
            self.location_names.append(location_name)
            self.location_names.sort()

        self._refresh_category_location_summary(category_key)

        self.show()
        self.raise_()
        self.activateWindow()

    def _next_category_location_name(self, category_key):
        dept_id = self.id_edit.text().strip()
        suffix = self.category_suffix_edits[category_key].text().strip()
        base_name = f"{dept_id}{suffix}"

        used = set(self.location_names)

        for locations in self.category_location_selections.values():
            used.update(str(x).strip() for x in locations if str(x).strip())

        if base_name not in used:
            return base_name

        counter = 2
        while True:
            candidate = f"{base_name}_{counter}"
            if candidate not in used:
                return candidate
            counter += 1

    def _normalise_task_generation_locations(self):
        result = {}

        existing = self.seed.get("task_generation_locations", {})
        if isinstance(existing, dict):
            for category_key, item in existing.items():
                if isinstance(item, dict):
                    locations = item.get(
                        "pickup_dropoff_locations", item.get("locations", [])
                    )
                else:
                    locations = item

                result[str(category_key)] = [
                    str(x).strip() for x in locations or [] if str(x).strip()
                ]

        return result

    def _refresh_category_location_summary(self, category_key):
        summary = self.category_location_summaries.get(category_key)
        if summary is None:
            return

        values = self.category_location_selections.get(category_key, [])
        if not values:
            summary.setText("None selected")
        elif len(values) <= 4:
            summary.setText(", ".join(values))
        else:
            summary.setText(f"{len(values)} selected")

    def _refresh_all_category_location_summaries(self):
        for category_key, *_ in self.task_generation_categories:
            self._refresh_category_location_summary(category_key)

    def _pick_category_locations(self, category_key):
        picker = MultiSelectPicker(
            self,
            "Select pickup / drop-off locations",
            self.location_names,
            selected=self.category_location_selections.get(category_key, []),
            group_resolver=self.group_resolver,
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.category_location_selections[category_key] = sorted(picker.result)
            self._refresh_category_location_summary(category_key)

    def _normalise_department_waste_streams(self, value):
        result = []

        for item in value or []:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                result.append(
                    {
                        "name": name,
                        "generation_mode": str(
                            item.get("generation_mode", "threshold")
                        ),
                        "frequency_per_day": float(item.get("frequency_per_day", 0.0)),
                        "volume_per_event_m3": float(
                            item.get("volume_per_event_m3", 0.0)
                        ),
                        "threshold_volume_m3": float(
                            item.get("threshold_volume_m3", 0.0)
                        ),
                        "base_daily_volume_m3": float(
                            item.get("base_daily_volume_m3", 0.0)
                        ),
                        "scheduled_times": list(item.get("scheduled_times", [])),
                    }
                )
            else:
                name = str(item).strip()
                if name:
                    result.append(
                        {
                            "name": name,
                            "generation_mode": "threshold",
                            "frequency_per_day": 0.0,
                            "volume_per_event_m3": 0.0,
                            "threshold_volume_m3": 0.0,
                            "base_daily_volume_m3": 0.0,
                            "scheduled_times": [],
                        }
                    )

        return result

    def _refresh_waste_summary(self):
        names = [
            str(x.get("name", "")).strip()
            for x in self.selected_waste_streams
            if str(x.get("name", "")).strip()
        ]

        if not names:
            self.waste_summary.setText("None selected")
        elif len(names) <= 4:
            self.waste_summary.setText(", ".join(names))
        else:
            self.waste_summary.setText(f"{len(names)} selected")

    def _pick_waste_streams(self):
        dialog = DepartmentWasteStreamSettingsDialog(
            self,
            self.waste_stream_names,
            self.selected_waste_streams,
        )

        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.selected_waste_streams = list(dialog.result)
            self._refresh_waste_summary()

    def _normalise_task_generation_locations(self):
        result = {}

        existing = self.seed.get("task_generation_locations", {})
        if isinstance(existing, dict):
            for category_key, item in existing.items():
                if isinstance(item, dict):
                    locations = item.get(
                        "pickup_dropoff_locations", item.get("locations", [])
                    )
                else:
                    locations = item

                result[str(category_key)] = [
                    str(x).strip() for x in (locations or []) if str(x).strip()
                ]

        # Legacy migration from old waste fields
        legacy = []

        for value in self.seed.get("waste_pickup_locations", []):
            text = str(value).strip()
            if text and text not in legacy:
                legacy.append(text)

        waste_cfg = self.seed.get("waste", {}) or {}
        for key in ["pickup_location", "dropoff_location"]:
            text = str(waste_cfg.get(key, "")).strip()
            if text and text not in legacy:
                legacy.append(text)

        if legacy and "waste" not in result:
            result["waste"] = legacy

        return result

    def _location_summary_text(self, locations):
        if not locations:
            return "None selected"
        if len(locations) <= 4:
            return ", ".join(locations)
        return f"{len(locations)} selected"

    def _refresh_category_location_summary(self, category_key):
        summary = self.category_location_summaries.get(category_key)
        if summary is None:
            return

        locations = self.category_location_selections.get(category_key, [])
        summary.setText(self._location_summary_text(locations))

    def _pick_category_locations(self, category_key):
        picker = MultiSelectPicker(
            self,
            "Select pickup / drop-off locations",
            self.location_names,
            selected=self.category_location_selections.get(category_key, []),
            group_resolver=self.group_resolver,
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.category_location_selections[category_key] = sorted(picker.result)
            self._refresh_category_location_summary(category_key)

    def accept(self):
        try:
            dept_id = self.id_edit.text().strip()
            name = self.name_edit.text().strip()
            if not dept_id:
                raise ValueError("Department ID is required")
            if not name:
                raise ValueError("Department name is required")

            days_active = [
                key for key, _ in self.DAYS if self.day_checks[key].isChecked()
            ]
            if not days_active:
                raise ValueError("Select at least one active day")

            dept_id = self.id_edit.text().strip()
            floor = int(self.floor_label.text())
            x = float(self.x_edit.text())
            y = float(self.y_edit.text())

            location_suffixes = {}

            for (
                category_key,
                _category_label,
                _default_suffix,
            ) in self.task_generation_categories:
                location_suffixes[category_key] = (
                    self.category_suffix_edits[category_key].text().strip()
                )

            create_locations = list(self.category_pending_locations.values())

            self.result = {
                "id": dept_id,
                "name": name,
                "floor": int(self.floor_label.text()),
                "enabled": self.enabled_check.isChecked(),
                "bed_count": int(float(self.bed_count_edit.text())),
                "patient_turnover": float(self.turnover_edit.text()),
                "staff_count": int(float(self.staff_count_edit.text())),
                "hours_operated_per_day": float(self.hours_edit.text()),
                "days_active": days_active,
                "waste_streams": [dict(x) for x in self.selected_waste_streams],
                "task_generation_locations": {
                    category_key: {
                        "pickup_dropoff_locations": [
                            str(x).strip()
                            for x in self.category_location_selections.get(
                                category_key, []
                            )
                            if str(x).strip()
                        ]
                    }
                    for category_key, *_ in self.task_generation_categories
                },
                "task_generation_location_suffixes": location_suffixes,
                "_create_locations": create_locations,
                "x": float(self.x_edit.text()),
                "y": float(self.y_edit.text()),
            }
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid department", str(exc))


class DepartmentListDialog(QDialog):

    def __init__(
        self,
        parent,
        items,
        location_names,
        waste_stream_names,
        current_floor,
        on_save,
        suggest_department_id,
        group_resolver=None,
        task_generation_categories=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Departments")
        self.resize(980, 520)
        self.items = [dict(x) for x in items]
        self.location_names = sorted(location_names)
        self.waste_stream_names = sorted(waste_stream_names)
        self.current_floor = int(current_floor)
        self.on_save = on_save
        self.suggest_department_id = suggest_department_id
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.task_generation_categories = list(task_generation_categories or [])

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Name",
                "Floor",
                "Enabled",
                "Beds",
                "Turnover",
                "Staff",
                "Waste streams",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        layout.addLayout(row)

        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        del_btn = QPushButton("Delete")
        save_btn = QPushButton("Save")

        auto_assign_btn = QPushButton("Auto assign locations")

        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(del_btn)
        row.addWidget(auto_assign_btn)
        row.addStretch(1)
        row.addWidget(save_btn)

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        del_btn.clicked.connect(self.delete_item)
        auto_assign_btn.clicked.connect(self.auto_assign_locations)
        save_btn.clicked.connect(self.save_items)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("name", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get("floor", ""))))
            self.table.setItem(
                row,
                3,
                QTableWidgetItem("Yes" if item.get("enabled", True) else "No"),
            )
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("bed_count", 0))))
            self.table.setItem(
                row,
                5,
                QTableWidgetItem(str(item.get("patient_turnover", 0.0))),
            )
            self.table.setItem(
                row,
                6,
                QTableWidgetItem(str(item.get("staff_count", 0))),
            )
            self.table.setItem(
                row,
                7,
                QTableWidgetItem(
                    ", ".join(
                        x.get("name", str(x)) if isinstance(x, dict) else str(x)
                        for x in item.get("waste_streams", [])
                    )
                ),
            )

    def auto_assign_locations(self):
        if not self.task_generation_categories:
            QMessageBox.information(
                self,
                "Auto assign locations",
                "No task generation categories are available.",
            )
            return

        location_set = {str(x).strip() for x in self.location_names if str(x).strip()}
        assigned_count = 0
        kept_count = 0

        for dept in self.items:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                continue

            suffixes = dept.setdefault("task_generation_location_suffixes", {})
            category_locations = dept.setdefault("task_generation_locations", {})

            for (
                category_key,
                _category_label,
                default_suffix,
            ) in self.task_generation_categories:
                suffix = str(suffixes.get(category_key, default_suffix)).strip()
                expected_prefix = f"{dept_id}{suffix}"

                matching_locations = sorted(
                    name
                    for name in location_set
                    if name == expected_prefix or name.startswith(f"{expected_prefix}_")
                )

                if not matching_locations:
                    continue

                entry = category_locations.setdefault(category_key, {})
                selected = entry.setdefault("pickup_dropoff_locations", [])

                existing = {str(x).strip() for x in selected if str(x).strip()}

                kept_count += len(existing)

                for location_name in matching_locations:
                    if location_name not in existing:
                        selected.append(location_name)
                        existing.add(location_name)
                        assigned_count += 1

        self._refresh_table()

        QMessageBox.information(
            self,
            "Auto assign locations",
            (
                f"Assigned {assigned_count} location reference(s).\n"
                f"Kept {kept_count} existing assigned location reference(s)."
            ),
        )

    def add_item(self):
        dialog = DepartmentEditorDialog(
            self,
            location_names=self.location_names,
            waste_stream_names=self.waste_stream_names,
            current_floor=self.current_floor,
            default_department_id=self.suggest_department_id(),
            group_resolver=self.group_resolver,
            task_generation_categories=self.task_generation_categories,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_id = str(dialog.result.get("id", "")).strip()
            new_name = str(dialog.result.get("name", "")).strip()

            for item in self.items:
                if str(item.get("id", "")).strip() == new_id:
                    QMessageBox.critical(
                        self, "Duplicate", "Department ID already exists"
                    )
                    return
                if str(item.get("name", "")).strip() == new_name:
                    QMessageBox.critical(
                        self, "Duplicate", "Department name already exists"
                    )
                    return

            self.items.append(dialog.result)
            self._refresh_table()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        dialog = DepartmentEditorDialog(
            self,
            location_names=self.location_names,
            waste_stream_names=self.waste_stream_names,
            current_floor=self.current_floor,
            seed=self.items[row],
            default_department_id=str(self.items[row].get("id", "")),
            group_resolver=self.group_resolver,
            default_x=float(self.items[row].get("x", 0.0)),
            default_y=float(self.items[row].get("y", 0.0)),
            task_generation_categories=self.task_generation_categories,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_id = str(dialog.result.get("id", "")).strip()
            new_name = str(dialog.result.get("name", "")).strip()

            for idx, item in enumerate(self.items):
                if idx == row:
                    continue
                if str(item.get("id", "")).strip() == new_id:
                    QMessageBox.critical(
                        self, "Duplicate", "Department ID already exists"
                    )
                    return
                if str(item.get("name", "")).strip() == new_name:
                    QMessageBox.critical(
                        self, "Duplicate", "Department name already exists"
                    )
                    return

            self.items[row] = dialog.result
            self._refresh_table()
            self.table.selectRow(row)

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0:
            return
        del self.items[row]
        self._refresh_table()

    def save_items(self):
        self.on_save(self.items)
        self.accept()


class ZoomableInventoryView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._middle_panning = False
        self._last_middle_pos = None
        self._inventory_mouse_press = None
        self._inventory_mouse_move = None
        self._inventory_mouse_release = None
        self.setDragMode(QGraphicsView.NoDrag)

    def set_inventory_mouse_handlers(self, press, move, release):
        self._inventory_mouse_press = press
        self._inventory_mouse_move = move
        self._inventory_mouse_release = release

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._middle_panning = True
            self._last_middle_pos = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if self._inventory_mouse_press:
            self._inventory_mouse_press(event)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._middle_panning and self._last_middle_pos is not None:
            current = event.position().toPoint()
            delta = current - self._last_middle_pos

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )

            self._last_middle_pos = current
            event.accept()
            return

        if self._inventory_mouse_move:
            self._inventory_mouse_move(event)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._middle_panning = False
            self._last_middle_pos = None
            self.viewport().unsetCursor()
            event.accept()
            return

        if self._inventory_mouse_release:
            self._inventory_mouse_release(event)
            return

        super().mouseReleaseEvent(event)


class InventorySpacesDialog(QDialog):
    def __init__(self, parent, location_name):
        super().__init__(parent)
        self.setWindowTitle(f"Inventory Spaces - {location_name}")
        self.resize(900, 650)

        self.location_name = location_name
        self.store = parent.store
        self.editor = parent
        self._dxf_background_pixmap = None
        self._dxf_background_rect = None
        self.location = self.store.get_location(location_name)
        self.spaces = self.store.get_location_inventory_spaces(location_name)

        self.current_points = []
        self.selected_space_index = None
        self.drag_point_index = None
        self.drag_whole_space = False
        self.drag_start_world = None
        self.drag_start_points = []
        self.copied_space = None
        self._initial_fit_done = False

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        layout.addLayout(left, 0)

        self.space_list = QListWidget()
        self.space_list.currentRowChanged.connect(self.select_space)
        self.space_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.space_list.customContextMenuRequested.connect(self._show_space_list_menu)

        left.addWidget(QLabel("Inventory spaces"))
        left.addWidget(self.space_list, 1)

        add_btn = QPushButton("New space")
        save_btn = QPushButton("Save current")
        copy_btn = QPushButton("Copy selected")
        paste_btn = QPushButton("Paste copy")
        delete_btn = QPushButton("Delete selected")
        finish_btn = QPushButton("Save and close")

        add_btn.clicked.connect(self.new_space)
        save_btn.clicked.connect(self.save_current_space)
        copy_btn.clicked.connect(self.copy_selected_space)
        paste_btn.clicked.connect(self.paste_copied_space)
        delete_btn.clicked.connect(self.delete_selected_space)
        finish_btn.clicked.connect(self.finish)

        left.addWidget(add_btn)
        left.addWidget(save_btn)
        left.addWidget(copy_btn)
        left.addWidget(paste_btn)
        left.addWidget(delete_btn)
        left.addStretch(1)
        left.addWidget(finish_btn)

        right = QVBoxLayout()
        layout.addLayout(right, 1)

        self.name_edit = QLineEdit()
        right.addWidget(QLabel("Space name"))
        right.addWidget(self.name_edit)

        self.rectangle_snap_check = QCheckBox("Rectangular snap")
        self.rectangle_snap_check.setChecked(True)
        right.addWidget(self.rectangle_snap_check)

        size_row = QHBoxLayout()

        self.length_edit = QLineEdit("0.000")
        self.width_edit = QLineEdit("0.000")
        self.lock_size_check = QCheckBox("Lock size")

        self.length_edit.editingFinished.connect(self._apply_size_from_fields)
        self.width_edit.editingFinished.connect(self._apply_size_from_fields)

        size_row.addWidget(QLabel("Length"))
        size_row.addWidget(self.length_edit)
        size_row.addWidget(QLabel("Width"))
        size_row.addWidget(self.width_edit)
        size_row.addWidget(self.lock_size_check)

        right.addLayout(size_row)

        self.scene = QGraphicsScene(self)
        self.view = ZoomableInventoryView(self.scene)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setRenderHint(self.view.renderHints())
        self.view.setMouseTracking(True)
        self.view.set_inventory_mouse_handlers(
            self._mouse_press,
            self._mouse_move,
            self._mouse_release,
        )
        right.addWidget(self.view, 1)

        self.status_label = QLabel(
            "Left-click to add points. Drag yellow points to edit. Right-click a point to remove it."
        )
        right.addWidget(self.status_label)

        self.refresh_list()
        self.refresh_scene()

    def _apply_size_from_fields(self):
        if len(self.current_points) != 4:
            return

        try:
            new_length = float(self.length_edit.text())
            new_width = float(self.width_edit.text())
        except ValueError:
            self._refresh_size_fields()
            return

        if new_length <= 0 or new_width <= 0:
            self._refresh_size_fields()
            return

        xs = [float(p["x"]) for p in self.current_points]
        ys = [float(p["y"]) for p in self.current_points]

        min_x = min(xs)
        min_y = min(ys)

        self.current_points = [
            {"x": round(min_x, 3), "y": round(min_y, 3)},
            {"x": round(min_x + new_length, 3), "y": round(min_y, 3)},
            {"x": round(min_x + new_length, 3), "y": round(min_y + new_width, 3)},
            {"x": round(min_x, 3), "y": round(min_y + new_width, 3)},
        ]

        self.refresh_scene()

    def _show_space_list_menu(self, pos):
        row = self.space_list.row(self.space_list.itemAt(pos))
        if row >= 0:
            self.space_list.setCurrentRow(row)

        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        delete_action = menu.addAction("Delete")

        copy_action.setEnabled(self.space_list.currentRow() >= 0)
        paste_action.setEnabled(self.copied_space is not None)
        delete_action.setEnabled(self.space_list.currentRow() >= 0)

        action = menu.exec(self.space_list.viewport().mapToGlobal(pos))

        if action == copy_action:
            self.copy_selected_space()
        elif action == paste_action:
            self.paste_copied_space()
        elif action == delete_action:
            self.delete_selected_space()

    def _current_size(self):
        if not self.current_points:
            return 0.0, 0.0

        xs = [float(p["x"]) for p in self.current_points]
        ys = [float(p["y"]) for p in self.current_points]

        length = max(xs) - min(xs)
        width = max(ys) - min(ys)

        return round(length, 3), round(width, 3)

    def _refresh_size_fields(self):
        length, width = self._current_size()
        self.length_edit.setText(f"{length:.3f}")
        self.width_edit.setText(f"{width:.3f}")

    def _point_inside_current_space(self, x, y):
        if len(self.current_points) < 3:
            return False

        inside = False
        points = self.current_points
        j = len(points) - 1

        for i in range(len(points)):
            xi = float(points[i]["x"])
            yi = float(points[i]["y"])
            xj = float(points[j]["x"])
            yj = float(points[j]["y"])

            intersects = ((yi > y) != (yj > y)) and (
                x < ((xj - xi) * (y - yi) / ((yj - yi) or 1e-9)) + xi
            )

            if intersects:
                inside = not inside

            j = i

        return inside

    def refresh_list(self):
        self.space_list.blockSignals(True)
        self.space_list.clear()
        for space in self.spaces:
            self.space_list.addItem(space.get("name", "Inventory space"))
        self.space_list.blockSignals(False)

    def select_space(self, row):
        if row < 0 or row >= len(self.spaces):
            return

        self.selected_space_index = row
        space = self.spaces[row]
        self.name_edit.setText(space.get("name", ""))

        self.current_points = self.store.inventory_space_points_absolute(
            self.location_name,
            space,
        )

        self.refresh_scene()

    def new_space(self):
        self.selected_space_index = None
        self.name_edit.setText(f"Inventory {len(self.spaces) + 1}")
        self.current_points = []
        self.refresh_scene()

    def save_current_space(self):
        name = self.name_edit.text().strip() or f"Inventory {len(self.spaces) + 1}"

        if len(self.current_points) < 3:
            QMessageBox.critical(
                self,
                "Invalid inventory space",
                "Draw at least three points for an inventory space.",
            )
            return

        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))

        payload = {
            "name": name,
            "points": [
                {
                    "dx": round(float(p["x"]) - lx, 3),
                    "dy": round(float(p["y"]) - ly, 3),
                }
                for p in self.current_points
            ],
        }

        if self.selected_space_index is None:
            self.spaces.append(payload)
            self.selected_space_index = len(self.spaces) - 1
        else:
            self.spaces[self.selected_space_index] = payload

        self.refresh_list()
        self.space_list.setCurrentRow(self.selected_space_index)
        self.refresh_scene()

    def delete_selected_space(self):
        row = self.space_list.currentRow()
        if row < 0 or row >= len(self.spaces):
            return

        del self.spaces[row]
        self.selected_space_index = None
        self.current_points = []
        self.name_edit.clear()
        self.refresh_list()
        self.refresh_scene()

    def finish(self):
        self.store.set_location_inventory_spaces(self.location_name, self.spaces)
        self.accept()

    def world_to_scene(self, x, y):
        return QPointF(float(x), -float(y))

    def scene_to_world(self, point):
        return float(point.x()), -float(point.y())

    def _apply_rectangle_snap(self, moving_index=None):
        if not self.rectangle_snap_check.isChecked():
            return

        if len(self.current_points) != 4:
            return

        if moving_index is None or moving_index < 0 or moving_index >= 4:
            xs = [float(p["x"]) for p in self.current_points]
            ys = [float(p["y"]) for p in self.current_points]

            min_x = round(min(xs), 3)
            max_x = round(max(xs), 3)
            min_y = round(min(ys), 3)
            max_y = round(max(ys), 3)

            self.current_points = [
                {"x": min_x, "y": min_y},
                {"x": max_x, "y": min_y},
                {"x": max_x, "y": max_y},
                {"x": min_x, "y": max_y},
            ]
            return

        p = self.current_points[moving_index]
        opposite_index = (moving_index + 2) % 4
        opposite = self.current_points[opposite_index]

        x1 = round(float(p["x"]), 3)
        y1 = round(float(p["y"]), 3)
        x2 = round(float(opposite["x"]), 3)
        y2 = round(float(opposite["y"]), 3)

        self.current_points = [
            {"x": x1, "y": y1},
            {"x": x2, "y": y1},
            {"x": x2, "y": y2},
            {"x": x1, "y": y2},
        ]

        if moving_index == 1:
            self.current_points = [
                {"x": x2, "y": y1},
                {"x": x1, "y": y1},
                {"x": x1, "y": y2},
                {"x": x2, "y": y2},
            ]
        elif moving_index == 2:
            self.current_points = [
                {"x": x2, "y": y2},
                {"x": x1, "y": y2},
                {"x": x1, "y": y1},
                {"x": x2, "y": y1},
            ]
        elif moving_index == 3:
            self.current_points = [
                {"x": x1, "y": y2},
                {"x": x2, "y": y2},
                {"x": x2, "y": y1},
                {"x": x1, "y": y1},
            ]

    def _nearest_current_point(self, x, y, radius=0.5):
        best = None
        best_dist = radius

        for idx, p in enumerate(self.current_points):
            d = ((float(p["x"]) - x) ** 2 + (float(p["y"]) - y) ** 2) ** 0.5
            if d <= best_dist:
                best = idx
                best_dist = d

        return best

    def _mouse_press(self, event):
        scene_pos = self.view.mapToScene(event.position().toPoint())
        x, y = self.scene_to_world(scene_pos)

        hit = self._nearest_current_point(x, y)

        if event.button() == Qt.RightButton:
            if hit is not None:
                self.current_points.pop(hit)
                self.refresh_scene()
            return

        if event.button() == Qt.LeftButton:
            if hit is not None and not self.lock_size_check.isChecked():
                self.drag_point_index = hit
                return

            if self.lock_size_check.isChecked() and self._point_inside_current_space(
                x, y
            ):
                self.drag_whole_space = True
                self.drag_start_world = {"x": x, "y": y}
                self.drag_start_points = [dict(p) for p in self.current_points]
                return

            if self.lock_size_check.isChecked():
                return

            self.current_points.append(
                {
                    "x": round(x, 3),
                    "y": round(y, 3),
                }
            )
            self._apply_rectangle_snap()
            self.refresh_scene()

    def _mouse_move(self, event):
        scene_pos = self.view.mapToScene(event.position().toPoint())
        x, y = self.scene_to_world(scene_pos)

        if self.drag_whole_space and self.drag_start_world is not None:
            dx = round(x - float(self.drag_start_world["x"]), 3)
            dy = round(y - float(self.drag_start_world["y"]), 3)

            self.current_points = [
                {
                    "x": round(float(p["x"]) + dx, 3),
                    "y": round(float(p["y"]) + dy, 3),
                }
                for p in self.drag_start_points
            ]

            self.refresh_scene()
            return

        if self.drag_point_index is None:
            return

        if 0 <= self.drag_point_index < len(self.current_points):
            self.current_points[self.drag_point_index] = {
                "x": round(x, 3),
                "y": round(y, 3),
            }
            self._apply_rectangle_snap(self.drag_point_index)
            self.refresh_scene()

    def _mouse_release(self, event):
        self.drag_point_index = None
        self.drag_whole_space = False
        self.drag_start_world = None
        self.drag_start_points = []

    def _location_box_scene_rect(self):
        location_box = self.store.get_location_bounding_box_points(self.location_name)

        if not location_box:
            return None

        pts = [self.world_to_scene(p["x"], p["y"]) for p in location_box]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]

        return QRectF(
            min(xs),
            min(ys),
            max(xs) - min(xs),
            max(ys) - min(ys),
        )

    def copy_selected_space(self):
        row = self.space_list.currentRow()
        if row < 0 or row >= len(self.spaces):
            return

        self.copied_space = {
            "name": self.spaces[row].get("name", "Inventory space"),
            "points": [dict(p) for p in self.spaces[row].get("points", [])],
        }

        self.status_label.setText(f"Copied {self.copied_space['name']}")

    def paste_copied_space(self):
        if not self.copied_space:
            return

        pasted = {
            "name": f"{self.copied_space.get('name', 'Inventory space')} copy",
            "points": [dict(p) for p in self.copied_space.get("points", [])],
        }

        # Small offset so pasted space is visible and selectable separately
        for p in pasted["points"]:
            p["dx"] = round(float(p.get("dx", 0.0)) + 0.25, 3)
            p["dy"] = round(float(p.get("dy", 0.0)) + 0.25, 3)

        self.spaces.append(pasted)
        self.selected_space_index = len(self.spaces) - 1
        self.refresh_list()
        self.space_list.setCurrentRow(self.selected_space_index)
        self.select_space(self.selected_space_index)
        self.refresh_scene()

    def _draw_dxf_background(self):
        if not self.location:
            return

        editor = getattr(self, "editor", None)
        if editor is None:
            return

        floor = int(self.location.get("floor", 0))

        if getattr(editor, "loaded_dxf_floor", None) != floor:
            editor.ensure_floor_dxf_loaded(floor)

        if getattr(editor, "loaded_dxf_floor", None) != floor:
            return

        dxf_scene = getattr(editor, "dxf_scene", None)
        if dxf_scene is None or not dxf_scene.entities:
            return

        view_rect = self._location_box_scene_rect()
        if view_rect is None or view_rect.isNull():
            return

        world_rect = QRectF(
            view_rect.left(),
            -view_rect.bottom(),
            view_rect.width(),
            view_rect.height(),
        ).adjusted(-1.0, -1.0, 1.0, 1.0)

        line_path = QPainterPath()
        poly_path = QPainterPath()
        arc_path = QPainterPath()

        for entity in dxf_scene.entities:
            bbox = entity.get("bbox")
            if bbox:
                min_x, min_y, max_x, max_y = bbox
                if (
                    max_x < world_rect.left()
                    or min_x > world_rect.right()
                    or max_y < world_rect.top()
                    or min_y > world_rect.bottom()
                ):
                    continue

            etype = entity.get("type")

            if etype == "LINE":
                x1, y1 = entity["start"]
                x2, y2 = entity["end"]
                line_path.moveTo(x1, -y1)
                line_path.lineTo(x2, -y2)

            elif etype == "POLYLINE":
                pts = [QPointF(x, -y) for x, y in entity.get("points", [])]
                if len(pts) >= 2:
                    poly_path.moveTo(pts[0])
                    for pt in pts[1:]:
                        poly_path.lineTo(pt)
                    if entity.get("closed"):
                        poly_path.closeSubpath()

            elif etype == "CIRCLE":
                cx, cy = entity["center"]
                r = float(entity["radius"])
                arc_path.addEllipse(QRectF(cx - r, -(cy + r), r * 2, r * 2))

            elif etype == "ARC":
                cx, cy = entity["center"]
                r = float(entity["radius"])
                start_angle = float(entity.get("start_angle", 0.0))
                end_angle = float(entity.get("end_angle", 0.0))
                span_angle = end_angle - start_angle
                if span_angle <= 0:
                    span_angle += 360.0

                rect = QRectF(cx - r, -(cy + r), r * 2, r * 2)
                arc_path.arcMoveTo(rect, -start_angle)
                arc_path.arcTo(rect, -start_angle, -span_angle)

        for path, colour in [
            (line_path, "#777777"),
            (poly_path, "#999999"),
            (arc_path, "#777777"),
        ]:
            if path.isEmpty():
                continue

            item = QGraphicsPathItem(path)
            item.setPen(QPen(QColor(colour), 0))
            item.setBrush(Qt.NoBrush)
            item.setZValue(-100)
            item.setOpacity(0.45)
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
            self.scene.addItem(item)

    def refresh_scene(self):
        self.scene.clear()
        self._draw_dxf_background()

        location_box = self.store.get_location_bounding_box_points(self.location_name)

        if location_box:
            pts = [self.world_to_scene(p["x"], p["y"]) for p in location_box]
            poly = QGraphicsPolygonItem(QPolygonF(pts))
            poly.setPen(QPen(QColor("#18c37e"), 0.08))
            poly.setBrush(QBrush(QColor(24, 195, 126, 35)))
            self.scene.addItem(poly)

        for idx, space in enumerate(self.spaces):
            if idx == self.selected_space_index:
                continue

            pts_abs = self.store.inventory_space_points_absolute(
                self.location_name,
                space,
            )
            if len(pts_abs) < 3:
                continue

            pts = [self.world_to_scene(p["x"], p["y"]) for p in pts_abs]
            poly = QGraphicsPolygonItem(QPolygonF(pts))
            poly.setPen(QPen(QColor("#6aa9ff"), 0.05))
            poly.setBrush(QBrush(QColor(106, 169, 255, 45)))
            poly.setZValue(-10)
            self.scene.addItem(poly)

            label = QGraphicsSimpleTextItem(space.get("name", "Inventory"))
            label.setBrush(QBrush(QColor("#bcd7ff")))
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            label.setPos(pts[0])
            self.scene.addItem(label)

        if self.current_points:
            pts = [self.world_to_scene(p["x"], p["y"]) for p in self.current_points]

            if len(pts) >= 3:
                poly = QGraphicsPolygonItem(QPolygonF(pts))
                poly.setPen(QPen(QColor("#ffdd57"), 0.08))
                poly.setBrush(QBrush(QColor(255, 221, 87, 55)))
                self.scene.addItem(poly)

            for idx, pt in enumerate(pts):
                handle = self.scene.addEllipse(
                    pt.x() - 0.18,
                    pt.y() - 0.18,
                    0.36,
                    0.36,
                    QPen(QColor("#ffffff"), 0),
                    QBrush(QColor("#ffdd57")),
                )
                handle.setZValue(10)

        base_rect = self._location_box_scene_rect()

        if base_rect is None:
            base_rect = self.scene.itemsBoundingRect()

        if not base_rect.isNull():
            padded = base_rect.adjusted(-2, -2, 2, 2)
            self.scene.setSceneRect(padded)

            if not self._initial_fit_done:
                self.view.fitInView(padded, Qt.KeepAspectRatio)
                self._initial_fit_done = True

        self._refresh_size_fields()
