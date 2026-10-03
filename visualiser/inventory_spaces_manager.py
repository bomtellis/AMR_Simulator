"""Transactional, building-wide inventory space editor."""

from copy import deepcopy
import math
from amr_inventory_inputs import inventory_space_is_amr

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from models import JsonStore
from ui_theme import polish_dialog


class InventoryPreviewView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


def is_amr_space(space):
    return inventory_space_is_amr(space)


def space_geometry(space, location=None):
    """Return centre, side lengths and heading, not the rotated bounding box."""
    location = location or {}
    points = [(float(p.get("dx", float(p.get("x", 0)) - location.get("x", 0))),
               float(p.get("dy", float(p.get("y", 0)) - location.get("y", 0))))
              for p in space.get("points", [])]
    if len(points) >= 4:
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        dx, dy = points[1][0] - points[0][0], points[1][1] - points[0][1]
        length = math.hypot(dx, dy)
        width = math.dist(points[1], points[2])
        return cx, cy, length, width, math.degrees(math.atan2(dy, dx)) % 360
    return 0.0, 0.0, float(space.get("length_m", 1)), float(space.get("width_m", 1)), 0.0


def resize_space(space, length, width, angle=None, location=None):
    """Resize about the existing centre while preserving its heading by default."""
    if not all(math.isfinite(v) and v > 0 for v in (length, width)):
        raise ValueError("Length and width must be positive finite numbers.")
    cx, cy, _, _, old_angle = space_geometry(space, location)
    angle = old_angle if angle is None else angle
    if not math.isfinite(angle):
        raise ValueError("Orientation must be a finite number.")
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    space["points"] = [
        {"dx": round(cx + x * cosine - y * sine, 6),
         "dy": round(cy + x * sine + y * cosine, 6)}
        for x, y in [(-length/2, -width/2), (length/2, -width/2),
                     (length/2, width/2), (-length/2, width/2)]
    ]
    space["length_m"], space["width_m"] = round(length, 3), round(width, 3)
    # Keep attached template drawings aligned when rotating a fixed bay.
    delta = math.radians(angle - old_angle)
    for slot in space.get("payload_slots", []):
        sx = float(slot.get("dx", float(slot.get("x", cx)) - (location or {}).get("x", 0)))
        sy = float(slot.get("dy", float(slot.get("y", cy)) - (location or {}).get("y", 0)))
        slot["dx"] = round(cx + (sx-cx)*math.cos(delta) - (sy-cy)*math.sin(delta), 6)
        slot["dy"] = round(cy + (sx-cx)*math.sin(delta) + (sy-cy)*math.cos(delta), 6)
        slot["rotation_deg"] = (float(slot.get("rotation_deg", 0)) + angle - old_angle) % 360
        slot.pop("x", None)
        slot.pop("y", None)


def similar_layout(reference, candidate, tolerance=5.0):
    """Match payload-bay counts and headings modulo 180, allowing reordered bays."""
    def angles(spaces):
        return sorted(space_geometry(s)[4] % 180 for s in spaces if not is_amr_space(s))
    left, right = angles(reference), angles(candidate)
    if not left or len(left) != len(right):
        return False
    # A circular order-preserving match avoids greedy errors at 0/180 degrees.
    return any(all(min(abs(a-b), 180-abs(a-b)) <= tolerance + 1e-6
                   for a, b in zip(left, right[offset:] + right[:offset]))
               for offset in range(len(right)))


