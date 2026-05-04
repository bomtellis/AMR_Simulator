import math
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGraphicsPolygonItem,
    QGraphicsScene, QGraphicsTextItem, QGraphicsView, QHBoxLayout, QInputDialog,
    QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget
)

from amr_dxf_scene import DXFScene
from amr_dialogs import LiftEditorDialog, PointEditorDialog, TableListEditor
from amr_advanced_dialogs import RouteProfilesEditorV2, TaskEditorWindow, TaskPlannerDialog
from models import JsonStore


class GraphView(QGraphicsView):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self._overlay_provider = None
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QBrush(QColor("#111111")))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

    def set_overlay_provider(self, overlay_provider):
        self._overlay_provider = overlay_provider
        self.viewport().update()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self._overlay_provider:
            painter.save()
            painter.resetTransform()
            self._overlay_provider(painter, self.viewport().rect())
            painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.editor.on_left_click(event)
            return
        if event.button() == Qt.MiddleButton:
            self.editor.on_middle_click(event)
            return
        if event.button() == Qt.RightButton:
            self.editor.on_right_click(event)
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.editor.on_double_click(event)
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.editor.on_left_release(event)
            return
        if event.button() == Qt.MiddleButton:
            self.editor.on_middle_release(event)
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.editor.on_drag(event)
            return
        if event.buttons() & Qt.MiddleButton:
            self.editor.on_middle_drag(event)
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.editor.on_mousewheel(event)
        event.accept()


class AMRGraphEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMR Simulation Graph Editor")
        self.resize(1500, 920)

        self.store = JsonStore()
        self.current_json_path = None
        self.current_dxf_path = None
        self.loaded_dxf_floor = None
        self.dxf_scene = DXFScene()

        self.scale = 5.0
        self.offset_x = 250
        self.offset_y = 250
        self.last_pan = None
        self.selected_for_edge = None
        self.selected_point_name = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.edge_delete_start = None

        self.scene = QGraphicsScene(self)
        self._build_ui()
        self.refresh_canvas()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(260)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self.sidebar)

        self.view = GraphView(self)
        self.view.setScene(self.scene)
        self.view.set_overlay_provider(self.draw_overlay_panels)
        root.addWidget(self.view, 1)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["select_move", "corridor_node", "location", "edge", "lift", "pan", "delete"])
        self.floor_spin = QSpinBox(); self.floor_spin.setRange(0, 99); self.floor_spin.setValue(0); self.floor_spin.valueChanged.connect(self.on_floor_changed)
        self.snap_check = QCheckBox("Snap to 1.0"); self.snap_check.setChecked(True)
        self.bidirectional_check = QCheckBox("Bidirectional edges"); self.bidirectional_check.setChecked(True)
        self.show_dxf_check = QCheckBox("Show DXF"); self.show_dxf_check.setChecked(True); self.show_dxf_check.stateChanged.connect(lambda *_: self.refresh_canvas())
        self.show_labels_check = QCheckBox("Show labels"); self.show_labels_check.setChecked(True); self.show_labels_check.stateChanged.connect(lambda *_: self.refresh_canvas())
        self.status_label = QLabel("Ready"); self.status_label.setWordWrap(True)
        self.file_label = QLabel("New file"); self.file_label.setWordWrap(True)

        self._build_sidebar()

    def _add_label(self, text):
        lbl = QLabel(text); self.sidebar_layout.addWidget(lbl); return lbl
    def _add_button(self, text, slot):
        btn = QPushButton(text); btn.clicked.connect(slot); self.sidebar_layout.addWidget(btn); return btn

    def _build_sidebar(self):
        self._add_label("Mode")
        self.sidebar_layout.addWidget(self.mode_combo)
        self._add_label("Floor")
        row = QHBoxLayout(); row.addWidget(self.floor_spin); go = QPushButton("Go"); go.clicked.connect(self.refresh_canvas); row.addWidget(go); self.sidebar_layout.addLayout(row)
        self.sidebar_layout.addWidget(self.snap_check)
        self.sidebar_layout.addWidget(self.bidirectional_check)
        self.sidebar_layout.addWidget(self.show_dxf_check)
        self.sidebar_layout.addWidget(self.show_labels_check)
        self._add_button("Open JSON", self.open_json)
        self._add_button("Save JSON", self.save_json)
        self._add_button("Map DXF to Floor", self.load_dxf)
        self._add_button("Clear Floor DXF", self.clear_floor_dxf)
        self._add_button("Fit View", self.fit_view)
        self._add_button("Validate", self.validate_json)
        self._add_button("Payloads", self.manage_payloads)
        self._add_button("AMRs", self.manage_amrs)
        self._add_button("Tasks", self.manage_tasks)
        self._add_button("Task Planner", self.manage_task_planner)
        self._add_button("Route Profiles", self.manage_route_profiles)
        self._add_label("Current file"); self.sidebar_layout.addWidget(self.file_label)
        self._add_label("Status"); self.sidebar_layout.addWidget(self.status_label)
        self.sidebar_layout.addStretch(1)

    def set_status(self, text):
        self.status_label.setText(text)

    def on_floor_changed(self, *_):
        self.refresh_canvas()

    def floor_dxf_entries(self):
        return self.store.data.setdefault("floor_dxf_files", [])

    def get_floor_dxf_path(self, floor):
        for entry in self.floor_dxf_entries():
            try:
                if int(entry.get("floor")) == int(floor):
                    path = (entry.get("filepath") or "").strip()
                    return path or None
            except Exception:
                continue
        return None

    def set_floor_dxf_path(self, floor, filepath):
        entries = self.floor_dxf_entries(); payload = {"floor": int(floor), "filepath": str(filepath)}
        for entry in entries:
            try:
                if int(entry.get("floor")) == int(floor):
                    entry.clear(); entry.update(payload); return
            except Exception:
                continue
        entries.append(payload); entries.sort(key=lambda item: int(item.get("floor", 0)))

    def clear_floor_dxf_mapping(self, floor):
        self.store.data["floor_dxf_files"] = [entry for entry in self.floor_dxf_entries() if int(entry.get("floor", -(10**9))) != int(floor)]

    def ensure_floor_dxf_loaded(self, floor, fit=False):
        target_path = self.get_floor_dxf_path(floor)
        if not target_path:
            if self.loaded_dxf_floor is not None or self.dxf_scene.entities:
                self.dxf_scene.clear(); self.current_dxf_path = None; self.loaded_dxf_floor = None
            return False
        if self.current_dxf_path == target_path and self.loaded_dxf_floor == int(floor):
            return True
        try:
            self.dxf_scene.load(target_path); self.current_dxf_path = target_path; self.loaded_dxf_floor = int(floor)
            if fit: self.fit_view()
            return True
        except Exception as exc:
            self.dxf_scene.clear(); self.current_dxf_path = None; self.loaded_dxf_floor = None
            self.set_status(f"Failed to load DXF for floor {floor}: {exc}")
            return False

    def world_to_scene(self, x, y):
        return QPointF(float(x), -float(y))

    def scene_to_world(self, sx, sy):
        return float(sx), -float(sy)

    def event_scene_pos(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        return self.view.mapToScene(pos)

    def snap(self, x, y):
        return (round(x), round(y)) if self.snap_check.isChecked() else (round(x, 3), round(y, 3))

    def _content_bounds(self, floor):
        bounds = []
        if self.dxf_scene.bounds and self.loaded_dxf_floor == int(floor):
            bounds.append(self.dxf_scene.bounds)

        floor_points = self.store.points_for_floor(floor)
        if floor_points:
            xs = [float(p["x"]) for p in floor_points.values()]
            ys = [float(p["y"]) for p in floor_points.values()]
            bounds.append((min(xs), min(ys), max(xs), max(ys)))

        if not bounds:
            return None

        return (
            min(b[0] for b in bounds),
            min(b[1] for b in bounds),
            max(b[2] for b in bounds),
            max(b[3] for b in bounds),
        )

    def _scene_rect_for_floor(self, floor, padding=8.0):
        bounds = self._content_bounds(floor)
        if not bounds:
            return None
        min_x, min_y, max_x, max_y = bounds
        return QRectF(
            min_x - padding,
            -(max_y + padding),
            max(1.0, (max_x - min_x) + (padding * 2)),
            max(1.0, (max_y - min_y) + (padding * 2)),
        )

    def fit_view(self):
        floor = self.floor_spin.value()
        self.ensure_floor_dxf_loaded(floor, fit=False)
        rect = self._scene_rect_for_floor(floor, padding=8.0)

        if rect is not None and not rect.isNull() and rect.width() > 0 and rect.height() > 0:
            self.view.resetTransform()
            self.view.fitInView(rect, Qt.KeepAspectRatio)
            self.scene.setSceneRect(rect.adjusted(-40, -40, 40, 40))
            self.view.viewport().update()

        self.refresh_canvas()

    def refresh_canvas(self):
        self.scene.clear()
        floor = self.floor_spin.value()
        self.ensure_floor_dxf_loaded(floor, fit=False)
        self.scene.setBackgroundBrush(QBrush(QColor("#111111")))

        rect = self._scene_rect_for_floor(floor, padding=8.0)
        if rect is not None:
            self.scene.setSceneRect(rect.adjusted(-40, -40, 40, 40))

        if (
            self.show_dxf_check.isChecked()
            and self.loaded_dxf_floor == int(floor)
            and self.dxf_scene.entities
        ):
            self.dxf_scene.populate_graphics_scene(
                self.scene,
                self.view.transform().m11(),
            )

        self.draw_edges(floor)
        self.draw_points(floor)
        self.file_label.setText(self.current_json_path or "New file")
        self.view.viewport().update()

    def draw_edges(self, floor):
        points = self.store.all_points()
        pen = QPen(QColor("#6aa9ff"), 0)

        for edge in self.store.edges_for_floor(floor):
            a = points.get(edge["from"])
            b = points.get(edge["to"])
            if not a or not b:
                continue

            pa = self.world_to_scene(a["x"], a["y"])
            pb = self.world_to_scene(b["x"], b["y"])
            self.scene.addLine(pa.x(), pa.y(), pb.x(), pb.y(), pen)

    def draw_points(self, floor):
        for name, point in self.store.points_for_floor(floor).items():
            pos = self.world_to_scene(point["x"], point["y"])
            selected = name == self.selected_point_name
            kind = point.get("kind")

            outline = QPen(QColor("#ffffff") if selected else QColor("transparent"), 0)

            if kind == "location":
                r = 0.3
                self.scene.addEllipse(
                    pos.x() - r,
                    pos.y() - r,
                    2 * r,
                    2 * r,
                    outline,
                    QBrush(QColor("#18c37e")),
                )
                label_color = QColor("#9bf0cd")

            elif kind == "corridor_node":
                r = 0.3
                self.scene.addRect(
                    pos.x() - r,
                    pos.y() - r,
                    2 * r,
                    2 * r,
                    outline,
                    QBrush(QColor("#f2c94c")),
                )
                label_color = QColor("#ffe8a3")

            else:
                r = 0.5
                poly = QPolygonF(
                    [
                        QPointF(pos.x(), pos.y() - r),
                        QPointF(pos.x() + r, pos.y()),
                        QPointF(pos.x(), pos.y() + r),
                        QPointF(pos.x() - r, pos.y()),
                    ]
                )
                item = QGraphicsPolygonItem(poly)
                item.setBrush(QBrush(QColor("#ff7b72")))
                item.setPen(QPen(QColor("#ffffff") if selected else QColor("#ffb3ae"), 0.08))
                self.scene.addItem(item)
                label_color = QColor("#ffb3ae")

            if self.show_labels_check.isChecked():
                label = self.scene.addText(name)
                label.setDefaultTextColor(label_color)
                label.setScale(0.05)
                label.setPos(pos.x() + 0.45, pos.y() - 0.45)

    def draw_overlay_panels(self, painter, viewport_rect):
        floor = self.floor_spin.value()
        mapped_path = self.get_floor_dxf_path(floor)
        dxf_name = Path(mapped_path).name if mapped_path else "None"

        lines = [
            "Legend",
            "Green circle = location",
            "Yellow square = corridor node",
            "Red diamond = lift node",
            f"Mode: {self.mode_combo.currentText()} | Floor: {floor}",
            f"DXF: {dxf_name}",
            "Double-click a point to edit",
        ]

        self._draw_overlay_box(painter, 12, 12, 300, lines, "#333333", "white")

    def _draw_overlay_box(self, painter, x, y, w, lines, border_color, title_color):
        margin_x = 10
        margin_y = 8
        line_h = 18
        box_h = (margin_y * 2) + (len(lines) * line_h)

        painter.save()
        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(QBrush(QColor("#151515")))
        painter.drawRect(x, y, w, box_h)

        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)

        for i, line in enumerate(lines):
            painter.setPen(QColor(title_color if i == 0 else "white"))
            painter.drawText(x + margin_x, y + margin_y + 12 + (i * line_h), line)

        painter.restore()

    def find_nearest_point_name(self, x, y, floor, radius_world=3.0):
        best = None; best_dist = radius_world
        for name, point in self.store.points_for_floor(floor).items():
            d = math.hypot(point["x"] - x, point["y"] - y)
            if d <= best_dist: best = name; best_dist = d
        return best

    def on_left_click(self, event):
        mode = self.mode_combo.currentText(); floor = self.floor_spin.value(); pos = self.event_scene_pos(event); x, y = self.snap(*self.scene_to_world(pos.x(), pos.y()))
        if mode == "pan": self.last_pan = event.position().toPoint() if hasattr(event, "position") else event.pos(); return
        picked = self.find_nearest_point_name(x, y, floor); self.selected_point_name = picked
        if mode == "select_move":
            if picked: self.dragging_point_name = picked; self.drag_mode_active = True; self.set_status(f"Selected {picked}")
            self.refresh_canvas(); return
        if mode == "delete":
            if picked:
                if picked.startswith("Lift-") and "-F" in picked:
                    lift_id = picked.rsplit("-F", 1)[0]
                    if QMessageBox.question(self, "Delete lift", f"Delete entire {lift_id}?") == QMessageBox.Yes:
                        self.store.delete_lift(lift_id); self.selected_point_name = None; self.set_status(f"Deleted {lift_id}")
                else:
                    if QMessageBox.question(self, "Delete point", f"Delete {picked}?") == QMessageBox.Yes:
                        self.store.delete_point(picked); self.selected_point_name = None; self.set_status(f"Deleted {picked}")
                self.refresh_canvas()
            return
        if mode == "corridor_node":
            name, ok = QInputDialog.getText(self, "Corridor node", "Node name:", text=self.store.suggest_next_corridor_name(floor))
            if ok and name.strip(): self.store.add_corridor_node(name.strip(), floor, x, y); self.set_status(f"Added corridor node {name.strip()}"); self.refresh_canvas()
            return
        if mode == "location":
            name, ok = QInputDialog.getText(self, "Location", "Location name:")
            if ok and name.strip(): self.store.add_location(name.strip(), floor, x, y); self.set_status(f"Added location {name.strip()}"); self.refresh_canvas()
            return
        if mode == "edge":
            if not picked: self.set_status("No nearby point found"); return
            if self.selected_for_edge is None:
                self.selected_for_edge = picked; self.set_status(f"Edge start selected: {picked}")
            else:
                self.store.add_edge(self.selected_for_edge, picked)
                if self.bidirectional_check.isChecked(): self.store.add_edge(picked, self.selected_for_edge)
                self.set_status(f"Connected {self.selected_for_edge} -> {picked}"); self.selected_for_edge = None; self.refresh_canvas()
            return
        if mode == "lift":
            existing_lift = None
            if picked and picked.startswith("Lift-") and "-F" in picked:
                lift_id = picked.rsplit("-F", 1)[0]
                existing_lift = next((item for item in self.store.data.get("lifts", []) if item["id"] == lift_id), None)
            dialog = LiftEditorDialog(self, existing_lift, default_floor=floor, default_x=x, default_y=y)
            if dialog.exec() and dialog.result:
                self.store.upsert_lift(dialog.result["id"], dialog.result["served_floors"], dialog.result["floor_locations"], dialog.result["speed_floors_per_sec"], dialog.result["door_time_sec"], dialog.result["boarding_time_sec"], dialog.result["capacity_size_units"], dialog.result["start_floor"])
                self.set_status(f"Saved {dialog.result['id']}"); self.refresh_canvas()

    def on_double_click(self, event):
        floor = self.floor_spin.value(); pos = self.event_scene_pos(event); x, y = self.scene_to_world(pos.x(), pos.y()); picked = self.find_nearest_point_name(x, y, floor)
        if not picked: return
        point = self.store.all_points()[picked]
        if point.get("kind") == "lift_node":
            lift_id = point["lift_id"]; existing_lift = next((x for x in self.store.data.get("lifts", []) if x["id"] == lift_id), None)
            dialog = LiftEditorDialog(self, existing_lift, default_floor=floor, default_x=point["x"], default_y=point["y"])
            if dialog.exec() and dialog.result:
                self.store.upsert_lift(dialog.result["id"], dialog.result["served_floors"], dialog.result["floor_locations"], dialog.result["speed_floors_per_sec"], dialog.result["door_time_sec"], dialog.result["boarding_time_sec"], dialog.result["capacity_size_units"], dialog.result["start_floor"])
                self.set_status(f"Edited {dialog.result['id']}"); self.refresh_canvas()
            return
        dialog = PointEditorDialog(self, f"Edit {picked}", picked, point)
        if dialog.exec() and dialog.result:
            self.store.set_point_position(picked, dialog.result["x"], dialog.result["y"]); self.store.rename_point(picked, dialog.result["name"]); self.selected_point_name = dialog.result["name"]; self.set_status(f"Edited {dialog.result['name']}"); self.refresh_canvas()

    def on_left_release(self, event):
        self.dragging_point_name = None; self.drag_mode_active = False; self.last_pan = None

    def on_right_click(self, event):
        mode = self.mode_combo.currentText(); floor = self.floor_spin.value(); pos = self.event_scene_pos(event); x, y = self.scene_to_world(pos.x(), pos.y()); picked = self.find_nearest_point_name(x, y, floor)
        if mode == "edge":
            if picked and self.edge_delete_start is None:
                self.edge_delete_start = picked; self.selected_for_edge = None; self.set_status(f"Edge delete start selected: {picked}"); return
            if picked and self.edge_delete_start:
                before = len(self.store.data.get("corridors", {}).get("edges", [])); self.store.remove_edge(self.edge_delete_start, picked); removed = len(self.store.data.get("corridors", {}).get("edges", [])) < before
                if self.bidirectional_check.isChecked():
                    before = len(self.store.data.get("corridors", {}).get("edges", [])); self.store.remove_edge(picked, self.edge_delete_start); removed = removed or len(self.store.data.get("corridors", {}).get("edges", [])) < before
                self.edge_delete_start = None; self.set_status("Edge removed" if removed else "No matching edge to remove"); self.refresh_canvas(); return
        if picked: self.selected_point_name = picked; self.refresh_canvas()

    def on_drag(self, event):
        mode = self.mode_combo.currentText(); pt = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if mode == "pan":
            if self.last_pan is None: self.last_pan = pt; return
            dx = pt.x() - self.last_pan.x(); dy = pt.y() - self.last_pan.y()
            self.view.horizontalScrollBar().setValue(self.view.horizontalScrollBar().value() - dx)
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().value() - dy)
            self.last_pan = pt
            self.view.viewport().update()
            return
        if mode == "select_move" and self.drag_mode_active and self.dragging_point_name:
            pos = self.event_scene_pos(event); x, y = self.snap(*self.scene_to_world(pos.x(), pos.y())); self.store.set_point_position(self.dragging_point_name, x, y); self.refresh_canvas()

    def on_middle_click(self, event): self.last_pan = event.position().toPoint() if hasattr(event, "position") else event.pos()
    def on_middle_drag(self, event):
        pt = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self.last_pan is None: self.last_pan = pt; return
        dx = pt.x() - self.last_pan.x(); dy = pt.y() - self.last_pan.y()
        self.view.horizontalScrollBar().setValue(self.view.horizontalScrollBar().value() - dx)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().value() - dy)
        self.last_pan = pt
        self.view.viewport().update()
    def on_middle_release(self, event): self.last_pan = None
    def on_mousewheel(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.view.scale(factor, factor)
        self.refresh_canvas()

    def open_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open JSON", "", "JSON files (*.json)")
        if not path: return
        self.store = JsonStore.from_file(path); self.current_json_path = path; self.current_dxf_path = None; self.loaded_dxf_floor = None; self.dxf_scene.clear(); self.ensure_floor_dxf_loaded(self.floor_spin.value(), fit=True); self.set_status(f"Opened {Path(path).name}"); self.refresh_canvas()
    def save_json(self):
        path = self.current_json_path
        if not path: path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "", "JSON files (*.json)")
        if not path: return
        if not path.lower().endswith(".json"): path += ".json"
        self.store.save(path); self.current_json_path = path; self.set_status(f"Saved {Path(path).name}"); self.refresh_canvas()
    def load_dxf(self):
        floor = self.floor_spin.value(); existing = self.get_floor_dxf_path(floor); initial = str(Path(existing).expanduser().parent) if existing else ""
        path, _ = QFileDialog.getOpenFileName(self, "Map DXF to Floor", initial, "DXF files (*.dxf)")
        if not path: return
        try:
            self.set_floor_dxf_path(floor, path); self.dxf_scene.load(path); self.current_dxf_path = path; self.loaded_dxf_floor = int(floor); self.fit_view(); self.set_status(f"Mapped DXF {Path(path).name} to floor {floor}")
        except Exception as exc: QMessageBox.critical(self, "DXF load failed", str(exc))
    def clear_floor_dxf(self):
        floor = self.floor_spin.value(); existing = self.get_floor_dxf_path(floor)
        if not existing: self.set_status(f"No DXF mapped to floor {floor}"); return
        if QMessageBox.question(self, "Clear floor DXF", f"Remove DXF mapping for floor {floor}?") != QMessageBox.Yes: return
        self.clear_floor_dxf_mapping(floor)
        if self.loaded_dxf_floor == int(floor): self.dxf_scene.clear(); self.current_dxf_path = None; self.loaded_dxf_floor = None
        self.set_status(f"Removed DXF mapping from floor {floor}"); self.refresh_canvas()
    def validate_json(self):
        errors = self.store.validate()
        if errors: QMessageBox.critical(self, "Validation errors", "\n".join(errors[:100])); self.set_status(f"Validation failed with {len(errors)} error(s)")
        else: QMessageBox.information(self, "Validation", "JSON structure is internally consistent."); self.set_status("Validation passed")
    def manage_payloads(self):
        columns=[("name","Name",220),("weight_kg","Weight kg",120),("size_units","Size units",120)]
        self._child = TableListEditor(self,"Payloads",columns,self.store.data.get("payloads",[]),self._save_payloads); self._child.show()
    def _save_payloads(self, items): self.store.data["payloads"] = items; self.set_status("Payloads updated")
    def manage_amrs(self):
        columns=[("id","ID",120),("quantity","Quantity",80),("payload_capacity_kg","Payload kg",110),("payload_size_capacity","Payload size",110),("speed_m_per_sec","Speed",90),("motor_power_w","Motor W",90),("battery_capacity_kwh","Battery kWh",100),("battery_charge_rate_kw","Charge kW",100),("recharge_threshold_percent","Recharge %",100),("battery_soc_percent","SOC %",80),("start_location","Start location",160)]
        self._child = TableListEditor(self,"AMRs",columns,self.store.data.get("amrs",[]),self._save_amrs); self._child.show()
    def _save_amrs(self, items): self.store.data["amrs"] = items; self.set_status("AMRs updated")
    def build_floor_map(self, store):
        floor_map = {}
        for item in store.get("locations", []): floor_map[item["name"]] = int(item["floor"])
        for item in store.get("corridors", {}).get("nodes", []): floor_map[item["name"]] = int(item["floor"])
        for lift in store.get("lifts", []):
            for floor_str in lift.get("floor_locations", {}).keys(): floor_map[f"{lift['id']}-F{floor_str}"] = int(floor_str)
        return floor_map
    def manage_tasks(self):
        locations=self.store.data.get("locations",[]); location_names=sorted(x["name"] for x in locations); payload_names=sorted(x["name"] for x in self.store.data.get("payloads",[])); profile_names=[""]+sorted(self.store.data.get("route_profiles",{}).keys()); floor_map=self.build_floor_map(self.store.data)
        self._child = TaskEditorWindow(self,self.store.data.get("tasks",[]),location_names,payload_names,profile_names,self.store.suggest_next_task_id,self._save_tasks,floor_map=floor_map); self._child.show()
    def _save_tasks(self, items): self.store.data["tasks"] = items; self.set_status("Tasks updated")
    def manage_task_planner(self):
        locations=self.store.data.get("locations",[]); location_names=sorted(x["name"] for x in locations); payload_names=sorted(x["name"] for x in self.store.data.get("payloads",[])); profile_names=[""]+sorted(self.store.data.get("route_profiles",{}).keys()); floor_map=self.build_floor_map(self.store.data)
        self._child = TaskPlannerDialog(self,self.store.data.get("tasks",[]),location_names,payload_names,profile_names,self.store.suggest_next_task_id,self._save_tasks,floor_map=floor_map); self._child.show()
    def manage_route_profiles(self):
        point_names=set(self.store.names_in_use())|{x["name"] for x in self.store.data.get("locations",[])}; lift_ids={x["id"] for x in self.store.data.get("lifts",[])}; floor_map=self.build_floor_map(self.store.data)
        self._child = RouteProfilesEditorV2(self,self.store.data.get("route_profiles",{}),point_names,lift_ids,self.store.data.get("corridors",{}).get("edges",[]),self._save_route_profiles,floor_map=floor_map); self._child.show()
    def _save_route_profiles(self, profiles): self.store.data["route_profiles"] = profiles; self.set_status("Route profiles updated")


def main():
    app = QApplication(sys.argv)
    win = AMRGraphEditor()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
