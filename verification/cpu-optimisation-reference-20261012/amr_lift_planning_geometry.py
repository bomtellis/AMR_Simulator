"""Reviewable DXF geometry and conservative aligned shaft/connector proposals."""
from copy import deepcopy
import heapq
import itertools
import math
from pathlib import Path

from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QPainterPath,QPainterPathStroker
from amr_run_evidence import file_hash

ROLES=('ignore','boundary','wall','opening','circulation','excluded','shaft')


def default_role(layer):
    name=layer.upper()
    for token,role in [('BOUNDARY','boundary'),('WALL','wall'),('DOOR','opening'),
        ('CIRCULATION','circulation'),('FACILIT','excluded'),('EXCLUD','excluded'),('SHAFT','shaft')]:
        if token in name:return role
    return 'ignore'


def transform(point,registration=None,inverse=False):
    r=registration or {};x,y=point
    angle=math.radians(r.get('rotation_deg',0));dx=r.get('dx',0);dy=r.get('dy',0)
    if inverse:x-=dx;y-=dy;angle=-angle
    a,b=math.cos(angle),math.sin(angle);p=(x*a-y*b,x*b+y*a)
    return p if inverse else (p[0]+dx,p[1]+dy)


def area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2


def _planning_paths(entity,tolerance):
    """Flatten analytic DXF curves directly, without cubic circle approximation."""
    from ezdxf.path import make_path
    from ezdxf.explode import virtual_boundary_path_entities
    from ezdxf.math import Vec3
    kind=entity.dxftype()
    def join(parts,start):
        result=[start]
        for part in parts:
            points=_planning_paths(part,tolerance)[0]
            if result[-1].distance(points[-1])<result[-1].distance(points[0]):points.reverse()
            if result[-1].distance(points[0])>tolerance:raise ValueError('Curve boundary has a gap; repair its edge ordering.')
            result.extend(points[1:])
        return result
    if kind in ('CIRCLE','ARC','ELLIPSE','SPLINE'):
        return [list(entity.flattening(tolerance))]
    if kind=='LINE':return [[entity.dxf.start,entity.dxf.end]]
    if kind in ('LWPOLYLINE','POLYLINE'):
        vertices=list(entity.vertices_in_wcs() if kind=='LWPOLYLINE' else entity.points_in_wcs())
        if not vertices:return [[]]
        return [join(list(entity.virtual_entities()),vertices[0])]
    if kind in ('HATCH','MPOLYGON'):
        from ezdxf.entities import LWPolyline
        from ezdxf.entities.boundary_paths import PolylinePath
        result=[]
        for boundary in entity.paths:
            if isinstance(boundary,PolylinePath):
                polyline=LWPolyline.new(dxfattribs=dict(extrusion=entity.dxf.extrusion,elevation=entity.dxf.elevation.z))
                polyline.set_points(boundary.vertices,format='xyb');polyline.closed=boundary.is_closed
                result.extend(_planning_paths(polyline,tolerance));continue
            virtual=entity.copy();virtual.paths.paths=[boundary]
            parts=virtual_boundary_path_entities(virtual)[0]
            if not parts:continue
            start=boundary.edges[0].real_start_point
            start=entity.ocs().to_wcs(Vec3(start.x,start.y,entity.dxf.elevation.z))
            result.append(join(parts,start))
        return result
    return [list(make_path(entity).flattening(tolerance))]


