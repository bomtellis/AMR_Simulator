"""Stationary geometric occupancy and stopping eligibility, in metres/seconds.

This module does not invent retreat paths or prove traffic deadlocks. Passing
place candidates must include a pose and a distance from a route planner which
has already established reachability (including permitted reversing).

Optional floor areas use ``[{"id": "P1", "bounds": [xmin,ymin,xmax,ymax]}]``.
Automatic door/junction protection is a conservative square at a graph point,
with side equal to its largest explicit incident corridor/opening width. It
protects the local node core, not every possible curved junction approach;
explicit no-queuing areas extend protection for such approaches. No width is
invented when the graph and explicit building defaults supply none.
"""
import math

from amr_trajectories import EPS, Pose, TrajectoryError, footprint
from amr_geometric_traffic import polygon_bounds, polygons_overlap


def _number(value, name, *, positive=False):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise TrajectoryError('invalid_input', f'{name} must be a finite '
                              f'{"positive" if positive else "nonnegative"} number.')
    return float(value)


def _bounds(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and abs(v) < 1e8 for v in value)
            and value[0] < value[2] and value[1] < value[3])


def _polygon(bounds):
    x0, y0, x1, y1 = bounds
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _pose(pose):
    if not isinstance(pose, Pose) or any(not isinstance(v, (int, float))
            or isinstance(v, bool) or not math.isfinite(v)
            for v in (pose.x, pose.y, pose.heading)):
        raise TrajectoryError('invalid_input', 'A finite Pose is required.')
    return pose


def _within(polygon, bounds):
    x0, y0, x1, y1 = bounds
    return all(x0-EPS <= x <= x1+EPS and y0-EPS <= y <= y1+EPS
               for x, y in polygon)


def area_input_findings(floor, path='/geometry/floors/0'):
    """Return path/message validation findings; absent optional arrays are valid."""
    findings = []
    if not isinstance(floor, dict):
        return [(path, 'A floor must be an object.')]
    for key in ('no_queuing_areas', 'passing_places'):
        areas = floor.get(key, [])
        if not isinstance(areas, list):
            findings.append((path+'/'+key, 'Expected an optional list of drawn areas.'))
            continue
        seen = set()
        for index, area in enumerate(areas):
            here = f'{path}/{key}/{index}'
            if not isinstance(area, dict):
                findings.append((here, 'A drawn area needs an id and rectangular bounds.'))
                continue
            identity = area.get('id')
            if not isinstance(identity, str) or not identity.strip() or identity in seen:
                findings.append((here+'/id', 'Area ids must be nonempty, unique strings within their kind.'))
            else:
                seen.add(identity)
            if not _bounds(area.get('bounds')):
                findings.append((here+'/bounds', 'Use ordered finite xmin/ymin/xmax/ymax bounds in metres.'))
            elif _bounds(floor.get('bounds')) and not _within(_polygon(area['bounds']), floor['bounds']):
                findings.append((here+'/bounds', 'The drawn area must lie within its modelled floor bounds.'))
    return findings


def _validate_floor(floor):
    findings = area_input_findings(floor)
    if not isinstance(floor, dict) or not _bounds(floor.get('bounds')):
        findings.append(('/geometry/floors/bounds', 'Explicit ordered floor bounds are required.'))
    if isinstance(floor, dict):
        obstacles = floor.get('obstacles')
        if not isinstance(obstacles, list) or any(not _bounds(box) for box in obstacles):
            findings.append(('/geometry/floors/obstacles', 'Explicit valid obstacle rectangles are required, including [] when clear.'))
    if findings:
        raise TrajectoryError('invalid_input', '; '.join(f'{p}: {m}' for p, m in findings))


