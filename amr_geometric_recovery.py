"""Verified retreat candidates along the existing graph, never invented links.

Passing-place rectangles select graph anchors whose complete stopped footprint
fits. With no marked places, eligible graph anchors may be used. The caller must
prove the proposed retreat actually enables the waiting task before committing.
This bounded search is not a proof of deadlock or geometric infeasibility.
"""
import math

from amr_geometric_occupancy import automatic_stop_areas, select_passing_place
from amr_clearances import resolved_clearances
from amr_sim_models import Location
from amr_trajectories import Pose, TrajectoryError

MAX_RECOVERY_CANDIDATES = 256


def retreat_candidates(sim, robot, now):
    if getattr(robot, 'movement', None) is None:
        raise TrajectoryError('missing_parameters', 'Recovery requires explicit empty and loaded movement settings.')
    start = sim._robot_location(robot)
    floor = next(f for f in sim.config['geometry']['floors'] if f['floor']==start.floor)
    points = {p['name']:p for p in sim.config.get('corridors',{}).get('nodes',[])}
    points.update({p['name']:p for p in sim.config['locations']})
    targets = [p for p in points.values() if p['floor']==start.floor and p['name']!=start.name]
    if len(targets)*3 > MAX_RECOVERY_CANDIDATES:
        raise TrajectoryError('search_limit', 'Recovery candidate budget exhausted; no infeasibility or deadlock is inferred.')
    separation = resolved_clearances(sim.config, robot.manoeuvring)
    places = floor.get('passing_places', [])
    result, failures = [], []
    for point in sorted(targets,key=lambda p:p['name']):
        target = Location(name=point['name'],floor=point['floor'],x=point['x'],y=point['y'])
        for movement in ('forward','reverse','lateral'):
            try:
                route = sim._same_floor_segments(robot,start,target,start_time_value=now,movement=movement)
                if route is None or not route[0] or route[2] <= 0:
                    continue
                segments, duration, distance = route
                last = next(s for s in reversed(segments) if s.get('motion_model')=='geometric_v1')
                heading = last['amr_rotation_end_deg']
                place_id = None
                if places:
                    fitting = select_passing_place(floor,[dict(area_id=p['id'],
                        pose=Pose(target.x,target.y,math.radians(heading)),route_distance_m=distance) for p in places],
                        length_m=robot.length_m,width_m=robot.width_m,wall_clearance_m=separation['wall_m'],
                        protected_areas=automatic_stop_areas(sim.config,start.floor))
                    if fitting is None:
                        continue
                    place_id = fitting['area_id']
                sim._check_geometric_occupancy(robot,segments,now,start,robot.rotation_deg,reserve=False)
                energy = sim._charge_motor_energy_kwh(robot,segments)
                if robot.battery_energy_kwh()-energy < robot.min_reserve_energy_kwh()-1e-12:
                    failures.append(dict(target=target.name,movement=movement,reason='insufficient_energy'))
                    continue
                result.append(dict(segments=segments,duration=duration,distance=distance,energy=energy,
                    start=start,target=target,heading=heading,movement=movement,passing_place=place_id))
            except (TrajectoryError, ValueError) as exc:
                reason = getattr(exc,'reason','invalid_input')
                if reason == 'search_limit':
                    raise TrajectoryError('search_limit',str(exc)) from exc
                failures.append(dict(target=target.name,movement=movement,reason=reason,detail=str(exc)))
    result.sort(key=lambda p:(p['distance'],p['duration'],p['target'].name,p['movement']))
    return result, failures