class LocationSpacesManagerDialog(QDialog):
    """Edit a private draft, then apply only changed locations on Save all."""

    _space_is_amr_space = staticmethod(is_amr_space)

    def __init__(self, parent):
        super().__init__(parent)
        self.editor = parent
        self.source_store = parent.store
        self.store = JsonStore(parent.store.data)
        self._original = {loc["name"]: deepcopy(loc.get("inventory_spaces", []))
                          for loc in self.store.data.get("locations", [])}
        self._loading = False
        self._active_location = ""
        self.setWindowTitle("Locations & Inventory Spaces")
        self.resize(1380, 850)
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        hint = QLabel("Browse locations on the left and edit spaces on the right. "
                      "Detach a payload to accept any payload that fits, including a 90° turn. "
                      "Changes stay in this dialog until Save all.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter locations by name or floor")
        self.search_edit.textChanged.connect(self.filter_locations)
        left_layout.addWidget(self.search_edit)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Location / drop-off zone", "Floor", "Spaces", "Flexible"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            self.table.setColumnWidth(column, 60)
        self.table.currentCellChanged.connect(self.location_changed)
        left_layout.addWidget(self.table, 1)
        match_row = QHBoxLayout()
        self.similarity_tolerance = QDoubleSpinBox()
        self.similarity_tolerance.setRange(0, 45)
        self.similarity_tolerance.setValue(5)
        self.similarity_tolerance.setSuffix("°")
        similar = QPushButton("Select similar locations")
        similar.setToolTip("Select locations with the same number of payload spaces and matching "
                           "orientations within this tolerance. AMR spaces are excluded; "
                           "position, payload type and dimensions do not affect the match.")
        similar.clicked.connect(self.select_similar_locations)
        match_row.addWidget(similar)
        match_row.addWidget(self.similarity_tolerance)
        left_layout.addLayout(match_row)
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.location_label = QLabel("Select a location")
        right_layout.addWidget(self.location_label)
        self.spaces_table = QTableWidget(0, 8)
        self.spaces_table.setHorizontalHeaderLabels([
            "Space", "Payload / AMR", "Length m", "Width m", "Height m", "Angle °", "Flexible", "Charger"])
        self.spaces_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.spaces_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.spaces_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.spaces_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for column in range(2, 8):
            self.spaces_table.setColumnWidth(column, 76)
        self.spaces_table.itemChanged.connect(self.space_edited)
        self.spaces_table.itemSelectionChanged.connect(self.refresh_preview)
        right_layout.addWidget(self.spaces_table, 2)
        actions = QHBoxLayout()
        for label, callback in [("Add flexible space", self.add_space),
                                ("Duplicate selected", self.duplicate_spaces),
                                ("Delete selected", self.delete_spaces)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        right_layout.addLayout(actions)
        template_row = QHBoxLayout()
        self.payload_combo = QComboBox()
        self.payload_combo.addItems([p["name"] for p in self.store.data.get("payloads", [])])
        attach = QPushButton("Attach payload to selected")
        attach.clicked.connect(self.attach_payload)
        template_row.addWidget(self.payload_combo, 1)
        template_row.addWidget(attach)
        right_layout.addLayout(template_row)
        amr_row = QHBoxLayout()
        self.amr_combo = QComboBox()
        self.amr_combo.addItems([a.get("id") or a.get("name", "")
                                for a in self.store.data.get("amrs", [])])
        add_amr = QPushButton("Add AMR space")
        add_amr.clicked.connect(self.add_amr_space)
        amr_row.addWidget(self.amr_combo, 1)
        amr_row.addWidget(add_amr)
        right_layout.addLayout(amr_row)
        bulk = QHBoxLayout()
        self.length_spin = self.dimension_spin()
        self.width_spin = self.dimension_spin()
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Selected spaces", "Current location", "Selected locations", "All locations"])
        bulk.addWidget(QLabel("Length m"))
        bulk.addWidget(self.length_spin)
        bulk.addWidget(QLabel("Width m"))
        bulk.addWidget(self.width_spin)
        bulk.addWidget(self.scope_combo)
        right_layout.addLayout(bulk)
        bulk_actions = QHBoxLayout()
        detach = QPushButton("Detach payloads in scope")
        detach.clicked.connect(self.detach_payloads)
        resize = QPushButton("Apply dimensions to flexible spaces in scope")
        resize.clicked.connect(self.apply_dimensions)
        bulk_actions.addWidget(detach)
        bulk_actions.addWidget(resize)
        right_layout.addLayout(bulk_actions)
        self.scene = QGraphicsScene(self)
        self.preview = InventoryPreviewView(self.scene)
        self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview.setMinimumHeight(160)
        right_layout.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([400, 960])
        self.status_label = QLabel("Fixed payload and AMR dimensions follow their templates. "
                                   "Detach payloads before resizing. Angles rotate the bay around its centre.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Save all")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_table()
        polish_dialog(self)

    def dimension_spin(self):
        field = QDoubleSpinBox()
        field.setDecimals(3)
        field.setRange(0.001, 999999)
        field.setValue(1.0)
        return field

    def _location_rows(self):
        zones = set()
        for dept in self.store.data.get("departments", []):
            for entry in dept.get("task_generation_locations", {}).values():
                if isinstance(entry, dict):
                    names = entry.get("dropoff_zone_locations", entry.get("drop_off_zone_locations", []))
                    zones.update([names] if isinstance(names, str) else names or [])
        rows = []
        for loc in self.store.data.get("locations", []):
            spaces = loc.get("inventory_spaces", [])
            amrs = [s for s in spaces if is_amr_space(s)]
            payloads = [s for s in spaces if not is_amr_space(s)]
            rows.append(dict(name=loc["name"], floor=loc.get("floor", 0),
                             role="Drop-off zone" if loc["name"] in zones else "Location",
                             total=len(spaces), payload=len(payloads), amr=len(amrs),
                             flexible=sum(bool(s.get("flexible")) for s in payloads),
                             chargers=sum(bool(s.get("has_charger")) for s in amrs)))
        return sorted(rows, key=lambda row: (row["floor"], row["name"].lower()))

    def selected_location_name(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else ""

    def selected_location_names(self):
        return [self.table.item(i.row(), 0).data(Qt.UserRole)
                for i in self.table.selectionModel().selectedRows()]

    def refresh_table(self):
        selected = set(self.selected_location_names())
        current = self._active_location or self.selected_location_name()
        self._loading = True
        self.table.setRowCount(0)
        self._rows = self._location_rows()
        for row, data in enumerate(self._rows):
            self.table.insertRow(row)
            for col, key in enumerate(("name", "floor", "total", "flexible")):
                item = QTableWidgetItem(str(data[key]))
                item.setData(Qt.UserRole, data["name"])
                item.setToolTip(f"{data['role']} | {data['payload']} payload spaces | "
                                f"{data['amr']} AMR spaces | {data['chargers']} chargers")
                self.table.setItem(row, col, item)
            if data["name"] == current:
                self.table.setCurrentCell(row, 0)
        if not current and self._rows:
            self.table.setCurrentCell(0, 0)
        if selected:
            self.table.clearSelection()
            for row, data in enumerate(self._rows):
                if data["name"] in selected:
                    for col in range(self.table.columnCount()):
                        self.table.item(row, col).setSelected(True)
        self._loading = False
        self.summary_label.setText(f"{len(self._rows)} locations | "
                                   f"{sum(r['total'] for r in self._rows)} inventory spaces")
        self.filter_locations()
        self.location_changed()

    def filter_locations(self, *_args):
        query = self.search_edit.text().casefold().strip()
        for row in range(self.table.rowCount()):
            text = " ".join(self.table.item(row, c).text() for c in (0, 1)).casefold()
            self.table.setRowHidden(row, bool(query and query not in text))

    def location_changed(self, *_args):
        if self._loading:
            return
        previous = self._active_location
        self._active_location = self.selected_location_name()
        self.location_label.setText(self._active_location or "Select a location")
        self.refresh_spaces([] if previous != self._active_location else None)

    def current_spaces(self):
        loc = self.store.get_location(self._active_location)
        return loc.setdefault("inventory_spaces", []) if loc else []

    def selected_space_indices(self):
        return [index.row() for index in self.spaces_table.selectionModel().selectedRows()]

    def refresh_spaces(self, selected=None):
        if selected is None:
            selected = self.selected_space_indices()
        self._loading = True
        self.spaces_table.setRowCount(0)
        loc = self.store.get_location(self._active_location)
        for row, space in enumerate(self.current_spaces()):
            self.spaces_table.insertRow(row)
            _, _, length, width, angle = space_geometry(space, loc)
            amr = is_amr_space(space)
            flexible = bool(space.get("flexible")) and not amr
            binding = ", ".join(s.get("payload", s.get("amr_type", ""))
                                for s in space.get("payload_slots", []))
            values = [space.get("name", ""), binding or ("Any fitting payload" if flexible else "Unassigned"),
                      f"{length:.3f}", f"{width:.3f}", f"{space.get('height_m', 999999):.3f}",
                      f"{angle:.1f}", flexible, bool(space.get("has_charger"))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value) if col < 6 else "")
                if col == 1 or (col in (2, 3) and not flexible):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col in (6, 7):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col == 7 and amr:
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if value else Qt.Unchecked)
                    if col == 6 or not amr:
                        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                self.spaces_table.setItem(row, col, item)
        for row in selected or []:
            if row < self.spaces_table.rowCount():
                for col in range(self.spaces_table.columnCount()):
                    self.spaces_table.item(row, col).setSelected(True)
        self._loading = False
        self.refresh_preview()

    def space_edited(self, item):
        if self._loading:
            return
        row, col = item.row(), item.column()
        space = self.current_spaces()[row]
        try:
            if col == 0:
                if not item.text().strip():
                    raise ValueError("Space name cannot be empty.")
                space["name"] = item.text().strip()
            elif col in (2, 3, 4, 5):
                value = float(item.text())
                if not math.isfinite(value) or (col != 5 and value <= 0):
                    raise ValueError("Dimensions must be positive; all values must be finite.")
                if col == 4:
                    space["height_m"] = value
                else:
                    loc = self.store.get_location(self._active_location)
                    _, _, length, width, angle = space_geometry(space, loc)
                    resize_space(space, value if col == 2 else length,
                                 value if col == 3 else width, value if col == 5 else angle, loc)
            elif col == 7 and is_amr_space(space):
                space["has_charger"] = item.checkState() == Qt.Checked
            self.status_label.setText("Draft updated. Save all applies changes to the configuration.")
        except ValueError as exc:
            self.status_label.setText(str(exc))
        self.refresh_spaces([row])

    def targets(self):
        scope = self.scope_combo.currentIndex()
        if scope == 0:
            spaces = self.current_spaces()
            return [(self._active_location, i, spaces[i]) for i in self.selected_space_indices()]
        names = ([self._active_location] if scope == 1 else self.selected_location_names()
                 if scope == 2 else [loc["name"] for loc in self.store.data.get("locations", [])])
        return [(name, i, space) for name in names if self.store.get_location(name)
                for i, space in enumerate(self.store.get_location(name).get("inventory_spaces", []))]

    def detach_payloads(self):
        count = skipped = 0
        for name, _, space in self.targets():
            if is_amr_space(space):
                skipped += 1
                continue
            _, _, length, width, _ = space_geometry(space, self.store.get_location(name))
            space["length_m"] = round(length, 3)
            space["width_m"] = round(width, 3)
            space["payload_slots"] = []
            space.pop("payload", None)
            space["flexible"] = True
            count += 1
        self.refresh_table()
        self.status_label.setText(f"Detached {count} payload space(s); skipped {skipped} AMR space(s). "
                                   "Position, orientation and height are preserved. Save all to apply.")

    def apply_dimensions(self):
        count = skipped = 0
        for name, _, space in self.targets():
            if is_amr_space(space) or not space.get("flexible"):
                skipped += 1
                continue
            resize_space(space, self.length_spin.value(), self.width_spin.value(),
                         location=self.store.get_location(name))
            count += 1
        self.refresh_spaces()
        self.status_label.setText(f"Resized {count} flexible space(s); skipped {skipped} fixed/AMR space(s). "
                                   "Centres and orientations preserved. Review the layout before Save all.")

    def select_similar_locations(self):
        reference = deepcopy(self.current_spaces())
        tolerance = self.similarity_tolerance.value()
        self.search_edit.clear()
        self.table.clearSelection()
        count = 0
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).data(Qt.UserRole)
            if similar_layout(reference, self.store.get_location(name).get("inventory_spaces", []), tolerance):
                for col in range(self.table.columnCount()):
                    self.table.item(row, col).setSelected(True)
                count += 1
        self.scope_combo.setCurrentText("Selected locations")
        self.status_label.setText(f"Selected {count} location(s) with matching payload-space counts "
                                   f"and orientations within {tolerance:g}°. Bulk scope: Selected locations.")

    def add_space(self):
        if not self._active_location:
            return
        spaces = self.current_spaces()
        space = dict(name=self.unique_name("Flexible space"), payload_slots=[], flexible=True,
                     height_m=999999.0, points=[])
        resize_space(space, self.length_spin.value(), self.width_spin.value())
        # Place after the existing bays, leaving a visible gap.
        if spaces:
            edge = max(float(p.get("dx", 0)) for s in spaces for p in s.get("points", []))
            for p in space["points"]:
                p["dx"] += edge + self.length_spin.value()/2 + 0.1
        spaces.append(space)
        self.refresh_table()
        self.refresh_spaces([len(spaces)-1])

    def unique_name(self, prefix):
        names = {s.get("name") for s in self.current_spaces()}
        number = 1
        while f"{prefix} {number}" in names:
            number += 1
        return f"{prefix} {number}"

    def add_amr_space(self):
        amr_name = self.amr_combo.currentText()
        amr = next((a for a in self.store.data.get("amrs", [])
                    if (a.get("id") or a.get("name")) == amr_name), None)
        if not amr or not self._active_location:
            return
        self.add_space()
        space = self.current_spaces()[-1]
        resize_space(space, float(amr.get("length_m", 0.8)), float(amr.get("width_m", 0.6)))
        cx, cy, _, _, angle = space_geometry(space)
        space.update(name=self.unique_name(amr_name + " bay"), stores_amr=True,
                     space_type="amr", amr_type=amr_name, has_charger=False,
                     flexible=False, height_m=float(amr.get("height_m", 999999)),
                     payload_slots=[dict(slot_type="amr", amr_type=amr_name,
                                         dx=cx, dy=cy, rotation_deg=angle)])
        self.refresh_table()

    def duplicate_spaces(self):
        spaces = self.current_spaces()
        for row in self.selected_space_indices():
            space = deepcopy(spaces[row])
            space["name"] = self.unique_name(space.get("name", "Space") + " copy")
            for point in space.get("points", []):
                point["dx"] = float(point.get("dx", 0)) + 0.2
                point["dy"] = float(point.get("dy", 0)) + 0.2
            for slot in space.get("payload_slots", []):
                slot["dx"] = float(slot.get("dx", 0)) + 0.2
                slot["dy"] = float(slot.get("dy", 0)) + 0.2
            for key in ("occupied", "payload_instance_id", "amr_id", "reserved_by_amr", "reserved_by_task"):
                space.pop(key, None)
            spaces.append(space)
        self.refresh_table()

    def delete_spaces(self):
        spaces = self.current_spaces()
        for row in sorted(self.selected_space_indices(), reverse=True):
            del spaces[row]
        self.refresh_table()

    def attach_payload(self):
        payload = next((p for p in self.store.data.get("payloads", [])
                        if p["name"] == self.payload_combo.currentText()), None)
        if not payload:
            return
        for row in self.selected_space_indices():
            space = self.current_spaces()[row]
            if is_amr_space(space):
                continue
            loc = self.store.get_location(self._active_location)
            cx, cy, _, _, angle = space_geometry(space, loc)
            space["payload_slots"] = []
            resize_space(space, float(payload.get("length_m", 1)), float(payload.get("width_m", 1)), location=loc)
            space["payload_slots"] = [dict(payload=payload["name"], dx=cx, dy=cy, rotation_deg=angle)]
            space["flexible"] = False
            space["height_m"] = max(float(space.get("height_m", 0)), float(payload.get("height_m", 0)))
        self.refresh_table()

    def refresh_preview(self):
        if self._loading:
            return
        self.scene.clear()
        selected = set(self.selected_space_indices())
        for i, space in enumerate(self.current_spaces()):
            points = self.store.inventory_space_points_absolute(self._active_location, space)
            if not points:
                continue
            color = QColor("#2563eb" if i in selected else "#718096")
            polygon = QPolygonF([QPointF(p["x"], -p["y"]) for p in points])
            self.scene.addPolygon(polygon, QPen(color, 0), QBrush(QColor("#dbeafe")))
            label = self.scene.addSimpleText(str(i + 1))
            label.setScale(0.025)
            label.setPos(polygon.boundingRect().center())
        bounds = self.scene.itemsBoundingRect()
        if not bounds.isEmpty():
            bounds = bounds.adjusted(-0.3, -0.3, 0.3, 0.3)
            self.scene.setSceneRect(bounds)
            self.preview.fitInView(bounds, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scene"):
            self.refresh_preview()

    def accept(self):
        changed = []
        for loc in self.store.data.get("locations", []):
            if loc.get("inventory_spaces", []) != self._original.get(loc["name"], []):
                changed.append(loc)
        for loc in changed:
            self.source_store.set_location_inventory_spaces(loc["name"], loc.get("inventory_spaces", []))
            # The model normalises a whole location when saving. Keep untouched
            # bays byte-for-byte equivalent, including custom/charger metadata.
            saved = self.source_store.get_location(loc["name"])["inventory_spaces"]
            for index, space in enumerate(loc.get("inventory_spaces", [])):
                if index < len(saved) and space in self._original.get(loc["name"], []):
                    saved[index] = deepcopy(space)
                elif index < len(saved):
                    saved[index] = {**deepcopy(space), **saved[index]}
        if changed and hasattr(self.editor, "refresh_canvas"):
            self.editor.refresh_canvas()
        if changed and hasattr(self.editor, "set_status"):
            self.editor.set_status(f"Updated inventory spaces at {len(changed)} location(s)")
        super().accept()
