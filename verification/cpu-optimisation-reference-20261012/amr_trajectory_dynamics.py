"""Apply explicit scalar movement dynamics to an existing geometric trajectory.

Translation and yaw respect finite acceleration/braking on reference-path arcs.
Circular fillets change curvature abruptly, so the robot stops at those joins
before steering changes. No steering dwell or alternative geometry is invented.
Equal signed-curvature subdivisions retain continuous speed. Path endpoints,
pivots and movement direction changes are stationary.
"""
from dataclasses import replace
import math

from amr_motion_profiles import (MotionProfile, MotionProfileError, MotionSettings,
                                 profile_for_movement)
from amr_trajectories import EPS, Trajectory


def _reachable(speed, acceleration, distance):
    squared = speed * speed + 2 * acceleration * distance
    if not math.isfinite(squared):
        raise MotionProfileError('Trajectory timing exceeds the numeric range.')
    result = math.sqrt(squared)
    # sqrt may round upwards. A boundary speed just above reachability can be
    # several distance ULPs out after subtracting close squared speeds. Round
    # the derived speed conservatively rather than relaxing physical limits.
    while result > speed and (result - speed) * ((result + speed) / acceleration) / 2 > distance:
        result = math.nextafter(result, 0.0)
    return result


def _same_pose(a, b):
    return (math.hypot(a.x - b.x, a.y - b.y) <= 1e-8
            and abs(math.remainder(a.heading - b.heading, 2 * math.pi)) <= 1e-8)


def _reference_key(motion):
    """Validate explicit timing/axis semantics before using offset geometry."""
    reference = motion.reference
    if reference is None:
        return None
    required = {'longitudinal_mm', 'lateral_mm', 'timing_reference', 'pivot_axis'}
    if not isinstance(reference, dict) or set(reference) != required:
        raise MotionProfileError('Motion reference requires explicit offsets, timing reference and pivot axis.')
    offsets = tuple(reference[key] for key in ('longitudinal_mm', 'lateral_mm'))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in offsets):
        raise MotionProfileError('Motion reference offsets must be finite numbers.')
    if (reference['timing_reference'] != 'turning_reference_point'
            or reference['pivot_axis'] not in ('body_centre', 'reference_point')):
        raise MotionProfileError('Motion reference timing or pivot axis is unsupported.')
    return (*offsets, reference['timing_reference'], reference['pivot_axis'])


def _validate_pivot(motion, settings):
    if (motion.length_m != 0 or motion.radius_m != 0 or motion.sweep_rad == 0
            or not settings.pivot_allowed):
        raise MotionProfileError('Pivot requires permission, zero length/radius and a nonzero sweep.',
                                 'infeasible_motion')
    if abs(math.remainder(motion.end.heading - motion.start.heading - motion.sweep_rad,
                          2 * math.pi)) > 1e-8:
        raise MotionProfileError('Pivot headings disagree with its sweep.', 'infeasible_motion')
    if motion.reference is not None and motion.reference['pivot_axis'] == 'reference_point':
        if (not isinstance(motion.centre, (list, tuple)) or len(motion.centre) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       for v in motion.centre)):
            raise MotionProfileError('Reference-axis pivot requires a finite fixed centre.')
        for fraction in (0., 1.):
            reference_pose = motion.reference_pose_at(fraction)
            if math.hypot(reference_pose.x - motion.centre[0], reference_pose.y - motion.centre[1]) > 1e-8:
                raise MotionProfileError('Reference-axis pivot must preserve its reference point.',
                                         'infeasible_motion')
    elif math.hypot(motion.end.x - motion.start.x, motion.end.y - motion.start.y) > 1e-8:
        raise MotionProfileError('A body-centre pivot cannot translate.', 'infeasible_motion')


