import json
from typing import Any, List, Optional

from advanced_dialogs import MultiSelectPicker

from PySide6.QtCore import Qt, QPointF, QRectF
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
