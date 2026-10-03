"""Location identities, scalar service settings and wash references."""
import math


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


def validate_location_inputs(config, *, require_complete=False):
    findings = list(location_input_findings(config, require_complete=require_complete))
    if findings:
        raise ValueError('Invalid location inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))
