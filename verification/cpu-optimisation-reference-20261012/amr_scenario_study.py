"""Reproducible bounded disruption studies over verified, independent project runs."""
from copy import deepcopy
from datetime import datetime, timedelta
import argparse
import csv
import json
import math
from pathlib import Path
import random
import uuid

from amr_project import atomic_write, configuration_bytes, digest, drawing_entries
from amr_project_runs import read_json, write_json
from amr_run_evidence import config_hash, file_hash, software_snapshot
from amr_run_review import verified_inputs, verified_events
from amr_simulation_inputs import simulation_horizon_seconds
from amr_simulation_modes import resolve_simulation_mode

EXECUTION_SETTINGS = ('workers', 'ram_limit_gib', 'reserve_ram_gib')


def search_settings(settings):
    return {key: value for key, value in settings.items() if key not in EXECUTION_SETTINGS}


def resources(config):
    """Each physical corridor appears once, even with separate reverse edges."""
    values = [('amr', str(r['id'])) for r in config.get('amrs', [])]
    values += [('lift', str(r['id'])) for r in config.get('lifts', [])]
    values += [('corridor', ' -> '.join(sorted((r['from'], r['to']))))
               for r in config.get('corridors', {}).get('edges', [])]
    values += [('corridor_node', str(r['name'])) for r in config.get('corridors', {}).get('nodes', [])
               if r.get('has_door')]
    return [list(r) for r in sorted(set(values))]


def default_settings(config):
    horizon = simulation_horizon_seconds(config) / 60
    return dict(assets=resources(config), durations_minutes=sorted({min(v, horizon) for v in (15, 30, 60, horizon)}),
                start_minute=0, end_minute=horizon, start_step_minutes=60,
                availability_percent=[0, 100], speed_percent=[25, 50, 75, 100],
                max_events=2, trial_budget=100, seed=0, workers=8, ram_limit_gib=16.0, reserve_ram_gib=8.0)


def validated_settings(config, settings):
    defaults = default_settings(config)
    result = {**defaults, **deepcopy(settings or {})}
    for key in ('max_events', 'trial_budget', 'seed'):
        if type(result[key]) is not int or result[key] < (0 if key == 'seed' else 1):
            raise ValueError(f'{key} must be a positive integer (seed may be zero).')
    if result['max_events'] > 8 or result['trial_budget'] > 100000:
        raise ValueError('Use at most eight simultaneous events and 100000 trials.')
    if type(result['workers']) is not int or not 1 <= result['workers'] <= 32:
        raise ValueError('Select between one and 32 CPU workers.')
    for key in ('ram_limit_gib', 'reserve_ram_gib'):
        if type(result[key]) not in (int, float) or not math.isfinite(result[key]) or result[key] <= 0:
            raise ValueError(f'{key} must be finite and positive.')
    for key in ('durations_minutes', 'availability_percent', 'speed_percent'):
        values = result[key]
        if (not isinstance(values, list) or not values or any(type(v) not in (int, float)
                or not math.isfinite(v) or v < 0 for v in values)):
            raise ValueError(f'{key} needs a list of finite nonnegative values.')
        if key == 'durations_minutes' and min(values) <= 0:
            raise ValueError('Durations must be positive.')
        if key != 'durations_minutes' and max(values) > 100:
            raise ValueError('Availability and speed percentages must be between 0 and 100.')
        result[key] = sorted(set(values))
    for key in ('start_minute', 'end_minute', 'start_step_minutes'):
        if type(result[key]) not in (int, float) or not math.isfinite(result[key]):
            raise ValueError(f'{key} must be finite.')
    if not 0 <= result['start_minute'] < result['end_minute'] <= defaults['end_minute']:
        raise ValueError('The search window must be inside the simulation period.')
    if result['start_step_minutes'] <= 0:
        raise ValueError('Start spacing must be positive.')
    available = {tuple(r) for r in defaults['assets']}
    if not isinstance(result['assets'], list) or not result['assets']:
        raise ValueError('Select at least one eligible asset.')
    if any(not isinstance(r, (list, tuple)) or len(r) != 2 or tuple(r) not in available for r in result['assets']):
        raise ValueError('An eligible asset no longer exists in this design.')
    result['assets'] = [list(r) for r in sorted({tuple(r) for r in result['assets']})]
    return result


