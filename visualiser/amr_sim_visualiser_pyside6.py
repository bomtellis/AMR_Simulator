import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dxf_scene import DXFScene

from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
    QPolygonF,
    QFont,
    QPainterPath,
    QMouseEvent,
)
from PySide6.QtCore import QPointF, QTimer, Qt, QRectF, QRect, QObject, Signal, QThread
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QProgressDialog,
    QGraphicsPathItem,
    QDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QMenu,
    QListWidgetItem,
    QListWidget,
    QFrame,
)

try:
    import ezdxf
except Exception:  # pragma: no cover
    ezdxf = None


@dataclass
class VisualEvent:
    start_time: datetime
    end_time: datetime
    row: dict


class LayoutModel:
    def __init__(self):
        self.data: dict = {}
        self.points: Dict[str, dict] = {}
        self.task_start_time: Optional[datetime] = None
        self.task_end_time: Optional[datetime] = None

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        value = (value or "").strip()
        if not value:
            return None

        candidates = [value, value.replace("Z", "+00:00")]
        for candidate in candidates:
            try:
                return datetime.fromisoformat(candidate)
            except Exception:
                continue

        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ]:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue

        return None

    def _rebuild_task_timeline(self):
        times = []
        for task in self.data.get("tasks", []):
            dt = self._parse_datetime(task.get("release_datetime", ""))
            if dt is not None:
                times.append(dt)

        if times:
            self.task_start_time = min(times)
            self.task_end_time = max(times)
        else:
            self.task_start_time = None
            self.task_end_time = None

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self._rebuild_points()
        self._rebuild_task_timeline()

    def _rebuild_points(self):
        self.points = {}
        for item in self.data.get("locations", []):
            self.points[item["name"]] = {**item, "kind": "location"}
        for item in self.data.get("corridors", {}).get("nodes", []):
            self.points[item["name"]] = {**item, "kind": "corridor_node"}
        for lift in self.data.get("lifts", []):
            for floor_str, pos in lift.get("floor_locations", {}).items():
                self.points[f"{lift['id']}-F{floor_str}"] = {
                    "name": f"{lift['id']}-F{floor_str}",
                    "floor": int(floor_str),
                    "x": pos["x"],
                    "y": pos["y"],
                    "kind": "lift_node",
                }

    def edges_for_floor(self, floor: int) -> List[dict]:
        edges = []
        for edge in self.data.get("corridors", {}).get("edges", []):
            a = self.points.get(edge["from"])
            b = self.points.get(edge["to"])
            if a and b and int(a["floor"]) == floor and int(b["floor"]) == floor:
                edges.append(edge)
        return edges

    def points_for_floor(self, floor: int) -> Dict[str, dict]:
        return {k: v for k, v in self.points.items() if int(v["floor"]) == floor}

    def floors(self) -> List[int]:
        return sorted({int(p["floor"]) for p in self.points.values()})


