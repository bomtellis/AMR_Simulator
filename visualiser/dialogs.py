import json
import math
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
    QTreeWidget,
    QTreeWidgetItem,
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


class BulkDepartmentTaskGenerationDialog(QDialog):
    DAYS = (
        TaskGenerationSettingsDialog.DAYS
        if "TaskGenerationSettingsDialog" in globals()
        else [
            ("mon", "Mon"),
            ("tue", "Tue"),
            ("wed", "Wed"),
            ("thu", "Thu"),
            ("fri", "Fri"),
            ("sat", "Sat"),
            ("sun", "Sun"),
        ]
    )

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
        category_key,
        category_label,
        departments,
        base_category,
        location_names,
        payload_names,
        profile_names,
        selected_department_ids=None,
        result_key="",
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Configure multiple departments - {category_label}")
        self.resize(920, 720)

        self.category_key = category_key
        self.departments = [dict(x) for x in departments or []]
        self.base_category = dict(base_category or {})
        self.location_names = sorted(location_names)
        self.payload_names = list(payload_names)
        self.profile_names = list(profile_names)
        self.result = None
        self.result_key = str(result_key or "").strip()
        self.selected_department_ids = list(selected_department_ids or [])
        self.department_location_role = "dropoff"
        self.department_location_role = str(
            self.base_category.get(
                "department_location_role", self.department_location_role
            )
        )
        self.selected_pickup_locations = []
        self.selected_dropoffs = list(self.base_category.get("dropoff_locations", []))
        self.scheduled_times = list(self.base_category.get("scheduled_times", []))

        # In the bulk/multiple department configuration dialog, only departments
        # with an existing assigned location for the selected category are valid.
        # This prevents applying generation settings to departments where the
        # category has not yet been placed/assigned in the Department editor.
        self.selected_department_ids = [
            dept_id
            for dept_id in self.selected_department_ids
            if self._department_has_assigned_category_location_by_id(dept_id)
        ]

        layout = QVBoxLayout(self)

        dept_row = QHBoxLayout()
        self.department_summary = QLabel("No departments selected")
        self.department_summary.setWordWrap(True)
        pick_depts_btn = QPushButton("Select departments...")
        pick_depts_btn.clicked.connect(self.pick_departments)
        dept_row.addWidget(self.department_summary, 1)
        dept_row.addWidget(pick_depts_btn)
        layout.addLayout(dept_row)

        role_row = QHBoxLayout()
        layout.addLayout(role_row)

        self.role_pickup_radio = QCheckBox("Use department locations as pickup/source")
        self.role_dropoff_radio = QCheckBox("Use department locations as drop-off")
        self.role_pickup_radio.setChecked(self.department_location_role == "pickup")
        self.role_dropoff_radio.setChecked(self.department_location_role != "pickup")

        self.role_pickup_radio.toggled.connect(
            lambda checked: self.set_department_location_role("pickup", checked)
        )
        self.role_dropoff_radio.toggled.connect(
            lambda checked: self.set_department_location_role("dropoff", checked)
        )

        role_row.addWidget(self.role_pickup_radio)
        role_row.addWidget(self.role_dropoff_radio)
        role_row.addStretch(1)

        form = QFormLayout()
        layout.addLayout(form)

        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(bool(self.base_category.get("enabled", False)))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.mode_combo.setCurrentText(
            str(self.base_category.get("generation_mode", "scheduled"))
        )

        self.priority_edit = QLineEdit(str(self.base_category.get("priority", 100)))

        legacy_pickup = str(self.base_category.get("pickup_location", "")).strip()
        self.selected_pickup_locations = [legacy_pickup] if legacy_pickup else []

        pickup_row = QHBoxLayout()
        self.pickup_summary = QLabel("None selected")
        self.pickup_summary.setWordWrap(True)

        self.pick_pickups_btn = QPushButton("Select...")
        self.pick_pickups_btn.clicked.connect(self.pick_pickups)

        self.clear_pickups_btn = QPushButton("Clear")
        self.clear_pickups_btn.clicked.connect(self.clear_pickups)

        pickup_row.addWidget(self.pickup_summary, 1)
        pickup_row.addWidget(self.pick_pickups_btn)
        pickup_row.addWidget(self.clear_pickups_btn)

        dropoff_row = QHBoxLayout()
        self.dropoff_summary = QLabel()
        self.dropoff_summary.setWordWrap(True)

        self.pick_dropoffs_btn = QPushButton("Select...")
        self.pick_dropoffs_btn.clicked.connect(self.pick_dropoffs)

        self.clear_dropoffs_btn = QPushButton("Clear")
        self.clear_dropoffs_btn.clicked.connect(self.clear_dropoffs)

        dropoff_row.addWidget(self.dropoff_summary, 1)
        dropoff_row.addWidget(self.pick_dropoffs_btn)
        dropoff_row.addWidget(self.clear_dropoffs_btn)

        self.payload_combo = QComboBox()
        self.payload_combo.addItems([""] + self.payload_names)
        self.payload_combo.setCurrentText(str(self.base_category.get("payload", "")))

        self.tracked_item_exchange_check = QCheckBox(
            "Generate tracked item exchange tasks"
        )
        self.tracked_item_exchange_check.setChecked(
            bool(self.base_category.get("tracked_item_exchange", False))
        )

        self.exchange_mode_combo = QComboBox()
        self.exchange_mode_combo.addItems(
            [
                "full_exchange",
                "top_up_only",
                "replace_empty",
            ]
        )
        self.exchange_mode_combo.setCurrentText(
            str(self.base_category.get("exchange_mode", "top_up_only"))
        )

        self.route_profile_combo = QComboBox()
        self.route_profile_combo.addItems([""] + self.profile_names)
        self.route_profile_combo.setCurrentText(
            str(self.base_category.get("route_profile", ""))
        )

        self.return_enabled_check = QCheckBox("Generate return / exchange task")
        self.return_enabled_check.setChecked(
            bool(self.base_category.get("return_enabled", False))
        )

        self.return_payload_combo = QComboBox()
        self.return_payload_combo.addItems([""] + self.payload_names)
        self.return_payload_combo.setCurrentText(
            str(self.base_category.get("return_payload", ""))
        )

        self.return_delay_edit = QLineEdit(
            str(self.base_category.get("return_delay_minutes", 0))
        )

        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        self.day_checks = {}
        active_days = set(
            self.base_category.get("days_active", ["mon", "tue", "wed", "thu", "fri"])
        )
        for key, label in self.DAYS:
            chk = QCheckBox(label)
            chk.setChecked(key in active_days)
            self.day_checks[key] = chk
            days_layout.addWidget(chk)
        days_layout.addStretch(1)

        schedule_row = QHBoxLayout()
        self.schedule_summary = QLabel()
        self.schedule_summary.setWordWrap(True)
        edit_times_btn = QPushButton("Edit times...")
        edit_times_btn.clicked.connect(self.edit_scheduled_times)
        clear_times_btn = QPushButton("Clear")
        clear_times_btn.clicked.connect(self.clear_scheduled_times)
        schedule_row.addWidget(self.schedule_summary, 1)
        schedule_row.addWidget(edit_times_btn)
        schedule_row.addWidget(clear_times_btn)

        self.frequency_edit = QLineEdit(
            str(self.base_category.get("frequency_per_day", 0.0))
        )
        self.volume_per_event_edit = QLineEdit(
            str(self.base_category.get("volume_per_event_m3", 0.0))
        )
        self.threshold_volume_edit = QLineEdit(
            str(self.base_category.get("threshold_volume_m3", 0.0))
        )
        self.base_daily_volume_edit = QLineEdit(
            str(self.base_category.get("base_daily_volume_m3", 0.0))
        )
        self.notes_edit = QPlainTextEdit(str(self.base_category.get("notes", "")))
        self.notes_edit.setFixedHeight(90)

        form.addRow("Enabled", self.enabled_check)
        form.addRow("Generation mode", self.mode_combo)
        form.addRow("Priority", self.priority_edit)
        form.addRow("Pickup / source locations", pickup_row)
        form.addRow("Drop-off destinations", dropoff_row)
        form.addRow("Payload", self.payload_combo)
        form.addRow("Tracked item exchange", self.tracked_item_exchange_check)
        form.addRow("Exchange mode", self.exchange_mode_combo)
        form.addRow("Route profile", self.route_profile_combo)
        form.addRow("Return task", self.return_enabled_check)
        form.addRow("Return payload", self.return_payload_combo)
        form.addRow("Return delay (minutes)", self.return_delay_edit)
        form.addRow("Days active", days_widget)
        form.addRow("Scheduled times", schedule_row)
        form.addRow("Frequency per day", self.frequency_edit)
        form.addRow("Volume per event m³", self.volume_per_event_edit)
        form.addRow("Threshold volume m³", self.threshold_volume_edit)
        form.addRow("Base daily volume m³", self.base_daily_volume_edit)
        form.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_department_summary()
        self.refresh_pickup_summary()
        self.update_role_field_state()
        self.refresh_dropoff_summary()
        self.refresh_schedule_summary()

    def set_department_location_role(self, role, checked):
        if not checked:
            return

        self.department_location_role = role

        self.role_pickup_radio.blockSignals(True)
        self.role_dropoff_radio.blockSignals(True)

        self.role_pickup_radio.setChecked(role == "pickup")
        self.role_dropoff_radio.setChecked(role == "dropoff")

        self.role_pickup_radio.blockSignals(False)
        self.role_dropoff_radio.blockSignals(False)

        self.update_role_field_state()

    def update_role_field_state(self):
        using_dept_as_pickup = self.department_location_role == "pickup"

        self.pickup_summary.setEnabled(not using_dept_as_pickup)
        self.pick_pickups_btn.setEnabled(not using_dept_as_pickup)
        self.clear_pickups_btn.setEnabled(not using_dept_as_pickup)

        self.dropoff_summary.setEnabled(using_dept_as_pickup)
        self.pick_dropoffs_btn.setEnabled(using_dept_as_pickup)
        self.clear_dropoffs_btn.setEnabled(using_dept_as_pickup)

    def _department_location_picker_rows(self):
        """Return picker rows for departments with assigned category locations.

        The picker should be readable to the user, so it shows the department
        identity/name.  The saved task-generation value must still be the real
        placed location assigned to this category.
        """
        placed_locations = {
            str(x).strip() for x in self.location_names if str(x).strip()
        }

        rows = []
        used_labels = set()

        sorted_departments = sorted(
            self.departments,
            key=lambda d: (
                (
                    int(d.get("floor", 0))
                    if str(d.get("floor", "")).strip().lstrip("-").isdigit()
                    else 999999
                ),
                str(d.get("name", "")).strip().lower()
                or str(d.get("id", "")).strip().lower(),
            ),
        )

        for dept in sorted_departments:
            dept_id = self._department_id_for_item(dept)
            if not dept_id:
                continue

            dept_name = str(dept.get("name", "")).strip()
            floor = str(dept.get("floor", "Other")).strip() or "Other"
            base_label = f"{dept_name} ({dept_id})" if dept_name else dept_id

            assigned_locations = []
            for location_name in self._category_locations_for_department(dept):
                if location_name in placed_locations:
                    assigned_locations.append(location_name)

            for location_name in sorted(set(assigned_locations)):
                label = f"{base_label}    [{location_name}]"
                if label in used_labels:
                    label = f"{base_label}    [{location_name}]    Floor {floor}"
                used_labels.add(label)
                rows.append(
                    {
                        "label": label,
                        "location": location_name,
                        "floor_group": f"Floor {floor}",
                        "department_id": dept_id,
                        "department_name": dept_name,
                    }
                )

        return rows

    def _department_label_for_location(self, location_name):
        location_name = str(location_name or "").strip()
        if not location_name:
            return ""

        for row in self._department_location_picker_rows():
            if row.get("location") == location_name:
                return row.get("label", location_name)

        return location_name

    def pick_pickups(self):
        rows = self._department_location_picker_rows()

        if not rows:
            QMessageBox.information(
                self,
                "Select pickup / source locations",
                (
                    f"No departments have an assigned placed location for "
                    f"the {self.category_key} category.\n\n"
                    "Assign or auto-assign category locations in the Department "
                    "editor first."
                ),
            )
            return

        label_to_location = {row["label"]: row["location"] for row in rows}
        label_to_group = {row["label"]: row["floor_group"] for row in rows}

        selected_labels = [
            row["label"]
            for row in rows
            if row["location"] in set(self.selected_pickup_locations)
        ]

        picker = MultiSelectPicker(
            self,
            "Select pickup / source department locations",
            [row["label"] for row in rows],
            selected=selected_labels,
            group_resolver=lambda item: label_to_group.get(item, "Departments"),
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_pickup_locations = sorted(
                {
                    label_to_location[label]
                    for label in picker.result
                    if label in label_to_location
                }
            )
            self.refresh_pickup_summary()

    def clear_pickups(self):
        self.selected_pickup_locations = []
        self.refresh_pickup_summary()

    def refresh_pickup_summary(self):
        if not self.selected_pickup_locations:
            self.pickup_summary.setText("None selected")
            return

        display_values = [
            self._department_label_for_location(location_name)
            for location_name in self.selected_pickup_locations
        ]

        if len(display_values) <= 4:
            self.pickup_summary.setText(", ".join(display_values))
        else:
            self.pickup_summary.setText(f"{len(display_values)} selected")

    def _department_id_for_item(self, dept):
        return str(dept.get("id", "")).strip() or str(dept.get("name", "")).strip()

    def _category_locations_for_department(self, dept):
        category_locations = dept.get("task_generation_locations", {}) or {}

        if not isinstance(category_locations, dict):
            return []

        category_entry = category_locations.get(self.category_key, {})

        if isinstance(category_entry, dict):
            raw_locations = category_entry.get(
                "pickup_dropoff_locations",
                category_entry.get("locations", []),
            )
        else:
            raw_locations = category_entry

        return [str(x).strip() for x in (raw_locations or []) if str(x).strip()]

    def _department_has_assigned_category_location(self, dept):
        placed_locations = {
            str(x).strip() for x in self.location_names if str(x).strip()
        }

        return any(
            location_name in placed_locations
            for location_name in self._category_locations_for_department(dept)
        )

    def _department_has_assigned_category_location_by_id(self, dept_id):
        dept_id = str(dept_id or "").strip()
        if not dept_id:
            return False

        for dept in self.departments:
            if self._department_id_for_item(dept) == dept_id:
                return self._department_has_assigned_category_location(dept)

        return False

    def pick_departments(self):
        options = []
        label_by_id = {}
        floor_by_label = {}

        sorted_departments = sorted(
            self.departments,
            key=lambda d: (
                int(d.get("floor", 0)),
                str(d.get("name", "")).strip().lower()
                or str(d.get("id", "")).strip().lower(),
            ),
        )

        for dept in sorted_departments:
            dept_id = self._department_id_for_item(dept)
            if not dept_id:
                continue

            # Only show departments that have a valid placed/assigned location
            # for the category currently being configured.
            if not self._department_has_assigned_category_location(dept):
                continue

            name = str(dept.get("name", "")).strip()
            floor = str(dept.get("floor", "Other")).strip() or "Other"
            category_locations = self._category_locations_for_department(dept)
            location_summary = ", ".join(category_locations[:3])
            if len(category_locations) > 3:
                location_summary += f", +{len(category_locations) - 3}"

            display = f"{dept_id} - {name}" if name else dept_id
            if location_summary:
                display = f"{display}    [{location_summary}]"

            options.append(display)
            label_by_id[display] = dept_id
            floor_by_label[display] = f"Floor {floor}"

        if not options:
            QMessageBox.information(
                self,
                "Select departments",
                (
                    f"No departments have an assigned placed location for "
                    f"the {self.category_key} category.\n\n"
                    "Assign or auto-assign category locations in the Department "
                    "editor first."
                ),
            )
            return

        picker = MultiSelectPicker(
            self,
            "Select departments",
            options,
            selected=[
                display
                for display, dept_id in label_by_id.items()
                if dept_id in self.selected_department_ids
            ],
            group_resolver=lambda item: floor_by_label.get(item, "Other"),
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_department_ids = [
                label_by_id[x] for x in picker.result if x in label_by_id
            ]

            self.refresh_department_summary()

    def _set_department_location_mode(self, dept_id, mode, checked, other_toggle):
        if not checked:
            return

        self.department_location_modes[dept_id] = mode

        other_toggle.blockSignals(True)
        other_toggle.setChecked(False)
        other_toggle.blockSignals(False)

    def refresh_department_summary(self):
        if not self.selected_department_ids:
            self.department_summary.setText("No departments selected")
        elif len(self.selected_department_ids) <= 6:
            self.department_summary.setText(", ".join(self.selected_department_ids))
        else:
            self.department_summary.setText(
                f"{len(self.selected_department_ids)} departments selected"
            )

    def pick_dropoffs(self):
        picker = MultiSelectPicker(
            self,
            "Select drop-off destinations",
            self.location_names,
            selected=self.selected_dropoffs,
            group_resolver=lambda item: "Locations",
        )
        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_dropoffs = sorted(picker.result)
            self.refresh_dropoff_summary()

    def clear_dropoffs(self):
        self.selected_dropoffs = []
        self.refresh_dropoff_summary()

    def refresh_dropoff_summary(self):
        if not self.selected_dropoffs:
            self.dropoff_summary.setText("None selected")
        elif len(self.selected_dropoffs) <= 4:
            self.dropoff_summary.setText(", ".join(self.selected_dropoffs))
        else:
            self.dropoff_summary.setText(f"{len(self.selected_dropoffs)} selected")

    def edit_scheduled_times(self):
        dialog = ScheduledTimesDialog(self, self.scheduled_times)
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.scheduled_times = list(dialog.result)
            self.refresh_schedule_summary()

    def clear_scheduled_times(self):
        self.scheduled_times = []
        self.refresh_schedule_summary()

    def refresh_schedule_summary(self):
        if not self.scheduled_times:
            self.schedule_summary.setText("No times selected")
        elif len(self.scheduled_times) <= 8:
            self.schedule_summary.setText(", ".join(self.scheduled_times))
        else:
            self.schedule_summary.setText(f"{len(self.scheduled_times)} times selected")

    def _department_default_location(self, dept_id):
        placed_locations = {
            str(x).strip() for x in self.location_names if str(x).strip()
        }

        for dept in self.departments:
            current_id = self._department_id_for_item(dept)
            if current_id != dept_id:
                continue

            for location_name in self._category_locations_for_department(dept):
                if location_name in placed_locations:
                    return location_name

        return ""

    def accept(self):
        try:
            if not self.selected_department_ids:
                raise ValueError("Select at least one department")

            days_active = [
                key for key, _label in self.DAYS if self.day_checks[key].isChecked()
            ]
            if not days_active:
                raise ValueError("Select at least one active day")

            dropoff_locations = [
                str(x).strip() for x in self.selected_dropoffs if str(x).strip()
            ]

            payload = {
                "enabled": self.enabled_check.isChecked(),
                "generation_mode": self.mode_combo.currentText().strip(),
                "priority": int(float(self.priority_edit.text() or 100)),
                "pickup_location": (
                    self.selected_pickup_locations[0]
                    if self.selected_pickup_locations
                    else ""
                ),
                "pickup_locations": list(self.selected_pickup_locations),
                "dropoff_location": dropoff_locations[0] if dropoff_locations else "",
                "dropoff_locations": dropoff_locations,
                "payload": self.payload_combo.currentText().strip(),
                "tracked_item_exchange": self.tracked_item_exchange_check.isChecked(),
                "exchange_mode": self.exchange_mode_combo.currentText().strip(),
                "return_enabled": self.return_enabled_check.isChecked(),
                "return_payload": self.return_payload_combo.currentText().strip(),
                "return_delay_minutes": float(self.return_delay_edit.text() or 0),
                "route_profile": self.route_profile_combo.currentText().strip(),
                "days_active": days_active,
                "scheduled_times": list(self.scheduled_times),
                "frequency_per_day": float(self.frequency_edit.text() or 0.0),
                "volume_per_event_m3": float(self.volume_per_event_edit.text() or 0.0),
                "threshold_volume_m3": float(self.threshold_volume_edit.text() or 0.0),
                "base_daily_volume_m3": float(
                    self.base_daily_volume_edit.text() or 0.0
                ),
                "notes": self.notes_edit.toPlainText().strip(),
            }

            self.result = {}

            for dept_id in self.selected_department_ids:
                item = dict(payload)
                role = self.department_location_role
                dept_location = self._department_default_location(dept_id)

                if role == "pickup":
                    item["pickup_location"] = dept_location
                    item["pickup_locations"] = [dept_location] if dept_location else []
                    item["dropoff_location"] = (
                        dropoff_locations[0] if dropoff_locations else ""
                    )
                    item["dropoff_locations"] = list(dropoff_locations)
                else:
                    item["pickup_location"] = (
                        self.selected_pickup_locations[0]
                        if self.selected_pickup_locations
                        else ""
                    )
                    item["pickup_locations"] = list(self.selected_pickup_locations)
                    item["dropoff_location"] = dept_location
                    item["dropoff_locations"] = [dept_location] if dept_location else []

                item["department_location_role"] = role
                self.result[dept_id] = item

            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid bulk department settings", str(exc))


class ConfiguredGroupSelectDialog(QDialog):
    def __init__(self, parent, title, groups, label_builder):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 520)
        self.result_key = None

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget, 1)

        for signature, group in groups.items():
            item = QListWidgetItem(label_builder(group))
            item.setData(Qt.UserRole, signature)
            item.setSizeHint(item.sizeHint())
            self.list_widget.addItem(item)

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.result_key = item.data(Qt.UserRole)
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
            "Select a department to configure department-specific task generation"
        )
        self.department_hint.setWordWrap(True)
        department_col.addWidget(self.department_hint)

        bulk_dept_btn = QPushButton("Configure multiple...")
        bulk_dept_btn.clicked.connect(self.configure_multiple_departments)
        department_col.addWidget(bulk_dept_btn)

        edit_group_btn = QPushButton("Edit configured group...")
        edit_group_btn.clicked.connect(self.edit_configured_department_group)
        department_col.addWidget(edit_group_btn)

        clear_group_btn = QPushButton("Clear configured group...")
        clear_group_btn.clicked.connect(self.clear_configured_department_group)
        department_col.addWidget(clear_group_btn)

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

        dropoff_row.addWidget(self.dropoff_summary, 1)
        dropoff_row.addWidget(self.pick_dropoffs_btn)
        dropoff_row.addWidget(self.clear_dropoffs_btn)

        self.payload_combo = QComboBox()
        self.payload_combo.addItems([""] + self.payload_names)

        self.tracked_item_exchange_check = QCheckBox(
            "Generate tracked item exchange tasks"
        )

        self.exchange_mode_combo = QComboBox()
        self.exchange_mode_combo.addItems(
            [
                "full_exchange",
                "top_up_only",
                "replace_empty",
            ]
        )

        self.route_profile_combo = QComboBox()
        self.route_profile_combo.addItems([""] + self.profile_names)

        self.return_enabled_check = QCheckBox("Generate return / exchange task")
        self.return_payload_combo = QComboBox()
        self.return_payload_combo.addItems([""] + self.payload_names)

        self.return_delay_edit = QLineEdit()

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
        form.addRow("Tracked item exchange", self.tracked_item_exchange_check)
        form.addRow("Exchange mode", self.exchange_mode_combo)
        form.addRow("Route profile", self.route_profile_combo)
        form.addRow("Return task", self.return_enabled_check)
        form.addRow("Return payload", self.return_payload_combo)
        form.addRow("Return delay (minutes)", self.return_delay_edit)
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

    def _department_display_name(self, dept_id):
        dept_id = str(dept_id).strip()

        for dept in self.departments:
            current_id = (
                str(dept.get("id", "")).strip() or str(dept.get("name", "")).strip()
            )
            if current_id == dept_id:
                name = str(dept.get("name", "")).strip()
                floor = str(dept.get("floor", "")).strip()
                if floor:
                    return f"{name or dept_id} (Floor {floor})"
                return name or dept_id

        return dept_id

    def _department_group_names_text(self, dept_ids, limit=4):
        names = [self._department_display_name(x) for x in sorted(dept_ids)]

        if len(names) <= limit:
            return ", ".join(names)

        shown = ", ".join(names[:limit])
        remaining = len(names) - limit
        return f"{shown}, +{remaining} departments"

    def _configured_group_label(self, group):
        payload = group.get("payload", {}) or {}
        dept_ids = sorted(group.get("departments", []))

        category_label = (
            self.category_list.currentItem().text()
            if self.category_list.currentItem()
            else self.current_key
        )

        payload_name = str(payload.get("payload", "")).strip() or "No payload"
        role = str(payload.get("department_location_role", "")).strip() or "default"
        mode = str(payload.get("generation_mode", "")).strip() or "default"
        pickup = str(payload.get("pickup_location", "")).strip() or "None"
        dropoff = str(payload.get("dropoff_location", "")).strip() or "None"
        delay = str(payload.get("return_delay_minutes", "")).strip()

        lines = [
            f"{category_label}    Payload: {payload_name}    Mode: {mode}",
            f"Departments: {self._department_group_names_text(dept_ids, limit=4)}",
            f"Role: {role}    Pickup: {pickup}    Drop-off: {dropoff}",
        ]

        if delay not in {"", "0", "0.0"}:
            lines.append(f"Return delay: {delay} min")

        return "\n".join(lines)

    def _current_form_has_generation_settings(self):
        if self.enabled_check.isChecked():
            return True

        if self.pickup_combo.currentText().strip():
            return True

        if self.selected_dropoffs:
            return True

        if self.payload_combo.currentText().strip():
            return True

        if self.return_enabled_check.isChecked():
            return True

        if self.return_payload_combo.currentText().strip():
            return True

        if self.route_profile_combo.currentText().strip():
            return True

        if self.scheduled_times:
            return True

        numeric_fields = [
            self.frequency_edit,
            self.volume_per_event_edit,
            self.threshold_volume_edit,
            self.base_daily_volume_edit,
        ]

        for widget in numeric_fields:
            try:
                if float(widget.text() or 0.0) != 0.0:
                    return True
            except Exception:
                if widget.text().strip():
                    return True

        if self.notes_edit.toPlainText().strip():
            return True

        if hasattr(self, "tracked_item_exchange_check"):
            if self.tracked_item_exchange_check.isChecked():
                return True

        return False

    def clear_configured_department_group(self):
        if not self.current_key:
            QMessageBox.information(
                self,
                "Clear configured group",
                "Select a category first.",
            )
            return

        try:
            self._store_current_category()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid current category", str(exc))
            return

        category = self.config.setdefault("categories", {}).setdefault(
            self.current_key, {}
        )
        overrides = category.setdefault("departments", {})
        groups = self._stored_department_group_map(self.current_key)

        if not groups:
            QMessageBox.information(
                self,
                "Clear configured group",
                "No multi-department configured groups were found for this category.",
            )
            return

        dialog = ConfiguredGroupSelectDialog(
            self,
            "Clear configured group",
            groups,
            self._configured_group_label,
        )

        if dialog.exec() != QDialog.Accepted or not dialog.result_key:
            return

        group = groups[dialog.result_key]
        dept_ids = sorted(group["departments"])

        if (
            QMessageBox.question(
                self,
                "Clear configured group",
                (
                    f"Clear task-generation overrides for {len(dept_ids)} department(s)?\n\n"
                    + ", ".join(dept_ids[:12])
                    + ("..." if len(dept_ids) > 12 else "")
                ),
            )
            != QMessageBox.Yes
        ):
            return

        for dept_id in dept_ids:
            overrides.pop(dept_id, None)

        category["department_groups"] = [
            group
            for group in self._department_groups_for_category(self.current_key)
            if str(group.get("id", "")).strip() != str(dialog.result_key).strip()
        ]

        remaining_dept = None

        for index in range(self.department_list.count()):
            item = self.department_list.item(index)
            dept_id = str(item.data(Qt.UserRole) or "").strip()
            if dept_id and dept_id not in dept_ids:
                remaining_dept = dept_id
                break

        self._loading = True
        self._refresh_department_list(select_dept_id=remaining_dept)

        if self.department_list.count() > 0:
            current = self.department_list.currentItem()
            self.current_department_id = current.data(Qt.UserRole) if current else ""
            self.current_department_id = self.current_department_id or ""
            self._load_category(self.current_key)
        else:
            self.current_department_id = ""
            self._clear_task_generation_form()

        self._loading = False

        self._loading = True
        self._refresh_department_list(select_dept_id="")
        self._load_category(self.current_key)
        self._loading = False

        QMessageBox.information(
            self,
            "Clear configured group",
            f"Cleared {len(dept_ids)} department override(s).",
        )

    def _bulk_group_signature(self, payload):
        return json.dumps(payload or {}, sort_keys=True)

    def _department_groups_for_category(self, category_key):
        category = self.config.setdefault("categories", {}).setdefault(category_key, {})
        groups = category.setdefault("department_groups", [])

        if not isinstance(groups, list):
            groups = []
            category["department_groups"] = groups

        clean_groups = []
        seen_ids = set()

        for group in groups:
            if not isinstance(group, dict):
                continue

            group_id = str(group.get("id", "")).strip()
            if not group_id:
                group_id = self._new_department_group_id(category)

            if group_id in seen_ids:
                group_id = self._new_department_group_id(category)

            departments = [
                str(x).strip() for x in group.get("departments", []) if str(x).strip()
            ]

            payload = group.get("payload", {})
            if not departments or not isinstance(payload, dict):
                continue

            seen_ids.add(group_id)
            clean_groups.append(
                {
                    "id": group_id,
                    "departments": sorted(set(departments)),
                    "payload": dict(payload),
                }
            )

        category["department_groups"] = clean_groups
        return clean_groups

    def _new_department_group_id(self, category):
        existing = {
            str(group.get("id", "")).strip()
            for group in category.get("department_groups", [])
            if isinstance(group, dict)
        }

        counter = 1
        while True:
            group_id = f"GROUP-{counter}"
            if group_id not in existing:
                return group_id
            counter += 1

    def _stored_department_group_map(self, category_key):
        groups = self._department_groups_for_category(category_key)
        return {
            str(group.get("id", "")).strip(): group
            for group in groups
            if str(group.get("id", "")).strip()
        }

    def _remove_departments_from_groups(
        self,
        category_key,
        department_ids,
        except_group_id=None,
    ):
        department_ids = {str(x).strip() for x in department_ids if str(x).strip()}

        if not department_ids:
            return

        groups = self._department_groups_for_category(category_key)
        kept_groups = []

        for group in groups:
            group_id = str(group.get("id", "")).strip()

            if except_group_id and group_id == str(except_group_id).strip():
                kept_groups.append(group)
                continue

            group["departments"] = [
                dept_id
                for dept_id in group.get("departments", [])
                if str(dept_id).strip() not in department_ids
            ]

            if group["departments"]:
                kept_groups.append(group)

        category = self.config.setdefault("categories", {}).setdefault(category_key, {})
        category["department_groups"] = kept_groups

    def _remove_department_from_group_if_settings_changed(
        self,
        category_key,
        department_id,
        payload,
    ):
        department_id = str(department_id or "").strip()
        if not department_id:
            return

        current_signature = self._bulk_group_signature(payload)
        groups = self._department_groups_for_category(category_key)
        changed = False

        for group in groups:
            group_payload = group.get("payload", {})
            group_signature = self._bulk_group_signature(group_payload)

            if department_id not in group.get("departments", []):
                continue

            if group_signature != current_signature:
                group["departments"] = [
                    dept_id
                    for dept_id in group.get("departments", [])
                    if dept_id != department_id
                ]
                changed = True

        if changed:
            category = self.config.setdefault("categories", {}).setdefault(
                category_key, {}
            )
            category["department_groups"] = [
                group for group in groups if group.get("departments")
            ]

    def _upsert_department_group(self, category_key, group_id, department_ids, payload):
        category = self.config.setdefault("categories", {}).setdefault(category_key, {})
        groups = self._department_groups_for_category(category_key)

        group_id = str(group_id or "").strip()
        if not group_id:
            group_id = self._new_department_group_id(category)

        department_ids = sorted(
            {str(x).strip() for x in department_ids if str(x).strip()}
        )

        if not department_ids:
            return ""

        self._remove_departments_from_groups(
            category_key,
            department_ids,
            except_group_id=group_id,
        )

        groups = self._department_groups_for_category(category_key)

        existing = next(
            (group for group in groups if str(group.get("id", "")).strip() == group_id),
            None,
        )

        if existing is None:
            groups.append(
                {
                    "id": group_id,
                    "departments": department_ids,
                    "payload": dict(payload),
                }
            )
        else:
            existing["departments"] = department_ids
            existing["payload"] = dict(payload)

        category["department_groups"] = [
            group for group in groups if group.get("departments")
        ]

        return group_id

    def edit_configured_department_group(self):
        if not self.current_key:
            QMessageBox.information(
                self,
                "Edit configured group",
                "Select a category first.",
            )
            return

        try:
            self._store_current_category()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid current category", str(exc))
            return

        category = self.config.setdefault("categories", {}).setdefault(
            self.current_key, {}
        )
        overrides = category.setdefault("departments", {})
        groups = self._stored_department_group_map(self.current_key)

        if not groups:
            QMessageBox.information(
                self,
                "Edit configured group",
                "No multi-department configured groups were found for this category.",
            )
            return

        dialog = ConfiguredGroupSelectDialog(
            self,
            "Edit configured group",
            groups,
            self._configured_group_label,
        )

        if dialog.exec() != QDialog.Accepted or not dialog.result_key:
            return

        group = groups[dialog.result_key]
        group_payload = dict(group["payload"])
        selected_department_ids = sorted(group["departments"])

        dialog = BulkDepartmentTaskGenerationDialog(
            self,
            category_key=self.current_key,
            category_label=(
                self.category_list.currentItem().text()
                if self.category_list.currentItem()
                else self.current_key
            ),
            departments=self.departments,
            base_category=group_payload,
            location_names=self.location_names,
            payload_names=self.payload_names,
            profile_names=self.profile_names,
            selected_department_ids=selected_department_ids,
            result_key=dialog.result_key,
        )

        if dialog.exec() == QDialog.Accepted and dialog.result:
            result_dept_ids = sorted(dialog.result.keys())
            result_payload = next(iter(dialog.result.values()))

            for dept_id in selected_department_ids:
                overrides.pop(dept_id, None)

            for dept_id, payload in dialog.result.items():
                overrides[dept_id] = payload

            self._upsert_department_group(
                self.current_key,
                getattr(dialog, "result_key", ""),
                result_dept_ids,
                result_payload,
            )

            self._load_category(self.current_key)

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
        current_dept_id = str(
            select_dept_id or self.current_department_id or ""
        ).strip()

        self.department_list.blockSignals(True)
        self.department_list.clear()

        selected_row = 0
        valid_departments = []

        for dept in self.departments:
            dept_id = str(dept.get("id", "")).strip()
            if not dept_id:
                dept_id = str(dept.get("name", "")).strip()

            if not dept_id:
                continue

            valid_departments.append((dept_id, dept))

        valid_departments.sort(
            key=lambda item: (
                (
                    int(item[1].get("floor", 0))
                    if str(item[1].get("floor", "")).strip().lstrip("-").isdigit()
                    else 999999
                ),
                str(item[1].get("name", "")).strip().lower()
                or str(item[0]).strip().lower(),
            )
        )

        for row_index, (dept_id, dept) in enumerate(valid_departments):
            item = QListWidgetItem(self._department_label(dept))
            item.setData(Qt.UserRole, dept_id)
            self.department_list.addItem(item)

            if dept_id == current_dept_id:
                selected_row = row_index

        self.department_list.blockSignals(False)

        if self.department_list.count() > 0:
            self.department_list.setCurrentRow(selected_row)
            current = self.department_list.currentItem()
            self.current_department_id = current.data(Qt.UserRole) if current else ""
            self.current_department_id = self.current_department_id or ""
        else:
            self.current_department_id = ""

    def configure_multiple_departments(self):
        if not self.current_key:
            QMessageBox.information(
                self,
                "Configure departments",
                "Select a category first.",
            )
            return

        try:
            self._store_current_category()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid current category", str(exc))
            return

        dialog = BulkDepartmentTaskGenerationDialog(
            self,
            category_key=self.current_key,
            category_label=(
                self.category_list.currentItem().text()
                if self.category_list.currentItem()
                else self.current_key
            ),
            departments=self.departments,
            base_category=self.config.get("categories", {}).get(self.current_key, {}),
            location_names=self.location_names,
            payload_names=self.payload_names,
            profile_names=self.profile_names,
        )

        if dialog.exec() == QDialog.Accepted and dialog.result:
            category = self.config.setdefault("categories", {}).setdefault(
                self.current_key, {}
            )
            overrides = category.setdefault("departments", {})

            result_dept_ids = sorted(dialog.result.keys())
            result_payload = next(iter(dialog.result.values()))

            for dept_id, payload in dialog.result.items():
                overrides[dept_id] = payload

            self._upsert_department_group(
                self.current_key,
                group_id="",
                department_ids=result_dept_ids,
                payload=result_payload,
            )

            self._load_category(self.current_key)

    def _on_department_changed(self, current, previous):
        if self._loading:
            return

        if previous is not None and self.current_key:
            previous_dept_id = str(previous.data(Qt.UserRole) or "").strip()

            if previous_dept_id and self._current_form_has_generation_settings():
                try:
                    self._store_category(
                        self.current_key,
                        list_item=None,
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

        self._loading = True
        self._refresh_department_list(select_dept_id=self.current_department_id)

        if self.department_list.count() > 0:
            current_dept = self.department_list.currentItem()
            self.current_department_id = (
                current_dept.data(Qt.UserRole) if current_dept else ""
            )
            self.current_department_id = self.current_department_id or ""
            self._load_category(self.current_key)
        else:
            self.current_department_id = ""
            self._clear_task_generation_form()

        self._loading = False

    def _clear_task_generation_form(self):
        self.enabled_check.setChecked(False)
        self.display_name_edit.setText("")
        self.display_name_edit.setEnabled(False)
        self.mode_combo.setCurrentText("scheduled")
        self.priority_edit.setText("100")
        self.pickup_combo.setCurrentText("")
        self.selected_dropoffs = []
        self._refresh_dropoff_summary()
        self.payload_combo.setCurrentText("")
        self.route_profile_combo.setCurrentText("")
        self.return_enabled_check.setChecked(False)
        self.return_payload_combo.setCurrentText("")
        self.return_delay_edit.setText("0")

        if hasattr(self, "tracked_item_exchange_check"):
            self.tracked_item_exchange_check.setChecked(False)

        if hasattr(self, "exchange_mode_combo"):
            self.exchange_mode_combo.setCurrentText("top_up_only")

        for day_key, _label in self.DAYS:
            self.day_checks[day_key].setChecked(False)

        self.scheduled_times = []
        self._refresh_schedule_summary()

        self.frequency_edit.setText("0.0")
        self.volume_per_event_edit.setText("0.0")
        self.threshold_volume_edit.setText("0.0")
        self.base_daily_volume_edit.setText("0.0")
        self.notes_edit.setPlainText("")
        self._update_mode_field_state()

    def _load_category(self, key):
        was_loading = self._loading
        self._loading = True
        item = self._effective_category_item(key, self.current_department_id)
        self._normalise_category_dropoffs(item)
        self.selected_dropoffs = list(item.get("dropoff_locations", []))
        self.enabled_check.setChecked(bool(item.get("enabled", False)))

        category = self.config.get("categories", {}).get(key, {})
        self.display_name_edit.setText(str(category.get("display_name", key.title())))
        self.display_name_edit.setEnabled(False)

        self.mode_combo.setCurrentText(str(item.get("generation_mode", "scheduled")))
        self.priority_edit.setText(str(item.get("priority", 100)))
        self.pickup_combo.setCurrentText(str(item.get("pickup_location", "")))
        self._refresh_dropoff_summary()
        self.payload_combo.setCurrentText(str(item.get("payload", "")))
        self.tracked_item_exchange_check.setChecked(
            bool(item.get("tracked_item_exchange", False))
        )
        self.exchange_mode_combo.setCurrentText(
            str(item.get("exchange_mode", "top_up_only"))
        )
        self.route_profile_combo.setCurrentText(str(item.get("route_profile", "")))
        self.return_enabled_check.setChecked(bool(item.get("return_enabled", False)))
        self.return_payload_combo.setCurrentText(str(item.get("return_payload", "")))
        self.return_delay_edit.setText(str(item.get("return_delay_minutes", 0)))
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

        if not self.current_department_id:
            return

        if not self._current_form_has_generation_settings():
            return

        self._store_category(
            self.current_key,
            list_item=None,
            department_id=self.current_department_id,
        )

    def _store_category(self, category_key, list_item=None, department_id=""):
        if not category_key:
            return

        department_id = str(department_id or "").strip()

        if not department_id:
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
            "tracked_item_exchange": self.tracked_item_exchange_check.isChecked(),
            "exchange_mode": self.exchange_mode_combo.currentText().strip(),
            "return_enabled": self.return_enabled_check.isChecked(),
            "return_payload": self.return_payload_combo.currentText().strip(),
            "return_delay_minutes": float(self.return_delay_edit.text() or 0),
            "route_profile": self.route_profile_combo.currentText().strip(),
            "days_active": days_active,
            "scheduled_times": list(self.scheduled_times),
            "frequency_per_day": float(self.frequency_edit.text() or 0.0),
            "volume_per_event_m3": float(self.volume_per_event_edit.text() or 0.0),
            "threshold_volume_m3": float(self.threshold_volume_edit.text() or 0.0),
            "base_daily_volume_m3": float(self.base_daily_volume_edit.text() or 0.0),
            "notes": self.notes_edit.toPlainText().strip(),
        }

        category = self.config.setdefault("categories", {}).setdefault(category_key, {})
        overrides = category.setdefault("departments", {})

        payload.pop("display_name", None)
        payload.pop("departments", None)

        # If the department row is effectively blank, remove the override instead
        # of writing disabled/default config into the JSON.
        if not self._current_form_has_generation_settings():
            overrides.pop(department_id, None)
            self._remove_departments_from_groups(category_key, [department_id])
            return

        # Also remove empty disabled overrides. This prevents switching departments
        # from creating blank/default task_generation entries.
        if not payload.get("enabled", False):
            has_meaningful_disabled_config = any(
                [
                    payload.get("pickup_location"),
                    payload.get("dropoff_location"),
                    payload.get("dropoff_locations"),
                    payload.get("payload"),
                    payload.get("return_enabled"),
                    payload.get("return_payload"),
                    payload.get("route_profile"),
                    payload.get("scheduled_times"),
                    float(payload.get("frequency_per_day", 0.0) or 0.0) != 0.0,
                    float(payload.get("volume_per_event_m3", 0.0) or 0.0) != 0.0,
                    float(payload.get("threshold_volume_m3", 0.0) or 0.0) != 0.0,
                    float(payload.get("base_daily_volume_m3", 0.0) or 0.0) != 0.0,
                    payload.get("notes"),
                    payload.get("tracked_item_exchange"),
                ]
            )

            if not has_meaningful_disabled_config:
                overrides.pop(department_id, None)
                self._remove_departments_from_groups(category_key, [department_id])
                return

        overrides[department_id] = payload
        self._remove_department_from_group_if_settings_changed(
            category_key,
            department_id,
            payload,
        )

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


