"""Atomic rotation of graph objects and their owned drawing geometry."""
from copy import deepcopy
import math


def finite(value):
    try:
        result = float(value)
        if isinstance(value, bool) or not math.isfinite(result):
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Rotation coordinates and angles must be finite numbers.') from None


def rotate_selection(store, names, centre, degrees):
    """Return a staged store; references and unselected geometry retain identity.

    Rotation changes layout geometry, not separately authored floor obstacles or
    initial robot headings. Inferred bay capacity dimensions are frozen before
    rotating its drawing so an axis-aligned envelope cannot change capacity.
    """
    cx, cy = map(finite, centre)
    angle = finite(degrees) % 360
    if angle == 0:
        raise ValueError('Enter a rotation other than a whole number of full turns.')
    if angle % 90 == 0:
        c, s = ((1, 0), (0, 1), (-1, 0), (0, -1))[int(angle / 90)]
    else:
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def xy(x, y, origin):
        x, y = finite(x) - origin[0], finite(y) - origin[1]
        return finite(origin[0] + c*x - s*y), finite(origin[1] + s*x + c*y)

    def owned_point(point):
        # Retain representations, including metadata and legacy absolute pairs.
        for keys, origin in ((('dx', 'dy'), (0, 0)), (('x', 'y'), (cx, cy))):
            if any(key in point for key in keys):
                if not all(key in point for key in keys):
                    raise ValueError('An attached point needs a complete coordinate pair.')
                point[keys[0]], point[keys[1]] = xy(point[keys[0]], point[keys[1]], origin)

    points = store.all_points()
    names = set(names)
    if not names or not names <= points.keys():
        raise ValueError('Select existing graph objects before rotating.')
    if len({points[name]['floor'] for name in names}) != 1:
        raise ValueError('Rotate objects on one floor at a time.')
    staged = deepcopy(store)
    from amr_payload_inputs import inventory_space_dimensions
    payloads = {row['name']: row for row in store.data.get('payloads', [])}
    for name in sorted(names):
        point = points[name]
        x, y = xy(point['x'], point['y'], (cx, cy))
        location = staged.get_location(name)
        if location is not None:
            for vertex in location.get('bounding_box', []):
                owned_point(vertex)
            for space in location.get('inventory_spaces', []):
                # Resolve against the original origin before moving the location.
                dimensions = inventory_space_dimensions(space, payloads, location)
                for axis, value in zip(('length', 'width', 'height'), dimensions):
                    if finite(space.get(axis + '_m', space.get(axis, 0))) == 0:
                        space[axis + '_m'] = finite(value)
                for vertex in space.get('points', []):
                    owned_point(vertex)
                space['rotation_deg'] = (finite(space.get('rotation_deg', 0)) + angle) % 360
                for slot in space.get('payload_slots', []):
                    owned_point(slot)
                    slot['rotation_deg'] = (finite(slot.get('rotation_deg', 0)) + angle) % 360
        staged.set_point_position(name, x, y, exact=True)
    from amr_location_inputs import validate_location_inputs
    from amr_inventory_inputs import validate_inventory_inputs
    validate_location_inputs(staged.data)
    validate_inventory_inputs(staged.data)
    return staged
