"""Atomic corridor subdivision with directed restrictions and resource references."""
from copy import deepcopy
import math


def drawing_target(points, edges, floor, x, y, snap=True):
    """Resolve a drawing click/preview: point, explicit edge, then free grid point."""
    x, y = float(x), float(y)
    if not all(math.isfinite(v) for v in (x, y)):
        raise ValueError('Choose a finite position on the current floor.')
    local = {name: p for name, p in points.items() if int(p['floor']) == int(floor)}

    def point_at(px, py, radius):
        candidates = [(math.hypot(float(p['x']) - px, float(p['y']) - py), name) for name, p in local.items()]
        nearby = sorted((distance, name) for distance, name in candidates if distance <= radius)
        if nearby:
            name = nearby[0][1]
            if local[name].get('kind') == 'department':
                raise ValueError('Connect to a department location, not the department marker.')
            return dict(kind='point', name=name, x=float(local[name]['x']), y=float(local[name]['y']))

    target = point_at(x, y, .45)
    if target:
        return target
    def edge_at(x, y, radius):
        candidates = []
        for edge in edges:
            key = tuple(sorted((edge['from'], edge['to'])))
            if any(n not in local or local[n].get('kind') == 'department' for n in key):
                continue
            a, b = (local[n] for n in key)
            try:
                fraction = project_fraction(a, b, x, y)
            except ValueError:
                continue
            if not 0 < fraction < 1:
                continue
            px = float(a['x']) + fraction * (float(b['x']) - float(a['x']))
            py = float(a['y']) + fraction * (float(b['y']) - float(a['y']))
            distance = math.hypot(px - x, py - y)
            if distance <= radius:
                candidates.append((distance, key, fraction, px, py))
        if candidates:
            _, key, fraction, px, py = min(candidates)
            return dict(kind='edge', key=key, fraction=fraction, x=px, y=py)
    target = edge_at(x, y, .45)
    if target:
        return target
    x, y = (float(round(x)), float(round(y))) if snap else (round(x, 3), round(y, 3))
    # Grid rounding must not create a second point at an occupied position.
    return point_at(x, y, 1e-6) or edge_at(x, y, 1e-6) or dict(kind='new', x=x, y=y)


def connect(config, points, start, finish, bidirectional=True):
    """Add one physical corridor without changing any existing permissions."""
    a, b = points.get(start), points.get(finish)
    if not a or not b or a.get('kind') == 'department' or b.get('kind') == 'department':
        raise ValueError('Both corridor endpoints must be graph points.')
    if int(a['floor']) != int(b['floor']):
        raise ValueError('Corridors must stay on one floor. Use a lift between floors.')
    if start == finish or math.hypot(float(a['x']) - float(b['x']), float(a['y']) - float(b['y'])) < 1e-6:
        raise ValueError('Choose a different point to extend the route.')
    project_fraction(a, b, a['x'], a['y'])
    if any({e['from'], e['to']} == {start, finish} for e in config['corridors']['edges']):
        return False
    width = float(config.get('building', {}).get('default_corridor_width_m', 2.4))
    if not math.isfinite(width) or width <= 0:
        raise ValueError('Set a positive finite default corridor width before drawing.')
    config['corridors']['edges'].append({'from': start, 'to': finish, 'bidirectional': bool(bidirectional),
                                        'width_m': width, 'people_area_type': 'none', 'people_profile_ids': []})
    return True


def draw_step(config, points, start, floor, x, y, *, snap=True, bidirectional=True):
    """Atomically place/reuse/split a target and connect it to the current anchor."""
    if start is not None and (start not in points or int(points[start]['floor']) != int(floor)):
        raise ValueError('Finish this route before starting on another floor or layout.')
    target = drawing_target(points, config['corridors']['edges'], floor, x, y, snap)
    result = deepcopy(config)
    if target['kind'] == 'edge':
        result, chains = subdivide(config, points, {target['key']: [target['fraction']]})
        name = chains[target['key']][1]
    elif target['kind'] == 'point':
        name = target['name']
    else:
        index = 1
        while f'C{int(floor)}-{index}' in points:
            index += 1
        name = f'C{int(floor)}-{index}'
        result['corridors']['nodes'].append(dict(name=name, floor=int(floor), x=target['x'], y=target['y'], has_door=False,
                                               door_clear_width_m=float(config.get('building', {}).get('default_door_clear_width_m', .9) or .9)))
    updated_points = dict(points)
    updated_points.update({p['name']: p for p in result['corridors']['nodes']})
    connected = connect(result, updated_points, start, name, bidirectional) if start is not None and start != name else False
    return result, dict(target, name=name, connected=connected)


def project_fraction(a, b, x, y):
    dx, dy = float(b['x']) - float(a['x']), float(b['y']) - float(a['y'])
    length_sq = dx * dx + dy * dy
    if not math.isfinite(length_sq) or length_sq <= 1e-12:
        raise ValueError('A corridor needs distinct finite endpoints before it can be split.')
    return ((float(x) - float(a['x'])) * dx + (float(y) - float(a['y'])) * dy) / length_sq


