"""Fresh-process CPU benchmarks on the unmodified seven-day LTN model."""
import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

class Quiet:
    def write(self,value): return len(value)
    def flush(self): pass

def sample(backend,path,profile=False):
    if backend != 'cpu':
        raise ValueError('Only CPU simulation is supported')
    from simulator import Simulation
    from amr_stress_resources import process_memory
    from benchmark_compact import outcome
    from amr_run_evidence import config_hash
    source=json.loads((ROOT/'ltn.json').read_text(encoding='utf-8-sig'))
    original_hash=config_hash(source)
    profiler=None
    if profile:
        import cProfile
        profiler=cProfile.Profile(); profiler.enable()
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as temporary:
        directory=Path(temporary); phases=[]; last_phase=[None,time.perf_counter()]
        def feedback(message):
            phase=message['phase']
            if phase=='Running simulation': phase='Execution'
            if phase!=last_phase[0]:
                now=time.perf_counter()
                if last_phase[0] is not None: phases.append(dict(phase=last_phase[0],seconds=now-last_phase[1]))
                last_phase[:]=[phase,now]
        start=time.perf_counter()
        with contextlib.redirect_stdout(Quiet()):
            init=time.perf_counter()
            sim=Simulation(source,verbose=True,verbose_csv_path=str(directory/'simulation_steps.csv'),defer_exports=True,
                           progress_callback=feedback)
            initialized=time.perf_counter()
            sim.run()
            executed=time.perf_counter()
            sim.write_verbose_csv()
            sealed=time.perf_counter()
        elapsed=sealed-start
        if profiler:
            profiler.disable(); profiler.dump_stats(str(path.with_suffix('.prof')))
        peak=process_memory(os.getpid())['peak']
        result=dict(backend=backend,profiled=profile,wall_sec=elapsed,initialisation_sec=initialized-init,
            execution_sec=executed-initialized,finalisation_sec=sealed-executed,peak_parent_bytes=peak,
            source_config_sha256=original_hash,software_sha256=sim._evidence_software['sha256'],
            period={key:source['simulation'][key] for key in ('start_datetime','end_datetime')},
            outcome=outcome(sim),
            evidence_bytes=sum(item.stat().st_size for item in directory.iterdir() if item.is_file()))
        from amr_event_store import iter_events
        from tests.test_compact_execution import normalise
        digest=hashlib.sha256()
        for row in iter_events(sim.event_store.path):
            digest.update(json.dumps(normalise(row,sim.run_id),sort_keys=True,separators=(',',':'),allow_nan=False).encode())
            digest.update(b'\n')
        result['outcome']['event_rows_sha256']=digest.hexdigest()
        from tests.test_route_reservation_atomicity import resource_state
        from dataclasses import fields,is_dataclass
        def data(value):
            if isinstance(value,float) and not math.isfinite(value): return {'special_float':value.hex()}
            if is_dataclass(value): return {field.name:data(getattr(value,field.name)) for field in fields(value)}
            if isinstance(value,dict): return {str(key):data(item) for key,item in value.items()}
            if isinstance(value,set): return sorted((data(item) for item in value),key=repr)
            if isinstance(value,(list,tuple)): return [data(item) for item in value]
            return value
        state=dict(resources=resource_state(sim),robots=[vars(robot) for robot in sim.amrs],
                   payload_inventory=vars(sim.payload_instance_store))
        result['outcome']['final_state_sha256']=hashlib.sha256(json.dumps(normalise(data(state),sim.run_id),
            sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        from amr_event_store import export_rows
        expanded=time.perf_counter()
        export_rows(sim.event_store.path,directory/'expanded.csv',sim._verbose_fieldnames())
        result['first_expansion_sec']=time.perf_counter()-expanded
        path.write_text(json.dumps(result,indent=2),encoding='utf-8')

def benchmark(output,repeats,backends):
    if backends != ['cpu']:
        raise ValueError('Only CPU simulation is supported')
    rows=[]; output.parent.mkdir(parents=True,exist_ok=True)
    for repeat in range(repeats):
        order=backends if repeat%2==0 else list(reversed(backends))
        for backend in order:
            path=ROOT/'tmp'/f'computation-{backend}-{repeat}.json'
            environment=os.environ.copy()
            environment['PYTHONPATH']=os.pathsep.join(value for value in sys.path if value)
            environment['PYTHONIOENCODING']='utf-8'
            for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
                environment[key]='1'
            command=[getattr(sys,'_base_executable',sys.executable),str(Path(__file__).resolve()),'--sample',backend,'--output',str(path)]
            result=subprocess.run(command,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
            if result.returncode: raise RuntimeError(result.stdout[-4000:])
            row=json.loads(path.read_text()); rows.append(row)
            print(f"{backend} {repeat+1}/{repeats}: {row['wall_sec']:.3f}s, execution {row['execution_sec']:.3f}s",flush=True)
            output.write_text(json.dumps(dict(samples=rows),indent=2),encoding='utf-8')
            if any(item['outcome']!=rows[0]['outcome'] or item['source_config_sha256']!=rows[0]['source_config_sha256'] or
                   item['software_sha256']!=rows[0]['software_sha256'] for item in rows):
                raise ValueError('Outcome/input/software parity failed')
    summaries={}
    for backend in backends:
        selected=[row for row in rows if row['backend']==backend]
        summaries[backend]={key:statistics.median(row[key] for row in selected) for key in
            ('wall_sec','initialisation_sec','execution_sec','finalisation_sec','peak_parent_bytes','evidence_bytes','first_expansion_sec')}
    output.write_text(json.dumps(dict(samples=rows,summaries=summaries,outcome_parity=True),indent=2),encoding='utf-8')
    print(json.dumps(summaries,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',choices=('cpu',))
    parser.add_argument('--backends',default='cpu')
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--source-tree', type=Path,
        help='For --sample only, load the simulator from a preserved source tree.')
    parser.add_argument('--output',type=Path,default=ROOT/'verification'/'cpu-ltn-seven-day.json')
    args=parser.parse_args()
    if args.source_tree is not None:
        if not args.sample:
            parser.error('--source-tree requires --sample')
        selected = args.source_tree.resolve()
        if not (selected / 'simulator.py').is_file():
            parser.error('--source-tree must contain simulator.py')
        sys.path.insert(0, str(selected))
        # Preload before benchmark helpers can prepend their own workspace.
        import simulator
    if args.sample: sample(args.sample,args.output,args.profile)
    else: benchmark(args.output,args.repeats,args.backends.split(','))
