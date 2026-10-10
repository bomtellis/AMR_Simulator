"""Private, resumable lift comparisons over normal frozen project/run contracts."""
from copy import deepcopy
from dataclasses import asdict
import argparse
import contextlib
import csv
import io
import json
from pathlib import Path
import time

from amr_project import Project,atomic_write
from amr_run_evidence import config_hash,file_hash,software_snapshot

SCENARIOS=('normal','peak','lift-1-outage','lift-2-outage','half-speed',
           'corridor-closure','reduced-charging','slow-wash')


def write_record(path,value):
    atomic_write(path,json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode('utf-8'))


def input_identity(config):
    # Opening a project fills editor defaults. Compare the same resolved inputs
    # before and after reopening, while retaining all explicitly authored fields.
    from visualiser.models import JsonStore
    c=JsonStore(config).data; drawings=[]
    for row in c.get('floor_dxf_files',[]):
        path=Path(row['filepath']); drawings.append(dict(floor=row['floor'],sha256=file_hash(path)))
        row['filepath']=f"sha256:{drawings[-1]['sha256']}"
    return dict(config_hash=config_hash(c),drawings=drawings)


def realize_demand(config):
    """Capture baseline requests, including endogenous returns, once for fair replay."""
    from simulator import Simulation
    cfg=deepcopy(config); cfg['scenario_testing']={'enabled':False,'scenarios':[]}
    captured={}; sim=Simulation(cfg,verbose=False)
    original=sim._log_task_released
    def record(task,event_time):
        row={k:v for k,v in asdict(task).items() if v is not None}; row['return_enabled']=False; row['payload_instance_id']=''
        row['pending_reason']=''; row['assigned_inventory_space']=''
        if row['target_time']<=0: row['target_time']=600.0
        captured[task.id]=row
        original(task,event_time)
    sim._log_task_released=record
    with contextlib.redirect_stdout(io.StringIO()):sim.run()
    if not captured: raise ValueError('No requests were released in the chosen study window.')
    if sim.failed_tasks or sim.pending_tasks:
        raise ValueError('Resolve baseline failed/pending work before freezing the demand schedule.')
    return sorted(captured.values(),key=lambda r:(r['release_time'],r['id']))


def scenario_config(config,requests,name):
    if name not in SCENARIOS:raise ValueError('Unknown teaching scenario.')
    c=deepcopy(config); c['task_generation']['enabled']=False; c['tasks']=deepcopy(requests)
    c['scenario_testing']=dict(enabled=False,enhanced_logging=True,active_scenario='Normal operation',scenarios=[])
    c['simulation'].update(scenario_mode=False,scenario_enhanced_logging=True,precompute_static_routes=False)
    # Frozen arrivals remain unchanged for each layout; peak duplicates all requests.
    if name=='peak':
        duplicates=deepcopy(requests)
        for r in duplicates:r['id']+='-peak';r['payload_instance_id']=''
        c['tasks']+=duplicates
    if name in ('lift-1-outage','lift-2-outage','half-speed','corridor-closure'):
        lifts=c.get('lifts',[])
        if len(lifts)<2:raise ValueError('The teaching comparison needs two lifts.')
        kind='lift'; resources=[lifts[1 if name=='lift-2-outage' else 0]['id']]
        if name=='corridor-closure':
            edges=c.get('corridors',{}).get('edges',[])
            # Prefer a non-connector trunk edge; preserve its identity in all proposals.
            edge=next((e for e in edges if '-J' in e['from'] and '-J' in e['to']),edges[0] if edges else None)
            if edge is None:raise ValueError('Provide an important corridor edge.')
            kind='corridor';resources=[f"{edge['from']} -> {edge['to']}"]
        event=dict(resource_type=kind,resource_ids=resources,start_time='06:05',end_time='06:20',
            days_active=['mon'],availability_percent=100 if name=='half-speed' else 0,
            speed_factor=.5 if name=='half-speed' else 1)
        # Use the configured start day/time rather than assuming a tutorial date.
        from datetime import datetime,timedelta
        start=datetime.fromisoformat(c['simulation']['start_datetime'])
        event['start_time']=(start+timedelta(minutes=5)).strftime('%H:%M')
        event['end_time']=(start+timedelta(minutes=20)).strftime('%H:%M')
        event['days_active']=[start.strftime('%a').lower()]
        c['scenario_testing'].update(enabled=True,active_scenario=name,scenarios=[dict(name=name,events=[event])])
    elif name=='reduced-charging':
        from amr_inventory_inputs import inventory_space_is_amr
        retained=False
        for location in c.get('locations',[]):
            for bay in location.get('inventory_spaces',[]):
                if inventory_space_is_amr(bay) and bay.get('has_charger'):
                    bay['has_charger']=not retained;retained=True
        if not retained:raise ValueError('This scenario needs charger-equipped AMR bays.')
    elif name=='slow-wash':
        for location in c.get('locations',[]):
            if location.get('wash_cycle_required'):location['wash_cycle_duration_sec']*=3
    return c


