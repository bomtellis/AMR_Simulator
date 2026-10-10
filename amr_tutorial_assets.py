"""Reproducible teaching building; no operational project or release is edited."""
from copy import deepcopy
from pathlib import Path
import json

from visualiser.models import JsonStore
from amr_tutorial_placement import CHARGING_BAYS

LAYERS = ('BOUNDARY', 'WALLS', 'DOORS', 'CIRCULATION', 'CLEAN', 'DIRTY',
          'FACILITIES', 'SHAFTS', 'ANNOTATIONS')


def building_config(drawings, policy='dedicated'):
    c = JsonStore().data
    c['simulation'].update(mode='simple', motion_model='legacy',
        start_datetime='2026-01-05T06:00:00', end_datetime='2026-01-05T08:00:00',
        precompute_static_routes=False, enable_opportunity_charging=False)
    c['building'].update(floor_count=3, floor_height_m=3.5, charge_locations=['Dispatch'],
        enable_idle_return=False, load_unload_time_sec=5, edge_slowdown_per_amr=0,
        node_clearance_time_sec=0, amr_spacing_m=0)
    c['floor_dxf_files'] = [dict(floor=f, filepath=str(Path(drawings) / f'floor-{f}.dxf')) for f in range(3)]
    c['locations'], c['departments'], c['lifts'], c['tasks'] = [], [], [], []
    c['corridors'] = dict(auto_connect=False, nodes=[], edges=[])
    c['payloads'] = [dict(name=n, length_m=.8, width_m=.6, height_m=1,
        weight_kg=20, allowed_carry_orientations=['lengthways']) for n in ('Clean tote', 'Dirty cart')]
    c['amrs'] = [dict(id='Teaching AMR', quantity=4, length_m=1, width_m=.7,
        speed_m_per_sec=1.5, payload_capacity_kg=100, payload_length_capacity_m=1.2,
        payload_width_capacity_m=.9, payload_height_capacity_m=1.5, motor_power_w=96,
        battery_capacity_kwh=.1, battery_soc_percent=15, battery_charge_rate_kw=2,
        recharge_threshold_percent=20)]
    for f in range(3):
        for flow, y in [('Clean', 7), ('Dirty', 13)]:
            c['locations'].append(dict(name=f'{flow}-F{f}', floor=f, x=8+f*2, y=4 if flow=='Clean' else 16,
                max_concurrency=2))
            for x in (3, 8, 10, 12, 18, 24, 30, 34, 38):
                c['corridors']['nodes'].append(dict(name=f'{flow}-J{x}-F{f}', floor=f, x=x, y=y))
            names = [f'{flow}-J{x}-F{f}' for x in (3, 8, 10, 12, 18, 24, 30, 34, 38)]
            for a,b in zip(names,names[1:]):
                c['corridors']['edges'].append(dict(**{'from':a,'to':b}, width_m=2.4, bidirectional=True))
            door=f'{flow}-door-F{f}'
            c['corridors']['nodes'].append(dict(name=door,floor=f,x=8+f*2,y=6 if flow=='Clean' else 14,
                has_door=True,door_clear_width_m=1.2))
            for a,b in [(f'{flow}-F{f}',door),(door,f'{flow}-J{8+f*2}-F{f}')]:
                c['corridors']['edges'].append(dict(**{'from':a,'to':b},width_m=2.4,bidirectional=True))
        c['departments'].append(dict(id=f'D{f}', name=f'Floor {f} service', enabled=True,
            floor=f, operating_start_time='06:00', operating_end_time='08:00',
            task_generation_locations={'stores':[f'Clean-F{f}'], 'linen':[f'Dirty-F{f}']}))
        c['corridors']['nodes'].append(dict(name=f'Transition-F{f}', floor=f, x=3, y=10))
        for flow in ('Clean','Dirty'):
            c['corridors']['edges'].append(dict(**{'from':f'{flow}-J3-F{f}',
                'to':f'Transition-F{f}'}, width_m=2.4, bidirectional=True))
    c['locations'] += [dict(name='Dispatch', floor=0, x=3, y=10, inventory_spaces=deepcopy(list(CHARGING_BAYS))),
        dict(name='Clean store', floor=0, x=3, y=7),
        dict(name='Dirty receiving', floor=0, x=3, y=13,
             wash_cycle_required=True, wash_location='Wash', wash_cycle_duration_sec=60),
        dict(name='Wash', floor=0, x=5, y=13, max_concurrency=1)]
    for a,b in [('Dispatch','Transition-F0'),('Clean store','Clean-J3-F0'),
                ('Dirty receiving','Dirty-J3-F0'),('Wash','Dirty-J3-F0')]:
        c['corridors']['edges'].append(dict(**{'from':a,'to':b}, width_m=2.4,
            bidirectional=True, distance_m=2 if a=='Wash' else .1))
    for i,x in enumerate((34,38),1):
        c['lifts'].append(dict(id=f'L{i}', served_floors=[0,1,2], start_floor=0,
            floor_locations={str(f):dict(x=x,y=10) for f in range(3)},
            speed_floors_per_sec=.5, door_time_sec=4, boarding_time_sec=3,
            capacity_length_m=2, capacity_width_m=2, capacity_height_m=2.5,
            capacity_size_units=1, health_loss_per_journey_percent=0,
            shaft_length_m=2, shaft_width_m=2, landing_depth_m=1, shaft_clearance_m=.1))
        for f in range(3):
            for flow in ('Clean','Dirty'):
                c['corridors']['edges'].append(dict(**{'from':f'{flow}-J{x}-F{f}',
                    'to':f'L{i}-F{f}'}, width_m=2.4, bidirectional=True))
    c['task_generation'] = dict(enabled=True, staff_config={'enabled':False}, categories={})
    for key,flow,payload in [('stores','Clean','Clean tote'),('linen','Dirty','Dirty cart')]:
        groups=[]
        for f in range(3):
            clean=flow=='Clean'
            groups.append(dict(id=f'{flow}-{f}', departments=[f'D{f}'], payload=dict(
                enabled=True, pickup_location='Clean store' if clean else f'Dirty-F{f}',
                dropoff_location=f'Clean-F{f}' if clean else 'Dirty receiving',
                department_location_role='dropoff' if clean else 'pickup')))
        c['task_generation']['categories'][key] = dict(enabled=True, display_name=flow,
            generation_mode='scheduled', scheduled_times=['06:05','06:35','07:05','07:35'],
            schedule_times=['06:05','06:35','07:05','07:35'], days_active=['mon'],
            payload=payload, route_profile=flow.lower(), priority=40,
            target_time=600, requires_staff=False, return_enabled=flow=='Clean',
            return_payload='Clean tote', return_route_profile='clean', return_delay_minutes=2,
            department_groups=groups)
    set_policy(c, policy)
    return c


