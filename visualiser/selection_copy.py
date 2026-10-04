"""Copy explicit layout sections without aliasing identities or operational rules."""
from copy import deepcopy
import math
from visualiser.selection_rotation import finite


def copy_selection(store, names, dx, dy, *, occupied=False):
    dx, dy = finite(dx), finite(dy)
    if dx == dy == 0:
        raise ValueError('Enter a non-zero copy displacement.')
    if store.data['corridors'].get('auto_connect', False):
        raise ValueError('Make automatically generated corridors explicit before copying layout sections.')
    points = store.all_points()
    names = set(names)
    if not names or not names <= points.keys():
        raise ValueError('Select existing locations or corridor nodes to copy.')
    if any(points[name]['kind'] not in ('location', 'corridor_node') for name in names):
        raise ValueError('Copy supports locations and corridor nodes. Create departments and lifts using their dedicated editors.')
    floors = {int(points[name]['floor']) for name in names}
    if len(floors) != 1:
        raise ValueError('Copy a selection from one floor at a time.')
    mapping, used, proposed = {}, set(points), []
    for name in sorted(names):
        number = 1
        while f'{name}-copy-{number}' in used:
            number += 1
        mapping[name] = f'{name}-copy-{number}'
        used.add(mapping[name])
        x, y = finite(finite(points[name]['x'])+dx), finite(finite(points[name]['y'])+dy)
        if any(math.hypot(px-x,py-y) < 1e-6 for px,py in proposed):
            raise ValueError('Selected points overlap; resolve their positions before copying.')
        proposed.append((x,y))
        if any(int(p['floor']) in floors and math.hypot(finite(p['x'])-x, finite(p['y'])-y) < 1e-6
               for p in points.values()):
            raise ValueError('A copied point would overlap an existing point. Choose another displacement.')
    result = deepcopy(store)

    def translate_absolute(point):
        if 'x' in point or 'y' in point:
            if not all(k in point for k in ('x','y')):
                raise ValueError('Attached geometry requires complete coordinates.')
            point['x'], point['y'] = finite(finite(point['x'])+dx), finite(finite(point['y'])+dy)

    for source, target in ((store.data['locations'], result.data['locations']),
                           (store.data['corridors']['nodes'], result.data['corridors']['nodes'])):
        for original in source:
            if original['name'] not in mapping:
                continue
            row = deepcopy(original)
            row['name'] = mapping[original['name']]
            row['x'], row['y'] = finite(finite(row['x'])+dx), finite(finite(row['y'])+dy)
            if row.get('wash_location') in mapping:
                row['wash_location'] = mapping[row['wash_location']]
            for point in row.get('bounding_box', []):
                translate_absolute(point)
            for space in row.get('inventory_spaces', []):
                if not occupied:
                    space['occupied'] = False
                for point in space.get('points', []):
                    translate_absolute(point)
                for slot in space.get('payload_slots', []):
                    translate_absolute(slot)
            target.append(row)
    edges = [edge for edge in store.data['corridors']['edges']
             if edge['from'] in mapping and edge['to'] in mapping]
    for original in edges:
        edge = deepcopy(original)
        edge.update({'from': mapping[original['from']], 'to': mapping[original['to']]})
        result.data['corridors']['edges'].append(edge)
    # Only named profile membership follows the copied layout. Per-task route
    # overrides, demand, people schedules and scenario events are separate input.
    for profile in result.data.get('route_profiles', {}).values():
        allowed = profile.get('allowed_nodes')
        if isinstance(allowed, list):
            allowed.extend(mapping[name] for name in list(allowed) if name in mapping)
        allowed = profile.get('allowed_edges')
        if isinstance(allowed, list):
            pairs = {(e['from'], e['to']) for e in edges}
            pairs |= {(b,a) for a,b in list(pairs)}
            allowed.extend([mapping[a],mapping[b]] for a,b in list(allowed)
                           if (a,b) in pairs)
    from amr_location_inputs import validate_location_inputs
    from amr_inventory_inputs import validate_inventory_inputs
    validate_location_inputs(result.data)
    validate_inventory_inputs(result.data)
    return result, mapping, len(edges)