def run_metrics(directory):
    from amr_project_runs import validate_run_inputs,read_json
    directory=Path(directory); manifest,c=validate_run_inputs(directory)
    if manifest['status']!='complete':raise ValueError('Only complete runs can be ranked.')
    log=directory/'simulation_steps.csv'; evidence=read_json(directory/'simulation_steps.csv.run.json')
    if evidence.get('log_sha256')!=file_hash(log) or evidence.get('project_binding')!=manifest['project_binding']:
        raise ValueError('Run log is incomplete or does not match its bound evidence.')
    with log.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    locations={r['name']:r for r in c.get('locations',[])}
    departments={r['id']:r for r in c.get('departments',[])}
    tasks={r['id']:r for r in c.get('tasks',[])}
    def number(row,key):return float(row.get(key) or 0)
    released={r['task_id']:r for r in rows if r['event_type']=='task_released'}
    complete={r['task_id']:number(r,'sim_time_sec') for r in rows if r['event_type']=='task_complete'}
    failed={r['task_id'] for r in rows if r['event_type']=='task_failed'}
    summary=evidence['summary']
    if (set(complete)!=set(summary['completed_task_ids']) or failed!=set(summary['failed_task_ids'])
        or set(complete)&failed or not (set(complete)|failed)<=set(released)
        or set(released)-set(complete)-failed!=set(summary.get('pending_task_ids',[]))):
        raise ValueError('Task outcomes do not reconcile with the registered run evidence.')
    if c.get('tasks') and set(released)!=set(tasks):
        raise ValueError('Frozen request evidence is incomplete.')
    groups={}; requests=[]
    for identity,row in released.items():
        task=tasks.get(identity,{})
        flow=task.get('route_profile') or ''
        if not flow:
            cats=c.get('task_generation',{}).get('categories',{})
            cat=next((value for key,value in cats.items() if identity.startswith('GEN_'+key.upper()+'_')
                      or identity.startswith('RETURN-GEN_'+key.upper()+'_')), {})
            flow=cat.get('route_profile') or row.get('payload') or 'unclassified'
        dest=locations.get(row['to_location'],{}).get('floor')
        dept=departments.get(row.get('department_id'),{})
        floor=dept.get('floor',dest)
        key=f'{floor}/{flow}'; target=number(row,'task_target_time_sec'); release=number(row,'task_release_time_sec')
        end=complete.get(identity); outcome='completed' if end is not None else 'failed' if identity in failed else 'pending'
        on_time=end is not None and target>0 and end<=release+target+.001
        g=groups.setdefault(key,dict(floor=floor,flow=flow,requests=0,completed=0,failed=0,pending=0,targeted=0,on_time=0))
        g['requests']+=1;g[outcome]+=1;g['targeted']+=target>0;g['on_time']+=on_time
        requests.append(dict(id=identity,release=release,target=target,pickup=row['from_location'],
            dropoff=row['to_location'],payload=row['payload'],destination_floor=dest,service_floor=floor,flow=flow,outcome=outcome,on_time=on_time))
    for g in groups.values():g['on_time_rate']=g['on_time']/g['targeted'] if g['targeted'] else None
    horizontal_loaded=horizontal_empty=vertical=lift_wait=charge_wait=wash_wait=0.0
    lifts={};wash=charging=0;seen=set()
    for row in rows:
        typ=row['segment_type']; event=row['event_type']
        if not event.startswith(('segment_','multi_stop_segment_')):continue
        try:detail=json.loads(row.get('details') or '{}')
        except ValueError:detail={}
        distance=number(row,'distance_m'); duration=number(row,'duration_sec')
        if typ=='corridor':
            if row.get('payload') or json.loads(row.get('onboard_payloads') or '[]'):horizontal_loaded+=distance
            else:horizontal_empty+=distance
        elif typ=='lift_transfer':
            identity=(row['lift_id'],row['start_time'],row['end_time'],row['from_location'],row['to_location'])
            if identity not in seen:
                seen.add(identity);vertical+=distance
                v=lifts.setdefault(row['lift_id'],dict(journeys=0,busy_sec=0,wait_sec=0))
                wait=number(row,'wait_time_sec') or float(detail.get('wait_time',0))
                v['journeys']+=1;v['busy_sec']+=max(0,duration-wait);v['wait_sec']+=wait;lift_wait+=wait
        elif typ=='wash_cycle':wash+=1
        elif typ=='charge':charging+=1
        elif typ=='wait_for_lift':
            lift_wait+=duration
            if row['lift_id']:
                v=lifts.setdefault(row['lift_id'],dict(journeys=0,busy_sec=0,wait_sec=0));v['wait_sec']+=duration
        if detail.get('wait_reason')=='wash_capacity':wash_wait+=duration
        if typ in ('charge_wait','wait_for_charge','wait_for_charger'):charge_wait+=duration
    from datetime import datetime
    horizon=(datetime.fromisoformat(c['simulation']['end_datetime'])-datetime.fromisoformat(c['simulation']['start_datetime'])).total_seconds()
    for v in lifts.values():v['utilisation']=v['busy_sec']/horizon
    return dict(groups=groups,requests=requests,completed=len(complete),failed=len(failed),pending=len(released)-len(complete)-len(failed),
        horizontal_loaded_m=horizontal_loaded,horizontal_empty_m=horizontal_empty,horizontal_m=horizontal_loaded+horizontal_empty,
        vertical_m=vertical,lift_wait_sec=lift_wait,lifts=lifts,wash_cycles=wash,charging_cycles=charging,
        charge_wait_sec=charge_wait,wash_wait_sec=wash_wait,run_key=manifest['run_key'],
        software_sha256=manifest['software']['sha256'],event_access=event_access(c,requests))


