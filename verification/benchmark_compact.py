"""Fresh-process, unprofiled compact/reference benchmarks and outcome parity."""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class Quiet:
    def write(self, value):
        return len(value)
    def flush(self):
        pass


def configuration(kind):
    if kind == 'deliveries':
        from tests.test_multi_stop_route_rules import multi_route_config
        cfg = multi_route_config()
        cfg['simulation']['end_datetime'] = '2026-01-05T08:00:00'
        cfg['amrs'][0].update(quantity=4, multi_stop_enabled=False)
        cfg['tasks'] = [dict(id=f'P{i}', pickup='A', dropoff='B', payload='Box', release_time=i * 10)
                        for i in range(1200)]
        return cfg
    if kind == 'detailed':
        from tests.test_geometric_simulation import geometric_config
        cfg = geometric_config()
        cfg['simulation']['end_datetime'] = '2026-01-05T04:00:00'
        cfg['tasks'] = [dict(id=f'G{i}', pickup='A', dropoff='B', payload='Box', release_time=i * 60)
                        for i in range(120)]
        return cfg
    from datetime import datetime, timedelta
    cfg = json.loads((ROOT / 'ltn.json').read_text(encoding='utf-8-sig'))
    start = datetime.fromisoformat(cfg['simulation']['start_datetime'])
    cfg['simulation']['end_datetime'] = (start + timedelta(days=1)).isoformat()
    return cfg


def outcome(simulation):
    # Includes full route/energy records, not just completion counts.
    def normalise(value, run_id):
        if isinstance(value, str):
            return value.replace(run_id, '<run>')
        if isinstance(value, dict):
            return {key: normalise(item, run_id) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalise(item, run_id) for item in value]
        return value
    encoded = json.dumps(normalise(simulation.completed_task_records, simulation.run_id),
                         sort_keys=True, default=str, separators=(',', ':')).encode()
    return dict(completed=len(simulation.completed_task_records), failed=sorted(simulation.failed_task_ids),
                pending=sorted(task.id for _, _, _, task in simulation.pending_tasks if not simulation._pending_task_removed(task)),
                end=simulation.current_time, records_sha256=hashlib.sha256(encoded).hexdigest())


def sample(kind, backend, result_path, profile=False):
    from amr_stress_resources import process_memory
    from simulator import Simulation
    cfg = configuration(kind) if kind != 'study' else None
    memory_start = process_memory(os.getpid())['private']
    with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as temporary:
        directory = Path(temporary)
        profiler = None
        if profile:
            import cProfile
            profiler = cProfile.Profile()
            profiler.enable()
        started = time.perf_counter()
        study_memory = []
        with contextlib.redirect_stdout(Quiet()):
            if kind == 'study':
                from amr_scenario_study import create_study, evaluate
                from tests.test_scenario_study import config
                path = directory / 'study.stress.json'
                create_study(config(), path, dict(workers=8, trial_budget=16))
                state = evaluate(path, runtime_backend=backend,
                    feedback=lambda message: study_memory.append(message.get('ram_bytes', 0)))
                signature = dict(order=list(state['results']), ranking=state['ranking'],
                    metrics={key: row['metrics'] for key, row in state['results'].items()}, coverage=state['coverage'])
                # Run keys identify executions, not numerical outcomes.
                for row in signature['metrics'].values():
                    row.pop('run_key', None)
                output = dict(trials=len(state['results']), sha256=hashlib.sha256(
                    json.dumps(signature, sort_keys=True).encode()).hexdigest())
                simulation = None
            else:
                simulation = Simulation(cfg, verbose=True, verbose_csv_path=str(directory / 'simulation_steps.csv'),
                    runtime_backend=backend, defer_exports=backend == 'compact')
                simulation.run()
                simulation.write_verbose_csv()
                if backend == 'reference':
                    simulation.write_visualiser_csv(str(directory / 'visualiser_steps.csv'))
                    for name in ('failed_tasks', 'transport_matrix', 'route_lengths', 'charger_estimate', 'scenario_impact'):
                        getattr(simulation, 'write_' + name + '_csv')(str(directory / (name + '.csv')))
                output = None
        elapsed = time.perf_counter() - started
        if profiler:
            profiler.disable()
        peak = process_memory(os.getpid())['peak']
        if study_memory:
            peak = max(peak, max(study_memory))
        if simulation is not None:
            output = outcome(simulation)
        bytes_before_view = sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())
        expansion = 0
        if simulation is not None and backend == 'compact':
            from amr_event_store import export_rows
            expanded = time.perf_counter()
            export_rows(simulation.event_store.path, directory / 'simulation_steps.csv', simulation._verbose_fieldnames())
            export_rows(simulation.event_store.path, directory / 'visualiser_steps.csv', simulation._visualiser_fieldnames(), playback_only=True)
            expansion = time.perf_counter() - expanded
        copied = None
        if profiler:
            import pstats
            stats = pstats.Stats(profiler)
            profiler.dump_stats(str(result_path.with_suffix('.prof')))
            copied = sum(value[3] for key, value in stats.stats.items() if key[2] == 'deepcopy')
        result = dict(kind=kind, backend=backend, wall_sec=elapsed, peak_bytes=peak,
            memory_start_bytes=memory_start, evidence_bytes=bytes_before_view, first_view_sec=expansion,
            outcome=output, profiled=profile, deepcopy_cumulative_sec=copied)
        result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')


