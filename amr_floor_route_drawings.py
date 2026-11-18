"""Aggregate saved movement legs for floor route drawings."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
import colorsys
import math
from pathlib import Path

from amr_route_analysis import CONFIRMED, MOVE_TYPES, _check, matches, recorded_segment_points
from amr_sim_payload_instances import normalise_payload_name
from visualiser.dxf_export import configured_floors


Point = tuple[float, float]
Category = tuple[str, str]
EMPTY_AMR = ('empty', 'Empty AMR')
MIXED_PAYLOAD = ('mixed', 'Mixed payload')
PALETTE = (
    '#0072B2', '#B44A00', '#00835E', '#A63D82', '#6C51A5', '#89630B',
    '#008496', '#BC3441', '#576C23', '#365CA4', '#8A4F36', '#343B4D',
)


@dataclass
class FloorDrawing:
    floor: int
    confirmed: Counter = field(default_factory=Counter)
    planned: Counter = field(default_factory=Counter)
    gaps: int = 0
    gap_points: set[Point] = field(default_factory=set)
    landings: set[Point] = field(default_factory=set)
    chains: list = field(default_factory=list)

    @property
    def total(self):
        return self.confirmed.total() + self.planned.total()


def drawing_run_name(run):
    source = Path(run.source)
    folder = source.parent.name
    if folder.casefold().startswith('run_'):
        return folder
    return run.metadata.get('run_id') or source.name


def payload_category(segments):
    payloads = {normalise_payload_name(segment.payload) for segment in segments} - {''}
    if len(payloads) == 1:
        return ('payload', next(iter(payloads)))
    return MIXED_PAYLOAD if payloads else EMPTY_AMR


def category_colours(run):
    names = {normalise_payload_name(entry.get('name')) for entry in run.config.get('payloads', [])}
    names.update(normalise_payload_name(segment.payload) for leg in run.legs
                 for segment in leg.segments if segment.kind in MOVE_TYPES)
    names.discard('')
    colours = {EMPTY_AMR: '#606A76', MIXED_PAYLOAD: '#332B35'}
    for index, name in enumerate(sorted(names, key=lambda value: (value.casefold(), value))):
        if index < len(PALETTE):
            colour = PALETTE[index]
        else:
            rgb = colorsys.hls_to_rgb((index * 0.618033989) % 1, 0.32 + 0.14 * (index % 2), 0.72)
            colour = '#' + ''.join(f'{round(channel * 255):02X}' for channel in rgb)
        colours['payload', name] = colour
    return colours


def _point(x, y):
    if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
        return None
    return round(x, 6), round(y, 6)


def _floor(value):
    return int(value) if value is not None and math.isfinite(value) and int(value) == value else None


def _floor_movements(run, segments):
    """Yield floor, path, missing-geometry endpoints, and any lift landing."""
    for segment in segments:
        start, end = _floor(segment.start[2]), _floor(segment.finish[2])
        if segment.kind == 'lift_transfer':
            for floor, location, key in ((start, segment.start, 'entry_edge'),
                                         (end, segment.finish, 'exit_edge')):
                connector = segment.detail.get(key) or {}
                landing = _point(*location[:2])
                if connector:
                    nodes = [run.points.get(connector.get(side), {}) for side in ('from', 'to')]
                    # Some older records can identify the floor from the saved connector alone.
                    if floor is None and nodes[0].get('floor') == nodes[1].get('floor'):
                        floor = _floor(nodes[0].get('floor'))
                    points = [_point(node.get('x'), node.get('y')) for node in nodes]
                    if floor is not None and all(point and node.get('floor') == floor
                                                 for point, node in zip(points, nodes)):
                        yield floor, points, None, landing
                        continue
                    yield floor, (), (landing,), landing
                else:
                    yield floor, (), None if landing else (), landing
            continue
        if start == end and start is not None:
            points = [_point(x, y) for x, y in recorded_segment_points(segment)]
            if len(points) >= 2 and all(point is not None for point in points) and len(set(points)) > 1:
                yield start, points, None, None
                continue
        if segment.origin != segment.destination or segment.distance or segment.trajectory:
            yield start, (), (_point(*segment.start[:2]),), None
            yield end, (), (_point(*segment.finish[:2]),), None


def build_floor_drawings(run, filters, *, include_plans=False, cancel=None):
    """Return floor drawings and the number of legs with an unassigned floor."""
    end = min(run.duration, filters.end) if filters.end is not None else run.duration
    if not math.isfinite(filters.start) or not math.isfinite(end) or not 0 <= filters.start < end:
        raise ValueError('Select a nonempty elapsed-time window within the run.')
    filters = replace(filters, evidence='')
    floors = set(configured_floors(run.config)) | run.drawings.keys() | run.pdf_drawings.keys()
    if filters.floor is not None:
        floors = {int(filters.floor)}
    drawings = {floor: FloorDrawing(floor) for floor in floors}
    edges_by_floor = defaultdict(dict)
    unassigned = 0
    for leg in run.legs:
        _check(cancel)
        confirmed = leg.evidence == CONFIRMED
        # The drawing dialog owns the evidence selection. All other applied
        # filters, including the common time window, come from the analysis.
        if not confirmed and not include_plans or leg.time is None or not filters.start <= leg.time < end:
            continue
        if not matches(leg, filters):
            continue
        segments = [segment for segment in leg.segments if segment.kind in MOVE_TYPES]
        category = payload_category(segments)
        visited, gaps = set(), set()
        for floor, path, gap, landing in _floor_movements(run, segments):
            if floor is None:
                gaps.add(None)
                continue
            if filters.floor is not None and floor != filters.floor:
                continue
            visited.add(floor)
            if floor not in drawings:
                drawings[floor] = FloorDrawing(floor)
            drawing = drawings[floor]
            if gap is not None:
                gaps.add(floor)
                drawing.gap_points.update(point for point in gap if point is not None)
            if landing is not None:
                drawing.landings.add(landing)
            for first, last in zip(path, path[1:]):
                if first != last:
                    edge = (first, last) if first < last else (last, first)
                    by_category = edges_by_floor[floor].setdefault(edge, {})
                    by_category[category] = by_category.get(category, False) or confirmed
        for floor in visited:
            drawing = drawings[floor]
            (drawing.confirmed if confirmed else drawing.planned)[category] += 1
            drawing.gaps += floor in gaps
        unassigned += None in gaps or (not visited and filters.floor is None)
    for floor, edges in sorted(edges_by_floor.items()):
        drawings[floor].chains = _route_chains(_split_overlaps(edges, cancel), cancel)
    return [drawings[floor] for floor in sorted(drawings)], unassigned


def _split_overlaps(edges, cancel):
    """Split collinear overlaps at recorded endpoints, including reversed traversals."""
    lines = defaultdict(list)
    for (a, b), styles in edges.items():
        _check(cancel)
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        ux, uy = math.cos(angle), math.sin(angle)
        line = round(angle, 7), round(a[1] * ux - a[0] * uy, 4)
        lines[line].append((a, b, styles))
    for (angle, _offset), members in lines.items():
        _check(cancel)
        if len(members) == 1:
            a, b, styles = members[0]
            yield a, b, tuple(sorted(styles.items()))
            continue
        ux, uy = math.cos(angle), math.sin(angle)
        events = defaultdict(Counter)
        points = {}
        for a, b, styles in members:
            start, end = (round(x * ux + y * uy, 6) for x, y in (a, b))
            if start >= end:
                continue
            points[start], points[end] = a, b
            events[start].update(styles.items())
            events[end].subtract(styles.items())
        active = Counter()
        previous = None
        for at in sorted(events):
            if active:
                categories = {category for category, _ in active}
                styles = tuple((category, (category, True) in active) for category in sorted(categories))
                yield points[previous], points[at], styles
            active.update(events[at])
            active = +active
            previous = at


def _route_chains(spans, cancel):
    """Join adjacent spans with identical payload lines before applying offsets."""
    neighbours = defaultdict(list)
    edges = list(spans)
    for index, (a, b, _styles) in enumerate(edges):
        neighbours[a].append(index)
        neighbours[b].append(index)

    def continuation(point, index, styles):
        links = neighbours[point]
        if len(links) == 2:
            other = links[1] if links[0] == index else links[0]
            if edges[other][2] == styles:
                return other
        return None

    used = set()
    chains = []
    starts = []
    loops = []
    for index, (a, b, styles) in enumerate(edges):
        if continuation(a, index, styles) is None:
            starts.append((index, a))
        elif continuation(b, index, styles) is None:
            starts.append((index, b))
        else:
            loops.append((index, a))
    for index, start in starts + loops:
        _check(cancel)
        if index in used:
            continue
        styles = edges[index][2]
        points = [start]
        while index is not None and index not in used:
            used.add(index)
            a, b, _styles = edges[index]
            target = b if points[-1] == a else a
            points.append(target)
            index = continuation(target, index, styles)
        if points[-1] < points[0]:
            points.reverse()
        chains.append((points, styles))
    return chains


def _offset_paths(points, count, pitch):
    if count == 1:
        yield points
        return
    closed = points[0] == points[-1]
    distance = [0.0]
    for a, b in zip(points, points[1:]):
        distance.append(distance[-1] + math.dist(a, b))
    length = distance[-1]
    taper = min(length * 0.22, max(1.5, count * 0.6) * pitch)
    if not closed:
        # Add taper breakpoints even when the shared corridor is one straight span.
        marks = sorted(set(distance + [taper, length - taper]))
        vertices = []
        index = 0
        for mark in marks:
            while distance[index + 1] < mark:
                index += 1
            amount = (mark - distance[index]) / (distance[index + 1] - distance[index])
            a, b = points[index:index + 2]
            vertices.append(tuple(start + (finish - start) * amount for start, finish in zip(a, b)))
        distance, points = marks, vertices
    normals = []
    for a, b in zip(points, points[1:]):
        span = math.dist(a, b)
        normals.append((-(b[1] - a[1]) / span, (b[0] - a[0]) / span))
    shifts = []
    for index, at in enumerate(distance):
        before = normals[index - 1] if index or closed else normals[0]
        after = normals[index] if index < len(normals) else normals[0] if closed else normals[-1]
        denominator = max(0.5, 1 + before[0] * after[0] + before[1] * after[1])
        factor = 1 if closed else min(at / taper, (length - at) / taper, 1)
        shifts.append(tuple((a + b) * factor / denominator for a, b in zip(before, after)))
    for lane in range(count):
        offset = (lane - (count - 1) / 2) * pitch
        yield [(x + dx * offset, y + dy * offset) for (x, y), (dx, dy) in zip(points, shifts)]


def category_paths(drawing, pitch):
    """Yield category, confirmation style and diagrammatic polyline for both formats."""
    for points, styles in drawing.chains:
        for (category, confirmed), path in zip(styles, _offset_paths(points, len(styles), pitch)):
            yield category, confirmed, path
