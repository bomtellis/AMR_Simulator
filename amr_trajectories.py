"""Explicit planar forward trajectories for engineering planning and display.

Metres, seconds and radians internally. No graph routing, automatic obstacle
avoidance, reversing or traffic claims are implied by a successful trajectory.
"""
from dataclasses import asdict, dataclass
import math

EPS = 1e-10


class TrajectoryError(ValueError):
    def __init__(self, reason, detail):
        self.reason = reason
        super().__init__(f'{reason}: {detail}')


def _number(value, name, minimum=0, positive=False):
    try:
        result = float(value)
        if isinstance(value, bool) or not math.isfinite(result) or result < minimum or (positive and result == minimum):
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError):
        raise TrajectoryError('invalid_input', f'{name} must be finite and {">" if positive else ">="} {minimum}.') from None


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    heading: float


@dataclass(frozen=True)
class Motion:
    kind: str
    start: Pose
    end: Pose
    length_m: float
    duration_sec: float
    sweep_rad: float = 0.0
    radius_m: float = 0.0
    centre: tuple = ()

    def pose_at(self, fraction):
        f = _number(fraction, 'fraction')
        if f > 1:
            raise TrajectoryError('invalid_input', 'fraction must be <= 1.')
        if f == 0:
            return self.start
        if f == 1:
            return self.end
        heading = self.start.heading + self.sweep_rad * f
        if self.kind == 'arc':
            angle = math.atan2(self.start.y - self.centre[1], self.start.x - self.centre[0]) + self.sweep_rad * f
            return Pose(self.centre[0] + self.radius_m * math.cos(angle),
                        self.centre[1] + self.radius_m * math.sin(angle), heading)
        return Pose(self.start.x + f * (self.end.x - self.start.x),
                    self.start.y + f * (self.end.y - self.start.y), heading)


@dataclass(frozen=True)
class Trajectory:
    motions: tuple
    minimum_radius_m: float
    pivot_allowed: bool

    @property
    def length_m(self):
        return sum(m.length_m for m in self.motions)

    @property
    def duration_sec(self):
        return sum(m.duration_sec for m in self.motions)

    def to_dict(self):
        return {'schema_version': 1, 'model': 'forward_fillet_v1',
                'minimum_radius_m': self.minimum_radius_m, 'pivot_allowed': self.pivot_allowed,
                'length_m': self.length_m, 'duration_sec': self.duration_sec,
                'motions': [asdict(m) for m in self.motions]}

    def poses(self, step_m=0.1, step_rad=math.radians(5)):
        step_m = _number(step_m, 'step_m', positive=True)
        step_rad = _number(step_rad, 'step_rad', positive=True)
        result = []
        for motion in self.motions:
            count = max(1, math.ceil(motion.length_m / step_m), math.ceil(abs(motion.sweep_rad) / step_rad))
            if len(result) + count > 100000:
                raise TrajectoryError('search_limit', 'Display sample budget exceeded.')
            if not result:
                result.append(motion.start)
            result.extend(motion.pose_at(i / count) for i in range(1, count + 1))
        return result


