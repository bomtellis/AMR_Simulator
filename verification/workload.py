"""Reproducible scale measurement; explicitly separate from realistic LTN validation."""
import argparse
import contextlib
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

from amr_project import Project
from amr_project_runs import PreparedRun, execute
from amr_results_investigation import load_investigation
from visualiser.project_checks import check_project


def workload_config(*, floors=10, robots_per_floor=6, tasks_per_day=1000, days=7,
                    lift_wear_percent_per_journey=None):
    if any(type(n) is not int or n <= 0 for n in (floors,robots_per_floor,tasks_per_day,days)):
        raise ValueError('Workload dimensions must be positive integers.')
    if lift_wear_percent_per_journey is not None and (
            type(lift_wear_percent_per_journey) not in (int,float)
            or not math.isfinite(lift_wear_percent_per_journey)
            or not 0 <= lift_wear_percent_per_journey <= 100):
        raise ValueError('Lift wear must be finite percentage points between 0 and 100.')
    start = datetime(2026,1,5,6)
    config = dict(simulation=dict(start_datetime=start.isoformat(),
        end_datetime=(start+timedelta(days=days)).isoformat(),motion_model='legacy',
        task_release_stagger_sec=0,precompute_static_routes=True),
        building=dict(floor_height_m=4,load_unload_time_sec=10,enable_idle_return=False,
                      charge_locations=[f'Source-{f}' for f in range(floors)]),
        locations=[],corridors=dict(auto_connect=False,nodes=[],edges=[]),amrs=[],
        payloads=[dict(name='Trolley',length_m=1,width_m=.7,height_m=1,weight_kg=50,
                       allowed_carry_orientations=['lengthways'])],lifts=[],tasks=[],
        task_generation=dict(enabled=False))
    for floor in range(floors):
        robot_type = f'Robot-F{floor}'
        bays = [dict(name=f'Charger-{i}',stores_amr=True,has_charger=True,
                     length_m=2,width_m=2,height_m=2,payload_slots=[dict(amr_type=robot_type)])
                for i in range(robots_per_floor)]
        config['locations'].extend([dict(name=f'Source-{floor}',floor=floor,x=0,y=0,inventory_spaces=bays),
                                    dict(name=f'Destination-{floor}',floor=floor,x=100,y=0)])
        config['amrs'].append(dict(id=robot_type,quantity=robots_per_floor,length_m=1,width_m=.6,height_m=.5,
            speed_m_per_sec=1.2,payload_capacity_kg=200,payload_length_capacity_m=2,
            payload_width_capacity_m=2,payload_height_capacity_m=2,battery_capacity_kwh=10,
            battery_charge_rate_kw=2,recharge_threshold_percent=20))
        chain = [f'Source-{floor}',f'Lift-1-F{floor}',f'Lift-2-F{floor}',f'Destination-{floor}']
        config['corridors']['edges'].extend(dict(zip(('from','to'),pair),width_m=3,bidirectional=True)
                                             for pair in zip(chain,chain[1:]))
    for lift,x in [('Lift-1',40),('Lift-2',60)]:
        config['lifts'].append(dict(id=lift,served_floors=list(range(floors)),speed_floors_per_sec=.25,
            door_time_sec=3,boarding_time_sec=5,capacity_length_m=3,capacity_width_m=2,
            capacity_height_m=2.2,floor_locations={str(f):dict(x=x,y=0) for f in range(floors)}))
        if lift_wear_percent_per_journey is not None:
            config['lifts'][-1]['health_loss_per_journey_percent'] = lift_wear_percent_per_journey
    for day in range(days):
        for index in range(tasks_per_day):
            floor = index % floors
            destination = (floor+1) % floors if index % 4 == 0 else floor
            config['tasks'].append(dict(id=f'D{day+1}-T{index+1}',pickup=f'Source-{floor}',
                dropoff=f'Destination-{destination}',payload='Trolley',
                release_time=day*86400+index*36000/tasks_per_day))
    return config


