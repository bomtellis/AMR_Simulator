"""Apply explicit scalar movement dynamics to an existing geometric trajectory.

Translational boundary speeds are continuous across tangent line/arc joins.
Pivot and path endpoints are stationary. Circular fillets have discontinuous
curvature: this module does not enforce angular acceleration at line/arc joins.
Angular acceleration/braking apply to stationary pivots. Curvature-continuous
steering geometry is needed to remove that limitation without stopping at joins.
"""
from dataclasses import replace
import math

from amr_motion_profiles import (MotionProfile, MotionProfileError, MotionSettings,
                                 profile_for_movement, turn_speed_limit)
from amr_trajectories import Trajectory


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


def retime_trajectory(trajectory, settings):
    """Return a Trajectory with profile-backed durations on the same geometry.

    Forward/reverse tangent lines/arcs and fixed-heading lateral lines retain
    their geometry. Direction changes and pivots stop translation. This does
    not search for paths. Input poses/clearance are never replaced.
    """
    if not isinstance(trajectory, Trajectory) or not trajectory.motions:
        raise MotionProfileError('Provide a nonempty geometric Trajectory.')
    if not isinstance(settings, MotionSettings):
        raise MotionProfileError('Provide validated MotionSettings.')
    motions = trajectory.motions
    for i, motion in enumerate(motions):
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
        if motion.kind == 'pivot':
            if motion.length_m != 0 or motion.sweep_rad == 0 or not settings.pivot_allowed:
                raise MotionProfileError('Pivot requires permission, zero length and a nonzero sweep.', 'infeasible_motion')
            if math.hypot(motion.end.x - motion.start.x, motion.end.y - motion.start.y) > 1e-8:
                raise MotionProfileError('A stationary pivot cannot translate.', 'infeasible_motion')
        elif motion.length_m <= 0:
            raise MotionProfileError('Travel motion requires positive length.')
        elif motion.kind == 'arc' and (motion.radius_m <= 0 or motion.sweep_rad == 0):
            raise MotionProfileError('An arc requires positive reference radius and nonzero sweep.')

    output = []

    def direction_key(m):
        if m.movement == 'lateral':
            side = ((m.end.y - m.start.y) * math.cos(m.start.heading)
                    - (m.end.x - m.start.x) * math.sin(m.start.heading))
            return (m.movement, 1 if side > 0 else -1)
        return (m.movement, 0)

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
        speed = {'forward': settings.forward_speed_m_per_sec,
                 'reverse': settings.reverse_speed_m_per_sec,
                 'lateral': settings.lateral_speed_m_per_sec}[motion.movement]
        caps = [min(speed,
                    turn_speed_limit(settings.maximum_turn_speed_m_per_sec,
                                     settings.lateral_acceleration_m_per_sec2, m.radius_m))
                if m.kind == 'arc' else speed for m in chain]
        speeds = [0.0] + [min(a, b) for a, b in zip(caps, caps[1:])] + [0.0]
        for j, m in enumerate(chain):
            speeds[j + 1] = min(speeds[j + 1], _reachable(speeds[j], settings.acceleration_m_per_sec2, m.length_m))
        for j in range(len(chain) - 1, -1, -1):
            speeds[j] = min(speeds[j], _reachable(speeds[j + 1], settings.braking_m_per_sec2, chain[j].length_m))
        for j, m in enumerate(chain):
            profile = MotionProfile(m.length_m, caps[j], settings.acceleration_m_per_sec2,
                                    settings.braking_m_per_sec2, speeds[j], speeds[j + 1])
            output.append(replace(m, duration_sec=profile.duration_sec, profile=profile.to_dict()))
        i = end
    return replace(trajectory, motions=tuple(output))
