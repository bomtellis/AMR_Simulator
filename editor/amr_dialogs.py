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

    def _build(self):
        lift = self.lift
        floors = lift.get("served_floors", [self.default_floor])
        floor_locations = lift.get("floor_locations", {})
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.id_edit = QLineEdit(str(lift.get("id", "Lift-1")))
        self.floors_edit = QLineEdit(", ".join(str(x) for x in floors))
        self.speed_edit = QLineEdit(str(lift.get("speed_floors_per_sec", 0.45)))
        self.door_edit = QLineEdit(str(lift.get("door_time_sec", 4)))
        self.board_edit = QLineEdit(str(lift.get("boarding_time_sec", 6)))
        self.capacity_edit = QLineEdit(str(lift.get("capacity_size_units", 1.0)))
        self.start_floor_edit = QLineEdit(str(lift.get("start_floor", self.default_floor)))
        form.addRow("Lift ID", self.id_edit)
        form.addRow("Served floors", self.floors_edit)
        form.addRow("Speed floors/sec", self.speed_edit)
        form.addRow("Door time sec", self.door_edit)
        form.addRow("Boarding time sec", self.board_edit)
        form.addRow("Capacity size units", self.capacity_edit)
        form.addRow("Start floor", self.start_floor_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("Per-floor positions. Format: {floor: [x, y]}"))
        self.pos_text = QTextEdit()
        if floor_locations:
            payload = {int(k): [v["x"], v["y"]] for k, v in floor_locations.items()}
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
                "speed_floors_per_sec": float(self.speed_edit.text()),
                "door_time_sec": float(self.door_edit.text()),
                "boarding_time_sec": float(self.board_edit.text()),
                "capacity_size_units": float(self.capacity_edit.text()),
                "start_floor": int(self.start_floor_edit.text()),
                "floor_locations": floor_locations,
            }
            super().accept()
        except Exception as exc:
            self._error("Invalid lift", str(exc))


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
