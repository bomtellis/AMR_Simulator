"""Project-owned presentation layers and editing locks; never route permissions."""
from copy import deepcopy

DEFAULT = 'Default'


class LayerLockedError(ValueError):
    pass


def definitions(config):
    result = {DEFAULT:dict(visible=True,locked=False)}
    raw = config.get('editor_layers')
    if raw is None:
        return result
    if (not isinstance(raw,dict) or type(raw.get('version')) is not int
            or raw['version'] != 1 or not isinstance(raw.get('layers'),dict)):
        raise ValueError('Editor layers require version 1 and a layers object.')
    for name, options in raw['layers'].items():
        if not isinstance(name,str) or not name.strip() or name != name.strip():
            raise ValueError('Layer names must be nonblank without surrounding whitespace.')
        if (not isinstance(options,dict) or set(options) != {'visible','locked'}
                or any(type(options[key]) is not bool for key in ('visible','locked'))):
            raise ValueError(f'Layer {name} requires boolean visible and locked settings.')
        result[name] = dict(options)
    return result


def point_rows(config):
    for section in ('locations','departments'):
        rows = config.get(section,[])
        for row in rows if isinstance(rows,list) else []:
            if isinstance(row,dict):
                yield (section,row.get('name')),row
    corridors = config.get('corridors',{})
    for row in corridors.get('nodes',[]) if isinstance(corridors,dict) and isinstance(corridors.get('nodes',[]),list) else []:
        if isinstance(row,dict):
            yield ('nodes',row.get('name')),row
    lifts = config.get('lifts',[])
    for lift in lifts if isinstance(lifts,list) else []:
        if not isinstance(lift,dict) or not isinstance(lift.get('floor_locations',{}),dict):
            continue
        for floor,row in lift.get('floor_locations',{}).items():
            if isinstance(row,dict):
                yield ('lift',f'{lift.get("id")}-F{floor}'),row


def layer_name(row):
    return row.get('editor_layer',DEFAULT)


def validate(config):
    if not isinstance(config,dict):
        return
    layers = definitions(config)
    corridors = config.get('corridors',{})
    edges = corridors.get('edges',[]) if isinstance(corridors,dict) else []
    for row in [row for _,row in point_rows(config)] + (edges if isinstance(edges,list) else []):
        if not isinstance(row,dict):
            continue
        name = layer_name(row)
        if not isinstance(name,str) or name not in layers:
            raise ValueError(f'Unknown editor layer {name!r}; define it or reassign the object.')


def locked_points(config):
    layers = definitions(config)
    names = {key[1] for key,row in point_rows(config) if layers[layer_name(row)]['locked']}
    for edge in config.get('corridors',{}).get('edges',[]):
        if layers[layer_name(edge)]['locked']:
            names.update((edge['from'],edge['to']))
    return names


def assert_unlocked_changes(before, after):
    layers = definitions(before)
    if not any(layer['locked'] for layer in layers.values()):
        return
    old_rows, new_rows = dict(point_rows(before)),dict(point_rows(after))
    for key,row in new_rows.items():
        if key not in old_rows and layers.get(layer_name(row),{}).get('locked'):
            raise LayerLockedError(f'Cannot create {key[1]} on locked layer {layer_name(row)}.')
    for key,row in old_rows.items():
        if layers[layer_name(row)]['locked'] and new_rows.get(key) != row:
            raise LayerLockedError(f'{key[1]} is on locked layer {layer_name(row)}. Unlock that layer before editing.')
    # A locked corridor protects its endpoints' position, not unrelated service
    # properties on the attached location. Reciprocal records share this lock.
    old_points = {key[1]:row for key,row in old_rows.items()}
    new_points = {key[1]:row for key,row in new_rows.items()}
    edges = before.get('corridors',{}).get('edges',[])
    changed = after.get('corridors',{}).get('edges',[])
    for edge in changed:
        if layers.get(layer_name(edge),{}).get('locked') and edge not in edges:
            raise LayerLockedError(f'Cannot create or change a corridor on locked layer {layer_name(edge)}.')
    for edge in edges:
        if not layers[layer_name(edge)]['locked']:
            continue
        pair = {edge['from'],edge['to']}
        old_group = [e for e in edges if {e['from'],e['to']} == pair]
        new_group = [e for e in changed if {e['from'],e['to']} == pair]
        moved = any(tuple(old_points.get(n,{}).get(k) for k in ('x','y','floor')) !=
                    tuple(new_points.get(n,{}).get(k) for k in ('x','y','floor')) for n in pair)
        if old_group != new_group or moved:
            raise LayerLockedError(f'Corridor {edge["from"]} → {edge["to"]} is on locked layer {layer_name(edge)}. Unlock it before editing.')


def set_layer(config, name, *, visible=True, locked=False):
    result = deepcopy(config)
    layers = definitions(config)
    layers[name] = dict(visible=visible,locked=locked)
    result['editor_layers'] = dict(version=1,layers=layers)
    validate(result)
    return result


def assign(config, points, edges, name):
    if name not in definitions(config):
        raise ValueError('Select an existing model layer.')
    result = deepcopy(config)
    for key,row in point_rows(result):
        if key[1] in points:
            row['editor_layer'] = name
    for edge in result.get('corridors',{}).get('edges',[]):
        if tuple(sorted((edge['from'],edge['to']))) in edges:
            edge['editor_layer'] = name
    return result
