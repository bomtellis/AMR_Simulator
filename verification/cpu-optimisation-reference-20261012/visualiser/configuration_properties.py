"""Configuration object fields and atomic, identity-preserving updates."""
from copy import deepcopy
import math

SECTIONS = {'amrs': ('Robots', 'id'), 'payloads': ('Payloads', 'name'),
            'lifts': ('Lifts', 'id'), 'tasks': ('Tasks', 'id'),
            'route_profiles': ('Route profiles', None)}
REQUIRED = {'amrs': {'speed_m_per_sec'}, 'payloads': {'weight_kg', 'allowed_carry_orientations'},
            'lifts': {'speed_floors_per_sec'}, 'tasks': {'pickup', 'dropoff', 'payload'}}


def records(config, target):
    section, keys = target
    if section not in SECTIONS or len(keys) != 1:
        raise ValueError('Select one configuration object.')
    key = keys[0]
    source = config.get(section, {} if section == 'route_profiles' else [])
    if section == 'route_profiles':
        if key not in source or not isinstance(source[key], dict):
            raise ValueError('The selected route profile is no longer available.')
    elif type(key) is not int or not 0 <= key < len(source):
        raise ValueError('The selected configuration object is no longer available.')
    return [(section, source[key])]


def specs(config, target):
    section = records(config, target)[0][0]
    return {
        'amrs': [('quantity', 'Fleet quantity', 'integer'), ('speed_m_per_sec', 'Travel speed (m/s)', 'positive'),
                 ('length_m', 'Robot length (m)', 'positive'), ('width_m', 'Robot width (m)', 'positive'),
                 ('height_m', 'Robot height (m)', 'positive'), ('weight_kg', 'Robot mass (kg)', 'nonnegative'),
                 ('motor_power_w', 'Motor power (W)', 'nonnegative'), ('battery_capacity_kwh', 'Battery capacity (kWh)', 'positive'),
                 ('battery_charge_rate_kw', 'Charging rate (kW)', 'positive'),
                 ('recharge_threshold_percent', 'Recharge threshold (%)', 'percent'), ('battery_soc_percent', 'Initial charge (%)', 'percent')],
        'payloads': [('weight_kg', 'Payload mass (kg)', 'nonnegative'), ('length_m', 'Payload length (m)', 'positive'),
                     ('width_m', 'Payload width (m)', 'positive'), ('height_m', 'Payload height (m)', 'positive'),
                     ('allowed_carry_orientations', 'Permitted carrying orientations', 'orientations'),
                     ('prefer_multi_stop_amr', 'Prefer multi-stop robot', 'bool')],
        'lifts': [('speed_floors_per_sec', 'Travel speed (floors/s)', 'positive'), ('door_time_sec', 'Door time (s)', 'nonnegative'),
                  ('boarding_time_sec', 'Boarding time (s)', 'nonnegative'),
                  ('capacity_length_m', 'Car length (m)', 'positive'), ('capacity_width_m', 'Car width (m)', 'positive'),
                  ('capacity_height_m', 'Car height (m)', 'positive'), ('car_mass_kg', 'Car mass (kg)', 'nonnegative'),
                  ('health_percent', 'Initial health (%)', 'percent'),
                  ('health_loss_per_journey_percent', 'Health loss per journey (%)', 'percent'),
                  ('mean_time_between_failures_hours', 'Mean time between failures (h)', 'nonnegative'),
                  ('mean_time_to_repair_hours', 'Mean repair time (h)', 'nonnegative')],
        'tasks': [('pickup', 'Pickup location', 'location'), ('dropoff', 'Dropoff location', 'location'),
                  ('payload', 'Payload', 'payload'), ('route_profile', 'Delivery route profile', 'profile'),
                  ('return_enabled', 'Create a return', 'bool'), ('return_payload', 'Return payload', 'payload'),
                  ('return_route_profile', 'Return route profile', 'profile')],
        'route_profiles': [('allowed_nodes', 'Allowed nodes', 'nodes'), ('allowed_edges', 'Allowed directed edges', 'edges'),
                           ('allowed_lifts', 'Allowed lifts', 'lifts')],
    }[section]


