import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import ezdxf
except Exception:  # pragma: no cover
    ezdxf = None


@dataclass
class VisualEvent:
    start_time: datetime
    end_time: datetime
    row: dict


import math
from typing import Dict, List, Tuple

try:
    import ezdxf
except Exception:  # pragma: no cover
    ezdxf = None


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

    @staticmethod
    def _expand_bbox(bbox, pad):
        if not bbox:
            return None
        return (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)

    @staticmethod
    def _text_pixel_height(world_to_canvas, insert, model_height):
        return 8

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

    def fit_transform(self, canvas_w: int, canvas_h: int, padding: int = 40):
        if not self.bounds:
            return 1.0, padding, canvas_h - padding
        min_x, min_y, max_x, max_y = self.bounds
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        sx = (canvas_w - (padding * 2)) / width
        sy = (canvas_h - (padding * 2)) / height
        scale = min(sx, sy)
        offset_x = padding - (min_x * scale)
        offset_y = canvas_h - padding + (min_y * scale)
        return scale, offset_x, offset_y

    def _visible_world_bbox(self, canvas, world_to_canvas):
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        def canvas_to_world(cx, cy):
            x0, y0 = world_to_canvas(0.0, 0.0)
            x1, y1 = world_to_canvas(1.0, 1.0)
            sx = x1 - x0
            sy = y1 - y0
            if sx == 0 or sy == 0:
                return 0.0, 0.0
            wx = cx / sx
            wy = (cy - y0) / sy
            return wx, wy

        corners = [
            canvas_to_world(0, 0),
            canvas_to_world(width, 0),
            canvas_to_world(0, height),
            canvas_to_world(width, height),
        ]
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        return (min(xs), min(ys), max(xs), max(ys))

    def draw(self, canvas, world_to_canvas):
        visible_world = self._expand_bbox(
            self._visible_world_bbox(canvas, world_to_canvas), 2.0
        )

        for entity in self.entities:
            if not self._bbox_intersects(entity.get("bbox"), visible_world):
                continue

            etype = entity["type"]
            if etype == "LINE":
                x1, y1 = world_to_canvas(*entity["start"])
                x2, y2 = world_to_canvas(*entity["end"])
                canvas.create_line(x1, y1, x2, y2, fill="#2e2e2e")
            elif etype == "POLYLINE":
                pts = []
                for x, y in entity["points"]:
                    cx, cy = world_to_canvas(x, y)
                    pts.extend([cx, cy])
                if len(pts) >= 4:
                    canvas.create_line(*pts, fill="#2e2e2e")
                    if entity.get("closed"):
                        canvas.create_line(
                            pts[-2], pts[-1], pts[0], pts[1], fill="#2e2e2e"
                        )
            elif etype == "CIRCLE":
                cx, cy = world_to_canvas(*entity["center"])
                ex, _ = world_to_canvas(
                    entity["center"][0] + entity["radius"], entity["center"][1]
                )
                r = abs(ex - cx)
                if r >= 1:
                    canvas.create_oval(
                        cx - r, cy - r, cx + r, cy + r, outline="#2e2e2e"
                    )
            elif etype == "ARC":
                cx, cy = world_to_canvas(*entity["center"])
                ex, _ = world_to_canvas(
                    entity["center"][0] + entity["radius"], entity["center"][1]
                )
                r = abs(ex - cx)
                if r >= 1:
                    canvas.create_arc(
                        cx - r,
                        cy - r,
                        cx + r,
                        cy + r,
                        start=-entity["end_angle"],
                        extent=entity["end_angle"] - entity["start_angle"],
                        style="arc",
                        outline="#2e2e2e",
                    )
            elif etype == "TEXT":
                x, y = world_to_canvas(*entity["insert"])
                size = self._text_pixel_height(
                    world_to_canvas, entity["insert"], entity.get("height", 2.5)
                )
                canvas.create_text(
                    x,
                    y,
                    text=entity.get("text", ""),
                    anchor="sw",
                    fill="#4a4a4a",
                    angle=-entity.get("rotation", 0.0),
                    font=("Arial", size),
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

        candidates = [
            value,
            value.replace("Z", "+00:00"),
        ]
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

        candidates = [
            value,
            value.replace("Z", "+00:00"),
        ]
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

            if segment_type in travel_markers:
                return event.start_time

            if event_type in travel_markers:
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
                    VisualEvent(
                        start_time=start_dt,
                        end_time=end_dt,
                        row=row,
                    )
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
        task_assignment_start: Dict[Tuple[str, str], datetime] = {}

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
                task_key = (amr_id, task_id)
                if task_key not in task_assignment_start:
                    task_assignment_start[task_key] = start_dt

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

            state["task_id"] = task_id
            state["payload"] = payload
            state["event_type"] = event_type
            state["segment_type"] = segment_type
            state["status"] = status
            state["timestamp"] = min(current_time, end_dt)
            state["start_time"] = start_dt
            state["end_time"] = end_dt
            state["start_node"] = start_node
            state["end_node"] = end_node
            state["from_location"] = from_location
            state["to_location"] = to_location
            state["raw"] = row

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
                if end_x is not None:
                    state["x"] = end_x
                elif start_x is not None:
                    state["x"] = start_x

                if end_y is not None:
                    state["y"] = end_y
                elif start_y is not None:
                    state["y"] = start_y

                if end_floor is not None:
                    state["floor"] = end_floor
                elif start_floor is not None:
                    state["floor"] = start_floor

                state["path"] = None

            if task_id:
                task_key = (amr_id, task_id)
                assignment_start = task_assignment_start.get(task_key, start_dt)
                state["task_runtime_sec"] = max(
                    (current_time - assignment_start).total_seconds(), 0.0
                )
            else:
                state["task_runtime_sec"] = 0.0

            amr_states[amr_id] = state
            recent_events.append({"timestamp": min(current_time, end_dt), "row": row})

        return amr_states, recent_events[-12:]


class SimulationVisualizer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AMR Simulation Visualiser")
        self.geometry("1600x960")

        self.layout_model = LayoutModel()
        self.dxf_scene = DXFScene()
        self.sim_log = SimulationLog()

        self.scale = 5.0
        self.offset_x = 220
        self.offset_y = 220
        self.last_pan = None

        self.current_json_path: Optional[str] = None
        self.current_dxf_path: Optional[str] = None
        self.current_csv_path: Optional[str] = None
        self.current_time: Optional[datetime] = None
        self.is_playing = False
        self.play_speed = 60.0
        self._timer_job = None
        self.floor_var = tk.IntVar(value=0)
        self.show_dxf_var = tk.BooleanVar(value=True)
        self.show_labels_var = tk.BooleanVar(value=True)
        self.follow_time_var = tk.BooleanVar(value=False)
        self.amr_width_var = tk.DoubleVar(value=0.8)
        self.amr_length_var = tk.DoubleVar(value=1.2)
        self.show_amr_box_var = tk.BooleanVar(value=True)
        self.follow_amr_var = tk.StringVar(value="")
        self.follow_enabled_var = tk.BooleanVar(value=False)
        self.slider_var = tk.DoubleVar(value=0.0)
        self.time_label_var = tk.StringVar(value="No simulation loaded")
        self.status_var = tk.StringVar(value="Ready")
        self.file_var = tk.StringVar(value="No files loaded")

        self._build_ui()
        self.refresh_canvas()

    def _center_view_on_world(self, x: float, y: float):
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        self.offset_x = (canvas_w / 2.0) - (x * self.scale)
        self.offset_y = (canvas_h / 2.0) + (y * self.scale)

    @staticmethod
    def _format_runtime(seconds: float) -> str:
        total = max(0, int(seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self, padding=8)
        side.grid(row=0, column=0, sticky="ns")
        side.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg="#111111")
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
        self.canvas.bind("<Button-2>", self.on_middle_click)
        self.canvas.bind("<B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_middle_release)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)

        row = 0
        ttk.Button(side, text="Open Layout JSON", command=self.open_json).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(side, text="Open DXF", command=self.open_dxf).grid(
            row=row, column=0, sticky="ew", pady=4
        )
        row += 1
        ttk.Button(side, text="Open Simulation CSV", command=self.open_csv).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(side, text="Fit View", command=self.fit_view).grid(
            row=row, column=0, sticky="ew", pady=4
        )
        row += 1

        ttk.Separator(side).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Label(side, text="Floor").grid(row=row, column=0, sticky="w")
        row += 1
        floor_row = ttk.Frame(side)
        floor_row.grid(row=row, column=0, sticky="ew")
        self.floor_spin = ttk.Spinbox(
            floor_row, from_=0, to=99, textvariable=self.floor_var, width=8
        )
        self.floor_spin.pack(side="left")
        ttk.Button(floor_row, text="Go", command=self.refresh_canvas).pack(
            side="left", padx=4
        )
        row += 1

        ttk.Checkbutton(
            side,
            text="Show DXF",
            variable=self.show_dxf_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1
        ttk.Checkbutton(
            side,
            text="Show labels",
            variable=self.show_labels_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Checkbutton(
            side, text="Follow slider time", variable=self.follow_time_var
        ).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Checkbutton(
            side,
            text="Show AMR box",
            variable=self.show_amr_box_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Label(side, text="AMR width (m)").grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        width_spin = ttk.Spinbox(
            side,
            from_=0.1,
            to=5.0,
            increment=0.1,
            textvariable=self.amr_width_var,
            width=10,
            command=self.refresh_canvas,
        )
        width_spin.grid(row=row, column=0, sticky="ew")
        width_spin.bind("<KeyRelease>", lambda _e: self.refresh_canvas())
        row += 1

        ttk.Label(side, text="AMR length (m)").grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        length_spin = ttk.Spinbox(
            side,
            from_=0.1,
            to=5.0,
            increment=0.1,
            textvariable=self.amr_length_var,
            width=10,
            command=self.refresh_canvas,
        )
        length_spin.grid(row=row, column=0, sticky="ew")
        length_spin.bind("<KeyRelease>", lambda _e: self.refresh_canvas())
        row += 1

        ttk.Separator(side).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Separator(side).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Label(side, text="Follow AMR").grid(row=row, column=0, sticky="w")
        row += 1

        self.follow_combo = ttk.Combobox(
            side, textvariable=self.follow_amr_var, state="readonly"
        )
        self.follow_combo.grid(row=row, column=0, sticky="ew")
        self.follow_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_canvas())
        row += 1

        ttk.Checkbutton(
            side,
            text="Enable follow",
            variable=self.follow_enabled_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Label(side, text="Playback").grid(row=row, column=0, sticky="w")
        row += 1

        # Playback controls

        controls = ttk.Frame(side)
        controls.grid(row=row, column=0, sticky="ew")
        ttk.Button(controls, text="|<", command=self.jump_start).pack(side="left")
        ttk.Button(controls, text="First Move", command=self.jump_first_travel).pack(
            side="left", padx=2
        )
        ttk.Button(controls, text="-10s", command=lambda: self.step_seconds(-10)).pack(
            side="left", padx=2
        )
        self.play_btn = ttk.Button(controls, text="Play", command=self.toggle_play)
        self.play_btn.pack(side="left", padx=2)
        ttk.Button(controls, text="+10s", command=lambda: self.step_seconds(10)).pack(
            side="left", padx=2
        )
        ttk.Button(controls, text=">|", command=self.jump_end).pack(side="left")

        # End playback controls

        ttk.Label(side, textvariable=self.time_label_var, wraplength=260).grid(
            row=row, column=0, sticky="w", pady=(8, 0)
        )
        row += 1
        self.slider = ttk.Scale(
            side,
            from_=0.0,
            to=1.0,
            variable=self.slider_var,
            command=self.on_slider_change,
        )
        self.slider.grid(row=row, column=0, sticky="ew")
        row += 1

        ttk.Label(side, text="Playback speed (sim seconds / real second)").grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        self.speed_combo = ttk.Combobox(
            side,
            state="readonly",
            values=["1", "2", "5", "10", "30", "60", "120", "300"],
        )
        self.speed_combo.set("60")
        self.speed_combo.bind("<<ComboboxSelected>>", self.on_speed_changed)
        self.speed_combo.grid(row=row, column=0, sticky="ew")
        row += 1

        ttk.Separator(side).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1
        ttk.Label(side, text="Loaded files").grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Label(side, textvariable=self.file_var, wraplength=260).grid(
            row=row, column=0, sticky="w"
        )
        row += 1
        ttk.Label(side, text="Status").grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1
        ttk.Label(side, textvariable=self.status_var, wraplength=260).grid(
            row=row, column=0, sticky="w"
        )
        row += 1

        self.event_box = tk.Text(side, height=18, width=34)
        self.event_box.grid(row=row, column=0, sticky="nsew", pady=(12, 0))
        side.rowconfigure(row, weight=1)

    def set_status(self, text: str):
        self.status_var.set(text)

    def world_to_canvas(self, x, y):
        return (x * self.scale) + self.offset_x, (-y * self.scale) + self.offset_y

    def canvas_to_world(self, cx, cy):
        return (cx - self.offset_x) / self.scale, -((cy - self.offset_y) / self.scale)

    def fit_view(self):
        if self.dxf_scene.bounds:
            canvas_w = max(self.canvas.winfo_width(), 1000)
            canvas_h = max(self.canvas.winfo_height(), 700)
            self.scale, self.offset_x, self.offset_y = self.dxf_scene.fit_transform(
                canvas_w, canvas_h
            )
        self.refresh_canvas()

    def _apply_follow_amr_floor(self):
        if not self.follow_enabled_var.get():
            return
        if not self.current_time or not self.sim_log.events:
            return

        followed_amr = self.follow_amr_var.get().strip()
        if not followed_amr:
            return

        amr_states, _ = self.sim_log.state_at(self.current_time, self.layout_model)
        state = amr_states.get(followed_amr)
        if not state:
            return

        followed_floor = state.get("floor")
        if followed_floor is not None and int(self.floor_var.get()) != int(
            followed_floor
        ):
            self.floor_var.set(int(followed_floor))

        if state.get("x") is not None and state.get("y") is not None:
            self._center_view_on_world(float(state["x"]), float(state["y"]))

    def refresh_canvas(self):
        self._apply_follow_amr_floor()
        self.canvas.delete("all")
        floor = int(self.floor_var.get())
        self.draw_grid()
        if self.show_dxf_var.get() and self.dxf_scene.entities:
            self.dxf_scene.draw(self.canvas, self.world_to_canvas)
        self.draw_layout(floor)
        self.draw_dynamic_state(floor)
        self.draw_legend()

    def draw_grid(self):
        w = self.canvas.winfo_width() or 1000
        h = self.canvas.winfo_height() or 800
        spacing = 50
        for x in range(0, w, spacing):
            self.canvas.create_line(x, 0, x, h, fill="#1d1d1d")
        for y in range(0, h, spacing):
            self.canvas.create_line(0, y, w, y, fill="#1d1d1d")

    def draw_layout(self, floor: int):
        for edge in self.layout_model.edges_for_floor(floor):
            a = self.layout_model.points.get(edge["from"])
            b = self.layout_model.points.get(edge["to"])
            if not a or not b:
                continue
            ax, ay = self.world_to_canvas(a["x"], a["y"])
            bx, by = self.world_to_canvas(b["x"], b["y"])
            self.canvas.create_line(ax, ay, bx, by, fill="#5f8dd3", width=2)

        for name, point in self.layout_model.points_for_floor(floor).items():
            x, y = self.world_to_canvas(point["x"], point["y"])
            kind = point.get("kind")
            if kind == "location":
                self.canvas.create_oval(
                    x - 5, y - 5, x + 5, y + 5, fill="#18c37e", outline=""
                )
                color = "#9bf0cd"
            elif kind == "corridor_node":
                self.canvas.create_rectangle(
                    x - 4, y - 4, x + 4, y + 4, fill="#f2c94c", outline=""
                )
                color = "#ffe8a3"
            else:
                self.canvas.create_polygon(
                    x, y - 6, x + 6, y, x, y + 6, x - 6, y, fill="#ff7b72", outline=""
                )
                color = "#ffb3ae"
            if self.show_labels_var.get():
                self.canvas.create_text(
                    x + 8, y - 8, text=name, anchor="sw", fill=color
                )

    def _draw_amr_box_colored(self, state: dict, fill="#4da3ff"):
        x = float(state["x"])
        y = float(state["y"])
        width = max(0.05, float(self.amr_width_var.get()))
        length = max(0.05, float(self.amr_length_var.get()))

        heading = 0.0
        if state.get("start_node") and state.get("end_node"):
            if (
                state["start_node"] in self.layout_model.points
                and state["end_node"] in self.layout_model.points
            ):
                a = self.layout_model.points[state["start_node"]]
                b = self.layout_model.points[state["end_node"]]
                heading = math.atan2(
                    float(b["y"]) - float(a["y"]),
                    float(b["x"]) - float(a["x"]),
                )

        hl = length / 2.0
        hw = width / 2.0
        corners = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]

        pts = []
        for dx, dy in corners:
            rx = (dx * math.cos(heading)) - (dy * math.sin(heading))
            ry = (dx * math.sin(heading)) + (dy * math.cos(heading))
            cx, cy = self.world_to_canvas(x + rx, y + ry)
            pts.extend([cx, cy])

        self.canvas.create_polygon(
            *pts,
            fill=fill,
            outline="#ffffff",
            width=2,
        )

        front_x = x + (hl * math.cos(heading))
        front_y = y + (hl * math.sin(heading))
        nose_x, nose_y = self.world_to_canvas(front_x, front_y)
        centre_x, centre_y = self.world_to_canvas(x, y)
        self.canvas.create_line(
            centre_x,
            centre_y,
            nose_x,
            nose_y,
            fill="#ffffff",
            width=2,
        )

    def _draw_amr_box(self, state: dict):
        self._draw_amr_box_colored(state, fill="#4da3ff")

    def draw_dynamic_state(self, floor: int):
        if not self.current_time or not self.sim_log.events:
            self.event_box.delete("1.0", "end")
            return

        amr_states, recent_events = self.sim_log.state_at(
            self.current_time, self.layout_model
        )

        followed_amr = self.follow_amr_var.get().strip()

        for amr_id, state in amr_states.items():
            if state.get("floor") != floor:
                continue
            if state.get("x") is None or state.get("y") is None:
                continue

            is_followed = self.follow_enabled_var.get() and followed_amr == amr_id
            x, y = self.world_to_canvas(state["x"], state["y"])

            if self.show_amr_box_var.get():
                self._draw_amr_box_colored(
                    state,
                    fill="#ff9f1c" if is_followed else "#4da3ff",
                )
            else:
                self.canvas.create_oval(
                    x - 10,
                    y - 10,
                    x + 10,
                    y + 10,
                    fill="#ff9f1c" if is_followed else "#4da3ff",
                    outline="#ffffff",
                    width=3 if is_followed else 2,
                )

            payload = state.get("payload") or ""
            label = amr_id if not payload else f"{amr_id} | {payload}"
            self.canvas.create_text(
                x,
                y - 18,
                text=label,
                fill="#cfe5ff",
            )

            action = (
                state.get("event_type")
                or state.get("segment_type")
                or state.get("status")
                or ""
            )
            if action:
                self.canvas.create_text(
                    x + 12,
                    y + 14,
                    text=action,
                    anchor="nw",
                    fill="#cfe5ff",
                )

        self.event_box.delete("1.0", "end")
        for item in recent_events:
            row = item["row"]
            stamp = item["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            line = (
                f"{stamp} | "
                f"{row.get('amr_id', '')} | "
                f"{row.get('payload', '')} | "
                f"{row.get('segment_type', '')} | "
                f"{row.get('start_node', '')} -> {row.get('end_node', '')}\n"
            )
            self.event_box.insert("end", line)

        self.draw_follow_info_box(amr_states)

    def draw_follow_info_box(self, amr_states: dict):
        if not self.follow_enabled_var.get():
            return

        followed_amr = self.follow_amr_var.get().strip()
        if not followed_amr:
            return

        state = amr_states.get(followed_amr)
        if not state:
            return

        canvas_w = self.canvas.winfo_width() or 1200
        x2 = canvas_w - 12
        x1 = canvas_w - 340
        y1 = 12
        y2 = 154

        task_id = state.get("task_id") or "-"
        payload = state.get("payload") or "-"
        start_pos = state.get("from_location") or state.get("start_node") or "-"
        end_pos = state.get("to_location") or state.get("end_node") or "-"
        start_time = "-"
        if state.get("start_time"):
            start_time = state["start_time"].strftime("%Y-%m-%d %H:%M:%S")
        duration = self._format_runtime(float(state.get("task_runtime_sec", 0.0)))

        lines = [
            f"Follow AMR: {followed_amr}",
            f"Task ID: {task_id}",
            f"Payload: {payload}",
            f"Start: {start_pos}",
            f"Finish: {end_pos}",
            f"Start time: {start_time}",
            f"Current duration: {duration}",
        ]

        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill="#151515",
            outline="#ff9f1c",
            width=2,
        )

        y = y1 + 10
        for i, line in enumerate(lines):
            self.canvas.create_text(
                x1 + 10,
                y,
                text=line,
                anchor="nw",
                fill="#ffe2b3" if i == 0 else "white",
            )
            y += 19

    def draw_legend(self):
        self.canvas.create_rectangle(10, 10, 325, 122, fill="#151515", outline="#333")
        lines = [
            "Legend",
            "Green circle = location",
            "Yellow square = corridor node",
            "Red diamond = lift node",
            "Blue AMR = active AMR, orange = followed AMR",
            f"Floor: {self.floor_var.get()}",
        ]
        y = 20
        for line in lines:
            self.canvas.create_text(20, y, text=line, anchor="nw", fill="white")
            y += 18

    def update_time_display(self):
        if not self.current_time:
            self.time_label_var.set("No simulation loaded")
            return
        fraction = (
            self.sim_log.time_to_fraction(self.current_time)
            if self.sim_log.start_time
            else 0.0
        )
        self.slider_var.set(fraction)
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
        self.time_label_var.set(
            f"Current: {self.current_time.strftime('%Y-%m-%d %H:%M:%S')}\nStart: {start}\nEnd: {end}"
        )

    def on_slider_change(self, _value):
        if not self.sim_log.start_time:
            return
        self.current_time = self.sim_log.fraction_to_time(self.slider_var.get())
        self.update_time_display()
        if self.follow_time_var.get():
            self.refresh_canvas()
        else:
            self.refresh_canvas()

    def on_speed_changed(self, _event=None):
        try:
            self.play_speed = float(self.speed_combo.get())
        except Exception:
            self.play_speed = 60.0

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.play_btn.config(text="Pause" if self.is_playing else "Play")
        if self.is_playing:
            self._schedule_tick()
        elif self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None

    def _schedule_tick(self):
        if not self.is_playing:
            return
        self._timer_job = self.after(100, self._tick)

    def _tick(self):
        if not self.is_playing or not self.current_time or not self.sim_log.end_time:
            return
        self.current_time += timedelta(seconds=self.play_speed * 0.1)
        if self.current_time >= self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
            self.is_playing = False
            self.play_btn.config(text="Play")
        self.update_time_display()
        self.refresh_canvas()
        if self.is_playing:
            self._schedule_tick()

    def step_seconds(self, seconds: int):
        if not self.current_time:
            return
        self.current_time += timedelta(seconds=seconds)
        if self.sim_log.start_time and self.current_time < self.sim_log.start_time:
            self.current_time = self.sim_log.start_time
        if self.sim_log.end_time and self.current_time > self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
        self.update_time_display()
        self.refresh_canvas()

    def jump_start(self):
        if self.sim_log.start_time:
            self.current_time = self.sim_log.start_time
            self.update_time_display()
            self.refresh_canvas()

    def jump_end(self):
        if self.sim_log.end_time:
            self.current_time = self.sim_log.end_time
            self.update_time_display()
            self.refresh_canvas()

    def jump_first_travel(self):
        travel_time = self.sim_log.first_travel_time()
        if travel_time is not None:
            self.current_time = travel_time
            self.update_time_display()
            self.refresh_canvas()

    def update_follow_amr_options(self):
        amr_ids = sorted(
            {
                (event.row.get("amr_id") or "").strip()
                for event in self.sim_log.events
                if (event.row.get("amr_id") or "").strip()
            }
        )
        self.follow_combo["values"] = amr_ids

        current = self.follow_amr_var.get().strip()
        if current not in amr_ids:
            self.follow_amr_var.set(amr_ids[0] if amr_ids else "")

    def open_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        self.layout_model.load(path)
        self.current_json_path = path
        floors = self.layout_model.floors()
        if floors:
            self.floor_var.set(floors[0])
        self.update_loaded_files()
        self._sync_timeline_from_layout_and_csv()
        self.refresh_canvas()
        self.set_status(f"Loaded layout {Path(path).name}")

    def open_dxf(self):
        path = filedialog.askopenfilename(filetypes=[("DXF files", "*.dxf")])
        if not path:
            return
        try:
            self.dxf_scene.load(path)
            self.current_dxf_path = path
            self.fit_view()
            self.update_loaded_files()
            self.set_status(f"Loaded DXF {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("DXF load failed", str(exc), parent=self)

    def open_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        self.sim_log.load(path)
        self.current_csv_path = path
        self.update_follow_amr_options()
        if not self.sim_log.events:
            messagebox.showerror(
                "No events", "No timestamped rows were found in the CSV.", parent=self
            )
            return
        self.update_loaded_files()
        self._sync_timeline_from_layout_and_csv()
        self.refresh_canvas()
        self.set_status(
            f"Loaded simulation CSV {Path(path).name} with {len(self.sim_log.events)} events"
        )

    def update_loaded_files(self):
        self.file_var.set(
            f"JSON: {Path(self.current_json_path).name if self.current_json_path else '-'}\n"
            f"DXF: {Path(self.current_dxf_path).name if self.current_dxf_path else '-'}\n"
            f"CSV: {Path(self.current_csv_path).name if self.current_csv_path else '-'}"
        )

    def on_left_click(self, event):
        self.last_pan = (event.x, event.y)

    def on_drag(self, event):
        if self.last_pan is None:
            self.last_pan = (event.x, event.y)
            return
        dx = event.x - self.last_pan[0]
        dy = event.y - self.last_pan[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last_pan = (event.x, event.y)
        self.refresh_canvas()

    def on_left_release(self, _event):
        self.last_pan = None

    def on_middle_click(self, event):
        self.last_pan = (event.x, event.y)

    def on_middle_drag(self, event):
        if self.last_pan is None:
            self.last_pan = (event.x, event.y)
            return
        dx = event.x - self.last_pan[0]
        dy = event.y - self.last_pan[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last_pan = (event.x, event.y)
        self.refresh_canvas()

    def on_middle_release(self, _event):
        self.last_pan = None

    def on_mousewheel(self, event):
        mouse_world_x, mouse_world_y = self.canvas_to_world(event.x, event.y)
        factor = 1.1 if event.delta > 0 else 0.9
        self.scale = max(0.2, min(60, self.scale * factor))
        self.offset_x = event.x - (mouse_world_x * self.scale)
        self.offset_y = event.y + (mouse_world_y * self.scale)
        self.refresh_canvas()

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


if __name__ == "__main__":
    app = SimulationVisualizer()
    app.mainloop()
