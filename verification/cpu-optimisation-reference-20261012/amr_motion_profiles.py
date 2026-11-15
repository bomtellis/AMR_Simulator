"""Analytic acceleration/braking profiles for detailed robot movement.

Scalar distances are metres for translation and radians for rotation. Profiles
describe a *given feasible path*, not collision avoidance or steering geometry.
No robot engineering parameters are inferred. Empty and loaded settings are
separate complete sets; legacy values must be migrated explicitly by the caller.
"""
from dataclasses import dataclass, field
import math


class MotionProfileError(ValueError):
    def __init__(self, detail, reason='invalid_input'):
        self.reason = reason
        super().__init__(f'{reason}: {detail}')


def _number(value, name, *, positive=False):
    if isinstance(value, bool):
        raise MotionProfileError(f'{name} must be a finite number.')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise MotionProfileError(f'{name} must be a finite number.') from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise MotionProfileError(f'{name} must be finite and {"positive" if positive else "nonnegative"}.')
    return result


def stopping_distance(speed, braking):
    """Distance to rest under constant braking, excluding reaction delay."""
    speed = _number(speed, 'speed')
    braking = _number(braking, 'braking', positive=True)
    result = speed * (speed / braking) / 2
    if not math.isfinite(result):
        raise MotionProfileError('Stopping distance exceeds the numeric range.')
    return result


def turn_speed_limit(max_turn_speed_m_per_sec, lateral_acceleration_m_per_sec2,
                     reference_radius_m):
    """Reference-point speed cap satisfying both configured turn constraints."""
    cap = _number(max_turn_speed_m_per_sec, 'max_turn_speed_m_per_sec', positive=True)
    acceleration = _number(lateral_acceleration_m_per_sec2,
                           'lateral_acceleration_m_per_sec2', positive=True)
    radius = _number(reference_radius_m, 'reference_radius_m', positive=True)
    # Separate roots avoid overflow in acceleration * radius.
    return min(cap, math.sqrt(acceleration) * math.sqrt(radius))


