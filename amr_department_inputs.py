"""Department identity/position contracts and atomic identity-aware replacements."""
from copy import deepcopy
import math


def department_identity(row):
    return str(row.get('id', '') or '').strip() or str(row.get('name', '') or '').strip()


def department_location_names(entry, *, zones=False):
    """Resolve modern keys before aliases; a scalar is one literal location name."""
    if isinstance(entry, dict):
        primary, legacy = ('dropoff_zone_locations', 'drop_off_zone_locations') if zones else ('pickup_dropoff_locations', 'locations')
        values = entry.get(primary, entry.get(legacy, []))
    else:
        values = [] if zones else entry
    if isinstance(values, str):
        values = [values]
    return list(dict.fromkeys(value.strip() for value in values or [] if isinstance(value, str) and value.strip()))


def department_zone_names(config):
    return {name for department in config.get('departments', [])
            for entry in department.get('task_generation_locations', {}).values()
            for name in department_location_names(entry, zones=True)}


def department_location_reference_findings(config):
    known = {row['name'] for row in config.get('locations', [])}
    escape = lambda value: str(value).replace('~', '~0').replace('/', '~1')
    for index, department in enumerate(config.get('departments', [])):
        for category, entry in department.get('task_generation_locations', {}).items():
            path = f'/departments/{index}/task_generation_locations/{escape(category)}'
            for zones in (False, True):
                primary, legacy = ('dropoff_zone_locations', 'drop_off_zone_locations') if zones else ('pickup_dropoff_locations', 'locations')
                source = path + '/' + (primary if primary in entry else legacy) if isinstance(entry, dict) else path
                for name in department_location_names(entry, zones=zones):
                    if name not in known:
                        yield source, name


def department_input_findings(config, *, require_identity=False):
    rows = config.get('departments', []) if isinstance(config, dict) else []
    if not isinstance(rows, list):
        yield '/departments', 'Departments must be a list.'
        return
    identities, names = set(), set()
    for index, row in enumerate(rows):
        path = f'/departments/{index}'
        if not isinstance(row, dict):
            yield path, 'Each department must be an object.'
            continue
        for key in ('id', 'name'):
            if key in row and (not isinstance(row[key], str) or row[key] != row[key].strip()):
                yield path + '/' + key, 'Department identities must be strings without surrounding whitespace.'
        identity = department_identity(row)
        if require_identity and not identity:
            yield path + '/id', 'A runnable department requires a nonblank ID or fallback name.'
        if identity and identity in identities:
            yield path + '/id', 'Effective department identities (ID, otherwise name) must be unique.'
        identities.add(identity)
        name = row.get('name')
        if isinstance(name, str) and name:
            if name in names:
                yield path + '/name', 'Department display names must be unique for unambiguous editing.'
            names.add(name)
        for key in ('x', 'y', 'floor'):
            if key not in row:
                continue
            value = row[key]
            try:
                number = float(value)
                valid = not isinstance(value, bool) and math.isfinite(number)
                if key == 'floor':
                    valid = valid and int(value) == number
            except (TypeError, ValueError, OverflowError):
                valid = False
            if not valid:
                yield path + '/' + key, 'Use a finite coordinate in metres or whole floor number; booleans are invalid.'
        assignments = row.get('task_generation_locations', {})
        if not isinstance(assignments, dict):
            yield path + '/task_generation_locations', 'Category location assignments must be an object.'
            continue
        for category, entry in assignments.items():
            entry_path = path + '/task_generation_locations/' + str(category).replace('~', '~0').replace('/', '~1')
            values = {key: entry[key] for key in ('pickup_dropoff_locations', 'locations', 'dropoff_zone_locations', 'drop_off_zone_locations')
                      if key in entry} if isinstance(entry, dict) else {'': entry}
            for key, value in values.items():
                if not isinstance(value, (list, str)) or (isinstance(value, list) and any(not isinstance(name, str) for name in value)):
                    yield entry_path + ('/' + key if key else ''), 'Location assignments must be one name or a list of names; null, booleans and object-valued names are invalid.'


def validate_department_inputs(config, *, require_identity=False):
    findings = list(department_input_findings(config, require_identity=require_identity))
    if findings:
        raise ValueError('Invalid departments: ' + '; '.join(f'{path}: {message}' for path, message in findings))


def department_reference_findings(config):
    known = {department_identity(row) for row in config.get('departments', [])}
    for name, category in config.get('task_generation', {}).get('categories', {}).items():
        if not isinstance(category, dict):
            continue
        path = '/task_generation/categories/' + str(name).replace('~', '~0').replace('/', '~1')
        for identity in category.get('departments', {}):
            if identity not in known:
                yield path + '/departments/' + identity.replace('~', '~0').replace('/', '~1'), identity
        for index, group in enumerate(category.get('department_groups', [])):
            for position, identity in enumerate(group.get('departments', [])):
                if identity not in known:
                    yield f'{path}/department_groups/{index}/departments/{position}', identity


