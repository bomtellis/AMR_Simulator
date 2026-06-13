import json
from typing import Any, Callable, Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
)


def _as_text(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return "" if value is None else str(value)


def _parse_value(value: str) -> Any:
    value = (value or "").strip()
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


class BaseDialog(QDialog):
    def _error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)


class PointEditorDialog(BaseDialog):
    def __init__(self, parent, title: str, point_name: str, point: dict):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.point_name = point_name
        self.point = point
        self.result = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(self.point_name)
        self.x_edit = QLineEdit(str(self.point.get("x", 0)))
        self.y_edit = QLineEdit(str(self.point.get("y", 0)))
        form.addRow("Name", self.name_edit)
        form.addRow("X", self.x_edit)
        form.addRow("Y", self.y_edit)
        form.addRow("Floor", QLabel(str(self.point.get("floor", ""))))
        form.addRow("Kind", QLabel(str(self.point.get("kind", ""))))
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            name = self.name_edit.text().strip()
            if not name:
                raise ValueError("Name is required")
            self.result = {"name": name, "x": float(self.x_edit.text()), "y": float(self.y_edit.text())}
            super().accept()
        except Exception as exc:
            self._error("Invalid value", str(exc))


class LiftEditorDialog(BaseDialog):
    def __init__(self, parent, lift=None, default_floor=0, default_x=0.0, default_y=0.0):
        super().__init__(parent)
        self.setWindowTitle("Lift Editor")
        self.resize(560, 520)
        self.lift = lift or {}
        self.default_floor = default_floor
        self.default_x = default_x
        self.default_y = default_y
        self.result = None
        self._build()

    def _floor_height_m(self) -> float:
        parent = self.parent()
        store = getattr(parent, "store", None)
        data = getattr(store, "data", {}) if store is not None else {}
        return float((data.get("building", {}) or {}).get("floor_height_m", 4.0) or 4.0)

    def _default_speed_m_per_sec(self, lift: dict) -> float:
        if lift.get("speed_m_per_sec") is not None:
            return float(lift.get("speed_m_per_sec") or 0.0)
        return float(lift.get("speed_floors_per_sec", 0.45) or 0.45) * self._floor_height_m()

    def _normalise_floor_locations(self, floor_locations):
        payload = {}
        for key, value in (floor_locations or {}).items():
            if isinstance(value, dict):
                payload[int(key)] = [float(value.get("x", self.default_x)), float(value.get("y", self.default_y))]
            else:
                payload[int(key)] = [float(value[0]), float(value[1])]
        return payload

    def _build(self):
        lift = self.lift
        floors = lift.get("served_floors", [self.default_floor])
        floor_locations = lift.get("floor_locations", {})
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.id_edit = QLineEdit(str(lift.get("id", "Lift-1")))
        self.floors_edit = QLineEdit(", ".join(str(x) for x in floors))
        self.speed_edit = QLineEdit(str(self._default_speed_m_per_sec(lift)))
        self.door_edit = QLineEdit(str(lift.get("door_time_sec", 4)))
        self.board_edit = QLineEdit(str(lift.get("boarding_time_sec", 6)))
        self.capacity_length_edit = QLineEdit(str(lift.get("capacity_length_m", 1.0)))
        self.capacity_width_edit = QLineEdit(str(lift.get("capacity_width_m", 1.0)))
        self.capacity_height_edit = QLineEdit(str(lift.get("capacity_height_m", 2.0)))
        self.car_mass_edit = QLineEdit(str(lift.get("car_mass_kg", 1200.0)))
        self.counterweight_edit = QLineEdit(str(lift.get("counterweight_ratio", 0.5)))
        self.travel_efficiency_edit = QLineEdit(str(lift.get("travel_efficiency", 0.75)))
        self.door_power_edit = QLineEdit(str(lift.get("door_power_w", 800.0)))
        self.standby_power_edit = QLineEdit(str(lift.get("standby_power_w", 120.0)))
        self.regen_efficiency_edit = QLineEdit(str(lift.get("regen_efficiency", 0.2)))
        self.health_edit = QLineEdit(str(lift.get("health_percent", 100.0)))
        self.health_loss_edit = QLineEdit(str(lift.get("health_loss_per_journey_percent", 0.05)))
        self.mtbf_edit = QLineEdit(str(lift.get("mean_time_between_failures_hours", 720.0)))
        self.mttr_edit = QLineEdit(str(lift.get("mean_time_to_repair_hours", 4.0)))
        self.start_floor_edit = QLineEdit(str(lift.get("start_floor", self.default_floor)))
        form.addRow("Lift ID", self.id_edit)
        form.addRow("Served floors", self.floors_edit)
        form.addRow("Speed m/sec", self.speed_edit)
        form.addRow("Door time sec", self.door_edit)
        form.addRow("Boarding time sec", self.board_edit)
        form.addRow("Capacity length m", self.capacity_length_edit)
        form.addRow("Capacity width m", self.capacity_width_edit)
        form.addRow("Capacity height m", self.capacity_height_edit)
        form.addRow("Car mass kg", self.car_mass_edit)
        form.addRow("Counterweight ratio", self.counterweight_edit)
        form.addRow("Travel efficiency", self.travel_efficiency_edit)
        form.addRow("Door power W", self.door_power_edit)
        form.addRow("Stationary power W", self.standby_power_edit)
        form.addRow("Regen efficiency", self.regen_efficiency_edit)
        form.addRow("Health %", self.health_edit)
        form.addRow("Health loss per journey %", self.health_loss_edit)
        form.addRow("MTBF hours", self.mtbf_edit)
        form.addRow("MTTR hours", self.mttr_edit)
        form.addRow("Start floor", self.start_floor_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("Per-floor positions. Format: {floor: [x, y]}"))
        self.pos_text = QTextEdit()
        if floor_locations:
            payload = self._normalise_floor_locations(floor_locations)
        else:
            payload = {self.default_floor: [self.default_x, self.default_y]}
        self.pos_text.setPlainText(json.dumps(payload, indent=2))
        layout.addWidget(self.pos_text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            lift_id = self.id_edit.text().strip()
            if not lift_id:
                raise ValueError("Lift ID is required")
            floors = [int(x.strip()) for x in self.floors_edit.text().split(",") if x.strip()]
            if not floors:
                raise ValueError("At least one served floor is required")
            raw_positions = json.loads(self.pos_text.toPlainText().strip())
            key_set = {str(k) for k in raw_positions.keys()}
            for floor in floors:
                if str(floor) not in key_set:
                    raise ValueError(f"Missing position for floor {floor}")
            floor_locations = {int(k): (float(v[0]), float(v[1])) for k, v in raw_positions.items()}
            self.result = {
                "id": lift_id,
                "served_floors": floors,
                "speed_m_per_sec": float(self.speed_edit.text()),
                "door_time_sec": float(self.door_edit.text()),
                "boarding_time_sec": float(self.board_edit.text()),
                "capacity_length_m": float(self.capacity_length_edit.text()),
                "capacity_width_m": float(self.capacity_width_edit.text()),
                "capacity_height_m": float(self.capacity_height_edit.text()),
                "car_mass_kg": float(self.car_mass_edit.text()),
                "counterweight_ratio": float(self.counterweight_edit.text()),
                "travel_efficiency": float(self.travel_efficiency_edit.text()),
                "door_power_w": float(self.door_power_edit.text()),
                "standby_power_w": float(self.standby_power_edit.text()),
                "regen_efficiency": float(self.regen_efficiency_edit.text()),
                "health_percent": float(self.health_edit.text()),
                "health_loss_per_journey_percent": float(self.health_loss_edit.text()),
                "mean_time_between_failures_hours": float(self.mtbf_edit.text()),
                "mean_time_to_repair_hours": float(self.mttr_edit.text()),
                "start_floor": int(self.start_floor_edit.text()),
                "floor_locations": floor_locations,
            }
            super().accept()
        except Exception as exc:
            self._error("Invalid lift", str(exc))


class LiftListDialog(BaseDialog):
    def __init__(self, parent, store, on_changed):
        super().__init__(parent)
        self.setWindowTitle("Lifts")
        self.resize(980, 460)
        self.store = store
        self.on_changed = on_changed
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Floors", "Speed m/sec", "Door s", "Board s", "Capacity LxWxH", "Stationary W", "Start floor"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        for text, slot in [("Add", self.add_lift), ("Edit", self.edit_lift), ("Delete", self.delete_lift)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def refresh(self):
        self.table.setRowCount(0)
        for lift in self.store.data.get("lifts", []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            floors = ", ".join(str(x) for x in lift.get("served_floors", []))
            dims = " x ".join(
                str(lift.get(key, ""))
                for key in ("capacity_length_m", "capacity_width_m", "capacity_height_m")
            )
            speed_m_per_sec = lift.get("speed_m_per_sec")
            if speed_m_per_sec in (None, ""):
                floor_height_m = float((self.store.data.get("building", {}) or {}).get("floor_height_m", 4.0) or 4.0)
                speed_m_per_sec = float(lift.get("speed_floors_per_sec", 0.45) or 0.45) * floor_height_m
            values = [
                lift.get("id", ""),
                floors,
                speed_m_per_sec,
                lift.get("door_time_sec", ""),
                lift.get("boarding_time_sec", ""),
                dims,
                lift.get("standby_power_w", ""),
                lift.get("start_floor", ""),
            ]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(_as_text(value)))

    def selected_lift(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        lifts = self.store.data.get("lifts", [])
        return lifts[idx] if 0 <= idx < len(lifts) else None

    def _default_floor(self):
        parent = self.parent()
        floor_spin = getattr(parent, "floor_spin", None)
        return int(floor_spin.value()) if floor_spin is not None else 0

    def _save_result(self, result, old_id=None):
        if old_id and old_id != result["id"]:
            self.store.delete_lift(old_id)
        self.store.upsert_lift(
            result["id"],
            result["served_floors"],
            result["floor_locations"],
            result["speed_m_per_sec"],
            result["door_time_sec"],
            result["boarding_time_sec"],
            result["capacity_length_m"],
            result["capacity_width_m"],
            result["capacity_height_m"],
            result["car_mass_kg"],
            result["counterweight_ratio"],
            result["travel_efficiency"],
            result["door_power_w"],
            result["standby_power_w"],
            result["regen_efficiency"],
            result["health_percent"],
            result["health_loss_per_journey_percent"],
            result["mean_time_between_failures_hours"],
            result["mean_time_to_repair_hours"],
            result["start_floor"],
        )
        self.on_changed()
        self.refresh()

    def add_lift(self):
        floor = self._default_floor()
        dialog = LiftEditorDialog(self.parent(), None, default_floor=floor)
        if dialog.exec():
            self._save_result(dialog.result)

    def edit_lift(self):
        lift = self.selected_lift()
        if lift is None:
            return
        dialog = LiftEditorDialog(self.parent(), lift)
        if dialog.exec():
            self._save_result(dialog.result, old_id=lift.get("id"))

    def delete_lift(self):
        lift = self.selected_lift()
        if lift is None:
            return
        lift_id = str(lift.get("id", "")).strip()
        if not lift_id:
            return
        if QMessageBox.question(self, "Delete lift", f"Delete {lift_id}?") != QMessageBox.Yes:
            return
        self.store.delete_lift(lift_id)
        self.on_changed()
        self.refresh()


class TableListEditor(QWidget):
    def __init__(self, parent, title: str, columns: list, items: list, on_save: Callable[[list], None]):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(title)
        self.resize(1100, 500)
        self.columns = columns
        self.items = items
        self.on_save = on_save
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([c[1] for c in self.columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in [("Add", self.add_item), ("Edit", self.edit_item), ("Delete", self.delete_item)]:
            btn = QPushButton(text); btn.clicked.connect(slot); row.addWidget(btn)
        row.addStretch(1)
        save_btn = QPushButton("Save"); save_btn.clicked.connect(self.save); row.addWidget(save_btn)
        layout.addLayout(row)

    def refresh(self):
        self.table.setRowCount(0)
        for item in self.items:
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, (key, _heading, _width) in enumerate(self.columns):
                self.table.setItem(r, c, QTableWidgetItem(_as_text(item.get(key, ""))))

    def selected_index(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def prompt_item(self, seed=None):
        seed = seed or {}
        result = {}
        for key, heading, _width in self.columns:
            value, ok = QInputDialog.getText(self, self.windowTitle(), heading, text=_as_text(seed.get(key, "")))
            if not ok:
                return None
            result[key] = _parse_value(value)
        return result

    def add_item(self):
        item = self.prompt_item()
        if item is not None:
            self.items.append(item); self.refresh()

    def edit_item(self):
        idx = self.selected_index()
        if idx is None:
            return
        item = self.prompt_item(self.items[idx])
        if item is not None:
            self.items[idx] = item; self.refresh()

    def delete_item(self):
        idx = self.selected_index()
        if idx is not None:
            del self.items[idx]; self.refresh()

    def save(self):
        self.on_save(self.items)
        self.close()