def automatic_stop_areas(config, floor_id):
    """Protect door cores and >=3-distinct-neighbour graph junction cores.

    The square side is max(incident corridor widths, door opening width).
    Widths may come from explicit building defaults. Reciprocal or duplicated
    directed edges count once for junction degree; separate floors never join.
    This is automatic local stopping protection, not inferred wall geometry.
    """
    if not isinstance(config, dict):
        raise TrajectoryError('invalid_input', 'A configuration object is required.')
    corridors, building = config.get('corridors', {}), config.get('building', {})
    if not isinstance(corridors, dict) or not isinstance(building, dict):
        raise TrajectoryError('invalid_input', 'Corridors and building must be objects.')
    locations, nodes, edges = config.get('locations', []), corridors.get('nodes', []), corridors.get('edges', [])
    if not all(isinstance(rows, list) for rows in (locations, nodes, edges)):
        raise TrajectoryError('invalid_input', 'Locations, nodes and edges must be lists.')
    points, neighbours, widths = {}, {}, {}
    for point in locations+nodes:
        if not isinstance(point, dict):
            raise TrajectoryError('invalid_input', 'Each graph point must be an object.')
        name = point.get('name')
        if not isinstance(name, str) or not name or name in points:
            raise TrajectoryError('invalid_input', 'Graph point names must be nonempty and unique.')
        points[name] = point
        neighbours[name], widths[name] = set(), []
    for edge in edges:
        if not isinstance(edge, dict):
            raise TrajectoryError('invalid_input', 'Each graph edge must be an object.')
        a, b = edge.get('from'), edge.get('to')
        if a not in points or b not in points:
            raise TrajectoryError('invalid_input', 'A protection edge references an unknown graph point.')
        if a == b or points[a].get('floor') != floor_id or points[b].get('floor') != floor_id:
            continue
        for source, target in ((a, b), (b, a)):
            neighbours[source].add(target)
            widths[source].append(edge.get('width_m', building.get('default_corridor_width_m')))
    result = []
    for name, point in points.items():
        if point.get('floor') != floor_id:
            continue
        door = point.get('has_door', False)
        if type(door) is not bool:
            raise TrajectoryError('invalid_input', f'{name}: has_door must be boolean.')
        junction = len(neighbours[name]) >= 3
        if not door and not junction:
            continue
        relevant_widths = list(widths[name])
        if door:
            relevant_widths.append(point.get('door_clear_width_m', building.get('default_door_clear_width_m')))
        if not relevant_widths or any(value is None for value in relevant_widths):
            raise TrajectoryError('missing_geometry', f'{name}: explicit opening/corridor widths are required for automatic stopping protection.')
        half = max(_number(value, f'{name} protection width', positive=True) for value in relevant_widths)/2
        x, y = point.get('x'), point.get('y')
        if any(not isinstance(v, (int, float)) or isinstance(v, bool)
               or not math.isfinite(v) or abs(v) >= 1e8 for v in (x, y)):
            raise TrajectoryError('missing_geometry', f'{name}: explicit finite graph coordinates are required.')
        box = (x-half, y-half, x+half, y+half)
        result.append({'id': name, 'source': 'door_junction' if door and junction else 'door' if door else 'junction',
                       'polygon': _polygon(box), 'envelope': box,
                       'protection_model': 'node_core_square_v1'})
    return result


