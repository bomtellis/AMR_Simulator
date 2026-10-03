"""Build continuous absolute occupancy from explicitly recorded geometric legs.

No location-name lookup, straight-line fallback, inferred lift movement or load
disappearance is permitted. Swept cells are recomputed from decoded trajectory
evidence and the physical loaded state, rather than trusting stale cached cells.
"""
import math

from amr_geometric_occupancy import stationary_claim
from amr_geometric_traffic import swept_cells
from amr_trajectories import Pose, TrajectoryError, trajectory_from_dict


def _number(value, name, *, positive=False):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise TrajectoryError('invalid_input', f'{name} must be a finite '
                              f'{"positive" if positive else "nonnegative"} number.')
    return float(value)


def _same(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-8)


def _heading_same(a, b):
    return abs(math.remainder(a - b, 2 * math.pi)) <= 1e-8


def _assert_pose(actual, expected, message):
    if (not _same(actual.x, expected.x) or not _same(actual.y, expected.y)
            or not _heading_same(actual.heading, expected.heading)):
        raise TrajectoryError('invalid_evidence', message)


def _check_metadata(segment, pose, floor, prefix, rotation_key):
    for axis in ('x', 'y'):
        key = f'{prefix}_{axis}'
        if key in segment:
            value = segment[key]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not _same(value, getattr(pose, axis))):
                raise TrajectoryError('invalid_evidence', f'{key} disagrees with geometric pose.')
    key = f'{prefix}_floor'
    if key in segment and (type(segment[key]) is not int or segment[key] != floor):
        raise TrajectoryError('unsupported_movement', 'Floor transfers require explicit supported geometry.')
    if rotation_key in segment:
        value = segment[rotation_key]
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or not _heading_same(math.radians(value), pose.heading)):
            raise TrajectoryError('invalid_evidence', f'{rotation_key} disagrees with geometric heading.')


