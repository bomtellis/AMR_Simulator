import json
from typing import Any, List, Optional

from advanced_dialogs import MultiSelectPicker

from PySide6.QtCore import Qt
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
)


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
        self.capacity_edit = QLineEdit(str(self.lift.get("capacity_size_units", 1.0)))
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
        form.addRow("Capacity size units", self.capacity_edit)
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
            int(x.strip())
            for x in self.floors_edit.text().split(",")
            if x.strip()
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
                "capacity_size_units": float(self.capacity_edit.text()),
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
        self.payload_capacity_edit = QLineEdit(str(self.seed.get("payload_capacity_kg", 100)))
        self.payload_size_edit = QLineEdit(str(self.seed.get("payload_size_capacity", 1.0)))
        self.speed_edit = QLineEdit(str(self.seed.get("speed_m_per_sec", 1.0)))
        self.motor_power_edit = QLineEdit(str(self.seed.get("motor_power_w", 250)))
        self.battery_capacity_edit = QLineEdit(str(self.seed.get("battery_capacity_kwh", 1.0)))
        self.charge_rate_edit = QLineEdit(str(self.seed.get("battery_charge_rate_kw", 0.5)))
        self.recharge_threshold_edit = QLineEdit(str(self.seed.get("recharge_threshold_percent", 20)))
        self.battery_soc_edit = QLineEdit(str(self.seed.get("battery_soc_percent", 100)))

        self.start_location_combo = QComboBox()
        self.start_location_combo.addItems([""] + self.location_names)
        self.start_location_combo.setCurrentText(str(self.seed.get("start_location", "")))

        form.addRow("AMR ID", self.id_edit)
        form.addRow("Quantity", self.quantity_edit)
        form.addRow("Payload capacity kg", self.payload_capacity_edit)
        form.addRow("Payload size capacity", self.payload_size_edit)
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
                "payload_size_capacity": float(self.payload_size_edit.text()),
                "speed_m_per_sec": float(self.speed_edit.text()),
                "motor_power_w": float(self.motor_power_edit.text()),
                "battery_capacity_kwh": float(self.battery_capacity_edit.text()),
                "battery_charge_rate_kw": float(self.charge_rate_edit.text()),
                "recharge_threshold_percent": float(self.recharge_threshold_edit.text()),
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
        ("payload_size_capacity", "Size cap.", 90),
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
        self.table.setHorizontalHeaderLabels([heading for _key, heading, _width in self.columns])
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
    ):
        super().__init__(parent)
        self.setWindowTitle("Department")
        self.result = None
        self.seed = seed or {}
        self.location_names = sorted(location_names)
        self.waste_stream_names = sorted(waste_stream_names)
        self.group_resolver = group_resolver or (lambda item: "Other")

        self.selected_locations = list(self.seed.get("waste_pickup_locations", []))
        self.selected_waste_streams = list(self.seed.get("waste_streams", []))

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

        pickup_row = QHBoxLayout()
        self.pickup_summary = QLabel("None selected")
        self.pickup_summary.setWordWrap(True)
        pickup_btn = QPushButton("Select...")
        pickup_btn.clicked.connect(self._pick_locations)
        pickup_row.addWidget(self.pickup_summary, 1)
        pickup_row.addWidget(pickup_btn)

        waste_row = QHBoxLayout()
        self.waste_summary = QLabel("None selected")
        self.waste_summary.setWordWrap(True)
        waste_btn = QPushButton("Select...")
        waste_btn.clicked.connect(self._pick_waste_streams)
        waste_row.addWidget(self.waste_summary, 1)
        waste_row.addWidget(waste_btn)

        waste_cfg = self.seed.get("waste", {})
        self.alpha_edit = QLineEdit(str(waste_cfg.get("alpha", 0.0)))
        self.beta_edit = QLineEdit(str(waste_cfg.get("beta", 0.0)))
        self.gamma_edit = QLineEdit(str(waste_cfg.get("gamma", 0.0)))

        self.waste_pickup_combo = QComboBox()
        self.waste_pickup_combo.addItems([""] + self.location_names)
        self.waste_pickup_combo.setCurrentText(waste_cfg.get("pickup_location", ""))

        self.waste_dropoff_combo = QComboBox()
        self.waste_dropoff_combo.addItems([""] + self.location_names)
        self.waste_dropoff_combo.setCurrentText(waste_cfg.get("dropoff_location", ""))

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
        form.addRow("Waste pickup locations", pickup_row)
        form.addRow("Assigned waste streams", waste_row)
        form.addRow("Alpha", self.alpha_edit)
        form.addRow("Beta", self.beta_edit)
        form.addRow("Gamma", self.gamma_edit)
        form.addRow("Waste pickup", self.waste_pickup_combo)
        form.addRow("Waste dropoff", self.waste_dropoff_combo)
        form.addRow("X", self.x_edit)
        form.addRow("Y", self.y_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_pickup_summary()
        self._refresh_waste_summary()

    def _refresh_pickup_summary(self):
        if not self.selected_locations:
            self.pickup_summary.setText("None selected")
        elif len(self.selected_locations) <= 4:
            self.pickup_summary.setText(", ".join(self.selected_locations))
        else:
            self.pickup_summary.setText(f"{len(self.selected_locations)} selected")

    def _refresh_waste_summary(self):
        if not self.selected_waste_streams:
            self.waste_summary.setText("None selected")
        elif len(self.selected_waste_streams) <= 4:
            self.waste_summary.setText(", ".join(self.selected_waste_streams))
        else:
            self.waste_summary.setText(f"{len(self.selected_waste_streams)} selected")

    def _pick_locations(self):
        picker = MultiSelectPicker(
            self,
            "Select waste pickup locations",
            self.location_names,
            selected=self.selected_locations,
            group_resolver=self.group_resolver,
        )
        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_locations = sorted(picker.result)
            self._refresh_pickup_summary()

    def _pick_waste_streams(self):
        picker = MultiSelectPicker(
            self,
            "Select waste streams",
            self.waste_stream_names,
            selected=self.selected_waste_streams,
            group_resolver=lambda _: "Waste streams",
        )
        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.selected_waste_streams = sorted(picker.result)
            self._refresh_waste_summary()

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

            pickup_location = self.waste_pickup_combo.currentText().strip()
            dropoff_location = self.waste_dropoff_combo.currentText().strip()

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
                "waste_pickup_locations": list(self.selected_locations),
                "waste_streams": list(self.selected_waste_streams),
                "waste": {
                    "alpha": float(self.alpha_edit.text()),
                    "beta": float(self.beta_edit.text()),
                    "gamma": float(self.gamma_edit.text()),
                    "pickup_location": pickup_location,
                    "dropoff_location": dropoff_location,
                },
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
                QTableWidgetItem(", ".join(item.get("waste_streams", []))),
            )

    def add_item(self):
        dialog = DepartmentEditorDialog(
            self,
            location_names=self.location_names,
            waste_stream_names=self.waste_stream_names,
            current_floor=self.current_floor,
            default_department_id=self.suggest_department_id(),
            group_resolver=self.group_resolver,
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
