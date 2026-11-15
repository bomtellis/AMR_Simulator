"""Trim/extend one free corridor node to the interior of a boundary corridor."""
from copy import deepcopy
import math
from visualiser.corridor_editing import subdivide
from visualiser.model_layers import assert_unlocked_changes


def free_endpoints(store, source):
    points = store.all_points()
    edges = {tuple(sorted((e['from'],e['to']))) for e in store.data['corridors']['edges']}
    return [n for n in source if points.get(n,{}).get('kind') == 'corridor_node'
            and sum(n in pair for pair in edges) == 1]


def trim_extend(store, source, endpoint, boundary):
    if store.data['corridors'].get('auto_connect',False):
        raise ValueError('Make automatically generated corridors explicit before trimming or extending.')
    if not source or not boundary or len(source) != 2 or len(boundary) != 2:
        raise ValueError('Choose source and boundary corridors.')
    source, boundary = tuple(sorted(source)),tuple(sorted(boundary))
    points = store.all_points()
    edges = store.data['corridors']['edges']
    pairs = {tuple(sorted((e['from'],e['to']))) for e in edges}
    if source not in pairs or boundary not in pairs or source == boundary:
        raise ValueError('Choose distinct existing source and boundary corridors.')
    if endpoint not in free_endpoints(store,source):
        raise ValueError('Choose a free corridor-node endpoint; junctions, locations and lift stops cannot be moved by this tool.')
    fixed = next(n for n in source if n != endpoint)
    a,b = points[fixed],points[endpoint]
    c,d = (points[n] for n in boundary)
    if len({int(p['floor']) for p in (a,b,c,d)}) != 1:
        raise ValueError('Source and boundary must be on the same floor.')
    ax,ay,bx,by,cx,cy,dx,dy = (float(p[k]) for p in (a,b,c,d) for k in ('x','y'))
    if not all(math.isfinite(v) for v in (ax,ay,bx,by,cx,cy,dx,dy)):
        raise ValueError('Corridor coordinates must be finite.')
    rx,ry,sx,sy = bx-ax,by-ay,dx-cx,dy-cy
    length = math.hypot(rx,ry)
    cross = rx*sy-ry*sx
    if length < 1e-6 or abs(cross) <= 1e-12*max(1,length*math.hypot(sx,sy)):
        raise ValueError('Parallel or zero-length corridors have no unique intersection.')
    t = ((cx-ax)*sy-(cy-ay)*sx)/cross
    u = ((cx-ax)*ry-(cy-ay)*rx)/cross
    if t <= 0 or t*length < 1e-6:
        raise ValueError('The boundary must intersect ahead of the retained endpoint.')
    if not 0 < u < 1:
        raise ValueError('Choose an intersection inside the boundary corridor; endpoint merging is not supported here.')
    x,y = ax+t*rx,ay+t*ry
    if not all(math.isfinite(v) for v in (x,y,t*length)):
        raise ValueError('The intersection must have finite coordinates and length.')
    if math.hypot(x-bx,y-by) < 1e-6:
        raise ValueError('The endpoint is already at this boundary.')
    if any(n != endpoint and int(p['floor']) == int(a['floor']) and
           math.hypot(float(p['x'])-x,float(p['y'])-y) < 1e-6 for n,p in points.items()):
        raise ValueError('An existing point occupies the intersection; resolve that junction explicitly.')
    staged = deepcopy(store)
    staged.set_point_position(endpoint,x,y,exact=True)
    for edge in staged.data['corridors']['edges']:
        if tuple(sorted((edge['from'],edge['to']))) == source and edge.get('distance_m') is not None:
            distance = float(edge['distance_m'])
            if not math.isfinite(distance) or distance < 0 or not math.isfinite(distance*t):
                raise ValueError('Source distance overrides must be finite and non-negative.')
            edge['distance_m'] = distance*t
    moved = staged.all_points()
    staged.data, chains = subdivide(staged.data,moved,{boundary:[u]},
                                   _join_cuts=True,_existing_cut_node=moved[endpoint])
    if chains[boundary][1] != endpoint:
        raise ValueError('Intersection precision cannot produce one shared junction.')
    assert_unlocked_changes(store.data,staged.data)
    return staged,dict(operation='Extend' if t > 1 else 'Trim',endpoint=endpoint,x=x,y=y,
                       old_length=length,new_length=t*length,boundary_chain=chains[boundary])
