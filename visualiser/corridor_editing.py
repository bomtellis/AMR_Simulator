"""Atomic corridor subdivision with directed restrictions and resource references."""
from copy import deepcopy
import math
from itertools import combinations


def intersection_target(points, edges, floor, x, y, radius=.45):
    """Find a nearby connected junction target, considering only local segments."""
    local = {name: p for name, p in points.items() if int(p['floor']) == int(floor)}
    segments = {}
    for edge in edges:
        key = tuple(sorted((edge['from'], edge['to'])))
        if key in segments or any(n not in local or local[n].get('kind') == 'department' for n in key):
            continue
        a, b = (local[n] for n in key)
        ax, ay, bx, by = (float(p[k]) for p in (a, b) for k in ('x', 'y'))
        if not all(math.isfinite(v) for v in (ax, ay, bx, by)):
            continue
        if not (min(ax, bx)-radius <= x <= max(ax, bx)+radius and min(ay, by)-radius <= y <= max(ay, by)+radius):
            continue
        try:
            t = min(1., max(0., project_fraction(a, b, x, y)))
        except ValueError:
            continue
        if math.hypot(ax+t*(bx-ax)-x, ay+t*(by-ay)-y) <= radius:
            segments[key] = (ax, ay, bx-ax, by-ay)
    candidates = []
    for (key, (ax, ay, rx, ry)), (other, (cx, cy, sx, sy)) in combinations(segments.items(), 2):
        cross = rx*sy-ry*sx
        if abs(cross) <= 1e-12 * max(1., math.hypot(rx, ry)*math.hypot(sx, sy)):
            continue
        t = ((cx-ax)*sy-(cy-ay)*sx)/cross
        u = ((cx-ax)*ry-(cy-ay)*rx)/cross
        if 0 <= t <= 1 and 0 <= u <= 1:
            px, py = ax+t*rx, ay+t*ry
            distance = math.hypot(px-x, py-y)
            if distance <= radius:
                candidates.append((distance, key, other, px, py))
    if not candidates:
        return None
    _, _, _, px, py = min(candidates)
    nearby = [dict(p, name=name) for name, p in local.items()
              if math.hypot(float(p['x'])-px, float(p['y'])-py) < 1e-6]
    if len(nearby) > 1 or (nearby and (nearby[0].get('kind') == 'department' or
            math.hypot(float(nearby[0]['x'])-px, float(nearby[0]['y'])-py) >= 1e-8)):
        raise ValueError('Resolve overlapping or near-coincident points before joining this intersection.')
    existing = nearby[0] if nearby else None
    cuts = {}
    for key, (ax, ay, rx, ry) in segments.items():
        t = ((px-ax)*rx+(py-ay)*ry)/(rx*rx+ry*ry)
        if 0 < t < 1 and math.hypot(ax+t*rx-px, ay+t*ry-py) < 1e-8:
            cuts[key] = [t]
    if not cuts:
        if existing:
            return dict(kind='point', name=existing['name'], x=px, y=py, snap_label='intersection')
        raise ValueError('Intersection endpoints must share one graph point.')
    return dict(kind='junction', x=px, y=py, cuts=cuts, existing=existing, snap_label='intersection')