@dataclass(frozen=True)
class MotionProfile:
    """Fastest scalar trapezoidal/triangular profile for fixed boundary speeds.

    Boundary speeds permit continuous passage between compatible path segments.
    Callers must choose boundary speeds consistent with adjacent segments and
    stop at pivots/direction changes. This class does not make that path decision.
    Time/distance lookups clamp beyond the endpoint; negative/nonfinite inputs
    are rejected. Zero distance requires zero boundary speeds.
    """
    distance: float
    max_speed: float
    acceleration: float
    braking: float
    start_speed: float = 0.0
    end_speed: float = 0.0
    peak_speed: float = field(init=False)
    acceleration_time: float = field(init=False)
    cruise_time: float = field(init=False)
    braking_time: float = field(init=False)
    acceleration_distance: float = field(init=False)
    cruise_distance: float = field(init=False)
    braking_distance: float = field(init=False)

    def __post_init__(self):
        for name in ('distance', 'max_speed', 'acceleration', 'braking', 'start_speed', 'end_speed'):
            object.__setattr__(self, name, _number(getattr(self, name), name,
                                                 positive=name in ('max_speed', 'acceleration', 'braking')))
        if max(self.start_speed, self.end_speed) > self.max_speed:
            raise MotionProfileError('Boundary speed exceeds maximum speed.', 'infeasible_motion')
        if self.distance == 0 and (self.start_speed or self.end_speed):
            raise MotionProfileError('Zero distance requires zero boundary speeds.', 'infeasible_motion')
        u, v, a, b = self.start_speed, self.end_speed, self.acceleration, self.braking
        minimum = ((v - u) * ((v + u) / a) / 2 if v >= u
                   else (u - v) * ((u + v) / b) / 2)
        if minimum > self.distance and minimum - self.distance > 4 * math.ulp(max(minimum, self.distance)):
            raise MotionProfileError('Insufficient distance for the boundary speed change.', 'infeasible_motion')
        # Solve d=(p²-u²)/(2a)+(p²-v²)/(2b), then cap the peak.
        # Ratios keep the weights bounded for widely differing a and b.
        scale = max(a, b)
        wa, wb = a / scale, b / scale
        peak_squared = (2 * self.distance * min(a, b) / (1 + min(a, b) / scale)
                        + (wb * u * u + wa * v * v) / (wa + wb))
        if not math.isfinite(peak_squared):
            raise MotionProfileError('Motion profile exceeds the numeric range.')
        peak = min(self.max_speed, max(u, v, math.sqrt(peak_squared)))
        da = (peak - u) * ((peak + u) / a) / 2
        db = (peak - v) * ((peak + v) / b) / 2
        dc = max(0.0, self.distance - da - db)
        ta, tb = (peak - u) / a, (peak - v) / b
        tc = dc / peak if peak else 0.0
        values = dict(peak_speed=peak, acceleration_time=ta, cruise_time=tc,
                      braking_time=tb, acceleration_distance=da,
                      cruise_distance=dc, braking_distance=db)
        if not all(math.isfinite(x) for x in values.values()) or not math.isfinite(ta + tc + tb):
            raise MotionProfileError('Motion profile exceeds the numeric range.')
        if self.distance > 0 and (peak == 0 or ta + tc + tb == 0):
            raise MotionProfileError('Motion profile is below the numeric resolution.')
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def duration_sec(self):
        return self.acceleration_time + self.cruise_time + self.braking_time

    def to_dict(self):
        """Constructor parameters only, sufficient to reproduce exact playback."""
        return {name: getattr(self, name) for name in
                ('distance', 'max_speed', 'acceleration', 'braking', 'start_speed', 'end_speed')}

    def speed_at_time(self, seconds):
        t = _number(seconds, 'seconds')
        if t >= self.duration_sec:
            return self.end_speed
        if t < self.acceleration_time:
            return self.start_speed + self.acceleration * t
        if t < self.acceleration_time + self.cruise_time:
            return self.peak_speed
        remaining = self.duration_sec - t
        return self.end_speed + self.braking * remaining

    def distance_at_time(self, seconds):
        t = _number(seconds, 'seconds')
        if t >= self.duration_sec:
            return self.distance
        if t < self.acceleration_time:
            return self.start_speed * t + self.acceleration * t * t / 2
        if t < self.acceleration_time + self.cruise_time:
            return self.acceleration_distance + self.peak_speed * (t - self.acceleration_time)
        remaining = self.duration_sec - t
        return max(0.0, self.distance - self.end_speed * remaining - self.braking * remaining * remaining / 2)

    def fraction_at_time(self, seconds):
        """Path fraction for Motion.pose_at; stationary zero-length motion is done."""
        distance = self.distance_at_time(seconds)
        return min(1.0, max(0.0, distance / self.distance)) if self.distance else 1.0

    def time_at_distance(self, distance):
        d = _number(distance, 'distance')
        if d >= self.distance:
            return self.duration_sec
        if d == 0:
            return 0.0
        if d < self.acceleration_distance:
            # Rationalised quadratic root avoids subtracting similar numbers.
            return 2 * d / (self.start_speed + math.sqrt(self.start_speed ** 2 + 2 * self.acceleration * d))
        if d < self.acceleration_distance + self.cruise_distance:
            return self.acceleration_time + (d - self.acceleration_distance) / self.peak_speed
        remaining = self.distance - d
        remaining_time = 2 * remaining / (self.end_speed + math.sqrt(self.end_speed ** 2 + 2 * self.braking * remaining))
        return self.duration_sec - remaining_time