def event_access(config,requests):
    """Topological loaded-leg access during the configured outage, distinct from uptime."""
    events=next((r.get('events',[]) for r in config.get('scenario_testing',{}).get('scenarios',[]) if
        r['name']==config.get('scenario_testing',{}).get('active_scenario')),[])
    down_lifts=set();down_edges=set();down_nodes=set()
    for event in events:
        if event.get('availability_percent',100)>0:continue
        resources=event.get('resource_ids',[])
        if event['resource_type']=='lift':down_lifts.update(resources)
        elif event['resource_type']=='corridor':down_edges.update(resources)
        elif event['resource_type']=='corridor_node':down_nodes.update(resources)
    profiles=config.get('route_profiles',{});result={}
    for request in requests:
        p=profiles.get(request['flow'],{});allowed=set(p.get('allowed_nodes',[]));edges=set(tuple(pair) for pair in p.get('allowed_edges',[]))
        graph={}
        def connect(a,b,both=True,lift=False):
            if a in down_nodes or b in down_nodes or (allowed and (a not in allowed or b not in allowed)):return
            if not lift and edges and (a,b) not in edges:return
            graph.setdefault(a,set()).add(b)
            if both and (lift or not edges or (b,a) in edges):graph.setdefault(b,set()).add(a)
        for e in config['corridors']['edges']:
            if f"{e['from']} -> {e['to']}" in down_edges or f"{e['to']} -> {e['from']}" in down_edges:continue
            connect(e['from'],e['to'],e.get('bidirectional',True))
        for lift in config['lifts']:
            if lift['id'] in down_lifts or (p.get('allowed_lifts') and lift['id'] not in p['allowed_lifts']):continue
            stops=[f"{lift['id']}-F{f}" for f in lift['served_floors']]
            for a in stops:
                for b in stops:
                    if a!=b:connect(a,b,False,lift=True)
        seen={request['pickup']};queue=[request['pickup']]
        while queue:
            for n in graph.get(queue.pop(),()):
                if n not in seen:seen.add(n);queue.append(n)
        key=f"{request['service_floor']}/{request['flow']}"
        result[key]=result.get(key,True) and request['dropoff'] in seen
    return result


