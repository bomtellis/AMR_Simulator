"""Project-local index plus discovery of existing and backed-up stress studies."""
from datetime import datetime
import os
from pathlib import Path

from amr_project_runs import read_json, write_json


def index_path(source):
    source = Path(source).resolve()
    return source.with_name(source.name + '.stress-history.json')


def remembered_paths(source):
    index = index_path(source)
    if not index.exists():
        return []
    value = read_json(index)
    if value.get('version') != 1 or not isinstance(value.get('studies'), list):
        raise ValueError('Invalid stress-study history index')
    return [(index.parent / item).resolve() for item in value['studies'] if isinstance(item, str)]


def remember_study(source, path):
    from amr_scenario_study import study_lock
    index = index_path(source)
    with study_lock(index):
        paths = list(dict.fromkeys([Path(path).resolve(), *remembered_paths(source)]))
        locations = []
        for item in paths:
            try:
                locations.append(os.path.relpath(item, index.parent))
            except ValueError:
                locations.append(str(item))
        write_json(index, dict(version=1, studies=locations))


def discover_studies(source=None, *, project_id=None, known=(), results_root=None):
    """Scan only adjacent study files, never recurse through large run outputs."""
    from amr_scenario_study import validate_study_document
    explicit = {Path(path).resolve() for path in known if path}
    if source:
        try:
            explicit.update(remembered_paths(source))
        except (OSError, ValueError, TypeError):
            pass  # Adjacent discovery still works if the optional index is damaged.
    directories = {path.parent for path in explicit}
    if source:
        directories.add(Path(source).resolve().parent)
    if results_root:
        directories.add(Path(results_root).resolve())
    paths = set(explicit)
    for directory in directories:
        paths.update(directory.glob('*.stress.json'))
    entries = []
    for path in paths:
        try:
            state = read_json(path)
            validate_study_document(state)
            owner = state.get('source_project_id')
            if owner and project_id and owner != project_id and path not in explicit:
                continue
            modified = path.stat().st_mtime
            entries.append(dict(path=path, modified=modified,
                updated=datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M'),
                status=state['status'], trials=len(state['results']),
                mode=state['settings'].get('data_mode', 'full')))
        except (OSError, ValueError, TypeError, KeyError):
            if path in explicit:
                entries.append(dict(path=path, modified=0, updated='', status='Missing or unreadable', trials='', mode=''))
    return sorted(entries, key=lambda item: (-item['modified'], str(item['path'])))
