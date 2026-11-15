"""Teaching values and effective department scopes checked after saving."""
from amr_department_inputs import department_location_names

AMR_VALUES=dict(quantity=4,length_m=1,width_m=.7,speed_m_per_sec=1.5,motor_power_w=96,
    battery_capacity_kwh=.1,battery_soc_percent=15,battery_charge_rate_kw=2,recharge_threshold_percent=20)
SLOT_VALUES=dict(payload_capacity_kg=100,payload_length_capacity_m=1.2,payload_width_capacity_m=.9,payload_height_capacity_m=1.5)
PAYLOAD_VALUES=dict(length_m=.8,width_m=.6,height_m=1,weight_kg=20)
LIFT_VALUES=dict(speed_floors_per_sec=.5,door_time_sec=4,boarding_time_sec=3,
    capacity_length_m=2,capacity_width_m=2,capacity_height_m=2.5,health_loss_per_journey_percent=0)
TIMES={'06:05','06:35','07:05','07:35'}


def route_nodes(config,flow,lifts,roles=None):
    roles=roles or {};y=7 if flow=='clean' else 13;door_y=6 if flow=='clean' else 14
    names={r['name'] for r in config.get('corridors',{}).get('nodes',[]) if
           abs(r.get('y',-999)-y)<.05 or r.get('has_door') and abs(r.get('y',-999)-door_y)<.05}
    for floor in range(3):names.add(roles.get(f'service_{flow}_{floor}',f'{flow.title()}-F{floor}'))
    names.add(roles.get('clean_store','Clean store') if flow=='clean' else roles.get('dirty_receiving','Dirty receiving'))
    if flow=='dirty':names.add(roles.get('wash','Wash'))
    names.update(f'{lift}-F{floor}' for lift in lifts for floor in range(3))
    return names


def route_edges(config,flow,lifts,roles=None):
    """Directed corridor permissions; lift travel uses Allowed lifts separately."""
    nodes=route_nodes(config,flow,lifts,roles);pairs=set()
    for edge in config.get('corridors',{}).get('edges',[]):
        a,b=edge['from'],edge['to']
        if not {a,b}<=nodes:continue
        pairs.add((a,b))
        if edge.get('bidirectional',True):pairs.add((b,a))
    return pairs


def route_issues(config,policy,roles=None):
    issues=[]
    for flow in ('clean','dirty'):
        lifts=['L1','L2'] if policy=='shared' else ['L1' if flow=='clean' else 'L2']
        row=config.get('route_profiles',{}).get(flow,{})
        if route_nodes(config,flow,lifts,roles)!=set(row.get('allowed_nodes',[])):
            issues.append(f'Layout > Route profiles > {flow} > Select nodes and edges in Layout: select only its lanes, doors, endpoints and permitted lift stops on every floor; Finish selection, Apply Changes, then Save All.')
        if route_edges(config,flow,lifts,roles)!={tuple(pair) for pair in row.get('allowed_edges',[])}:
            issues.append(f'Layout > Route profiles > {flow} > Select nodes and edges in Layout: select its allowed corridor edges on all floors, respecting direction; Finish selection, Apply Changes, then Save All.')
        if set(row.get('allowed_lifts',[]))!=set(lifts):
            issues.append(f'Route profiles > {flow} > Allowed lifts > Pick: choose {", ".join(lifts)}; Apply Changes, then Save All.')
    return issues