def replace_departments(config, rows, id_changes=None):
    """Return a candidate with explicit renames applied; never infer identity from order."""
    candidate = deepcopy(config)
    candidate['departments'] = deepcopy(rows)
    validate_department_inputs(candidate)
    old_ids = {department_identity(row) for row in config.get('departments', [])}
    new_ids = {department_identity(row) for row in rows}
    changes = dict(id_changes or {})
    for old, new in changes.items():
        if old not in old_ids or new not in new_ids or not old or not new:
            raise ValueError('Department rename no longer matches the original and replacement identities.')
    if len(set(changes.values())) != len(changes):
        raise ValueError('Department renames must have distinct destinations.')

    def changed_reference(value):
        if not isinstance(value, str):
            raise ValueError('Department references must be strings before departments can be edited.')
        if value in changes:
            return changes[value]
        if value in old_ids and value not in new_ids:
            raise ValueError(f'Department {value!r} is still referenced by demand or tasks; remove those assignments before deleting it.')
        return value

    for category in candidate.get('task_generation', {}).get('categories', {}).values():
        if not isinstance(category, dict):
            continue
        overrides = category.get('departments', {})
        if isinstance(overrides, dict):
            updated = {}
            for identity, override in overrides.items():
                target = changed_reference(identity)
                if target in updated:
                    raise ValueError(f'Renaming would overwrite existing demand settings for {target!r}.')
                updated[target] = override
            if 'departments' in category:
                category['departments'] = updated
        for group in category.get('department_groups', []) or []:
            if isinstance(group, dict) and isinstance(group.get('departments'), list):
                group['departments'] = [changed_reference(value) for value in group['departments']]
    for task in candidate.get('tasks', []):
        if 'department_id' in task:
            task['department_id'] = changed_reference(task['department_id'])
    # Validate the entire proposal before it can replace editor state.
    from amr_generation_inputs import validate_generation_inputs
    validate_generation_inputs(candidate)
    _commit_generated_locations(candidate)
    return candidate


def _commit_generated_locations(candidate):
    """Validate all provisional placements inside the isolated replacement candidate."""
    occupied = {row['name'] for row in candidate.get('locations', [])}
    occupied.update(row['name'] for row in candidate.get('corridors', {}).get('nodes', []))
    occupied.update(row.get('name') for row in candidate.get('departments', []))
    for lift in candidate.get('lifts', []):
        occupied.update(f"{lift['id']}-F{floor}" for floor in lift.get('floor_locations', {}))
    for department in candidate.get('departments', []):
        pending = department.pop('_create_locations', [])
        if not isinstance(pending, list):
            raise ValueError('Provisional department locations must be a list.')
        for item in pending:
            if not isinstance(item, dict):
                raise ValueError('Each provisional department location must be an object.')
            name = item.get('name')
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError('A provisional location needs a nonblank name without surrounding whitespace.')
            if name in occupied:
                raise ValueError(f'Provisional location {name!r} conflicts with an existing or proposed point.')
            position = {key: item.get(key, department.get(key, 0)) for key in ('floor', 'x', 'y')}
            validate_department_inputs({'departments': [position]})
            candidate.setdefault('locations', []).append(dict(
                name=name, floor=int(position['floor']), x=float(position['x']), y=float(position['y']),
                bounding_box=[], inventory_spaces=[], wash_cycle_required=False,
                wash_cycle_duration_sec=300.0, wash_location='', people_area_type='none'))
            occupied.add(name)


def remove_department_drafts(rows, indexes):
    """Discard selected drafts, transferring shared provisional points to survivors."""
    removed = set(indexes)
    survivors = deepcopy([row for index, row in enumerate(rows) if index not in removed])
    pending = {}
    for index, row in enumerate(rows):
        if index in removed:
            for point in row.get('_create_locations', []):
                name = point['name']
                if name in pending and pending[name] != point:
                    raise ValueError(f'Conflicting provisional placements for {name!r}; resolve them before deleting.')
                pending[name] = point
    for name, point in pending.items():
        target = next((row for row in survivors
                       if any(name in department_location_names(entry, zones=zones)
                              for entry in row.get('task_generation_locations', {}).values()
                              for zones in (False, True))), None)
        if target is None:
            continue
        existing = [item for row in survivors for item in row.get('_create_locations', []) if item['name'] == name]
        if any(item != point for item in existing):
            raise ValueError(f'Conflicting provisional placements for {name!r}; resolve them before deleting.')
        if not existing:
            target.setdefault('_create_locations', []).append(deepcopy(point))
    return survivors
