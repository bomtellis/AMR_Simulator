"""Graph-route geometry used by drop-off-zone staff animation."""

from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Tuple


def _point_distance(a: dict, b: dict, floor_height_m: float = 4.0) -> float:
    horizontal = math.hypot(
        float(b.get("x", 0.0)) - float(a.get("x", 0.0)),
        float(b.get("y", 0.0)) - float(a.get("y", 0.0)),
    )
    vertical = abs(int(b.get("floor", 0)) - int(a.get("floor", 0))) * max(
        0.1, float(floor_height_m or 4.0)
    )
    return math.hypot(horizontal, vertical)


def shortest_staff_route_points(
    layout_data: dict,
    points: Dict[str, dict],
    start_name: str,
    end_name: str,
    preferred_lift_id: str = "",
) -> List[dict]:
    """Return graph points for a staff route, or an empty list if disconnected."""
    start_name = str(start_name or "").strip()
    end_name = str(end_name or "").strip()
    preferred_lift_id = str(preferred_lift_id or "").strip()
    if start_name not in points or end_name not in points:
        return []
    if start_name == end_name:
        return [dict(points[start_name])]

    adjacency: Dict[str, List[Tuple[str, float]]] = {
        name: [] for name in points
    }
    undirected_degree = {name: 0 for name in points}

    def add_edge(a_name: str, b_name: str, weight: Optional[float] = None) -> None:
        if a_name not in points or b_name not in points:
            return
        if weight is None:
            weight = _point_distance(points[a_name], points[b_name])
        adjacency[a_name].append((b_name, max(1e-6, float(weight))))
        undirected_degree[a_name] += 1
        undirected_degree[b_name] += 1

    corridor_cfg = layout_data.get("corridors", {}) or {}
    for edge in corridor_cfg.get("edges", []) or []:
        a_name = str(edge.get("from", "") or "").strip()
        b_name = str(edge.get("to", "") or "").strip()
        if a_name not in points or b_name not in points:
            continue
        configured_distance = edge.get("distance_m")
        try:
            distance = (
                float(configured_distance)
                if configured_distance is not None
                else _point_distance(points[a_name], points[b_name])
            )
        except Exception:
            distance = _point_distance(points[a_name], points[b_name])
        add_edge(a_name, b_name, distance)
        if bool(edge.get("bidirectional", True)):
            add_edge(b_name, a_name, distance)

    # Match the simulator's optional connection of otherwise isolated locations
    # and lift landings to the nearest corridor node on their floor.
    if bool(corridor_cfg.get("auto_connect", True)):
        corridor_names_by_floor: Dict[int, List[str]] = {}
        for node in corridor_cfg.get("nodes", []) or []:
            name = str(node.get("name", "") or "").strip()
            if name in points:
                corridor_names_by_floor.setdefault(
                    int(points[name].get("floor", 0)), []
                ).append(name)
        corridor_name_set = {
            name for names in corridor_names_by_floor.values() for name in names
        }
        for name, point in points.items():
            if name in corridor_name_set:
                continue
            if undirected_degree.get(name, 0) > 0:
                continue
            candidates = corridor_names_by_floor.get(int(point.get("floor", 0)), [])
            if not candidates:
                continue
            nearest = min(
                candidates,
                key=lambda candidate: _point_distance(point, points[candidate]),
            )
            distance = _point_distance(point, points[nearest])
            add_edge(name, nearest, distance)
            add_edge(nearest, name, distance)

    # Staff lift events record the lift selected by the simulator. Restrict
    # vertical graph links to that lift when present so animation follows the
    # same route rather than choosing a visually shorter alternative.
    for lift in layout_data.get("lifts", []) or []:
        lift_id = str(lift.get("id", "") or "").strip()
        if preferred_lift_id and lift_id != preferred_lift_id:
            continue
        floor_names = []
        for floor in sorted(int(value) for value in (lift.get("served_floors", []) or [])):
            name = f"{lift_id}-F{floor}"
            if name in points:
                floor_names.append(name)
        for a_name, b_name in zip(floor_names, floor_names[1:]):
            distance = _point_distance(points[a_name], points[b_name])
            add_edge(a_name, b_name, distance)
            add_edge(b_name, a_name, distance)

    distances = {start_name: 0.0}
    previous: Dict[str, str] = {}
    queue = [(0.0, start_name)]
    while queue:
        distance, name = heapq.heappop(queue)
        if distance > distances.get(name, math.inf) + 1e-9:
            continue
        if name == end_name:
            break
        for neighbour, weight in adjacency.get(name, []):
            candidate = distance + weight
            if candidate + 1e-9 >= distances.get(neighbour, math.inf):
                continue
            distances[neighbour] = candidate
            previous[neighbour] = name
            heapq.heappush(queue, (candidate, neighbour))

    if end_name not in distances:
        return []
    names = [end_name]
    while names[-1] != start_name:
        names.append(previous[names[-1]])
    names.reverse()
    return [dict(points[name]) for name in names]


