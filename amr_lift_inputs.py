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


def lift_structure_findings(config, *, require_complete=False):
    """Validate explicit structure; permit missing fields only in editor drafts."""
    if not isinstance(config, dict):
        return
    lifts = config.get('lifts', [])
    if not isinstance(lifts, list):
        yield '/lifts', 'Lifts must be a list of JSON objects.'
        return
    point_names = set()
    corridors = config.get('corridors', {})
    for rows in (config.get('locations', []), corridors.get('nodes', []) if isinstance(corridors, dict) else []):
        if isinstance(rows, list):
            point_names.update(row['name'] for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str))
    identities = set()
    for index, lift in enumerate(lifts):
        path = f'/lifts/{index}'
        if not isinstance(lift, dict):
            yield path, 'Each lift must be a JSON object.'
            continue
        if require_complete:
            for key in ('id', 'served_floors', 'floor_locations'):
                if key not in lift:
                    yield path + '/' + key, f'{key} is required for a runnable lift.'
        identity = lift.get('id')
        valid_identity = isinstance(identity, str) and bool(identity) and identity == identity.strip()
        if 'id' in lift:
            if not valid_identity:
                yield path + '/id', 'Lift id must be a nonblank string without surrounding whitespace.'
            elif identity in identities:
                yield path + '/id', f'Duplicate lift id: {identity}.'
            else:
                identities.add(identity)
        floors = lift.get('served_floors')
        valid_floors = (isinstance(floors, list) and bool(floors)
                        and all(type(floor) is int for floor in floors))
        if valid_floors:
            valid_floors = len(set(floors)) == len(floors)
        if 'served_floors' in lift and not valid_floors:
            yield path + '/served_floors', 'served_floors must be a nonempty list of unique JSON integers, including negative floors where needed.'
        start = lift.get('start_floor', 0)
        if type(start) is not int or (valid_floors and start not in floors):
            yield path + '/start_floor', 'start_floor must be a JSON integer included in served_floors; omission means floor 0.'
        positions = lift.get('floor_locations')
        if 'floor_locations' not in lift:
            continue
        if not isinstance(positions, dict):
            yield path + '/floor_locations', 'floor_locations must be an object keyed by canonical integer floor labels.'
            continue
        keys = set()
        for key, position in positions.items():
            try:
                floor = int(key)
                valid_key = isinstance(key, str) and key == str(floor)
            except (TypeError, ValueError, OverflowError):
                valid_key = False
            if not valid_key or floor in keys:
                yield path + '/floor_locations', 'Floor keys must be unique canonical integers; aliases such as 01, +1 and 1.0 are invalid.'
                continue
            keys.add(floor)
            valid_position = isinstance(position, dict)
            if valid_position:
                for axis in ('x', 'y'):
                    try:
                        value = position[axis]
                        valid_position &= not isinstance(value, bool) and math.isfinite(float(value))
                    except (KeyError, TypeError, ValueError, OverflowError):
                        valid_position = False
            if not valid_position:
                escaped = str(key).replace('~', '~0').replace('/', '~1')
                yield path + '/floor_locations/' + escaped, 'Each floor position must contain finite numeric x and y coordinates in metres; booleans are invalid.'
        if valid_floors and keys != set(floors):
            yield path + '/floor_locations', 'Floor positions must match served_floors exactly; missing or extra positions would describe different editor and simulation graphs.'
        if valid_identity and valid_floors:
            for floor in floors:
                name = f'{identity}-F{floor}'
                if name in point_names:
                    yield path + '/id', f'Lift stop {name} conflicts with another graph point.'
                point_names.add(name)


def lift_input_findings(config, *, require_speed=False, require_complete=False):
    yield from lift_structure_findings(config, require_complete=require_complete)
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


def validate_lift_inputs(config, *, require_speed=False, require_complete=False):
    findings = list(lift_input_findings(config, require_speed=require_speed, require_complete=require_complete))
    if findings:
        raise ValueError('Invalid lift inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))


def lift_display_speed_m_per_sec(lift, floor_height_m):
    """Show effective runtime speed; use metadata only for an incomplete draft."""
    if 'speed_floors_per_sec' in lift:
        return float(lift['speed_floors_per_sec']) * float(floor_height_m)
    if 'speed_m_per_sec' in lift:
        return float(lift['speed_m_per_sec'])
    return 0.45 * float(floor_height_m)