def rank_results(results,scenarios=SCENARIOS):
    baseline=results.get('current',{}); evaluated=[]
    if set(baseline)!=set(scenarios):return []
    def arrivals(metrics):
        return sorted((r['id'],r['release'],r['target'],r['pickup'],r['dropoff'],r['payload']) for r in metrics['requests'])
    for name,runs in results.items():
        if name=='current' or set(runs)!=set(scenarios):continue
        eligible=True;reasons=[];rates=[];distance=wait=0
        for scenario in scenarios:
            actual=runs[scenario]['metrics'];reference=baseline[scenario]['metrics']
            if arrivals(actual)!=arrivals(reference) or actual['software_sha256']!=reference['software_sha256']:
                eligible=False;reasons.append(f'{scenario}: arrivals or software differ')
            if set(actual['groups'])!=set(reference['groups']):eligible=False;reasons.append(f'{scenario}: floor/flow groups differ')
            for key,b in reference['groups'].items():
                a=actual['groups'].get(key,{})
                if b['on_time_rate'] is None or a.get('on_time_rate') is None:
                    eligible=False;reasons.append(f'{scenario}, {key}: no explicit service target');continue
                rates.append(a['on_time_rate'])
                if a['on_time_rate']+1e-12<b['on_time_rate'] or a['completed']<b['completed']:
                    eligible=False;reasons.append(f'{scenario}, {key}: service regression')
            distance+=actual['horizontal_m'];wait+=actual['lift_wait_sec']
        baseline_distance=sum(r['metrics']['horizontal_m'] for r in baseline.values())
        baseline_wait=sum(r['metrics']['lift_wait_sec'] for r in baseline.values())
        evaluated.append(dict(id=name,eligible=eligible,reasons=sorted(set(reasons)),
            worst_service=min(rates) if rates else 0,horizontal_m=distance,lift_wait_sec=wait,
            distance_change_m=distance-baseline_distance,wait_change_sec=wait-baseline_wait))
    return sorted(evaluated,key=lambda r:(not r['eligible'],-r['worst_service'],r['horizontal_m'],r['lift_wait_sec'],r['id']))


def create_study(config,path,source_project=None):
    import uuid
    path=Path(path).resolve();root=path.with_suffix('')/('study-'+uuid.uuid4().hex[:12]);root.mkdir(parents=True,exist_ok=True)
    frozen=deepcopy(config)
    for r in frozen.get('floor_dxf_files',[]):
        source=Path(r['filepath']);target=root/f"floor-{r['floor']}-{file_hash(source)[:12]}.dxf"
        atomic_write(target,source.read_bytes());r['filepath']=str(target)
    state=dict(version=1,status='ready',root=str(root),source_identity=input_identity(config),software_sha256=software_snapshot()['sha256'],
        source_project=str(source_project) if source_project else None,config=frozen,
        requests=realize_demand(frozen),scenarios=list(SCENARIOS),proposals={},results={},
        baseline_complete=False,recommendation=None,variant=None,geometry=None,confirmed=False)
    if source_project:state['source_revision']=Project.open(source_project).revisions[-1]
    write_record(path,state);return state