def plan_trajectory(points, *, minimum_radius_m, speed_m_per_sec, pivot_allowed, pivot_speed_deg_per_sec):
    """Fillet a requested polyline; never shorten the specified minimum radius.

    If allowed, a turn that cannot fit becomes an explicit stationary pivot.
    This checks the requested path only, not existence of alternative routes.
    Endpoint headings follow the first and last segments.
    """
    radius = _number(minimum_radius_m, 'minimum_radius_m', positive=True)
    speed = _number(speed_m_per_sec, 'speed_m_per_sec', positive=True)
    angular_speed = math.radians(_number(pivot_speed_deg_per_sec, 'pivot_speed_deg_per_sec', positive=True))
    if not isinstance(pivot_allowed, bool):
        raise TrajectoryError('invalid_input', 'pivot_allowed must be an explicit boolean.')
    if not isinstance(points, (list, tuple)) or not 2 <= len(points) <= 10000:
        raise TrajectoryError('invalid_input', 'Provide 2 to 10000 route points.')
    route = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise TrajectoryError('invalid_input', 'Each route point must be an x/y pair.')
        try:
            pair = tuple(float(v) for v in point)
            if any(isinstance(v, bool) for v in point) or not all(math.isfinite(v) and abs(v) <= 1e9 for v in pair):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise TrajectoryError('invalid_input', 'Route coordinates must be finite numbers within ±1e9 m.') from None
        route.append(pair)
    lengths, headings, directions = [], [], []
    for a, b in zip(route, route[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        distance = math.hypot(dx, dy)
        if not math.isfinite(distance) or distance <= EPS:
            raise TrajectoryError('invalid_input', 'Consecutive points must be distinct with finite separation.')
        lengths.append(distance)
        headings.append(math.atan2(dy, dx))
        directions.append((dx / distance, dy / distance))
    sweeps, trims, pivots = {}, {}, set()
    for i in range(1, len(route) - 1):
        delta = math.atan2(math.sin(headings[i] - headings[i-1]), math.cos(headings[i] - headings[i-1]))
        sweeps[i] = delta
        if abs(abs(delta) - math.pi) < EPS:
            if not pivot_allowed:
                raise TrajectoryError('infeasible_route', f'Reversal at point {i + 1} needs a pivot or a different path.')
            pivots.add(i)
            trims[i] = 0.0
        else:
            trims[i] = radius * math.tan(abs(delta) / 2)
    for i, distance in enumerate(lengths):
        if trims.get(i, 0) + trims.get(i + 1, 0) > distance + EPS:
            if not pivot_allowed:
                raise TrajectoryError('infeasible_route', f'Segment {i + 1} is too short for the specified radius.')
            for corner in (i, i + 1):
                if corner in trims:
                    pivots.add(corner)
                    trims[corner] = 0.0
    motions = []
    current = Pose(*route[0], headings[0])

    def line_to(point, heading):
        nonlocal current
        end = Pose(*point, heading)
        distance = math.hypot(end.x - current.x, end.y - current.y)
        if distance > EPS:
            motions.append(Motion('line', Pose(current.x, current.y, heading), end, distance, distance / speed))
        current = end

    for i in range(1, len(route) - 1):
        corner, delta, trim = route[i], sweeps[i], trims[i]
        u, v = directions[i-1], directions[i]
        entry = (corner[0] - u[0] * trim, corner[1] - u[1] * trim)
        line_to(entry, headings[i-1])
        end_heading = current.heading + delta
        if i in pivots:
            end = Pose(*corner, end_heading)
            motions.append(Motion('pivot', current, end, 0.0, abs(delta) / angular_speed, delta))
            current = end
        elif abs(delta) > EPS:
            sign = 1 if delta > 0 else -1
            centre = (entry[0] - u[1] * radius * sign, entry[1] + u[0] * radius * sign)
            end = Pose(corner[0] + v[0] * trim, corner[1] + v[1] * trim, end_heading)
            length = radius * abs(delta)
            motions.append(Motion('arc', current, end, length, length / speed, delta, radius, centre))
            current = end
    line_to(route[-1], headings[-1])
    if not all(math.isfinite(x) for m in motions for x in (m.length_m, m.duration_sec, m.end.x, m.end.y)):
        raise TrajectoryError('invalid_input', 'Trajectory arithmetic overflowed.')
    return Trajectory(tuple(motions), radius, pivot_allowed)


def footprint(pose, length_m, width_m, margin_m=0):
    margin = _number(margin_m, 'margin_m')
    length = _number(length_m, 'length_m', positive=True) / 2 + margin
    width = _number(width_m, 'width_m', positive=True) / 2 + margin
    c, s = math.cos(pose.heading), math.sin(pose.heading)
    points = [(pose.x + x*c - y*s, pose.y + x*s + y*c)
              for x, y in [(-length, -width), (length, -width), (length, width), (-length, width)]]
    if not all(math.isfinite(v) and abs(v) <= 1e9 for point in points for v in point):
        raise TrajectoryError('invalid_input', 'Footprint extends beyond the supported ±1e9 m coordinate range.')
    return points


def _hull(points):
    points = sorted(set(points))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    def half(seq):
        result = []
        for p in seq:
            while len(result) >= 2 and cross(result[-2], result[-1], p) <= 0:
                result.pop()
            result.append(p)
        return result
    return half(points)[:-1] + half(reversed(points))[:-1]


def _overlaps(polygon, box):
    a, b, c, d = box
    rectangle = [(a,b), (c,b), (c,d), (a,d)]
    for shape in (polygon, rectangle):
        for p, q in zip(shape, shape[1:] + shape[:1]):
            axis = (p[1]-q[1], q[0]-p[0])
            size = math.hypot(*axis)
            if size <= EPS:
                continue
            axis = (axis[0]/size, axis[1]/size)
            project = lambda points: [x*axis[0]+y*axis[1] for x,y in points]
            first, second = project(polygon), project(rectangle)
            # Exact contact is allowed; required clearance belongs in footprint.
            if max(first) <= min(second) + EPS or max(second) <= min(first) + EPS:
                return False
    return True


def check_clearance(trajectory, *, length_m, width_m, obstacles, clearance_m=0,
                    resolution_m=0.001, max_checks=50000):
    """Conservatively certify a centred rectangular loaded footprint.

    Lines use an exact swept convex hull. Curves/pivots recursively enclose every
    corner's continuous movement; sampled poses alone never establish clearance.
    A tight interval that cannot be certified is unresolved, never silently clear.
    Obstacles are explicit axis-aligned rectangles; drawings are not obstacles.
    """
    length = _number(length_m, 'length_m', positive=True)
    width = _number(width_m, 'width_m', positive=True)
    clearance = _number(clearance_m, 'clearance_m')
    resolution = _number(resolution_m, 'resolution_m', positive=True)
    if isinstance(max_checks, bool) or not isinstance(max_checks, int) or max_checks < 1:
        raise TrajectoryError('invalid_input', 'max_checks must be a positive integer.')
    if trajectory.motions:
        footprint(trajectory.motions[0].start, length, width, clearance)
    boxes = []
    for box in obstacles:
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise TrajectoryError('invalid_input', 'Obstacles must be xmin/ymin/xmax/ymax rectangles.')
        try:
            a,b,c,d = map(float, box)
            if any(isinstance(v, bool) for v in box) or not all(math.isfinite(v) and abs(v) <= 1e9 for v in (a,b,c,d)) or a >= c or b >= d:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise TrajectoryError('invalid_input', 'Obstacle bounds must be finite and ordered.') from None
        boxes.append((a,b,c,d))
    checks = 0
    corner_radius = math.hypot(length/2 + clearance, width/2 + clearance)
    for index, motion in enumerate(trajectory.motions):
        for obstacle, box in enumerate(boxes):
            stack = [(0., 1.)]
            while stack:
                if checks >= max_checks:
                    return {'status': 'search_limit', 'motion': index, 'obstacle': obstacle, 'checks': checks}
                checks += 1
                low, high = stack.pop()
                if motion.kind == 'line':
                    swept = _hull(footprint(motion.start, length, width, clearance) + footprint(motion.end, length, width, clearance))
                    if _overlaps(swept, box):
                        return {'status': 'collision', 'motion': index, 'obstacle': obstacle, 'checks': checks}
                    continue
                mid = (low + high) / 2
                poses = [motion.pose_at(f) for f in (low, mid, high)]
                if any(_overlaps(footprint(p, length, width, clearance), box) for p in poses):
                    return {'status': 'collision', 'motion': index, 'obstacle': obstacle, 'checks': checks}
                bound = 2 * (motion.radius_m + corner_radius) * math.sin(abs(motion.sweep_rad) * (high-low) / 4)
                if not _overlaps(footprint(poses[1], length, width, clearance + bound), box):
                    continue
                if bound <= resolution:
                    return {'status': 'clearance_unresolved', 'motion': index, 'obstacle': obstacle, 'checks': checks}
                stack.extend([(mid, high), (low, mid)])
    return {'status': 'clear', 'checks': checks}