def subdivide(config, points, cuts):
    """Return a replacement configuration and new node chains, without mutation.

    cuts maps canonical (sorted endpoint) pairs to fractions along that pair.
    Both explicit directions of a physical corridor share the same new nodes.
    """
    if not cuts:
        raise ValueError('Select at least one corridor first.')
    result = deepcopy(config)
    edges = result['corridors']['edges']
    used = set(points)
    chains, proportions = {}, {}
    for key, values in sorted(cuts.items()):
        if len(key) != 2 or tuple(sorted(key)) != key or key[0] == key[1]:
            raise ValueError('Corridor endpoints must be a distinct, sorted pair.')
        a, b = (points.get(name) for name in key)
        if not a or not b or a.get('kind') == 'department' or b.get('kind') == 'department' or int(a['floor']) != int(b['floor']):
            raise ValueError('Only corridor links between points on the same floor can be subdivided.')
        if not any({e['from'], e['to']} == set(key) for e in edges):
            raise ValueError('The selected corridor no longer exists.')
        fractions = [float(value) for value in values]
        if not fractions or len(fractions) > 99 or any(not math.isfinite(t) or not 0 < t < 1 for t in fractions):
            raise ValueError('Choose between 2 and 100 sections, with cuts strictly inside the corridor.')
        if fractions != sorted(set(fractions)):
            raise ValueError('Subdivision positions must be distinct and ordered.')
        project_fraction(a, b, a['x'], a['y'])  # Validate non-zero drawing length.
        bounds = [0.0, *fractions, 1.0]
        drawing_length = math.hypot(float(b['x']) - float(a['x']), float(b['y']) - float(a['y']))
        if any((right - left) * drawing_length < 1e-6 for left, right in zip(bounds, bounds[1:])):
            raise ValueError('A subdivision would create a section shorter than 0.000001 m.')
        names = []
        floor = int(a['floor'])
        index = 1
        for fraction in fractions:
            while f'C{floor}-{index}' in used:
                index += 1
            name = f'C{floor}-{index}'
            used.add(name)
            names.append(name)
            result['corridors']['nodes'].append({
                'name': name, 'floor': floor,
                'x': float(a['x']) + fraction * (float(b['x']) - float(a['x'])),
                'y': float(a['y']) + fraction * (float(b['y']) - float(a['y'])),
                'has_door': False,
                'door_clear_width_m': float(config.get('building', {}).get('default_door_clear_width_m', .9) or .9)})
        chains[key] = [key[0], *names, key[1]]
        proportions[key] = [right - left for left, right in zip(bounds, bounds[1:])]

    replacements = {}
    for key, chain in chains.items():
        replacements[key] = list(zip(chain, chain[1:]))
        reverse = list(reversed(chain))
        replacements[tuple(reversed(key))] = list(zip(reverse, reverse[1:]))
    new_edges = []
    for edge in edges:
        key = tuple(sorted((edge['from'], edge['to'])))
        if key not in chains:
            new_edges.append(edge)
            continue
        direction = (edge['from'], edge['to'])
        ratios = proportions[key] if direction == key else list(reversed(proportions[key]))
        distance = edge.get('distance_m')
        if distance is not None:
            distance = float(distance)
            if not math.isfinite(distance) or distance < 0:
                raise ValueError('Configured corridor distance must be finite and non-negative.')
        for (start, finish), ratio in zip(replacements[direction], ratios):
            piece = deepcopy(edge)
            piece.update({'from': start, 'to': finish})
            if distance is not None:
                piece['distance_m'] = distance * ratio
            new_edges.append(piece)
    result['corridors']['edges'] = new_edges

    original_profiles = config.get('route_profiles', {})

    def edge_labels(values):
        expanded = []
        for value in values:
            parts = (list(value) if isinstance(value, (list, tuple)) else
                     [part.strip() for part in str(value).replace('<->', '->').split('->')])
            replacement = replacements.get(tuple(parts)) if len(parts) == 2 else None
            if replacement:
                expanded.extend(f'{a} -> {b}' for a, b in replacement)
            else:
                expanded.append(value)
        return expanded

    def rewrite(value):
        if isinstance(value, dict):
            node_list = value.get('allowed_nodes')
            if isinstance(node_list, list) and node_list:
                # Task-local allowances extend profile allowances. Preserve that
                # union when its endpoints are divided between the two lists.
                effective = set(node_list)
                # Return tasks use their return profile but do not inherit the
                # outbound task's local node allowance.
                profile_names = [value.get('route_profile')]
                if not value.get('route_profile') and 'dirty' in value.get('labels', []):
                    profile_names.append('dirty')
                profile_sets = [set(original_profiles.get(name, {}).get('allowed_nodes', []))
                                for name in profile_names if isinstance(name, str)]
                for key, chain in chains.items():
                    if any(set(key).issubset(effective | extra) for extra in [set(), *profile_sets]):
                        node_list.extend(n for n in chain[1:-1] if n not in node_list)
            pairs = value.get('allowed_edges')
            if isinstance(pairs, list):
                expanded = []
                for pair in pairs:
                    replacement = replacements.get(tuple(pair)) if isinstance(pair, (list, tuple)) and len(pair) == 2 else None
                    expanded.extend([list(p) for p in replacement] if replacement else [pair])
                value['allowed_edges'] = expanded
            if isinstance(value.get('corridor_edges'), list):
                value['corridor_edges'] = edge_labels(value['corridor_edges'])
            if str(value.get('resource_type', '')).strip().lower() == 'corridor':
                ids = value.get('resource_ids', [])
                if isinstance(ids, str):
                    ids = [s.strip() for s in ids.split(',') if s.strip()]
                if not ids and value.get('resource_id'):
                    ids = [value['resource_id']]
                expanded = edge_labels(ids)
                if expanded != ids:
                    value['resource_ids'] = expanded
                    value.pop('resource_id', None)
            for child in value.values():
                rewrite(child)
        elif isinstance(value, list):
            for child in value:
                rewrite(child)
    rewrite(result)
    return result, chains
