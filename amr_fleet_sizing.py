"""Sequential fleet trials using the normal engine and volatile event storage."""
from copy import deepcopy
import gc
import math
import sqlite3

from amr_memory_runs import check_cancelled, RunMemoryLimit
from amr_run_utilisation import FIELDS, summarise_utilisation


def run_trial(config, type_id, count, *, memory_limit, cancel=None, progress=None):
    from simulator import Simulation, TaskFailureStop

    check_cancelled(cancel)
    inputs = deepcopy(config)
    robot = next(row for row in inputs['amrs'] if row['id'] == type_id)
    robot['quantity'] = count
    simulation = None
    try:
        try:
            simulation = Simulation(inputs, verbose=True, defer_exports=True,
                memory_event_limit=memory_limit, cancel_requested=cancel,
                progress_callback=progress, console_progress=False, stop_on_task_failure=True)
            simulation.run()
        except TaskFailureStop as exc:
            check_cancelled(cancel)
            return dict(count=count, total=sum(int(row.get('quantity', 1)) for row in inputs['amrs']),
                        status='failed', failed=1, completed=None, pending=None,
                        utilisation_pct=None, fleet_utilisation_pct=None, first_failure=exc.record)
        check_cancelled(cancel)
        pending = len(getattr(simulation, '_evidence_pending_task_ids', []))
        complete = len(simulation.completed_task_records)
        status = ('incomplete' if simulation._evidence_run_status != 'finished' or pending else
                  'no_work' if not complete else 'passed')
        utilisation = None
        fleet_utilisation = None
        if status == 'passed':
            metadata = dict(frozen_inputs=inputs,
                            summary=dict(battery_amr_ids=[amr.id for amr in simulation.amrs]))
            summary = summarise_utilisation(simulation.event_store.iter_rows(FIELDS), metadata, cancel=cancel)
            ids = {f'{type_id}-{index + 1}' for index in range(count)}
            selected = [row['utilisation_pct'] for row in summary['amrs'] if row['id'] in ids]
            all_amrs = [row['utilisation_pct'] for row in summary['amrs']]
            if selected and all(value is not None for value in selected):
                utilisation = sum(selected) / len(selected)
            if all_amrs and all(value is not None for value in all_amrs):
                fleet_utilisation = sum(all_amrs) / len(all_amrs)
        return dict(count=count, total=len(simulation.amrs), status=status, failed=0,
                    completed=complete, pending=pending, utilisation_pct=utilisation,
                    fleet_utilisation_pct=fleet_utilisation, first_failure=None)
    except sqlite3.OperationalError as exc:
        if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL:
            raise RunMemoryLimit() from exc
        raise
    except MemoryError as exc:
        raise RunMemoryLimit() from exc
    finally:
        if simulation is not None:
            if not simulation.event_store.closed:
                simulation.event_store.close(flush=False)
            if simulation.routing_executor is not None:
                simulation.routing_executor.shutdown(wait=True, cancel_futures=True)
                simulation.routing_executor = None
        # The engine contains cycles; release one trial before constructing another.
        simulation = None
        gc.collect()


def search_fleet(config, type_id, start_count, max_count, target_pct=75., *,
                 memory_limit, cancel=None, progress=None):
    """Find the first pass/fail boundary for one type, keeping other types fixed.

    Reduce a passing starting count to its first failing neighbour. If the start
    fails, increase one at a time to the first pass within the explicit limit.
    Utilisation is informational and never changes the recommendation.
    """
    if type(start_count) is not int or type(max_count) is not int or not 0 <= start_count <= max_count:
        raise ValueError('Starting and maximum counts must be nonnegative whole counts, with start <= maximum.')
    if not math.isfinite(target_pct) or not 0 < target_pct <= 100:
        raise ValueError('Target utilisation must be greater than 0% and at most 100%.')
    if not any(row['id'] == type_id for row in config.get('amrs', [])):
        raise ValueError('Select a configured AMR type to size.')
    if memory_limit < 64 * 1024:
        raise RunMemoryLimit()
    result = dict(type_id=type_id, target_pct=target_pct, trials=[], recommendation=None,
                  status='searching', first_failing_count=None)
    best = None
    direction = None
    count = start_count
    try:
        while True:
            check_cancelled(cancel)
            if progress:
                progress(dict(kind='trial_start', count=count, label=f'Testing {type_id}: {count} AMRs'))
            def report(message):
                if progress:
                    progress(dict(kind='simulation', count=count, **message))
            trial = run_trial(config, type_id, count, memory_limit=memory_limit,
                              cancel=cancel, progress=report)
            result['trials'].append(trial)
            if progress:
                progress(dict(kind='trial_result', trial=trial))
            if trial['status'] in ('incomplete', 'no_work'):
                result['status'] = trial['status']
                break
            if trial['status'] == 'passed':
                best = count
                if direction == 1 or count == 0:
                    result.update(status='complete', recommendation=best)
                    break
                direction = -1
            else:
                result['first_failing_count'] = count
                if best is not None:
                    result.update(status='complete', recommendation=best)
                    break
                direction = 1
                if count == max_count:
                    result['status'] = 'limit'
                    break
            count += direction
    except InterruptedError:
        result['status'] = 'cancelled'
    return result
