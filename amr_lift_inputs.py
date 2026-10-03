"""Lift scalar contracts shared by import, preflight and simulation.

Floors/second remains the simulation speed. Metres/second is editor metadata;
import never rewrites the authoritative speed or silently resolves a conflict.
"""
import math


# name: (minimum, maximum, minimum is exclusive, units)
LIFT_SCALARS = {
    'speed_floors_per_sec': (0, None, True, 'floors/second'),
    'speed_m_per_sec': (0, None, True, 'metres/second'),
    'door_time_sec': (0, None, False, 'seconds'),
    'boarding_time_sec': (0, None, False, 'seconds'),
    'capacity_length_m': (0, None, True, 'metres'),
    'capacity_width_m': (0, None, True, 'metres'),
    'capacity_height_m': (0, None, True, 'metres'),
    'car_mass_kg': (0, None, False, 'kilograms'),
    'counterweight_ratio': (0, None, False, 'ratio to empty car mass'),
    'travel_efficiency': (0, 1, True, 'fraction'),
    'door_power_w': (0, None, False, 'watts'),
    'standby_power_w': (0, None, False, 'watts'),
    'regen_efficiency': (0, 1, False, 'fraction'),
    'health_percent': (0, 100, False, 'percent'),
    'health_loss_per_journey_percent': (0, 100, False, 'percentage points'),
    'mean_time_between_failures_hours': (0, None, False, 'hours'),
    'mean_time_to_repair_hours': (0, None, False, 'hours'),
    'minimum_operational_health_percent': (0, 100, False, 'percent'),
    'health_speed_penalty_at_zero': (0.05, 1, False, 'speed fraction'),
}


def lift_input_findings(config, *, require_speed=False):
    if not isinstance(config, dict) or not isinstance(config.get('lifts', []), list):
        return
    for index, lift in enumerate(config.get('lifts', [])):
        if not isinstance(lift, dict):
            continue
        prefix = f'/lifts/{index}'
        if require_speed and 'speed_floors_per_sec' not in lift:
            yield prefix + '/speed_floors_per_sec', 'speed_floors_per_sec is required; metres/second metadata alone cannot define simulation speed.'
        for key, (minimum, maximum, exclusive, units) in LIFT_SCALARS.items():
            if key not in lift:
                continue
            raw = lift[key]
            try:
                value = float(raw)
                valid = (not isinstance(raw, bool) and math.isfinite(value)
                         and (value > minimum if exclusive else value >= minimum)
                         and (maximum is None or value <= maximum))
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                bounds = f'{">" if exclusive else ">="} {minimum}'
                if maximum is not None:
                    bounds += f' and <= {maximum}'
                yield prefix + '/' + key, f'{key} must be finite, {bounds} {units}; booleans are not numbers.'


def validate_lift_inputs(config, *, require_speed=False):
    findings = list(lift_input_findings(config, require_speed=require_speed))
    if findings:
        raise ValueError('Invalid lift inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))


def lift_display_speed_m_per_sec(lift, floor_height_m):
    """Show effective runtime speed; use metadata only for an incomplete draft."""
    if 'speed_floors_per_sec' in lift:
        return float(lift['speed_floors_per_sec']) * float(floor_height_m)
    if 'speed_m_per_sec' in lift:
        return float(lift['speed_m_per_sec'])
    return 0.45 * float(floor_height_m)