def drawing_target(points, edges, floor, x, y, snap=True, *, exact=False, grid_spacing=1.0, object_snap=True,
                   anchor=None, angle_step=None, snap_mode="nearest"):
    """Resolve a drawing click/preview: point, explicit edge, then free grid point."""
    if snap_mode not in ("nearest", "endpoints", "midpoints", "perpendicular", "intersections"):
        raise ValueError("Choose a supported object snap mode.")
    x, y = float(x), float(y)
    if not all(math.isfinite(v) for v in (x, y)):
        raise ValueError('Choose a finite position on the current floor.')
    if snap_mode == 'perpendicular' and anchor is not None:
        anchor = tuple(map(float, anchor))
        if len(anchor) != 2 or not all(math.isfinite(v) for v in anchor):
            raise ValueError('Perpendicular snapping requires a finite route endpoint.')
    if angle_step is not None and anchor is not None and not exact:
        step = float(angle_step)
        ax, ay = map(float, anchor)
        if not all(math.isfinite(v) for v in (step, ax, ay)) or not 0 < step <= 90:
            raise ValueError('Drawing angle increment must be between zero and 90 degrees, with a finite anchor.')
        # Resolve grid first, then project onto the closest permitted ray. Object
        # attraction is accepted only when it retains that ray's direction.
        base = drawing_target(points, edges, floor, x, y, snap,
                              grid_spacing=grid_spacing, object_snap=False)
        dx, dy = base['x'] - ax, base['y'] - ay
        angle = math.radians(math.floor(math.degrees(math.atan2(dy, dx)) / step + .5) * step)
        ux, uy = math.cos(angle), math.sin(angle)
        distance = max(0., dx * ux + dy * uy)
        px, py = ax + distance * ux, ay + distance * uy
        candidate = drawing_target(points, edges, floor, px, py, False, exact=True,
                                   grid_spacing=grid_spacing, object_snap=object_snap, snap_mode=snap_mode,
                                   anchor=anchor)
        cx, cy = candidate['x'] - ax, candidate['y'] - ay
        if abs(cx * uy - cy * ux) <= 1e-8 and cx * ux + cy * uy >= -1e-8:
            return dict(candidate, angle_step=step)
        target = drawing_target(points, edges, floor, px, py, False, exact=True,
                                grid_spacing=grid_spacing, object_snap=False)
        return dict(target, angle_step=step)
    local = {name: p for name, p in points.items() if int(p['floor']) == int(floor)}

    def point_at(px, py, radius):
        candidates = [(math.hypot(float(p['x']) - px, float(p['y']) - py), name) for name, p in local.items()]
        nearby = sorted((distance, name) for distance, name in candidates if distance <= radius)
        if nearby:
            name = nearby[0][1]
            if local[name].get('kind') == 'department':
                raise ValueError('Connect to a department location, not the department marker.')
            return dict(kind='point', name=name, x=float(local[name]['x']), y=float(local[name]['y']))

    grid_spacing = float(grid_spacing)
    if not math.isfinite(grid_spacing) or grid_spacing <= 0:
        raise ValueError("Grid spacing must be finite and greater than zero metres.")
    if object_snap and snap_mode == 'intersections':
        target = intersection_target(points, edges, floor, x, y)
        if target:
            return target
    target = point_at(x, y, .45 if object_snap and snap_mode in ('nearest', 'endpoints') else 1e-6)
    if target:
        return target
    def edge_at(x, y, radius, midpoint=False, perpendicular=False):
        candidates = []
        for edge in edges:
            key = tuple(sorted((edge['from'], edge['to'])))
            if any(n not in local or local[n].get('kind') == 'department' for n in key):
                continue
            a, b = (local[n] for n in key)
            try:
                fraction = project_fraction(a, b, *anchor) if perpendicular else project_fraction(a, b, x, y)
                if midpoint:
                    fraction = .5
            except ValueError:
                continue
            if not (0 <= fraction <= 1 if perpendicular else 0 < fraction < 1):
                continue
            px = float(a['x']) + fraction * (float(b['x']) - float(a['x']))
            py = float(a['y']) + fraction * (float(b['y']) - float(a['y']))
            if perpendicular and math.hypot(px-anchor[0], py-anchor[1]) < 1e-6:
                continue
            distance = math.hypot(px - x, py - y)
            if distance <= radius:
                candidates.append((distance, key, fraction, px, py))
        if candidates:
            _, key, fraction, px, py = min(candidates)
            if perpendicular and fraction in (0., 1.):
                return dict(kind='point', name=key[int(fraction)], x=px, y=py, snap_label='perpendicular')
            return dict(kind='edge', key=key, fraction=fraction, x=px, y=py,
                        snap_label='perpendicular' if perpendicular else ('midpoint' if midpoint else 'edge'))
    attract_edge = object_snap and snap_mode not in ('endpoints', 'intersections') and (snap_mode != 'perpendicular' or anchor is not None)
    target = edge_at(x, y, .45, midpoint=snap_mode == 'midpoints', perpendicular=snap_mode == 'perpendicular') if attract_edge else None
    target = target or edge_at(x, y, 1e-6)
    if target:
        return target
    if not exact:
        x, y = (round(round(x / grid_spacing) * grid_spacing, 12), round(round(y / grid_spacing) * grid_spacing, 12)) if snap else (round(x, 3), round(y, 3))
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


def draw_step(config, points, start, floor, x, y, *, snap=True, bidirectional=True, exact=False, grid_spacing=1.0, object_snap=True, angle_step=None, snap_mode="nearest"):
    """Atomically place/reuse/split a target and connect it to the current anchor."""
    if start is not None and (start not in points or int(points[start]['floor']) != int(floor)):
        raise ValueError('Finish this route before starting on another floor or layout.')
    anchor = (points[start]['x'], points[start]['y']) if start is not None else None
    target = drawing_target(points, config['corridors']['edges'], floor, x, y, snap, exact=exact,
                            grid_spacing=grid_spacing, object_snap=object_snap, anchor=anchor, angle_step=angle_step, snap_mode=snap_mode)
    result = deepcopy(config)
    if target['kind'] == 'junction':
        result, chains = subdivide(config, points, target['cuts'], _join_cuts=True, _existing_cut_node=target['existing'])
        names = {chain[1] for chain in chains.values()}
        if len(names) != 1:
            raise ValueError('Intersection cannot be resolved to one graph point at supported precision.')
        name = names.pop()
    elif target['kind'] == 'edge':
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


