"""Location identities, scalar service settings and wash references."""
import math


def _outline_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Outline coordinates must be finite numbers in metres.') from exc
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError('Outline coordinates must be finite numbers in metres; booleans are invalid.')
    return number


def location_outline_points(location, *, local=False):
    """Resolve each complete local pair before legacy absolute pairs, without rounding."""
    points = location.get('bounding_box', [])
    if not isinstance(points, list):
        raise ValueError('Location bounding_box must be a list of point objects.')
    lx, ly = (_outline_number(location.get(key, 0)) for key in ('x', 'y'))
    result = []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise ValueError(f'Outline point {index} must be an object.')
        if 'dx' in point and 'dy' in point:
            x, y = (_outline_number(point[key]) for key in ('dx', 'dy'))
            world = x + lx, y + ly
            resolved = (x, y) if local else world
        elif 'x' in point and 'y' in point:
            world = tuple(_outline_number(point[key]) for key in ('x', 'y'))
            resolved = (world[0] - lx, world[1] - ly) if local else world
        else:
            raise ValueError(f'Outline point {index} needs a complete dx/dy or x/y pair.')
        if not all(math.isfinite(value) for value in (*world, *resolved)):
            raise ValueError(f'Outline point {index} overflows after coordinate conversion.')
        result.append(dict(zip(('x', 'y'), resolved)))
    return result


def location_outline_metrics(location):
    """Plan envelope and algebraic polygon area; not a containment/validity test."""
    points = location_outline_points(location, local=True)
    if len(points) < 3:
        return dict(length=0., width=0., area=0.)
    # Translate before the shoelace products to avoid cancellation at large origins.
    origin = points[0]
    coordinates = [(p['x'] - origin['x'], p['y'] - origin['y']) for p in points]
    xs, ys = zip(*coordinates)
    length, width = max(xs) - min(xs), max(ys) - min(ys)
    try:
        area = abs(math.fsum(x * coordinates[(i + 1) % len(points)][1]
                             - coordinates[(i + 1) % len(points)][0] * y
                             for i, (x, y) in enumerate(coordinates))) / 2
    except (ValueError, OverflowError) as exc:
        raise ValueError('Outline metrics overflow; use representable geometry.') from exc
    if not all(math.isfinite(v) for v in (length, width, area)):
        raise ValueError('Outline metrics overflow; use representable geometry.')
    return dict(length=length, width=width, area=area)


def location_input_findings(config, *, require_complete=False):
    if not isinstance(config, dict):
        return
    rows = config.get('locations', [])
    if not isinstance(rows, list):
        yield '/locations', 'Locations must be a list of objects.'
        return
    names = {row.get('name') for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str)}
    seen = set()
    for index, row in enumerate(rows):
        path = f'/locations/{index}'
        if not isinstance(row, dict):
            yield path, 'Each location must be an object.'
            continue
        if require_complete:
            for key in ('name', 'floor'):
                if key not in row:
                    yield path + '/' + key, f'{key} is required for a runnable location.'
        if 'name' in row:
            name = row['name']
            if not isinstance(name, str) or not name or name != name.strip():
                yield path + '/name', 'Location names must be nonblank strings without surrounding whitespace.'
            elif name in seen:
                yield path + '/name', 'Location names must be unique.'
            else:
                seen.add(name)
        for key in ('x', 'y', 'floor', 'max_concurrency', 'wash_cycle_duration_sec'):
            if key not in row:
                continue
            value = row[key]
            try:
                numeric = float(value)
                valid = not isinstance(value, bool) and math.isfinite(numeric)
                if key in ('floor', 'max_concurrency'):
                    valid = valid and numeric == int(value)
                if key == 'max_concurrency':
                    valid = valid and numeric > 0
                if key == 'wash_cycle_duration_sec':
                    valid = valid and numeric >= 0
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                requirement = {'max_concurrency': 'a positive whole service capacity',
                               'floor': 'a whole floor number',
                               'wash_cycle_duration_sec': 'a nonnegative duration in seconds'}.get(key, 'a coordinate in metres')
                yield path + '/' + key, f'{key} must be finite and {requirement}; booleans are invalid.'
        if 'wash_cycle_required' in row and type(row['wash_cycle_required']) is not bool:
            yield path + '/wash_cycle_required', 'wash_cycle_required must be a JSON boolean.'
        if 'wash_location' in row:
            target = row['wash_location']
            if not isinstance(target, str) or target != target.strip():
                yield path + '/wash_location', 'Wash location must be a location name without surrounding whitespace, or an empty string to use the task drop-off.'
            elif require_complete and target and target not in names:
                yield path + '/wash_location', f'Unknown wash location {target!r}; resolve it before running. An empty target uses the task drop-off.'
        if 'people_area_type' in row:
            value = row['people_area_type']
            if not isinstance(value, str) or value.strip().lower() not in {'', 'none', 'staff', 'public', 'both'}:
                yield path + '/people_area_type', 'People area must be none, staff, public or both; an empty string retains none.'
        if 'bounding_box' in row:
            try:
                location_outline_metrics(row)
            except ValueError as exc:
                yield path + '/bounding_box', str(exc)


def validate_location_inputs(config, *, require_complete=False):
    findings = list(location_input_findings(config, require_complete=require_complete))
    if findings:
        raise ValueError('Invalid location inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
