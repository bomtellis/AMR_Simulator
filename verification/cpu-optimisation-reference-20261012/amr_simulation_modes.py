"""Explicit user-facing simulation modes and lossless structural transitions.

Historical geometric studies remain a compatibility mode, including those with
constant-speed or whole-route models. Selecting Detailed does not supply robot
engineering values, geometry or placements. Editing incomplete inputs is allowed;
the shared run checks report the remaining requirements.
"""
from copy import deepcopy


def _contract(config):
    findings = []
    if not isinstance(config, dict):
        return None, [('/', 'Project configuration must be an object.')]
    simulation = config.get('simulation', {})
    if not isinstance(simulation, dict):
        return None, [('/simulation', 'Simulation settings must be an object.')]
    explicit = 'mode' in simulation
    chosen = simulation.get('mode')
    motion = simulation.get('motion_model', 'legacy')
    if explicit and chosen not in ('simple', 'detailed'):
        findings.append(('/simulation/mode', 'Select simple or detailed; historical compatibility is resolved only when mode is omitted.'))
    if motion not in ('legacy', 'geometric_v1'):
        findings.append(('/simulation/motion_model', 'Select legacy or geometric_v1 explicitly.'))
    if explicit:
        required = {'simple': 'legacy', 'detailed': 'geometric_v1'}.get(chosen) if isinstance(chosen, str) else None
        if required and simulation.get('motion_model') != required:
            findings.append(('/simulation/motion_model', f'Explicit {chosen} mode requires motion_model={required}; model fields must agree.'))
    geometry = config.get('geometry', {})
    traffic = None
    if motion == 'geometric_v1' or chosen == 'detailed':
        if not isinstance(geometry, dict):
            findings.append(('/geometry', 'Active geometric settings must be an object.'))
        else:
            traffic = geometry.get('traffic_model', 'whole_route_v1')
            if traffic not in ('whole_route_v1', 'keep_right_v1'):
                findings.append(('/geometry/traffic_model', 'Select whole_route_v1 or keep_right_v1 explicitly.'))
            if chosen == 'detailed' and geometry.get('traffic_model') != 'keep_right_v1':
                findings.append(('/geometry/traffic_model', 'Explicit detailed mode requires traffic_model=keep_right_v1.'))
    mode = chosen if explicit else ('simple' if motion == 'legacy' else 'geometric_compatibility')
    return dict(schema_version=1, mode=mode, motion_model=motion, traffic_model=traffic,
                selection='explicit' if explicit else 'legacy_adapter'), findings


def resolve_simulation_mode(config):
    """Resolve only the model contract, allowing old frozen evidence to be read.

    This deliberately does not require new robot parameters or physical inputs.
    Structural contradictions are errors, never an implicit precedence rule.
    Dormant geometry has no active traffic model in Simple mode.
    """
    mode, findings = _contract(config)
    if findings:
        raise ValueError('Invalid simulation mode: ' + '; '.join(f'{path}: {message}' for path, message in findings))
    return mode


def mode_input_findings(config):
    """Check the mode contract and explicit Detailed requirements without recursion.

    Complete geometry, numerical limits, collisions and placements are validated
    by geometry_input_findings. This function never calls that validator.
    """
    mode, findings = _contract(config)
    if findings or mode['mode'] != 'detailed':
        return findings
    geometry = config.get('geometry', {})
    if not isinstance(geometry.get('initial_placements'), list):
        findings.append(('/geometry/initial_placements',
                         'Detailed mode requires explicit per-robot initial placements, including a single robot.'))
    defaults = geometry.get('clearances', {})
    defaults = defaults if isinstance(defaults, dict) else {}
    robots = config.get('amrs', [])
    if not isinstance(robots, list):
        return findings + [('/amrs', 'Detailed mode requires a robot type list.')]
    for index, robot in enumerate(robots):
        if not isinstance(robot, dict):
            findings.append((f'/amrs/{index}', 'A robot type must be an object.'))
            continue
        base = f'/amrs/{index}'
        movement = robot.get('movement')
        if (not isinstance(movement, dict) or type(movement.get('schema_version')) is not int
                or movement['schema_version'] != 2):
            findings.append((base+'/movement/schema_version',
                             'Detailed mode requires explicit movement schema 2 and complete empty/loaded settings.'))
        manoeuvring = robot.get('manoeuvring', {})
        manoeuvring = manoeuvring if isinstance(manoeuvring, dict) else {}
        if 'reference_point' not in manoeuvring:
            findings.append((base+'/manoeuvring/reference_point',
                             'Detailed mode requires explicit reference offsets, timing reference and pivot axis, including zero offsets.'))
        for override, project in (('wall_clearance_m', 'wall_m'), ('robot_clearance_m', 'robot_m')):
            if override not in manoeuvring and project not in defaults:
                findings.append((base+'/manoeuvring/'+override,
                                 'Detailed mode requires separate explicit wall and robot clearances; use a robot override or project default.'))
    return findings


def preview_mode_change(config, target):
    """Preview structural edits and full geometric readiness without mutating input."""
    if target not in ('simple', 'detailed'):
        raise ValueError('Select simple or detailed.')
    if not isinstance(config, dict):
        raise ValueError('Project configuration must be an object.')
    result = deepcopy(config)
    if 'simulation' in result and not isinstance(result['simulation'], dict):
        raise ValueError('Repair the simulation object before changing mode.')
    simulation = result.setdefault('simulation', {})
    changes = []

    def set_value(container, key, value, path):
        present = key in container
        before = deepcopy(container.get(key))
        if not present or before != value:
            changes.append(dict(path=path, old_value=before, new_value=value, old_present=present))
            container[key] = value

    set_value(simulation, 'mode', target, '/simulation/mode')
    set_value(simulation, 'motion_model', 'legacy' if target == 'simple' else 'geometric_v1',
              '/simulation/motion_model')
    if target == 'detailed':
        if 'geometry' in result and not isinstance(result['geometry'], dict):
            raise ValueError('Repair the geometry object before selecting Detailed mode.')
        geometry = result.setdefault('geometry', {})
        set_value(geometry, 'traffic_model', 'keep_right_v1', '/geometry/traffic_model')
    from amr_geometric_routing import geometry_input_findings
    findings = geometry_input_findings(result)
    return dict(config=result, changes=changes, findings=findings, mode=resolve_simulation_mode(result))


def apply_mode_change(config, target):
    """Apply only the previewed structural edit; incomplete projects remain editable."""
    return preview_mode_change(config, target)['config']
