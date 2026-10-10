"""Shared routing scalar checks applied before normalisation or simulation."""
import math


def routing_input_findings(config):
    """Yield (JSON pointer, message) without changing input or filling defaults.

    Container/reference validation belongs to Project checks. Missing scalar
    options retain their documented defaults; explicitly invalid values do not.
    """
    if not isinstance(config, dict):
        return
    building = config.get('building', {})
    corridors = config.get('corridors', {})
    entries = []
    if isinstance(building, dict):
        entries.extend((building, '/building', name, False) for name in
                       ('default_corridor_width_m', 'default_door_clear_width_m'))
    if isinstance(corridors, dict):
        entries.append((corridors, '/corridors', 'auto_connect', True))
        for collection, fields in [('nodes', [('has_door', True), ('door_clear_width_m', False)]),
                                   ('edges', [('bidirectional', True), ('width_m', False)])]:
            values = corridors.get(collection, [])
            if not isinstance(values, list):
                continue
            for index, entry in enumerate(values):
                if isinstance(entry, dict):
                    entries.extend((entry, f'/corridors/{collection}/{index}', name, boolean)
                                   for name, boolean in fields)
    for entry, path, name, boolean in entries:
        if name not in entry:
            continue
        value = entry[name]
        if boolean:
            if not isinstance(value, bool):
                yield path + '/' + name, f'{name} must be a JSON boolean (true or false), not a string or number.'
        else:
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                yield path + '/' + name, f'{name} must be a finite positive width in metres.'


def validate_routing_inputs(config):
    findings = list(routing_input_findings(config))
    if findings:
        raise ValueError('Invalid routing inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
