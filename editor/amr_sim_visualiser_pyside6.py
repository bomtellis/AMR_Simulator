import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


class DXFScene:
    def __init__(self):
        self.path = None
        self.entities = []
        self.bounds = None

    def clear(self):
        self.path = None
        self.entities = []
        self.bounds = None

    @staticmethod
    def _bbox_from_points(points):
        if not points:
            return None
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return (min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _bbox_intersects(a, b):
        if not a or not b:
            return False
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def _append_entity(self, entity: Dict):
        if "bbox" not in entity or entity["bbox"] is None:
            pts = entity.get("points", [])
            entity["bbox"] = self._bbox_from_points(pts)
        self.entities.append(entity)

    def load(self, path: str):
        if ezdxf is None:
            raise RuntimeError(
                "ezdxf is not installed. Install with: pip install ezdxf"
            )

        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        self.clear()
        self.path = path

        all_points = []

        def track_points(points):
            for x, y in points:
                all_points.append((float(x), float(y)))

        def add_line(start, end):
            points = [
                (float(start[0]), float(start[1])),
                (float(end[0]), float(end[1])),
            ]
            track_points(points)
            self._append_entity(
                {
                    "type": "LINE",
                    "start": points[0],
                    "end": points[1],
                    "bbox": self._bbox_from_points(points),
                }
            )

        def add_polyline(points, closed=False):
            if len(points) < 2:
                return
            clean = [(float(x), float(y)) for x, y in points]
            track_points(clean)
            self._append_entity(
                {
                    "type": "POLYLINE",
                    "points": clean,
                    "closed": bool(closed),
                    "bbox": self._bbox_from_points(clean),
                }
            )

        def add_text_entity(insert, text, height=2.5, rotation=0.0):
            x = float(insert[0])
            y = float(insert[1])
            h = float(height or 2.5)
            track_points([(x, y), (x + h, y + h)])
            self._append_entity(
                {
                    "type": "TEXT",
                    "insert": (x, y),
                    "text": str(text),
                    "height": h,
                    "rotation": float(rotation or 0.0),
                    "bbox": (x, y - h, x + max(h, len(str(text)) * h * 0.6), y + h),
                }
            )

        def add_circle(center, radius):
            cx = float(center[0])
            cy = float(center[1])
            r = float(radius)
            bbox = (cx - r, cy - r, cx + r, cy + r)
            track_points([(bbox[0], bbox[1]), (bbox[2], bbox[3])])
            self._append_entity(
                {
                    "type": "CIRCLE",
                    "center": (cx, cy),
                    "radius": r,
                    "bbox": bbox,
                }
            )

        def add_arc(center, radius, start_angle, end_angle):
            cx = float(center[0])
            cy = float(center[1])
            r = float(radius)
            bbox = (cx - r, cy - r, cx + r, cy + r)
            track_points([(bbox[0], bbox[1]), (bbox[2], bbox[3])])
            self._append_entity(
                {
                    "type": "ARC",
                    "center": (cx, cy),
                    "radius": r,
                    "start_angle": float(start_angle),
                    "end_angle": float(end_angle),
                    "bbox": bbox,
                }
            )

        def load_hatch(entity):
            try:
                boundary_paths = entity.paths
            except Exception:
                return

            for path in boundary_paths:
                points = []
                try:
                    if hasattr(path, "vertices"):
                        for vx in path.vertices:
                            points.append((float(vx[0]), float(vx[1])))
                    elif hasattr(path, "edges"):
                        for edge in path.edges:
                            edge_type = edge.__class__.__name__
                            if edge_type == "LineEdge":
                                points.append(
                                    (float(edge.start[0]), float(edge.start[1]))
                                )
                                points.append((float(edge.end[0]), float(edge.end[1])))
                            elif edge_type == "ArcEdge":
                                cx = float(edge.center[0])
                                cy = float(edge.center[1])
                                r = float(edge.radius)
                                start = math.radians(float(edge.start_angle))
                                end = math.radians(float(edge.end_angle))
                                if end < start:
                                    end += math.tau
                                steps = 24
                                for i in range(steps + 1):
                                    a = start + ((end - start) * i / steps)
                                    points.append(
                                        (cx + (r * math.cos(a)), cy + (r * math.sin(a)))
                                    )
                    if points:
                        add_polyline(points, closed=True)
                except Exception:
                    continue

        def load_insert(entity, doc_ref):
            try:
                block = doc_ref.blocks.get(entity.dxf.name)
            except Exception:
                return

            insert = entity.dxf.insert
            ix = float(insert.x)
            iy = float(insert.y)
            sx = float(getattr(entity.dxf, "xscale", 1.0) or 1.0)
            sy = float(getattr(entity.dxf, "yscale", 1.0) or 1.0)
            rotation = math.radians(float(getattr(entity.dxf, "rotation", 0.0) or 0.0))
            cos_r = math.cos(rotation)
            sin_r = math.sin(rotation)

            def transform_point(x, y):
                x *= sx
                y *= sy
                rx = (x * cos_r) - (y * sin_r)
                ry = (x * sin_r) + (y * cos_r)
                return ix + rx, iy + ry

            for child in block:
                try:
                    dtype = child.dxftype()
                    if dtype == "LINE":
                        s = child.dxf.start
                        e = child.dxf.end
                        add_line(transform_point(s.x, s.y), transform_point(e.x, e.y))
                    elif dtype in {"LWPOLYLINE", "POLYLINE"}:
                        points = []
                        try:
                            raw_points = list(child.get_points())
                            for p in raw_points:
                                points.append(transform_point(float(p[0]), float(p[1])))
                        except Exception:
                            try:
                                for v in child.vertices:
                                    points.append(
                                        transform_point(
                                            float(v.dxf.location.x),
                                            float(v.dxf.location.y),
                                        )
                                    )
                            except Exception:
                                continue
                        add_polyline(
                            points, closed=bool(getattr(child, "closed", False))
                        )
                    elif dtype == "TEXT":
                        p = child.dxf.insert
                        tx, ty = transform_point(p.x, p.y)
                        add_text_entity(
                            (tx, ty),
                            child.dxf.text,
                            child.dxf.height,
                            float(getattr(child.dxf, "rotation", 0.0) or 0.0),
                        )
                    elif dtype == "MTEXT":
                        p = child.dxf.insert
                        tx, ty = transform_point(p.x, p.y)
                        add_text_entity(
                            (tx, ty),
                            child.text,
                            child.dxf.char_height,
                            float(getattr(child.dxf, "rotation", 0.0) or 0.0),
                        )
                except Exception:
                    continue

        for entity in msp:
            dtype = entity.dxftype()
            if dtype == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                add_line((start.x, start.y), (end.x, end.y))
            elif dtype in {"LWPOLYLINE", "POLYLINE"}:
                points = []
                try:
                    raw_points = list(entity.get_points())
                    for p in raw_points:
                        points.append((float(p[0]), float(p[1])))
                except Exception:
                    try:
                        for v in entity.vertices:
                            points.append(
                                (float(v.dxf.location.x), float(v.dxf.location.y))
                            )
                    except Exception:
                        continue
                add_polyline(points, closed=bool(getattr(entity, "closed", False)))
            elif dtype == "CIRCLE":
                center = entity.dxf.center
                add_circle((center.x, center.y), entity.dxf.radius)
            elif dtype == "ARC":
                center = entity.dxf.center
                add_arc(
                    (center.x, center.y),
                    entity.dxf.radius,
                    entity.dxf.start_angle,
                    entity.dxf.end_angle,
                )
            elif dtype == "TEXT":
                insert = entity.dxf.insert
                add_text_entity(
                    (insert.x, insert.y),
                    entity.dxf.text,
                    entity.dxf.height,
                    getattr(entity.dxf, "rotation", 0.0),
                )
            elif dtype == "MTEXT":
                insert = entity.dxf.insert
                add_text_entity(
                    (insert.x, insert.y),
                    entity.text,
                    entity.dxf.char_height,
                    getattr(entity.dxf, "rotation", 0.0),
                )
            elif dtype == "HATCH":
                load_hatch(entity)
            elif dtype == "INSERT":
                load_insert(entity, doc)

        self.bounds = (
            self._bbox_from_points(all_points)
            if all_points
            else (0.0, 0.0, 100.0, 100.0)
        )


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


class DxfLoadWorker(QObject):
    progress = Signal(int, int, str)
    floor_loaded = Signal(int, str, object)
    error = Signal(int, str)
    finished = Signal()

    def __init__(self, floor_dxf_files):
        super().__init__()
        self.floor_dxf_files = list(floor_dxf_files)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.floor_dxf_files)

        for i, entry in enumerate(self.floor_dxf_files, start=1):
            if self._cancelled:
                break

            try:
                floor = int(entry.get("floor"))
                path = str(entry.get("filepath") or "").strip()
            except Exception:
                continue

            self.progress.emit(
                i - 1,
                total,
                f"Loading floor {floor}...\n{Path(path).name if path else ''}",
            )

            try:
                if not path or not Path(path).exists():
                    self.error.emit(floor, f"DXF file not found: {path}")
                    continue

                dxf_scene = DXFScene()
                dxf_scene.load(path)
                self.floor_loaded.emit(floor, path, dxf_scene)

            except Exception as exc:
                self.error.emit(floor, str(exc))

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

        self.row_height = 28
        self.left_pad = 140
        self.top_pad = 34
        self.right_pad = 40
        self.bottom_pad = 28

        self.seconds_per_pixel = 4.0
        self.min_lane_width = 1400
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))

        painter.setFont(QFont("", 9))

        if not self.timeline_data or not self.start_time or not self.end_time:
            painter.setPen(QColor("#cfcfcf"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No timeline data")
            return

        axis_y = self.top_pad - 8

        painter.setPen(QColor("#8a8a8a"))
        painter.drawLine(
            self.left_pad,
            axis_y,
            int(self.left_pad + self._usable_width()),
            axis_y,
        )

        ticks = max(6, int(self._usable_width() // 180))
        for i in range(ticks + 1):
            frac = i / max(1, ticks)
            x = self.left_pad + (self._usable_width() * frac)
            tick_time = self.start_time + ((self.end_time - self.start_time) * frac)

            painter.setPen(QColor("#2a2a2a"))
            painter.drawLine(
                int(x), axis_y - 4, int(x), self.height() - self.bottom_pad + 2
            )

            painter.setPen(QColor("#d7d7d7"))
            painter.drawText(
                int(x) - 65,
                6,
                130,
                22,
                Qt.AlignCenter,
                self._format_datetime(tick_time),
            )

        for row, lane in enumerate(self.timeline_data):
            y = self.top_pad + (row * self.row_height)

            painter.setPen(QColor("#d7d7d7"))
            painter.drawText(8, y + 17, lane["amr_id"])

            painter.setPen(QColor("#2a2a2a"))
            painter.drawLine(
                self.left_pad,
                y + 18,
                int(self.left_pad + self._usable_width()),
                y + 18,
            )

            for block in lane["blocks"]:
                x1 = self._time_to_x(block["start"])
                x2 = self._time_to_x(block["end"])
                if x2 < x1 + 2:
                    x2 = x1 + 2

                rect = QRectF(x1, y + 6, x2 - x1, 12)
                painter.fillRect(rect, QColor(block["color"]))
                painter.setPen(QColor("#000000"))
                painter.drawRect(rect)

        if self.current_time is not None:
            x = self._time_to_x(self.current_time)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(
                int(x), self.top_pad - 10, int(x), self.height() - self.bottom_pad + 4
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
        self.sim_log = SimulationLog()

        self.current_json_path: Optional[str] = None
        self.current_dxf_path: Optional[str] = None
        self.current_csv_path: Optional[str] = None
        self.current_time: Optional[datetime] = None
        self.is_playing = False
        self.play_speed = 60.0
        self.lift_monitor_dialog: Optional[LiftMonitorDialog] = None
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

    def on_zoom(self):
        self.zoom_redraw_timer.start(20)
        self.refresh_static_scene()
        self.refresh_dynamic_scene()

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
            pan_callback=lambda: self.pan_redraw_timer.start(20),
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

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.addWidget(self.view)
        self.main_splitter.addWidget(self.timeline_scroll)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([760, 220])

        layout.addWidget(side)
        layout.addWidget(self.main_splitter, 1)

    def reload_current_floor_dxf(self):
        floor = self.current_floor()
        path = self.dxf_paths_by_floor.get(floor)

        if not path:
            QMessageBox.information(
                self, "No DXF", f"No DXF is assigned to floor {floor}."
            )
            return

        try:
            old_items = self.dxf_items_by_floor.pop(floor, [])
            for item in old_items:
                self.graphics_scene.removeItem(item)

            self.dxf_scenes.pop(floor, None)

            dxf_scene = DXFScene()
            dxf_scene.load(path)

            self.dxf_scenes[floor] = dxf_scene
            self.dxf_paths_by_floor[floor] = path

            self.ensure_dxf_floor_loaded(floor)
            self.show_dxf_floor(floor)

            self.fit_view()
            self.refresh_static_scene()
            self.refresh_dynamic_scene()
            self.set_status(f"Reloaded DXF for floor {floor}: {Path(path).name}")

        except Exception as exc:
            QMessageBox.critical(
                self,
                "DXF reload failed",
                f"Failed to reload DXF for floor {floor}:\n{exc}",
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
        self.current_dxf_floor = None

    def start_loading_floor_dxfs_from_json(self):
        floor_dxf_files = self.layout_model.data.get("floor_dxf_files", [])
        self.clear_all_loaded_dxf_items()

        if not floor_dxf_files:
            self.update_loaded_files()
            self.refresh_static_scene()
            return

        self.dxf_progress_dialog = QProgressDialog(
            "Loading DXFs...", "Cancel", 0, len(floor_dxf_files), self
        )
        self.dxf_progress_dialog.setWindowTitle("Loading")
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

    def on_dxf_floor_loaded(self, floor: int, path: str, dxf_scene):
        self.dxf_scenes[floor] = dxf_scene
        self.dxf_paths_by_floor[floor] = path
        self.ensure_dxf_floor_loaded(floor)
        self.update_loaded_files()
        if floor == self.current_floor():
            self.show_dxf_floor(floor)
            self.refresh_static_scene()
            self.view.viewport().update()

    def on_dxf_load_error(self, floor: int, message: str):
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

        items = []
        for entity in dxf_scene.entities:
            etype = entity["type"]
            item = None

            if etype == "LINE":
                x1, y1 = self.world_to_scene(*entity["start"])
                x2, y2 = self.world_to_scene(*entity["end"])
                item = QGraphicsLineItem(x1, y1, x2, y2)
                pen = QPen(QColor("#858585"))
                pen.setWidthF(0.0)
                item.setPen(pen)

            elif etype == "POLYLINE":
                pts = [QPointF(*self.world_to_scene(x, y)) for x, y in entity["points"]]
                poly = QPolygonF(pts)
                item = QGraphicsPolygonItem(poly)
                item.setBrush(Qt.NoBrush)
                pen = QPen(QColor("#bebebe"))
                pen.setWidthF(0.0)
                item.setPen(pen)

            elif etype == "CIRCLE":
                cx, cy = self.world_to_scene(*entity["center"])
                r = float(entity["radius"])
                item = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
                pen = QPen(QColor("#bebebe"))
                pen.setWidthF(0.0)
                item.setPen(pen)
                item.setBrush(Qt.NoBrush)

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
                path.arcMoveTo(rect, -start_angle)
                path.arcTo(rect, -start_angle, -span_angle)

                item = QGraphicsPathItem(path)
                pen = QPen(QColor("#2e2e2e"))
                pen.setWidthF(0.0)
                item.setPen(pen)
                item.setBrush(Qt.NoBrush)

            elif etype == "TEXT":
                text = (entity.get("text") or "").strip()
                if not text:
                    continue
                if self.view.transform().m11() < 0.3:
                    continue

                text_height = float(entity.get("height") or 0.0)
                if text_height > 20:
                    continue

                x, y = self.world_to_scene(*entity["insert"])
                item = QGraphicsSimpleTextItem(text)
                item.setBrush(QBrush(QColor("#C0C0C0")))
                font = item.font()
                font.setPixelSize(12)
                item.setFont(font)
                item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                item.setPos(x, y)
                item.setRotation(-float(entity.get("rotation", 0.0)))

            if item is None:
                continue

            item.setVisible(False)
            item.setData(0, "dxf")
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
            self.graphics_scene.addItem(item)
            items.append(item)

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

    def _node_name_at_view_event(self, event: QMouseEvent) -> Optional[str]:
        scene_pos = self.view.mapToScene(event.position().toPoint())

        for item in self.graphics_scene.items(scene_pos):
            item_type = item.data(0)
            if item_type in {"layout_node", "layout_node_label"}:
                node_name = item.data(1)
                if node_name:
                    return str(node_name)

        floor = self.current_floor()
        world_x = float(scene_pos.x())
        world_y = -float(scene_pos.y())
        best_name = None
        best_dist = 2.0

        for name, point in self.layout_model.points_for_floor(floor).items():
            dist = math.hypot(
                float(point["x"]) - world_x,
                float(point["y"]) - world_y,
            )
            if dist <= best_dist:
                best_name = name
                best_dist = dist

        return best_name

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

            payload = state.get("payload") or ""
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
        self.hide_all_dxf_items()

        for floor, items in list(self.dxf_items_by_floor.items()):
            for item in items:
                self.graphics_scene.removeItem(item)

        self.dxf_scenes.clear()
        self.dxf_paths_by_floor.clear()
        self.dxf_items_by_floor.clear()

        floor_dxf_files = self.layout_model.data.get("floor_dxf_files", [])
        total = len(floor_dxf_files)

        if total == 0:
            return

        progress = QProgressDialog("Loading DXFs...", "Cancel", 0, total, self)
        progress.setWindowTitle("Loading")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self.view.setUpdatesEnabled(False)

        for i, entry in enumerate(floor_dxf_files):
            if progress.wasCanceled():
                break

            floor = int(entry.get("floor"))
            path = str(entry.get("filepath") or "").strip()

            progress.setLabelText(f"Loading floor {floor}...\n{Path(path).name}")
            progress.setValue(i)
            QApplication.processEvents()

            try:
                if not path or not Path(path).exists():
                    continue

                dxf_scene = DXFScene()
                dxf_scene.load(path)

                self.dxf_scenes[floor] = dxf_scene
                self.dxf_paths_by_floor[floor] = path

                self.ensure_dxf_floor_loaded(floor)

            except Exception as exc:
                self.set_status(f"Failed DXF F{floor}: {exc}")

        progress.setValue(total)
        self.view.setUpdatesEnabled(True)
        self.view.viewport().update()

        self.show_dxf_floor(self.current_floor())
        self.update_loaded_files()

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
        try:
            dxf_scene = DXFScene()
            dxf_scene.load(path)

            self.dxf_scenes[floor] = dxf_scene
            self.dxf_paths_by_floor[floor] = path

            old_items = self.dxf_items_by_floor.pop(floor, [])
            for item in old_items:
                self.graphics_scene.removeItem(item)

            self.ensure_dxf_floor_loaded(floor)
            self.show_dxf_floor(floor)

            self.update_loaded_files()
            self.fit_view()
            self.set_status(f"Loaded DXF {Path(path).name} for floor {floor}")
        except Exception as exc:
            QMessageBox.critical(self, "DXF load failed", str(exc))

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

        if layout_start is not None:
            self.sim_log.start_time = layout_start
        elif csv_start is not None:
            self.sim_log.start_time = csv_start

        candidates = [x for x in (layout_end, csv_end) if x is not None]
        self.sim_log.end_time = (
            max(candidates) if candidates else self.sim_log.start_time
        )

        self.current_time = self.sim_log.start_time
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
        payload = state.get("payload") or "-"
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

            lanes.setdefault(amr_id, []).append(
                {
                    "start": start_dt,
                    "end": end_dt,
                    "type": block_type,
                    "color": color,
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

    def refresh_timeline(self):
        if not hasattr(self, "timeline_widget"):
            return

        timeline_data = self.build_amr_timeline_data() if self.sim_log.events else []
        self.timeline_widget.set_data(
            timeline_data,
            self.sim_log.start_time,
            self.sim_log.end_time,
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