def peak_working_set():
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)] + [
            (name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
            'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    current = ctypes.WinDLL('kernel32').GetCurrentProcess
    current.restype = wintypes.HANDLE
    read = ctypes.WinDLL('psapi').GetProcessMemoryInfo
    read.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    return counters.PeakWorkingSetSize if read(current(),ctypes.byref(counters),counters.cb) else None


def run_workload(output, **dimensions):
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if (output/'workload.amrproj').exists():
        raise ValueError('Use a new output directory to preserve previous benchmark evidence.')
    config = workload_config(**dimensions)
    raw = json.dumps(config,sort_keys=True,indent=2).encode()
    (output/'input.json').write_bytes(raw)
    project = Project()
    started = time.perf_counter()
    project.save(output/'workload.amrproj',config,base_dir=output,label='Controlled scale benchmark')
    save_seconds = time.perf_counter()-started
    started = time.perf_counter()
    reopened = Project.open(project.path)
    roundtrip = reopened.configuration() == config
    open_seconds = time.perf_counter()-started
    draft = PreparedRun(project,output/'results')
    try:
        findings = check_project(draft.config,base_path=draft.directory)
        findings.acknowledge_warnings()
        directory = draft.commit(findings)
    finally:
        draft.discard()
    started = time.perf_counter()
    with (directory/'process.log').open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log):
        sim = execute(directory)
    execution_seconds = time.perf_counter()-started
    completed = sorted(row['task_id'] for row in sim.completed_task_records)
    expected = sorted(task['id'] for task in config['tasks'])
    pending_tasks = sorted((task for _,_,_,task in sim.pending_tasks
                            if task.id not in sim._removed_pending_task_ids),key=lambda task: task.id)
    pending = [task.id for task in pending_tasks]
    outcome = dict(completed=sim.completed_task_records,failed=sim.failed_tasks,pending=pending)
    report = dict(dimensions=dimensions,python=sys.version,platform=platform.platform(),
        input_sha256=hashlib.sha256(raw).hexdigest(),project_bytes=project.path.stat().st_size,
        save_seconds=save_seconds,open_seconds=open_seconds,configuration_roundtrip_matches=roundtrip,
        execution_and_exports_seconds=execution_seconds,simulated_last_event_sec=sim.current_time,
        robot_count=len(sim.amrs),expected_tasks=len(expected),completed_tasks=len(completed),
        failed_tasks=len(sim.failed_tasks),pending_tasks=len(pending),all_expected_completed=completed == expected,
        pending_task_details=[dict(task_id=t.id,pickup=t.pickup,dropoff=t.dropoff,
                                   last_pending_reason=t.pending_reason) for t in pending_tasks],
        final_robots=[dict(id=a.id,location=a.location_name,battery_soc_percent=a.battery_soc_percent,
                           is_charging=a.is_charging,available_time=a.available_time,
                           home_charge_location=a.home_charge_location) for a in sim.amrs],
        final_lifts=[dict(id=lift.id,health_percent=lift.health_percent,
                          journeys_completed=lift.journeys_completed) for lift in sim.lifts],
        outcome_sha256=hashlib.sha256(json.dumps(outcome,sort_keys=True,default=str).encode()).hexdigest(),
        run_directory=str(directory),output_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),
        warning_review='Automatically acknowledged for this controlled benchmark, not human approval.',
        lift_wear_assumption=('Simulator defaults retained.' if dimensions.get('lift_wear_percent_per_journey') is None
            else f"Explicit sensitivity case: {dimensions['lift_wear_percent_per_journey']} percentage points lost per journey. This does not model maintenance."),
        limitations=['Controlled simple-mode workload, not LTN or detailed traffic validation.',
            'Ten-hour daily release window; every fourth task goes to the next floor when multiple floors exist.',
            'Two lift banks, 100 m straight floor routes, one payload type, six robot bays per floor at default scale.',
            'No geometric walls, drawings, staffing or dynamic demand; live GUI responsiveness is not measured.',
            'No agreed runtime threshold. Each invocation measures one fresh process.'])
    started = time.perf_counter()
    try:
        investigation = load_investigation(directory)
        report['reconciliation'] = investigation['reconciliation']
        report['reconciliation_matches'] = all(r['matches'] for r in investigation['reconciliation'])
    except (ValueError, OSError) as error:
        report.update(reconciliation_matches=False,investigation_error=str(error))
    report['investigation_seconds'] = time.perf_counter()-started
    report['peak_working_set_bytes'] = peak_working_set()
    report['input_unchanged'] = (output/'input.json').read_bytes() == raw
    (output/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--lift-wear-percent-per-journey',type=float,default=None,
                        help='Explicit lift-wear sensitivity override; omit to retain simulator defaults. Zero models constant health, not maintenance.')
    for name,default in [('floors',10),('robots-per-floor',6),('tasks-per-day',1000),('days',7)]:
        parser.add_argument('--'+name,type=int,default=default)
    args = vars(parser.parse_args())
    report = run_workload(**args)
    return 0 if all(report[k] for k in ('all_expected_completed','reconciliation_matches','input_unchanged','configuration_roundtrip_matches')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
