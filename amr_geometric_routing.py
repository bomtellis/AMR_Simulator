"""Versioned planar geometric routing and conservative moving-route claims.

Graph edges express access/topology. Explicit floor bounds and obstacles express
physical space. Route envelope claims precede the later directional-lane model.
"""
import math
from copy import deepcopy
from amr_trajectories import Motion, Pose, Trajectory, TrajectoryError, check_clearance
from amr_sim_payload_instances import is_empty_payload_name
from amr_geometric_traffic import TRAFFIC_MODEL, traffic_enabled, lane_trajectory
from amr_clearances import clearance_input_findings, resolved_clearances
from amr_geometric_occupancy import area_input_findings
from amr_motion_profiles import select_motion_settings, MotionProfileError
from amr_trajectory_dynamics import retime_trajectory
from amr_initial_placements import initial_placement_findings
from amr_reference_inputs import reference_point_options

MODEL = 'geometric_v1'
PARAMETERS = ('minimum_radius_m','pivot_speed_deg_per_sec','initial_heading_deg')


def geometry_enabled(config):
    return isinstance(config,dict) and isinstance(config.get('simulation',{}),dict) and config.get('simulation',{}).get('motion_model','legacy') == MODEL


def geometry_input_findings(config):
    if not isinstance(config,dict):
        return []
    findings = []
    sim = config.get('simulation',{})
    if not isinstance(sim,dict):
        return []
    mode = sim.get('motion_model','legacy')
    if mode not in ('legacy', MODEL):
        return [('/simulation/motion_model', 'Select legacy or geometric_v1 explicitly.')]
    if mode == 'legacy':
        return []
    def error(path, message):
        findings.append((path,message))
    for section in ('amrs','locations'):
        if not isinstance(config.get(section,[]),list):
            error('/'+section,'Expected a list of objects.')
    for section in ('corridors','scenario_testing'):
        if not isinstance(config.get(section,{}),dict):
            error('/'+section,'Expected an object.')
    if findings:
        return findings
    for key in ('nodes','edges'):
        if not isinstance(config.get('corridors',{}).get(key,[]),list):
            error('/corridors/'+key,'Expected a list of objects.')
    if findings:
        return findings
    def number(value, positive=False):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and (value>0 if positive else value>=0)
    def bounds(value):
        return (isinstance(value,list) and len(value)==4 and all(isinstance(v,(int,float)) and not isinstance(v,bool)
                and math.isfinite(v) and abs(v)<1e8 for v in value) and value[0]<value[2] and value[1]<value[3])
    geometry = config.get('geometry',{})
    if not isinstance(geometry,dict) or geometry.get('schema_version') != 1:
        error('/geometry/schema_version','Geometric mode needs an explicit version 1 physical-space model.')
        return findings
    if geometry.get('traffic_model','whole_route_v1') not in ('whole_route_v1',TRAFFIC_MODEL):
        error('/geometry/traffic_model','Select whole_route_v1 or keep_right_v1 explicitly.')
    findings.extend(clearance_input_findings(config))
    floors = geometry.get('floors')
    if not isinstance(floors,list) or not floors:
        error('/geometry/floors','Provide at least one modelled floor with bounds and obstacles.')
        return findings
    known = set()
    for index, floor in enumerate(floors):
        path = f'/geometry/floors/{index}'
        if not isinstance(floor,dict):
            error(path,'A modelled floor must be an object.')
            continue
        findings.extend(area_input_findings(floor,path))
        identity = floor.get('floor')
        if isinstance(identity,bool) or not isinstance(identity,int) or identity in known:
            error(path+'/floor','Floor identifiers must be unique whole numbers.')
        else:
            known.add(identity)
        if not bounds(floor.get('bounds')):
            error(path+'/bounds','Provide ordered finite xmin/ymin/xmax/ymax bounds in metres, within +/-1e8 m.')
        obstacles = floor.get('obstacles')
        if not isinstance(obstacles,list):
            error(path+'/obstacles','Explicitly provide an obstacle list, including [] when clear.')
        else:
            for j, box in enumerate(obstacles):
                if not bounds(box):
                    error(path+f'/obstacles/{j}','Each obstacle needs ordered finite xmin/ymin/xmax/ymax bounds.')
    for i, robot in enumerate(config.get('amrs',[])):
        if not isinstance(robot,dict):
            continue
        if 'movement' in robot:
            try:
                select_motion_settings(robot['movement'],loaded=False)
                for state in ('empty', 'loaded'):
                    settings = robot['movement'][state]
                    for key in ('rotation_speed_deg_per_sec', 'angular_acceleration_deg_per_sec2',
                                'angular_braking_deg_per_sec2'):
                        if settings.get(key) is None:
                            error(f'/amrs/{i}/movement/{state}/{key}',
                                  'Explicit angular limits are required for curved travel, including robots that cannot pivot.')
            except MotionProfileError as exc:
                error(f'/amrs/{i}/movement',str(exc))
        path = f'/amrs/{i}/manoeuvring'
        values = robot.get('manoeuvring',{})
        if not isinstance(values,dict):
            error(path,'Provide explicit manoeuvring parameters.')
            continue
        try:
            reference_point_options(values)
        except ValueError as exc:
            error(path+'/reference_point', str(exc))
        for key in PARAMETERS:
            value = values.get(key)
            valid = (isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
                     if key == 'initial_heading_deg' else number(value, positive=key!='clearance_m'))
            if not valid:
                error(path+'/'+key,f'Explicit finite {key} is required; lengths/rates are positive and clearance is nonnegative.')
        if type(values.get('pivot_allowed')) is not bool:
            error(path+'/pivot_allowed','Explicit true/false pivot permission is required.')
        if len(robot.get('payload_slots',[]) or []) > 1 and robot.get('multi_stop_enabled',True):
            error(f'/amrs/{i}/multi_stop_enabled','Geometric multi-slot loading needs positioned load envelopes; disable batching until that model is supplied.')
    points = {}
    for section, rows in [('locations',config.get('locations',[])),('corridors/nodes',config.get('corridors',{}).get('nodes',[]))]:
        for index, row in enumerate(rows):
            if not isinstance(row,dict):
                continue
            if row.get('floor') not in known:
                error(f'/{section}/{index}/floor','Every route point needs an explicitly modelled floor.')
            points[row.get('name')] = row
            for key in ('x','y'):
                value = row.get(key)
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or abs(value)>=1e8:
                    error(f'/{section}/{index}/{key}','Explicit finite coordinates within +/-1e8 m are required.')
            # Legacy off-graph bay curves are never accepted as geometric motion.
            if row.get('inventory_spaces'):
                error(f'/{section}/{index}/inventory_spaces','Geometric bay entry/exit is not integrated yet; remove bays for this mode or retain legacy mode.')
    for index, edge in enumerate(config.get('corridors',{}).get('edges',[])):
        if isinstance(edge,dict) and edge.get('traffic_mode','keep_right') not in ('keep_right','single_file'):
            error(f'/corridors/edges/{index}/traffic_mode','Use keep_right or single_file.')
        if not isinstance(edge,dict) or 'distance_m' not in edge:
            continue
        a,b = points.get(edge.get('from'),{}),points.get(edge.get('to'),{})
        try:
            actual = math.hypot(float(a['x'])-float(b['x']),float(a['y'])-float(b['y']))
            if not math.isclose(float(edge['distance_m']),actual,rel_tol=1e-9,abs_tol=1e-8):
                error(f'/corridors/edges/{index}/distance_m','Geometric mode uses modelled coordinates; a different distance override cannot be honoured.')
        except (TypeError,ValueError,KeyError):
            pass  # Shared routing/reference checks explain malformed edges.
    for section in ('lifts','people_movements'):
        if config.get(section):
            error('/'+section, f'{section} interaction with geometric motion is not integrated yet; retain legacy mode for this project.')
    if config.get('scenario_testing',{}).get('enabled'):
        error('/scenario_testing/enabled','Scenario outages/slowdowns are not integrated with geometric trajectories yet.')
    if not findings:
        findings.extend(initial_placement_findings(config))
    return findings