def retime_trajectory(trajectory, settings):
    """Return a Trajectory with profile-backed durations on the same geometry.

    Forward/reverse tangent lines/arcs and fixed-heading lateral lines retain
    their geometry. Direction changes, curvature changes and pivots stop
    translation. This does not search for paths. Input poses/clearance are
    never replaced.
    """
    if not isinstance(trajectory, Trajectory) or not trajectory.motions:
        raise MotionProfileError('Provide a nonempty geometric Trajectory.')
    if not isinstance(settings, MotionSettings):
        raise MotionProfileError('Provide validated MotionSettings.')
    motions = trajectory.motions
    for i, motion in enumerate(motions):
        _reference_key(motion)
        coordinates = (motion.start.x, motion.start.y, motion.start.heading,
                       motion.end.x, motion.end.y, motion.end.heading,
                       motion.length_m, motion.radius_m, motion.sweep_rad)
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) for v in coordinates):
            raise MotionProfileError('Motion coordinates and dimensions must be finite numbers.')
        if i and not _same_pose(motions[i - 1].end, motion.start):
            raise MotionProfileError('Adjacent motions do not share a continuous pose.', 'infeasible_motion')
        if motion.kind not in ('line', 'arc', 'pivot'):
            raise MotionProfileError(f'Unsupported motion kind {motion.kind!r}.')
        if (motion.movement not in ('forward', 'reverse', 'lateral')
                or (motion.kind == 'pivot' and motion.movement != 'forward')
                or (motion.kind == 'arc' and motion.movement == 'lateral')):
            raise MotionProfileError('Unsupported movement type for this primitive.')
        if motion.movement == 'lateral' and not settings.lateral_allowed:
            raise MotionProfileError('This robot does not permit lateral movement.', 'infeasible_motion')
        if motion.movement == 'reverse' and not settings.reverse_allowed:
            raise MotionProfileError('This robot does not permit reverse movement.', 'infeasible_motion')
        if motion.kind == 'pivot':
            _validate_pivot(motion, settings)
        elif motion.length_m <= 0:
            raise MotionProfileError('Travel motion requires positive length.')
        elif motion.kind == 'arc' and (motion.radius_m <= 0 or motion.sweep_rad == 0):
            raise MotionProfileError('An arc requires positive reference radius and nonzero sweep.')
        if (motion.kind == 'arc' and motion.reference is not None
                and motion.centre_orbit_radius_m <= EPS and not settings.pivot_allowed):
            raise MotionProfileError('A reference arc that rotates in place requires pivot permission.',
                                     'infeasible_motion')

    output = []

    def direction_key(m):
        if m.movement == 'lateral':
            side = ((m.end.y - m.start.y) * math.cos(m.start.heading)
                    - (m.end.x - m.start.x) * math.sin(m.start.heading))
            return (m.movement, 1 if side > 0 else -1, _reference_key(m))
        # Exact signed radius avoids treating slightly different curvature as
        # continuous, or reciprocals underflowing to the straight-line key.
        return (m.movement, math.copysign(m.radius_m, m.sweep_rad)
                if m.kind == 'arc' else 0, _reference_key(m))

    i = 0
    while i < len(motions):
        motion = motions[i]
        if motion.kind == 'pivot':
            profile = profile_for_movement(settings, movement='pivot', distance=abs(motion.sweep_rad))
            output.append(replace(motion, duration_sec=profile.duration_sec, profile=profile.to_dict()))
            i += 1
            continue
        end = i
        while (end < len(motions) and motions[end].kind != 'pivot'
               and direction_key(motions[end]) == direction_key(motion)):
            end += 1
        chain = motions[i:end]
        limits = [profile_for_movement(settings, movement=m.movement, distance=m.length_m,
                                       turn_radius_m=m.radius_m if m.kind == 'arc' else None)
                  for m in chain]
        caps = [p.max_speed for p in limits]
        speeds = [0.0] + [min(a, b) for a, b in zip(caps, caps[1:])] + [0.0]
        for j, m in enumerate(chain):
            speeds[j + 1] = min(speeds[j + 1], _reachable(speeds[j], limits[j].acceleration, m.length_m))
        for j in range(len(chain) - 1, -1, -1):
            speeds[j] = min(speeds[j], _reachable(speeds[j + 1], limits[j].braking, chain[j].length_m))
        for j, m in enumerate(chain):
            profile = MotionProfile(m.length_m, caps[j], limits[j].acceleration,
                                    limits[j].braking, speeds[j], speeds[j + 1])
            output.append(replace(m, duration_sec=profile.duration_sec, profile=profile.to_dict()))
        i = end
    return replace(trajectory, motions=tuple(output))