def extract_floor(path,floor,roles=None,registration=None,unit_scale=None):
    import ezdxf
    from visualiser.dxf_scene import DXFScene
    doc=ezdxf.readfile(path);units=int(doc.header.get('$INSUNITS',0))
    scale=unit_scale if unit_scale is not None else DXFScene.DXF_UNIT_TO_METRES.get(units)
    if not scale or not math.isfinite(scale) or scale<=0:raise ValueError('Confirm drawing units; unitless/unsupported units are ambiguous.')
    rows=[];warnings=[];layers=set();roles=roles or {}
    def visit(entity,inherited='0',depth=0):
        if depth>16:raise ValueError('Drawing blocks exceed the planning nesting limit.')
        layer=entity.dxf.layer if entity.dxf.layer!='0' else inherited;layers.add(layer)
        role=roles.get(layer,default_role(layer))
        if role not in ROLES:raise ValueError('Invalid drawing layer role.')
        if entity.dxftype()=='INSERT':
            for child in entity.virtual_entities():visit(child,layer,depth+1)
            return
        if role=='ignore':return
        try:
            paths=_planning_paths(entity,.005/scale)
            group=len(rows) if entity.dxftype() in ('HATCH','MPOLYGON') else None
            for curve in paths:
                points=[transform((p.x*scale,p.y*scale),registration) for p in curve]
                if len(points)<2:continue
                closed=math.dist(points[0],points[-1])<=.01
                if closed:points=points[:-1]
                rows.append(dict(layer=layer,role=role,points=[list(p) for p in points],closed=closed,hatch_group=group))
        except (TypeError,AttributeError,NotImplementedError,ValueError) as exc:
            warnings.append(f'{layer}: unsupported {entity.dxftype()} — {exc}')
    for entity in doc.modelspace():visit(entity)
    # Stitch straight boundary segments without inventing connections across gaps.
    open_rows=[r for r in rows if r['role']=='boundary' and not r['closed']]
    remaining=list(open_rows)
    while remaining:
        first=remaining.pop(0);points=list(first['points'])
        while True:
            match=next(((i,reverse) for i,r in enumerate(remaining) for reverse in (False,True)
                if math.dist(points[-1],r['points'][-1 if reverse else 0])<=.01),None)
            if match is None:break
            i,reverse=match;r=remaining.pop(i);other=list(reversed(r['points'])) if reverse else r['points'];points+=other[1:]
        if math.dist(points[0],points[-1])<=.01:
            rows.append(dict(layer=first['layer'],role='boundary',points=points[:-1],closed=True))
    boundaries=[r for r in rows if r['role']=='boundary' and r['closed'] and area(r['points'])>.01]
    if len(boundaries)!=1:raise ValueError(f'Confirm one closed building boundary on floor {floor}; found {len(boundaries)}.')
    if not any(r['role']=='circulation' and r['closed'] for r in rows):
        raise ValueError(f'Confirm closed circulation areas on floor {floor}; layer names alone do not establish access.')
    if warnings:raise ValueError('Repair or ignore unsupported geometry before confirming: '+'; '.join(warnings[:5]))
    return dict(floor=int(floor),filepath=str(Path(path).resolve()),sha256=file_hash(path),unit_scale=scale,
        registration=registration or dict(dx=0,dy=0,rotation_deg=0),layers=sorted(layers),entities=rows,
        boundary_area_m2=area(boundaries[0]['points']),roles={layer:roles.get(layer,default_role(layer)) for layer in sorted(layers)})


def _shape(row,stroke=.2):
    p=QPainterPath();points=row['points'];p.moveTo(*points[0])
    for point in points[1:]:p.lineTo(*point)
    if row['closed']:p.closeSubpath()
    else:
        s=QPainterPathStroker();s.setWidth(stroke);p=s.createStroke(p)
    return p


def masks(geometry,retain_shafts=False,exclusions=()):
    roles={k:QPainterPath() for k in ROLES}
    hatches={}
    for row in geometry['entities']:
        if row.get('hatch_group') is not None:
            key=(row['role'],row['hatch_group']);p=hatches.setdefault(key,QPainterPath());p.addPath(_shape(row));p.setFillRule(Qt.OddEvenFill)
        else:roles[row['role']]=roles[row['role']].united(_shape(row))
    for (role,_),p in hatches.items():roles[role]=roles[role].united(p)
    blocked=roles['wall'].subtracted(roles['opening']).united(roles['excluded'])
    if retain_shafts:blocked=blocked.united(roles['shaft'])
    for bounds in exclusions:
        p=QPainterPath();p.addRect(QRectF(bounds[0],bounds[1],bounds[2]-bounds[0],bounds[3]-bounds[1]));blocked=blocked.united(p)
    return roles['boundary'],blocked,roles['circulation'].intersected(roles['boundary']).subtracted(blocked)


def rect_path(x,y,length,width,clearance=0):
    p=QPainterPath();p.addRect(QRectF(x-length/2-clearance,y-width/2-clearance,length+2*clearance,width+2*clearance));return p