def choices(config, kind):
    if kind == 'location':
        return [(r['name'], r['name']) for r in config.get('locations', [])]
    if kind == 'payload':
        return [(r['name'], r['name']) for r in config.get('payloads', [])]
    if kind == 'profile':
        return [(name, name) for name in config.get('route_profiles', {})]
    if kind == 'orientations':
        return [('Lengthways', 'lengthways'), ('Sideways', 'sideways')]
    if kind == 'lifts':
        return [(r['id'], r['id']) for r in config.get('lifts', [])]
    points = {r['name'] for r in config.get('locations', []) + config.get('corridors', {}).get('nodes', [])}
    points.update(f"{lift['id']}-F{floor}" for lift in config.get('lifts', []) for floor in lift.get('floor_locations', {}))
    if kind == 'nodes':
        return [(name, name) for name in sorted(points)]
    if kind == 'edges':
        pairs = set()
        for row in config.get('corridors', {}).get('edges', []):
            pairs.add((row['from'], row['to']))
            if row.get('bidirectional', True):
                pairs.add((row['to'], row['from']))
        return [(f'{a} → {b}', [a, b]) for a, b in sorted(pairs)]
    return []


def apply(config, target, changes):
    fields = {key: kind for key, _label, kind in specs(config, target)}
    if not changes or any(key not in fields for key in changes):
        raise ValueError('Choose supported configuration properties.')
    result = deepcopy(config)
    row = records(result, target)[0][1]
    for key, value in changes.items():
        kind = fields[key]
        if value is None:
            if key in REQUIRED.get(target[0], set()):
                raise ValueError(f'{key} requires an explicit value.')
            row.pop(key, None)
            continue
        if kind == 'bool':
            if type(value) is not bool:
                raise ValueError('Choose Yes, No or the inherited default.')
        elif kind in {'integer', 'positive', 'nonnegative', 'percent'}:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f'{key} must be numeric.') from None
            if not math.isfinite(value) or value < 0 or (kind in {'integer', 'positive'} and value <= 0) or (kind == 'percent' and value > 100):
                raise ValueError(f'{key} is outside its allowed range.')
            if kind == 'integer':
                if not value.is_integer():
                    raise ValueError('Fleet quantity must be a whole number.')
                value = int(value)
        elif kind in {'location', 'payload', 'profile'}:
            if value not in [data for _label, data in choices(config, kind)]:
                raise ValueError(f'{key} must refer to an existing {kind}.')
        else:
            if not isinstance(value, list):
                raise ValueError(f'{key} must be a list of selected entries.')
            allowed = [data for _label, data in choices(config, kind)]
            for entry in value:
                if kind == 'edges':
                    nodes = {data for _label, data in choices(config, 'nodes')}
                    # Profiles can also name implicit graph links. Check the
                    # endpoints here; connectivity belongs to project checks.
                    valid = isinstance(entry, list) and len(entry) == 2 and all(n in nodes for n in entry)
                else:
                    valid = entry in allowed
                if not valid:
                    raise ValueError(f'{key} contains an unknown or invalid entry: {entry}')
            if kind == 'orientations' and not value:
                raise ValueError('Select at least one carrying orientation.')
        row[key] = value
        if target[0] == 'lifts' and key == 'speed_floors_per_sec':
            height = float(config.get('building', {}).get('floor_height_m', 4.0))
            if not math.isfinite(height) or height <= 0:
                raise ValueError('Set a positive building floor height before changing lift speed.')
            # The simulator reads floors/s; keep the legacy dialog's m/s
            # representation consistent so a later dialog edit cannot reset it.
            row['speed_m_per_sec'] = value * height
    return result