class SimulationLog:
    def __init__(self):
        self.events: List[VisualEvent] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    @staticmethod
    def _format_runtime(seconds: float) -> str:
        total = max(0, int(seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _parse_datetime(value: str) -> Optional[datetime]:
        value = (value or "").strip()
        if not value:
            return None
        candidates = [value, value.replace("Z", "+00:00")]
        for candidate in candidates:
            try:
                return datetime.fromisoformat(candidate)
            except Exception:
                continue
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ]:
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def _float_or_none(value):
        try:
            return float(value) if value not in (None, "") else None
        except Exception:
            return None

    @staticmethod
    def _int_or_none(value):
        try:
            return int(float(value)) if value not in (None, "") else None
        except Exception:
            return None

    def first_travel_time(self) -> Optional[datetime]:
        travel_markers = {
            "travel",
            "move",
            "movement",
            "corridor",
            "edge",
            "lift_travel",
            "lift",
        }
        for event in self.events:
            row = event.row
            segment_type = (row.get("segment_type") or "").strip().lower()
            event_type = (row.get("event_type") or "").strip().lower()
            start_node = (row.get("start_node") or "").strip()
            end_node = (row.get("end_node") or "").strip()
            if segment_type in travel_markers or event_type in travel_markers:
                return event.start_time
            if start_node and end_node and start_node != end_node:
                return event.start_time
        return self.start_time

    def load(self, path: str):
        self.events = []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                start_dt = self._parse_datetime(
                    row.get("start_time", "")
                ) or self._parse_datetime(row.get("sim_datetime", ""))
                end_dt = self._parse_datetime(row.get("end_time", "")) or start_dt
                if start_dt is None or end_dt is None:
                    continue
                self.events.append(
                    VisualEvent(start_time=start_dt, end_time=end_dt, row=row)
                )
        self.events.sort(key=lambda e: e.start_time)
        self.start_time = self.events[0].start_time if self.events else None
        self.end_time = max((e.end_time for e in self.events), default=None)

    def fraction_to_time(self, fraction: float) -> Optional[datetime]:
        if not self.start_time or not self.end_time:
            return None
        fraction = max(0.0, min(1.0, fraction))
        span = self.end_time - self.start_time
        return self.start_time + (span * fraction)

    def time_to_fraction(self, value: datetime) -> float:
        if not self.start_time or not self.end_time or self.start_time == self.end_time:
            return 0.0
        return max(
            0.0,
            min(
                1.0,
                (value - self.start_time).total_seconds()
                / (self.end_time - self.start_time).total_seconds(),
            ),
        )

    def state_at(self, current_time: datetime, layout: LayoutModel):
        amr_states: Dict[str, dict] = {}
        recent_events: List[dict] = []
        current_task_start_by_amr: Dict[str, datetime] = {}
        last_task_id_by_amr: Dict[str, str] = {}

        for event in self.events:
            if event.start_time > current_time:
                break

            row = event.row
            amr_id = (row.get("amr_id") or "").strip() or "AMR"
            task_id = (row.get("task_id") or "").strip()
            payload = (row.get("payload") or "").strip()
            event_type = (row.get("event_type") or "").strip()
            segment_type = (row.get("segment_type") or "").strip()
            status = (row.get("status") or "").strip()

            start_x = self._float_or_none(row.get("start_x"))
            start_y = self._float_or_none(row.get("start_y"))
            start_floor = self._int_or_none(row.get("start_floor"))
            end_x = self._float_or_none(row.get("end_x"))
            end_y = self._float_or_none(row.get("end_y"))
            end_floor = self._int_or_none(row.get("end_floor"))

            start_node = (row.get("start_node") or "").strip()
            end_node = (row.get("end_node") or "").strip()
            from_location = (row.get("from_location") or "").strip()
            to_location = (row.get("to_location") or "").strip()

            start_dt = event.start_time
            end_dt = (
                event.end_time
                if event.end_time >= event.start_time
                else event.start_time
            )

            if task_id:
                previous_task_id = last_task_id_by_amr.get(amr_id)
                if previous_task_id != task_id:
                    current_task_start_by_amr[amr_id] = start_dt
                    last_task_id_by_amr[amr_id] = task_id
            else:
                current_task_start_by_amr.pop(amr_id, None)
                last_task_id_by_amr.pop(amr_id, None)

            state = amr_states.get(
                amr_id,
                {
                    "amr_id": amr_id,
                    "task_id": task_id,
                    "payload": payload,
                    "event_type": event_type,
                    "segment_type": segment_type,
                    "status": status,
                    "timestamp": start_dt,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "start_node": start_node,
                    "end_node": end_node,
                    "from_location": from_location,
                    "to_location": to_location,
                    "floor": None,
                    "x": None,
                    "y": None,
                    "path": None,
                    "task_runtime_sec": 0.0,
                    "raw": row,
                },
            )

            state.update(
                {
                    "task_id": task_id,
                    "payload": payload,
                    "event_type": event_type,
                    "segment_type": segment_type,
                    "status": status,
                    "timestamp": min(current_time, end_dt),
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "start_node": start_node,
                    "end_node": end_node,
                    "from_location": from_location,
                    "to_location": to_location,
                    "raw": row,
                }
            )

            if start_dt <= current_time <= end_dt:
                total = max((end_dt - start_dt).total_seconds(), 0.001)
                elapsed = max((current_time - start_dt).total_seconds(), 0.0)
                frac = max(0.0, min(1.0, elapsed / total))

                if (
                    start_x is not None
                    and start_y is not None
                    and end_x is not None
                    and end_y is not None
                ):
                    state["x"] = start_x + ((end_x - start_x) * frac)
                    state["y"] = start_y + ((end_y - start_y) * frac)

                if start_floor is not None and end_floor is not None:
                    state["floor"] = start_floor if frac < 1.0 else end_floor
                elif end_floor is not None:
                    state["floor"] = end_floor
                elif start_floor is not None:
                    state["floor"] = start_floor

                state["path"] = (
                    (start_node, end_node) if start_node and end_node else None
                )
            else:
                state["x"] = end_x if end_x is not None else start_x
                state["y"] = end_y if end_y is not None else start_y
                state["floor"] = end_floor if end_floor is not None else start_floor
                state["path"] = None

            if task_id:
                assignment_start = current_task_start_by_amr.get(amr_id, start_dt)
                state["task_runtime_sec"] = max(
                    (current_time - assignment_start).total_seconds(), 0.0
                )
            else:
                state["task_runtime_sec"] = 0.0

            amr_states[amr_id] = state
            recent_events.append({"timestamp": min(current_time, end_dt), "row": row})

        return amr_states, recent_events[-12:]


class GraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_pan_pos = None
        self._zoom_callback = None
        self._pan_callback = None
        self._overlay_provider = None
        self._context_menu_callback = None

        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QBrush(QColor("#111111")))

    def set_callbacks(self, zoom_callback=None, pan_callback=None):
        self._zoom_callback = zoom_callback
        self._pan_callback = pan_callback

    def set_context_menu_callback(self, context_menu_callback):
        self._context_menu_callback = context_menu_callback

    def set_overlay_provider(self, overlay_provider):
        self._overlay_provider = overlay_provider
        self.viewport().update()

    def wheelEvent(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.scale(factor, factor)
        if self._zoom_callback:
            self._zoom_callback()
        self.viewport().update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.RightButton and self._context_menu_callback:
            self._context_menu_callback(event)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._last_pan_pos is not None:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            if self._pan_callback:
                self._pan_callback()
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._last_pan_pos = None
            self.setCursor(Qt.ArrowCursor)
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self._overlay_provider:
            painter.save()
            painter.resetTransform()
            self._overlay_provider(painter, self.viewport().rect())
            painter.restore()


def _load_dxf_floor_process(job):
    """Load one DXF in a worker process and return serialisable content.

    This mirrors the editor: DXF parsing happens outside the GUI thread and
    only plain entity/bounds data is passed back to Qt. QGraphicsItems are
    created later, on demand, for the active floor only.
    """
    floor, path = job
    floor = int(floor)
    path = str(path or "").strip()

    try:
        if not path or not Path(path).exists():
            return {
                "ok": False,
                "floor": floor,
                "path": path,
                "entities": None,
                "bounds": None,
                "error": f"DXF file not found: {path}",
            }

        payload = DXFScene.load_content(path)
        return {
            "ok": True,
            "floor": floor,
            "path": path,
            "entities": payload.get("entities", []),
            "bounds": payload.get("bounds"),
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "floor": floor,
            "path": path,
            "entities": None,
            "bounds": None,
            "error": str(exc),
        }


class DxfLoadWorker(QObject):
    progress = Signal(int, int, str)
    floor_loaded = Signal(int, str, object, object)
    error = Signal(int, str)
    finished = Signal()

    def __init__(self, floor_dxf_files):
        super().__init__()
        self.floor_dxf_files = list(floor_dxf_files)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _normalise_jobs(self):
        jobs = []
        seen = set()

        for entry in self.floor_dxf_files:
            try:
                floor = int(entry.get("floor"))
                path = str(entry.get("filepath") or "").strip()
            except Exception:
                continue

            if not path:
                continue

            key = (floor, path)
            if key in seen:
                continue

            seen.add(key)
            jobs.append(key)

        return jobs

    def run(self):
        jobs = self._normalise_jobs()
        total = len(jobs)

        if total <= 0:
            self.finished.emit()
            return

        worker_count = min(total, max(1, (os.cpu_count() or 2) - 1))
        completed = 0

        self.progress.emit(0, total, "Preparing DXF load...")

        try:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                futures = [pool.submit(_load_dxf_floor_process, job) for job in jobs]

                for future in as_completed(futures):
                    completed += 1

                    if self._cancelled:
                        continue

                    result = future.result()
                    floor = int(result.get("floor", 0))
                    path = str(result.get("path", ""))
                    label = Path(path).name if path else ""

                    self.progress.emit(
                        completed,
                        total,
                        f"Loaded {completed} of {total} DXFs...\n{label}",
                    )

                    if result.get("ok"):
                        self.floor_loaded.emit(
                            floor,
                            path,
                            result.get("entities") or [],
                            result.get("bounds"),
                        )
                    else:
                        self.error.emit(
                            floor,
                            str(result.get("error") or "Unknown DXF load error"),
                        )
        finally:
            self.finished.emit()


class TaskJumpDialog(QDialog):
    def __init__(self, parent, grouped_tasks):
        super().__init__(parent)
        self.setWindowTitle("Tasks by AMR")
        self.resize(980, 620)
        self.selected_start_time = None
        self.selected_amr_id = None

        self._sort_column = None
        self._sort_state = 0  # 0=original, 1=asc, 2=desc
        self._insertion_counter = 0

        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            [
                "Task ID / Segment",
                "Payload",
                "Origin",
                "Destination",
                "Duration",
                "Datetime",
            ]
        )
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.header().sectionClicked.connect(self._on_header_clicked)

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        for amr_id in sorted(grouped_tasks.keys()):
            amr_item = QTreeWidgetItem([amr_id, "", "", "", "", ""])
            amr_item.setFirstColumnSpanned(True)
            amr_item.setData(0, Qt.UserRole, None)
            amr_item.setData(1, Qt.UserRole, None)
            amr_item.setData(0, Qt.UserRole + 10, self._next_insertion_order())
            amr_item.setData(0, Qt.UserRole + 20, "amr")

            for task in grouped_tasks[amr_id]:
                task_item = QTreeWidgetItem(
                    [
                        task["task_id"],
                        task["payload"],
                        task["origin"],
                        task["destination"],
                        task["duration"],
                        task["sim_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                    ]
                )
                task_item.setData(0, Qt.UserRole, task["start_time"])
                task_item.setData(1, Qt.UserRole, amr_id)
                task_item.setData(0, Qt.UserRole + 10, self._next_insertion_order())
                task_item.setData(0, Qt.UserRole + 20, "task")

                for segment in task.get("segments", []):
                    segment_item = QTreeWidgetItem(
                        [
                            segment["label"],
                            "",
                            segment["origin"],
                            segment["destination"],
                            segment["duration"],
                            segment["sim_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                        ]
                    )
                    segment_item.setData(0, Qt.UserRole, segment["start_time"])
                    segment_item.setData(1, Qt.UserRole, amr_id)
                    segment_item.setData(
                        0, Qt.UserRole + 10, self._next_insertion_order()
                    )
                    segment_item.setData(0, Qt.UserRole + 20, "segment")
                    task_item.addChild(segment_item)

                task_item.setExpanded(False)
                amr_item.addChild(task_item)

            amr_item.setExpanded(True)
            self.tree.addTopLevelItem(amr_item)

        layout.addWidget(self.tree)

    def _next_insertion_order(self) -> int:
        value = self._insertion_counter
        self._insertion_counter += 1
        return value

    def _on_item_double_clicked(self, item, _column):
        start_time = item.data(0, Qt.UserRole)
        amr_id = item.data(1, Qt.UserRole)

        if start_time is None:
            return

        self.selected_start_time = start_time
        self.selected_amr_id = amr_id
        self.accept()

    def _on_header_clicked(self, column: int):
        if self._sort_column != column:
            self._sort_column = column
            self._sort_state = 1
        else:
            self._sort_state = (self._sort_state + 1) % 3

        if self._sort_state == 0:
            self._restore_original_order()
        else:
            ascending = self._sort_state == 1
            self._sort_tree(column, ascending)

    def _restore_original_order(self):
        amr_items = []
        while self.tree.topLevelItemCount():
            amr_items.append(self.tree.takeTopLevelItem(0))

        amr_items.sort(key=lambda item: item.data(0, Qt.UserRole + 10))

        for amr_item in amr_items:
            self._sort_children_by_original_order(amr_item)
            self.tree.addTopLevelItem(amr_item)

    def _sort_children_by_original_order(self, parent_item: QTreeWidgetItem):
        children = []
        while parent_item.childCount():
            children.append(parent_item.takeChild(0))

        children.sort(key=lambda item: item.data(0, Qt.UserRole + 10))

        for child in children:
            self._sort_children_by_original_order(child)
            parent_item.addChild(child)

    def _sort_tree(self, column: int, ascending: bool):
        amr_items = []
        while self.tree.topLevelItemCount():
            amr_items.append(self.tree.takeTopLevelItem(0))

        amr_items.sort(
            key=lambda item: self._item_sort_key(item, column), reverse=not ascending
        )

        for amr_item in amr_items:
            self._sort_children(amr_item, column, ascending)
            self.tree.addTopLevelItem(amr_item)

    def _sort_children(
        self, parent_item: QTreeWidgetItem, column: int, ascending: bool
    ):
        children = []
        while parent_item.childCount():
            children.append(parent_item.takeChild(0))

        children.sort(
            key=lambda item: self._item_sort_key(item, column), reverse=not ascending
        )

        for child in children:
            self._sort_children(child, column, ascending)
            parent_item.addChild(child)

    def _item_sort_key(self, item: QTreeWidgetItem, column: int):
        item_type = item.data(0, Qt.UserRole + 20)

        # Keep AMR rows grouped sensibly when sorting their children
        if item_type == "amr":
            return (
                self._safe_text(item, 0).lower(),
                item.data(0, Qt.UserRole + 10),
            )

        if column == 4:
            return (
                self._duration_seconds(self._safe_text(item, 4)),
                self._safe_text(item, 0).lower(),
                item.data(0, Qt.UserRole + 10),
            )

        if column == 5:
            return (
                self._datetime_key(self._safe_text(item, 5)),
                self._safe_text(item, 0).lower(),
                item.data(0, Qt.UserRole + 10),
            )

        return (
            self._safe_text(item, column).lower(),
            self._safe_text(item, 0).lower(),
            item.data(0, Qt.UserRole + 10),
        )

    def _safe_text(self, item: QTreeWidgetItem, column: int) -> str:
        text = item.text(column)
        return text if text is not None else ""

    def _duration_seconds(self, text: str) -> int:
        parts = [p for p in text.strip().split(":") if p != ""]
        try:
            if len(parts) == 3:
                h, m, s = [int(x) for x in parts]
                return h * 3600 + m * 60 + s
            if len(parts) == 2:
                m, s = [int(x) for x in parts]
                return m * 60 + s
        except Exception:
            pass
        return -1

    def _datetime_key(self, text: str):
        try:
            return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min


class LiftShaftWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lift_state = None
        self.setMinimumSize(120, 260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_lift_state(self, lift_state: dict):
        self.lift_state = lift_state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151515"))

        state = self.lift_state or {}
        floors = list(state.get("served_floors", []))
        if not floors:
            floors = [0]

        min_floor = min(floors)
        max_floor = max(floors)
        span = max(1, max_floor - min_floor)

        left = 44
        top = 20
        shaft_w = 32
        shaft_h = max(160, self.height() - 120)

        painter.setPen(QPen(QColor("#666666"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(left, top, shaft_w, shaft_h)

        font = QFont()
        font.setPixelSize(11)
        painter.setFont(font)

        for floor in sorted(floors):
            if span == 0:
                frac = 0.0
            else:
                frac = (floor - min_floor) / span
            y = top + shaft_h - (frac * shaft_h)
            painter.setPen(QPen(QColor("#2f2f2f"), 1))
            painter.drawLine(left - 10, int(y), left + shaft_w + 10, int(y))
            painter.setPen(QColor("#d7d7d7"))
            painter.drawText(6, int(y) + 4, f"F{floor}")

        current_floor = float(state.get("current_floor", min_floor))
        current_floor = max(min_floor, min(max_floor, current_floor))
        if span == 0:
            frac = 0.0
        else:
            frac = (current_floor - min_floor) / span
        car_h = 24
        car_y = top + shaft_h - (frac * shaft_h) - (car_h / 2)

        painter.setPen(QPen(QColor("#111111"), 1))
        painter.setBrush(QBrush(QColor("#f39c12")))
        painter.drawRect(left + 2, int(car_y), shaft_w - 4, car_h)

        occupant = state.get("occupant") or "-"
        painter.setPen(QColor("#ffffff"))
        painter.drawText(12, top + shaft_h + 26, f"AMR: {occupant}")
        painter.drawText(12, top + shaft_h + 46, f"Pos: F{current_floor:.2f}")


class LocationInventoryPayloadDialog(QDialog):
    columns = [
        ("space", "Inventory space", 180),
        ("payload", "Current payload", 170),
        ("task_id", "Task", 100),
        ("amr_id", "AMR", 100),
        ("status", "Status", 130),
        ("timestamp", "Updated", 160),
        ("source", "Source", 120),
    ]

    def __init__(
        self,
        parent,
        location_name: str,
        rows: List[dict],
        current_time: Optional[datetime],
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Inventory payloads - {location_name}")
        self.resize(980, 420)
        self.location_name = location_name
        self.rows = list(rows or [])
        self.current_time = current_time

        layout = QVBoxLayout(self)
        stamp = current_time.strftime("%Y-%m-%d %H:%M:%S") if current_time else "-"
        self.summary_label = QLabel(
            f"Location: {location_name}\nTime: {stamp}\nSpaces: {len(self.rows)}"
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [heading for _key, heading, _width in self.columns]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)
        layout.addWidget(self.table, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for row_data in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, (key, _heading, _width) in enumerate(self.columns):
                value = row_data.get(key, "")
                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(str(value if value not in (None, "") else "-")),
                )


class LocationInventorySpacesDialog(QDialog):
    columns = [
        ("name", "Inventory space", 180),
        ("length_m", "Length m", 90),
        ("width_m", "Width m", 90),
        ("height_m", "Height m", 90),
        ("occupied", "Occupied", 90),
        ("payload", "Payload", 160),
        ("task_id", "Task", 120),
        ("reserved_by_task", "Reserved by", 120),
        ("points", "Points", 90),
    ]

    def __init__(self, parent, location_name: str, rows: List[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Inventory spaces - {location_name}")
        self.resize(1080, 460)
        self.location_name = location_name
        self.rows = list(rows or [])

        layout = QVBoxLayout(self)
        self.summary_label = QLabel(
            f"Location: {location_name}\nInventory spaces: {len(self.rows)}"
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [heading for _key, heading, _width in self.columns]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)
        layout.addWidget(self.table, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for row_data in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, (key, _heading, _width) in enumerate(self.columns):
                value = row_data.get(key, "")
                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(str(value if value not in (None, "") else "-")),
                )


class AmrPayloadMonitorDialog(QDialog):
    columns = [
        ("amr_id", "AMR", 120),
        ("payloads", "Payloads onboard", 260),
        ("payload_count", "Count", 70),
        ("slots", "Slots", 90),
        ("task_ids", "Task(s)", 190),
        ("status", "Status", 130),
        ("segment_type", "Segment", 130),
        ("from_location", "From", 150),
        ("to_location", "To", 150),
        ("floor", "Floor", 70),
        ("updated", "Updated", 160),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AMR Payload Monitor")
        self.setWindowModality(Qt.NonModal)
        self.resize(1320, 520)
        self._rows = []

        layout = QVBoxLayout(self)
        self.summary_label = QLabel("No simulation loaded")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(
            [heading for _key, heading, _width in self.columns]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)
        layout.addWidget(self.table, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def update_states(self, rows: List[dict], current_time: Optional[datetime]):
        self._rows = list(rows or [])
        stamp = current_time.strftime("%Y-%m-%d %H:%M:%S") if current_time else "-"
        payload_total = sum(int(row.get("payload_count", 0) or 0) for row in self._rows)
        self.summary_label.setText(
            f"Time: {stamp}\nAMRs: {len(self._rows)} | Payloads onboard: {payload_total}"
        )
        self._refresh_table()

    def _refresh_table(self):
        selected_amr = ""
        selected_rows = (
            self.table.selectionModel().selectedRows()
            if self.table.selectionModel()
            else []
        )
        if selected_rows:
            item = self.table.item(selected_rows[0].row(), 0)
            selected_amr = item.text() if item else ""

        self.table.setRowCount(0)
        for row_data in self._rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, (key, _heading, _width) in enumerate(self.columns):
                value = row_data.get(key, "")
                text = str(value if value not in (None, "") else "-")
                item = QTableWidgetItem(text)
                if key == "payload_count":
                    try:
                        item.setData(Qt.DisplayRole, int(value or 0))
                    except Exception:
                        pass
                self.table.setItem(row, col, item)
            if selected_amr and str(row_data.get("amr_id", "")) == selected_amr:
                self.table.selectRow(row)


class LiftMonitorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lift Monitor")
        self.setModal(True)
        self.resize(980, 520)
        self._lift_widgets = {}

        outer = QVBoxLayout(self)
        row = QHBoxLayout()
        outer.addLayout(row)

        self._row = row

        self.setWindowModality(Qt.NonModal)

    def set_lifts(self, lift_states: List[dict]):
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._lift_widgets = {}

        for lift_state in lift_states:
            panel = QFrame()
            panel.setFrameShape(QFrame.StyledPanel)
            panel.setStyleSheet(
                "QFrame { background: #101010; border: 1px solid #333333; } QLabel { color: white; } QListWidget { background: #151515; color: white; border: 1px solid #333333; }"
            )
            layout = QVBoxLayout(panel)

            shaft = LiftShaftWidget(panel)
            waiting_label = QLabel("Waiting AMRs")
            waiting_list = QListWidget(panel)
            waiting_list.setMinimumHeight(110)
            name_label = QLabel(lift_state.get("lift_id", "Lift"))
            name_label.setAlignment(Qt.AlignCenter)

            layout.addWidget(shaft, alignment=Qt.AlignHCenter)
            layout.addWidget(name_label)
            layout.addWidget(waiting_label)
            layout.addWidget(waiting_list)

            self._row.addWidget(panel)
            self._lift_widgets[lift_state.get("lift_id", "")] = (shaft, waiting_list)

        self.update_states(lift_states)

    def update_states(self, lift_states: List[dict]):
        if set(self._lift_widgets.keys()) != {
            x.get("lift_id", "") for x in lift_states
        }:
            self.set_lifts(lift_states)
            return

        for lift_state in lift_states:
            lift_id = lift_state.get("lift_id", "")
            if lift_id not in self._lift_widgets:
                continue
            shaft, waiting_list = self._lift_widgets[lift_id]
            shaft.set_lift_state(lift_state)
            waiting_list.clear()
            waiting = lift_state.get("waiting_amrs", [])
            if waiting:
                for amr in waiting:
                    waiting_list.addItem(QListWidgetItem(amr))
            else:
                waiting_list.addItem(QListWidgetItem("-"))


class AmrTimelineWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.current_time: Optional[datetime] = None

        self.row_height = 34
        self.left_pad = 150
        self.top_pad = 58
        self.right_pad = 60
        self.bottom_pad = 30

        # Long simulations can span several days.  The lane remains horizontally
        # scrollable, while the AMR name column is redrawn at the visible left
        # edge so the lane identity is always readable.
        self.seconds_per_pixel = 4.0
        self.min_lane_width = 1400
        self.label_column_width = 142
        self.min_tick_spacing_px = 120
        self._pressed = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_virtual_size()

    def set_data(self, timeline_data, start_time, end_time, current_time):
        self.timeline_data = timeline_data or []
        self.start_time = start_time
        self.end_time = end_time
        self.current_time = current_time
        self._update_virtual_size()
        self.update()

    def _timeline_seconds(self) -> float:
        if not self.start_time or not self.end_time or self.end_time <= self.start_time:
            return 0.0
        return max(0.0, (self.end_time - self.start_time).total_seconds())

    def _usable_width(self) -> float:
        seconds = self._timeline_seconds()
        if seconds <= 0:
            return self.min_lane_width
        return max(self.min_lane_width, seconds / self.seconds_per_pixel)

    def _update_virtual_size(self):
        lane_count = max(1, len(self.timeline_data))
        width = int(self.left_pad + self._usable_width() + self.right_pad)
        height = int(
            self.top_pad + self.bottom_pad + (lane_count * self.row_height) + 20
        )
        self.setMinimumSize(width, height)
        self.resize(width, height)

    def _time_to_x(self, value: datetime) -> float:
        if not self.start_time or not self.end_time or self.end_time <= self.start_time:
            return float(self.left_pad)

        total = (self.end_time - self.start_time).total_seconds()
        elapsed = (value - self.start_time).total_seconds()
        frac = max(0.0, min(1.0, elapsed / total))
        return self.left_pad + (self._usable_width() * frac)

    def _x_to_time(self, x: float) -> Optional[datetime]:
        if not self.start_time or not self.end_time or self.end_time <= self.start_time:
            return None

        frac = (x - self.left_pad) / max(1.0, self._usable_width())
        frac = max(0.0, min(1.0, frac))
        span = self.end_time - self.start_time
        return self.start_time + (span * frac)

    def _format_datetime(self, value: Optional[datetime]) -> str:
        if value is None:
            return "-"
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _visible_scroll_x(self) -> int:
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return int(parent.horizontalScrollBar().value())
            parent = parent.parent()
        return 0

    def _nice_tick_seconds(self) -> int:
        seconds = max(1.0, self._timeline_seconds())
        approximate_ticks = max(
            2, int(self._usable_width() // self.min_tick_spacing_px)
        )
        raw_step = seconds / approximate_ticks
        candidates = [
            60,
            5 * 60,
            10 * 60,
            15 * 60,
            30 * 60,
            60 * 60,
            2 * 60 * 60,
            3 * 60 * 60,
            6 * 60 * 60,
            12 * 60 * 60,
            24 * 60 * 60,
            2 * 24 * 60 * 60,
            7 * 24 * 60 * 60,
        ]
        for step in candidates:
            if step >= raw_step:
                return step
        return candidates[-1]

    def _iter_tick_times(self):
        if not self.start_time or not self.end_time:
            return
        step = self._nice_tick_seconds()
        start_epoch = int(self.start_time.timestamp())
        first_epoch = (start_epoch // step) * step
        if first_epoch < start_epoch:
            first_epoch += step
        tick = datetime.fromtimestamp(first_epoch, tz=self.start_time.tzinfo)
        while tick <= self.end_time:
            yield tick
            tick += timedelta(seconds=step)

    def _format_tick_label(self, value: datetime, step_seconds: int) -> str:
        if step_seconds >= 24 * 60 * 60:
            return value.strftime("%d %b\n%Y")
        if self.start_time and value.date() != self.start_time.date():
            return value.strftime("%d %b\n%H:%M")
        return value.strftime("%H:%M")

    def _draw_day_bands(self, painter: QPainter, axis_y: int):
        if not self.start_time or not self.end_time:
            return

        day = datetime(
            self.start_time.year,
            self.start_time.month,
            self.start_time.day,
            tzinfo=self.start_time.tzinfo,
        )
        if day < self.start_time:
            day += timedelta(days=1)

        while day <= self.end_time:
            x = self._time_to_x(day)
            painter.setPen(QPen(QColor("#555555"), 1))
            painter.drawLine(
                int(x), axis_y - 20, int(x), self.height() - self.bottom_pad + 2
            )
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                int(x) + 4,
                4,
                120,
                18,
                Qt.AlignLeft | Qt.AlignVCenter,
                day.strftime("%a %d %b"),
            )
            day += timedelta(days=1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))

        font = QFont("", 9)
        painter.setFont(font)

        if not self.timeline_data or not self.start_time or not self.end_time:
            painter.setPen(QColor("#cfcfcf"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No timeline data")
            return

        scroll_x = self._visible_scroll_x()
        fixed_label_x = scroll_x + 8
        fixed_label_panel = QRectF(scroll_x, 0, self.label_column_width, self.height())

        axis_y = self.top_pad - 12
        lane_start_x = self.left_pad
        lane_end_x = int(self.left_pad + self._usable_width())

        painter.setPen(QColor("#8a8a8a"))
        painter.drawLine(lane_start_x, axis_y, lane_end_x, axis_y)

        self._draw_day_bands(painter, axis_y)

        step_seconds = self._nice_tick_seconds()
        for tick_time in self._iter_tick_times() or []:
            x = self._time_to_x(tick_time)
            painter.setPen(QColor("#2a2a2a"))
            painter.drawLine(
                int(x), axis_y - 4, int(x), self.height() - self.bottom_pad + 2
            )

            painter.setPen(QColor("#d7d7d7"))
            painter.drawText(
                int(x) - 42,
                22,
                84,
                30,
                Qt.AlignCenter,
                self._format_tick_label(tick_time, step_seconds),
            )

        for row, lane in enumerate(self.timeline_data):
            y = self.top_pad + (row * self.row_height)

            painter.setPen(QColor("#2a2a2a"))
            painter.drawLine(lane_start_x, y + 22, lane_end_x, y + 22)

            for block in lane["blocks"]:
                x1 = self._time_to_x(block["start"])
                x2 = self._time_to_x(block["end"])
                if x2 < x1 + 2:
                    x2 = x1 + 2

                rect = QRectF(x1, y + 7, x2 - x1, 16)
                painter.fillRect(rect, QColor(block["color"]))
                painter.setPen(QColor("#000000"))
                painter.drawRect(rect)

                label = str(block.get("label", "")).strip()
                if label and rect.width() >= 54:
                    metrics = painter.fontMetrics()
                    text = metrics.elidedText(
                        label, Qt.ElideRight, max(1, int(rect.width()) - 8)
                    )
                    painter.setPen(QColor("#ffffff"))
                    painter.drawText(
                        rect.adjusted(4, 0, -4, 0),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        text,
                    )

        if self.current_time is not None:
            x = self._time_to_x(self.current_time)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(
                int(x), self.top_pad - 28, int(x), self.height() - self.bottom_pad + 4
            )

        # Redraw the lane labels last as a fixed overlay tied to the scroll view.
        painter.fillRect(fixed_label_panel, QColor("#151515"))
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawLine(
            int(scroll_x + self.label_column_width),
            0,
            int(scroll_x + self.label_column_width),
            self.height(),
        )
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            int(fixed_label_x),
            22,
            self.label_column_width - 16,
            24,
            Qt.AlignLeft | Qt.AlignVCenter,
            "AMR",
        )
        for row, lane in enumerate(self.timeline_data):
            y = self.top_pad + (row * self.row_height)
            painter.setPen(QColor("#d7d7d7"))
            painter.drawText(
                int(fixed_label_x),
                y + 3,
                self.label_column_width - 16,
                24,
                Qt.AlignLeft | Qt.AlignVCenter,
                str(lane["amr_id"]),
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._emit_seek(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed:
            self._emit_seek(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _emit_seek(self, x: float):
        new_time = self._x_to_time(x)
        if new_time is None:
            return
        parent = self.parent()
        while parent is not None and not hasattr(parent, "on_timeline_seek"):
            parent = parent.parent()
        if parent and hasattr(parent, "on_timeline_seek"):
            parent.on_timeline_seek(new_time)


class LocationInventoryPayloadDialog(QDialog):
    columns = [
        ("space", "Inventory space", 180),
        ("payload", "Current payload", 170),
        ("task_id", "Task", 100),
        ("amr_id", "AMR", 100),
        ("status", "Status", 130),
        ("timestamp", "Updated", 160),
        ("source", "Source", 120),
    ]

    def __init__(self, parent, location_name, rows, current_time):
        super().__init__(parent)
        self.setWindowTitle(f"Inventory payloads - {location_name}")
        self.resize(980, 420)

        layout = QVBoxLayout(self)

        stamp = current_time.strftime("%Y-%m-%d %H:%M:%S") if current_time else "-"
        layout.addWidget(
            QLabel(f"Location: {location_name}\nTime: {stamp}\nSpaces: {len(rows)}")
        )

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([h for _k, h, _w in self.columns])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        for idx, (_key, _heading, width) in enumerate(self.columns):
            self.table.setColumnWidth(idx, width)

        layout.addWidget(self.table, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

        for row_data in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, (key, _heading, _width) in enumerate(self.columns):
                value = row_data.get(key, "-")
                self.table.setItem(r, c, QTableWidgetItem(str(value or "-")))


class SimulationVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMR Simulation Visualiser (PySide6)")
        self.resize(1600, 960)

        self.layout_model = LayoutModel()
        self.dxf_scenes: Dict[int, DXFScene] = {}
        self.dxf_load_thread: Optional[QThread] = None
        self.dxf_load_worker: Optional[DxfLoadWorker] = None
        self.dxf_progress_dialog: Optional[QProgressDialog] = None
        self.dxf_paths_by_floor: Dict[int, str] = {}
        self.dxf_items_by_floor: Dict[int, List[QGraphicsItem]] = {}
        self.current_dxf_floor: Optional[int] = None
        self.dxf_loading_failures: Dict[int, str] = {}
        self._dxf_text_bucket: Optional[int] = None
        self.sim_log = SimulationLog()

        self.current_json_path: Optional[str] = None
        self.current_dxf_path: Optional[str] = None
        self.current_csv_path: Optional[str] = None
        self.current_time: Optional[datetime] = None
        self.is_playing = False
        self.play_speed = 60.0
        self.lift_monitor_dialog: Optional[LiftMonitorDialog] = None
        self.amr_payload_monitor_dialog: Optional[AmrPayloadMonitorDialog] = None
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._tick)

        self.zoom_redraw_timer = QTimer(self)
        self.zoom_redraw_timer.setSingleShot(True)
        self.zoom_redraw_timer.timeout.connect(self.refresh_static_scene)

        self.pan_redraw_timer = QTimer(self)
        self.pan_redraw_timer.setSingleShot(True)
        self.pan_redraw_timer.timeout.connect(self.refresh_static_scene)

        self._build_ui()
        self.refresh_all()

    # def on_zoom(self):
    #     self.zoom_redraw_timer.start(20)
    #     self.refresh_static_scene()
    #     self.refresh_dynamic_scene()

    def on_zoom(self):
        new_bucket = self._current_dxf_text_bucket()
        if new_bucket != self._dxf_text_bucket:
            self._dxf_text_bucket = new_bucket
            floor = self.current_floor()
            if floor in self.dxf_items_by_floor:
                self.rebuild_dxf_floor_items(floor)
                if self.show_dxf_check.isChecked():
                    self.show_dxf_floor(floor)
        self.refresh_dynamic_scene()
        self.view.viewport().update()

    def _current_dxf_text_bucket(self) -> int:
        scale = self.view.transform().m11()
        if scale < 6.0:
            return 0
        if scale < 12.0:
            return 1
        return 2

    def rebuild_dxf_floor_items(self, floor: int):
        old_items = self.dxf_items_by_floor.pop(floor, [])
        for item in old_items:
            self.graphics_scene.removeItem(item)
        self.ensure_dxf_floor_loaded(floor)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        side = QWidget()
        side.setFixedWidth(340)
        side_layout = QVBoxLayout(side)

        self.graphics_scene = QGraphicsScene(self)
        self.view = GraphicsView(self)
        self.view.setScene(self.graphics_scene)
        self.view.set_callbacks(
            zoom_callback=self.on_zoom,
            pan_callback=lambda: self.view.viewport().update(),
        )
        self.view.set_context_menu_callback(self.on_view_right_click)
        self.view.set_overlay_provider(self.draw_overlay_panels)

        self.static_items = []
        self.dynamic_items = []
        self.node_context_menu = QMenu(self)

        def add_btn(text, fn):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            side_layout.addWidget(btn)
            return btn

        add_btn("Open Layout JSON", self.open_json)
        add_btn("Open DXF", self.open_dxf)
        add_btn("Reload Current Floor DXF", self.reload_current_floor_dxf)
        add_btn("Open Simulation CSV", self.open_csv)
        add_btn("Jump to Task", self.open_task_jump_dialog)
        add_btn("Lift Monitor", self.open_lift_monitor_dialog)
        add_btn("AMR Payload Monitor", self.open_amr_payload_monitor_dialog)
        add_btn("Fit View", self.fit_view)

        side_layout.addWidget(QLabel("Floor"))
        self.floor_spin = QSpinBox()
        self.floor_spin.setRange(0, 99)
        self.floor_spin.valueChanged.connect(self.refresh_all)
        side_layout.addWidget(self.floor_spin)

        self.show_dxf_check = QCheckBox("Show DXF")
        self.show_dxf_check.setChecked(True)
        self.show_dxf_check.toggled.connect(self.refresh_static_scene)
        side_layout.addWidget(self.show_dxf_check)

        self.show_labels_check = QCheckBox("Show labels")
        self.show_labels_check.setChecked(True)
        self.show_labels_check.toggled.connect(self.refresh_all)
        side_layout.addWidget(self.show_labels_check)

        self.follow_time_check = QCheckBox("Follow slider time")
        side_layout.addWidget(self.follow_time_check)

        self.show_amr_box_check = QCheckBox("Show AMR box")
        self.show_amr_box_check.setChecked(True)
        self.show_amr_box_check.toggled.connect(self.refresh_dynamic_scene)
        side_layout.addWidget(self.show_amr_box_check)

        side_layout.addWidget(QLabel("AMR width (m)"))
        self.amr_width_spin = QDoubleSpinBox()
        self.amr_width_spin.setRange(0.1, 5.0)
        self.amr_width_spin.setSingleStep(0.1)
        self.amr_width_spin.setValue(0.8)
        self.amr_width_spin.valueChanged.connect(self.refresh_dynamic_scene)
        side_layout.addWidget(self.amr_width_spin)

        side_layout.addWidget(QLabel("AMR length (m)"))
        self.amr_length_spin = QDoubleSpinBox()
        self.amr_length_spin.setRange(0.1, 5.0)
        self.amr_length_spin.setSingleStep(0.1)
        self.amr_length_spin.setValue(1.2)
        self.amr_length_spin.valueChanged.connect(self.refresh_dynamic_scene)
        side_layout.addWidget(self.amr_length_spin)

        side_layout.addWidget(QLabel("Follow AMR"))
        self.follow_combo = QComboBox()
        self.follow_combo.currentTextChanged.connect(self.refresh_dynamic_scene)
        side_layout.addWidget(self.follow_combo)

        self.follow_enabled_check = QCheckBox("Enable follow")
        self.follow_enabled_check.toggled.connect(self.refresh_dynamic_scene)
        side_layout.addWidget(self.follow_enabled_check)

        controls = QHBoxLayout()
        for text, fn in [
            ("|<", self.jump_start),
            ("First Move", self.jump_first_travel),
            ("-10s", lambda: self.step_seconds(-10)),
            ("Play", self.toggle_play),
            ("+10s", lambda: self.step_seconds(10)),
            (">|", self.jump_end),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            controls.addWidget(btn)
            if text == "Play":
                self.play_btn = btn
        side_layout.addLayout(controls)

        self.time_label = QLabel("No simulation loaded")
        self.time_label.setWordWrap(True)
        side_layout.addWidget(self.time_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.valueChanged.connect(self.on_slider_change)
        side_layout.addWidget(self.slider)

        side_layout.addWidget(QLabel("Playback speed (sim seconds / real second)"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["1", "2", "5", "10", "30", "60", "120", "300"])
        self.speed_combo.setCurrentText("60")
        self.speed_combo.currentTextChanged.connect(self.on_speed_changed)
        side_layout.addWidget(self.speed_combo)

        side_layout.addWidget(QLabel("Loaded files"))
        self.file_label = QLabel("No files loaded")
        self.file_label.setWordWrap(True)
        side_layout.addWidget(self.file_label)

        side_layout.addWidget(QLabel("Status"))
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        side_layout.addWidget(self.status_label)

        self.event_box = QTextEdit()
        self.event_box.setReadOnly(True)
        side_layout.addWidget(self.event_box, 1)

        self.timeline_widget = AmrTimelineWidget(self)

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.timeline_scroll.setWidget(self.timeline_widget)
        self.timeline_scroll.horizontalScrollBar().valueChanged.connect(
            self.timeline_widget.update
        )
        self.timeline_scroll.verticalScrollBar().valueChanged.connect(
            self.timeline_widget.update
        )

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.addWidget(self.view)
        self.main_splitter.addWidget(self.timeline_scroll)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([760, 220])

        layout.addWidget(side)
        layout.addWidget(self.main_splitter, 1)

    def _location_by_name(self, location_name):
        for location in self.layout_model.data.get("locations", []):
            if str(location.get("name", "")).strip() == str(location_name).strip():
                return location
        return None

    def _payload_value_from_space(self, space):
        for key in (
            "current_payload",
            "payload",
            "payload_name",
            "stored_payload",
            "contents",
            "content",
            "item",
        ):
            value = space.get(key)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return ", ".join(str(x) for x in value if str(x).strip()) or "-"
                return str(value)
        return "-"

    def _inventory_payload_rows_for_location(self, location_name):
        location = self._location_by_name(location_name)
        if not location:
            return []

        rows = []
        for idx, space in enumerate(
            location.get("inventory_spaces", []) or [], start=1
        ):
            payload = self._payload_value_from_space(space)
            rows.append(
                {
                    "space": str(space.get("name", "")).strip() or f"Inventory {idx}",
                    "payload": payload,
                    "task_id": space.get("task_id", "-"),
                    "amr_id": space.get("amr_id", "-"),
                    "status": "Stored" if payload != "-" else "Empty",
                    "timestamp": space.get("timestamp", "-"),
                    "source": "Layout JSON",
                }
            )

        return rows

    def show_location_inventory_payloads(self, location_name):
        point = self.layout_model.points.get(location_name, {})
        if point.get("kind") != "location":
            QMessageBox.information(
                self,
                "Inventory status",
                f"{location_name} is not a location node.",
            )
            return

        rows = self._inventory_payload_rows_for_location(location_name)
        if not rows:
            QMessageBox.information(
                self,
                f"Inventory status - {location_name}",
                f"Location: {location_name}\n\nNo inventory spaces are defined for this location.",
            )
            return

        dialog = LocationInventoryPayloadDialog(
            self,
            location_name,
            rows,
            self.current_time,
        )
        dialog.exec()

    def reload_current_floor_dxf(self):
        floor = self.current_floor()
        path = self.dxf_paths_by_floor.get(floor)

        if not path:
            QMessageBox.information(
                self, "No DXF", f"No DXF is assigned to floor {floor}."
            )
            return

        old_items = self.dxf_items_by_floor.pop(floor, [])
        for item in old_items:
            self.graphics_scene.removeItem(item)

        self.dxf_scenes.pop(floor, None)
        self.dxf_loading_failures.pop(floor, None)
        self.current_dxf_floor = None

        self._start_dxf_load_batch(
            [{"floor": floor, "filepath": path}],
            label=f"Reloading DXF for floor {floor}...",
        )

    def set_status(self, text: str):
        self.status_label.setText(text)

    def update_loaded_files(self):
        dxf_lines = []
        for floor in sorted(self.dxf_paths_by_floor):
            dxf_lines.append(f"F{floor}: {Path(self.dxf_paths_by_floor[floor]).name}")
        dxf_text = "\n".join(dxf_lines) if dxf_lines else "-"

        self.file_label.setText(
            f"JSON: {Path(self.current_json_path).name if self.current_json_path else '-'}\n"
            f"DXFs:\n{dxf_text}\n"
            f"CSV: {Path(self.current_csv_path).name if self.current_csv_path else '-'}"
        )

    def clear_all_loaded_dxf_items(self):
        self.hide_all_dxf_items()
        for floor, items in list(self.dxf_items_by_floor.items()):
            for item in items:
                self.graphics_scene.removeItem(item)
        self.dxf_scenes.clear()
        self.dxf_paths_by_floor.clear()
        self.dxf_items_by_floor.clear()
        self.dxf_loading_failures.clear()
        self.current_dxf_floor = None

    def _dxf_loader_active(self) -> bool:
        return bool(self.dxf_load_thread and self.dxf_load_thread.isRunning())

    def _start_dxf_load_batch(self, floor_dxf_files, label="Loading DXFs..."):
        floor_dxf_files = list(floor_dxf_files or [])

        if not floor_dxf_files:
            self.update_loaded_files()
            return

        if self._dxf_loader_active():
            self.set_status(
                "DXF loading is already running. Cancel it before starting another load."
            )
            return

        self.dxf_progress_dialog = QProgressDialog(
            label, "Cancel", 0, len(floor_dxf_files), self
        )
        self.dxf_progress_dialog.setWindowTitle("Loading DXFs")
        self.dxf_progress_dialog.setWindowModality(Qt.WindowModal)
        self.dxf_progress_dialog.setMinimumDuration(0)
        self.dxf_progress_dialog.setValue(0)
        self.dxf_progress_dialog.show()

        self.view.setUpdatesEnabled(False)

        self.dxf_load_thread = QThread(self)
        self.dxf_load_worker = DxfLoadWorker(floor_dxf_files)
        self.dxf_load_worker.moveToThread(self.dxf_load_thread)

        self.dxf_load_thread.started.connect(self.dxf_load_worker.run)
        self.dxf_load_worker.progress.connect(self.on_dxf_load_progress)
        self.dxf_load_worker.floor_loaded.connect(self.on_dxf_floor_loaded)
        self.dxf_load_worker.error.connect(self.on_dxf_load_error)
        self.dxf_load_worker.finished.connect(self.on_dxf_load_finished)
        self.dxf_load_worker.finished.connect(self.dxf_load_thread.quit)
        self.dxf_load_thread.finished.connect(self.dxf_load_thread.deleteLater)
        self.dxf_progress_dialog.canceled.connect(self.dxf_load_worker.cancel)

        self.dxf_load_thread.start()

    def start_loading_floor_dxfs_from_json(self):
        floor_dxf_files = self.layout_model.data.get("floor_dxf_files", [])
        self.clear_all_loaded_dxf_items()
        self.dxf_loading_failures.clear()

        if not floor_dxf_files:
            self.update_loaded_files()
            self.refresh_static_scene()
            return

        self._start_dxf_load_batch(floor_dxf_files, label="Loading DXFs...")

    def on_dxf_load_progress(self, value: int, total: int, label: str):
        if self.dxf_progress_dialog is None:
            return
        if self.dxf_progress_dialog:
            try:
                self.dxf_progress_dialog.setMaximum(total)
                self.dxf_progress_dialog.setValue(value)
                self.dxf_progress_dialog.setLabelText(label)
            except NameError as e:
                return

    def on_dxf_floor_loaded(self, floor: int, path: str, entities, bounds):
        floor = int(floor)
        self.dxf_scenes[floor] = DXFScene.from_content(path, entities, bounds)
        self.dxf_paths_by_floor[floor] = path
        self.dxf_loading_failures.pop(floor, None)

        # Match the editor principle: cache parsed DXF content for every floor,
        # but only create QGraphicsItems for the active floor on demand.
        old_items = self.dxf_items_by_floor.pop(floor, [])
        for item in old_items:
            self.graphics_scene.removeItem(item)

        self.update_loaded_files()
        if floor == self.current_floor():
            self.ensure_dxf_floor_loaded(floor)
            self.show_dxf_floor(floor)
            self.refresh_static_scene()
            self.view.viewport().update()

    def on_dxf_load_error(self, floor: int, message: str):
        self.dxf_loading_failures[int(floor)] = str(message)
        self.set_status(f"Failed DXF F{floor}: {message}")

    def on_dxf_load_finished(self):
        if self.dxf_progress_dialog:
            self.dxf_progress_dialog.setValue(self.dxf_progress_dialog.maximum())
            self.dxf_progress_dialog.close()
            self.dxf_progress_dialog = None

        self.view.setUpdatesEnabled(True)
        self.show_dxf_floor(self.current_floor())
        self.refresh_static_scene()
        self.view.viewport().update()

        if self.dxf_loading_failures:
            self.set_status(
                f"Loaded DXFs with {len(self.dxf_loading_failures)} failure(s)."
            )
        else:
            self.set_status("Loaded DXFs.")

        self.dxf_load_worker = None
        self.dxf_load_thread = None

    def current_dxf_scene(self) -> Optional[DXFScene]:
        return self.dxf_scenes.get(self.current_floor())

    def hide_all_dxf_items(self):
        for items in self.dxf_items_by_floor.values():
            for item in items:
                item.setVisible(False)

    def show_dxf_floor(self, floor: int):
        self.hide_all_dxf_items()
        for item in self.dxf_items_by_floor.get(floor, []):
            item.setVisible(self.show_dxf_check.isChecked())
        self.current_dxf_floor = floor

    def ensure_dxf_floor_loaded(self, floor: int):
        if floor in self.dxf_items_by_floor:
            return

        dxf_scene = self.dxf_scenes.get(floor)
        if not dxf_scene:
            self.dxf_items_by_floor[floor] = []
            return

        view_scale = self.view.transform().m11()
        items = dxf_scene.populate_graphics_scene(
            self.graphics_scene,
            view_scale=view_scale,
        )

        for item in items:
            item.setVisible(False)
            item.setData(0, "dxf")

        self.dxf_items_by_floor[floor] = items

    def current_floor(self) -> int:
        return int(self.floor_spin.value())

    def world_to_scene(self, x, y):
        return float(x), -float(y)

    def clear_items(self, items):
        for item in items:
            self.graphics_scene.removeItem(item)
        items.clear()

    def refresh_all(self):
        self.refresh_static_scene()
        self.refresh_dynamic_scene()
        self.refresh_timeline()

    def refresh_static_scene(self):
        self.clear_items(self.static_items)
        floor = self.current_floor()

        if self.show_dxf_check.isChecked():
            self.ensure_dxf_floor_loaded(floor)
            self.show_dxf_floor(floor)
        else:
            self.hide_all_dxf_items()

        self.draw_layout_qt(floor)
        self.view.viewport().update()

    def refresh_dynamic_scene(self):
        self.clear_items(self.dynamic_items)
        self.draw_dynamic_state_qt(self.current_floor())
        self.update_follow_view()
        self.update_lift_monitor_dialog()
        self.update_amr_payload_monitor_dialog()
        self.view.viewport().update()

    def draw_line_item(self, x1, y1, x2, y2, color="#858585", width=0.0, dynamic=False):
        item = QGraphicsLineItem(x1, y1, x2, y2)
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        item.setPen(pen)
        self.graphics_scene.addItem(item)
        (self.dynamic_items if dynamic else self.static_items).append(item)
        return item

    def get_text_pixel_size(self) -> int:
        scale = self.view.transform().m11()

        # 12 px when zoomed in, taper down harder when zoomed out
        if scale >= 2.0:
            return 12
        if scale >= 1.2:
            return 11
        if scale >= 0.8:
            return 10
        if scale >= 0.5:
            return 8
        if scale >= 0.35:
            return 6
        return 5

    def draw_text_item(
        self,
        x,
        y,
        text,
        color="white",
        dynamic=False,
        ignore_transform=False,
        pixel_size: Optional[float] = None,
    ):
        item = QGraphicsSimpleTextItem(text)
        item.setBrush(QBrush(QColor(color)))

        if ignore_transform and pixel_size is None:
            pixel_size = self.get_text_pixel_size()

        if pixel_size is not None:
            font = item.font()
            font.setPixelSize(max(1, int(pixel_size)))
            item.setFont(font)

        if ignore_transform:
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

        item.setPos(x, y)
        self.graphics_scene.addItem(item)
        (self.dynamic_items if dynamic else self.static_items).append(item)
        return item

    def draw_dxf_scene_qt(self):
        visible_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        visible_world = (
            visible_rect.left(),
            -visible_rect.bottom(),
            visible_rect.right(),
            -visible_rect.top(),
        )

        for entity in self.dxf_scene.entities:
            if not self.dxf_scene._bbox_intersects(entity.get("bbox"), visible_world):
                continue

            etype = entity["type"]
            if etype == "LINE":
                x1, y1 = self.world_to_scene(*entity["start"])
                x2, y2 = self.world_to_scene(*entity["end"])
                self.draw_line_item(x1, y1, x2, y2, "#858585")
            elif etype == "POLYLINE":
                pts = [QPointF(*self.world_to_scene(x, y)) for x, y in entity["points"]]
                for i in range(len(pts) - 1):
                    self.draw_line_item(
                        pts[i].x(),
                        pts[i].y(),
                        pts[i + 1].x(),
                        pts[i + 1].y(),
                        "#858585",
                    )
                if entity.get("closed") and len(pts) > 2:
                    self.draw_line_item(
                        pts[-1].x(), pts[-1].y(), pts[0].x(), pts[0].y(), "#858585"
                    )
            elif etype == "CIRCLE":
                cx, cy = self.world_to_scene(*entity["center"])
                r = float(entity["radius"])
                item = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
                item.setPen(QPen(QColor("#858585"), 0.0))
                self.graphics_scene.addItem(item)
                self.static_items.append(item)
            elif etype == "ARC":
                cx, cy = self.world_to_scene(*entity["center"])
                r = float(entity["radius"])

                start_angle = float(entity.get("start_angle", 0.0))
                end_angle = float(entity.get("end_angle", 0.0))

                span_angle = end_angle - start_angle
                if span_angle <= 0:
                    span_angle += 360.0

                rect = QRectF(cx - r, cy - r, r * 2, r * 2)

                path = QPainterPath()
                # Qt arc angles are counter-clockwise in degrees, but your Y axis is flipped
                # by world_to_scene(), so negate the angles for the correct visual direction.
                path.arcMoveTo(rect, -start_angle)
                path.arcTo(rect, -start_angle, -span_angle)

                item = QGraphicsPathItem(path)
                pen = QPen(QColor("#2e2e2e"))
                pen.setWidthF(0.0)
                item.setPen(pen)
                item.setBrush(Qt.NoBrush)
                self.graphics_scene.addItem(item)
                self.static_items.append(item)
            elif etype == "TEXT":
                text = (entity.get("text") or "").strip()
                if not text:
                    continue
                if self.view.transform().m11() < 0.3:
                    continue

                # Skip absurdly large DXF text objects that can stall the scene.
                text_height = float(entity.get("height") or 0.0)
                if text_height > 20.0:
                    continue

                x, y = self.world_to_scene(*entity["insert"])
                item = self.draw_text_item(
                    x,
                    y,
                    text,
                    "#858585",
                    ignore_transform=True,
                )
                item.setRotation(-float(entity.get("rotation", 0.0)))

    def draw_layout_qt(self, floor: int):
        for edge in self.layout_model.edges_for_floor(floor):
            a = self.layout_model.points.get(edge["from"])
            b = self.layout_model.points.get(edge["to"])
            if not a or not b:
                continue
            ax, ay = self.world_to_scene(a["x"], a["y"])
            bx, by = self.world_to_scene(b["x"], b["y"])
            self.draw_line_item(ax, ay, bx, by, "#5f8dd3", 0.0)

        for name, point in self.layout_model.points_for_floor(floor).items():
            x, y = self.world_to_scene(point["x"], point["y"])
            kind = point.get("kind")
            if kind == "location":
                item = QGraphicsEllipseItem(x - 0.5, y - 0.5, 1.0, 1.0)
                item.setBrush(QBrush(QColor("#18c37e")))
                item.setPen(QPen(Qt.NoPen))
                color = "#9bf0cd"
            elif kind == "corridor_node":
                item = QGraphicsRectItem(x - 0.4, y - 0.4, 0.8, 0.8)
                item.setBrush(QBrush(QColor("#f2c94c")))
                item.setPen(QPen(Qt.NoPen))
                color = "#ffe8a3"
            else:
                poly = QPolygonF(
                    [
                        QPointF(x, y - 0.6),
                        QPointF(x + 0.6, y),
                        QPointF(x, y + 0.6),
                        QPointF(x - 0.6, y),
                    ]
                )
                item = QGraphicsPolygonItem(poly)
                item.setBrush(QBrush(QColor("#ff7b72")))
                item.setPen(QPen(Qt.NoPen))
                color = "#ffb3ae"

            item.setData(0, "layout_node")
            item.setData(1, name)
            self.graphics_scene.addItem(item)
            self.static_items.append(item)

            if self.show_labels_check.isChecked():
                label_item = self.draw_text_item(
                    x + 0.8, y - 0.8, name, color, ignore_transform=True
                )
                label_item.setData(0, "layout_node_label")
                label_item.setData(1, name)

    def _draw_amr_box_colored_qt(self, state: dict, fill="#4da3ff"):
        x = float(state["x"])
        y = float(state["y"])
        width = max(0.05, float(self.amr_width_spin.value()))
        length = max(0.05, float(self.amr_length_spin.value()))

        heading = 0.0
        if state.get("start_node") and state.get("end_node"):
            if (
                state["start_node"] in self.layout_model.points
                and state["end_node"] in self.layout_model.points
            ):
                a = self.layout_model.points[state["start_node"]]
                b = self.layout_model.points[state["end_node"]]
                heading = math.atan2(
                    float(b["y"]) - float(a["y"]), float(b["x"]) - float(a["x"])
                )

        hl = length / 2.0
        hw = width / 2.0
        corners = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
        poly_pts = []
        for dx, dy in corners:
            rx = (dx * math.cos(heading)) - (dy * math.sin(heading))
            ry = (dx * math.sin(heading)) + (dy * math.cos(heading))
            sx, sy = self.world_to_scene(x + rx, y + ry)
            poly_pts.append(QPointF(sx, sy))

        poly = QGraphicsPolygonItem(QPolygonF(poly_pts))
        poly.setBrush(QBrush(QColor(fill)))
        poly.setPen(QPen(QColor("#858585"), 0.0))
        self.graphics_scene.addItem(poly)
        self.dynamic_items.append(poly)

        front_x = x + (hl * math.cos(heading))
        front_y = y + (hl * math.sin(heading))
        sx0, sy0 = self.world_to_scene(x, y)
        sx1, sy1 = self.world_to_scene(front_x, front_y)
        self.draw_line_item(sx0, sy0, sx1, sy1, "#858585", 0.0, dynamic=True)

    def build_lift_monitor_state(self) -> List[dict]:
        lifts = []
        current_time = self.current_time

        for lift in self.layout_model.data.get("lifts", []):
            served_floors = sorted(int(x) for x in lift.get("served_floors", []))
            start_floor = int(
                lift.get("start_floor", served_floors[0] if served_floors else 0)
            )
            state = {
                "lift_id": lift.get("id", "Lift"),
                "served_floors": served_floors or [start_floor],
                "current_floor": float(start_floor),
                "occupant": None,
                "waiting_amrs": [],
            }

            if current_time and self.sim_log.events:
                waiting = set()
                last_floor = float(start_floor)
                active_travel = None
                active_occupant = None

                for event in self.sim_log.events:
                    row = event.row

                    row_lift_id = (row.get("lift_id") or "").strip()
                    segment_type = (row.get("segment_type") or "").strip().lower()
                    event_type = (row.get("event_type") or "").strip().lower()
                    status = (row.get("status") or "").strip().lower()

                    start_node = (row.get("start_node") or "").strip()
                    end_node = (row.get("end_node") or "").strip()
                    from_location = (row.get("from_location") or "").strip()
                    to_location = (row.get("to_location") or "").strip()

                    lift_id = state["lift_id"]
                    lift_prefix = f"{lift_id}-f"

                    row_matches_lift = False

                    if row_lift_id == lift_id:
                        row_matches_lift = True
                    elif start_node.lower().startswith(lift_prefix):
                        row_matches_lift = True
                    elif end_node.lower().startswith(lift_prefix):
                        row_matches_lift = True
                    elif from_location.lower().startswith(lift_prefix):
                        row_matches_lift = True
                    elif to_location.lower().startswith(lift_prefix):
                        row_matches_lift = True

                    if not row_matches_lift:
                        continue

                    start_dt = event.start_time
                    end_dt = (
                        event.end_time
                        if event.end_time >= event.start_time
                        else event.start_time
                    )
                    if start_dt > current_time:
                        break

                    start_floor = self.sim_log._int_or_none(row.get("start_floor"))
                    end_floor = self.sim_log._int_or_none(row.get("end_floor"))
                    amr_id = (row.get("amr_id") or "").strip() or None
                    text_blob = " ".join(
                        x for x in [segment_type, event_type, status] if x
                    )

                    if end_dt <= current_time:
                        if start_floor is not None and end_floor is not None:
                            last_floor = float(end_floor)

                    is_reposition = "lift_reposition" in text_blob

                    is_travel = (
                        "lift_transfer" in text_blob
                        or "segment_lift" in text_blob
                        or (
                            row_lift_id
                            and start_floor is not None
                            and end_floor is not None
                            and start_floor != end_floor
                            and not is_reposition
                        )
                    )

                    is_waiting = any(
                        word in text_blob for word in ["wait", "queue", "board", "door"]
                    )

                    if start_dt <= current_time <= end_dt:
                        if (
                            (is_travel or is_reposition)
                            and start_floor is not None
                            and end_floor is not None
                        ):
                            total = max((end_dt - start_dt).total_seconds(), 0.001)
                            elapsed = max(
                                (current_time - start_dt).total_seconds(), 0.0
                            )
                            frac = max(0.0, min(1.0, elapsed / total))
                            active_travel = float(start_floor) + (
                                (float(end_floor) - float(start_floor)) * frac
                            )
                            if not is_reposition:
                                active_occupant = amr_id
                        elif is_waiting and amr_id:
                            waiting.add(amr_id)
                        elif row_lift_id and amr_id and "lift" in text_blob:
                            if not is_reposition:
                                active_occupant = amr_id

                state["current_floor"] = (
                    active_travel if active_travel is not None else last_floor
                )
                state["occupant"] = active_occupant
                if active_occupant in waiting:
                    waiting.discard(active_occupant)
                state["waiting_amrs"] = sorted(waiting)

            lifts.append(state)

        return lifts

    def update_lift_monitor_dialog(self):
        if self.lift_monitor_dialog is None:
            return
        lift_states = self.build_lift_monitor_state()
        self.lift_monitor_dialog.update_states(lift_states)
        if hasattr(self, "lift_dialog") and self.lift_dialog.isVisible():
            self.lift_dialog.update_from_time(self.current_time)

    def open_lift_monitor_dialog(self):
        lift_states = self.build_lift_monitor_state()
        if not lift_states:
            QMessageBox.information(
                self, "No lifts", "No lifts are defined in the loaded layout."
            )
            return

        # Reuse if already open
        if self.lift_monitor_dialog and self.lift_monitor_dialog.isVisible():
            self.lift_monitor_dialog.raise_()
            self.lift_monitor_dialog.activateWindow()
            return

        self.lift_monitor_dialog = LiftMonitorDialog(self)
        self.lift_monitor_dialog.set_lifts(lift_states)
        self.lift_monitor_dialog.show()

    def _configured_amr_slot_summary_by_base_id(self) -> Dict[str, str]:
        summaries: Dict[str, str] = {}
        for amr_cfg in self.layout_model.data.get("amrs", []) or []:
            base_id = str(amr_cfg.get("id", "")).strip()
            if not base_id:
                continue
            slots = amr_cfg.get("payload_slots", []) or []
            if not isinstance(slots, list) or not slots:
                summaries[base_id] = "1/1"
                continue
            summaries[base_id] = f"0/{len(slots)}"
        return summaries

    def _base_amr_id_from_runtime_id(self, amr_id: str) -> str:
        amr_id = str(amr_id or "").strip()
        for amr_cfg in self.layout_model.data.get("amrs", []) or []:
            base_id = str(amr_cfg.get("id", "")).strip()
            if not base_id:
                continue
            if amr_id == base_id or amr_id.startswith(base_id + "-"):
                return base_id
        return amr_id.rsplit("-", 1)[0] if "-" in amr_id else amr_id

    def _split_csv_cell(self, value) -> List[str]:
        text = str(value or "").strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]

    def _parse_onboard_payloads_from_row(self, row: dict) -> Optional[List[dict]]:
        raw = str(row.get("onboard_payloads", "") or "").strip()
        if not raw:
            return None

        try:
            value = json.loads(raw)
        except Exception:
            return None

        if not isinstance(value, list):
            return None

        records = []
        for item in value:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id", "") or "").strip()
            payload = str(item.get("payload", "") or "").strip()
            if not task_id or not payload:
                continue
            records.append(
                {
                    "task_id": task_id,
                    "payload": payload,
                    "payload_instance_id": str(
                        item.get("payload_instance_id", "") or ""
                    ).strip(),
                    "from_location": str(
                        item.get("pickup", "")
                        or item.get("from_location", "")
                        or item.get("origin", "")
                        or ""
                    ).strip(),
                    "to_location": str(
                        item.get("dropoff", "")
                        or item.get("to_location", "")
                        or item.get("destination", "")
                        or ""
                    ).strip(),
                    "slot": str(
                        item.get("slot_name", "") or item.get("slot", "") or ""
                    ).strip(),
                }
            )
        return records

    def _records_from_grouped_payload_row(self, row: dict) -> List[dict]:
        """Build per-payload records from grouped multi-pickup CSV cells.

        The simulator writes grouped pickup/dropoff rows as comma-separated
        task_id/payload/payload_slot values.  The monitor needs one record per
        payload, not just the first cell value.
        """
        task_ids = self._split_csv_cell(row.get("task_id", ""))
        payloads = self._split_csv_cell(row.get("payload", ""))
        slots = self._split_csv_cell(
            row.get("payload_slot", "") or row.get("slot_name", "")
        )
        instances = self._split_csv_cell(row.get("payload_instance_id", ""))

        if not task_ids or not payloads:
            return []

        records = []
        for idx, task_id in enumerate(task_ids):
            payload = payloads[idx] if idx < len(payloads) else payloads[-1]
            if not payload:
                continue
            records.append(
                {
                    "task_id": task_id,
                    "payload": payload,
                    "payload_instance_id": instances[idx] if idx < len(instances) else "",
                    "from_location": str(
                        row.get("from_location", "") or row.get("start_node", "") or ""
                    ).strip(),
                    "to_location": str(
                        row.get("to_location", "") or row.get("end_node", "") or ""
                    ).strip(),
                    "slot": slots[idx] if idx < len(slots) else "",
                }
            )
        return records

    def _format_onboard_payloads_for_label(self, row: dict) -> str:
        records = self._parse_onboard_payloads_from_row(row or {})
        if not records:
            records = self._records_from_grouped_payload_row(row or {})
        if not records:
            return ""
        parts = []
        for rec in records:
            payload = str(rec.get("payload", "") or "").strip()
            task_id = str(rec.get("task_id", "") or "").strip()
            slot = str(rec.get("slot", "") or "").strip()
            if not payload:
                continue
            text = payload
            if task_id:
                text = f"{text} ({task_id})"
            if slot:
                text = f"{slot}: {text}"
            parts.append(text)
        return ", ".join(parts)

    def build_amr_payload_monitor_rows(self) -> List[dict]:
        if not self.current_time or not self.sim_log.events:
            return []

        amr_states, _recent = self.sim_log.state_at(
            self.current_time, self.layout_model
        )
        onboard: Dict[str, Dict[str, dict]] = {}
        last_seen: Dict[str, datetime] = {}

        for event in self.sim_log.events:
            if event.start_time > self.current_time:
                break

            row = event.row
            amr_id = str(row.get("amr_id", "") or "").strip()
            if not amr_id:
                continue

            last_seen[amr_id] = min(self.current_time, event.end_time)

            event_type = str(row.get("event_type", "") or "").strip().lower()
            segment_type = str(row.get("segment_type", "") or "").strip().lower()
            status = str(row.get("status", "") or "").strip().lower()
            text = " ".join([event_type, segment_type, status])

            # Authoritative state from the latest patched simulator.
            parsed_onboard = self._parse_onboard_payloads_from_row(row)
            if parsed_onboard is not None:
                amr_payloads = {}
                for item in parsed_onboard:
                    item = dict(item)
                    item["updated"] = event.start_time
                    amr_payloads[item["task_id"]] = item
                onboard[amr_id] = amr_payloads
                continue

            grouped_records = self._records_from_grouped_payload_row(row)
            amr_payloads = onboard.setdefault(amr_id, {})

            if grouped_records and (
                "pickup" in text or "pick_up" in text or "load" in text
            ):
                for item in grouped_records:
                    item = dict(item)
                    item["updated"] = event.start_time
                    amr_payloads[item["task_id"]] = item
                continue

            if grouped_records and (
                "dropoff" in text
                or "drop_off" in text
                or "unload" in text
                or "complete" in text
            ):
                for item in grouped_records:
                    amr_payloads.pop(item["task_id"], None)
                continue

            # Backwards-compatible inference for older single-payload CSVs.
            task_id = str(row.get("task_id", "") or "").strip()
            payload = str(row.get("payload", "") or "").strip()
            if not task_id or not payload:
                continue

            if "pickup" in text or "pick_up" in text or "load" in text:
                amr_payloads[task_id] = {
                    "task_id": task_id,
                    "payload": payload,
                    "from_location": str(
                        row.get("from_location", "") or row.get("start_node", "") or ""
                    ).strip(),
                    "to_location": str(
                        row.get("to_location", "") or row.get("end_node", "") or ""
                    ).strip(),
                    "slot": str(
                        row.get("payload_slot", "") or row.get("slot_name", "") or ""
                    ).strip(),
                    "updated": event.start_time,
                }
            elif (
                "dropoff" in text
                or "drop_off" in text
                or "unload" in text
                or "complete" in text
            ):
                amr_payloads.pop(task_id, None)

        amr_ids = sorted(set(amr_states.keys()) | set(last_seen.keys()))
        base_slot_summary = self._configured_amr_slot_summary_by_base_id()
        rows = []

        for amr_id in amr_ids:
            state = amr_states.get(amr_id, {})
            payload_records = list(onboard.get(amr_id, {}).values())
            payload_records.sort(
                key=lambda rec: (str(rec.get("slot", "")), str(rec.get("task_id", "")))
            )
            payload_text = ", ".join(
                f"{rec['slot'] + ': ' if rec.get('slot') else ''}{rec['payload']} ({rec['task_id']})"
                for rec in payload_records
            )
            task_text = ", ".join(rec["task_id"] for rec in payload_records)

            base_id = self._base_amr_id_from_runtime_id(amr_id)
            configured_slots = base_slot_summary.get(base_id, "")
            if configured_slots and "/" in configured_slots:
                total_slots = configured_slots.split("/", 1)[1]
                slots_text = f"{len(payload_records)}/{total_slots}"
            else:
                slots_text = str(len(payload_records))

            updated = last_seen.get(amr_id) or state.get("timestamp")
            rows.append(
                {
                    "amr_id": amr_id,
                    "payloads": payload_text or "-",
                    "payload_count": len(payload_records),
                    "slots": slots_text,
                    "task_ids": task_text or (state.get("task_id") or "-"),
                    "status": state.get("status") or state.get("event_type") or "-",
                    "segment_type": state.get("segment_type") or "-",
                    "from_location": state.get("from_location")
                    or state.get("start_node")
                    or "-",
                    "to_location": state.get("to_location")
                    or state.get("end_node")
                    or "-",
                    "floor": (
                        state.get("floor") if state.get("floor") is not None else "-"
                    ),
                    "updated": (
                        updated.strftime("%Y-%m-%d %H:%M:%S") if updated else "-"
                    ),
                }
            )

        return rows

    def update_amr_payload_monitor_dialog(self):
        if self.amr_payload_monitor_dialog is None:
            return
        if not self.amr_payload_monitor_dialog.isVisible():
            return
        self.amr_payload_monitor_dialog.update_states(
            self.build_amr_payload_monitor_rows(),
            self.current_time,
        )

    def open_amr_payload_monitor_dialog(self):
        if not self.sim_log.events:
            QMessageBox.information(
                self,
                "No simulation loaded",
                "Load a simulation CSV first.",
            )
            return

        if (
            self.amr_payload_monitor_dialog
            and self.amr_payload_monitor_dialog.isVisible()
        ):
            self.amr_payload_monitor_dialog.raise_()
            self.amr_payload_monitor_dialog.activateWindow()
            return

        self.amr_payload_monitor_dialog = AmrPayloadMonitorDialog(self)
        self.amr_payload_monitor_dialog.update_states(
            self.build_amr_payload_monitor_rows(),
            self.current_time,
        )
        self.amr_payload_monitor_dialog.show()

    def _node_name_at_view_event(self, event: QMouseEvent) -> Optional[str]:
        scene_pos = self.view.mapToScene(event.position().toPoint())

        # Only accept actual node marker items.
        # Do not accept labels because ItemIgnoresTransformations can make
        # their hit boxes behave incorrectly at different zoom levels.
        for item in self.graphics_scene.items(scene_pos):
            item_type = item.data(0)
            if item_type == "layout_node":
                node_name = item.data(1)
                if node_name:
                    return str(node_name)

        # Pixel-based fallback, locations only.
        floor = self.current_floor()
        cursor_view_pos = event.position()

        best_name = None
        best_dist_px = 12.0

        for name, point in self.layout_model.points_for_floor(floor).items():
            if point.get("kind") != "location":
                continue

            sx, sy = self.world_to_scene(point["x"], point["y"])
            point_view_pos = self.view.mapFromScene(QPointF(sx, sy))

            dist_px = math.hypot(
                float(point_view_pos.x()) - float(cursor_view_pos.x()),
                float(point_view_pos.y()) - float(cursor_view_pos.y()),
            )

            if dist_px <= best_dist_px:
                best_name = name
                best_dist_px = dist_px

        return best_name

    def _tasks_dropping_off_at_node(self, node_name: str) -> List[dict]:
        if not node_name:
            return []

        tasks = []
        for task in self.layout_model.data.get("tasks", []):
            dropoff = (task.get("dropoff") or "").strip()
            if dropoff != node_name:
                continue

            tasks.append(
                {
                    "id": (task.get("id") or "").strip() or "-",
                    "pickup": (task.get("pickup") or "").strip() or "-",
                    "dropoff": dropoff,
                    "payload": (task.get("payload") or "").strip() or "-",
                    "release_datetime": (task.get("release_datetime") or "").strip()
                    or "-",
                    "priority": str(task.get("priority", "-")),
                    "target_time": str(task.get("target_time") or "").strip() or "-",
                    "route_profile": (task.get("route_profile") or "").strip() or "-",
                }
            )

        tasks.sort(
            key=lambda item: (
                item["release_datetime"],
                item["id"],
            )
        )
        return tasks

    def _tasks_picking_up_at_node(self, node_name: str) -> List[dict]:
        if not node_name:
            return []

        tasks = []
        for task in self.layout_model.data.get("tasks", []):
            pickup = str(task.get("pickup") or "").strip()
            if pickup != node_name:
                continue

            tasks.append(
                {
                    "id": str(task.get("id") or "").strip() or "-",
                    "pickup": pickup,
                    "dropoff": str(task.get("dropoff") or "").strip() or "-",
                    "payload": str(task.get("payload") or "").strip() or "-",
                    "release_datetime": str(task.get("release_datetime") or "").strip()
                    or "-",
                    "priority": str(task.get("priority") or "-"),
                    "target_time": str(task.get("target_time") or "").strip() or "-",
                    "route_profile": str(task.get("route_profile") or "").strip()
                    or "-",
                }
            )

        tasks.sort(
            key=lambda item: (
                item["release_datetime"],
                item["id"],
            )
        )
        return tasks

    def _current_amrs_at_node(self, node_name: str) -> List[dict]:
        if not node_name or not self.current_time or not self.sim_log.events:
            return []

        node = self.layout_model.points.get(node_name)
        if not node:
            return []

        node_floor = int(node.get("floor", self.current_floor()))
        node_x = float(node["x"])
        node_y = float(node["y"])

        amr_states, _recent_events = self.sim_log.state_at(
            self.current_time,
            self.layout_model,
        )
        matches = []

        for state in amr_states.values():
            state_floor = state.get("floor")
            if state_floor is None or int(state_floor) != node_floor:
                continue

            at_node = False

            if (
                state.get("start_node") == node_name
                or state.get("end_node") == node_name
            ):
                if state.get("x") is None or state.get("y") is None:
                    at_node = True

            if state.get("x") is not None and state.get("y") is not None:
                dist = math.hypot(
                    float(state["x"]) - node_x,
                    float(state["y"]) - node_y,
                )
                if dist <= 0.75:
                    at_node = True

            if at_node:
                matches.append(state)

        matches.sort(key=lambda item: str(item.get("amr_id", "")))
        return matches

    def _location_by_name(self, location_name: str) -> Optional[dict]:
        for location in self.layout_model.data.get("locations", []):
            if str(location.get("name", "")).strip() == str(location_name).strip():
                return location
        return None

    def _payload_value_from_space(self, space: dict):
        for key in (
            "current_payload",
            "payload",
            "payload_name",
            "stored_payload",
            "contents",
            "content",
            "item",
        ):
            value = space.get(key)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return ", ".join(str(x) for x in value if str(x).strip()) or "-"
                return str(value)
        return "-"

    def _find_inventory_space_row(self, rows: List[dict], space_name: str):
        space_name = str(space_name or "").strip()
        if not space_name:
            return None
        for row in rows:
            if str(row.get("space", "")).strip() == space_name:
                return row
        return None

    def _first_empty_inventory_space_row(self, rows: List[dict]):
        for row in rows:
            if str(row.get("payload", "-")).strip() in {"", "-"}:
                return row
        return None

    def _event_location_matches(
        self, row: dict, location_name: str, event_kind: str
    ) -> bool:
        location_name = str(location_name or "").strip()
        if not location_name:
            return False

        field_groups = {
            "dropoff": [
                "to_location",
                "dropoff",
                "end_node",
                "destination",
                "location",
            ],
            "pickup": ["from_location", "pickup", "start_node", "origin", "location"],
        }
        for key in field_groups.get(event_kind, []):
            if str(row.get(key, "")).strip() == location_name:
                return True
        return False

    def _inventory_space_name_from_event(self, row: dict, event_kind: str) -> str:
        keys = [
            "inventory_space",
            "inventory_space_name",
            "space",
            "space_name",
        ]
        if event_kind == "dropoff":
            keys = ["to_inventory_space", "dropoff_inventory_space"] + keys
        elif event_kind == "pickup":
            keys = ["from_inventory_space", "pickup_inventory_space"] + keys
        for key in keys:
            value = str(row.get(key, "")).strip()
            if value:
                return value
        return ""

    def _inventory_payload_rows_for_location(self, location_name: str) -> List[dict]:
        location = self._location_by_name(location_name)
        if not location:
            return []

        spaces = location.get("inventory_spaces", []) or []
        rows = []

        if spaces:
            for idx, space in enumerate(spaces, start=1):
                space_name = str(space.get("name", "")).strip() or f"Inventory {idx}"
                payload = self._payload_value_from_space(space)

                rows.append(
                    {
                        "space": space_name,
                        "payload": payload,
                        "task_id": space.get("task_id", "-"),
                        "amr_id": space.get("amr_id", "-"),
                        "status": "Stored" if payload != "-" else "Empty",
                        "timestamp": space.get("timestamp", "-"),
                        "source": "Layout JSON",
                    }
                )
        else:
            # No defined inventory spaces: still show the location contents.
            rows.append(
                {
                    "space": "Location",
                    "payload": "-",
                    "task_id": "-",
                    "amr_id": "-",
                    "status": "Empty",
                    "timestamp": "-",
                    "source": "Location fallback",
                }
            )

        if not self.current_time or not self.sim_log.events:
            return rows

        for event in self.sim_log.events:
            if event.start_time > self.current_time:
                break

            row = event.row
            event_type = str(row.get("event_type", "")).strip().lower()
            segment_type = str(row.get("segment_type", "")).strip().lower()
            status = str(row.get("status", "")).strip().lower()
            text = " ".join([event_type, segment_type, status])

            is_dropoff = any(
                token in text
                for token in ["dropoff", "drop_off", "deliver", "delivery", "unload"]
            )
            is_pickup = any(
                token in text for token in ["pickup", "pick_up", "collect", "load"]
            )

            if not is_dropoff and not is_pickup:
                continue

            if is_dropoff and self._event_location_matches(
                row, location_name, "dropoff"
            ):
                target = self._find_inventory_space_row(
                    rows, self._inventory_space_name_from_event(row, "dropoff")
                ) or self._first_empty_inventory_space_row(rows)
                if target is None:
                    continue
                target.update(
                    {
                        "payload": str(row.get("payload", "")).strip() or "-",
                        "task_id": str(row.get("task_id", "")).strip() or "-",
                        "amr_id": str(row.get("amr_id", "")).strip() or "-",
                        "status": "Occupied",
                        "timestamp": event.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "Simulation CSV",
                    }
                )

            if is_pickup and self._event_location_matches(row, location_name, "pickup"):
                payload = str(row.get("payload", "")).strip()
                target = self._find_inventory_space_row(
                    rows, self._inventory_space_name_from_event(row, "pickup")
                )
                if target is None and payload:
                    for candidate in rows:
                        if str(candidate.get("payload", "")).strip() == payload:
                            target = candidate
                            break
                if target is None:
                    continue
                target.update(
                    {
                        "payload": "-",
                        "task_id": str(row.get("task_id", "")).strip() or "-",
                        "amr_id": str(row.get("amr_id", "")).strip() or "-",
                        "status": "Empty",
                        "timestamp": event.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "Simulation CSV",
                    }
                )

        return rows

    def _inventory_space_rows_for_location(self, location_name: str) -> List[dict]:
        location = self._location_by_name(location_name)
        if not location:
            return []

        rows = []
        for idx, space in enumerate(
            location.get("inventory_spaces", []) or [], start=1
        ):
            points = list(space.get("points", []) or [])
            rows.append(
                {
                    "name": str(space.get("name", "")).strip() or f"Inventory {idx}",
                    "length_m": space.get("length_m", space.get("length", "")),
                    "width_m": space.get("width_m", space.get("width", "")),
                    "height_m": space.get("height_m", space.get("height", "")),
                    "occupied": "Yes" if bool(space.get("occupied", False)) else "No",
                    "payload": self._payload_value_from_space(space),
                    "task_id": space.get("task_id", "-"),
                    "reserved_by_task": space.get("reserved_by_task", "-"),
                    "points": len(points),
                }
            )
        return rows

    def show_location_inventory_spaces(self, location_name: str):
        point = self.layout_model.points.get(location_name, {})
        if point.get("kind") != "location":
            QMessageBox.information(
                self,
                "Inventory spaces",
                f"{location_name} is not a location node.",
            )
            return

        rows = self._inventory_payload_rows_for_location(location_name)
        if not rows:
            QMessageBox.information(
                self,
                f"Inventory status - {location_name}",
                f"Location: {location_name}\n\nNo location information was found.",
            )
            return

        dialog = LocationInventorySpacesDialog(self, location_name, rows)
        dialog.exec()

    def show_location_inventory_payloads(self, location_name: str):

        rows = self._inventory_payload_rows_for_location(location_name)
        if not rows:
            QMessageBox.information(
                self,
                f"Inventory payloads - {location_name}",
                f"Location: {location_name}\n\nNo inventory spaces are defined for this location.",
            )
            return

        dialog = LocationInventoryPayloadDialog(
            self,
            location_name,
            rows,
            self.current_time,
        )
        dialog.exec()

    def show_dropoff_tasks_at_node(self, node_name: str):
        tasks = self._tasks_dropping_off_at_node(node_name)

        if not tasks:
            QMessageBox.information(
                self,
                f"Drop-off tasks at {node_name}",
                f"Node: {node_name}\n\nNo tasks drop off at this location.",
            )
            return

        lines = [f"Node: {node_name}", f"Drop-off tasks: {len(tasks)}", ""]
        for task in tasks:
            lines.append(
                f"Task {task['id']} | Pickup: {task['pickup']} | Payload: {task['payload']} | "
                f"Release: {task['release_datetime']} | Priority: {task['priority']} | "
                f"Target: {task['target_time']} | Route profile: {task['route_profile']}"
            )

        QMessageBox.information(
            self,
            f"Drop-off tasks at {node_name}",
            "\n".join(lines),
        )

    def show_pickup_tasks_at_node(self, node_name: str):
        tasks = self._tasks_picking_up_at_node(node_name)

        if not tasks:
            QMessageBox.information(
                self,
                f"Pickup tasks at {node_name}",
                f"Node: {node_name}\n\nNo tasks pick up from this location.",
            )
            return

        lines = [f"Node: {node_name}", f"Pickup tasks: {len(tasks)}", ""]
        for task in tasks:
            lines.append(
                f"Task {task['id']} | Dropoff: {task['dropoff']} | Payload: {task['payload']} | "
                f"Release: {task['release_datetime']} | Priority: {task['priority']} | "
                f"Target: {task['target_time']} | Route profile: {task['route_profile']}"
            )

        QMessageBox.information(
            self,
            f"Pickup tasks at {node_name}",
            "\n".join(lines),
        )

    def show_node_amr_status(self, node_name: str):
        states = self._current_amrs_at_node(node_name)
        current_stamp = (
            self.current_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.current_time
            else "-"
        )

        if not states:
            QMessageBox.information(
                self,
                f"AMRs at {node_name}",
                f"Node: {node_name}\nTime: {current_stamp}\n\nNo AMRs are currently at this node.",
            )
            return

        lines = [f"Node: {node_name}", f"Time: {current_stamp}", ""]
        for state in states:
            status_text = (
                state.get("status")
                or state.get("event_type")
                or state.get("segment_type")
                or "-"
            )
            task_id = state.get("task_id") or "-"
            payload = state.get("payload") or "-"
            lines.append(
                f"{state.get('amr_id', 'AMR')} | Status: {status_text} | Task: {task_id} | Payload: {payload}"
            )

        QMessageBox.information(self, f"AMRs at {node_name}", "\n".join(lines))

    def on_view_right_click(self, event: QMouseEvent):
        node_name = self._node_name_at_view_event(event)
        if not node_name:
            return

        self.node_context_menu.clear()

        self.node_context_menu.addAction(
            "Show AMRs at node",
            lambda checked=False, name=node_name: self.show_node_amr_status(name),
        )

        self.node_context_menu.addAction(
            "Show drop-off tasks at location",
            lambda checked=False, name=node_name: self.show_dropoff_tasks_at_node(name),
        )

        self.node_context_menu.addAction(
            "Show pickup tasks at location",
            lambda checked=False, name=node_name: self.show_pickup_tasks_at_node(name),
        )

        point = self.layout_model.points.get(node_name, {})
        if point.get("kind") == "location":
            self.node_context_menu.addSeparator()
            self.node_context_menu.addAction(
                "View inventory spaces",
                lambda checked=False, name=node_name: self.show_location_inventory_spaces(
                    name
                ),
            )
            self.node_context_menu.addAction(
                "Show inventory payloads",
                lambda checked=False, name=node_name: self.show_location_inventory_payloads(
                    name
                ),
            )

        self.node_context_menu.popup(event.globalPosition().toPoint())

    def draw_dynamic_state_qt(self, floor: int):
        if not self.current_time or not self.sim_log.events:
            self.event_box.clear()
            return

        amr_states, recent_events = self.sim_log.state_at(
            self.current_time, self.layout_model
        )
        followed_amr = self.follow_combo.currentText().strip()

        for amr_id, state in amr_states.items():
            if state.get("floor") != floor:
                continue
            if state.get("x") is None or state.get("y") is None:
                continue

            is_followed = (
                self.follow_enabled_check.isChecked() and followed_amr == amr_id
            )
            x, y = self.world_to_scene(state["x"], state["y"])

            if self.show_amr_box_check.isChecked():
                self._draw_amr_box_colored_qt(
                    state, fill="#ff9f1c" if is_followed else "#4da3ff"
                )
            else:
                r = 0.5
                item = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
                item.setBrush(QBrush(QColor("#ff9f1c" if is_followed else "#4da3ff")))
                item.setPen(QPen(QColor("#858585"), 0.0))
                self.graphics_scene.addItem(item)
                self.dynamic_items.append(item)

            onboard_label = self._format_onboard_payloads_for_label(state.get("raw", {}))
            payload = onboard_label or (state.get("payload") or "")
            label = amr_id if not payload else f"{amr_id} | {payload}"
            self.draw_text_item(
                x, y - 1.2, label, "#cfe5ff", dynamic=True, ignore_transform=True
            )

            action = (
                state.get("event_type")
                or state.get("segment_type")
                or state.get("status")
                or ""
            )
            if action:
                self.draw_text_item(
                    x + 1.0,
                    y + 0.6,
                    action,
                    "#cfe5ff",
                    dynamic=True,
                    ignore_transform=True,
                )

        self.event_box.clear()
        for item in recent_events:
            row = item["row"]
            stamp = item["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            line = (
                f"{stamp} | "
                f"{row.get('amr_id', '')} | "
                f"{row.get('payload', '')} | "
                f"{row.get('segment_type', '')} | "
                f"{row.get('start_node', '')} -> {row.get('end_node', '')}"
            )
            self.event_box.append(line)

    def update_time_display(self):
        if not self.current_time:
            self.time_label.setText("No simulation loaded")
            self.update_lift_monitor_dialog()
            self.update_amr_payload_monitor_dialog()
            return
        fraction = (
            self.sim_log.time_to_fraction(self.current_time)
            if self.sim_log.start_time
            else 0.0
        )
        self.slider.blockSignals(True)
        self.slider.setValue(int(fraction * 1000))
        self.slider.blockSignals(False)
        start = (
            self.sim_log.start_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.sim_log.start_time
            else "-"
        )
        end = (
            self.sim_log.end_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.sim_log.end_time
            else "-"
        )
        self.time_label.setText(
            f"Current: {self.current_time.strftime('%Y-%m-%d %H:%M:%S')}\nStart: {start}\nEnd: {end}"
        )
        self.refresh_timeline()
        self.update_lift_monitor_dialog()
        self.update_amr_payload_monitor_dialog()

    def on_slider_change(self, value):
        if not self.sim_log.start_time:
            return
        self.current_time = self.sim_log.fraction_to_time(value / 1000.0)
        self.update_time_display()
        self.refresh_dynamic_scene()
        self.view.viewport().update()

    def on_speed_changed(self, _value=None):
        try:
            self.play_speed = float(self.speed_combo.currentText())
        except Exception:
            self.play_speed = 60.0

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.play_btn.setText("Pause" if self.is_playing else "Play")
        if self.is_playing:
            self.play_timer.start(100)
        else:
            self.play_timer.stop()

    def _tick(self):
        if not self.is_playing or not self.current_time or not self.sim_log.end_time:
            return
        self.current_time += timedelta(seconds=self.play_speed * 0.1)
        if self.current_time >= self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
            self.is_playing = False
            self.play_btn.setText("Play")
            self.play_timer.stop()
        self.update_time_display()
        self.refresh_dynamic_scene()
        self.view.viewport().update()

    def step_seconds(self, seconds: int):
        if not self.current_time:
            return
        self.current_time += timedelta(seconds=seconds)
        if self.sim_log.start_time and self.current_time < self.sim_log.start_time:
            self.current_time = self.sim_log.start_time
        if self.sim_log.end_time and self.current_time > self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
        self.update_time_display()
        self.refresh_dynamic_scene()
        self.view.viewport().update()

    def jump_start(self):
        if self.sim_log.start_time:
            self.current_time = self.sim_log.start_time
            self.update_time_display()
            self.refresh_dynamic_scene()
            self.view.viewport().update()

    def jump_end(self):
        if self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
            self.update_time_display()
            self.refresh_dynamic_scene()
            self.view.viewport().update()

    def jump_first_travel(self):
        travel_time = self.sim_log.first_travel_time()
        if travel_time is not None:
            self.current_time = travel_time
            self.update_time_display()
            self.refresh_dynamic_scene()
            self.view.viewport().update()

    def update_follow_amr_options(self):
        amr_ids = sorted(
            {
                (event.row.get("amr_id") or "").strip()
                for event in self.sim_log.events
                if (event.row.get("amr_id") or "").strip()
            }
        )
        self.follow_combo.blockSignals(True)
        self.follow_combo.clear()
        self.follow_combo.addItems(amr_ids)
        self.follow_combo.blockSignals(False)

    def load_floor_dxfs_from_json(self):
        # Backwards-compatible entry point retained for older callers.
        self.start_loading_floor_dxfs_from_json()

    def _finish_first_json_load(self):
        self.refresh_static_scene()
        self.refresh_dynamic_scene()
        self.refresh_timeline()
        self.fit_view()
        self.view.viewport().update()

    def open_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Layout JSON", "", "JSON files (*.json)"
        )
        if not path:
            return

        self.layout_model.load(path)
        self.current_json_path = path

        floors = self.layout_model.floors()
        if floors:
            self.floor_spin.blockSignals(True)
            self.floor_spin.setValue(int(floors[0]))
            self.floor_spin.blockSignals(False)

        self.update_loaded_files()
        self._sync_timeline_from_layout_and_csv()

        # Build initial scene contents immediately
        self.refresh_static_scene()
        self.refresh_dynamic_scene()
        self.refresh_timeline()

        # Let Qt finish sizing/layout before fitting the scene
        QTimer.singleShot(0, self._finish_first_json_load)

        self.start_loading_floor_dxfs_from_json()
        self.set_status(f"Loaded layout {Path(path).name}")

    def open_dxf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DXF", "", "DXF files (*.dxf)")
        if not path:
            return

        floor = self.current_floor()
        self.dxf_paths_by_floor[floor] = path
        self.dxf_loading_failures.pop(floor, None)

        old_items = self.dxf_items_by_floor.pop(floor, [])
        for item in old_items:
            self.graphics_scene.removeItem(item)

        self.dxf_scenes.pop(floor, None)
        self.current_dxf_floor = None
        self.update_loaded_files()
        self.set_status(f"Mapped DXF {Path(path).name} to floor {floor}")

        self._start_dxf_load_batch(
            [{"floor": floor, "filepath": path}],
            label=f"Loading DXF for floor {floor}...",
        )

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Simulation CSV", "", "CSV files (*.csv)"
        )
        if not path:
            return
        self.sim_log.load(path)
        self.current_csv_path = path
        self.update_follow_amr_options()
        if not self.sim_log.events:
            QMessageBox.critical(
                self, "No events", "No timestamped rows were found in the CSV."
            )
            return
        self.update_loaded_files()
        self._sync_timeline_from_layout_and_csv()
        self.refresh_all()
        self.set_status(
            f"Loaded simulation CSV {Path(path).name} with {len(self.sim_log.events)} events"
        )

    def _content_bounds(self):
        floor = self.current_floor()
        dxf_scene = self.dxf_scenes.get(floor)
        if dxf_scene and dxf_scene.bounds:
            return dxf_scene.bounds

        floor_points = self.layout_model.points_for_floor(floor)
        if floor_points:
            xs = [float(p["x"]) for p in floor_points.values()]
            ys = [float(p["y"]) for p in floor_points.values()]
            return min(xs), min(ys), max(xs), max(ys)

        return None

    def set_floor(self, floor: int):
        if floor == self.current_floor():
            self.refresh_all()
            return

        self.floor_spin.blockSignals(True)
        self.floor_spin.setValue(int(floor))
        self.floor_spin.blockSignals(False)

        self.refresh_all()

    def fit_view(self):
        bounds = self._content_bounds()
        if not bounds:
            return

        min_x, min_y, max_x, max_y = bounds

        rect_left = min_x
        rect_top = -max_y
        rect_width = max(max_x - min_x, 1.0)
        rect_height = max(max_y - min_y, 1.0)

        content_rect = QRectF(rect_left, rect_top, rect_width, rect_height)

        self.view.resetTransform()
        self.view.fitInView(content_rect, Qt.KeepAspectRatio)

        pad = max(rect_width, rect_height, 1000.0) * 20.0
        self.graphics_scene.setSceneRect(content_rect.adjusted(-pad, -pad, pad, pad))

        self.refresh_all()

    def _sync_timeline_from_layout_and_csv(self):
        layout_start = self.layout_model.task_start_time
        layout_end = self.layout_model.task_end_time
        csv_start = self.sim_log.start_time
        csv_end = self.sim_log.end_time

        # The JSON task list is only a planned schedule.  The simulation CSV is
        # the executed timeline and can legitimately contain generated tasks that
        # start before the first manual JSON task.  Use the earliest available
        # start and latest available end so loading the JSON cannot clip the
        # timeline and hide the first CSV task.
        start_candidates = [x for x in (csv_start, layout_start) if x is not None]
        end_candidates = [x for x in (csv_end, layout_end) if x is not None]

        self.sim_log.start_time = min(start_candidates) if start_candidates else None
        self.sim_log.end_time = (
            max(end_candidates) if end_candidates else self.sim_log.start_time
        )

        if self.current_time is None:
            self.current_time = self.sim_log.start_time
        elif self.sim_log.start_time and self.current_time < self.sim_log.start_time:
            self.current_time = self.sim_log.start_time
        elif self.sim_log.end_time and self.current_time > self.sim_log.end_time:
            self.current_time = self.sim_log.end_time

        # When the data range changes, keep the first events reachable.
        if hasattr(self, "timeline_scroll"):
            self.timeline_scroll.horizontalScrollBar().setValue(0)

        self.update_time_display()

    def _follow_overlay_lines(self):
        if not self.follow_enabled_check.isChecked():
            return None

        followed_amr = self.follow_combo.currentText().strip()
        if not followed_amr or not self.current_time or not self.sim_log.events:
            return None

        amr_states, _recent_events = self.sim_log.state_at(
            self.current_time, self.layout_model
        )
        state = amr_states.get(followed_amr)
        if not state:
            return None

        task_id = state.get("task_id") or "-"
        onboard_label = self._format_onboard_payloads_for_label(state.get("raw", {}))
        payload = onboard_label or state.get("payload") or "-"
        start_pos = state.get("from_location") or state.get("start_node") or "-"
        end_pos = state.get("to_location") or state.get("end_node") or "-"
        start_time = (
            state["start_time"].strftime("%Y-%m-%d %H:%M:%S")
            if state.get("start_time")
            else "-"
        )
        duration = SimulationLog._format_runtime(
            float(state.get("task_runtime_sec", 0.0))
        )

        return [
            f"Follow AMR: {followed_amr}",
            f"Task ID: {task_id}",
            f"Payload: {payload}",
            f"Start: {start_pos}",
            f"Finish: {end_pos}",
            f"Start time: {start_time}",
            f"Current duration: {duration}",
        ]

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

    def draw_overlay_panels(self, painter, viewport_rect):
        legend_lines = [
            "Legend",
            "Green circle = location",
            "Yellow square = corridor node",
            "Red diamond = lift node",
            "Blue AMR = active AMR, orange = followed AMR",
            "Timeline:",
            "blue=move, orange=lift, ",
            "green=charge, purple=pickup/dropoff",
            f"Floor: {self.current_floor()}",
        ]
        self._draw_overlay_box(
            painter,
            12,
            12,
            320,
            legend_lines,
            "#333333",
            "white",
        )

        follow_lines = self._follow_overlay_lines()
        if follow_lines:
            self._draw_overlay_box(
                painter,
                viewport_rect.width() - 332,
                12,
                320,
                follow_lines,
                "#ff9f1c",
                "#ffe2b3",
            )

    def update_follow_view(self):
        if not self.follow_enabled_check.isChecked():
            return
        if not self.current_time or not self.sim_log.events:
            return

        followed_amr = self.follow_combo.currentText().strip()
        if not followed_amr:
            return

        amr_states, _ = self.sim_log.state_at(self.current_time, self.layout_model)
        state = amr_states.get(followed_amr)
        if not state:
            return
        if state.get("x") is None or state.get("y") is None:
            return

        amr_floor = state.get("floor")
        if amr_floor is None:
            return

        if int(amr_floor) != self.current_floor():
            self.set_floor(int(amr_floor))

        sx, sy = self.world_to_scene(state["x"], state["y"])
        self.view.centerOn(sx, sy)
        self.view.viewport().update()

    def _format_duration_label(self, start_time: datetime, end_time: datetime) -> str:
        seconds = max(0.0, (end_time - start_time).total_seconds())
        total = int(seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _sum_task_segment_seconds(self, segments: List[dict]) -> float:
        total = 0.0

        for segment in segments:
            label = (segment.get("label") or "").strip().lower()
            event_type = (segment.get("event_type") or "").strip().lower()
            segment_type = (segment.get("segment_type") or "").strip().lower()

            # Ignore bookkeeping rows that should not inflate task duration.
            if label in {"task assigned", "task complete", "task overrun"}:
                continue
            if event_type in {
                "task_assigned",
                "task assigned",
                "task_complete",
                "task complete",
                "task_completed",
                "task completed",
                "task_overrun",
                "task overrun",
            }:
                continue

            start_dt = segment.get("start_time")
            end_dt = segment.get("end_time")

            if start_dt is None or end_dt is None:
                continue

            seconds = max(0.0, (end_dt - start_dt).total_seconds())
            total += seconds

        return total

    def build_task_jump_index(self) -> Dict[str, List[dict]]:
        grouped: Dict[str, List[dict]] = {}

        # Track the currently open displayed task per AMR/task_id
        open_tasks: Dict[tuple[str, str], dict] = {}

        for event in self.sim_log.events:
            row = event.row
            amr_id = (row.get("amr_id") or "").strip()
            task_id = (row.get("task_id") or "").strip()

            if not amr_id or not task_id:
                continue

            start_dt = event.start_time
            end_dt = (
                event.end_time
                if event.end_time >= event.start_time
                else event.start_time
            )

            sim_dt_str = (row.get("sim_datetime") or "").strip()
            sim_dt = (
                self.sim_log._parse_datetime(sim_dt_str) if sim_dt_str else start_dt
            )

            origin = (
                (row.get("from_location") or "").strip()
                or (row.get("start_node") or "").strip()
                or "-"
            )
            destination = (
                (row.get("to_location") or "").strip()
                or (row.get("end_node") or "").strip()
                or "-"
            )
            payload = (row.get("payload") or "").strip() or "-"

            event_type = (row.get("event_type") or "").strip()
            segment_type = (row.get("segment_type") or "").strip()
            status = (row.get("status") or "").strip()

            event_type_lower = event_type.lower()
            label_source = event_type or segment_type or status or "Segment"
            segment_label = label_source.replace("_", " ").title()

            amr_tasks = grouped.setdefault(amr_id, [])
            key = (amr_id, task_id)

            current_bucket = open_tasks.get(key)

            # Start a new displayed task only if none is currently open
            if current_bucket is None:
                current_bucket = {
                    "task_id": task_id,
                    "payload": payload,
                    "origin": origin,
                    "destination": destination,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "sim_datetime": sim_dt,
                    "segments": [],
                }
                amr_tasks.append(current_bucket)
                open_tasks[key] = current_bucket
            else:
                if start_dt < current_bucket["start_time"]:
                    current_bucket["start_time"] = start_dt
                    current_bucket["origin"] = origin
                if end_dt > current_bucket["end_time"]:
                    current_bucket["end_time"] = end_dt
                    current_bucket["destination"] = destination
                if sim_dt < current_bucket.get("sim_datetime", sim_dt):
                    current_bucket["sim_datetime"] = sim_dt
                if current_bucket["payload"] == "-" and payload != "-":
                    current_bucket["payload"] = payload

            current_bucket["segments"].append(
                {
                    "label": segment_label,
                    "origin": origin,
                    "destination": destination,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "duration": self._format_duration_label(start_dt, end_dt),
                    "event_type": event_type,
                    "segment_type": segment_type,
                    "sim_datetime": sim_dt,
                }
            )

            # Close the displayed task only on completion
            if event_type_lower in {
                "task_complete",
                "task complete",
                "task_completed",
                "task completed",
            }:
                open_tasks.pop(key, None)

        result: Dict[str, List[dict]] = {}

        for amr_id in sorted(grouped.keys()):
            task_list = grouped[amr_id]

            for task in task_list:
                task["segments"].sort(
                    key=lambda item: (
                        item.get("sim_datetime") or item["start_time"],
                        item["start_time"],
                        item["end_time"],
                        item.get("event_type", ""),
                        item.get("segment_type", ""),
                        item["label"],
                    )
                )
                total_seconds = self._sum_task_segment_seconds(task["segments"])
                task["duration"] = SimulationLog._format_runtime(total_seconds)

            task_list.sort(
                key=lambda item: (
                    item.get("sim_datetime") or item["start_time"],
                    item["start_time"],
                    item["task_id"],
                )
            )
            result[amr_id] = task_list

        return result

    def open_task_jump_dialog(self):
        if not self.sim_log.events:
            QMessageBox.information(
                self,
                "No simulation loaded",
                "Load a simulation CSV first.",
            )
            return

        grouped_tasks = self.build_task_jump_index()
        if not grouped_tasks:
            QMessageBox.information(
                self,
                "No tasks found",
                "No task rows with AMR IDs were found in the simulation log.",
            )
            return

        dialog = TaskJumpDialog(self, grouped_tasks)
        if dialog.exec() != QDialog.Accepted:
            return

        if dialog.selected_start_time is None:
            return

        self.current_time = dialog.selected_start_time
        if dialog.selected_amr_id:
            index = self.follow_combo.findText(dialog.selected_amr_id)
            if index >= 0:
                self.follow_combo.setCurrentIndex(index)
            self.follow_enabled_check.setChecked(True)

        self.update_time_display()
        self.refresh_dynamic_scene()
        self.set_status(
            f"Jumped to task start {dialog.selected_start_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.view.viewport().update()

    def build_amr_timeline_data(self) -> List[dict]:
        lanes: Dict[str, List[dict]] = {}

        for event in self.sim_log.events:
            row = event.row
            amr_id = (row.get("amr_id") or "").strip()
            if not amr_id:
                continue

            start_dt = event.start_time
            end_dt = (
                event.end_time
                if event.end_time >= event.start_time
                else event.start_time
            )

            segment_type = (row.get("segment_type") or "").strip().lower()
            event_type = (row.get("event_type") or "").strip().lower()
            lift_id = (row.get("lift_id") or "").strip()

            block_type = "other"
            color = "#6f6f6f"

            if "charge" in segment_type or "charge" in event_type:
                block_type = "charging"
                color = "#2ecc71"
            elif lift_id or "lift" in segment_type or "lift" in event_type:
                block_type = "lift"
                color = "#f39c12"
            elif any(
                word in segment_type for word in ["corridor", "move", "travel"]
            ) or any(word in event_type for word in ["move", "travel"]):
                block_type = "movement"
                color = "#3498db"
            elif "pickup" in segment_type or "dropoff" in segment_type:
                block_type = "handling"
                color = "#9b59b6"

            task_id = (row.get("task_id") or "").strip()
            payload = (row.get("payload") or "").strip()
            label_parts = [task_id or block_type.title()]
            if payload:
                label_parts.append(payload)

            lanes.setdefault(amr_id, []).append(
                {
                    "start": start_dt,
                    "end": end_dt,
                    "type": block_type,
                    "color": color,
                    "label": " | ".join(label_parts),
                }
            )

        result = []
        for amr_id in sorted(lanes.keys()):
            blocks = sorted(lanes[amr_id], key=lambda b: (b["start"], b["end"]))
            merged = []

            for block in blocks:
                if not merged:
                    merged.append(block.copy())
                    continue

                prev = merged[-1]
                same_type = (
                    prev["type"] == block["type"] and prev["color"] == block["color"]
                )
                touching = block["start"] <= prev["end"]

                if same_type and touching:
                    if block["end"] > prev["end"]:
                        prev["end"] = block["end"]
                else:
                    merged.append(block.copy())

            result.append(
                {
                    "amr_id": amr_id,
                    "blocks": merged,
                }
            )

        return result

    def _timeline_display_range(self, timeline_data: List[dict]):
        starts = []
        ends = []

        if self.sim_log.start_time is not None:
            starts.append(self.sim_log.start_time)
        if self.sim_log.end_time is not None:
            ends.append(self.sim_log.end_time)

        # Guard against stale start/end values if a JSON file is loaded after a
        # CSV.  The painted range must always include the actual event blocks.
        for lane in timeline_data or []:
            for block in lane.get("blocks", []):
                if block.get("start") is not None:
                    starts.append(block["start"])
                if block.get("end") is not None:
                    ends.append(block["end"])

        start_time = min(starts) if starts else None
        end_time = max(ends) if ends else start_time
        return start_time, end_time

    def refresh_timeline(self):
        if not hasattr(self, "timeline_widget"):
            return

        timeline_data = self.build_amr_timeline_data() if self.sim_log.events else []
        start_time, end_time = self._timeline_display_range(timeline_data)
        self.timeline_widget.set_data(
            timeline_data,
            start_time,
            end_time,
            self.current_time,
        )

    def on_timeline_seek(self, new_time: datetime):
        self.current_time = new_time
        self.update_time_display()
        self.refresh_dynamic_scene()
        self.refresh_timeline()
        self.view.viewport().update()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimulationVisualizer()
    window.show()
    sys.exit(app.exec())