def benchmark(output, kinds, repeats):
    records = []
    output.parent.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        for index in range(repeats):
            # Alternate execution order to reduce systematic thermal/order bias.
            for backend in (('reference', 'compact') if index % 2 == 0 else ('compact', 'reference')):
                path = ROOT / 'tmp' / f'compact-bench-{kind}-{backend}-{index}.json'
                environment = os.environ.copy()
                environment['PYTHONPATH'] = os.pathsep.join(value for value in sys.path if value)
                environment['PYTHONIOENCODING'] = 'utf-8'
                for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
                    environment[key] = '1'
                run = subprocess.run([getattr(sys, '_base_executable', sys.executable), str(Path(__file__).resolve()),
                    '--sample', kind, '--backend', backend, '--output', str(path)],
                    env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
                if run.returncode:
                    raise RuntimeError(run.stdout[-4000:])
                record = json.loads(path.read_text())
                records.append(record)
                print(f"{kind} {backend} {index + 1}/{repeats}: {record['wall_sec']:.3f}s, {record['peak_bytes']/1024**2:.1f} MiB", flush=True)
                output.write_text(json.dumps(dict(samples=records), indent=2), encoding='utf-8')
        selected = [row for row in records if row['kind'] == kind]
        expected = selected[0]['outcome']
        if any(row['outcome'] != expected for row in selected):
            raise ValueError(f'Outcome parity failed for {kind}')
    summaries = []
    for kind in kinds:
        summary = dict(kind=kind, outcome_parity=True)
        for backend in ('reference', 'compact'):
            selected = [row for row in records if row['kind'] == kind and row['backend'] == backend]
            summary[backend] = {key: statistics.median(row[key] for row in selected)
                for key in ('wall_sec', 'peak_bytes', 'evidence_bytes', 'first_view_sec')}
        summary['speedup'] = summary['reference']['wall_sec'] / summary['compact']['wall_sec']
        summary['peak_memory_reduction_percent'] = 100 * (1 - summary['compact']['peak_bytes'] / summary['reference']['peak_bytes'])
        summaries.append(summary)
    output.write_text(json.dumps(dict(samples=records, summaries=summaries), indent=2), encoding='utf-8')
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', choices=('deliveries', 'ltn', 'detailed', 'study'))
    parser.add_argument('--backend', choices=('reference', 'compact'), default='compact')
    parser.add_argument('--output', type=Path, default=ROOT / 'verification' / 'compact-benchmark.json')
    parser.add_argument('--kinds', default='deliveries,ltn,detailed,study')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--profile', action='store_true')
    arguments = parser.parse_args()
    if arguments.sample:
        sample(arguments.sample, arguments.backend, arguments.output, arguments.profile)
    else:
        benchmark(arguments.output, arguments.kinds.split(','), arguments.repeats)