def connector_path(start,end,free,clearance=.4,step=.25):
    """Eight-connected A*; reject diagonal corner cutting and swept-width collisions."""
    if math.dist(start,end)<.01:return [list(start),list(end)]
    def valid(point):return free.contains(rect_path(*point,clearance*2,clearance*2))
    if not valid(start) or not valid(end):return None
    def segment_ok(a,b):
        count=max(1,math.ceil(math.dist(a,b)/(step/2)))
        return all(valid((a[0]+(b[0]-a[0])*t/count,a[1]+(b[1]-a[1])*t/count)) for t in range(count+1))
    if segment_ok(start,end):return [list(start),list(end)]
    origin=(round(start[0]/step),round(start[1]/step));goal=(round(end[0]/step),round(end[1]/step))
    def point(k):return (k[0]*step,k[1]*step)
    if not segment_ok(start,point(origin)) or not segment_ok(point(goal),end):return None
    queue=[(math.dist(point(origin),end),0,origin)];cost={origin:0};parent={};visited=0
    while queue and visited<50000:
        _,g,node=heapq.heappop(queue)
        if g!=cost[node]:continue
        visited+=1
        if node==goal:
            chain=[end,point(node)]
            while node in parent:node=parent[node];chain.append(point(node))
            chain.append(start);chain.reverse()
            # Simplify only along verified free segments.
            result=[chain[0]];i=0
            while i<len(chain)-1:
                j=len(chain)-1
                while j>i+1 and not segment_ok(chain[i],chain[j]):j-=1
                result.append(chain[j]);i=j
            return [list(p) for p in result]
        for dx,dy in itertools.product((-1,0,1),repeat=2):
            if dx==dy==0:continue
            nxt=(node[0]+dx,node[1]+dy)
            if not segment_ok(point(node),point(nxt)):continue
            ng=g+math.hypot(dx,dy)*step
            if ng<cost.get(nxt,float('inf')):
                cost[nxt]=ng;parent[nxt]=node;heapq.heappush(queue,(ng+math.dist(point(nxt),end),ng,nxt))
    return None