def create_crossing_junction(config, points, keys):
    """Explicitly join two crossing corridors, reusing a unique existing point."""
    keys = sorted(set(tuple(sorted(key)) for key in keys))
    if len(keys) != 2 or any(len(key) != 2 for key in keys):
        raise ValueError('Select exactly two crossing corridors.')
    if any(not any({e['from'], e['to']} == set(key) for e in config['corridors']['edges']) for key in keys):
        raise ValueError('A selected corridor no longer exists.')
    try:
        a, b, c, d = [points[name] for key in keys for name in key]
    except KeyError:
        raise ValueError('A selected corridor endpoint no longer exists.') from None
    if len({int(p['floor']) for p in (a, b, c, d)}) != 1:
        raise ValueError('A junction must connect corridors on the same floor.')
    if any(p.get('kind') == 'department' for p in (a, b, c, d)):
        raise ValueError('Department markers are not corridor endpoints.')
    ax, ay, bx, by, cx, cy, dx, dy = [float(p[k]) for p in (a, b, c, d) for k in ('x', 'y')]
    if not all(math.isfinite(v) for v in (ax, ay, bx, by, cx, cy, dx, dy)):
        raise ValueError('Corridor coordinates must be finite.')
    rx, ry, sx, sy = bx-ax, by-ay, dx-cx, dy-cy
    cross = rx*sy - ry*sx
    if abs(cross) <= 1e-12 * max(1., math.hypot(rx, ry) * math.hypot(sx, sy)):
        raise ValueError('Parallel or overlapping corridors have no unique crossing junction.')
    t = ((cx-ax)*sy - (cy-ay)*sx) / cross
    u = ((cx-ax)*ry - (cy-ay)*rx) / cross
    if not (0 <= t <= 1 and 0 <= u <= 1):
        raise ValueError('Choose corridors that intersect within their finite lengths.')
    x, y, floor = ax+t*rx, ay+t*ry, int(a['floor'])
    nearby = [dict(p, name=name) for name, p in points.items()
              if int(p['floor']) == floor and math.hypot(float(p['x'])-x, float(p['y'])-y) < 1e-6]
    if len(nearby) > 1:
        raise ValueError('Multiple points occupy this crossing; resolve their identities before joining.')
    existing = nearby[0] if nearby else None
    if existing and (existing.get('kind') == 'department'
                     or math.hypot(float(existing['x'])-x, float(existing['y'])-y) >= 1e-8):
        raise ValueError('The crossing requires an exact graph point, not a nearby point or department marker.')
    cuts = {key: [fraction] for key, fraction in zip(keys, (t, u)) if 0 < fraction < 1}
    if not cuts:
        raise ValueError('These corridors already meet at an endpoint; no new junction is needed.')
    result, chains = subdivide(config, points, cuts, _join_cuts=True, _existing_cut_node=existing)
    if len({chain[1] for chain in chains.values()}) != 1:
        raise ValueError('The crossing cannot be resolved to one point at the supported coordinate precision.')
    for key in keys:
        chains.setdefault(key, list(key))
    return result, chains


def subdivide(config, points, cuts, *, _join_cuts=False, _existing_cut_node=None):
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
    inserted = [_existing_cut_node] if _existing_cut_node is not None else []
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
            x = float(a['x']) + fraction * (float(b['x']) - float(a['x']))
            y = float(a['y']) + fraction * (float(b['y']) - float(a['y']))
            shared = next((node for node in inserted if node['floor'] == floor
                           and math.hypot(node['x']-x, node['y']-y) < 1e-8), None) if _join_cuts else None
            if shared is not None:
                names.append(shared['name'])
                continue
            while f'C{floor}-{index}' in used:
                index += 1
            name = f'C{floor}-{index}'
            used.add(name)
            names.append(name)
            node = {
                'name': name, 'floor': floor,
                'x': x, 'y': y,
                'has_door': False,
                'door_clear_width_m': float(config.get('building', {}).get('default_door_clear_width_m', .9) or .9)}
            result['corridors']['nodes'].append(node)
            inserted.append(node)
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