def input_identity(config):
    from visualiser.models import JsonStore
    frozen = deepcopy(JsonStore(config).data)
    frozen.get('scenario_testing', {}).pop('stress_test', None)
    frozen.get('scenario_testing', {}).pop('study_evidence', None)
    for entry, _ in drawing_entries(frozen):
        entry['filepath'] = 'sha256:' + file_hash(entry['filepath'])
    # Ordering of generation categories affects deterministic request identity.
    return digest(configuration_bytes(frozen))


def domain(settings):
    count = math.ceil((settings['end_minute'] - settings['start_minute']) / settings['start_step_minutes'])
    if count * len(settings['durations_minutes']) > 100000:
        raise ValueError('Timing grid is too large; increase start spacing or reduce duration choices.')
    windows = sorted({(settings['start_minute'] + i * settings['start_step_minutes'],
                       min(settings['end_minute'], settings['start_minute'] + i * settings['start_step_minutes'] + duration))
                      for i in range(count) for duration in settings['durations_minutes']})
    effects = sorted({(0, 100) if availability == 0 or speed == 0 else (availability, speed)
                      for availability in settings['availability_percent'] for speed in settings['speed_percent']
                      if min(availability, speed) < 100})
    if not effects:
        raise ValueError('Select at least one outage or slowdown setting.')
    return windows, effects


def candidate_count(settings):
    windows, effects = domain(settings)
    assets, variants = len(settings['assets']), len(windows) * len(effects)
    return sum(math.comb(assets, k) * variants ** k for k in range(1, min(assets, settings['max_events']) + 1))


def candidate_at(settings, rank):
    """Unrank a finite domain without materializing all asset combinations."""
    windows, effects = domain(settings)
    size, variants = len(settings['assets']), len(windows) * len(effects)
    for k in range(1, min(size, settings['max_events']) + 1):
        block = math.comb(size, k) * variants ** k
        if rank < block:
            break
        rank -= block
    else:
        raise ValueError('Candidate rank outside the search domain.')
    combination_rank, variant_rank = divmod(rank, variants ** k)
    selected = []
    start = 0
    for remaining in range(k, 0, -1):
        for index in range(start, size - remaining + 1):
            block = math.comb(size - index - 1, remaining - 1)
            if combination_rank < block:
                selected.append(index)
                start = index + 1
                break
            combination_rank -= block
    result = []
    for asset in selected:
        variant_rank, option = divmod(variant_rank, variants)
        window, effect = divmod(option, len(effects))
        result.append([asset, window, effect])
    return result


def candidate_id(candidate):
    return config_hash(sorted(candidate))


def candidate_events(config, settings, candidate):
    windows, effects = domain(settings)
    origin = datetime.fromisoformat(config['simulation']['start_datetime'])
    events = []
    for asset, window, effect in candidate:
        kind, identity = settings['assets'][asset]
        begin, end = windows[window]
        availability, speed = effects[effect]
        events.append(dict(resource_type=kind, resource_ids=[identity], availability_percent=availability,
            speed_factor=speed / 100, start_datetime=(origin + timedelta(minutes=begin)).isoformat(),
            end_datetime=(origin + timedelta(minutes=end)).isoformat(), notes='Automated stress test'))
    return events


def scenario_config(config, events, name):
    result = deepcopy(config)
    result['scenario_testing'].update(enabled=bool(events), enhanced_logging=True, study_evidence=True,
        active_scenario=name if events else 'Normal operation', scenarios=[dict(name=name, events=deepcopy(events))] if events else [])
    result['simulation'].update(scenario_mode=bool(events), scenario_enhanced_logging=True)
    result['simulation'].update(parallel_routing=False, routing_worker_threads=1)
    return result


def baseline_identity(config):
    """Compare normal-operation inputs without study logging/execution metadata."""
    from visualiser.models import JsonStore
    normalized = JsonStore(config).data
    section = normalized.get('scenario_testing', {})
    if section.get('enabled') and section.get('active_scenario', 'Normal operation') != 'Normal operation':
        raise ValueError('A disruption run cannot supply the normal-operation baseline.')
    normalized = scenario_config(normalized, [], 'Normal operation')
    normalized['scenario_testing'] = dict(enabled=False, active_scenario='Normal operation',
                                         enhanced_logging=True, scenarios=[])
    normalized['simulation'] = dict(sorted(normalized['simulation'].items()))
    # Top-level key order and simulation-setting order do not affect demand;
    # preserve the nested generation-rule order used for deterministic task IDs.
    return input_identity(dict(sorted(normalized.items())))