def validate_geometry_inputs(config):
    findings = geometry_input_findings(config)
    if findings:
        raise ValueError('Invalid geometric model: '+'; '.join(f'{p}: {m}' for p,m in findings))


def route_trajectory(sim, amr, route, start, end, payload, orientation, start_heading_deg=None, movement='forward'):
    from amr_reference_trajectories import plan_reference_trajectory, plan_reference_lateral_trajectory
    parameters = amr.manoeuvring
    reference_options = reference_point_options(parameters)
    clearances = resolved_clearances(sim.config,parameters)
    loaded = payload is not None and not is_empty_payload_name(payload.name)
    settings = select_motion_settings(amr.movement,loaded=loaded) if getattr(amr,'movement',None) is not None else None
    radius = (settings.minimum_radius_m or parameters['minimum_radius_m']) if settings else parameters['minimum_radius_m']
    pivot_allowed = settings.pivot_allowed if settings else parameters['pivot_allowed']
    pivot_speed = (settings.rotation_speed_deg_per_sec or parameters['pivot_speed_deg_per_sec']) if settings else parameters['pivot_speed_deg_per_sec']
    speed = settings.forward_speed_m_per_sec if settings else amr.speed_m_per_sec
    nodes = {row['name']: row for row in sim.config.get('corridors',{}).get('nodes',[])}
    nodes.update({row['name']:row for row in sim.config['locations']})
    names = [start.name]+[edge['to'] for edge in route['edges']]
    points = [(float(nodes[name]['x']),float(nodes[name]['y'])) for name in names]
    heading = amr.rotation_deg if start_heading_deg is None else start_heading_deg
    if movement not in ('forward', 'reverse', 'lateral'):
        raise TrajectoryError('invalid_input', 'Unknown requested movement type.')
    if movement != 'forward' and settings is None:
        raise TrajectoryError('invalid_input', 'Recovery needs explicit empty and loaded movement settings.')
    static = len(points)==1
    if static:
        pose=Pose(*points[0],math.radians(heading))
        # A unit-duration stationary envelope is used only by the clearance checker.
        trajectory=Trajectory((Motion('pivot',pose,pose,0,1),),parameters['minimum_radius_m'],parameters['pivot_allowed'])
    elif movement == 'lateral':
        # A lateral leg must follow one straight graph alignment; do not cut
        # across an intermediate graph corner by joining its endpoints.
        distance = math.hypot(end.x-start.x, end.y-start.y)
        dx,dy = end.x-start.x,end.y-start.y
        projections = [((x-start.x)*dx+(y-start.y)*dy)/distance for x,y in points] if distance>0 else []
        if (not projections or any(abs((x-start.x)*dy-(y-start.y)*dx)/distance>1e-8 for x,y in points)
                or any(b<a-1e-8 for a,b in zip(projections,projections[1:]))):
            raise TrajectoryError('infeasible_route', 'Lateral recovery needs a straight graph alignment.')
        trajectory = plan_reference_lateral_trajectory(Pose(start.x,start.y,math.radians(heading)),points[-1],
            speed_m_per_sec=settings.lateral_speed_m_per_sec or speed,lateral_allowed=settings.lateral_allowed,
            **reference_options)
    else:
        if movement == 'reverse':
            speed = settings.reverse_speed_m_per_sec
        trajectory = plan_reference_trajectory(points, minimum_radius_m=radius,
            speed_m_per_sec=speed, pivot_allowed=pivot_allowed,
            pivot_speed_deg_per_sec=pivot_speed, start_heading_deg=heading,
            movement=movement, **reference_options)
    length,width = amr.length_m,amr.width_m
    if payload is not None and not is_empty_payload_name(payload.name):
        pl,pw,_ = sim._payload_orientation_dimensions(payload,orientation)
        length,width = max(length,pl),max(width,pw)
    lane_sections = []
    if not static and traffic_enabled(sim.config) and movement == 'forward':
        trajectory,lane_sections = lane_trajectory(trajectory,points,route['edges'],
            loaded_width_m=width,clearance_m=clearances['wall_m'],speed_m_per_sec=speed,
            robot_clearance_m=clearances['robot_m'] if clearances['explicit'] else None)
    floor = next(row for row in sim.config['geometry']['floors'] if row['floor']==start.floor)
    a,b,c,d = floor['bounds']
    walls = [(-1e9,-1e9,a,1e9),(c,-1e9,1e9,1e9),(a,-1e9,c,b),(a,d,c,1e9)]
    result = check_clearance(trajectory,length_m=length,width_m=width,
        clearance_m=clearances['wall_m'],obstacles=floor['obstacles']+walls)
    if result['status'] != 'clear':
        raise TrajectoryError(result['status'],f'Route {start.name} to {end.name}: motion {result.get("motion")}, obstacle {result.get("obstacle")}.')
    if not static and settings is not None:
        try:
            trajectory=retime_trajectory(trajectory,settings)
        except MotionProfileError as exc:
            raise TrajectoryError(exc.reason,str(exc)) from exc
    result['clearances'] = clearances
    # Bounding boxes enclose all continuous swept motion, including pivot corners.
    # Reserving the complete envelope is intentionally conservative until lanes.
    pad = math.hypot(length/2+clearances['wall_m'],width/2+clearances['wall_m'])
    xs,ys = [],[]
    for motion in trajectory.motions:
        if motion.centre_orbit_radius_m > 0 and motion.kind in ('arc', 'pivot'):
            centre = (motion.centre if motion.kind == 'arc' else
                      (motion.reference_pose_at(0).x, motion.reference_pose_at(0).y))
            xs.extend([centre[0]-motion.centre_orbit_radius_m,centre[0]+motion.centre_orbit_radius_m])
            ys.extend([centre[1]-motion.centre_orbit_radius_m,centre[1]+motion.centre_orbit_radius_m])
        else:
            xs.extend([motion.start.x,motion.end.x]);ys.extend([motion.start.y,motion.end.y])
    envelope = (min(xs)-pad,min(ys)-pad,max(xs)+pad,max(ys)+pad)
    return None if static else trajectory, envelope, result, (length,width), names,lane_sections


