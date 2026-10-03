"""Atomic edits of explicit layout properties; object identities stay stable."""
from copy import deepcopy
import hashlib
import json
import math


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def records(config, target):
    kind, keys = target
    if kind not in {'points', 'edges'}:
        from configuration_properties import records as config_records
        return config_records(config, target)
    if kind == 'edges':
        edges = config.get('corridors', {}).get('edges', [])
        if not keys or any(type(i) is not int or not 0 <= i < len(edges) for i in keys):
            raise ValueError('The selected corridor record is no longer available.')
        return [('edge', edges[i]) for i in keys]
    if kind != 'points' or not keys:
        raise ValueError('Select a layout object first.')
    result = []
    for name in keys:
        matches = []
        for section, item_kind in [('locations', 'location'), ('departments', 'department')]:
            matches.extend((item_kind, row) for row in config.get(section, []) if row.get('name') == name)
        matches.extend(('corridor_node', row) for row in config.get('corridors', {}).get('nodes', []) if row.get('name') == name)
        for lift in config.get('lifts', []):
            matches.extend(('lift_node', row) for floor, row in lift.get('floor_locations', {}).items()
                           if f"{lift['id']}-F{floor}" == name)
        if len(matches) != 1:
            raise ValueError(f'{name}: the object is missing or its name is ambiguous. Repair it in project checks.')
        result.extend(matches)
    return result


def specs(config, target):
    if target[0] not in {'points', 'edges'}:
        from configuration_properties import specs as config_specs
        return config_specs(config, target)
    rows = records(config, target)
    kinds = {kind for kind, _ in rows}
    fields = []
    if kinds == {'edge'}:
        fields = [('width_m', 'Corridor width (m)', 'positive'), ('distance_m', 'Override length (m)', 'nonnegative'),
                  ('people_area_type', 'People using this area', 'people')]
        if len(rows) == 1:
            fields.insert(2, ('bidirectional', 'Allow travel both ways', 'bool'))
    else:
        if len(rows) == 1:
            fields = [('x', 'X position (m)', 'coordinate'), ('y', 'Y position (m)', 'coordinate')]
        if kinds == {'corridor_node'}:
            fields += [('has_door', 'Door restriction', 'bool'), ('door_clear_width_m', 'Clear door opening (m)', 'positive')]
        if kinds == {'location'}:
            fields += [('people_area_type', 'People using this area', 'people'),
                       ('wash_cycle_required', 'Wash cycle required', 'bool'),
                       ('wash_cycle_duration_sec', 'Wash duration (s)', 'nonnegative'),
                       ('wash_location', 'Wash location', 'location')]
    return fields


def apply_properties(config, target, changes, expected):
    if fingerprint(config) != expected:
        raise ValueError('The project changed after these values were opened. Discard the draft to reload current values.')
    if target[0] not in {'points', 'edges'}:
        from configuration_properties import apply
        return apply(config, target, changes)
    fields = {key: kind for key, _label, kind in specs(config, target)}
    if not changes or any(key not in fields for key in changes):
        raise ValueError('Choose supported properties to change.')
    parsed = {}
    for key, value in changes.items():
        kind = fields[key]
        if value is None:
            if kind == 'coordinate':
                raise ValueError('Positions must be finite numbers in metres.')
        elif kind == 'bool':
            if type(value) is not bool:
                raise ValueError('Choose Yes, No or the inherited default.')
        elif kind in {'coordinate', 'positive', 'nonnegative'}:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f'{key} must be a number.') from None
            if not math.isfinite(value) or (kind == 'positive' and value <= 0) or (kind == 'nonnegative' and value < 0):
                raise ValueError(f'{key} must be finite and ' + ('greater than zero.' if kind == 'positive' else 'within its allowed range.'))
            if key in {'width_m', 'door_clear_width_m'} and value < .1:
                raise ValueError(f'{key} must be at least 0.1 m, the simulator’s minimum width.')
        elif kind == 'people' and value not in {'none', 'staff', 'public', 'both'}:
            raise ValueError('Choose a supported people-area classification.')
        elif kind == 'location' and value not in {r.get('name') for r in config.get('locations', [])}:
            raise ValueError('Choose an existing wash location or clear it to use the task drop-off.')
        parsed[key] = value
    result = deepcopy(config)
    for kind, row in records(result, target):
        for key, value in parsed.items():
            if value is None:
                row.pop(key, None)
            else:
                row[key] = value
        if kind == 'corridor_node' and row.get('has_door'):
            width = row.get('door_clear_width_m', result.get('building', {}).get('default_door_clear_width_m', .9))
            if not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0:
                raise ValueError('An enabled door needs a positive clear opening or a valid building default.')
    return result