def verify_trial_inputs(state, record):
    manifest, actual, _, _ = verified_events(record['directory'], drawings=True, allow_partial=True)
    if manifest['software']['sha256'] != state['software_sha256']:
        raise ValueError('Trial software differs from the study software.')
    if record.get('reused'):
        if (record['id'] != 'baseline' or record['kind'] != 'baseline' or record['events']
                or manifest['status'] != 'complete'
                or baseline_identity(actual) != baseline_identity(scenario_config(state['config'], [], 'Normal operation'))):
            raise ValueError('Reused baseline does not match the study inputs.')
    else:
        expected = scenario_config(state['config'], record['events'], record['name'])
        if input_identity(actual) != input_identity(expected):
            raise ValueError('Saved trial does not match its study inputs.')
    return manifest


def reusable_baseline(state, *, feedback=None, cancelled=lambda: False):
    """Find verified evidence among linked and discovered source-project runs."""
    from amr_project import Project
    from amr_project_runs import inspect_run, MANIFEST
    source = state.get('source_project')
    if not source:
        return None
    try:
        project = Project.open(source)
        if project.project_id != state['source_project_id']:
            return None
        stored = {project.resolve_results_location(ref['location']): ref for ref in project.external_results['runs']}
        candidates = set(stored) | {p.parent.resolve() for p in project.results_root().glob('*/' + MANIFEST)}
    except (OSError, ValueError):
        return None
    eligible = []
    for directory in candidates:
        if cancelled():
            return None
        try:
            manifest = inspect_run(directory, project, reference=stored.get(directory))
            if manifest['status'] == 'complete' and manifest['software']['sha256'] == state['software_sha256']:
                eligible.append((manifest.get('completed_at', ''), str(directory), directory))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for _, _, directory in sorted(eligible, reverse=True):
        if cancelled():
            return None
        if feedback:
            feedback(dict(type='phase', phase='Checking existing simulation for baseline reuse'))
        record = dict(id='baseline', kind='baseline', name='Normal operation', events=[],
                      directory=str(directory), project=str(project.path), reused=True)
        try:
            verify_trial_inputs(state, record)
            record['metrics'] = run_metrics(directory)
            return record
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def run_metrics(directory, baseline=None):
    manifest, config, log, _ = verified_events(directory, allow_partial=True)
    evidence = read_json(str(log) + '.run.json')
    released, failed, idle = set(), set(), set()
    logged_complete, complete, obligations = {}, {}, {}
    from amr_event_store import iter_events
    for row in iter_events(log, ('event_type', 'task_id', 'sim_time_sec', 'details'), event_types=(
            'task_released', 'task_complete', 'multi_stop_task_complete', 'stress_task_completion',
            'task_failed', 'stress_task_obligation')):
        typ, identity = row['event_type'], row['task_id']
        if typ == 'task_released':
            released.add(identity)
        elif typ in ('task_complete', 'multi_stop_task_complete'):
            logged_complete[identity] = float(row['sim_time_sec'])
        elif typ == 'stress_task_completion':
            time = json.loads(row['details'])['completion_time_sec']
            if type(time) not in (float, int) or not math.isfinite(time) or time < 0 or identity in complete:
                raise ValueError('Invalid precise completion evidence.')
            complete[identity] = time
        elif typ == 'task_failed':
            failed.add(identity)
        elif typ == 'stress_task_obligation':
            detail = json.loads(row['details'])
            # Queued generated work can fail its deferral limit before the
            # generator releases it. It still represents required service.
            released.add(identity)
            if detail['idle']:
                idle.add(identity)
                continue
            key = detail['key']
            if key in obligations:
                raise ValueError('Ambiguous service obligation identity.')
            obligations[key] = dict(task_id=identity, signature=detail['signature'],
                expected_return=detail['expected_return'])
    if set(complete) != set(logged_complete) or any(round(time, 3) != logged_complete[key] for key, time in complete.items()):
        raise ValueError('Precise task completion times do not match the event log.')
    pending = set(evidence['summary'].get('pending_task_ids', []))
    if (set(complete) != set(evidence['summary']['completed_task_ids']) or failed != set(evidence['summary']['failed_task_ids'])
            or set(complete) & failed or not (set(complete) | failed) <= released
            or not pending <= released - set(complete) - failed
            or (released - set(complete) - failed - pending) - idle):
        raise ValueError('Task outcomes do not reconcile with the verified run.')
    for task in obligations.values():
        task['completion'] = complete.get(task['task_id'])
    if not obligations:
        raise ValueError('No service work was released in this study period.')
    obligation_ids = {task['task_id'] for task in obligations.values()}
    if not obligation_ids <= released or 'stress_task_obligations_v1' not in evidence.get('event_capabilities', []):
        raise ValueError('Study service obligations lack matching release evidence.')
    horizon = simulation_horizon_seconds(config)
    # The period bounds new demand, not completion. Released service and its
    # configured returns drain under the simulator's assignment deferral limit.
    unmet = {key for key, task in obligations.items() if task['completion'] is None}
    for task in obligations.values():
        if task['expected_return'] and task['expected_return'] not in obligations:
            unmet.add(task['expected_return'])
    delay = 0.0
    if baseline:
        for key, original in baseline['obligations'].items():
            actual = obligations.get(key)
            if actual is None or actual['signature'] != original['signature']:
                unmet.add(key)
            elif actual['completion'] is not None:
                delay += max(0, actual['completion'] - original['completion'])
    late = sum(t > horizon + 1e-9 for t in complete.values())
    passed = manifest['status'] == 'complete' and not failed and not pending and not unmet
    return dict(passed=passed, obligations=obligations, unmet=sorted(unmet), unmet_count=len(unmet),
        added_delay_sec=delay, latest_completion_sec=max(complete.values(), default=0),
        completed=len(complete), failed=len(failed), pending=len(pending), late=late,
        status=manifest['status'], run_key=manifest['run_key'])