def generate_sites(config,geometries,options,requests,progress=None):
    length=float(options.get('shaft_length_m',2));width=float(options.get('shaft_width_m',2))
    landing=float(options.get('landing_depth_m',1));gap=float(options.get('clearance_m',.1))
    if min(length,width,landing)<=0 or gap<0:raise ValueError('Provide positive shaft/landing dimensions and nonnegative clearance.')
    if len(config.get('lifts',[]))!=2:raise ValueError('This proposal study evaluates two existing lifts; create other counts as separate designs.')
    floors=set(config['lifts'][0]['served_floors'])|set(config['lifts'][1]['served_floors'])
    by_floor={g['floor']:g for g in geometries}
    if not floors<=set(by_floor):raise ValueError('Interpret a drawing for every served floor.')
    points={r['name']:r for r in config.get('locations',[])+config.get('corridors',{}).get('nodes',[])}
    attachments={};weights={}
    for r in requests:
        for key in ('pickup','dropoff'):
            pair=(r[key],r.get('route_profile',''));weights[pair]=weights.get(pair,0)+1
    for f in floors:
        attachments[f]=[r for r in points.values() if r['floor']==f]
    first=by_floor[min(floors)];boundary,_,_=masks(first)
    bounds=boundary.boundingRect();candidates=[]
    mask={f:masks(by_floor[f],False,options.get('excluded',{}).get(str(f),[])) for f in floors}
    # Shortlist using directed, profile-permitted graph distances. Distances to
    # off-aisle service points include their actual door/corridor edges.
    distances={}
    for name,flow in weights:
        profile=config.get('route_profiles',{}).get(flow,{})
        allowed=set(profile.get('allowed_nodes',[]));allowed_edges={tuple(e) for e in profile.get('allowed_edges',[])}
        graph={}
        for edge in config['corridors']['edges']:
            a,b=edge['from'],edge['to']
            if a not in points or b not in points or (allowed and (a not in allowed or b not in allowed)):continue
            for start,end in [(a,b)]+([(b,a)] if edge.get('bidirectional',True) else []):
                if allowed_edges and (start,end) not in allowed_edges:continue
                length_m=edge.get('distance_m')
                if length_m is None:length_m=math.dist((points[a]['x'],points[a]['y']),(points[b]['x'],points[b]['y']))
                graph.setdefault(end,[]).append((start,float(length_m)))
        d={name:0};queue=[(0,name)]
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=d[node]:continue
            for other,length_m in graph.get(node,[]):
                new=cost+length_m
                if new<d.get(other,float('inf')):d[other]=new;heapq.heappush(queue,(new,other))
        distances[name,flow]=d
    def graph_score(x,y):
        score=0;paths={}
        for (name,flow),weight in weights.items():
            if name not in points or points[name]['floor'] not in floors:continue
            f=points[name]['floor'];best=float('inf')
            for node,cost in distances[name,flow].items():
                p=points.get(node)
                if not p or p['floor']!=f:continue
                key=(f,node)
                if key not in paths:
                    path=connector_path((x,y),transform((p['x'],p['y']),by_floor[f]['registration']),mask[f][2])
                    paths[key]=sum(math.dist(a,b) for a,b in zip(path,path[1:])) if path else float('inf')
                best=min(best,cost+paths[key])
            if not math.isfinite(best):return float('inf')
            score+=weight*best
        return score
    xs=range(math.ceil(bounds.left()),math.floor(bounds.right())+1)
    for column,x in enumerate(xs):
        if progress:progress(column,len(xs))
        for y in range(math.ceil(bounds.top()),math.floor(bounds.bottom())+1):
            footprint=rect_path(x,y,length,width,gap); landing_shape=rect_path(x,y,length,width+2*landing,gap)
            if any(not mask[f][0].contains(landing_shape) or mask[f][1].intersects(landing_shape)
                   or not mask[f][2].contains(landing_shape) for f in floors):continue
            # Do not place shafts over existing non-lift circulation edges.
            obstructs=False
            for e in config.get('corridors',{}).get('edges',[]):
                a,b=points.get(e['from']),points.get(e['to'])
                if not a or not b or a['floor'] not in floors:continue
                f=a['floor'];reg=by_floor[f]['registration'];p=QPainterPath()
                p.moveTo(*transform((a['x'],a['y']),reg));p.lineTo(*transform((b['x'],b['y']),reg))
                if footprint.intersects(p):obstructs=True;break
            if obstructs:continue
            score=graph_score(x,y)
            if math.isfinite(score):candidates.append(dict(x=x,y=y,score=score))
    candidates.sort(key=lambda r:(r['score'],r['x'],r['y']))
    # Diversify the eight-site shortlist so disjoint shaft pairs exist.
    shortlist=[]
    for c in candidates:
        if all(math.dist((c['x'],c['y']),(s['x'],s['y']))>=max(length,width)+gap*2 for s in shortlist):shortlist.append(c)
        if len(shortlist)==8:break
    if len(shortlist)<2:raise ValueError('No two non-overlapping aligned sites. Review units, registration, exclusions and landing space.')
    for lift in config['lifts']:
        if not options.get('movable',{}).get(lift['id'],True):
            f=lift['served_floors'][0];p=lift['floor_locations'][str(f)]
            x,y=transform((p['x'],p['y']),by_floor[f]['registration'])
            if any(not mask[f][0].contains(rect_path(x,y,length,width,gap)) or mask[f][1].intersects(rect_path(x,y,length,width,gap)) for f in lift['served_floors']):
                raise ValueError('A retained shaft conflicts with confirmed boundaries/exclusions.')
            retained=dict(x=x,y=y,score=graph_score(x,y))
            if not any(math.dist((x,y),(s['x'],s['y']))<.01 for s in shortlist):shortlist.append(retained)
    for n,site in enumerate(shortlist):site['id']=f'S{n+1}'
    return shortlist