def interpolate_staff_route(
    route_points: List[dict],
    fraction: float,
    floor_height_m: float = 4.0,
) -> Optional[dict]:
    """Interpolate by route distance and return position plus travel tangent."""
    if not route_points:
        return None
    if len(route_points) == 1:
        point = route_points[0]
        return {
            "x": float(point.get("x", 0.0)),
            "y": float(point.get("y", 0.0)),
            "floor": int(point.get("floor", 0)),
            "heading_dx": 1.0,
            "heading_dy": 0.0,
        }

    fraction = max(0.0, min(1.0, float(fraction or 0.0)))
    lengths = [
        _point_distance(a, b, floor_height_m)
        for a, b in zip(route_points, route_points[1:])
    ]
    total = sum(lengths)
    if total <= 1e-9:
        point = route_points[-1]
        return {
            "x": float(point.get("x", 0.0)),
            "y": float(point.get("y", 0.0)),
            "floor": int(point.get("floor", 0)),
            "heading_dx": 1.0,
            "heading_dy": 0.0,
        }

    target = total * fraction
    traversed = 0.0
    segment_index = len(lengths) - 1
    segment_fraction = 1.0
    for index, length in enumerate(lengths):
        if target <= traversed + length + 1e-9:
            segment_index = index
            segment_fraction = (
                1.0 if length <= 1e-9 else (target - traversed) / length
            )
            break
        traversed += length

    a = route_points[segment_index]
    b = route_points[segment_index + 1]
    ax, ay = float(a.get("x", 0.0)), float(a.get("y", 0.0))
    bx, by = float(b.get("x", 0.0)), float(b.get("y", 0.0))
    dx, dy = bx - ax, by - ay
    heading_length = math.hypot(dx, dy)
    if heading_length <= 1e-9:
        # A lift segment has no plan-view tangent. Use the nearest horizontal
        # segment so the payload retains a stable orientation in the lift.
        for neighbour_index in range(segment_index - 1, -1, -1):
            before, after = route_points[neighbour_index:neighbour_index + 2]
            dx = float(after.get("x", 0.0)) - float(before.get("x", 0.0))
            dy = float(after.get("y", 0.0)) - float(before.get("y", 0.0))
            if math.hypot(dx, dy) > 1e-9:
                break
        if math.hypot(dx, dy) <= 1e-9:
            for neighbour_index in range(segment_index + 1, len(route_points) - 1):
                before, after = route_points[neighbour_index:neighbour_index + 2]
                dx = float(after.get("x", 0.0)) - float(before.get("x", 0.0))
                dy = float(after.get("y", 0.0)) - float(before.get("y", 0.0))
                if math.hypot(dx, dy) > 1e-9:
                    break
    heading_length = max(math.hypot(dx, dy), 1e-9)
    start_floor = int(a.get("floor", 0))
    end_floor = int(b.get("floor", start_floor))
    floor = start_floor if segment_fraction < 0.5 else end_floor
    return {
        "x": ax + ((bx - ax) * segment_fraction),
        "y": ay + ((by - ay) * segment_fraction),
        "floor": floor,
        "heading_dx": dx / heading_length,
        "heading_dy": dy / heading_length,
    }


def person_position_behind_payload(
    payload_x: float,
    payload_y: float,
    heading_dx: float,
    heading_dy: float,
    payload_length_m: float,
    clearance_m: float = 0.30,
) -> Tuple[float, float]:
    """Position a person behind the rear face of a direction-aligned payload."""
    length = max(math.hypot(heading_dx, heading_dy), 1e-9)
    unit_x, unit_y = heading_dx / length, heading_dy / length
    offset = max(0.45, (max(0.0, float(payload_length_m)) / 2.0) + clearance_m)
    return payload_x - (unit_x * offset), payload_y - (unit_y * offset)
