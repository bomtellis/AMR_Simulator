"""Keep-right lane trajectories and conservative continuous swept-time claims.

Lane changes are two tangent arcs, not lateral jumps. Centre-line junction turns
retain their original radii. Temporal cells enclose all motion within each cell;
they are reservations, not sampled collision tests. Units: metres and seconds.
"""
import math

from amr_trajectories import EPS, Motion, Pose, Trajectory, TrajectoryError, footprint

TRAFFIC_MODEL = 'keep_right_v1'
CELL_SECONDS = .25
MAX_CELLS = 50000
MAX_PAIR_CHECKS = 1000000


def traffic_enabled(config):
    return config.get('geometry', {}).get('traffic_model', 'whole_route_v1') == TRAFFIC_MODEL


def _arc(start, radius, sweep, speed):
    sign = 1 if sweep > 0 else -1
    centre = (start.x-sign*radius*math.sin(start.heading),
              start.y+sign*radius*math.cos(start.heading))
    heading = start.heading+sweep
    end = Pose(centre[0]+sign*radius*math.sin(heading),
               centre[1]-sign*radius*math.cos(heading), heading)
    length = radius*abs(sweep)
    return Motion('arc', start, end, length, length/speed, sweep, radius, centre)


def lane_trajectory(trajectory, points, edges, *, loaded_width_m, clearance_m, speed_m_per_sec):
    """Replace each straight with a right lane and smooth centre-line transitions.

    A junction starts/ends at the existing tangent points. Single-file sections
    remain on the centre line. A too-short two-way lane is explicitly infeasible;
    users may specify single_file on that edge to model a constrained section.
    """
    output, sections = [], []
    for motion in trajectory.motions:
        if motion.kind != 'line':
            output.append(motion)
            continue
        midpoint = ((motion.start.x+motion.end.x)/2,(motion.start.y+motion.end.y)/2)
        matches = []
        for index, (a,b,edge) in enumerate(zip(points,points[1:],edges)):
            dx,dy = b[0]-a[0],b[1]-a[1]
            distance = math.hypot(dx,dy)
            along = ((midpoint[0]-a[0])*dx+(midpoint[1]-a[1])*dy)/distance
            cross = abs((midpoint[0]-a[0])*dy-(midpoint[1]-a[1])*dx)/distance
            if cross < 1e-7 and -EPS <= along <= distance+EPS:
                matches.append((index,edge))
        if not matches:
            raise TrajectoryError('invalid_input','A lane straight has no supporting graph edge.')
        index,edge = min(matches,key=lambda row:float(row[1]['width_m']))
        width = float(edge['width_m'])
        required = loaded_width_m+2*clearance_m
        single = edge.get('traffic_mode','keep_right') == 'single_file' or 2*required > width+EPS
        sections.append({'edge_index':index,'mode':'single_file' if single else 'keep_right',
                         'offset_m':0 if single else width/4,'effective_width_m':width})
        if single:
            output.append(motion)
            continue
        offset = width/4
        # Increase radius only when necessary for an offset larger than 2R.
        radius = max(trajectory.minimum_radius_m,offset/2)
        angle = math.acos(max(-1.,min(1.,1-offset/(2*radius))))
        run = 2*radius*math.sin(angle)
        straight = motion.length_m-2*run
        if straight < -EPS:
            raise TrajectoryError('infeasible_route',
                f'Edge {index+1}: keep-right transitions require {2*run:.6g} m of straight; '
                f'only {motion.length_m:.6g} m is available. Model a single-file section or extend the approach.')
        start = motion.start
        for sweep in (-angle,angle):
            arc = _arc(start,radius,sweep,speed_m_per_sec)
            output.append(arc)
            start = arc.end
        if straight > EPS:
            end = Pose(start.x+straight*math.cos(start.heading),start.y+straight*math.sin(start.heading),start.heading)
            output.append(Motion('line',start,end,straight,straight/speed_m_per_sec))
            start = end
        for sweep in (angle,-angle):
            arc = _arc(start,radius,sweep,speed_m_per_sec)
            output.append(arc)
            start = arc.end
        if math.hypot(start.x-motion.end.x,start.y-motion.end.y) > 1e-7:
            raise TrajectoryError('invalid_input','Lane transition endpoints disagree.')
    return Trajectory(tuple(output),trajectory.minimum_radius_m,trajectory.pivot_allowed),sections


def polygon_bounds(polygon):
    return (min(p[0] for p in polygon),min(p[1] for p in polygon),
            max(p[0] for p in polygon),max(p[1] for p in polygon))


def polygons_overlap(a,b):
    """Strict convex SAT: boundary contact is allowed; margins supply clearance."""
    for polygon in (a,b):
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            nx,ny = p[1]-q[1],q[0]-p[0]
            norm = math.hypot(nx,ny)
            if norm <= EPS:
                continue
            nx,ny = nx/norm,ny/norm
            pa,pb = [nx*x+ny*y for x,y in a],[nx*x+ny*y for x,y in b]
            if max(pa) <= min(pb)+EPS or max(pb) <= min(pa)+EPS:
                return False
    return True


def swept_cells(trajectory, *, length_m, width_m, clearance_m, max_cells=MAX_CELLS):
    """Return relative time intervals with certified enclosing convex footprints."""
    cells,elapsed = [],0.
    corner = math.hypot(length_m/2+clearance_m,width_m/2+clearance_m)
    for motion in trajectory.motions:
        count = max(1,math.ceil(motion.duration_sec/CELL_SECONDS))
        if len(cells)+count > max_cells:
            raise TrajectoryError('search_limit','Swept-time reservation cell budget exhausted.')
        for index in range(count):
            lo,hi = index/count,(index+1)/count
            mid = motion.pose_at((lo+hi)/2)
            if motion.kind == 'line':
                # Fixed heading: elongation is the exact swept rectangle.
                polygon = footprint(mid,length_m+motion.length_m*(hi-lo),width_m,clearance_m)
            else:
                # Every corner stays within this Euclidean radius of its midpoint.
                bound = 2*(motion.radius_m+corner)*math.sin(abs(motion.sweep_rad)*(hi-lo)/4)
                polygon = footprint(mid,length_m,width_m,clearance_m+bound)
            cells.append({'start':elapsed+lo*motion.duration_sec,'end':elapsed+hi*motion.duration_sec,
                          'polygon':polygon,'envelope':polygon_bounds(polygon)})
        elapsed += motion.duration_sec
    return cells


def first_traffic_slot(reservations,cells,requested,owner,separation,*,max_pair_checks=MAX_PAIR_CHECKS):
    """Find earliest start outside all forbidden intervals; estimates never mutate."""
    intervals,checks = [],0
    for cell in cells:
        a = cell['envelope']
        for row in reservations:
            if row['owner'] == owner:
                continue
            checks += 1
            if checks > max_pair_checks:
                raise TrajectoryError('search_limit','Traffic conflict comparison budget exhausted.')
            b = row['envelope']
            if a[0] >= b[2] or b[0] >= a[2] or a[1] >= b[3] or b[1] >= a[3]:
                continue
            if polygons_overlap(cell['polygon'],row['polygon']):
                intervals.append((row['start']-separation-cell['end'],row['end']+separation-cell['start'],row['owner']))
    start = requested
    blockers = set()
    for low,high,other in sorted(intervals):
        if low >= start-EPS:
            break
        if high > start+EPS:
            start = high
            blockers.add(other)
    return start,sorted(blockers)