def set_policy(c, policy):
    if policy not in ('dedicated','shared'):
        raise ValueError('Choose dedicated or shared lift access.')
    c['route_profiles']={}
    for flow,lift in [('clean','L1'),('dirty','L2')]:
        nodes=[r['name'] for r in c['locations']+c['corridors']['nodes'] if
               r['name'].lower().startswith(flow)]
        if flow=='dirty': nodes.append('Wash')
        lifts=[r['id'] for r in c['lifts']] if policy=='shared' else [lift]
        nodes += [f'{name}-F{f}' for name in lifts for f in range(3)]
        c['route_profiles'][flow]=dict(allowed_nodes=nodes, allowed_lifts=lifts)
        from amr_tutorial_values import route_edges
        c['route_profiles'][flow]['allowed_edges']=[list(pair) for pair in sorted(route_edges(c,flow,lifts))]


def generate_assets(output):
    import ezdxf
    from amr_project import Project
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    def add_floor(doc, floor, offset=0, prefix=''):
        m=doc.modelspace()
        def rect(layer,x0,y0,x1,y1):
            m.add_lwpolyline([(x0+offset,y0),(x1+offset,y0),(x1+offset,y1),(x0+offset,y1)],
                close=True,dxfattribs={'layer':prefix+layer})
        rect('BOUNDARY',0,0,40,20)
        rect('CIRCULATION',1,6,39,14)
        rect('WALLS',0,5.8,40,6); rect('WALLS',0,14,40,14.2)
        rect('CLEAN',1,1,39,5.8); rect('DIRTY',1,14.2,39,19)
        for x in (8,10,12,24):
            rect('DOORS',x-.6,5.7,x+.6,6.1); rect('DOORS',x-.6,13.9,x+.6,14.3)
        for x in (34,38): rect('SHAFTS',x-1,9,x+1,11)
        if floor==0:
            for name,x,y in [('Dispatch / recharge',3,10),('Clean store',3,7),
                              ('Dirty receiving',3,13),('AMR washing',5,13)]:
                m.add_text(name,dxfattribs={'layer':prefix+'ANNOTATIONS','height':.35,
                                          'insert':(x+offset,y)})
            rect('FACILITIES',1,8.5,5,11.5)
        m.add_text(f'Floor {floor} — 800 m2 — 40 x 20 m',dxfattribs={
            'layer':prefix+'ANNOTATIONS','height':.5,'insert':(1+offset,19)})
    combined=ezdxf.new('R2010'); combined.units=6
    for f in range(3):
        doc=ezdxf.new('R2010'); doc.units=6
        for layer in LAYERS: doc.layers.new(layer)
        add_floor(doc,f); _save_drawing(doc,output/f'floor-{f}.dxf')
        for layer in LAYERS: combined.layers.new(f'F{f}_{layer}')
        add_floor(combined,f,offset=f*45,prefix=f'F{f}_')
    _save_drawing(combined,output/'building-three-floors.dxf')
    reference=building_config(output)
    starter=deepcopy(reference)
    for key in ('locations','departments','amrs','payloads','lifts','tasks'): starter[key]=[]
    starter['corridors']=dict(auto_connect=False,nodes=[],edges=[])
    starter['task_generation']=dict(enabled=False,categories={}); starter['route_profiles']={}
    for name,config in [('starter',starter),('reference-dedicated',reference),
                        ('reference-shared',building_config(output,'shared'))]:
        p=Project(); p.save(output/f'{name}.amrproj',config,label=name)
        (output/f'{name}.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    for chapter in (3,4,5,6,7):
        cfg=deepcopy(reference)
        if chapter<7: cfg['task_generation']=dict(enabled=False,categories={})
        if chapter<6: cfg['route_profiles']={}
        if chapter<5: cfg['amrs']=[]; cfg['payloads']=[]; cfg['lifts']=[]
        if chapter<5: cfg['corridors']['edges']=[e for e in cfg['corridors']['edges'] if not
                                               any(v.startswith('L1-') or v.startswith('L2-') for v in (e['from'],e['to']))]
        if chapter<4:
            cfg['locations']=[r for r in cfg['locations'] if '-F' in r['name']]
            known={r['name'] for r in cfg['locations']+cfg['corridors']['nodes']}
            cfg['corridors']['edges']=[e for e in cfg['corridors']['edges'] if e['from'] in known and e['to'] in known]
        p=Project(); p.save(output/f'chapter-{chapter}.amrproj',cfg,label=f'Chapter {chapter}')
    return reference


def _save_drawing(doc,path):
    import ezdxf
    previous=ezdxf.options.write_fixed_meta_data_for_testing
    try:
        ezdxf.options.write_fixed_meta_data_for_testing=True
        from ezdxf.document import CREATED_BY_EZDXF,CONST_MARKER_STRING
        doc.ezdxf_metadata()[CREATED_BY_EZDXF]=CONST_MARKER_STRING
        doc.saveas(path)
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing=previous


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('output',type=Path)
    generate_assets(p.parse_args().output)
