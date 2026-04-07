import math
from typing import List, Tuple

try:
    import ezdxf
except Exception:  # pragma: no cover
    ezdxf = None


class DXFScene:
    def __init__(self):
        self.path = None
        self.entities = []
        self.bounds = None

    @staticmethod
    def _model_text_pixel_height(world_to_canvas, insert, model_height):
        x1, y1 = world_to_canvas(insert[0], insert[1])
        x2, y2 = world_to_canvas(insert[0], insert[1] + model_height)
        return max(1, int(abs(y2 - y1)))

    def clear(self):
        self.path = None
        self.entities = []
        self.bounds = None

    def load(self, path: str):
        if ezdxf is None:
            raise RuntimeError(
                "ezdxf is not installed. Install with: pip install ezdxf"
            )

        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        self.clear()
        self.path = path

        xs = []
        ys = []

        def add_point(x, y):
            xs.append(float(x))
            ys.append(float(y))

        def add_line(start, end):
            add_point(start[0], start[1])
            add_point(end[0], end[1])
            self.entities.append(
                {
                    "type": "LINE",
                    "start": (float(start[0]), float(start[1])),
                    "end": (float(end[0]), float(end[1])),
                }
            )

        def add_polyline(points, closed=False):
            if len(points) < 2:
                return
            clean = []
            for x, y in points:
                add_point(x, y)
                clean.append((float(x), float(y)))
            self.entities.append(
                {
                    "type": "POLYLINE",
                    "points": clean,
                    "closed": bool(closed),
                }
            )

        def add_text_entity(insert, text, height=2.5, rotation=0.0):
            x = float(insert[0])
            y = float(insert[1])
            add_point(x, y)
            self.entities.append(
                {
                    "type": "TEXT",
                    "insert": (x, y),
                    "text": str(text),
                    "height": float(height or 2.5),
                    "rotation": float(rotation or 0.0),
                }
            )

        def add_circle(center, radius):
            cx = float(center[0])
            cy = float(center[1])
            r = float(radius)
            add_point(cx - r, cy - r)
            add_point(cx + r, cy + r)
            self.entities.append(
                {
                    "type": "CIRCLE",
                    "center": (cx, cy),
                    "radius": r,
                }
            )

        def add_arc(center, radius, start_angle, end_angle):
            cx = float(center[0])
            cy = float(center[1])
            r = float(radius)
            add_point(cx - r, cy - r)
            add_point(cx + r, cy + r)
            self.entities.append(
                {
                    "type": "ARC",
                    "center": (cx, cy),
                    "radius": r,
                    "start_angle": float(start_angle),
                    "end_angle": float(end_angle),
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
                            x = float(vx[0])
                            y = float(vx[1])
                            points.append((x, y))
                    elif hasattr(path, "edges"):
                        for edge in path.edges:
                            edge_type = getattr(edge, "type", None)
                            if edge_type == "LineEdge":
                                points.append(
                                    (float(edge.start[0]), float(edge.start[1]))
                                )
                                points.append((float(edge.end[0]), float(edge.end[1])))
                            elif edge_type == "ArcEdge":
                                cx, cy = float(edge.center[0]), float(edge.center[1])
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

        if xs and ys:
            self.bounds = (min(xs), min(ys), max(xs), max(ys))
        else:
            self.bounds = (0.0, 0.0, 100.0, 100.0)

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

    def draw(self, canvas, world_to_canvas):
        for entity in self.entities:
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
                    canvas.create_line(*pts, fill="#f7f7f7")
                    if entity.get("closed"):
                        canvas.create_line(
                            pts[-2], pts[-1], pts[0], pts[1], fill="#f7f7f7"
                        )
            elif etype == "CIRCLE":
                cx, cy = world_to_canvas(*entity["center"])
                rx = entity["radius"]
                ex, _ = world_to_canvas(entity["center"][0] + rx, entity["center"][1])
                r = abs(ex - cx)
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#cdcdcd")
            elif etype == "ARC":
                cx, cy = world_to_canvas(*entity["center"])
                rx = entity["radius"]
                ex, _ = world_to_canvas(entity["center"][0] + rx, entity["center"][1])
                r = abs(ex - cx)
                canvas.create_arc(
                    cx - r,
                    cy - r,
                    cx + r,
                    cy + r,
                    start=-entity["end_angle"],
                    extent=entity["end_angle"] - entity["start_angle"],
                    style="arc",
                    outline="#cdcdcd",
                )
            elif etype == "TEXT":
                x, y = world_to_canvas(*entity["insert"])
                # model_height = float(entity.get("height", 2.5) or 2.5)
                model_height = 0.5
                size = self._model_text_pixel_height(
                    world_to_canvas, entity["insert"], model_height
                )
                text = entity.get("text", "")
                canvas.create_text(
                    x,
                    y,
                    text=text,
                    anchor="sw",
                    fill="#ffffff",
                    angle=-entity.get("rotation", 0.0),
                    font=("Arial", size),
                )
