import math
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal, QRect, QThread, Slot
from PySide6.QtGui import QAction, QColor, QBrush, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMenu,
)

from dxf_scene import DXFScene
from dialogs import (
    EdgeConnectionsDialog,
    LiftEditorDialog,
    PointEditorDialog,
    TableListEditor,
)
from advanced_dialogs import RouteProfilesEditorV2, TaskEditorWindow, TaskPlannerDialog
from models import JsonStore


class DXFLoadWorker(QObject):
    loaded = Signal(int, str, object, object)
    failed = Signal(int, str, str)

    @Slot(int, str)
    def load_floor(self, floor, path):
        try:
            payload = DXFScene.load_content(path)
            self.loaded.emit(
                int(floor), str(path), payload["entities"], payload["bounds"]
            )
        except Exception as exc:
            self.failed.emit(int(floor), str(path), str(exc))


class DXFLoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._completed = False
        self.setWindowTitle("Loading DXFs")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self.message_label = QLabel("Loading DXF files...")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("0 / 0")
        layout.addWidget(self.detail_label)

    def update_progress(self, current, total, message, failed_count=0):
        total = max(1, int(total))
        current = max(0, min(int(current), total))
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.message_label.setText(message)
        detail = f"{current} / {total} loaded"
        if failed_count:
            detail += f" ({failed_count} failed)"
        self.detail_label.setText(detail)

    def mark_complete(self):
        self._completed = True
        self.accept()

    def reject(self):
        if self._completed:
            super().reject()

    def closeEvent(self, event):
        if self._completed:
            super().closeEvent(event)
        else:
            event.ignore()