def ranking_key(record):
    metrics = record['metrics']
    return (-metrics['added_delay_sec'], -metrics['latest_completion_sec'], record['id'])


def refresh_summary(state):
    trials = [r for r in state['results'].values() if r['kind'] != 'baseline']
    passing = sorted((r for r in trials if r['metrics']['passed']), key=ranking_key)
    state['ranking'] = [r['id'] for r in passing]
    state['worst_passing'] = passing[0]['id'] if passing else None
    corridors = sorted((r for r in trials if r['kind'] == 'corridor'), key=lambda r:
        (-r['metrics']['unmet_count'], -r['metrics']['added_delay_sec'], r['id']))
    state['corridor_ranking'] = [r['id'] for r in corridors]
    windows, effects = domain(state['settings'])
    tested = {candidate_id(r['candidate']) for r in trials if r.get('candidate')}
    # Corridor sweep tests can also be members of the combined domain.
    for r in corridors:
        asset = ['corridor', r['corridor']]
        if asset in state['settings']['assets'] and (0, state['horizon_sec'] / 60) in windows and (0, 100) in effects:
            tested.add(candidate_id([[state['settings']['assets'].index(asset),
                windows.index((0, state['horizon_sec'] / 60)), effects.index((0, 100))]]))
    state['coverage'] = dict(candidate_count=candidate_count(state['settings']), tested_candidates=len(tested),
        combined_trials=sum(r['kind'] == 'combined' for r in trials),
        corridor_trials=len(corridors), exhaustive=len(tested) == candidate_count(state['settings']))


def create_study(config, path, settings=None, *, project=None):
    from visualiser.models import JsonStore
    frozen = deepcopy(JsonStore(config).data)
    if resolve_simulation_mode(frozen)['mode'] != 'simple':
        raise ValueError('Automated stress testing currently requires Simple mode. Detailed scenario interactions are not supported.')
    settings = validated_settings(frozen, settings)
    domain(settings)
    identity = input_identity(frozen)
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Choose a new study file; existing studies must be opened for resume.')
    path.parent.mkdir(parents=True, exist_ok=True)
    root = path.parent / ('stress-' + uuid.uuid4().hex[:12])
    root.mkdir()
    for entry, suffix in drawing_entries(frozen):
        source = Path(entry['filepath'])
        target = root / (file_hash(source) + suffix)
        atomic_write(target, source.read_bytes())
        entry['filepath'] = str(target)
    state = dict(version=1, status='ready', root=str(root), config=frozen, settings=settings,
        source_identity=identity, software_sha256=software_snapshot()['sha256'],
        settings_sha256=config_hash(search_settings(settings)),
        horizon_sec=simulation_horizon_seconds(frozen), results={}, sample_queue=[], sample_generated=False,
        sample_sha256=config_hash([]))
    if project is not None and project.path is not None:
        state.update(source_project=str(project.path.resolve()), source_project_id=project.project_id)
    refresh_summary(state)
    write_json(path, state)
    return state


