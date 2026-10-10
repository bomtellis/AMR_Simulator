"""Exact teaching routes and read-only checks, independent of object names."""
import math

XS=(3,8,10,12,18,24,30,34,38)
TOLERANCE=.05


def steps():
    result=[]
    for floor in range(3):
        x=8+2*floor
        for flow,y in (('clean',7),('dirty',13)):
            result.append(dict(floor=floor,kind='route',tool='Corridor',points=[(a,y) for a in XS],
                title=f'Floor {floor}: {flow} corridor',
                instruction=f'Choose floor {floor} and Corridor. Follow the numbered {flow} lane markers at y={y} m from left to right. Keep 2.4 m width and bidirectional travel. Escape finishes the route.'))
        result.append(dict(floor=floor,kind='route',tool='Corridor',points=[(3,7),(3,10),(3,13)],
            title=f'Floor {floor}: create the shared transition',
            instruction=f'On floor {floor}, choose Transition and click empty space at (3,10) to create the shared node. Then choose Corridor: click the clean lane at (3,7), the new node at (3,10), and the dirty lane at (3,13). Keep 2.4 m width and bidirectional travel. Escape finishes.'))
        result.append(dict(floor=floor,kind='door',tool='Door',points=[(x,6),(x,14)],
            title=f'Floor {floor}: clean and dirty doors',instruction=f'Choose Door. Place doors at ({x},6) and ({x},14). Select each, explicitly open Properties, set Clear door opening to 1.2 m, and Apply changes.'))
        result.append(dict(floor=floor,kind='location',tool='Location',points=[(x,4),(x,16)],
            names=[f'Clean-F{floor}',f'Dirty-F{floor}'],title=f'Floor {floor}: service locations',
            instruction=f'Choose Location. Place Clean-F{floor} at ({x},4) and Dirty-F{floor} at ({x},16); enter the shown name at each marker.'))
        for flow,ys in (('clean',(7,6,4)),('dirty',(13,14,16))):
            result.append(dict(floor=floor,kind='route',tool='Corridor',points=[(x,y) for y in ys],
                title=f'Floor {floor}: {flow} service connection',instruction=f'Choose Corridor. Connect the {flow} lane through its door to its service location, following the three markers. Escape finishes.'))
    return tuple(result)


CIRCULATION_STEPS=steps()