def _normalise_amr_payload_slots(amr):
    """Return the AMR payload slot list, migrating legacy single-slot fields."""
    slots = amr.get("payload_slots", []) if isinstance(amr, dict) else []
    clean = []

    if isinstance(slots, list):
        for idx, slot in enumerate(slots, start=1):
            if not isinstance(slot, dict):
                continue
            clean.append(
                {
                    "name": str(slot.get("name", "")).strip() or f"Slot {idx}",
                    "payload_capacity_kg": float(
                        slot.get("payload_capacity_kg", 0.0) or 0.0
                    ),
                    "payload_length_capacity_m": float(
                        slot.get("payload_length_capacity_m", 0.0) or 0.0
                    ),
                    "payload_width_capacity_m": float(
                        slot.get("payload_width_capacity_m", 0.0) or 0.0
                    ),
                    "payload_height_capacity_m": float(
                        slot.get("payload_height_capacity_m", 0.0) or 0.0
                    ),
                }
            )

    if not clean:
        clean = [
            {
                "name": "Slot 1",
                "payload_capacity_kg": float(
                    amr.get("payload_capacity_kg", 100) or 100
                ),
                "payload_length_capacity_m": float(
                    amr.get("payload_length_capacity_m", 1.0) or 1.0
                ),
                "payload_width_capacity_m": float(
                    amr.get("payload_width_capacity_m", 1.0) or 1.0
                ),
                "payload_height_capacity_m": float(
                    amr.get("payload_height_capacity_m", 1.0) or 1.0
                ),
            }
        ]

    return clean


