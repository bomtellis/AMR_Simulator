"""Export editor-owned floor geometry to standalone DXF drawings.

Mapped DXF files and PDF underlays are deliberately not read here. The JSON
model stores editable geometry in the same metre-based world coordinate system
as those backgrounds, so model coordinates preserve alignment without copying
the background artwork.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple

try:
    import ezdxf
except Exception:  # pragma: no cover - exercised by the editor error path
    ezdxf = None


LAYER_SPECS = {
    "AMR_CORRIDORS": 5,
    "AMR_CORRIDOR_NODES": 2,
    "AMR_DOOR_NODES": 30,
    "AMR_LOCATIONS": 3,
    "AMR_DEPARTMENTS": 4,
    "AMR_LIFTS": 1,
    "AMR_LOCATION_BOUNDS": 4,
    "AMR_INVENTORY_SPACES": 6,
    "AMR_INVENTORY_SLOTS": 140,
    "AMR_LABELS": 7,
}

# Display label: ($INSUNITS value, drawing units per editor metre).
DXF_UNIT_SPECS = {
    "Metres": (6, 1.0),
    "Millimetres": (4, 1000.0),
    "Centimetres": (5, 100.0),
    "Feet": (2, 1.0 / 0.3048),
    "Inches": (1, 1.0 / 0.0254),
}


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_floor(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _add_label(
    modelspace,
    text: str,
    x_metres: float,
    y_metres: float,
    height_metres: float = 0.25,
    units_per_metre: float = 1.0,
):
    text = str(text or "").strip()
    if not text:
        return
    modelspace.add_text(
        text,
        height=height_metres * units_per_metre,
        dxfattribs={
            "layer": "AMR_LABELS",
            "insert": (
                (x_metres + 0.45) * units_per_metre,
                (y_metres + 0.10) * units_per_metre,
            ),
        },
    )


def _add_closed_polyline(
    modelspace,
    points: Iterable[Tuple[float, float]],
    layer: str,
):
    vertices = [(float(x), float(y)) for x, y in points]
    if len(vertices) >= 3:
        modelspace.add_lwpolyline(vertices, close=True, dxfattribs={"layer": layer})
        return True
    return False


def _point_index(data: Mapping) -> Dict[str, dict]:
    """Return route-capable points only (departments cannot own edges)."""
    points: Dict[str, dict] = {}
    for location in data.get("locations", []) or []:
        if isinstance(location, dict) and str(location.get("name", "")).strip():
            points[str(location["name"])] = location
    for node in (data.get("corridors", {}) or {}).get("nodes", []) or []:
        if isinstance(node, dict) and str(node.get("name", "")).strip():
            points[str(node["name"])] = node
    for lift in data.get("lifts", []) or []:
        if not isinstance(lift, dict):
            continue
        lift_id = str(lift.get("id", "") or "").strip()
        for floor_text, position in (lift.get("floor_locations", {}) or {}).items():
            floor = _as_floor(floor_text)
            if not lift_id or floor is None or not isinstance(position, dict):
                continue
            name = f"{lift_id}-F{floor_text}"
            points[name] = {
                "name": name,
                "floor": floor,
                "x": position.get("x", 0.0),
                "y": position.get("y", 0.0),
            }
    return points


def configured_floors(data: Mapping) -> list[int]:
    """Return every floor represented by geometry or a configured underlay."""
    floors = set()
    for collection in (
        data.get("locations", []) or [],
        (data.get("corridors", {}) or {}).get("nodes", []) or [],
        data.get("departments", []) or [],
        data.get("floor_dxf_files", []) or [],
        data.get("floor_pdf_underlays", []) or [],
    ):
        for item in collection:
            if not isinstance(item, dict):
                continue
            floor = _as_floor(item.get("floor"))
            if floor is not None:
                floors.add(floor)
    for lift in data.get("lifts", []) or []:
        if not isinstance(lift, dict):
            continue
        for floor_text in (lift.get("floor_locations", {}) or {}):
            floor = _as_floor(floor_text)
            if floor is not None:
                floors.add(floor)
    return sorted(floors)


def export_floor_to_dxf(
    data: Mapping,
    floor: int,
    path,
    units: str = "Metres",
) -> dict:
    """Write editable geometry for one floor and return entity counts.

    Editor coordinates are converted from metres to ``units``. Background
    mapping keys are never consulted for entity content.
    """
    if ezdxf is None:
        raise RuntimeError("ezdxf is not installed. Install with: pip install ezdxf")
    if units not in DXF_UNIT_SPECS:
        raise ValueError(
            f"Unsupported DXF units: {units}. Choose one of: "
            f"{', '.join(DXF_UNIT_SPECS)}"
        )

    floor = int(floor)
    output_path = Path(path)
    insunits, units_per_metre = DXF_UNIT_SPECS[units]

    def xy(x, y):
        return (_as_float(x) * units_per_metre, _as_float(y) * units_per_metre)

    def scaled_points(points):
        return [xy(x, y) for x, y in points]

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = insunits
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    for layer_name, colour in LAYER_SPECS.items():
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=colour)

    modelspace = doc.modelspace()
    counts = {
        "edges": 0,
        "corridor_nodes": 0,
        "locations": 0,
        "departments": 0,
        "lifts": 0,
        "location_bounds": 0,
        "inventory_spaces": 0,
        "inventory_slots": 0,
    }

    points = _point_index(data)
    seen_edges = set()
    for edge in (data.get("corridors", {}) or {}).get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        from_name = str(edge.get("from", "") or "").strip()
        to_name = str(edge.get("to", "") or "").strip()
        start, end = points.get(from_name), points.get(to_name)
        if not start or not end:
            continue
        if _as_floor(start.get("floor")) != floor or _as_floor(end.get("floor")) != floor:
            continue
        physical_key = tuple(sorted((from_name, to_name)))
        if physical_key in seen_edges:
            continue
        seen_edges.add(physical_key)
        modelspace.add_line(
            xy(start.get("x"), start.get("y")),
            xy(end.get("x"), end.get("y")),
            dxfattribs={"layer": "AMR_CORRIDORS"},
        )
        counts["edges"] += 1

    for node in (data.get("corridors", {}) or {}).get("nodes", []) or []:
        if not isinstance(node, dict) or _as_floor(node.get("floor")) != floor:
            continue
        x, y = _as_float(node.get("x")), _as_float(node.get("y"))
        layer = (
            "AMR_DOOR_NODES"
            if bool(node.get("has_door", False))
            else "AMR_CORRIDOR_NODES"
        )
        half_size = 0.30
        _add_closed_polyline(
            modelspace,
            scaled_points(
                [
                    (x - half_size, y - half_size),
                    (x + half_size, y - half_size),
                    (x + half_size, y + half_size),
                    (x - half_size, y + half_size),
                ]
            ),
            layer,
        )
        _add_label(
            modelspace,
            node.get("name", ""),
            x,
            y,
            units_per_metre=units_per_metre,
        )
        counts["corridor_nodes"] += 1

    for location in data.get("locations", []) or []:
        if not isinstance(location, dict) or _as_floor(location.get("floor")) != floor:
            continue
        name = str(location.get("name", "") or "").strip()
        x, y = _as_float(location.get("x")), _as_float(location.get("y"))
        modelspace.add_circle(
            xy(x, y),
            radius=0.30 * units_per_metre,
            dxfattribs={"layer": "AMR_LOCATIONS"},
        )
        _add_label(modelspace, name, x, y, units_per_metre=units_per_metre)
        counts["locations"] += 1

        boundary = []
        for point in location.get("bounding_box", []) or []:
            if not isinstance(point, dict):
                continue
            if "dx" in point and "dy" in point:
                boundary.append(
                    (x + _as_float(point.get("dx")), y + _as_float(point.get("dy")))
                )
            elif "x" in point and "y" in point:
                boundary.append((_as_float(point.get("x")), _as_float(point.get("y"))))
        if _add_closed_polyline(
            modelspace,
            scaled_points(boundary),
            "AMR_LOCATION_BOUNDS",
        ):
            counts["location_bounds"] += 1

        for space in location.get("inventory_spaces", []) or []:
            if not isinstance(space, dict):
                continue
            vertices = []
            for point in space.get("points", []) or []:
                if not isinstance(point, dict):
                    continue
                if "dx" in point and "dy" in point:
                    vertices.append(
                        (x + _as_float(point.get("dx")), y + _as_float(point.get("dy")))
                    )
                elif "x" in point and "y" in point:
                    vertices.append((_as_float(point.get("x")), _as_float(point.get("y"))))
            if _add_closed_polyline(
                modelspace,
                scaled_points(vertices),
                "AMR_INVENTORY_SPACES",
            ):
                counts["inventory_spaces"] += 1
                _add_label(
                    modelspace,
                    space.get("name", ""),
                    min(point[0] for point in vertices),
                    min(point[1] for point in vertices),
                    height_metres=0.18,
                    units_per_metre=units_per_metre,
                )

            for slot in space.get("payload_slots", []) or []:
                if not isinstance(slot, dict):
                    continue
                if "dx" in slot and "dy" in slot:
                    slot_x = x + _as_float(slot.get("dx"))
                    slot_y = y + _as_float(slot.get("dy"))
                elif "x" in slot and "y" in slot:
                    slot_x = _as_float(slot.get("x"))
                    slot_y = _as_float(slot.get("y"))
                else:
                    continue
                modelspace.add_circle(
                    xy(slot_x, slot_y),
                    radius=0.10 * units_per_metre,
                    dxfattribs={"layer": "AMR_INVENTORY_SLOTS"},
                )
                _add_label(
                    modelspace,
                    slot.get("amr_type", slot.get("payload", "")),
                    slot_x,
                    slot_y,
                    height_metres=0.15,
                    units_per_metre=units_per_metre,
                )
                counts["inventory_slots"] += 1

    for department in data.get("departments", []) or []:
        if not isinstance(department, dict) or _as_floor(department.get("floor", 0)) != floor:
            continue
        name = str(department.get("name", "") or "").strip()
        if not name:
            continue
        x, y = _as_float(department.get("x")), _as_float(department.get("y"))
        half_size = 0.90
        _add_closed_polyline(
            modelspace,
            scaled_points(
                [
                    (x, y + half_size),
                    (x + half_size, y),
                    (x, y - half_size),
                    (x - half_size, y),
                ]
            ),
            "AMR_DEPARTMENTS",
        )
        _add_label(modelspace, name, x, y, units_per_metre=units_per_metre)
        counts["departments"] += 1

    for lift in data.get("lifts", []) or []:
        if not isinstance(lift, dict):
            continue
        lift_id = str(lift.get("id", "") or "").strip()
        position = (lift.get("floor_locations", {}) or {}).get(str(floor))
        if not lift_id or not isinstance(position, dict):
            continue
        x, y = _as_float(position.get("x")), _as_float(position.get("y"))
        half_size = 0.30
        _add_closed_polyline(
            modelspace,
            scaled_points(
                [
                    (x, y + half_size),
                    (x + half_size, y),
                    (x, y - half_size),
                    (x - half_size, y),
                ]
            ),
            "AMR_LIFTS",
        )
        _add_label(
            modelspace,
            f"{lift_id}-F{floor}",
            x,
            y,
            units_per_metre=units_per_metre,
        )
        counts["lifts"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    counts["total"] = sum(counts.values())
    counts["units"] = units
    return counts


def all_floor_output_paths(data: Mapping, base_path) -> list[tuple[int, int, Path]]:
    """Return ``(sequence, floor, path)`` entries for an all-floor export."""
    floors = configured_floors(data)
    if not floors:
        raise ValueError("There are no configured floors to export")

    base_path = Path(base_path)
    stem = base_path.stem if base_path.suffix else base_path.name
    digits = max(3, len(str(len(floors))))
    return [
        (
            sequence,
            floor,
            base_path.with_name(f"{stem}_{sequence:0{digits}d}_F{floor}.dxf"),
        )
        for sequence, floor in enumerate(floors, start=1)
    ]


def export_all_floors_to_dxf(
    data: Mapping,
    base_path,
    units: str = "Metres",
) -> list[dict]:
    """Export configured floors to sequentially numbered standalone files."""
    results = []
    for sequence, floor, output_path in all_floor_output_paths(data, base_path):
        counts = export_floor_to_dxf(data, floor, output_path, units=units)
        results.append(
            {
                "sequence": sequence,
                "floor": floor,
                "path": output_path,
                **counts,
            }
        )
    return results