def stopping_findings(pose, *, length_m, width_m, wall_clearance_m, floor, protected_areas=()):
    """Explain invalid stops using complete centred loaded rectangle.

    Wall margin applies to bounds/obstacles. No-queuing and automatic protection
    check the actual footprint; boundary contact alone does not obstruct an area.
    This checks static geometry only, not whether another robot can pass.
    """
    _validate_floor(floor)
    _pose(pose)
    _number(wall_clearance_m, 'wall_clearance_m')
    physical = footprint(pose, length_m, width_m)
    wall_shape = footprint(pose, length_m, width_m, wall_clearance_m)
    findings = []
    if not _within(wall_shape, floor['bounds']):
        findings.append({'code': 'floor_clearance', 'area_id': None,
                         'detail': 'The full loaded footprint plus wall clearance extends outside the floor.'})
    for index, bounds in enumerate(floor['obstacles']):
        if polygons_overlap(wall_shape, _polygon(bounds)):
            findings.append({'code': 'obstacle_clearance', 'area_id': index,
                             'detail': 'The full loaded footprint plus wall clearance intersects an obstacle.'})
    for area in floor.get('no_queuing_areas', []):
        if polygons_overlap(physical, _polygon(area['bounds'])):
            findings.append({'code': 'no_queuing_area', 'area_id': area['id'],
                             'detail': 'The loaded footprint obstructs a drawn no-queuing area.'})
    for area in protected_areas:
        if polygons_overlap(physical, area['polygon']):
            findings.append({'code': 'protected_'+area['source'], 'area_id': area['id'],
                             'detail': 'The loaded footprint obstructs automatic door/junction protection.'})
    return findings


def stationary_claim(pose, *, start, end, owner, length_m, width_m, clearance_m=0, robot_clearance_m=0):
    """One continuous reservation compatible with swept-time traffic cells.

    Use clearance_m=0 for a physical claim; robot_clearance_m records the pairwise
    requirement, to be enforced as max(A,B) by the traffic scheduler. The function
    does not inflate both robots by the whole pairwise gap. Positive infinite end
    explicitly means no known departure; start is finite and end must exceed it.
    """
    _pose(pose)
    start = _number(start, 'start')
    if (not isinstance(end, (int, float)) or isinstance(end, bool)
            or math.isnan(end) or end <= start):
        raise TrajectoryError('invalid_input', 'Stationary end must exceed start; +infinity denotes an unknown departure.')
    if not isinstance(owner, str) or not owner:
        raise TrajectoryError('invalid_input', 'A stationary claim needs a nonempty owner id.')
    _number(clearance_m, 'clearance_m')
    gap = _number(robot_clearance_m, 'robot_clearance_m')
    polygon = footprint(pose, length_m, width_m, clearance_m)
    return {'start': start, 'end': float(end), 'owner': owner, 'polygon': polygon,
            'envelope': polygon_bounds(polygon), 'robot_clearance_m': gap,
            'occupancy_kind': 'stationary'}


def select_passing_place(floor, candidates, *, length_m, width_m, wall_clearance_m, protected_areas=()):
    """Select nearest fitting candidate by provided verified route distance.

    A candidate is {area_id, pose: Pose, route_distance_m}. Only candidates whose
    route has already been shown reachable belong here. +inf means unreachable;
    negative/NaN/missing distances are invalid, not silently ignored. A tie uses
    area id then pose coordinates for deterministic selection. Returns None if
    no supplied reachable candidate fits; does not assert global infeasibility.
    """
    _validate_floor(floor)
    if not isinstance(candidates, (list, tuple)):
        raise TrajectoryError('invalid_input', 'Passing-place candidates must be a list.')
    areas = {area['id']: area for area in floor.get('passing_places', [])}
    accepted = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get('area_id') not in areas:
            raise TrajectoryError('invalid_input', 'A passing candidate must reference a drawn passing place.')
        pose = _pose(candidate.get('pose'))
        distance = candidate.get('route_distance_m')
        if not isinstance(distance, (int, float)) or isinstance(distance, bool) or math.isnan(distance) or distance < 0:
            raise TrajectoryError('invalid_input', 'A candidate needs a nonnegative route distance.')
        if math.isinf(distance):
            continue
        if not _within(footprint(pose, length_m, width_m), areas[candidate['area_id']]['bounds']):
            continue
        if stopping_findings(pose, length_m=length_m, width_m=width_m,
                             wall_clearance_m=wall_clearance_m, floor=floor, protected_areas=protected_areas):
            continue
        accepted.append(candidate)
    return min(accepted, key=lambda row: (row['route_distance_m'], row['area_id'],
               row['pose'].x, row['pose'].y, row['pose'].heading)) if accepted else None