def inspect_step(config,index,bindings=None):
    """Return all missing work plus its exact floor/point for the UI overlay."""
    step=CIRCULATION_STEPS[index];floor=step['floor'];issues=[];bindings=bindings or {}
    nodes=config.get('corridors',{}).get('nodes',[]);locations=config.get('locations',[])
    points={r['name']:r for r in nodes+locations}
    def at(rows,point):
        return [r for r in rows if r.get('floor')==floor and
                math.hypot(float(r.get('x',0))-point[0],float(r.get('y',0))-point[1])<=TOLERANCE]
    def issue(message,point,**extra):issues.append(dict(message=message,floor=floor,point=point,**extra))
    matched=[]
    for n,point in enumerate(step['points']):
        rows=at(locations if step['kind']=='location' else nodes+locations,point)
        if step['kind']=='door':rows=at(nodes,point)
        if not rows:
            if step['kind']=='route' and point==(3,10):
                issue(f'Floor {floor}: create the shared transition. Choose Transition and click empty space at (3,10). Then choose Corridor and connect (3,7), (3,10), (3,13); keep 2.4 m width and both directions. Escape finishes.',point)
            else:issue(f"Floor {floor}: add {step['kind'] if step['kind']!='route' else 'route point'} at ({point[0]},{point[1]}) m.",point)
            matched.append(None);continue
        if len(rows)>1:
            # Later facilities intentionally coincide with junctions. Prefer the
            # graph node for route starts, and the location for service ends.
            preferred=[r for r in rows if r in nodes]
            rows=preferred if preferred and step['kind']=='route' else rows
        row=rows[0];matched.append(row)
        if step['kind']=='door':
            if not row.get('has_door'):issue(f"Floor {floor}: mark the node at ({point[0]},{point[1]}) as a Door.",point)
            elif abs(float(row.get('door_clear_width_m',0) or 0)-1.2)>.001:
                issue(f"Floor {floor}: select this door, open Properties, set Clear door opening to 1.2 m and Apply changes.",point,property='door_clear_width_m',name=row['name'])
        if step['kind']=='location':
            role=f"service_{'clean' if n==0 else 'dirty'}_{floor}"
            expected=bindings.get(role,step['names'][n])
            if row['name']!=expected:issue(f"Floor {floor}: choose Select, double-click this location and set Name to {expected}, then Save. Alternatively, rebind its tutorial role after renaming.",point,
                                         name=row['name'],expected_name=expected,property='name')
    if step['kind']=='route':
        for start,finish,a,b in zip(step['points'],step['points'][1:],matched,matched[1:]):
            if a is None or b is None:continue
            # Allow genuine subdivisions, while forbidding shortcuts, wrong
            # directions, wrong widths and silently overridden teaching lengths.
            dx,dy=finish[0]-start[0],finish[1]-start[1];length=math.hypot(dx,dy)
            def on_segment(row):
                rx,ry=float(row['x'])-start[0],float(row['y'])-start[1]
                t=(rx*dx+ry*dy)/(length*length)
                return row.get('floor')==floor and -.0001<=t<=1.0001 and abs(rx*dy-ry*dx)/length<=TOLERANCE
            local={name:r for name,r in points.items() if on_segment(r)}
            graph={name:set() for name in local}
            bad=[]
            for edge_index,edge in enumerate(config.get('corridors',{}).get('edges',[])):
                u,v=edge.get('from'),edge.get('to')
                if u not in local or v not in local:continue
                measured=math.hypot(local[u]['x']-local[v]['x'],local[u]['y']-local[v]['y'])
                prop=None
                if abs(float(edge.get('width_m',config.get('building',{}).get('default_corridor_width_m',2.4)) or 0)-2.4)>.001:prop='width_m'
                elif edge.get('distance_m') is not None and abs(float(edge['distance_m'])-measured)>.05:prop='distance_m'
                elif not edge.get('bidirectional',True):prop='bidirectional'
                if prop:
                    bad.append((edge_index,prop,u,v))
                    if prop!='bidirectional':continue
                graph[u].add(v)
                if edge.get('bidirectional',True):graph[v].add(u)
            def reaches(u,v):
                seen=set();queue=[u]
                while queue:
                    name=queue.pop()
                    if name==v:return True
                    if name in seen:continue
                    seen.add(name);queue.extend(graph.get(name,set())-seen)
                return False
            if not reaches(a['name'],b['name']) or not reaches(b['name'],a['name']):
                if bad:
                    edge_index,prop,u,v=bad[0]
                    message={'width_m':'Set Width to 2.4 m','distance_m':'Use Default for Distance to restore geometric length',
                             'bidirectional':'Set Bidirectional to Yes for both directions'}[prop]
                    middle=((local[u]['x']+local[v]['x'])/2,(local[u]['y']+local[v]['y'])/2)
                    issue(f'Floor {floor}: select the highlighted corridor, open Properties. {message}, then Apply changes.',middle,
                          property=prop,edge_index=edge_index,path_start=(local[u]['x'],local[u]['y']),path_finish=(local[v]['x'],local[v]['y']))
                else:issue(f'Floor {floor}: connect ({start[0]},{start[1]}) to ({finish[0]},{finish[1]}) along the shown segment; use 2.4 m width, both directions and geometric length.',finish,start=start)
    return issues


def inspect_all(config,bindings=None):
    issues=[r for n in range(len(CIRCULATION_STEPS)) for r in inspect_step(config,n,bindings)]
    points={r['name']:r for r in config.get('locations',[])+config.get('corridors',{}).get('nodes',[])}
    for edge in config.get('corridors',{}).get('edges',[]):
        a,b=points.get(edge.get('from')),points.get(edge.get('to'))
        if a and b and a['floor']!=b['floor']:
            issues.append(dict(message=f"Remove the ordinary cross-floor edge {a['name']} → {b['name']}; use lifts.",floor=a['floor'],point=(a['x'],a['y'])))
    return issues
