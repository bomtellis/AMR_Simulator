"""Explicit body-frame conventions for robot turning-reference configuration."""
import math


DEFAULT_REFERENCE_POINT = dict(longitudinal_mm=0., lateral_mm=0.,
                               timing_reference='turning_reference_point', pivot_axis='body_centre')


def reference_point_options(manoeuvring):
    """Planner arguments; omitted configuration retains the centred legacy model.

    Positive longitudinal is forwards; positive lateral is body-left. Travel
    speeds and radii refer to the configured point. Pivot axis is independent and
    explicit, so an offset never silently changes an existing pivot convention.
    """
    if not isinstance(manoeuvring, dict):
        raise ValueError('Manoeuvring parameters must be an object.')
    value = manoeuvring.get('reference_point', DEFAULT_REFERENCE_POINT)
    if not isinstance(value, dict) or set(value) != set(DEFAULT_REFERENCE_POINT):
        raise ValueError('reference_point requires longitudinal_mm, lateral_mm, timing_reference and pivot_axis.')
    for key in ('longitudinal_mm', 'lateral_mm'):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number):
            raise ValueError(f'reference_point.{key} must be a finite signed millimetre offset.')
    if value['timing_reference'] != 'turning_reference_point':
        raise ValueError('reference_point.timing_reference must explicitly be turning_reference_point.')
    if value['pivot_axis'] not in ('body_centre', 'reference_point'):
        raise ValueError('reference_point.pivot_axis must be body_centre or reference_point.')
    return dict(reference_longitudinal_mm=float(value['longitudinal_mm']),
                reference_lateral_mm=float(value['lateral_mm']), pivot_axis=value['pivot_axis'])