def transport_issues(index,config):
    issues=[]
    if index==0:
        row=next((r for r in config.get('amrs',[]) if r.get('id')=='Teaching AMR'),{})
        for key,value in AMR_VALUES.items():
            if row.get(key)!=value:issues.append(f'Teaching AMR: set {key.replace("_", " ")} to {value} in Robots, then Save the AMR type and list.')
        slots=row.get('payload_slots') or [row]
        if len(slots)!=1 or any(slots[0].get(key)!=value for key,value in SLOT_VALUES.items()):
            issues.append('Teaching AMR > Payload slots > Edit selected: set one 100 kg slot, 1.2 × 0.9 × 1.5 m, then Save the slot, AMR type and list.')
    elif index==1:
        for name in ('Clean tote','Dirty cart'):
            row=next((r for r in config.get('payloads',[]) if r.get('name')==name),{})
            if any(row.get(key)!=value for key,value in PAYLOAD_VALUES.items()) or row.get('allowed_carry_orientations')!=['lengthways']:
                issues.append(f'Payloads > {name}: set 0.8 × 0.6 × 1 m, 20 kg, Lengthways only; Save the payload and list.')
    elif index==2:
        for floor in range(3):
            row=next((r for r in config.get('departments',[]) if r.get('id')==f'D{floor}'),{})
            if (row.get('floor')!=floor or not row.get('enabled',True) or row.get('operating_start_time')!='06:00'
                    or row.get('operating_end_time')!='08:00'):
                issues.append(f'Departments > D{floor}: Floor {floor}, Enabled, Operating start 06:00 and Operating end 08:00; Save.')
            for key,location in [('stores',f'Clean-F{floor}'),('linen',f'Dirty-F{floor}')]:
                if location not in department_location_names(row.get('task_generation_locations',{}).get(key,[])):
                    issues.append(f'D{floor} > Task locations & zones > {key.title()} > Select: choose {location}, then Save the department and list.')
    else:
        for name in ('L1','L2'):
            row=next((r for r in config.get('lifts',[]) if r.get('id')==name),{})
            if any(row.get(key)!=value for key,value in LIFT_VALUES.items()) or set(row.get('served_floors',[]))!={0,1,2}:
                issues.append(f'Lifts > {name}: Floors served 0,1,2, speed 1.75 m/s, door 4 s, boarding 3 s, car 2 × 2 × 2.5 m and health loss 0; Save.')
    return issues


def demand_scopes(config,key):
    category=config.get('task_generation',{}).get('categories',{}).get(key,{})
    departments={r.get('id'):r for r in config.get('departments',[]) if r.get('enabled',True)}
    scopes=[];covered=set()
    for group in category.get('department_groups',[]) or []:
        payload=group.get('payload',{})
        for identity in group.get('departments',[]):
            covered.add(identity)
            if identity in departments:scopes.append((departments[identity],{**category,**payload}))
    for identity,payload in (category.get('departments',{}) or {}).items():
        if identity not in covered and identity in departments:scopes.append((departments[identity],{**category,**payload}))
    return scopes


def demand_issues(index,config,roles=None):
    issues=[]
    roles=roles or {};clean_store=roles.get('clean_store','Clean store');dirty_receiving=roles.get('dirty_receiving','Dirty receiving')
    if not config.get('task_generation',{}).get('enabled'):issues.append('Demand generation: enable automatic task generation and Save.')
    for key in ('stores','linen'):
        scopes=demand_scopes(config,key);active=[(d,c) for d,c in scopes if c.get('enabled')]
        if {d.get('floor') for d,c in active}!={0,1,2}:
            issues.append(f'Demand generation > {key.title()}: configure enabled scopes for D0, D1 and D2, then Save.')
        for department,row in active:
            prefix=f'{key.title()} > {department.get("id")}'
            if index==0:
                if row.get('generation_mode')!='scheduled':issues.append(f'{prefix} > Basics: Generation mode scheduled.')
                if row.get('payload')!=('Clean tote' if key=='stores' else 'Dirty cart') or row.get('route_profile')!=('clean' if key=='stores' else 'dirty'):
                    issues.append(f'{prefix} > Locations & routing: choose the matching payload and route profile.')
                if row.get('requires_staff',False):issues.append(f'{prefix} > Schedule & staff: turn Staff handling off.')
                role='dropoff' if key=='stores' else 'pickup'
                if row.get('department_location_role')!=role:issues.append(f'{prefix} > Locations & routing: use department locations as {role}.')
                if key=='stores' and row.get('pickup_location')!=clean_store:issues.append(f'{prefix}: Pickup / source location {clean_store}.')
                if key=='linen' and dirty_receiving not in (row.get('dropoff_locations') or [row.get('dropoff_location')]):issues.append(f'{prefix}: Drop-off destinations > Select > {dirty_receiving}.')
            else:
                if set(row.get('scheduled_times',row.get('schedule_times',[])))!=TIMES:issues.append(f'{prefix} > Schedule & staff > Edit times: add 06:05, 06:35, 07:05 and 07:35.')
                if row.get('target_time')!=600:issues.append(f'{prefix} > Basics: Service target (s) 600.')
                if key=='stores' and (not row.get('return_enabled') or row.get('return_delay_minutes')!=2 or row.get('return_payload')!='Clean tote' or row.get('return_route_profile')!='clean'):
                    issues.append(f'{prefix} > Returns & stock: enable return, payload Clean tote, route profile clean, delay 2 minutes.')
                if key=='linen' and row.get('return_enabled',False):issues.append(f'{prefix} > Returns & stock: turn returns off.')
    return issues
