"""Rigid turning-reference offsets with canonical body-centre output poses.

Longitudinal offset is positive towards the body front; lateral is positive
left. Translation speeds, distances and radii describe the turning reference.
Pivot timing remains angular. Graph points are body-centre anchors, not reference
positions. Fillets may cut interior corners, as in the original planner.
"""
from dataclasses import replace
import math

from amr_trajectories import (EPS, Motion, Pose, Trajectory, TrajectoryError,
                              plan_trajectory, plan_reverse_trajectory,
                              plan_lateral_trajectory, trajectory_from_dict)


def reference_metadata(longitudinal_mm, lateral_mm, pivot_axis):
    values = []
    for name, value in (('longitudinal_mm', longitudinal_mm), ('lateral_mm', lateral_mm)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise TrajectoryError('invalid_input', f'{name} must be an explicit finite number.')
        values.append(float(value))
    if pivot_axis not in ('body_centre', 'reference_point'):
        raise TrajectoryError('invalid_input', 'pivot_axis must be body_centre or reference_point.')
    return dict(longitudinal_mm=values[0], lateral_mm=values[1],
                timing_reference='turning_reference_point', pivot_axis=pivot_axis)


def _validated_reference(reference):
    if not isinstance(reference, dict) or set(reference) != {
            'longitudinal_mm', 'lateral_mm', 'timing_reference', 'pivot_axis'}:
        raise TrajectoryError('invalid_input', 'Provide complete explicit reference metadata.')
    if reference['timing_reference'] != 'turning_reference_point':
        raise TrajectoryError('invalid_input', 'Timing must use the turning reference point.')
    return reference_metadata(reference['longitudinal_mm'], reference['lateral_mm'], reference['pivot_axis'])


def _offset(pose, reference, sign):
    x, y = reference['longitudinal_mm'] / 1000, reference['lateral_mm'] / 1000
    c, s = math.cos(pose.heading), math.sin(pose.heading)
    return Pose(pose.x + sign * (c*x - s*y), pose.y + sign * (s*x + c*y), pose.heading)


def reference_motion_to_body(motion, reference):
    """Transform a reference-frame primitive into a canonical centre primitive.

    Lines/arcs and reference-axis pivots are supported. A centre-axis pivot is
    constructed directly from its stationary body centre, rather than treating
    a stationary reference point as a stationary centre.
    """
    reference = _validated_reference(reference)
    if not reference['longitudinal_mm'] and not reference['lateral_mm']:
        return motion
    if motion.reference is not None:
        raise TrajectoryError('invalid_input', 'Motion is already reference-transformed.')
    if motion.kind == 'pivot' and reference['pivot_axis'] != 'reference_point':
        raise TrajectoryError('invalid_input', 'A stationary reference pivot needs reference_point pivot_axis.')
    centre = ((motion.start.x, motion.start.y) if motion.kind == 'pivot' else motion.centre)
    return replace(motion, start=_offset(motion.start, reference, -1),
                   end=_offset(motion.end, reference, -1), centre=centre, reference=reference)


def plan_reference_lateral_trajectory(start, end_xy, *, reference_longitudinal_mm,
                                      reference_lateral_mm, pivot_axis,
                                      speed_m_per_sec, lateral_allowed):
    reference = reference_metadata(reference_longitudinal_mm, reference_lateral_mm, pivot_axis)
    result = plan_lateral_trajectory(start, end_xy, speed_m_per_sec=speed_m_per_sec,
                                     lateral_allowed=lateral_allowed)
    if not reference_longitudinal_mm and not reference_lateral_mm:
        return result
    return replace(result, motions=tuple(replace(m, reference=reference) for m in result.motions))


def plan_reference_trajectory(points, *, reference_longitudinal_mm, reference_lateral_mm,
                               pivot_axis, movement='forward', minimum_radius_m,
                               speed_m_per_sec, pivot_allowed, pivot_speed_deg_per_sec,
                               start_heading_deg=None):
    """Fillet shifted reference support lines while retaining centre endpoints.

    At curvature changes the detailed retimer stops before steering. A turn
    which does not fit may become a pivot only about the configured axis.
    Reference-axis initial heading corrections and parallel displaced reversal
    supports require an additional manoeuvre search and are rejected explicitly.
    """
    reference = reference_metadata(reference_longitudinal_mm, reference_lateral_mm, pivot_axis)
    if movement not in ('forward', 'reverse'):
        raise TrajectoryError('invalid_input', 'Use the separate lateral planner for lateral translation.')
    planner = plan_reverse_trajectory if movement == 'reverse' else plan_trajectory
    kwargs = dict(minimum_radius_m=minimum_radius_m, speed_m_per_sec=speed_m_per_sec,
                  pivot_allowed=pivot_allowed, pivot_speed_deg_per_sec=pivot_speed_deg_per_sec,
                  start_heading_deg=start_heading_deg)
    if not reference_longitudinal_mm and not reference_lateral_mm:
        return planner(points, **kwargs)
    # Reuse established input validation, with pivots enabled only for this
    # discarded validation trajectory. Offset geometry decides actual feasibility.
    validated = planner(points, **{**kwargs, 'pivot_allowed': True})
    if not isinstance(pivot_allowed, bool):
        raise TrajectoryError('invalid_input', 'pivot_allowed must be an explicit boolean.')
    radius = validated.minimum_radius_m
    speed = float(speed_m_per_sec)
    angular_speed = math.radians(float(pivot_speed_deg_per_sec))
    route = [tuple(map(float, p)) for p in points]
    reverse = math.pi if movement == 'reverse' else 0.0
    directions, headings, lengths = [], [], []
    for a, b in zip(route, route[1:]):
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        lengths.append(length)
        directions.append(((b[0]-a[0])/length, (b[1]-a[1])/length))
        headings.append(math.atan2(b[1]-a[1], b[0]-a[0]) + reverse)
    corners = {}
    for i in range(1, len(route)-1):
        incoming, outgoing = directions[i-1], directions[i]
        h = headings[i-1]
        sweep = math.remainder(headings[i]-h, 2*math.pi)
        if abs(sweep) <= EPS:
            corners[i] = None
            continue
        p = _offset(Pose(*route[i], h), reference, 1)
        q = _offset(Pose(*route[i], h+sweep), reference, 1)
        cross = incoming[0]*outgoing[1] - incoming[1]*outgoing[0]
        if abs(abs(sweep)-math.pi) <= EPS:
            # Parallel supports can share a reference pivot only when they
            # coincide (zero lateral offset); otherwise a connector is needed.
            ref_corner = (p.x, p.y)
            if pivot_axis == 'reference_point' and reference_lateral_mm != 0:
                raise TrajectoryError('infeasible_route', 'Reference-axis reversal needs a connector between displaced supports.')
            fallback = True
        else:
            t = ((q.x-p.x)*outgoing[1] - (q.y-p.y)*outgoing[0]) / cross
            ref_corner = (p.x+t*incoming[0], p.y+t*incoming[1])
            fallback = False
        trim = radius * math.tan(abs(sweep)/2) if not fallback else 0
        ref_entry = Pose(ref_corner[0]-incoming[0]*trim, ref_corner[1]-incoming[1]*trim, h)
        ref_exit = Pose(ref_corner[0]+outgoing[0]*trim, ref_corner[1]+outgoing[1]*trim, h+sweep)
        sign = math.copysign(1, sweep)
        centre = (ref_entry.x-incoming[1]*radius*sign, ref_entry.y+incoming[0]*radius*sign)
        arc = Motion('arc', ref_entry, ref_exit, radius*abs(sweep), radius*abs(sweep)/speed,
                     sweep, radius, centre, movement=movement)
        corners[i] = dict(motion=reference_motion_to_body(arc, reference), sweep=sweep,
                          reference_corner=ref_corner, pivot=fallback)

    def make_pivot(i):
        corner = corners[i]
        if not pivot_allowed:
            raise TrajectoryError('infeasible_route', f'Offset turn at point {i+1} does not fit the configured radius.')
        h, sweep = headings[i-1], corner['sweep']
        if pivot_axis == 'body_centre':
            motion = Motion('pivot', Pose(*route[i], h), Pose(*route[i], h+sweep), 0,
                            abs(sweep)/angular_speed, sweep, reference=reference)
        else:
            xy = corner['reference_corner']
            motion = reference_motion_to_body(Motion('pivot', Pose(*xy, h), Pose(*xy, h+sweep), 0,
                                                     abs(sweep)/angular_speed, sweep), reference)
        corner['motion'], corner['pivot'] = motion, True

    for i, corner in corners.items():
        if corner and corner['pivot']:
            make_pivot(i)
    # Check each remaining straight interval on the original centre support.
    # Replacing an overlapping fillet by a pivot may restore its neighbours.
    for unused in range(len(route)):
        changed = False
        for segment, u in enumerate(directions):
            left, right = corners.get(segment), corners.get(segment+1)
            start = left['motion'].end if left else Pose(*route[segment], headings[segment])
            end = right['motion'].start if right else Pose(*route[segment+1], headings[segment])
            distance = (end.x-start.x)*u[0] + (end.y-start.y)*u[1]
            if distance < -EPS:
                candidates = [i for i in (segment, segment+1)
                              if corners.get(i) and not corners[i]['pivot']]
                if not candidates:
                    raise TrajectoryError('infeasible_route', 'Offset pivot supports require an additional connector manoeuvre.')
                for i in candidates:
                    make_pivot(i)
                changed = True
        if not changed:
            break
    motions = []
    current = Pose(*route[0], headings[0])
    if start_heading_deg is not None:
        initial = math.radians(float(start_heading_deg))
        delta = math.remainder(headings[0]-initial, 2*math.pi)
        if abs(delta) > EPS:
            if not pivot_allowed or pivot_axis != 'body_centre':
                raise TrajectoryError('infeasible_route', 'Initial heading needs an allowed centre pivot or a connector manoeuvre.')
            motions.append(Motion('pivot', Pose(*route[0], initial), Pose(*route[0], initial+delta),
                                  0, abs(delta)/angular_speed, delta, reference=reference))
    for segment, u in enumerate(directions):
        corner = corners.get(segment+1)
        target = corner['motion'].start if corner else Pose(*route[segment+1], headings[segment])
        distance = math.hypot(target.x-current.x, target.y-current.y)
        if distance > EPS:
            along = (target.x-current.x)*u[0] + (target.y-current.y)*u[1]
            across = (target.x-current.x)*u[1] - (target.y-current.y)*u[0]
            if along < -EPS or abs(across) > 1e-7:
                raise TrajectoryError('infeasible_route', 'Reference geometry does not join the requested centre support.')
            motions.append(Motion('line', Pose(current.x, current.y, headings[segment]), target,
                                  distance, distance/speed, movement=movement, reference=reference))
        current = target
        if corner:
            motions.append(corner['motion'])
            current = corner['motion'].end
    result = Trajectory(tuple(motions), radius, pivot_allowed)
    if not pivot_allowed and any(m.kind == 'arc' and m.centre_orbit_radius_m <= EPS for m in motions):
        raise TrajectoryError('infeasible_route', 'The offset arc rotates the body centre in place and requires pivot permission.')
    # Exercise the evidence contract before returning potentially unsafe geometry.
    trajectory_from_reference_dict(result.to_dict())
    return result


def trajectory_from_reference_dict(data):
    """Validate reference evidence through reconstructed reference primitives."""
    try:
        if type(data['schema_version']) is not int or data['schema_version'] != 3 or data['model'] != 'reference_offset_v1':
            raise ValueError('Unsupported reference model.')
        rows = data['motions']
        if not isinstance(rows, list) or not 1 <= len(rows) <= 30000:
            raise ValueError('Invalid motion list.')
        motions = []
        common = None
        close = lambda a, b: math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-8)
        finite_number = lambda value: (isinstance(value, (int, float))
                                       and not isinstance(value, bool) and math.isfinite(value))
        if not all(finite_number(data[key]) for key in ('minimum_radius_m', 'length_m', 'duration_sec')):
            raise ValueError('Reference trajectory totals/radius must be finite numbers.')
        for row in rows:
            ref = _validated_reference(row['reference'])
            if not ref['longitudinal_mm'] and not ref['lateral_mm']:
                raise ValueError('Zero offsets must use the legacy evidence model.')
            if common is not None and ref != common:
                raise ValueError('Reference metadata changes within a trajectory.')
            common = ref
            if not all(finite_number(row[key]) for key in ('length_m', 'duration_sec', 'sweep_rad', 'radius_m')):
                raise ValueError('Reference motion dimensions and sweep must be finite numbers.')
            raw_centre = row.get('centre', ())
            if not isinstance(raw_centre, (list, tuple)) or not all(finite_number(v) for v in raw_centre):
                raise ValueError('Motion centre must contain finite numeric coordinates.')
            centre = tuple(raw_centre)
            start, end = Pose(**row['start']), Pose(**row['end'])
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
                   for p in (start, end) for v in (p.x, p.y, p.heading)):
                raise ValueError('Invalid body-centre pose.')
            legacy = dict(row)
            legacy.pop('reference')
            centre_pivot = row['kind'] == 'pivot' and ref['pivot_axis'] == 'body_centre'
            if row['kind'] == 'line' and (centre or row['radius_m'] != 0):
                raise ValueError('Straight motion must not declare an orbital centre or radius.')
            if centre_pivot and centre and (len(centre) != 2 or not close(centre[0], start.x)
                                           or not close(centre[1], start.y)):
                raise ValueError('Body-centre pivot centre must be empty or match its fixed body centre.')
            if not centre_pivot:
                from dataclasses import asdict
                legacy['start'], legacy['end'] = (asdict(_offset(p, ref, 1)) for p in (start, end))
            one = dict(schema_version=2, model='directional_fillet_v1', minimum_radius_m=data['minimum_radius_m'],
                       pivot_allowed=data['pivot_allowed'], length_m=row['length_m'],
                       duration_sec=row['duration_sec'], motions=[legacy])
            checked = trajectory_from_dict(one).motions[0]
            if row['kind'] == 'pivot':
                if row.get('radius_m', 0) != 0:
                    raise ValueError('Pivot reference radius must be zero.')
                if not centre_pivot:
                    r = _offset(start, ref, 1)
                    if len(centre) != 2 or not close(centre[0], r.x) or not close(centre[1], r.y):
                        raise ValueError('Reference-axis pivot centre is inconsistent.')
            motion = replace(checked, start=start, end=end, centre=centre, reference=ref)
            if (motion.kind == 'arc' and motion.centre_orbit_radius_m <= EPS
                    and not data['pivot_allowed']):
                raise ValueError('Centre-stationary offset arc requires pivot permission.')
            if motions:
                previous = motions[-1].end
                if not close(previous.x, start.x) or not close(previous.y, start.y) or abs(math.remainder(previous.heading-start.heading, 2*math.pi)) > 1e-8:
                    raise ValueError('Discontinuous body-centre trajectory.')
            motions.append(motion)
        result = Trajectory(tuple(motions), float(data['minimum_radius_m']), data['pivot_allowed'])
        if not close(result.length_m, float(data['length_m'])) or not close(result.duration_sec, float(data['duration_sec'])):
            raise ValueError('Reference trajectory totals disagree.')
        return result
    except (KeyError, TypeError, ValueError, OverflowError, IndexError) as exc:
        raise TrajectoryError('invalid_evidence', str(exc)) from None
