"""Resolve a finding's recorded path before using its human-readable target.

Array indices distinguish duplicate IDs and parallel corridor records. The caller
must verify finding freshness before resolving against a changed configuration.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    kind: str
    key: object
    field: str = ''


def point_names(config):
    names = [row.get('name') for row in config.get('locations', []) if isinstance(row, dict)]
    names += [row.get('name') for row in config.get('corridors', {}).get('nodes', []) if isinstance(row, dict)]
    names += [f"{lift.get('id')}-F{floor}" for lift in config.get('lifts', []) if isinstance(lift, dict)
              for floor in lift.get('floor_locations', {})]
    names += [row.get('name') for row in config.get('departments', []) if isinstance(row, dict)]
    return names


def destination(config, finding):
    if not isinstance(config, dict):
        return None
    parts = [piece.replace('~1', '/').replace('~0', '~') for piece in finding.path.split('/')[1:]]
    section = parts[0] if parts else ''
    if section == 'route_profiles':
        profiles = config.get('route_profiles', {})
        name = finding.target if finding.target in profiles else parts[1] if len(parts) > 1 else None
        if name in profiles and isinstance(profiles[name], dict):
            return Destination('route_profiles', name, parts[-1] if len(parts) > 2 else '')
    indexed = None
    if len(parts) > 1 and parts[1].isdigit() and isinstance(config.get(section), list):
        index = int(parts[1])
        if index < len(config[section]) and isinstance(config[section][index], dict):
            indexed = index
    if indexed is not None:
        row = config[section][indexed]
        field = parts[2] if len(parts) > 2 else ''
        if section in {'amrs', 'payloads', 'tasks', 'lifts'}:
            if section == 'lifts' and len(parts) > 4 and field == 'floor_locations':
                name = f"{row.get('id')}-F{parts[3]}"
                if point_names(config).count(name) == 1:
                    return Destination('point', name, parts[4])
            return Destination(section, indexed, field)
        if section == 'locations' and point_names(config).count(row.get('name')) == 1:
            return Destination('point', row['name'], field)
    if section == 'corridors' and len(parts) > 2 and parts[2].isdigit():
        rows = config.get('corridors', {}).get(parts[1], [])
        index = int(parts[2])
        if isinstance(rows, list) and index < len(rows) and isinstance(rows[index], dict):
            field = parts[3] if len(parts) > 3 else ''
            if parts[1] == 'edges':
                return Destination('edge', index, field)
            if parts[1] == 'nodes' and point_names(config).count(rows[index].get('name')) == 1:
                return Destination('point', rows[index]['name'], field)
    if finding.section in {'locations', 'corridors', 'lifts'} and finding.target and point_names(config).count(finding.target) == 1:
        return Destination('point', finding.target, parts[-1] if finding.code == 'POSITION' else '')
    return None