def occupancy_plan(*, initial_pose, floor, start, owner, robot_length_m, robot_width_m,
                   loaded_length_m, loaded_width_m, robot_clearance_m, segments,
                   initial_loaded=False):
    """Return floor-labelled absolute claims covering every interval and final rest.

    Pickup occupies the union of centred empty/loaded rectangles throughout
    handling. Dropoff remains loaded until handling ends. The terminal claim
    preserves the actual final load state, indefinitely until replaced by another
    complete plan. Zero-duration handling creates an instantaneous physical claim;
    it is never widened into a fictitious positive time interval.
    Wall and forbidden-stopping checks are intentionally handled by the caller.
    """
    if (not isinstance(initial_pose, Pose) or any(isinstance(v, bool)
            or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in (initial_pose.x, initial_pose.y, initial_pose.heading))):
        raise TrajectoryError('invalid_input', 'initial_pose must be a finite Pose.')
    if type(floor) is not int:
        raise TrajectoryError('invalid_input', 'floor must be an explicit integer.')
    if not isinstance(owner, str) or not owner.strip():
        raise TrajectoryError('invalid_input', 'owner must be a nonempty string.')
    if not isinstance(segments, (list, tuple)) or type(initial_loaded) is not bool:
        raise TrajectoryError('invalid_input', 'Provide a segment list and explicit boolean initial_loaded.')
    empty = (_number(robot_length_m, 'robot_length_m', positive=True),
             _number(robot_width_m, 'robot_width_m', positive=True))
    loaded = (max(empty[0], _number(loaded_length_m, 'loaded_length_m', positive=True)),
              max(empty[1], _number(loaded_width_m, 'loaded_width_m', positive=True)))
    gap = _number(robot_clearance_m, 'robot_clearance_m')
    clock = _number(start, 'start')
    pose, carrying = initial_pose, initial_loaded
    output = []

    def stationary(begin, end, dimensions, segment_type, index, has_load):
        instantaneous = end == begin and segment_type in ('pickup', 'dropoff')
        if end <= begin and not instantaneous:
            return
        # Reuse physical polygon validation. The temporary unbounded end is
        # replaced before exposing the instantaneous claim; no epsilon is used.
        claim = stationary_claim(pose, start=begin, end=math.inf if instantaneous else end, owner=owner,
                                  length_m=dimensions[0], width_m=dimensions[1],
                                  robot_clearance_m=gap)
        if instantaneous:
            claim.update(end=begin, occupancy_kind='instantaneous')
        claim.update(floor=floor, pose=pose, length_m=dimensions[0], width_m=dimensions[1],
                     segment_type=segment_type, segment_index=index, loaded=has_load,
                     source_id=f'{index}:{segment_type}')
        output.append(claim)

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or not isinstance(segment.get('type'), str):
            raise TrajectoryError('invalid_input', f'Segment {index} needs an explicit type.')
        kind = segment['type']
        duration = _number(segment.get('duration'), f'Segment {index} duration')
        if _number(segment.get('wait_time', 0), f'Segment {index} wait_time') != 0:
            raise TrajectoryError('unsupported_movement', 'Represent waits as explicit stationary segments.')
        end_time = clock + duration
        if not math.isfinite(end_time) or (duration > 0 and end_time <= clock):
            raise TrajectoryError('invalid_input', 'Absolute occupancy time exceeds numeric range.')
        _check_metadata(segment, pose, floor, 'from', 'amr_rotation_start_deg')
        if kind == 'corridor':
            if segment.get('motion_model') != 'geometric_v1':
                raise TrajectoryError('unsupported_movement', 'Moving occupancy needs explicit geometric trajectory evidence.')
            trajectory = trajectory_from_dict(segment.get('trajectory'))
            _assert_pose(trajectory.motions[0].start, pose, 'Trajectory start does not match preceding occupancy.')
            if not _same(duration, trajectory.duration_sec):
                raise TrajectoryError('invalid_evidence', 'Segment duration disagrees with recorded trajectory.')
            if 'distance_m' in segment and not _same(_number(segment['distance_m'], 'distance_m'), trajectory.length_m):
                raise TrajectoryError('invalid_evidence', 'Segment distance disagrees with recorded trajectory.')
            dimensions = loaded if carrying else empty
            cells = swept_cells(trajectory, length_m=dimensions[0], width_m=dimensions[1],
                                clearance_m=0, robot_clearance_m=gap)
            for cell_index, cell in enumerate(cells):
                claim = dict(cell)
                claim.update(start=clock + cell['start'], end=clock + cell['end'], owner=owner,
                             floor=floor, occupancy_kind='moving', segment_type=kind,
                             segment_index=index, loaded=carrying,
                             source_id=f'{index}:{kind}:{cell_index}',
                             length_m=dimensions[0], width_m=dimensions[1])
                if claim['end'] <= claim['start']:
                    raise TrajectoryError('invalid_input', 'Absolute swept-cell times exceed numeric resolution.')
                output.append(claim)
            pose = trajectory.motions[-1].end
        else:
            known_stationary = kind in ('pickup', 'dropoff', 'charge', 'wash', 'wash_cycle', 'wait') or kind.startswith('wait_')
            if not known_stationary:
                raise TrajectoryError('unsupported_movement', f'Unsupported occupancy segment {kind!r}.')
            if _number(segment.get('distance_m', 0), 'stationary distance_m') != 0 or segment.get('trajectory') is not None:
                raise TrajectoryError('unsupported_movement', 'A stationary segment cannot carry movement evidence.')
            if kind == 'pickup' and carrying:
                raise TrajectoryError('invalid_evidence', 'Pickup while already loaded needs an explicit multi-load model.')
            if kind == 'dropoff' and not carrying:
                raise TrajectoryError('invalid_evidence', 'Dropoff has no preceding carried load.')
            has_load = carrying or kind == 'pickup'
            dimensions = loaded if has_load else empty
            stationary(clock, end_time, dimensions, kind, index, has_load)
            if kind == 'pickup':
                carrying = True
            elif kind == 'dropoff':
                carrying = False
        _check_metadata(segment, pose, floor, 'to', 'amr_rotation_end_deg')
        clock = end_time
    stationary(clock, math.inf, loaded if carrying else empty, 'terminal', len(segments), carrying)
    return output