def evaluate(path,cancel=None,progress=None):
    from amr_project_runs import PreparedRun,execute
    from visualiser.project_checks import check_project
    path=Path(path).resolve();state=json.loads(path.read_text(encoding='utf-8'));root=Path(state['root'])
    if not state.get('confirmed') or not state.get('geometry'):raise ValueError('Confirm drawing interpretation before evaluating sites.')
    if state.get('software_sha256')!=software_snapshot()['sha256']:raise ValueError('Software changed; create a new study.')
    if input_identity(state['config'])!=state['source_identity']:raise ValueError('Frozen drawing or configuration changed; create a new study.')
    for proposal in state['proposals'].values():
        for key in ('simulation','building','amrs','payloads','departments','locations','tasks','task_generation'):
            if proposal.get(key)!=state['config'].get(key):raise ValueError('Location comparisons must keep equipment, demand and operational assumptions fixed.')
        originals=[{k:v for k,v in lift.items() if k!='floor_locations'} for lift in state['config']['lifts']]
        actual=[{k:v for k,v in lift.items() if k!='floor_locations'} for lift in proposal['lifts']]
        if originals!=actual:raise ValueError('Lift identities and equipment must remain fixed.')
        for name,p in state['config'].get('route_profiles',{}).items():
            if p.get('allowed_lifts')!=proposal.get('route_profiles',{}).get(name,{}).get('allowed_lifts'):
                raise ValueError('Flow policy changed; create a separate study.')
    state.pop('error',None);state['status']='running';write_record(path,state)
    layouts={'current':state['config'],**state['proposals']}
    total=len(layouts)*len(state['scenarios']);number=0
    try:
        for identity,layout in layouts.items():
            runs=state['results'].setdefault(identity,{})
            for scenario in state['scenarios']:
                number+=1
                if cancel and cancel():state['status']='cancelled';write_record(path,state);return state
                previous=runs.get(scenario)
                if previous:
                    try:
                        fresh=run_metrics(previous['directory'])
                        if fresh==previous['metrics']:continue
                    except (OSError,ValueError,KeyError):pass
                if progress:progress(number,total,identity,scenario)
                cfg=scenario_config(layout,state['requests'],scenario)
                project=Project(); project_path=root/f'{identity}-{scenario}.amrproj'
                project.save(project_path,cfg,label=f'{identity}: {scenario}')
                draft=PreparedRun(project,root/'runs')
                report=check_project(draft.config)
                if any(f.severity=='error' for f in report.findings):
                    draft.discard();raise ValueError('; '.join(f.message for f in report.findings if f.severity=='error'))
                report.acknowledge_warnings();directory=draft.commit(report)
                try:
                    with contextlib.redirect_stdout(io.StringIO()):execute(directory)
                    metrics=run_metrics(directory)
                except Exception as exc:
                    from amr_project_runs import finish_run
                    finish_run(directory,1,error=str(exc));raise
                runs[scenario]=dict(directory=str(directory),project=str(project_path),metrics=metrics)
                state['baseline_complete']=set(state['results'].get('current',{}))==set(state['scenarios'])
                write_record(path,state)
        state['ranking']=rank_results(state['results'],state['scenarios'])
        baseline_worst=min(g['on_time_rate'] for r in state['results']['current'].values() for g in r['metrics']['groups'].values())
        eligible=[r for r in state['ranking'] if r['eligible'] and (r['worst_service']>baseline_worst+1e-12 or r['distance_change_m']<-.01 or r['wait_change_sec']<-.01)]
        state['recommendation']=eligible[0]['id'] if eligible else None
        state['explanation']='Service protected on every floor/flow.' if eligible else (
            'No evaluated proposal improves distance or waiting without reducing protected service. '
            'Dedicated lift permissions can prevent backup access; relocation does not add capacity or improve equipment uptime.')
        state['status']='complete';write_record(path,state);return state
    except Exception as exc:
        state['status']='failed';state['error']=str(exc);write_record(path,state);raise


def relink_result(state,layout,scenario,directory):
    old=state['results'][layout][scenario];new=run_metrics(directory)
    if new!=old['metrics']:raise ValueError('Moved run identity or evidence differs.')
    old['directory']=str(Path(directory).resolve())


def export_comparison(state,path):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['layout','scenario','service_floor','flow','requests','completed','failed','pending',
            'on_time_rate','loaded_horizontal_m','empty_horizontal_m','vertical_m','lift_wait_sec','charge_wait_sec','wash_wait_sec','reachable_during_event','run_key'])
        for layout,runs in state['results'].items():
            for scenario,run in runs.items():
                m=run['metrics']
                for g in m['groups'].values():writer.writerow([layout,scenario,g['floor'],g['flow'],g['requests'],g['completed'],g['failed'],
                    g['pending'],g['on_time_rate'],m['horizontal_loaded_m'],m['horizontal_empty_m'],m['vertical_m'],m['lift_wait_sec'],m['charge_wait_sec'],m['wash_wait_sec'],m.get('event_access',{}).get(f"{g['floor']}/{g['flow']}"),m['run_key']])


def main(path):
    evaluate(path,progress=lambda n,total,layout,scenario:print(f'{n}/{total}: {layout} — {scenario}',flush=True))
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('study',type=Path)
    raise SystemExit(main(p.parse_args().study))