def envelopes_overlap(a,b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def first_route_slot(reservations, envelope, requested, duration, owner, separation):
    time = requested
    for _ in range(len(reservations)+1):
        blocked = [row for row in reservations if row['owner'] != owner
            and envelopes_overlap(envelope,row['envelope'])
            and time < row['end']+separation and time+duration > row['start']-separation]
        if not blocked:
            return time
        time = max(row['end']+separation for row in blocked)
    raise TrajectoryError('search_limit','Moving-route reservation search exhausted.')


def simulation_project_from_study(study):
    """Explicit migration into a new single-delivery project; never alter a study.

    Floor bounds are a reviewable rectangle around the supplied route/obstacles.
    The exported robot starts aligned with the first segment, at pickup A.
    """
    p = study['parameters']
    reference_point_options(p)
    points = deepcopy(study['points'])
    obstacles = deepcopy(study['obstacles'])
    names = ['A']+[f'P{i}' for i in range(2,len(points))]+['B']
    rows = [dict(name=name,floor=0,x=point[0],y=point[1]) for name,point in zip(names,points)]
    margin = 2*max(p['minimum_radius_m'],p['robot_length_m'],p['robot_width_m'],p['payload_length_m'],p['payload_width_m'])+1
    xs = [point[0] for point in points]+[v for box in obstacles for v in (box[0],box[2])]
    ys = [point[1] for point in points]+[v for box in obstacles for v in (box[1],box[3])]
    width = max(p['robot_width_m'],p['payload_width_m'])+2*p['clearance_m']
    result = {
        'simulation': {'start_datetime':'2026-01-05T00:00:00','end_datetime':'2026-01-05T00:10:00',
                       'motion_model':MODEL, 'precompute_static_routes':False},
        'building': {'charge_locations':['A'],'enable_idle_return':False,'load_unload_time_sec':2},
        'locations':[rows[0],rows[-1]],
        'corridors':{'auto_connect':False,'nodes':rows[1:-1],
            'edges':[{'from':a,'to':b,'width_m':max(3,width),'bidirectional':True} for a,b in zip(names,names[1:])]},
        'geometry':{'schema_version':1,'floors':[{'floor':0,'bounds':[min(xs)-margin,min(ys)-margin,max(xs)+margin,max(ys)+margin],
                                                  'obstacles':obstacles}]},
        'amrs':[{'id':'R','quantity':1,'length_m':p['robot_length_m'],'width_m':p['robot_width_m'],
            'speed_m_per_sec':p['speed_m_per_sec'],'payload_capacity_kg':100,
            'payload_length_capacity_m':max(2,p['payload_length_m']), 'payload_width_capacity_m':max(2,p['payload_width_m']),
            'payload_height_capacity_m':2,'battery_capacity_kwh':10,'battery_charge_rate_kw':2,
            'recharge_threshold_percent':1,'manoeuvring':{
                **{key:p[key] for key in ('minimum_radius_m','pivot_speed_deg_per_sec','pivot_allowed','clearance_m')},
                'initial_heading_deg':math.degrees(math.atan2(points[1][1]-points[0][1],points[1][0]-points[0][0]))}}],
        'payloads':[{'name':'Load','weight_kg':10,'length_m':p['payload_length_m'],'width_m':p['payload_width_m'],
                     'height_m':1,'allowed_carry_orientations':['lengthways']}],
        'lifts':[], 'tasks':[{'id':'Geometry-reference','pickup':'A','dropoff':'B','payload':'Load'}],
        'task_generation':{'enabled':False},
    }
    if 'reference_point' in p:
        result['amrs'][0]['manoeuvring']['reference_point'] = deepcopy(p['reference_point'])
    validate_geometry_inputs(result)
    return result
