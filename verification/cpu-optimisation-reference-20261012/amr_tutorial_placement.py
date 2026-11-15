"""Placement hints and checks shared by every spatial tutorial chapter."""
import math
from amr_tutorial_circulation import CIRCULATION_STEPS,TOLERANCE,inspect_step

FACILITIES=(('dispatch','Dispatch',(3,10)),('clean_store','Clean store',(3,7)),
            ('dirty_receiving','Dirty receiving',(3,13)),('wash','Wash',(5,13)))
CHARGING_BAYS=tuple(dict(name=f'Charger {i+1}',space_type='amr',has_charger=True,
    length_m=1.4,width_m=1.1,height_m=2,dx=-1 if i%2==0 else 1,dy=-.8 if i<2 else .8)
    for i in range(4))

def facility_issues(config,roles):
    rows=config.get('locations',[]);nodes=config.get('corridors',{}).get('nodes',[]);issues=[]
    edges=config.get('corridors',{}).get('edges',[])
    graph={r['name']:set() for r in rows+nodes if r.get('floor')==0}
    for edge in edges:
        a,b=edge.get('from'),edge.get('to')
        if a in graph and b in graph:
            graph[a].add(b)
            if edge.get('bidirectional',True):graph[b].add(a)
    for role,name,point in FACILITIES:
        name=roles.get(role,name);row=next((r for r in rows if r['name']==name),None)
        issue=dict(floor=0,point=point,name=name,role=role)
        if row is None:
            nearby=next((r for r in rows if r.get('floor')==0 and math.hypot(r.get('x',0)-point[0],r.get('y',0)-point[1])<=TOLERANCE),None)
            text=(f'Rename {nearby["name"]} to {name}, or bind it to {role} in More > Bind an object.' if nearby else
                  f'Choose Location; place {name} at X {point[0]}, Y {point[1]} m on floor 0.')
            issues.append(dict(issue,missing=nearby is None,message=text));continue
        if row.get('floor')!=0 or math.hypot(row.get('x',0)-point[0],row.get('y',0)-point[1])>TOLERANCE:
            issues.append(dict(issue,property='x',message=f'Move {name} to floor 0, X {point[0]}, Y {point[1]} m using Properties or Move selected by.'));continue
        seen=set();queue=[name]
        while queue:
            n=queue.pop()
            if n in seen:continue
            seen.add(n);queue.extend(graph.get(n,set())-seen)
        if not any(r['name'] in seen for r in nodes):
            issues.append(dict(issue,connection=True,message=f'{name} has no circulation connection. Redo the removed access link, or recreate it at the marker to join the corridor.'))
    return issues

def placement_step(chapter,index,config,roles):
    """Return a spatial instruction, including live names after rebinding."""
    if chapter==2:return CIRCULATION_STEPS[index]
    if chapter==3 and index==0:
        return dict(floor=0,kind='location',tool='Location',points=[p for _,_,p in FACILITIES],
            names=[roles.get(role,name) for role,name,_ in FACILITIES],title='Place and connect the four facilities')
    if chapter==3 and index in (1,2,3):
        role={1:'dispatch',2:'dirty_receiving',3:'wash'}[index]
        _,name,point=next(r for r in FACILITIES if r[0]==role)
        if index==1:
            return dict(floor=0,kind='bay',tool='Properties',points=[(point[0]+dx,point[1]+dy) for dx,dy in ((-1,-.8),(1,-.8),(-1,.8),(1,.8))],
                names=[f'Charger {n}' for n in range(1,5)],title='Four charging bays at Dispatch')
        return dict(floor=0,kind='inspect',tool='Select',points=[point],names=[roles.get(role,name)],title='Configure '+name)
    if chapter==4 and index==2:
        floors={r.get('floor') for r in config.get('departments',[])}
        floor=next((f for f in range(3) if f not in floors),0)
        return dict(floor=floor,kind='department',tool='Department',points=[(6,10)],names=[f'D{floor}'],title=f'Floor {floor} service department')
    if chapter==4 and index==3:
        return dict(floor=0,kind='lift',tool='Lift',points=[(34,10),(38,10)],
            names=[roles.get('lift1','L1'),roles.get('lift2','L2')],title='Two aligned lifts on floors 0–2')
    return None

def placement_issues(chapter,index,config,roles):
    if chapter==2:return inspect_step(config,index,roles)
    if chapter==3 and index==0:return facility_issues(config,roles)
    step=placement_step(chapter,index,config,roles)
    if step and step['kind']=='lift':
        issues=[]
        for name,point in zip(step['names'],step['points']):
            row=next((r for r in config.get('lifts',[]) if r['id']==name),None)
            for floor in range(3):
                position=(row or {}).get('floor_locations',{}).get(str(floor))
                if not position or math.hypot(position.get('x',0)-point[0],position.get('y',0)-point[1])>TOLERANCE:
                    issues.append(dict(floor=floor,point=point,name=name,message=f'Set {name} stop on floor {floor} to X {point[0]}, Y {point[1]} m, then Save.'))
        return issues
    if step and step['kind']=='department' and step['floor'] not in {r.get('floor') for r in config.get('departments',[])}:
        return [dict(floor=step['floor'],point=step['points'][0],name=step['names'][0],message=f'Add {step["names"][0]} for floor {step["floor"]}. Use the marked point if placing its marker in Layout.')]
    return []
