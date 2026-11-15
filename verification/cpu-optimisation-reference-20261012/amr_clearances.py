"""Explicit wall and robot separation settings with a legacy geometry adapter."""
import math


def _valid(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0


def clearance_input_findings(config):
    geometry = config.get('geometry',{})
    defaults = geometry.get('clearances',{})
    findings = []
    if not isinstance(defaults,dict):
        return [('/geometry/clearances','Provide wall_m and robot_m as nonnegative distances in metres.')]
    if 'clearances' in geometry:
        for key in ('wall_m','robot_m'):
            if not _valid(defaults.get(key)):
                findings.append(('/geometry/clearances/'+key,'An explicit finite nonnegative distance in metres is required.'))
    for index,robot in enumerate(config.get('amrs',[])):
        if not isinstance(robot,dict) or not isinstance(robot.get('manoeuvring',{}),dict):
            continue
        settings = robot.get('manoeuvring',{})
        path = f'/amrs/{index}/manoeuvring/'
        for key in ('wall_clearance_m','robot_clearance_m','clearance_m'):
            if key in settings and not _valid(settings[key]):
                findings.append((path+key,'Clearance must be a finite nonnegative distance in metres.'))
        for key,default in (('wall_clearance_m','wall_m'),('robot_clearance_m','robot_m')):
            if key not in settings and default not in defaults and 'clearance_m' not in settings:
                findings.append((path+key,'Provide a robot override or explicit project clearance; legacy clearance_m is accepted for existing studies.'))
    return findings


def resolved_clearances(config,manoeuvring):
    """Overrides > project values > recorded legacy margin; no universal default.

    Legacy clearance_m inflated both moving rectangles. Its equivalent total
    inter-robot requirement is twice that margin. New robot_m is the entire gap,
    and interactions use max(A,B), never their sum.
    """
    defaults = config.get('geometry',{}).get('clearances',{})
    legacy = manoeuvring.get('clearance_m')
    wall = manoeuvring.get('wall_clearance_m',defaults.get('wall_m',legacy))
    gap = manoeuvring.get('robot_clearance_m',defaults.get('robot_m',None if legacy is None else 2*legacy))
    if not _valid(wall) or not _valid(gap):
        raise ValueError('Explicit finite wall and robot clearances are required.')
    explicit = bool(defaults) or any(key in manoeuvring for key in ('wall_clearance_m','robot_clearance_m'))
    return {'wall_m':float(wall),'robot_m':float(gap),'explicit':explicit}