class EditorGraphicsView(QGraphicsView):
    leftClicked = Signal(object, float, float)
    leftDoubleClicked = Signal(object, float, float)
    leftReleased = Signal(object)
    rightClicked = Signal(object, float, float)
    middleClicked = Signal(object)
    middleDragged = Signal(object)
    middleReleased = Signal(object)
    mouseWheelScrolled = Signal(object)
    mouseDragged = Signal(object, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setBackgroundBrush(QBrush(QColor("#111111")))
        self._overlay_provider = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._middle_panning = False
        self._last_middle_pos = None

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.LeftButton:
            self.leftClicked.emit(event, scene_pos.x(), scene_pos.y())
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(event, scene_pos.x(), scene_pos.y())
        elif event.button() == Qt.MiddleButton:
            self._middle_panning = True
            self._last_middle_pos = event.position().toPoint()
            self.middleClicked.emit(event)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.LeftButton:
            self.leftDoubleClicked.emit(event, scene_pos.x(), scene_pos.y())
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.leftReleased.emit(event)
        elif event.button() == Qt.MiddleButton:
            self._middle_panning = False
            self._last_middle_pos = None
            self.middleReleased.emit(event)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._middle_panning and self._last_middle_pos is not None:
            self.middleDragged.emit(event)
        if event.buttons() & Qt.LeftButton:
            self.mouseDragged.emit(event, scene_pos.x(), scene_pos.y())
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.mouseWheelScrolled.emit(event)
        event.accept()

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


class AMRGraphEditor(QMainWindow):
    _request_dxf_load = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMR Simulation Graph Editor")
        self.resize(1500, 920)

        self.store = JsonStore()
        self.current_json_path = None
        self.current_dxf_path = None
        self.loaded_dxf_floor = None
        self.dxf_scene = DXFScene()
        self._dxf_cache = {}
        self._dxf_loading_floors = set()
        self._pending_fit_after_load = False
        self._last_requested_floor = None
        self._loading_dialog = None
        self._loading_batch_floors = set()
        self._loading_batch_failed = set()
        self._loading_batch_active = False

        self._dxf_thread = QThread(self)
        self._dxf_worker = DXFLoadWorker()
        self._dxf_worker.moveToThread(self._dxf_thread)
        self._dxf_worker.loaded.connect(self._on_dxf_loaded)
        self._dxf_worker.failed.connect(self._on_dxf_failed)
        self._request_dxf_load.connect(self._dxf_worker.load_floor)
        self._dxf_thread.start()

        self.scale = 5.0
        self.offset_x = 250
        self.offset_y = 250
        self.last_pan = None
        self.selected_for_edge = None
        self.selected_point_name = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.edge_delete_start = None

        self._item_lookup = {}
        self._point_item_lookup = {}

        self._build_ui()
        self.refresh_canvas()

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(260)
        sidebar_layout = QVBoxLayout(self.sidebar)
        layout.addWidget(self.sidebar)

        self.scene = QGraphicsScene(self)
        self.canvas = EditorGraphicsView(self)
        self.canvas.setScene(self.scene)
        self.canvas.set_overlay_provider(self.draw_overlay_panels)
        layout.addWidget(self.canvas, 1)

        self.canvas.leftClicked.connect(self.on_left_click)
        self.canvas.leftDoubleClicked.connect(self.on_double_click)
        self.canvas.leftReleased.connect(self.on_left_release)
        self.canvas.rightClicked.connect(self.on_right_click)
        self.canvas.middleClicked.connect(self.on_middle_click)
        self.canvas.middleDragged.connect(self.on_middle_drag)
        self.canvas.middleReleased.connect(self.on_middle_release)
        self.canvas.mouseWheelScrolled.connect(self.on_mousewheel)
        self.canvas.mouseDragged.connect(self.on_drag)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                "select_move",
                "corridor_node",
                "location",
                "edge",
                "lift",
                "pan",
                "delete",
            ]
        )
        self.floor_spin = QSpinBox()
        self.floor_spin.setRange(0, 99)
        self.floor_spin.valueChanged.connect(self.on_floor_changed)
        self.snap_check = QCheckBox("Snap to 1.0")
        self.snap_check.setChecked(True)
        self.bidirectional_check = QCheckBox("Bidirectional edges")
        self.bidirectional_check.setChecked(True)
        self.show_dxf_check = QCheckBox("Show DXF")
        self.show_dxf_check.setChecked(True)
        self.show_labels_check = QCheckBox("Show labels")
        self.show_labels_check.setChecked(True)
        self.show_dxf_check.toggled.connect(self.refresh_canvas)
        self.show_labels_check.toggled.connect(self.refresh_canvas)

        sidebar_layout.addWidget(QLabel("Mode"))
        sidebar_layout.addWidget(self.mode_combo)
        sidebar_layout.addSpacing(10)
        sidebar_layout.addWidget(QLabel("Floor"))
        floor_row = QHBoxLayout()
        floor_row.addWidget(self.floor_spin)
        go_btn = QPushButton("Go")
        go_btn.clicked.connect(self.refresh_canvas)
        floor_row.addWidget(go_btn)
        sidebar_layout.addLayout(floor_row)
        sidebar_layout.addSpacing(10)
        sidebar_layout.addWidget(self.snap_check)
        sidebar_layout.addWidget(self.bidirectional_check)
        sidebar_layout.addWidget(self.show_dxf_check)
        sidebar_layout.addWidget(self.show_labels_check)
        sidebar_layout.addSpacing(10)

        for text, handler in [
            ("Open JSON", self.open_json),
            ("Save JSON", self.save_json),
            ("Map DXF to Floor", self.load_dxf),
            ("Clear Floor DXF", self.clear_floor_dxf),
            ("Fit View", self.fit_view),
            ("Validate", self.validate_json),
            ("Payloads", self.manage_payloads),
            ("AMRs", self.manage_amrs),
            ("Tasks", self.manage_tasks),
            ("Task Planner", self.manage_task_planner),
            ("Route Profiles", self.manage_route_profiles),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            sidebar_layout.addWidget(btn)
            if text in {"Validate", "Route Profiles"}:
                sidebar_layout.addSpacing(10)

        sidebar_layout.addWidget(QLabel("Current file"))
        self.file_label = QLabel("New file")
        self.file_label.setWordWrap(True)
        sidebar_layout.addWidget(self.file_label)
        sidebar_layout.addWidget(QLabel("Status"))
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        sidebar_layout.addWidget(self.status_label)
        sidebar_layout.addStretch(1)

    def set_status(self, text):
        self.status_label.setText(text)

    def on_floor_changed(self, *_):
        self.refresh_canvas()
        self._queue_all_floor_dxf_loads(
            active_floor=self.floor_spin.value(), force_reload=False
        )

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
        entries = self.floor_dxf_entries()
        payload = {"floor": int(floor), "filepath": str(filepath)}
        for entry in entries:
            try:
                if int(entry.get("floor")) == int(floor):
                    entry.clear()
                    entry.update(payload)
                    return
            except Exception:
                continue
        entries.append(payload)
        entries.sort(key=lambda item: int(item.get("floor", 0)))

    def clear_floor_dxf_mapping(self, floor):
        self.store.data["floor_dxf_files"] = [
            entry
            for entry in self.floor_dxf_entries()
            if int(entry.get("floor", -(10**9))) != int(floor)
        ]

    def _all_mapped_floors(self):
        floors = []
        for entry in self.floor_dxf_entries():
            try:
                floor = int(entry.get("floor"))
            except Exception:
                continue
            if self.get_floor_dxf_path(floor):
                floors.append(floor)
        return sorted(set(floors))

    def _ensure_loading_dialog(self):
        if self._loading_dialog is None:
            self._loading_dialog = DXFLoadingDialog(self)
        return self._loading_dialog

    def _update_loading_dialog(self):
        if not self._loading_batch_active:
            return
        dialog = self._ensure_loading_dialog()
        total = len(self._loading_batch_floors)
        completed = 0
        for floor in self._loading_batch_floors:
            path = self.get_floor_dxf_path(floor)
            cached = self._dxf_cache.get(floor)
            if cached and path and cached.get("path") == path:
                completed += 1
            elif floor in self._loading_batch_failed:
                completed += 1
        failed_count = len(self._loading_batch_failed)
        pending = max(0, total - completed)
        message = f"Loading {total} DXF file(s)..."
        if pending:
            message = f"Loading {pending} remaining DXF file(s)..."
        elif failed_count:
            message = "Finished loading DXFs with some failures."
        else:
            message = "Finished loading all DXFs."
        dialog.update_progress(completed, total, message, failed_count=failed_count)
        if total > 0 and not dialog.isVisible():
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        QApplication.processEvents()
        if total > 0 and completed >= total:
            dialog.mark_complete()
            self._loading_batch_active = False

    def _start_loading_batch(self, floors):
        target_floors = []
        for floor in floors:
            floor = int(floor)
            path = self.get_floor_dxf_path(floor)
            if path:
                target_floors.append(floor)
        target_floors = sorted(set(target_floors))
        if not target_floors:
            return
        self._loading_batch_floors = set(target_floors)
        self._loading_batch_failed = set()
        self._loading_batch_active = True
        dialog = self._ensure_loading_dialog()
        dialog._completed = False
        self._update_loading_dialog()

    def _queue_all_floor_dxf_loads(self, active_floor=None, force_reload=False):
        floors = self._all_mapped_floors()
        if not floors:
            return
        if active_floor is not None:
            floors = [int(active_floor)] + [
                f for f in floors if int(f) != int(active_floor)
            ]
        self._start_loading_batch(floors)
        for floor in floors:
            self.request_floor_dxf_load(
                floor,
                force_reload=force_reload and int(floor) == int(active_floor),
                prefetch=int(floor)
                != int(active_floor if active_floor is not None else floor),
            )
        self._update_loading_dialog()

    def _clear_dxf_cache(self):
        self._dxf_cache.clear()
        self._dxf_loading_floors.clear()
        self._loading_batch_floors.clear()
        self._loading_batch_failed.clear()
        self._loading_batch_active = False
        if self._loading_dialog is not None and self._loading_dialog.isVisible():
            self._loading_dialog.mark_complete()
        self.current_dxf_path = None
        self.loaded_dxf_floor = None
        self.dxf_scene.clear()

    def _set_active_dxf_floor(self, floor):
        floor = int(floor)
        cached = self._dxf_cache.get(floor)
        if not cached:
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
            self.dxf_scene.clear()
            return False
        self.current_dxf_path = cached["path"]
        self.loaded_dxf_floor = floor
        self.dxf_scene.set_content(cached["path"], cached["entities"], cached["bounds"])
        return True

    def request_floor_dxf_load(self, floor, force_reload=False, prefetch=False):
        floor = int(floor)
        path = self.get_floor_dxf_path(floor)
        if not path:
            if not prefetch and floor == self.floor_spin.value():
                self.dxf_scene.clear()
                self.current_dxf_path = None
                self.loaded_dxf_floor = None
            return False

        cached = self._dxf_cache.get(floor)
        if (not force_reload) and cached and cached.get("path") == path:
            if not prefetch and floor == self.floor_spin.value():
                self._set_active_dxf_floor(floor)
            return True

        if floor in self._dxf_loading_floors:
            self._update_loading_dialog()
            return False

        self._dxf_loading_floors.add(floor)
        if not prefetch and floor == self.floor_spin.value():
            self.set_status(f"Loading DXF for floor {floor}...")
        self._request_dxf_load.emit(floor, path)
        self._update_loading_dialog()
        return False

    def ensure_floor_dxf_loaded(self, floor, force_reload=False):
        floor = int(floor)
        path = self.get_floor_dxf_path(floor)
        if not path:
            if floor == self.floor_spin.value():
                self.dxf_scene.clear()
                self.current_dxf_path = None
                self.loaded_dxf_floor = None
            return False

        cached = self._dxf_cache.get(floor)
        if (not force_reload) and cached and cached.get("path") == path:
            return self._set_active_dxf_floor(floor)

        self.request_floor_dxf_load(floor, force_reload=force_reload, prefetch=False)
        return False

    def _prefetch_other_floor_dxfs(self, active_floor):
        for entry in self.floor_dxf_entries():
            try:
                floor = int(entry.get("floor"))
            except Exception:
                continue
            if floor == int(active_floor):
                continue
            self.request_floor_dxf_load(floor, prefetch=True)

    @Slot(int, str, object, object)
    def _on_dxf_loaded(self, floor, path, entities, bounds):
        floor = int(floor)
        self._dxf_loading_floors.discard(floor)
        self._loading_batch_failed.discard(floor)
        self._dxf_cache[floor] = {
            "path": path,
            "entities": list(entities or []),
            "bounds": bounds,
        }

        if self.get_floor_dxf_path(floor) != path:
            return

        if floor == self.floor_spin.value():
            self._set_active_dxf_floor(floor)
            self.refresh_canvas()
            if self._pending_fit_after_load:
                self._pending_fit_after_load = False
                self.fit_view()
            else:
                self.set_status(f"Loaded DXF {Path(path).name} for floor {floor}")

        self._prefetch_other_floor_dxfs(floor)
        self._update_loading_dialog()

    @Slot(int, str, str)
    def _on_dxf_failed(self, floor, path, error):
        floor = int(floor)
        self._dxf_loading_floors.discard(floor)
        self._loading_batch_failed.add(floor)
        cached = self._dxf_cache.get(floor)
        if cached and cached.get("path") == path:
            self._dxf_cache.pop(floor, None)
        if floor == self.floor_spin.value():
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
            self.refresh_canvas()
            self.set_status(f"Failed to load DXF for floor {floor}: {error}")
        self._update_loading_dialog()

    def world_to_scene(self, x, y):
        return QPointF(float(x), -float(y))

    def scene_to_world(self, sx, sy):
        return float(sx), -float(sy)

    def snap(self, x, y):
        if self.snap_check.isChecked():
            return round(x), round(y)
        return round(x, 3), round(y, 3)

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

        min_x = min(b[0] for b in bounds)
        min_y = min(b[1] for b in bounds)
        max_x = max(b[2] for b in bounds)
        max_y = max(b[3] for b in bounds)
        return min_x, min_y, max_x, max_y

    def _scene_rect_for_floor(self, floor, padding=8.0):
        bounds = self._content_bounds(floor)
        if not bounds:
            return None
        min_x, min_y, max_x, max_y = bounds
        return self._scene_rect_from_bounds(
            (min_x, min_y, max_x, max_y), padding=padding
        )

    def _scene_rect_from_bounds(self, bounds, padding=8.0):
        min_x, min_y, max_x, max_y = bounds
        return QRect(
            min_x - padding,
            -(max_y + padding),
            max(1.0, (max_x - min_x) + (padding * 2)),
            max(1.0, (max_y - min_y) + (padding * 2)),
        )

    def fit_view(self):
        floor = self.floor_spin.value()
        ready = self.ensure_floor_dxf_loaded(floor)
        rect = self._scene_rect_for_floor(floor, padding=8.0)
        if rect is None and not ready and self.get_floor_dxf_path(floor):
            self._pending_fit_after_load = True
            return
        if (
            rect is not None
            and not rect.isNull()
            and rect.width() > 0
            and rect.height() > 0
        ):
            self.canvas.resetTransform()
            self.canvas.fitInView(rect, Qt.KeepAspectRatio)
            self.scene.setSceneRect(rect.adjusted(-40, -40, 40, 40))
            self.canvas.viewport().update()
        self.refresh_canvas()

    def refresh_canvas(self):
        self.scene.clear()
        self._item_lookup = {}
        self._point_item_lookup = {}
        floor = self.floor_spin.value()
        self.ensure_floor_dxf_loaded(floor)
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
                self.scene, self.canvas.transform().m11()
            )
        self.draw_edges(floor)
        self.draw_points(floor)
        self.file_label.setText(self.current_json_path or "New file")
        self.canvas.viewport().update()

    def _edge_rows_for_point(self, point_name):
        points = self.store.all_points()
        results = []
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            if edge.get("from") != point_name and edge.get("to") != point_name:
                continue
            from_name = edge.get("from", "")
            to_name = edge.get("to", "")
            from_point = points.get(from_name)
            to_point = points.get(to_name)
            from_floor = from_point.get("floor", "") if from_point else ""
            to_floor = to_point.get("floor", "") if to_point else ""
            results.append(
                {
                    "from": from_name,
                    "from_floor": from_floor,
                    "to": to_name,
                    "to_floor": to_floor,
                    "cross_floor": (
                        from_point is not None
                        and to_point is not None
                        and int(from_floor) != int(to_floor)
                    ),
                }
            )
        results.sort(
            key=lambda edge: (
                str(edge.get("from_floor", "")),
                str(edge.get("from", "")),
                str(edge.get("to_floor", "")),
                str(edge.get("to", "")),
            )
        )
        return results

    def _delete_edge_connections(self, edges):
        removed = 0
        for edge in edges:
            before = len(self.store.data.get("corridors", {}).get("edges", []))
            self.store.remove_edge(edge.get("from", ""), edge.get("to", ""))
            after = len(self.store.data.get("corridors", {}).get("edges", []))
            if after < before:
                removed += 1
        self.refresh_canvas()
        self.set_status(f"Deleted {removed} edge connection(s)")

    def _show_edge_connections_dialog(self, point_name):
        dialog = EdgeConnectionsDialog(
            self,
            point_name,
            self._edge_rows_for_point(point_name),
            self._delete_edge_connections,
        )
        dialog.exec()

    def draw_edges(self, floor):
        points = self.store.all_points()
        pen_same_floor = QPen(QColor("#6aa9ff"), 0)
        pen_cross_floor = QPen(QColor("#ff4d4f"), 0)
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            a = points.get(edge["from"])
            b = points.get(edge["to"])
            if not a or not b:
                continue
            a_floor = int(a["floor"])
            b_floor = int(b["floor"])
            if int(floor) not in {a_floor, b_floor}:
                continue
            pa = self.world_to_scene(a["x"], a["y"])
            pb = self.world_to_scene(b["x"], b["y"])
            pen = pen_cross_floor if a_floor != b_floor else pen_same_floor
            item = self.scene.addLine(pa.x(), pa.y(), pb.x(), pb.y(), pen)
            self._item_lookup[item] = ("edge", edge)

    def draw_points(self, floor):
        for name, point in self.store.points_for_floor(floor).items():
            pos = self.world_to_scene(point["x"], point["y"])
            selected = name == self.selected_point_name
            kind = point.get("kind")
            outline = QPen(QColor("#ffffff") if selected else QColor("transparent"), 0)
            if kind == "location":
                r = 0.3
                item = self.scene.addEllipse(
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
                item = self.scene.addRect(
                    pos.x() - r,
                    pos.y() - r,
                    2 * r,
                    2 * r,
                    outline,
                    QBrush(QColor("#f2c94c")),
                )
                label_color = QColor("#ffe8a3")
            else:
                r = 0.3
                poly = [
                    QPointF(pos.x(), pos.y() - r),
                    QPointF(pos.x() + r, pos.y()),
                    QPointF(pos.x(), pos.y() + r),
                    QPointF(pos.x() - r, pos.y()),
                ]
                item = QGraphicsPolygonItem()
                from PySide6.QtGui import QPolygonF

                item.setPolygon(QPolygonF(poly))
                item.setPen(outline)
                item.setBrush(QBrush(QColor("#ff7b72")))
                self.scene.addItem(item)
                label_color = QColor("#ffb3ae")
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
            self._item_lookup[item] = ("point", name)
            self._point_item_lookup[name] = item
            if self.show_labels_check.isChecked():
                text = QGraphicsSimpleTextItem(name)
                text.setBrush(label_color)
                text.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                text.setPos(pos.x() + 0.5, pos.y() - 0)
                self.scene.addItem(text)
                self._item_lookup[text] = ("point_label", name)

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
        self._draw_overlay_box(painter, 12, 12, 320, lines, "#333333", "white")

    def _draw_overlay_box(self, painter, x, y, w, lines, border_color, title_color):
        margin_x = 10
        margin_y = 8
        line_h = 18
        box_h = (margin_y * 2) + (len(lines) * line_h)

        painter.save()
        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(QBrush(QColor("#151515")))
        painter.drawRect(QRect(x, y, w, box_h))

        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)

        for i, line in enumerate(lines):
            painter.setPen(QColor(title_color if i == 0 else "white"))
            painter.drawText(x + margin_x, y + margin_y + 12 + (i * line_h), line)

        painter.restore()

    def find_nearest_point_name(self, x, y, floor, radius_world=3.0):
        best = None
        best_dist = radius_world
        for name, point in self.store.points_for_floor(floor).items():
            d = math.hypot(point["x"] - x, point["y"] - y)
            if d <= best_dist:
                best = name
                best_dist = d
        return best

    def _item_at_scene(self, sx, sy):
        return self.canvas.itemAt(self.canvas.mapFromScene(QPointF(sx, sy)))

    def on_left_click(self, event, sx, sy):
        mode = self.mode_combo.currentText()
        floor = self.floor_spin.value()
        x, y = self.scene_to_world(sx, sy)
        x, y = self.snap(x, y)

        if mode == "pan":
            self.last_pan = event.position().toPoint()
            return

        picked = self.find_nearest_point_name(x, y, floor)
        self.selected_point_name = picked

        if mode == "select_move":
            if picked:
                self.dragging_point_name = picked
                self.drag_mode_active = True
                self.set_status(f"Selected {picked}")
            self.refresh_canvas()
            return

        if mode == "delete":
            if picked:
                if picked.startswith("Lift-") and "-F" in picked:
                    lift_id = picked.rsplit("-F", 1)[0]
                    if (
                        QMessageBox.question(
                            self, "Delete lift", f"Delete entire {lift_id}?"
                        )
                        == QMessageBox.Yes
                    ):
                        self.store.delete_lift(lift_id)
                        self.selected_point_name = None
                        self.set_status(f"Deleted {lift_id}")
                else:
                    if (
                        QMessageBox.question(self, "Delete point", f"Delete {picked}?")
                        == QMessageBox.Yes
                    ):
                        self.store.delete_point(picked)
                        self.selected_point_name = None
                        self.set_status(f"Deleted {picked}")
                self.refresh_canvas()
            return

        if mode == "corridor_node":
            name, ok = QInputDialog.getText(
                self,
                "Corridor node",
                "Node name:",
                text=self.store.suggest_next_corridor_name(floor),
            )
            if not ok or not name:
                return
            self.store.add_corridor_node(name, floor, x, y)
            self.set_status(f"Added corridor node {name}")
            self.refresh_canvas()
            return

        if mode == "location":
            name, ok = QInputDialog.getText(self, "Location", "Location name:")
            if not ok or not name:
                return
            self.store.add_location(name, floor, x, y)
            self.set_status(f"Added location {name}")
            self.refresh_canvas()
            return

        if mode == "edge":
            if not picked:
                self.set_status("No nearby point found")
                return
            if self.selected_for_edge is None:
                self.selected_for_edge = picked
                self.set_status(f"Edge start selected: {picked}")
            else:
                self.store.add_edge(self.selected_for_edge, picked)
                if self.bidirectional_check.isChecked():
                    self.store.add_edge(picked, self.selected_for_edge)
                self.set_status(f"Connected {self.selected_for_edge} -> {picked}")
                self.selected_for_edge = None
                self.refresh_canvas()
            return

        if mode == "lift":
            existing_lift = None
            if picked and picked.startswith("Lift-") and "-F" in picked:
                lift_id = picked.rsplit("-F", 1)[0]
                for item in self.store.data.get("lifts", []):
                    if item["id"] == lift_id:
                        existing_lift = item
                        break
            dialog = LiftEditorDialog(
                self, existing_lift, default_floor=floor, default_x=x, default_y=y
            )
            if dialog.exec() == QDialog.Accepted and dialog.result:
                self.store.upsert_lift(
                    dialog.result["id"],
                    dialog.result["served_floors"],
                    dialog.result["floor_locations"],
                    dialog.result["speed_floors_per_sec"],
                    dialog.result["door_time_sec"],
                    dialog.result["boarding_time_sec"],
                    dialog.result["capacity_size_units"],
                    dialog.result["start_floor"],
                )
                self.set_status(f"Saved {dialog.result['id']}")
                self.refresh_canvas()
            return

    def on_double_click(self, event, sx, sy):
        floor = self.floor_spin.value()
        x, y = self.scene_to_world(sx, sy)
        picked = self.find_nearest_point_name(x, y, floor)
        if not picked:
            return
        point = self.store.all_points()[picked]
        if point.get("kind") == "lift_node":
            lift_id = point["lift_id"]
            existing_lift = next(
                (x for x in self.store.data.get("lifts", []) if x["id"] == lift_id),
                None,
            )
            dialog = LiftEditorDialog(
                self,
                existing_lift,
                default_floor=floor,
                default_x=point["x"],
                default_y=point["y"],
            )
            if dialog.exec() == QDialog.Accepted and dialog.result:
                self.store.upsert_lift(
                    dialog.result["id"],
                    dialog.result["served_floors"],
                    dialog.result["floor_locations"],
                    dialog.result["speed_floors_per_sec"],
                    dialog.result["door_time_sec"],
                    dialog.result["boarding_time_sec"],
                    dialog.result["capacity_size_units"],
                    dialog.result["start_floor"],
                )
                self.set_status(f"Edited {dialog.result['id']}")
                self.refresh_canvas()
            return
        dialog = PointEditorDialog(self, f"Edit {picked}", picked, point)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            self.store.set_point_position(
                picked, dialog.result["x"], dialog.result["y"]
            )
            self.store.rename_point(picked, dialog.result["name"])
            self.selected_point_name = dialog.result["name"]
            self.set_status(f"Edited {dialog.result['name']}")
            self.refresh_canvas()

    def on_left_release(self, event):
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.last_pan = None

    def on_right_click(self, event, sx, sy):
        mode = self.mode_combo.currentText()
        floor = self.floor_spin.value()
        x, y = self.scene_to_world(sx, sy)
        picked = self.find_nearest_point_name(x, y, floor)
        if mode == "edge":
            if picked and self.edge_delete_start is None:
                self.edge_delete_start = picked
                self.selected_for_edge = None
                self.set_status(f"Edge delete start selected: {picked}")
                return
            if picked and self.edge_delete_start:
                removed = False
                before = len(self.store.data.get("corridors", {}).get("edges", []))
                self.store.remove_edge(self.edge_delete_start, picked)
                after = len(self.store.data.get("corridors", {}).get("edges", []))
                removed = removed or (after < before)
                if self.bidirectional_check.isChecked():
                    before = len(self.store.data.get("corridors", {}).get("edges", []))
                    self.store.remove_edge(picked, self.edge_delete_start)
                    after = len(self.store.data.get("corridors", {}).get("edges", []))
                    removed = removed or (after < before)
                self.edge_delete_start = None
                self.set_status(
                    "Edge removed" if removed else "No matching edge to remove"
                )
                self.refresh_canvas()
                return
        if mode == "select_move" and picked:
            self.selected_point_name = picked
            self.refresh_canvas()
            menu = QMenu(self)
            show_edges_action = menu.addAction("Show all edge connections")
            action = menu.exec(event.globalPosition().toPoint())
            if action == show_edges_action:
                self._show_edge_connections_dialog(picked)
            return
        if picked:
            self.selected_point_name = picked
            self.refresh_canvas()

    def on_drag(self, event, sx, sy):
        mode = self.mode_combo.currentText()
        if mode == "pan":
            current = event.position().toPoint()
            if self.last_pan is None:
                self.last_pan = current
                return
            dx = current.x() - self.last_pan.x()
            dy = current.y() - self.last_pan.y()
            self.canvas.horizontalScrollBar().setValue(
                self.canvas.horizontalScrollBar().value() - dx
            )
            self.canvas.verticalScrollBar().setValue(
                self.canvas.verticalScrollBar().value() - dy
            )
            self.last_pan = current
            self.canvas.viewport().update()
            return
        if mode == "select_move" and self.drag_mode_active and self.dragging_point_name:
            x, y = self.scene_to_world(sx, sy)
            x, y = self.snap(x, y)
            self.store.set_point_position(self.dragging_point_name, x, y)
            self.refresh_canvas()

    def on_middle_click(self, event):
        self.last_pan = event.position().toPoint()

    def on_middle_drag(self, event):
        current = event.position().toPoint()
        if self.last_pan is None:
            self.last_pan = current
            return
        dx = current.x() - self.last_pan.x()
        dy = current.y() - self.last_pan.y()
        self.canvas.horizontalScrollBar().setValue(
            self.canvas.horizontalScrollBar().value() - dx
        )
        self.canvas.verticalScrollBar().setValue(
            self.canvas.verticalScrollBar().value() - dy
        )
        self.last_pan = current
        self.canvas.viewport().update()

    def on_middle_release(self, event):
        self.last_pan = None
        self.refresh_canvas()

    def on_mousewheel(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.canvas.scale(factor, factor)
        self.canvas.viewport().update()

    def open_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open JSON", "", "JSON files (*.json)"
        )
        if not path:
            return
        self.store = JsonStore.from_file(path)
        self.current_json_path = path
        self._clear_dxf_cache()
        current_floor = self.floor_spin.value()
        self._pending_fit_after_load = bool(self.get_floor_dxf_path(current_floor))
        self._queue_all_floor_dxf_loads(active_floor=current_floor, force_reload=False)
        self.set_status(f"Opened {Path(path).name}")
        self.refresh_canvas()
        self.fit_view()

    def save_json(self):
        path = self.current_json_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save JSON", "", "JSON files (*.json)"
            )
        if not path:
            return
        self.store.save(path)
        self.current_json_path = path
        self.set_status(f"Saved {Path(path).name}")
        self.refresh_canvas()

    def load_dxf(self):
        floor = self.floor_spin.value()
        initialdir = ""
        existing = self.get_floor_dxf_path(floor)
        if existing:
            try:
                initialdir = str(Path(existing).expanduser().resolve().parent)
            except Exception:
                initialdir = str(Path(existing).expanduser().parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DXF", initialdir, "DXF files (*.dxf)"
        )
        if not path:
            return
        self.set_floor_dxf_path(floor, path)
        self._dxf_cache.pop(int(floor), None)
        if self.loaded_dxf_floor == int(floor):
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
        self._pending_fit_after_load = True
        self._queue_all_floor_dxf_loads(active_floor=floor, force_reload=True)
        self.refresh_canvas()
        self.set_status(f"Mapped DXF {Path(path).name} to floor {floor}")

    def clear_floor_dxf(self):
        floor = self.floor_spin.value()
        existing = self.get_floor_dxf_path(floor)
        if not existing:
            self.set_status(f"No DXF mapped to floor {floor}")
            return
        if (
            QMessageBox.question(
                self, "Clear floor DXF", f"Remove DXF mapping for floor {floor}?"
            )
            != QMessageBox.Yes
        ):
            return
        self.clear_floor_dxf_mapping(floor)
        self._dxf_cache.pop(int(floor), None)
        self._dxf_loading_floors.discard(int(floor))
        if self.loaded_dxf_floor == int(floor):
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
        self.set_status(f"Removed DXF mapping from floor {floor}")
        self.refresh_canvas()

    def validate_json(self):
        errors = self.store.validate()
        if errors:
            QMessageBox.critical(self, "Validation errors", "\n".join(errors[:100]))
            self.set_status(f"Validation failed with {len(errors)} error(s)")
        else:
            QMessageBox.information(
                self, "Validation", "JSON structure is internally consistent."
            )
            self.set_status("Validation passed")

    def manage_payloads(self):
        columns = [
            ("name", "Name", 220),
            ("weight_kg", "Weight kg", 120),
            ("size_units", "Size units", 120),
        ]
        TableListEditor(
            self,
            "Payloads",
            columns,
            self.store.data.get("payloads", []),
            self._save_payloads,
        )

    def _save_payloads(self, items):
        self.store.data["payloads"] = items
        self.set_status("Payloads updated")

    def manage_amrs(self):
        columns = [
            ("id", "ID", 120),
            ("quantity", "Quantity", 80),
            ("payload_capacity_kg", "Payload kg", 110),
            ("payload_size_capacity", "Payload size", 110),
            ("speed_m_per_sec", "Speed", 90),
            ("motor_power_w", "Motor W", 90),
            ("battery_capacity_kwh", "Battery kWh", 100),
            ("battery_charge_rate_kw", "Charge kW", 100),
            ("recharge_threshold_percent", "Recharge %", 100),
            ("battery_soc_percent", "SOC %", 80),
            ("start_location", "Start location", 160),
        ]
        TableListEditor(
            self, "AMRs", columns, self.store.data.get("amrs", []), self._save_amrs
        )

    def _save_amrs(self, items):
        self.store.data["amrs"] = items
        self.set_status("AMRs updated")

    def build_floor_map(self, store):
        floor_map = {}
        for item in store.get("locations", []):
            floor_map[item["name"]] = int(item["floor"])
        for item in store.get("corridors", {}).get("nodes", []):
            floor_map[item["name"]] = int(item["floor"])
        for lift in store.get("lifts", []):
            for floor_str in lift.get("floor_locations", {}).keys():
                floor_map[f"{lift['id']}-F{floor_str}"] = int(floor_str)
        return floor_map

    def manage_tasks(self):
        locations = self.store.data.get("locations", [])
        location_names = sorted(x["name"] for x in locations)
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = [""] + sorted(self.store.data.get("route_profiles", {}).keys())
        floor_map = self.build_floor_map(self.store.data)
        TaskEditorWindow(
            self,
            self.store.data.get("tasks", []),
            location_names,
            payload_names,
            profile_names,
            self.store.suggest_next_task_id,
            self._save_tasks,
            floor_map=floor_map,
        )

    def _save_tasks(self, items):
        self.store.data["tasks"] = items
        self.set_status("Tasks updated")

    def manage_task_planner(self):
        locations = self.store.data.get("locations", [])
        location_names = sorted(x["name"] for x in locations)
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = [""] + sorted(self.store.data.get("route_profiles", {}).keys())
        floor_map = self.build_floor_map(self.store.data)
        for item in locations:
            floor_map[item["name"]] = int(item["floor"])
        TaskPlannerDialog(
            self,
            self.store.data.get("tasks", []),
            location_names,
            payload_names,
            profile_names,
            self.store.suggest_next_task_id,
            self._save_tasks,
            floor_map=floor_map,
        )

    def manage_route_profiles(self):
        point_names = set(self.store.names_in_use()) | {
            x["name"] for x in self.store.data.get("locations", [])
        }
        lift_ids = {x["id"] for x in self.store.data.get("lifts", [])}
        floor_map = self.build_floor_map(self.store.data)
        dialog = RouteProfilesEditorV2(
            self,
            self.store.data.get("route_profiles", {}),
            point_names,
            lift_ids,
            self.store.data.get("corridors", {}).get("edges", []),
            self._save_route_profiles,
            floor_map=floor_map,
        )
        dialog.exec()

    def _save_route_profiles(self, profiles):
        self.store.data["route_profiles"] = profiles
        self.set_status("Route profiles updated")

    def closeEvent(self, event):
        try:
            self._dxf_thread.quit()
            self._dxf_thread.wait(2000)
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = AMRGraphEditor()
    window.show()
    return app.exec()