@dataclass(frozen=True)
class MotionSettings:
    forward_speed_m_per_sec: float
    reverse_speed_m_per_sec: float
    acceleration_m_per_sec2: float
    braking_m_per_sec2: float
    maximum_turn_speed_m_per_sec: float
    lateral_acceleration_m_per_sec2: float
    pivot_allowed: bool
    lateral_allowed: bool
    lateral_speed_m_per_sec: float | None = None
    rotation_speed_deg_per_sec: float | None = None
    angular_acceleration_deg_per_sec2: float | None = None
    angular_braking_deg_per_sec2: float | None = None
    # Geometry may use the separately explicit manoeuvring radius when omitted.
    # Timing does not invent or substitute a radius for a requested arc.
    minimum_radius_m: float | None = None
    # Unversioned configurations and direct callers historically allowed reverse.
    # Versioned input contracts require an explicit value in each load state.
    reverse_allowed: bool = True

    def __post_init__(self):
        for name in ('pivot_allowed', 'lateral_allowed', 'reverse_allowed'):
            if not isinstance(getattr(self, name), bool):
                raise MotionProfileError(f'{name} must be an explicit boolean.')
        required = ['forward_speed_m_per_sec', 'reverse_speed_m_per_sec',
                    'acceleration_m_per_sec2', 'braking_m_per_sec2',
                    'maximum_turn_speed_m_per_sec', 'lateral_acceleration_m_per_sec2']
        if self.lateral_allowed:
            required.append('lateral_speed_m_per_sec')
        if self.pivot_allowed:
            required.extend(('rotation_speed_deg_per_sec', 'angular_acceleration_deg_per_sec2',
                             'angular_braking_deg_per_sec2'))
        for name in self.__dataclass_fields__:
            if name in ('pivot_allowed', 'lateral_allowed', 'reverse_allowed'):
                continue
            value = getattr(self, name)
            if value is not None or name in required:
                object.__setattr__(self, name, _number(value, name, positive=True))


def select_motion_settings(movement, *, loaded):
    """Select a complete empty/loaded set; no inheritance between operating states.

    Both sets are validated, so a malformed unused set cannot silently survive
    input checks. Additional movement geometry belongs outside these sets.
    Legacy reverse permission is resolved by amr_movement_inputs; its resolver
    exposes the compatibility decisions for checks and explicit migration.
    """
    if not isinstance(loaded, bool):
        raise MotionProfileError('loaded must be an explicit boolean.')
    from amr_movement_inputs import resolve_movement_inputs
    resolved = resolve_movement_inputs(movement)['movement']
    return MotionSettings(**resolved['loaded' if loaded else 'empty'])


def profile_for_movement(settings, *, movement, distance, start_speed=0, end_speed=0,
                         turn_radius_m=None):
    """Build a profile; distance is metres, or positive radians for a pivot.

    Arc radius refers to the modelled centre path. For a fixed-radius arc,
    yaw speed is v/r and yaw acceleration is a/r: both linear and angular
    limits apply, even when stationary pivots are forbidden.
    """
    if not isinstance(settings, MotionSettings):
        raise MotionProfileError('settings must be validated MotionSettings.')
    a, b = settings.acceleration_m_per_sec2, settings.braking_m_per_sec2
    if movement == 'forward':
        speed = settings.forward_speed_m_per_sec
    elif movement == 'reverse':
        if not settings.reverse_allowed:
            raise MotionProfileError('This movement state does not permit reversing.', 'infeasible_motion')
        speed = settings.reverse_speed_m_per_sec
    elif movement == 'lateral' and settings.lateral_allowed:
        speed = settings.lateral_speed_m_per_sec
    elif movement == 'pivot' and settings.pivot_allowed:
        speed = math.radians(settings.rotation_speed_deg_per_sec)
        a = math.radians(settings.angular_acceleration_deg_per_sec2)
        b = math.radians(settings.angular_braking_deg_per_sec2)
    else:
        raise MotionProfileError(f'Movement {movement!r} is unknown or not permitted.')
    if turn_radius_m is not None:
        if movement not in ('forward', 'reverse'):
            raise MotionProfileError('Turning radius applies only to forward/reverse travel.')
        radius = _number(turn_radius_m, 'turn_radius_m', positive=True)
        angular = [math.radians(_number(getattr(settings, name), name, positive=True))
                   for name in ('rotation_speed_deg_per_sec',
                                'angular_acceleration_deg_per_sec2',
                                'angular_braking_deg_per_sec2')]
        speed = min(speed, turn_speed_limit(settings.maximum_turn_speed_m_per_sec,
                                           settings.lateral_acceleration_m_per_sec2, radius),
                    angular[0] * radius)
        a = min(a, angular[1] * radius)
        b = min(b, angular[2] * radius)
    return MotionProfile(distance, speed, a, b, start_speed, end_speed)
