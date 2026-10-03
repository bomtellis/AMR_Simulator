"""Conservative input dependencies for existing preflight checks.

Unchanged inputs never grant run readiness after a project edit. Unknown or
legacy checks depend on the entire configuration until their contract is audited.
"""
import hashlib
import json
from pathlib import Path

GRAPH = ('locations', 'corridors', 'lifts')
GROUPS = {
    'structure': ('Section structure', ('*',)),
    'generation': ('Generation input contracts', ('task_generation', 'departments', 'tasks')),
    'values': ('Numbers and schedules', ('*',)),
    'references': ('Identifiers and references', ('*',)),
    'graph': ('Graph connectivity', (*GRAPH, 'tasks', 'route_profiles')),
    'compatibility': ('Payload compatibility', ('amrs', 'payloads')),
    'legacy': ('Existing validation', ('*',)),
    'drawings': ('Drawing availability', ('floor_dxf_files', 'floor_pdf_underlays', '@drawings')),
    'scope': ('Model assumptions', ('corridors', 'lifts', 'route_profiles')),
}
INPUT_LABELS = {'*': 'Whole project', '@drawings': 'Drawing availability', 'amrs': 'Robots',
                'payloads': 'Payloads', 'corridors': 'Corridors', 'locations': 'Locations',
                'lifts': 'Lifts', 'tasks': 'Tasks', 'route_profiles': 'Route profiles',
                'task_generation': 'Demand rules', 'departments': 'Departments',
                'floor_dxf_files': 'DXF mappings', 'floor_pdf_underlays': 'PDF mappings'}


def input_names(keys):
    return ', '.join(INPUT_LABELS.get(key, key.replace('_', ' ').capitalize()) for key in keys)


def dependencies(finding):
    code, section = finding.code, finding.section
    local = (section,) if section and section != 'project' else ('*',)
    if code in {'NUMBER', 'INTEGER', 'SCHEDULE', 'IDENTIFIER', 'GENERATION_INPUT', 'GENERATION_UNSUPPORTED'}:
        return local
    if code == 'RUN_PERIOD':
        return ('simulation',)
    if code == 'DUPLICATE':
        return GRAPH if section in GRAPH else local
    if code in {'POSITION', 'CROSS_FLOOR', 'LOCATION_ISOLATED'}:
        return GRAPH
    if code in {'REFERENCE', 'PROFILE_REFERENCE', 'GENERATION_REFERENCE'}:
        return tuple(sorted(set(local + GRAPH + ('payloads', 'route_profiles', 'task_generation', 'departments'))))
    if code in {'RECOVERY_INPUT', 'RECOVERY_POLICY', 'PAYLOAD_ID_TYPE'}:
        return ('tasks', 'payloads')
    if code == 'TASK_UNREACHABLE':
        return (*GRAPH, 'tasks', 'route_profiles')
    if code == 'PAYLOAD_NO_AMR':
        return ('payloads', 'amrs')
    if code == 'DRAWING_MISSING':
        return (*local, '@drawings')
    if code in {'MODEL_SCOPE', 'LIFT_MODEL_SCOPE', 'PROFILE_POLICY'}:
        return local
    return ('*',)


def drawing_state(config, base_path=None):
    state = {}
    if not isinstance(config, dict):
        return state
    for section in ('floor_dxf_files', 'floor_pdf_underlays'):
        entries = config.get(section, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            value = entry.get('filepath') if isinstance(entry, dict) else None
            if isinstance(value, str) and value:
                path = Path(value)
                if not path.is_absolute() and base_path:
                    path = Path(base_path) / path
                path = path.absolute()
                try:
                    state[str(path)] = path.is_file()
                except (OSError, ValueError):
                    state[str(path)] = None
    return state


def current_drawings(recorded):
    result = {}
    for name in recorded:
        try:
            result[name] = Path(name).is_file()
        except (OSError, ValueError):
            result[name] = None
    return result


def input_hash(config, dependency, external):
    if dependency == '*':
        value = config
    elif dependency == '@drawings':
        value = external
    else:
        value = {'present': isinstance(config, dict) and dependency in config,
                 'value': config.get(dependency) if isinstance(config, dict) else None}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def snapshot(config, deps, external):
    return {key: input_hash(config, key, external) for key in deps}


def changed_inputs(recorded, config, external):
    return [key for key, checksum in recorded.items() if input_hash(config, key, external) != checksum]
