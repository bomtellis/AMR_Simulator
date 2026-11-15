"""Explicit, physically checked initial positions for detailed traffic fleets.

``geometry.initial_placements`` contains one ``amr_id``, named ``location`` and
``heading_deg`` per expanded robot instance. The sole implicit placement is the
existing single-robot first-charger position. Simple and whole-route comparison
models do not interpret this field. All distances are metres; headings degrees.
"""
import math

from amr_clearances import resolved_clearances
from amr_fleet_allocation import configured_charge_locations
from amr_geometric_traffic import polygons_overlap
from amr_geometric_occupancy import automatic_stop_areas, stopping_findings
from amr_trajectories import Pose, TrajectoryError, footprint


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _bounds(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(_number(v) and abs(v) < 1e8 for v in value)
            and value[0] < value[2] and value[1] < value[3])


def _resolve(config):
    if not isinstance(config, dict):
        return {}, []
    sim, geometry = config.get('simulation', {}), config.get('geometry', {})
    if (not isinstance(sim, dict) or sim.get('motion_model') != 'geometric_v1'
            or not isinstance(geometry, dict) or geometry.get('traffic_model') != 'keep_right_v1'):
        return {}, []
    findings, robots, result = [], {}, {}
    path = '/geometry/initial_placements'
    def error(where, detail):
        findings.append((where, detail))
    definitions = config.get('amrs')
    locations = config.get('locations')
    floors = geometry.get('floors')
    if not isinstance(definitions, list) or not isinstance(locations, list) or not isinstance(floors, list):
        return {}, [(path, 'Robot, location and modelled floor lists are required to resolve initial placements.')]
    for index, robot in enumerate(definitions):
        here = f'/amrs/{index}'
        if not isinstance(robot, dict) or not isinstance(robot.get('id'), str) or not robot['id'].strip():
            error(here, 'A named robot type is required for initial placement.')
            continue
        count = robot.get('quantity', 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            error(here+'/quantity', 'Initial fleet quantity must be a positive whole number.')
            continue
        for number in range(1, count+1):
            identity = f'{robot["id"]}-{number}'
            if identity in robots:
                error(here+'/id', 'Expanded robot instance identifiers must be unique.')
            robots[identity] = robot
    if findings:
        return {}, findings
    rows = geometry.get('initial_placements')
    if 'initial_placements' not in geometry:
        if len(robots) != 1:
            return {}, [(path, 'Provide an explicit placement for every robot in a multi-robot detailed fleet.')]
        identity, robot = next(iter(robots.items()))
        try:
            homes = configured_charge_locations(config)
        except (TypeError, AttributeError):
            homes = []
        manoeuvring = robot.get('manoeuvring', {})
        rows = [{'amr_id': identity, 'location': homes[0] if homes else None,
                 'heading_deg': manoeuvring.get('initial_heading_deg') if isinstance(manoeuvring, dict) else None}]
    if not isinstance(rows, list):
        return {}, [(path, 'Initial placements must be a list of per-instance locations and headings.')]
    seen = set()
    for index, row in enumerate(rows):
        here = f'{path}/{index}'
        if not isinstance(row, dict):
            error(here, 'An initial placement must be an object.')
            continue
        identity, name, heading = row.get('amr_id'), row.get('location'), row.get('heading_deg')
        if not isinstance(identity, str) or identity not in robots or identity in seen:
            error(here+'/amr_id', 'Use a known robot instance exactly once, such as R-1.')
            continue
        seen.add(identity)
        matches = [loc for loc in locations if isinstance(loc, dict) and isinstance(name, str) and loc.get('name') == name]
        if len(matches) != 1:
            error(here+'/location', 'Select one unambiguous named service location; corridor nodes are not initial locations.')
            continue
        location = matches[0]
        floor_id = location.get('floor')
        modelled = [floor for floor in floors if isinstance(floor, dict) and floor.get('floor') == floor_id]
        if (not isinstance(floor_id, int) or isinstance(floor_id, bool) or len(modelled) != 1
                or not all(_number(location.get(k)) and abs(location[k]) < 1e8 for k in ('x', 'y'))):
            error(here+'/location', 'The initial location requires finite coordinates and one modelled integer floor.')
            continue
        floor = modelled[0]
        if (not _bounds(floor.get('bounds')) or not isinstance(floor.get('obstacles'), list)
                or any(not _bounds(box) for box in floor['obstacles'])):
            error(here+'/location', 'Initial footprint checking requires valid floor bounds and obstacle rectangles.')
            continue
        if not _number(heading):
            error(here+'/heading_deg', 'Provide an explicit finite initial heading in degrees.')
            continue
        robot = robots[identity]
        length, width = robot.get('length_m', .8), robot.get('width_m', .6)
        if not all(_number(v) and 0 < v < 1e8 for v in (length, width)):
            error(here, 'The initial robot footprint must have positive finite dimensions.')
            continue
        try:
            clearances = resolved_clearances(config, robot.get('manoeuvring', {}))
        except (ValueError, TypeError, AttributeError):
            error(here, 'Explicit valid wall and robot clearances are required for initial placement.')
            continue
        pose = Pose(location['x'], location['y'], math.radians(heading))
        physical = footprint(pose, length, width)
        try:
            # An initial pose is parked indefinitely until work is committed,
            # including in a no-work simulation; it cannot obstruct protected areas.
            stopped = stopping_findings(pose, length_m=length, width_m=width,
                wall_clearance_m=clearances['wall_m'], floor=floor,
                protected_areas=automatic_stop_areas(config, floor_id))
            for finding in stopped:
                error(here, f'{identity}: {finding["code"]}: {finding["area_id"]}; {finding["detail"]}')
        except TrajectoryError as exc:
            error(here, f'{identity}: {exc.reason}: {exc}')
        result[identity] = {'amr_id': identity, 'location': name, 'floor': floor_id,
                            'x': pose.x, 'y': pose.y, 'heading_deg': float(heading),
                            'length_m': float(length), 'width_m': float(width),
                            'robot_clearance_m': clearances['robot_m'], 'polygon': physical}
    for identity in sorted(robots.keys()-seen):
        error(path, f'Missing initial placement for {identity}.')
    placed = list(result.values())
    for index, first in enumerate(placed):
        for second in placed[index+1:]:
            if (first['floor'] == second['floor'] and polygons_overlap(first['polygon'], second['polygon'],
                    max(first['robot_clearance_m'], second['robot_clearance_m']))):
                error(path, f'{first["amr_id"]} and {second["amr_id"]}: initial footprints overlap or violate required robot separation.')
    return result, findings


def initial_placement_findings(config):
    """Return structured input findings without modifying supplied configuration."""
    return _resolve(config)[1]


def resolve_initial_placements(config):
    """Resolve checked poses or fail; no fabricated fleet spreading is permitted."""
    result, findings = _resolve(config)
    if findings:
        raise ValueError('Invalid initial placements: '+'; '.join(f'{path}: {detail}' for path, detail in findings))
    return result
