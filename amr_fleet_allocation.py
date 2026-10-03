"""Deterministic distinct-bay matching and shared initial charging contracts."""
from collections import deque

from amr_inventory_inputs import inventory_space_is_amr, inventory_space_amr_types
from amr_payload_inputs import inventory_space_dimensions


def maximum_bay_assignment(candidates, initial=None):
    """Maximum matching, preserving existing matches unless an augmenting path needs them.

    Candidate/robot iteration order breaks ties. A seeded matching retains every
    already occupied bay, so extending a maximum charger matching with parking
    maximises occupied bays without losing charger occupancy.
    """
    result = dict(initial or {})
    owners = {}
    for robot, bay in result.items():
        if robot not in candidates or bay not in candidates[robot] or bay in owners:
            raise ValueError('Initial bay matching must contain distinct compatible assignments.')
        owners[bay] = robot
    for root in candidates:
        if root in result:
            continue
        parents = {root: None}
        queue = deque([root])
        found = False
        while queue and not found:
            robot = queue.popleft()
            for bay in candidates[robot]:
                owner = owners.get(bay)
                if owner is None:
                    while True:
                        result[robot] = bay
                        owners[bay] = robot
                        previous = parents[robot]
                        if previous is None:
                            break
                        robot, bay = previous
                    found = True
                    break
                if owner not in parents:
                    parents[owner] = (robot, bay)
                    queue.append(owner)
    return result


def configured_charge_locations(config):
    building = config.get('building', {})
    names = building.get('charge_locations', [])
    if isinstance(names, str):
        names = names.split(',')
    names = [name.strip() for name in names if isinstance(name, str) and name.strip()]
    if not names:
        legacy = building.get('charge_location', '')
        names = [legacy.strip()] if isinstance(legacy, str) and legacy.strip() else []
    if not names and config.get('locations'):
        name = config['locations'][0].get('name')
        names = [name] if isinstance(name, str) and name else []
    return list(dict.fromkeys(names))


def charge_input_findings(config, *, check_references=False):
    if not isinstance(config, dict) or not isinstance(config.get('building', {}), dict):
        return
    building = config.get('building', {})
    malformed = False
    if 'charge_locations' in building:
        names = building['charge_locations']
        if not isinstance(names, (str, list)) or (isinstance(names, list) and
                any(not isinstance(name, str) or not name.strip() for name in names)):
            malformed = True
            yield '/building/charge_locations', 'Charging locations must be a list of nonblank location names or a legacy comma-separated string.'
    if 'charge_location' in building and not isinstance(building['charge_location'], str):
        malformed = True
        yield '/building/charge_location', 'Legacy charging location must be a location name or an empty string.'
    if check_references and not malformed:
        locations = {row.get('name') for row in config.get('locations', [])
                     if isinstance(row, dict) and isinstance(row.get('name'), str)}
        for name in configured_charge_locations(config):
            if name not in locations:
                yield '/building/charge_locations', f'Unknown charging location {name!r}; charging requires an actual location, not a corridor node.'


def validate_charge_inputs(config, *, check_references=False):
    findings = list(charge_input_findings(config, check_references=check_references))
    if findings:
        raise ValueError('Invalid charging inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))


def amr_bay_compatible(space, robot_id, robot_dimensions, bay_dimensions):
    if not inventory_space_is_amr(space):
        return False
    allowed = inventory_space_amr_types(space)
    if allowed and robot_id not in allowed and robot_id.rsplit('-', 1)[0] not in allowed:
        return False
    length, width, height = robot_dimensions
    bay_length, bay_width, bay_height = bay_dimensions
    tolerance = 1e-3
    return (((length <= bay_length + tolerance and width <= bay_width + tolerance)
             or (length <= bay_width + tolerance and width <= bay_length + tolerance))
            and height <= bay_height + tolerance)


def configured_fleet_bay_plan(config):
    """Configuration compatibility only; initial occupancy markers are not stock.

    Runtime performs live availability checks separately. Location-level legacy
    chargers do not become fabricated physical inventory bays in this plan.
    """
    locations = {row['name']: row for row in config.get('locations', [])}
    payloads = {row['name']: row for row in config.get('payloads', [])}
    bays = {}
    legacy_locations = []
    for name in configured_charge_locations(config):
        location_bays = [(index, bay) for index, bay in enumerate(locations.get(name, {}).get('inventory_spaces', []))
                         if inventory_space_is_amr(bay)]
        if not location_bays and name in locations:
            legacy_locations.append(name)
        for index, bay in location_bays:
            bays[(name, bay.get('name') or f'Space {index+1}')] = (bay, inventory_space_dimensions(bay, payloads, locations[name]))
    candidates, chargers = {}, {}
    for robot in config.get('amrs', []):
        for index in range(int(robot.get('quantity', 1))):
            robot_id = f"{robot['id']}-{index+1}"
            dimensions = tuple(float(robot.get(axis + '_m', default))
                               for axis, default in [('length', .8), ('width', .6), ('height', 1.2)])
            candidates[robot_id] = [key for key, (bay, envelope) in bays.items()
                                    if amr_bay_compatible(bay, robot_id, dimensions, envelope)]
            chargers[robot_id] = [key for key in candidates[robot_id] if bays[key][0].get('has_charger', False)]
    charge_matching = maximum_bay_assignment(chargers)
    return dict(charger_assignment=charge_matching, assignment=maximum_bay_assignment(candidates, charge_matching),
                robot_ids=list(candidates), explicit_bays=len(bays), legacy_locations=legacy_locations)