def validate_study(state, config=None, *, verify_results=True, feedback=None):
    if state.get('version') != 1 or state['source_identity'] != input_identity(state['config']):
        raise ValueError('Frozen study configuration or drawing contents changed; create a new study.')
    if state['software_sha256'] != software_snapshot()['sha256']:
        raise ValueError('Software changed; create a new study. Previous evidence remains available.')
    if config is not None and state['source_identity'] != input_identity(config):
        raise ValueError('Design inputs changed; create a new study.')
    if (validated_settings(state['config'], state['settings']) != state['settings']
            or config_hash(search_settings(state['settings'])) != state['settings_sha256']):
        raise ValueError('Study search settings changed.')
    if (state['horizon_sec'] != simulation_horizon_seconds(state['config'])
            or config_hash(state['sample_queue']) != state['sample_sha256']):
        raise ValueError('Study horizon or saved search schedule changed.')
    if not verify_results:
        return
    windows, effects = domain(state['settings'])
    for index, (identity, record) in enumerate(state['results'].items(), 1):
        if feedback:
            feedback(dict(type='phase', phase=f"Verifying saved trial {index} of {len(state['results'])}"))
        if record['id'] != identity:
            raise ValueError('Trial identity differs from its saved study record.')
        candidate = record.get('candidate')
        if record['kind'] == 'combined' and not candidate:
            raise ValueError('Combined trial is missing its search candidate.')
        if candidate:
            if (not 1 <= len(candidate) <= state['settings']['max_events']
                    or any(len(row) != 3 or any(type(v) is not int for v in row)
                           or not 0 <= row[0] < len(state['settings']['assets'])
                           or not 0 <= row[1] < len(windows) or not 0 <= row[2] < len(effects) for row in candidate)
                    or len({row[0] for row in candidate}) != len(candidate)):
                raise ValueError('Trial candidate is outside the frozen search domain.')
            expected_events = candidate_events(state['config'], state['settings'], candidate)
            without_notes = lambda events: [{key: value for key, value in event.items() if key != 'notes'} for event in events]
            if without_notes(record['events']) != without_notes(expected_events):
                raise ValueError('Trial events differ from their search candidate.')
            if record['kind'] == 'combined' and identity != candidate_id(candidate):
                raise ValueError('Combined candidate identity changed.')
        verify_trial_inputs(state, record)
        fresh = run_metrics(record['directory'], None if record['kind'] == 'baseline' else state['results']['baseline']['metrics'])
        if fresh != record['metrics']:
            raise ValueError('Saved trial metrics do not match their evidence.')


def neighbours(settings, candidate):
    windows, effects = domain(settings)
    for i, (asset, window, effect) in enumerate(candidate):
        begin, end = windows[window]
        # Adjacent start and duration values, then adjacent severity choices.
        starts = sorted({w[0] for w in windows})
        lengths = sorted({w[1] - w[0] for w in windows if w[0] == begin})
        alternatives = []
        for values, value, axis in [(starts, begin, 'start'), (lengths, end - begin, 'duration')]:
            pos = values.index(value)
            for nxt in (pos - 1, pos + 1):
                if 0 <= nxt < len(values):
                    wanted = (values[nxt], values[nxt] + end - begin) if axis == 'start' else (begin, begin + values[nxt])
                    if wanted in windows:
                        alternatives.append((windows.index(wanted), effect))
        alternatives += [(window, nxt) for nxt in (effect - 1, effect + 1) if 0 <= nxt < len(effects)]
        for new_window, new_effect in alternatives:
            result = deepcopy(candidate)
            result[i] = [asset, new_window, new_effect]
            yield result


def evaluate(path, cancel=None, progress=None, feedback=None, *, runtime_backend='compact'):
    from amr_stress_execution import evaluate_parallel
    return evaluate_parallel(path, cancel=cancel, progress=progress, feedback=feedback, runtime_backend=runtime_backend)


def main(path):
    from amr_stress_execution import emit
    evaluate(path, feedback=emit)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    raise SystemExit(main(parser.parse_args().study))
