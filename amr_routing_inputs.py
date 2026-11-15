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
        yield from waypoint_input_findings(config)
        yield from lift_policy_input_findings(config)
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


def lift_policy_input_findings(config):
    building = config.get('building', {})
    known = set()
    count = building.get('floor_count')
    if type(count) is int and 0 < count <= 10000:
        known.update(range(count))
    corridors = config.get('corridors', {})
    collections = [config.get('locations', []), corridors.get('nodes', []) if isinstance(corridors, dict) else []]
    for collection in collections:
        if isinstance(collection, list):
            known.update(row['floor'] for row in collection if isinstance(row, dict) and type(row.get('floor')) is int)
    for lift in config.get('lifts', []) if isinstance(config.get('lifts', []), list) else []:
        if isinstance(lift, dict) and isinstance(lift.get('served_floors'), list):
            known.update(f for f in lift['served_floors'] if type(f) is int)
    floor = building.get('lift_transfer_floor')
    if floor is not None and (type(floor) is not int or floor not in known):
        yield '/building/lift_transfer_floor', 'Transfer floor must identify an existing floor as a whole number, or be unset.'
    enabled = building.get('force_via_floor_enabled', False)
    if type(enabled) is not bool:
        yield '/building/force_via_floor_enabled', 'Force every AMR journey via a floor must be a boolean (true or false).'
    forced = building.get('force_via_floor')
    if enabled is True or forced is not None:
        if type(forced) is not int or forced not in known:
            yield '/building/force_via_floor', 'Select an existing whole floor number for forced AMR journeys.'
    if enabled is True:
        rules = building.get('mandatory_floor_waypoints', [])
        for index, rule in enumerate(rules if isinstance(rules, list) else []):
            if isinstance(rule, dict) and rule.get('via_floor') != forced:
                yield f'/building/mandatory_floor_waypoints/{index}/via_floor', (
                    f'Waypoint rule {index + 1} conflicts with forced floor {forced}. '
                    'Use the same via floor or remove the conflicting rule before enabling forced journeys.')
    yield from _forced_lift_preference_findings(config, building, known)
    floors = building.get('destination_side_lift_floors', [])
    if (not isinstance(floors, list) or any(type(f) is not int or f not in known for f in floors)
            or len(set(floors)) != len(floors)):
        yield '/building/destination_side_lift_floors', 'Destination-side lift floors must be a list of unique existing whole floor numbers.'


def _forced_lift_preference_findings(config, building, known_floors):
    path = '/building/forced_floor_lift_preference'
    preference = building.get('forced_floor_lift_preference', {})
    if not isinstance(preference, dict):
        yield path, 'Forced-floor lift preference must be an object.'
        return
    mode = preference.get('mode', 'off')
    if mode not in ('off', 'prefer', 'required'):
        yield path + '/mode', 'Choose Off, Prefer selected lifts with fallback, or Selected lifts only.'
        return
    if mode == 'off' or building.get('force_via_floor_enabled') is not True:
        return
    departure = preference.get('from_floor')
    if type(departure) is not int or departure not in known_floors:
        yield path + '/from_floor', 'Select an existing departure floor for the lift preference.'
    ids = preference.get('lift_ids')
    if (not isinstance(ids, list) or not ids or any(not isinstance(lift_id, str) for lift_id in ids)
            or len(set(ids)) != len(ids)):
        yield path + '/lift_ids', 'Select at least one lift and list each selected lift once.'
        return
    lifts = config.get('lifts', [])
    stops = {lift['id']: lift.get('served_floors') for lift in lifts if isinstance(lift, dict)
             and isinstance(lift.get('id'), str)} if isinstance(lifts, list) else {}
    missing = set(ids) - stops.keys()
    if missing:
        yield path + '/lift_ids', f'Unknown selected lifts: {", ".join(sorted(missing))}.'
    elif not any(isinstance(stops[lift_id], list) and building.get('force_via_floor') in stops[lift_id]
                 for lift_id in ids):
        yield path + '/lift_ids', 'Select at least one lift that serves the required floor.'


def waypoint_input_findings(config):
    path = '/building/mandatory_floor_waypoints'
    rules = config.get('building', {}).get('mandatory_floor_waypoints', [])
    if not isinstance(rules, list):
        yield path, 'Mandatory floor waypoints must be a list of rules.'
        return
    if not rules:
        return
    known = set()
    locations = config.get('locations', [])
    corridors = config.get('corridors', {})
    nodes = corridors.get('nodes', []) if isinstance(corridors, dict) else []
    for collection in (locations, nodes):
        if isinstance(collection, list):
            known.update(v['floor'] for v in collection if isinstance(v, dict) and type(v.get('floor')) is int)
    lifts = config.get('lifts', [])
    for lift in lifts if isinstance(lifts, list) else []:
        if isinstance(lift, dict):
            floors = lift.get('served_floors', [])
            if isinstance(floors, list):
                known.update(v for v in floors if type(v) is int)
    count = config.get('building', {}).get('floor_count')
    if type(count) is int and 0 < count <= 10000:
        known.update(range(count))
    pairs = set()
    for i, rule in enumerate(rules):
        pointer = f'{path}/{i}'
        if not isinstance(rule, dict):
            yield pointer, 'Each waypoint rule must be an object.'
            continue
        valid = True
        for key in ('from_floor', 'via_floor'):
            floor = rule.get(key)
            if type(floor) is not int or floor not in known:
                yield pointer + '/' + key, f'{key} must identify an existing floor as a whole number.'
                valid = False
        destinations = rule.get('to_floors')
        if (not isinstance(destinations, list) or not destinations
                or any(type(v) is not int or v not in known for v in destinations)):
            yield pointer + '/to_floors', 'Destination floors must be a nonempty list of existing floor numbers.'
            valid = False
        if not valid:
            continue
        if rule['from_floor'] == rule['via_floor']:
            yield pointer + '/via_floor', 'The waypoint floor must differ from the starting floor.'
        if rule['from_floor'] in destinations or len(set(destinations)) != len(destinations):
            yield pointer + '/to_floors', 'List each destination once and exclude the starting floor.'
        for floor in destinations:
            pair = rule['from_floor'], floor
            if pair in pairs:
                yield pointer, 'Only one waypoint rule may apply to a given starting and destination floor.'
            pairs.add(pair)