def build_proposals(config,geometries,sites,options,progress=None):
    geometries={g['floor']:g for g in geometries};proposals={};previews={}
    lifts=config['lifts'];movable=options.get('movable',{r['id']:True for r in lifts})
    pairs=sorted(itertools.permutations(sites,2),key=lambda pair:sum(r['score'] for r in pair))
    for number,pair in enumerate(pairs):
        if progress:progress(number,len(pairs))
        c=deepcopy(config);overlay=[];valid=True
        footprints=[rect_path(s['x'],s['y'],options.get('shaft_length_m',2),options.get('shaft_width_m',2),options.get('clearance_m',.1)) for s in pair]
        if footprints[0].intersects(footprints[1]):continue
        for index,(lift,site) in enumerate(zip(c['lifts'],pair)):
            if not movable.get(lift['id'],True):
                # A retained shaft must remain at its original registered centre.
                f=lift['served_floors'][0];pos=lift['floor_locations'][str(f)]
                if math.dist(transform((pos['x'],pos['y']),geometries[f]['registration']),(site['x'],site['y']))>.01:valid=False;break
            for floor in lift['served_floors']:
                g=geometries[floor];reg=g['registration'];stop=f"{lift['id']}-F{floor}"
                adjacent=[e for e in c['corridors']['edges'] if stop in (e['from'],e['to'])]
                c['corridors']['edges']=[e for e in c['corridors']['edges'] if stop not in (e['from'],e['to'])]
                lift['floor_locations'][str(floor)]=dict(zip(('x','y'),transform((site['x'],site['y']),reg,inverse=True)))
                _,_,free=masks(g,False,options.get('excluded',{}).get(str(floor),[]))
                free=free.subtracted(footprints[1-index])
                points={r['name']:r for r in c['locations']+c['corridors']['nodes']}
                for old in adjacent:
                    neighbor=old['to'] if old['from']==stop else old['from'];row=points.get(neighbor)
                    if not row:valid=False;break
                    # Attach to the closest permitted point in the neighbor's connected
                    # non-lift graph component; never silently broaden a profile.
                    component={neighbor};changed=True
                    while changed:
                        changed=False
                        for edge in c['corridors']['edges']:
                            if edge['from'] in component and edge['to'] in points and edge['to'] not in component:
                                component.add(edge['to']);changed=True
                            if edge.get('bidirectional',True) and edge['to'] in component and edge['from'] in points and edge['from'] not in component:
                                component.add(edge['from']);changed=True
                    profiles=[p for p in c.get('route_profiles',{}).values() if
                        (stop in p.get('allowed_nodes',[]) and neighbor in p.get('allowed_nodes',[])) or
                        [stop,neighbor] in p.get('allowed_edges',[]) or [neighbor,stop] in p.get('allowed_edges',[])]
                    eligible=[points[n] for n in component if n in points and points[n]['floor']==floor and
                        all(not p.get('allowed_nodes') or n in p['allowed_nodes'] for p in profiles)]
                    eligible.sort(key=lambda r:(math.dist((site['x'],site['y']),transform((r['x'],r['y']),reg)),r['name']))
                    path=None
                    for target in eligible:
                        path=connector_path((site['x'],site['y']),transform((target['x'],target['y']),reg),free)
                        if path:neighbor=target['name'];break
                    if path is None:valid=False;break
                    chain=[stop]
                    for j,p in enumerate(path[1:-1]):
                        name=f"PLAN-{lift['id']}-F{floor}-{len(overlay)}-{j}"
                        xy=transform(p,reg,inverse=True);c['corridors']['nodes'].append(dict(name=name,floor=floor,x=xy[0],y=xy[1]))
                        chain.append(name)
                        for profile in profiles:
                            if profile.get('allowed_nodes'):profile['allowed_nodes'].append(name)
                    chain.append(neighbor)
                    if not old.get('bidirectional',True) and old['from']!=stop:
                        chain.reverse();path.reverse()
                    for profile in profiles:
                        if profile.get('allowed_edges'):
                            profile['allowed_edges']=[e for e in profile['allowed_edges'] if e not in ([stop,row['name']],[row['name'],stop])]
                    for a,b,p,q in zip(chain,chain[1:],path,path[1:]):
                        edge=deepcopy(old);edge.update({'from':a,'to':b,'distance_m':math.dist(p,q)})
                        c['corridors']['edges'].append(edge)
                        for profile in profiles:
                            if profile.get('allowed_edges'):
                                profile['allowed_edges'] += [[a,b],[b,a]] if old.get('bidirectional',True) else [[a,b]]
                    overlay.append(dict(floor=floor,lift=lift['id'],path=path))
                if not valid:break
            if not valid:break
        if not valid:continue
        from visualiser.project_checks import check_project
        if any(r.severity=='error' for r in check_project(c).findings):continue
        identity=f'proposal-{len(proposals)+1}';proposals[identity]=c;previews[identity]=overlay
        if len(proposals)==5:break
    if not proposals:raise ValueError('No proposal has permitted connectors on every floor. Review route permissions and circulation.')
    return proposals,previews
