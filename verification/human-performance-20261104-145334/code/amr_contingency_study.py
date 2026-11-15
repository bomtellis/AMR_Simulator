"""Reproducible, resumable search for a passing human contingency roster."""
from copy import deepcopy
import json
from pathlib import Path

from amr_contingency_inputs import validate_settings, shift_candidates, peak_people
from amr_contingency_runtime import simulate_candidate, StudyCancelled
from amr_project_runs import write_json, read_json
from amr_run_evidence import config_hash, software_snapshot
from amr_scenario_study import study_lock

VARIANTS = ('dedicated_current', 'shared_current', 'dedicated_buffered', 'shared_buffered')


def project_identity(config):
    value = deepcopy(config)
    value.pop('human_contingency', None)
    # Drawings are presentation assets; route geometry is already in the graph.
    # Saved projects and runs relocate these paths without changing the workload.
    from amr_project import drawing_entries
    for entry, _suffix in drawing_entries(value):
        entry['filepath'] = '<drawing>'
    return config_hash(value)


def create_study(config, settings, path):
    settings = validate_settings(config, settings)
    path = Path(path)
    if path.exists():
        raise ValueError('Choose a new study filename; existing evidence is not overwritten.')
    frozen = deepcopy(config)
    frozen.pop('human_contingency', None)
    state = dict(schema_version=1, kind='human_contingency', configuration=frozen, settings=settings,
        config_sha256=project_identity(frozen), workload_sha256=config_hash(dict(config=frozen, services=settings['services'])),
        software=software_snapshot(), status='ready', variants={}, seed=settings['seed'])
    state['inputs_sha256'] = config_hash(dict(config=frozen, settings=settings))
    save_study(path, state)
    return state


def save_study(path, state):
    value = deepcopy(state)
    value.pop('evidence_sha256', None)
    value['evidence_sha256'] = config_hash(value)
    write_json(Path(path), value)


def load_study(path, config=None, *, for_resume=False):
    state = read_json(Path(path))
    if state.get('schema_version') != 1 or state.get('kind') != 'human_contingency':
        raise ValueError('Not a supported human contingency study.')
    bound = {k:v for k,v in state.items() if k != 'evidence_sha256'}
    if config_hash(bound) != state.get('evidence_sha256'):
        raise ValueError('Study evidence has changed or is incomplete.')
    if state['inputs_sha256'] != config_hash(dict(config=state['configuration'], settings=state['settings'])):
        raise ValueError('Study inputs no longer match their recorded identity.')
    if config is not None and state['config_sha256'] != project_identity(config):
        raise ValueError('Study is stale: the project configuration has changed. Create a new study.')
    if for_resume and state['software']['sha256'] != software_snapshot()['sha256']:
        raise ValueError('Study is stale: application software has changed. Create a new study.')
    return state


def rank(result):
    return (result['staffed_hours'], result['peak_people'], result['trips'], result['distance_m'])


def roster_key(roster):
    return config_hash(sorted(roster, key=lambda r:(r['pool'],r['start'],r['end'])))


def neighbours(config, settings, arrangement, current):
    roster = [{k:v for k,v in r.items() if k != 'id'} for r in current['roster']]
    candidates = shift_candidates(config, settings, arrangement)
    maximum = settings['shifts']['max_people']
    if current['passed']:
        for i in range(len(roster)):
            yield roster[:i]+roster[i+1:]
        for i, old in enumerate(roster):
            nearby = [c for c in candidates if c['pool'] == old['pool'] and
                      abs(c['start']-old['start']) <= 3600 and c['end']-c['start'] <= old['end']-old['start']]
            for c in sorted(nearby, key=lambda r:(r['end']-r['start'], abs(r['start']-old['start']),r['start'])):
                if c != old:
                    trial = roster[:i]+[c]+roster[i+1:]
                    if peak_people(trial) <= maximum:
                        yield trial
    else:
        unmet = current['unresolved']
        def coverage(c):
            return sum(1 for t in unmet if (c['pool'] == 'shared' or c['pool'] == t['service']) and
                       c['start'] <= t['deadline'] and c['end'] > t['release'])
        ordered = sorted(candidates, key=lambda c:(-coverage(c)/((c['end']-c['start'])/3600), c['start'], c['pool']))
        # Evaluate alternative placements before increasing staffing again.
        for c in ordered:
            if coverage(c) and peak_people(roster+[c]) <= maximum:
                yield roster+[c]


def evaluate_study(path, *, cancelled=lambda:False, progress=lambda value:None):
    path = Path(path)
    with study_lock(path):
        state = load_study(path, for_resume=True)
        settings, config = state['settings'], state['configuration']
        cancel_path = Path(str(path)+'.cancel')
        def stopping():
            return cancelled() or cancel_path.exists()
        state['status'] = 'running'
        save_study(path,state)
        try:
            for name in VARIANTS:
                arrangement, timing = name.split('_')
                record = state['variants'].setdefault(name, dict(trials=0, tested=[], status='ready',
                    best=None, current=None, frontier=[]))
                if record['status'] == 'complete':
                    continue
                budget = settings['trial_budget']
                while record['trials'] < budget:
                    if stopping():
                        raise StudyCancelled()
                    if record['current'] is None:
                        roster = []
                    else:
                        if not record['frontier']:
                            record['frontier'] = [r for r in neighbours(config, settings, arrangement, record['current'])
                                                   if roster_key(r) not in record['tested']][:24]
                        if not record['frontier']:
                            record['status'] = 'complete'
                            break
                        roster = record['frontier'][0]
                    result = simulate_candidate(config, settings, roster, buffered=timing == 'buffered', cancelled=stopping)
                    if record['frontier']:
                        record['frontier'].pop(0)
                    record['trials'] += 1
                    record['tested'].append(roster_key(roster))
                    old = record['current']
                    improve = (old is None or (result['passed'] and (not old['passed'] or rank(result)<rank(old))) or
                               (not result['passed'] and not old['passed'] and
                                (len(result['unresolved']), -result['completed']) < (len(old['unresolved']), -old['completed'])))
                    if improve:
                        record['current'] = result
                        record['frontier'] = []
                    if result['passed'] and (record['best'] is None or rank(result)<rank(record['best'])):
                        record['best'] = result
                    # Permit extra simultaneous workers when one extra shift alone
                    # cannot unlock a shared stock/return cycle.
                    if not record['frontier'] and not improve and old and not old['passed']:
                        if len(roster)>len(old['roster']):
                            record['current'] = result
                    record['status'] = 'running'
                    save_study(path,state)
                    progress(dict(variant=name, trials=record['trials'], budget=budget,
                                  passed=result['passed'], unresolved=len(result['unresolved']),
                                  best_hours=record['best']['staffed_hours'] if record['best'] else None))
                if record['status'] != 'complete':
                    record['status'] = 'budget_exhausted'
                save_study(path,state)
            state['status'] = 'complete' if all(r['status']=='complete' for r in state['variants'].values()) else 'budget_exhausted'
        except StudyCancelled:
            state['status'] = 'cancelled'
        except Exception as exc:
            state['status'] = 'failed'
            state['error'] = str(exc)
            save_study(path,state)
            raise
        save_study(path,state)
        return state


def main(path):
    import sys
    try:
        state = evaluate_study(path, progress=lambda v:print('CONTINGENCY '+json.dumps(v), flush=True))
        print('CONTINGENCY '+json.dumps(dict(status=state['status'])), flush=True)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