def _amr_payload_slot_summary(amr):
    slots = _normalise_amr_payload_slots(amr)
    if len(slots) == 1:
        slot = slots[0]
        return (
            f"1 slot ({slot.get('payload_capacity_kg', 0):g} kg, "
            f"{slot.get('payload_length_capacity_m', 0):g} x "
            f"{slot.get('payload_width_capacity_m', 0):g} x "
            f"{slot.get('payload_height_capacity_m', 0):g} m)"
        )
    return f"{len(slots)} slots"


class AMREditorDialog(QDialog):
    def __init__(self, parent, location_names, seed=None, default_amr_id="AMR-1"):
        super().__init__(parent)
        self.setWindowTitle("AMR")
        self.result = None
        self.seed = seed or {}
        self.location_names = sorted(location_names)
        self.payload_slots = _normalise_amr_payload_slots(self.seed)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.id_edit = QLineEdit(str(self.seed.get("id", default_amr_id)))
        self.quantity_edit = QLineEdit(str(self.seed.get("quantity", 1)))
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
        self.multi_stop_check = QCheckBox("Allow multi-stop route batching")
        self.multi_stop_check.setChecked(
            bool(self.seed.get("multi_stop_enabled", len(self.payload_slots) > 1))
        )

        self.start_location_combo = QComboBox()
        self.start_location_combo.addItems([""] + self.location_names)
        self.start_location_combo.setCurrentText(
            str(self.seed.get("start_location", ""))
        )

        form.addRow("AMR ID", self.id_edit)
        form.addRow("Quantity", self.quantity_edit)
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
        form.addRow("Multi-stop", self.multi_stop_check)

        layout.addWidget(QLabel("Payload slots"))
        self.slots_table = QTableWidget(0, 5)
        self.slots_table.setHorizontalHeaderLabels(
            ["Slot", "Weight kg", "Length m", "Width m", "Height m"]
        )
        self.slots_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.slots_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.slots_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        layout.addWidget(self.slots_table, 1)

        slot_buttons = QHBoxLayout()
        layout.addLayout(slot_buttons)

        add_slot_btn = QPushButton("Add slot")
        duplicate_slot_btn = QPushButton("Duplicate selected slot")
        delete_slot_btn = QPushButton("Delete selected slot")

        add_slot_btn.clicked.connect(self.add_payload_slot)
        duplicate_slot_btn.clicked.connect(self.duplicate_payload_slot)
        delete_slot_btn.clicked.connect(self.delete_payload_slot)

        slot_buttons.addWidget(add_slot_btn)
        slot_buttons.addWidget(duplicate_slot_btn)
        slot_buttons.addWidget(delete_slot_btn)
        slot_buttons.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_slots_table()
        self.resize(720, 620)

    def _refresh_slots_table(self):
        self.slots_table.setRowCount(0)
        for slot in self.payload_slots:
            row = self.slots_table.rowCount()
            self.slots_table.insertRow(row)
            values = [
                slot.get("name", f"Slot {row + 1}"),
                slot.get("payload_capacity_kg", 0.0),
                slot.get("payload_length_capacity_m", 0.0),
                slot.get("payload_width_capacity_m", 0.0),
                slot.get("payload_height_capacity_m", 0.0),
            ]
            for col, value in enumerate(values):
                self.slots_table.setItem(row, col, QTableWidgetItem(str(value)))

    def add_payload_slot(self):
        self.payload_slots.append(
            {
                "name": f"Slot {len(self.payload_slots) + 1}",
                "payload_capacity_kg": 100.0,
                "payload_length_capacity_m": 1.0,
                "payload_width_capacity_m": 1.0,
                "payload_height_capacity_m": 1.0,
            }
        )
        self._refresh_slots_table()
        self.slots_table.selectRow(self.slots_table.rowCount() - 1)

    def duplicate_payload_slot(self):
        row = self.slots_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Payload slots",
                "Select a payload slot to duplicate.",
            )
            return

        try:
            # Read from the table first so any unsaved edits in the selected row
            # are copied rather than the last refreshed backing data.
            name_item = self.slots_table.item(row, 0)
            kg_item = self.slots_table.item(row, 1)
            length_item = self.slots_table.item(row, 2)
            width_item = self.slots_table.item(row, 3)
            height_item = self.slots_table.item(row, 4)

            source_name = (
                name_item.text().strip()
                if name_item and name_item.text().strip()
                else f"Slot {row + 1}"
            )

            duplicate = {
                "name": f"{source_name} Copy",
                "payload_capacity_kg": float(kg_item.text() if kg_item else 0.0),
                "payload_length_capacity_m": float(
                    length_item.text() if length_item else 0.0
                ),
                "payload_width_capacity_m": float(
                    width_item.text() if width_item else 0.0
                ),
                "payload_height_capacity_m": float(
                    height_item.text() if height_item else 0.0
                ),
            }

            insert_at = row + 1
            self.payload_slots.insert(insert_at, duplicate)
            self._refresh_slots_table()
            self.slots_table.selectRow(insert_at)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Payload slots",
                f"Could not duplicate selected slot: {exc}",
            )

    def delete_payload_slot(self):
        row = self.slots_table.currentRow()
        if row < 0:
            return
        if len(self.payload_slots) <= 1:
            QMessageBox.critical(
                self, "Payload slots", "AMRs must have at least one payload slot."
            )
            return
        del self.payload_slots[row]
        self._refresh_slots_table()

    def _collect_payload_slots(self):
        slots = []
        for row in range(self.slots_table.rowCount()):
            name_item = self.slots_table.item(row, 0)
            kg_item = self.slots_table.item(row, 1)
            length_item = self.slots_table.item(row, 2)
            width_item = self.slots_table.item(row, 3)
            height_item = self.slots_table.item(row, 4)
            slot = {
                "name": (name_item.text().strip() if name_item else "")
                or f"Slot {row + 1}",
                "payload_capacity_kg": float(kg_item.text() if kg_item else 0.0),
                "payload_length_capacity_m": float(
                    length_item.text() if length_item else 0.0
                ),
                "payload_width_capacity_m": float(
                    width_item.text() if width_item else 0.0
                ),
                "payload_height_capacity_m": float(
                    height_item.text() if height_item else 0.0
                ),
            }
            if slot["payload_capacity_kg"] <= 0:
                raise ValueError(
                    f"{slot['name']} weight capacity must be greater than 0"
                )
            for key in [
                "payload_length_capacity_m",
                "payload_width_capacity_m",
                "payload_height_capacity_m",
            ]:
                if slot[key] <= 0:
                    raise ValueError(
                        f"{slot['name']} dimensions must be greater than 0"
                    )
            slots.append(slot)
        if not slots:
            raise ValueError("Add at least one payload slot")
        return slots

    def accept(self):
        try:
            amr_id = self.id_edit.text().strip()
            if not amr_id:
                raise ValueError("AMR ID is required")

            payload_slots = self._collect_payload_slots()
            primary_slot = payload_slots[0]
            multi_stop_enabled = bool(
                self.multi_stop_check.isChecked() and len(payload_slots) > 1
            )

            self.result = {
                "id": amr_id,
                "quantity": int(float(self.quantity_edit.text())),
                "payload_slots": payload_slots,
                "payload_capacity_kg": float(primary_slot["payload_capacity_kg"]),
                "payload_length_capacity_m": float(
                    primary_slot["payload_length_capacity_m"]
                ),
                "payload_width_capacity_m": float(
                    primary_slot["payload_width_capacity_m"]
                ),
                "payload_height_capacity_m": float(
                    primary_slot["payload_height_capacity_m"]
                ),
                "multi_stop_enabled": multi_stop_enabled,
                "manual_task_compatible": len(payload_slots) == 1,
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


class PayloadTrackedItemDialog(QDialog):
    MODES = [
        "scheduled",
        "threshold",
        "continuous",
        "sporadic",
        "hybrid",
        "scheduled_threshold",
        "scheduled_sporadic",
    ]

    def __init__(self, parent, seed=None, payload_names=None, location_names=None):
        super().__init__(parent)
        self.setWindowTitle("Tracked payload item")
        self.seed = seed or {}
        self.result = None

        self.payload_names = sorted(payload_names or [])
        self.location_names = sorted(location_names or [])
        self.selected_source_locations = (
            [str(self.seed.get("source_location", "")).strip()]
            if str(self.seed.get("source_location", "")).strip()
            else []
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_edit = QLineEdit(str(self.seed.get("name", "")))
        self.max_edit = QLineEdit(str(self.seed.get("max", 100)))
        self.threshold_edit = QLineEdit(str(self.seed.get("top_up_threshold", 15)))
        self.consumption_edit = QLineEdit(
            str(self.seed.get("consumption_per_day", 0.0))
        )

        self.exchange_payload_combo = QComboBox()
        self.exchange_payload_combo.addItems([""] + self.payload_names)
        self.exchange_payload_combo.setCurrentText(
            str(self.seed.get("exchange_payload", ""))
        )

        source_row = QHBoxLayout()
        self.source_location_summary = QLabel("None selected")
        self.source_location_summary.setWordWrap(True)

        source_btn = QPushButton("Select...")
        source_btn.clicked.connect(self.pick_source_locations)

        clear_source_btn = QPushButton("Clear")
        clear_source_btn.clicked.connect(self.clear_source_locations)

        source_row.addWidget(self.source_location_summary, 1)
        source_row.addWidget(source_btn)
        source_row.addWidget(clear_source_btn)

        self.usage_rate_combo = QComboBox()
        self.usage_rate_combo.addItems(self.MODES)
        self.usage_rate_combo.setCurrentText(
            str(self.seed.get("usage_rate", "scheduled_sporadic"))
        )

        form.addRow("Item name", self.name_edit)
        form.addRow("Maximum quantity", self.max_edit)
        form.addRow("Top-up threshold", self.threshold_edit)
        form.addRow("Usage rate", self.usage_rate_combo)

        form.addRow("Consumption/day", self.consumption_edit)

        form.addRow("Exchange payload", self.exchange_payload_combo)
        form.addRow("Source location", source_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_source_location_summary()

    def pick_source_locations(self):
        picker = MultiSelectPicker(
            self,
            "Select source location",
            self.location_names,
            selected=self.selected_source_locations,
            group_resolver=lambda item: "Locations",
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_source_locations = sorted(picker.result[:1])
            self.refresh_source_location_summary()

    def clear_source_locations(self):
        self.selected_source_locations = []
        self.refresh_source_location_summary()

    def refresh_source_location_summary(self):
        if not self.selected_source_locations:
            self.source_location_summary.setText("None selected")
        else:
            self.source_location_summary.setText(self.selected_source_locations[0])

    def accept(self):
        try:
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Item name is required")

            max_qty = float(self.max_edit.text() or 0)
            threshold = float(self.threshold_edit.text() or 0)

            if max_qty <= 0:
                raise ValueError("Maximum quantity must be greater than 0")
            if threshold < 0:
                raise ValueError("Top-up threshold cannot be negative")
            if threshold > max_qty:
                raise ValueError("Top-up threshold cannot be greater than maximum")

            self.result = {
                "name": name,
                "max": max_qty,
                "top_up_threshold": threshold,
                "usage_rate": self.usage_rate_combo.currentText().strip(),
                "consumption_per_day": float(self.consumption_edit.text() or 0.0),
                "exchange_payload": self.exchange_payload_combo.currentText().strip(),
                "source_location": (
                    self.selected_source_locations[0]
                    if self.selected_source_locations
                    else ""
                ),
            }

            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid tracked item", str(exc))


class PayloadEditorDialog(QDialog):

    def __init__(self, parent, seed=None, payload_names=None, location_names=None):
        super().__init__(parent)
        self.setWindowTitle("Payload")
        self.seed = seed or {}
        self.result = None
        self.tracked_items = self._normalise_tracked_items(self.seed.get("items", []))

        self.payload_names = sorted(payload_names or [])
        self.location_names = sorted(location_names or [])

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.name_edit = QLineEdit(str(self.seed.get("name", "")))
        self.weight_edit = QLineEdit(str(self.seed.get("weight_kg", 0.0)))
        self.length_edit = QLineEdit(str(self.seed.get("length_m", 0.0)))
        self.width_edit = QLineEdit(str(self.seed.get("width_m", 0.0)))
        self.height_edit = QLineEdit(str(self.seed.get("height_m", 0.0)))

        self.track_items_check = QCheckBox("Track items held within this payload")
        self.track_items_check.setChecked(bool(self.seed.get("track_items", False)))

        self.prefer_multi_stop_amr_check = QCheckBox(
            "Prefer multi-stop AMRs for this payload"
        )
        self.prefer_multi_stop_amr_check.setChecked(
            bool(self.seed.get("prefer_multi_stop_amr", False))
        )

        form.addRow("Payload name", self.name_edit)
        form.addRow("Weight kg", self.weight_edit)
        form.addRow("Length m", self.length_edit)
        form.addRow("Width m", self.width_edit)
        form.addRow("Height m", self.height_edit)
        form.addRow("Track items", self.track_items_check)
        form.addRow("Prefer multi-stop AMR", self.prefer_multi_stop_amr_check)

        layout.addWidget(QLabel("Tracked items"))

        self.items_table = QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(
            ["Name", "Max", "Top-up threshold", "Usage rate"]
        )
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.items_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        layout.addWidget(self.items_table, 1)

        item_buttons = QHBoxLayout()
        layout.addLayout(item_buttons)

        add_item_btn = QPushButton("Add item")
        edit_item_btn = QPushButton("Edit item")
        delete_item_btn = QPushButton("Delete item")

        add_item_btn.clicked.connect(self.add_tracked_item)
        edit_item_btn.clicked.connect(self.edit_tracked_item)
        delete_item_btn.clicked.connect(self.delete_tracked_item)

        item_buttons.addWidget(add_item_btn)
        item_buttons.addWidget(edit_item_btn)
        item_buttons.addWidget(delete_item_btn)
        item_buttons.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(760, 560)
        self._refresh_items_table()

    def _normalise_tracked_items(self, value):
        result = []

        # Supports both requested object form and easier list form.
        # Requested example:
        # "items": {
        #   "gloves": {"max": 100, "top_up_threshold": 15, "usage_rate": "scheduled_sporadic"}
        # }
        if isinstance(value, dict):
            iterable = []
            for name, cfg in value.items():
                cfg = dict(cfg or {})
                cfg["name"] = name
                iterable.append(cfg)
        else:
            iterable = list(value or [])

        for item in iterable:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name", "")).strip()
            if not name:
                continue

            result.append(
                {
                    "name": name,
                    "max": float(item.get("max", 100)),
                    "top_up_threshold": float(item.get("top_up_threshold", 15)),
                    "usage_rate": str(item.get("usage_rate", "scheduled_sporadic")),
                    "consumption_per_day": float(item.get("consumption_per_day", 0.0)),
                    "exchange_payload": str(item.get("exchange_payload", "")),
                    "source_location": str(item.get("source_location", "")),
                }
            )

        return result

    def _refresh_items_table(self):
        self.items_table.setRowCount(0)

        for item in self.tracked_items:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)

            values = [
                item.get("name", ""),
                item.get("max", 100),
                item.get("top_up_threshold", 15),
                item.get("usage_rate", "scheduled_sporadic"),
                item.get("consumption_per_day", 0.0),
                item.get("exchange_payload", ""),
                item.get("source_location", ""),
            ]

            for col, value in enumerate(values):
                self.items_table.setItem(row, col, QTableWidgetItem(str(value)))

    def add_tracked_item(self):
        dialog = PayloadTrackedItemDialog(
            self,
            payload_names=self.payload_names,
            location_names=self.location_names,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            name = dialog.result["name"]
            if any(str(x.get("name", "")).strip() == name for x in self.tracked_items):
                QMessageBox.critical(self, "Duplicate", "Tracked item already exists")
                return
            self.tracked_items.append(dialog.result)
            self._refresh_items_table()

    def edit_tracked_item(self):
        row = self.items_table.currentRow()
        if row < 0:
            return

        dialog = PayloadTrackedItemDialog(
            self,
            self.tracked_items[row],
            payload_names=self.payload_names,
            location_names=self.location_names,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            name = dialog.result["name"]
            for idx, item in enumerate(self.tracked_items):
                if idx != row and str(item.get("name", "")).strip() == name:
                    QMessageBox.critical(
                        self, "Duplicate", "Tracked item already exists"
                    )
                    return

            self.tracked_items[row] = dialog.result
            self._refresh_items_table()
            self.items_table.selectRow(row)

    def delete_tracked_item(self):
        row = self.items_table.currentRow()
        if row < 0:
            return
        del self.tracked_items[row]
        self._refresh_items_table()

    def accept(self):
        try:
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Payload name is required")

            items_payload = {
                item["name"]: {
                    "max": float(item.get("max", 100)),
                    "top_up_threshold": float(item.get("top_up_threshold", 15)),
                    "usage_rate": str(item.get("usage_rate", "scheduled_sporadic")),
                    "consumption_per_day": float(item.get("consumption_per_day", 0.0)),
                    "exchange_payload": str(item.get("exchange_payload", "")),
                    "source_location": str(item.get("source_location", "")),
                }
                for item in self.tracked_items
            }

            self.result = {
                "name": name,
                "weight_kg": float(self.weight_edit.text() or 0.0),
                "length_m": float(self.length_edit.text() or 0.0),
                "width_m": float(self.width_edit.text() or 0.0),
                "height_m": float(self.height_edit.text() or 0.0),
                "track_items": self.track_items_check.isChecked(),
                "prefer_multi_stop_amr": self.prefer_multi_stop_amr_check.isChecked(),
                "items": items_payload,
            }

            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid payload", str(exc))


class PayloadListDialog(QDialog):
    columns = [
        ("name", "Name", 180),
        ("weight_kg", "Weight kg", 90),
        ("length_m", "Length m", 90),
        ("width_m", "Width m", 90),
        ("height_m", "Height m", 90),
        ("track_items", "Track items", 90),
        ("prefer_multi_stop_amr", "Prefer multi-stop", 120),
        ("items", "Items", 260),
    ]

    def __init__(self, parent, items, on_save, location_names=None):
        super().__init__(parent)
        self.setWindowTitle("Payloads")
        self.resize(980, 520)
        self.items = [dict(x) for x in items]
        self.on_save = on_save
        self.location_names = sorted(location_names or [])

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

        layout.addWidget(self.table, 1)

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

    def _items_summary(self, payload):
        items = payload.get("items", {})
        if isinstance(items, dict):
            names = list(items.keys())
        else:
            names = [
                str(x.get("name", "")).strip()
                for x in items or []
                if isinstance(x, dict) and str(x.get("name", "")).strip()
            ]

        if not names:
            return ""

        if len(names) <= 3:
            return ", ".join(names)

        return ", ".join(names[:3]) + f", +{len(names) - 3} items"

    def _refresh_table(self):
        self.table.setRowCount(0)

        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                str(item.get("name", "")),
                str(item.get("weight_kg", "")),
                str(item.get("length_m", "")),
                str(item.get("width_m", "")),
                str(item.get("height_m", "")),
                "Yes" if item.get("track_items", False) else "No",
                "Yes" if item.get("prefer_multi_stop_amr", False) else "No",
                self._items_summary(item),
            ]

            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _suggest_next_payload_name(self):
        existing = {str(x.get("name", "")).strip() for x in self.items}
        base = "payload"
        if base not in existing:
            return base
        counter = 2
        while f"{base}_{counter}" in existing:
            counter += 1
        return f"{base}_{counter}"

    def add_item(self):
        dialog = PayloadEditorDialog(
            self,
            seed={"name": self._suggest_next_payload_name()},
            payload_names=[x.get("name", "") for x in self.items],
            location_names=self.location_names,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            name = dialog.result["name"]
            if any(str(x.get("name", "")).strip() == name for x in self.items):
                QMessageBox.critical(self, "Duplicate", "Payload already exists")
                return
            self.items.append(dialog.result)
            self._refresh_table()

    def edit_item(self):
        row = self.table.currentRow()
        if row < 0:
            return

        dialog = PayloadEditorDialog(
            self,
            seed=self.items[row],
            payload_names=[
                x.get("name", "") for idx, x in enumerate(self.items) if idx != row
            ],
            location_names=self.location_names,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            new_name = dialog.result["name"]
            for idx, item in enumerate(self.items):
                if idx != row and str(item.get("name", "")).strip() == new_name:
                    QMessageBox.critical(self, "Duplicate", "Payload already exists")
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


class AMRListDialog(QDialog):
    columns = [
        ("id", "ID", 120),
        ("quantity", "Qty", 70),
        ("payload_slot_summary", "Payload slots", 180),
        ("multi_stop_enabled", "Multi-stop", 90),
        ("manual_task_compatible", "Manual task", 100),
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
                if key == "payload_slot_summary":
                    value = _amr_payload_slot_summary(item)
                elif key == "manual_task_compatible":
                    value = (
                        "Yes" if len(_normalise_amr_payload_slots(item)) == 1 else "No"
                    )
                else:
                    value = item.get(key, "")
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

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


class SimulationSettingsDialog(QDialog):
    def __init__(self, parent, simulation=None):
        super().__init__(parent)
        self.setWindowTitle("Simulation settings")
        self.resize(720, 520)

        self.simulation = dict(simulation or {})
        simulation = self._normalise_simulation(self.simulation)
        self.result = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.start_datetime_edit = QLineEdit(
            str(simulation.get("start_datetime", "2026-01-05T06:00:00") or "")
        )
        self.end_datetime_edit = QLineEdit(
            str(simulation.get("end_datetime", "2026-01-06T06:00:00") or "")
        )
        self.tick_rate_edit = QLineEdit(str(simulation.get("tick_rate", 1000) or 1000))

        self.generated_stagger_edit = QLineEdit(
            str(simulation.get("generated_task_release_stagger_sec", 0.25))
        )

        self.precompute_routes_check = QCheckBox("Precompute static route cache")
        self.precompute_routes_check.setChecked(
            bool(simulation.get("precompute_static_routes", True))
        )

        self.route_precompute_max_pairs_edit = QLineEdit(
            str(simulation.get("route_precompute_max_pairs", 100000))
        )
        self.max_multi_stop_candidate_tasks_edit = QLineEdit(
            str(simulation.get("max_multi_stop_candidate_tasks", 8))
        )
        self.max_single_candidate_tasks_edit = QLineEdit(
            str(simulation.get("max_single_candidate_tasks", 8))
        )
        self.max_assignments_per_tick_edit = QLineEdit(
            str(simulation.get("max_assignments_per_tick", 25))
        )
        self.assignment_continue_delay_edit = QLineEdit(
            str(simulation.get("assignment_continue_delay_sec", 0.001))
        )

        form.addRow("Start datetime", self.start_datetime_edit)
        form.addRow("End datetime", self.end_datetime_edit)
        form.addRow("Tick rate", self.tick_rate_edit)
        form.addRow("Generated release stagger sec", self.generated_stagger_edit)
        form.addRow("Static route precompute", self.precompute_routes_check)
        form.addRow("Route precompute max pairs", self.route_precompute_max_pairs_edit)
        form.addRow("Max multi-stop candidate tasks", self.max_multi_stop_candidate_tasks_edit)
        form.addRow("Max single candidate tasks", self.max_single_candidate_tasks_edit)
        form.addRow("Max assignments per tick", self.max_assignments_per_tick_edit)
        form.addRow("Assignment continue delay sec", self.assignment_continue_delay_edit)

        help_label = QLabel(
            "Use ISO format, for example 2026-01-05T06:00:00. "
            "generated_task_release_stagger_sec spreads generated tasks that would "
            "otherwise release at the same instant. Static route precompute fills "
            "the route cache before the run. Candidate and assignment limits reduce "
            "large release bursts from blocking the simulator UI/event loop."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _normalise_simulation(self, simulation):
        result = dict(simulation or {})
        result.setdefault("start_datetime", "2026-01-05T06:00:00")
        result.setdefault("end_datetime", "2026-01-06T06:00:00")
        result.setdefault("tick_rate", 1000)
        result.setdefault("generated_task_release_stagger_sec", 0.25)
        result.setdefault("precompute_static_routes", True)
        result.setdefault("route_precompute_max_pairs", 100000)
        result.setdefault("max_multi_stop_candidate_tasks", 8)
        result.setdefault("max_single_candidate_tasks", 8)
        result.setdefault("max_assignments_per_tick", 25)
        result.setdefault("assignment_continue_delay_sec", 0.001)
        return result

    def _validate_datetime(self, value, field_name, allow_blank=False):
        text = str(value or "").strip()
        if not text and allow_blank:
            return ""
        if not text:
            raise ValueError(f"{field_name} is required")
        try:
            from datetime import datetime

            datetime.fromisoformat(text)
        except Exception:
            raise ValueError(
                f"{field_name} must use ISO format, e.g. 2026-01-05T06:00:00"
            )
        return text

    def _float_value(self, widget, field_name, minimum=None, allow_zero=True):
        try:
            value = float(widget.text() or 0.0)
        except Exception:
            raise ValueError(f"{field_name} must be a number")

        if minimum is not None:
            if allow_zero and value == 0:
                return value
            if value < minimum:
                raise ValueError(f"{field_name} must be at least {minimum}")
        return value

    def _int_value(self, widget, field_name, minimum=None):
        try:
            value = int(float(widget.text() or 0))
        except Exception:
            raise ValueError(f"{field_name} must be a whole number")
        if minimum is not None and value < minimum:
            raise ValueError(f"{field_name} must be at least {minimum}")
        return value

    def accept(self):
        try:
            start_datetime = self._validate_datetime(
                self.start_datetime_edit.text(), "Start datetime"
            )
            end_datetime = self._validate_datetime(
                self.end_datetime_edit.text(), "End datetime", allow_blank=True
            )
            tick_rate = self._float_value(
                self.tick_rate_edit, "Tick rate", minimum=0.0, allow_zero=False
            )

            if end_datetime:
                from datetime import datetime

                if datetime.fromisoformat(end_datetime) <= datetime.fromisoformat(
                    start_datetime
                ):
                    raise ValueError("End datetime must be after the start datetime")

            generated_stagger = self._float_value(
                self.generated_stagger_edit,
                "Generated release stagger seconds",
                minimum=0.0,
                allow_zero=True,
            )
            route_precompute_max_pairs = self._int_value(
                self.route_precompute_max_pairs_edit,
                "Route precompute max pairs",
                minimum=0,
            )
            max_multi_stop_candidate_tasks = self._int_value(
                self.max_multi_stop_candidate_tasks_edit,
                "Max multi-stop candidate tasks",
                minimum=1,
            )
            max_single_candidate_tasks = self._int_value(
                self.max_single_candidate_tasks_edit,
                "Max single candidate tasks",
                minimum=1,
            )
            max_assignments_per_tick = self._int_value(
                self.max_assignments_per_tick_edit,
                "Max assignments per tick",
                minimum=1,
            )
            assignment_continue_delay = self._float_value(
                self.assignment_continue_delay_edit,
                "Assignment continue delay seconds",
                minimum=0.0,
                allow_zero=True,
            )

            result = dict(self.simulation)
            result.update(
                {
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "tick_rate": tick_rate,
                    "generated_task_release_stagger_sec": generated_stagger,
                    "precompute_static_routes": self.precompute_routes_check.isChecked(),
                    "route_precompute_max_pairs": route_precompute_max_pairs,
                    "max_multi_stop_candidate_tasks": max_multi_stop_candidate_tasks,
                    "max_single_candidate_tasks": max_single_candidate_tasks,
                    "max_assignments_per_tick": max_assignments_per_tick,
                    "assignment_continue_delay_sec": assignment_continue_delay,
                }
            )

            self.result = result
        except Exception as exc:
            QMessageBox.warning(self, "Invalid simulation settings", str(exc))
            return

        super().accept()


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


class BulkDepartmentWasteStreamControlDialog(QDialog):
    """Bulk add/remove/edit department waste streams for selected departments.

    Checked      = assign/update the stream on every selected department.
    Unchecked    = remove the stream from every selected department.
    Part checked = leave mixed existing assignments unchanged.
    """

    MODES = [
        "scheduled",
        "threshold",
        "continuous",
        "sporadic",
        "hybrid",
        "scheduled_threshold",
        "scheduled_sporadic",
    ]

    DEFAULT_STREAM_SETTINGS = {
        "generation_mode": "threshold",
        "frequency_per_day": 0.0,
        "volume_per_event_m3": 0.0,
        "threshold_volume_m3": 0.0,
        "base_daily_volume_m3": 0.0,
        "scheduled_times": [],
    }

    def __init__(self, parent, waste_stream_names, departments):
        super().__init__(parent)
        self.setWindowTitle("Manage waste streams for selected departments")
        self.resize(1180, 650)

        self.global_waste_stream_names = {
            str(x).strip() for x in waste_stream_names if str(x).strip()
        }
        self.departments = [dict(x) for x in departments or []]

        # Include deleted/orphaned stream names that still exist on the selected
        # departments. They must remain visible so they can be unchecked and
        # removed even after the global waste stream definition has been deleted.
        assigned_names = set()
        for dept in self.departments:
            assigned_names.update(self._stream_names_for_department(dept))

        self.waste_stream_names = sorted(
            self.global_waste_stream_names | assigned_names
        )
        self.orphan_waste_stream_names = sorted(
            assigned_names - self.global_waste_stream_names
        )
        self.result = None
        self._row_widgets = {}

        layout = QVBoxLayout(self)

        help_label = QLabel(
            "Tick a stream to assign it to all selected departments. "
            "Untick a stream to remove it from all selected departments. "
            "A partially ticked stream is currently assigned to only some departments; "
            "leave it partially ticked to make no assignment/settings change. "
            "For checked streams, the generation settings below are applied to every "
            "selected department at the same time. Deleted/orphaned streams are shown "
            "so they can be unchecked and removed."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTreeWidget()
        self.table.setColumnCount(10)
        self.table.setHeaderLabels(
            [
                "Waste stream",
                "Status",
                "Currently assigned",
                "Bulk action",
                "Generation mode",
                "Frequency / day",
                "Volume / event m³",
                "Threshold m³",
                "Base daily m³",
                "Scheduled times",
            ]
        )
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table, 1)

        tools = QHBoxLayout()
        layout.addLayout(tools)

        check_all_btn = QPushButton("Assign all")
        clear_all_btn = QPushButton("Remove all")
        unchanged_btn = QPushButton("Leave mixed unchanged")

        check_all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        clear_all_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        unchanged_btn.clicked.connect(self._restore_partial_states)

        tools.addWidget(check_all_btn)
        tools.addWidget(clear_all_btn)
        tools.addWidget(unchanged_btn)
        tools.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._initial_partial_streams = set()
        self._refresh_table()

    def _stream_names_for_department(self, dept):
        names = set()
        for item in dept.get("waste_streams", []) or []:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
            else:
                name = str(item).strip()
            if name:
                names.add(name)
        return names

    def _normalise_stream_item(self, item):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if not name:
                return None
            return {
                "name": name,
                "generation_mode": str(
                    item.get(
                        "generation_mode",
                        self.DEFAULT_STREAM_SETTINGS["generation_mode"],
                    )
                    or self.DEFAULT_STREAM_SETTINGS["generation_mode"]
                ),
                "frequency_per_day": float(item.get("frequency_per_day", 0.0) or 0.0),
                "volume_per_event_m3": float(
                    item.get("volume_per_event_m3", 0.0) or 0.0
                ),
                "threshold_volume_m3": float(
                    item.get("threshold_volume_m3", 0.0) or 0.0
                ),
                "base_daily_volume_m3": float(
                    item.get("base_daily_volume_m3", 0.0) or 0.0
                ),
                "scheduled_times": list(item.get("scheduled_times", []) or []),
            }

        name = str(item).strip()
        if not name:
            return None
        return {"name": name, **self.DEFAULT_STREAM_SETTINGS}

    def _first_settings_for_stream(self, stream_name):
        """Use the first existing department settings as the edit seed."""
        for dept in self.departments:
            for item in dept.get("waste_streams", []) or []:
                normalised = self._normalise_stream_item(item)
                if not normalised:
                    continue
                if str(normalised.get("name", "")).strip() == stream_name:
                    return normalised
        return {"name": stream_name, **self.DEFAULT_STREAM_SETTINGS}

    def _make_number_edit(self, value):
        edit = QLineEdit(str(value))
        edit.setMinimumWidth(90)
        return edit

    def _refresh_table(self):
        self.table.clear()
        self._row_widgets = {}
        self._initial_partial_streams = set()

        dept_count = len(self.departments)
        orphan_count = len(self.orphan_waste_stream_names)
        if orphan_count:
            self.summary_label.setText(
                f"Selected departments: {dept_count} | "
                f"Deleted/orphaned assigned streams: {orphan_count}"
            )
        else:
            self.summary_label.setText(f"Selected departments: {dept_count}")

        for stream_name in self.waste_stream_names:
            assigned_count = sum(
                1
                for dept in self.departments
                if stream_name in self._stream_names_for_department(dept)
            )

            is_orphan = stream_name not in self.global_waste_stream_names
            item = QTreeWidgetItem(
                [
                    stream_name,
                    (
                        "Deleted / not in global waste streams"
                        if is_orphan
                        else "Configured"
                    ),
                    f"{assigned_count} / {dept_count}",
                    (
                        "Preserve or remove"
                        if is_orphan
                        else (
                            "Apply settings to all"
                            if assigned_count == dept_count and dept_count > 0
                            else (
                                "Assign/update all"
                                if assigned_count == 0
                                else "Mixed - leave unchanged unless checked/unchecked"
                            )
                        )
                    ),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            item.setData(0, Qt.UserRole, stream_name)
            item.setFlags(
                item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )

            if assigned_count <= 0:
                state = Qt.Unchecked
            elif assigned_count >= dept_count:
                state = Qt.Checked
            else:
                state = Qt.PartiallyChecked
                self._initial_partial_streams.add(stream_name)

            item.setCheckState(0, state)
            self.table.addTopLevelItem(item)

            seed = self._first_settings_for_stream(stream_name)
            mode_combo = QComboBox()
            mode_combo.addItems(self.MODES)
            mode = str(seed.get("generation_mode", "threshold") or "threshold")
            if mode not in self.MODES:
                mode = "threshold"
            mode_combo.setCurrentText(mode)

            frequency_edit = self._make_number_edit(seed.get("frequency_per_day", 0.0))
            volume_edit = self._make_number_edit(seed.get("volume_per_event_m3", 0.0))
            threshold_edit = self._make_number_edit(
                seed.get("threshold_volume_m3", 0.0)
            )
            base_daily_edit = self._make_number_edit(
                seed.get("base_daily_volume_m3", 0.0)
            )

            scheduled_times = list(seed.get("scheduled_times", []) or [])
            schedule_label = QLabel()
            schedule_label.setWordWrap(True)
            edit_times_btn = QPushButton("Edit...")
            clear_times_btn = QPushButton("Clear")

            schedule_widget = QWidget()
            schedule_row = QHBoxLayout(schedule_widget)
            schedule_row.setContentsMargins(0, 0, 0, 0)
            schedule_row.addWidget(schedule_label, 1)
            schedule_row.addWidget(edit_times_btn)
            schedule_row.addWidget(clear_times_btn)

            self._row_widgets[stream_name] = {
                "mode_combo": mode_combo,
                "frequency_edit": frequency_edit,
                "volume_edit": volume_edit,
                "threshold_edit": threshold_edit,
                "base_daily_edit": base_daily_edit,
                "scheduled_times": scheduled_times,
                "schedule_label": schedule_label,
                "edit_times_btn": edit_times_btn,
                "clear_times_btn": clear_times_btn,
            }

            edit_times_btn.clicked.connect(
                lambda _checked=False, name=stream_name: self._edit_times_for_stream(
                    name
                )
            )
            clear_times_btn.clicked.connect(
                lambda _checked=False, name=stream_name: self._clear_times_for_stream(
                    name
                )
            )
            mode_combo.currentTextChanged.connect(
                lambda _value, name=stream_name: self._update_stream_field_state(name)
            )

            self.table.setItemWidget(item, 4, mode_combo)
            self.table.setItemWidget(item, 5, frequency_edit)
            self.table.setItemWidget(item, 6, volume_edit)
            self.table.setItemWidget(item, 7, threshold_edit)
            self.table.setItemWidget(item, 8, base_daily_edit)
            self.table.setItemWidget(item, 9, schedule_widget)

            self._refresh_schedule_summary(stream_name)
            self._update_stream_field_state(stream_name)

            if is_orphan:
                # Orphaned stream definitions no longer exist globally. They can
                # be preserved or removed, but not bulk-edited/reassigned.
                for widget in (
                    mode_combo,
                    frequency_edit,
                    volume_edit,
                    threshold_edit,
                    base_daily_edit,
                    edit_times_btn,
                    clear_times_btn,
                ):
                    widget.setEnabled(False)
                schedule_label.setEnabled(False)

        for col in range(self.table.columnCount()):
            self.table.resizeColumnToContents(col)

    def _set_all(self, state):
        for idx in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(idx)
            item.setCheckState(0, state)

    def _restore_partial_states(self):
        for idx in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(idx)
            stream_name = str(item.data(0, Qt.UserRole) or "").strip()
            if stream_name in self._initial_partial_streams:
                item.setCheckState(0, Qt.PartiallyChecked)

    def _refresh_schedule_summary(self, stream_name):
        widgets = self._row_widgets.get(stream_name, {})
        label = widgets.get("schedule_label")
        if label is None:
            return
        times = list(widgets.get("scheduled_times", []) or [])
        if not times:
            label.setText("No times")
        elif len(times) <= 3:
            label.setText(", ".join(times))
        else:
            label.setText(f"{len(times)} times")

    def _edit_times_for_stream(self, stream_name):
        widgets = self._row_widgets.get(stream_name, {})
        dialog = ScheduledTimesDialog(self, widgets.get("scheduled_times", []))
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            widgets["scheduled_times"] = list(dialog.result)
            self._refresh_schedule_summary(stream_name)

    def _clear_times_for_stream(self, stream_name):
        widgets = self._row_widgets.get(stream_name, {})
        widgets["scheduled_times"] = []
        self._refresh_schedule_summary(stream_name)

    def _update_stream_field_state(self, stream_name):
        widgets = self._row_widgets.get(stream_name, {})
        mode_combo = widgets.get("mode_combo")
        if mode_combo is None:
            return

        mode = mode_combo.currentText().strip()
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

        for key in ("schedule_label", "edit_times_btn", "clear_times_btn"):
            widget = widgets.get(key)
            if widget is not None:
                widget.setEnabled(uses_schedule)

        if widgets.get("threshold_edit") is not None:
            widgets["threshold_edit"].setEnabled(uses_threshold)
        if widgets.get("base_daily_edit") is not None:
            widgets["base_daily_edit"].setEnabled(uses_continuous or uses_threshold)
        if widgets.get("frequency_edit") is not None:
            widgets["frequency_edit"].setEnabled(uses_sporadic)
        if widgets.get("volume_edit") is not None:
            widgets["volume_edit"].setEnabled(uses_sporadic)

    def _settings_for_stream(self, stream_name):
        widgets = self._row_widgets.get(stream_name, {})
        return {
            "generation_mode": widgets["mode_combo"].currentText().strip(),
            "frequency_per_day": float(widgets["frequency_edit"].text() or 0.0),
            "volume_per_event_m3": float(widgets["volume_edit"].text() or 0.0),
            "threshold_volume_m3": float(widgets["threshold_edit"].text() or 0.0),
            "base_daily_volume_m3": float(widgets["base_daily_edit"].text() or 0.0),
            "scheduled_times": list(widgets.get("scheduled_times", []) or []),
        }

    def accept(self):
        add_streams = []
        remove_streams = []
        unchanged_streams = []
        update_stream_settings = {}

        try:
            for idx in range(self.table.topLevelItemCount()):
                item = self.table.topLevelItem(idx)
                stream_name = str(item.data(0, Qt.UserRole) or "").strip()
                if not stream_name:
                    continue

                state = item.checkState(0)
                is_orphan = stream_name not in self.global_waste_stream_names
                if state == Qt.Checked:
                    # Orphaned/deleted streams cannot be newly assigned or edited
                    # because there is no global stream definition to back them.
                    # Keeping them checked means preserve existing assignments.
                    if is_orphan:
                        unchanged_streams.append(stream_name)
                    else:
                        add_streams.append(stream_name)
                        update_stream_settings[stream_name] = self._settings_for_stream(
                            stream_name
                        )
                elif state == Qt.Unchecked:
                    remove_streams.append(stream_name)
                else:
                    unchanged_streams.append(stream_name)
        except Exception as exc:
            QMessageBox.critical(self, "Invalid waste stream settings", str(exc))
            return

        self.result = {
            "add_streams": add_streams,
            "remove_streams": remove_streams,
            "unchanged_streams": unchanged_streams,
            "update_stream_settings": update_stream_settings,
        }
        super().accept()


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

        self.table = QTreeWidget()
        self.table.setColumnCount(8)
        self.table.setHeaderLabels(
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
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _item, _col: self.edit_item())
        self.table.header().setSectionResizeMode(QHeaderView.Interactive)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        layout.addLayout(row)

        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        del_btn = QPushButton("Delete")
        save_btn = QPushButton("Save")

        auto_assign_btn = QPushButton("Auto assign locations")
        bulk_waste_btn = QPushButton("Manage waste streams...")

        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(del_btn)
        row.addWidget(auto_assign_btn)
        row.addWidget(bulk_waste_btn)
        row.addStretch(1)
        row.addWidget(save_btn)

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        del_btn.clicked.connect(self.delete_item)
        auto_assign_btn.clicked.connect(self.auto_assign_locations)
        bulk_waste_btn.clicked.connect(
            self.manage_waste_streams_for_selected_departments
        )
        save_btn.clicked.connect(self.save_items)

        self._refresh_table()

    def _refresh_table(self):
        self.table.clear()
        self._tree_item_to_index = {}

        grouped = {}

        for idx, item in enumerate(self.items):
            try:
                floor = int(item.get("floor", 0))
            except Exception:
                floor = 0
            grouped.setdefault(floor, []).append((idx, item))

        for floor in sorted(grouped.keys()):
            floor_item = QTreeWidgetItem([f"Floor {floor}", "", "", "", "", "", "", ""])
            floor_item.setFirstColumnSpanned(True)
            floor_item.setExpanded(True)
            self.table.addTopLevelItem(floor_item)

            grouped[floor].sort(
                key=lambda pair: (
                    str(pair[1].get("name", "")).strip().lower()
                    or str(pair[1].get("id", "")).strip().lower()
                )
            )

            for idx, item in grouped[floor]:
                waste_text = ", ".join(
                    x.get("name", str(x)) if isinstance(x, dict) else str(x)
                    for x in item.get("waste_streams", [])
                )

                child = QTreeWidgetItem(
                    [
                        str(item.get("id", "")),
                        str(item.get("name", "")),
                        str(item.get("floor", "")),
                        "Yes" if item.get("enabled", True) else "No",
                        str(item.get("bed_count", 0)),
                        str(item.get("patient_turnover", 0.0)),
                        str(item.get("staff_count", 0)),
                        waste_text,
                    ]
                )

                child.setData(0, Qt.UserRole, idx)
                floor_item.addChild(child)
                self._tree_item_to_index[id(child)] = idx

        for col in range(self.table.columnCount()):
            self.table.resizeColumnToContents(col)

    def _selected_department_indexes(self):
        indexes = []

        for item in self.table.selectedItems():
            idx = item.data(0, Qt.UserRole)
            if idx is None:
                continue
            try:
                indexes.append(int(idx))
            except Exception:
                continue

        return sorted(set(indexes))

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
                        "frequency_per_day": float(
                            item.get("frequency_per_day", 0.0) or 0.0
                        ),
                        "volume_per_event_m3": float(
                            item.get("volume_per_event_m3", 0.0) or 0.0
                        ),
                        "threshold_volume_m3": float(
                            item.get("threshold_volume_m3", 0.0) or 0.0
                        ),
                        "base_daily_volume_m3": float(
                            item.get("base_daily_volume_m3", 0.0) or 0.0
                        ),
                        "scheduled_times": list(item.get("scheduled_times", []) or []),
                    }
                )
                continue

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

        # De-duplicate while preserving the first existing settings for each stream.
        seen = set()
        clean = []
        for item in result:
            name = str(item.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            clean.append(item)
        return clean

    def manage_waste_streams_for_selected_departments(self):
        rows = self._selected_department_indexes()

        if not rows:
            QMessageBox.information(
                self,
                "Manage waste streams",
                "Select one or more departments first.",
            )
            return

        selected_departments = [
            self.items[row] for row in rows if 0 <= row < len(self.items)
        ]

        if not selected_departments:
            return

        selected_assigned_streams = set()
        for dept in selected_departments:
            for item in dept.get("waste_streams", []) or []:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                else:
                    name = str(item).strip()
                if name:
                    selected_assigned_streams.add(name)

        if not self.waste_stream_names and not selected_assigned_streams:
            QMessageBox.information(
                self,
                "Manage waste streams",
                "No global or currently assigned waste streams are available.",
            )
            return

        dialog = BulkDepartmentWasteStreamControlDialog(
            self,
            waste_stream_names=self.waste_stream_names,
            departments=selected_departments,
        )

        if dialog.exec() != QDialog.Accepted or not dialog.result:
            return

        add_streams = {
            str(x).strip()
            for x in dialog.result.get("add_streams", [])
            if str(x).strip()
        }
        remove_streams = {
            str(x).strip()
            for x in dialog.result.get("remove_streams", [])
            if str(x).strip()
        }
        update_stream_settings = {
            str(name).strip(): dict(settings or {})
            for name, settings in (
                dialog.result.get("update_stream_settings", {}) or {}
            ).items()
            if str(name).strip()
        }

        if not add_streams and not remove_streams and not update_stream_settings:
            return

        added_count = 0
        removed_count = 0
        updated_count = 0

        for row in rows:
            if row < 0 or row >= len(self.items):
                continue

            dept = self.items[row]
            existing_items = self._normalise_department_waste_streams(
                dept.get("waste_streams", [])
            )

            filtered_items = []
            existing_names = set()

            for item in existing_items:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                if name in remove_streams:
                    removed_count += 1
                    continue

                if name in update_stream_settings:
                    updated_item = dict(item)
                    updated_item.update(update_stream_settings[name])
                    updated_item["name"] = name
                    filtered_items.append(updated_item)
                    updated_count += 1
                else:
                    filtered_items.append(item)

                existing_names.add(name)

            for stream_name in sorted(add_streams):
                if stream_name in existing_names:
                    continue
                settings = dict(
                    update_stream_settings.get(
                        stream_name,
                        BulkDepartmentWasteStreamControlDialog.DEFAULT_STREAM_SETTINGS,
                    )
                )
                filtered_items.append({"name": stream_name, **settings})
                existing_names.add(stream_name)
                added_count += 1
                updated_count += 1

            dept["waste_streams"] = filtered_items

        self._refresh_table()

        QMessageBox.information(
            self,
            "Manage waste streams",
            (
                f"Updated {len(rows)} selected department(s).\n"
                f"Added {added_count} waste stream assignment(s).\n"
                f"Removed {removed_count} waste stream assignment(s).\n"
                f"Applied generation settings to {updated_count} department stream assignment(s)."
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
        indexes = self._selected_department_indexes()
        if not indexes:
            return

        row = indexes[0]

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

    def delete_item(self):
        indexes = self._selected_department_indexes()
        if not indexes:
            return

        if (
            QMessageBox.question(
                self,
                "Delete departments",
                f"Delete {len(indexes)} selected department(s)?",
            )
            != QMessageBox.Yes
        ):
            return

        for idx in reversed(indexes):
            if 0 <= idx < len(self.items):
                del self.items[idx]

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
        self.selected_space_indices = set()
        self.rotate_space_index = None
        self.rotate_start_center = None
        self.drag_point_index = None
        self.drag_whole_space = False
        self.drag_start_world = None
        self.drag_start_points = []
        self.drag_payload_index = None
        self.drag_payload_start_world = None
        self.drag_payload_start = None
        self.drag_space_indices = set()
        self.drag_spaces_start_world = None
        self.drag_spaces_start_slots = {}
        self.drag_space_indices = set()
        self.drag_spaces_start_world = None
        self.drag_spaces_start_slots = {}
        self.rotate_space_index = None
        self.rotate_start_center = None
        self.copied_space = None
        self._initial_fit_done = False
        self.selected_payload_index = None
        self.drag_payload_index = None
        self.drag_payload_start_world = None
        self.drag_payload_start = None
        self.drag_space_indices = set()
        self.drag_spaces_start_world = None
        self.drag_spaces_start_slots = {}

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        layout.addLayout(left, 0)

        self.space_list = QListWidget()
        self.space_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.space_list.currentRowChanged.connect(self.select_space)
        self.space_list.itemSelectionChanged.connect(self._sync_space_list_selection)
        self.space_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.space_list.customContextMenuRequested.connect(self._show_space_list_menu)

        left.addWidget(QLabel("Inventory spaces"))
        left.addWidget(self.space_list, 1)

        add_btn = QPushButton("New space")
        add_btn.setVisible(False)
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
        self.rectangle_snap_check.setVisible(False)
        right.addWidget(self.rectangle_snap_check)

        size_row = QHBoxLayout()

        self.length_edit = QLineEdit("0.000")
        self.width_edit = QLineEdit("0.000")
        self.lock_size_check = QCheckBox("Lock size")

        self.length_edit.setReadOnly(True)
        self.width_edit.setReadOnly(True)
        self.length_edit.editingFinished.connect(self._apply_size_from_fields)
        self.width_edit.editingFinished.connect(self._apply_size_from_fields)

        size_row.addWidget(QLabel("Length"))
        size_row.addWidget(self.length_edit)
        size_row.addWidget(QLabel("Width"))
        size_row.addWidget(self.width_edit)
        size_row.addWidget(self.lock_size_check)

        right.addLayout(size_row)

        rotate_row = QHBoxLayout()
        self.rotation_edit = QLineEdit("0.0")
        self.rotation_edit.setToolTip(
            "Free-angle rotation in degrees for the selected payload inventory space"
        )
        self.rotation_edit.editingFinished.connect(self.apply_rotation_from_field)
        rotate_left_btn = QPushButton("-5°")
        rotate_right_btn = QPushButton("+5°")
        rotate_left_btn.clicked.connect(lambda: self.nudge_selected_rotation(-5.0))
        rotate_right_btn.clicked.connect(lambda: self.nudge_selected_rotation(5.0))
        rotate_row.addWidget(QLabel("Rotation °"))
        rotate_row.addWidget(self.rotation_edit)
        rotate_row.addWidget(rotate_left_btn)
        rotate_row.addWidget(rotate_right_btn)
        right.addLayout(rotate_row)

        payload_tools = QHBoxLayout()
        self.payload_combo = QComboBox()
        self.payload_combo.addItems([""] + self._payload_names())
        add_payload_btn = QPushButton("Add payload")
        auto_align_btn = QPushButton("Auto align")
        add_payload_btn.clicked.connect(self.add_payload_slot)
        auto_align_btn.clicked.connect(self.auto_align_payloads)
        payload_tools.addWidget(QLabel("Payload"))
        payload_tools.addWidget(self.payload_combo, 1)
        payload_tools.addWidget(add_payload_btn)
        payload_tools.addWidget(auto_align_btn)
        right.addLayout(payload_tools)

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
            "Inventory spaces are payload footprints only. Use Add payload to create a fixed-size space, drag to position it, or drag the rotate handle / enter an angle for free rotation."
        )
        right.addWidget(self.status_label)

        self.refresh_list()
        self.refresh_scene()

    def _sync_space_list_selection(self):
        rows = set()
        for item in self.space_list.selectedItems():
            row = self.space_list.row(item)
            if row >= 0:
                rows.add(row)
        if rows:
            self.selected_space_indices = rows
        elif self.selected_space_index is not None:
            self.selected_space_indices = {self.selected_space_index}
        self.refresh_scene()

    def _set_space_selection(self, indices, current_index=None):
        clean = {int(i) for i in indices if 0 <= int(i) < len(self.spaces)}
        if current_index is not None and 0 <= int(current_index) < len(self.spaces):
            clean.add(int(current_index))
            self.selected_space_index = int(current_index)
        self.selected_space_indices = clean

        self.space_list.blockSignals(True)
        self.space_list.clearSelection()
        for index in sorted(clean):
            item = self.space_list.item(index)
            if item is not None:
                item.setSelected(True)
        if (
            self.selected_space_index is not None
            and 0 <= self.selected_space_index < self.space_list.count()
        ):
            self.space_list.setCurrentRow(self.selected_space_index)
        self.space_list.blockSignals(False)

    def _space_payload_slot(self, index):
        if not (0 <= int(index) < len(self.spaces)):
            return None
        slots = self.spaces[int(index)].setdefault("payload_slots", [])
        return slots[0] if slots else None

    def _space_slot_polygon_points(self, index):
        slot = self._space_payload_slot(index)
        if not slot:
            return []
        return self._slot_polygon_points(slot)

    def _nearest_space_index_at(self, x, y):
        for index in reversed(range(len(self.spaces))):
            pts = self._space_slot_polygon_points(index)
            if pts and self._point_in_polygon(x, y, pts):
                return index
            pts_abs = self.store.inventory_space_points_absolute(
                self.location_name, self.spaces[index]
            )
            if pts_abs and self._point_in_polygon(x, y, pts_abs):
                return index
        return None

    def _space_group_fits_location_box(self, starts, dx, dy):
        location_box = self.store.get_location_bounding_box_points(self.location_name)
        if len(location_box) < 3:
            return True
        for index, slot_start in starts.items():
            candidate = dict(slot_start)
            sx, sy = self._slot_center_absolute(slot_start)
            self._set_slot_center_absolute(candidate, sx + dx, sy + dy)
            for p in self._slot_polygon_points(candidate):
                if not self._point_in_polygon(p["x"], p["y"], location_box):
                    return False
        return True

    def _move_space_group(self, starts, dx, dy):
        if not self._space_group_fits_location_box(starts, dx, dy):
            return False
        for index, slot_start in starts.items():
            slot = self._space_payload_slot(index)
            if not slot:
                continue
            sx, sy = self._slot_center_absolute(slot_start)
            candidate = dict(slot_start)
            self._set_slot_center_absolute(candidate, sx + dx, sy + dy)
            slot.update(candidate)
            self._sync_space_from_payload_index(index)
        return True

    def _payload_names(self):
        return sorted(
            str(p.get("name", "")).strip()
            for p in self.store.data.get("payloads", [])
            if str(p.get("name", "")).strip()
        )

    def _payload_by_name(self, name):
        name = str(name or "").strip()
        for payload in self.store.data.get("payloads", []):
            if str(payload.get("name", "")).strip() == name:
                return payload
        return None

    def _payload_dimensions(self, name):
        payload = self._payload_by_name(name)
        if not payload:
            return 0.0, 0.0
        length = float(payload.get("length_m", 0.0) or 0.0)
        width = float(payload.get("width_m", 0.0) or 0.0)
        return max(0.0, length), max(0.0, width)

    def _current_space_slots(self):
        if self.selected_space_index is None:
            return []
        if 0 <= self.selected_space_index < len(self.spaces):
            return self.spaces[self.selected_space_index].setdefault(
                "payload_slots", []
            )
        return []

    def _space_bounds(self):
        if not self.current_points:
            return None
        xs = [float(p["x"]) for p in self.current_points]
        ys = [float(p["y"]) for p in self.current_points]
        return min(xs), min(ys), max(xs), max(ys)

    def _slot_center_absolute(self, slot):
        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        if "dx" in slot and "dy" in slot:
            return lx + float(slot.get("dx", 0.0)), ly + float(slot.get("dy", 0.0))
        return float(slot.get("x", lx)), float(slot.get("y", ly))

    def _set_slot_center_absolute(self, slot, x, y):
        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        slot["dx"] = round(float(x) - lx, 3)
        slot["dy"] = round(float(y) - ly, 3)
        slot.pop("x", None)
        slot.pop("y", None)

    def _payload_slot_rect_points(self, slot, padding=0.0):
        payload_name = str(slot.get("payload", "")).strip()
        length, width = self._payload_dimensions(payload_name)
        if length <= 0 or width <= 0:
            return []
        cx, cy = self._slot_center_absolute(slot)
        rotation = float(slot.get("rotation_deg", 0.0) or 0.0) % 180.0
        # Inventory space footprint follows the fixed payload size.  A 90°
        # rotation swaps the axis-aligned stored footprint so the simulator and
        # reports see the same usable inventory rectangle that the user sees.
        if abs(rotation - 90.0) < 1e-6:
            length, width = width, length
        length += float(padding) * 2.0
        width += float(padding) * 2.0
        return [
            {"x": round(cx - (length / 2.0), 3), "y": round(cy - (width / 2.0), 3)},
            {"x": round(cx + (length / 2.0), 3), "y": round(cy - (width / 2.0), 3)},
            {"x": round(cx + (length / 2.0), 3), "y": round(cy + (width / 2.0), 3)},
            {"x": round(cx - (length / 2.0), 3), "y": round(cy + (width / 2.0), 3)},
        ]

    def _sync_current_space_from_payload(self):
        slots = self._current_space_slots()
        if not slots:
            return False
        points = self._slot_polygon_points(slots[0])
        if len(points) < 3:
            return False
        self.current_points = points
        return True

    def _commit_current_space(self, show_errors=False):
        if self.selected_space_index is None:
            return True
        if not (0 <= self.selected_space_index < len(self.spaces)):
            return True

        # For payload-only spaces, the stored space polygon is always derived
        # from the payload slot.
        self._sync_current_space_from_payload()

        if len(self.current_points) < 3:
            if show_errors:
                QMessageBox.critical(
                    self,
                    "Invalid inventory space",
                    "Inventory spaces must be created from a payload footprint.",
                )
            return False

        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        name = self.name_edit.text().strip() or self.spaces[
            self.selected_space_index
        ].get("name", f"Inventory {self.selected_space_index + 1}")
        self.spaces[self.selected_space_index] = {
            "name": name,
            "points": [
                {
                    "dx": round(float(p["x"]) - lx, 3),
                    "dy": round(float(p["y"]) - ly, 3),
                }
                for p in self.current_points
            ],
            "payload_slots": [
                dict(slot)
                for slot in self.spaces[self.selected_space_index].get(
                    "payload_slots", []
                )
            ],
        }
        return True

    def _slot_polygon_points(self, slot):
        payload_name = str(slot.get("payload", "")).strip()
        length, width = self._payload_dimensions(payload_name)
        if length <= 0 or width <= 0:
            return []
        cx, cy = self._slot_center_absolute(slot)
        angle = math.radians(float(slot.get("rotation_deg", 0.0) or 0.0))
        c = math.cos(angle)
        s = math.sin(angle)
        corners = [
            (-length / 2.0, -width / 2.0),
            (length / 2.0, -width / 2.0),
            (length / 2.0, width / 2.0),
            (-length / 2.0, width / 2.0),
        ]
        return [
            {
                "x": round(cx + (dx * c) - (dy * s), 3),
                "y": round(cy + (dx * s) + (dy * c), 3),
            }
            for dx, dy in corners
        ]

    def _point_in_polygon(self, x, y, points):
        if len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi = float(points[i]["x"])
            yi = float(points[i]["y"])
            xj = float(points[j]["x"])
            yj = float(points[j]["y"])
            if ((yi > y) != (yj > y)) and (
                x < ((xj - xi) * (y - yi) / ((yj - yi) or 1e-9)) + xi
            ):
                inside = not inside
            j = i
        return inside

    def _slot_contains_point(self, slot, x, y):
        return self._point_in_polygon(x, y, self._slot_polygon_points(slot))

    def _nearest_payload_slot_index(self, x, y):
        for idx in reversed(range(len(self._current_space_slots()))):
            if self._slot_contains_point(self._current_space_slots()[idx], x, y):
                return idx
        return None

    def _slot_fits_current_space(self, slot):
        if not self.current_points:
            return True
        return all(
            self._point_in_polygon(p["x"], p["y"], self.current_points)
            for p in self._slot_polygon_points(slot)
        )

    def add_payload_slot(self):
        payload_name = self.payload_combo.currentText().strip()
        if not payload_name:
            QMessageBox.information(self, "Payload", "Select a payload first.")
            return

        length, width = self._payload_dimensions(payload_name)
        if length <= 0 or width <= 0:
            QMessageBox.critical(
                self,
                "Payload",
                "Payload length and width must be greater than zero.",
            )
            return

        # Add payload now creates a dedicated inventory space that is exactly
        # the fixed footprint of the selected payload.  The payload slot is
        # centred inside that space, so it can still be moved/rotated with the
        # existing payload-edit tools if required.
        cx, cy = self._next_payload_space_centre(length, width)
        min_x = cx - (length / 2.0)
        min_y = cy - (width / 2.0)
        max_x = cx + (length / 2.0)
        max_y = cy + (width / 2.0)

        points_abs = [
            {"x": round(min_x, 3), "y": round(min_y, 3)},
            {"x": round(max_x, 3), "y": round(min_y, 3)},
            {"x": round(max_x, 3), "y": round(max_y, 3)},
            {"x": round(min_x, 3), "y": round(max_y, 3)},
        ]

        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        name = self._next_payload_space_name(payload_name)
        space = {
            "name": name,
            "points": [
                {
                    "dx": round(float(p["x"]) - lx, 3),
                    "dy": round(float(p["y"]) - ly, 3),
                }
                for p in points_abs
            ],
            "payload_slots": [
                {
                    "payload": payload_name,
                    "dx": round(cx - lx, 3),
                    "dy": round(cy - ly, 3),
                    "rotation_deg": 0.0,
                }
            ],
        }

        self.spaces.append(space)
        self.selected_space_index = len(self.spaces) - 1
        self.name_edit.setText(name)
        self._sync_current_space_from_payload()
        self.selected_payload_index = 0
        self.selected_space_indices = {self.selected_space_index}
        self.lock_size_check.setChecked(True)
        self.refresh_list()
        self.space_list.setCurrentRow(self.selected_space_index)
        self.refresh_scene()
        self.status_label.setText(
            f"Created inventory space '{name}' sized to {payload_name} "
            f"({length:.3f} m × {width:.3f} m)."
        )

    def _next_payload_space_name(self, payload_name):
        base = str(payload_name).strip() or "Payload"
        existing = {str(space.get("name", "")).strip() for space in self.spaces}
        index = 1
        while True:
            name = f"{base} space {index}"
            if name not in existing:
                return name
            index += 1

    def _next_payload_space_centre(self, length, width):
        # Prefer placing inside the location bounding box when one exists;
        # otherwise start at the location origin.  Each added payload is
        # offset by one payload width/length plus a small gap so new spaces do
        # not sit exactly on top of each other.
        gap = 0.1
        location_box = self.store.get_location_bounding_box_points(self.location_name)

        if location_box:
            xs = [float(p["x"]) for p in location_box]
            ys = [float(p["y"]) for p in location_box]
            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)

            usable_width = max(0.0, max_x - min_x)
            columns = max(1, int((usable_width + gap) // (float(length) + gap)))
            index = len(self.spaces)
            col = index % columns
            row = index // columns
            cx = min_x + (float(length) / 2.0) + (col * (float(length) + gap))
            cy = min_y + (float(width) / 2.0) + (row * (float(width) + gap))

            # If the calculated row would run beyond the bounding box, keep it
            # visible by falling back to the lower-left origin plus stagger.
            if cy + (float(width) / 2.0) <= max_y + 1e-9:
                return round(cx, 3), round(cy, 3)

        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        offset = len(self.spaces) * (max(float(length), float(width)) + gap)
        return round(lx + (float(length) / 2.0) + offset, 3), round(
            ly + (float(width) / 2.0), 3
        )

    def _sync_space_from_payload_index(self, index):
        if not (0 <= int(index) < len(self.spaces)):
            return False

        space = self.spaces[int(index)]
        slots = space.setdefault("payload_slots", [])
        if not slots:
            return False

        points = self._slot_polygon_points(slots[0])
        if len(points) < 3:
            return False

        lx = float(self.location.get("x", 0.0))
        ly = float(self.location.get("y", 0.0))
        space["points"] = [
            {
                "dx": round(float(p["x"]) - lx, 3),
                "dy": round(float(p["y"]) - ly, 3),
            }
            for p in points
        ]

        if index == self.selected_space_index:
            self.current_points = points

        return True

    def auto_align_payloads(self):
        location_box = self.store.get_location_bounding_box_points(self.location_name)
        if len(location_box) < 3:
            QMessageBox.information(
                self,
                "Auto align",
                "Draw or define the location bounding box first. Auto align arranges payload spaces within that bounding box.",
            )
            return

        self._commit_current_space(show_errors=False)

        xs = [float(p["x"]) for p in location_box]
        ys = [float(p["y"]) for p in location_box]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        gap = 0.05

        payload_spaces = []
        skipped = 0

        for index, space in enumerate(self.spaces):
            slots = space.setdefault("payload_slots", [])
            if not slots:
                skipped += 1
                continue

            slot = slots[0]
            payload_name = str(slot.get("payload", "")).strip()
            length, width = self._payload_dimensions(payload_name)
            if length <= 0 or width <= 0:
                skipped += 1
                continue

            payload_spaces.append((index, slot, payload_name, length, width))

        if not payload_spaces:
            QMessageBox.information(
                self,
                "Auto align",
                "There are no payload-based inventory spaces to align.",
            )
            return

        # Shelf-pack payload footprints into the location bounding box.  For each
        # payload, try the orientation that fits the current row; otherwise start
        # a new row and retry.  Oversized/overflowing payloads are left unchanged.
        x = min_x
        y = min_y
        row_height = 0.0
        placed = 0
        overflow = 0

        for index, slot, _payload_name, length, width in payload_spaces:
            orientations = [(length, width, 0.0)]
            if abs(length - width) > 1e-9:
                orientations.append((width, length, 90.0))

            chosen = None

            for item_len, item_wid, rotation in orientations:
                if (x + item_len <= max_x + 1e-9) and (y + item_wid <= max_y + 1e-9):
                    chosen = (item_len, item_wid, rotation)
                    break

            if chosen is None:
                x = min_x
                y = y + row_height + gap
                row_height = 0.0

                for item_len, item_wid, rotation in orientations:
                    if (x + item_len <= max_x + 1e-9) and (
                        y + item_wid <= max_y + 1e-9
                    ):
                        chosen = (item_len, item_wid, rotation)
                        break

            if chosen is None:
                overflow += 1
                continue

            item_len, item_wid, rotation = chosen
            cx = x + (item_len / 2.0)
            cy = y + (item_wid / 2.0)
            slot["rotation_deg"] = rotation
            self._set_slot_center_absolute(slot, cx, cy)
            self._sync_space_from_payload_index(index)

            x = x + item_len + gap
            row_height = max(row_height, item_wid)
            placed += 1

        if self.selected_space_index is not None:
            self.select_space(self.selected_space_index)

        self.refresh_list()
        self.refresh_scene()

        message = (
            f"Auto aligned {placed} payload space(s) within the location bounding box."
        )
        if overflow:
            message += (
                f" {overflow} payload space(s) did not fit and were left unchanged."
            )
        if skipped:
            message += f" {skipped} non-payload/invalid space(s) skipped."
        self.status_label.setText(message)

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
        previous_index = self.selected_space_index
        if previous_index is not None and previous_index != row:
            self._commit_current_space(show_errors=False)

        if row < 0 or row >= len(self.spaces):
            return

        self.selected_space_index = row
        if not self.selected_space_indices or row not in self.selected_space_indices:
            self.selected_space_indices = {row}
        space = self.spaces[row]
        self.name_edit.setText(space.get("name", ""))

        slots = space.setdefault("payload_slots", [])
        if slots:
            self.current_points = self._slot_polygon_points(slots[0])
            self.selected_payload_index = 0
            self.payload_combo.setCurrentText(str(slots[0].get("payload", "")))
            self._refresh_rotation_field()
        else:
            self.current_points = self.store.inventory_space_points_absolute(
                self.location_name,
                space,
            )
            self.selected_payload_index = None
            self._refresh_rotation_field()

        self.refresh_scene()

    def new_space(self):
        QMessageBox.information(
            self,
            "Inventory space",
            "Inventory spaces are now created from payload footprints. Select a payload and use Add payload.",
        )

    def save_current_space(self):
        if self._commit_current_space(show_errors=True):
            self.refresh_list()
            if self.selected_space_index is not None:
                self.space_list.blockSignals(True)
                self.space_list.setCurrentRow(self.selected_space_index)
                self.space_list.blockSignals(False)
            self.refresh_scene()

    def delete_selected_space(self):
        rows = sorted(
            self.selected_space_indices or {self.space_list.currentRow()}, reverse=True
        )
        rows = [row for row in rows if 0 <= row < len(self.spaces)]
        if not rows:
            return

        for row in rows:
            del self.spaces[row]
        self.selected_space_index = None
        self.selected_space_indices = set()
        self.current_points = []
        self.name_edit.clear()
        self.refresh_list()
        self.refresh_scene()

    def finish(self):
        self._commit_current_space(show_errors=False)
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

    def _normalise_degrees(self, angle):
        try:
            angle = float(angle)
        except Exception:
            angle = 0.0
        angle = angle % 360.0
        if angle < 0:
            angle += 360.0
        return round(angle, 3)

    def _selected_space_slot(self):
        if self.selected_space_index is None:
            return None
        return self._space_payload_slot(self.selected_space_index)

    def _refresh_rotation_field(self):
        if not hasattr(self, "rotation_edit"):
            return
        slot = self._selected_space_slot()
        if not slot:
            self.rotation_edit.setText("0.0")
            return
        self.rotation_edit.setText(
            f"{self._normalise_degrees(slot.get('rotation_deg', 0.0)):.1f}"
        )

    def apply_rotation_from_field(self):
        slot = self._selected_space_slot()
        if not slot or self.selected_space_index is None:
            self._refresh_rotation_field()
            return
        try:
            angle = float(self.rotation_edit.text())
        except ValueError:
            self._refresh_rotation_field()
            return
        slot["rotation_deg"] = self._normalise_degrees(angle)
        self.selected_payload_index = 0
        self._sync_space_from_payload_index(self.selected_space_index)
        self._commit_current_space(show_errors=False)
        self.refresh_scene()

    def nudge_selected_rotation(self, delta):
        slot = self._selected_space_slot()
        if not slot or self.selected_space_index is None:
            return
        slot["rotation_deg"] = self._normalise_degrees(
            float(slot.get("rotation_deg", 0.0) or 0.0) + float(delta)
        )
        self.selected_payload_index = 0
        self._sync_space_from_payload_index(self.selected_space_index)
        self._commit_current_space(show_errors=False)
        self.refresh_scene()

    def _rotation_handle_world(self, slot):
        payload_name = str(slot.get("payload", "")).strip()
        length, width = self._payload_dimensions(payload_name)
        if length <= 0 or width <= 0:
            return None
        cx, cy = self._slot_center_absolute(slot)
        angle = math.radians(float(slot.get("rotation_deg", 0.0) or 0.0))
        distance = (max(length, width) / 2.0) + 0.35
        return {
            "x": cx + (math.cos(angle) * distance),
            "y": cy + (math.sin(angle) * distance),
        }

    def _nearest_rotation_handle_index_at(self, x, y, radius=0.25):
        # Only the current space exposes the handle to avoid accidental rotation
        # of a space hidden under another selected payload.
        if self.selected_space_index is None:
            return None
        slot = self._selected_space_slot()
        if not slot:
            return None
        handle = self._rotation_handle_world(slot)
        if not handle:
            return None
        dist = math.hypot(float(handle["x"]) - float(x), float(handle["y"]) - float(y))
        return self.selected_space_index if dist <= radius else None

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

        hit_space = self._nearest_space_index_at(x, y)
        modifiers = event.modifiers()
        additive = bool(modifiers & (Qt.ControlModifier | Qt.ShiftModifier))

        rotate_hit = self._nearest_rotation_handle_index_at(x, y)
        if event.button() == Qt.LeftButton and rotate_hit is not None:
            slot = self._space_payload_slot(rotate_hit)
            if slot:
                self.rotate_space_index = rotate_hit
                self.rotate_start_center = self._slot_center_absolute(slot)
                self.drag_space_indices = set()
                self.drag_spaces_start_world = None
                self.drag_spaces_start_slots = {}
                self.selected_payload_index = 0
                self.status_label.setText(
                    "Drag to rotate freely. Release to save the angle."
                )
                return

        if event.button() == Qt.RightButton:
            if hit_space is not None:
                previous_index = self.selected_space_index
                if previous_index is not None and previous_index != hit_space:
                    self._commit_current_space(show_errors=False)
                self.select_space(hit_space)
                self.status_label.setText(
                    "Use the rotation angle field, +/- buttons, or drag the rotate handle for free-angle rotation."
                )
            return

        if event.button() != Qt.LeftButton:
            return

        if hit_space is not None:
            previous_index = self.selected_space_index
            if previous_index is not None and previous_index != hit_space:
                self._commit_current_space(show_errors=False)

            if additive:
                selected = set(self.selected_space_indices)
                if hit_space in selected and len(selected) > 1:
                    selected.remove(hit_space)
                else:
                    selected.add(hit_space)
                self._set_space_selection(selected, current_index=hit_space)
            elif hit_space not in self.selected_space_indices:
                self._set_space_selection({hit_space}, current_index=hit_space)
            else:
                self.selected_space_index = hit_space

            self.select_space(hit_space)
            self.selected_payload_index = 0
            drag_indices = set(self.selected_space_indices or {hit_space})
            self.drag_space_indices = drag_indices
            self.drag_spaces_start_world = {"x": x, "y": y}
            self.drag_spaces_start_slots = {}
            for index in drag_indices:
                slot = self._space_payload_slot(index)
                if slot:
                    self.drag_spaces_start_slots[index] = dict(slot)
            self.refresh_scene()
            return

    def _mouse_move(self, event):
        scene_pos = self.view.mapToScene(event.position().toPoint())
        x, y = self.scene_to_world(scene_pos)

        # Qt can still deliver a move event after the mouse button has been
        # released, especially if the cursor leaves the rotate handle/viewport.
        # Treat that as a cancelled drag so rotation cannot continue running.
        if not (event.buttons() & Qt.LeftButton):
            if self.rotate_space_index is not None:
                self.rotate_space_index = None
                self.rotate_start_center = None
                self._commit_current_space(show_errors=False)
                self.refresh_scene()
            self.drag_point_index = None
            self.drag_whole_space = False
            self.drag_start_world = None
            self.drag_start_points = []
            self.drag_payload_index = None
            self.drag_payload_start_world = None
            self.drag_payload_start = None
            self.drag_space_indices = set()
            self.drag_spaces_start_world = None
            self.drag_spaces_start_slots = {}
            return

        if self.rotate_space_index is not None and self.rotate_start_center is not None:
            slot = self._space_payload_slot(self.rotate_space_index)
            if slot:
                cx, cy = self.rotate_start_center
                angle = math.degrees(
                    math.atan2(float(y) - float(cy), float(x) - float(cx))
                )
                if event.modifiers() & Qt.ShiftModifier:
                    angle = round(angle / 90.0) * 90.0
                slot["rotation_deg"] = self._normalise_degrees(angle)
                self.selected_space_index = self.rotate_space_index
                self.selected_payload_index = 0
                self._sync_space_from_payload_index(self.rotate_space_index)
                self.current_points = self._slot_polygon_points(slot)
                self.refresh_scene()
            return

        if self.drag_spaces_start_world is not None and self.drag_spaces_start_slots:
            dx = x - float(self.drag_spaces_start_world["x"])
            dy = y - float(self.drag_spaces_start_world["y"])
            self._move_space_group(self.drag_spaces_start_slots, dx, dy)
            if self.selected_space_index is not None:
                self._sync_space_from_payload_index(self.selected_space_index)
            self.refresh_scene()
            return

        if (
            self.drag_payload_index is not None
            and self.drag_payload_start_world is not None
            and self.drag_payload_start is not None
        ):
            slots = self._current_space_slots()
            if 0 <= self.drag_payload_index < len(slots):
                start_x, start_y = self._slot_center_absolute(self.drag_payload_start)
                dx = x - float(self.drag_payload_start_world["x"])
                dy = y - float(self.drag_payload_start_world["y"])
                candidate = dict(self.drag_payload_start)
                self._set_slot_center_absolute(candidate, start_x + dx, start_y + dy)
                # Payload footprints define the inventory space, so movement is
                # allowed and then the space polygon is regenerated from the slot.
                slots[self.drag_payload_index].update(candidate)
                self._sync_current_space_from_payload()
                self.refresh_scene()
            return

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
        if self.rotate_space_index is not None:
            self.rotate_space_index = None
            self.rotate_start_center = None
            self._commit_current_space(show_errors=False)
            self.refresh_scene()

        self.drag_point_index = None
        self.drag_whole_space = False
        self.drag_start_world = None
        self.drag_start_points = []
        self.drag_payload_index = None
        self.drag_payload_start_world = None
        self.drag_payload_start = None
        self.drag_space_indices = set()
        self.drag_spaces_start_world = None
        self.drag_spaces_start_slots = {}
        event.accept()

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
            "payload_slots": [
                dict(slot) for slot in self.spaces[row].get("payload_slots", [])
            ],
        }

        self.status_label.setText(f"Copied {self.copied_space['name']}")

    def paste_copied_space(self):
        if not self.copied_space:
            return

        pasted = {
            "name": f"{self.copied_space.get('name', 'Inventory space')} copy",
            "points": [dict(p) for p in self.copied_space.get("points", [])],
            "payload_slots": [
                dict(slot) for slot in self.copied_space.get("payload_slots", [])
            ],
        }

        # Small offset so pasted space is visible and selectable separately
        for p in pasted["points"]:
            p["dx"] = round(float(p.get("dx", 0.0)) + 0.25, 3)
            p["dy"] = round(float(p.get("dy", 0.0)) + 0.25, 3)
        for slot in pasted.get("payload_slots", []):
            slot["dx"] = round(float(slot.get("dx", 0.0)) + 0.25, 3)
            slot["dy"] = round(float(slot.get("dy", 0.0)) + 0.25, 3)

        self.spaces.append(pasted)
        self.selected_space_index = len(self.spaces) - 1
        self.selected_space_indices = {self.selected_space_index}
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
            poly.setPen(QPen(QColor("#18c37e"), 0.0))
            poly.setBrush(QBrush(QColor(24, 195, 126, 18)))
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
            is_multi_selected = idx in self.selected_space_indices
            poly.setPen(
                QPen(QColor("#ffffff" if is_multi_selected else "#6aa9ff"), 0.0)
            )
            poly.setBrush(
                QBrush(QColor(106, 169, 255, 38 if is_multi_selected else 18))
            )
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
                poly.setPen(QPen(QColor("#ffdd57"), 0.0))
                poly.setBrush(QBrush(QColor(255, 221, 87, 30)))
                self.scene.addItem(poly)

            # No freehand handles: inventory spaces are fixed payload footprints.

        for slot_index, slot in enumerate(self._current_space_slots()):
            payload_name = str(slot.get("payload", "")).strip()
            poly_points = self._slot_polygon_points(slot)
            if len(poly_points) < 3:
                continue
            pts = [self.world_to_scene(p["x"], p["y"]) for p in poly_points]
            item = QGraphicsPolygonItem(QPolygonF(pts))
            selected = slot_index == self.selected_payload_index
            item.setPen(QPen(QColor("#ffffff" if selected else "#3da5ff"), 0.0))
            item.setBrush(QBrush(QColor(61, 165, 255, 65 if selected else 35)))
            item.setZValue(15)
            self.scene.addItem(item)
            cx, cy = self._slot_center_absolute(slot)
            label = QGraphicsSimpleTextItem(payload_name)
            label.setBrush(QBrush(QColor("#e3f2ff")))
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            label.setPos(self.world_to_scene(cx, cy))
            label.setZValue(16)
            self.scene.addItem(label)

            if selected:
                handle = self._rotation_handle_world(slot)
                if handle:
                    centre_scene = self.world_to_scene(cx, cy)
                    handle_scene = self.world_to_scene(handle["x"], handle["y"])
                    line = self.scene.addLine(
                        centre_scene.x(),
                        centre_scene.y(),
                        handle_scene.x(),
                        handle_scene.y(),
                        QPen(QColor("#ffffff"), 0.0),
                    )
                    line.setZValue(17)
                    r = 0.12
                    ellipse = self.scene.addEllipse(
                        handle_scene.x() - r,
                        handle_scene.y() - r,
                        r * 2.0,
                        r * 2.0,
                        QPen(QColor("#ffffff"), 0.0),
                        QBrush(QColor("#ffdd57")),
                    )
                    ellipse.setZValue(18)

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
