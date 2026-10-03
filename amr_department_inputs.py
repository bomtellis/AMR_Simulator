"""Department identity/position contracts and atomic identity-aware replacements."""
from copy import deepcopy
import math


def department_identity(row):
    return str(row.get('id', '') or '').strip() or str(row.get('name', '') or '').strip()


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
    return candidate
